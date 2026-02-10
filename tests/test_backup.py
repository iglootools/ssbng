"""
Tests for backup functionality.
"""

import pytest
import tempfile
from pathlib import Path
from ssb.backup import BackupManager
from ssb.encryption import EncryptionManager


class TestBackupManager:
    """Test cases for BackupManager."""

    def test_init(self):
        """Test BackupManager initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_manager = BackupManager(temp_dir)
            assert backup_manager.backup_dir == Path(temp_dir)
            assert isinstance(
                backup_manager.encryption_manager, EncryptionManager
            )

    def test_create_file_backup(self):
        """Test creating a backup of a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test file
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("Hello, World!")

            # Create a separate backup directory
            backup_dir = Path(temp_dir) / "backups"
            backup_manager = BackupManager(str(backup_dir))
            backup_path = backup_manager.create_backup(str(test_file))

            assert Path(backup_path).exists()
            assert Path(backup_path).read_text() == "Hello, World!"

    def test_create_directory_backup(self):
        """Test creating a backup of a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test directory with files
            test_dir = Path(temp_dir) / "test_dir"
            test_dir.mkdir()
            (test_dir / "file1.txt").write_text("File 1")
            (test_dir / "file2.txt").write_text("File 2")

            # Create a separate backup directory
            backup_dir = Path(temp_dir) / "backups"
            backup_manager = BackupManager(str(backup_dir))
            backup_path = backup_manager.create_backup(str(test_dir))

            assert Path(backup_path).exists()
            assert (Path(backup_path) / "file1.txt").exists()
            assert (Path(backup_path) / "file2.txt").exists()

    def test_backup_nonexistent_source(self):
        """Test backup with non-existent source."""
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_dir = Path(temp_dir) / "backups"
            backup_manager = BackupManager(str(backup_dir))

            with pytest.raises(FileNotFoundError):
                backup_manager.create_backup("/nonexistent/path")

    def test_list_backups(self):
        """Test listing backups."""
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_dir = Path(temp_dir) / "backups"
            backup_manager = BackupManager(str(backup_dir))

            # Create some test files in backup directory
            (backup_dir / "backup1").touch()
            (backup_dir / "backup2").touch()

            backups = backup_manager.list_backups()
            assert "backup1" in backups
            assert "backup2" in backups
