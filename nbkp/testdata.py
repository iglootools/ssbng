"""Fake data builders for manual testing and output validation."""

from __future__ import annotations

from .config import (
    BtrfsSnapshotConfig,
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)
from .sync import PruneResult, SyncResult
from .check import (
    SyncReason,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
)

_SNAP_BASE = "/mnt/usb-backup/snapshots"


def _bastion_server() -> RsyncServer:
    return RsyncServer(
        slug="bastion",
        host="bastion.example.com",
        user="admin",
    )


def _nas_server() -> RsyncServer:
    return RsyncServer(
        slug="nas",
        host="nas.example.com",
        port=5022,
        user="backup",
        ssh_key="~/.ssh/nas_ed25519",
        proxy_jump="bastion",
    )


def _base_volumes() -> dict[str, LocalVolume | RemoteVolume]:
    return {
        "laptop": LocalVolume(slug="laptop", path="/mnt/data"),
        "usb-drive": LocalVolume(slug="usb-drive", path="/mnt/usb-backup"),
        "nas-backup": RemoteVolume(
            slug="nas-backup",
            rsync_server="nas",
            path="/volume1/backups",
        ),
    }


# ── status ──────────────────────────────────────────────────────


def check_config() -> Config:
    """Config with local + remote volumes and varied syncs."""
    volumes = _base_volumes()
    volumes["external-drive"] = LocalVolume(
        slug="external-drive", path="/mnt/external"
    )
    return Config(
        rsync_servers={
            "bastion": _bastion_server(),
            "nas": _nas_server(),
        },
        volumes=volumes,
        syncs={
            "photos-to-usb": SyncConfig(
                slug="photos-to-usb",
                source=SyncEndpoint(volume="laptop", subdir="photos"),
                destination=DestinationSyncEndpoint(
                    volume="usb-drive",
                    btrfs_snapshots=BtrfsSnapshotConfig(
                        enabled=True, max_snapshots=10
                    ),
                ),
                filters=[
                    "+ *.jpg",
                    "+ *.png",
                    "- *.tmp",
                ],
            ),
            "docs-to-nas": SyncConfig(
                slug="docs-to-nas",
                source=SyncEndpoint(volume="laptop", subdir="documents"),
                destination=DestinationSyncEndpoint(
                    volume="nas-backup",
                    subdir="docs",
                ),
            ),
            "music-to-usb": SyncConfig(
                slug="music-to-usb",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(volume="usb-drive"),
                extra_rsync_options=[
                    "--compress",
                    "--progress",
                ],
            ),
            "disabled-backup": SyncConfig(
                slug="disabled-backup",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(
                    volume="external-drive",
                ),
                enabled=False,
            ),
        },
    )


def check_data(
    config: Config,
) -> tuple[dict[str, VolumeStatus], dict[str, SyncStatus]]:
    """Volume and sync statuses with mixed active/inactive."""
    laptop_vs = VolumeStatus(
        slug="laptop",
        config=config.volumes["laptop"],
        reasons=[],
    )
    usb_vs = VolumeStatus(
        slug="usb-drive",
        config=config.volumes["usb-drive"],
        reasons=[],
    )
    nas_vs = VolumeStatus(
        slug="nas-backup",
        config=config.volumes["nas-backup"],
        reasons=[VolumeReason.UNREACHABLE],
    )
    external_vs = VolumeStatus(
        slug="external-drive",
        config=config.volumes["external-drive"],
        reasons=[VolumeReason.MARKER_NOT_FOUND],
    )

    vol_statuses = {
        "laptop": laptop_vs,
        "usb-drive": usb_vs,
        "nas-backup": nas_vs,
        "external-drive": external_vs,
    }

    sync_statuses = {
        "photos-to-usb": SyncStatus(
            slug="photos-to-usb",
            config=config.syncs["photos-to-usb"],
            source_status=laptop_vs,
            destination_status=usb_vs,
            reasons=[],
        ),
        "docs-to-nas": SyncStatus(
            slug="docs-to-nas",
            config=config.syncs["docs-to-nas"],
            source_status=laptop_vs,
            destination_status=nas_vs,
            reasons=[SyncReason.DESTINATION_UNAVAILABLE],
        ),
        "music-to-usb": SyncStatus(
            slug="music-to-usb",
            config=config.syncs["music-to-usb"],
            source_status=laptop_vs,
            destination_status=usb_vs,
            reasons=[],
        ),
        "disabled-backup": SyncStatus(
            slug="disabled-backup",
            config=config.syncs["disabled-backup"],
            source_status=laptop_vs,
            destination_status=external_vs,
            reasons=[SyncReason.DISABLED],
        ),
    }

    return vol_statuses, sync_statuses


