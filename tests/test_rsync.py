"""Tests for nbkp.rsync."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from nbkp.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)
from nbkp.sync.rsync import build_rsync_command, run_rsync


class TestBuildRsyncCommandLocalToLocal:
    def test_basic(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
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
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "/mnt/src/photos/",
            "/mnt/dst/backup/latest/",
        ]

    def test_dry_run(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
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
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
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
            slug="nas-server",
            host="nas.local",
            port=5022,
            user="backup",
            ssh_key="~/.ssh/key",
        )
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = RemoteVolume(
            slug="dst",
            rsync_server="nas-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
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
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "-e",
            "ssh -p 5022 -i ~/.ssh/key",
            "/mnt/src/photos/",
            "backup@nas.local:/backup/photos/latest/",
        ]


class TestBuildRsyncCommandRemoteToLocal:
    def test_basic(self) -> None:
        server = RsyncServer(
            slug="server",
            host="server.local",
            user="admin",
        )
        src = RemoteVolume(
            slug="src",
            rsync_server="server",
            path="/data",
        )
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
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
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "-e",
            "ssh",
            "admin@server.local:/data/",
            "/mnt/dst/backup/latest/",
        ]


class TestBuildRsyncCommandRemoteToRemote:
    def test_basic(self) -> None:
        src_server = RsyncServer(
            slug="src-server",
            host="src.local",
            port=2222,
            user="srcuser",
        )
        dst_server = RsyncServer(
            slug="dst-server",
            host="dst.local",
            user="dstuser",
            ssh_key="~/.ssh/dst_key",
        )
        src = RemoteVolume(
            slug="src",
            rsync_server="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
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
        assert inner.startswith("rsync -a --delete")
        assert "--delete-excluded" in inner
        assert "--safe-links" in inner
        assert "-e 'ssh -p 2222'" in inner
        assert "srcuser@src.local:/data/photos/" in inner
        assert "/backup/photos/latest/" in inner

    def test_dry_run(self) -> None:
        src_server = RsyncServer(slug="src-server", host="src.local")
        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            rsync_server="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
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


class TestBuildRsyncCommandFilters:
    def test_inline_filters(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            filters=["+ *.jpg", "- *.tmp"],
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "--filter=+ *.jpg",
            "--filter=- *.tmp",
            "/mnt/src/",
            "/mnt/dst/latest/",
        ]

    def test_filter_file(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            filter_file="/etc/nbkp/filters.rules",
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "--filter=merge /etc/nbkp/filters.rules",
            "/mnt/src/",
            "/mnt/dst/latest/",
        ]

    def test_filters_and_filter_file(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            filters=["+ *.jpg"],
            filter_file="/etc/nbkp/filters.rules",
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "--filter=+ *.jpg",
            "--filter=merge /etc/nbkp/filters.rules",
            "/mnt/src/",
            "/mnt/dst/latest/",
        ]

    def test_remote_to_remote_filters(self) -> None:
        src_server = RsyncServer(slug="src-server", host="src.local")
        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            rsync_server="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            filters=["+ *.jpg", "- *.tmp"],
            filter_file="/etc/nbkp/filters.rules",
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
        inner = cmd[-1]
        assert "'--filter=+ *.jpg'" in inner
        assert "'--filter=- *.tmp'" in inner
        assert "'--filter=merge /etc/nbkp/filters.rules'" in inner

    def test_no_filters(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert not any("--filter" in arg for arg in cmd)


class TestBuildRsyncCommandOptions:
    def test_override_rsync_options(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            rsync_options=["-a"],
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-a",
            "/mnt/src/",
            "/mnt/dst/latest/",
        ]

    def test_extra_rsync_options(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            extra_rsync_options=["--compress"],
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "--compress",
            "/mnt/src/",
            "/mnt/dst/latest/",
        ]

    def test_override_and_extra(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            rsync_options=["-a", "--delete"],
            extra_rsync_options=["--compress"],
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--compress",
            "/mnt/src/",
            "/mnt/dst/latest/",
        ]

    def test_remote_to_remote_override(self) -> None:
        src_server = RsyncServer(slug="src-server", host="src.local")
        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            rsync_server="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            rsync_options=["-a"],
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
        inner = cmd[-1]
        assert inner.startswith("rsync -a")
        assert "--delete" not in inner

    def test_remote_to_remote_extra(self) -> None:
        src_server = RsyncServer(slug="src-server", host="src.local")
        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            rsync_server="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            extra_rsync_options=["--compress"],
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
        inner = cmd[-1]
        assert "--compress" in inner
        assert inner.startswith(
            "rsync -a --delete --delete-excluded --safe-links" " --compress"
        )


class TestBuildRsyncCommandSpacesInPaths:
    def test_local_to_local_spaces(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/my src")
        dst = LocalVolume(slug="dst", path="/mnt/my dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="my photos"),
            destination=DestinationSyncEndpoint(
                volume="dst", subdir="my backup"
            ),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        cmd = build_rsync_command(sync, config)
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "/mnt/my src/my photos/",
            "/mnt/my dst/my backup/latest/",
        ]

    def test_remote_to_remote_spaces(self) -> None:
        src_server = RsyncServer(
            slug="src-server",
            host="src.local",
            port=2222,
            user="srcuser",
        )
        dst_server = RsyncServer(
            slug="dst-server",
            host="dst.local",
            user="dstuser",
        )
        src = RemoteVolume(
            slug="src",
            rsync_server="src-server",
            path="/my data",
        )
        dst = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/my backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="my photos"),
            destination=DestinationSyncEndpoint(
                volume="dst", subdir="my dest"
            ),
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
        inner = cmd[-1]
        # Paths with spaces must be shlex-quoted
        assert "'srcuser@src.local:/my data/my photos/'" in inner
        assert "'/my backup/my dest/latest/'" in inner


class TestBuildRsyncCommandVerbose:
    def _simple_config(self) -> tuple[SyncConfig, Config]:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        return sync, config

    def test_no_verbose(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config)
        assert "-v" not in cmd
        assert "-vv" not in cmd
        assert "-vvv" not in cmd

    def test_verbose_1(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config, verbose=1)
        assert "-v" in cmd

    def test_verbose_2(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config, verbose=2)
        assert "-vv" in cmd

    def test_verbose_3(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config, verbose=3)
        assert "-vvv" in cmd

    def test_verbose_clamped_to_3(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config, verbose=5)
        assert "-vvv" in cmd

    def test_remote_to_remote_verbose(self) -> None:
        src_server = RsyncServer(slug="src-server", host="src.local")
        dst_server = RsyncServer(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            rsync_server="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            rsync_server="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
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

        cmd = build_rsync_command(sync, config, verbose=2)
        inner = cmd[-1]
        assert "-vv" in inner


class TestRunRsync:
    @patch("nbkp.sync.rsync.subprocess.run")
    def test_run_rsync(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="done", stderr=""
        )
        src = LocalVolume(slug="src", path="/src")
        dst = LocalVolume(slug="dst", path="/dst")
        sync = SyncConfig(
            slug="s1",
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

    @patch("nbkp.sync.rsync.subprocess.Popen")
    def test_run_rsync_streams_output(self, mock_popen: MagicMock) -> None:
        src = LocalVolume(slug="src", path="/src")
        dst = LocalVolume(slug="dst", path="/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )

        streamed = "sending incremental file list\r\nfile.txt\n"
        proc = MagicMock()
        proc.stdout = io.StringIO(streamed)
        proc.poll.side_effect = lambda: (
            0 if proc.stdout.tell() == len(streamed) else None
        )
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        chunks: list[str] = []
        result = run_rsync(sync, config, on_output=chunks.append)

        assert result.returncode == 0
        assert result.stdout == streamed
        assert "".join(chunks) == streamed
        mock_popen.assert_called_once()
