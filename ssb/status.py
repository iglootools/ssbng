"""Runtime status types for volumes and syncs, and activity checks."""

from __future__ import annotations

import enum
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, computed_field

from .config import (
    Config,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    Volume,
)
from .ssh import run_remote_command


class VolumeReason(str, enum.Enum):
    MARKER_NOT_FOUND = "marker not found"
    UNREACHABLE = "unreachable"


class SyncReason(str, enum.Enum):
    DISABLED = "disabled"
    SOURCE_UNAVAILABLE = "source unavailable"
    DESTINATION_UNAVAILABLE = "destination unavailable"
    SOURCE_MARKER_NOT_FOUND = "source marker .ssb-src not found"
    DESTINATION_MARKER_NOT_FOUND = "destination marker .ssb-dst not found"
    RSYNC_NOT_FOUND_ON_SOURCE = "rsync not found on source"
    RSYNC_NOT_FOUND_ON_DESTINATION = "rsync not found on destination"
    BTRFS_NOT_FOUND_ON_DESTINATION = "btrfs not found on destination"
    STAT_NOT_FOUND_ON_DESTINATION = "stat not found on destination"
    FINDMNT_NOT_FOUND_ON_DESTINATION = "findmnt not found on destination"
    DESTINATION_NOT_BTRFS = "destination not on btrfs filesystem"
    DESTINATION_NOT_BTRFS_SUBVOLUME = (
        "destination endpoint is not a btrfs subvolume"
    )
    DESTINATION_NOT_MOUNTED_USER_SUBVOL_RM = (
        "destination not mounted with user_subvol_rm_allowed"
    )
    DESTINATION_LATEST_NOT_FOUND = "destination latest/ directory not found"
    DESTINATION_SNAPSHOTS_DIR_NOT_FOUND = (
        "destination snapshots/ directory not found"
    )


class VolumeStatus(BaseModel):
    """Runtime status of a volume."""

    slug: str
    config: Volume
    reasons: list[VolumeReason]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def active(self) -> bool:
        return len(self.reasons) == 0


class SyncStatus(BaseModel):
    """Runtime status of a sync."""

    slug: str
    config: SyncConfig
    source_status: VolumeStatus
    destination_status: VolumeStatus
    reasons: list[SyncReason]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def active(self) -> bool:
        return len(self.reasons) == 0


def check_volume(volume: Volume, config: Config) -> VolumeStatus:
    """Check if a volume is active."""
    match volume:
        case LocalVolume():
            return _check_local_volume(volume)
        case RemoteVolume():
            return _check_remote_volume(volume, config)


def _check_local_volume(volume: LocalVolume) -> VolumeStatus:
    """Check if a local volume is active (.ssb-vol marker exists)."""
    marker = Path(volume.path) / ".ssb-vol"
    reasons: list[VolumeReason] = (
        [] if marker.exists() else [VolumeReason.MARKER_NOT_FOUND]
    )
    return VolumeStatus(
        slug=volume.slug,
        config=volume,
        reasons=reasons,
    )


def _check_remote_volume(volume: RemoteVolume, config: Config) -> VolumeStatus:
    """Check if a remote volume is active (SSH + .ssb-vol marker)."""
    server = config.rsync_servers[volume.rsync_server]
    marker_path = f"{volume.path}/.ssb-vol"
    result = run_remote_command(server, ["test", "-f", marker_path])
    reasons: list[VolumeReason] = (
        [] if result.returncode == 0 else [VolumeReason.UNREACHABLE]
    )
    return VolumeStatus(
        slug=volume.slug,
        config=volume,
        reasons=reasons,
    )


