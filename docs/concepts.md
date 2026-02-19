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
Provides the host, port, user, ssh key, ssh options, and connect timeout.

The `connect-timeout` field controls the SSH connection timeout in seconds (default: `10`).

### Rsync Remote Volume

A reusable configuration for a remote source or destination that can be shared between multiple syncs.
References an rsync server by name and provides the path to the remote volume.

To be considered active, a remote volume must have a `.ssb-vol` file in the root of the volume, and the server must be reachable.

### Rsync Options

By default, every sync uses the following rsync flags: `-a --delete --delete-excluded --safe-links`. The `-v` flag is not included by default; pass `-v`, `-vv`, or `-vvv` to the `run` command to increase rsync verbosity. Two optional fields let you customise the flags per sync:

**`rsync-options`** — replaces the default flags entirely:

```yaml
syncs:
  my-sync:
    rsync-options:
      - "-a"
      - "--delete"
```

**`extra-rsync-options`** — appends additional flags after the defaults (or after `rsync-options` when both are set):

```yaml
syncs:
  my-sync:
    extra-rsync-options:
      - "--compress"
      - "--progress"
```

When neither field is set, the defaults are used unchanged.

### Filters

A sync can optionally define rsync filters to control which files are included or excluded during the backup. There are three complementary mechanisms:

**Structured rules** — `include` / `exclude` dictionaries that are normalized into rsync filter syntax:

```yaml
filters:
  - include: "*.jpg"    # becomes "+ *.jpg"
  - exclude: "*.tmp"    # becomes "- *.tmp"
```

**Raw rsync filter strings** — passed directly to rsync's `--filter` option, supporting the full rsync filter syntax:

```yaml
filters:
  - "H .git"            # hide .git
  - "- __pycache__/"    # exclude __pycache__
```

Structured and raw filters can be mixed freely in the same list. They are applied in order as `--filter=RULE` arguments.

**External filter file** — a path to a file containing rsync filter rules in native rsync syntax, applied via `--filter=merge FILE`:

```yaml
filter-file: ~/.config/ssb/filters/photos.rules
```

When both inline `filters` and `filter-file` are present, inline filters are applied first, followed by the filter file.

### Example Config

```yaml
rsync-servers:
  # SSH connection details for the NAS
  nas:
    host: nas.example.com
    port: 5022                  # optional, defaults to 22
    user: backup                # optional
    ssh-key: ~/.ssh/nas_ed25519 # optional
    connect-timeout: 30         # optional, defaults to 10 (seconds)
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
  # Local-to-remote sync with filters
  photos-to-nas:
    source:
      volume: laptop
      subdir: photos            # optional subdirectory on the volume
    destination:
      volume: nas-photos
      subdir: photos-backup
    enabled: true               # optional, defaults to true
    filters:                    # optional rsync filters
      - include: "*.jpg"        # structured include rule
      - include: "*.png"
      - exclude: "*.tmp"        # structured exclude rule
      - "H .git"                # raw rsync filter string
    filter-file: ~/.config/ssb/filters/photos.rules  # optional

  # Local-to-local sync with btrfs snapshots
  documents-to-usb:
    source:
      volume: laptop
      subdir: documents
    destination:
      volume: usb-drive
      btrfs-snapshots: true     # optional, defaults to false

  # Sync with custom rsync options
  music-to-nas:
    source:
      volume: laptop
      subdir: music
    destination:
      volume: nas-backups
      subdir: music-backup
    extra-rsync-options:        # optional, appended to defaults
      - "--compress"
      - "--progress"
```
