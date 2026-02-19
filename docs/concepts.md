## Concepts

## Backup Config

Expressed in YAML. Sourced from the regular locations (e.g. `/etc/ssb/config.yaml`, `~/.config/ssb/config.yaml`, etc) and can also be provided as an argument when calling the backup tool.

### Sync

A sync describes a source and destination pair with the relevant config (type of the backup, source and destination paths, server, etc).
Both the source and destination can be local or remote, and can be on removable drives.
The only supported backup type for now is rsync, but other backup types will be added in the future (e.g. git, etc).

For a sync to be considered active, both the source and the destination must provide a `.ssb-src` and `.ssb-dst` file respectively.
For remote sources/destinations, the server must be reachable for the corresponding sync to be active.

This is to ensure that when using removable drives, both the source and destinations are currently mounted / available to prevent data loss
or backups to the wrong drives.

For the rsync backup type, the source and the destination can either be a rsync local or a rsync remote volume, and can specify a subdirectory on the volume.

Individual syncs can be enabled or disabled when calling the backup tool.

A sync can optionally enable btrfs snapshots, which will be used to perform incremental backups.
This is only supported for local sources and destinations that are on btrfs volumes.

The latest backup will be stored under ${destination}/latest and snapshots (if enabled and supported) will be stored under ${destination}/snapshots/${iso8601_timestamp}.
When enabled, a new btrfs snapshot is created each time the backup completes.

### Rsync Local Volume

A reusable configuration for a local source or destination that can be shared between multiple syncs.

To be considered active, a local volume must have a `.ssb-vol` file in the root of the volume.

### Rsync Server

A reusable configuration for an SSH server that can be shared between multiple remote volumes.
Provides the host, port, user, ssh key, and ssh options.

### Rsync Remote Volume

A reusable configuration for a remote source or destination that can be shared between multiple syncs.
References an rsync server by name and provides the path to the remote volume.

To be considered active, a remote volume must have a `.ssb-vol` file in the root of the volume, and the server must be reachable.

### Example Config

```yaml
rsync-servers:
  # SSH connection details for the NAS
  nas:
    host: nas.example.com
    port: 5022                  # optional, defaults to 22
    user: backup                # optional
    ssh-key: ~/.ssh/nas_ed25519 # optional
    ssh-options:                # optional
      - StrictHostKeyChecking=no

volumes:
  # Local volume on a removable drive
  laptop:
    type: local
    path: /mnt/data

  # Local volume on a btrfs filesystem
  usb-drive:
    type: local
    path: /mnt/usb-backup

  # Remote volumes on the NAS — reference the server by name
  nas-backups:
    type: remote
    rsync-server: nas
    path: /volume1/backups

  nas-photos:
    type: remote
    rsync-server: nas
    path: /volume2/photos

syncs:
  # Simple local-to-remote sync
  photos-to-nas:
    source:
      volume: laptop
      subdir: photos            # optional subdirectory on the volume
    destination:
      volume: nas-photos
      subdir: photos-backup
    enabled: true               # optional, defaults to true

  # Local-to-local sync with btrfs snapshots
  documents-to-usb:
    source:
      volume: laptop
      subdir: documents
    destination:
      volume: usb-drive
      btrfs-snapshots: true     # optional, defaults to false
```
