"""
Command-line interface for SSB.
"""

from pathlib import Path
from typing import Optional

import typer

from .backup import BackupManager
from .encryption import EncryptionManager

app = typer.Typer(
    name="ssb",
    help="Simple Safe Backup - A secure backup solution",
    no_args_is_help=True,
)


@app.command()
def backup(
    source: str = typer.Argument(..., help="Source file or directory to backup"),
    backup_dir: str = typer.Argument(..., help="Directory to store backups"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Name for the backup"),
    encrypt: bool = typer.Option(False, "--encrypt", "-e", help="Encrypt the backup"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password for encryption"),
) -> None:
    """Create a backup of the specified source."""
    try:
        source_path = Path(source)
        if not source_path.exists():
            typer.echo(f"Error: Source not found: {source}", err=True)
            raise typer.Exit(1)

        # Create encryption manager if needed
        encryption_manager = None
        if encrypt:
            if not password:
                password = typer.prompt("Enter encryption password", hide_input=True)
            if password:  # Ensure password is not None
                encryption_manager = EncryptionManager.from_password(password)

        # Create backup
        backup_manager = BackupManager(backup_dir, encryption_manager)
        backup_path = backup_manager.create_backup(source, name)

        typer.echo(f"Backup created successfully: {backup_path}")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def restore(
    backup_name: str = typer.Argument(..., help="Name of the backup to restore"),
    backup_dir: str = typer.Argument(..., help="Directory containing backups"),
    destination: str = typer.Argument(..., help="Destination path for restoration"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password for decryption"),
) -> None:
    """Restore a backup to the specified destination."""
    try:
        backup_manager = BackupManager(backup_dir)

        # Check if backup exists
        backups = backup_manager.list_backups()
        if backup_name not in backups:
            typer.echo(f"Error: Backup not found: {backup_name}", err=True)
            raise typer.Exit(1)

        # Restore backup
        restored_path = backup_manager.restore_backup(backup_name, destination)
        typer.echo(f"Backup restored successfully: {restored_path}")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def list_backups(
    backup_dir: str = typer.Argument(..., help="Directory containing backups"),
) -> None:
    """List all available backups."""
    try:
        backup_manager = BackupManager(backup_dir)
        backups = backup_manager.list_backups()

        if not backups:
            typer.echo("No backups found.")
        else:
            typer.echo("Available backups:")
            for backup in sorted(backups):
                typer.echo(f"  - {backup}")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
