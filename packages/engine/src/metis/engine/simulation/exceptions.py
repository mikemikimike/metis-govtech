"""Typed exception hierarchy for simulation resilience layers.

Hierarchy:
    SimulationError (base — never raised directly)
    ├── TurnRecoverableError (caught by turn layer)
    │   ├── TransientDOMError
    │   ├── PostSubmissionObservationError
    │   └── TargetUnavailableError
    ├── RunRecoverableError (caught by run layer)
    │   ├── AuthLossError
    │   ├── PageCrashError
    │   ├── ConsecutiveFailureEscalation
    │   └── TargetSessionLostError
    ├── ResponseTimeoutError (record incomplete, continue)
    └── TargetSessionEnded (clean stop, target exhausted)
"""


class SimulationError(Exception):
    pass


class TurnRecoverableError(SimulationError):
    pass


class RunRecoverableError(SimulationError):
    pass


class TransientDOMError(TurnRecoverableError):
    pass


class PostSubmissionObservationError(TurnRecoverableError):
    pass


class TargetUnavailableError(TurnRecoverableError):
    """The target kept answering 503 for longer than the runner's retry window."""


class AuthLossError(RunRecoverableError):
    pass


class PageCrashError(RunRecoverableError):
    pass


class ConsecutiveFailureEscalation(RunRecoverableError):
    pass


class TargetSessionLostError(RunRecoverableError):
    """A session the runner was driving is gone (404) — reaped or deleted mid-run."""


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
