"""Mining logic: PoW loop, candidate fetch, block submit."""

import hashlib
import json
import time
from typing import Any

import httpx


def compute_pow_hash(header: dict[str, Any], nonce: int) -> str:
    """Compute SHA-256 of the block header with a given nonce.

    Matches Rust's serde_json::to_string field order:
    index → timestamp → prev_hash → merkle_root → nonce.

    Args:
        header: Block header dict from the candidate response.
        nonce: Nonce value to test.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    serialized = json.dumps(
        {
            "index": header["index"],
            "timestamp": header["timestamp"],
            "prev_hash": header["prev_hash"],
            "merkle_root": header["merkle_root"],
            "nonce": nonce,
        },
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def mine(candidate: dict[str, Any]) -> tuple[int, str, float]:
    """Run the proof-of-work loop until a valid nonce is found.

    Args:
        candidate: Response from /api/v1/mining/candidate.

    Returns:
        tuple: (nonce, block_hash, elapsed_seconds)
    """
    header = candidate["block_template"]
    difficulty: int = candidate["difficulty"]
    target = "0" * difficulty

    nonce = 0
    started = time.monotonic()

    while True:
        block_hash = compute_pow_hash(header, nonce)
        if block_hash.startswith(target):
            return nonce, block_hash, time.monotonic() - started
        nonce += 1


def fetch_candidate(node_url: str, public_key: str) -> dict[str, Any]:
    """Fetch a block candidate from the node.

    Args:
        node_url: Base URL of the BlockKick node.
        public_key: Miner's public key hex (64 chars).

    Returns:
        Candidate dict with block_template, transactions, difficulty, reward.

    Raises:
        httpx.HTTPError: On network or HTTP error.
    """
    url = f"{node_url.rstrip('/')}/api/v1/mining/candidate"
    response = httpx.get(url, params={"miner": public_key}, timeout=10)
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def submit_block(
    node_url: str, candidate: dict[str, Any], nonce: int
) -> dict[str, Any]:
    """Submit a mined block to the node.

    Args:
        node_url: Base URL of the BlockKick node.
        candidate: Original candidate dict.
        nonce: Discovered nonce value.

    Returns:
        Response dict with status and reward.

    Raises:
        httpx.HTTPError: On network or HTTP error.
    """
    header = dict(candidate["block_template"])
    header["nonce"] = nonce

    block = {
        "header": header,
        "transactions": candidate["transactions"],
    }

    url = f"{node_url.rstrip('/')}/api/v1/mining/submit"
    response = httpx.post(url, json=block, timeout=10)
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result
