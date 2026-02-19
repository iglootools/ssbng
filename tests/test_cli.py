"""Tests for ssb.cli."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ssb.cli import app
from ssb.config import (
    Config,
    DestinationSyncEndpoint,
    LocalVolume,
    RemoteVolume,
    SyncConfig,
    SyncEndpoint,
)
from ssb.status import (
    SyncReason,
    SyncResult,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
)

runner = CliRunner()


def _sample_config() -> Config:
    src = LocalVolume(name="local-data", path="/mnt/data")
    dst = RemoteVolume(
        name="nas",
        host="nas.example.com",
        path="/volume1/backups",
        port=5022,
        user="backup",
    )
    sync = SyncConfig(
        name="photos-to-nas",
        source=SyncEndpoint(volume_name="local-data", subdir="photos"),
        destination=DestinationSyncEndpoint(
            volume_name="nas", subdir="photos-backup"
        ),
    )
    return Config(
        volumes={"local-data": src, "nas": dst},
        syncs={"photos-to-nas": sync},
    )


def _sample_vol_statuses(
    config: Config,
) -> dict[str, VolumeStatus]:
    return {
        "local-data": VolumeStatus(
            name="local-data",
            config=config.volumes["local-data"],
            reasons=[],
        ),
        "nas": VolumeStatus(
            name="nas",
            config=config.volumes["nas"],
            reasons=[VolumeReason.UNREACHABLE],
        ),
    }


def _sample_sync_statuses(
    config: Config,
    vol_statuses: dict[str, VolumeStatus],
) -> dict[str, SyncStatus]:
    return {
        "photos-to-nas": SyncStatus(
            name="photos-to-nas",
            config=config.syncs["photos-to-nas"],
            source_status=vol_statuses["local-data"],
            destination_status=vol_statuses["nas"],
            reasons=[SyncReason.DESTINATION_UNAVAILABLE],
        ),
    }


class TestStatusCommand:
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_human_output(
        self, mock_load: MagicMock, mock_checks: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_vol_statuses(config)
        sync_s = _sample_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(app, ["status", "--config", "/fake.yaml"])
        assert result.exit_code == 0
        assert "local-data" in result.output
        assert "nas" in result.output
        assert "active" in result.output
        assert "inactive" in result.output
        assert "photos-to-nas" in result.output

    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_json_output(
        self, mock_load: MagicMock, mock_checks: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_vol_statuses(config)
        sync_s = _sample_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(
            app,
            ["status", "--config", "/fake.yaml", "--output", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "volumes" in data
        assert "syncs" in data


class TestRunCommand:
    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.load_config")
    def test_successful_run(
        self, mock_load: MagicMock, mock_run: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        mock_run.return_value = (
            {},
            [
                SyncResult(
                    sync_name="photos-to-nas",
                    success=True,
                    dry_run=False,
                    rsync_exit_code=0,
                    output="done",
                )
            ],
        )

        result = runner.invoke(app, ["run", "--config", "/fake.yaml"])
        assert result.exit_code == 0
        assert "OK" in result.output

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.load_config")
    def test_failed_run(
        self, mock_load: MagicMock, mock_run: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        mock_run.return_value = (
            {},
            [
                SyncResult(
                    sync_name="photos-to-nas",
                    success=False,
                    dry_run=False,
                    rsync_exit_code=23,
                    output="",
                    error="rsync failed",
                )
            ],
        )

        result = runner.invoke(app, ["run", "--config", "/fake.yaml"])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.load_config")
    def test_dry_run(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        config = _sample_config()
        mock_load.return_value = config
        mock_run.return_value = (
            {},
            [
                SyncResult(
                    sync_name="photos-to-nas",
                    success=True,
                    dry_run=True,
                    rsync_exit_code=0,
                    output="",
                )
            ],
        )

        result = runner.invoke(
            app, ["run", "--config", "/fake.yaml", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "dry run" in result.output

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.load_config")
    def test_json_output(
        self, mock_load: MagicMock, mock_run: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        mock_run.return_value = (
            {},
            [
                SyncResult(
                    sync_name="photos-to-nas",
                    success=True,
                    dry_run=False,
                    rsync_exit_code=0,
                    output="done",
                )
            ],
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                "/fake.yaml",
                "--output",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["sync_name"] == "photos-to-nas"

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.load_config")
    def test_sync_filter(
        self, mock_load: MagicMock, mock_run: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        mock_run.return_value = (
            {},
            [
                SyncResult(
                    sync_name="photos-to-nas",
                    success=True,
                    dry_run=False,
                    rsync_exit_code=0,
                    output="",
                )
            ],
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                "/fake.yaml",
                "--sync",
                "photos-to-nas",
            ],
        )
        assert result.exit_code == 0
        # Verify sync_names was passed
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("sync_names") == ["photos-to-nas"]


class TestConfigError:
    @patch(
        "ssb.cli.load_config",
        side_effect=__import__(
            "ssb.configloader", fromlist=["ConfigError"]
        ).ConfigError("bad config"),
    )
    def test_status_config_error(self, mock_load: MagicMock) -> None:
        result = runner.invoke(app, ["status", "--config", "/bad.yaml"])
        assert result.exit_code == 2

    @patch(
        "ssb.cli.load_config",
        side_effect=__import__(
            "ssb.configloader", fromlist=["ConfigError"]
        ).ConfigError("bad config"),
    )
    def test_run_config_error(self, mock_load: MagicMock) -> None:
        result = runner.invoke(app, ["run", "--config", "/bad.yaml"])
        assert result.exit_code == 2
