"""Integration tests: remote-to-local sync (Docker)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ssb.config import (
    Config,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    SyncEndpoint,
)
from ssb.rsync import run_rsync

from .conftest import ssh_exec

pytestmark = pytest.mark.integration


class TestRemoteToLocal:
    def test_sync_from_container(
        self,
        tmp_path: Path,
        docker_container: dict[str, Any],
        remote_volume: RemoteVolume,
    ) -> None:
        # Create test files on container
        ssh_exec(
            docker_container,
            "echo 'hello from remote' > /data/src/remote-file.txt",
        )

        # Set up local destination
        dst_dir = tmp_path / "dst"
        (dst_dir / "latest").mkdir(parents=True)

        dst_vol = LocalVolume(name="dst", path=str(dst_dir))
        # Use a RemoteVolume for src pointing at /data/src
        src_vol = RemoteVolume(
            name="src-remote",
            host=docker_container["host"],
            path="/data/src",
            port=docker_container["port"],
            user=docker_container["user"],
            ssh_key=docker_container["private_key"],
            ssh_options=[
                "StrictHostKeyChecking=no",
                "UserKnownHostsFile=/dev/null",
            ],
        )
        sync = SyncConfig(
            name="test-sync",
            source=SyncEndpoint(volume_name="src"),
            destination=SyncEndpoint(volume_name="dst"),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"test-sync": sync},
        )

        result = run_rsync(sync, config)
        assert result.returncode == 0
        assert (
            dst_dir / "latest" / "remote-file.txt"
        ).read_text().strip() == "hello from remote"
