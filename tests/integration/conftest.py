"""Integration test fixtures -- Docker SSH server with rsync + btrfs."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Generator

import docker as dockerlib
import pytest

from nbkp.config import RemoteVolume, SshEndpoint, SshConnectionOptions
from nbkp.testkit.docker import (
    generate_ssh_keypair,
    ssh_exec,
    wait_for_ssh,
)

DOCKER_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "nbkp"
    / "testkit"
    / "dockerbuild"
)


def _docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        client = dockerlib.from_env()
        client.ping()
        return True
    except dockerlib.errors.DockerException:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker not available"
)


@pytest.fixture(scope="session")
def ssh_key_pair() -> Generator[tuple[Path, Path], None, None]:
    """Generate an ephemeral ed25519 SSH key pair for tests."""
    tmpdir = Path(tempfile.mkdtemp(prefix="nbkp-test-ssh-"))
    pair = generate_ssh_keypair(tmpdir)

    yield pair

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def _docker_image() -> str:
    """Build the Docker image and return its tag."""
    from testcontainers.core.image import DockerImage

    image = DockerImage(
        path=str(DOCKER_DIR),
        tag="nbkp-test-server:latest",
    )
    image.build()
    return str(image)


@pytest.fixture(scope="session")
def _docker_network() -> Generator[Any, None, None]:
    """Create a Docker bridge network for inter-container comms."""
    client = dockerlib.from_env()
    name = f"nbkp-test-{uuid.uuid4().hex[:8]}"
    network = client.networks.create(name, driver="bridge")

    yield network

    try:
        network.remove()
    except dockerlib.errors.APIError:
        pass


@pytest.fixture(scope="session")
def docker_container(
    ssh_key_pair: tuple[Path, Path],
    _docker_image: str,
    _docker_network: Any,
) -> Generator[SshEndpoint, None, None]:
    """Start Docker container and yield SshEndpoint."""
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import (
        LogMessageWaitStrategy,
    )

    private_key, public_key = ssh_key_pair

    wait_strategy = LogMessageWaitStrategy(
        "Server listening",
    ).with_startup_timeout(30)

    container = (
        DockerContainer(_docker_image)
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

    # Connect to network with alias for bastion access
    wrapped = container.get_wrapped_container()
    _docker_network.connect(wrapped, aliases=["backup-server"])

    server = SshEndpoint(
        slug="test-server",
        host=container.get_container_host_ip(),
        port=int(container.get_exposed_port(22)),
        user="testuser",
        key=str(private_key),
        connection_options=SshConnectionOptions(
            strict_host_key_checking=False,
            known_hosts_file="/dev/null",
        ),
    )

    wait_for_ssh(server, timeout=30)
    yield server

    container.stop()


@pytest.fixture(scope="session")
def bastion_container(
    ssh_key_pair: tuple[Path, Path],
    _docker_image: str,
    _docker_network: Any,
) -> Generator[SshEndpoint, None, None]:
    """Start a bastion (jump proxy) container."""
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import (
        LogMessageWaitStrategy,
    )

    private_key, public_key = ssh_key_pair

    wait_strategy = LogMessageWaitStrategy(
        "Server listening",
    ).with_startup_timeout(30)

    container = (
        DockerContainer(_docker_image)
        .with_exposed_ports(22)
        .with_volume_mapping(
            str(public_key),
            "/tmp/authorized_keys",
            "ro",
        )
        .with_env("NBKP_BASTION_ONLY", "1")
        .waiting_for(wait_strategy)
    )
    container.start()

    wrapped = container.get_wrapped_container()
    _docker_network.connect(wrapped)

    server = SshEndpoint(
        slug="bastion",
        host=container.get_container_host_ip(),
        port=int(container.get_exposed_port(22)),
        user="testuser",
        key=str(private_key),
        connection_options=SshConnectionOptions(
            strict_host_key_checking=False,
            known_hosts_file="/dev/null",
        ),
    )

    wait_for_ssh(server, timeout=30)
    yield server

    container.stop()


@pytest.fixture(scope="session")
def proxied_ssh_endpoint(
    ssh_key_pair: tuple[Path, Path],
    bastion_container: SshEndpoint,
    docker_container: SshEndpoint,
) -> SshEndpoint:
    """SshEndpoint that routes through the bastion."""
    private_key, _ = ssh_key_pair
    return SshEndpoint(
        slug="proxied-server",
        host="backup-server",
        port=22,
        user="testuser",
        key=str(private_key),
        proxy_jump="bastion",
        connection_options=SshConnectionOptions(
            strict_host_key_checking=False,
            known_hosts_file="/dev/null",
        ),
    )


@pytest.fixture(scope="session")
def ssh_endpoint(
    docker_container: SshEndpoint,
) -> SshEndpoint:
    """SshEndpoint pointing at the Docker container."""
    return docker_container


@pytest.fixture(scope="session")
def remote_volume() -> RemoteVolume:
    """RemoteVolume pointing at /data on the container."""
    return RemoteVolume(
        slug="test-remote",
        ssh_endpoint="test-server",
        path="/data",
    )


@pytest.fixture(scope="session")
def remote_btrfs_volume() -> RemoteVolume:
    """RemoteVolume pointing at /mnt/btrfs on the container."""
    return RemoteVolume(
        slug="test-btrfs",
        ssh_endpoint="test-server",
        path="/mnt/btrfs",
    )


@pytest.fixture(scope="session")
def remote_hardlink_volume() -> RemoteVolume:
    """RemoteVolume pointing at /data/hl on the container."""
    return RemoteVolume(
        slug="test-hl",
        ssh_endpoint="test-server",
        path="/data/hl",
    )


def create_markers(
    server: SshEndpoint,
    path: str,
    markers: list[str],
) -> None:
    """Create marker files on the container via SSH."""
    for marker in markers:
        result = ssh_exec(server, f"touch {path}/{marker}", check=False)
        assert (
            result.returncode == 0
        ), f"Failed to create marker {marker}: {result.stderr}"


@pytest.fixture(autouse=True)
def _cleanup_remote(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Clean up /data and /mnt/btrfs paths between tests."""
    yield

    # Only clean up if ssh_endpoint was used by this test
    if "ssh_endpoint" not in request.fixturenames:
        return

    server: SshEndpoint = request.getfixturevalue("ssh_endpoint")

    def run(cmd: str) -> None:
        ssh_exec(server, cmd, check=False)

    # Clean /data paths
    run("rm -rf /data/src/* /data/latest/*")
    run("find /data -name '.nbkp-*' -delete")
    # Recreate latest in case it was removed
    run("mkdir -p /data/latest")
    # Remove any subdir structures created by tests
    run(
        "find /data -mindepth 1 -maxdepth 1"
        " ! -name src ! -name latest -exec rm -rf {} +"
    )

    # Clean hard-link test paths
    run("rm -rf /data/hl/snapshots/* /data/hl/latest")
    run("find /data/hl -name '.nbkp-*' -delete 2>/dev/null || true")

    # Clean btrfs paths — delete snapshot subvolumes first,
    # then latest
    snapshots_result = ssh_exec(
        server,
        "ls /mnt/btrfs/snapshots 2>/dev/null || true",
        check=False,
    )
    if snapshots_result.stdout.strip():
        for snap in snapshots_result.stdout.strip().split("\n"):
            snap = snap.strip()
            if snap:
                run(
                    "btrfs property set"
                    f" /mnt/btrfs/snapshots/{snap} ro false"
                    " 2>/dev/null || true"
                )
                run(
                    "btrfs subvolume delete"
                    f" /mnt/btrfs/snapshots/{snap}"
                    " 2>/dev/null || true"
                )

    # Delete latest subvolume if it exists
    run("btrfs property set" " /mnt/btrfs/latest ro false 2>/dev/null || true")
    run("btrfs subvolume delete" " /mnt/btrfs/latest 2>/dev/null || true")
    run("rm -rf /mnt/btrfs/snapshots 2>/dev/null || true")
    run("rm -rf /mnt/btrfs/src/*")
    run("find /mnt/btrfs -name '.nbkp-*' -delete")
