"""Tests for ssb.checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ssb.checks import (
    check_all_syncs,
    check_sync,
    check_volume,
    _check_command_available,
)
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
    VolumeReason,
    VolumeStatus,
)


class TestCheckLocalVolume:
    def test_active(self, tmp_path: Path) -> None:
        vol = LocalVolume(name="data", path=str(tmp_path))
        (tmp_path / ".ssb-vol").touch()
        status = check_volume(vol)
        assert status.active is True
        assert status.reasons == []

    def test_inactive(self, tmp_path: Path) -> None:
        vol = LocalVolume(name="data", path=str(tmp_path))
        status = check_volume(vol)
        assert status.active is False
        assert status.reasons == [VolumeReason.MARKER_NOT_FOUND]


class TestCheckRemoteVolume:
    @patch("ssb.checks.run_remote_command")
    def test_active(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol = RemoteVolume(name="nas", host="nas.local", path="/backup")
        status = check_volume(vol)
        assert status.active is True
        assert status.reasons == []
        mock_run.assert_called_once_with(vol, "test -f /backup/.ssb-vol")

    @patch("ssb.checks.run_remote_command")
    def test_inactive(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        vol = RemoteVolume(name="nas", host="nas.local", path="/backup")
        status = check_volume(vol)
        assert status.active is False
        assert status.reasons == [VolumeReason.UNREACHABLE]


class TestCheckCommandAvailableLocal:
    @patch("ssb.checks.shutil.which")
    def test_command_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/bin/rsync"
        vol = LocalVolume(name="data", path="/mnt/data")
        assert _check_command_available(vol, "rsync") is True
        mock_which.assert_called_once_with("rsync")

    @patch("ssb.checks.shutil.which")
    def test_command_not_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        vol = LocalVolume(name="data", path="/mnt/data")
        assert _check_command_available(vol, "rsync") is False
        mock_which.assert_called_once_with("rsync")


class TestCheckCommandAvailableRemote:
    @patch("ssb.checks.run_remote_command")
    def test_command_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol = RemoteVolume(name="nas", host="nas.local", path="/backup")
        assert _check_command_available(vol, "rsync") is True
        mock_run.assert_called_once_with(vol, "which rsync")

    @patch("ssb.checks.run_remote_command")
    def test_command_not_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        vol = RemoteVolume(name="nas", host="nas.local", path="/backup")
        assert _check_command_available(vol, "btrfs") is False
        mock_run.assert_called_once_with(vol, "which btrfs")


class TestCheckSync:
    def _make_config(
        self, tmp_src: Path, tmp_dst: Path
    ) -> tuple[Config, SyncConfig]:
        src_vol = LocalVolume(name="src", path=str(tmp_src))
        dst_vol = LocalVolume(name="dst", path=str(tmp_dst))
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume_name="dst", subdir="backup"
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        return config, sync

    @patch("ssb.checks.shutil.which", return_value="/usr/bin/rsync")
    def test_active_sync(self, mock_which: MagicMock, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        (src / ".ssb-vol").touch()
        (dst / ".ssb-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".ssb-src").touch()
        (dst / "backup").mkdir()
        (dst / "backup" / ".ssb-dst").touch()

        config, sync = self._make_config(src, dst)
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=config.volumes["src"],
                reasons=[],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                reasons=[],
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is True
        assert status.reasons == []

    def test_disabled_sync(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        config, _ = self._make_config(src, dst)
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume_name="dst", subdir="backup"
            ),
            enabled=False,
        )
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=config.volumes["src"],
                reasons=[],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                reasons=[],
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert status.reasons == [SyncReason.DISABLED]

    def test_source_unavailable(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        config, sync = self._make_config(src, dst)
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=config.volumes["src"],
                reasons=[VolumeReason.MARKER_NOT_FOUND],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                reasons=[],
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.SOURCE_UNAVAILABLE in status.reasons

    def test_missing_src_marker(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "data").mkdir()
        (dst / "backup").mkdir()
        (dst / "backup" / ".ssb-dst").touch()

        config, sync = self._make_config(src, dst)
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=config.volumes["src"],
                reasons=[],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                reasons=[],
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.SOURCE_MARKER_NOT_FOUND in status.reasons

    def _setup_active_markers(self, src: Path, dst: Path) -> None:
        (src / ".ssb-vol").touch()
        (dst / ".ssb-vol").touch()
        (src / "data").mkdir(exist_ok=True)
        (src / "data" / ".ssb-src").touch()
        (dst / "backup").mkdir(exist_ok=True)
        (dst / "backup" / ".ssb-dst").touch()

    def _make_active_vol_statuses(
        self, config: Config
    ) -> dict[str, VolumeStatus]:
        return {
            "src": VolumeStatus(
                name="src",
                config=config.volumes["src"],
                reasons=[],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                reasons=[],
            ),
        }

    @patch("ssb.checks.shutil.which", return_value=None)
    def test_rsync_not_found_on_source(
        self, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        self._setup_active_markers(src, dst)

        config, sync = self._make_config(src, dst)
        vol_statuses = self._make_active_vol_statuses(config)

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.RSYNC_NOT_FOUND_ON_SOURCE in status.reasons
        assert SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION in status.reasons

    @patch(
        "ssb.checks.shutil.which",
        side_effect=lambda cmd: ("/usr/bin/rsync" if cmd == "rsync" else None),
    )
    def test_rsync_found_btrfs_not_found_on_destination(
        self, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        self._setup_active_markers(src, dst)

        src_vol = LocalVolume(name="src", path=str(src))
        dst_vol = LocalVolume(name="dst", path=str(dst))
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume_name="dst",
                subdir="backup",
                btrfs_snapshots=True,
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = self._make_active_vol_statuses(config)

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.BTRFS_NOT_FOUND_ON_DESTINATION in status.reasons

    @patch("ssb.checks.shutil.which", return_value="/usr/bin/rsync")
    def test_btrfs_check_skipped_when_not_enabled(
        self, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        self._setup_active_markers(src, dst)

        config, sync = self._make_config(src, dst)
        vol_statuses = self._make_active_vol_statuses(config)

        status = check_sync(sync, config, vol_statuses)
        assert status.active is True
        assert status.reasons == []

    @patch("ssb.checks.shutil.which", return_value=None)
    def test_multiple_failures_accumulated(
        self, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        """Source marker missing AND rsync missing on both sides."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / ".ssb-vol").touch()
        (dst / ".ssb-vol").touch()
        (src / "data").mkdir()
        # No .ssb-src marker
        (dst / "backup").mkdir()
        (dst / "backup" / ".ssb-dst").touch()

        config, sync = self._make_config(src, dst)
        vol_statuses = self._make_active_vol_statuses(config)

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.SOURCE_MARKER_NOT_FOUND in status.reasons
        assert SyncReason.RSYNC_NOT_FOUND_ON_SOURCE in status.reasons
        assert SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION in status.reasons

    def test_both_volumes_unavailable(self, tmp_path: Path) -> None:
        """Both source and destination unavailable."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        config, sync = self._make_config(src, dst)
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=config.volumes["src"],
                reasons=[VolumeReason.MARKER_NOT_FOUND],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                reasons=[VolumeReason.MARKER_NOT_FOUND],
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.SOURCE_UNAVAILABLE in status.reasons
        assert SyncReason.DESTINATION_UNAVAILABLE in status.reasons


class TestCheckSyncRemoteCommands:
    @patch("ssb.checks.run_remote_command")
    def test_rsync_not_found_on_remote_source(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        dst = tmp_path / "dst"
        dst.mkdir()
        (dst / ".ssb-vol").touch()
        (dst / "backup").mkdir()
        (dst / "backup" / ".ssb-dst").touch()

        src_vol = RemoteVolume(name="src", host="src.local", path="/data")
        dst_vol = LocalVolume(name="dst", path=str(dst))
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume_name="dst", subdir="backup"
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=src_vol,
                reasons=[],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=dst_vol,
                reasons=[],
            ),
        }

        def remote_side_effect(vol: RemoteVolume, cmd: str) -> MagicMock:
            if cmd == "test -f /data/data/.ssb-src":
                return MagicMock(returncode=0)
            if cmd == "which rsync":
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.RSYNC_NOT_FOUND_ON_SOURCE in status.reasons

    @patch("ssb.checks.run_remote_command")
    @patch("ssb.checks.shutil.which", return_value="/usr/bin/rsync")
    def test_rsync_not_found_on_remote_destination(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / ".ssb-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".ssb-src").touch()

        src_vol = LocalVolume(name="src", path=str(src))
        dst_vol = RemoteVolume(name="dst", host="dst.local", path="/backup")
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume_name="dst", subdir="backup"
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=src_vol,
                reasons=[],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=dst_vol,
                reasons=[],
            ),
        }

        def remote_side_effect(vol: RemoteVolume, cmd: str) -> MagicMock:
            if cmd == "test -f /backup/backup/.ssb-dst":
                return MagicMock(returncode=0)
            if cmd == "which rsync":
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION in status.reasons

    @patch("ssb.checks.run_remote_command")
    @patch("ssb.checks.shutil.which", return_value="/usr/bin/rsync")
    def test_btrfs_not_found_on_remote_destination(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / ".ssb-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".ssb-src").touch()

        src_vol = LocalVolume(name="src", path=str(src))
        dst_vol = RemoteVolume(name="dst", host="dst.local", path="/backup")
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume_name="dst",
                subdir="backup",
                btrfs_snapshots=True,
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=src_vol,
                reasons=[],
            ),
            "dst": VolumeStatus(
                name="dst",
                config=dst_vol,
                reasons=[],
            ),
        }

        def remote_side_effect(vol: RemoteVolume, cmd: str) -> MagicMock:
            if cmd == "test -f /backup/backup/.ssb-dst":
                return MagicMock(returncode=0)
            if cmd == "which rsync":
                return MagicMock(returncode=0)
            if cmd == "which btrfs":
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.BTRFS_NOT_FOUND_ON_DESTINATION in status.reasons


class TestCheckAllSyncs:
    @patch("ssb.checks.shutil.which", return_value="/usr/bin/rsync")
    def test_check_all(self, mock_which: MagicMock, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / ".ssb-vol").touch()
        (dst / ".ssb-vol").touch()
        (src / ".ssb-src").touch()
        (dst / ".ssb-dst").touch()

        src_vol = LocalVolume(name="src", path=str(src))
        dst_vol = LocalVolume(name="dst", path=str(dst))
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src"),
            destination=DestinationSyncEndpoint(volume_name="dst"),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )

        vol_statuses, sync_statuses = check_all_syncs(config)
        assert vol_statuses["src"].active is True
        assert vol_statuses["dst"].active is True
        assert sync_statuses["s1"].active is True
