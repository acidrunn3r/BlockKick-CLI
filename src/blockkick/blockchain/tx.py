"""Module for signing transactions"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def sign_transaction(data: str, private_key_bytes: bytes) -> str:
    """Sign transaction data with Ed25519 private key.
    
    Args:
        data: Transaction data to sign.
        private_key_bytes: Raw private key bytes (32 bytes).
        
    Returns:
        str: Signature as hex string.
    """
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature = private_key.sign(data.encode("utf-8"))

    return signature.hex()

# For tests
def verify_signature(data: str, signature_hex: str, public_key_hex: str) -> bool:
    """Verify transaction signature.
    
    Args:
        data: Original transaction data.
        signature_hex: Signature as hex string.
        public_key_hex: Public key as hex string.
        
    Returns:
        bool: True if signature is valid.
    """    
    public_key = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(public_key_hex)
    )

    try:
        public_key.verify(
            bytes.fromhex(signature_hex),
            data.encode("utf-8")
        )
        return True
    except Exception:
        return False
