"""
app/security/crypto.py
敏感字段加解密工具。
"""

from __future__ import annotations

from cryptography.fernet import Fernet


def encrypt_secret(secret: str, key: str) -> str:
    return Fernet(key.encode("utf-8")).encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str, key: str) -> str:
    return Fernet(key.encode("utf-8")).decrypt(cipher_text.encode("utf-8")).decode("utf-8")
