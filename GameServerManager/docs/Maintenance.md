# Maintenance and Autostart

Game Server Manager separates Windows startup, automatic server startup, and scheduled maintenance.

## Windows startup options

### Start Game Server Manager at login

Creates a user-level startup entry that launches the manager from its current executable location.

### Start the active server automatically

When enabled, the manager starts the server currently marked **Active** after the application starts.

This option is independent of Windows startup. The combinations are:

| Manager startup | Active-server startup | Result |
|---:|---:|---|
| Off | Off | Nothing starts automatically |
| On | Off | Only the manager opens after login |
| On | On | Manager opens and starts the active server |
| Off | On | The active server starts whenever the user launches the manager |

The last combination can be useful, but users should be aware that opening the manager manually may then start the active server.

## Recovery after a Windows update

For automatic recovery after a Windows restart:

1. Mark the desired server as Active.
2. Enable **Start Game Server Manager at Windows login**.
3. Enable **Start active server automatically**.
4. Save Settings.
5. Test the behavior during a controlled restart before relying on it unattended.

The manager checks its tracked state and should avoid deliberately launching duplicate managed instances. Servers started outside the manager may not always be adoptable as fully managed console processes.

## Daily maintenance

Daily maintenance uses a user-specific Windows scheduled task and targets the server currently marked Active.

The implemented maintenance flow follows the application's existing server workflow:

```text
Stop
↓
Backup
↓
Update
↓
Start
```

The exact update behavior depends on the server type:

- Supported Minecraft types may use automatic stable updates.
- An optional update script may run for plugins or custom maintenance.
- Unsupported automatic-update types rely on their configured update script.

## Requirements

- The Windows user must be logged in.
- The computer must be awake.
- Game Server Manager must remain able to open in the interactive user session.
- The active server must have valid scripts and health checks for the required actions.

## Single-instance behavior

If a scheduled command runs while Game Server Manager is already open, the existing instance receives the action instead of opening a second full application window.

## Moving the executable

Windows startup and scheduled maintenance point to the current executable path. After moving the portable application folder:

1. Start the manager from the new location.
2. Open Settings.
3. Save the startup and maintenance settings again.

This refreshes Windows integration without requiring a fixed installation directory.

## Notifications

When ntfy is enabled, the manager can report failures such as:

- Unexpected server exit
- Failed automatic server startup
- Scheduled-maintenance failure
- Unhandled application exception

Use **Test ntfy** before relying on unattended notifications.
