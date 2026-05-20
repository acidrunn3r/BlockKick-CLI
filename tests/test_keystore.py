"""Tests for wallet.keystore module."""

import json

import pytest

from blockkick.wallet.keystore import (
    create_keystore,
    decrypt_keystore,
    get_selected_wallet,
    get_session_private_key,
    save_session,
    set_selected_wallet,
)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    """Redirect all blockkick home paths to tmp_path."""
    import blockkick.wallet.keystore as ks

    keystore_dir = tmp_path / "keystores"
    keystore_dir.mkdir()

    monkeypatch.setattr(ks, "KEYSTORE_DIR", keystore_dir)
    monkeypatch.setattr(ks, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(ks, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(ks, "METADATA_FILE", tmp_path / "metadata.json")

    return tmp_path


# ==== create_keystore ====


class TestCreateKeystore:

    def test_json_structure(self, isolated_paths):
        path, pub = create_keystore("password123")
        data = json.loads(path.read_text())
        assert data["public_key_hex"] == pub
        assert "timestamp" in data
        assert data["crypto"]["cipher"] == "aes-256-gcm"
        assert data["crypto"]["kdf"] == "scrypt"


# ==== decrypt_keystore ====


class TestDecryptKeystore:

    def test_correct_password_returns_bytes(self, isolated_paths):
        path, _ = create_keystore("password123")
        key = decrypt_keystore(path, "password123")
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_wrong_password_raises_value_error(self, isolated_paths):
        path, _ = create_keystore("password123")
        with pytest.raises(ValueError):
            decrypt_keystore(path, "wrongpassword")


# ==== get_selected_wallet / set_selected_wallet ====


class TestSelectedWallet:

    def test_roundtrip(self, isolated_paths):
        set_selected_wallet("keystore-abc.json")
        assert get_selected_wallet() == "keystore-abc.json"


# ==== save_session / get_session_private_key / clear_session ====


class TestSession:

    def test_roundtrip(self, isolated_paths):
        key = b"\x01" * 32
        save_session("keystore-abc.json", key)
        filename, returned_key = get_session_private_key()
        assert filename == "keystore-abc.json"
        assert returned_key == key
