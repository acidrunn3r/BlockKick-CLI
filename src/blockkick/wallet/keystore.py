"""Module for managing keystore files."""

from rich.console import Console
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import os
import json
import binascii
from pathlib import Path
from .keys import generate_ed25519_wallet

console = Console()

KEYSTORE_DIR = Path.home() / ".blockkick" / "keystores"
KEYSTORE_DIR.mkdir(parents=True, exist_ok=True)


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive strong key from password using scrypt (memory-hard KDF).
    
    Args:
        password (str): User-provided password.
        salt (bytes): Random salt.

    Returns:
        bytes: A 32-byte derived key suitable for AES-256-GCM.
    """
    kdf = Scrypt(
        salt=salt,
        length=32,
        n=2**14,
        r=8,
        p=1,
        backend=default_backend()
    )
    return kdf.derive(password.encode("utf-8"))


def create_keystore(password: str) -> tuple[Path, str]:
    """Creates a new wallet, encrypts the private key, and saves it as a keystore file.
    
    Args:
        password (str): The password to use for encrypting the private key.

    Returns:
        Path: The path to the created keystore file.
    """
    wallet = generate_ed25519_wallet()

    # Encrypting private key
    salt = os.urandom(32)
    nonce = os.urandom(12)
    key = derive_key(password, salt)

    aesgcm = AESGCM(key)
    priv_bytes = binascii.unhexlify(wallet["private_key_hex"])
    ciphertext = aesgcm.encrypt(nonce, priv_bytes, None)

    keystore_data = {
        "public_key_hex": wallet["public_key_hex"],
        "timestamp": wallet["timestamp"],
        "version": wallet["version"],
        "crypto": {
            "cipher": "aes-256-gcm",
            "ciphertext": binascii.hexlify(ciphertext).decode(),
            "nonce": binascii.hexlify(nonce).decode(),
            "kdf": "scrypt",
            "kdfparams": {
                "salt": binascii.hexlify(salt).decode(),
                "n": 16384,
                "r": 8,
                "p": 1,
                "dklen": 32
            }
        }
    }

    filename = f"keystore-{wallet['public_key_hex'][:16]}.json"
    filepath = KEYSTORE_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(keystore_data, f, indent=2, ensure_ascii=False)

    return filepath, wallet['public_key_hex']


def decrypt_keystore(keystore: Path, password: str) -> bytes:
    """Decrypt keystore file and return private key.
    
    Args:
        keystore: Path to keystore file.
        password: Password, used for creating the wallet.
        
    Returns:
        bytes: Decrypted private key (raw bytes, not hex).
        
    Raises:
        ValueError: If password is incorrect or keystore is invalid.
        FileNotFoundError: If keystore file does not exist.
    """
    with open(keystore, "r", encoding="utf-8") as f:
        keystore_data = json.load(f)
    
    crypto = keystore_data["crypto"]
    ciphertext = binascii.unhexlify(crypto["ciphertext"])
    nonce = binascii.unhexlify(crypto["nonce"])
    salt = binascii.unhexlify(crypto["kdfparams"]["salt"])
    
    key = derive_key(password, salt)
    
    aesgcm = AESGCM(key)
    try:
        private_key_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as e:
        raise ValueError("Неверный пароль или повреждённый keystore") from e
    
    return private_key_bytes
