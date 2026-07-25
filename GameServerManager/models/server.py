from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any

ACTIONS = ("start", "stop", "restart", "update")

@dataclass
class HealthCheck:
    level: str
    message: str

    def __post_init__(self) -> None:
        level = str(self.level).strip().casefold()
        self.level = level if level in {"ok", "warning", "error", "info"} else "info"
        self.message = str(self.message).strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class ServerInfo:
    id: str
    name: str
    server_type: str
    path: str
    action_scripts: dict[str, str] = field(default_factory=lambda: {a: "" for a in ACTIONS})
    active: bool = False
    detected_files: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    plugins: list[str] = field(default_factory=list)
    worlds: list[str] = field(default_factory=list)
    backup_paths: list[str] = field(default_factory=list)
    health_checks: list[HealthCheck] = field(default_factory=list)

    @property
    def start_script(self) -> str:
        return self.action_scripts.get("start", "")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["health_checks"] = [c.to_dict() for c in self.health_checks]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerInfo":
        scripts = {a: "" for a in ACTIONS}
        incoming = data.get("action_scripts") or data.get("scripts") or {}
        if isinstance(incoming, dict):
            for action in ACTIONS:
                scripts[action] = str(incoming.get(action, ""))
        # Migration from earlier project versions.
        scripts["start"] = scripts["start"] or str(data.get("start_script", ""))
        scripts["update"] = scripts["update"] or str(data.get("update_script", ""))
        return cls(
            id=str(data.get("id", "")), name=str(data.get("name", "")),
            server_type=str(data.get("server_type", "generic")), path=str(data.get("path", "")),
            action_scripts=scripts, active=bool(data.get("active", False)),
            detected_files=list(data.get("detected_files", [])),
            properties=dict(data.get("properties", {})), plugins=list(data.get("plugins", [])),
            worlds=list(data.get("worlds", [])),
            backup_paths=[
                str(x) for x in data.get("backup_paths", [])
                if isinstance(x, (str, int, float)) and str(x).strip()
            ],
            health_checks=[
                HealthCheck(str(x.get("level", "info")), str(x.get("message", "")))
                for x in data.get("health_checks", [])
                if isinstance(x, dict)
            ],
        )
