"""Sync orchestration: checks -> rsync -> snapshots."""

from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel

from .btrfs import create_snapshot, get_latest_snapshot, prune_snapshots
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
    pruned_paths: Optional[list[str]] = None
    error: Optional[str] = None


class PruneResult(BaseModel):
    """Result of pruning snapshots for a sync."""

    sync_slug: str
    deleted: list[str]
    kept: int
    dry_run: bool
    error: Optional[str] = None


def run_all_syncs(
    config: Config,
    sync_statuses: dict[str, SyncStatus],
    dry_run: bool = False,
    only_syncs: list[str] | None = None,
    verbose: int = 0,
    on_rsync_output: Callable[[str], None] | None = None,
    on_sync_start: Callable[[str], None] | None = None,
    on_sync_end: Callable[[str, SyncResult], None] | None = None,
) -> list[SyncResult]:
    """Run all (or selected) syncs.

    Expects pre-computed sync statuses from ``check_all_syncs``.
    """

    results: list[SyncResult] = []

    selected = (
        {s: st for s, st in sync_statuses.items() if s in only_syncs}
        if only_syncs
        else sync_statuses
    )

    for slug, status in selected.items():
        if on_sync_start:
            on_sync_start(slug)

        if not status.active:
            result = SyncResult(
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
        else:
            result = _run_single_sync(
                slug,
                status,
                config,
                dry_run,
                verbose,
                on_rsync_output,
            )

        results.append(result)
        if on_sync_end:
            on_sync_end(slug, result)

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
    if sync.destination.btrfs_snapshots.enabled:
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
    else:
        # Create btrfs snapshot if configured and not dry run
        snapshot_path: str | None = None
        pruned_paths: list[str] | None = None
        btrfs_cfg = sync.destination.btrfs_snapshots
        if btrfs_cfg.enabled and not dry_run:
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
            if btrfs_cfg.max_snapshots is not None:
                pruned_paths = prune_snapshots(
                    sync, config, btrfs_cfg.max_snapshots
                )

        return SyncResult(
            sync_slug=slug,
            success=True,
            dry_run=dry_run,
            rsync_exit_code=proc.returncode,
            output=proc.stdout,
            snapshot_path=snapshot_path,
            pruned_paths=pruned_paths,
        )
