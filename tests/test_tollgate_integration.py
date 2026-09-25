"""
Tollgate リバースプロキシ連携およびスタンドアロン両立のテスト
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from portico.api.deps import get_request_context, get_tenant_id
from portico.main import app
from portico.schemas.context import RequestContext


@pytest.fixture
def mock_context_app():
    """コンテキスト確認用の軽量 FastAPI テストアプリ"""
    test_app = FastAPI()

    @test_app.get("/test/context")
    async def endpoint_context(ctx: RequestContext = Depends(get_request_context)):
        return ctx.model_dump()

    @test_app.get("/test/tenant")
    async def endpoint_tenant(tid: str = Depends(get_tenant_id)):
        return {"tenant_id": tid}

    return test_app


def test_standalone_no_headers_insecure_mode(mock_context_app, monkeypatch):
    """INSECURE_NO_GATEWAY_AUTH=True (開発モード) 時はシークレットなしで動作すること"""
    monkeypatch.setattr("portico.api.deps.INSECURE_NO_GATEWAY_AUTH", True)
    client = TestClient(mock_context_app)
    res = client.get("/test/context")
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == "tenant_default"
    assert data["is_proxied"] is False
    assert data["key_id"] is None

    res_tenant = client.get("/test/tenant")
    assert res_tenant.status_code == 200
    assert res_tenant.json()["tenant_id"] == "tenant_default"


def test_gateway_secret_all_headers(mock_context_app, monkeypatch):
    """Tollgate / Proxy から X-Gateway-Secret と全連携ヘッダーが付与された場合に認証成功すること"""
    monkeypatch.setattr("portico.api.deps.INSECURE_NO_GATEWAY_AUTH", False)
    monkeypatch.setattr(
        "portico.api.deps.get_valid_gateway_secrets",
        lambda: ["gw-secret-32-chars-long-abcdef0123456789"],
    )

    client = TestClient(mock_context_app)
    headers = {
        "X-Gateway-Secret": "gw-secret-32-chars-long-abcdef0123456789",
        "X-Tenant-ID": "tenant_corp_abc123",
        "X-Key-ID": "550e8400-e29b-41d4-a716-446655440000",
        "X-Key-Prefix": "tlge-live-8f9c",
        "X-Service-ID": "svc-mcp-cluster-1",
    }
    res = client.get("/test/context", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == "tenant_corp_abc123"
    assert data["key_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert data["key_prefix"] == "tlge-live-8f9c"
    assert data["service_id"] == "svc-mcp-cluster-1"
    assert data["is_proxied"] is True


def test_gateway_secret_rotation(mock_context_app, monkeypatch):
    """新旧 Gateway 共有シークレット（ローテーション対応）のいずれでも認証が通過すること"""
    monkeypatch.setattr("portico.api.deps.INSECURE_NO_GATEWAY_AUTH", False)
    monkeypatch.setattr(
        "portico.api.deps.get_valid_gateway_secrets",
        lambda: ["primary-secret-32-chars-0000000000", "previous-secret-32-chars-11111111"],
    )

    client = TestClient(mock_context_app)

    # 1. 新シークレット (Primary) での認証成功
    res_primary = client.get(
        "/test/context",
        headers={"X-Gateway-Secret": "primary-secret-32-chars-0000000000"},
    )
    assert res_primary.status_code == 200

    # 2. 旧シークレット (Previous) での認証成功 (ローテーション移行期間)
    res_previous = client.get(
        "/test/context",
        headers={"X-Gateway-Secret": "previous-secret-32-chars-11111111"},
    )
    assert res_previous.status_code == 200

    # 3. 不正シークレットでの認証失敗 (401)
    res_invalid = client.get(
        "/test/context",
        headers={"X-Gateway-Secret": "invalid-secret"},
    )
    assert res_invalid.status_code == 401
    assert "Missing or invalid gateway shared secret" in res_invalid.json()["detail"]

    # 4. シークレット欠落での認証失敗 (401)
    res_missing = client.get("/test/context")
    assert res_missing.status_code == 401


def test_tenant_id_conflict_fail_fast(mock_context_app, monkeypatch):
    """X-Tenant-ID ヘッダーと query tenant_id が不一致の場合は 403 で Fail-Fast すること"""
    monkeypatch.setattr("portico.api.deps.INSECURE_NO_GATEWAY_AUTH", True)
    client = TestClient(mock_context_app)
    headers = {"X-Tenant-ID": "tenant_from_header"}
    res = client.get("/test/context?tenant_id=tenant_from_query", headers=headers)
    assert res.status_code == 403
    assert "Tenant ID conflict" in res.json()["detail"]


def test_main_app_servers_endpoint_with_gateway_secret(monkeypatch):
    """実アプリケーションエンドポイント (/v1/servers) への X-Gateway-Secret 連携動作確認"""
    monkeypatch.setattr("portico.api.deps.INSECURE_NO_GATEWAY_AUTH", False)
    monkeypatch.setattr(
        "portico.api.deps.get_valid_gateway_secrets",
        lambda: ["gw-secret-32-chars-long-abcdef0123456789"],
    )
    client = TestClient(app)
    headers = {
        "X-Gateway-Secret": "gw-secret-32-chars-long-abcdef0123456789",
        "X-Tenant-ID": "tenant_live_demo",
        "X-Key-ID": "key-uuid-9999",
        "X-Key-Prefix": "tlge-live-demo",
    }
    res = client.get("/v1/servers", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)



