"""Typed exception hierarchy for simulation resilience layers.

Hierarchy:
    SimulationError (base — never raised directly)
    ├── TurnRecoverableError (caught by turn layer)
    │   ├── TransientDOMError
    │   └── PostSubmissionObservationError
    ├── RunRecoverableError (caught by run layer)
    │   ├── AuthLossError
    │   ├── PageCrashError
    │   └── ConsecutiveFailureEscalation
    └── ResponseTimeoutError (record incomplete, continue)
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


class AuthLossError(RunRecoverableError):
    pass


class PageCrashError(RunRecoverableError):
    pass


class ConsecutiveFailureEscalation(RunRecoverableError):
    pass


class ResponseTimeoutError(SimulationError):
    pass
