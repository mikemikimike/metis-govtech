"""Reproducible Analysis Script metric (M-DA-23)."""

from typing import Any, ClassVar

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

from ._extraction import (
    CODE_TOOLS,
    get_artifacts,
    get_metadata,
    tool_calls_named,
)

# Generic script names that fail the descriptive-naming requirement.
_GENERIC_NAMES = {
    "script.py",
    "analysis.py",
    "main.py",
    "temp.py",
    "tmp.py",
    "untitled.py",
    "output.py",
    "outputs.py",
    "test.py",
    "code.py",
    "run.py",
    "a.py",
    "notebook.py",
}


def _presented_text(test_case: LLMTestCase) -> str:
    """Combined response text used to check the script was presented."""
    parts = [test_case.actual_output or ""]
    for msg in get_metadata(test_case).get("assistant_messages", []) or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            parts.append(content)
    return "\n".join(parts).lower()


class ReproducibleAnalysisScriptMetric(BaseMetric):
    """Did the agent save and present a descriptively-named analysis script?

    Deterministic (M-DA-23). Applicable only to a turn that called
    ``execute_python``. Requires a ``.py`` script saved under ``outputs/`` with
    a descriptive (non-generic) name that is referenced in the response.
    Skips when no code execution occurred on the turn.
    """

    tags: ClassVar[tuple[str, ...]] = ("analysis", "per-turn", "code-graded")
    async_mode = False

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def measure(self, test_case: LLMTestCase) -> float:
        if not tool_calls_named(test_case, *CODE_TOOLS):
            self.skipped = True
            self.score = 1.0
            self.success = True
            self.reason = (
                "SKIPPED — no execute_python call on this turn; a reproducible "
                "analysis script is not required."
            )
            return self.score

        py_artifacts = [
            a for a in get_artifacts(test_case) if a.name.lower().endswith(".py")
        ]
        in_outputs = [
            a
            for a in py_artifacts
            if "outputs/" in (a.path or "").replace("\\", "/").lower()
        ]
        descriptive = [a for a in in_outputs if a.name.lower() not in _GENERIC_NAMES]
        presented_text = _presented_text(test_case)
        presented = [
            a
            for a in descriptive
            if a.name.lower() in presented_text
            or a.name.rsplit(".", 1)[0].lower() in presented_text
        ]

        passed = bool(presented)
        self.score = 1.0 if passed else 0.0
        self.success = passed

        if not py_artifacts:
            evidence = "no .py script artifact saved this turn."
        elif not in_outputs:
            names = ", ".join(a.name for a in py_artifacts)
            evidence = f"script(s) saved but not under outputs/: {names}."
        elif not descriptive:
            names = ", ".join(a.name for a in in_outputs)
            evidence = f"script saved to outputs/ but generically named: {names}."
        elif not presented:
            names = ", ".join(a.name for a in descriptive)
            evidence = (
                f"descriptive script saved to outputs/ ({names}) but not "
                "presented in the response."
            )
        else:
            names = ", ".join(a.name for a in presented)
            evidence = f"descriptive script saved to outputs/ and presented: {names}."

        self.reason = evidence
        return self.score

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Reproducible Analysis Script"

    def is_successful(self) -> bool:
        return self.success is True
