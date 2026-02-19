"""Volume and sync activity checks."""

from __future__ import annotations

from pathlib import Path

from .config import (
    Config,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    Volume,
)
from .model import (
    SyncReason,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
)
from .ssh import run_remote_command


def check_volume(volume: Volume) -> VolumeStatus:
    """Check if a volume is active."""
    if isinstance(volume, LocalVolume):
        return _check_local_volume(volume)
    else:
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
    if result.returncode == 0:
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

    if isinstance(volume, LocalVolume):
        return Path(rel_path).exists()
    else:
        result = run_remote_command(volume, f"test -f {rel_path}")
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
    volume_statuses: dict[str, VolumeStatus] = {}
    for name, volume in config.volumes.items():
        volume_statuses[name] = check_volume(volume)

    sync_statuses: dict[str, SyncStatus] = {}
    for name, sync in config.syncs.items():
        sync_statuses[name] = check_sync(sync, config, volume_statuses)

    return volume_statuses, sync_statuses
