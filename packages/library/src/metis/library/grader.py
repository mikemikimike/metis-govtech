"""The grader contract: what every grader in METIS implements.

A grader judges what the target did, so ``grade()`` sees only the session's Langfuse traces and
the artifacts the run produced (``GradingInput``), never the scenario, persona or stop reason.
A grader that needs a reference value, such as an expected tool sequence, gets it through its
args.

A grader returns a score for each grading scope it chooses and never decides pass or fail; the
engine applies the criterion's ``threshold``. ``Grader`` is deliberately thin: a single-shot
prompt, a multi-step claim check, or a full agentic loop are all valid ``grade()`` bodies.

This module is the contract; ``metis.library.graders`` is the catalogue of graders built on it.
They are kept apart so that the catalogue package exports concrete graders only.
"""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Generic,
    TypeVar,
    get_args,
    get_origin,
)

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from metis.core.grading import GraderResult
from metis.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from openai import AsyncOpenAI

    from metis.core.grading import GradingOutput
    from metis.core.profile import CriterionDescription
    from metis.core.specification import Specification
    from metis.core.traces import GradingInput


class GraderArgs(BaseModel):
    """Base of every grader's args model: the keys a criterion sets under ``grader_args``.

    Unknown keys are rejected, so a misspelt arg fails the engine's pre-run validation instead
    of silently taking its default. Frozen, because one grader, and so one args object, is
    shared by every concurrent grader run of its criterion.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    threshold: float = Field(default=0.5, ge=0, le=1, strict=True)
    """A scored result passes when ``score >= threshold``. The default also separates the
    ``0.0``/``1.0`` scores of a binary grader, so only graders with graded scores need it set."""


logger = get_logger(__name__)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

DEFAULT_MAX_INPUT_TOKENS = 128_000


class JudgeArgs(GraderArgs):
    """Base of a model-based grader's args model."""

    model: NonEmptyText
    """The judge model. The engine resolves it before validation (``grader_args.model``, then
    ``defaults.judge_model``, then ``JUDGE_MODEL``, then the package default), so it is always
    set inside ``grade()`` and recorded with every result."""

    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS
    """The largest estimated request that one judge call may send. The engine resolves it
    before validation (``grader_args.max_input_tokens``, then ``JUDGE_MAX_INPUT_TOKENS``, then
    this default). Check it with ``input_budget_error`` before each model call."""

    @field_validator("max_input_tokens", mode="before")
    @classmethod
    def _positive_or_default(cls, value: object) -> int:
        # A bad limit must not block a run that would otherwise succeed, so it falls back
        # to the default with a warning.
        try:
            parsed = int(value) if isinstance(value, int | str) else 0
        except ValueError:
            parsed = 0
        if isinstance(value, bool) or parsed < 1:
            logger.warning(
                "invalid_max_input_tokens",
                value=value,
                default=DEFAULT_MAX_INPUT_TOKENS,
            )
            return DEFAULT_MAX_INPUT_TOKENS
        return parsed


class CriterionJudgeArgs(JudgeArgs):
    """Settings of a judge that takes its instructions from the criterion description.

    The engine and the wizard set ``criterion`` from the current description with
    ``criterion_judge_args``, so an edit to the description applies on the next run. A
    specification never sets it under ``grader_args``.
    """

    criterion: NonEmptyText


def criterion_judge_args(
    args_model: type[GraderArgs],
    settings: Mapping[str, Any],
    description: CriterionDescription | None,
) -> dict[str, Any]:
    """Copy ``settings`` and, for a ``CriterionJudgeArgs`` model, add the description as ``criterion``.

    Raises ``ValueError`` when the settings already name ``criterion`` or the description has a
    blank clause.
    """
    resolved = dict(settings)
    if not issubclass(args_model, CriterionJudgeArgs):
        return resolved
    if "criterion" in resolved:
        raise ValueError(
            "Edit the criterion description instead of grader_args.criterion."
        )
    if description is None:
        raise ValueError("The criterion description is required.")
    for clause in ("given", "when", "then"):
        if not getattr(description, clause).strip():
            raise ValueError(f"Criterion description.{clause} must not be blank.")
    resolved["criterion"] = str(description)
    return resolved


