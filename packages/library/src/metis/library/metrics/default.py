"""The fallback judge for a criterion nothing in the library measures.

One parameterised class, not codegen. The wizard's matcher embeds each acceptance criterion
against the library and picks the best match above a threshold; below it, the criterion is
bound to this class with its own text as an argument. So a criterion nobody wrote a metric for
still gets judged, and no file is generated that would then need keeping in sync.

An experiment that leans on this heavily is telling you something worth knowing: those are
behaviours the product owner cared about that nothing in the library covers.
"""

from typing import cast

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._judge import _get_judge_model


class CriterionGEvalMetric(GEval):
    """Judges one acceptance criterion, written in the user's own words.

    The criterion arrives as given/when/then prose from the wizard. It is handed to GEval as
    the evaluation criteria more or less verbatim — rewriting it here would put words in the
    user's mouth that they never reviewed.
    """

    def __init__(
        self,
        criterion: str,
        name: str = "Acceptance criterion",
        threshold: float = 0.6,
    ) -> None:
        super().__init__(
            name=name,
            model=_get_judge_model(),
            criteria=(
                "Evaluate whether the agent's response satisfies this acceptance "
                "criterion, which was written by the product owner:\n\n"
                f"{criterion}\n\n"
                "The 'input' is what the user asked. The 'actual_output' is what the "
                "agent produced.\n\n"
                "Score 1.0 if the criterion is clearly satisfied. Score 0.5 if it is "
                "partially satisfied or the evidence is ambiguous. Score 0.0 if it is "
                "not satisfied. Judge only this criterion — ignore other qualities of "
                "the response, however good or bad."
            ),
            evaluation_params=cast(
                "list[SingleTurnParams]",
                [LLMTestCase.INPUT, LLMTestCase.ACTUAL_OUTPUT],
            ),
            threshold=threshold,
            async_mode=False,
        )
        self.criterion = criterion
