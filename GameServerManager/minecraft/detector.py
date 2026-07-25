from __future__ import annotations
import re
from pathlib import Path
from detectors.base_detector import BaseDetector
from core.server_types import get_server_type_name
from models import ACTIONS, HealthCheck, ServerInfo

class MinecraftDetector(BaseDetector):
    CANDIDATES={
      'start':('startup.bat','start.bat','run.bat','server.bat'),
      'stop':('stop.bat','shutdown.bat'), 'restart':('restart.bat','reboot.bat'),
      'update':('update.bat','update_server.bat','server_update.bat','update.cmd')}
    def can_handle(self,path:Path)->bool:
        return (path/'server.properties').is_file() and any(p.suffix.lower()=='.jar' for p in path.iterdir() if p.is_file())
    def detect(self,path:Path)->ServerInfo:
        props=self._props(path/'server.properties'); scripts={a:self._find(path,a) for a in ACTIONS}
        jars=[p.name.casefold() for p in path.iterdir() if p.is_file() and p.suffix.lower()=='.jar']
        kind=next((k for token,k in [('paper','minecraft_paper'),('folia','minecraft_folia'),('purpur','minecraft_purpur'),('spigot','minecraft_spigot'),('bukkit','minecraft_bukkit'),('fabric','minecraft_fabric'),('neoforge','minecraft_neoforge'),('forge','minecraft_forge')] if any(token in j for j in jars)),'minecraft_vanilla')
        plugins=self._plugins(path/'plugins'); level=props.get('level-name','world') or 'world'
        worlds=[]
        for d in path.iterdir():
            if d.is_dir() and (d.name in {level,level+'_nether',level+'_the_end'} or (d/'level.dat').is_file()): worlds.append(d.name)
        worlds=sorted(set(worlds),key=str.casefold)
        checks=[HealthCheck('ok', f"{get_server_type_name(kind)} detected."),
                HealthCheck('ok' if scripts['start'] else 'warning',f"Start script: {scripts['start'] or 'not configured'}"),
                HealthCheck('ok','Minecraft can be stopped safely with the console command stop; no separate stop script is required.')]
        vd=self._int(props.get('view-distance'),10); sd=self._int(props.get('simulation-distance'),10)
        if vd>12:checks.append(HealthCheck('warning',f'View distance is relatively high at {vd} '))
        if sd>12:checks.append(HealthCheck('warning',f'Simulation distance is relatively high at {sd} '))
        relevant={'motd':props.get('motd',''),'server-port':self._int(props.get('server-port'),25565),'max-players':self._int(props.get('max-players'),20),
          'white-list':self._bool(props.get('white-list')),'enforce-whitelist':self._bool(props.get('enforce-whitelist')),
          'online-mode':self._bool(props.get('online-mode'),True),'gamemode':props.get('gamemode','survival'),'difficulty':props.get('difficulty','normal'),
          'view-distance':vd,'simulation-distance':sd,'level-name':level}
        detected=['server.properties']+[x for x in scripts.values() if x]+worlds+(['plugins'] if (path/'plugins').is_dir() else [])
        return ServerInfo(
            id='',
            name=props.get('motd','').strip() or path.name,
            server_type=kind,
            path=str(path),
            action_scripts=scripts,
            active=False,
            detected_files=detected,
            properties=relevant,
            plugins=plugins,
            worlds=worlds,
            backup_paths=[],
            health_checks=checks,
        )
    def _find(self,path,action):
        names={p.name.casefold():p.name for p in path.iterdir() if p.is_file()}
        return next((names[x.casefold()] for x in self.CANDIDATES[action] if x.casefold() in names),'')
    def _props(self,path):
        result={}
        for raw in path.read_text(encoding='utf-8-sig',errors='replace').splitlines():
            line=raw.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1);result[k.strip()]=v.strip()
        return result
    def _plugins(self,path):
        if not path.is_dir():return []
        out=[]
        for p in path.glob('*.jar'):
            name=re.sub(r'[-_ ]?v?\d+(?:\.\d+)+.*$','',p.stem).strip('-_ ') or p.stem
            for token,display in [('geyser','Geyser'),('floodgate','Floodgate'),('viaversion','ViaVersion')]:
                if token in p.stem.casefold():name=display
            out.append(name)
        return sorted(set(out),key=str.casefold)
    @staticmethod
    def _bool(v,default=False):return default if v is None else str(v).casefold() in {'true','1','yes','on'}
    @staticmethod
    def _int(v,default):
        try:return int(v)
        except:return default
