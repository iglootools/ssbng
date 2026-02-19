"""Sync orchestration: checks -> rsync -> snapshots."""

from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel

from .btrfs import create_snapshot, get_latest_snapshot
from .config import Config
from .status import SyncStatus
from .rsync import run_rsync


class SyncResult(BaseModel):
    """Result of running a sync."""

    sync_slug: str
    success: bool
    dry_run: bool
    rsync_exit_code: int
    output: str
    snapshot_path: Optional[str] = None
    error: Optional[str] = None


def run_all_syncs(
    config: Config,
    sync_statuses: dict[str, SyncStatus],
    dry_run: bool = False,
    sync_slugs: list[str] | None = None,
    verbose: int = 0,
    on_rsync_output: Callable[[str], None] | None = None,
) -> list[SyncResult]:
    """Run all (or selected) syncs.

    Expects pre-computed sync statuses from ``check_all_syncs``.
    """

    results: list[SyncResult] = []

    for slug, status in sync_statuses.items():
        if sync_slugs and slug not in sync_slugs:
            continue

        if not status.active:
            results.append(
                SyncResult(
                    sync_slug=slug,
                    success=False,
                    dry_run=dry_run,
                    rsync_exit_code=-1,
                    output="",
                    error=(
                        "Sync not active: "
                        + ", ".join(r.value for r in status.reasons)
                    ),
                )
            )
            continue

        result = _run_single_sync(
            slug,
            status,
            config,
            dry_run,
            verbose,
            on_rsync_output,
        )
        results.append(result)

    return results


def _run_single_sync(
    slug: str,
    status: SyncStatus,
    config: Config,
    dry_run: bool,
    verbose: int = 0,
    on_rsync_output: Callable[[str], None] | None = None,
) -> SyncResult:
    """Run a single sync operation."""
    sync = status.config

    # Check for link-dest if btrfs snapshots are configured
    link_dest: str | None = None
    if sync.destination.btrfs_snapshots:
        latest = get_latest_snapshot(sync, config)
        if latest:
            link_dest = f"../../snapshots/{latest.rsplit('/', 1)[-1]}"

    try:
        proc = run_rsync(
            sync,
            config,
            dry_run=dry_run,
            link_dest=link_dest,
            verbose=verbose,
            on_output=on_rsync_output,
        )
    except Exception as e:
        return SyncResult(
            sync_slug=slug,
            success=False,
            dry_run=dry_run,
            rsync_exit_code=-1,
            output="",
            error=str(e),
        )

    if proc.returncode != 0:
        return SyncResult(
            sync_slug=slug,
            success=False,
            dry_run=dry_run,
            rsync_exit_code=proc.returncode,
            output=proc.stdout + proc.stderr,
            error=f"rsync exited with code {proc.returncode}",
        )

    # Create btrfs snapshot if configured and not dry run
    snapshot_path: str | None = None
    if sync.destination.btrfs_snapshots and not dry_run:
        try:
            snapshot_path = create_snapshot(sync, config)
        except RuntimeError as e:
            return SyncResult(
                sync_slug=slug,
                success=False,
                dry_run=dry_run,
                rsync_exit_code=proc.returncode,
                output=proc.stdout,
                error=f"Snapshot failed: {e}",
            )

    return SyncResult(
        sync_slug=slug,
        success=True,
        dry_run=dry_run,
        rsync_exit_code=proc.returncode,
        output=proc.stdout,
        snapshot_path=snapshot_path,
    )
