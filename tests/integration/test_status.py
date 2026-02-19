"""Integration tests: volume and sync status checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ssb.status import (
    SyncReason,
    _check_btrfs_filesystem,
    _check_btrfs_subvolume,
    check_sync,
    check_volume,
)
from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)

from .conftest import create_markers, ssh_exec

pytestmark = pytest.mark.integration


class TestLocalVolumeStatus:
    def test_local_volume_active(self, tmp_path: Path) -> None:
        vol_path = tmp_path / "vol"
        vol_path.mkdir()
        (vol_path / ".ssb-vol").touch()

        vol = LocalVolume(slug="local", path=str(vol_path))
        config = Config(
            volumes={"local": vol},
        )
        status = check_volume(vol, config)
        assert status.active is True

    def test_local_volume_inactive(self, tmp_path: Path) -> None:
        vol_path = tmp_path / "vol"
        vol_path.mkdir()
        # No .ssb-vol marker

        vol = LocalVolume(slug="local", path=str(vol_path))
        config = Config(
            volumes={"local": vol},
        )
        status = check_volume(vol, config)
        assert status.active is False


class TestRemoteVolumeStatus:
    def test_remote_volume_active(
        self,
        docker_container: dict[str, Any],
        rsync_server: RsyncServer,
        remote_volume: RemoteVolume,
    ) -> None:
        create_markers(docker_container, "/data", [".ssb-vol"])
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"test-remote": remote_volume},
        )
        status = check_volume(remote_volume, config)
        assert status.active is True

    def test_remote_volume_inactive(
        self,
        docker_container: dict[str, Any],
        rsync_server: RsyncServer,
        remote_volume: RemoteVolume,
    ) -> None:
        # No marker created
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"test-remote": remote_volume},
        )
        status = check_volume(remote_volume, config)
        assert status.active is False


class TestSyncStatus:
    def test_sync_status_active(
        self,
        tmp_path: Path,
        docker_container: dict[str, Any],
        rsync_server: RsyncServer,
        remote_volume: RemoteVolume,
    ) -> None:
        # Set up local source volume
        src_path = tmp_path / "src"
        src_path.mkdir()
        (src_path / ".ssb-vol").touch()
        (src_path / ".ssb-src").touch()

        # Set up remote destination markers
        create_markers(docker_container, "/data", [".ssb-vol", ".ssb-dst"])

        src_vol = LocalVolume(slug="src", path=str(src_path))
        sync = SyncConfig(
            slug="test-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"src": src_vol, "dst": remote_volume},
            syncs={"test-sync": sync},
        )

        src_status = check_volume(src_vol, config)
        dst_status = check_volume(remote_volume, config)
        volume_statuses = {
            "src": src_status,
            "dst": dst_status,
        }

        status = check_sync(sync, config, volume_statuses)
        assert status.active is True
        assert status.reasons == []


class TestBtrfsFilesystemCheck:
    def test_btrfs_path_detected(
        self,
        docker_container: dict[str, Any],
        rsync_server: RsyncServer,
        remote_btrfs_volume: RemoteVolume,
    ) -> None:
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"btrfs": remote_btrfs_volume},
        )
        assert _check_btrfs_filesystem(remote_btrfs_volume, config) is True

    def test_non_btrfs_path_detected(
        self,
        docker_container: dict[str, Any],
        rsync_server: RsyncServer,
        remote_volume: RemoteVolume,
    ) -> None:
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"data": remote_volume},
        )
        assert _check_btrfs_filesystem(remote_volume, config) is False


class TestBtrfsSubvolumeCheck:
    def test_subvolume_detected(
        self,
        docker_container: dict[str, Any],
        rsync_server: RsyncServer,
        remote_btrfs_volume: RemoteVolume,
    ) -> None:
        ssh_exec(
            docker_container,
            "btrfs subvolume create /mnt/btrfs/test-subvol",
        )
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"btrfs": remote_btrfs_volume},
        )
        assert (
            _check_btrfs_subvolume(remote_btrfs_volume, "test-subvol", config)
            is True
        )

        # Cleanup
        ssh_exec(
            docker_container,
            "btrfs subvolume delete /mnt/btrfs/test-subvol",
        )

    def test_regular_dir_not_subvolume(
        self,
        docker_container: dict[str, Any],
        rsync_server: RsyncServer,
        remote_btrfs_volume: RemoteVolume,
    ) -> None:
        ssh_exec(
            docker_container,
            "mkdir -p /mnt/btrfs/regular-dir",
        )
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"btrfs": remote_btrfs_volume},
        )
        assert (
            _check_btrfs_subvolume(remote_btrfs_volume, "regular-dir", config)
            is False
        )

        # Cleanup
        ssh_exec(
            docker_container,
            "rm -rf /mnt/btrfs/regular-dir",
        )


class TestSyncStatusBtrfsChecks:
    def test_sync_inactive_when_not_subvolume(
        self,
        tmp_path: Path,
        docker_container: dict[str, Any],
        rsync_server: RsyncServer,
        remote_btrfs_volume: RemoteVolume,
    ) -> None:
        # Create a regular directory (not a subvolume)
        ssh_exec(
            docker_container,
            "mkdir -p /mnt/btrfs/not-a-subvol",
        )
        create_markers(
            docker_container,
            "/mnt/btrfs",
            [".ssb-vol"],
        )
        create_markers(
            docker_container,
            "/mnt/btrfs/not-a-subvol",
            [".ssb-dst"],
        )

        src_path = tmp_path / "src"
        src_path.mkdir()
        (src_path / ".ssb-vol").touch()
        (src_path / ".ssb-src").touch()

        src_vol = LocalVolume(slug="src", path=str(src_path))
        sync = SyncConfig(
            slug="test-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="not-a-subvol",
                btrfs_snapshots=True,
            ),
        )
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"src": src_vol, "dst": remote_btrfs_volume},
            syncs={"test-sync": sync},
        )

        src_status = check_volume(src_vol, config)
        dst_status = check_volume(remote_btrfs_volume, config)
        volume_statuses = {
            "src": src_status,
            "dst": dst_status,
        }

        status = check_sync(sync, config, volume_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_NOT_BTRFS_SUBVOLUME in status.reasons

        # Cleanup
        ssh_exec(
            docker_container,
            "rm -rf /mnt/btrfs/not-a-subvol",
        )
