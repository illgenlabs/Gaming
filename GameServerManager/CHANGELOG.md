# Changelog

All notable changes to Game Server Manager are documented in this file.

The project currently uses phase-based version labels. Future public releases may adopt semantic versioning.

## [Unreleased]

### Changed

- Expanded `ServerTypeDefinition` into the central source for server family, shutdown strategy, capabilities, and static backup defaults.
- Kept detector modules responsible only for installation detection, configuration parsing, script discovery, health checks, and dynamic backup paths.

## [Phase 8.9] - 2026-07-25

### Added

- Automatic detection for Factorio Dedicated Server.
- Automatic detection for Valheim Dedicated Server.
- Automatic detection for ARK: Survival Evolved Dedicated Server.
- Automatic detection for ARK: Survival Ascended Dedicated Server.
- Automatic detection for Minecraft Bedrock Dedicated Server.
- Conservative backup defaults for Factorio and ARK.
- Portable Valheim `-savedir` detection.
- Minecraft Bedrock world handling and `stop` console command.
- Factorio `/quit` console shutdown.

### Changed

- Valheim, ARK, and Windrose use the exact process tracked by the manager when a process-tree stop is required.
- All added integrations remain portable and do not copy server scripts or files.

## [Phase 8.8] - 2026-07-25

### Added

- ntfy notification settings and test button.
- Traffic-light server status in the server list.

### Changed

- Replaced SMTP email notifications with credential-free ntfy notifications.
- Increased the main-window width and widened server-list columns.

## [Phase 8.7] - 2026-07-25

### Added

- Separate settings for Windows startup and automatic startup of the active server.
- Non-blocking notification test workflow.
- Error notifications for unexpected exits, failed automatic startup, maintenance failures, and unhandled UI exceptions.

### Changed

- Settings remain saved even when Windows integration reports an error.

> Phase 8.7 initially used SMTP. This was replaced by ntfy in Phase 8.8.

## [Phase 8.6] - 2026-07-25

### Added

- Portable server and backup defaults relative to the running application.
- User-level Windows startup entry.
- User-specific daily-maintenance task with limited privileges.

### Changed

- Removed fixed `C:\GameServer` and `C:\GameServerBackups` defaults.
- Inaccessible legacy scheduled tasks no longer prevent settings from being saved.

## [Phase 8.5] - 2026-07-25

### Added

- Windows application icon.
- PyInstaller one-file build script.
- Optional diagnostic console build.

## [Phase 8.4] - 2026-07-25

### Changed

- Windrose shutdown now targets the exact managed PID and process tree.
- Removed the unreliable Ctrl+Break and console-attachment implementation.
- Restart remains Stop → Start.
- Maintenance remains Stop → Backup → Update → Start.

## [Phase 8.3] - 2026-07-25

### Added

- Integrated hidden Windrose process output.

### Deprecated

- The Ctrl+Break shutdown experiment introduced in this phase was removed in Phase 8.4.

## [Phase 8.2] - 2026-07-25

### Added

- Backup-selection dialog with file and folder selection.
- Immediate persistence after script selection.

### Changed

- Removed bundled server scripts.
- The manager stores paths to scripts that remain inside each server directory.
- Removed the separate script-save button.
- Deliberate server stops no longer create false crash alerts.
