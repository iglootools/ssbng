"""YAML configuration loading, parsing, and validation."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .config import Config


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

    try:
        config = Config.model_validate(raw)
    except Exception as e:
        raise ConfigError("Config validation error") from e
    return config
