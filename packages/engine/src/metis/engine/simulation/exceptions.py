"""Typed exception hierarchy for simulation resilience layers.

Hierarchy:
    SimulationError (base — never raised directly)
    ├── TurnRecoverableError (caught by turn layer)
    │   ├── TransientDOMError
    │   ├── PostSubmissionObservationError
    │   └── TargetUnavailableError
    ├── TrialRecoverableError (caught by trial layer)
    │   ├── AuthLossError
    │   ├── PageCrashError
    │   ├── ConsecutiveFailureEscalation
    │   └── TargetSessionLostError
    ├── ResponseTimeoutError (record incomplete, continue)
    ├── TargetSessionEnded (clean stop, target exhausted)
    └── RunnerContractError (engine defect, no retry — system error)
"""


class SimulationError(Exception):
    pass


class TurnRecoverableError(SimulationError):
    pass


class TrialRecoverableError(SimulationError):
    pass


class TransientDOMError(TurnRecoverableError):
    pass


class PostSubmissionObservationError(TurnRecoverableError):
    pass


class TargetUnavailableError(TurnRecoverableError):
    """The target kept answering 503 for longer than the runner's retry window."""


class AuthLossError(TrialRecoverableError):
    pass


class PageCrashError(TrialRecoverableError):
    pass


class ConsecutiveFailureEscalation(TrialRecoverableError):
    pass


class TargetSessionLostError(TrialRecoverableError):
    """A session the runner was driving is gone (404) — reaped or deleted mid-trial."""


class ResponseTimeoutError(SimulationError):
    pass


class TargetSessionEnded(SimulationError):
    """The session cannot carry another turn, whatever the persona sends.

    Not the target refusing one message but the session itself being spent —
    a lifetime budget reached, or (the Orca API runner's live case) an input
    cap the accumulated context keeps exceeding.

    Neither turn- nor run-recoverable: retrying the turn cannot succeed and a
    fresh session would not continue the same conversation. The orchestrator
    ends the run with stop reason target_exhausted and a clean record.
    """


class RunnerContractError(SimulationError):
    """The runner returned an Observation that violates the runner contract
    (e.g. the set of ActionResult.action_index values does not match the
    submitted actions — invariant I1).

    Non-recoverable: a broken runner is an engine defect, not a turn or run
    failure. The orchestrator does not retry; the run ends as a system error.
    """
