"""Integration test fixtures -- Docker SSH server with rsync + btrfs."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Generator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from nbkp.config import RemoteVolume, RsyncServer, SshOptions

DOCKER_DIR = Path(__file__).parent / "docker"


def _docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker not available"
)


@pytest.fixture(scope="session")
def ssh_key_pair() -> Generator[tuple[Path, Path], None, None]:
    """Generate an ephemeral ed25519 SSH key pair for tests.

    Ed25519: fast generation, small keys, no parameter choices
    to get wrong — ideal for throwaway test keys.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="nbkp-test-ssh-"))
    private_key = tmpdir / "id_ed25519"
    public_key = tmpdir / "id_ed25519.pub"

    # ssh-keygen -t ed25519 -f <private_key> -N "" -C nbkp-integration-test
    key = Ed25519PrivateKey.generate()
    private_key.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        )
    )
    private_key.chmod(0o600)
    pub_bytes = key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    )
    public_key.write_text(f"{pub_bytes.decode()} nbkp-integration-test\n")

    yield private_key, public_key

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def docker_container(
    ssh_key_pair: tuple[Path, Path],
) -> Generator[dict[str, Any], None, None]:
    """Start Docker container and yield connection info.

    Yields a dict with keys: host, port, user, private_key.
    """
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.image import DockerImage
    from testcontainers.core.wait_strategies import (
        LogMessageWaitStrategy,
    )

    private_key, public_key = ssh_key_pair

    image = DockerImage(
        path=str(DOCKER_DIR),
        tag="nbkp-test-server:latest",
    )
    image.build()

    wait_strategy = LogMessageWaitStrategy(
        "Server listening",
    ).with_startup_timeout(30)

    container = (
        DockerContainer(str(image))
        .with_exposed_ports(22)
        .with_volume_mapping(
            str(public_key),
            "/tmp/authorized_keys",
            "ro",
        )
        .with_kwargs(privileged=True)
        .waiting_for(wait_strategy)
    )
    container.start()

    port = int(container.get_exposed_port(22))
    info: dict[str, Any] = {
        "host": container.get_container_host_ip(),
        "port": port,
        "user": "testuser",
        "private_key": str(private_key),
    }

    _wait_for_ssh(info, timeout=30)
    yield info

    container.stop()
    image.remove()


def _wait_for_ssh(info: dict[str, Any], timeout: int = 30) -> None:
    """Poll SSH until it accepts connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=2",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "BatchMode=yes",
                "-p",
                str(info["port"]),
                "-i",
                info["private_key"],
                f"{info['user']}@{info['host']}",
                "echo ready",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and "ready" in result.stdout:
            return
        time.sleep(1)
    raise TimeoutError(f"SSH not ready after {timeout}s")


@pytest.fixture(scope="session")
def rsync_server(
    docker_container: dict[str, Any],
) -> RsyncServer:
    """RsyncServer pointing at the Docker container."""
    return RsyncServer(
        slug="test-server",
        host=docker_container["host"],
        port=docker_container["port"],
        user=docker_container["user"],
        ssh_key=docker_container["private_key"],
        ssh_options=SshOptions(
            strict_host_key_checking=False,
            known_hosts_file="/dev/null",
        ),
    )


@pytest.fixture(scope="session")
def remote_volume() -> RemoteVolume:
    """RemoteVolume pointing at /data on the container."""
    return RemoteVolume(
        slug="test-remote",
        rsync_server="test-server",
        path="/data",
    )


@pytest.fixture(scope="session")
def remote_btrfs_volume() -> RemoteVolume:
    """RemoteVolume pointing at /mnt/btrfs on the container."""
    return RemoteVolume(
        slug="test-btrfs",
        rsync_server="test-server",
        path="/mnt/btrfs",
    )


def ssh_exec(
    docker_info: dict[str, Any], command: str
) -> subprocess.CompletedProcess[str]:
    """Run a command on the container via SSH."""
    return subprocess.run(
        [
            "ssh",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "BatchMode=yes",
            "-p",
            str(docker_info["port"]),
            "-i",
            docker_info["private_key"],
            f"{docker_info['user']}@{docker_info['host']}",
            command,
        ],
        capture_output=True,
        text=True,
    )


def create_markers(
    docker_info: dict[str, Any],
    path: str,
    markers: list[str],
) -> None:
    """Create marker files on the container via SSH."""
    for marker in markers:
        result = ssh_exec(docker_info, f"touch {path}/{marker}")
        assert (
            result.returncode == 0
        ), f"Failed to create marker {marker}: {result.stderr}"


@pytest.fixture(autouse=True)
def _cleanup_remote(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Clean up /data and /mnt/btrfs paths between tests."""
    yield

    # Only clean up if docker_container was used by this test
    if "docker_container" not in request.fixturenames:
        return

    docker_container = request.getfixturevalue("docker_container")

    # Clean /data paths
    ssh_exec(docker_container, "rm -rf /data/src/* /data/latest/*")
    ssh_exec(
        docker_container,
        "find /data -name '.nbkp-*' -delete",
    )
    # Recreate latest in case it was removed
    ssh_exec(docker_container, "mkdir -p /data/latest")
    # Remove any subdir structures created by tests
    ssh_exec(
        docker_container,
        "find /data -mindepth 1 -maxdepth 1"
        " ! -name src ! -name latest -exec rm -rf {} +",
    )

    # Clean btrfs paths — delete snapshot subvolumes first,
    # then latest
    snapshots_result = ssh_exec(
        docker_container,
        "ls /mnt/btrfs/snapshots 2>/dev/null || true",
    )
    if snapshots_result.stdout.strip():
        for snap in snapshots_result.stdout.strip().split("\n"):
            snap = snap.strip()
            if snap:
                ssh_exec(
                    docker_container,
                    "btrfs property set"
                    f" /mnt/btrfs/snapshots/{snap} ro false"
                    " 2>/dev/null || true",
                )
                ssh_exec(
                    docker_container,
                    "btrfs subvolume delete"
                    f" /mnt/btrfs/snapshots/{snap}"
                    " 2>/dev/null || true",
                )

    # Delete latest subvolume if it exists
    ssh_exec(
        docker_container,
        "btrfs property set" " /mnt/btrfs/latest ro false 2>/dev/null || true",
    )
    ssh_exec(
        docker_container,
        "btrfs subvolume delete" " /mnt/btrfs/latest 2>/dev/null || true",
    )
    ssh_exec(
        docker_container,
        "rm -rf /mnt/btrfs/snapshots 2>/dev/null || true",
    )
    ssh_exec(docker_container, "rm -rf /mnt/btrfs/src/*")
    ssh_exec(
        docker_container,
        "find /mnt/btrfs -name '.nbkp-*' -delete",
    )
