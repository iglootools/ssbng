"""Rsync command building and execution."""

from __future__ import annotations

import subprocess

from .config import (
    Config,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
)
from .ssh import (
    build_ssh_base_args,
    build_ssh_e_option,
    format_remote_path,
)


def _resolve_path(
    volume: LocalVolume | RemoteVolume, subdir: str | None
) -> str:
    """Resolve the full path for a volume with optional subdir."""
    if subdir:
        return f"{volume.path}/{subdir}"
    return volume.path


def _base_rsync_args(dry_run: bool, link_dest: str | None) -> list[str]:
    """Build common rsync flags."""
    args = ["rsync", "-av", "--delete"]
    if dry_run:
        args.append("--dry-run")
    if link_dest:
        args.append(f"--link-dest={link_dest}")
    return args


def _filter_args(sync: SyncConfig) -> list[str]:
    """Build rsync --filter arguments."""
    args: list[str] = []
    for rule in sync.filters:
        args.append(f"--filter={rule}")
    if sync.filter_file:
        args.append(f"--filter=merge {sync.filter_file}")
    return args


def _filter_args_inner(sync: SyncConfig) -> list[str]:
    """Build quoted --filter args for remote-to-remote inner command."""
    args: list[str] = []
    for rule in sync.filters:
        args.append(f"--filter='{rule}'")
    if sync.filter_file:
        args.append(f"--filter='merge {sync.filter_file}'")
    return args


def build_rsync_command(
    sync: SyncConfig,
    config: Config,
    dry_run: bool = False,
    link_dest: str | None = None,
) -> list[str]:
    """Build the rsync command for a sync operation.

    Returns the full command as a list of args, potentially
    wrapped in SSH for remote-to-remote syncs.
    """
    src_vol = config.volumes[sync.source.volume]
    dst_vol = config.volumes[sync.destination.volume]

    src_path = _resolve_path(src_vol, sync.source.subdir)
    dst_path = _resolve_path(dst_vol, sync.destination.subdir)

    match (src_vol, dst_vol):
        case (RemoteVolume() as sv, RemoteVolume() as dv):
            src_server = config.rsync_servers[sv.rsync_server]
            dst_server = config.rsync_servers[dv.rsync_server]
            return _build_remote_to_remote(
                sync,
                src_server,
                dst_server,
                src_path,
                dst_path,
                dry_run,
                link_dest,
            )
        case (RemoteVolume() as sv, LocalVolume()):
            src_server = config.rsync_servers[sv.rsync_server]
            rsync_args = _base_rsync_args(dry_run, link_dest)
            rsync_args.extend(_filter_args(sync))
            rsync_args.extend(build_ssh_e_option(src_server))
            rsync_args.append(format_remote_path(src_server, src_path) + "/")
            rsync_args.append(f"{dst_path}/latest/")
            return rsync_args
        case (LocalVolume(), RemoteVolume() as dv):
            dst_server = config.rsync_servers[dv.rsync_server]
            rsync_args = _base_rsync_args(dry_run, link_dest)
            rsync_args.extend(_filter_args(sync))
            rsync_args.extend(build_ssh_e_option(dst_server))
            rsync_args.append(f"{src_path}/")
            rsync_args.append(
                format_remote_path(dst_server, dst_path) + "/latest/"
            )
            return rsync_args
        case _:
            rsync_args = _base_rsync_args(dry_run, link_dest)
            rsync_args.extend(_filter_args(sync))
            rsync_args.append(f"{src_path}/")
            rsync_args.append(f"{dst_path}/latest/")
            return rsync_args


def _build_remote_to_remote(
    sync: SyncConfig,
    src_server: RsyncServer,
    dst_server: RsyncServer,
    src_path: str,
    dst_path: str,
    dry_run: bool,
    link_dest: str | None,
) -> list[str]:
    """Build remote-to-remote rsync command (SSH into dest, rsync from src)."""
    inner_rsync_parts = ["rsync", "-av", "--delete"]
    if dry_run:
        inner_rsync_parts.append("--dry-run")
    if link_dest:
        inner_rsync_parts.append(f"--link-dest={link_dest}")
    inner_rsync_parts.extend(_filter_args_inner(sync))

    # SSH options for source host (from destination's perspective)
    src_ssh_parts = ["ssh"]
    if src_server.port != 22:
        src_ssh_parts.extend(["-p", str(src_server.port)])
    if src_server.ssh_key:
        src_ssh_parts.extend(["-i", src_server.ssh_key])

    if len(src_ssh_parts) > 1:
        inner_rsync_parts.extend(["-e", "'" + " ".join(src_ssh_parts) + "'"])

    src_remote = format_remote_path(src_server, src_path)
    inner_rsync_parts.append(f"{src_remote}/")
    inner_rsync_parts.append(f"{dst_path}/latest/")

    inner_command = " ".join(inner_rsync_parts)

    return build_ssh_base_args(dst_server) + [inner_command]


def run_rsync(
    sync: SyncConfig,
    config: Config,
    dry_run: bool = False,
    link_dest: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Build and execute the rsync command for a sync."""
    cmd = build_rsync_command(sync, config, dry_run, link_dest)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
