"""Dependency-free exceptions shared by the engine and backend adapters."""


class BackendError(RuntimeError):
    """An upstream operation failed; an interrupted mutation may have committed."""


class MutationUncertain(BackendError):
    """A mutation was attempted but its durable outcome is not established."""

    outcome = "uncertain"
