"""Module for building and preparing transactions"""

import json
from typing import TypedDict


class Transaction(TypedDict):
    """Transaction structure."""
    type: str
    sender: str
    data: dict
    nonce: int
    timestamp: int


def serialize_transaction(tx: Transaction) -> str:
    """Serialize transaction to JSON string for signing.
    
    Args:
        tx: Transaction dictionary.
        
    Returns:
        JSON string
    """
    return json.dumps(tx, sort_keys=True, separators=(",", ":"))

# TODO: add transaction builders, when blockchain APIs are ready.
