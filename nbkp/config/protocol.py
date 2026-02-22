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


class SshOptions(_BaseModel):
    """SSH connection options.

    These fields map to parameters across three layers:
    - SSH client: ssh(1) -o options
    - Paramiko: SSHClient.connect() kwargs
      https://docs.paramiko.org/en/stable/api/client.html
    - Fabric: Connection() constructor
      https://docs.fabfile.org/en/stable/api/connection.html
    """

    model_config = ConfigDict(frozen=True)

    # Connection
    # SSH: ConnectTimeout | Paramiko: timeout | Fabric: connect_timeout
    connect_timeout: int = Field(default=10, ge=1)
    # SSH: Compression | Paramiko: compress
    compress: bool = False
    # SSH: ServerAliveInterval | Paramiko: transport.set_keepalive()
    server_alive_interval: Optional[int] = Field(default=None, ge=1)

    # Authentication
    # Paramiko: allow_agent — use SSH agent for key lookup
    allow_agent: bool = True
    # Paramiko: look_for_keys — search ~/.ssh/ for keys
    look_for_keys: bool = True

    # Timeouts
    # Paramiko: banner_timeout — wait for SSH banner
    banner_timeout: Optional[float] = Field(default=None, ge=0)
    # Paramiko: auth_timeout — wait for auth response
    auth_timeout: Optional[float] = Field(default=None, ge=0)
    # Paramiko: channel_timeout — wait for channel open
    channel_timeout: Optional[float] = Field(default=None, ge=0)

    # Host key verification
    # SSH: StrictHostKeyChecking
    # Paramiko: SSHClient.set_missing_host_key_policy()
    strict_host_key_checking: bool = True
    # SSH: UserKnownHostsFile
    # Paramiko: SSHClient.load_host_keys()
    known_hosts_file: Optional[str] = None

    # Forwarding
    # SSH: ForwardAgent | Fabric: forward_agent
    forward_agent: bool = False

    # Algorithm restrictions
    # Paramiko: disabled_algorithms — disable specific algorithms
    # (Paramiko/Fabric only — no SSH CLI equivalent)
    disabled_algorithms: Optional[Dict[str, List[str]]] = None


class RsyncServer(_BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: Slug
    host: str = Field(..., min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    user: Optional[str] = None
    ssh_key: Optional[str] = None
    ssh_options: SshOptions = Field(default_factory=lambda: SshOptions())
    proxy_jump: Optional[str] = None


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
    """Top-level NBKP configuration."""

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

    def resolve_proxy(self, server: RsyncServer) -> RsyncServer | None:
        """Resolve the proxy-jump server, if any."""
        if server.proxy_jump is not None:
            return self.rsync_servers[server.proxy_jump]
        return None

    @model_validator(mode="after")
    def validate_cross_references(self) -> Config:
        for slug, server in self.rsync_servers.items():
            if server.proxy_jump is not None:
                if server.proxy_jump not in self.rsync_servers:
                    raise ValueError(
                        f"Server '{slug}' references "
                        f"unknown proxy-jump server "
                        f"'{server.proxy_jump}'"
                    )
                visited: set[str] = {slug}
                current: str | None = server.proxy_jump
                while current is not None:
                    if current in visited:
                        raise ValueError(
                            f"Circular proxy-jump chain "
                            f"detected starting from "
                            f"server '{slug}'"
                        )
                    visited.add(current)
                    current = self.rsync_servers[current].proxy_jump

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
