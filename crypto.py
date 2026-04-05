"""
Lightweight XOR + Base64 cipher for sender names.
Uses SHA-256 to derive the XOR key from the passphrase, giving an
avalanche effect — even a small error in the passphrase produces
completely jumbled output.
Not cryptographically secure — intended only to obscure names from casual observers.
"""

import base64
import hashlib


def _derive_key(passphrase: str) -> bytes:
    """Hash the passphrase with SHA-256 to produce a 32-byte key."""
    return hashlib.sha256(passphrase.encode("utf-8")).digest()


def encrypt_name(plaintext: str, key: str) -> str:
    """SHA-256 the key, XOR plaintext with derived bytes, then Base64 encode."""
    derived = _derive_key(key)
    xored = bytes(
        ord(p) ^ derived[i % len(derived)]
        for i, p in enumerate(plaintext)
    )
    return base64.urlsafe_b64encode(xored).decode("ascii")


def decrypt_name(ciphertext: str, key: str) -> str:
    """Base64 decode, SHA-256 the key, then XOR to recover plaintext."""
    derived = _derive_key(key)
    xored = base64.urlsafe_b64decode(ciphertext)
    return "".join(
        chr(b ^ derived[i % len(derived)])
        for i, b in enumerate(xored)
    )


if __name__ == "__main__":
    # Quick self-test
    key = "testkey"
    name = "John Doe"
    enc = encrypt_name(name, key)
    dec = decrypt_name(enc, key)
    print(f"Original:  {name}")
    print(f"Encrypted: {enc}")
    print(f"Decrypted: {dec}")
    assert dec == name, "Round-trip failed!"

    # Test avalanche — wrong key should produce total garbage
    wrong = decrypt_name(enc, "testke")
    print(f"Wrong key: {wrong}")
    assert wrong != name, "Wrong key should not decrypt!"
    print("OK — avalanche effect confirmed")
