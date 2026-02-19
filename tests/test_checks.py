"""Tests for ssb.status check functions."""

from __future__ import annotations

from pathlib import Path
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
    VolumeReason,
    VolumeStatus,
    _check_btrfs_filesystem,
    _check_btrfs_subvolume,
    _check_command_available,
    check_all_syncs,
    check_sync,
    check_volume,
)


def _remote_config(
    vol_name: str = "nas",
    server_name: str = "nas-server",
    host: str = "nas.local",
    path: str = "/backup",
) -> tuple[RemoteVolume, Config]:
    server = RsyncServer(slug=server_name, host=host)
    vol = RemoteVolume(
        slug=vol_name,
        rsync_server=server_name,
        path=path,
    )
    config = Config(
        rsync_servers={server_name: server},
        volumes={vol_name: vol},
    )
    return vol, config


class TestCheckLocalVolume:
    def test_active(self, tmp_path: Path) -> None:
        vol = LocalVolume(slug="data", path=str(tmp_path))
        (tmp_path / ".ssb-vol").touch()
        config = Config(volumes={"data": vol})
        status = check_volume(vol, config)
        assert status.active is True
        assert status.reasons == []

    def test_inactive(self, tmp_path: Path) -> None:
        vol = LocalVolume(slug="data", path=str(tmp_path))
        config = Config(volumes={"data": vol})
        status = check_volume(vol, config)
        assert status.active is False
        assert status.reasons == [VolumeReason.MARKER_NOT_FOUND]


class TestCheckRemoteVolume:
    @patch("ssb.status.run_remote_command")
    def test_active(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol, config = _remote_config()
        status = check_volume(vol, config)
        assert status.active is True
        assert status.reasons == []
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server, ["test", "-f", "/backup/.ssb-vol"]
        )

    @patch("ssb.status.run_remote_command")
    def test_inactive(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        vol, config = _remote_config()
        status = check_volume(vol, config)
        assert status.active is False
        assert status.reasons == [VolumeReason.UNREACHABLE]


class TestCheckCommandAvailableLocal:
    @patch("ssb.status.shutil.which")
    def test_command_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/bin/rsync"
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_command_available(vol, "rsync", config) is True
        mock_which.assert_called_once_with("rsync")

    @patch("ssb.status.shutil.which")
    def test_command_not_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_command_available(vol, "rsync", config) is False
        mock_which.assert_called_once_with("rsync")


class TestCheckCommandAvailableRemote:
    @patch("ssb.status.run_remote_command")
    def test_command_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol, config = _remote_config()
        assert _check_command_available(vol, "rsync", config) is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(server, ["which", "rsync"])

    @patch("ssb.status.run_remote_command")
    def test_command_not_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        vol, config = _remote_config()
        assert _check_command_available(vol, "btrfs", config) is False
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(server, ["which", "btrfs"])


class TestCheckBtrfsFilesystemLocal:
    @patch("ssb.status.subprocess.run")
    def test_btrfs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="btrfs\n")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_filesystem(vol, config) is True
        mock_run.assert_called_once_with(
            ["stat", "-f", "-c", "%T", "/mnt/data"],
            capture_output=True,
            text=True,
        )

    @patch("ssb.status.subprocess.run")
    def test_not_btrfs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ext2/ext3\n")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_filesystem(vol, config) is False

    @patch("ssb.status.subprocess.run")
    def test_stat_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_filesystem(vol, config) is False


class TestCheckBtrfsFilesystemRemote:
    @patch("ssb.status.run_remote_command")
    def test_btrfs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="btrfs\n")
        vol, config = _remote_config()
        assert _check_btrfs_filesystem(vol, config) is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["stat", "-f", "-c", "%T", "/backup"],
        )

    @patch("ssb.status.run_remote_command")
    def test_not_btrfs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ext2/ext3\n")
        vol, config = _remote_config()
        assert _check_btrfs_filesystem(vol, config) is False


