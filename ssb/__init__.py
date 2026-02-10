"""
Simple Safe Backup (SSB) - A secure backup solution.

This package provides tools for creating secure, encrypted backups
of files and directories.
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .backup import BackupManager
from .encryption import EncryptionManager

__all__ = ["BackupManager", "EncryptionManager"]
