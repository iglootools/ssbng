"""Fake sync and prune result builders for manual testing."""

from __future__ import annotations

from ...sync import PruneResult, SyncResult

_SNAP_BASE = "/mnt/usb-backup/snapshots"


def run_results() -> list[SyncResult]:
    """Sync results: success, success+snapshot, failure."""
    snap = f"{_SNAP_BASE}/2026-02-19T10:30:00.000Z"
    return [
        SyncResult(
            sync_slug="music-to-usb",
            success=True,
            dry_run=False,
            rsync_exit_code=0,
            output="",
        ),
        SyncResult(
            sync_slug="photos-to-usb",
            success=True,
            dry_run=False,
            rsync_exit_code=0,
            output="",
            snapshot_path=snap,
            pruned_paths=[
                f"{_SNAP_BASE}/2026-02-01T08:00:00.000Z",
                f"{_SNAP_BASE}/2026-02-10T12:00:00.000Z",
            ],
        ),
        SyncResult(
            sync_slug="docs-to-nas",
            success=False,
            dry_run=False,
            rsync_exit_code=23,
            output=(
                "rsync: [sender] link_stat"
                ' "/mnt/data/documents" failed:'
                " No such file or directory (2)\n"
                "rsync error: some files/attrs"
                " were not transferred (code 23)\n"
            ),
            error="rsync exited with code 23",
        ),
    ]


def dry_run_result() -> SyncResult:
    """Single dry-run success result."""
    return SyncResult(
        sync_slug="photos-to-usb",
        success=True,
        dry_run=True,
        rsync_exit_code=0,
        output="",
    )


def prune_results() -> list[PruneResult]:
    """Prune results: success, noop, error."""
    return [
        PruneResult(
            sync_slug="photos-to-usb",
            deleted=[
                f"{_SNAP_BASE}/2026-01-01T00:00:00.000Z",
                f"{_SNAP_BASE}/2026-01-15T00:00:00.000Z",
                f"{_SNAP_BASE}/2026-02-01T00:00:00.000Z",
            ],
            kept=7,
            dry_run=False,
        ),
        PruneResult(
            sync_slug="music-to-usb",
            deleted=[],
            kept=5,
            dry_run=False,
        ),
        PruneResult(
            sync_slug="docs-to-nas",
            deleted=[],
            kept=0,
            dry_run=False,
            error="btrfs delete failed:" " Permission denied",
        ),
    ]


def prune_dry_run_results() -> list[PruneResult]:
    """Prune dry-run results."""
    return [
        PruneResult(
            sync_slug="photos-to-usb",
            deleted=[
                f"{_SNAP_BASE}/2026-01-01T00:00:00.000Z",
                f"{_SNAP_BASE}/2026-01-15T00:00:00.000Z",
            ],
            kept=10,
            dry_run=True,
        ),
    ]
