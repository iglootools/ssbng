"""Typer CLI: run and status commands."""

from __future__ import annotations

import json
from typing import Annotated, Optional

import typer

from .config import Config
from .status import SyncReason, SyncStatus, VolumeStatus, check_all_syncs
from .configloader import ConfigError, load_config
from .btrfs import list_snapshots, prune_snapshots
from .output import (
    OutputFormat,
    print_human_prune_results,
    print_human_results,
    print_human_status,
    print_human_troubleshoot,
)
from .runner import PruneResult, run_all_syncs

_REMOVABLE_DEVICE_REASONS = {
    SyncReason.SOURCE_MARKER_NOT_FOUND,
    SyncReason.DESTINATION_MARKER_NOT_FOUND,
}

app = typer.Typer(
    name="ssb",
    help="Simple Safe Backup - An rsync-based backup tool",
    no_args_is_help=True,
)


@app.command()
def status(
    config: Annotated[
        Optional[str],
        typer.Option("--config", help="Path to config file"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: human or json"),
    ] = "human",
    allow_removable_devices: Annotated[
        bool,
        typer.Option(
            "--allow-removable-devices/--no-allow-removable-devices",
            help=(
                "Treat missing .ssb-src/.ssb-dst markers"
                " as non-fatal for exit code"
            ),
        ),
    ] = True,
) -> None:
    """Show status of volumes and syncs."""
    cfg = _load_config_or_exit(config)
    output_format = OutputFormat(output)
    vol_statuses, sync_statuses, has_errors = _check_and_display_status(
        cfg, output_format, allow_removable_devices
    )

    if output_format is OutputFormat.JSON:
        data = {
            "volumes": [v.model_dump() for v in vol_statuses.values()],
            "syncs": [s.model_dump() for s in sync_statuses.values()],
        }
        typer.echo(json.dumps(data, indent=2))

    if has_errors:
        raise typer.Exit(1)


@app.command()
def run(
    config: Annotated[
        Optional[str],
        typer.Option("--config", help="Path to config file"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Perform a dry run"),
    ] = False,
    sync: Annotated[
        Optional[list[str]],
        typer.Option("--sync", help="Sync name(s) to run"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: human or json"),
    ] = "human",
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose",
            "-v",
            count=True,
            help="Increase rsync verbosity (-v, -vv, -vvv)",
        ),
    ] = 0,
    allow_removable_devices: Annotated[
        bool,
        typer.Option(
            "--allow-removable-devices/--no-allow-removable-devices",
            help=(
                "Treat missing .ssb-src/.ssb-dst markers"
                " as non-fatal for exit code"
            ),
        ),
    ] = True,
) -> None:
    """Run backup syncs."""
    cfg = _load_config_or_exit(config)
    output_format = OutputFormat(output)
    vol_statuses, sync_statuses, has_errors = _check_and_display_status(
        cfg, output_format, allow_removable_devices
    )

    if has_errors:
        if output_format is OutputFormat.JSON:
            data = {
                "volumes": [v.model_dump() for v in vol_statuses.values()],
                "syncs": [s.model_dump() for s in sync_statuses.values()],
                "results": [],
            }
            typer.echo(json.dumps(data, indent=2))
        raise typer.Exit(1)
    else:
        if output_format is OutputFormat.HUMAN:
            typer.echo("")

        stream_output = (
            (lambda chunk: typer.echo(chunk, nl=False))
            if output_format is OutputFormat.HUMAN
            else None
        )
        results = run_all_syncs(
            cfg,
            sync_statuses,
            dry_run=dry_run,
            sync_slugs=sync,
            verbose=verbose,
            on_rsync_output=stream_output,
        )

        match output_format:
            case OutputFormat.JSON:
                data = {
                    "volumes": [v.model_dump() for v in vol_statuses.values()],
                    "syncs": [s.model_dump() for s in sync_statuses.values()],
                    "results": [r.model_dump() for r in results],
                }
                typer.echo(json.dumps(data, indent=2))
            case OutputFormat.HUMAN:
                print_human_results(results, dry_run)

        if any(not r.success for r in results):
            raise typer.Exit(1)


@app.command()
def troubleshoot(
    config: Annotated[
        Optional[str],
        typer.Option("--config", help="Path to config file"),
    ] = None,
) -> None:
    """Diagnose issues and show how to fix them."""
    cfg = _load_config_or_exit(config)
    vol_statuses, sync_statuses = check_all_syncs(cfg)
    print_human_troubleshoot(vol_statuses, sync_statuses, cfg)


@app.command()
def prune(
    config: Annotated[
        Optional[str],
        typer.Option("--config", help="Path to config file"),
    ] = None,
    sync: Annotated[
        Optional[list[str]],
        typer.Option("--sync", help="Sync name(s) to prune"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Perform a dry run"),
    ] = False,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: human or json"),
    ] = "human",
) -> None:
    """Prune old snapshots beyond max-snapshots limit."""
    cfg = _load_config_or_exit(config)
    output_format = OutputFormat(output)
    _, sync_statuses = check_all_syncs(cfg)

    prunable = [
        (slug, status)
        for slug, status in sync_statuses.items()
        if (not sync or slug in sync)
        and status.active
        and status.config.destination.btrfs_snapshots.enabled
        and status.config.destination.btrfs_snapshots.max_snapshots is not None
    ]

    results: list[PruneResult] = []
    for slug, status in prunable:
        btrfs_cfg = status.config.destination.btrfs_snapshots
        assert btrfs_cfg.max_snapshots is not None
        try:
            deleted = prune_snapshots(
                status.config,
                cfg,
                btrfs_cfg.max_snapshots,
                dry_run=dry_run,
            )
            remaining = list_snapshots(status.config, cfg)
            results.append(
                PruneResult(
                    sync_slug=slug,
                    deleted=deleted,
                    kept=len(remaining) + (len(deleted) if dry_run else 0),
                    dry_run=dry_run,
                )
            )
        except RuntimeError as e:
            results.append(
                PruneResult(
                    sync_slug=slug,
                    deleted=[],
                    kept=0,
                    dry_run=dry_run,
                    error=str(e),
                )
            )

    match output_format:
        case OutputFormat.JSON:
            typer.echo(json.dumps([r.model_dump() for r in results], indent=2))
        case OutputFormat.HUMAN:
            print_human_prune_results(results, dry_run)

    if any(r.error for r in results):
        raise typer.Exit(1)


def _load_config_or_exit(config_path: str | None) -> Config:
    """Load config or exit with code 2 on error."""
    try:
        return load_config(config_path)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(2)


def _check_and_display_status(
    cfg: Config,
    output_format: OutputFormat,
    allow_removable_devices: bool,
) -> tuple[
    dict[str, VolumeStatus],
    dict[str, SyncStatus],
    bool,
]:
    """Compute statuses, display human output, and check for errors.

    Returns volume statuses, sync statuses, and whether there are
    fatal errors.
    """
    vol_statuses, sync_statuses = check_all_syncs(cfg)

    if output_format is OutputFormat.HUMAN:
        print_human_status(vol_statuses, sync_statuses, cfg)

    if allow_removable_devices:
        has_errors = any(
            set(s.reasons) - _REMOVABLE_DEVICE_REASONS
            for s in sync_statuses.values()
        )
    else:
        has_errors = any(not s.active for s in sync_statuses.values())

    return vol_statuses, sync_statuses, has_errors


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
