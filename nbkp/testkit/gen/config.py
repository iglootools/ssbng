"""Fake config builders for manual testing."""

from __future__ import annotations

from ...config import (
    BtrfsSnapshotConfig,
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)


def bastion_server() -> RsyncServer:
    return RsyncServer(
        slug="bastion",
        host="bastion.example.com",
        user="admin",
    )


def nas_server() -> RsyncServer:
    return RsyncServer(
        slug="nas",
        host="nas.example.com",
        port=5022,
        user="backup",
        ssh_key="~/.ssh/nas_ed25519",
        proxy_jump="bastion",
    )


def base_volumes() -> dict[str, LocalVolume | RemoteVolume]:
    return {
        "laptop": LocalVolume(slug="laptop", path="/mnt/data"),
        "usb-drive": LocalVolume(slug="usb-drive", path="/mnt/usb-backup"),
        "nas-backup": RemoteVolume(
            slug="nas-backup",
            rsync_server="nas",
            path="/volume1/backups",
        ),
    }


def config_show_config() -> Config:
    """Config exercising all display paths for config show."""
    return Config(
        rsync_servers={
            "bastion": bastion_server(),
            "nas": nas_server(),
        },
        volumes=base_volumes(),
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
                filters=["+ *.jpg", "- *.tmp"],
            ),
            "docs-to-nas": SyncConfig(
                slug="docs-to-nas",
                source=SyncEndpoint(volume="laptop", subdir="documents"),
                destination=DestinationSyncEndpoint(
                    volume="nas-backup",
                    subdir="docs",
                ),
            ),
            "disabled-backup": SyncConfig(
                slug="disabled-backup",
                source=SyncEndpoint(volume="laptop"),
                destination=DestinationSyncEndpoint(
                    volume="usb-drive",
                ),
                enabled=False,
            ),
        },
    )
