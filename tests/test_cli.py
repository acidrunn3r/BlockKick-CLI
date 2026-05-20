"""Tests for CLI commands."""

import json

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
        ks.METADATA_FILE.write_text(
            json.dumps(
                {
                    first: {"last_action": 1000},
                    second: {"last_action": 2000},
                }
            )
        )
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
        result = runner.invoke(
            app, ["wallet", "select", filename, "--password", "password123"]
        )
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
        result = runner.invoke(
            app, ["wallet", "select", filename, "--password", "wrongpassword"]
        )
        assert result.exit_code != 0
        assert "error" in result.output.lower()

    def test_missing_file_exits_with_error(self, isolated_paths):
        result = runner.invoke(
            app,
            [
                "wallet",
                "select",
                "keystore-nonexistent.json",
                "--password",
                "password123",
            ],
        )
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


# ==== config set-node ====


class TestConfigSetNode:

    def test_persists_url(self, isolated_paths):
        from blockkick.wallet.keystore import get_node_url

        runner.invoke(app, ["config", "set-node", "http://localhost:3000"])
        assert get_node_url() == "http://localhost:3000"

    def test_shows_confirmation(self, isolated_paths):
        result = runner.invoke(app, ["config", "set-node", "http://localhost:3000"])
        assert result.exit_code == 0
        assert "http://localhost:3000" in result.output

    def test_overwrites_previous_url(self, isolated_paths):
        from blockkick.wallet.keystore import get_node_url

        runner.invoke(app, ["config", "set-node", "http://localhost:3000"])
        runner.invoke(app, ["config", "set-node", "http://192.168.1.1:8080"])
        assert get_node_url() == "http://192.168.1.1:8080"


# ==== config show ====


