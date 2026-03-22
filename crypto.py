"""
Lightweight XOR + Base64 cipher for sender names.
Not cryptographically secure — intended only to obscure names from casual observers.
"""

import base64


def encrypt_name(plaintext: str, key: str) -> str:
    """XOR plaintext with repeating key, then Base64 encode."""
    xored = bytes(
        ord(p) ^ ord(key[i % len(key)])
        for i, p in enumerate(plaintext)
    )
    return base64.urlsafe_b64encode(xored).decode("ascii")


def decrypt_name(ciphertext: str, key: str) -> str:
    """Base64 decode, then XOR with repeating key to recover plaintext."""
    xored = base64.urlsafe_b64decode(ciphertext)
    return "".join(
        chr(b ^ ord(key[i % len(key)]))
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
    print("OK")
