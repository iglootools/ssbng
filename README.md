# Nomad Backup (nbkp)

![Stable Version](https://img.shields.io/pypi/v/nbkp?label=stable)
![Pre-release Version](https://img.shields.io/github/v/release/iglootools/nbkp?label=pre-release&include_prereleases&sort=semver)
![Python Versions](https://img.shields.io/pypi/pyversions/nbkp)
![Download Stats](https://img.shields.io/pypi/dm/nbkp)
![GitHub Stars](https://img.shields.io/github/stars/iglootools/nbkp)
![License](https://img.shields.io/github/license/iglootools/nbkp)
![CI Status](https://github.com/iglootools/nbkp/actions/workflows/test.yml/badge.svg?branch=main)

A robust backup tool powered by rsync, designed for both local and remote targets—including removable drives and intermittently available backup servers. 
It optionally leverages btrfs snapshots for incremental backups and encrypted volumes for enhanced security.

## Main Use Cases

While not being limited to these, the tool is primarily designed to address the following backup use cases:
- **Laptop to Server**: Back up files on your laptop to your home server whenever you are on the home network
- **Laptop to External Drive**: Back up files on your laptop to an external drive whenever it is connected
- **Laptop External Drive to Server**: Back up files from an external drive to your home server whenever the drive is connected and you are on the home network
- **Server to External Drive**: Back up files on your home server to an external drive whenever it is connected

Think of it as a tool replacing the rsync-based shell scripts you would write to back up your data to external drives or to your Raspberry Pi server, but with 
- Automatic detection of available/mounted source and destination volumes (to account for the fact that backup servers and external drives are not always available)
- Support for btrfs snapshots (to protect against corrupting the backups with corrupted/deleted data)
- A more robust configuration model
- Better error handling

## Philosophy

**Guiding Design Principles**
- Laptop-centric workflows
- Changing networks
-	Drives being plugged/unplugged
- Backups happening when possible
- Not always-on infrastructure
- Personal homelab / Raspberry Pi setups

**Implementation Principles**
Rather than reinventing its own storage format, network protocol, and encryption mechanisms, 
the project leverages existing tools and libraries to keep things simple and reliable:
- Rsync (and SSH): Perform the backups locally and remotely, with support for filters, and more
- Plain directory: Files are stored as-is, no complicated restore process
- Btrfs snapshots: Optionally perform incremental backups thanks to the snapshotting capabilities of btrfs, with automatic pruning of old snapshots based on retention policies. 
  Each snapshot (btrfs read-only subvolume) exposes a plain directory tree
- Cryptsetup: Optionally encrypt your backups using encrypted volumes

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


## Features

TODO

### Commands

- run (with support for dry run)
- status (list the active syncs and volumes)

TODO

#### Outputs

All commands provide the following outputs:
- Human-readable logs (default)
- JSON

## Usage

See [docs/usage.md](https://github.com/iglootools/nbkp/blob/main/docs/usage.md) for detailed usage instructions for both the CLI and Python API, including examples.

## Architecture

See [docs/architecture.md](https://github.com/iglootools/nbkp/blob/main/docs/architecture.md) for a detailed overview of the architecture, design patterns, and execution flow.

## Concepts

See [docs/concepts.md](https://github.com/iglootools/nbkp/blob/main/docs/concepts.md) for explanations of key concepts such as volumes, syncs, and the configuration model.

## Conventions

See [docs/conventions.md](https://github.com/iglootools/nbkp/blob/main/docs/conventions.md) for coding conventions, testing practices, and other guidelines for contributing to the codebase.

## Development

### Setup Development Environment

See [docs/setup-development-environment.md](https://github.com/iglootools/nbkp/blob/main/docs/setup-development-environment.md) for instructions on setting up the development environment.

### Building and Testing

See [docs/building-and-testing.md](https://github.com/iglootools/nbkp/blob/main/docs/building-and-testing.md) for instructions on how to run unit and integration tests, as well as formatting and linting checks.

### Releasing and Publishing

See [docs/releasing-and-publishing.md](https://github.com/iglootools/nbkp/blob/main/docs/releasing-and-publishing.md) for instructions on how to create new releases and publish the package to PyPI.

## License

This project is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) - see the LICENSE file for details.

