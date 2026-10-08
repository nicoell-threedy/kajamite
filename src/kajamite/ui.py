"""Static, read-only MCP Apps presentation for knowledge change receipts."""

from importlib.resources import files
import json
import hashlib
from .theme import validate_theme


RESOURCE_URI = "ui://kajamite/knowledge-change/v4.html"


def html(theme=None) -> str:
    data = json.dumps(validate_theme(theme), ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = files("kajamite").joinpath("knowledge-change.html").read_text(encoding="utf-8")
    return template.replace("__KAJAMITE_THEME_JSON__", data)


def resource_uri(theme=None) -> str:
    normalized = validate_theme(theme)
    if not any(normalized.values()):
        return RESOURCE_URI
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()[:16]
    return RESOURCE_URI.replace("v4.html", f"v4-{digest}.html")
