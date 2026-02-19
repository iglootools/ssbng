"""Tests for ssb.checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ssb.checks import (
    check_all_syncs,
    check_sync,
    check_volume,
)
from ssb.config import (
    Config,
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
        assert status.reason == VolumeReason.OK

    def test_inactive(self, tmp_path: Path) -> None:
        vol = LocalVolume(name="data", path=str(tmp_path))
        status = check_volume(vol)
        assert status.active is False
        assert status.reason == VolumeReason.MARKER_NOT_FOUND


class TestCheckRemoteVolume:
    @patch("ssb.checks.run_remote_command")
    def test_active(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol = RemoteVolume(name="nas", host="nas.local", path="/backup")
        status = check_volume(vol)
        assert status.active is True
        mock_run.assert_called_once_with(vol, "test -f /backup/.ssb-vol")

    @patch("ssb.checks.run_remote_command")
    def test_inactive(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        vol = RemoteVolume(name="nas", host="nas.local", path="/backup")
        status = check_volume(vol)
        assert status.active is False
        assert status.reason == VolumeReason.UNREACHABLE


class TestCheckSync:
    def _make_config(
        self, tmp_src: Path, tmp_dst: Path
    ) -> tuple[Config, SyncConfig]:
        src_vol = LocalVolume(name="src", path=str(tmp_src))
        dst_vol = LocalVolume(name="dst", path=str(tmp_dst))
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src", subdir="data"),
            destination=SyncEndpoint(volume_name="dst", subdir="backup"),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        return config, sync

    def test_active_sync(self, tmp_path: Path) -> None:
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
                active=True,
                reason=VolumeReason.OK,
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                active=True,
                reason=VolumeReason.OK,
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is True
        assert status.reason == SyncReason.OK

    def test_disabled_sync(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        config, _ = self._make_config(src, dst)
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="src", subdir="data"),
            destination=SyncEndpoint(volume_name="dst", subdir="backup"),
            enabled=False,
        )
        vol_statuses = {
            "src": VolumeStatus(
                name="src",
                config=config.volumes["src"],
                active=True,
                reason=VolumeReason.OK,
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                active=True,
                reason=VolumeReason.OK,
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert status.reason == SyncReason.DISABLED

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
                active=False,
                reason=VolumeReason.MARKER_NOT_FOUND,
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                active=True,
                reason=VolumeReason.OK,
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert status.reason == SyncReason.SOURCE_UNAVAILABLE

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
                active=True,
                reason=VolumeReason.OK,
            ),
            "dst": VolumeStatus(
                name="dst",
                config=config.volumes["dst"],
                active=True,
                reason=VolumeReason.OK,
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert status.reason == SyncReason.SOURCE_MARKER_NOT_FOUND


class TestCheckAllSyncs:
    def test_check_all(self, tmp_path: Path) -> None:
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
            destination=SyncEndpoint(volume_name="dst"),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )

        vol_statuses, sync_statuses = check_all_syncs(config)
        assert vol_statuses["src"].active is True
        assert vol_statuses["dst"].active is True
        assert sync_statuses["s1"].active is True
