"""CLI output formatting."""

from __future__ import annotations

import enum

import typer

from .config import LocalVolume, RemoteVolume
from .status import SyncResult, SyncStatus, VolumeStatus


class OutputFormat(str, enum.Enum):
    """Output format for CLI commands."""

    HUMAN = "human"
    JSON = "json"


def format_volume_display(vol: LocalVolume | RemoteVolume) -> str:
    """Format a volume for human display."""
    match vol:
        case RemoteVolume():
            parts = []
            if vol.user:
                parts.append(f"{vol.user}@{vol.host}")
            else:
                parts.append(vol.host)
            if vol.port != 22:
                parts[-1] += f":{vol.port}"
            return " ".join(parts)
        case LocalVolume():
            return vol.path


def print_human_status(
    vol_statuses: dict[str, VolumeStatus],
    sync_statuses: dict[str, SyncStatus],
) -> None:
    """Print human-readable status output."""
    typer.echo("Volumes:")
    for vs in vol_statuses.values():
        vol = vs.config
        match vol:
            case RemoteVolume():
                vol_type = "remote"
            case LocalVolume():
                vol_type = "local"
        display = format_volume_display(vol)
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


def print_human_results(results: list[SyncResult], dry_run: bool) -> None:
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