class TestCheckBtrfsSubvolumeLocal:
    @patch("ssb.status.subprocess.run")
    def test_is_subvolume(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="256\n")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_subvolume(vol, None, config) is True
        mock_run.assert_called_once_with(
            ["stat", "-c", "%i", "/mnt/data"],
            capture_output=True,
            text=True,
        )

    @patch("ssb.status.subprocess.run")
    def test_is_subvolume_with_subdir(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="256\n")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_subvolume(vol, "backup", config) is True
        mock_run.assert_called_once_with(
            ["stat", "-c", "%i", "/mnt/data/backup"],
            capture_output=True,
            text=True,
        )

    @patch("ssb.status.subprocess.run")
    def test_not_subvolume(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="1234\n")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_subvolume(vol, None, config) is False

    @patch("ssb.status.subprocess.run")
    def test_stat_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_subvolume(vol, None, config) is False


class TestCheckBtrfsSubvolumeRemote:
    @patch("ssb.status.run_remote_command")
    def test_is_subvolume(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="256\n")
        vol, config = _remote_config()
        assert _check_btrfs_subvolume(vol, None, config) is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["stat", "-c", "%i", "/backup"],
        )

    @patch("ssb.status.run_remote_command")
    def test_is_subvolume_with_subdir(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="256\n")
        vol, config = _remote_config()
        assert _check_btrfs_subvolume(vol, "data", config) is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["stat", "-c", "%i", "/backup/data"],
        )

    @patch("ssb.status.run_remote_command")
    def test_not_subvolume(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="1234\n")
        vol, config = _remote_config()
        assert _check_btrfs_subvolume(vol, None, config) is False


class TestCheckSync:
    def _make_config(
        self, tmp_src: Path, tmp_dst: Path
    ) -> tuple[Config, SyncConfig]:
        src_vol = LocalVolume(slug="src", path=str(tmp_src))
        dst_vol = LocalVolume(slug="dst", path=str(tmp_dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="backup"),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        return config, sync

    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
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
                slug="src",
                config=config.volumes["src"],
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
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
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="backup"),
            enabled=False,
        )
        vol_statuses = {
            "src": VolumeStatus(
                slug="src",
                config=config.volumes["src"],
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
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
                slug="src",
                config=config.volumes["src"],
                reasons=[VolumeReason.MARKER_NOT_FOUND],
            ),
            "dst": VolumeStatus(
                slug="dst",
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
                slug="src",
                config=config.volumes["src"],
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
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
                slug="src",
                config=config.volumes["src"],
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
                config=config.volumes["dst"],
                reasons=[],
            ),
        }

    @patch("ssb.status.shutil.which", return_value=None)
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
        "ssb.status.shutil.which",
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

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
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

    @patch("ssb.status.subprocess.run")
    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/fake",
    )
    def test_destination_not_btrfs_filesystem(
        self,
        mock_which: MagicMock,
        mock_subprocess: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        self._setup_active_markers(src, dst)

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=True,
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = self._make_active_vol_statuses(config)

        mock_subprocess.return_value = MagicMock(
            returncode=0, stdout="ext2/ext3\n"
        )

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_NOT_BTRFS in status.reasons

    @patch("ssb.status.subprocess.run")
    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/fake",
    )
    def test_destination_not_btrfs_subvolume(
        self,
        mock_which: MagicMock,
        mock_subprocess: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        self._setup_active_markers(src, dst)

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=True,
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = self._make_active_vol_statuses(config)

        def subprocess_side_effect(
            cmd: list[str], **kwargs: object
        ) -> MagicMock:
            if cmd[:4] == ["stat", "-f", "-c", "%T"]:
                return MagicMock(returncode=0, stdout="btrfs\n")
            if cmd[:3] == ["stat", "-c", "%i"]:
                return MagicMock(returncode=0, stdout="1234\n")
            return MagicMock(returncode=0)

        mock_subprocess.side_effect = subprocess_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_NOT_BTRFS_SUBVOLUME in status.reasons

    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
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

    @patch("ssb.status.shutil.which", return_value=None)
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
                slug="src",
                config=config.volumes["src"],
                reasons=[VolumeReason.MARKER_NOT_FOUND],
            ),
            "dst": VolumeStatus(
                slug="dst",
                config=config.volumes["dst"],
                reasons=[VolumeReason.MARKER_NOT_FOUND],
            ),
        }

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.SOURCE_UNAVAILABLE in status.reasons
        assert SyncReason.DESTINATION_UNAVAILABLE in status.reasons