# ── troubleshoot ────────────────────────────────────────────────


def troubleshoot_config() -> Config:
    """Config designed to trigger every troubleshoot reason."""
    return Config(
        rsync_servers={
            "bastion": _bastion_server(),
            "nas": _nas_server(),
        },
        volumes=_base_volumes(),
        syncs={
            "disabled-sync": SyncConfig(
                slug="disabled-sync",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(
                    volume="usb-drive",
                ),
                enabled=False,
            ),
            "unavailable-volumes": SyncConfig(
                slug="unavailable-volumes",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(
                    volume="nas-backup",
                ),
            ),
            "missing-markers": SyncConfig(
                slug="missing-markers",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(volume="usb-drive"),
            ),
            "rsync-missing": SyncConfig(
                slug="rsync-missing",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(volume="nas-backup"),
            ),
            "btrfs-not-detected": SyncConfig(
                slug="btrfs-not-detected",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(
                    volume="usb-drive",
                    btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
                ),
            ),
            "btrfs-mount-issues": SyncConfig(
                slug="btrfs-mount-issues",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(
                    volume="nas-backup",
                    btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
                ),
            ),
            "tools-missing": SyncConfig(
                slug="tools-missing",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(
                    volume="usb-drive",
                    btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
                ),
            ),
        },
    )


def troubleshoot_data(
    config: Config,
) -> tuple[dict[str, VolumeStatus], dict[str, SyncStatus]]:
    """Statuses covering every VolumeReason and SyncReason."""
    laptop_vs = VolumeStatus(
        slug="laptop",
        config=config.volumes["laptop"],
        reasons=[VolumeReason.MARKER_NOT_FOUND],
    )
    usb_vs = VolumeStatus(
        slug="usb-drive",
        config=config.volumes["usb-drive"],
        reasons=[],
    )
    nas_vs = VolumeStatus(
        slug="nas-backup",
        config=config.volumes["nas-backup"],
        reasons=[VolumeReason.UNREACHABLE],
    )

    vol_statuses = {
        "laptop": laptop_vs,
        "usb-drive": usb_vs,
        "nas-backup": nas_vs,
    }

    sync_statuses = {
        "disabled-sync": SyncStatus(
            slug="disabled-sync",
            config=config.syncs["disabled-sync"],
            source_status=laptop_vs,
            destination_status=usb_vs,
            reasons=[SyncReason.DISABLED],
        ),
        "unavailable-volumes": SyncStatus(
            slug="unavailable-volumes",
            config=config.syncs["unavailable-volumes"],
            source_status=laptop_vs,
            destination_status=nas_vs,
            reasons=[
                SyncReason.SOURCE_UNAVAILABLE,
                SyncReason.DESTINATION_UNAVAILABLE,
            ],
        ),
        "missing-markers": SyncStatus(
            slug="missing-markers",
            config=config.syncs["missing-markers"],
            source_status=laptop_vs,
            destination_status=usb_vs,
            reasons=[
                SyncReason.SOURCE_MARKER_NOT_FOUND,
                SyncReason.DESTINATION_MARKER_NOT_FOUND,
            ],
        ),
        "rsync-missing": SyncStatus(
            slug="rsync-missing",
            config=config.syncs["rsync-missing"],
            source_status=laptop_vs,
            destination_status=nas_vs,
            reasons=[
                SyncReason.RSYNC_NOT_FOUND_ON_SOURCE,
                SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION,
            ],
        ),
        "btrfs-not-detected": SyncStatus(
            slug="btrfs-not-detected",
            config=config.syncs["btrfs-not-detected"],
            source_status=laptop_vs,
            destination_status=usb_vs,
            reasons=[
                SyncReason.BTRFS_NOT_FOUND_ON_DESTINATION,
                SyncReason.DESTINATION_NOT_BTRFS,
                SyncReason.DESTINATION_NOT_BTRFS_SUBVOLUME,
            ],
        ),
        "btrfs-mount-issues": SyncStatus(
            slug="btrfs-mount-issues",
            config=config.syncs["btrfs-mount-issues"],
            source_status=laptop_vs,
            destination_status=nas_vs,
            reasons=[
                SyncReason.DESTINATION_NOT_MOUNTED_USER_SUBVOL_RM,
                SyncReason.DESTINATION_LATEST_NOT_FOUND,
                SyncReason.DESTINATION_SNAPSHOTS_DIR_NOT_FOUND,
            ],
        ),
        "tools-missing": SyncStatus(
            slug="tools-missing",
            config=config.syncs["tools-missing"],
            source_status=laptop_vs,
            destination_status=usb_vs,
            reasons=[
                SyncReason.STAT_NOT_FOUND_ON_DESTINATION,
                SyncReason.FINDMNT_NOT_FOUND_ON_DESTINATION,
            ],
        ),
    }

    return vol_statuses, sync_statuses


