# Device-Aware Backup (dab)

A flexible, rsync-powered backup tool for local and remote targets using removable drives—optionally leveraging btrfs snapshots and encrypted volumes.

Rather than reinventing its own storage format, network protocol, and encryption mechanisms, this project leverages existing tools and libraries:
- rsync (and SSH) for performing the backups locally and remotely, with support for filters, and more
- no complicated restore process: the backup is just a copy of the source files, so you can restore by simply copying the files back to their original location
- btrfs snapshots to  performing incremental backups thanks to snapshotting (optional)
- cryptsetup for encryption (optional). Not directly used by the tool yet, but can be used to create encrypted volumes for storing backups

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

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.

## TODO


Features:
- Support for Remote to Remote? How do handle authentication and connectivity checks for both servers? rsync filter files., other problems?
- Git source support
- Dry run for both run and status: display all the commands that would be executed. Do we want additional option for that?
  - Even better? Can generate plain shell script to perform the backup to avoid any dependency on dab?
  - Should work with relative directory for destination, and should run on both linux and mac os X. Should include all the status checks
  - Goals: 1. make it easy to understand what the tool is doing 2. implement custom things without having to contribute to the codebase
  - Actually run rsync with --dry-run, and maybe pass -v automatically during dry-runs to provide more detailed output?
- Server: ability to use private vs public ip? CLI flag? List of IPs/hostnames to check for connectivity in order?
  `--private vs --public`
- Make it possible (optional) to perform syncs in parallel when there are no overlapping source or destination volumes.

Refactorings:
- Switch to [paramiko for SSH](https://www.paramiko.org/)?

Build & CI:
- Add Github workflows
- packaging and publishing (PyPI) to use as a regular app
- Conventional commit changelog release system / workflow
- Add to `testcli` CLI app:
  - set up a docker environment to manually test the generated config and outputs, and to use for development in general?
- Dry run: actually call rsync with `--dry-run`
- Distribution
  - Make it possible to install and run using tools such as pipx
- Improve automated tests
  - Add end to end tests with filters, and other more complex configurations.
  - add local tests with btrfs snapshots on docker, with dab fully installed as an app
  - add remote to remote tests with two docker containers, with ssh server set up on one of them, and dab?rsync fully installed as an app on both of them. Test connectivity checks, rsync backup, btrfs snapshots, etc.

Doc:
- Use cases instead of features
  - Provide comparison with borg and restic. Why dab over these alternatives.
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

Bugs:
- can prune work without sudo?
  Deleting readonly btrfs subvolumes requires either `CAP_SYS_ADMIN` or the `user_subvol_rm_allowed` mount option.
  The integration test Docker setup uses `mount -o user_subvol_rm_allowed` to allow the unprivileged testuser to delete snapshots.
  For production use, the btrfs volume should be mounted with `user_subvol_rm_allowed` or the user should have `CAP_SYS_ADMIN`.
  https://unix.stackexchange.com/questions/88932/why-cant-a-regular-user-delete-a-btrfs-subvolume