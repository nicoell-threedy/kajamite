"""Knowledge continuity over an independently managed Basic Memory project."""

__version__ = "0.4.0"


def __getattr__(name):
    if name == "KnowledgeEngine":
        from .engine import KnowledgeEngine
        return KnowledgeEngine
    if name == "RecordEngine":
        from .governance import RecordEngine
        return RecordEngine
    raise AttributeError(name)
