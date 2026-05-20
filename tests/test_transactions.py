"""Tests for blockchain.transactions module."""

import json

from blockkick.blockchain.transactions import (
    build_create_project_tx,
    build_fund_project_tx,
    build_transfer_tx,
    get_signing_data,
)

CREATOR = "a" * 64
SENDER = "b" * 64
RECIPIENT = "c" * 64
PROJECT_ID = "proj_1234567890abcdef"


class TestGetSigningData:

    def test_structure(self):
        tx = build_create_project_tx(CREATOR, "Name", "Desc", 100, 9999999999)
        data = json.loads(get_signing_data(tx))
        assert data["id"] == ""
        assert data["signature"] is None
        assert set(data.keys()) == {
            "id",
            "tx_type",
            "from",
            "to",
            "data",
            "timestamp",
            "signature",
        }


class TestBuildCreateProjectTx:

    def test_fields(self):
        tx = build_create_project_tx(CREATOR, "My Project", "Desc", 500, 1234567890)
        assert tx["tx_type"] == "CreateProject"
        assert tx["from"] == CREATOR
        assert tx["to"] is None
        assert tx["data"]["name"] == "My Project"
        assert tx["data"]["goal_amount"] == 500
        assert tx["data"]["deadline_timestamp"] == 1234567890
        assert tx["data"]["creator_wallet"] == CREATOR
        assert tx["data"]["project_id"].startswith("proj_")


class TestBuildTransferTx:

    def test_fields(self):
        tx = build_transfer_tx(SENDER, RECIPIENT, 100, "payment")
        assert tx["tx_type"] == "Transfer"
        assert tx["from"] == SENDER
        assert tx["to"] == RECIPIENT
        assert tx["data"]["amount"] == 100
        assert tx["data"]["memo"] == "payment"


class TestBuildFundProjectTx:

    def test_fields(self):
        tx = build_fund_project_tx(SENDER, CREATOR, PROJECT_ID, 50, "Great project!")
        assert tx["tx_type"] == "FundProject"
        assert tx["from"] == SENDER
        assert tx["to"] == CREATOR
        assert tx["data"]["project_id"] == PROJECT_ID
        assert tx["data"]["amount"] == 50
        assert tx["data"]["backer_note"] == "Great project!"
