"""Developer test CLI: fake output rendering and seed data."""

from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

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

_console = Console()

app = typer.Typer(
    name="nbkp-test",
    help="NBKP developer test CLI",
    no_args_is_help=True,
)


# ── Commands ─────────────────────────────────────────────────────


def _capture_console() -> tuple[Console, StringIO]:
    """Create a Console that captures output to a StringIO buffer."""
    buf = StringIO()
    console = Console(
        file=buf,
        force_terminal=True,
        width=_console.width - 4,
    )
    return console, buf


def _print_panel(title: str, buf: StringIO) -> None:
    """Wrap captured console output in a titled panel."""
    content = Text.from_ansi(buf.getvalue().rstrip("\n"))
    _console.print(
        Panel(
            content,
            title=f"[bold]{title}[/bold]",
            border_style="cyan",
            padding=(0, 1),
        )
    )


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
    console, buf = _capture_console()
    config = config_show_config()
    print_human_config(config, console=console)
    _print_panel("print_human_config", buf)


def _show_check() -> None:
    console, buf = _capture_console()
    config = check_config()
    vol_statuses, sync_statuses = check_data(config)
    print_human_check(vol_statuses, sync_statuses, config, console=console)
    _print_panel("print_human_check", buf)


def _show_results() -> None:
    console, buf = _capture_console()
    print_human_results(run_results(), dry_run=False, console=console)
    _print_panel("print_human_results (run)", buf)

    console, buf = _capture_console()
    print_human_results([dry_run_result()], dry_run=True, console=console)
    _print_panel("print_human_results (dry run)", buf)


def _show_prune() -> None:
    console, buf = _capture_console()
    print_human_prune_results(prune_results(), dry_run=False, console=console)
    _print_panel("print_human_prune_results (prune)", buf)

    console, buf = _capture_console()
    print_human_prune_results(
        prune_dry_run_results(), dry_run=True, console=console
    )
    _print_panel("print_human_prune_results (dry run)", buf)


def _show_troubleshoot() -> None:
    console, buf = _capture_console()
    config = troubleshoot_config()
    vol_statuses, sync_statuses = troubleshoot_data(config)
    print_human_troubleshoot(
        vol_statuses, sync_statuses, config, console=console
    )
    _print_panel("print_human_troubleshoot", buf)


def _show_config_errors() -> None:
    console, buf = _capture_console()
    print_config_error(
        ConfigError("Config file not found: /etc/nbkp/config.yaml"),
        console=console,
    )
    _print_panel("print_config_error (file not found)", buf)

    console, buf = _capture_console()
    try:
        yaml.safe_load("not_a_list:\n  - [invalid")
    except yaml.YAMLError as ye:
        err = ConfigError(f"Invalid YAML in /etc/nbkp/config.yaml: {ye}")
        err.__cause__ = ye
        print_config_error(err, console=console)
    _print_panel("print_config_error (invalid YAML)", buf)

    console, buf = _capture_console()
    try:
        ConfigModel.model_validate(
            {"volumes": {"v": {"type": "ftp", "path": "/x"}}}
        )
    except ValidationError as ve:
        err = ConfigError(str(ve))
        err.__cause__ = ve
        print_config_error(err, console=console)
    _print_panel("print_config_error (invalid volume type)", buf)

    console, buf = _capture_console()
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
        print_config_error(err, console=console)
    _print_panel("print_config_error (unknown server reference)", buf)

    console, buf = _capture_console()
    try:
        ConfigModel.model_validate(
            {"volumes": {"v": {"type": "local"}}, "syncs": {}}
        )
    except ValidationError as ve:
        err = ConfigError(str(ve))
        err.__cause__ = ve
        print_config_error(err, console=console)
    _print_panel("print_config_error (missing required field)", buf)


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
    rows: list[tuple[str, str]] = [
        ("Seed directory", str(tmp)),
        ("Config file", str(config_path)),
    ]
    if docker:
        assert docker_server is not None
        rows.append(
            (
                "Docker",
                f"{CONTAINER_NAME}" f" (port {docker_server.port})",
            )
        )
    label_w = max(len(r[0]) for r in rows)
    summary = Text()
    for i, (label, value) in enumerate(rows):
        if i > 0:
            summary.append("\n")
        summary.append(f"{label:<{label_w}}  ", style="bold")
        summary.append(value)
    _console.print(Panel(summary, border_style="blue", padding=(0, 1)))

    lines = [
        f'CFG="{config_path}"',
        f'SH="{backup_sh}"',
        "",
        "# Show parsed configuration",
        "poetry run nbkp config show --config $CFG",
        "",
        "# Show configuration as JSON",
        "poetry run nbkp config show --config $CFG --output json",
        "",
        "# Volume and sync health checks",
        "poetry run nbkp check --config $CFG",
        "",
        "# Preview what rsync would do without changes",
        "poetry run nbkp run --config $CFG --dry-run",
        "",
        "# Execute backup syncs",
        "poetry run nbkp run --config $CFG",
        "",
        "# Prune old btrfs snapshots",
        "poetry run nbkp prune --config $CFG",
        "",
        "# Generate standalone bash script to stdout",
        "poetry run nbkp sh --config $CFG",
        "",
        "# Write script to file, validate, and run",
        "poetry run nbkp sh --config $CFG -o $SH \\",
        "  && bash -n $SH \\",
        "  && $SH --dry-run \\",
        "  && $SH",
        "",
        "# With relative paths (src and dst)",
        "poetry run nbkp sh --config $CFG -o $SH"
        " --relative-src --relative-dst \\",
        "  && bash -n $SH \\",
        "  && $SH --dry-run \\",
        "  && $SH",
    ]
    if docker:
        lines += [
            "",
            "# Teardown Docker container",
            f"docker rm -f {CONTAINER_NAME}",
        ]
    commands = "\n".join(lines)
    _console.print(
        Panel(
            Syntax(
                commands,
                "bash",
                theme="monokai",
                background_color="default",
                word_wrap=True,
            ),
            title="[bold]Try[/bold]",
            border_style="green",
            padding=(0, 1),
        )
    )


def main() -> None:
    """Test CLI entry point."""
    app()


if __name__ == "__main__":
    main()
