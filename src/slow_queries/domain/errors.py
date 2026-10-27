"""Named errors of the lesson. Each says what went wrong in terms a reader of the plans would use."""


class LabError(Exception):
    """Base class of every error this package raises on purpose."""


class PlanParseError(LabError):
    """A query plan did not have the lines or fields the lesson reads."""


class UnknownStepError(LabError):
    """A migration step number outside the lesson's steps."""


class LessonInterruptedError(LabError):
    """The replay was asked to stop (SIGINT or SIGTERM) between two steps."""
