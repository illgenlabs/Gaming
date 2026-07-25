from __future__ import annotations
from pathlib import Path
from detectors.base_detector import BaseDetector
from models import ACTIONS, HealthCheck, ServerInfo


class FactorioDetector(BaseDetector):
    @staticmethod
    def default_backup_paths(path: Path) -> list[str]:
        candidates = ["saves", "config", "mods", "data/server-settings.json", "server-settings.json",
                      "server-adminlist.json", "server-banlist.json", "server-whitelist.json"]
        existing = [item for item in candidates if (path / item).exists()]
        return existing or ["saves"]

    def can_handle(self, path: Path) -> bool:
        return (path / "bin" / "x64" / "factorio.exe").is_file() or (path / "factorio.exe").is_file()

    def detect(self, path: Path) -> ServerInfo:
        scripts = self._scripts(path)
        exe = "bin/x64/factorio.exe" if (path / "bin" / "x64" / "factorio.exe").is_file() else "factorio.exe"
        backups = self.default_backup_paths(path)
        checks = [
            HealthCheck("ok", "Factorio Dedicated Server detected."),
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
