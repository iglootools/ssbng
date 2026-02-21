"""SSH command building and remote command execution helpers."""

from __future__ import annotations

import shlex
import subprocess

from .config import RsyncServer


def build_ssh_base_args(server: RsyncServer) -> list[str]:
    """Build base SSH command args for a remote volume.

    Returns args like:
        ssh -o ConnectTimeout=10 -o BatchMode=yes [opts] host
    """
    args = [
        "ssh",
        "-o",
        f"ConnectTimeout={server.connect_timeout}",
        "-o",
        "BatchMode=yes",
    ]
    if server.port != 22:
        args.extend(["-p", str(server.port)])
    if server.ssh_key:
        args.extend(["-i", server.ssh_key])
    for opt in server.ssh_options:
        args.extend(["-o", opt])

    host = f"{server.user}@{server.host}" if server.user else server.host
    args.append(host)
    return args


def run_remote_command(
    server: RsyncServer, command: list[str]
) -> subprocess.CompletedProcess[str]:
    """Run a command on a remote host via SSH."""
    cmd_string = " ".join(shlex.quote(arg) for arg in command)
    args = build_ssh_base_args(server) + [cmd_string]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
    )


def build_ssh_e_option(server: RsyncServer) -> list[str]:
    """Build rsync's -e option for SSH with custom port/key.

    Returns a list like: ["-e", "ssh -p 5022 -i ~/.ssh/key"]
    """
    ssh_cmd_parts = ["ssh"]
    if server.port != 22:
        ssh_cmd_parts.extend(["-p", str(server.port)])
    if server.ssh_key:
        ssh_cmd_parts.extend(["-i", server.ssh_key])
    for opt in server.ssh_options:
        ssh_cmd_parts.extend(["-o", opt])

    return ["-e", " ".join(ssh_cmd_parts)]


def format_remote_path(server: RsyncServer, path: str) -> str:
    """Format a remote path as [user@]host:path."""
    host = f"{server.user}@{server.host}" if server.user else server.host
    return f"{host}:{path}"
