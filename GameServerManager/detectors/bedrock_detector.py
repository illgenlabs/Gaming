from __future__ import annotations
from pathlib import Path
from detectors.base_detector import BaseDetector
from models import ACTIONS, HealthCheck, ServerInfo


class BedrockDetector(BaseDetector):
    def can_handle(self, path: Path) -> bool:
        return (path / "bedrock_server.exe").is_file() and (path / "server.properties").is_file()

    def detect(self, path: Path) -> ServerInfo:
        props = self._props(path / "server.properties")
        scripts = self._scripts(path)
        world_name = props.get("level-name", "Bedrock level") or "Bedrock level"
        config_files = [x for x in ("server.properties", "allowlist.json", "permissions.json") if (path / x).is_file()]
        checks = [
            HealthCheck("ok", "Minecraft Bedrock Dedicated Server detected."),
            HealthCheck("ok" if scripts["start"] else "warning", f"Start script: {scripts['start'] or 'not configured'}"),
            HealthCheck("ok", "Minecraft Bedrock can be stopped safely with the console command stop."),
            HealthCheck("ok" if (path / "worlds").exists() else "info", "World data: worlds"),
        ]
        relevant = {
            "server-name": props.get("server-name", path.name),
            "server-port": self._int(props.get("server-port"), 19132),
            "max-players": self._int(props.get("max-players"), 10),
            "gamemode": props.get("gamemode", "survival"),
            "difficulty": props.get("difficulty", "easy"),
            "level-name": world_name,
        }
        return ServerInfo("", props.get("server-name", "").strip() or path.name, "minecraft_bedrock", str(path),
                          scripts, False, ["bedrock_server.exe"] + config_files + [x for x in scripts.values() if x],
                          relevant, [], ["worlds"], [], checks)

    @staticmethod
    def _scripts(path: Path) -> dict[str, str]:
        names = {p.name.casefold(): p.name for p in path.iterdir() if p.is_file()}
        choices = {
            "start": ("start_server.bat", "start_bedrock.bat", "start.bat", "run.bat", "server.bat"),
            "stop": ("stop.bat", "shutdown.bat"),
            "restart": ("restart.bat", "reboot.bat"),
            "update": ("update.bat", "update_server.bat", "update_bedrock.bat", "server_update.bat"),
        }
        return {a: next((names[n.casefold()] for n in choices[a] if n.casefold() in names), "") for a in ACTIONS}

    @staticmethod
    def _props(path: Path) -> dict[str, str]:
        result = {}
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
        return result

    @staticmethod
    def _int(value: str | None, default: int) -> int:
        try:
            return int(value) if value is not None else default
        except ValueError:
            return default
