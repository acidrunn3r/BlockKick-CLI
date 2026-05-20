"""Tests for CLI commands."""

import pytest
from typer.testing import CliRunner

from blockkick.cli import app

runner = CliRunner()


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
    # cli.py imports KEYSTORE_DIR by value, so patch it there too
    monkeypatch.setattr(cli, "KEYSTORE_DIR", keystore_dir)

    return tmp_path


def _create_and_select_wallet(password: str = "password123") -> str:
    """Helper: create a wallet, select it (active session), return its filename."""
    filename = _create_wallet(password)
    runner.invoke(app, ["wallet", "select", filename, "--password", password])
    return filename


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

    def test_shows_wallets(self, isolated_paths):
        _create_wallet()
        result = runner.invoke(app, ["wallet", "list"])
        assert result.exit_code == 0
        assert "keystore-" in result.output


# ==== wallet info ====


class TestWalletInfo:

    def test_shows_public_key(self, isolated_paths):
        filename = _create_wallet()
        result = runner.invoke(app, ["wallet", "info", filename])
        assert result.exit_code == 0
        assert "Public key" in result.output


# ==== wallet select ====


class TestWalletSelect:

    def test_correct_password_succeeds(self, isolated_paths):
        filename = _create_wallet()
        result = runner.invoke(
            app, ["wallet", "select", filename, "--password", "password123"]
        )
        assert result.exit_code == 0
        assert "Active wallet set to" in result.output

    def test_wrong_password_exits_with_error(self, isolated_paths):
        filename = _create_wallet()
        result = runner.invoke(
            app, ["wallet", "select", filename, "--password", "wrongpassword"]
        )
        assert result.exit_code != 0
        assert "error" in result.output.lower()


# ==== wallet deselect ====


class TestWalletDeselect:

    def test_clears_selection(self, isolated_paths):
        from blockkick.wallet.keystore import get_selected_wallet

        filename = _create_wallet()
        runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        runner.invoke(app, ["wallet", "deselect"])
        assert get_selected_wallet() != filename


# ==== project create ====


class TestProjectCreate:

    def test_creates_project_successfully(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        monkeypatch.setattr(
            cli_module,
            "submit_transaction",
            lambda *a, **kw: {"status": "pending", "tx_id": "abc123"},
        )
        _create_and_select_wallet()
        result = runner.invoke(
            app,
            ["project", "create"],
            input="My Project\nA cool project\n100\n30\n",
        )
        assert result.exit_code == 0
        assert "Project created!" in result.output

    def test_requires_wallet_selection(self, isolated_paths):
        result = runner.invoke(
            app,
            ["project", "create"],
            input="My Project\nDesc\n100\n30\n",
        )
        assert result.exit_code != 0
        assert "No wallet selected" in result.output


# ==== project donate ====


class TestProjectDonate:

    def test_donates_successfully(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        monkeypatch.setattr(cli_module, "get_balance", lambda *a, **kw: 1000)
        monkeypatch.setattr(
            cli_module,
            "submit_transaction",
            lambda *a, **kw: {"status": "pending", "tx_id": "abc123"},
        )
        _create_and_select_wallet()
        result = runner.invoke(
            app,
            ["project", "donate", "proj_1234567890abcdef"],
            input=f"50\n{'b' * 64}\nGreat project!\n",
        )
        assert result.exit_code == 0
        assert "Donation sent!" in result.output

    def test_insufficient_balance_exits_with_error(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        monkeypatch.setattr(cli_module, "get_balance", lambda *a, **kw: 5)
        _create_and_select_wallet()
        result = runner.invoke(
            app,
            ["project", "donate", "proj_1234567890abcdef"],
            input=f"100\n{'b' * 64}\n\n",
        )
        assert result.exit_code != 0
        assert "Insufficient balance" in result.output


# ==== transfer ====


class TestTransfer:

    RECIPIENT = "c" * 64

    def test_sends_successfully(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        monkeypatch.setattr(cli_module, "get_balance", lambda *a, **kw: 1000)
        monkeypatch.setattr(
            cli_module,
            "submit_transaction",
            lambda *a, **kw: {"status": "pending", "tx_id": "abc123"},
        )
        _create_and_select_wallet()
        result = runner.invoke(app, ["transfer", self.RECIPIENT, "50"])
        assert result.exit_code == 0
        assert "Transfer sent!" in result.output

    def test_insufficient_balance_exits_with_error(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        monkeypatch.setattr(cli_module, "get_balance", lambda *a, **kw: 10)
        _create_and_select_wallet()
        result = runner.invoke(app, ["transfer", self.RECIPIENT, "100"])
        assert result.exit_code != 0
        assert "Insufficient balance" in result.output


# ==== tx ====


class TestTxCmd:

    TX_ID = "a" * 64

    def test_shows_transaction_details(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        monkeypatch.setattr(
            cli_module,
            "get_transaction",
            lambda *a, **kw: {
                "id": self.TX_ID,
                "tx_type": "Transfer",
                "from": "b" * 64,
                "to": "c" * 64,
                "status": "confirmed",
                "block_index": 5,
                "data": {},
            },
        )
        result = runner.invoke(app, ["tx", self.TX_ID])
        assert result.exit_code == 0
        assert "confirmed" in result.output
        assert "Transfer" in result.output


# ==== logout ====


class TestLogout:

    def test_clears_api_tokens(self, isolated_paths):
        import blockkick.wallet.keystore as ks

        ks.save_api_tokens("access_tok", "refresh_tok")
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert not ks.API_AUTH_FILE.exists()
