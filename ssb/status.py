"""Runtime status types for volumes and syncs."""

from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel

from .config import SyncConfig, Volume


class VolumeReason(str, enum.Enum):
    OK = "ok"
    MARKER_NOT_FOUND = "marker not found"
    UNREACHABLE = "unreachable"


class SyncReason(str, enum.Enum):
    OK = "ok"
    DISABLED = "disabled"
    SOURCE_UNAVAILABLE = "source unavailable"
    DESTINATION_UNAVAILABLE = "destination unavailable"
    SOURCE_MARKER_NOT_FOUND = "source marker .ssb-src not found"
    DESTINATION_MARKER_NOT_FOUND = "destination marker .ssb-dst not found"


class VolumeStatus(BaseModel):
    """Runtime status of a volume."""

    name: str
    config: Volume
    active: bool
    reason: VolumeReason


class SyncStatus(BaseModel):
    """Runtime status of a sync."""

    name: str
    config: SyncConfig
    source_status: VolumeStatus
    destination_status: VolumeStatus
    active: bool
    reason: SyncReason


class SyncResult(BaseModel):
    """Result of running a sync."""

    sync_name: str
    success: bool
    dry_run: bool
    rsync_exit_code: int
    output: str
    snapshot_path: Optional[str] = None
    error: Optional[str] = None
