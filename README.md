# Nomad Backup (nbkp)

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

Guiding Design Principles:
- Laptop-centric workflows
- Changing networks
-	Drives being plugged/unplugged
- Backups happening when possible
- Not always-on infrastructure
- Personal homelab / Raspberry Pi setups

In terms of implementation, rather than reinventing its own storage format, network protocol, and encryption mechanisms, 
this project leverages existing tools and libraries to keep things simple and reliable:
- Rsync (and SSH): Perform the backups locally and remotely, with support for filters, and more
- Plain directory: Files are stored as-is, no complicated restore process
- Btrfs snapshots: Optionally perform incremental backups thanks to snapshotting capabilities of btrfs, with automatic pruning of old snapshots based on retention policies. 
  Each snapshot (btrfs read-only subvolume) exposes a plain directory tree
- Cryptsetup: Optionally encrypt your backups using encrypted volumes

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

See [docs/usage.md](docs/usage.md) for detailed usage instructions for both the CLI and Python API, including examples.

## Architecture

See [docs/architecture.md](docs/architecture.md) for a detailed overview of the architecture, design patterns, and execution flow.

## Concepts

See [docs/concepts.md](docs/concepts.md) for explanations of key concepts such as volumes, syncs, and the configuration model.

## Conventions

See [docs/conventions.md](docs/conventions.md) for coding conventions, testing practices, and other guidelines for contributing to the codebase.

## Development

### Setup Development Environment

See [docs/setup-development-environment.md](docs/setup-development-environment.md) for instructions on setting up the development environment.

### Building and Testing

See [docs/building-and-testing.md](docs/building-and-testing.md) for instructions on how to run unit and integration tests, as well as formatting and linting checks.

### Releasing and Publishing

See [docs/releasing-and-publishing.md](docs/releasing-and-publishing.md) for instructions on how to create new releases and publish the package to PyPI.

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.

## TODO


Features:
- Dry run: actually call rsync with `--dry-run`
- Support for Remote to Remote? How do handle authentication and connectivity checks for both servers? rsync filter files., other problems?
- Git source support
- Dry run for both run and status: display all the commands that would be executed. Do we want additional option for that?
  - Even better? Can generate plain shell script to perform the backup to avoid any dependency on nbkp?
  - Should work with relative directory for destination, and should run on both linux and mac os X. Should include all the status checks
  - Goals: 1. make it easy to understand what the tool is doing 2. implement custom things without having to contribute to the codebase
  - Actually run rsync with --dry-run, and maybe pass -v automatically during dry-runs to provide more detailed output?
- Server: ability to use private vs public ip? CLI flag? List of IPs/hostnames to check for connectivity in order?
  `--private vs --public`
- Make it possible (optional) to perform syncs in parallel when there are no overlapping source or destination volumes.
- `troubleshoot` command: also provide instructions to help setting up encrypted volumes with cryptsetup, and maybe even trigger mounts using `systemd-run --pipe --wait systemctl start
  The tool can automatically mount and unmount these volumes, and support for storing encryption keys in the client OS keyring is planned.
- Add support for APFS snapshots on Mac OS X (APFS). Most likely at the volume level, no filesystem isolation (may require sudo)
- Add User-friendly error messages with malformed configuration, missing volumes, connectivity issues, etc. with actionable instructions to fix the issues.
- Dependencies between syncs to handle the use case of laptop -> server mount A. server mount A -> server mount B: we want server mount A -> server mount B to be performed after to sync the most up to date data 
- Backup log used + alerting of the user if something has not been backed up for a while (could use snapshots as well as a log, but not every backup is snapshot-enabled). add new monitoring config and command?
  - Store the backup logs in the destination volume
  - Could have a cache of the backup logs to make it possible to remind the user what backusp need to be done based on their targets/objectives
  - if we introduce run ids, should the run id be available in the snapshot (name?)?
  - + functionality to show backup logs and stats about the backups (last backup time, size, etc.)?
  - `history` command to show the backup logs and stats about the backups (last backup time, size, etc.)?
- Backups to cloud using other tools?
- list command to list current syncs
- status -> scan? status is a bit misleading as it implies that we are checking the status of the syncs, but we are actually scanning for available volumes and connectivity, and then displaying the syncs that can be performed based on that. Maybe `scan` is a better name for that command?

Testing
- `testcli` CLI app:
  - set up a docker environment to manually test the generated config and outputs, and to use for development in general?
- Improve automated tests
  - Add end to end tests with filters, and other more complex configurations.
  - add local tests with btrfs snapshots on docker, with nbkp fully installed as an app
  - add remote to remote tests with two docker containers, with ssh server set up on one of them, and nbkp?rsync fully installed as an app on both of them. Test connectivity checks, rsync backup, btrfs snapshots, etc.

Refactorings:
- Switch to [paramiko for SSH](https://www.paramiko.org/)?

Build & CI:
- Release & Publishing workflows:
  - Test the workflows using [TestPyPI](https://github.com/pypa/gh-action-pypi-publish#)
  - Create PyPI account
  - Enable the release workflows
- Add support for release branch? (`release/*`)

Doc:
- Add install instructions (from PyPI and from source) to the README
- Use cases instead of features
  - Provide comparison with borg and restic. Why nbkp over these alternatives.
- Testing strategy and practices in conventions
- Architecture: use mermaid diagram, and complete architecture overview
- Review Features, Usage, Architecture and Concepts sections
- `poetry config virtualenvs.in-project true` => conventions?
- Conventions: dry-run for all destructive operations
- document btrfs subvolume setup conventions used: one per destination
- Skills / conventions for all the tools / libraries used in the project? (pydantic, testcontainers, ...)
- Convention: When execuuting shell commands, use command lines expressed as arg array, not strings. This is safer and more robust, as it avoids issues with shell quoting and escaping. For example, instead of `subprocess.run("rsync -avz source/ destination/")`, use `subprocess.run(["rsync", "-avz", "source/", "destination/"])`. This also allows for better error handling and debugging, as you can easily see the exact command being executed without worrying about shell interpretation.
- Convention: assert pydantic errors in tests with `assert e.errors() == [...]` instead of just checking the error message string. This is more robust and less brittle, as it checks the actual structure and content of the validation errors rather than relying on specific wording in the error messages, which may change or be localized. For example, instead of `assert str(e) == "1 validation error for Config\nfield\n  field required (type=value_error.missing)"`, use `assert e.errors() == [{"loc": ("field",), "msg": "field required", "type": "value_error.missing"}]`. This also allows for better test coverage and clarity, as you can easily see which fields are causing validation errors and what the specific issues are.
- 4 types of documentation. Implement full documentation website? (Nuxt content, ...). Or maybe a python-specific doc generator?
- terminal demo: https://asciinema.org/

Features - Think harder about:
- Add support for mouting encrypted volumes using cryptsetup, and a key stored in the client OS keyring (python keyring library).
  - investigate what `secretstorage` ( D-Bus Secret Service API) can do on Linux
  - Problem: requires sudo permissions, so would need some sort of agent running directly on the machine, or a way to trigger mounts using a different mechanism
  - `systemd-run --pipe --wait systemctl start systemd-cryptsetup@securedata.service`
  - Other checks / troubleshooting instructions needed (cryptsetup, etc?)?
