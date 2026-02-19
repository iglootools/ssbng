"""Integration tests: volume and sync status checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ssb.status import check_sync, check_volume
from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)

from .conftest import create_markers

pytestmark = pytest.mark.integration


class TestLocalVolumeStatus:
    def test_local_volume_active(self, tmp_path: Path) -> None:
        vol_path = tmp_path / "vol"
        vol_path.mkdir()
        (vol_path / ".ssb-vol").touch()

        vol = LocalVolume(name="local", path=str(vol_path))
        config = Config(
            volumes={"local": vol},
        )
        status = check_volume(vol, config)
        assert status.active is True

    def test_local_volume_inactive(self, tmp_path: Path) -> None:
        vol_path = tmp_path / "vol"
        vol_path.mkdir()
        # No .ssb-vol marker

        vol = LocalVolume(name="local", path=str(vol_path))
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

        src_vol = LocalVolume(name="src", path=str(src_path))
        sync = SyncConfig(
            name="test-sync",
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
