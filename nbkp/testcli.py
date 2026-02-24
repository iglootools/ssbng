"""Developer test CLI: fake output rendering and seed data."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console

from .config import (
    BtrfsSnapshotConfig,
    Config,
    ConfigError,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SshOptions,
    SyncConfig,
    SyncEndpoint,
)
from .testkit.docker import (
    CONTAINER_NAME,
    DOCKER_DIR,
    check_docker,
    generate_ssh_keypair,
    ssh_exec,
    start_docker_container,
    wait_for_ssh,
)
from .config.protocol import Config as ConfigModel
from .output import (
    print_config_error,
    print_human_check,
    print_human_config,
    print_human_prune_results,
    print_human_results,
    print_human_troubleshoot,
)
from .testkit.gen.check import (
    check_config,
    check_data,
    troubleshoot_config,
    troubleshoot_data,
)
from .testkit.gen.config import config_show_config
from .testkit.gen.fs import (
    create_seed_data,
    create_seed_markers,
)
from .testkit.gen.sync import (
    dry_run_result,
    prune_dry_run_results,
    prune_results,
    run_results,
)

_INDENT = "  "
_console = Console()

app = typer.Typer(
    name="nbkp-test",
    help="NBKP developer test CLI",
    no_args_is_help=True,
)


# ── Commands ─────────────────────────────────────────────────────


@app.command()
def output() -> None:
    """Render all human output functions with fake data."""
    _show_config_show()
    _show_check()
    _show_results()
    _show_prune()
    _show_troubleshoot()
    _show_config_errors()


def _show_config_show() -> None:
    _console.rule("print_human_config")
    config = config_show_config()
    print_human_config(config)


def _show_check() -> None:
    _console.rule("print_human_check")
    config = check_config()
    vol_statuses, sync_statuses = check_data(config)
    print_human_check(vol_statuses, sync_statuses, config)


def _show_results() -> None:
    _console.rule("print_human_results (run)")
    print_human_results(run_results(), dry_run=False)

    _console.rule("print_human_results (dry run)")
    print_human_results([dry_run_result()], dry_run=True)


def _show_prune() -> None:
    _console.rule("print_human_prune_results (prune)")
    print_human_prune_results(prune_results(), dry_run=False)

    _console.rule("print_human_prune_results (dry run)")
    print_human_prune_results(prune_dry_run_results(), dry_run=True)


def _show_troubleshoot() -> None:
    _console.rule("print_human_troubleshoot")
    config = troubleshoot_config()
    vol_statuses, sync_statuses = troubleshoot_data(config)
    print_human_troubleshoot(vol_statuses, sync_statuses, config)


def _show_config_errors() -> None:
    _console.rule("print_config_error (file not found)")
    print_config_error(
        ConfigError("Config file not found: /etc/nbkp/config.yaml")
    )

    _console.rule("print_config_error (invalid YAML)")
    try:
        yaml.safe_load("not_a_list:\n  - [invalid")
    except yaml.YAMLError as ye:
        err = ConfigError(f"Invalid YAML in /etc/nbkp/config.yaml: {ye}")
        err.__cause__ = ye
        print_config_error(err)

    _console.rule("print_config_error (invalid volume type)")
    try:
        ConfigModel.model_validate(
            {"volumes": {"v": {"type": "ftp", "path": "/x"}}}
        )
    except ValidationError as ve:
        err = ConfigError(str(ve))
        err.__cause__ = ve
        print_config_error(err)

    _console.rule("print_config_error (unknown server reference)")
    try:
        ConfigModel.model_validate(
            {
                "rsync-servers": {},
                "volumes": {
                    "v": {
                        "type": "remote",
                        "rsync-server": "missing",
                        "path": "/x",
                    },
                },
                "syncs": {},
            }
        )
    except ValidationError as ve:
        err = ConfigError(str(ve))
        err.__cause__ = ve
        print_config_error(err)

    _console.rule("print_config_error (missing required field)")
    try:
        ConfigModel.model_validate(
            {"volumes": {"v": {"type": "local"}}, "syncs": {}}
        )
    except ValidationError as ve:
        err = ConfigError(str(ve))
        err.__cause__ = ve
        print_config_error(err)


@app.command()
def seed(
    big_file_size: Annotated[
        int,
        typer.Option(
            "--big-file-size",
            help="Size in MB for large files (e.g. 100, 1024)."
            " When set, large files are written at this size"
            " to slow down syncs."
            " Set to 0 to disable.",
        ),
    ] = 1024,
    docker: Annotated[
        bool,
        typer.Option(
            "--docker",
            help="Start a Docker container for remote syncs.",
        ),
    ] = False,
) -> None:
    """Create a temp folder with config and test data."""
    if docker:
        check_docker()
        if not DOCKER_DIR.is_dir():
            typer.echo(
                "Error: Docker directory not found:" f" {DOCKER_DIR}",
                err=True,
            )
            raise typer.Exit(1)

    tmp = Path(tempfile.mkdtemp(prefix="nbkp-seed-"))
    src = tmp / "src-data"
    dst = tmp / "dst-backup"

    # Docker container
    docker_server: RsyncServer | None = None
    if docker:
        private_key, pub_key = generate_ssh_keypair(tmp)
        with _console.status("Starting Docker container..."):
            docker_port = start_docker_container(pub_key)
        docker_server = RsyncServer(
            slug="docker",
            host="127.0.0.1",
            port=docker_port,
            user="testuser",
            ssh_key=str(private_key),
            ssh_options=SshOptions(
                strict_host_key_checking=False,
                known_hosts_file="/dev/null",
            ),
        )
        with _console.status("Waiting for SSH..."):
            wait_for_ssh(docker_server)

    # Config
    rsync_servers: dict[str, RsyncServer] = {}
    volumes: dict[str, LocalVolume | RemoteVolume] = {
        "src-data": LocalVolume(slug="src-data", path=str(src)),
        "dst-backup": LocalVolume(slug="dst-backup", path=str(dst)),
    }
    syncs: dict[str, SyncConfig] = {
        "photos-backup": SyncConfig(
            slug="photos-backup",
            source=SyncEndpoint(volume="src-data", subdir="photos"),
            destination=DestinationSyncEndpoint(volume="dst-backup"),
        ),
        "full-backup": SyncConfig(
            slug="full-backup",
            source=SyncEndpoint(volume="src-data"),
            destination=DestinationSyncEndpoint(volume="dst-backup"),
        ),
    }

    if docker:
        assert docker_server is not None
        rsync_servers["docker"] = docker_server
        volumes["remote-backup"] = RemoteVolume(
            slug="remote-backup",
            rsync_server="docker",
            path="/data",
        )
        volumes["remote-btrfs"] = RemoteVolume(
            slug="remote-btrfs",
            rsync_server="docker",
            path="/mnt/btrfs",
        )
        syncs["photos-to-remote"] = SyncConfig(
            slug="photos-to-remote",
            source=SyncEndpoint(volume="src-data", subdir="photos"),
            destination=DestinationSyncEndpoint(
                volume="remote-backup",
            ),
        )
        syncs["full-to-remote-btrfs"] = SyncConfig(
            slug="full-to-remote-btrfs",
            source=SyncEndpoint(volume="src-data"),
            destination=DestinationSyncEndpoint(
                volume="remote-btrfs",
                btrfs_snapshots=BtrfsSnapshotConfig(
                    enabled=True, max_snapshots=5
                ),
            ),
        )

    config = Config(
        rsync_servers=rsync_servers,
        volumes=volumes,
        syncs=syncs,
    )

    # Create markers and seed data
    if docker:
        assert docker_server is not None
        _server = docker_server

        def _run_remote(cmd: str) -> None:
            ssh_exec(_server, cmd)

        with _console.status("Setting up volumes..."):
            create_seed_markers(config, remote_exec=_run_remote)
    else:
        create_seed_markers(config)
    create_seed_data(config, big_file_size_mb=big_file_size)

    config_path = tmp / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            config.model_dump(by_alias=True),
            default_flow_style=False,
            sort_keys=False,
        )
    )

    backup_sh = tmp / "backup.sh"

    # Print summary
    seed_label = "Seed directory:"
    cfg_label = "Config file:"
    labels = [seed_label, cfg_label]
    if docker:
        docker_label = "Docker container:"
        labels.append(docker_label)
    w = max(len(label) for label in labels)
    typer.echo(f"{seed_label:<{w}} {tmp}")
    typer.echo(f"{cfg_label:<{w}} {config_path}")
    if docker:
        assert docker_server is not None
        typer.echo(
            f"{docker_label:<{w}} {CONTAINER_NAME}"
            f" (port {docker_server.port})"
        )
    typer.echo()
    typer.echo("Try:")
    typer.echo("poetry install, then run:")
    typer.echo()
    typer.echo(f"{_INDENT}# Show parsed configuration")
    typer.echo(f"{_INDENT}nbkp config show" f" --config {config_path}")
    typer.echo()
    typer.echo(f"{_INDENT}# Show configuration as JSON")
    typer.echo(
        f"{_INDENT}nbkp config show"
        f" --config {config_path}"
        f" --output json"
    )
    typer.echo()
    typer.echo(f"{_INDENT}# Volume and sync health checks")
    typer.echo(f"{_INDENT}nbkp check --config {config_path}")
    typer.echo()
    typer.echo(f"{_INDENT}# Preview what rsync would do" f" without changes")
    typer.echo(f"{_INDENT}nbkp run" f" --config {config_path} --dry-run")
    typer.echo()
    typer.echo(f"{_INDENT}# Execute backup syncs")
    typer.echo(f"{_INDENT}nbkp run --config {config_path}")
    typer.echo()
    typer.echo(f"{_INDENT}# Prune old btrfs snapshots")
    typer.echo(f"{_INDENT}nbkp prune --config {config_path}")
    typer.echo()
    typer.echo(f"{_INDENT}# Generate standalone bash script" f" to stdout")
    typer.echo(f"{_INDENT}nbkp sh --config {config_path}")
    typer.echo()
    typer.echo(
        f"{_INDENT}# Write script to file," f" validate syntax, and run"
    )
    typer.echo(
        f"{_INDENT}nbkp sh --config {config_path}"
        f"  -o {backup_sh} \\\n"
        f"{_INDENT} && bash -n {backup_sh} \\\n"
        f"{_INDENT} && {backup_sh} --dry-run \\\n"
        f"{_INDENT} && {backup_sh}"
    )
    typer.echo()
    typer.echo(f"{_INDENT}# With Relative paths (src and dst)")
    typer.echo(
        f"{_INDENT}nbkp sh --config {config_path}"
        f"  -o {backup_sh}"
        f" --relative-src --relative-dst \\\n"
        f"{_INDENT} && bash -n {backup_sh} \\\n"
        f"{_INDENT} && {backup_sh} --dry-run \\\n"
        f"{_INDENT} && {backup_sh}"
    )
    typer.echo()

    if docker:
        typer.echo(f"{_INDENT}# Teardown Docker container")
        typer.echo(f"{_INDENT}docker rm -f {CONTAINER_NAME}")
        typer.echo()


def main() -> None:
    """Test CLI entry point."""
    app()


if __name__ == "__main__":
    main()
