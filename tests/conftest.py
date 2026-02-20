"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)


def config_to_yaml(config: Config) -> str:
    """Convert a Config to a YAML string."""
    return yaml.safe_dump(
        config.model_dump(by_alias=True),
        default_flow_style=False,
        sort_keys=False,
    )


def _sample_config() -> Config:
    """Build the full sample Config."""
    return Config(
        rsync_servers={
            "nas-server": RsyncServer(
                slug="nas-server",
                host="nas.example.com",
                port=5022,
                user="backup",
                ssh_key="~/.ssh/key",
            ),
        },
        volumes={
            "local-data": LocalVolume(
                slug="local-data", path="/mnt/data"
            ),
            "nas": RemoteVolume(
                slug="nas",
                rsync_server="nas-server",
                path="/volume1/backups",
            ),
        },
        syncs={
            "photos-to-nas": SyncConfig(
                slug="photos-to-nas",
                source=SyncEndpoint(
                    volume="local-data", subdir="photos"
                ),
                destination=DestinationSyncEndpoint(
                    volume="nas",
                    subdir="photos-backup",
                ),
                enabled=True,
                filters=["+ *.jpg", "- *.tmp"],
                filter_file=(
                    "~/.config/ssb/filters/photos.rules"
                ),
            ),
        },
    )


def _sample_minimal_config() -> Config:
    """Build the minimal sample Config."""
    return Config(
        volumes={
            "src": LocalVolume(slug="src", path="/src"),
            "dst": LocalVolume(slug="dst", path="/dst"),
        },
        syncs={
            "s1": SyncConfig(
                slug="s1",
                source=SyncEndpoint(volume="src"),
                destination=DestinationSyncEndpoint(
                    volume="dst"
                ),
            ),
        },
    )


@pytest.fixture()
def sample_config_file(tmp_path: Path) -> Path:
    """Write sample YAML config to a temp file."""
    p = tmp_path / "config.yaml"
    p.write_text(config_to_yaml(_sample_config()))
    return p


@pytest.fixture()
def sample_minimal_config_file(tmp_path: Path) -> Path:
    """Write minimal YAML config to a temp file."""
    p = tmp_path / "config.yaml"
    p.write_text(config_to_yaml(_sample_minimal_config()))
    return p


@pytest.fixture()
def local_volume() -> LocalVolume:
    return LocalVolume(slug="local-data", path="/mnt/data")


@pytest.fixture()
def rsync_server() -> RsyncServer:
    return RsyncServer(
        slug="nas-server",
        host="nas.example.com",
        port=5022,
        user="backup",
        ssh_key="~/.ssh/key",
    )


@pytest.fixture()
def rsync_server_minimal() -> RsyncServer:
    return RsyncServer(
        slug="nas2-server",
        host="nas2.example.com",
    )


@pytest.fixture()
def remote_volume() -> RemoteVolume:
    return RemoteVolume(
        slug="nas",
        rsync_server="nas-server",
        path="/volume1/backups",
    )


@pytest.fixture()
def remote_volume_minimal() -> RemoteVolume:
    return RemoteVolume(
        slug="nas2",
        rsync_server="nas2-server",
        path="/backups",
    )


@pytest.fixture()
def sample_config() -> Config:
    return _sample_config()
