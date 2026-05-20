"""HTTP client for BlockKick API."""

from collections.abc import Mapping
from typing import Any

import httpx


def request_challenge(api_url: str, wallet_address: str) -> str:
    """Request a nonce challenge for the given wallet address.

    Args:
        api_url: Base URL of the BlockKick API.
        wallet_address: Ed25519 public key hex (64 chars).

    Returns:
        str: The nonce UUID to be signed.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.post(
        f"{api_url.rstrip('/')}/api/v1/auth/challenge",
        json={"wallet_address": wallet_address},
        timeout=10,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    nonce: str = data["nonce"]
    return nonce


def auth_login(
    api_url: str, wallet_address: str, nonce: str, signature_hex: str
) -> dict[str, Any]:
    """Submit signed nonce to authenticate and receive JWT tokens.

    Args:
        api_url: Base URL of the BlockKick API.
        wallet_address: Ed25519 public key hex (64 chars).
        nonce: UUID nonce received from request_challenge.
        signature_hex: Ed25519 signature of the nonce bytes (128 hex chars).

    Returns:
        dict: Token response with access_token, refresh_token, etc.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.post(
        f"{api_url.rstrip('/')}/api/v1/auth/login",
        json={
            "wallet_address": wallet_address,
            "nonce": nonce,
            "signature": signature_hex,
        },
        timeout=10,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def update_profile(
    api_url: str, access_token: str, display_name: str, bio: str = ""
) -> dict[str, Any]:
    """Update the authenticated user's display name and bio.

    Args:
        api_url: Base URL of the BlockKick API.
        access_token: JWT access token.
        display_name: New display name (max 100 chars).
        bio: Optional bio text.

    Returns:
        dict: Updated user profile.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    params = {"display_name": display_name}
    if bio:
        params["bio"] = bio

    response = httpx.put(
        f"{api_url.rstrip('/')}/api/v1/users/me",
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def list_projects(api_url: str) -> list[Any]:
    """Fetch all crowdfunding projects.

    Args:
        api_url: Base URL of the BlockKick API.

    Returns:
        list: List of project summaries.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.get(
        f"{api_url.rstrip('/')}/api/v1/projects",
        timeout=10,
    )
    response.raise_for_status()
    result: list[Any] = response.json()
    return result


def get_balance(node_url: str, public_key: str) -> int:
    """Fetch the coin balance of a wallet from the node.

    Args:
        node_url: Base URL of the BlockKick node.
        public_key: Hex-encoded Ed25519 public key (64 chars).

    Returns:
        int: Current coin balance.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.get(
        f"{node_url.rstrip('/')}/api/v1/balance/{public_key}",
        timeout=10,
    )
    response.raise_for_status()
    result: int = response.json()["balance"]
    return result


def submit_transaction(node_url: str, tx: Mapping[str, Any]) -> dict[str, Any]:
    """Submit a signed transaction to the node.

    Args:
        node_url: Base URL of the BlockKick node.
        tx: Signed transaction dict with id, tx_type, from, to, data,
            timestamp and signature fields.

    Returns:
        dict: Response with ``tx_id`` and ``status``.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.post(
        f"{node_url.rstrip('/')}/api/v1/transactions",
        json=tx,
        timeout=10,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def get_transaction(node_url: str, tx_id: str) -> dict[str, Any]:
    """Fetch a transaction by ID from the node.

    Args:
        node_url: Base URL of the BlockKick node.
        tx_id: Hex-encoded SHA-256 transaction ID (64 chars).

    Returns:
        dict: Transaction details including status, tx_type, from, to, data.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.get(
        f"{node_url.rstrip('/')}/api/v1/transactions/{tx_id}",
        timeout=10,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def get_wallet_transactions(api_url: str, address: str) -> list[Any]:
    """Fetch indexed transaction history for a wallet address.

    Args:
        api_url: Base URL of the BlockKick API.
        address: Hex-encoded Ed25519 public key (64 chars).

    Returns:
        list: Transactions where wallet is sender or recipient, newest first.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.get(
        f"{api_url.rstrip('/')}/api/v1/wallets/{address}/transactions",
        timeout=10,
    )
    response.raise_for_status()
    result: list[Any] = response.json()
    return result


def get_project(api_url: str, project_id: str) -> dict[str, Any]:
    """Fetch full detail for a single project including recent backers.

    Args:
        api_url: Base URL of the BlockKick API.
        project_id: Project identifier (format proj_<16 hex chars>).

    Returns:
        dict: Project detail with project_id, name, goal_amount, raised_amount,
              status, and recent_backers list.

    Raises:
        httpx.HTTPError: On network or HTTP errors (404 if not found).
    """
    response = httpx.get(
        f"{api_url.rstrip('/')}/api/v1/projects/{project_id}",
        timeout=10,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def get_profile(api_url: str, access_token: str) -> dict[str, Any]:
    """Fetch the authenticated user's profile.

    Args:
        api_url: Base URL of the BlockKick API.
        access_token: JWT access token.

    Returns:
        dict: User profile with wallet_address, display_name, bio.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.get(
        f"{api_url.rstrip('/')}/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result
