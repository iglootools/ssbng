"""Tests for ssb.btrfs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ssb.btrfs import create_snapshot, get_latest_snapshot
from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)


def _local_config() -> tuple[Config, SyncConfig]:
    src = LocalVolume(name="src", path="/mnt/src")
    dst = LocalVolume(name="dst", path="/mnt/dst")
    sync = SyncConfig(
        name="s1",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(
            volume="dst",
            subdir="backup",
            btrfs_snapshots=True,
        ),
    )
    config = Config(
        volumes={"src": src, "dst": dst},
        syncs={"s1": sync},
    )
    return config, sync


def _remote_config() -> tuple[Config, SyncConfig]:
    src = LocalVolume(name="src", path="/mnt/src")
    dst_server = RsyncServer(
        name="nas-server",
        host="nas.local",
        user="admin",
    )
    dst = RemoteVolume(
        name="dst",
        rsync_server="nas-server",
        path="/backup",
    )
    sync = SyncConfig(
        name="s1",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(
            volume="dst",
            subdir="data",
            btrfs_snapshots=True,
        ),
    )
    config = Config(
        rsync_servers={"nas-server": dst_server},
        volumes={"src": src, "dst": dst},
        syncs={"s1": sync},
    )
    return config, sync


class TestCreateSnapshotLocal:
    @patch("ssb.btrfs.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        config, sync = _local_config()
        from datetime import datetime, timezone

        fixed_now = datetime(2024, 1, 15, 12, 0, 0, 0, tzinfo=timezone.utc)
        path = create_snapshot(sync, config, now=fixed_now)
        assert path == ("/mnt/dst/backup/snapshots/2024-01-15T12:00:00.000Z")
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == [
            "btrfs",
            "subvolume",
            "snapshot",
            "-r",
            "/mnt/dst/backup/latest",
            "/mnt/dst/backup/snapshots/2024-01-15T12:00:00.000Z",
        ]

    @patch("ssb.btrfs.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=1, stderr="permission denied"
        )
        config, sync = _local_config()
        from datetime import datetime, timezone

        fixed_now = datetime(2024, 1, 15, 12, 0, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(RuntimeError, match="btrfs snapshot"):
            create_snapshot(sync, config, now=fixed_now)


class TestCreateSnapshotRemote:
    @patch("ssb.btrfs.run_remote_command")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        config, sync = _remote_config()
        from datetime import datetime, timezone

        fixed_now = datetime(2024, 1, 15, 12, 0, 0, 0, tzinfo=timezone.utc)
        path = create_snapshot(sync, config, now=fixed_now)
        assert path == ("/backup/data/snapshots/2024-01-15T12:00:00.000Z")
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == config.rsync_servers["nas-server"]
        assert call_args[0][1] == [
            "btrfs",
            "subvolume",
            "snapshot",
            "-r",
            "/backup/data/latest",
            "/backup/data/snapshots/2024-01-15T12:00:00.000Z",
        ]


class TestGetLatestSnapshotLocal:
    @patch("ssb.btrfs.subprocess.run")
    def test_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="20240101T000000Z\n20240115T120000Z\n",
        )
        config, sync = _local_config()

        result = get_latest_snapshot(sync, config)
        assert result == ("/mnt/dst/backup/snapshots/20240115T120000Z")

    @patch("ssb.btrfs.subprocess.run")
    def test_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        config, sync = _local_config()

        result = get_latest_snapshot(sync, config)
        assert result is None

    @patch("ssb.btrfs.subprocess.run")
    def test_dir_missing(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=2, stdout="")
        config, sync = _local_config()

        result = get_latest_snapshot(sync, config)
        assert result is None


class TestGetLatestSnapshotRemote:
    @patch("ssb.btrfs.run_remote_command")
    def test_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="20240101T000000Z\n20240115T120000Z\n",
        )
        config, sync = _remote_config()

        result = get_latest_snapshot(sync, config)
        assert result == ("/backup/data/snapshots/20240115T120000Z")
        mock_run.assert_called_once_with(
            config.rsync_servers["nas-server"],
            ["ls", "/backup/data/snapshots"],
        )


def _local_config_spaces() -> tuple[Config, SyncConfig]:
    src = LocalVolume(name="src", path="/mnt/my src")
    dst = LocalVolume(name="dst", path="/mnt/my dst")
    sync = SyncConfig(
        name="s1",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(
            volume="dst",
            subdir="my backup",
            btrfs_snapshots=True,
        ),
    )
    config = Config(
        volumes={"src": src, "dst": dst},
        syncs={"s1": sync},
    )
    return config, sync


def _remote_config_spaces() -> tuple[Config, SyncConfig]:
    src = LocalVolume(name="src", path="/mnt/my src")
    dst_server = RsyncServer(
        name="nas-server",
        host="nas.local",
        user="admin",
    )
    dst = RemoteVolume(
        name="dst",
        rsync_server="nas-server",
        path="/my backup",
    )
    sync = SyncConfig(
        name="s1",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(
            volume="dst",
            subdir="my data",
            btrfs_snapshots=True,
        ),
    )
    config = Config(
        rsync_servers={"nas-server": dst_server},
        volumes={"src": src, "dst": dst},
        syncs={"s1": sync},
    )
    return config, sync


class TestCreateSnapshotLocalSpaces:
    @patch("ssb.btrfs.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        config, sync = _local_config_spaces()
        from datetime import datetime, timezone

        fixed_now = datetime(2024, 1, 15, 12, 0, 0, 0, tzinfo=timezone.utc)
        path = create_snapshot(sync, config, now=fixed_now)
        assert path == (
            "/mnt/my dst/my backup/snapshots/" "2024-01-15T12:00:00.000Z"
        )
        call_args = mock_run.call_args[0][0]
        assert call_args == [
            "btrfs",
            "subvolume",
            "snapshot",
            "-r",
            "/mnt/my dst/my backup/latest",
            "/mnt/my dst/my backup/snapshots/" "2024-01-15T12:00:00.000Z",
        ]


class TestCreateSnapshotRemoteSpaces:
    @patch("ssb.btrfs.run_remote_command")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        config, sync = _remote_config_spaces()
        from datetime import datetime, timezone

        fixed_now = datetime(2024, 1, 15, 12, 0, 0, 0, tzinfo=timezone.utc)
        path = create_snapshot(sync, config, now=fixed_now)
        assert path == (
            "/my backup/my data/snapshots/" "2024-01-15T12:00:00.000Z"
        )
        call_args = mock_run.call_args
        assert call_args[0][1] == [
            "btrfs",
            "subvolume",
            "snapshot",
            "-r",
            "/my backup/my data/latest",
            "/my backup/my data/snapshots/" "2024-01-15T12:00:00.000Z",
        ]


class TestGetLatestSnapshotRemoteSpaces:
    @patch("ssb.btrfs.run_remote_command")
    def test_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="20240101T000000Z\n20240115T120000Z\n",
        )
        config, sync = _remote_config_spaces()

        result = get_latest_snapshot(sync, config)
        assert result == ("/my backup/my data/snapshots/20240115T120000Z")
        mock_run.assert_called_once_with(
            config.rsync_servers["nas-server"],
            ["ls", "/my backup/my data/snapshots"],
        )
