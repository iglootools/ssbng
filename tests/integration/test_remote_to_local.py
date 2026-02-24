"""Integration tests: remote-to-local sync (Docker)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nbkp.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)
from nbkp.sync.rsync import run_rsync

from .conftest import ssh_exec

pytestmark = pytest.mark.integration


class TestRemoteToLocal:
    def test_sync_from_container(
        self,
        tmp_path: Path,
        rsync_server: RsyncServer,
    ) -> None:
        # Create test files on container
        ssh_exec(
            rsync_server,
            "echo 'hello from remote' > /data/src/remote-file.txt",
        )

        # Set up local destination
        dst_dir = tmp_path / "dst"
        (dst_dir / "latest").mkdir(parents=True)

        dst_vol = LocalVolume(slug="dst", path=str(dst_dir))
        src_vol = RemoteVolume(
            slug="src-remote",
            rsync_server="test-server",
            path="/data/src",
        )
        sync = SyncConfig(
            slug="test-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            rsync_servers={"test-server": rsync_server},
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"test-sync": sync},
        )

        result = run_rsync(sync, config)
        assert result.returncode == 0
        assert (
            dst_dir / "latest" / "remote-file.txt"
        ).read_text().strip() == "hello from remote"
