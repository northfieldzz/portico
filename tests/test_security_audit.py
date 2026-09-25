"""
暗号化キーの本番バリデーションおよびツール実行監査ログのテスト
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from portico.core.config import validate_gateway_auth_config
from portico.main import app
from portico.schemas.context import RequestContext
from portico.services.audit import log_tool_execution
from portico.services.crypto import validate_crypto_config


def test_production_without_gateway_secret_raises():
    """本番環境 (ENVIRONMENT=production) で GATEWAY_SHARED_SECRET 未設定時は起動時例外を送出すること"""
    with (
        patch("portico.core.config.ENVIRONMENT", "production"),
        patch("portico.core.config.INSECURE_NO_GATEWAY_AUTH", False),
        patch("portico.core.config.GATEWAY_SHARED_SECRET", None),
        patch("portico.core.config.GATEWAY_SHARED_SECRET_PREVIOUS", None),
        pytest.raises(RuntimeError, match="GATEWAY_SHARED_SECRET must be set in production"),
    ):
        validate_gateway_auth_config()


def test_production_short_gateway_secret_raises():
    """本番環境で GATEWAY_SHARED_SECRET が32文字未満の場合は起動時例外を送出すること"""
    with (
        patch("portico.core.config.ENVIRONMENT", "production"),
        patch("portico.core.config.INSECURE_NO_GATEWAY_AUTH", False),
        patch("portico.core.config.GATEWAY_SHARED_SECRET", "too-short-secret"),
        patch("portico.core.config.GATEWAY_SHARED_SECRET_PREVIOUS", None),
        pytest.raises(RuntimeError, match="at least 32 characters"),
    ):
        validate_gateway_auth_config()


def test_production_without_secret_key_raises():
    """本番環境 (ENVIRONMENT=production) で SECRET_ENCRYPTION_KEY 未設定時は起動時例外を送出すること"""
    with (
        patch.dict("os.environ", {"ENVIRONMENT": "production", "SECRET_ENCRYPTION_KEY": ""}),
        pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY must be set in production"),
    ):
        validate_crypto_config()


def test_development_without_secret_key_logs_warning(caplog):
    """開発環境では例外にならず警告ログで許容されること"""
    with (
        patch.dict("os.environ", {"ENVIRONMENT": "development", "SECRET_ENCRYPTION_KEY": ""}),
        caplog.at_level(logging.WARNING),
    ):
        validate_crypto_config()
        assert "Using default fallback key for development" in caplog.text



def test_audit_logging_structure(caplog):
    """log_tool_execution で期待通りの構造化ログが出力されること"""
    ctx = RequestContext(
        tenant_id="tenant_audit_test",
        key_id="550e8400-e29b-41d4-a716-446655440000",
        key_prefix="tlge-audit-1234",
        service_id="svc-mcp",
        is_proxied=True,
    )
    with caplog.at_level(logging.INFO, logger="portico.audit"):
        record = log_tool_execution(
            tool_name="test_tool",
            duration_ms=45.67,
            success=True,
            context=ctx,
        )
        assert record["tool_name"] == "test_tool"
        assert record["duration_ms"] == 45.67
        assert record["success"] is True
        assert record["tenant_id"] == "tenant_audit_test"
        assert record["key_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert record["key_prefix"] == "tlge-audit-1234"
        assert record["is_proxied"] is True
        assert "AUDIT_EVENT:" in caplog.text


@pytest.mark.asyncio
async def test_audit_log_emitted_during_tool_execution(caplog):
    """ツール実行時に監査ログが正しく出力されること"""
    from fastapi import HTTPException
    from portico.services.server_service import dispatch_tool_call

    ctx = RequestContext(
        tenant_id="tenant_live_audit",
        key_id="key-test-9999",
        key_prefix="tlge-test",
        is_proxied=True,
    )
    with caplog.at_level(logging.INFO, logger="portico.audit"):
        # 存在しないツールを実行 (404 でも失敗イベントとして監査ログが残る)
        with pytest.raises(HTTPException):
            await dispatch_tool_call(
                "nonexistent_audit_tool",
                {"param": "value"},
                tenant_id="tenant_live_audit",
                context=ctx,
            )
        assert "AUDIT_EVENT:" in caplog.text
        assert "tenant_live_audit" in caplog.text
        assert "key-test-9999" in caplog.text

