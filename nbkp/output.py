"""CLI output formatting."""

from __future__ import annotations

import enum
import textwrap

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import (
    Config,
    ConfigError,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
)
from .sync import PruneResult, SyncResult
from .check import SyncReason, SyncStatus, VolumeReason, VolumeStatus


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
    else:
        reason_str = ", ".join(r.value for r in reasons)
        return Text(f"inactive ({reason_str})", style="red")


def _sync_options(sync: SyncConfig) -> str:
    """Build a comma-separated string of enabled sync options."""
    opts: list[str] = []
    if sync.filters or sync.filter_file:
        opts.append("rsync-filter")
    if sync.destination.btrfs_snapshots.enabled:
        btrfs_label = "btrfs-snapshots"
        max_snap = sync.destination.btrfs_snapshots.max_snapshots
        if max_snap is not None:
            btrfs_label += f"(max:{max_snap})"
        opts.append(btrfs_label)
    return ", ".join(opts)


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


def print_human_check(
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
            vs.slug,
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
    sync_table.add_column("Options")
    sync_table.add_column("Status")

    for ss in sync_statuses.values():
        sync_table.add_row(
            ss.slug,
            ss.config.source.volume,
            ss.config.destination.volume,
            _sync_options(ss.config),
            _status_text(ss.active, ss.reasons),
        )

    console.print(sync_table)


def print_human_results(results: list[SyncResult], dry_run: bool) -> None:
    """Print human-readable run results."""
    console = Console()
    mode = " (dry run)" if dry_run else ""

    table = Table(
        title=f"NBKP run{mode}:",
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
        if r.pruned_paths:
            details_parts.append(f"Pruned: {len(r.pruned_paths)} snapshot(s)")
        if r.output and not r.success:
            lines = r.output.strip().split("\n")[:5]
            details_parts.extend(lines)

        table.add_row(
            r.sync_slug,
            status,
            "\n".join(details_parts),
        )

    console.print(table)


def print_human_prune_results(
    results: list[PruneResult], dry_run: bool
) -> None:
    """Print human-readable prune results."""
    console = Console()
    mode = " (dry run)" if dry_run else ""

    table = Table(
        title=f"NBKP prune{mode}:",
    )
    table.add_column("Name", style="bold")
    table.add_column("Deleted")
    table.add_column("Kept")
    table.add_column("Status")

    for r in results:
        if r.error:
            status = Text("FAILED", style="red")
        else:
            status = Text("OK", style="green")

        table.add_row(
            r.sync_slug,
            str(len(r.deleted)),
            str(r.kept),
            status,
        )

    console.print(table)


def _ssh_prefix(server: RsyncServer) -> str:
    """Build human-friendly SSH command prefix."""
    parts = ["ssh"]
    if server.port != 22:
        parts.extend(["-p", str(server.port)])
    if server.ssh_key:
        parts.extend(["-i", server.ssh_key])
    host = f"{server.user}@{server.host}" if server.user else server.host
    parts.append(host)
    return " ".join(parts)


def _wrap_cmd(
    cmd: str,
    vol: LocalVolume | RemoteVolume,
    config: Config,
) -> str:
    """Wrap a shell command for remote execution."""
    match vol:
        case LocalVolume():
            return cmd
        case RemoteVolume():
            server = config.rsync_servers[vol.rsync_server]
            return f"{_ssh_prefix(server)} '{cmd}'"


def _endpoint_path(
    vol: LocalVolume | RemoteVolume,
    subdir: str | None,
) -> str:
    """Resolve the full endpoint path."""
    if subdir:
        return f"{vol.path}/{subdir}"
    else:
        return vol.path


def _host_label(
    vol: LocalVolume | RemoteVolume,
    config: Config,
) -> str:
    """Human-readable host label for a volume."""
    match vol:
        case LocalVolume():
            return "this machine"
        case RemoteVolume():
            server = config.rsync_servers[vol.rsync_server]
            return server.host


_INDENT = "  "

_RSYNC_INSTALL = (
    "Ubuntu/Debian: sudo apt install rsync\n"
    "Fedora/RHEL:   sudo dnf install rsync\n"
    "macOS:         brew install rsync"
)

_BTRFS_INSTALL = (
    "Ubuntu/Debian: sudo apt install btrfs-progs\n"
    "Fedora/RHEL:   sudo dnf install btrfs-progs"
)

_COREUTILS_INSTALL = (
    "Ubuntu/Debian: sudo apt install coreutils\n"
    "Fedora/RHEL:   sudo dnf install coreutils"
)

_UTIL_LINUX_INSTALL = (
    "Ubuntu/Debian: sudo apt install util-linux\n"
    "Fedora/RHEL:   sudo dnf install util-linux"
)


def _print_marker_fix(
    console: Console,
    vol: LocalVolume | RemoteVolume,
    path: str,
    marker: str,
    config: Config,
) -> None:
    """Print marker creation fix with mount reminder."""
    p2 = _INDENT * 2
    console.print(f"{p2}Ensure the volume is mounted, then:")
    mkdir_cmd = f"mkdir -p {path}"
    touch_cmd = f"touch {path}/{marker}"
    console.print(f"{p2}{_wrap_cmd(mkdir_cmd, vol, config)}")
    console.print(f"{p2}{_wrap_cmd(touch_cmd, vol, config)}")


def _print_ssh_troubleshoot(
    console: Console,
    server: RsyncServer,
) -> None:
    """Print SSH connectivity troubleshooting instructions."""
    p2 = _INDENT * 2
    p3 = _INDENT * 3
    ssh_cmd = _ssh_prefix(server)
    console.print(f"{p2}Server {server.host} is unreachable.")
    console.print(f"{p2}Verify connectivity:")
    console.print(f"{p3}{ssh_cmd} echo ok")
    console.print(f"{p2}If authentication fails:")
    if server.ssh_key:
        console.print(
            f"{p3}1. Ensure the key exists:" f" ls -l {server.ssh_key}"
        )
        console.print(
            f"{p3}2. Copy it to the server:"
            f" ssh-copy-id"
            f" {'-p ' + str(server.port) + ' ' if server.port != 22 else ''}"
            f"-i {server.ssh_key}"
            f" {server.user + '@' if server.user else ''}"
            f"{server.host}"
        )
    else:
        console.print(f"{p3}1. Generate a key:" " ssh-keygen -t ed25519")
        console.print(
            f"{p3}2. Copy it to the server:"
            f" ssh-copy-id"
            f" {'-p ' + str(server.port) + ' ' if server.port != 22 else ''}"
            f"{server.user + '@' if server.user else ''}"
            f"{server.host}"
        )
    console.print(f"{p3}3. Verify passwordless login:" f" {ssh_cmd} echo ok")


def _print_sync_reason_fix(
    console: Console,
    sync: SyncConfig,
    reason: SyncReason,
    config: Config,
) -> None:
    """Print fix instructions for a sync reason."""
    p2 = _INDENT * 2
    p3 = _INDENT * 3
    match reason:
        case SyncReason.DISABLED:
            console.print(f"{p2}Enable the sync in the" " configuration file.")
        case SyncReason.SOURCE_UNAVAILABLE:
            src = config.volumes[sync.source.volume]
            match src:
                case RemoteVolume():
                    server = config.rsync_servers[src.rsync_server]
                    _print_ssh_troubleshoot(console, server)
                case LocalVolume():
                    console.print(
                        f"{p2}Source volume"
                        f" '{sync.source.volume}'"
                        " is not available."
                    )
        case SyncReason.DESTINATION_UNAVAILABLE:
            dst = config.volumes[sync.destination.volume]
            match dst:
                case RemoteVolume():
                    server = config.rsync_servers[dst.rsync_server]
                    _print_ssh_troubleshoot(console, server)
                case LocalVolume():
                    console.print(
                        f"{p2}Destination volume"
                        f" '{sync.destination.volume}'"
                        " is not available."
                    )
        case SyncReason.SOURCE_MARKER_NOT_FOUND:
            src = config.volumes[sync.source.volume]
            path = _endpoint_path(src, sync.source.subdir)
            _print_marker_fix(console, src, path, ".nbkp-src", config)
        case SyncReason.DESTINATION_MARKER_NOT_FOUND:
            dst = config.volumes[sync.destination.volume]
            path = _endpoint_path(dst, sync.destination.subdir)
            _print_marker_fix(console, dst, path, ".nbkp-dst", config)
        case SyncReason.RSYNC_NOT_FOUND_ON_SOURCE:
            src = config.volumes[sync.source.volume]
            host = _host_label(src, config)
            console.print(f"{p2}Install rsync on {host}:")
            console.print(textwrap.indent(_RSYNC_INSTALL, p3))
        case SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION:
            dst = config.volumes[sync.destination.volume]
            host = _host_label(dst, config)
            console.print(f"{p2}Install rsync on {host}:")
            console.print(textwrap.indent(_RSYNC_INSTALL, p3))
        case SyncReason.BTRFS_NOT_FOUND_ON_DESTINATION:
            dst = config.volumes[sync.destination.volume]
            host = _host_label(dst, config)
            console.print(f"{p2}Install btrfs-progs on {host}:")
            console.print(textwrap.indent(_BTRFS_INSTALL, p3))
        case SyncReason.STAT_NOT_FOUND_ON_DESTINATION:
            dst = config.volumes[sync.destination.volume]
            host = _host_label(dst, config)
            console.print(f"{p2}Install coreutils (stat)" f" on {host}:")
            console.print(textwrap.indent(_COREUTILS_INSTALL, p3))
        case SyncReason.FINDMNT_NOT_FOUND_ON_DESTINATION:
            dst = config.volumes[sync.destination.volume]
            host = _host_label(dst, config)
            console.print(f"{p2}Install util-linux (findmnt)" f" on {host}:")
            console.print(textwrap.indent(_UTIL_LINUX_INSTALL, p3))
        case SyncReason.DESTINATION_NOT_BTRFS:
            console.print(
                f"{p2}The destination is not on" " a btrfs filesystem."
            )
        case SyncReason.DESTINATION_NOT_BTRFS_SUBVOLUME:
            dst = config.volumes[sync.destination.volume]
            ep = _endpoint_path(dst, sync.destination.subdir)
            cmds = [
                f"sudo btrfs subvolume create {ep}/latest",
                f"sudo mkdir {ep}/snapshots",
                ("sudo chown <user>:<group>" f" {ep}/latest {ep}/snapshots"),
            ]
            for cmd in cmds:
                console.print(f"{p2}{_wrap_cmd(cmd, dst, config)}")
        case SyncReason.DESTINATION_NOT_MOUNTED_USER_SUBVOL_RM:
            dst = config.volumes[sync.destination.volume]
            console.print(
                f"{p2}Remount the btrfs volume" " with user_subvol_rm_allowed:"
            )
            cmd = (
                "sudo mount -o"
                " remount,user_subvol_rm_allowed"
                f" {dst.path}"
            )
            console.print(f"{p2}{_wrap_cmd(cmd, dst, config)}")
            console.print(
                f"{p2}To persist, add"
                " user_subvol_rm_allowed to"
                " the mount options in /etc/fstab"
                f" for {dst.path}."
            )
        case SyncReason.DESTINATION_LATEST_NOT_FOUND:
            dst = config.volumes[sync.destination.volume]
            ep = _endpoint_path(dst, sync.destination.subdir)
            cmds = [
                f"sudo btrfs subvolume create {ep}/latest",
                ("sudo chown <user>:<group>" f" {ep}/latest"),
            ]
            for cmd in cmds:
                console.print(f"{p2}{_wrap_cmd(cmd, dst, config)}")
        case SyncReason.DESTINATION_SNAPSHOTS_DIR_NOT_FOUND:
            dst = config.volumes[sync.destination.volume]
            ep = _endpoint_path(dst, sync.destination.subdir)
            cmds = [
                f"sudo mkdir {ep}/snapshots",
                ("sudo chown <user>:<group>" f" {ep}/snapshots"),
            ]
            for cmd in cmds:
                console.print(f"{p2}{_wrap_cmd(cmd, dst, config)}")


def print_human_troubleshoot(
    vol_statuses: dict[str, VolumeStatus],
    sync_statuses: dict[str, SyncStatus],
    config: Config,
) -> None:
    """Print troubleshooting instructions."""
    console = Console()
    has_issues = False

    failed_vols = [vs for vs in vol_statuses.values() if vs.reasons]
    failed_syncs = [ss for ss in sync_statuses.values() if ss.reasons]
    has_issues = bool(failed_vols or failed_syncs)

    for vs in failed_vols:
        console.print(f"\n[bold]Volume {vs.slug!r}:[/bold]")
        vol = vs.config
        for reason in vs.reasons:
            console.print(f"{_INDENT}{reason.value}")
            match reason:
                case VolumeReason.MARKER_NOT_FOUND:
                    _print_marker_fix(
                        console,
                        vol,
                        vol.path,
                        ".nbkp-vol",
                        config,
                    )
                case VolumeReason.UNREACHABLE:
                    match vol:
                        case RemoteVolume():
                            server = config.rsync_servers[vol.rsync_server]
                            _print_ssh_troubleshoot(console, server)

    for ss in failed_syncs:
        console.print(f"\n[bold]Sync {ss.slug!r}:[/bold]")
        for sync_reason in ss.reasons:
            console.print(f"{_INDENT}{sync_reason.value}")
            _print_sync_reason_fix(console, ss.config, sync_reason, config)

    if not has_issues:
        console.print("No issues found." " All volumes and syncs are active.")


def print_config_error(e: ConfigError) -> None:
    """Print a ConfigError as a Rich panel to stderr."""
    console = Console(stderr=True)
    cause = e.__cause__
    match cause:
        case ValidationError():
            lines: list[str] = []
            for err in cause.errors():
                loc = " → ".join(str(p) for p in err["loc"])
                msg = err["msg"]
                if msg.startswith("Value error, "):
                    msg = msg[len("Value error, "):]
                if loc:
                    lines.append(f"{loc}: {msg}")
                else:
                    lines.append(msg)
            body = "\n".join(lines)
        case _:
            body = str(e)
    console.print(Panel(body, title="Config error", style="red"))
