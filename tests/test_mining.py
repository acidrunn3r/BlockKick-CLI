"""Tests for blockchain.mining module and mine/balance CLI commands."""

import hashlib
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from blockkick.blockchain.mining import compute_pow_hash, fetch_candidate, mine, submit_block
from blockkick.cli import app

runner = CliRunner()


# ---- shared fixtures ----

SAMPLE_CANDIDATE = {
    "block_template": {
        "index": 1,
        "timestamp": 1000000,
        "prev_hash": "a" * 64,
        "merkle_root": "b" * 64,
        "nonce": 0,
    },
    "transactions": [
        {
            "id": "b" * 64,
            "tx_type": "Coinbase",
            "from": None,
            "to": "c" * 64,
            "data": {"reward": 50, "block_height": 1},
            "timestamp": 1000000,
            "signature": None,
        }
    ],
    "prev_hash": "a" * 64,
    "difficulty": 1,
    "reward": 50,
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
    monkeypatch.setattr(cli, "KEYSTORE_DIR", keystore_dir)

    return tmp_path


def _create_and_select_wallet(tmp_path):
    """Helper: create a wallet file and select it."""
    import blockkick.wallet.keystore as ks

    pub_key = "4233a729cf3534a8" * 4
    wallet_data = {
        "public_key_hex": pub_key,
        "timestamp": 1000000,
        "version": "1.0",
        "crypto": {
            "cipher": "aes-256-gcm",
            "ciphertext": "aa" * 32,
            "nonce": "bb" * 12,
            "kdf": "scrypt",
            "kdfparams": {"salt": "cc" * 32, "n": 16384, "r": 8, "p": 1, "dklen": 32},
        },
    }
    filename = f"keystore-{pub_key[:16]}.json"
    (tmp_path / "keystores" / filename).write_text(json.dumps(wallet_data))
    ks.set_selected_wallet(filename)
    return filename, pub_key


# ==== compute_pow_hash ====

class TestComputePowHash:

    def test_returns_64_char_hex(self):
        header = SAMPLE_CANDIDATE["block_template"]
        result = compute_pow_hash(header, 0)
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        header = SAMPLE_CANDIDATE["block_template"]
        assert compute_pow_hash(header, 42) == compute_pow_hash(header, 42)

    def test_different_nonces_give_different_hashes(self):
        header = SAMPLE_CANDIDATE["block_template"]
        assert compute_pow_hash(header, 0) != compute_pow_hash(header, 1)

    def test_matches_expected_sha256(self):
        header = SAMPLE_CANDIDATE["block_template"]
        nonce = 7
        expected = hashlib.sha256(
            json.dumps(
                {
                    "index": header["index"],
                    "timestamp": header["timestamp"],
                    "prev_hash": header["prev_hash"],
                    "merkle_root": header["merkle_root"],
                    "nonce": nonce,
                },
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert compute_pow_hash(header, nonce) == expected

    def test_field_order_matches_rust_serde_json(self):
        header = SAMPLE_CANDIDATE["block_template"]
        serialized = json.dumps(
            {
                "index": header["index"],
                "timestamp": header["timestamp"],
                "prev_hash": header["prev_hash"],
                "merkle_root": header["merkle_root"],
                "nonce": 0,
            },
            separators=(",", ":"),
        )
        keys = list(json.loads(serialized).keys())
        assert keys == ["index", "timestamp", "prev_hash", "merkle_root", "nonce"]


# ==== mine ====

class TestMine:

    def test_returns_tuple_of_three(self):
        result = mine(SAMPLE_CANDIDATE)
        assert len(result) == 3

    def test_found_hash_starts_with_target(self):
        nonce, block_hash, _ = mine(SAMPLE_CANDIDATE)
        difficulty = SAMPLE_CANDIDATE["difficulty"]
        assert block_hash.startswith("0" * difficulty)

    def test_nonce_produces_correct_hash(self):
        nonce, block_hash, _ = mine(SAMPLE_CANDIDATE)
        assert compute_pow_hash(SAMPLE_CANDIDATE["block_template"], nonce) == block_hash

    def test_elapsed_is_positive_float(self):
        _, _, elapsed = mine(SAMPLE_CANDIDATE)
        assert isinstance(elapsed, float)
        assert elapsed >= 0


# ==== fetch_candidate ====

class TestFetchCandidate:

    def test_calls_correct_url(self):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_CANDIDATE
        mock_response.raise_for_status = MagicMock()

        with patch("blockkick.blockchain.mining.httpx.get", return_value=mock_response) as mock_get:
            fetch_candidate("http://localhost:3000", "a" * 64)
            url = mock_get.call_args[0][0]
            assert url == "http://localhost:3000/api/v1/mining/candidate"

    def test_passes_miner_as_query_param(self):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_CANDIDATE
        mock_response.raise_for_status = MagicMock()

        with patch("blockkick.blockchain.mining.httpx.get", return_value=mock_response) as mock_get:
            fetch_candidate("http://localhost:3000", "a" * 64)
            params = mock_get.call_args[1]["params"]
            assert params == {"miner": "a" * 64}

    def test_returns_parsed_json(self):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_CANDIDATE
        mock_response.raise_for_status = MagicMock()

        with patch("blockkick.blockchain.mining.httpx.get", return_value=mock_response):
            result = fetch_candidate("http://localhost:3000", "a" * 64)
            assert result == SAMPLE_CANDIDATE

    def test_raises_on_http_error(self):
        with patch("blockkick.blockchain.mining.httpx.get", side_effect=httpx.ConnectError("down")):
            with pytest.raises(httpx.ConnectError):
                fetch_candidate("http://localhost:3000", "a" * 64)


# ==== submit_block ====

class TestSubmitBlock:

    def test_calls_correct_url(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "accepted", "reward": 50}
        mock_response.raise_for_status = MagicMock()

        with patch("blockkick.blockchain.mining.httpx.post", return_value=mock_response) as mock_post:
            submit_block("http://localhost:3000", SAMPLE_CANDIDATE, 42)
            url = mock_post.call_args[0][0]
            assert url == "http://localhost:3000/api/v1/mining/submit"

    def test_sends_correct_nonce(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "accepted", "reward": 50}
        mock_response.raise_for_status = MagicMock()

        with patch("blockkick.blockchain.mining.httpx.post", return_value=mock_response) as mock_post:
            submit_block("http://localhost:3000", SAMPLE_CANDIDATE, 42)
            body = mock_post.call_args[1]["json"]
            assert body["header"]["nonce"] == 42

    def test_sends_transactions_unchanged(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "accepted", "reward": 50}
        mock_response.raise_for_status = MagicMock()

        with patch("blockkick.blockchain.mining.httpx.post", return_value=mock_response) as mock_post:
            submit_block("http://localhost:3000", SAMPLE_CANDIDATE, 0)
            body = mock_post.call_args[1]["json"]
            assert body["transactions"] == SAMPLE_CANDIDATE["transactions"]

    def test_returns_parsed_json(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "accepted", "reward": 50}
        mock_response.raise_for_status = MagicMock()

        with patch("blockkick.blockchain.mining.httpx.post", return_value=mock_response):
            result = submit_block("http://localhost:3000", SAMPLE_CANDIDATE, 0)
            assert result == {"status": "accepted", "reward": 50}

    def test_raises_on_http_error(self):
        with patch("blockkick.blockchain.mining.httpx.post", side_effect=httpx.ConnectError("down")):
            with pytest.raises(httpx.ConnectError):
                submit_block("http://localhost:3000", SAMPLE_CANDIDATE, 0)


# ==== blockkick mine (CLI) ====

class TestMineCommand:

    def test_no_wallet_selected_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["mine"])
        assert result.exit_code != 0
        assert "No wallet selected" in result.output

    def test_node_unreachable_exits_with_error(self, isolated_paths):
        _create_and_select_wallet(isolated_paths)
        with patch("blockkick.cli.fetch_candidate", side_effect=httpx.ConnectError("down")):
            result = runner.invoke(app, ["mine", "--node", "http://localhost:3000"])
        assert result.exit_code != 0
        assert "Failed to reach node" in result.output

    def test_successful_mine_shows_reward(self, isolated_paths):
        _create_and_select_wallet(isolated_paths)
        with patch("blockkick.cli.fetch_candidate", return_value=SAMPLE_CANDIDATE), \
             patch("blockkick.cli.mine", return_value=(42, "0" * 64, 0.5)), \
             patch("blockkick.cli.submit_block", return_value={"status": "accepted", "reward": 50}):
            result = runner.invoke(app, ["mine", "--node", "http://localhost:3000"])
        assert result.exit_code == 0
        assert "Block accepted" in result.output
        assert "50" in result.output

    def test_submit_failure_exits_with_error(self, isolated_paths):
        _create_and_select_wallet(isolated_paths)
        with patch("blockkick.cli.fetch_candidate", return_value=SAMPLE_CANDIDATE), \
             patch("blockkick.cli.mine", return_value=(42, "0" * 64, 0.5)), \
             patch("blockkick.cli.submit_block", side_effect=httpx.ConnectError("down")):
            result = runner.invoke(app, ["mine", "--node", "http://localhost:3000"])
        assert result.exit_code != 0
        assert "Submission failed" in result.output


# ==== blockkick balance (CLI) ====

class TestBalanceCommand:

    def test_no_wallet_selected_exits_with_error(self, isolated_paths):
        result = runner.invoke(app, ["balance"])
        assert result.exit_code != 0
        assert "No wallet selected" in result.output

    def test_shows_balance(self, isolated_paths):
        _create_and_select_wallet(isolated_paths)
        mock_response = MagicMock()
        mock_response.json.return_value = {"balance": 50}
        mock_response.raise_for_status = MagicMock()
        with patch("blockkick.cli.httpx.get", return_value=mock_response):
            result = runner.invoke(app, ["balance", "--node", "http://localhost:3000"])
        assert result.exit_code == 0
        assert "50" in result.output

    def test_node_unreachable_exits_with_error(self, isolated_paths):
        _create_and_select_wallet(isolated_paths)
        with patch("blockkick.cli.httpx.get", side_effect=httpx.ConnectError("down")):
            result = runner.invoke(app, ["balance", "--node", "http://localhost:3000"])
        assert result.exit_code != 0
        assert "Failed to reach node" in result.output

    def test_calls_correct_address(self, isolated_paths):
        _, pub_key = _create_and_select_wallet(isolated_paths)
        mock_response = MagicMock()
        mock_response.json.return_value = {"balance": 0}
        mock_response.raise_for_status = MagicMock()
        with patch("blockkick.cli.httpx.get", return_value=mock_response) as mock_get:
            runner.invoke(app, ["balance", "--node", "http://localhost:3000"])
            url = mock_get.call_args[0][0]
            assert pub_key in url