def input_budget_error(
    args: JudgeArgs, request: Mapping[str, Any]
) -> GraderResult | None:
    """An errored result when ``request`` is above ``args.max_input_tokens``, else ``None``.

    ``request`` is the keyword arguments for one chat completion call. One token per UTF-8
    byte is a conservative bound for byte-based tokenizers; 4,096 covers message framing.
    """
    estimate = len(json.dumps(request, ensure_ascii=False).encode("utf-8")) + 4096
    if estimate <= args.max_input_tokens:
        return None
    # TODO: Name the settings that judge a part of the session when they are designed.
    return GraderResult(
        status="errored",
        reason=(
            f"The judge request needs about {estimate:,} estimated tokens; the limit is "
            f"{args.max_input_tokens:,}. Raise the limit or judge a smaller part of the session."
        ),
    )


ArgsT = TypeVar("ArgsT", bound=GraderArgs)


@dataclass(frozen=True)
class LLMSettings:
    """What the engine hands every grader run for making grader LLM calls.

    A plain holder, not a wrapper: graders call ``llm.client`` directly, and a future setting
    becomes a field here rather than a change to every ``grade()`` signature. The client is
    shared by every grader run in an evaluation, and its connection pool caps how many grader
    LLM calls are in flight. Code-based graders ignore it.
    """

    client: AsyncOpenAI


class Grader(abc.ABC, Generic[ArgsT]):
    """One way of judging a session. Built once per criterion as ``SomeGrader(args)``.

    A direct subclass names its args model twice: as the type argument, so ``self.args`` is
    typed as that model, and as ``args_model``, so the engine can validate ``grader_args`` at
    runtime. ``__init_subclass__`` checks that the two name the same class.

    A grader holds only its validated args and keeps no per-evaluation state, since ``grade()``
    returns its results.
    """

    args_model: ClassVar[type[GraderArgs]]
    """This grader's parameters, as written under ``grader_args`` in specification.yaml."""

    def __init__(self, args: ArgsT) -> None:
        self.args = args

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if Grader not in cls.__bases__:
            return  # inherits an args_model that was checked on its own parent
        declared = next(
            (
                get_args(base)[0]
                for base in cls.__dict__.get("__orig_bases__", ())
                if get_origin(base) is Grader
            ),
            None,
        )
        if declared is None:
            raise TypeError(
                f"{cls.__name__} must subclass Grader[ItsArgsModel], not bare Grader."
            )
        if isinstance(declared, TypeVar):
            return  # a generic intermediate base; its own subclasses are checked
        args_model = cls.__dict__.get("args_model")
        if args_model is not declared:
            raise TypeError(
                f"{cls.__name__} subclasses Grader[{declared.__name__}] but its args_model is "
                f"{getattr(args_model, '__name__', args_model)!r}; set "
                f"args_model = {declared.__name__}."
            )

    @abc.abstractmethod
    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        """Grades the session, returning one result per grading scope.

        A model-based grader calls ``input_budget_error`` before each model call.

        Return one skipped result, never an empty list, when there is nothing to judge. When a
        grader LLM call fails or its reply can't be parsed for one part of the session, record
        that part as errored and carry on. An exception that escapes ``grade()`` is recorded as
        one errored result for the whole grader run.
        """

    @classmethod
    def check_setup(cls, args: ArgsT, spec: Specification) -> list[str]:
        """Checks across the spec that the args model can't express.

        For example, that a fixture an arg names exists. Returns error messages, empty if
        valid. Runs in the engine's pre-run pass, with no client or credentials. Default: no
        extra checks.
        """
        return []
