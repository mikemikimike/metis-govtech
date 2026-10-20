"""metis.library.graders.demo: example graders built on the shared trace processor (#431).

They show grader authors how to read a session through ``metis.core.trace_processing``, and
they run on a real captured session in the tests. They are not a catalogue: this sub-package
is not re-exported from ``metis.library.graders``, so the wizard never offers them. A
criterion can still name one by its full path, e.g.
``metis.library.graders.demo.DemoTraceBudgetGrader``.
"""

from ._answer_helpfulness import (
    DemoAnswerHelpfulnessGrader as DemoAnswerHelpfulnessGrader,
)
from ._required_tool import DemoRequiredToolArgs as DemoRequiredToolArgs
from ._required_tool import DemoRequiredToolGrader as DemoRequiredToolGrader
from ._task_completion import DemoTaskCompletionGrader as DemoTaskCompletionGrader
from ._trace_budget import DemoTraceBudgetArgs as DemoTraceBudgetArgs
from ._trace_budget import DemoTraceBudgetGrader as DemoTraceBudgetGrader
