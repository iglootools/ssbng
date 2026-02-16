"""Integration tests: local-to-remote sync (Docker)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ssb.model import (
    Config,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    SyncEndpoint,
)
from ssb.rsync import run_rsync

from .conftest import create_markers, ssh_exec

pytestmark = pytest.mark.integration


class TestLocalToRemote:
    def test_sync_to_container(
        self,
        tmp_path: Path,
        docker_container: dict[str, Any],
        remote_volume: RemoteVolume,
    ) -> None:
        # Create markers on remote
        create_markers(docker_container, "/data", [".ssb-vol", ".ssb-dst"])

        # Create local source files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "hello.txt").write_text("hello from local")

        src_vol = LocalVolume(name="src", path=str(src_dir))
        sync = SyncConfig(
            name="test-sync",
            source=SyncEndpoint(volume_name="src"),
            destination=SyncEndpoint(volume_name="dst"),
        )
        config = Config(
            volumes={"src": src_vol, "dst": remote_volume},
            syncs={"test-sync": sync},
        )

        result = run_rsync(sync, config)
        assert result.returncode == 0

        # Verify file arrived on container
        check = ssh_exec(docker_container, "cat /data/latest/hello.txt")
        assert check.returncode == 0
        assert check.stdout.strip() == "hello from local"

    def test_sync_with_subdir(
        self,
        tmp_path: Path,
        docker_container: dict[str, Any],
        remote_volume: RemoteVolume,
    ) -> None:
        # Create remote subdir structure and markers
        ssh_exec(docker_container, "mkdir -p /data/photos-backup/latest")
        create_markers(docker_container, "/data", [".ssb-vol"])
        create_markers(docker_container, "/data/photos-backup", [".ssb-dst"])

        # Create local source with subdir
        src_dir = tmp_path / "src" / "photos"
        src_dir.mkdir(parents=True)
        (src_dir / "img.jpg").write_text("image-data")

        src_vol = LocalVolume(name="src", path=str(tmp_path / "src"))
        sync = SyncConfig(
            name="test-sync",
            source=SyncEndpoint(volume_name="src", subdir="photos"),
            destination=SyncEndpoint(
                volume_name="dst", subdir="photos-backup"
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": remote_volume},
            syncs={"test-sync": sync},
        )

        result = run_rsync(sync, config)
        assert result.returncode == 0

        check = ssh_exec(
            docker_container,
            "cat /data/photos-backup/latest/img.jpg",
        )
        assert check.returncode == 0
        assert check.stdout.strip() == "image-data"
