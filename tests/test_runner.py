"""Tests for ssb.runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    SyncEndpoint,
)
from ssb.status import (
    SyncReason,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
)
from ssb.runner import run_all_syncs


def _make_local_config() -> Config:
    src = LocalVolume(name="src", path="/src")
    dst = LocalVolume(name="dst", path="/dst")
    sync = SyncConfig(
        name="s1",
        source=SyncEndpoint(volume_name="src"),
        destination=DestinationSyncEndpoint(volume_name="dst"),
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"s1": sync},
    )


def _make_btrfs_config() -> Config:
    src = LocalVolume(name="src", path="/src")
    dst = LocalVolume(name="dst", path="/dst")
    sync = SyncConfig(
        name="s1",
        source=SyncEndpoint(volume_name="src"),
        destination=DestinationSyncEndpoint(
            volume_name="dst",
            btrfs_snapshots=True,
        ),
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"s1": sync},
    )


def _make_remote_to_remote_config() -> Config:
    src = RemoteVolume(
        name="src", host="src.local", path="/data", user="srcuser"
    )
    dst = RemoteVolume(
        name="dst", host="dst.local", path="/backup", user="dstuser"
    )
    sync = SyncConfig(
        name="s1",
        source=SyncEndpoint(volume_name="src"),
        destination=DestinationSyncEndpoint(
            volume_name="dst",
            btrfs_snapshots=True,
        ),
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"s1": sync},
    )


def _active_statuses(
    config: Config,
) -> tuple[dict[str, VolumeStatus], dict[str, SyncStatus]]:
    vol_statuses = {
        name: VolumeStatus(
            name=name,
            config=vol,
            reasons=[],
        )
        for name, vol in config.volumes.items()
    }
    sync_statuses = {
        name: SyncStatus(
            name=name,
            config=sync,
            source_status=vol_statuses[sync.source.volume_name],
            destination_status=vol_statuses[sync.destination.volume_name],
            reasons=[],
        )
        for name, sync in config.syncs.items()
    }
    return vol_statuses, sync_statuses


def _inactive_statuses(
    config: Config,
) -> tuple[dict[str, VolumeStatus], dict[str, SyncStatus]]:
    vol_statuses = {
        name: VolumeStatus(
            name=name,
            config=vol,
            reasons=[VolumeReason.UNREACHABLE],
        )
        for name, vol in config.volumes.items()
    }
    sync_statuses = {
        name: SyncStatus(
            name=name,
            config=sync,
            source_status=vol_statuses[sync.source.volume_name],
            destination_status=vol_statuses[sync.destination.volume_name],
            reasons=[SyncReason.SOURCE_UNAVAILABLE],
        )
        for name, sync in config.syncs.items()
    }
    return vol_statuses, sync_statuses


class TestRunAllSyncs:
    @patch("ssb.runner.run_rsync")
    @patch("ssb.runner.check_all_syncs")
    def test_successful_sync(
        self, mock_checks: MagicMock, mock_rsync: MagicMock
    ) -> None:
        config = _make_local_config()
        mock_checks.return_value = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )

        statuses, results = run_all_syncs(config)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].rsync_exit_code == 0

    @patch("ssb.runner.check_all_syncs")
    def test_inactive_sync(self, mock_checks: MagicMock) -> None:
        config = _make_local_config()
        mock_checks.return_value = _inactive_statuses(config)

        statuses, results = run_all_syncs(config)
        assert len(results) == 1
        assert results[0].success is False
        assert "not active" in (results[0].error or "")

    @patch("ssb.runner.run_rsync")
    @patch("ssb.runner.check_all_syncs")
    def test_rsync_failure(
        self, mock_checks: MagicMock, mock_rsync: MagicMock
    ) -> None:
        config = _make_local_config()
        mock_checks.return_value = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=23, stdout="", stderr="error"
        )

        statuses, results = run_all_syncs(config)
        assert results[0].success is False
        assert results[0].rsync_exit_code == 23

    @patch("ssb.runner.run_rsync")
    @patch("ssb.runner.check_all_syncs")
    def test_filter_by_sync_name(
        self, mock_checks: MagicMock, mock_rsync: MagicMock
    ) -> None:
        config = _make_local_config()
        mock_checks.return_value = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )

        statuses, results = run_all_syncs(config, sync_names=["nonexistent"])
        assert len(results) == 0

    @patch("ssb.runner.create_snapshot")
    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    @patch("ssb.runner.check_all_syncs")
    def test_btrfs_snapshot_after_sync(
        self,
        mock_checks: MagicMock,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        config = _make_btrfs_config()
        mock_checks.return_value = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = None
        mock_snap.return_value = "/dst/snapshots/20240115T120000Z"

        statuses, results = run_all_syncs(config)
        assert results[0].success is True
        assert results[0].snapshot_path == "/dst/snapshots/20240115T120000Z"
        mock_snap.assert_called_once()

    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    @patch("ssb.runner.check_all_syncs")
    def test_btrfs_snapshot_skipped_on_dry_run(
        self,
        mock_checks: MagicMock,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
    ) -> None:
        config = _make_btrfs_config()
        mock_checks.return_value = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = None

        statuses, results = run_all_syncs(config, dry_run=True)
        assert results[0].success is True
        assert results[0].snapshot_path is None

    @patch("ssb.runner.create_snapshot")
    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    @patch("ssb.runner.check_all_syncs")
    def test_link_dest_from_latest_snapshot(
        self,
        mock_checks: MagicMock,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        config = _make_btrfs_config()
        mock_checks.return_value = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = "/dst/snapshots/20240101T000000Z"
        mock_snap.return_value = "/dst/snapshots/20240115T120000Z"

        statuses, results = run_all_syncs(config)

        # Verify link_dest was passed to run_rsync
        call_kwargs = mock_rsync.call_args
        assert (
            call_kwargs.kwargs.get("link_dest")
            == "../../snapshots/20240101T000000Z"
        )

    @patch("ssb.runner.create_snapshot")
    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    @patch("ssb.runner.check_all_syncs")
    def test_remote_to_remote_with_btrfs(
        self,
        mock_checks: MagicMock,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        config = _make_remote_to_remote_config()
        mock_checks.return_value = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = None
        mock_snap.return_value = "/backup/snapshots/20240115T120000Z"

        statuses, results = run_all_syncs(config)
        assert results[0].success is True
        assert results[0].snapshot_path is not None
        mock_snap.assert_called_once()

    @patch("ssb.runner.create_snapshot")
    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    @patch("ssb.runner.check_all_syncs")
    def test_snapshot_failure(
        self,
        mock_checks: MagicMock,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        config = _make_btrfs_config()
        mock_checks.return_value = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = None
        mock_snap.side_effect = RuntimeError("btrfs failed")

        statuses, results = run_all_syncs(config)
        assert results[0].success is False
        assert "Snapshot failed" in (results[0].error or "")
