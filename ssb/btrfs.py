"""Btrfs snapshot creation and lookup."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from .config import Config, LocalVolume, RemoteVolume, SyncConfig
from .ssh import run_remote_command


def _resolve_dest_path(sync: SyncConfig, config: Config) -> str:
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
) -> str:
    """Create a read-only btrfs snapshot of latest/ into snapshots/.

    Returns the snapshot path.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    dest_path = _resolve_dest_path(sync, config)
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
            server = config.rsync_servers[dst_vol.rsync_server]
            result = run_remote_command(server, cmd)
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


def get_latest_snapshot(sync: SyncConfig, config: Config) -> str | None:
    """Get the path to the most recent snapshot, or None."""
    dest_path = _resolve_dest_path(sync, config)
    snapshots_dir = f"{dest_path}/snapshots"

    dst_vol = config.volumes[sync.destination.volume]
    match dst_vol:
        case RemoteVolume():
            server = config.rsync_servers[dst_vol.rsync_server]
            result = run_remote_command(server, ["ls", snapshots_dir])
        case LocalVolume():
            result = subprocess.run(
                ["ls", snapshots_dir],
                capture_output=True,
                text=True,
            )

    if result.returncode != 0 or not result.stdout.strip():
        return None
    else:
        entries = sorted(result.stdout.strip().split("\n"))
        latest = entries[-1]
        return f"{snapshots_dir}/{latest}"
