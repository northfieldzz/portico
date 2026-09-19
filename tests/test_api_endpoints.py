"""
Unit and integration tests for FastAPI routes and dependency injection.
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from portico.core.config import INTERNAL_SERVICE_SECRET
from portico.db.session import get_memory_external_servers


class TestDependencyInjection:
    """api/deps.py のテナントIDおよびシークレット検証テスト。"""

    def test_get_tenant_id_from_header(self, client: TestClient):
        """X-Tenant-ID ヘッダーからテナントIDが抽出される。"""
        mem = get_memory_external_servers()
        mem["srv-h1"] = {"id": "srv-h1", "tenant_id": "tenant_header_123", "name": "H1", "url": "https://h1.example.com", "status": "active"}
        resp = client.get("/v1/servers", headers={"X-Tenant-ID": "tenant_header_123"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["tenant_id"] == "tenant_header_123"

    def test_get_tenant_id_from_query(self, client: TestClient):
        """クエリパラメータ tenant_id からテナントIDが抽出される。"""
        mem = get_memory_external_servers()
        mem["srv-q1"] = {"id": "srv-q1", "tenant_id": "tenant_query_456", "name": "Q1", "url": "https://q1.example.com", "status": "active"}
        resp = client.get("/v1/servers?tenant_id=tenant_query_456")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["tenant_id"] == "tenant_query_456"

    def test_get_tenant_id_default(self, client: TestClient):
        """指定がない場合は tenant_default となる。"""
        mem = get_memory_external_servers()
        mem["srv-d1"] = {"id": "srv-d1", "tenant_id": "tenant_default", "name": "D1", "url": "https://d1.example.com", "status": "active"}
        resp = client.get("/v1/servers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["tenant_id"] == "tenant_default"

    def test_internal_secret_forbidden_when_missing_or_invalid(self, client: TestClient):
        """内部APIに不正または欠落した X-Internal-Secret を渡すと 403 となる。"""
        resp_missing = client.delete("/v1/internal/tenants/t1")
        assert resp_missing.status_code == 403

        resp_invalid = client.delete("/v1/internal/tenants/t1", headers={"X-Internal-Secret": "wrong-secret"})
        assert resp_invalid.status_code == 403

    def test_internal_secret_authorized(self, client: TestClient):
        """正しい X-Internal-Secret で内部APIにアクセスできる。"""
        resp = client.delete(
            "/v1/internal/tenants/tenant_clean",
            headers={"X-Internal-Secret": INTERNAL_SERVICE_SECRET},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["tenant_id"] == "tenant_clean"


class TestServerRoutes:
    """api/routes/servers.py のテスト。"""

    def test_list_servers(self, client: TestClient):
        """サーバー一覧の取得。"""
        resp = client.get("/v1/servers", headers={"X-Tenant-ID": "tenant_srv_test"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_register_server_ssrf_blocked(self, client: TestClient):
        """SSRF に該当する不正な URL は 422 バリデーションエラーとなる。"""
        resp = client.post(
            "/v1/servers",
            headers={"X-Tenant-ID": "tenant_srv_test"},
            json={"name": "Evil Server", "url": "http://169.254.169.254/latest"},
        )
        assert resp.status_code == 422

    def test_register_server_success(self, client: TestClient):
        """正常な外部サーバーの登録。"""
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
            with patch("httpx.AsyncClient.post", return_value=AsyncMock(status_code=200)):
                resp = client.post(
                    "/v1/servers",
                    headers={"X-Tenant-ID": "tenant_srv_test"},
                    json={"name": "Confluence MCP", "url": "https://confluence.example.com"},
                )
                assert resp.status_code == 201
                data = resp.json()
                assert data["name"] == "Confluence MCP"
                assert data["status"] == "active"
                assert data["tenant_id"] == "tenant_srv_test"


    def test_delete_nonexistent_server_returns_404(self, client: TestClient):
        """存在しない外部サーバーの削除は 404 となる。"""
        resp = client.delete("/v1/servers/ext-nonexist", headers={"X-Tenant-ID": "tenant_srv_test"})
        assert resp.status_code == 404

    def test_delete_external_server_success(self, client: TestClient):
        """登録済み外部サーバーの削除成功。"""
        mem = get_memory_external_servers()
        mem["ext-123"] = {
            "id": "ext-123",
            "tenant_id": "tenant_del_route",
            "name": "To Delete",
            "url": "https://delete.example.com",
            "status": "active",
        }

        resp = client.delete("/v1/servers/ext-123", headers={"X-Tenant-ID": "tenant_del_route"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["id"] == "ext-123"


    def test_create_server_with_bearer_auth(self, client: TestClient):
        """Bearer 認証付きの外部サーバー登録と平文トークン非露出を検証。"""
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
            with patch("httpx.AsyncClient.post", return_value=AsyncMock(status_code=200)):
                resp = client.post(

                    "/v1/servers",
                    headers={"X-Tenant-ID": "tenant_api_auth"},
                    json={
                        "name": "Auth API Server",
                        "url": "https://api-auth.example.com",
                        "auth_type": "bearer",
                        "auth_token": "super-secret-token",
                    },
                )
                assert resp.status_code == 201
                data = resp.json()
                assert data["auth_type"] == "bearer"
                assert data["has_auth"] is True
                assert "super-secret-token" not in resp.text


class TestToolRoutes:
    """api/routes/tools.py のテスト。"""

    def test_list_tools_empty_when_no_servers(self, client: TestClient):
        """外部サーバー未登録時のツールマニフェスト一覧は空。"""
        resp = client.get("/v1/tools", headers={"X-Tenant-ID": "tenant_tool_test"})
        assert resp.status_code == 200
        tools = resp.json()
        assert isinstance(tools, list)
        assert len(tools) == 0

    def test_execute_unknown_tool_returns_404(self, client: TestClient):
        """未登録のツール呼び出しは 404 となる。"""
        resp = client.post(
            "/v1/tools/completely_nonexistent_tool",
            headers={"X-Tenant-ID": "tenant_tool_test"},
            json={"foo": "bar"},
        )
        assert resp.status_code == 404
        assert "Unknown tool" in resp.json()["detail"]

    def test_execute_external_tool_with_auth(self, client: TestClient):
        """外部 MCP サーバーへのツール実行プロキシ時に認証ヘッダーが付与される。"""
        mem = get_memory_external_servers()
        from portico.services.crypto import encrypt_auth_config

        enc = encrypt_auth_config(
            {
                "auth_type": "bearer",
                "headers": {"Authorization": "Bearer ext-token-999"},
            }
        )
        mem["ext-proxy-1"] = {
            "id": "ext-proxy-1",
            "tenant_id": "tenant_proxy_auth",
            "name": "Proxy Target",
            "url": "https://proxy.example.com",
            "auth_type": "bearer",
            "encrypted_auth_config": enc,
        }

        mock_resp = httpx.Response(200, json={"jsonrpc": "2.0", "result": {"value": 42}})
        with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
            resp = client.post(
                "/v1/tools/ext_calc",
                headers={"X-Tenant-ID": "tenant_proxy_auth"},
                json={"x": 20, "y": 22},
            )
            assert resp.status_code == 200
            assert resp.json()["result"]["value"] == 42

            # プロキシリクエストのヘッダーに Bearer トークンが付与されていること
            mock_post.assert_awaited()
            call_headers = mock_post.call_args[1].get("headers", {})
            assert call_headers.get("Authorization") == "Bearer ext-token-999"
            call_json = mock_post.call_args[1].get("json", {})
            assert call_json.get("method") == "tools/call"
            assert call_json.get("params", {}).get("name") == "ext_calc"

    def test_execute_namespaced_tool_targeted_routing(self, client: TestClient):
        """名前空間付きツール名 ({server_slug}__{tool}) で呼び出した際、対象サーバーにのみプロキシ転送されることを検証。"""
        mem = get_memory_external_servers()
        mem["srv-alpha"] = {
            "id": "srv-alpha",
            "tenant_id": "tenant_route_test",
            "name": "Alpha Service",
            "url": "https://alpha.example.com",
        }
        mem["srv-beta"] = {
            "id": "srv-beta",
            "tenant_id": "tenant_route_test",
            "name": "Beta Service",
            "url": "https://beta.example.com",
        }

        mock_post_resp = httpx.Response(200, json={"jsonrpc": "2.0", "result": {"server": "alpha"}})

        with patch("httpx.AsyncClient.post", return_value=mock_post_resp) as mock_post:
            # Alpha 側の名前空間で実行
            resp = client.post(
                "/v1/tools/alpha_service__deploy",
                headers={"X-Tenant-ID": "tenant_route_test"},
                json={"env": "staging"},
            )
            assert resp.status_code == 200
            assert resp.json()["result"]["server"] == "alpha"

            # 送信先 URL が alpha.example.com であること (beta には送られない)
            called_url = mock_post.call_args[0][0]
            assert "https://alpha.example.com" in called_url
            call_json = mock_post.call_args[1].get("json", {})
            assert call_json.get("method") == "tools/call"
            assert call_json.get("params", {}).get("name") == "deploy"
