"""Volume and sync activity checks."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import (
    Config,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    Volume,
)
from .status import (
    SyncReason,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
)
from .ssh import run_remote_command


def check_volume(volume: Volume) -> VolumeStatus:
    """Check if a volume is active."""
    match volume:
        case LocalVolume():
            return _check_local_volume(volume)
        case RemoteVolume():
            return _check_remote_volume(volume)


def _check_local_volume(volume: LocalVolume) -> VolumeStatus:
    """Check if a local volume is active (.ssb-vol marker exists)."""
    marker = Path(volume.path) / ".ssb-vol"
    if marker.exists():
        return VolumeStatus(
            name=volume.name,
            config=volume,
            active=True,
            reason=VolumeReason.OK,
        )
    return VolumeStatus(
        name=volume.name,
        config=volume,
        active=False,
        reason=VolumeReason.MARKER_NOT_FOUND,
    )


def _check_remote_volume(volume: RemoteVolume) -> VolumeStatus:
    """Check if a remote volume is active (SSH + .ssb-vol marker)."""
    marker_path = f"{volume.path}/.ssb-vol"
    result = run_remote_command(volume, f"test -f {marker_path}")
    match result.returncode:
        case 0:
            return VolumeStatus(
                name=volume.name,
                config=volume,
                active=True,
                reason=VolumeReason.OK,
            )
        case _:
            return VolumeStatus(
                name=volume.name,
                config=volume,
                active=False,
                reason=VolumeReason.UNREACHABLE,
            )


def _check_endpoint_marker(
    volume: Volume, subdir: str | None, marker_name: str
) -> bool:
    """Check if an endpoint marker file exists."""
    if subdir:
        rel_path = f"{volume.path}/{subdir}/{marker_name}"
    else:
        rel_path = f"{volume.path}/{marker_name}"

    match volume:
        case LocalVolume():
            return Path(rel_path).exists()
        case RemoteVolume():
            result = run_remote_command(volume, f"test -f {rel_path}")
            return result.returncode == 0


def _check_command_available(volume: Volume, command: str) -> bool:
    """Check if a command is available on the volume's host."""
    match volume:
        case LocalVolume():
            return shutil.which(command) is not None
        case RemoteVolume():
            result = run_remote_command(volume, f"which {command}")
            return result.returncode == 0


def check_sync(
    sync: SyncConfig,
    config: Config,
    volume_statuses: dict[str, VolumeStatus],
) -> SyncStatus:
    """Check if a sync is active."""
    src_vol_name = sync.source.volume_name
    dst_vol_name = sync.destination.volume_name

    src_status = volume_statuses[src_vol_name]
    dst_status = volume_statuses[dst_vol_name]

    if not sync.enabled:
        return SyncStatus(
            name=sync.name,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            active=False,
            reason=SyncReason.DISABLED,
        )

    if not src_status.active:
        return SyncStatus(
            name=sync.name,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            active=False,
            reason=SyncReason.SOURCE_UNAVAILABLE,
        )

    if not dst_status.active:
        return SyncStatus(
            name=sync.name,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            active=False,
            reason=SyncReason.DESTINATION_UNAVAILABLE,
        )

    src_vol = config.volumes[src_vol_name]
    dst_vol = config.volumes[dst_vol_name]

    if not _check_endpoint_marker(src_vol, sync.source.subdir, ".ssb-src"):
        return SyncStatus(
            name=sync.name,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            active=False,
            reason=SyncReason.SOURCE_MARKER_NOT_FOUND,
        )

    if not _check_endpoint_marker(
        dst_vol, sync.destination.subdir, ".ssb-dst"
    ):
        return SyncStatus(
            name=sync.name,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            active=False,
            reason=SyncReason.DESTINATION_MARKER_NOT_FOUND,
        )

    if not _check_command_available(src_vol, "rsync"):
        return SyncStatus(
            name=sync.name,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            active=False,
            reason=SyncReason.RSYNC_NOT_FOUND_ON_SOURCE,
        )

    if not _check_command_available(dst_vol, "rsync"):
        return SyncStatus(
            name=sync.name,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            active=False,
            reason=SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION,
        )

    if sync.btrfs_snapshots and not _check_command_available(dst_vol, "btrfs"):
        return SyncStatus(
            name=sync.name,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            active=False,
            reason=SyncReason.BTRFS_NOT_FOUND_ON_DESTINATION,
        )

    return SyncStatus(
        name=sync.name,
        config=sync,
        source_status=src_status,
        destination_status=dst_status,
        active=True,
        reason=SyncReason.OK,
    )


def check_all_syncs(
    config: Config,
) -> tuple[dict[str, VolumeStatus], dict[str, SyncStatus]]:
    """Check all volumes and syncs, caching volume checks."""
    volume_statuses = {
        name: check_volume(volume) for name, volume in config.volumes.items()
    }
    sync_statuses = {
        name: check_sync(sync, config, volume_statuses)
        for name, sync in config.syncs.items()
    }
    return volume_statuses, sync_statuses
