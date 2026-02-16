"""Data model for SSB backup configuration and status."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LocalVolume:
    """A local filesystem volume."""

    name: str
    path: str


@dataclass(frozen=True)
class RemoteVolume:
    """A remote volume accessible via SSH."""

    name: str
    host: str
    path: str
    port: int = 22
    user: str | None = None
    ssh_key: str | None = None
    ssh_options: list[str] = field(default_factory=list)


Volume = LocalVolume | RemoteVolume


@dataclass(frozen=True)
class SyncEndpoint:
    """A sync endpoint referencing a volume by name."""

    volume_name: str
    subdir: str | None = None


@dataclass(frozen=True)
class SyncConfig:
    """Configuration for a single sync operation."""

    name: str
    source: SyncEndpoint
    destination: SyncEndpoint
    enabled: bool = True
    btrfs_snapshots: bool = False


@dataclass(frozen=True)
class Config:
    """Top-level SSB configuration."""

    volumes: dict[str, Volume] = field(default_factory=dict)
    syncs: dict[str, SyncConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class VolumeStatus:
    """Runtime status of a volume."""

    name: str
    config: Volume
    active: bool
    reason: str


@dataclass(frozen=True)
class SyncStatus:
    """Runtime status of a sync."""

    name: str
    config: SyncConfig
    source_status: VolumeStatus
    destination_status: VolumeStatus
    active: bool
    reason: str


@dataclass(frozen=True)
class SyncResult:
    """Result of running a sync."""

    sync_name: str
    success: bool
    dry_run: bool
    rsync_exit_code: int
    output: str
    snapshot_path: str | None = None
    error: str | None = None


class OutputFormat(enum.Enum):
    """Output format for CLI commands."""

    HUMAN = "human"
    JSON = "json"
