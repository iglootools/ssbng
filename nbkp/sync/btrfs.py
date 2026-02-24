"""Btrfs snapshot creation, lookup, and pruning."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from ..config import (
    Config,
    LocalVolume,
    RemoteVolume,
    ResolvedEndpoints,
    SyncConfig,
    Volume,
)
from ..remote import run_remote_command


def resolve_dest_path(sync: SyncConfig, config: Config) -> str:
    """Resolve the destination path for a sync."""
    vol = config.volumes[sync.destination.volume]
    if sync.destination.subdir:
        return f"{vol.path}/{sync.destination.subdir}"
    else:
        return vol.path


def create_snapshot(
    sync: SyncConfig,
    config: Config,
    *,
    now: datetime | None = None,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> str:
    """Create a read-only btrfs snapshot of latest/ into snapshots/.

    Returns the snapshot path.
    """
    re = resolved_endpoints or {}
    if now is None:
        now = datetime.now(timezone.utc)
    dest_path = resolve_dest_path(sync, config)
    # isoformat uses +00:00, but Z is more conventional for UTC.
    timestamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    snapshot_path = f"{dest_path}/snapshots/{timestamp}"
    latest_path = f"{dest_path}/latest"

    cmd = [
        "btrfs",
        "subvolume",
        "snapshot",
        "-r",
        latest_path,
        snapshot_path,
    ]

    dst_vol = config.volumes[sync.destination.volume]
    match dst_vol:
        case RemoteVolume():
            ep = re[dst_vol.slug]
            result = run_remote_command(ep.server, cmd, ep.proxy)
        case LocalVolume():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )

    if result.returncode != 0:
        raise RuntimeError(f"btrfs snapshot failed: {result.stderr}")
    else:
        return snapshot_path


def list_snapshots(
    sync: SyncConfig,
    config: Config,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> list[str]:
    """List all snapshot paths sorted oldest-first."""
    re = resolved_endpoints or {}
    dest_path = resolve_dest_path(sync, config)
    snapshots_dir = f"{dest_path}/snapshots"

    dst_vol = config.volumes[sync.destination.volume]
    match dst_vol:
        case RemoteVolume():
            ep = re[dst_vol.slug]
            result = run_remote_command(
                ep.server, ["ls", snapshots_dir], ep.proxy
            )
        case LocalVolume():
            result = subprocess.run(
                ["ls", snapshots_dir],
                capture_output=True,
                text=True,
            )

    if result.returncode != 0 or not result.stdout.strip():
        return []
    else:
        entries = sorted(result.stdout.strip().split("\n"))
        return [f"{snapshots_dir}/{e}" for e in entries]


def get_latest_snapshot(
    sync: SyncConfig,
    config: Config,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> str | None:
    """Get the path to the most recent snapshot, or None."""
    snapshots = list_snapshots(sync, config, resolved_endpoints)
    if snapshots:
        return snapshots[-1]
    else:
        return None


def _make_snapshot_writable(
    path: str,
    volume: Volume,
    resolved_endpoints: ResolvedEndpoints,
) -> None:
    """Unset the readonly property so the snapshot can be deleted."""
    cmd = ["btrfs", "property", "set", path, "ro", "false"]
    match volume:
        case RemoteVolume():
            ep = resolved_endpoints[volume.slug]
            result = run_remote_command(ep.server, cmd, ep.proxy)
        case LocalVolume():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )

    if result.returncode != 0:
        raise RuntimeError(
            f"btrfs property set ro=false failed: {result.stderr}"
        )


def delete_snapshot(
    path: str,
    volume: Volume,
    resolved_endpoints: ResolvedEndpoints,
) -> None:
    """Delete a single btrfs snapshot subvolume.

    First unsets the readonly property (needed when the filesystem
    is mounted with user_subvol_rm_allowed instead of granting
    CAP_SYS_ADMIN), then deletes the subvolume.
    """
    _make_snapshot_writable(path, volume, resolved_endpoints)

    cmd = ["btrfs", "subvolume", "delete", path]
    match volume:
        case RemoteVolume():
            ep = resolved_endpoints[volume.slug]
            result = run_remote_command(ep.server, cmd, ep.proxy)
        case LocalVolume():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )

    if result.returncode != 0:
        raise RuntimeError(f"btrfs delete failed: {result.stderr}")


def prune_snapshots(
    sync: SyncConfig,
    config: Config,
    max_snapshots: int,
    *,
    dry_run: bool = False,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> list[str]:
    """Delete oldest snapshots exceeding max_snapshots.

    Returns list of deleted (or would-be-deleted) paths.
    """
    re = resolved_endpoints or {}
    snapshots = list_snapshots(sync, config, re)
    excess = len(snapshots) - max_snapshots
    if excess <= 0:
        return []

    to_delete = snapshots[:excess]
    if not dry_run:
        dst_vol = config.volumes[sync.destination.volume]
        for path in to_delete:
            delete_snapshot(path, dst_vol, re)

    return to_delete
