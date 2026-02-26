"""Tests for nbkp.rsync."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from nbkp.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    SshEndpoint,
    SyncConfig,
    SyncEndpoint,
    resolve_all_endpoints,
)
from nbkp.sync.rsync import ProgressMode, build_rsync_command, run_rsync


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
        nas_server = SshEndpoint(
            slug="nas-server",
            host="nas.local",
            port=5022,
            user="backup",
            key="~/.ssh/key",
        )
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="nas-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="photos"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="photos"),
        )
        config = Config(
            ssh_endpoints={"nas-server": nas_server},
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "-e",
            "ssh -o ConnectTimeout=10 -o BatchMode=yes"
            " -p 5022 -i ~/.ssh/key",
            "/mnt/src/photos/",
            "backup@nas.local:/backup/photos/latest/",
        ]


class TestBuildRsyncCommandRemoteToLocal:
    def test_basic(self) -> None:
        server = SshEndpoint(
            slug="server",
            host="server.local",
            user="admin",
        )
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="server",
            path="/data",
        )
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="backup"),
        )
        config = Config(
            ssh_endpoints={"server": server},
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "-e",
            "ssh -o ConnectTimeout=10 -o BatchMode=yes",
            "admin@server.local:/data/",
            "/mnt/dst/backup/latest/",
        ]


class TestBuildRsyncCommandRemoteToRemote:
    def test_basic(self) -> None:
        src_server = SshEndpoint(
            slug="src-server",
            host="src.local",
            port=2222,
            user="srcuser",
        )
        dst_server = SshEndpoint(
            slug="dst-server",
            host="dst.local",
            user="dstuser",
            key="~/.ssh/dst_key",
        )
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src", subdir="photos"),
            destination=DestinationSyncEndpoint(volume="dst", subdir="photos"),
        )
        config = Config(
            ssh_endpoints={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)

        # Should SSH into destination host
        assert cmd[0] == "ssh"
        assert "dstuser@dst.local" in cmd

        # Inner command should be the last arg
        inner = cmd[-1]
        assert inner.startswith("rsync -a --delete")
        assert "--delete-excluded" in inner
        assert "--safe-links" in inner
        assert (
            "-e 'ssh -o ConnectTimeout=10"
            " -o BatchMode=yes -p 2222'" in inner
        )
        assert "srcuser@src.local:/data/photos/" in inner
        assert "/backup/photos/latest/" in inner

    def test_dry_run(self) -> None:
        src_server = SshEndpoint(slug="src-server", host="src.local")
        dst_server = SshEndpoint(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(
            sync, config, dry_run=True, resolved_endpoints=resolved
        )
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
        src_server = SshEndpoint(slug="src-server", host="src.local")
        dst_server = SshEndpoint(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
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
            ssh_endpoints={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
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
        src_server = SshEndpoint(slug="src-server", host="src.local")
        dst_server = SshEndpoint(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            rsync_options=["-a"],
        )
        config = Config(
            ssh_endpoints={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
        inner = cmd[-1]
        assert inner.startswith("rsync -a")
        assert "--delete" not in inner

    def test_remote_to_remote_extra(self) -> None:
        src_server = SshEndpoint(slug="src-server", host="src.local")
        dst_server = SshEndpoint(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            extra_rsync_options=["--compress"],
        )
        config = Config(
            ssh_endpoints={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
        inner = cmd[-1]
        assert "--compress" in inner
        assert inner.startswith(
            "rsync -a --delete --delete-excluded --safe-links" " --compress"
        )


class TestBuildRsyncCommandProxyJump:
    def test_local_to_remote_with_proxy(self) -> None:
        bastion = SshEndpoint(
            slug="bastion",
            host="bastion.example.com",
            port=2222,
            user="admin",
        )
        nas_server = SshEndpoint(
            slug="nas-server",
            host="nas.local",
            port=5022,
            user="backup",
            key="~/.ssh/key",
            proxy_jump="bastion",
        )
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="nas-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={
                "bastion": bastion,
                "nas-server": nas_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
        import shlex

        proxy_cmd = (
            "ssh -o ConnectTimeout=10 -o BatchMode=yes"
            " -p 2222"
            " -W %h:%p admin@bastion.example.com"
        )
        quoted = shlex.quote(f"ProxyCommand={proxy_cmd}")
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "-e",
            "ssh -o ConnectTimeout=10 -o BatchMode=yes"
            " -p 5022 -i ~/.ssh/key"
            f" -o {quoted}",
            "/mnt/src/",
            "backup@nas.local:/backup/latest/",
        ]

    def test_remote_to_local_with_proxy(self) -> None:
        bastion = SshEndpoint(
            slug="bastion",
            host="bastion.example.com",
            user="admin",
        )
        server = SshEndpoint(
            slug="server",
            host="server.internal",
            user="backup",
            proxy_jump="bastion",
        )
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="server",
            path="/data",
        )
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={
                "bastion": bastion,
                "server": server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
        import shlex

        proxy_cmd = (
            "ssh -o ConnectTimeout=10 -o BatchMode=yes"
            " -W %h:%p admin@bastion.example.com"
        )
        quoted = shlex.quote(f"ProxyCommand={proxy_cmd}")
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "-e",
            "ssh -o ConnectTimeout=10 -o BatchMode=yes" f" -o {quoted}",
            "backup@server.internal:/data/",
            "/mnt/dst/latest/",
        ]

    def test_remote_to_remote_with_proxy(self) -> None:
        bastion = SshEndpoint(
            slug="bastion",
            host="bastion.example.com",
            user="admin",
        )
        src_server = SshEndpoint(
            slug="src-server",
            host="src.internal",
            user="srcuser",
            proxy_jump="bastion",
        )
        dst_server = SshEndpoint(
            slug="dst-server",
            host="dst.internal",
            user="dstuser",
            proxy_jump="bastion",
        )
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={
                "bastion": bastion,
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)

        # Should SSH into destination host with proxy
        assert cmd[0] == "ssh"
        proxy_cmd = (
            "ssh -o ConnectTimeout=10 -o BatchMode=yes"
            " -W %h:%p admin@bastion.example.com"
        )
        assert f"ProxyCommand={proxy_cmd}" in cmd
        assert "dstuser@dst.internal" in cmd

        # Inner rsync should also have proxy for source
        inner = cmd[-1]
        assert "ProxyCommand=" in inner
        assert "admin@bastion.example.com" in inner


class TestBuildRsyncCommandMultiHopProxy:
    def test_local_to_remote_with_multi_hop_proxy(self) -> None:
        bastion1 = SshEndpoint(
            slug="bastion1",
            host="bastion1.example.com",
            user="admin",
        )
        bastion2 = SshEndpoint(
            slug="bastion2",
            host="bastion2.example.com",
            port=2222,
        )
        nas_server = SshEndpoint(
            slug="nas-server",
            host="nas.local",
            port=5022,
            user="backup",
            key="~/.ssh/key",
            proxy_jumps=["bastion1", "bastion2"],
        )
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="nas-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={
                "bastion1": bastion1,
                "bastion2": bastion2,
                "nas-server": nas_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
        import shlex

        inner = (
            "ssh -o ConnectTimeout=10 -o BatchMode=yes"
            " -W %%h:%%p admin@bastion1.example.com"
        )
        proxy_cmd = (
            "ssh -o ConnectTimeout=10 -o BatchMode=yes"
            f" -o ProxyCommand={inner}"
            " -p 2222"
            " -W %h:%p bastion2.example.com"
        )
        quoted = shlex.quote(f"ProxyCommand={proxy_cmd}")
        assert cmd == [
            "rsync",
            "-a",
            "--delete",
            "--delete-excluded",
            "--safe-links",
            "-e",
            "ssh -o ConnectTimeout=10 -o BatchMode=yes"
            " -p 5022 -i ~/.ssh/key"
            f" -o {quoted}",
            "/mnt/src/",
            "backup@nas.local:/backup/latest/",
        ]

    def test_remote_to_remote_with_multi_hop_proxy(
        self,
    ) -> None:
        bastion1 = SshEndpoint(
            slug="bastion1",
            host="bastion1.example.com",
            user="admin",
        )
        bastion2 = SshEndpoint(
            slug="bastion2",
            host="bastion2.example.com",
            port=2222,
        )
        src_server = SshEndpoint(
            slug="src-server",
            host="src.internal",
            user="srcuser",
            proxy_jumps=["bastion1", "bastion2"],
        )
        dst_server = SshEndpoint(
            slug="dst-server",
            host="dst.internal",
            user="dstuser",
            proxy_jumps=["bastion1", "bastion2"],
        )
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={
                "bastion1": bastion1,
                "bastion2": bastion2,
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)

        # Outer SSH into destination host with proxy chain
        assert cmd[0] == "ssh"
        assert any("ProxyCommand=" in arg for arg in cmd)
        assert "admin@bastion1.example.com" in str(cmd)
        assert "bastion2.example.com" in str(cmd)
        assert "dstuser@dst.internal" in cmd

        # Inner rsync should also have proxy chain for source
        inner = cmd[-1]
        assert "ProxyCommand=" in inner
        assert "admin@bastion1.example.com" in inner
        assert "bastion2.example.com" in inner


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
        src_server = SshEndpoint(
            slug="src-server",
            host="src.local",
            port=2222,
            user="srcuser",
        )
        dst_server = SshEndpoint(
            slug="dst-server",
            host="dst.local",
            user="dstuser",
        )
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/my data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
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
            ssh_endpoints={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(sync, config, resolved_endpoints=resolved)
        inner = cmd[-1]
        # Paths with spaces must be shlex-quoted
        assert "'srcuser@src.local:/my data/my photos/'" in inner
        assert "'/my backup/my dest/latest/'" in inner


class TestBuildRsyncCommandProgress:
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

    def test_no_progress(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config)
        assert "-v" not in cmd
        assert "--progress" not in cmd
        assert "--info=progress2" not in cmd
        assert "--stats" not in cmd
        assert "--human-readable" not in cmd

    def test_progress_none(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config, progress=ProgressMode.NONE)
        assert "-v" not in cmd
        assert "--progress" not in cmd
        assert "--info=progress2" not in cmd

    def test_progress_overall(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config, progress=ProgressMode.OVERALL)
        assert "--info=progress2" in cmd
        assert "--stats" in cmd
        assert "--human-readable" in cmd
        assert "-v" not in cmd
        assert "--progress" not in cmd

    def test_progress_per_file(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config, progress=ProgressMode.PER_FILE)
        assert "-v" in cmd
        assert "--progress" in cmd
        assert "--human-readable" in cmd
        assert "--info=progress2" not in cmd
        assert "--stats" not in cmd

    def test_progress_full(self) -> None:
        sync, config = self._simple_config()
        cmd = build_rsync_command(sync, config, progress=ProgressMode.FULL)
        assert "-v" in cmd
        assert "--progress" in cmd
        assert "--info=progress2" in cmd
        assert "--stats" in cmd
        assert "--human-readable" in cmd

    def test_remote_to_remote_progress(self) -> None:
        src_server = SshEndpoint(slug="src-server", host="src.local")
        dst_server = SshEndpoint(slug="dst-server", host="dst.local")
        src = RemoteVolume(
            slug="src",
            ssh_endpoint="src-server",
            path="/data",
        )
        dst = RemoteVolume(
            slug="dst",
            ssh_endpoint="dst-server",
            path="/backup",
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(
            sync,
            config,
            progress=ProgressMode.PER_FILE,
            resolved_endpoints=resolved,
        )
        inner = cmd[-1]
        assert "-v" in inner
        assert "--progress" in inner


class TestDestSuffix:
    def test_default_latest(self) -> None:
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
        assert cmd[-1] == "/mnt/dst/latest/"

    def test_custom_suffix(self) -> None:
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
            sync, config, dest_suffix="snapshots/2026-02-21T12:00:00.000Z"
        )
        assert cmd[-1] == "/mnt/dst/snapshots/2026-02-21T12:00:00.000Z/"

    def test_local_to_remote(self) -> None:
        server = SshEndpoint(slug="nas", host="nas.local", user="backup")
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = RemoteVolume(slug="dst", ssh_endpoint="nas", path="/backup")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={"nas": server},
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(
            sync,
            config,
            resolved_endpoints=resolved,
            dest_suffix="snapshots/T1",
        )
        assert cmd[-1] == "backup@nas.local:/backup/snapshots/T1/"

    def test_remote_to_local(self) -> None:
        server = SshEndpoint(slug="srv", host="srv.local", user="admin")
        src = RemoteVolume(slug="src", ssh_endpoint="srv", path="/data")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={"srv": server},
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(
            sync,
            config,
            resolved_endpoints=resolved,
            dest_suffix="snapshots/T1",
        )
        assert cmd[-1] == "/mnt/dst/snapshots/T1/"

    def test_remote_to_remote(self) -> None:
        src_server = SshEndpoint(slug="src-server", host="src.local")
        dst_server = SshEndpoint(slug="dst-server", host="dst.local")
        src = RemoteVolume(slug="src", ssh_endpoint="src-server", path="/data")
        dst = RemoteVolume(
            slug="dst", ssh_endpoint="dst-server", path="/backup"
        )
        sync = SyncConfig(
            slug="s1",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            ssh_endpoints={
                "src-server": src_server,
                "dst-server": dst_server,
            },
            volumes={"src": src, "dst": dst},
            syncs={"s1": sync},
        )
        resolved = resolve_all_endpoints(config)

        cmd = build_rsync_command(
            sync,
            config,
            resolved_endpoints=resolved,
            dest_suffix="snapshots/T1",
        )
        inner = cmd[-1]
        assert "/backup/snapshots/T1/" in inner


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
