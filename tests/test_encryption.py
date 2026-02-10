"""
Tests for encryption functionality.
"""

import pytest
import tempfile
from pathlib import Path
from ssb.encryption import EncryptionManager


class TestEncryptionManager:
    """Test cases for EncryptionManager."""

    def test_init(self):
        """Test EncryptionManager initialization."""
        encryption_manager = EncryptionManager()
        assert encryption_manager.key is not None
        assert len(encryption_manager.key) > 0

    def test_init_with_key(self):
        """Test EncryptionManager initialization with provided key."""
        key = EncryptionManager().key
        encryption_manager = EncryptionManager(key)
        assert encryption_manager.key == key

    def test_from_password(self):
        """Test creating EncryptionManager from password."""
        password = "test_password"
        encryption_manager = EncryptionManager.from_password(password)
        assert encryption_manager.key is not None

    def test_encrypt_decrypt_file(self):
        """Test encrypting and decrypting a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test file
            original_file = Path(temp_dir) / "original.txt"
            original_content = "Hello, World! This is a test file."
            original_file.write_text(original_content)

            encrypted_file = Path(temp_dir) / "encrypted.bin"
            decrypted_file = Path(temp_dir) / "decrypted.txt"

            encryption_manager = EncryptionManager()

            # Encrypt the file
            encryption_manager.encrypt_file(
                str(original_file), str(encrypted_file)
            )
            assert encrypted_file.exists()

            # Decrypt the file
            encryption_manager.decrypt_file(
                str(encrypted_file), str(decrypted_file)
            )
            assert decrypted_file.exists()

            # Check content
            assert decrypted_file.read_text() == original_content

    def test_encrypt_nonexistent_file(self):
        """Test encrypting a non-existent file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            encryption_manager = EncryptionManager()
            output_file = Path(temp_dir) / "output.bin"

            with pytest.raises(FileNotFoundError):
                encryption_manager.encrypt_file(
                    "/nonexistent/file.txt", str(output_file)
                )

    def test_save_load_key(self):
        """Test saving and loading encryption keys."""
        with tempfile.TemporaryDirectory() as temp_dir:
            encryption_manager = EncryptionManager()
            key_file = Path(temp_dir) / "key.bin"

            # Save the key
            encryption_manager.save_key(str(key_file))
            assert key_file.exists()

            # Load the key
            loaded_manager = EncryptionManager.load_key(str(key_file))
            assert loaded_manager.key == encryption_manager.key

    def test_decrypt_with_wrong_key(self):
        """Test decrypting with wrong key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create and encrypt a file
            original_file = Path(temp_dir) / "original.txt"
            original_file.write_text("Test content")

            encrypted_file = Path(temp_dir) / "encrypted.bin"
            decrypted_file = Path(temp_dir) / "decrypted.txt"

            encryption_manager1 = EncryptionManager()
            encryption_manager1.encrypt_file(
                str(original_file), str(encrypted_file)
            )

            # Try to decrypt with different key
            encryption_manager2 = EncryptionManager()

            with pytest.raises(ValueError):
                encryption_manager2.decrypt_file(
                    str(encrypted_file), str(decrypted_file)
                )
