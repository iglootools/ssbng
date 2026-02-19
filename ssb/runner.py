"""Sync orchestration: checks -> rsync -> snapshots."""

from __future__ import annotations

from .btrfs import create_snapshot, get_latest_snapshot
from .checks import check_all_syncs
from .config import Config
from .status import SyncResult, SyncStatus
from .rsync import run_rsync


def run_all_syncs(
    config: Config,
    dry_run: bool = False,
    sync_names: list[str] | None = None,
) -> tuple[dict[str, SyncStatus], list[SyncResult]]:
    """Run all (or selected) syncs.

    Returns sync statuses and a list of results.
    """
    _, sync_statuses = check_all_syncs(config)

    results: list[SyncResult] = []

    for name, status in sync_statuses.items():
        if sync_names and name not in sync_names:
            continue

        if not status.active:
            results.append(
                SyncResult(
                    sync_name=name,
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

        result = _run_single_sync(name, status, config, dry_run)
        results.append(result)

    return sync_statuses, results


def _run_single_sync(
    name: str,
    status: SyncStatus,
    config: Config,
    dry_run: bool,
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
        proc = run_rsync(sync, config, dry_run=dry_run, link_dest=link_dest)
    except Exception as e:
        return SyncResult(
            sync_name=name,
            success=False,
            dry_run=dry_run,
            rsync_exit_code=-1,
            output="",
            error=str(e),
        )

    if proc.returncode != 0:
        return SyncResult(
            sync_name=name,
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
                sync_name=name,
                success=False,
                dry_run=dry_run,
                rsync_exit_code=proc.returncode,
                output=proc.stdout,
                error=f"Snapshot failed: {e}",
            )

    return SyncResult(
        sync_name=name,
        success=True,
        dry_run=dry_run,
        rsync_exit_code=proc.returncode,
        output=proc.stdout,
        snapshot_path=snapshot_path,
    )
