"""Tests for ssb.ssh."""

from __future__ import annotations

from unittest.mock import patch

from ssb.config import RemoteVolume
from ssb.ssh import (
    build_ssh_base_args,
    build_ssh_e_option,
    format_remote_path,
    run_remote_command,
)


class TestBuildSshBaseArgs:
    def test_minimal(self, remote_volume_minimal: RemoteVolume) -> None:
        args = build_ssh_base_args(remote_volume_minimal)
        assert args == [
            "ssh",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            "nas2.example.com",
        ]

    def test_full(self, remote_volume: RemoteVolume) -> None:
        args = build_ssh_base_args(remote_volume)
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
        vol = RemoteVolume(
            name="test",
            host="host.example.com",
            path="/data",
            ssh_options=[
                "StrictHostKeyChecking=no",
                "UserKnownHostsFile=/dev/null",
            ],
        )
        args = build_ssh_base_args(vol)
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


class TestBuildSshEOption:
    def test_minimal(self, remote_volume_minimal: RemoteVolume) -> None:
        result = build_ssh_e_option(remote_volume_minimal)
        assert result == ["-e", "ssh"]

    def test_full(self, remote_volume: RemoteVolume) -> None:
        result = build_ssh_e_option(remote_volume)
        assert result == ["-e", "ssh -p 5022 -i ~/.ssh/key"]

    def test_with_ssh_options(self) -> None:
        vol = RemoteVolume(
            name="test",
            host="host.example.com",
            path="/data",
            ssh_options=["StrictHostKeyChecking=no"],
        )
        result = build_ssh_e_option(vol)
        assert result == ["-e", "ssh -o StrictHostKeyChecking=no"]


class TestFormatRemotePath:
    def test_with_user(self, remote_volume: RemoteVolume) -> None:
        result = format_remote_path(remote_volume, "/data")
        assert result == "backup@nas.example.com:/data"

    def test_without_user(self, remote_volume_minimal: RemoteVolume) -> None:
        result = format_remote_path(remote_volume_minimal, "/data")
        assert result == "nas2.example.com:/data"


class TestRunRemoteCommand:
    @patch("ssb.ssh.subprocess.run")
    def test_run_remote_command(
        self, mock_run: object, remote_volume: RemoteVolume
    ) -> None:
        run_remote_command(remote_volume, "ls /tmp")
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
