"""Tests for wallet.keystore module."""

import json
import stat
import pytest
from pathlib import Path
from unittest.mock import patch

from blockkick.wallet.keystore import (
    create_keystore,
    decrypt_keystore,
    get_selected_wallet,
    set_selected_wallet,
    save_session,
    get_session_private_key,
    clear_session,
    get_last_action,
    update_last_action,
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

    def test_creates_file(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        path, _ = create_keystore("password123")
        assert path.exists()

    def test_returns_public_key_hex(self, isolated_paths):
        _, pub = create_keystore("password123")
        assert isinstance(pub, str)
        assert len(pub) == 64

    def test_json_structure(self, isolated_paths):
        path, pub = create_keystore("password123")
        data = json.loads(path.read_text())
        assert data["public_key_hex"] == pub
        assert "timestamp" in data
        assert "version" in data
        assert data["crypto"]["cipher"] == "aes-256-gcm"
        assert data["crypto"]["kdf"] == "scrypt"

    def test_filename_contains_public_key_prefix(self, isolated_paths):
        path, pub = create_keystore("password123")
        assert pub[:16] in path.name


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

    def test_decrypted_key_matches_original(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        import binascii
        path, pub = create_keystore("password123")
        key_bytes = decrypt_keystore(path, "password123")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        derived_pub = Ed25519PrivateKey.from_private_bytes(key_bytes).public_key().public_bytes_raw().hex()
        assert derived_pub == pub


# ==== get_selected_wallet / set_selected_wallet ====

class TestSelectedWallet:

    def test_returns_none_when_no_config(self, isolated_paths):
        assert get_selected_wallet() is None

    def test_roundtrip(self, isolated_paths):
        set_selected_wallet("keystore-abc.json")
        assert get_selected_wallet() == "keystore-abc.json"

    def test_overwrites_previous_selection(self, isolated_paths):
        set_selected_wallet("keystore-first.json")
        set_selected_wallet("keystore-second.json")
        assert get_selected_wallet() == "keystore-second.json"

    def test_returns_none_on_corrupt_config(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.CONFIG_FILE.write_text("not json")
        assert get_selected_wallet() is None

    def test_preserves_other_config_keys(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.CONFIG_FILE.write_text(json.dumps({"other_key": "value"}))
        set_selected_wallet("keystore-abc.json")
        data = json.loads(ks.CONFIG_FILE.read_text())
        assert data["other_key"] == "value"
        assert data["selected_wallet"] == "keystore-abc.json"


# ==== save_session / get_session_private_key / clear_session ====

class TestSession:

    def test_roundtrip(self, isolated_paths):
        key = b"\x01" * 32
        save_session("keystore-abc.json", key)
        filename, returned_key = get_session_private_key()
        assert filename == "keystore-abc.json"
        assert returned_key == key

    def test_session_file_permissions(self, isolated_paths):
        save_session("keystore-abc.json", b"\x02" * 32)
        import blockkick.wallet.keystore as ks
        file_mode = stat.S_IMODE(ks.SESSION_FILE.stat().st_mode)
        assert file_mode == 0o600

    def test_returns_none_tuple_when_no_session(self, isolated_paths):
        filename, key = get_session_private_key()
        assert filename is None
        assert key is None

    def test_clear_session_removes_file(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        save_session("keystore-abc.json", b"\x03" * 32)
        clear_session()
        assert not ks.SESSION_FILE.exists()

    def test_clear_session_no_op_when_no_file(self, isolated_paths):
        clear_session()

    def test_returns_none_on_corrupt_session(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.SESSION_FILE.write_text("not json")
        filename, key = get_session_private_key()
        assert filename is None
        assert key is None


# ==== get_last_action / update_last_action ====

class TestLastAction:

    def test_returns_none_when_no_metadata(self, isolated_paths):
        assert get_last_action("keystore-abc.json") is None

    def test_roundtrip(self, isolated_paths):
        update_last_action("keystore-abc.json")
        ts = get_last_action("keystore-abc.json")
        assert isinstance(ts, int)
        assert ts > 0

    def test_multiple_wallets_are_independent(self, isolated_paths):
        update_last_action("keystore-aaa.json")
        update_last_action("keystore-bbb.json")
        assert get_last_action("keystore-aaa.json") is not None
        assert get_last_action("keystore-bbb.json") is not None
        assert get_last_action("keystore-ccc.json") is None

    def test_update_overwrites_previous_timestamp(self, isolated_paths):
        import time
        update_last_action("keystore-abc.json")
        first = get_last_action("keystore-abc.json")
        time.sleep(1.1)
        update_last_action("keystore-abc.json")
        second = get_last_action("keystore-abc.json")
        assert second > first

    def test_returns_none_on_corrupt_metadata(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.METADATA_FILE.write_text("not json")
        assert get_last_action("keystore-abc.json") is None
