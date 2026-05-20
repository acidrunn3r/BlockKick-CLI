"""HTTP client for BlockKick API."""

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