class TestConfigShow:

    def test_shows_default_node_url(self, isolated_paths):
        from blockkick.wallet.keystore import DEFAULT_NODE_URL

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert DEFAULT_NODE_URL in result.output

    def test_shows_configured_node_url(self, isolated_paths):
        runner.invoke(app, ["config", "set-node", "http://localhost:3000"])
        result = runner.invoke(app, ["config", "show"])
        assert "http://localhost:3000" in result.output

    def test_shows_dash_when_no_wallet_selected(self, isolated_paths):
        result = runner.invoke(app, ["config", "show"])
        assert "—" in result.output

    def test_shows_selected_wallet(self, isolated_paths):
        filename = _create_wallet()
        runner.invoke(app, ["wallet", "select", filename, "--password", "password123"])
        result = runner.invoke(app, ["config", "show"])
        assert filename in result.output


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

    def test_shows_project_id_with_proj_prefix(self, isolated_paths, monkeypatch):
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
        assert "proj_" in result.output

    def test_shows_tx_status(self, isolated_paths, monkeypatch):
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
            input="My Project\nDesc\n100\n30\n",
        )
        assert "pending" in result.output

    def test_requires_wallet_selection(self, isolated_paths):
        result = runner.invoke(
            app,
            ["project", "create"],
            input="My Project\nDesc\n100\n30\n",
        )
        assert result.exit_code != 0
        assert "No wallet selected" in result.output

    def test_node_failure_exits_with_error(self, isolated_paths, monkeypatch):
        import httpx

        import blockkick.cli as cli_module

        def raise_error(*a, **kw):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(cli_module, "submit_transaction", raise_error)
        _create_and_select_wallet()
        result = runner.invoke(
            app,
            ["project", "create"],
            input="My Project\nDesc\n100\n30\n",
        )
        assert result.exit_code != 0

    def test_transaction_carries_correct_creator_wallet(
        self, isolated_paths, monkeypatch
    ):
        import json as _json

        import blockkick.cli as cli_module
        import blockkick.wallet.keystore as ks

        captured = {}

        def capture(node_url, tx):
            captured["tx"] = tx
            return {"status": "pending", "tx_id": "abc123"}

        monkeypatch.setattr(cli_module, "submit_transaction", capture)
        filename = _create_and_select_wallet()
        public_key = _json.loads((ks.KEYSTORE_DIR / filename).read_text())[
            "public_key_hex"
        ]

        runner.invoke(
            app,
            ["project", "create"],
            input="My Project\nDesc\n100\n30\n",
        )
        assert captured["tx"]["from"] == public_key
        assert captured["tx"]["data"]["creator_wallet"] == public_key

    def test_transaction_carries_correct_goal(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        captured = {}

        def capture(node_url, tx):
            captured["tx"] = tx
            return {"status": "pending", "tx_id": "abc123"}

        monkeypatch.setattr(cli_module, "submit_transaction", capture)
        _create_and_select_wallet()
        runner.invoke(
            app,
            ["project", "create"],
            input="My Project\nDesc\n250\n30\n",
        )
        assert captured["tx"]["data"]["goal_amount"] == 250

    def test_transaction_is_signed(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        captured = {}

        def capture(node_url, tx):
            captured["tx"] = tx
            return {"status": "pending", "tx_id": "abc123"}

        monkeypatch.setattr(cli_module, "submit_transaction", capture)
        _create_and_select_wallet()
        runner.invoke(
            app,
            ["project", "create"],
            input="My Project\nDesc\n100\n30\n",
        )
        assert captured["tx"].get("signature") is not None
        assert len(captured["tx"]["signature"]) == 128


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

    def test_insufficient_balance_shows_amounts(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        monkeypatch.setattr(cli_module, "get_balance", lambda *a, **kw: 5)
        _create_and_select_wallet()
        result = runner.invoke(
            app,
            ["project", "donate", "proj_1234567890abcdef"],
            input=f"100\n{'b' * 64}\n\n",
        )
        assert "5 coins" in result.output
        assert "100 coins" in result.output

    def test_requires_wallet_selection(self, isolated_paths):
        result = runner.invoke(
            app,
            ["project", "donate", "proj_1234567890abcdef"],
            input=f"50\n{'b' * 64}\n\n",
        )
        assert result.exit_code != 0
        assert "No wallet selected" in result.output

    def test_shows_project_id_in_output(self, isolated_paths, monkeypatch):
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
            input=f"50\n{'b' * 64}\n\n",
        )
        assert "proj_1234567890abcdef" in result.output

    def test_node_failure_exits_with_error(self, isolated_paths, monkeypatch):
        import httpx

        import blockkick.cli as cli_module

        def raise_error(*a, **kw):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(cli_module, "get_balance", lambda *a, **kw: 1000)
        monkeypatch.setattr(cli_module, "submit_transaction", raise_error)
        _create_and_select_wallet()
        result = runner.invoke(
            app,
            ["project", "donate", "proj_1234567890abcdef"],
            input=f"50\n{'b' * 64}\n\n",
        )
        assert result.exit_code != 0

    def test_transaction_fields_are_correct(self, isolated_paths, monkeypatch):
        import json as _json

        import blockkick.cli as cli_module
        import blockkick.wallet.keystore as ks

        captured = {}

        def capture(node_url, tx):
            captured["tx"] = tx
            return {"status": "pending", "tx_id": "abc123"}

        monkeypatch.setattr(cli_module, "get_balance", lambda *a, **kw: 1000)
        monkeypatch.setattr(cli_module, "submit_transaction", capture)
        filename = _create_and_select_wallet()
        public_key = _json.loads((ks.KEYSTORE_DIR / filename).read_text())[
            "public_key_hex"
        ]
        creator = "b" * 64

        runner.invoke(
            app,
            ["project", "donate", "proj_1234567890abcdef"],
            input=f"50\n{creator}\nSupport!\n",
        )
        tx = captured["tx"]
        assert tx["tx_type"] == "FundProject"
        assert tx["from"] == public_key
        assert tx["to"] == creator
        assert tx["data"]["amount"] == 50
        assert tx["data"]["project_id"] == "proj_1234567890abcdef"
        assert tx["data"]["backer_note"] == "Support!"

    def test_transaction_is_signed(self, isolated_paths, monkeypatch):
        import blockkick.cli as cli_module

        captured = {}

        def capture(node_url, tx):
            captured["tx"] = tx
            return {"status": "pending", "tx_id": "abc123"}

        monkeypatch.setattr(cli_module, "get_balance", lambda *a, **kw: 1000)
        monkeypatch.setattr(cli_module, "submit_transaction", capture)
        _create_and_select_wallet()
        runner.invoke(
            app,
            ["project", "donate", "proj_1234567890abcdef"],
            input=f"50\n{'b' * 64}\n\n",
        )
        assert captured["tx"].get("signature") is not None
        assert len(captured["tx"]["signature"]) == 128


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

    def test_requires_wallet_selection(self, isolated_paths):
        result = runner.invoke(app, ["transfer", self.RECIPIENT, "50"])
        assert result.exit_code != 0
        assert "No wallet selected" in result.output


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

    def test_not_found_exits_with_error(self, isolated_paths, monkeypatch):
        import httpx

        import blockkick.cli as cli_module

        def raise_404(*a, **kw):
            resp = httpx.Response(404)
            raise httpx.HTTPStatusError("not found", request=None, response=resp)

        monkeypatch.setattr(cli_module, "get_transaction", raise_404)
        result = runner.invoke(app, ["tx", self.TX_ID])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ==== logout ====


class TestLogout:

    def test_clears_api_tokens(self, isolated_paths):
        import blockkick.wallet.keystore as ks

        ks.save_api_tokens("access_tok", "refresh_tok")
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert not ks.API_AUTH_FILE.exists()

    def test_no_op_when_not_logged_in(self, isolated_paths):
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert "Not logged in" in result.output
