"""
Backup management functionality for SSB.
"""

import shutil
from pathlib import Path
from typing import List, Optional
from .encryption import EncryptionManager


class BackupManager:
    """Manages backup operations for files and directories."""

    def __init__(
        self,
        backup_dir: str,
        encryption_manager: Optional[EncryptionManager] = None,
    ):
        """
        Initialize the backup manager.

        Args:
            backup_dir: Directory where backups will be stored
            encryption_manager: Optional encryption manager for secure backups
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.encryption_manager = encryption_manager or EncryptionManager()

    def create_backup(
        self, source_path: str, backup_name: Optional[str] = None
    ) -> str:
        """
        Create a backup of the specified source.

        Args:
            source_path: Path to the file or directory to backup
            backup_name: Optional name for the backup (defaults to source name)

        Returns:
            Path to the created backup
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(
                f"Source path does not exist: {source_path}"
            )

        if backup_name is None:
            backup_name = source.name

        backup_path = self.backup_dir / backup_name

        # Check if source and destination are the same
        if source.resolve() == backup_path.resolve():
            raise ValueError(
                f"Cannot backup to the same location: {source_path}"
            )

        if source.is_file():
            return self._backup_file(source, backup_path)
        elif source.is_dir():
            return self._backup_directory(source, backup_path)
        else:
            raise ValueError(
                f"Source path is neither a file nor directory: {source_path}"
            )

    def _backup_file(self, source: Path, backup_path: Path) -> str:
        """Backup a single file."""
        shutil.copy2(source, backup_path)
        return str(backup_path)

    def _backup_directory(self, source: Path, backup_path: Path) -> str:
        """Backup a directory."""
        shutil.copytree(source, backup_path, dirs_exist_ok=True)
        return str(backup_path)

    def list_backups(self) -> List[str]:
        """List all available backups."""
        return [
            item.name for item in self.backup_dir.iterdir() if item.exists()
        ]

    def restore_backup(self, backup_name: str, destination: str) -> str:
        """
        Restore a backup to the specified destination.

        Args:
            backup_name: Name of the backup to restore
            destination: Path where the backup should be restored

        Returns:
            Path to the restored backup
        """
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_name}")

        dest_path = Path(destination)

        if backup_path.is_file():
            shutil.copy2(backup_path, dest_path)
        else:
            shutil.copytree(backup_path, dest_path, dirs_exist_ok=True)

        return str(dest_path)
