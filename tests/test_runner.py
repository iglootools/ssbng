"""Tests for ssb.runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
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
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(volume="dst"),
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
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(
            volume="dst",
            btrfs_snapshots=True,
        ),
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"s1": sync},
    )


def _make_remote_to_remote_config() -> Config:
    src_server = RsyncServer(
        name="src-server", host="src.local", user="srcuser"
    )
    dst_server = RsyncServer(
        name="dst-server", host="dst.local", user="dstuser"
    )
    src = RemoteVolume(
        name="src",
        rsync_server="src-server",
        path="/data",
    )
    dst = RemoteVolume(
        name="dst",
        rsync_server="dst-server",
        path="/backup",
    )
    sync = SyncConfig(
        name="s1",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(
            volume="dst",
            btrfs_snapshots=True,
        ),
    )
    return Config(
        rsync_servers={
            "src-server": src_server,
            "dst-server": dst_server,
        },
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
            source_status=vol_statuses[sync.source.volume],
            destination_status=vol_statuses[sync.destination.volume],
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
            source_status=vol_statuses[sync.source.volume],
            destination_status=vol_statuses[sync.destination.volume],
            reasons=[SyncReason.SOURCE_UNAVAILABLE],
        )
        for name, sync in config.syncs.items()
    }
    return vol_statuses, sync_statuses


class TestRunAllSyncs:
    @patch("ssb.runner.run_rsync")
    def test_successful_sync(self, mock_rsync: MagicMock) -> None:
        config = _make_local_config()
        _, sync_statuses = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )

        results = run_all_syncs(config, sync_statuses)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].rsync_exit_code == 0

    def test_inactive_sync(self) -> None:
        config = _make_local_config()
        _, sync_statuses = _inactive_statuses(config)

        results = run_all_syncs(config, sync_statuses)
        assert len(results) == 1
        assert results[0].success is False
        assert "not active" in (results[0].error or "")

    @patch("ssb.runner.run_rsync")
    def test_rsync_failure(self, mock_rsync: MagicMock) -> None:
        config = _make_local_config()
        _, sync_statuses = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=23, stdout="", stderr="error"
        )

        results = run_all_syncs(config, sync_statuses)
        assert results[0].success is False
        assert results[0].rsync_exit_code == 23

    @patch("ssb.runner.run_rsync")
    def test_filter_by_sync_name(self, mock_rsync: MagicMock) -> None:
        config = _make_local_config()
        _, sync_statuses = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )

        results = run_all_syncs(
            config, sync_statuses, sync_names=["nonexistent"]
        )
        assert len(results) == 0

    @patch("ssb.runner.create_snapshot")
    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    def test_btrfs_snapshot_after_sync(
        self,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        config = _make_btrfs_config()
        _, sync_statuses = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = None
        mock_snap.return_value = "/dst/snapshots/20240115T120000Z"

        results = run_all_syncs(config, sync_statuses)
        assert results[0].success is True
        assert results[0].snapshot_path == "/dst/snapshots/20240115T120000Z"
        mock_snap.assert_called_once()

    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    def test_btrfs_snapshot_skipped_on_dry_run(
        self,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
    ) -> None:
        config = _make_btrfs_config()
        _, sync_statuses = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = None

        results = run_all_syncs(config, sync_statuses, dry_run=True)
        assert results[0].success is True
        assert results[0].snapshot_path is None

    @patch("ssb.runner.create_snapshot")
    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    def test_link_dest_from_latest_snapshot(
        self,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        config = _make_btrfs_config()
        _, sync_statuses = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = "/dst/snapshots/20240101T000000Z"
        mock_snap.return_value = "/dst/snapshots/20240115T120000Z"

        run_all_syncs(config, sync_statuses)

        # Verify link_dest was passed to run_rsync
        call_kwargs = mock_rsync.call_args
        assert (
            call_kwargs.kwargs.get("link_dest")
            == "../../snapshots/20240101T000000Z"
        )

    @patch("ssb.runner.create_snapshot")
    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    def test_remote_to_remote_with_btrfs(
        self,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        config = _make_remote_to_remote_config()
        _, sync_statuses = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = None
        mock_snap.return_value = "/backup/snapshots/20240115T120000Z"

        results = run_all_syncs(config, sync_statuses)
        assert results[0].success is True
        assert results[0].snapshot_path is not None
        mock_snap.assert_called_once()

    @patch("ssb.runner.create_snapshot")
    @patch("ssb.runner.get_latest_snapshot")
    @patch("ssb.runner.run_rsync")
    def test_snapshot_failure(
        self,
        mock_rsync: MagicMock,
        mock_latest: MagicMock,
        mock_snap: MagicMock,
    ) -> None:
        config = _make_btrfs_config()
        _, sync_statuses = _active_statuses(config)
        mock_rsync.return_value = MagicMock(
            returncode=0, stdout="done\n", stderr=""
        )
        mock_latest.return_value = None
        mock_snap.side_effect = RuntimeError("btrfs failed")

        results = run_all_syncs(config, sync_statuses)
        assert results[0].success is False
        assert "Snapshot failed" in (results[0].error or "")
