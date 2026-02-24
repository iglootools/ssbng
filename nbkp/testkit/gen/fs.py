"""Seed filesystem helpers: markers and sample data."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...config import (
    Config,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
)

_CHUNK_SIZE = 1024 * 1024  # 1 MB

_SAMPLE_FILES = [
    ("sample.txt", "Sample data for backup testing\n"),
    ("photo.jpg", "fake jpeg data\n"),
    ("document.pdf", "fake pdf data\n"),
]


def _write_zeroed_file(path: Path, size_bytes: int) -> None:
    """Write a zeroed file in chunks to avoid large allocs."""
    chunk = b"\x00" * min(_CHUNK_SIZE, size_bytes)
    with path.open("wb") as f:
        remaining = size_bytes
        while remaining > 0:
            f.write(chunk[:remaining])
            remaining -= len(chunk)


def create_seed_markers(
    config: Config,
    remote_exec: Callable[[str], None] | None = None,
) -> None:
    """Create volume, source, and destination markers.

    For local volumes, creates directories and marker files
    directly.  For remote volumes, uses *remote_exec(command)*
    to run shell commands on the remote host.
    """
    # Volume markers (.nbkp-vol)
    for vol in config.volumes.values():
        match vol:
            case LocalVolume():
                vol_path = Path(vol.path)
                vol_path.mkdir(parents=True, exist_ok=True)
                (vol_path / ".nbkp-vol").touch()
            case RemoteVolume():
                if remote_exec is not None:
                    remote_exec(f"mkdir -p {vol.path}")
                    remote_exec(f"touch {vol.path}/.nbkp-vol")

    # Sync endpoint markers
    for sync in config.syncs.values():
        _create_source_markers(config, sync, remote_exec)
        _create_dest_markers(config, sync, remote_exec)


def _create_source_markers(
    config: Config,
    sync: SyncConfig,
    remote_exec: Callable[[str], None] | None,
) -> None:
    vol = config.volumes[sync.source.volume]
    subdir = sync.source.subdir

    match vol:
        case LocalVolume():
            path = Path(vol.path)
            if subdir:
                path = path / subdir
            path.mkdir(parents=True, exist_ok=True)
            (path / ".nbkp-src").touch()
        case RemoteVolume():
            if remote_exec is not None:
                rp = vol.path
                if subdir:
                    rp = f"{rp}/{subdir}"
                remote_exec(f"mkdir -p {rp}")
                remote_exec(f"touch {rp}/.nbkp-src")


def _create_dest_markers(
    config: Config,
    sync: SyncConfig,
    remote_exec: Callable[[str], None] | None,
) -> None:
    vol = config.volumes[sync.destination.volume]
    subdir = sync.destination.subdir
    btrfs = sync.destination.btrfs_snapshots
    hard_link = sync.destination.hard_link_snapshots

    match vol:
        case LocalVolume():
            path = Path(vol.path)
            if subdir:
                path = path / subdir
            path.mkdir(parents=True, exist_ok=True)
            (path / ".nbkp-dst").touch()
            if hard_link.enabled:
                (path / "snapshots").mkdir(exist_ok=True)
            else:
                (path / "latest").mkdir(exist_ok=True)
                if btrfs.enabled:
                    (path / "snapshots").mkdir(exist_ok=True)
        case RemoteVolume():
            if remote_exec is not None:
                rp = vol.path
                if subdir:
                    rp = f"{rp}/{subdir}"
                remote_exec(f"mkdir -p {rp}")
                remote_exec(f"touch {rp}/.nbkp-dst")
                if hard_link.enabled:
                    remote_exec(f"mkdir -p {rp}/snapshots")
                elif btrfs.enabled:
                    remote_exec("btrfs subvolume create" f" {rp}/latest")
                    remote_exec(f"mkdir -p {rp}/snapshots")
                else:
                    remote_exec(f"mkdir -p {rp}/latest")


def create_seed_data(
    config: Config,
    big_file_size_mb: int = 0,
) -> None:
    """Generate sample files in local source volumes.

    Creates a handful of small files in each unique source
    path.  When *big_file_size_mb* > 0, an additional large
    zeroed file is written to slow down syncs for manual
    testing.
    """
    size_bytes = big_file_size_mb * 1024 * 1024
    seen: set[str] = set()

    for sync in config.syncs.values():
        vol = config.volumes[sync.source.volume]
        if not isinstance(vol, LocalVolume):
            continue
        base = Path(vol.path)
        path = base / sync.source.subdir if sync.source.subdir else base
        key = str(path)
        if key in seen:
            continue
        seen.add(key)

        path.mkdir(parents=True, exist_ok=True)
        for name, content in _SAMPLE_FILES:
            (path / name).write_text(content)
        if big_file_size_mb:
            _write_zeroed_file(path / "large-file.bin", size_bytes)
