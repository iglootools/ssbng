# SSB (Simple Safe Backup)

A secure backup solution for files and directories with optional encryption.

## Features

- **Simple Backup**: Easy-to-use backup functionality for files and directories
- **Encryption**: Optional AES encryption for secure backups
- **CLI Interface**: Command-line tool for quick backups and restores
- **Python API**: Programmatic access to backup functionality

## Installation

### Using Poetry (Recommended)

**Requirements:**
- Python 3.13 or higher
- Poetry

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ssbng
   ```

2. Install dependencies and the package:
   ```bash
   poetry install
   ```

3. Activate the virtual environment:
   ```bash
   poetry shell
   ```

### Using pip

```bash
pip install .
```

## Usage

### Command Line Interface

The `ssb` command provides a simple interface for backup operations:

#### Create a backup:
```bash
# Basic backup
ssb backup /path/to/source /path/to/backup/dir

# Encrypted backup
ssb backup /path/to/source /path/to/backup/dir --encrypt

# Named backup
ssb backup /path/to/source /path/to/backup/dir --name my_backup

# With password
ssb backup /path/to/source /path/to/backup/dir --encrypt --password mypassword
```

#### List available backups:
```bash
ssb list-backups /path/to/backup/dir
```

#### Restore a backup:
```bash
ssb restore backup_name /path/to/backup/dir /path/to/restore/dir
```

#### Get help:
```bash
ssb --help
ssb backup --help
ssb restore --help
ssb list-backups --help
```

### Python API

```python
from ssb import BackupManager, EncryptionManager

# Create a backup manager
backup_manager = BackupManager("/path/to/backup/dir")

# Create a simple backup
backup_path = backup_manager.create_backup("/path/to/source")

# Create an encrypted backup
encryption_manager = EncryptionManager.from_password("my_password")
backup_manager = BackupManager("/path/to/backup/dir", encryption_manager)
backup_path = backup_manager.create_backup("/path/to/source")

# List backups
backups = backup_manager.list_backups()

# Restore a backup
restored_path = backup_manager.restore_backup("backup_name", "/path/to/restore")
```

## Development

### Setup Development Environment

**Requirements:**
- Python 3.13 or higher

1. Install Poetry if you haven't already:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Activate the virtual environment:
   ```bash
   poetry shell
   ```

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
```

### Type Checking

```bash
mypy ssbng/
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

