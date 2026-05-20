"""Tests for blockchain.transactions module."""

import json
import time

from blockkick.blockchain.transactions import (
    build_create_project_tx,
    build_fund_project_tx,
    build_transfer_tx,
    compute_tx_id,
    get_signing_data,
)

CREATOR = "a" * 64
SENDER = "b" * 64
RECIPIENT = "c" * 64
PROJECT_ID = "proj_1234567890abcdef"


# ==== get_signing_data ====


class TestGetSigningData:

    def test_returns_valid_json(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert isinstance(json.loads(get_signing_data(tx)), dict)

    def test_id_is_empty_string(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert json.loads(get_signing_data(tx))["id"] == ""

    def test_signature_is_null(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert json.loads(get_signing_data(tx))["signature"] is None

    def test_contains_all_required_fields(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert set(json.loads(get_signing_data(tx)).keys()) == {
            "id",
            "tx_type",
            "from",
            "to",
            "data",
            "timestamp",
            "signature",
        }

    def test_same_tx_produces_same_signing_data(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert get_signing_data(tx) == get_signing_data(tx)


# ==== compute_tx_id ====


class TestComputeTxId:

    def test_returns_64_char_hex(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        tx_id = compute_tx_id(tx)
        assert len(tx_id) == 64
        assert all(c in "0123456789abcdef" for c in tx_id)

    def test_id_field_matches_compute_result(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert tx["id"] == compute_tx_id(tx)

    def test_deterministic_for_same_tx(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert compute_tx_id(tx) == compute_tx_id(tx)


# ==== build_create_project_tx ====


class TestBuildCreateProjectTx:

    def test_tx_type(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert tx["tx_type"] == "CreateProject"

    def test_from_is_creator(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert tx["from"] == CREATOR

    def test_to_is_none(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert tx["to"] is None

    def test_project_id_format(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        pid = tx["data"]["project_id"]
        assert pid.startswith("proj_")
        assert len(pid) == 21  # "proj_" (5) + 16 hex chars

    def test_project_ids_are_unique(self):
        tx1 = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        tx2 = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert tx1["data"]["project_id"] != tx2["data"]["project_id"]

    def test_id_field_is_populated(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert len(tx["id"]) == 64

    def test_signature_is_none(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert tx["signature"] is None

    def test_data_name(self):
        tx = build_create_project_tx(CREATOR, "My Project", "Desc", 100, 9999999999)
        assert tx["data"]["name"] == "My Project"

    def test_data_description(self):
        tx = build_create_project_tx(CREATOR, "Name", "My description", 100, 9999999999)
        assert tx["data"]["description"] == "My description"

    def test_data_goal_amount(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 500, 9999999999)
        assert tx["data"]["goal_amount"] == 500

    def test_data_creator_wallet(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        assert tx["data"]["creator_wallet"] == CREATOR

    def test_data_deadline_timestamp(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 1234567890)
        assert tx["data"]["deadline_timestamp"] == 1234567890

    def test_timestamp_is_recent(self):
        before = int(time.time())
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        after = int(time.time())
        assert before <= tx["timestamp"] <= after


# ==== build_transfer_tx ====


class TestBuildTransferTx:

    def test_fields(self):
        tx = build_transfer_tx(SENDER, RECIPIENT, 100, "payment")
        assert tx["tx_type"] == "Transfer"
        assert tx["from"] == SENDER
        assert tx["to"] == RECIPIENT
        assert tx["data"]["amount"] == 100
        assert tx["data"]["memo"] == "payment"

    def test_id_and_signature(self):
        tx = build_transfer_tx(SENDER, RECIPIENT, 100)
        assert tx["id"] == compute_tx_id(tx)
        assert tx["signature"] is None


# ==== build_fund_project_tx ====


class TestBuildFundProjectTx:

    def test_tx_type(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        assert tx["tx_type"] == "FundProject"

    def test_from_is_sender(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        assert tx["from"] == SENDER

    def test_to_is_creator(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        assert tx["to"] == CREATOR

    def test_data_project_id(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        assert tx["data"]["project_id"] == PROJECT_ID

    def test_data_amount(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        assert tx["data"]["amount"] == 50

    def test_data_backer_note_defaults_to_empty(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        assert tx["data"]["backer_note"] == ""

    def test_data_backer_note_custom(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50, "Great project!")
        assert tx["data"]["backer_note"] == "Great project!"

    def test_id_field_is_populated(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        assert len(tx["id"]) == 64

    def test_signature_is_none(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        assert tx["signature"] is None

    def test_timestamp_is_recent(self):
        before = int(time.time())
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50)
        after = int(time.time())
        assert before <= tx["timestamp"] <= after
