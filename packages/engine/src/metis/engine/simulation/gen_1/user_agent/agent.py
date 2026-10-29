"""Core user agent logic for simulating persona-driven interactions."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from openai import APIError
from pydantic import BaseModel

from metis.core.logging import get_logger

from ...llm_calls import parse_completion
from ...model_settings import llm_client, sampling_options, user_agent_settings
from ...user_context import persona_text, scenario_text
from ..types import (
    ActionResult,
    ActionSlot,
    Artifact,
    Observation,
    UserAgentInput,
    UserAgentOutput,
)
from .prompts import (
    OPENING_TURN_PROMPT,
    RESPONSE_TURN_PROMPT,
    SYSTEM_PROMPT_TEMPLATE,
)

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

    from metis.core.model_settings import RoleSettings

    from ...llm_calls import LLMCallLog
    from ...types import Persona, Scenario

logger = get_logger()

MAX_HISTORY_TURNS = 20


def _render_available_actions(available_actions: list[ActionSlot] | None) -> str:
    """Render offered slots into the prompt's Available Actions block.

    Returns an empty string when there are none so the section disappears.
    """
    if not available_actions:
        return ""
    action_lines = ["Available actions:"]
    for slot in available_actions:
        parts = f'  - id: "{slot.id}", kind: "{slot.kind}", label: "{slot.label}"'
        if slot.options:
            parts += f", options: {slot.options}"
        if slot.required is not None:
            parts += f", required: {'true' if slot.required else 'false'}"
        action_lines.append(parts)
    return "\n" + "\n".join(action_lines) + "\n"


def _render_observed_actions(available_actions: list[ActionSlot] | None) -> str:
    """Render the three states of ``Observation.available_actions``.

    A list of slots renders as the slot list; ``[]`` says the target offers
    nothing this turn; ``None`` says nobody looked. All three must be
    distinguishable, because the persona has no other source for what it may
    do next and an absent block reads to it as "nothing on offer" — so
    rendering ``[]`` and ``None`` the same way tells it its controls were
    withdrawn when in fact nobody checked.

    Delegates the non-empty case rather than formatting slots itself, so the
    opening turn and every later turn describe the same slot identically.
    """
    if available_actions is None:
        return "\nThe actions on offer this turn could not be determined.\n"
    if not available_actions:
        return "\nNo actions are on offer this turn.\n"
    return _render_available_actions(available_actions)


def _artifact_line(art: Artifact) -> str:
    """One registry line: id, name, a direction/turn tag, then the description."""
    desc = art.content_description or "(no description available)"
    if art.source == "fixture":
        tag = "fixture"
    elif art.at_simulated_turn is not None:
        tag = f"delivered turn {art.at_simulated_turn}"
    else:
        tag = "delivered"
    line = f'  - id: "{art.id}", name: "{art.name}" ({tag}): {desc}'
    if art.state_description:
        line += f" [{art.state_description}]"
    return line


def _render_artifacts(artifacts: dict[str, Artifact] | None) -> str:
    """Render the cumulative artifact registry, grouped by direction.

    Two labelled groups keep the persona from mistaking its own uploaded input
    for a target deliverable. Same-named files are disambiguated by the per-line
    tag (source + at_simulated_turn). Compact and description-only: never the uri or the
    bytes. Empty string when there are none so the section disappears.

    The delivered group is presented as exhaustive, which is what lets the
    persona disbelieve a file named only in the target's prose. Stated as
    absence rather than as a count on purpose: ``Artifact.external_id`` is
    optional, and a file reported without one can appear under several record
    ids, so any count would be wrong (see :meth:`UserAgent._merge_artifacts`).

    That exhaustiveness claim is why an entry is excluded unless
    ``state == "received"``: an ``unfetched`` artifact is a file the target
    has that this runner failed to download, recorded so the failure is
    auditable and the download retried, and an ``unavailable`` artifact is one
    there is nothing left to retry for — a path-bearing ``unfetched`` record is
    excluded just the same as one with no ``path`` at all. Listing either here
    would assert the persona received a file that never arrived — the same
    false pass the closure sentence exists to prevent (issue #337). The persona
    still hears about the failure through ``Observation.response_notices``, in
    terms a real user could perceive.
    """
    if not artifacts:
        return ""
    uploaded = [a for a in artifacts.values() if a.source == "fixture"]
    delivered = [
        a for a in artifacts.values() if a.source != "fixture" and a.state == "received"
    ]
    lines: list[str] = []
    if uploaded:
        lines.append(
            "Files you've uploaded to the assistant. These are your own inputs, "
            "not deliverables:"
        )
        lines.extend(_artifact_line(art) for art in uploaded)
    if delivered:
        lines.append(
            "Files the assistant has delivered to you so far. Treat each as a "
            "real file you have received — do NOT claim you got nothing, and do "
            "NOT demand it be pasted inline; judge sufficiency from the "
            "descriptions. This is every file you have received: a file the "
            "assistant's message claims to have delivered but which is absent "
            "here did not reach you:"
        )
        lines.extend(_artifact_line(art) for art in delivered)
    if not lines:
        # Every artifact was filtered out (e.g. the only entries are failed
        # downloads). Same contract as the no-artifacts case: no section at all,
        # rather than two bare newlines in the middle of the prompt.
        return ""
    return "\n" + "\n".join(lines) + "\n"


def _render_problems(results: list[ActionResult], notices: list[str]) -> str:
    """Render prior-turn problems into the prompt's problem block.

    Two kinds share one block: an action of the persona's that did not happen,
    and a problem with the reply that no submitted action accounts for. The
    action rows come first because they are about the persona's own choices,
    and they carry the ``retryable`` hint so it can tell "try that again" from
    "that will never work".

    Withheld rows are rendered like any other failure. ``withheld`` marks a
    rejection made by METIS rather than by the target, which matters to the
    report's blame attribution and not at all here: an action that did not
    happen did not happen, and a persona that is not told proceeds believing
    it did.

    Returns an empty string when there is nothing to report so the section
    disappears.
    """
    failed = [row for row in results if not row.succeeded]
    if not failed and not notices:
        return ""
    lines = ["Problems reported on your previous turn — take them into account:"]
    for row in failed:
        # 1-based: nothing else in the prompt exposes a zero-based index, and
        # the persona counts the actions it asked for from one.
        line = f"  - action {row.action_index + 1}: {row.detail}"
        if row.retryable is True:
            line += " (you may try this again)"
        elif row.retryable is False:
            line += " (trying this again will not help)"
        lines.append(line)
    for notice in notices:
        lines.append(f"  - {notice}")
    return "\n" + "\n".join(lines) + "\n"


class HistoryRole(StrEnum):
    """Roles in the user-agent conversation history."""

    USER_AGENT = "user_agent"
    TARGET = "target"


class HistoryEntry(BaseModel, frozen=True):
    """A single entry in the conversation history."""

    role: HistoryRole
    content: str


class UserAgent:
    """Simulates a user persona interacting with an AI assistant."""

    def __init__(
        self,
        persona: Persona,
        scenario: Scenario,
        *,
        llm_log: LLMCallLog,
        settings: RoleSettings | None = None,
    ) -> None:
        """Initialize with persona definition and scenario description.

        :param persona: The persona driving the simulated user.
        :param scenario: The experiment scenario defining the goal.
        :param llm_log: The trial's LLM-call log; every attempt at every call
            appends a row.
        :param settings: The user agent role. Unset, it resolves from the environment.
        """
        self.settings = settings or user_agent_settings()
        self.persona = persona
        self.scenario = scenario
        self.conversation_history: list[HistoryEntry] = []
        self.turn_count = 0
        # Cumulative registry of artifacts surfaced to the persona, keyed by
        # target-side identity where there is one (see _merge_artifacts, which
        # populates it turn-by-turn). The keys are internal: every consumer
        # reads .values().
        self._artifacts: dict[str, Artifact] = {}
        self._llm_log = llm_log
        # Retries go through parse_completion so each attempt is logged.
        self.client = llm_client(self.settings)
        self._system_prompt = self._build_system_prompt()

    async def generate_opening(self) -> UserAgentOutput:
        """Generate the first message to start the conversation."""
        logger.info(
            "[user_agent] Generating opening message (persona=%s, model=%s)...",
            self.persona.id,
            self.settings.model,
        )
        opening_slots = [
            ActionSlot(id=name, kind="file_upload", label=f"Attach file '{name}'")
            for name in self.scenario.fixtures
        ]
        opening_prompt = OPENING_TURN_PROMPT.format(
            available_actions_section=_render_available_actions(opening_slots or None),
        )
        response = await self._call_llm(opening_prompt)
        self.turn_count += 1
        self.conversation_history.append(
            HistoryEntry(role=HistoryRole.USER_AGENT, content=response.message)
        )
        logger.info("[user_agent] === OPENING TURN ===")
        if response.reasoning:
            logger.info("[user_agent]   Reasoning: %s", response.reasoning)
        logger.info("[user_agent]   Decision: %s", response.decision)
        logger.info("[user_agent]   Message: %s", response.message[:200])
        if response.actions:
            logger.info(
                "[user_agent]   Actions: %s",
                [a.model_dump() for a in response.actions],
            )
        return response

    async def generate_response(self, turn_payload: UserAgentInput) -> UserAgentOutput:
        """Given the target's response, generate the user's next message.

        :param turn_payload: Structured payload containing the target's
            observation and optional session metadata.
        """
        observation = turn_payload.observation
        self._merge_artifacts(observation)
        target_message = observation.text
        available_actions = observation.available_actions

        logger.info(
            "[user_agent] Generating response (turn=%d, history=%d msgs, target_text=%d chars)...",
            self.turn_count + 1,
            len(self.conversation_history),
            len(target_message),
        )
        logger.info("[user_agent]   Target said: %s", target_message[:300])

        self.conversation_history.append(
            HistoryEntry(role=HistoryRole.TARGET, content=target_message)
        )

        # Build the turn-specific prompt
        user_prompt = self._build_user_prompt(
            target_message,
            available_actions=available_actions,
            action_results=observation.action_results,
            response_notices=observation.response_notices,
            artifacts=self._artifacts,
        )

        # Call LLM
        response = await self._call_llm(user_prompt)
        self.turn_count += 1

        self.conversation_history.append(
            HistoryEntry(role=HistoryRole.USER_AGENT, content=response.message)
        )

        logger.info("[user_agent] === TURN %d DECISION ===", self.turn_count)
        if response.reasoning:
            logger.info("[user_agent]   Reasoning: %s", response.reasoning)
        logger.info("[user_agent]   Decision: %s", response.decision)
        logger.info("[user_agent]   Message: %s", response.message[:200])
        if response.actions:
            logger.info(
                "[user_agent]   Actions: %s",
                [a.model_dump() for a in response.actions],
            )
        return response

    def _build_system_prompt(self) -> str:
        """Build the system prompt that instructs the LLM to act as this persona."""
        if self.scenario.fixtures:
            lines = [
                "\n## Files to Upload",
                "The following files are staged and ready to upload. Attach them "
                "with `upload_file` actions in your **first message**. "
                "Do NOT upload any file not in this list:",
            ]
            for f in self.scenario.fixtures:
                lines.append(f"- {f}")
            fixtures_section = "\n".join(lines) + "\n"
        else:
            fixtures_section = ""
        return SYSTEM_PROMPT_TEMPLATE.format(
            persona_description=persona_text(
                self.persona.description, self.persona.metadata
            ),
            scenario_description=scenario_text(
                self.scenario.description, self.scenario.metadata
            ),
            fixtures_section=fixtures_section,
        )

    def _merge_artifacts(self, observation: Observation) -> None:
        """Fold this turn's artifacts into the cumulative registry.

        Dedup is by the file's identity on the target's side rather than by the
        record: ``Artifact.id`` is minted per record while ``external_id`` names
        the file itself (see :class:`~metis.core.artifacts.Artifact`), so keying
        on the record id lets one file occupy two slots. A runner may report the
        same file on more than one turn — a retrieval that failed is expected to
        be retried — so a single file can arrive first as a record with no
        ``path`` and later as one that has the file, and keyed by record id both
        would persist for the rest of the run.

        ``source`` joins ``external_id`` in the key because the two directions
        are rendered as separate groups and nothing promises a target draws the
        ids for files it was given and files it produced from disjoint
        namespaces. Collapsing the two would relabel the persona's own input as
        something the assistant delivered.

        A held record already at ``state == "received"`` is never displaced by
        an incoming record that is not, so which of the two arrives last does
        not decide what the persona is told it received — the deciding factor
        is ``state``, not whether a ``path`` is present. A held ``"unfetched"``
        record can carry a non-``None`` ``path`` and still be replaced by a
        later record, since it is ``state``, not ``path``, that is checked.

        ``external_id`` is optional, and a record without one has no identity to
        key on: it falls back to its own id, which means repeated reports of one
        such file cannot be collapsed. That is why the delivered-files header
        states absence rather than a count (see :func:`_render_artifacts`).
        """
        for artifact in observation.artifacts:
            key = (
                f"{artifact.source}:{artifact.external_id}"
                if artifact.external_id is not None
                else artifact.id
            )
            held = self._artifacts.get(key)
            if (
                held is not None
                and held.state == "received"
                and artifact.state != "received"
            ):
                continue
            self._artifacts[key] = artifact

    def _build_user_prompt(
        self,
        target_message: str,
        available_actions: list[ActionSlot] | None = None,
        action_results: list[ActionResult] | None = None,
        response_notices: list[str] | None = None,
        artifacts: dict[str, Artifact] | None = None,
    ) -> str:
        """Build the turn-specific instruction prompt (excludes history, which
        is conveyed structurally via multi-turn contents)."""
        return RESPONSE_TURN_PROMPT.format(
            target_message=target_message,
            problems_section=_render_problems(
                action_results or [], response_notices or []
            ),
            available_actions_section=_render_observed_actions(available_actions),
            artifacts_section=_render_artifacts(artifacts),
            turn_number=self.turn_count + 1,
        )

    def _build_messages(self, user_prompt: str) -> list[ChatCompletionMessageParam]:
        """Build OpenAI chat messages from conversation history.

        Role mapping is inverted relative to the domain: this LLM *plays* the
        user, so its own prior outputs are "assistant" while the target's
        messages (the thing it reacts to) are "user".

        :param user_prompt: The turn-specific instruction appended as the
            final "user" message.
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._system_prompt},
        ]
        recent_history = self.conversation_history[-MAX_HISTORY_TURNS:]
        for entry in recent_history:
            if entry.role == HistoryRole.USER_AGENT:
                messages.append({"role": "assistant", "content": entry.content})
            else:
                messages.append({"role": "user", "content": entry.content})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    async def _call_llm(self, user_prompt: str) -> UserAgentOutput:
        """Call the LLM with structured output enforcement.

        The OpenAI API guarantees the response conforms to UserAgentOutput's
        schema, so no manual JSON parsing or retries are needed.
        """
        messages = self._build_messages(user_prompt)
        options = sampling_options()
        logger.debug(
            "[user_agent] Calling LLM: model=%s, messages=%d, options=%s",
            self.settings.model,
            len(messages),
            options,
        )

        try:
            response = await parse_completion(
                self.client,
                self._llm_log,
                component="user_agent",
                model=self.settings.model,
                messages=messages,
                response_format=UserAgentOutput,
                **options,
            )
            message = response.choices[0].message
            if message.parsed is not None:
                return message.parsed
            if message.refusal:
                logger.error(
                    "[user_agent] Model refused to respond: %s", message.refusal
                )
                raise RuntimeError(f"User agent LLM refused: {message.refusal}")
            logger.error(
                "[user_agent] Structured output parsed to None (finish_reason=%s, content=%r)",
                response.choices[0].finish_reason,
                message.content,
            )
            raise RuntimeError(
                f"User agent LLM returned unparseable response (finish_reason={response.choices[0].finish_reason})"
            )
        except APIError as e:
            logger.error("[user_agent] OpenAI API error: %s", e)
            raise RuntimeError(f"User agent LLM call failed: {e}") from e
