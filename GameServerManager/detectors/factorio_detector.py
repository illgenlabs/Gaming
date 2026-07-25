from __future__ import annotations
from pathlib import Path
from detectors.base_detector import BaseDetector
from core.server_types import get_server_type
from models import ACTIONS, HealthCheck, ServerInfo


class FactorioDetector(BaseDetector):
    def can_handle(self, path: Path) -> bool:
        return (path / "bin" / "x64" / "factorio.exe").is_file() or (path / "factorio.exe").is_file()

    def detect(self, path: Path) -> ServerInfo:
        scripts = self._scripts(path)
        exe = "bin/x64/factorio.exe" if (path / "bin" / "x64" / "factorio.exe").is_file() else "factorio.exe"
        definition = get_server_type("factorio")
        backups = definition.backup_paths_for(path)
        checks = [
            HealthCheck("ok", f"{definition.display_name} detected."),
            HealthCheck("ok" if scripts["start"] else "warning", f"Start script: {scripts['start'] or 'not configured'}"),
            HealthCheck("ok", "The manager stops Factorio through the console command /quit."),
            HealthCheck("ok" if (path / "saves").exists() else "info", "Save data: saves"),
        ]
        return ServerInfo("", path.name, "factorio", str(path), scripts, False,
                          [exe] + [x for x in scripts.values() if x],
                          {"Executable": exe, "Save data": "saves"}, [], ["saves"], backups, checks)

    @staticmethod
    def _scripts(path: Path) -> dict[str, str]:
        names = {p.name.casefold(): p.name for p in path.iterdir() if p.is_file()}
        choices = {
            "start": ("start_server.bat", "start-factorio.bat", "start.bat", "run.bat", "server.bat"),
            "stop": ("stop.bat", "shutdown.bat"),
            "restart": ("restart.bat", "reboot.bat"),
            "update": ("update.bat", "update_server.bat", "update-factorio.bat", "server_update.bat"),
        }
        return {a: next((names[n.casefold()] for n in choices[a] if n.casefold() in names), "") for a in ACTIONS}
