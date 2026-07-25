# Backups

Game Server Manager stores local backups and applies count-based retention plus a per-server storage limit.

## Backup types

- **Full:** complete configured backup selection for the server
- **World:** world or save data
- **Plugin update:** safety backup associated with plugin maintenance
- **Server update:** safety backup created before a server update
- **Manual:** user-triggered backup

Backups include manifests and SHA-256 checksums where supported by the current backup workflow.

## Default retention

The default `config/backup_rules.json` contains:

| Backup type | Retained count |
|---|---:|
| Full | 5 |
| World | 20 |
| Plugin update | 10 |
| Server update | 5 |
| Manual | 10 |

The default maximum storage is **50 GB per registered server**. At least the two newest full backups are protected by the default policy.

Count-based cleanup runs before storage-limit cleanup. When more space must be freed, older non-full backups are removed before protected full backups.

## Default exclusions

The default rules exclude common transient data such as:

```text
logs/**
.paper-remapped/**
**/cache/**
**/tmp/**
**/temp/**
**/*.tmp
**/*.lock
**/session.lock
```

Review exclusions before relying on backups for a server with an unusual layout.

## Server-specific behavior

### Minecraft Java

World directories are detected automatically. Full and world backups use the detected world layout.

### Minecraft Bedrock

The `worlds` directory is handled automatically.

### Windrose

Default selection:

```text
R5/Saved/SaveProfiles/Default
R5/ServerDescription.json
```

A root-level `ServerDescription.json` may be used by some layouts.

### Factorio

The manager selects the `saves` directory and common server JSON configuration files when present.

### Valheim

Automatic portable backup selection requires a `-savedir` inside the managed server directory. Save data outside the selected server folder is not silently copied into the portable backup set.

### ARK Evolved and Ascended

Default selection:

```text
ShooterGame/Saved
```

### Generic servers

Open the backup-selection dialog in the Scripts tab and add the required files and folders manually.

## Safe backup practice

- Stop the server before a full or save backup unless the server integration explicitly guarantees a consistent live snapshot.
- Scheduled maintenance stops the active server before its safety backup.
- Test restoration before treating backups as production-ready.
- Keep an additional copy on another disk or system. Local retention protects against mistakes and updates, but not against disk failure, theft, or complete host loss.
- Do not store active backups inside the server directory being backed up.

## Changing the backup root

The backup root can be changed in Settings. Existing archives are not moved automatically. Move them manually only while the manager and all servers are stopped.

## Restoring

The application currently focuses on creating and retaining backups. A careful manual restoration process is recommended:

1. Stop the server.
2. Create a copy of the current server data.
3. Verify the selected backup and checksum information.
4. Extract or copy the required files to the correct server location.
5. Start the server and review its console and health checks.
