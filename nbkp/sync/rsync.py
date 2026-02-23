"""Rsync command building and execution."""

from __future__ import annotations

import shlex
import subprocess
from typing import Callable

from ..config import (
    Config,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
)
from ..remote import (
    build_ssh_base_args,
    build_ssh_e_option,
    format_remote_path,
)

_DEFAULT_RSYNC_OPTIONS: list[str] = [
    "-a",
    "--delete",
    "--delete-excluded",
    "--safe-links",
]


def resolve_path(
    volume: LocalVolume | RemoteVolume, subdir: str | None
) -> str:
    """Resolve the full path for a volume with optional subdir."""
    if subdir:
        return f"{volume.path}/{subdir}"
    else:
        return volume.path


def _base_rsync_args(
    sync: SyncConfig,
    dry_run: bool,
    link_dest: str | None,
    verbose: int = 0,
) -> list[str]:
    """Build common rsync flags."""
    options = (
        sync.rsync_options
        if sync.rsync_options is not None
        else _DEFAULT_RSYNC_OPTIONS
    )
    args = ["rsync"] + list(options) + list(sync.extra_rsync_options)
    if verbose > 0:
        args.append("-" + "v" * min(verbose, 3))
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


def build_rsync_command(
    sync: SyncConfig,
    config: Config,
    dry_run: bool = False,
    link_dest: str | None = None,
    verbose: int = 0,
) -> list[str]:
    """Build the rsync command for a sync operation.

    Returns the full command as a list of args, potentially
    wrapped in SSH for remote-to-remote syncs.
    """
    src_vol = config.volumes[sync.source.volume]
    dst_vol = config.volumes[sync.destination.volume]

    src_path = resolve_path(src_vol, sync.source.subdir)
    dst_path = resolve_path(dst_vol, sync.destination.subdir)

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
                verbose,
                src_proxy=config.resolve_proxy(src_server),
                dst_proxy=config.resolve_proxy(dst_server),
            )
        case (RemoteVolume() as sv, LocalVolume()):
            src_server = config.rsync_servers[sv.rsync_server]
            rsync_args = _base_rsync_args(sync, dry_run, link_dest, verbose)
            rsync_args.extend(_filter_args(sync))
            rsync_args.extend(
                build_ssh_e_option(
                    src_server,
                    config.resolve_proxy(src_server),
                )
            )
            rsync_args.append(format_remote_path(src_server, src_path) + "/")
            rsync_args.append(f"{dst_path}/latest/")
            return rsync_args
        case (LocalVolume(), RemoteVolume() as dv):
            dst_server = config.rsync_servers[dv.rsync_server]
            rsync_args = _base_rsync_args(sync, dry_run, link_dest, verbose)
            rsync_args.extend(_filter_args(sync))
            rsync_args.extend(
                build_ssh_e_option(
                    dst_server,
                    config.resolve_proxy(dst_server),
                )
            )
            rsync_args.append(f"{src_path}/")
            rsync_args.append(
                format_remote_path(dst_server, dst_path) + "/latest/"
            )
            return rsync_args
        case _:
            rsync_args = _base_rsync_args(sync, dry_run, link_dest, verbose)
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
    verbose: int = 0,
    src_proxy: RsyncServer | None = None,
    dst_proxy: RsyncServer | None = None,
) -> list[str]:
    """Build remote-to-remote rsync command (SSH into dest, rsync from src)."""
    options = (
        sync.rsync_options
        if sync.rsync_options is not None
        else _DEFAULT_RSYNC_OPTIONS
    )
    inner_rsync_parts = (
        ["rsync"] + list(options) + list(sync.extra_rsync_options)
    )
    if verbose > 0:
        inner_rsync_parts.append("-" + "v" * min(verbose, 3))
    if dry_run:
        inner_rsync_parts.append("--dry-run")
    if link_dest:
        inner_rsync_parts.append(f"--link-dest={link_dest}")
    inner_rsync_parts.extend(_filter_args(sync))

    inner_rsync_parts.extend(build_ssh_e_option(src_server, src_proxy))

    src_remote = format_remote_path(src_server, src_path)
    inner_rsync_parts.append(f"{src_remote}/")
    inner_rsync_parts.append(f"{dst_path}/latest/")

    inner_command = " ".join(shlex.quote(p) for p in inner_rsync_parts)

    return build_ssh_base_args(dst_server, dst_proxy) + [inner_command]


def run_rsync(
    sync: SyncConfig,
    config: Config,
    dry_run: bool = False,
    link_dest: str | None = None,
    verbose: int = 0,
    on_output: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Build and execute the rsync command for a sync."""
    cmd = build_rsync_command(sync, config, dry_run, link_dest, verbose)
    if on_output is None:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert proc.stdout is not None
        output_chunks: list[str] = []

        # Stream one character at a time so rsync progress
        # updates that rely on carriage returns are visible
        # immediately.
        while True:
            ch = proc.stdout.read(1)
            if ch:
                output_chunks.append(ch)
                on_output(ch)
            elif proc.poll() is not None:
                break

        return subprocess.CompletedProcess(
            cmd,
            proc.wait(),
            stdout="".join(output_chunks),
            stderr="",
        )
