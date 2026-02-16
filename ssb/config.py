"""YAML configuration loading, parsing, and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .model import (
    Config,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    SyncEndpoint,
    Volume,
)


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def find_config_file(config_path: str | None = None) -> Path:
    """Find the configuration file using search order.

    Order: explicit path > XDG_CONFIG_HOME > /etc/ssb/
    """
    if config_path is not None:
        p = Path(config_path)
        if not p.is_file():
            raise ConfigError(f"Config file not found: {config_path}")
        return p

    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    xdg_path = Path(xdg) / "ssb" / "config.yaml"
    if xdg_path.is_file():
        return xdg_path

    etc_path = Path("/etc/ssb/config.yaml")
    if etc_path.is_file():
        return etc_path

    raise ConfigError(
        "No config file found. Searched: " f"{xdg_path}, /etc/ssb/config.yaml"
    )


def load_config(config_path: str | None = None) -> Config:
    """Load and validate configuration from a YAML file."""
    path = find_config_file(config_path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError("Config file must be a YAML mapping")

    volumes = _parse_volumes(raw.get("volumes", {}))
    syncs = _parse_syncs(raw.get("syncs", {}))

    config = Config(volumes=volumes, syncs=syncs)
    _validate(config)
    return config


def _parse_volumes(
    raw_volumes: Any,
) -> dict[str, Volume]:
    """Parse the volumes section of the config."""
    if not isinstance(raw_volumes, dict):
        raise ConfigError("'volumes' must be a mapping")

    volumes: dict[str, Volume] = {}
    for name, data in raw_volumes.items():
        if not isinstance(data, dict):
            raise ConfigError(f"Volume '{name}' must be a mapping")

        vol_type = data.get("type")
        if vol_type == "local":
            path = data.get("path")
            if not path:
                raise ConfigError(f"Local volume '{name}' requires 'path'")
            volumes[name] = LocalVolume(name=name, path=path)
        elif vol_type == "remote":
            host = data.get("host")
            path = data.get("path")
            if not host or not path:
                raise ConfigError(
                    f"Remote volume '{name}' requires 'host' and 'path'"
                )
            volumes[name] = RemoteVolume(
                name=name,
                host=host,
                path=path,
                port=data.get("port", 22),
                user=data.get("user"),
                ssh_key=data.get("ssh_key"),
                ssh_options=data.get("ssh_options", []),
            )
        else:
            raise ConfigError(f"Volume '{name}' has invalid type: {vol_type}")

    return volumes


def _parse_syncs(raw_syncs: Any) -> dict[str, SyncConfig]:
    """Parse the syncs section of the config."""
    if not isinstance(raw_syncs, dict):
        raise ConfigError("'syncs' must be a mapping")

    syncs: dict[str, SyncConfig] = {}
    for name, data in raw_syncs.items():
        if not isinstance(data, dict):
            raise ConfigError(f"Sync '{name}' must be a mapping")

        source_data = data.get("source")
        dest_data = data.get("destination")
        if not isinstance(source_data, dict):
            raise ConfigError(f"Sync '{name}' requires 'source' mapping")
        if not isinstance(dest_data, dict):
            raise ConfigError(f"Sync '{name}' requires 'destination' mapping")

        source_vol = source_data.get("volume")
        if not source_vol:
            raise ConfigError(f"Sync '{name}' source requires 'volume'")
        dest_vol = dest_data.get("volume")
        if not dest_vol:
            raise ConfigError(f"Sync '{name}' destination requires 'volume'")

        syncs[name] = SyncConfig(
            name=name,
            source=SyncEndpoint(
                volume_name=source_vol,
                subdir=source_data.get("subdir"),
            ),
            destination=SyncEndpoint(
                volume_name=dest_vol,
                subdir=dest_data.get("subdir"),
            ),
            enabled=data.get("enabled", True),
            btrfs_snapshots=data.get("btrfs_snapshots", False),
        )

    return syncs


def _validate(config: Config) -> None:
    """Validate cross-references in the config."""
    for sync_name, sync in config.syncs.items():
        if sync.source.volume_name not in config.volumes:
            raise ConfigError(
                f"Sync '{sync_name}' references unknown source "
                f"volume '{sync.source.volume_name}'"
            )
        if sync.destination.volume_name not in config.volumes:
            raise ConfigError(
                f"Sync '{sync_name}' references unknown destination "
                f"volume '{sync.destination.volume_name}'"
            )
