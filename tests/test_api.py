"""Tests for register and login commands."""

import json
import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from blockkick.cli import app

runner = CliRunner()

API_URL = "http://localhost:8000"
FAKE_NONCE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_ACCESS_TOKEN = "access.token.here"
FAKE_REFRESH_TOKEN = "refresh.token.here"
FAKE_TOKENS = {
    "access_token": FAKE_ACCESS_TOKEN,
    "refresh_token": FAKE_REFRESH_TOKEN,
    "token_type": "Bearer",
    "expires_in": 3600,
}


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
    monkeypatch.setattr(ks, "API_AUTH_FILE", tmp_path / "api_auth.json")
    monkeypatch.setattr(cli, "KEYSTORE_DIR", keystore_dir)

    return tmp_path


def _create_and_select_wallet(password: str = "password123") -> str:
    """Helper: create a wallet and select it (session active)."""
    result = runner.invoke(app, ["wallet", "create", "--password", password])
    assert result.exit_code == 0

    import blockkick.wallet.keystore as ks
    files = list(ks.KEYSTORE_DIR.glob("keystore-*.json"))
    filename = files[0].name

    result = runner.invoke(app, ["wallet", "select", filename, "--password", password])
    assert result.exit_code == 0
    return filename


# ==== register ====

class TestRegister:

    def test_no_wallet_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["register", "--api", API_URL])
        assert result.exit_code != 0
        assert "No wallet selected" in result.output

    def test_success_stores_tokens(self, isolated_paths):
        _create_and_select_wallet()

        with patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE), \
             patch("blockkick.cli.auth_login", return_value=FAKE_TOKENS):
            result = runner.invoke(app, ["register", "--api", API_URL])

        assert result.exit_code == 0
        assert "Registered" in result.output

        import blockkick.wallet.keystore as ks
        assert ks.get_api_access_token() == FAKE_ACCESS_TOKEN

    def test_success_with_name(self, isolated_paths):
        _create_and_select_wallet()
        mock_profile = {"wallet_address": "a" * 64, "display_name": "Alice", "bio": ""}

        with patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE), \
             patch("blockkick.cli.auth_login", return_value=FAKE_TOKENS), \
             patch("blockkick.cli.update_profile", return_value=mock_profile) as mock_update:
            result = runner.invoke(app, ["register", "--api", API_URL, "--name", "Alice"])

        assert result.exit_code == 0
        assert "Alice" in result.output
        mock_update.assert_called_once()

    def test_no_name_skips_profile_update(self, isolated_paths):
        _create_and_select_wallet()

        with patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE), \
             patch("blockkick.cli.auth_login", return_value=FAKE_TOKENS), \
             patch("blockkick.cli.update_profile") as mock_update:
            result = runner.invoke(app, ["register", "--api", API_URL])

        assert result.exit_code == 0
        mock_update.assert_not_called()

    def test_challenge_failure_exits_with_error(self, isolated_paths):
        import httpx
        _create_and_select_wallet()

        with patch("blockkick.cli.request_challenge", side_effect=httpx.ConnectError("refused")):
            result = runner.invoke(app, ["register", "--api", API_URL])

        assert result.exit_code != 0
        assert "Failed to reach API" in result.output

    def test_login_failure_exits_with_error(self, isolated_paths):
        import httpx
        _create_and_select_wallet()

        mock_response = MagicMock()
        mock_response.text = "invalid signature"

        with patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE), \
             patch("blockkick.cli.auth_login",
                   side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)):
            result = runner.invoke(app, ["register", "--api", API_URL])

        assert result.exit_code != 0
        assert "Authentication failed" in result.output


# ==== login ====

class TestLogin:

    def test_no_wallet_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["login", "--api", API_URL])
        assert result.exit_code != 0
        assert "No wallet selected" in result.output

    def test_success_stores_tokens(self, isolated_paths):
        _create_and_select_wallet()
        mock_profile = {"wallet_address": "a" * 64, "display_name": "Alice", "bio": ""}

        with patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE), \
             patch("blockkick.cli.auth_login", return_value=FAKE_TOKENS), \
             patch("blockkick.cli.get_profile", return_value=mock_profile):
            result = runner.invoke(app, ["login", "--api", API_URL])

        assert result.exit_code == 0
        assert "Logged in" in result.output

        import blockkick.wallet.keystore as ks
        assert ks.get_api_access_token() == FAKE_ACCESS_TOKEN

    def test_shows_display_name_on_success(self, isolated_paths):
        _create_and_select_wallet()
        mock_profile = {"wallet_address": "a" * 64, "display_name": "Alice", "bio": ""}

        with patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE), \
             patch("blockkick.cli.auth_login", return_value=FAKE_TOKENS), \
             patch("blockkick.cli.get_profile", return_value=mock_profile):
            result = runner.invoke(app, ["login", "--api", API_URL])

        assert "Alice" in result.output

    def test_challenge_failure_exits_with_error(self, isolated_paths):
        import httpx
        _create_and_select_wallet()

        with patch("blockkick.cli.request_challenge", side_effect=httpx.ConnectError("refused")):
            result = runner.invoke(app, ["login", "--api", API_URL])

        assert result.exit_code != 0
        assert "Failed to reach API" in result.output

    def test_login_failure_exits_with_error(self, isolated_paths):
        import httpx
        _create_and_select_wallet()

        mock_response = MagicMock()
        mock_response.text = "unauthorized"

        with patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE), \
             patch("blockkick.cli.auth_login",
                   side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)):
            result = runner.invoke(app, ["login", "--api", API_URL])

        assert result.exit_code != 0
        assert "Authentication failed" in result.output

    def test_overwrites_previous_token(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        _create_and_select_wallet()

        ks.save_api_tokens("old_token", "old_refresh")

        new_tokens = {**FAKE_TOKENS, "access_token": "new_token", "refresh_token": "new_refresh"}
        mock_profile = {"wallet_address": "a" * 64, "display_name": "", "bio": ""}

        with patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE), \
             patch("blockkick.cli.auth_login", return_value=new_tokens), \
             patch("blockkick.cli.get_profile", return_value=mock_profile):
            runner.invoke(app, ["login", "--api", API_URL])

        assert ks.get_api_access_token() == "new_token"


# ==== config set-api ====

class TestConfigSetApi:

    def test_persists_url(self, isolated_paths):
        from blockkick.wallet.keystore import get_api_url
        runner.invoke(app, ["config", "set-api", API_URL])
        assert get_api_url() == API_URL

    def test_shows_confirmation(self, isolated_paths):
        result = runner.invoke(app, ["config", "set-api", API_URL])
        assert result.exit_code == 0
        assert API_URL in result.output

    def test_overwrites_previous_url(self, isolated_paths):
        from blockkick.wallet.keystore import get_api_url
        runner.invoke(app, ["config", "set-api", "http://localhost:9000"])
        runner.invoke(app, ["config", "set-api", API_URL])
        assert get_api_url() == API_URL
