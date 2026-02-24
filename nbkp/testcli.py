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
    Config,
    ConfigError,
    DestinationSyncEndpoint,
    LocalVolume,
    SyncConfig,
    SyncEndpoint,
)
from .config.protocol import Config as ConfigModel
from .output import (
    print_config_error,
    print_human_prune_results,
    print_human_results,
    print_human_status,
    print_human_troubleshoot,
)
from .testdata import (
    dry_run_result,
    prune_dry_run_results,
    prune_results,
    run_results,
    status_config,
    status_data,
    troubleshoot_config,
    troubleshoot_data,
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
    _show_status()
    _show_results()
    _show_prune()
    _show_troubleshoot()
    _show_config_errors()


def _show_status() -> None:
    _console.rule("print_human_status")
    config = status_config()
    vol_statuses, sync_statuses = status_data(config)
    print_human_status(vol_statuses, sync_statuses, config)


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


_CHUNK_SIZE = 1024 * 1024  # 1 MB


def _write_zeroed_file(path: Path, size_bytes: int) -> None:
    """Write a zeroed file in chunks to avoid large allocations."""
    chunk = b"\x00" * min(_CHUNK_SIZE, size_bytes)
    with path.open("wb") as f:
        remaining = size_bytes
        while remaining > 0:
            f.write(chunk[:remaining])
            remaining -= len(chunk)


@app.command()
def seed(
    big_file_size: Annotated[
        int,
        typer.Option(
            "--big-file-size",
            help="Size in MB for large files (e.g. 100, 1024)."
            " When set, vacation.jpg and report.pdf"
            " are written at this size to slow down syncs."
            " Set to 0 to disable.",
        ),
    ] = 1024,
) -> None:
    """Create a temp folder with config and test data."""
    size_bytes = big_file_size * 1024 * 1024
    tmp = Path(tempfile.mkdtemp(prefix="nbkp-seed-"))

    # Source volume
    src = tmp / "src-data"
    src.mkdir()
    (src / ".nbkp-vol").touch()
    (src / ".nbkp-src").touch()

    photos = src / "photos"
    photos.mkdir()
    (photos / ".nbkp-src").touch()
    if big_file_size:
        _write_zeroed_file(photos / "vacation.jpg", size_bytes)
    else:
        (photos / "vacation.jpg").write_text("fake jpeg data - vacation photo")
    (photos / "family.png").write_text("fake png data - family photo")

    docs = src / "documents"
    docs.mkdir()
    (docs / "notes.txt").write_text(
        "Meeting notes from Monday\n"
        "- Review backup strategy\n"
        "- Test rsync filters\n"
    )
    if big_file_size:
        _write_zeroed_file(docs / "report.pdf", size_bytes)
    else:
        (docs / "report.pdf").write_text("fake pdf data - quarterly report")

    # Destination volume
    dst = tmp / "dst-backup"
    dst.mkdir()
    (dst / ".nbkp-vol").touch()
    (dst / ".nbkp-dst").touch()
    (dst / "latest").mkdir()

    # Config file
    config = Config(
        volumes={
            "src-data": LocalVolume(slug="src-data", path=str(src)),
            "dst-backup": LocalVolume(slug="dst-backup", path=str(dst)),
        },
        syncs={
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
        },
    )
    config_path = tmp / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            config.model_dump(by_alias=True),
            default_flow_style=False,
            sort_keys=False,
        )
    )

    backup_sh = tmp / "backup.sh"

    seed_label = "Seed directory:"
    cfg_label = "Config file:"
    w = max(len(seed_label), len(cfg_label))
    typer.echo(f"{seed_label:<{w}} {tmp}")
    typer.echo(f"{cfg_label:<{w}} {config_path}")
    typer.echo()
    typer.echo("Try:")
    typer.echo("poetry install, then run:")
    typer.echo()
    typer.echo(f"{_INDENT}# Volume and sync health checks")
    typer.echo(f"{_INDENT}nbkp status --config {config_path}")
    typer.echo()
    typer.echo(f"{_INDENT}# Preview what rsync would do without changes")
    typer.echo(f"{_INDENT}nbkp run --config {config_path} --dry-run")
    typer.echo()
    typer.echo(f"{_INDENT}# Execute backup syncs")
    typer.echo(f"{_INDENT}nbkp run --config {config_path}")
    typer.echo()
    typer.echo(f"{_INDENT}# Prune old btrfs snapshots")
    typer.echo(f"{_INDENT}nbkp prune --config {config_path}")
    typer.echo()
    typer.echo(f"{_INDENT}# Generate standalone bash script to stdout")
    typer.echo(f"{_INDENT}nbkp sh --config {config_path}")
    typer.echo()
    typer.echo(f"{_INDENT}# Write script to file, validate syntax, and run")
    typer.echo(
        f"{_INDENT}nbkp sh --config {config_path}  -o {backup_sh} \\\n"
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


def main() -> None:
    """Test CLI entry point."""
    app()


if __name__ == "__main__":
    main()
