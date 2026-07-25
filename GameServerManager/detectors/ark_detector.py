from __future__ import annotations
from pathlib import Path
from detectors.base_detector import BaseDetector
from models import ACTIONS, HealthCheck, ServerInfo


class ArkDetector(BaseDetector):
    SAVE_PATH = "ShooterGame/Saved"

    def can_handle(self, path: Path) -> bool:
        win64 = path / "ShooterGame" / "Binaries" / "Win64"
        return (win64 / "ShooterGameServer.exe").is_file() or (win64 / "ArkAscendedServer.exe").is_file()

    def detect(self, path: Path) -> ServerInfo:
        win64 = path / "ShooterGame" / "Binaries" / "Win64"
        ascended = (win64 / "ArkAscendedServer.exe").is_file()
        kind = "ark_ascended" if ascended else "ark_evolved"
        exe = "ShooterGame/Binaries/Win64/ArkAscendedServer.exe" if ascended else "ShooterGame/Binaries/Win64/ShooterGameServer.exe"
        scripts = self._scripts(path)
        checks = [
            HealthCheck("ok", ("ARK: Survival Ascended" if ascended else "ARK: Survival Evolved") + " Dedicated Server detected."),
            HealthCheck("ok" if scripts["start"] else "warning", f"Start script: {scripts['start'] or 'not configured'}"),
            HealthCheck("info", "ARK is stopped by terminating the exact managed process tree."),
            HealthCheck("ok" if (path / self.SAVE_PATH).exists() else "info", f"Save data: {self.SAVE_PATH}"),
        ]
        return ServerInfo("", path.name, kind, str(path), scripts, False,
                          [exe] + [x for x in scripts.values() if x],
                          {"Executable": exe, "Save data": self.SAVE_PATH}, [], [], [self.SAVE_PATH], checks)

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
