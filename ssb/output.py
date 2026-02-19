"""CLI output formatting."""

from __future__ import annotations

import enum

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .config import Config, LocalVolume, RemoteVolume
from .runner import SyncResult
from .status import SyncReason, SyncStatus, VolumeReason, VolumeStatus


class OutputFormat(str, enum.Enum):
    """Output format for CLI commands."""

    HUMAN = "human"
    JSON = "json"


def _status_text(
    active: bool,
    reasons: list[VolumeReason] | list[SyncReason],
) -> Text:
    """Format status with optional reasons as styled text."""
    if active:
        return Text("active", style="green")
    reason_str = ", ".join(r.value for r in reasons)
    return Text(f"inactive ({reason_str})", style="red")


def format_volume_display(
    vol: LocalVolume | RemoteVolume, config: Config
) -> str:
    """Format a volume for human display."""
    match vol:
        case RemoteVolume():
            server = config.rsync_servers[vol.rsync_server]
            if server.user:
                host_part = f"{server.user}@{server.host}"
            else:
                host_part = server.host
            if server.port != 22:
                host_part += f":{server.port}"
            return f"{host_part}:{vol.path}"
        case LocalVolume():
            return vol.path


def print_human_status(
    vol_statuses: dict[str, VolumeStatus],
    sync_statuses: dict[str, SyncStatus],
    config: Config,
) -> None:
    """Print human-readable status output."""
    console = Console()

    vol_table = Table(
        title="Volumes:",
    )
    vol_table.add_column("Name", style="bold")
    vol_table.add_column("Type")
    vol_table.add_column("Location")
    vol_table.add_column("Status")

    for vs in vol_statuses.values():
        vol = vs.config
        match vol:
            case RemoteVolume():
                vol_type = "remote"
            case LocalVolume():
                vol_type = "local"
        vol_table.add_row(
            vs.name,
            vol_type,
            format_volume_display(vol, config),
            _status_text(vs.active, vs.reasons),
        )

    console.print(vol_table)
    console.print()

    sync_table = Table(
        title="Syncs:",
    )
    sync_table.add_column("Name", style="bold")
    sync_table.add_column("Source")
    sync_table.add_column("Destination")
    sync_table.add_column("Status")

    for ss in sync_statuses.values():
        sync_table.add_row(
            ss.name,
            ss.config.source.volume,
            ss.config.destination.volume,
            _status_text(ss.active, ss.reasons),
        )

    console.print(sync_table)


def print_human_results(results: list[SyncResult], dry_run: bool) -> None:
    """Print human-readable run results."""
    console = Console()
    mode = " (dry run)" if dry_run else ""

    table = Table(
        title=f"SSB run{mode}:",
    )
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    for r in results:
        if r.success:
            status = Text("OK", style="green")
        else:
            status = Text("FAILED", style="red")

        details_parts: list[str] = []
        if r.error:
            details_parts.append(f"Error: {r.error}")
        if r.snapshot_path:
            details_parts.append(f"Snapshot: {r.snapshot_path}")
        if r.output and not r.success:
            lines = r.output.strip().split("\n")[:5]
            details_parts.extend(lines)

        table.add_row(
            r.sync_name,
            status,
            "\n".join(details_parts),
        )

    console.print(table)
