"""JWT, password hashing, AES-256-GCM for webhook secrets."""

from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt

from app.config import get_settings


ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("password required")
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid password hash") from exc


def create_access_token(user_id: UUID, email: str) -> str:
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "email": email, "exp": exp}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("invalid or expired token") from exc


def _aes_key() -> bytes:
    settings = get_settings()
    raw = settings.encryption_key or settings.secret_key
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_secret(plaintext: str) -> str:
    if plaintext is None:
        raise ValueError("plaintext required")
    if plaintext == "":
        return ""
    nonce = os.urandom(12)
    aes = AESGCM(_aes_key())
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(blob: str) -> str:
    if not blob:
        return ""
    try:
        raw = base64.b64decode(blob.encode("ascii"))
        nonce, ct = raw[:12], raw[12:]
        aes = AESGCM(_aes_key())
        return aes.decrypt(nonce, ct, None).decode("utf-8")
    except Exception as exc:
        raise ValueError("failed to decrypt secret") from exc
