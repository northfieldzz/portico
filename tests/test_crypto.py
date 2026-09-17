"""
Unit tests for crypto and authentication utilities in mcp_gateway.
"""

from __future__ import annotations

import pytest

from mcp_gateway.schemas.server import AuthType
from mcp_gateway.services.crypto import (
    build_auth_headers,
    decrypt_auth_config,
    decrypt_secret,
    encrypt_auth_config,
    encrypt_secret,
)


def test_encrypt_decrypt_string_roundtrip():
    plaintext = "super-secret-token-12345"
    ciphertext = encrypt_secret(plaintext)
    assert ciphertext != plaintext
    assert isinstance(ciphertext, str)

    decrypted = decrypt_secret(ciphertext)
    assert decrypted == plaintext


def test_encrypt_empty_or_none():
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""


def test_decrypt_invalid_ciphertext():
    with pytest.raises(ValueError):
        decrypt_secret("enc:v1:not-valid")

    with pytest.raises(ValueError):
        decrypt_secret("enc:v1:part1:part2:part3")


def test_build_auth_headers_none():
    assert build_auth_headers(AuthType.NONE) == {}


def test_build_auth_headers_bearer():
    headers = build_auth_headers(AuthType.BEARER, auth_token="my-jwt-token")
    assert headers == {"Authorization": "Bearer my-jwt-token"}


def test_build_auth_headers_api_key_default():
    headers = build_auth_headers(AuthType.API_KEY, auth_token="my-api-key")
    assert headers == {"X-API-Key": "my-api-key"}


def test_build_auth_headers_api_key_custom_name():
    headers = build_auth_headers(
        AuthType.API_KEY,
        auth_token="my-api-key",
        auth_header_name="X-Custom-Auth",
    )
    assert headers == {"X-Custom-Auth": "my-api-key"}


def test_build_auth_headers_custom():
    custom = {"X-Tenant": "tenant-1", "X-Signature": "sig123"}
    headers = build_auth_headers(
        AuthType.CUSTOM,
        auth_token="ignored-in-custom",
        custom_headers=custom,
    )
    assert headers == {"X-Tenant": "tenant-1", "X-Signature": "sig123"}


def test_encrypt_and_decrypt_auth_config():
    headers = build_auth_headers(AuthType.BEARER, auth_token="secret-token-xyz")
    enc = encrypt_auth_config(
        {
            "auth_type": AuthType.BEARER.value,
            "headers": headers,
        }
    )
    assert enc != ""
    assert "secret-token-xyz" not in enc  # Plaintext token must not be present

    dec = decrypt_auth_config(enc)
    assert dec["auth_type"] == "bearer"
    assert dec["headers"] == {"Authorization": "Bearer secret-token-xyz"}


def test_encrypt_auth_config_none():
    enc = encrypt_auth_config({})
    assert enc == ""

    dec = decrypt_auth_config(None)
    assert dec == {}
