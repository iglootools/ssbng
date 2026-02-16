"""Tests for ssb.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from ssb.config import ConfigError, find_config_file, load_config
from ssb.model import LocalVolume, RemoteVolume


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
        assert "local-data" in cfg.volumes
        assert "nas" in cfg.volumes
        assert "photos-to-nas" in cfg.syncs

        local = cfg.volumes["local-data"]
        assert isinstance(local, LocalVolume)
        assert local.path == "/mnt/data"

        remote = cfg.volumes["nas"]
        assert isinstance(remote, RemoteVolume)
        assert remote.host == "nas.example.com"
        assert remote.port == 5022
        assert remote.user == "backup"
        assert remote.ssh_key == "~/.ssh/key"

        sync = cfg.syncs["photos-to-nas"]
        assert sync.source.volume_name == "local-data"
        assert sync.source.subdir == "photos"
        assert sync.destination.volume_name == "nas"
        assert sync.destination.subdir == "photos-backup"
        assert sync.enabled is True
        assert sync.btrfs_snapshots is False

    def test_minimal_config(self, sample_minimal_config_file: Path) -> None:
        cfg = load_config(str(sample_minimal_config_file))
        sync = cfg.syncs["s1"]
        assert sync.enabled is True
        assert sync.btrfs_snapshots is False
        assert sync.source.subdir is None

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
        with pytest.raises(ConfigError, match="invalid type"):
            load_config(str(p))

    def test_missing_local_path(self, tmp_path: Path) -> None:
        p = tmp_path / "no_path.yaml"
        p.write_text("volumes:\n  v:\n    type: local\nsyncs: {}\n")
        with pytest.raises(ConfigError, match="requires 'path'"):
            load_config(str(p))

    def test_missing_remote_host(self, tmp_path: Path) -> None:
        p = tmp_path / "no_host.yaml"
        p.write_text(
            "volumes:\n  v:\n    type: remote\n    path: /x\n" "syncs: {}\n"
        )
        with pytest.raises(ConfigError, match="requires 'host' and 'path'"):
            load_config(str(p))

    def test_unknown_volume_reference(self, tmp_path: Path) -> None:
        p = tmp_path / "bad_ref.yaml"
        p.write_text(
            "volumes:\n  v:\n    type: local\n    path: /x\n"
            "syncs:\n  s:\n    source:\n      volume: v\n"
            "    destination:\n      volume: missing\n"
        )
        with pytest.raises(ConfigError, match="unknown destination volume"):
            load_config(str(p))

    def test_missing_source_volume(self, tmp_path: Path) -> None:
        p = tmp_path / "no_src_vol.yaml"
        p.write_text(
            "volumes:\n  v:\n    type: local\n    path: /x\n"
            "syncs:\n  s:\n    source:\n      volume: missing\n"
            "    destination:\n      volume: v\n"
        )
        with pytest.raises(ConfigError, match="unknown source volume"):
            load_config(str(p))

    def test_sync_missing_source(self, tmp_path: Path) -> None:
        p = tmp_path / "no_src.yaml"
        p.write_text(
            "volumes:\n  v:\n    type: local\n    path: /x\n"
            "syncs:\n  s:\n    destination:\n      volume: v\n"
        )
        with pytest.raises(ConfigError, match="requires 'source'"):
            load_config(str(p))
