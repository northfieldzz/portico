"""
IT Context Platform — Secret Encryption & Authentication Utility
外部 MCP サーバーの認証ヘッダー等の機密情報を安全に暗号化・復号・組み立てる。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any, Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

PREFIX: Final[str] = "enc:v1:"
DEFAULT_KEY_SALT: Final[str] = "itcp_master_secret_encryption_salt_2026"


def validate_crypto_config() -> None:
    """
    暗号化キー設定の検証。
    本番環境 (ENVIRONMENT == 'production') において SECRET_ENCRYPTION_KEY が未設定またはデフォルト値の場合は
    安全のため RuntimeError を送出する。非本番環境では警告ログを出力する。
    """
    env_key = os.getenv("SECRET_ENCRYPTION_KEY")
    env = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()
    if env == "production":
        if not env_key or not env_key.strip() or env_key == DEFAULT_KEY_SALT:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_ENCRYPTION_KEY must be set in production environment!"
            )
    else:
        if not env_key:
            logger.warning(
                "SECRET_ENCRYPTION_KEY is not set. Using default fallback key for development. Do not use in production!"
            )


def _get_key(custom_key: bytes | None = None) -> bytes:
    """32バイト (256ビット) の AES 鍵を取得または導出する。"""
    if custom_key:
        if len(custom_key) == 32:
            return custom_key
        return hashlib.sha256(custom_key).digest()

    env_key = os.getenv("SECRET_ENCRYPTION_KEY")
    if env_key:
        return hashlib.sha256(env_key.encode()).digest()

    return hashlib.sha256(DEFAULT_KEY_SALT.encode()).digest()


def encrypt_secret(plaintext: str, key: bytes | None = None) -> str:
    """平文文字列を AES-256-GCM で暗号化する。"""
    if not plaintext:
        return ""

    aes_key = _get_key(key)
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(12)

    data = plaintext.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, data, None)

    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    cipher_b64 = base64.b64encode(ciphertext).decode("ascii")

    return f"{PREFIX}{nonce_b64}:{cipher_b64}"


def decrypt_secret(encrypted_text: str, key: bytes | None = None) -> str:
    """暗号化されたシークレット文字列を復号する。"""
    if not encrypted_text:
        return ""

    if not encrypted_text.startswith(PREFIX):
        return encrypted_text

    payload = encrypted_text[len(PREFIX) :]
    parts = payload.split(":")
    if len(parts) != 2:
        raise ValueError("Invalid encrypted secret format")

    nonce_b64, cipher_b64 = parts
    nonce = base64.b64decode(nonce_b64)
    ciphertext = base64.b64decode(cipher_b64)

    aes_key = _get_key(key)
    aesgcm = AESGCM(aes_key)

    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_bytes.decode("utf-8")


def build_auth_headers(
    auth_type: str = "none",
    auth_token: str | None = None,
    auth_header_name: str | None = None,
    custom_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    認証種別に応じた HTTP リクエストヘッダー辞書を構築する。
    """
    headers: dict[str, str] = {}

    if auth_type == "bearer" and auth_token:
        headers["Authorization"] = f"Bearer {auth_token.strip()}"
    elif auth_type == "api_key" and auth_token:
        header_name = (auth_header_name or "X-API-Key").strip()
        headers[header_name] = auth_token.strip()
    elif auth_type == "custom":
        if custom_headers:
            headers.update({str(k): str(v) for k, v in custom_headers.items()})

    # custom_headers が追加指定されている場合はマージ
    if auth_type in ("bearer", "api_key") and custom_headers:
        headers.update({str(k): str(v) for k, v in custom_headers.items()})

    return headers


def encrypt_auth_config(auth_config: dict[str, Any]) -> str:
    """認証設定辞書を JSON 文字列化して暗号化する。"""
    if not auth_config:
        return ""
    serialized = json.dumps(auth_config)
    return encrypt_secret(serialized)


def decrypt_auth_config(encrypted_text: str | None) -> dict[str, Any]:
    """暗号化された認証設定文字列を復号して辞書に戻す。"""
    if not encrypted_text:
        return {}
    try:
        decrypted = decrypt_secret(encrypted_text)
        return json.loads(decrypted) if decrypted else {}
    except Exception as exc:
        logger.warning("Failed to decrypt auth config: %s", exc)
        return {}
