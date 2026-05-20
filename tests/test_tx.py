"""Tests for blockchain.tx module."""

from blockkick.blockchain.tx import sign_transaction, verify_signature


class TestSignTransaction:
    """Tests for sign_transaction function."""

    def test_sign_returns_hex_string(self):
        """Signature should be a hex string."""
        private_key = b"0" * 32
        signature = sign_transaction("test_data", private_key)

        assert isinstance(signature, str)
        assert len(signature) == 128


class TestVerifySignature:
    """Tests for verify_signature function."""

    def test_verify_valid_signature(self):
        """Valid signature should verify successfully."""
        private_key = b"0" * 32
        data = "campaign_123:100"

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        public_key = Ed25519PrivateKey.from_private_bytes(private_key).public_key()
        public_key_hex = public_key.public_bytes_raw().hex()

        signature = sign_transaction(data, private_key)

        assert verify_signature(data, signature, public_key_hex) is True

    def test_verify_invalid_signature(self):
        """Tampered data should fail verification."""
        private_key = b"0" * 32
        data = "original_data"

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        public_key = Ed25519PrivateKey.from_private_bytes(private_key).public_key()
        public_key_hex = public_key.public_bytes_raw().hex()

        signature = sign_transaction(data, private_key)

        assert verify_signature("tampered_data", signature, public_key_hex) is False
