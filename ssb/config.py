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


Slug = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
    ),
]


class LocalVolume(_BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["local"] = "local"
    """A local filesystem volume."""
    slug: Slug
    path: str = Field(..., min_length=1)


class RsyncServer(_BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: Slug
    host: str = Field(..., min_length=1)
    port: int = Field(22, ge=1, le=65535)
    user: Optional[str] = None
    ssh_key: Optional[str] = None
    ssh_options: List[str] = Field(default_factory=list)
    connect_timeout: int = Field(10, ge=1)


class RemoteVolume(_BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["remote"] = "remote"
    """A remote volume accessible via SSH."""
    slug: Slug
    rsync_server: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)


Volume = Annotated[
    Union[LocalVolume, RemoteVolume], Field(discriminator="type")
]


class SyncEndpoint(_BaseModel):
    """A sync endpoint referencing a volume by slug."""

    volume: str = Field(..., min_length=1)
    subdir: Optional[str] = None


class BtrfsSnapshotConfig(_BaseModel):
    """Configuration for btrfs snapshot management."""

    model_config = ConfigDict(frozen=True)
    enabled: bool = False
    max_snapshots: Optional[int] = Field(default=None, ge=1)


class DestinationSyncEndpoint(SyncEndpoint):
    """A destination sync endpoint with snapshot options."""

    btrfs_snapshots: BtrfsSnapshotConfig = Field(
        default_factory=lambda: BtrfsSnapshotConfig()
    )


class SyncConfig(_BaseModel):
    """Configuration for a single sync operation."""

    slug: Slug
    source: SyncEndpoint
    destination: DestinationSyncEndpoint
    enabled: bool = True
    rsync_options: Optional[List[str]] = None
    extra_rsync_options: List[str] = Field(default_factory=list)
    filters: List[str] = Field(default_factory=list)
    filter_file: Optional[str] = None

    @field_validator("filters", mode="before")
    @classmethod
    def normalize_filters(cls, v: Any) -> list[str]:
        result: list[str] = []
        for item in v:
            match item:
                case str():
                    result.append(item)
                case {"include": str() as pattern}:
                    result.append(f"+ {pattern}")
                case {"exclude": str() as pattern}:
                    result.append(f"- {pattern}")
                case _:
                    raise ValueError(
                        f"Filter must be a string or a dict"
                        f" with 'include'/'exclude' key,"
                        f" got: {item!r}"
                    )
        return result


class Config(_BaseModel):
    """Top-level SSB configuration."""

    rsync_servers: Dict[str, RsyncServer] = Field(default_factory=dict)

    @field_validator("rsync_servers", mode="before")
    @classmethod
    def inject_rsync_server_slugs(cls, v: Any, info: ValidationInfo) -> Any:
        return {
            slug: (
                {**data, "slug": slug}
                if isinstance(data, dict) and "slug" not in data
                else data
            )
            for slug, data in v.items()
        }

    volumes: Dict[str, Volume] = Field(default_factory=dict)

    # The volume slug is the key in the volumes dict,
    # but we also want it as a field in the Volume objects.
    @field_validator("volumes", mode="before")
    @classmethod
    def inject_volume_slugs(cls, v: Any, info: ValidationInfo) -> Any:
        return {
            slug: (
                {**data, "slug": slug}
                if isinstance(data, dict) and "slug" not in data
                else data
            )
            for slug, data in v.items()
        }

    syncs: Dict[str, SyncConfig] = Field(default_factory=dict)

    # The sync slug is the key in the syncs dict,
    # but we also want it as a field in the SyncConfig objects.
    @field_validator("syncs", mode="before")
    @classmethod
    def inject_sync_slugs(cls, v: Any, info: ValidationInfo) -> Any:
        return {
            slug: (
                {**data, "slug": slug}
                if isinstance(data, dict) and "slug" not in data
                else data
            )
            for slug, data in v.items()
        }

    @model_validator(mode="after")
    def validate_cross_references(self) -> Config:
        for vol_slug, vol in self.volumes.items():
            match vol:
                case RemoteVolume():
                    if vol.rsync_server not in self.rsync_servers:
                        ref = vol.rsync_server
                        raise ValueError(
                            f"Volume '{vol_slug}' references "
                            f"unknown rsync-server '{ref}'"
                        )
        for sync_slug, sync in self.syncs.items():
            if sync.source.volume not in self.volumes:
                src = sync.source.volume
                raise ValueError(
                    f"Sync '{sync_slug}' references "
                    f"unknown source volume '{src}'"
                )
            if sync.destination.volume not in self.volumes:
                dst = sync.destination.volume
                raise ValueError(
                    f"Sync '{sync_slug}' references "
                    f"unknown destination volume '{dst}'"
                )
        return self
