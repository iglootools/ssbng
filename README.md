# Nomad Backup (nbkp)

![Stable Version](https://img.shields.io/pypi/v/nbkp?label=stable)
![Pre-release Version](https://img.shields.io/github/v/release/iglootools/nbkp?label=pre-release&include_prereleases&sort=semver)
![Python Versions](https://img.shields.io/pypi/pyversions/nbkp)
![Download Stats](https://img.shields.io/pypi/dm/nbkp)
![GitHub Stars](https://img.shields.io/github/stars/iglootools/nbkp)
![License](https://img.shields.io/github/license/iglootools/nbkp)
![CI Status](https://github.com/iglootools/nbkp/actions/workflows/test.yml/badge.svg?branch=main)

A robust backup tool powered by rsync, designed for both local and remote targets—including removable drives and intermittently available backup servers. 
It optionally leverages btrfs snapshots to retain historical backups space-efficiently, and encrypted volumes for enhanced security.

## Main Use Cases

The tool is primarily designed for the following backup scenarios:
- **Laptop to Server** — back up to your home server whenever you're on the home network
- **Laptop to External Drive** — back up to an external drive whenever it's connected
- **External Drive to Server** — replicate an external drive to your home server when both are available
- **Server to External Drive** — back up your home server to an external drive, piloted from your laptop

It replaces the rsync shell scripts you'd normally maintain, adding:
- **Volume detection** — only runs when sources and destinations are actually available
- **Btrfs snapshots** — keeps point-in-time copies so a bad sync can't wipe good backups
- **Declarative config** — one YAML file describes all your backup pairs
- **Structured output** — human-readable and JSON output for scripting and automation

Full feature list: [docs/features.md](https://github.com/iglootools/nbkp/blob/main/docs/features.md).

## Philosophy

**Design Principles**
- Laptop-centric workflows
- Changing networks
-	Drives being plugged/unplugged
- Backups happening when possible
- Not always-on infrastructure
- Personal homelab / Raspberry Pi setups

**Implementation Principles**
No custom storage format, protocol, or encryption — just proven tools composed together:
- **rsync + SSH** — handles the actual file transfer, locally or remotely
- **Plain directories** — files are stored as-is; restoring is just a copy
- **Btrfs snapshots (optional)** — space-efficient point-in-time copies via copy-on-write, with automatic pruning. Each snapshot is a read-only subvolume exposing a plain directory tree
- **cryptsetup (optional)** — full-volume encryption for backup destinations

**Nomad backup metaphor**
A nomad:
- Moves between places
- Sets up temporary camp
- Carries essential belongings
- Adapts to environment
- Relies on what is present

Which maps to:
- Laptop
- External drive
- Home server
- Network availability
- Mount detection

## Installation

See [docs/installation.md](https://github.com/iglootools/nbkp/blob/main/docs/installation.md).

## Usage

See [docs/usage.md](https://github.com/iglootools/nbkp/blob/main/docs/usage.md).

## Concepts

See [docs/concepts.md](https://github.com/iglootools/nbkp/blob/main/docs/concepts.md).

## Contribute
- [docs/architecture.md](https://github.com/iglootools/nbkp/blob/main/docs/architecture.md) - architecture overview
- [docs/conventions.md](https://github.com/iglootools/nbkp/blob/main/docs/conventions.md) — coding conventions and guidelines
- [docs/setup-development-environment.md](https://github.com/iglootools/nbkp/blob/main/docs/setup-development-environment.md) — development setup
- [docs/building-and-testing.md](https://github.com/iglootools/nbkp/blob/main/docs/building-and-testing.md) — running tests and checks
- [docs/releasing-and-publishing.md](https://github.com/iglootools/nbkp/blob/main/docs/releasing-and-publishing.md) — releases and PyPI publishing

## Resources
- [Releases](https://pypi.org/project/nbkp/#history)
- [Issue Tracker](https://github.com/iglootools/nbkp/issues)

## Related Projects

### Dependencies
- [rsync](https://rsync.samba.org/) — the underlying file synchronization tool
- [btrfs](https://btrfs.wiki.kernel.org/index.php/Main_Page) — for space-efficient point-in-time copies via copy-on-write
- [cryptsetup](https://gitlab.com/cryptsetup/cryptsetup) — for full-volume encryption
- [typer](https://typer.tiangolo.com/) — for building the CLI interface
- [pydantic](https://pydantic.dev/) — for data modeling and validation

### Similar Tools

There are a number of open source backup tools that use rsync, btrfs, or similar principles. This section describes how `nbkp` compares to some of the popular ones.
If you believe that the representation is inaccurate or if there are other tools that should be included in this list, please submit an issue or PR to update this section.

#### Rsync-based

- **[rsnapshot](https://rsnapshot.org/)** — periodic snapshots via rsync + hard links (hourly/daily/weekly/monthly). Designed for server/cron use with no awareness of removable or intermittent targets. Files stored as plain directories.
- **[Back In Time](https://github.com/bit-team/backintime)** — GUI/CLI tool using rsync + hard links with scheduling and encfs encryption. Provides a Qt interface; uses hard links instead of btrfs snapshots; no sentinel-file mechanism for removable drives.
- **[rsync-time-backup](https://github.com/laurent22/rsync-time-backup)** — Time Machine-style shell script using rsync `--link-dest`. Single script, no config file; uses hard links instead of btrfs snapshots; no volume detection.
- **[rdiff-backup](https://rdiff-backup.net/)** — keeps the latest backup as a plain mirror, stores reverse diffs for older versions. Older versions require the tool to reconstruct; no removable-drive awareness.
- **[Dirvish](https://dirvish.org/)** — rotating network backup system using rsync + hard links. Oriented toward server-pull workflows; no removable-drive detection or btrfs support.

#### Deduplicating

- **[BorgBackup](https://www.borgbackup.org/)** — chunk-level deduplication with compression and authenticated encryption. Proprietary repository format (not plain directories); requires `borg` on the remote side; no removable-drive detection.
- **[Restic](https://restic.net/)** — content-addressable backups with encryption by default, supporting many backends (local, S3, SFTP, B2). Proprietary format; restoring requires the restic tool; no volume detection.
- **[Duplicity](https://duplicity.us/)** — GPG-encrypted tar volumes with librsync incremental transfers. Not browsable as plain directories; full+incremental chain model; no btrfs integration.
- **[Kopia](https://kopia.io/)** — content-addressable storage with encryption, compression, and both CLI/GUI. Proprietary format; includes an optional scheduling server; no removable-drive or btrfs support.

#### Btrfs / snapshot-focused

- **[btrbk](https://github.com/digint/btrbk)** — btrfs-native snapshot management with send/receive for remote transfers. Btrfs-only (no rsync); more sophisticated retention policies (hourly/daily/weekly/monthly); no non-btrfs filesystem support.
- **[Snapper](http://snapper.io/)** — automated btrfs snapshot creation with timeline-based retention and rollback. Local snapshot management only; no rsync or remote transfer; no external backup targets.
- **[Timeshift](https://github.com/linuxmint/timeshift)** — system restore via rsync + hard links or btrfs snapshots. Targets root filesystem for system-level rollback; excludes user data by default; no remote backup.

## License

This project is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) - see the LICENSE file for details.

