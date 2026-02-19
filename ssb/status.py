"""Runtime status types for volumes and syncs."""

from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel, computed_field

from .config import SyncConfig, Volume


class VolumeReason(str, enum.Enum):
    MARKER_NOT_FOUND = "marker not found"
    UNREACHABLE = "unreachable"


class SyncReason(str, enum.Enum):
    DISABLED = "disabled"
    SOURCE_UNAVAILABLE = "source unavailable"
    DESTINATION_UNAVAILABLE = "destination unavailable"
    SOURCE_MARKER_NOT_FOUND = "source marker .ssb-src not found"
    DESTINATION_MARKER_NOT_FOUND = "destination marker .ssb-dst not found"
    RSYNC_NOT_FOUND_ON_SOURCE = "rsync not found on source"
    RSYNC_NOT_FOUND_ON_DESTINATION = "rsync not found on destination"
    BTRFS_NOT_FOUND_ON_DESTINATION = "btrfs not found on destination"


class VolumeStatus(BaseModel):
    """Runtime status of a volume."""

    name: str
    config: Volume
    reasons: list[VolumeReason]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def active(self) -> bool:
        return len(self.reasons) == 0


class SyncStatus(BaseModel):
    """Runtime status of a sync."""

    name: str
    config: SyncConfig
    source_status: VolumeStatus
    destination_status: VolumeStatus
    reasons: list[SyncReason]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def active(self) -> bool:
        return len(self.reasons) == 0


class SyncResult(BaseModel):
    """Result of running a sync."""

    sync_name: str
    success: bool
    dry_run: bool
    rsync_exit_code: int
    output: str
    snapshot_path: Optional[str] = None
    error: Optional[str] = None
