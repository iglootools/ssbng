"""Tests for ssb.configloader."""

from __future__ import annotations

from pathlib import Path

import pytest

from ssb.config import LocalVolume, RemoteVolume
from ssb.configloader import ConfigError, find_config_file, load_config


class TestFindConfigFile:
    def test_explicit_path(self, sample_config_file: Path) -> None:
        result = find_config_file(str(sample_config_file))
        assert result == sample_config_file

    def test_explicit_path_missing(self) -> None:
        with pytest.raises(ConfigError, match="not found"):
            find_config_file("/nonexistent/config.yaml")

    def test_xdg_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        xdg = tmp_path / "xdg"
        cfg = xdg / "ssb" / "config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("volumes: {}\nsyncs: {}\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        result = find_config_file()
        assert result == cfg

    def test_no_config_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
        with pytest.raises(ConfigError, match="No config file found"):
            find_config_file()


class TestLoadConfig:
    def test_full_config(self, sample_config_file: Path) -> None:
        cfg = load_config(str(sample_config_file))
        assert "nas-server" in cfg.rsync_servers
        server = cfg.rsync_servers["nas-server"]
        assert server.name == "nas-server"
        assert server.host == "nas.example.com"
        assert server.port == 5022
        assert server.user == "backup"
        assert server.ssh_key == "~/.ssh/key"
        assert server.connect_timeout == 10
        assert "local-data" in cfg.volumes
        assert "nas" in cfg.volumes
        assert "photos-to-nas" in cfg.syncs
        local = cfg.volumes["local-data"]
        assert isinstance(local, LocalVolume)
        assert local.path == "/mnt/data"
        remote = cfg.volumes["nas"]
        assert isinstance(remote, RemoteVolume)
        assert remote.rsync_server == "nas-server"
        sync = cfg.syncs["photos-to-nas"]
        assert sync.source.volume == "local-data"
        assert sync.source.subdir == "photos"
        assert sync.destination.volume == "nas"
        assert sync.destination.subdir == "photos-backup"
        assert sync.enabled is True
        assert sync.destination.btrfs_snapshots is False
        assert sync.rsync_options is None
        assert sync.extra_rsync_options == []
        assert sync.filters == ["+ *.jpg", "- *.tmp"]
        assert sync.filter_file == "~/.config/ssb/filters/photos.rules"

    def test_minimal_config(self, sample_minimal_config_file: Path) -> None:
        cfg = load_config(str(sample_minimal_config_file))
        sync = cfg.syncs["s1"]
        assert sync.enabled is True
        assert sync.destination.btrfs_snapshots is False
        assert sync.source.subdir is None
        assert sync.rsync_options is None
        assert sync.extra_rsync_options == []
        assert sync.filters == []
        assert sync.filter_file is None

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("not_a_list:\n  - [invalid")
        with pytest.raises(Exception):
            load_config(str(p))

    def test_not_a_mapping(self, tmp_path: Path) -> None:
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError, match="must be a YAML mapping"):
            load_config(str(p))

    def test_invalid_volume_type(self, tmp_path: Path) -> None:
        p = tmp_path / "bad_type.yaml"
        p.write_text(
            "volumes:\n  v:\n    type: ftp\n    path: /x\n" "syncs: {}\n"
        )
        with pytest.raises(ConfigError) as excinfo:
            load_config(str(p))
        cause = excinfo.value.__cause__
        assert cause is not None
        assert "does not match any of the expected tags" in str(cause)

    def test_missing_local_path(self, tmp_path: Path) -> None:
        p = tmp_path / "no_path.yaml"
        p.write_text("volumes:\n  v:\n    type: local\nsyncs: {}\n")
        with pytest.raises(ConfigError) as excinfo:
            load_config(str(p))
        cause = excinfo.value.__cause__
        assert cause is not None
        errors = cause.errors()
        assert any(
            err["loc"] == ("volumes", "v", "local", "path")
            and err["type"] == "missing"
            for err in errors
        )

    def test_missing_remote_host(self, tmp_path: Path) -> None:
        p = tmp_path / "no_host.yaml"
        p.write_text(
            "rsync-servers:\n  s:\n    port: 22\n"
            "volumes:\n  v:\n    type: remote\n"
            "    rsync-server: s\n"
            "    path: /x\n"
            "syncs: {}\n"
        )
        with pytest.raises(ConfigError) as excinfo:
            load_config(str(p))
        cause = excinfo.value.__cause__
        assert cause is not None
        errors = cause.errors()
        assert any(
            "host" in str(err["loc"]) and err["type"] == "missing"
            for err in errors
        )

    def test_unknown_rsync_server_reference(self, tmp_path: Path) -> None:
        p = tmp_path / "bad_server_ref.yaml"
        p.write_text(
            "rsync-servers: {}\n"
            "volumes:\n  v:\n    type: remote\n"
            "    rsync-server: missing\n"
            "    path: /x\n"
            "syncs: {}\n"
        )
        with pytest.raises(ConfigError) as excinfo:
            load_config(str(p))
        cause = excinfo.value.__cause__
        assert cause is not None
        assert "unknown rsync-server 'missing'" in str(cause)

    def test_unknown_volume_reference(self, tmp_path: Path) -> None:
        p = tmp_path / "bad_ref.yaml"
        p.write_text(
            "volumes:\n  v:\n    type: local\n    path: /x\n"
            "syncs:\n  s:\n    source:\n      volume: v\n"
            "    destination:\n      volume: missing\n"
        )
        with pytest.raises(ConfigError) as excinfo:
            load_config(str(p))
        cause = excinfo.value.__cause__
        assert cause is not None
        assert "unknown destination volume" in str(cause)

    def test_missing_source_volume(self, tmp_path: Path) -> None:
        p = tmp_path / "no_src_vol.yaml"
        p.write_text(
            "volumes:\n  v:\n    type: local\n    path: /x\n"
            "syncs:\n  s:\n    source:\n      volume: missing\n"
            "    destination:\n      volume: v\n"
        )
        with pytest.raises(ConfigError) as excinfo:
            load_config(str(p))
        cause = excinfo.value.__cause__
        assert cause is not None
        assert "unknown source volume" in str(cause)

    def test_sync_missing_source(self, tmp_path: Path) -> None:
        p = tmp_path / "no_src.yaml"
        p.write_text(
            "volumes:\n  v:\n    type: local\n    path: /x\n"
            "syncs:\n  s:\n    destination:\n      volume: v\n"
        )
        with pytest.raises(ConfigError) as excinfo:
            load_config(str(p))
        cause = excinfo.value.__cause__
        assert cause is not None
        errors = cause.errors()
        assert any(
            err["loc"] == ("syncs", "s", "source") and err["type"] == "missing"
            for err in errors
        )

    def test_filter_normalization(self, tmp_path: Path) -> None:
        p = tmp_path / "filters.yaml"
        p.write_text(
            "volumes:\n"
            "  v:\n    type: local\n    path: /x\n"
            "syncs:\n"
            "  s:\n"
            "    source:\n      volume: v\n"
            "    destination:\n      volume: v\n"
            "    filters:\n"
            '      - include: "*.jpg"\n'
            '      - exclude: "*.tmp"\n'
            '      - "H .git"\n'
        )
        cfg = load_config(str(p))
        sync = cfg.syncs["s"]
        assert sync.filters == ["+ *.jpg", "- *.tmp", "H .git"]

    def test_rsync_options_override(self, tmp_path: Path) -> None:
        p = tmp_path / "opts.yaml"
        p.write_text(
            "volumes:\n"
            "  v:\n    type: local\n    path: /x\n"
            "syncs:\n"
            "  s:\n"
            "    source:\n      volume: v\n"
            "    destination:\n      volume: v\n"
            "    rsync-options:\n"
            '      - "-a"\n'
            '      - "--delete"\n'
        )
        cfg = load_config(str(p))
        sync = cfg.syncs["s"]
        assert sync.rsync_options == ["-a", "--delete"]
        assert sync.extra_rsync_options == []

    def test_extra_rsync_options(self, tmp_path: Path) -> None:
        p = tmp_path / "extra.yaml"
        p.write_text(
            "volumes:\n"
            "  v:\n    type: local\n    path: /x\n"
            "syncs:\n"
            "  s:\n"
            "    source:\n      volume: v\n"
            "    destination:\n      volume: v\n"
            "    extra-rsync-options:\n"
            '      - "--compress"\n'
            '      - "--progress"\n'
        )
        cfg = load_config(str(p))
        sync = cfg.syncs["s"]
        assert sync.rsync_options is None
        assert sync.extra_rsync_options == ["--compress", "--progress"]

    def test_connect_timeout(self, tmp_path: Path) -> None:
        p = tmp_path / "timeout.yaml"
        p.write_text(
            "rsync-servers:\n"
            "  slow:\n"
            "    host: slow.example.com\n"
            "    connect-timeout: 30\n"
            "volumes: {}\n"
            "syncs: {}\n"
        )
        cfg = load_config(str(p))
        assert cfg.rsync_servers["slow"].connect_timeout == 30

    def test_invalid_filter_entry(self, tmp_path: Path) -> None:
        p = tmp_path / "bad_filter.yaml"
        p.write_text(
            "volumes:\n"
            "  v:\n    type: local\n    path: /x\n"
            "syncs:\n"
            "  s:\n"
            "    source:\n      volume: v\n"
            "    destination:\n      volume: v\n"
            "    filters:\n"
            "      - badkey: value\n"
        )
        with pytest.raises(ConfigError) as excinfo:
            load_config(str(p))
        cause = excinfo.value.__cause__
        assert cause is not None
        assert "include" in str(cause) or "exclude" in str(cause)
