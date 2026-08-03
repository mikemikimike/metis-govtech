"""Hand-authored profiles used across the tests.

Writing one by hand is the point of `ProductProfile` carrying no step, no history and no
session id: this file proves the document is a pure artefact by building one without an
interview ever having run.
"""

from metis.wizard.contracts import (
    Behaviour,
    Criterion,
    Epic,
    EpicScope,
    InteractionType,
    Persona,
    Product,
    ProductProfile,
    Task,
)

UNIVERSAL_TURN_BUDGET = "metis.engine.metrics.universal.TurnBudgetMetric"
CITATION_METRIC = "metis.engine.metrics.orchestration.SynthesisFaithfulnessMetric"
BOUNDED_TROUBLESHOOTING = "metis.engine.metrics.universal.BoundedTroubleshootingMetric"


def research_assistant() -> ProductProfile:
    """A profile exercising every shape the compiler has to handle.

    Deliberately contains: a ticked behaviour with several criteria, an unticked behaviour
    that still has criteria (dormant, not deleted), a criterion the user typed by hand, one
    task covering two behaviours, a task with two personas, and the universal epic.
    """
    return ProductProfile(
        product=Product(
            name="Research assistant",
            summary=(
                "An agent that answers research questions over an internal document "
                "library, citing what it used."
            ),
            users=(
                "Policy analysts and their managers. Some know exactly what they want; "
                "others are exploring and do not."
            ),
            architecture=(
                "A router agent with a document search tool and a summariser subagent. "
                "Search can time out. Nothing is carried between sessions."
            ),
        ),
        epics=[
            Epic(
                id="EP-1",
                name="Answer quality",
                behaviours=[
                    Behaviour(
                        id="EB-1",
                        statement="Cites a source for every factual claim",
                        priority=True,
                        criteria=[
                            Criterion(
                                id="AC-1-1",
                                given="a question answerable from the library",
                                when="the answer is returned",
                                then="every factual claim names the document it came from",
                                metric_fqn=CITATION_METRIC,
                            ),
                            Criterion(
                                id="AC-1-2",
                                given="a question the library cannot answer",
                                when="the answer is returned",
                                then="it says so rather than citing an unrelated document",
                                metric_fqn=CITATION_METRIC,
                            ),
                        ],
                    ),
                    Behaviour(
                        id="EB-2",
                        statement="Keeps answers under a page unless asked otherwise",
                        priority=False,  # unticked — criteria below are dormant, not deleted
                        criteria=[
                            Criterion(
                                id="AC-2-1",
                                given="a question with no length instruction",
                                when="the answer is returned",
                                then="it is under 500 words",
                                metric_fqn=UNIVERSAL_TURN_BUDGET,
                            ),
                        ],
                    ),
                ],
            ),
            Epic(
                id="EP-2",
                name="Recovery",
                behaviours=[
                    Behaviour(
                        id="EB-3",
                        statement="Stops after repeated search failures and says what it tried",
                        priority=True,
                        # the user typed this one — it must survive any regeneration
                        interaction_type=InteractionType.FORM,
                        criteria=[
                            Criterion(
                                id="AC-3-1",
                                given="a document search that times out repeatedly",
                                when="the agent has retried three times",
                                then="it stops and reports what it attempted",
                                metric_fqn=BOUNDED_TROUBLESHOOTING,
                                interaction_type=InteractionType.FORM,
                            ),
                        ],
                    ),
                ],
            ),
            Epic(
                id="EP-UNI",
                name="Always checked",
                scope=EpicScope.UNIVERSAL,
                behaviours=[
                    Behaviour(
                        id="EB-U1",
                        statement="Stays within a sensible number of turns",
                        priority=True,
                        criteria=[
                            Criterion(
                                id="AC-U1-1",
                                given="any session",
                                when="the task completes",
                                then="it took no more turns than the budget allows",
                                metric_fqn=UNIVERSAL_TURN_BUDGET,
                            ),
                        ],
                    ),
                ],
            ),
        ],
        personas=[
            Persona(
                id="cooperative-delegator",
                description=(
                    "A policy analyst comfortable with AI tools who engages fully, "
                    "answers questions willingly, and redirects gently if things stall."
                ),
            ),
            Persona(
                id="impatient-executive",
                description=(
                    "A time-poor director who writes in curt imperatives, will not "
                    "answer clarifying questions, and abandons the task quickly."
                ),
            ),
        ],
        tasks=[
            Task(
                id="T-1",
                description=(
                    "Ask for a literature review on a topic the library covers well, "
                    "then ask a follow-up that needs a second document."
                ),
                behaviour_refs=["EB-1", "EB-2"],  # M:N — one task covers two behaviours
                persona_refs=["cooperative-delegator", "impatient-executive"],
                num_trials=3,
            ),
            Task(
                id="T-2",
                description=(
                    "Ask a question whose documents live behind a search that will "
                    "time out, forcing the retry path."
                ),
                behaviour_refs=["EB-3"],
                persona_refs=["cooperative-delegator"],
                fixtures=["policy.pdf"],
                num_trials=3,
            ),
        ],
    )
