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
    RsyncServer,
    SyncConfig,
    SyncEndpoint,
)
from ssb.runner import SyncResult
from ssb.status import (
    SyncReason,
    SyncStatus,
    VolumeReason,
    VolumeStatus,
)

runner = CliRunner()


def _sample_config() -> Config:
    src = LocalVolume(slug="local-data", path="/mnt/data")
    nas_server = RsyncServer(
        slug="nas-server",
        host="nas.example.com",
        port=5022,
        user="backup",
    )
    dst = RemoteVolume(
        slug="nas",
        rsync_server="nas-server",
        path="/volume1/backups",
    )
    sync = SyncConfig(
        slug="photos-to-nas",
        source=SyncEndpoint(volume="local-data", subdir="photos"),
        destination=DestinationSyncEndpoint(
            volume="nas", subdir="photos-backup"
        ),
    )
    return Config(
        rsync_servers={"nas-server": nas_server},
        volumes={"local-data": src, "nas": dst},
        syncs={"photos-to-nas": sync},
    )


def _sample_vol_statuses(
    config: Config,
) -> dict[str, VolumeStatus]:
    return {
        "local-data": VolumeStatus(
            slug="local-data",
            config=config.volumes["local-data"],
            reasons=[],
        ),
        "nas": VolumeStatus(
            slug="nas",
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
            slug="photos-to-nas",
            config=config.syncs["photos-to-nas"],
            source_status=vol_statuses["local-data"],
            destination_status=vol_statuses["nas"],
            reasons=[SyncReason.DESTINATION_UNAVAILABLE],
        ),
    }


def _sample_marker_only_sync_statuses(
    config: Config,
    vol_statuses: dict[str, VolumeStatus],
) -> dict[str, SyncStatus]:
    return {
        "photos-to-nas": SyncStatus(
            slug="photos-to-nas",
            config=config.syncs["photos-to-nas"],
            source_status=vol_statuses["local-data"],
            destination_status=vol_statuses["nas"],
            reasons=[
                SyncReason.SOURCE_MARKER_NOT_FOUND,
                SyncReason.DESTINATION_MARKER_NOT_FOUND,
            ],
        ),
    }


def _sample_all_active_vol_statuses(
    config: Config,
) -> dict[str, VolumeStatus]:
    return {
        "local-data": VolumeStatus(
            slug="local-data",
            config=config.volumes["local-data"],
            reasons=[],
        ),
        "nas": VolumeStatus(
            slug="nas",
            config=config.volumes["nas"],
            reasons=[],
        ),
    }


def _sample_all_active_sync_statuses(
    config: Config,
    vol_statuses: dict[str, VolumeStatus],
) -> dict[str, SyncStatus]:
    return {
        "photos-to-nas": SyncStatus(
            slug="photos-to-nas",
            config=config.syncs["photos-to-nas"],
            source_status=vol_statuses["local-data"],
            destination_status=vol_statuses["nas"],
            reasons=[],
        ),
    }


