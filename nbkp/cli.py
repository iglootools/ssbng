"""Typer CLI: run and status commands."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import Config, ConfigError, load_config
from .status import SyncReason, SyncStatus, VolumeStatus, check_all_syncs
from .sync.btrfs import list_snapshots, prune_snapshots
from .output import (
    OutputFormat,
    print_config_error,
    print_human_prune_results,
    print_human_results,
    print_human_status,
    print_human_troubleshoot,
)
from .scriptgen import ScriptOptions, generate_script
from .sync import PruneResult, SyncResult, run_all_syncs

_MARKER_ONLY_REASONS = {
    SyncReason.SOURCE_MARKER_NOT_FOUND,
    SyncReason.DESTINATION_MARKER_NOT_FOUND,
}

app = typer.Typer(
    name="nbkp",
    help="Nomad Backup",
    no_args_is_help=True,
)


@app.command()
def status(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    output: Annotated[
        OutputFormat,
        typer.Option("--output", "-o", help="Output format"),
    ] = OutputFormat.HUMAN,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict/--no-strict",
            help=(
                "Exit non-zero on any inactive sync,"
                " including missing markers"
            ),
        ),
    ] = False,
) -> None:
    """Show status of volumes and syncs."""
    cfg = _load_config_or_exit(config)
    output_format = output
    vol_statuses, sync_statuses, has_errors = _check_and_display_status(
        cfg, output_format, strict
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
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Perform a dry run"),
    ] = False,
    sync: Annotated[
        Optional[list[str]],
        typer.Option("--sync", "-s", help="Sync name(s) to run"),
    ] = None,
    output: Annotated[
        OutputFormat,
        typer.Option("--output", "-o", help="Output format"),
    ] = OutputFormat.HUMAN,
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose",
            "-v",
            count=True,
            help="Increase rsync verbosity (-v, -vv, -vvv)",
        ),
    ] = 0,
    prune: Annotated[
        bool,
        typer.Option(
            "--prune/--no-prune",
            help="Prune old snapshots after sync",
        ),
    ] = True,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict/--no-strict",
            help=(
                "Exit non-zero on any inactive sync,"
                " including missing markers"
            ),
        ),
    ] = False,
) -> None:
    """Run backup syncs."""
    cfg = _load_config_or_exit(config)
    output_format = output
    vol_statuses, sync_statuses, has_errors = _check_and_display_status(
        cfg, output_format, strict, only_syncs=sync
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

        use_spinner = output_format is OutputFormat.HUMAN and verbose == 0
        stream_output = (
            (lambda chunk: typer.echo(chunk, nl=False))
            if output_format is OutputFormat.HUMAN and not use_spinner
            else None
        )

        console = Console() if use_spinner else None
        status_display = None

        def on_sync_start(slug: str) -> None:
            nonlocal status_display
            if console is not None:
                status_display = console.status(f"Syncing {slug}...")
                status_display.start()

        def on_sync_end(slug: str, result: SyncResult) -> None:
            nonlocal status_display
            if status_display is not None:
                status_display.stop()
                status_display = None
            if console is not None:
                icon = (
                    "[green]✓[/green]" if result.success else ("[red]✗[/red]")
                )
                console.print(f"{icon} {slug}")

        results = run_all_syncs(
            cfg,
            sync_statuses,
            dry_run=dry_run,
            only_syncs=sync,
            verbose=verbose,
            prune=prune,
            on_rsync_output=stream_output,
            on_sync_start=on_sync_start if use_spinner else None,
            on_sync_end=on_sync_end if use_spinner else None,
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
                typer.echo("")
                print_human_results(results, dry_run)

        if any(not r.success for r in results):
            raise typer.Exit(1)


@app.command()
def sh(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    output_file: Annotated[
        Optional[str],
        typer.Option(
            "--output-file",
            "-o",
            help="Write script to file (made executable)",
        ),
    ] = None,
    relative_src: Annotated[
        bool,
        typer.Option(
            "--relative-src",
            help=(
                "Make source paths relative to script location"
                " (requires --output-file)"
            ),
        ),
    ] = False,
    relative_dst: Annotated[
        bool,
        typer.Option(
            "--relative-dst",
            help=(
                "Make destination paths relative to script location"
                " (requires --output-file)"
            ),
        ),
    ] = False,
) -> None:
    """Generate a standalone backup shell script.

    This is useful for deploying to systems without Python,
    or auditing what commands will run.
    """
    if (relative_src or relative_dst) and output_file is None:
        typer.echo(
            "Error: --relative-src/--relative-dst" " require --output-file",
            err=True,
        )
        raise typer.Exit(2)

    cfg = _load_config_or_exit(config)
    script = generate_script(
        cfg,
        ScriptOptions(
            config_path=config,
            output_file=(
                os.path.abspath(output_file) if output_file else None
            ),
            relative_src=relative_src,
            relative_dst=relative_dst,
        ),
    )
    if output_file is not None:
        path = Path(output_file)
        path.write_text(script, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        typer.echo(f"Written to {output_file}", err=True)
    else:
        typer.echo(script)


@app.command()
def troubleshoot(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
) -> None:
    """Diagnose issues and show how to fix them."""
    cfg = _load_config_or_exit(config)
    vol_statuses, sync_statuses = _check_all_with_progress(
        cfg, use_progress=True
    )
    print_human_troubleshoot(vol_statuses, sync_statuses, cfg)


@app.command()
def prune(
    config: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    sync: Annotated[
        Optional[list[str]],
        typer.Option("--sync", "-s", help="Sync name(s) to prune"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Perform a dry run"),
    ] = False,
    output: Annotated[
        OutputFormat,
        typer.Option("--output", "-o", help="Output format"),
    ] = OutputFormat.HUMAN,
) -> None:
    """Prune old snapshots beyond max-snapshots limit."""
    cfg = _load_config_or_exit(config)
    output_format = output
    _, sync_statuses = _check_all_with_progress(
        cfg, use_progress=output_format is OutputFormat.HUMAN
    )

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
        print_config_error(e)
        raise typer.Exit(2)


def _check_all_with_progress(
    cfg: Config,
    use_progress: bool,
    only_syncs: list[str] | None = None,
) -> tuple[dict[str, VolumeStatus], dict[str, SyncStatus]]:
    """Run check_all_syncs with an optional progress bar."""
    total = len(cfg.volumes) + len(cfg.syncs)
    if not use_progress or total == 0:
        return check_all_syncs(cfg, only_syncs=only_syncs)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("{task.completed}/{task.total}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Checking volumes and syncs...", total=total)

        def on_progress(_slug: str) -> None:
            progress.advance(task)

        return check_all_syncs(
            cfg,
            on_progress=on_progress,
            only_syncs=only_syncs,
        )


def _check_and_display_status(
    cfg: Config,
    output_format: OutputFormat,
    strict: bool,
    only_syncs: list[str] | None = None,
) -> tuple[
    dict[str, VolumeStatus],
    dict[str, SyncStatus],
    bool,
]:
    """Compute statuses, display human output, and check for errors.

    Returns volume statuses, sync statuses, and whether there are
    fatal errors.  When *only_syncs* is given, only those syncs
    (and the volumes they reference) are checked.
    """
    vol_statuses, sync_statuses = _check_all_with_progress(
        cfg,
        use_progress=output_format is OutputFormat.HUMAN,
        only_syncs=only_syncs,
    )

    if output_format is OutputFormat.HUMAN:
        print_human_status(vol_statuses, sync_statuses, cfg)

    if strict:
        has_errors = any(not s.active for s in sync_statuses.values())
    else:
        has_errors = any(
            set(s.reasons) - _MARKER_ONLY_REASONS
            for s in sync_statuses.values()
        )

    return vol_statuses, sync_statuses, has_errors


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
