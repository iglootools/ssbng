"""Docker helpers for the developer test CLI seed command."""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import docker as dockerlib
import typer

from ..config import RsyncServer
from ..remote.fabricssh import run_remote_command

DOCKER_DIR = Path(__file__).resolve().parent / "dockerbuild"
CONTAINER_NAME = "nbkp-seed"
_IMAGE_TAG = "nbkp-seed-server:latest"


def check_docker() -> None:
    """Verify Docker daemon is reachable."""
    try:
        client = dockerlib.from_env()
        client.ping()
    except dockerlib.errors.DockerException as exc:
        typer.echo(
            f"Error: Docker is not available: {exc}",
            err=True,
        )
        raise typer.Exit(1)


def generate_ssh_keypair(
    seed_dir: Path,
) -> tuple[Path, Path]:
    """Generate Ed25519 SSH key pair in seed_dir/ssh/."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    ssh_dir = seed_dir / "ssh"
    ssh_dir.mkdir()
    private_key_path = ssh_dir / "id_ed25519"
    public_key_path = ssh_dir / "id_ed25519.pub"

    key = Ed25519PrivateKey.generate()
    private_key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        )
    )
    private_key_path.chmod(0o600)
    pub_bytes = key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    )
    public_key_path.write_text(f"{pub_bytes.decode()} nbkp-seed\n")

    return private_key_path, public_key_path


def start_docker_container(pub_key: Path) -> int:
    """Build image, destroy old container, start new. Return SSH port."""
    client = dockerlib.from_env()

    # Build image
    try:
        image, _ = client.images.build(
            path=str(DOCKER_DIR),
            tag=_IMAGE_TAG,
            nocache=True,
        )
    except dockerlib.errors.BuildError as exc:
        typer.echo(
            f"Error: Docker image build failed: {exc}",
            err=True,
        )
        raise typer.Exit(1)

    # Remove existing container if any
    try:
        old = client.containers.get(CONTAINER_NAME)
        old.remove(force=True)
    except dockerlib.errors.NotFound:
        pass

    # Start container
    container = client.containers.run(
        image,
        detach=True,
        name=CONTAINER_NAME,
        privileged=True,
        ports={"22/tcp": None},
        volumes={
            str(pub_key): {
                "bind": "/tmp/authorized_keys",
                "mode": "ro",
            }
        },
    )

    # Get mapped port
    container.reload()
    port_info = container.attrs["NetworkSettings"]["Ports"]["22/tcp"]
    return int(port_info[0]["HostPort"])


def wait_for_ssh(
    server: RsyncServer,
    timeout: int = 30,
) -> None:
    """Poll SSH until the daemon sends its banner."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(
                (server.host, server.port), timeout=2
            ) as sock:
                data = sock.recv(256)
                if data.startswith(b"SSH-"):
                    return
        except OSError:
            pass
        time.sleep(1)
    raise TimeoutError(
        f"SSH not ready after {timeout}s"
    )


def ssh_exec(
    server: RsyncServer,
    command: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command on the container via SSH."""
    result = run_remote_command(server, ["sh", "-c", command])
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            result.stdout,
            result.stderr,
        )
    return result


def setup_remote(server: RsyncServer) -> None:
    """Create markers and btrfs subvolumes on container."""

    def run(cmd: str) -> None:
        ssh_exec(server, cmd)

    run("touch /data/.nbkp-vol /data/.nbkp-dst")
    run("btrfs subvolume create /mnt/btrfs/latest")
    run("mkdir -p /mnt/btrfs/snapshots")
    run("touch /mnt/btrfs/.nbkp-vol" " /mnt/btrfs/.nbkp-dst")
