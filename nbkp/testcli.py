"""Developer test CLI: fake output rendering and seed data."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

import typer
import yaml

from .config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    SyncConfig,
    SyncEndpoint,
)
from .output import (
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


def _show_status() -> None:
    typer.echo("\n=== print_human_status ===\n")
    config = status_config()
    vol_statuses, sync_statuses = status_data(config)
    print_human_status(vol_statuses, sync_statuses, config)


def _show_results() -> None:
    typer.echo("\n=== print_human_results (run) ===\n")
    print_human_results(run_results(), dry_run=False)

    typer.echo("\n=== print_human_results (dry run) ===\n")
    print_human_results([dry_run_result()], dry_run=True)


def _show_prune() -> None:
    typer.echo("\n=== print_human_prune_results (prune) ===\n")
    print_human_prune_results(prune_results(), dry_run=False)

    typer.echo("\n=== print_human_prune_results (dry run) ===\n")
    print_human_prune_results(prune_dry_run_results(), dry_run=True)


def _show_troubleshoot() -> None:
    typer.echo("\n=== print_human_troubleshoot ===\n")
    config = troubleshoot_config()
    vol_statuses, sync_statuses = troubleshoot_data(config)
    print_human_troubleshoot(vol_statuses, sync_statuses, config)


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

    seed_label = "Seed directory:"
    cfg_label = "Config file:"
    w = max(len(seed_label), len(cfg_label))
    typer.echo(f"{seed_label:<{w}} {tmp}")
    typer.echo(f"{cfg_label:<{w}} {config_path}")
    typer.echo()
    typer.echo("Try:")
    typer.echo(f"{_INDENT}poetry run nbkp status --config {config_path}")
    typer.echo(
        f"{_INDENT}poetry run nbkp run --config {config_path} --dry-run"
    )
    typer.echo(f"{_INDENT}poetry run nbkp run --config {config_path}")
    typer.echo(f"{_INDENT}poetry run nbkp prune --config {config_path}")
    typer.echo(f"{_INDENT}poetry run nbkp sh --config {config_path}")
    typer.echo(
        f"{_INDENT}poetry run nbkp sh --config {config_path}"
        f" -o /tmp/backup.sh && bash -n /tmp/backup.sh && /tmp/backup.sh"
    )


def main() -> None:
    """Test CLI entry point."""
    app()


if __name__ == "__main__":
    main()
