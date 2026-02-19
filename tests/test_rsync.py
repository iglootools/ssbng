"""Tests for ssb.rsync."""

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
from ssb.rsync import build_rsync_command, run_rsync


class TestBuildRsyncCommandLocalToLocal:
    def test_basic(self) -> None:
        src = LocalVolume(name="src", path="/mnt/src")
        dst = LocalVolume(name="dst", path="/mnt/dst")
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume="src", subdir="photos"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="backup"),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-av",
            "--delete",
            "/mnt/src/photos/",
            "/mnt/dst/backup/latest/",
        ]

    def test_dry_run(self) -> None:
        src = LocalVolume(name="src", path="/mnt/src")
        dst = LocalVolume(name="dst", path="/mnt/dst")
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config, dry_run=True)
        assert "--dry-run" in cmd

    def test_link_dest(self) -> None:
        src = LocalVolume(name="src", path="/mnt/src")
        dst = LocalVolume(name="dst", path="/mnt/dst")
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(
            sync,
            config,
            link_dest="../../snapshots/20240101T000000Z",
        )
        assert "--link-dest=../../snapshots/20240101T000000Z" in cmd


class TestBuildRsyncCommandLocalToRemote:
    def test_basic(self) -> None:
        nas_server = RsyncServer(
            name="nas-server",
            host="nas.local",
            port=5022,
            user="backup",
            ssh_key="~/.ssh/key",
        )
        src = LocalVolume(name="src", path="/mnt/src")
        dst = RemoteVolume(
            name="dst",
            rsync_server="nas-server",
            path="/backup",
        )
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume="src", subdir="photos"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="photos"),
        )
        config = Config(
            rsync_servers={"nas-server": nas_server},
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-av",
            "--delete",
            "-e",
            "ssh -p 5022 -i ~/.ssh/key",
            "/mnt/src/photos/",
            "backup@nas.local:/backup/photos/latest/",
        ]


class TestBuildRsyncCommandRemoteToLocal:
    def test_basic(self) -> None:
        server = RsyncServer(
            name="server",
            host="server.local",
            user="admin",
        )
        src = RemoteVolume(
            name="src",
            rsync_server="server",
            path="/data",
        )
        dst = LocalVolume(name="dst", path="/mnt/dst")
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="backup"),
        )
        config = Config(
            rsync_servers={"server": server},
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-av",
            "--delete",
            "-e",
            "ssh",
            "admin@server.local:/data/",
            "/mnt/dst/backup/latest/",
        ]


class TestBuildRsyncCommandRemoteToRemote:
    def test_basic(self) -> None:
        src_server = RsyncServer(
            name="src-server",
            host="src.local",
            port=2222,
            user="srcuser",
        )
        dst_server = RsyncServer(
            name="dst-server",
            host="dst.local",
            user="dstuser",
            ssh_key="~/.ssh/dst_key",
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
            source=SyncEndpoint(volume="src", subdir="photos"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="photos"),
        )
        config = Config(
            rsync_servers={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)

        # Should SSH into destination host
        assert cmd[0] == "ssh"
        assert "dstuser@dst.local" in cmd

        # Inner command should be the last arg
        inner = cmd[-1]
        assert "rsync -av --delete" in inner
        assert "-e 'ssh -p 2222'" in inner
        assert "srcuser@src.local:/data/photos/" in inner
        assert "/backup/photos/latest/" in inner

    def test_dry_run(self) -> None:
        src_server = RsyncServer(name="src-server", host="src.local")
        dst_server = RsyncServer(name="dst-server", host="dst.local")
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
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            rsync_servers={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config, dry_run=True)
        inner = cmd[-1]
        assert "--dry-run" in inner


class TestRunRsync:
    @patch("ssb.rsync.subprocess.run")
    def test_run_rsync(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="done", stderr=""
        )
        src = LocalVolume(name="src", path="/src")
        dst = LocalVolume(name="dst", path="/dst")
        sync = SyncConfig(
            name="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        result = run_rsync(sync, config)
        assert result.returncode == 0
        mock_run.assert_called_once()
