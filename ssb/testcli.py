"""Developer test CLI: fake output rendering and seed data."""

from __future__ import annotations

import tempfile
from pathlib import Path

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

app = typer.Typer(
    name="ssb-testcli",
    help="SSB developer test CLI",
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


@app.command()
def seed() -> None:
    """Create a temp folder with config and test data."""
    tmp = Path(tempfile.mkdtemp(prefix="ssb-seed-"))

    # Source volume
    src = tmp / "src-data"
    src.mkdir()
    (src / ".ssb-vol").touch()
    (src / ".ssb-src").touch()

    photos = src / "photos"
    photos.mkdir()
    (photos / ".ssb-src").touch()
    (photos / "vacation.jpg").write_text("fake jpeg data - vacation photo")
    (photos / "family.png").write_text("fake png data - family photo")

    docs = src / "documents"
    docs.mkdir()
    (docs / "notes.txt").write_text(
        "Meeting notes from Monday\n"
        "- Review backup strategy\n"
        "- Test rsync filters\n"
    )
    (docs / "report.pdf").write_text("fake pdf data - quarterly report")

    # Destination volume
    dst = tmp / "dst-backup"
    dst.mkdir()
    (dst / ".ssb-vol").touch()
    (dst / ".ssb-dst").touch()
    (dst / "latest").mkdir()

    # Config file
    config = Config(
        volumes={
            "src-data": LocalVolume(
                slug="src-data", path=str(src)
            ),
            "dst-backup": LocalVolume(
                slug="dst-backup", path=str(dst)
            ),
        },
        syncs={
            "photos-backup": SyncConfig(
                slug="photos-backup",
                source=SyncEndpoint(
                    volume="src-data", subdir="photos"
                ),
                destination=DestinationSyncEndpoint(
                    volume="dst-backup"
                ),
            ),
            "full-backup": SyncConfig(
                slug="full-backup",
                source=SyncEndpoint(
                    volume="src-data"
                ),
                destination=DestinationSyncEndpoint(
                    volume="dst-backup"
                ),
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

    typer.echo(f"Seed directory: {tmp}")
    typer.echo(f"Config file:    {config_path}")
    typer.echo()
    typer.echo("Try:")
    typer.echo(f"  ssb status --config {config_path}")
    typer.echo(f"  ssb run --config {config_path} --dry-run")
    typer.echo(f"  ssb run --config {config_path}")


def main() -> None:
    """Test CLI entry point."""
    app()


if __name__ == "__main__":
    main()
