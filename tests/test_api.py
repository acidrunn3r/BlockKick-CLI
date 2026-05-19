"""Tests for register, login, and profile commands."""

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


# ==== profile show ====

class TestProfileShow:

    def test_no_token_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["profile", "show", "--api", API_URL])
        assert result.exit_code != 0
        assert "Not logged in" in result.output

    def test_shows_profile(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        mock_profile = {"wallet_address": "a" * 64, "display_name": "Alice", "bio": "Builder"}
        with patch("blockkick.cli.get_profile", return_value=mock_profile):
            result = runner.invoke(app, ["profile", "show", "--api", API_URL])

        assert result.exit_code == 0
        assert "Alice" in result.output
        assert "Builder" in result.output
        assert "a" * 64 in result.output

    def test_empty_name_shows_dash(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        mock_profile = {"wallet_address": "a" * 64, "display_name": "", "bio": ""}
        with patch("blockkick.cli.get_profile", return_value=mock_profile):
            result = runner.invoke(app, ["profile", "show", "--api", API_URL])

        assert result.exit_code == 0
        assert "—" in result.output

    def test_expired_token_shows_helpful_message(self, isolated_paths):
        import httpx
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        with patch("blockkick.cli.get_profile",
                   side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)):
            result = runner.invoke(app, ["profile", "show", "--api", API_URL])

        assert result.exit_code != 0
        assert "expired" in result.output.lower()

    def test_network_error_exits_with_error(self, isolated_paths):
        import httpx
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        with patch("blockkick.cli.get_profile", side_effect=httpx.ConnectError("refused")):
            result = runner.invoke(app, ["profile", "show", "--api", API_URL])

        assert result.exit_code != 0
        assert "Failed to reach API" in result.output


# ==== profile update ====

class TestProfileUpdate:

    def test_no_token_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["profile", "update", "--name", "Alice", "--api", API_URL])
        assert result.exit_code != 0
        assert "Not logged in" in result.output

    def test_missing_name_exits_with_error(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        result = runner.invoke(app, ["profile", "update", "--api", API_URL])
        assert result.exit_code != 0

    def test_success_shows_updated_name(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        mock_profile = {"wallet_address": "a" * 64, "display_name": "Alice", "bio": ""}
        with patch("blockkick.cli.update_profile", return_value=mock_profile):
            result = runner.invoke(app, ["profile", "update", "--name", "Alice", "--api", API_URL])

        assert result.exit_code == 0
        assert "Alice" in result.output
        assert "updated" in result.output.lower()

    def test_passes_bio_to_api(self, isolated_paths):
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        mock_profile = {"wallet_address": "a" * 64, "display_name": "Alice", "bio": "Builder"}
        with patch("blockkick.cli.update_profile", return_value=mock_profile) as mock_update:
            runner.invoke(app, ["profile", "update", "--name", "Alice", "--bio", "Builder", "--api", API_URL])

        mock_update.assert_called_once_with(API_URL, FAKE_ACCESS_TOKEN, "Alice", "Builder")

    def test_expired_token_shows_helpful_message(self, isolated_paths):
        import httpx
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        with patch("blockkick.cli.update_profile",
                   side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)):
            result = runner.invoke(app, ["profile", "update", "--name", "Alice", "--api", API_URL])

        assert result.exit_code != 0
        assert "expired" in result.output.lower()

    def test_network_error_exits_with_error(self, isolated_paths):
        import httpx
        import blockkick.wallet.keystore as ks
        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        with patch("blockkick.cli.update_profile", side_effect=httpx.ConnectError("refused")):
            result = runner.invoke(app, ["profile", "update", "--name", "Alice", "--api", API_URL])

        assert result.exit_code != 0
        assert "Failed to reach API" in result.output


# ==== projects ====

FAKE_PROJECTS = [
    {"project_id": "proj_aabbccdd11223344", "name": "BlockKick Fund", "goal_amount": 1000, "raised_amount": 250, "status": "ACTIVE"},
    {"project_id": "proj_eeff00112233aabb", "name": "DeFi Launch", "goal_amount": 5000, "raised_amount": 5000, "status": "SUCCESS"},
]


class TestProjects:

    def test_shows_projects_table(self, isolated_paths):
        with patch("blockkick.cli.list_projects", return_value=FAKE_PROJECTS):
            result = runner.invoke(app, ["projects", "--api", API_URL])

        assert result.exit_code == 0
        assert "BlockKick Fund" in result.output
        assert "DeFi Launch" in result.output
        assert "ACTIVE" in result.output
        assert "SUCCESS" in result.output

    def test_empty_list_shows_message(self, isolated_paths):
        with patch("blockkick.cli.list_projects", return_value=[]):
            result = runner.invoke(app, ["projects", "--api", API_URL])

        assert result.exit_code == 0
        assert "No projects" in result.output

    def test_network_error_exits_with_error(self, isolated_paths):
        import httpx
        with patch("blockkick.cli.list_projects", side_effect=httpx.ConnectError("refused")):
            result = runner.invoke(app, ["projects", "--api", API_URL])

        assert result.exit_code != 0
        assert "Failed to reach API" in result.output

    def test_shows_goal_and_raised(self, isolated_paths):
        with patch("blockkick.cli.list_projects", return_value=FAKE_PROJECTS):
            result = runner.invoke(app, ["projects", "--api", API_URL])

        assert "1000" in result.output
        assert "250" in result.output


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
