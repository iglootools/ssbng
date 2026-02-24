"""Hard-link snapshot creation, lookup, symlink management, and pruning."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..config import (
    Config,
    LocalVolume,
    RemoteVolume,
    ResolvedEndpoints,
    SyncConfig,
    Volume,
)
from ..remote import run_remote_command
from .btrfs import list_snapshots, resolve_dest_path


def create_snapshot_dir(
    sync: SyncConfig,
    config: Config,
    *,
    now: datetime | None = None,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> str:
    """Create a snapshot directory for the current sync.

    Returns the full snapshot path.
    """
    re = resolved_endpoints or {}
    if now is None:
        now = datetime.now(timezone.utc)
    dest_path = resolve_dest_path(sync, config)
    timestamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    snapshot_path = f"{dest_path}/snapshots/{timestamp}"

    dst_vol = config.volumes[sync.destination.volume]
    match dst_vol:
        case RemoteVolume():
            ep = re[dst_vol.slug]
            result = run_remote_command(
                ep.server, ["mkdir", "-p", snapshot_path], ep.proxy
            )
        case LocalVolume():
            result = subprocess.run(
                ["mkdir", "-p", snapshot_path],
                capture_output=True,
                text=True,
            )

    if result.returncode != 0:
        raise RuntimeError(f"mkdir snapshot dir failed: {result.stderr}")
    return snapshot_path


def read_latest_symlink(
    sync: SyncConfig,
    config: Config,
    *,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> str | None:
    """Read the latest symlink target, returning the snapshot name.

    Returns None if the symlink does not exist.
    """
    re = resolved_endpoints or {}
    dest_path = resolve_dest_path(sync, config)
    latest_path = f"{dest_path}/latest"

    dst_vol = config.volumes[sync.destination.volume]
    match dst_vol:
        case LocalVolume():
            p = Path(latest_path)
            if not p.is_symlink():
                return None
            target = str(p.readlink())
        case RemoteVolume():
            ep = re[dst_vol.slug]
            result = run_remote_command(
                ep.server,
                ["readlink", latest_path],
                ep.proxy,
            )
            if result.returncode != 0:
                return None
            target = result.stdout.strip()

    # Target is like "snapshots/{name}" — extract the name
    if "/" in target:
        return target.rsplit("/", 1)[-1]
    else:
        return target


def update_latest_symlink(
    sync: SyncConfig,
    config: Config,
    snapshot_name: str,
    *,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> None:
    """Create or update the latest symlink to point to a snapshot."""
    re = resolved_endpoints or {}
    dest_path = resolve_dest_path(sync, config)
    latest_path = f"{dest_path}/latest"
    target = f"snapshots/{snapshot_name}"

    dst_vol = config.volumes[sync.destination.volume]
    match dst_vol:
        case LocalVolume():
            p = Path(latest_path)
            p.unlink(missing_ok=True)
            p.symlink_to(target)
        case RemoteVolume():
            ep = re[dst_vol.slug]
            result = run_remote_command(
                ep.server,
                ["ln", "-sfn", target, latest_path],
                ep.proxy,
            )
            if result.returncode != 0:
                raise RuntimeError(f"symlink update failed: {result.stderr}")


def cleanup_orphaned_snapshots(
    sync: SyncConfig,
    config: Config,
    *,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> list[str]:
    """Remove snapshots newer than the latest symlink target.

    These are leftover directories from failed syncs.
    Returns list of deleted paths.
    """
    re = resolved_endpoints or {}
    latest_name = read_latest_symlink(sync, config, resolved_endpoints=re)
    if latest_name is None:
        return []

    all_snapshots = list_snapshots(sync, config, re)
    dst_vol = config.volumes[sync.destination.volume]
    deleted: list[str] = []

    for snap_path in all_snapshots:
        snap_name = snap_path.rsplit("/", 1)[-1]
        if snap_name > latest_name:
            delete_snapshot(snap_path, dst_vol, re)
            deleted.append(snap_path)

    return deleted


def delete_snapshot(
    path: str,
    volume: Volume,
    resolved_endpoints: ResolvedEndpoints,
) -> None:
    """Delete a hard-link snapshot directory."""
    match volume:
        case RemoteVolume():
            ep = resolved_endpoints[volume.slug]
            result = run_remote_command(
                ep.server, ["rm", "-rf", path], ep.proxy
            )
            if result.returncode != 0:
                raise RuntimeError(f"rm -rf snapshot failed: {result.stderr}")
        case LocalVolume():
            shutil.rmtree(path)


def prune_snapshots(
    sync: SyncConfig,
    config: Config,
    max_snapshots: int,
    *,
    dry_run: bool = False,
    resolved_endpoints: ResolvedEndpoints | None = None,
) -> list[str]:
    """Delete oldest snapshots exceeding max_snapshots.

    Never prunes the snapshot that the latest symlink points to.
    Returns list of deleted (or would-be-deleted) paths.
    """
    re = resolved_endpoints or {}
    snapshots = list_snapshots(sync, config, re)
    excess = len(snapshots) - max_snapshots
    if excess <= 0:
        return []

    latest_name = read_latest_symlink(sync, config, resolved_endpoints=re)

    # Candidates are oldest first, but skip the latest target
    to_delete: list[str] = []
    for snap_path in snapshots:
        if len(to_delete) >= excess:
            break
        snap_name = snap_path.rsplit("/", 1)[-1]
        if snap_name == latest_name:
            continue
        to_delete.append(snap_path)

    if not dry_run:
        dst_vol = config.volumes[sync.destination.volume]
        for path in to_delete:
            delete_snapshot(path, dst_vol, re)

    return to_delete
