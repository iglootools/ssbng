"""Configuration types and loading."""

from .loader import ConfigError, find_config_file, load_config
from .protocol import (
    BtrfsSnapshotConfig,
    Config,
    DestinationSyncEndpoint,
    EndpointFilter,
    HardLinkSnapshotConfig,
    LocalVolume,
    RemoteVolume,
    SshEndpoint,
    Slug,
    SshConnectionOptions,
    SyncConfig,
    SyncEndpoint,
    Volume,
)
from .resolution import (
    ResolvedEndpoint,
    ResolvedEndpoints,
    resolve_all_endpoints,
)

__all__ = [
    "BtrfsSnapshotConfig",
    "Config",
    "ConfigError",
    "DestinationSyncEndpoint",
    "EndpointFilter",
    "HardLinkSnapshotConfig",
    "LocalVolume",
    "RemoteVolume",
    "ResolvedEndpoint",
    "ResolvedEndpoints",
    "SshEndpoint",
    "Slug",
    "SshConnectionOptions",
    "SyncConfig",
    "SyncEndpoint",
    "Volume",
    "find_config_file",
    "load_config",
    "resolve_all_endpoints",
]