class TestCheckSyncRemoteCommands:
    @patch("ssb.status.run_remote_command")
    def test_rsync_not_found_on_remote_source(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        dst = tmp_path / "dst"
        dst.mkdir()
        (dst / ".ssb-vol").touch()
        (dst / "backup").mkdir()
        (dst / "backup" / ".ssb-dst").touch()

        src_server = RsyncServer(slug="src-server", host="src.local")
        src_vol = RemoteVolume(
            slug="src",
            rsync_server="src-server",
            path="/data",
        )
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="backup"),
        )
        config = Config(
            rsync_servers={"src-server": src_server},
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = {
            "src": VolumeStatus(
                slug="src",
                config=src_vol,
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
                config=dst_vol,
                reasons=[],
            ),
        }

        def remote_side_effect(
            server: RsyncServer, cmd: list[str]
        ) -> MagicMock:
            if cmd == ["test", "-f", "/data/data/.ssb-src"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.RSYNC_NOT_FOUND_ON_SOURCE in status.reasons

    @patch("ssb.status.run_remote_command")
    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
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

        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="backup"),
        )
        config = Config(
            rsync_servers={"dst-server": dst_server},
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = {
            "src": VolumeStatus(
                slug="src",
                config=src_vol,
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
                config=dst_vol,
                reasons=[],
            ),
        }

        def remote_side_effect(
            server: RsyncServer, cmd: list[str]
        ) -> MagicMock:
            if cmd == ["test", "-f", "/backup/backup/.ssb-dst"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION in status.reasons

    @patch("ssb.status.run_remote_command")
    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
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

        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=True,
            ),
        )
        config = Config(
            rsync_servers={"dst-server": dst_server},
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = {
            "src": VolumeStatus(
                slug="src",
                config=src_vol,
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
                config=dst_vol,
                reasons=[],
            ),
        }

        def remote_side_effect(
            server: RsyncServer, cmd: list[str]
        ) -> MagicMock:
            if cmd == ["test", "-f", "/backup/backup/.ssb-dst"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.BTRFS_NOT_FOUND_ON_DESTINATION in status.reasons

    @patch("ssb.status.run_remote_command")
    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_destination_not_btrfs_on_remote(
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

        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=True,
            ),
        )
        config = Config(
            rsync_servers={"dst-server": dst_server},
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = {
            "src": VolumeStatus(
                slug="src",
                config=src_vol,
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
                config=dst_vol,
                reasons=[],
            ),
        }

        def remote_side_effect(
            server: RsyncServer, cmd: list[str]
        ) -> MagicMock:
            if cmd == ["test", "-f", "/backup/backup/.ssb-dst"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == ["stat", "-f", "-c", "%T", "/backup"]:
                return MagicMock(returncode=0, stdout="ext2/ext3\n")
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_NOT_BTRFS in status.reasons

    @patch("ssb.status.run_remote_command")
    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_destination_not_subvolume_on_remote(
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

        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="backup"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=True,
            ),
        )
        config = Config(
            rsync_servers={"dst-server": dst_server},
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = {
            "src": VolumeStatus(
                slug="src",
                config=src_vol,
                reasons=[],
            ),
            "dst": VolumeStatus(
                slug="dst",
                config=dst_vol,
                reasons=[],
            ),
        }

        def remote_side_effect(
            server: RsyncServer, cmd: list[str]
        ) -> MagicMock:
            if cmd == ["test", "-f", "/backup/backup/.ssb-dst"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == ["stat", "-f", "-c", "%T", "/backup"]:
                return MagicMock(returncode=0, stdout="btrfs\n")
            if cmd == [
                "stat",
                "-c",
                "%i",
                "/backup/backup",
            ]:
                return MagicMock(returncode=0, stdout="1234\n")
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_NOT_BTRFS_SUBVOLUME in status.reasons


class TestCheckAllSyncs:
    @patch(
        "ssb.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_check_all(self, mock_which: MagicMock, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / ".ssb-vol").touch()
        (dst / ".ssb-vol").touch()
        (src / ".ssb-src").touch()
        (dst / ".ssb-dst").touch()

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )

        vol_statuses, sync_statuses = check_all_syncs(config)
        assert vol_statuses["src"].active is True
        assert vol_statuses["dst"].active is True
        assert sync_statuses["s1"].active is True


class TestCheckRemoteVolumeSpaces:
    @patch("ssb.status.run_remote_command")
    def test_active(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol, config = _remote_config(path="/my backup")
        status = check_volume(vol, config)
        assert status.active is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["test", "-f", "/my backup/.ssb-vol"],
        )
