"""Модуль для работы с ключами."""

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import binascii
import time


def generate_ed25519_wallet() -> dict:
    """Генерирует пару Ed25519 ключей.
    
    Returns:
        dict: Словарь с ключами:
            - private_key_hex (str): приватный ключ в hex
            - public_key_hex (str): публичный ключ в hex
            - timestamp (int): timestamp создания ключа
            - version (str): версия формата
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
