from __future__ import annotations

from typing import Any, Annotated, Dict, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


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


class DestinationSyncEndpoint(SyncEndpoint):
    """A destination sync endpoint with snapshot options."""

    btrfs_snapshots: bool = False


class SyncConfig(BaseModel):
    """Configuration for a single sync operation."""

    name: str = Field(..., min_length=1)
    source: SyncEndpoint
    destination: DestinationSyncEndpoint
    enabled: bool = True


class Config(BaseModel):
    """Top-level SSB configuration."""

    volumes: Dict[str, Volume] = Field(default_factory=dict)

    # The volume name is the key in the volumes dict,
    # but we also want it as a field in the Volume objects.
    @field_validator("volumes", mode="before")
    @classmethod
    def inject_volume_names(cls, v: Any, info: ValidationInfo) -> Any:
        return {
            name: (
                {**data, "name": name}
                if isinstance(data, dict) and "name" not in data
                else data
            )
            for name, data in v.items()
        }

    syncs: Dict[str, SyncConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cross_references(self) -> Config:
        for sync_name, sync in self.syncs.items():
            if sync.source.volume_name not in self.volumes:
                src = sync.source.volume_name
                raise ValueError(
                    f"Sync '{sync_name}' references "
                    f"unknown source volume '{src}'"
                )
            if sync.destination.volume_name not in self.volumes:
                dst = sync.destination.volume_name
                raise ValueError(
                    f"Sync '{sync_name}' references "
                    f"unknown destination volume '{dst}'"
                )
        return self
