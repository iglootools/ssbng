"""Integration tests: remote-to-local sync (Docker)."""

from __future__ import annotations

import pytest

from nbkp.config import (
    Config,
    DestinationSyncEndpoint,
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
        ssh_endpoint: SshEndpoint,
    ) -> None:
        # Create test files on remote source
        ssh_exec(
            ssh_endpoint,
            "echo 'hello from remote' > /data/src/remote-file.txt",
        )

        # Set up remote destination
        ssh_exec(ssh_endpoint, "mkdir -p /data/dst/latest")

        # Both volumes reference the same SSH endpoint.
        # The same-server optimization SSHes in once and
        # runs rsync with local paths.
        src_vol = RemoteVolume(
            slug="src-remote",
            ssh_endpoint="test-server",
            path="/data/src",
        )
        dst_vol = RemoteVolume(
            slug="dst-remote",
            ssh_endpoint="test-server",
            path="/data/dst",
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
        out = ssh_exec(
            ssh_endpoint,
            "cat /data/dst/latest/remote-file.txt",
        )
        assert out.stdout.strip() == "hello from remote"
