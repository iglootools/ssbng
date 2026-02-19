"""SSH command building and remote command execution helpers."""

from __future__ import annotations

import subprocess

from .config import RemoteVolume


def build_ssh_base_args(volume: RemoteVolume) -> list[str]:
    """Build base SSH command args for a remote volume.

    Returns args like:
        ssh -o ConnectTimeout=10 -o BatchMode=yes [opts] host
    """
    args = [
        "ssh",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
    ]
    if volume.port != 22:
        args.extend(["-p", str(volume.port)])
    if volume.ssh_key:
        args.extend(["-i", volume.ssh_key])
    for opt in volume.ssh_options:
        args.extend(["-o", opt])

    host = f"{volume.user}@{volume.host}" if volume.user else volume.host
    args.append(host)
    return args


def run_remote_command(
    volume: RemoteVolume, command: str
) -> subprocess.CompletedProcess[str]:
    """Run a shell command on a remote host via SSH."""
    args = build_ssh_base_args(volume) + [command]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
    )


def build_ssh_e_option(volume: RemoteVolume) -> list[str]:
    """Build rsync's -e option for SSH with custom port/key.

    Returns a list like: ["-e", "ssh -p 5022 -i ~/.ssh/key"]
    """
    ssh_cmd_parts = ["ssh"]
    if volume.port != 22:
        ssh_cmd_parts.extend(["-p", str(volume.port)])
    if volume.ssh_key:
        ssh_cmd_parts.extend(["-i", volume.ssh_key])
    for opt in volume.ssh_options:
        ssh_cmd_parts.extend(["-o", opt])

    return ["-e", " ".join(ssh_cmd_parts)]


def format_remote_path(volume: RemoteVolume, path: str) -> str:
    """Format a remote path as [user@]host:path."""
    host = f"{volume.user}@{volume.host}" if volume.user else volume.host
    return f"{host}:{path}"
