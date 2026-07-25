from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServerTypeDefinition:
    """User-facing name and capabilities for a registered server type."""

    key: str
    display_name: str
    is_minecraft: bool = False
    supports_console_stop: bool = False
    console_stop_command: str = ""
    supports_managed_pid_stop: bool = False
    supports_automatic_update: bool = False
    supports_plugins: bool = False
    supports_worlds: bool = False


SERVER_TYPES: dict[str, ServerTypeDefinition] = {
    "minecraft_paper": ServerTypeDefinition("minecraft_paper", "Minecraft (Paper)", True, True, "stop", False, True, True, True),
    "minecraft_folia": ServerTypeDefinition("minecraft_folia", "Minecraft (Folia)", True, True, "stop", False, True, True, True),
    "minecraft_purpur": ServerTypeDefinition("minecraft_purpur", "Minecraft (Purpur)", True, True, "stop", False, True, True, True),
    "minecraft_vanilla": ServerTypeDefinition("minecraft_vanilla", "Minecraft (Vanilla)", True, True, "stop", False, True, False, True),
    "minecraft_fabric": ServerTypeDefinition("minecraft_fabric", "Minecraft (Fabric)", True, True, "stop", False, True, True, True),
    "minecraft_forge": ServerTypeDefinition("minecraft_forge", "Minecraft (Forge)", True, True, "stop", False, False, True, True),
    "minecraft_neoforge": ServerTypeDefinition("minecraft_neoforge", "Minecraft (NeoForge)", True, True, "stop", False, False, True, True),
    "minecraft_spigot": ServerTypeDefinition("minecraft_spigot", "Minecraft (Spigot)", True, True, "stop", False, False, True, True),
    "minecraft_bukkit": ServerTypeDefinition("minecraft_bukkit", "Minecraft (Bukkit)", True, True, "stop", False, False, True, True),
    "minecraft_java": ServerTypeDefinition("minecraft_java", "Minecraft (Java Edition)", True, True, "stop", False, False, False, True),
    "minecraft_bedrock": ServerTypeDefinition("minecraft_bedrock", "Minecraft Bedrock Dedicated Server", True, True, "stop", False, False, False, True),
    "factorio": ServerTypeDefinition("factorio", "Factorio Dedicated Server", False, True, "/quit", False, False, False, True),
    "valheim": ServerTypeDefinition("valheim", "Valheim Dedicated Server", False, False, "", True, False, False, True),
    "ark_evolved": ServerTypeDefinition("ark_evolved", "ARK: Survival Evolved Dedicated Server", False, False, "", True),
    "ark_ascended": ServerTypeDefinition("ark_ascended", "ARK: Survival Ascended Dedicated Server", False, False, "", True),
    "windrose": ServerTypeDefinition("windrose", "Windrose Dedicated Server", False, False, "", True),
    "generic": ServerTypeDefinition("generic", "Generic Server"),
}


def get_server_type(server_type: str) -> ServerTypeDefinition:
    key = str(server_type or "generic").strip() or "generic"
    definition = SERVER_TYPES.get(key)
    if definition is not None:
        return definition
    fallback_name = key.replace("_", " ").strip().title() or "Generic Server"
    return ServerTypeDefinition(key=key, display_name=fallback_name)


def get_server_type_name(server_type: str) -> str:
    return get_server_type(server_type).display_name


def is_minecraft_server(server_type: str) -> bool:
    return get_server_type(server_type).is_minecraft


def supports_console_stop(server_type: str) -> bool:
    return get_server_type(server_type).supports_console_stop


def get_console_stop_command(server_type: str) -> str:
    return get_server_type(server_type).console_stop_command or "stop"


def supports_automatic_update(server_type: str) -> bool:
    return get_server_type(server_type).supports_automatic_update


def supports_managed_pid_stop(server_type: str) -> bool:
    return get_server_type(server_type).supports_managed_pid_stop


# Compatibility alias for older UI code/configuration.
def supports_ctrl_break_stop(server_type: str) -> bool:
    return supports_managed_pid_stop(server_type)
