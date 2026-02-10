#!/usr/bin/env python3
"""
Basic usage example for SSB (Simple Safe Backup).
"""

import tempfile
from pathlib import Path
from ssb import BackupManager, EncryptionManager


def main():
    """Demonstrate basic backup functionality."""
    print("SSB (Simple Safe Backup) - Basic Usage Example")
    print("=" * 50)

    # Create temporary directories for demonstration
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create some test files
        source_file = temp_path / "important_document.txt"
        source_file.write_text(
            "This is a very important document that needs backup!"
        )

        source_dir = temp_path / "project_files"
        source_dir.mkdir()
        (source_dir / "main.py").write_text("print('Hello, World!')")
        (source_dir / "config.json").write_text('{"version": "1.0.0"}')
        (source_dir / "README.md").write_text(
            "# My Project\n\nThis is my project."
        )

        # Create backup directory
        backup_dir = temp_path / "backups"
        backup_dir.mkdir()

        print(f"Created test files in: {temp_path}")
        print(f"Backup directory: {backup_dir}")
        print()

        # 1. Simple backup
        print("1. Creating simple backup...")
        backup_manager = BackupManager(str(backup_dir))

        # Backup a file
        file_backup_path = backup_manager.create_backup(str(source_file))
        print(f"   File backup created: {file_backup_path}")

        # Backup a directory
        dir_backup_path = backup_manager.create_backup(str(source_dir))
        print(f"   Directory backup created: {dir_backup_path}")

        # List backups
        backups = backup_manager.list_backups()
        print(f"   Available backups: {backups}")
        print()

        # 2. Encrypted backup
        print("2. Creating encrypted backup...")
        encryption_manager = EncryptionManager.from_password(
            "my_secure_password"
        )
        secure_backup_manager = BackupManager(
            str(backup_dir), encryption_manager
        )

        # Create encrypted backup with custom name
        secure_backup_path = secure_backup_manager.create_backup(
            str(source_file), "encrypted_document"
        )
        print(f"   Encrypted backup created: {secure_backup_path}")
        print()

        # 3. Restore example
        print("3. Restoring backup...")
        restore_dir = temp_path / "restored"
        restore_dir.mkdir()

        restored_path = backup_manager.restore_backup(
            "important_document.txt",
            str(restore_dir / "restored_document.txt"),
        )
        print(f"   Backup restored to: {restored_path}")

        # Verify restoration
        restored_content = Path(restored_path).read_text()
        print(f"   Restored content: {restored_content}")
        print()

        print("Example completed successfully!")
        print("All files and directories were created in temporary locations.")


if __name__ == "__main__":
    main()
