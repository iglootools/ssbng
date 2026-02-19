"""Typer CLI: run and status commands."""

from __future__ import annotations

import json
from typing import Annotated, Optional

import typer

from .checks import check_all_syncs
from .configloader import ConfigError, load_config
from .output import (
    OutputFormat,
    print_human_results,
    print_human_status,
)
from .runner import run_all_syncs

app = typer.Typer(
    name="ssb",
    help="Simple Safe Backup - An rsync-based backup tool",
    no_args_is_help=True,
)


def _load_or_exit(config_path: str | None) -> object:
    """Load config or exit with code 2 on error."""
    try:
        return load_config(config_path)
    except ConfigError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(2)


@app.command()
def status(
    config: Annotated[
        Optional[str],
        typer.Option("--config", help="Path to config file"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: human or json"),
    ] = "human",
) -> None:
    """Show status of volumes and syncs."""
    cfg = _load_or_exit(config)
    from .config import Config

    assert isinstance(cfg, Config)
    vol_statuses, sync_statuses = check_all_syncs(cfg)

    match OutputFormat(output):
        case OutputFormat.JSON:
            data = {
                "volumes": [v.model_dump() for v in vol_statuses.values()],
                "syncs": [s.model_dump() for s in sync_statuses.values()],
            }
            typer.echo(json.dumps(data, indent=2))
        case OutputFormat.HUMAN:
            print_human_status(vol_statuses, sync_statuses, cfg)


@app.command()
def run(
    config: Annotated[
        Optional[str],
        typer.Option("--config", help="Path to config file"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Perform a dry run"),
    ] = False,
    sync: Annotated[
        Optional[list[str]],
        typer.Option("--sync", help="Sync name(s) to run"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: human or json"),
    ] = "human",
) -> None:
    """Run backup syncs."""
    cfg = _load_or_exit(config)
    from .config import Config

    assert isinstance(cfg, Config)

    sync_statuses, results = run_all_syncs(
        cfg, dry_run=dry_run, sync_names=sync
    )

    match OutputFormat(output):
        case OutputFormat.JSON:
            data = [r.model_dump() for r in results]
            typer.echo(json.dumps(data, indent=2))
        case OutputFormat.HUMAN:
            print_human_results(results, dry_run)

    if any(not r.success for r in results):
        raise typer.Exit(1)


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