# ── run results ─────────────────────────────────────────────────


def run_results() -> list[SyncResult]:
    """Sync results: success, success+snapshot, failure."""
    snap = f"{_SNAP_BASE}/2026-02-19T10:30:00.000Z"
    return [
        SyncResult(
            sync_slug="music-to-usb",
            success=True,
            dry_run=False,
            rsync_exit_code=0,
            output="",
        ),
        SyncResult(
            sync_slug="photos-to-usb",
            success=True,
            dry_run=False,
            rsync_exit_code=0,
            output="",
            snapshot_path=snap,
            pruned_paths=[
                f"{_SNAP_BASE}/2026-02-01T08:00:00.000Z",
                f"{_SNAP_BASE}/2026-02-10T12:00:00.000Z",
            ],
        ),
        SyncResult(
            sync_slug="docs-to-nas",
            success=False,
            dry_run=False,
            rsync_exit_code=23,
            output=(
                "rsync: [sender] link_stat"
                ' "/mnt/data/documents" failed:'
                " No such file or directory (2)\n"
                "rsync error: some files/attrs"
                " were not transferred (code 23)\n"
            ),
            error="rsync exited with code 23",
        ),
    ]


def dry_run_result() -> SyncResult:
    """Single dry-run success result."""
    return SyncResult(
        sync_slug="photos-to-usb",
        success=True,
        dry_run=True,
        rsync_exit_code=0,
        output="",
    )


# ── prune results ───────────────────────────────────────────────


def prune_results() -> list[PruneResult]:
    """Prune results: success, noop, error."""
    return [
        PruneResult(
            sync_slug="photos-to-usb",
            deleted=[
                f"{_SNAP_BASE}/2026-01-01T00:00:00.000Z",
                f"{_SNAP_BASE}/2026-01-15T00:00:00.000Z",
                f"{_SNAP_BASE}/2026-02-01T00:00:00.000Z",
            ],
            kept=7,
            dry_run=False,
        ),
        PruneResult(
            sync_slug="music-to-usb",
            deleted=[],
            kept=5,
            dry_run=False,
        ),
        PruneResult(
            sync_slug="docs-to-nas",
            deleted=[],
            kept=0,
            dry_run=False,
            error="btrfs delete failed: Permission denied",
        ),
    ]


def prune_dry_run_results() -> list[PruneResult]:
    """Prune dry-run results."""
    return [
        PruneResult(
            sync_slug="photos-to-usb",
            deleted=[
                f"{_SNAP_BASE}/2026-01-01T00:00:00.000Z",
                f"{_SNAP_BASE}/2026-01-15T00:00:00.000Z",
            ],
            kept=10,
            dry_run=True,
        ),
    ]
