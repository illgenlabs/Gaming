from __future__ import annotations
from pathlib import Path
from uuid import uuid4
from core.config_manager import ConfigManager
from minecraft.detector import MinecraftDetector
from detectors.windrose_detector import WindroseDetector
from detectors.factorio_detector import FactorioDetector
from detectors.valheim_detector import ValheimDetector
from detectors.ark_detector import ArkDetector
from detectors.bedrock_detector import BedrockDetector
from models import ACTIONS, HealthCheck, ServerInfo

class ServerManager:
    def __init__(self) -> None:
        self.config=ConfigManager(); self.detectors=[BedrockDetector(), MinecraftDetector(), FactorioDetector(), ValheimDetector(), ArkDetector(), WindroseDetector()]
        self.servers=self.config.load_servers()
        changed = False
        for server in self.servers:
            if server.backup_paths:
                continue
            path = Path(server.path)
            if server.server_type == "windrose":
                server.backup_paths = WindroseDetector.default_backup_paths(path)
            elif server.server_type == "factorio":
                server.backup_paths = FactorioDetector.default_backup_paths(path)
            elif server.server_type in {"ark_evolved", "ark_ascended"}:
                server.backup_paths = [ArkDetector.SAVE_PATH]
            if server.backup_paths:
                changed = True
        if changed:
            self.config.save_servers(self.servers)

    def detect_server(self, folder: str, allow_generic: bool=True) -> ServerInfo:
        path=Path(folder).resolve()
        if not path.is_dir(): raise ValueError("The selected path is not a valid folder.")
        for detector in self.detectors:
            if detector.can_handle(path):
                server=detector.detect(path); server.id=uuid4().hex; return server
        if allow_generic:
            return self._generic_server(path)
        raise ValueError("The server type could not be detected.")

    def _generic_server(self, path: Path) -> ServerInfo:
        scripts={a:self._find_script(path,a) for a in ACTIONS}
        checks=[HealthCheck("info", "Generic script-based server.")]
        for action,label in (("start","Start"),("stop","Stop"),("update","Update")):
            checks.append(HealthCheck("ok" if scripts[action] else "warning", f"{label} script: {scripts[action] or 'not configured'}"))
        return ServerInfo(id=uuid4().hex,name=path.name,server_type="generic",path=str(path),action_scripts=scripts,
                          detected_files=[x for x in scripts.values() if x],health_checks=checks)

    @staticmethod
    def _find_script(path: Path, action: str) -> str:
        candidates={
            "start":("start.bat","startup.bat","run.bat","start.cmd"),
            "stop":("stop.bat","shutdown.bat","stop.cmd"),
            "restart":("restart.bat","reboot.bat","restart.cmd"),
            "update":("update.bat","update_server.bat","server_update.bat","update.cmd"),
        }[action]
        names={p.name.casefold():p.name for p in path.iterdir() if p.is_file()}
        return next((names[c.casefold()] for c in candidates if c.casefold() in names),"")

    def add_server(self, server: ServerInfo) -> None:
        target=str(Path(server.path).resolve()).casefold()
        if any(str(Path(s.path).resolve()).casefold()==target for s in self.servers):
            raise ValueError("This server folder has already been added.")
        if not self.servers: server.active=True
        self.servers.append(server); self.config.save_servers(self.servers)

    def remove_server(self, server_id: str) -> None:
        was_active=bool(self.get_server(server_id) and self.get_server(server_id).active)
        self.servers=[s for s in self.servers if s.id!=server_id]
        if was_active and self.servers: self.servers[0].active=True
        self.config.save_servers(self.servers)

    def get_server(self, server_id: str) -> ServerInfo|None:
        return next((s for s in self.servers if s.id==server_id),None)

    def set_active_server(self, server_id: str) -> None:
        for s in self.servers: s.active=s.id==server_id
        self.config.save_servers(self.servers)

    def save_scripts(self, server_id: str, scripts: dict[str,str]) -> ServerInfo:
        server=self.get_server(server_id)
        if not server: raise ValueError("Server not found.")
        root=Path(server.path).resolve()
        cleaned={a:"" for a in ACTIONS}
        for action in ACTIONS:
            value=scripts.get(action,"").strip()
            if not value: continue
            candidate=Path(value)
            if candidate.is_absolute():
                try: value=str(candidate.resolve().relative_to(root))
                except ValueError: raise ValueError("Scripts must be located inside the server folder.")
            full=root/value
            if not full.is_file(): raise ValueError(f"The {action} script was not found: {full}")
            if full.suffix.lower() not in {'.bat','.cmd','.ps1','.exe'}:
                raise ValueError(f"Unsupported script type: {full.suffix}")
            cleaned[action]=value
        server.action_scripts=cleaned
        self.config.save_servers(self.servers); return server


    def save_backup_paths(self, server_id: str, backup_paths: list[str]) -> ServerInfo:
        server=self.get_server(server_id)
        if not server: raise ValueError("Server not found.")
        root=Path(server.path).resolve()
        cleaned=[]
        for raw in backup_paths:
            value=str(raw).strip().replace("\\", "/")
            if not value or value.startswith("#"): continue
            candidate=Path(value)
            if candidate.is_absolute():
                try: value=candidate.resolve().relative_to(root).as_posix()
                except ValueError: raise ValueError("Backup paths must be located inside the server folder.")
            value=value.lstrip("./")
            if value and value not in cleaned: cleaned.append(value)
        server.backup_paths=cleaned
        self.config.save_servers(self.servers)
        return server

    def refresh_server(self, server_id: str) -> ServerInfo:
        old=self.get_server(server_id)
        if not old: raise ValueError("Server not found.")
        fresh=self.detect_server(old.path)
        fresh.id=old.id; fresh.active=old.active
        fresh.backup_paths = list(old.backup_paths) or list(fresh.backup_paths)
        # User-selected scripts have priority over auto-detection.
        for action,value in old.action_scripts.items():
            if value: fresh.action_scripts[action]=value
        self.servers[self.servers.index(old)]=fresh; self.config.save_servers(self.servers); return fresh
