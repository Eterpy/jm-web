from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from backend.app.core.config import settings


def _build_key() -> bytes:
    if settings.credential_key:
        raw = settings.credential_key.encode("utf-8")
    else:
        raw = settings.secret_key.encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_build_key())


def encrypt_text(plain_text: str) -> str:
    return _fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_text(cipher_text: str) -> str:
    return _fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
