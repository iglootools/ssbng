"""Tests for ssb.status and ssb.output."""

from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)
from ssb.output import OutputFormat
from ssb.runner import SyncResult
from ssb.status import (
    SyncReason,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
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
        assert sc.destination.btrfs_snapshots is False
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
                btrfs_snapshots=True,
            ),
            enabled=False,
            rsync_options=["-a", "--delete"],
            extra_rsync_options=["--compress"],
            filters=["+ *.jpg", "- *.tmp"],
            filter_file="/etc/ssb/filters.rules",
        )
        assert sc.enabled is False
        assert sc.destination.btrfs_snapshots is True
        assert sc.rsync_options == ["-a", "--delete"]
        assert sc.extra_rsync_options == ["--compress"]
        assert sc.filters == ["+ *.jpg", "- *.tmp"]
        assert sc.filter_file == "/etc/ssb/filters.rules"


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
