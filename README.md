# SSB (Simple Safe Backup)

Effortless, flexible backups anywhere—local or remote, even on removable drives, powered by rsync.

An rsync-based backup tool supporting local-to-local, local-to-remote, and remote-to-remote backups with source and destination paths possibly being on removable drives.

Rather than reinventing the wheel, this project leverages existing tools and libraries:
- rsync (and SSH) for performing the backups
- btrfs for performing incremental backups thanks to snapshotting (optional)
- cryptsetup for encryption (optional). Not directly used by the tool yet, but can be used to create encrypted volumes for storing backups

## Concepts

### Backup Config

Expressed in YAML. Sourced from the regular locations (e.g. `/etc/ssb/config.yaml`, `~/.config/ssb/config.yaml`, etc) and can also be provided as an argument when calling the backup tool.

#### Sync

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

### Rsync Remote Volume

A reusable configuration for a remote source or destination that can be shared between multiple syncs.
Provides the host, port, user, ssh key, and path to the remote volume.

To be considered active, a remote volume must have a `.ssb-vol` file in the root of the volume, and the server must be reachable.

### Example Config

```yaml
volumes:
  # Local volume on a removable drive
  laptop:
    type: local
    path: /mnt/data

  # Local volume on a btrfs filesystem
  usb-drive:
    type: local
    path: /mnt/usb-backup

  # Remote NAS accessible via SSH
  nas:
    type: remote
    host: nas.example.com
    port: 5022                  # optional, defaults to 22
    user: backup                # optional
    ssh_key: ~/.ssh/nas_ed25519 # optional
    path: /volume1/backups
    ssh_options:                # optional
      - StrictHostKeyChecking=no

syncs:
  # Simple local-to-remote sync
  photos-to-nas:
    source:
      volume: laptop
      subdir: photos            # optional subdirectory on the volume
    destination:
      volume: nas
      subdir: photos-backup
    enabled: true               # optional, defaults to true

  # Local-to-local sync with btrfs snapshots
  documents-to-usb:
    source:
      volume: laptop
      subdir: documents
    destination:
      volume: usb-drive
    btrfs_snapshots: true       # optional, defaults to false
```

## Features

### Commands

- run (with support for dry run)
- status (list the active syncs and volumes)

#### Outputs

All commands provide the following outputs:
- Human-readable logs (default)
- JSON


## Usage

### CLI

TODO: add CLI usage examples here.

#### Get help:
```bash
ssb --help
```

### Python API

TODO: add Python API usage examples here.

## Development

### Setup Development Environment

**Requirements:**
- Python 3.14 or higher

1. Install Poetry and other tools if you haven't already:
   ```bash
   # Mac OS X with Homebrew:
   brew install poetry docker
   # TODO: add asdf instructions

   # TODO: add instructions for other platforms
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Activate the virtual environment:
   ```bash
   poetry shell
   ```

### Running Tests

Run unit tests (no external dependencies):
```bash
make test
```

Run integration tests (requires Docker):
```bash
make test-integration
```

Run all checks (format, lint, type-check, unit tests):
```bash
make check
```

### Integration Tests

Integration tests exercise the real rsync/SSH/btrfs pipeline against a Docker container.

**Requirements:**
- Docker Desktop (or Docker Engine on Linux)

Run integration tests:
```bash
make test-integration
```

Run all tests (unit + integration):
```bash
make test-all
```

The integration test suite automatically:
- Generates an ephemeral SSH key pair
- Builds and starts a Docker container with SSH, rsync, and a btrfs filesystem
- Runs tests covering local-to-local, local-to-remote, remote-to-local syncs, btrfs snapshots, and status checks
- Tears down the container on completion

If Docker is not available, integration tests are skipped with a clear message.

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.


## TODO
- `status`: check existence of dependencies on remote volumes (rsync, btrfs-tools, etc) and report in the status output.
- Figure out poetry and asdf integration for Python version management and installation instructions.
- Makefile: is there a better way?