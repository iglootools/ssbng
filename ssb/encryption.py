"""
Encryption functionality for secure backups.
"""

import os
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


class EncryptionManager:
    """Manages encryption and decryption of backup files."""

    def __init__(self, key: Optional[bytes] = None):
        """
        Initialize the encryption manager.

        Args:
            key: Optional encryption key (will generate one if not provided)
        """
        if key is None:
            self.key = Fernet.generate_key()
        else:
            self.key = key
        self.cipher = Fernet(self.key)

    @classmethod
    def from_password(
        cls, password: str, salt: Optional[bytes] = None
    ) -> "EncryptionManager":
        """
        Create an encryption manager from a password.

        Args:
            password: Password to derive the key from
            salt: Optional salt for key derivation

        Returns:
            EncryptionManager instance
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return cls(key)

    def encrypt_file(self, input_path: str, output_path: str) -> None:
        """
        Encrypt a file.

        Args:
            input_path: Path to the file to encrypt
            output_path: Path where the encrypted file will be saved
        """
        input_file = Path(input_path)
        output_file = Path(output_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        with open(input_file, "rb") as f:
            data = f.read()

        encrypted_data = self.cipher.encrypt(data)

        with open(output_file, "wb") as f:
            f.write(encrypted_data)

    def decrypt_file(self, input_path: str, output_path: str) -> None:
        """
        Decrypt a file.

        Args:
            input_path: Path to the encrypted file
            output_path: Path where the decrypted file will be saved
        """
        input_file = Path(input_path)
        output_file = Path(output_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        with open(input_file, "rb") as f:
            encrypted_data = f.read()

        try:
            decrypted_data = self.cipher.decrypt(encrypted_data)
        except Exception as e:
            raise ValueError(f"Failed to decrypt file: {e}")

        with open(output_file, "wb") as f:
            f.write(decrypted_data)

    def get_key(self) -> bytes:
        """Get the current encryption key."""
        return self.key

    def save_key(self, key_path: str) -> None:
        """
        Save the encryption key to a file.

        Args:
            key_path: Path where the key will be saved
        """
        with open(key_path, "wb") as f:
            f.write(self.key)

    @classmethod
    def load_key(cls, key_path: str) -> "EncryptionManager":
        """
        Load an encryption manager from a saved key file.

        Args:
            key_path: Path to the saved key file

        Returns:
            EncryptionManager instance
        """
        with open(key_path, "rb") as f:
            key = f.read()
        return cls(key)
