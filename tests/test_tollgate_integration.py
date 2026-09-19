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


def test_standalone_no_headers(mock_context_app):
    """ヘッダーなし直接呼び出し時はデフォルトテナントで動作すること"""
    client = TestClient(mock_context_app)
    res = client.get("/test/context")
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == "tenant_default"
    assert data["is_proxied"] is False
    assert data["key_id"] is None
    assert data["key_prefix"] is None
    assert data["service_id"] is None

    res_tenant = client.get("/test/tenant")
    assert res_tenant.status_code == 200
    assert res_tenant.json()["tenant_id"] == "tenant_default"


def test_standalone_query_tenant(mock_context_app):
    """ヘッダーなし・クエリパラメータ指定時は指定テナントが使われること"""
    client = TestClient(mock_context_app)
    res = client.get("/test/context?tenant_id=custom_tenant")
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == "custom_tenant"
    assert data["is_proxied"] is False


def test_tollgate_headers_all(mock_context_app):
    """Tollgate からの全連携ヘッダーが付与された場合にコンテキストへ正しく反映されること"""
    client = TestClient(mock_context_app)
    headers = {
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

    res_tenant = client.get("/test/tenant", headers=headers)
    assert res_tenant.json()["tenant_id"] == "tenant_corp_abc123"


def test_tollgate_headers_without_service_id(mock_context_app):
    """X-Service-ID がない場合でも必須ヘッダーがあればプロキシ認証扱いとなること"""
    client = TestClient(mock_context_app)
    headers = {
        "X-Tenant-ID": "tenant_xyz",
        "X-Key-ID": "key-12345",
        "X-Key-Prefix": "tlge-test-1111",
    }
    res = client.get("/test/context", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == "tenant_xyz"
    assert data["key_id"] == "key-12345"
    assert data["key_prefix"] == "tlge-test-1111"
    assert data["service_id"] is None
    assert data["is_proxied"] is True


def test_enforce_tollgate_auth_enabled(mock_context_app, monkeypatch):
    """ENFORCE_TOLLGATE_AUTH=True 時はヘッダー欠落リクエストが 401 で拒絶されること"""
    monkeypatch.setattr("portico.api.deps.ENFORCE_TOLLGATE_AUTH", True)
    client = TestClient(mock_context_app)

    # ヘッダーなし -> 401
    res = client.get("/test/context")
    assert res.status_code == 401
    assert "Tollgate authentication required" in res.json()["detail"]

    # X-Tenant-ID のみ -> 401 (X-Key-ID 欠落)
    res = client.get("/test/context", headers={"X-Tenant-ID": "t1"})
    assert res.status_code == 401

    # 両方あり -> 200 OK
    res = client.get("/test/context", headers={"X-Tenant-ID": "t1", "X-Key-ID": "k1"})
    assert res.status_code == 200
    assert res.json()["tenant_id"] == "t1"


def test_main_app_tools_endpoint_with_tollgate_headers():
    """実アプリケーションエンドポイント (/api/v1/mcp/tools) への Tollgate ヘッダー透過動作確認"""
    client = TestClient(app)
    headers = {
        "X-Tenant-ID": "tenant_live_demo",
        "X-Key-ID": "key-uuid-9999",
        "X-Key-Prefix": "tlge-live-demo",
    }
    res = client.get("/api/v1/mcp/tools", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
