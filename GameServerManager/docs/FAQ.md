# Frequently Asked Questions

## Does Game Server Manager install game servers?

No. It manages existing server installations. Server creation, SteamCMD installation, and automatic generation of complete start scripts are outside the current scope.

## Does the application require a fixed installation directory?

No. The project is portable. Application-owned paths are resolved from the source project or the folder containing `GameServerManager.exe`.

## Can I move the manager after configuring it?

Yes, but move the complete portable folder and save Settings again afterward when Windows startup or scheduled maintenance is enabled. External absolute server paths remain unchanged.

## Are server scripts copied into the manager?

No. Scripts remain inside each managed server directory. Only their paths are stored.

## Why is there no restart script?

Restart is always implemented as Stop followed by Start. This keeps behavior consistent and avoids an additional script type.

## Will the active server return after a Windows update restart?

Yes, when both Windows startup and automatic active-server startup are enabled. Test the setup with a controlled restart first.

## Why must the user be logged in for maintenance?

The managed server console is attached to the desktop application. Scheduled maintenance therefore runs in the interactive user session rather than as a background Windows service.

## Does ntfy require credentials?

Not when using a public topic on `https://ntfy.sh`. Choose a long, unique topic name because anyone who knows that public topic can subscribe to it. A self-hosted ntfy server may use its own authentication rules.

## Is ntfy email?

No. ntfy delivers push notifications through its app, browser interface, or compatible clients.

## What does the traffic light mean?

- Green: server is running
- Yellow: an update or another manager operation is in progress
- Red: server is stopped

## Why is a detected server shown as Generic?

Detection is conservative. Verify that the expected executable and layout exist below the selected folder. You can still configure start, stop, update, and backup paths manually for a Generic server.

## Can the manager control a server started outside the application?

Reliable console input and exact process tracking require the server to be started by the manager. An externally started process may not be fully controllable or adoptable.

## Why does Valheim not receive an automatic backup selection?

The manager only auto-selects Valheim data when the start configuration uses `-savedir` inside the managed server folder. This avoids silently depending on user-profile data outside the portable installation.

## Does ARK receive an automatic backup selection?

Yes. ARK Evolved and Ascended use `ShooterGame/Saved` as the conservative default backup root.

## Does Factorio stop safely?

When attached to the integrated console, Factorio uses the `/quit` command.

## Does Minecraft Bedrock use the same handling as Java?

It shares safe console stopping and world backup concepts, but Bedrock uses `bedrock_server.exe`, `server.properties`, and the `worlds` directory. Java-specific plugin handling does not apply.

## Are backups stored in the cloud?

No. Backups are local. For disaster recovery, copy important backups to another physical disk or remote system.

## Is there telemetry?

No telemetry is included.

## Where are configuration files stored?

In the `config` folder next to the source project or executable. Important files include:

```text
config/settings.json
config/servers.json
config/backup_rules.json
```

## How do I diagnose a build or startup problem?

Build a console-enabled executable:

```powershell
.\build.ps1 -Console -Clean
```

Also review the `logs` directory and remove secrets before sharing log excerpts publicly.
