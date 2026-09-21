"""
暗号化キーの本番バリデーションおよびツール実行監査ログのテスト
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from portico.main import app
from portico.schemas.context import RequestContext
from portico.services.audit import log_tool_execution
from portico.services.crypto import validate_crypto_config


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


def test_audit_log_emitted_during_tool_execution(caplog):
    """REST エンドポイント経由でツール実行した際、監査ログが正しく出力されること"""
    client = TestClient(app)
    headers = {
        "X-Tenant-ID": "tenant_live_audit",
        "X-Key-ID": "key-test-9999",
        "X-Key-Prefix": "tlge-test",
    }
    with caplog.at_level(logging.INFO, logger="portico.audit"):
        # 存在しないツールを実行 (404 でも失敗イベントとして監査ログが残る)
        res = client.post(
            "/v1/tools/nonexistent_audit_tool",
            headers=headers,
            json={"param": "value"},
        )
        assert res.status_code == 404
        assert "AUDIT_EVENT:" in caplog.text
        assert "tenant_live_audit" in caplog.text
        assert "key-test-9999" in caplog.text
