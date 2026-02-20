"""Tests for dab.status and dab.output."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from dab.config import (
    BtrfsSnapshotConfig,
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)
from dab.output import OutputFormat
from dab.runner import SyncResult
from dab.status import (
    SyncReason,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
    _check_btrfs_filesystem,
    _check_btrfs_mount_option,
    _check_btrfs_subvolume,
    _check_command_available,
    check_all_syncs,
    check_sync,
    check_volume,
)


class TestLocalVolume:
    def test_construction(self) -> None:
        vol = LocalVolume(slug="data", path="/mnt/data")
        assert vol.slug == "data"
        assert vol.path == "/mnt/data"

    def test_frozen(self) -> None:
        import pydantic

        vol = LocalVolume(slug="data", path="/mnt/data")
        try:
            vol.slug = "other"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError, pydantic.ValidationError:
            pass


class TestRsyncServer:
    def test_construction_defaults(self) -> None:
        server = RsyncServer(slug="nas-server", host="nas.local")
        assert server.slug == "nas-server"
        assert server.host == "nas.local"
        assert server.port == 22
        assert server.user is None
        assert server.ssh_key is None
        assert server.ssh_options == []
        assert server.connect_timeout == 10

    def test_construction_full(self) -> None:
        server = RsyncServer(
            slug="nas-server",
            host="nas.local",
            port=2222,
            user="backup",
            ssh_key="~/.ssh/id_rsa",
            connect_timeout=30,
        )
        assert server.port == 2222
        assert server.user == "backup"
        assert server.ssh_key == "~/.ssh/id_rsa"
        assert server.connect_timeout == 30


class TestRemoteVolume:
    def test_construction(self) -> None:
        vol = RemoteVolume(
            slug="nas",
            rsync_server="nas-server",
            path="/backup",
        )
        assert vol.slug == "nas"
        assert vol.rsync_server == "nas-server"
        assert vol.path == "/backup"

    def test_frozen(self) -> None:
        import pydantic

        vol = RemoteVolume(
            slug="nas",
            rsync_server="nas-server",
            path="/backup",
        )
        try:
            vol.path = "other"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError, pydantic.ValidationError:
            pass


class TestSyncEndpoint:
    def test_construction_defaults(self) -> None:
        ep = SyncEndpoint(volume="data")
        assert ep.volume == "data"
        assert ep.subdir is None

    def test_construction_with_subdir(self) -> None:
        ep = SyncEndpoint(volume="data", subdir="photos")
        assert ep.subdir == "photos"


class TestSyncConfig:
    def test_construction_defaults(self) -> None:
        sc = SyncConfig(
            slug="sync1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        assert sc.slug == "sync1"
        assert sc.enabled is True
        assert sc.destination.btrfs_snapshots.enabled is False
        assert sc.rsync_options is None
        assert sc.extra_rsync_options == []
        assert sc.filters == []
        assert sc.filter_file is None

    def test_construction_full(self) -> None:
        sc = SyncConfig(
            slug="sync1",
            source=SyncEndpoint(volume="src", subdir="a"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="b",
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
            ),
            enabled=False,
            rsync_options=["-a", "--delete"],
            extra_rsync_options=["--compress"],
            filters=["+ *.jpg", "- *.tmp"],
            filter_file="/etc/dab/filters.rules",
        )
        assert sc.enabled is False
        assert sc.destination.btrfs_snapshots.enabled is True
        assert sc.rsync_options == ["-a", "--delete"]
        assert sc.extra_rsync_options == ["--compress"]
        assert sc.filters == ["+ *.jpg", "- *.tmp"]
        assert sc.filter_file == "/etc/dab/filters.rules"


class TestConfig:
    def test_empty(self) -> None:
        cfg = Config()
        assert cfg.volumes == {}
        assert cfg.syncs == {}

    def test_with_data(self) -> None:
        vol = LocalVolume(slug="data", path="/mnt/data")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="data"),
            destination=DestinationSyncEndpoint(volume="data"),
        )
        cfg = Config(
            volumes={"data": vol},
            syncs={"s1": sync},
        )
        assert "data" in cfg.volumes
        assert "s1" in cfg.syncs


class TestVolumeStatus:
    def test_construction_active(self) -> None:
        vol = LocalVolume(slug="data", path="/mnt/data")
        vs = VolumeStatus(
            slug="data",
            config=vol,
            reasons=[],
        )
        assert vs.active is True

    def test_construction_inactive(self) -> None:
        vol = LocalVolume(slug="data", path="/mnt/data")
        vs = VolumeStatus(
            slug="data",
            config=vol,
            reasons=[VolumeReason.MARKER_NOT_FOUND],
        )
        assert vs.active is False


class TestSyncStatus:
    def test_construction_active(self) -> None:
        vol = LocalVolume(slug="data", path="/mnt/data")
        vs = VolumeStatus(
            slug="data",
            config=vol,
            reasons=[],
        )
        sc = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="data"),
            destination=DestinationSyncEndpoint(volume="data"),
        )
        ss = SyncStatus(
            slug="s1",
            config=sc,
            source_status=vs,
            destination_status=vs,
            reasons=[],
        )
        assert ss.active is True

    def test_construction_inactive(self) -> None:
        vol = LocalVolume(slug="data", path="/mnt/data")
        vs = VolumeStatus(
            slug="data",
            config=vol,
            reasons=[],
        )
        sc = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="data"),
            destination=DestinationSyncEndpoint(volume="data"),
        )
        ss = SyncStatus(
            slug="s1",
            config=sc,
            source_status=vs,
            destination_status=vs,
            reasons=[SyncReason.DISABLED],
        )
        assert ss.active is False


class TestSyncResult:
    def test_construction_defaults(self) -> None:
        sr = SyncResult(
            sync_slug="s1",
            success=True,
            dry_run=False,
            rsync_exit_code=0,
            output="done",
        )
        assert sr.snapshot_path is None
        assert sr.error is None

    def test_construction_full(self) -> None:
        sr = SyncResult(
            sync_slug="s1",
            success=False,
            dry_run=False,
            rsync_exit_code=1,
            output="",
            error="failed",
            snapshot_path="/snap/2024",
        )
        assert sr.error == "failed"
        assert sr.snapshot_path == "/snap/2024"


class TestSlugValidation:
    def test_valid_simple(self) -> None:
        vol = LocalVolume(slug="data", path="/mnt/data")
        assert vol.slug == "data"

    def test_valid_kebab_case(self) -> None:
        vol = LocalVolume(slug="my-usb-drive", path="/mnt")
        assert vol.slug == "my-usb-drive"

    def test_valid_with_numbers(self) -> None:
        vol = LocalVolume(slug="nas2", path="/mnt")
        assert vol.slug == "nas2"

    def test_invalid_uppercase(self) -> None:
        import pytest

        with pytest.raises(Exception):
            LocalVolume(slug="MyDrive", path="/mnt")

    def test_invalid_underscore(self) -> None:
        import pytest

        with pytest.raises(Exception):
            LocalVolume(slug="my_drive", path="/mnt")

    def test_invalid_spaces(self) -> None:
        import pytest

        with pytest.raises(Exception):
            LocalVolume(slug="my drive", path="/mnt")

    def test_invalid_trailing_hyphen(self) -> None:
        import pytest

        with pytest.raises(Exception):
            LocalVolume(slug="drive-", path="/mnt")

    def test_invalid_leading_hyphen(self) -> None:
        import pytest

        with pytest.raises(Exception):
            LocalVolume(slug="-drive", path="/mnt")

    def test_invalid_empty(self) -> None:
        import pytest

        with pytest.raises(Exception):
            LocalVolume(slug="", path="/mnt")

    def test_invalid_too_long(self) -> None:
        import pytest

        with pytest.raises(Exception):
            LocalVolume(slug="a" * 51, path="/mnt")

    def test_valid_max_length(self) -> None:
        vol = LocalVolume(slug="a" * 50, path="/mnt")
        assert len(vol.slug) == 50


class TestOutputFormat:
    def test_values(self) -> None:
        assert OutputFormat.HUMAN.value == "human"
        assert OutputFormat.JSON.value == "json"


# --- Check function tests (moved from test_checks.py) ---


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
        (tmp_path / ".dab-vol").touch()
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
    @patch("dab.status.run_remote_command")
    def test_active(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol, config = _remote_config()
        status = check_volume(vol, config)
        assert status.active is True
        assert status.reasons == []
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server, ["test", "-f", "/backup/.dab-vol"]
        )

    @patch("dab.status.run_remote_command")
    def test_inactive(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        vol, config = _remote_config()
        status = check_volume(vol, config)
        assert status.active is False
        assert status.reasons == [VolumeReason.UNREACHABLE]


class TestCheckCommandAvailableLocal:
    @patch("dab.status.shutil.which")
    def test_command_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/bin/rsync"
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_command_available(vol, "rsync", config) is True
        mock_which.assert_called_once_with("rsync")

    @patch("dab.status.shutil.which")
    def test_command_not_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_command_available(vol, "rsync", config) is False
        mock_which.assert_called_once_with("rsync")


class TestCheckCommandAvailableRemote:
    @patch("dab.status.run_remote_command")
    def test_command_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol, config = _remote_config()
        assert _check_command_available(vol, "rsync", config) is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(server, ["which", "rsync"])

    @patch("dab.status.run_remote_command")
    def test_command_not_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        vol, config = _remote_config()
        assert _check_command_available(vol, "btrfs", config) is False
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(server, ["which", "btrfs"])


class TestCheckBtrfsFilesystemLocal:
    @patch("dab.status.subprocess.run")
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

    @patch("dab.status.subprocess.run")
    def test_not_btrfs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ext2/ext3\n")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_filesystem(vol, config) is False

    @patch("dab.status.subprocess.run")
    def test_stat_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_filesystem(vol, config) is False


class TestCheckBtrfsFilesystemRemote:
    @patch("dab.status.run_remote_command")
    def test_btrfs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="btrfs\n")
        vol, config = _remote_config()
        assert _check_btrfs_filesystem(vol, config) is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["stat", "-f", "-c", "%T", "/backup"],
        )

    @patch("dab.status.run_remote_command")
    def test_not_btrfs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="ext2/ext3\n")
        vol, config = _remote_config()
        assert _check_btrfs_filesystem(vol, config) is False


class TestCheckBtrfsSubvolumeLocal:
    @patch("dab.status.subprocess.run")
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

    @patch("dab.status.subprocess.run")
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

    @patch("dab.status.subprocess.run")
    def test_not_subvolume(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="1234\n")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_subvolume(vol, None, config) is False

    @patch("dab.status.subprocess.run")
    def test_stat_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert _check_btrfs_subvolume(vol, None, config) is False


class TestCheckBtrfsSubvolumeRemote:
    @patch("dab.status.run_remote_command")
    def test_is_subvolume(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="256\n")
        vol, config = _remote_config()
        assert _check_btrfs_subvolume(vol, None, config) is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["stat", "-c", "%i", "/backup"],
        )

    @patch("dab.status.run_remote_command")
    def test_is_subvolume_with_subdir(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="256\n")
        vol, config = _remote_config()
        assert _check_btrfs_subvolume(vol, "data", config) is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["stat", "-c", "%i", "/backup/data"],
        )

    @patch("dab.status.run_remote_command")
    def test_not_subvolume(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="1234\n")
        vol, config = _remote_config()
        assert _check_btrfs_subvolume(vol, None, config) is False


class TestCheckBtrfsMountOptionLocal:
    @patch("dab.status.subprocess.run")
    def test_option_present(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="rw,relatime,user_subvol_rm_allowed\n",
        )
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert (
            _check_btrfs_mount_option(vol, "user_subvol_rm_allowed", config)
            is True
        )
        mock_run.assert_called_once_with(
            ["findmnt", "-n", "-o", "OPTIONS", "/mnt/data"],
            capture_output=True,
            text=True,
        )

    @patch("dab.status.subprocess.run")
    def test_option_missing(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="rw,relatime\n")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert (
            _check_btrfs_mount_option(vol, "user_subvol_rm_allowed", config)
            is False
        )

    @patch("dab.status.subprocess.run")
    def test_findmnt_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        vol = LocalVolume(slug="data", path="/mnt/data")
        config = Config(volumes={"data": vol})
        assert (
            _check_btrfs_mount_option(vol, "user_subvol_rm_allowed", config)
            is False
        )


class TestCheckBtrfsMountOptionRemote:
    @patch("dab.status.run_remote_command")
    def test_option_present(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="rw,relatime,user_subvol_rm_allowed\n",
        )
        vol, config = _remote_config()
        assert (
            _check_btrfs_mount_option(vol, "user_subvol_rm_allowed", config)
            is True
        )
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["findmnt", "-n", "-o", "OPTIONS", "/backup"],
        )

    @patch("dab.status.run_remote_command")
    def test_option_missing(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="rw,relatime\n")
        vol, config = _remote_config()
        assert (
            _check_btrfs_mount_option(vol, "user_subvol_rm_allowed", config)
            is False
        )


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
        "dab.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_active_sync(self, mock_which: MagicMock, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()

        (src / ".dab-vol").touch()
        (dst / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()
        (dst / "backup").mkdir()
        (dst / "backup" / ".dab-dst").touch()

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
        (dst / "backup" / ".dab-dst").touch()

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
        (src / ".dab-vol").touch()
        (dst / ".dab-vol").touch()
        (src / "data").mkdir(exist_ok=True)
        (src / "data" / ".dab-src").touch()
        (dst / "backup").mkdir(exist_ok=True)
        (dst / "backup" / ".dab-dst").touch()

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

    @patch("dab.status.shutil.which", return_value=None)
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
        "dab.status.shutil.which",
        side_effect=lambda cmd: (
            None if cmd == "btrfs" else f"/usr/bin/{cmd}"
        ),
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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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

    @patch(
        "dab.status.shutil.which",
        side_effect=lambda cmd: (None if cmd == "stat" else f"/usr/bin/{cmd}"),
    )
    def test_stat_not_found_on_destination(
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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = self._make_active_vol_statuses(config)

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.STAT_NOT_FOUND_ON_DESTINATION in status.reasons
        assert SyncReason.DESTINATION_NOT_BTRFS not in status.reasons
        assert SyncReason.DESTINATION_NOT_BTRFS_SUBVOLUME not in status.reasons

    @patch("dab.status.subprocess.run")
    @patch(
        "dab.status.shutil.which",
        side_effect=lambda cmd: (
            None if cmd == "findmnt" else f"/usr/bin/{cmd}"
        ),
    )
    def test_findmnt_not_found_on_destination(
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
        (dst / "backup" / "latest").mkdir()
        (dst / "backup" / "snapshots").mkdir()

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
                return MagicMock(returncode=0, stdout="256\n")
            return MagicMock(returncode=0)

        mock_subprocess.side_effect = subprocess_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.FINDMNT_NOT_FOUND_ON_DESTINATION in status.reasons
        assert (
            SyncReason.DESTINATION_NOT_MOUNTED_USER_SUBVOL_RM
            not in status.reasons
        )

    @patch(
        "dab.status.shutil.which",
        side_effect=lambda cmd: (
            None if cmd in ("stat", "findmnt") else f"/usr/bin/{cmd}"
        ),
    )
    def test_stat_and_findmnt_both_missing(
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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
            ),
        )
        config = Config(
            volumes={"src": src_vol, "dst": dst_vol},
            syncs={"s1": sync},
        )
        vol_statuses = self._make_active_vol_statuses(config)

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.STAT_NOT_FOUND_ON_DESTINATION in status.reasons
        assert SyncReason.FINDMNT_NOT_FOUND_ON_DESTINATION in status.reasons

    @patch("dab.status.subprocess.run")
    @patch(
        "dab.status.shutil.which",
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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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

    @patch("dab.status.subprocess.run")
    @patch(
        "dab.status.shutil.which",
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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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

    @patch("dab.status.subprocess.run")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/fake",
    )
    def test_destination_not_mounted_user_subvol_rm(
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
        (dst / "backup" / "latest").mkdir()
        (dst / "backup" / "snapshots").mkdir()

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
                return MagicMock(returncode=0, stdout="256\n")
            if cmd[0] == "findmnt":
                return MagicMock(returncode=0, stdout="rw,relatime\n")
            return MagicMock(returncode=0)

        mock_subprocess.side_effect = subprocess_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert (
            SyncReason.DESTINATION_NOT_MOUNTED_USER_SUBVOL_RM in status.reasons
        )

    @patch("dab.status.subprocess.run")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/fake",
    )
    def test_destination_latest_not_found(
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
        # snapshots exists but latest does not
        (dst / "backup" / "snapshots").mkdir()

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
                return MagicMock(returncode=0, stdout="256\n")
            if cmd[0] == "findmnt":
                return MagicMock(
                    returncode=0,
                    stdout="rw,user_subvol_rm_allowed\n",
                )
            return MagicMock(returncode=0)

        mock_subprocess.side_effect = subprocess_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_LATEST_NOT_FOUND in status.reasons
        assert (
            SyncReason.DESTINATION_SNAPSHOTS_DIR_NOT_FOUND
            not in status.reasons
        )

    @patch("dab.status.subprocess.run")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/fake",
    )
    def test_destination_snapshots_dir_not_found(
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
        # latest exists but snapshots does not
        (dst / "backup" / "latest").mkdir()

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
                return MagicMock(returncode=0, stdout="256\n")
            if cmd[0] == "findmnt":
                return MagicMock(
                    returncode=0,
                    stdout="rw,user_subvol_rm_allowed\n",
                )
            return MagicMock(returncode=0)

        mock_subprocess.side_effect = subprocess_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_SNAPSHOTS_DIR_NOT_FOUND in status.reasons
        assert SyncReason.DESTINATION_LATEST_NOT_FOUND not in status.reasons

    @patch("dab.status.subprocess.run")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/fake",
    )
    def test_destination_latest_and_snapshots_both_missing(
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
        # neither latest nor snapshots exist

        src_vol = LocalVolume(slug="src", path=str(src))
        dst_vol = LocalVolume(slug="dst", path=str(dst))
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="data"),
            destination=DestinationSyncEndpoint(
                volume="dst",
                subdir="backup",
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
                return MagicMock(returncode=0, stdout="256\n")
            if cmd[0] == "findmnt":
                return MagicMock(
                    returncode=0,
                    stdout="rw,user_subvol_rm_allowed\n",
                )
            return MagicMock(returncode=0)

        mock_subprocess.side_effect = subprocess_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_LATEST_NOT_FOUND in status.reasons
        assert SyncReason.DESTINATION_SNAPSHOTS_DIR_NOT_FOUND in status.reasons

    @patch(
        "dab.status.shutil.which",
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

    @patch("dab.status.shutil.which", return_value=None)
    def test_multiple_failures_accumulated(
        self, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        """Source marker missing AND rsync missing on both sides."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / ".dab-vol").touch()
        (dst / ".dab-vol").touch()
        (src / "data").mkdir()
        # No .dab-src marker
        (dst / "backup").mkdir()
        (dst / "backup" / ".dab-dst").touch()

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
    @patch("dab.status.run_remote_command")
    def test_rsync_not_found_on_remote_source(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        dst = tmp_path / "dst"
        dst.mkdir()
        (dst / ".dab-vol").touch()
        (dst / "backup").mkdir()
        (dst / "backup" / ".dab-dst").touch()

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
            if cmd == ["test", "-f", "/data/data/.dab-src"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.RSYNC_NOT_FOUND_ON_SOURCE in status.reasons

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
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
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.RSYNC_NOT_FOUND_ON_DESTINATION in status.reasons

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
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
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
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

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
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
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == [
                "stat",
                "-f",
                "-c",
                "%T",
                "/backup",
            ]:
                return MagicMock(returncode=0, stdout="ext2/ext3\n")
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_NOT_BTRFS in status.reasons

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
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
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == [
                "stat",
                "-f",
                "-c",
                "%T",
                "/backup",
            ]:
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

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_destination_not_mounted_user_subvol_rm_on_remote(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == [
                "stat",
                "-f",
                "-c",
                "%T",
                "/backup",
            ]:
                return MagicMock(returncode=0, stdout="btrfs\n")
            if cmd == [
                "stat",
                "-c",
                "%i",
                "/backup/backup",
            ]:
                return MagicMock(returncode=0, stdout="256\n")
            if cmd == [
                "findmnt",
                "-n",
                "-o",
                "OPTIONS",
                "/backup",
            ]:
                return MagicMock(returncode=0, stdout="rw,relatime\n")
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert (
            SyncReason.DESTINATION_NOT_MOUNTED_USER_SUBVOL_RM in status.reasons
        )

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_stat_not_found_on_remote_destination(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "stat"]:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.STAT_NOT_FOUND_ON_DESTINATION in status.reasons
        assert SyncReason.DESTINATION_NOT_BTRFS not in status.reasons

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_findmnt_not_found_on_remote_destination(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "findmnt"]:
                return MagicMock(returncode=1)
            if cmd == [
                "stat",
                "-f",
                "-c",
                "%T",
                "/backup",
            ]:
                return MagicMock(returncode=0, stdout="btrfs\n")
            if cmd == [
                "stat",
                "-c",
                "%i",
                "/backup/backup",
            ]:
                return MagicMock(returncode=0, stdout="256\n")
            if cmd == ["test", "-d", "/backup/backup/latest"]:
                return MagicMock(returncode=0)
            if cmd == ["test", "-d", "/backup/backup/snapshots"]:
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.FINDMNT_NOT_FOUND_ON_DESTINATION in status.reasons
        assert (
            SyncReason.DESTINATION_NOT_MOUNTED_USER_SUBVOL_RM
            not in status.reasons
        )

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_destination_latest_not_found_on_remote(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == [
                "stat",
                "-f",
                "-c",
                "%T",
                "/backup",
            ]:
                return MagicMock(returncode=0, stdout="btrfs\n")
            if cmd == [
                "stat",
                "-c",
                "%i",
                "/backup/backup",
            ]:
                return MagicMock(returncode=0, stdout="256\n")
            if cmd == [
                "findmnt",
                "-n",
                "-o",
                "OPTIONS",
                "/backup",
            ]:
                return MagicMock(
                    returncode=0,
                    stdout="rw,user_subvol_rm_allowed\n",
                )
            if cmd == [
                "test",
                "-d",
                "/backup/backup/latest",
            ]:
                return MagicMock(returncode=1)
            if cmd == [
                "test",
                "-d",
                "/backup/backup/snapshots",
            ]:
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_LATEST_NOT_FOUND in status.reasons
        assert (
            SyncReason.DESTINATION_SNAPSHOTS_DIR_NOT_FOUND
            not in status.reasons
        )

    @patch("dab.status.run_remote_command")
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_destination_snapshots_dir_not_found_on_remote(
        self,
        mock_which: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / ".dab-vol").touch()
        (src / "data").mkdir()
        (src / "data" / ".dab-src").touch()

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
                btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
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
            if cmd == [
                "test",
                "-f",
                "/backup/backup/.dab-dst",
            ]:
                return MagicMock(returncode=0)
            if cmd == ["which", "rsync"]:
                return MagicMock(returncode=0)
            if cmd == ["which", "btrfs"]:
                return MagicMock(returncode=0)
            if cmd == [
                "stat",
                "-f",
                "-c",
                "%T",
                "/backup",
            ]:
                return MagicMock(returncode=0, stdout="btrfs\n")
            if cmd == [
                "stat",
                "-c",
                "%i",
                "/backup/backup",
            ]:
                return MagicMock(returncode=0, stdout="256\n")
            if cmd == [
                "findmnt",
                "-n",
                "-o",
                "OPTIONS",
                "/backup",
            ]:
                return MagicMock(
                    returncode=0,
                    stdout="rw,user_subvol_rm_allowed\n",
                )
            if cmd == [
                "test",
                "-d",
                "/backup/backup/latest",
            ]:
                return MagicMock(returncode=0)
            if cmd == [
                "test",
                "-d",
                "/backup/backup/snapshots",
            ]:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = remote_side_effect

        status = check_sync(sync, config, vol_statuses)
        assert status.active is False
        assert SyncReason.DESTINATION_SNAPSHOTS_DIR_NOT_FOUND in status.reasons
        assert SyncReason.DESTINATION_LATEST_NOT_FOUND not in status.reasons


class TestCheckAllSyncs:
    @patch(
        "dab.status.shutil.which",
        return_value="/usr/bin/rsync",
    )
    def test_check_all(self, mock_which: MagicMock, tmp_path: Path) -> None:
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / ".dab-vol").touch()
        (dst / ".dab-vol").touch()
        (src / ".dab-src").touch()
        (dst / ".dab-dst").touch()

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
    @patch("dab.status.run_remote_command")
    def test_active(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        vol, config = _remote_config(path="/my backup")
        status = check_volume(vol, config)
        assert status.active is True
        server = config.rsync_servers["nas-server"]
        mock_run.assert_called_once_with(
            server,
            ["test", "-f", "/my backup/.dab-vol"],
        )
