"""Tests for ssb.ssh."""

from __future__ import annotations

from unittest.mock import patch

from ssb.config import RsyncServer
from ssb.ssh import (
    build_ssh_base_args,
    build_ssh_e_option,
    format_remote_path,
    run_remote_command,
)


class TestBuildSshBaseArgs:
    def test_minimal(self, rsync_server_minimal: RsyncServer) -> None:
        args = build_ssh_base_args(rsync_server_minimal)
        assert args == [
            "ssh",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "nas2.example.com",
        ]

    def test_full(self, rsync_server: RsyncServer) -> None:
        args = build_ssh_base_args(rsync_server)
        assert args == [
            "ssh",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "-p",
            "5022",
            "-i",
            "~/.ssh/key",
            "backup@nas.example.com",
        ]

    def test_with_ssh_options(self) -> None:
        server = RsyncServer(
            slug="host-server",
            host="host.example.com",
            ssh_options=[
                "StrictHostKeyChecking=no",
                "UserKnownHostsFile=/dev/null",
            ],
        )
        args = build_ssh_base_args(server)
        assert args == [
            "ssh",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "host.example.com",
        ]

    def test_custom_connect_timeout(self) -> None:
        server = RsyncServer(
            slug="slow-server",
            host="slow.example.com",
            connect_timeout=30,
        )
        args = build_ssh_base_args(server)
        assert args == [
            "ssh",
            "-o",
            "ConnectTimeout=30",
            "-o",
            "BatchMode=yes",
            "slow.example.com",
        ]


class TestBuildSshEOption:
    def test_minimal(self, rsync_server_minimal: RsyncServer) -> None:
        result = build_ssh_e_option(rsync_server_minimal)
        assert result == ["-e", "ssh"]

    def test_full(self, rsync_server: RsyncServer) -> None:
        result = build_ssh_e_option(rsync_server)
        assert result == ["-e", "ssh -p 5022 -i ~/.ssh/key"]

    def test_with_ssh_options(self) -> None:
        server = RsyncServer(
            slug="host-server",
            host="host.example.com",
            ssh_options=["StrictHostKeyChecking=no"],
        )
        result = build_ssh_e_option(server)
        assert result == ["-e", "ssh -o StrictHostKeyChecking=no"]


class TestFormatRemotePath:
    def test_with_user(self, rsync_server: RsyncServer) -> None:
        result = format_remote_path(rsync_server, "/data")
        assert result == "backup@nas.example.com:/data"

    def test_without_user(self, rsync_server_minimal: RsyncServer) -> None:
        result = format_remote_path(rsync_server_minimal, "/data")
        assert result == "nas2.example.com:/data"


class TestRunRemoteCommand:
    @patch("ssb.ssh.subprocess.run")
    def test_run_remote_command(
        self, mock_run: object, rsync_server: RsyncServer
    ) -> None:
        run_remote_command(rsync_server, ["ls", "/tmp"])
        from unittest.mock import call

        expected_args = [
            "ssh",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "-p",
            "5022",
            "-i",
            "~/.ssh/key",
            "backup@nas.example.com",
            "ls /tmp",
        ]
        assert mock_run.call_args == call(  # type: ignore[attr-defined]
            expected_args,
            capture_output=True,
            text=True,
        )
