"""SSH command building and remote command execution helpers."""

from __future__ import annotations

import shlex
import subprocess

from ..config import RsyncServer, SshOptions


def _ssh_o_options(opts: SshOptions) -> list[str]:
    """Derive SSH -o option values from structured options."""
    result = [
        f"ConnectTimeout={opts.connect_timeout}",
        "BatchMode=yes",
    ]
    if opts.compress:
        result.append("Compression=yes")
    if opts.server_alive_interval is not None:
        result.append(f"ServerAliveInterval=" f"{opts.server_alive_interval}")
    if not opts.strict_host_key_checking:
        result.append("StrictHostKeyChecking=no")
    if opts.known_hosts_file is not None:
        result.append(f"UserKnownHostsFile={opts.known_hosts_file}")
    if opts.forward_agent:
        result.append("ForwardAgent=yes")
    return result


def _format_proxy_jump(proxy: RsyncServer) -> str:
    """Format proxy server as [user@]host[:port] for SSH -J."""
    host = f"{proxy.user}@{proxy.host}" if proxy.user else proxy.host
    if proxy.port != 22:
        host += f":{proxy.port}"
    return host


def build_ssh_base_args(
    server: RsyncServer,
    proxy_server: RsyncServer | None = None,
) -> list[str]:
    """Build base SSH command args for a remote volume.

    Returns args like:
        ssh -o ConnectTimeout=10 -o BatchMode=yes [opts] host
    """
    args = ["ssh"]
    for opt in _ssh_o_options(server.ssh_options):
        args.extend(["-o", opt])
    if server.port != 22:
        args.extend(["-p", str(server.port)])
    if server.ssh_key:
        args.extend(["-i", server.ssh_key])
    if proxy_server is not None:
        args.extend(["-J", _format_proxy_jump(proxy_server)])

    host = f"{server.user}@{server.host}" if server.user else server.host
    args.append(host)
    return args


def run_remote_command(
    server: RsyncServer,
    command: list[str],
    proxy_server: RsyncServer | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command on a remote host via SSH."""
    cmd_string = " ".join(shlex.quote(arg) for arg in command)
    args = build_ssh_base_args(server, proxy_server) + [cmd_string]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
    )


def build_ssh_e_option(
    server: RsyncServer,
    proxy_server: RsyncServer | None = None,
) -> list[str]:
    """Build rsync's -e option for SSH with custom port/key.

    Returns a list like:
        ["-e", "ssh -o ConnectTimeout=10 -o BatchMode=yes ..."]
    """
    ssh_cmd_parts = ["ssh"]
    for opt in _ssh_o_options(server.ssh_options):
        ssh_cmd_parts.extend(["-o", opt])
    if server.port != 22:
        ssh_cmd_parts.extend(["-p", str(server.port)])
    if server.ssh_key:
        ssh_cmd_parts.extend(["-i", server.ssh_key])
    if proxy_server is not None:
        ssh_cmd_parts.extend(["-J", _format_proxy_jump(proxy_server)])

    return ["-e", " ".join(ssh_cmd_parts)]


def format_remote_path(server: RsyncServer, path: str) -> str:
    """Format a remote path as [user@]host:path."""
    host = f"{server.user}@{server.host}" if server.user else server.host
    return f"{host}:{path}"
