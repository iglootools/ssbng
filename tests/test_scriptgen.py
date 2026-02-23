"""Tests for nbkp.scriptgen."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from nbkp.config import (
    BtrfsSnapshotConfig,
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    RsyncServer,
    SshOptions,
    SyncConfig,
    SyncEndpoint,
)
from nbkp.scriptgen import ScriptOptions, generate_script

_NOW = datetime(2026, 2, 21, 12, 0, 0, tzinfo=timezone.utc)
_OPTIONS = ScriptOptions(config_path="/etc/nbkp/config.yaml")


def _local_to_local_config() -> Config:
    src = LocalVolume(slug="src", path="/mnt/src")
    dst = LocalVolume(slug="dst", path="/mnt/dst")
    sync = SyncConfig(
        slug="my-sync",
        source=SyncEndpoint(volume="src", subdir="photos"),
        destination=DestinationSyncEndpoint(volume="dst", subdir="backup"),
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"my-sync": sync},
    )


def _local_to_remote_config() -> Config:
    src = LocalVolume(slug="src", path="/mnt/data")
    server = RsyncServer(
        slug="nas",
        host="nas.example.com",
        port=5022,
        user="backup",
        ssh_key="~/.ssh/nas_ed25519",
    )
    dst = RemoteVolume(
        slug="nas-vol",
        rsync_server="nas",
        path="/volume1/backups",
    )
    sync = SyncConfig(
        slug="photos-to-nas",
        source=SyncEndpoint(volume="src", subdir="photos"),
        destination=DestinationSyncEndpoint(
            volume="nas-vol", subdir="photos-backup"
        ),
    )
    return Config(
        rsync_servers={"nas": server},
        volumes={"src": src, "nas-vol": dst},
        syncs={"photos-to-nas": sync},
    )


def _remote_to_local_config() -> Config:
    server = RsyncServer(
        slug="remote",
        host="remote.example.com",
        user="admin",
    )
    src = RemoteVolume(
        slug="remote-vol",
        rsync_server="remote",
        path="/data",
    )
    dst = LocalVolume(slug="local", path="/mnt/backup")
    sync = SyncConfig(
        slug="pull-data",
        source=SyncEndpoint(volume="remote-vol"),
        destination=DestinationSyncEndpoint(volume="local"),
    )
    return Config(
        rsync_servers={"remote": server},
        volumes={"remote-vol": src, "local": dst},
        syncs={"pull-data": sync},
    )


def _remote_to_remote_config() -> Config:
    src_server = RsyncServer(
        slug="src-server",
        host="src.example.com",
        user="srcuser",
    )
    dst_server = RsyncServer(
        slug="dst-server",
        host="dst.example.com",
        user="dstuser",
        port=2222,
    )
    src = RemoteVolume(
        slug="src-vol",
        rsync_server="src-server",
        path="/data",
    )
    dst = RemoteVolume(
        slug="dst-vol",
        rsync_server="dst-server",
        path="/backup",
    )
    sync = SyncConfig(
        slug="r2r-sync",
        source=SyncEndpoint(volume="src-vol"),
        destination=DestinationSyncEndpoint(volume="dst-vol"),
    )
    return Config(
        rsync_servers={
            "src-server": src_server,
            "dst-server": dst_server,
        },
        volumes={"src-vol": src, "dst-vol": dst},
        syncs={"r2r-sync": sync},
    )


def _btrfs_config() -> Config:
    src = LocalVolume(slug="src", path="/mnt/src")
    dst = LocalVolume(slug="dst", path="/mnt/dst")
    sync = SyncConfig(
        slug="btrfs-sync",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(
            volume="dst",
            btrfs_snapshots=BtrfsSnapshotConfig(enabled=True, max_snapshots=5),
        ),
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"btrfs-sync": sync},
    )


def _btrfs_no_prune_config() -> Config:
    src = LocalVolume(slug="src", path="/mnt/src")
    dst = LocalVolume(slug="dst", path="/mnt/dst")
    sync = SyncConfig(
        slug="btrfs-sync",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(
            volume="dst",
            btrfs_snapshots=BtrfsSnapshotConfig(enabled=True),
        ),
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"btrfs-sync": sync},
    )


def _disabled_config() -> Config:
    src = LocalVolume(slug="src", path="/mnt/src")
    dst = LocalVolume(slug="dst", path="/mnt/dst")
    sync = SyncConfig(
        slug="disabled-sync",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(volume="dst"),
        enabled=False,
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"disabled-sync": sync},
    )


def _filters_config() -> Config:
    src = LocalVolume(slug="src", path="/mnt/src")
    dst = LocalVolume(slug="dst", path="/mnt/dst")
    sync = SyncConfig(
        slug="filtered-sync",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(volume="dst"),
        filters=["+ *.jpg", "- *.tmp", "H .git"],
        filter_file="~/.config/nbkp/filters.rules",
    )
    return Config(
        volumes={"src": src, "dst": dst},
        syncs={"filtered-sync": sync},
    )


def _proxy_jump_config() -> Config:
    bastion = RsyncServer(
        slug="bastion",
        host="bastion.example.com",
        user="admin",
    )
    nas = RsyncServer(
        slug="nas",
        host="nas.internal",
        port=5022,
        user="backup",
        proxy_jump="bastion",
    )
    src = LocalVolume(slug="src", path="/mnt/data")
    dst = RemoteVolume(
        slug="nas-vol",
        rsync_server="nas",
        path="/volume1",
    )
    sync = SyncConfig(
        slug="proxy-sync",
        source=SyncEndpoint(volume="src"),
        destination=DestinationSyncEndpoint(volume="nas-vol"),
    )
    return Config(
        rsync_servers={"bastion": bastion, "nas": nas},
        volumes={"src": src, "nas-vol": dst},
        syncs={"proxy-sync": sync},
    )


class TestHeader:
    def test_shebang(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert script.startswith("#!/bin/bash\n")

    def test_strict_mode(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "set -euo pipefail" in script
        assert "IFS=$'\\n\\t'" in script

    def test_config_path_in_header(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "# Config: /etc/nbkp/config.yaml" in script

    def test_timestamp_in_header(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "2026-02-21T12:00:00Z" in script

    def test_preserved_dropped_comments(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "# Preserved from nbkp run:" in script
        assert "# Dropped from nbkp run:" in script
        assert "rsync command variants" in script
        assert "Paramiko-only SSH options" in script

    def test_arg_parsing(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "NBKP_DRY_RUN=false" in script
        assert "NBKP_VERBOSE=0" in script
        assert "-n|--dry-run" in script
        assert "NBKP_FAILURES=0" in script

    def test_nbkp_log_helper(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "nbkp_log()" in script

    def test_nbkp_log_dry_run_tag(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "[nbkp] [dry-run]" in script
        assert '"[nbkp] $*"' in script


class TestVolumeChecks:
    def test_local_volume_check(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "test -f /mnt/src/.nbkp-vol" in script
        assert "test -f /mnt/dst/.nbkp-vol" in script

    def test_remote_volume_check(self) -> None:
        config = _local_to_remote_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        # Remote volume check uses ssh
        assert "ssh" in script
        assert "/volume1/backups/.nbkp-vol" in script


class TestLocalToLocal:
    def test_rsync_command(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "rsync" in script
        assert "/mnt/src/photos/" in script
        assert "/mnt/dst/backup/latest/" in script

    def test_function_name(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "sync_my_sync()" in script

    def test_sync_invocation(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert (
            "sync_my_sync" " || NBKP_FAILURES=$((NBKP_FAILURES + 1))"
        ) in script


class TestLocalToRemote:
    def test_rsync_with_ssh(self) -> None:
        config = _local_to_remote_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "rsync" in script
        assert "/mnt/data/photos/" in script
        assert "backup@nas.example.com:/volume1/backups" in script
        assert "-e" in script
        assert "-p" in script
        assert "5022" in script


class TestRemoteToLocal:
    def test_rsync_with_remote_source(self) -> None:
        config = _remote_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "admin@remote.example.com:/data/" in script
        assert "/mnt/backup/latest/" in script


class TestRemoteToRemote:
    def test_ssh_wrapper(self) -> None:
        config = _remote_to_remote_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        # R2R: SSH into dest, run rsync from there
        assert "dst.example.com" in script
        assert "src.example.com" in script
        assert "rsync" in script


class TestDisabledSync:
    def test_commented_out(self) -> None:
        config = _disabled_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "# : disabled" in script
        assert "# sync_disabled_sync()" in script

    def test_disabled_invocation_commented(self) -> None:
        config = _disabled_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "# sync_disabled_sync || NBKP_FAILURES" in script


class TestBtrfs:
    def test_link_dest_resolution(self) -> None:
        config = _btrfs_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "NBKP_LATEST_SNAP=" in script
        assert "RSYNC_LINK_DEST=" in script
        assert "--link-dest=../../snapshots/" in script

    def test_snapshot_creation(self) -> None:
        config = _btrfs_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "btrfs" in script
        assert "subvolume" in script
        assert "snapshot" in script
        assert "/mnt/dst/latest" in script
        assert "NBKP_TS=$(date -u" in script

    def test_snapshot_guarded_by_dry_run(self) -> None:
        config = _btrfs_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert 'if [ "$NBKP_DRY_RUN" = false ]' in script

    def test_prune_with_max_snapshots(self) -> None:
        config = _btrfs_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "Prune old snapshots" in script
        assert "max: 5" in script
        assert "NBKP_EXCESS" in script
        assert "btrfs property set" in script
        assert "btrfs subvolume delete" in script

    def test_no_prune_without_max(self) -> None:
        config = _btrfs_no_prune_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "NBKP_LATEST_SNAP=" in script
        assert "Prune old snapshots" not in script

    def test_latest_and_snapshots_dir_checks(self) -> None:
        config = _btrfs_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "latest/ directory not found" in script
        assert "snapshots/ directory not found" in script


class TestPreflightChecks:
    def test_source_marker(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert ".nbkp-src" in script
        assert "source marker" in script

    def test_destination_marker(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert ".nbkp-dst" in script
        assert "destination marker" in script

    def test_rsync_availability(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "command -v rsync" in script
        assert "rsync not found" in script

    def test_btrfs_availability(self) -> None:
        config = _btrfs_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "command -v btrfs" in script
        assert "btrfs not found" in script

    def test_remote_preflight_uses_ssh(self) -> None:
        config = _local_to_remote_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        # Remote destination checks should use ssh
        assert "ssh" in script
        assert ".nbkp-dst" in script


class TestDryRunAndVerbose:
    def test_dry_run_flag_injected(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "RSYNC_DRY_RUN_FLAG" in script
        assert '${RSYNC_DRY_RUN_FLAG:+"$RSYNC_DRY_RUN_FLAG"}' in script

    def test_verbose_flag_injected(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "RSYNC_VERBOSE_FLAG" in script
        assert '${RSYNC_VERBOSE_FLAG:+"$RSYNC_VERBOSE_FLAG"}' in script

    def test_verbose_levels(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert '"-vvv"' in script
        assert '"-vv"' in script
        assert '"-v"' in script


class TestFilters:
    def test_filter_args_present(self) -> None:
        config = _filters_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "--filter=+ *.jpg" in script
        assert "--filter=- *.tmp" in script
        assert "--filter=H .git" in script

    def test_filter_file_present(self) -> None:
        config = _filters_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "--filter=merge ~/.config/nbkp/filters.rules" in script


class TestProxyJump:
    def test_proxy_jump_in_ssh(self) -> None:
        config = _proxy_jump_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "-J" in script
        assert "admin@bastion.example.com" in script


class TestSshOptions:
    def test_ssh_options_in_script(self) -> None:
        server = RsyncServer(
            slug="nas",
            host="nas.example.com",
            user="backup",
            ssh_options=SshOptions(
                compress=True,
                server_alive_interval=60,
                strict_host_key_checking=False,
                forward_agent=True,
            ),
        )
        src = LocalVolume(slug="src", path="/mnt/data")
        dst = RemoteVolume(
            slug="nas-vol",
            rsync_server="nas",
            path="/backup",
        )
        sync = SyncConfig(
            slug="ssh-opts-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="nas-vol"),
        )
        config = Config(
            rsync_servers={"nas": server},
            volumes={"src": src, "nas-vol": dst},
            syncs={"ssh-opts-sync": sync},
        )
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "Compression=yes" in script
        assert "ServerAliveInterval=60" in script
        assert "StrictHostKeyChecking=no" in script
        assert "ForwardAgent=yes" in script


class TestShellValidity:
    def test_local_to_local_valid_syntax(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_local_to_remote_valid_syntax(self) -> None:
        config = _local_to_remote_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_remote_to_local_valid_syntax(self) -> None:
        config = _remote_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_remote_to_remote_valid_syntax(self) -> None:
        config = _remote_to_remote_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_btrfs_valid_syntax(self) -> None:
        config = _btrfs_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_disabled_valid_syntax(self) -> None:
        config = _disabled_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_filters_valid_syntax(self) -> None:
        config = _filters_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_proxy_jump_valid_syntax(self) -> None:
        config = _proxy_jump_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


class TestEdgeCases:
    def test_empty_config(self) -> None:
        config = Config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "#!/bin/bash" in script
        assert "All syncs completed successfully" in script
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_all_disabled(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        s1 = SyncConfig(
            slug="s-one",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            enabled=False,
        )
        s2 = SyncConfig(
            slug="s-two",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            enabled=False,
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"s-one": s1, "s-two": s2},
        )
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "# : disabled" in script
        assert "# sync_s_one" in script
        assert "# sync_s_two" in script
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_paths_with_spaces(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/my data")
        dst = LocalVolume(slug="dst", path="/mnt/my backup")
        sync = SyncConfig(
            slug="space-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"space-sync": sync},
        )
        script = generate_script(config, _OPTIONS, now=_NOW)
        # Paths with spaces should be properly quoted
        assert "'/mnt/my data/'" in script
        assert "'/mnt/my backup/latest/'" in script
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_no_config_path(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(config_path=None)
        script = generate_script(config, options, now=_NOW)
        assert "# Config: <stdin>" in script

    def test_custom_rsync_options(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        sync = SyncConfig(
            slug="custom-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            rsync_options=["-a", "--delete"],
            extra_rsync_options=["--compress", "--progress"],
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={"custom-sync": sync},
        )
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "--compress" in script
        assert "--progress" in script

    def test_mixed_enabled_disabled(self) -> None:
        src = LocalVolume(slug="src", path="/mnt/src")
        dst = LocalVolume(slug="dst", path="/mnt/dst")
        enabled = SyncConfig(
            slug="active-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
        )
        disabled = SyncConfig(
            slug="off-sync",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(volume="dst"),
            enabled=False,
        )
        config = Config(
            volumes={"src": src, "dst": dst},
            syncs={
                "active-sync": enabled,
                "off-sync": disabled,
            },
        )
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "sync_active_sync()" in script
        assert "# : disabled — off-sync" in script
        assert (
            "sync_active_sync" " || NBKP_FAILURES=$((NBKP_FAILURES + 1))"
        ) in script
        assert "# sync_off_sync || NBKP_FAILURES" in script
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


class TestSummary:
    def test_failure_count_and_exit(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert 'nbkp_log "$NBKP_FAILURES sync(s) failed"' in script
        assert "exit 1" in script
        assert "All syncs completed successfully" in script


class TestRemoteBtrfs:
    def test_remote_btrfs_snapshot(self) -> None:
        server = RsyncServer(
            slug="nas",
            host="nas.example.com",
            user="backup",
        )
        src = LocalVolume(slug="src", path="/mnt/data")
        dst = RemoteVolume(
            slug="nas-vol",
            rsync_server="nas",
            path="/volume1",
        )
        sync = SyncConfig(
            slug="remote-btrfs",
            source=SyncEndpoint(volume="src"),
            destination=DestinationSyncEndpoint(
                volume="nas-vol",
                btrfs_snapshots=BtrfsSnapshotConfig(
                    enabled=True, max_snapshots=3
                ),
            ),
        )
        config = Config(
            rsync_servers={"nas": server},
            volumes={"src": src, "nas-vol": dst},
            syncs={"remote-btrfs": sync},
        )
        script = generate_script(config, _OPTIONS, now=_NOW)
        # Btrfs commands should be wrapped in SSH
        assert "btrfs subvolume snapshot" in script
        assert "btrfs property set" in script
        assert "btrfs subvolume delete" in script
        assert "nas.example.com" in script
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


class TestRelativePaths:
    """Tests for --relative-src / --relative-dst path handling."""

    def test_relative_dst_local_to_local(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/dst/backup.sh",
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        # Source stays absolute
        assert "/mnt/src/photos/" in script
        # Dest uses NBKP_SCRIPT_DIR-relative path
        assert "${NBKP_SCRIPT_DIR}" in script
        assert "/mnt/dst/backup/latest/" not in script

    def test_relative_src_local_to_local(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/src/backup.sh",
            relative_src=True,
        )
        script = generate_script(config, options, now=_NOW)
        # Source uses NBKP_SCRIPT_DIR-relative path
        assert "${NBKP_SCRIPT_DIR}" in script
        # Dest stays absolute
        assert "/mnt/dst/backup/latest/" in script

    def test_relative_both(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/backup.sh",
            relative_src=True,
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        assert "${NBKP_SCRIPT_DIR}" in script
        # Both absolute paths replaced
        assert "/mnt/src/photos/" not in script
        assert "/mnt/dst/backup/latest/" not in script

    def test_relative_src_local_to_remote(self) -> None:
        config = _local_to_remote_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/data/backup.sh",
            relative_src=True,
        )
        script = generate_script(config, options, now=_NOW)
        # Local source relativized
        assert "${NBKP_SCRIPT_DIR}" in script
        # Remote dest stays absolute
        assert "nas.example.com" in script

    def test_relative_dst_remote_to_local(self) -> None:
        config = _remote_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/backup/backup.sh",
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        # Local dest relativized
        assert "${NBKP_SCRIPT_DIR}" in script
        # Remote source stays absolute
        assert "admin@remote.example.com" in script

    def test_relative_remote_to_remote_unchanged(self) -> None:
        config = _remote_to_remote_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/tmp/backup.sh",
            relative_src=True,
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        # Remote volumes are never relativized
        assert "NBKP_SCRIPT_DIR" not in script

    def test_script_dir_in_header(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/dst/backup.sh",
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        assert "NBKP_SCRIPT_DIR=" in script
        assert "BASH_SOURCE[0]" in script

    def test_no_script_dir_when_absolute(self) -> None:
        config = _local_to_local_config()
        script = generate_script(config, _OPTIONS, now=_NOW)
        assert "NBKP_SCRIPT_DIR" not in script

    def test_relative_shell_valid(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/dst/backup.sh",
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_relative_both_shell_valid(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/backup.sh",
            relative_src=True,
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_relative_btrfs(self) -> None:
        config = _btrfs_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/dst/backup.sh",
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        assert "${NBKP_SCRIPT_DIR}" in script
        # Btrfs snapshot uses relative dest paths
        assert "btrfs" in script
        assert "subvolume" in script
        assert "snapshot" in script
        assert "${NBKP_SCRIPT_DIR}" in script
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"

    def test_relative_volume_checks(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/dst/backup.sh",
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        # Dst volume check should use relative path
        assert "${NBKP_SCRIPT_DIR}" in script
        # Src volume check stays absolute
        assert "test -f /mnt/src/.nbkp-vol" in script

    def test_relative_preflight_checks(self) -> None:
        config = _local_to_local_config()
        options = ScriptOptions(
            config_path="/etc/nbkp/config.yaml",
            output_file="/mnt/dst/backup.sh",
            relative_dst=True,
        )
        script = generate_script(config, options, now=_NOW)
        # Source preflight stays absolute
        assert "/mnt/src/photos/.nbkp-src" in script
        # Dest preflight uses relative
        assert ".nbkp-dst" in script