def _check_endpoint_marker(
    volume: Volume,
    subdir: str | None,
    marker_name: str,
    config: Config,
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
            server = config.rsync_servers[volume.rsync_server]
            result = run_remote_command(server, ["test", "-f", rel_path])
            return result.returncode == 0


def _check_command_available(
    volume: Volume, command: str, config: Config
) -> bool:
    """Check if a command is available on the volume's host."""
    match volume:
        case LocalVolume():
            return shutil.which(command) is not None
        case RemoteVolume():
            server = config.rsync_servers[volume.rsync_server]
            result = run_remote_command(server, ["which", command])
            return result.returncode == 0


def _check_btrfs_filesystem(volume: Volume, config: Config) -> bool:
    """Check if the volume path is on a btrfs filesystem."""
    cmd = ["stat", "-f", "-c", "%T", volume.path]
    match volume:
        case LocalVolume():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
        case RemoteVolume():
            server = config.rsync_servers[volume.rsync_server]
            result = run_remote_command(server, cmd)
    return result.returncode == 0 and result.stdout.strip() == "btrfs"


def _resolve_endpoint(volume: Volume, subdir: str | None) -> str:
    """Resolve the full endpoint path for a volume."""
    if subdir:
        return f"{volume.path}/{subdir}"
    else:
        return volume.path


def _check_directory_exists(volume: Volume, path: str, config: Config) -> bool:
    """Check if a directory exists on the volume's host."""
    match volume:
        case LocalVolume():
            return Path(path).is_dir()
        case RemoteVolume():
            server = config.rsync_servers[volume.rsync_server]
            result = run_remote_command(server, ["test", "-d", path])
            return result.returncode == 0


def _check_btrfs_subvolume(
    volume: Volume,
    subdir: str | None,
    config: Config,
) -> bool:
    """Check if the endpoint path is a btrfs subvolume.

    On btrfs, subvolumes always have inode number 256.
    """
    path = _resolve_endpoint(volume, subdir)
    cmd = ["stat", "-c", "%i", path]
    match volume:
        case LocalVolume():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
        case RemoteVolume():
            server = config.rsync_servers[volume.rsync_server]
            result = run_remote_command(server, cmd)
    return result.returncode == 0 and result.stdout.strip() == "256"


def _check_btrfs_mount_option(
    volume: Volume,
    option: str,
    config: Config,
) -> bool:
    """Check if the volume is mounted with a specific mount option."""
    cmd = ["findmnt", "-n", "-o", "OPTIONS", volume.path]
    match volume:
        case LocalVolume():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
        case RemoteVolume():
            server = config.rsync_servers[volume.rsync_server]
            result = run_remote_command(server, cmd)
    if result.returncode != 0:
        return False
    options = result.stdout.strip().split(",")
    return option in options


def _check_btrfs_dest(
    dst_vol: Volume,
    sync: SyncConfig,
    config: Config,
    has_findmnt: bool,
    reasons: list[SyncReason],
) -> None:
    """Run btrfs filesystem, subvolume, and directory checks."""
    if not _check_btrfs_filesystem(dst_vol, config):
        reasons.append(SyncReason.DESTINATION_NOT_BTRFS)
    elif not _check_btrfs_subvolume(
        dst_vol,
        sync.destination.subdir,
        config,
    ):
        reasons.append(SyncReason.DESTINATION_NOT_BTRFS_SUBVOLUME)
    else:
        if has_findmnt and not _check_btrfs_mount_option(
            dst_vol,
            "user_subvol_rm_allowed",
            config,
        ):
            reasons.append(SyncReason.DESTINATION_NOT_MOUNTED_USER_SUBVOL_RM)
        ep = _resolve_endpoint(dst_vol, sync.destination.subdir)
        if not _check_directory_exists(dst_vol, f"{ep}/latest", config):
            reasons.append(SyncReason.DESTINATION_LATEST_NOT_FOUND)
        if not _check_directory_exists(dst_vol, f"{ep}/snapshots", config):
            reasons.append(SyncReason.DESTINATION_SNAPSHOTS_DIR_NOT_FOUND)


def check_sync(
    sync: SyncConfig,
    config: Config,
    volume_statuses: dict[str, VolumeStatus],
) -> SyncStatus:
    """Check if a sync is active, accumulating all failure reasons."""
    src_vol_name = sync.source.volume
    dst_vol_name = sync.destination.volume

    src_status = volume_statuses[src_vol_name]
    dst_status = volume_statuses[dst_vol_name]

    if not sync.enabled:
        return SyncStatus(
            slug=sync.slug,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            reasons=[SyncReason.DISABLED],
        )
    else:
        reasons: list[SyncReason] = []

        src_vol = config.volumes[src_vol_name]
        dst_vol = config.volumes[dst_vol_name]

        # Volume availability
        if not src_status.active:
            reasons.append(SyncReason.SOURCE_UNAVAILABLE)

        if not dst_status.active:
            reasons.append(SyncReason.DESTINATION_UNAVAILABLE)

        # Source checks (only if source volume is active)
        if src_status.active:
            if not _check_endpoint_marker(
                src_vol, sync.source.subdir, ".ssb-src", config
            ):
                reasons.append(SyncReason.SOURCE_MARKER_NOT_FOUND)
            if not _check_command_available(src_vol, "rsync", config):
                reasons.append(SyncReason.RSYNC_NOT_FOUND_ON_SOURCE)

        # Destination checks (only if destination volume is active)
        if dst_status.active:
            if not _check_endpoint_marker(
                dst_vol,
                sync.destination.subdir,
                ".ssb-dst",
                config,
            ):
                reasons.append(SyncReason.DESTINATION_MARKER_NOT_FOUND)
            if not _check_command_available(dst_vol, "rsync", config):
                reasons.append(SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION)
            if sync.destination.btrfs_snapshots.enabled:
                if not _check_command_available(dst_vol, "btrfs", config):
                    reasons.append(SyncReason.BTRFS_NOT_FOUND_ON_DESTINATION)
                else:
                    has_stat = _check_command_available(
                        dst_vol, "stat", config
                    )
                    has_findmnt = _check_command_available(
                        dst_vol, "findmnt", config
                    )

                    if not has_stat:
                        reasons.append(
                            SyncReason.STAT_NOT_FOUND_ON_DESTINATION
                        )
                    if not has_findmnt:
                        reasons.append(
                            SyncReason.FINDMNT_NOT_FOUND_ON_DESTINATION
                        )

                    if has_stat:
                        _check_btrfs_dest(
                            dst_vol,
                            sync,
                            config,
                            has_findmnt,
                            reasons,
                        )

        return SyncStatus(
            slug=sync.slug,
            config=sync,
            source_status=src_status,
            destination_status=dst_status,
            reasons=reasons,
        )


def check_all_syncs(
    config: Config,
) -> tuple[dict[str, VolumeStatus], dict[str, SyncStatus]]:
    """Check all volumes and syncs, caching volume checks."""
    volume_statuses = {
        slug: check_volume(volume, config)
        for slug, volume in config.volumes.items()
    }
    sync_statuses = {
        slug: check_sync(sync, config, volume_statuses)
        for slug, sync in config.syncs.items()
    }
    return volume_statuses, sync_statuses
