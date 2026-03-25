"""Module for generating key pairs for the wallet."""

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import binascii
import time


def generate_ed25519_wallet() -> dict:
    """Generates an Ed25519 key pair.

    Returns:
        dict: A dictionary with the following keys:
            - private_key_hex (str): The private key in hexadecimal format.
            - public_key_hex (str): The public key in hexadecimal format.
            - timestamp (int): The timestamp of when the key was created.
            - version (str): The version of the key format.
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    return {
        "private_key_hex": binascii.hexlify(priv_bytes).decode(),
        "public_key_hex": binascii.hexlify(pub_bytes).decode(),
        "timestamp": int(time.time()),
        "version": "1.0",
    }
