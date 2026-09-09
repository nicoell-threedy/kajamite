"""Static, read-only MCP Apps presentation for knowledge change receipts."""

from importlib.resources import files


RESOURCE_URI = "ui://kajamite/knowledge-change.html"


def html() -> str:
    return files("kajamite").joinpath("knowledge-change.html").read_text(encoding="utf-8")
