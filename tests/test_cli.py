"""Tests for CLI commands."""

import json
import pytest
from typer.testing import CliRunner

from blockkick.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    """Redirect all blockkick home paths to tmp_path."""
    import blockkick.wallet.keystore as ks
    import blockkick.cli as cli

    keystore_dir = tmp_path / "keystores"
    keystore_dir.mkdir()

    monkeypatch.setattr(ks, "KEYSTORE_DIR", keystore_dir)
    monkeypatch.setattr(ks, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(ks, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(ks, "METADATA_FILE", tmp_path / "metadata.json")
    # cli.py imports KEYSTORE_DIR by value, so patch it there too
    monkeypatch.setattr(cli, "KEYSTORE_DIR", keystore_dir)

    return tmp_path


def _create_wallet(password: str = "password123") -> str:
    """Helper: create a wallet and return its filename."""
    import blockkick.wallet.keystore as ks
    before = set(ks.KEYSTORE_DIR.glob("keystore-*.json"))
    result = runner.invoke(app, ["wallet", "create", "--password", password])
    assert result.exit_code == 0
    after = set(ks.KEYSTORE_DIR.glob("keystore-*.json"))
    new_files = after - before
    assert len(new_files) == 1
    return next(iter(new_files)).name


# ==== wallet list ====

class TestWalletList:

    def test_empty_state_message(self, isolated_paths):
        result = runner.invoke(app, ["wallet", "list"])
        assert result.exit_code == 0
        assert "No wallets found" in result.output

    def test_shows_wallets(self, isolated_paths):
        _create_wallet()
        result = runner.invoke(app, ["wallet", "list"])
        assert result.exit_code == 0
        assert "keystore-" in result.output

    def test_selected_wallet_marked(self, isolated_paths):
        filename = _create_wallet()
        runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        result = runner.invoke(app, ["wallet", "list"])
        assert "*" in result.output

    def test_no_marker_when_nothing_selected(self, isolated_paths):
        _create_wallet()
        result = runner.invoke(app, ["wallet", "list"])
        assert "*" not in result.output

    def test_most_recently_used_sorts_first(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        first = _create_wallet()
        second = _create_wallet("otherpass1")
        # Override metadata to guarantee a known ordering
        ks.METADATA_FILE.write_text(json.dumps({
            first: {"last_action": 1000},
            second: {"last_action": 2000},
        }))
        result = runner.invoke(app, ["wallet", "list"])
        lines = result.output.splitlines()
        first_row = next(i for i, line in enumerate(lines) if first[:20] in line)
        second_row = next(i for i, line in enumerate(lines) if second[:20] in line)
        assert second_row < first_row


# ==== wallet info ====

class TestWalletInfo:

    def test_shows_public_key(self, isolated_paths):
        filename = _create_wallet()
        result = runner.invoke(app, ["wallet", "info", filename])
        assert result.exit_code == 0
        assert "Public key" in result.output

    def test_shows_cipher_and_kdf(self, isolated_paths):
        filename = _create_wallet()
        result = runner.invoke(app, ["wallet", "info", filename])
        assert "AES-256-GCM" in result.output
        assert "scrypt" in result.output

    def test_missing_file_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["wallet", "info", "keystore-nonexistent.json"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ==== wallet select ====

class TestWalletSelect:

    def test_correct_password_succeeds(self, isolated_paths):
        filename = _create_wallet()
        result = runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        assert result.exit_code == 0
        assert "Active wallet set to" in result.output

    def test_persists_selection(self, isolated_paths):
        from blockkick.wallet.keystore import get_selected_wallet
        filename = _create_wallet()
        runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        assert get_selected_wallet() == filename

    def test_saves_session(self, isolated_paths):
        from blockkick.wallet.keystore import get_session_private_key
        filename = _create_wallet()
        runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        session_filename, key = get_session_private_key()
        assert session_filename == filename
        assert isinstance(key, bytes)

    def test_wrong_password_exits_with_error(self, isolated_paths):
        filename = _create_wallet()
        result = runner.invoke(app, ["wallet", "select", filename, "--password", "wrongpassword"])
        assert result.exit_code != 0
        assert "error" in result.output.lower()

    def test_missing_file_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["wallet", "select", "keystore-nonexistent.json", "--password", "password123"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_updates_last_action(self, isolated_paths):
        from blockkick.wallet.keystore import get_last_action
        filename = _create_wallet()
        runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        assert get_last_action(filename) is not None


# ==== wallet deselect ====

class TestWalletDeselect:

    def test_clears_selection(self, isolated_paths):
        from blockkick.wallet.keystore import get_selected_wallet
        filename = _create_wallet()
        runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        runner.invoke(app, ["wallet", "deselect"])
        assert get_selected_wallet() != filename

    def test_clears_session(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        filename = _create_wallet()
        runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        runner.invoke(app, ["wallet", "deselect"])
        assert not ks.SESSION_FILE.exists()

    def test_no_op_message_when_nothing_selected(self, isolated_paths):
        result = runner.invoke(app, ["wallet", "deselect"])
        assert result.exit_code == 0
        assert "No wallet" in result.output