class TestStatusCommand:
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_human_output_inactive(
        self, mock_load: MagicMock, mock_checks: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_vol_statuses(config)
        sync_s = _sample_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(app, ["status", "--config", "/fake.yaml"])
        assert result.exit_code == 1
        assert "local-data" in result.output
        assert "nas" in result.output
        assert "active" in result.output
        assert "inactive" in result.output
        assert "photos-to-nas" in result.output

    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_human_output_all_active(
        self, mock_load: MagicMock, mock_checks: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(app, ["status", "--config", "/fake.yaml"])
        assert result.exit_code == 0

    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_json_output_inactive(
        self, mock_load: MagicMock, mock_checks: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_vol_statuses(config)
        sync_s = _sample_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(
            app,
            [
                "status",
                "--config",
                "/fake.yaml",
                "--output",
                "json",
            ],
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "volumes" in data
        assert "syncs" in data

    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_json_output_all_active(
        self, mock_load: MagicMock, mock_checks: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(
            app,
            [
                "status",
                "--config",
                "/fake.yaml",
                "--output",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "volumes" in data
        assert "syncs" in data

    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_marker_only_exit_0_by_default(
        self, mock_load: MagicMock, mock_checks: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_marker_only_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(app, ["status", "--config", "/fake.yaml"])
        assert result.exit_code == 0

    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_marker_only_exit_1_when_no_allow_removable(
        self, mock_load: MagicMock, mock_checks: MagicMock
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_marker_only_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(
            app,
            [
                "status",
                "--config",
                "/fake.yaml",
                "--no-allow-removable-devices",
            ],
        )
        assert result.exit_code == 1


class TestRunCommand:
    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_successful_run(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)
        mock_run.return_value = [
            SyncResult(
                sync_slug="photos-to-nas",
                success=True,
                dry_run=False,
                rsync_exit_code=0,
                output="done",
            )
        ]

        result = runner.invoke(app, ["run", "--config", "/fake.yaml"])
        assert result.exit_code == 0
        assert "photos-to-nas" in result.output
        assert "OK" in result.output
        call_kwargs = mock_run.call_args
        assert callable(call_kwargs.kwargs.get("on_rsync_output"))

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_displays_status_before_results(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)
        mock_run.return_value = [
            SyncResult(
                sync_slug="photos-to-nas",
                success=True,
                dry_run=False,
                rsync_exit_code=0,
                output="done",
            )
        ]

        result = runner.invoke(app, ["run", "--config", "/fake.yaml"])
        assert result.exit_code == 0
        # Status section appears before results section
        assert "Volumes:" in result.output
        assert "Syncs:" in result.output
        vol_pos = result.output.index("Volumes:")
        ok_pos = result.output.index("OK")
        assert vol_pos < ok_pos

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_failed_run(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)
        mock_run.return_value = [
            SyncResult(
                sync_slug="photos-to-nas",
                success=False,
                dry_run=False,
                rsync_exit_code=23,
                output="",
                error="rsync failed",
            )
        ]

        result = runner.invoke(app, ["run", "--config", "/fake.yaml"])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_dry_run(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)
        mock_run.return_value = [
            SyncResult(
                sync_slug="photos-to-nas",
                success=True,
                dry_run=True,
                rsync_exit_code=0,
                output="",
            )
        ]

        result = runner.invoke(
            app,
            ["run", "--config", "/fake.yaml", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "dry run" in result.output

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_json_output(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)
        mock_run.return_value = [
            SyncResult(
                sync_slug="photos-to-nas",
                success=True,
                dry_run=False,
                rsync_exit_code=0,
                output="done",
            )
        ]

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
        assert "volumes" in data
        assert "syncs" in data
        assert "results" in data
        assert data["results"][0]["sync_slug"] == "photos-to-nas"
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("on_rsync_output") is None

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_sync_filter(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)
        mock_run.return_value = [
            SyncResult(
                sync_slug="photos-to-nas",
                success=True,
                dry_run=False,
                rsync_exit_code=0,
                output="",
            )
        ]

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
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("sync_slugs") == ["photos-to-nas"]

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_verbose(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_all_active_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)
        mock_run.return_value = [
            SyncResult(
                sync_slug="photos-to-nas",
                success=True,
                dry_run=False,
                rsync_exit_code=0,
                output="",
            )
        ]

        result = runner.invoke(
            app,
            ["run", "--config", "/fake.yaml", "-v", "-v"],
        )
        assert result.exit_code == 0
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("verbose") == 2

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_exits_before_syncs_on_status_error(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_vol_statuses(config)
        sync_s = _sample_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(app, ["run", "--config", "/fake.yaml"])
        assert result.exit_code == 1
        mock_run.assert_not_called()

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_marker_only_proceeds_by_default(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_marker_only_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)
        mock_run.return_value = [
            SyncResult(
                sync_slug="photos-to-nas",
                success=True,
                dry_run=False,
                rsync_exit_code=0,
                output="done",
            )
        ]

        result = runner.invoke(app, ["run", "--config", "/fake.yaml"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("ssb.cli.run_all_syncs")
    @patch("ssb.cli.check_all_syncs")
    @patch("ssb.cli.load_config")
    def test_marker_only_exits_when_no_allow_removable(
        self,
        mock_load: MagicMock,
        mock_checks: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        config = _sample_config()
        mock_load.return_value = config
        vol_s = _sample_all_active_vol_statuses(config)
        sync_s = _sample_marker_only_sync_statuses(config, vol_s)
        mock_checks.return_value = (vol_s, sync_s)

        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                "/fake.yaml",
                "--no-allow-removable-devices",
            ],
        )
        assert result.exit_code == 1
        mock_run.assert_not_called()


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
