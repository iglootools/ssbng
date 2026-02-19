"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    SyncEndpoint,
)

SAMPLE_YAML = """\
volumes:
  local-data:
    type: local
    path: /mnt/data

  nas:
    type: remote
    host: nas.example.com
    port: 5022
    user: backup
    ssh_key: ~/.ssh/key
    path: /volume1/backups

syncs:
  photos-to-nas:
    enabled: true
    source:
      volume: local-data
      subdir: photos
    destination:
      volume: nas
      subdir: photos-backup
      btrfs_snapshots: false
"""

SAMPLE_YAML_MINIMAL = """\
volumes:
  src:
    type: local
    path: /src

  dst:
    type: local
    path: /dst

syncs:
  s1:
    source:
      volume: src
    destination:
      volume: dst
"""


@pytest.fixture()
def sample_config_file(tmp_path: Path) -> Path:
    """Write sample YAML config to a temp file."""
    p = tmp_path / "config.yaml"
    p.write_text(SAMPLE_YAML)
    return p


@pytest.fixture()
def sample_minimal_config_file(tmp_path: Path) -> Path:
    """Write minimal YAML config to a temp file."""
    p = tmp_path / "config.yaml"
    p.write_text(SAMPLE_YAML_MINIMAL)
    return p


@pytest.fixture()
def local_volume() -> LocalVolume:
    return LocalVolume(name="local-data", path="/mnt/data")


@pytest.fixture()
def remote_volume() -> RemoteVolume:
    return RemoteVolume(
        name="nas",
        host="nas.example.com",
        path="/volume1/backups",
        port=5022,
        user="backup",
        ssh_key="~/.ssh/key",
    )


@pytest.fixture()
def remote_volume_minimal() -> RemoteVolume:
    return RemoteVolume(
        name="nas2",
        host="nas2.example.com",
        path="/backups",
    )


@pytest.fixture()
def sample_config(
    local_volume: LocalVolume, remote_volume: RemoteVolume
) -> Config:
    return Config(
        volumes={
            "local-data": local_volume,
            "nas": remote_volume,
        },
        syncs={
            "photos-to-nas": SyncConfig(
                name="photos-to-nas",
                source=SyncEndpoint(volume_name="local-data", subdir="photos"),
                destination=DestinationSyncEndpoint(
                    volume_name="nas",
                    subdir="photos-backup",
                    btrfs_snapshots=False,
                ),
                enabled=True,
            ),
        },
    )
