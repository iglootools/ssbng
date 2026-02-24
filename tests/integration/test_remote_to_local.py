"""Integration tests: remote-to-local sync (Docker)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nbkp.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    SshEndpoint,
    SyncConfig,
    SyncEndpoint,
    resolve_all_endpoints,
)
from nbkp.sync.rsync import run_rsync

from .conftest import ssh_exec

pytestmark = pytest.mark.integration


class TestRemoteToLocal:
    def test_sync_from_container(
        self,
        tmp_path: Path,
        ssh_endpoint: SshEndpoint,
    ) -> None:
        # Create test files on container
        ssh_exec(
            ssh_endpoint,
            "echo 'hello from remote' > /data/src/remote-file.txt",
        )

        # Set up local destination
        dst_dir = tmp_path / "dst"
        (dst_dir / "latest").mkdir(parents=True)

        dst_vol = LocalVolume(slug="dst", path=str(dst_dir))
        src_vol = RemoteVolume(
            slug="src-remote",
            ssh_endpoint="test-server",
            path="/data/src",
        )
        sync = SyncConfig(
            slug="test-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={"test-server": ssh_endpoint},
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"test-sync": sync},
        )

        resolved = resolve_all_endpoints(config)
        result = run_rsync(
            sync,
            config,
            resolved_endpoints=resolved,
        )
        assert result.returncode == 0
        assert (
            dst_dir / "latest" / "remote-file.txt"
        ).read_text().strip() == "hello from remote"
