"""Core user agent logic for simulating persona-driven interactions."""

from enum import StrEnum

from openai import APIError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from metis.core.logging import get_logger

from ..types import (
    FormElement,
    Persona,
    Scenario,
    UIState,
    UserAgentInput,
    UserAgentOutput,
)
from .config import (
    USER_AGENT_MAX_TOKENS,
    USER_AGENT_MODEL,
    USER_AGENT_TEMPERATURE,
)
from .prompts import (
    OPENING_TURN_PROMPT,
    RESPONSE_TURN_PROMPT,
    SYSTEM_PROMPT_TEMPLATE,
)

logger = get_logger()

MAX_HISTORY_TURNS = 20


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

    def __init__(self, persona: Persona, scenario: Scenario):
        """Initialize with persona definition and scenario description.

        :param persona: The persona driving the simulated user.
        :param scenario: The experiment scenario defining the goal.
        """
        self.persona = persona
        self.scenario = scenario
        self.conversation_history: list[HistoryEntry] = []
        self.turn_count = 0
        self.client = AsyncOpenAI()
        self._system_prompt = self._build_system_prompt()

    async def generate_opening(self) -> UserAgentOutput:
        """Generate the first message to start the conversation."""
        logger.info(
            "[user_agent] Generating opening message (persona=%s, model=%s)...",
            self.persona.id,
            USER_AGENT_MODEL,
        )
        response = await self._call_llm(OPENING_TURN_PROMPT)
        self.turn_count += 1
        self.conversation_history.append(
            HistoryEntry(role=HistoryRole.USER_AGENT, content=response.message)
        )
        logger.info("[user_agent] === OPENING TURN ===")
        if response.reasoning:
            logger.info("[user_agent]   Reasoning: %s", response.reasoning)
        logger.info("[user_agent]   Decision: %s", response.decision)
        logger.info("[user_agent]   Message: %s", response.message[:200])
        if response.ui_actions:
            logger.info(
                "[user_agent]   UI Actions: %s",
                [a.model_dump() for a in response.ui_actions],
            )
        return response

    async def generate_response(self, turn_payload: UserAgentInput) -> UserAgentOutput:
        """Given the system's response, generate the user's next message.

        :param turn_payload: Structured payload containing the target system's
            UI state and optional session metadata.
        """
        ui_state: UIState = turn_payload.ui_state
        target_message = ui_state.text
        form_elements = ui_state.form_elements or None
        action_feedback = turn_payload.action_feedback or None

        logger.info(
            "[user_agent] Generating response (turn=%d, history=%d msgs, target_text=%d chars)...",
            self.turn_count + 1,
            len(self.conversation_history),
            len(target_message),
        )
        logger.info("[user_agent]   Target said: %s", target_message[:300])
        if action_feedback:
            logger.info(
                "[user_agent]   Action feedback: %s",
                "; ".join(action_feedback),
            )

        self.conversation_history.append(
            HistoryEntry(role=HistoryRole.TARGET, content=target_message)
        )

        # Build the turn-specific prompt
        user_prompt = self._build_user_prompt(
            target_message,
            form_elements=form_elements,
            action_feedback=action_feedback,
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
        if response.ui_actions:
            logger.info(
                "[user_agent]   UI Actions: %s",
                [a.model_dump() for a in response.ui_actions],
            )
        return response

    def _build_system_prompt(self) -> str:
        """Build the system prompt that instructs the LLM to act as this persona."""
        if self.scenario.fixtures:
            lines = [
                "\n## Files to Upload",
                "The following files are staged and ready to upload. Include them "
                "as file_upload actions in ui_actions of your **first message**. "
                "Do NOT upload any file not in this list:",
            ]
            for f in self.scenario.fixtures:
                lines.append(f"- {f}")
            fixtures_section = "\n".join(lines) + "\n"
        else:
            fixtures_section = ""
        return SYSTEM_PROMPT_TEMPLATE.format(
            persona_description=self.persona.description,
            scenario_description=self.scenario.description,
            fixtures_section=fixtures_section,
        )

    def _build_user_prompt(
        self,
        target_message: str,
        form_elements: list[FormElement] | None = None,
        action_feedback: list[str] | None = None,
    ) -> str:
        """Build the turn-specific instruction prompt (excludes history, which
        is conveyed structurally via multi-turn contents)."""
        form_elements_section = ""
        if form_elements:
            form_lines = ["Available form elements:"]
            for el in form_elements:
                if el.type == "select":
                    form_lines.append(
                        f'  - [{el.type}] "{el.label}" '
                        f"(selector: {el.selector})"
                        f" options: {el.options or []}"
                        f" current: {el.value or ''}"
                    )
                elif el.type == "button":
                    form_lines.append(
                        f'  - [{el.type}] "{el.label}" (selector: {el.selector})'
                    )
                else:
                    form_lines.append(
                        f'  - [{el.type}] "{el.label}" (selector: {el.selector}) value: {el.value or ""}'
                    )
            form_elements_section = "\n" + "\n".join(form_lines) + "\n"

        action_feedback_section = ""
        if action_feedback:
            lines = [
                "[Action feedback from previous turn]",
                *[f"- {fb}" for fb in action_feedback],
            ]
            action_feedback_section = "\n" + "\n".join(lines) + "\n"

        return RESPONSE_TURN_PROMPT.format(
            target_message=target_message,
            form_elements_section=form_elements_section,
            action_feedback_section=action_feedback_section,
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
        logger.debug(
            "[user_agent] Calling LLM: model=%s, messages=%d, max_tokens=%d, temp=%s",
            USER_AGENT_MODEL,
            len(messages),
            USER_AGENT_MAX_TOKENS,
            USER_AGENT_TEMPERATURE,
        )

        try:
            response = await self.client.beta.chat.completions.parse(
                model=USER_AGENT_MODEL,
                messages=messages,
                max_tokens=USER_AGENT_MAX_TOKENS,
                temperature=USER_AGENT_TEMPERATURE,
                response_format=UserAgentOutput,
            )
            message = response.choices[0].message
            if message.parsed is not None:
                usage = response.usage
                if usage:
                    logger.debug(
                        "[user_agent] LLM usage: prompt=%d, completion=%d, total=%d tokens",
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                    )
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
