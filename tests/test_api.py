"""Tests for register, login, and profile commands."""

from unittest.mock import patch

import httpx
import pytest
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
    import blockkick.cli as cli
    import blockkick.wallet.keystore as ks

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

        with (
            patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE),
            patch("blockkick.cli.auth_login", return_value=FAKE_TOKENS),
        ):
            result = runner.invoke(app, ["register", "--api", API_URL])

        assert result.exit_code == 0
        assert "Registered" in result.output

        import blockkick.wallet.keystore as ks

        assert ks.get_api_access_token() == FAKE_ACCESS_TOKEN


# ==== login ====


class TestLogin:

    def test_success_stores_tokens(self, isolated_paths):
        _create_and_select_wallet()
        mock_profile = {"wallet_address": "a" * 64, "display_name": "Alice", "bio": ""}

        with (
            patch("blockkick.cli.request_challenge", return_value=FAKE_NONCE),
            patch("blockkick.cli.auth_login", return_value=FAKE_TOKENS),
            patch("blockkick.cli.get_profile", return_value=mock_profile),
        ):
            result = runner.invoke(app, ["login", "--api", API_URL])

        assert result.exit_code == 0
        assert "Logged in" in result.output

        import blockkick.wallet.keystore as ks

        assert ks.get_api_access_token() == FAKE_ACCESS_TOKEN


# ==== profile show ====


class TestProfileShow:

    def test_shows_profile(self, isolated_paths):
        import blockkick.wallet.keystore as ks

        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        mock_profile = {
            "wallet_address": "a" * 64,
            "display_name": "Alice",
            "bio": "Builder",
        }
        with patch("blockkick.cli.get_profile", return_value=mock_profile):
            result = runner.invoke(app, ["profile", "show", "--api", API_URL])

        assert result.exit_code == 0
        assert "Alice" in result.output
        assert "Builder" in result.output
        assert "a" * 64 in result.output


# ==== profile update ====


class TestProfileUpdate:

    def test_success_shows_updated_name(self, isolated_paths):
        import blockkick.wallet.keystore as ks

        ks.save_api_tokens(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN)

        mock_profile = {"wallet_address": "a" * 64, "display_name": "Alice", "bio": ""}
        with patch("blockkick.cli.update_profile", return_value=mock_profile):
            result = runner.invoke(
                app, ["profile", "update", "--name", "Alice", "--api", API_URL]
            )

        assert result.exit_code == 0
        assert "Alice" in result.output
        assert "updated" in result.output.lower()


# ==== projects ====

FAKE_PROJECTS = [
    {
        "project_id": "proj_aabbccdd11223344",
        "name": "BlockKick Fund",
        "goal_amount": 1000,
        "raised_amount": 250,
        "status": "ACTIVE",
    },
    {
        "project_id": "proj_eeff00112233aabb",
        "name": "DeFi Launch",
        "goal_amount": 5000,
        "raised_amount": 5000,
        "status": "SUCCESS",
    },
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


# ==== history ====

FAKE_WALLET = "a" * 64
FAKE_TX_HISTORY = [
    {
        "tx_id": "b" * 64,
        "tx_type": "Transfer",
        "from_address": FAKE_WALLET,
        "to_address": "c" * 64,
        "amount": 10,
        "project_id": None,
        "block_height": 5,
        "timestamp": 1000000,
    },
    {
        "tx_id": "d" * 64,
        "tx_type": "Coinbase",
        "from_address": None,
        "to_address": FAKE_WALLET,
        "amount": 50,
        "project_id": None,
        "block_height": 3,
        "timestamp": 999000,
    },
]


class TestHistory:

    def test_shows_history_table(self, isolated_paths):
        import blockkick.wallet.keystore as ks

        ks.set_selected_wallet("keystore-fake.json")
        keystore_file = isolated_paths / "keystores" / "keystore-fake.json"
        import json

        keystore_file.write_text(json.dumps({"public_key_hex": FAKE_WALLET}))

        with patch(
            "blockkick.cli.get_wallet_transactions", return_value=FAKE_TX_HISTORY
        ):
            result = runner.invoke(app, ["history", "--api", API_URL])

        assert result.exit_code == 0
        assert "Transfer" in result.output
        assert "Mining reward" in result.output

    def test_no_wallet_selected_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["history", "--api", API_URL])
        assert result.exit_code != 0
        assert "No wallet selected" in result.output


# ==== project status ====

FAKE_PROJECT_DETAIL = {
    "project_id": "proj_aabbccdd11223344",
    "name": "BlockKick Fund",
    "description": "A great project",
    "goal_amount": 1000,
    "raised_amount": 250,
    "status": "ACTIVE",
    "deadline_timestamp": 1999999999,
    "creator_wallet": "a" * 64,
    "recent_backers": [
        {"from_address": "c" * 64, "amount": 100, "timestamp": 1000000},
    ],
}


class TestProjectStatus:

    def test_shows_project_detail(self, isolated_paths):
        with patch("blockkick.cli.get_project", return_value=FAKE_PROJECT_DETAIL):
            result = runner.invoke(
                app, ["project", "status", "proj_aabbccdd11223344", "--api", API_URL]
            )
        assert result.exit_code == 0
        assert "BlockKick Fund" in result.output
        assert "250" in result.output
        assert "ACTIVE" in result.output

    def test_not_found_exits_with_error(self, isolated_paths):
        from unittest.mock import MagicMock

        err = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        with patch("blockkick.cli.get_project", side_effect=err):
            result = runner.invoke(
                app, ["project", "status", "proj_notexist", "--api", API_URL]
            )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()
