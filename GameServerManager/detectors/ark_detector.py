from __future__ import annotations
from pathlib import Path
from detectors.base_detector import BaseDetector
from core.server_types import get_server_type
from models import ACTIONS, HealthCheck, ServerInfo


class ArkDetector(BaseDetector):
    def can_handle(self, path: Path) -> bool:
        win64 = path / "ShooterGame" / "Binaries" / "Win64"
        return (win64 / "ShooterGameServer.exe").is_file() or (win64 / "ArkAscendedServer.exe").is_file()

    def detect(self, path: Path) -> ServerInfo:
        win64 = path / "ShooterGame" / "Binaries" / "Win64"
        ascended = (win64 / "ArkAscendedServer.exe").is_file()
        kind = "ark_ascended" if ascended else "ark_evolved"
        exe = "ShooterGame/Binaries/Win64/ArkAscendedServer.exe" if ascended else "ShooterGame/Binaries/Win64/ShooterGameServer.exe"
        scripts = self._scripts(path)
        definition = get_server_type(kind)
        backup_paths = definition.backup_paths_for(path)
        save_path = backup_paths[0]
        checks = [
            HealthCheck("ok", f"{definition.display_name} detected."),
            HealthCheck("ok" if scripts["start"] else "warning", f"Start script: {scripts['start'] or 'not configured'}"),
            HealthCheck("info", "ARK is stopped by terminating the exact managed process tree."),
            HealthCheck("ok" if (path / save_path).exists() else "info", f"Save data: {save_path}"),
        ]
        return ServerInfo("", path.name, kind, str(path), scripts, False,
                          [exe] + [x for x in scripts.values() if x],
                          {"Executable": exe, "Save data": save_path}, [], [], backup_paths, checks)

    @staticmethod
    def _scripts(path: Path) -> dict[str, str]:
        names = {p.name.casefold(): p.name for p in path.iterdir() if p.is_file()}
        choices = {
            "start": ("start_server.bat", "start_ark_server.bat", "startark.bat", "start.bat", "run.bat"),
            "stop": ("stop.bat", "shutdown.bat"),
            "restart": ("restart.bat", "reboot.bat"),
            "update": ("update.bat", "update_server.bat", "update_ark_server.bat", "server_update.bat"),
        }
        return {a: next((names[n.casefold()] for n in choices[a] if n.casefold() in names), "") for a in ACTIONS}
