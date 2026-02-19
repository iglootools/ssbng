"""Tests for ssb.status and ssb.output."""

from ssb.config import (
    Config,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    SyncEndpoint,
)
from ssb.output import OutputFormat
from ssb.status import (
    SyncReason,
    SyncResult,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
)


class TestLocalVolume:
    def test_construction(self) -> None:
        vol = LocalVolume(name="data", path="/mnt/data")
        assert vol.name == "data"
        assert vol.path == "/mnt/data"

    def test_frozen(self) -> None:
        import pydantic

        vol = LocalVolume(name="data", path="/mnt/data")
        try:
            vol.name = "other"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError, pydantic.ValidationError:
            pass


class TestRemoteVolume:
    def test_construction_defaults(self) -> None:
        vol = RemoteVolume(name="nas", host="nas.local", path="/backup")
        assert vol.name == "nas"
        assert vol.host == "nas.local"
        assert vol.path == "/backup"
        assert vol.port == 22
        assert vol.user is None
        assert vol.ssh_key is None
        assert vol.ssh_options == []

    def test_construction_full(self) -> None:
        vol = RemoteVolume(
            name="nas",
            host="nas.local",
            path="/backup",
            port=2222,
            user="backup",
            ssh_key="~/.ssh/id_rsa",
        )
        assert vol.port == 2222
        assert vol.user == "backup"
        assert vol.ssh_key == "~/.ssh/id_rsa"

    def test_frozen(self) -> None:
        import pydantic

        vol = RemoteVolume(name="nas", host="nas.local", path="/backup")
        try:
            vol.host = "other"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError, pydantic.ValidationError:
            pass


class TestSyncEndpoint:
    def test_construction_defaults(self) -> None:
        ep = SyncEndpoint(volume_name="data")
        assert ep.volume_name == "data"
        assert ep.subdir is None

    def test_construction_with_subdir(self) -> None:
        ep = SyncEndpoint(volume_name="data", subdir="photos")
        assert ep.subdir == "photos"


class TestSyncConfig:
    def test_construction_defaults(self) -> None:
        sc = SyncConfig(
            name="sync1",
            source=SyncEndpoint(volume_name="src"),
            destination=SyncEndpoint(volume_name="dst"),
        )
        assert sc.name == "sync1"
        assert sc.enabled is True
        assert sc.btrfs_snapshots is False

    def test_construction_full(self) -> None:
        sc = SyncConfig(
            name="sync1",
            source=SyncEndpoint(volume_name="src", subdir="a"),
            destination=SyncEndpoint(volume_name="dst", subdir="b"),
            enabled=False,
            btrfs_snapshots=True,
        )
        assert sc.enabled is False
        assert sc.btrfs_snapshots is True


class TestConfig:
    def test_empty(self) -> None:
        cfg = Config()
        assert cfg.volumes == {}
        assert cfg.syncs == {}

    def test_with_data(self) -> None:
        vol = LocalVolume(name="data", path="/mnt/data")
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="data"),
            destination=SyncEndpoint(volume_name="data"),
        )
        cfg = Config(
            volumes={"data": vol},
            syncs={"s1": sync},
        )
        assert "data" in cfg.volumes
        assert "s1" in cfg.syncs


class TestVolumeStatus:
    def test_construction(self) -> None:
        vol = LocalVolume(name="data", path="/mnt/data")
        vs = VolumeStatus(
            name="data",
            config=vol,
            active=True,
            reason=VolumeReason.OK,
        )
        assert vs.active is True
        assert vs.reason == VolumeReason.OK


class TestSyncStatus:
    def test_construction(self) -> None:
        vol = LocalVolume(name="data", path="/mnt/data")
        vs = VolumeStatus(
            name="data",
            config=vol,
            active=True,
            reason=VolumeReason.OK,
        )
        sc = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume_name="data"),
            destination=SyncEndpoint(volume_name="data"),
        )
        ss = SyncStatus(
            name="s1",
            config=sc,
            source_status=vs,
            destination_status=vs,
            active=True,
            reason=SyncReason.OK,
        )
        assert ss.active is True


class TestSyncResult:
    def test_construction_defaults(self) -> None:
        sr = SyncResult(
            sync_name="s1",
            success=True,
            dry_run=False,
            rsync_exit_code=0,
            output="done",
        )
        assert sr.snapshot_path is None
        assert sr.error is None

    def test_construction_full(self) -> None:
        sr = SyncResult(
            sync_name="s1",
            success=False,
            dry_run=False,
            rsync_exit_code=1,
            output="",
            error="failed",
            snapshot_path="/snap/2024",
        )
        assert sr.error == "failed"
        assert sr.snapshot_path == "/snap/2024"


class TestOutputFormat:
    def test_values(self) -> None:
        assert OutputFormat.HUMAN.value == "human"
        assert OutputFormat.JSON.value == "json"
