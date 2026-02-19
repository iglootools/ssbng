from __future__ import annotations

from typing import Any, Annotated, Dict, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


def _to_kebab(name: str) -> str:
    return name.replace("_", "-")


class _BaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_kebab,
        populate_by_name=True,
    )


class LocalVolume(_BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["local"] = "local"
    """A local filesystem volume."""
    name: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)


class RsyncServer(_BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = Field(..., min_length=1)
    host: str = Field(..., min_length=1)
    port: int = Field(22, ge=1, le=65535)
    user: Optional[str] = None
    ssh_key: Optional[str] = None
    ssh_options: List[str] = Field(default_factory=list)


class RemoteVolume(_BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["remote"] = "remote"
    """A remote volume accessible via SSH."""
    name: str = Field(..., min_length=1)
    rsync_server: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)


Volume = Annotated[
    Union[LocalVolume, RemoteVolume], Field(discriminator="type")
]


class SyncEndpoint(_BaseModel):
    """A sync endpoint referencing a volume by name."""

    volume: str = Field(..., min_length=1)
    subdir: Optional[str] = None


class DestinationSyncEndpoint(SyncEndpoint):
    """A destination sync endpoint with snapshot options."""

    btrfs_snapshots: bool = False


class SyncConfig(_BaseModel):
    """Configuration for a single sync operation."""

    name: str = Field(..., min_length=1)
    source: SyncEndpoint
    destination: DestinationSyncEndpoint
    enabled: bool = True


class Config(_BaseModel):
    """Top-level SSB configuration."""

    rsync_servers: Dict[str, RsyncServer] = Field(default_factory=dict)

    @field_validator("rsync_servers", mode="before")
    @classmethod
    def inject_rsync_server_names(cls, v: Any, info: ValidationInfo) -> Any:
        return {
            name: (
                {**data, "name": name}
                if isinstance(data, dict) and "name" not in data
                else data
            )
            for name, data in v.items()
        }

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

    # The sync name is the key in the syncs dict,
    # but we also want it as a field in the SyncConfig objects.
    @field_validator("syncs", mode="before")
    @classmethod
    def inject_sync_names(cls, v: Any, info: ValidationInfo) -> Any:
        return {
            name: (
                {**data, "name": name}
                if isinstance(data, dict) and "name" not in data
                else data
            )
            for name, data in v.items()
        }

    @model_validator(mode="after")
    def validate_cross_references(self) -> Config:
        for vol_name, vol in self.volumes.items():
            match vol:
                case RemoteVolume():
                    if vol.rsync_server not in self.rsync_servers:
                        ref = vol.rsync_server
                        raise ValueError(
                            f"Volume '{vol_name}' references "
                            f"unknown rsync-server '{ref}'"
                        )
        for sync_name, sync in self.syncs.items():
            if sync.source.volume not in self.volumes:
                src = sync.source.volume
                raise ValueError(
                    f"Sync '{sync_name}' references "
                    f"unknown source volume '{src}'"
                )
            if sync.destination.volume not in self.volumes:
                dst = sync.destination.volume
                raise ValueError(
                    f"Sync '{sync_name}' references "
                    f"unknown destination volume '{dst}'"
                )
        return self
