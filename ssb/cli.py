"""Typer CLI: run and status commands."""

from __future__ import annotations

import dataclasses
import json
from typing import Annotated, Optional

import typer

from .checks import check_all_syncs
from .config import ConfigError, load_config
from .model import (
    LocalVolume,
    OutputFormat,
    RemoteVolume,
    SyncResult,
    SyncStatus,
    VolumeStatus,
)
from .runner import run_all_syncs

app = typer.Typer(
    name="ssb",
    help="Simple Safe Backup - An rsync-based backup tool",
    no_args_is_help=True,
)


def _load_or_exit(config_path: str | None) -> object:
    """Load config or exit with code 2 on error."""
    try:
        return load_config(config_path)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(2)


def _format_volume_display(vol: LocalVolume | RemoteVolume) -> str:
    """Format a volume for human display."""
    if isinstance(vol, RemoteVolume):
        parts = []
        if vol.user:
            parts.append(f"{vol.user}@{vol.host}")
        else:
            parts.append(vol.host)
        if vol.port != 22:
            parts[-1] += f":{vol.port}"
        return " ".join(parts)
    return vol.path


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
) -> None:
    """Show status of volumes and syncs."""
    cfg = _load_or_exit(config)
    from .model import Config

    assert isinstance(cfg, Config)
    vol_statuses, sync_statuses = check_all_syncs(cfg)

    fmt = OutputFormat(output)

    if fmt == OutputFormat.JSON:
        data = {
            "volumes": [v.model_dump() for v in vol_statuses.values()],
            "syncs": [s.model_dump() for s in sync_statuses.values()],
        }
        typer.echo(json.dumps(data, indent=2))
        return

    _print_human_status(vol_statuses, sync_statuses)


def _print_human_status(
    vol_statuses: dict[str, VolumeStatus],
    sync_statuses: dict[str, SyncStatus],
) -> None:
    """Print human-readable status output."""
    typer.echo("Volumes:")
    for vs in vol_statuses.values():
        vol = vs.config
        if isinstance(vol, RemoteVolume):
            vol_type = "remote"
        else:
            vol_type = "local"
        display = _format_volume_display(vol)
        status_str = "active" if vs.active else "inactive"
        reason = "" if vs.active else f" ({vs.reason})"
        typer.echo(
            f"  {vs.name:<18s}{vol_type:<10s}{display:<24s}"
            f"{status_str}{reason}"
        )

    typer.echo("")
    typer.echo("Syncs:")
    for ss in sync_statuses.values():
        src = ss.config.source.volume_name
        dst = ss.config.destination.volume_name
        arrow = f"{src} -> {dst}"
        status_str = "active" if ss.active else "inactive"
        reason = "" if ss.active else f" ({ss.reason})"
        typer.echo(f"  {ss.name:<18s}{arrow:<30s}{status_str}{reason}")


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
) -> None:
    """Run backup syncs."""
    cfg = _load_or_exit(config)
    from .model import Config

    assert isinstance(cfg, Config)

    sync_statuses, results = run_all_syncs(
        cfg, dry_run=dry_run, sync_names=sync
    )

    fmt = OutputFormat(output)

    if fmt == OutputFormat.JSON:
        data = [r.model_dump() for r in results]
        typer.echo(json.dumps(data, indent=2))
    else:
        _print_human_results(results, dry_run)

    if any(not r.success for r in results):
        raise typer.Exit(1)


def _print_human_results(results: list[SyncResult], dry_run: bool) -> None:
    """Print human-readable run results."""
    mode = " (dry run)" if dry_run else ""
    typer.echo(f"SSB run{mode}:")
    typer.echo("")

    for r in results:
        if r.success:
            status = "OK"
        else:
            status = "FAILED"

        typer.echo(f"  {r.sync_name}: {status}")
        if r.error:
            typer.echo(f"    Error: {r.error}")
        if r.snapshot_path:
            typer.echo(f"    Snapshot: {r.snapshot_path}")
        if r.output and not r.success:
            for line in r.output.strip().split("\n")[:5]:
                typer.echo(f"    {line}")


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
