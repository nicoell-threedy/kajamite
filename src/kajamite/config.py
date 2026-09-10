"""Explicit backend selection; no note roots, model accounts, or installers."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Settings:
    command: str
    args: list[str]
    project: str
    project_id: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 60
    state_dir: Path | None = None
    telemetry_file: Path | None = None
    semantic_search: bool = False

    @classmethod
    def load(cls, path: str | Path):
        config_path = Path(path).resolve()
        value = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
        backend = value.get("backend", {})
        for name in ("command", "project"):
            if not isinstance(backend.get(name), str) or not backend[name].strip():
                raise ValueError(f"backend.{name} must be a nonempty string")
        args = backend.get("args", [])
        env = backend.get("env", {})
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ValueError("backend.args must be a list of strings")
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise ValueError("backend.env must contain string values")
        semantic_search = backend.get("semantic_search", False)
        if not isinstance(semantic_search, bool):
            raise ValueError("backend.semantic_search must be a boolean")
        timeout = backend.get("timeout", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 600:
            raise ValueError("backend.timeout must be between 0 and 600 seconds")
        project_id = backend.get("project_id")
        if project_id is not None and (not isinstance(project_id, str) or not project_id.strip()):
            raise ValueError("backend.project_id must be a nonempty string")

        def configured_path(name):
            raw = value.get(name)
            if raw is None:
                return None
            if not isinstance(raw, str) or not raw:
                raise ValueError(f"{name} must be a path string")
            return (config_path.parent / Path(raw).expanduser()).resolve()

        return cls(backend["command"], args, backend["project"], project_id, env,
                   timeout, configured_path("state_dir"), configured_path("telemetry_file"), semantic_search)

    def lock_path(self):
        # One backend-wide lock is adequate for interactive note updates.
        # Different connection aliases must explicitly share state_dir.
        identity = json.dumps([self.command, self.args, self.project_id or self.project, self.env], sort_keys=True)
        key = hashlib.sha256(identity.encode()).hexdigest()[:24]
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) if os.name == "nt" else Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        return (self.state_dir or base / "kajamite" / key) / "mutation.lock"
