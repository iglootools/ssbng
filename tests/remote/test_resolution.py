"""Tests for nbkp.remote.resolution."""

from __future__ import annotations

import socket

import paramiko  # type: ignore[import-untyped]
import pytest

from nbkp.remote.resolution import (
    is_private_host,
    resolve_host,
    resolve_hostname,
)


class TestResolveHostname:
    """Tests for resolve_hostname (SSH config lookup)."""

    def test_from_ssh_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ssh_config = paramiko.SSHConfig.from_text(
            "Host mynas\n  HostName 192.168.1.100\n"
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: ssh_config,
        )
        assert resolve_hostname("mynas") == "192.168.1.100"

    def test_no_ssh_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: None,
        )
        assert resolve_hostname("mynas") == "mynas"

    def test_not_in_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ssh_config = paramiko.SSHConfig.from_text(
            "Host other\n  HostName 10.0.0.1\n"
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: ssh_config,
        )
        assert resolve_hostname("mynas") == "mynas"

    def test_with_port_and_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ssh_config = paramiko.SSHConfig.from_text(
            "Host mynas\n"
            "  HostName 192.168.1.100\n"
            "  Port 2222\n"
            "  User backup\n"
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: ssh_config,
        )
        # resolve_hostname only returns the hostname
        assert resolve_hostname("mynas") == "192.168.1.100"


class TestResolveHost:
    """Tests for resolve_host (SSH config + DNS)."""

    def test_via_ssh_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ssh_config = paramiko.SSHConfig.from_text(
            "Host mynas\n  HostName 127.0.0.1\n"
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: ssh_config,
        )
        addrs = resolve_host("mynas")
        assert addrs is not None
        assert "127.0.0.1" in addrs

    def test_unresolvable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: None,
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution.socket.getaddrinfo",
            _raise_gaierror,
        )
        assert resolve_host("nonexistent.invalid") is None

    def test_direct_hostname(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: None,
        )
        addrs = resolve_host("localhost")
        assert addrs is not None
        assert len(addrs) > 0


class TestIsPrivateHost:
    """Tests for is_private_host (SSH config + DNS + IP)."""

    def test_private_via_ssh_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ssh_config = paramiko.SSHConfig.from_text(
            "Host mynas\n  HostName 192.168.1.100\n"
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: ssh_config,
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution.socket.getaddrinfo",
            lambda host, port: [
                (None, None, None, None, ("192.168.1.100", 0))
            ],
        )
        assert is_private_host("mynas") is True

    def test_public_via_ssh_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ssh_config = paramiko.SSHConfig.from_text(
            "Host mypublic\n  HostName 8.8.8.8\n"
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: ssh_config,
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution.socket.getaddrinfo",
            lambda host, port: [(None, None, None, None, ("8.8.8.8", 0))],
        )
        assert is_private_host("mypublic") is False

    def test_unresolvable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: None,
        )
        monkeypatch.setattr(
            "nbkp.remote.resolution.socket.getaddrinfo",
            _raise_gaierror,
        )
        assert is_private_host("nonexistent.invalid") is None

    def test_localhost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "nbkp.remote.resolution._load_ssh_config",
            lambda: None,
        )
        assert is_private_host("localhost") is True


def _raise_gaierror(*args: object, **kwargs: object) -> None:
    raise socket.gaierror("mocked DNS failure")
