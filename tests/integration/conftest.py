"""Integration test fixtures — Docker SSH server with rsync + btrfs."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Generator

import pytest

from ssb.model import RemoteVolume

DOCKER_COMPOSE_DIR = Path(__file__).parent / "docker"


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
    """Generate an ephemeral ed25519 SSH key pair for tests."""
    tmpdir = Path(tempfile.mkdtemp(prefix="ssb-test-ssh-"))
    private_key = tmpdir / "id_ed25519"
    public_key = tmpdir / "id_ed25519.pub"

    subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            str(private_key),
            "-N",
            "",
            "-C",
            "ssb-integration-test",
        ],
        capture_output=True,
        check=True,
    )

    yield private_key, public_key

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def docker_container(
    ssh_key_pair: tuple[Path, Path],
) -> Generator[dict[str, Any], None, None]:
    """Start Docker container and yield connection info.

    Yields a dict with keys: host, port, user, private_key.
    """
    private_key, public_key = ssh_key_pair

    env = {
        **os.environ,
        "SSB_TEST_SSH_PUBKEY": str(public_key),
    }

    # Build and start the container
    subprocess.run(
        ["docker", "compose", "up", "-d", "--build", "--wait"],
        cwd=str(DOCKER_COMPOSE_DIR),
        env=env,
        capture_output=True,
        check=True,
        timeout=120,
    )

    # Get the dynamically assigned port
    result = subprocess.run(
        [
            "docker",
            "compose",
            "port",
            "ssb-test-server",
            "22",
        ],
        cwd=str(DOCKER_COMPOSE_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    # Output is like "0.0.0.0:55123"
    port = int(result.stdout.strip().split(":")[-1])

    info: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": port,
        "user": "testuser",
        "private_key": str(private_key),
    }

    # Wait for SSH to be ready
    _wait_for_ssh(info, timeout=30)

    yield info

    # Teardown
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=str(DOCKER_COMPOSE_DIR),
        env=env,
        capture_output=True,
        timeout=30,
    )


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
def remote_volume(docker_container: dict[str, Any]) -> RemoteVolume:
    """RemoteVolume pointing at /data on the container."""
    return RemoteVolume(
        name="test-remote",
        host=docker_container["host"],
        path="/data",
        port=docker_container["port"],
        user=docker_container["user"],
        ssh_key=docker_container["private_key"],
        ssh_options=[
            "StrictHostKeyChecking=no",
            "UserKnownHostsFile=/dev/null",
        ],
    )


@pytest.fixture(scope="session")
def remote_btrfs_volume(docker_container: dict[str, Any]) -> RemoteVolume:
    """RemoteVolume pointing at /mnt/btrfs on the container."""
    return RemoteVolume(
        name="test-btrfs",
        host=docker_container["host"],
        path="/mnt/btrfs",
        port=docker_container["port"],
        user=docker_container["user"],
        ssh_key=docker_container["private_key"],
        ssh_options=[
            "StrictHostKeyChecking=no",
            "UserKnownHostsFile=/dev/null",
        ],
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
    docker_info: dict[str, Any], path: str, markers: list[str]
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
    ssh_exec(docker_container, "find /data -name '.ssb-*' -delete")
    # Recreate latest in case it was removed
    ssh_exec(docker_container, "mkdir -p /data/latest")
    # Remove any subdir structures created by tests
    ssh_exec(
        docker_container,
        "find /data -mindepth 1 -maxdepth 1"
        " ! -name src ! -name latest -exec rm -rf {} +",
    )

    # Clean btrfs paths — delete snapshot subvolumes first, then latest
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
                    "btrfs subvolume delete"
                    f" /mnt/btrfs/snapshots/{snap}"
                    " 2>/dev/null || true",
                )

    # Delete latest subvolume if it exists
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
        "find /mnt/btrfs -name '.ssb-*' -delete",
    )
