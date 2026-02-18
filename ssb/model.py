from __future__ import annotations
from pydantic import root_validator
from typing import Annotated, Optional, List, Dict, Union, Literal
from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    model_validator,
    field_validator,
)
import enum


class LocalVolume(BaseModel):
    model_config = {"frozen": True}
    type: Literal["local"] = "local"
    """A local filesystem volume."""
    name: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)


class RemoteVolume(BaseModel):
    model_config = {"frozen": True}
    type: Literal["remote"] = "remote"
    """A remote volume accessible via SSH."""
    name: str = Field(..., min_length=1)
    host: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    port: int = Field(22, ge=1, le=65535)
    user: Optional[str] = None
    ssh_key: Optional[str] = None
    ssh_options: List[str] = Field(default_factory=list)


Volume = Annotated[
    Union[LocalVolume, RemoteVolume], Field(discriminator="type")
]


class SyncEndpoint(BaseModel):
    """A sync endpoint referencing a volume by name."""

    volume_name: str = Field(..., min_length=1)
    subdir: Optional[str] = None


class SyncConfig(BaseModel):
    """Configuration for a single sync operation."""

    name: str = Field(..., min_length=1)
    source: SyncEndpoint
    destination: SyncEndpoint
    enabled: bool = True
    btrfs_snapshots: bool = False


class Config(BaseModel):
    """Top-level SSB configuration."""

    volumes: Dict[str, Volume] = Field(default_factory=dict)

    # The volume name is the key in the volumes dict, but we also want it as a field in the Volume objects to make pydantic happy
    @field_validator("volumes", mode="before")
    @classmethod
    def inject_volume_names(cls, v, info: ValidationInfo):
        result = {}
        for volume_name, volume_data in v.items():
            # Inject the name if not present
            if "name" not in volume_data:
                volume_data = dict(volume_data)
                volume_data["name"] = volume_name
            result[volume_name] = volume_data
        return result

    syncs: Dict[str, SyncConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cross_references(self):
        for sync_name, sync in self.syncs.items():
            if sync.source.volume_name not in self.volumes:
                raise ValueError(
                    f"Sync '{sync_name}' references unknown source volume '{sync.source.volume_name}'"
                )
            if sync.destination.volume_name not in self.volumes:
                raise ValueError(
                    f"Sync '{sync_name}' references unknown destination volume '{sync.destination.volume_name}'"
                )
        return self


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


class OutputFormat(str, enum.Enum):
    """Output format for CLI commands."""

    HUMAN = "human"
    JSON = "json"
