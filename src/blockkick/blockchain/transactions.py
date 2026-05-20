"""Module for building and preparing transactions"""

import hashlib
import json
import secrets
import time
from typing import Any, TypedDict

# Functional form is required to allow the reserved keyword 'from' as a field name.
Transaction = TypedDict(
    "Transaction",
    {
        "id": str,
        "tx_type": str,
        "from": str,
        "to": str | None,
        "data": dict[str, Any],
        "timestamp": int,
        "signature": str | None,
    },
)


def get_signing_data(tx: Transaction) -> str:
    """Return the canonical JSON string used for ID computation and signing.

    Sets ``id`` to an empty string and ``signature`` to null, then serializes
    with explicit field ordering to match Rust's serde_json struct layout.

    Args:
        tx: Transaction dictionary.

    Returns:
        JSON string to be hashed (for ID) and signed (for signature).
    """
    return json.dumps(
        {
            "id": "",
            "tx_type": tx["tx_type"],
            "from": tx["from"],
            "to": tx["to"],
            "data": tx["data"],
            "timestamp": tx["timestamp"],
            "signature": None,
        },
        separators=(",", ":"),
    )


def compute_tx_id(tx: Transaction) -> str:
    """Compute SHA-256 transaction ID from signing data.

    Args:
        tx: Transaction dictionary.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(get_signing_data(tx).encode()).hexdigest()


def build_create_project_tx(
    creator_public_key: str,
    name: str,
    description: str,
    goal_amount: int,
    deadline_timestamp: int,
) -> Transaction:
    """Build a CreateProject transaction with a generated project ID.

    The returned transaction has its ``id`` field populated but ``signature``
    set to ``None``.  Call ``get_signing_data(tx)`` to obtain the payload to
    sign, then store the result in ``tx["signature"]`` before submitting.

    Args:
        creator_public_key: Hex-encoded Ed25519 public key of the project creator.
        name: Project display name.
        description: Project description.
        goal_amount: Fundraising goal in coins (≥ 1).
        deadline_timestamp: Unix timestamp for the campaign deadline.

    Returns:
        Unsigned Transaction dict.
    """
    project_id = "proj_" + secrets.token_hex(8)
    tx: Transaction = {
        "id": "",
        "tx_type": "CreateProject",
        "from": creator_public_key,
        "to": None,
        "data": {
            "project_id": project_id,
            "name": name,
            "description": description,
            "goal_amount": goal_amount,
            "deadline_timestamp": deadline_timestamp,
            "creator_wallet": creator_public_key,
        },
        "timestamp": int(time.time()),
        "signature": None,
    }
    tx["id"] = compute_tx_id(tx)
    return tx


def build_transfer_tx(
    sender_public_key: str,
    recipient_public_key: str,
    amount: int,
    memo: str = "",
) -> Transaction:
    """Build a Transfer transaction.

    The returned transaction has its ``id`` field populated but ``signature``
    set to ``None``.  Call ``get_signing_data(tx)`` to obtain the payload to
    sign, then store the result in ``tx["signature"]`` before submitting.

    Args:
        sender_public_key: Hex-encoded Ed25519 public key of the sender.
        recipient_public_key: Hex-encoded Ed25519 public key of the recipient.
        amount: Amount in coins to transfer (≥ 1).
        memo: Optional memo string attached to the transfer.

    Returns:
        Unsigned Transaction dict.
    """
    tx: Transaction = {
        "id": "",
        "tx_type": "Transfer",
        "from": sender_public_key,
        "to": recipient_public_key,
        "data": {
            "amount": amount,
            "memo": memo,
        },
        "timestamp": int(time.time()),
        "signature": None,
    }
    tx["id"] = compute_tx_id(tx)
    return tx


def build_fund_project_tx(
    sender_public_key: str,
    creator_public_key: str,
    project_id: str,
    amount: int,
    backer_note: str = "",
) -> Transaction:
    """Build a FundProject transaction.

    The returned transaction has its ``id`` field populated but ``signature``
    set to ``None``.  Call ``get_signing_data(tx)`` to obtain the payload to
    sign, then store the result in ``tx["signature"]`` before submitting.

    Args:
        sender_public_key: Hex-encoded public key of the backer.
        creator_public_key: Hex-encoded public key of the project creator (``to`` field).
        project_id: Target project identifier (format ``proj_<16 hex chars>``).
        amount: Contribution amount in coins (≥ 1).
        backer_note: Optional message from the backer.

    Returns:
        Unsigned Transaction dict.
    """
    tx: Transaction = {
        "id": "",
        "tx_type": "FundProject",
        "from": sender_public_key,
        "to": creator_public_key,
        "data": {
            "project_id": project_id,
            "amount": amount,
            "backer_note": backer_note,
        },
        "timestamp": int(time.time()),
        "signature": None,
    }
    tx["id"] = compute_tx_id(tx)
    return tx
