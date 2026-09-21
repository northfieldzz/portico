"""
Unit tests for external MCP server management and tool aggregation service.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import httpx
import pytest
from fastapi import HTTPException

from portico.db.session import get_memory_external_servers
from portico.schemas.server import AuthType, ServerCreateRequest
from portico.services.server_service import (
    add_external_server,
    delete_all_servers_for_tenant,
    get_aggregated_tools,
    get_external_servers_with_auth,
    list_servers_for_tenant,
    remove_external_server,
)



class TestServerService:
    """外部 MCP サーバー管理ロジックの単体テスト。"""

    @pytest.mark.asyncio
    async def test_list_servers_empty_when_no_external_servers(self):
        """外部サーバーが未登録の場合、空リストが返る。"""
        servers = await list_servers_for_tenant("tenant_empty")
        assert servers == []

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_memory(self):
        """テナント A と テナント B の外部サーバーが相互に混ざらない。"""
        mem = get_memory_external_servers()
        mem["srv-1"] = {
            "id": "srv-1",
            "tenant_id": "tenant_a",
            "name": "Server A",
            "url": "https://a.mcp.example.com",
            "status": "active",
        }
        mem["srv-2"] = {
            "id": "srv-2",
            "tenant_id": "tenant_b",
            "name": "Server B",
            "url": "https://b.mcp.example.com",
            "status": "active",
        }

        servers_a = await list_servers_for_tenant("tenant_a")
        server_names_a = [s["name"] for s in servers_a]
        assert "Server A" in server_names_a
        assert "Server B" not in server_names_a

        servers_b = await list_servers_for_tenant("tenant_b")
        server_names_b = [s["name"] for s in servers_b]
        assert "Server B" in server_names_b
        assert "Server A" not in server_names_b

    @pytest.mark.asyncio
    async def test_add_external_server_success(self):
        """外部サーバーの登録、プローブ判定、AI Engine への通知が正常に行われる。"""
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
            req = ServerCreateRequest(name="Jira MCP", url="https://jira.mcp.example.com")

        async def mock_post(url, **kwargs):
            if "/sync" in str(url):
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": []}})

        with patch("httpx.AsyncClient.post", side_effect=mock_post) as mock_p:
            res = await add_external_server(req, tenant_id="tenant_jira")

            assert res["name"] == "Jira MCP"
            assert res["url"] == "https://jira.mcp.example.com"
            assert res["status"] == "active"
            assert res["tenant_id"] == "tenant_jira"
            assert res["is_builtin"] is False

    @pytest.mark.asyncio
    async def test_add_external_server_infrastructure_limit(self):
        """物理リミット (MAX_SERVERS_PER_TENANT) 到達時に 429 エラーを送出する。"""
        with (
            patch("portico.services.server_service.MAX_SERVERS_PER_TENANT", 2),
            patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]),
        ):
            mem = get_memory_external_servers()
            mem["s-1"] = {"id": "s-1", "tenant_id": "tenant_limit_test", "name": "S1", "url": "http://s1", "is_builtin": False}
            mem["s-2"] = {"id": "s-2", "tenant_id": "tenant_limit_test", "name": "S2", "url": "http://s2", "is_builtin": False}

            req = ServerCreateRequest(name="S3", url="https://s3.example.com")
            with pytest.raises(HTTPException) as exc_info:
                await add_external_server(req, tenant_id="tenant_limit_test")
            assert exc_info.value.status_code == 429
            assert "Tenant infrastructure limit reached" in exc_info.value.detail


    @pytest.mark.asyncio
    async def test_remove_external_server(self):

        """外部サーバーの削除テスト。"""
        mem = get_memory_external_servers()
        mem["srv-del"] = {
            "id": "srv-del",
            "tenant_id": "tenant_del",
            "name": "Delete Me",
            "url": "https://del.example.com",
            "status": "active",
        }

        # 正常削除
        deleted = await remove_external_server("srv-del", "tenant_del")
        assert deleted is True
        assert "srv-del" not in mem

        # 存在しないサーバーの削除は False
        deleted_nonexist = await remove_external_server("srv-nonexist", "tenant_del")
        assert deleted_nonexist is False


    @pytest.mark.asyncio
    async def test_delete_all_servers_for_tenant(self):
        """テナント一括削除時に該当テナントのサーバーのみ削除される。"""
        mem = get_memory_external_servers()
        mem["s1"] = {"id": "s1", "tenant_id": "tenant_x", "name": "S1", "url": "http://1"}
        mem["s2"] = {"id": "s2", "tenant_id": "tenant_x", "name": "S2", "url": "http://2"}
        mem["s3"] = {"id": "s3", "tenant_id": "tenant_y", "name": "S3", "url": "http://3"}

        count = await delete_all_servers_for_tenant("tenant_x")
        assert count == 2
        assert "s1" not in mem
        assert "s2" not in mem
        assert "s3" in mem  # tenant_y は保持される

    @pytest.mark.asyncio
    async def test_get_aggregated_tools(self):
        """標準ツールと外部 MCP サーバーのツールマニフェストがマージされる。"""
        mem = get_memory_external_servers()
        mem["s-ext"] = {
            "id": "s-ext",
            "tenant_id": "tenant_agg",
            "name": "External Tools",
            "url": "https://ext.example.com",
        }

        mock_resp = httpx.Response(
            200,
            json={"jsonrpc": "2.0", "result": {"tools": [{"name": "custom_deploy_tool", "description": "Custom deployer", "parameters": {}}]}},
        )

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            tools = await get_aggregated_tools("tenant_agg")
            tool_names = [t["name"] for t in tools]
            orig_names = [t.get("original_name") for t in tools]
            # 外部ツールには名前空間プレフィックスが付与されること
            assert "external_tools__custom_deploy_tool" in tool_names
            assert "custom_deploy_tool" in orig_names

    @pytest.mark.asyncio
    async def test_namespaced_tools_collision_prevention(self):
        """同一ツール名を持つ2つの外部 MCP サーバーが登録された際、名前空間によって衝突せず共存できることを検証。"""
        mem = get_memory_external_servers()
        mem["srv-slack"] = {
            "id": "srv-slack",
            "tenant_id": "tenant_collision",
            "name": "Slack MCP",
            "url": "https://slack.example.com",
        }
        mem["srv-teams"] = {
            "id": "srv-teams",
            "tenant_id": "tenant_collision",
            "name": "Teams MCP",
            "url": "https://teams.example.com",
        }

        async def mock_post_collision(url, **kwargs):
            host = urlparse(str(url)).hostname
            if host == "slack.example.com":
                return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": [{"name": "send_message", "description": "Send via Slack"}]}})
            if host == "teams.example.com":
                return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": [{"name": "send_message", "description": "Send via Teams"}]}})
            return httpx.Response(404)

        with patch("httpx.AsyncClient.post", side_effect=mock_post_collision):
            tools = await get_aggregated_tools("tenant_collision")
            tool_names = [t["name"] for t in tools]
            # 両サーバーの同名ツールが独立した名前空間で保持されること
            assert "slack_mcp__send_message" in tool_names
            assert "teams_mcp__send_message" in tool_names

            # 各ツールの server_name, original_name, description の整合性を確認
            slack_tool = next(t for t in tools if t["name"] == "slack_mcp__send_message")
            teams_tool = next(t for t in tools if t["name"] == "teams_mcp__send_message")
            assert slack_tool["original_name"] == "send_message"
            assert slack_tool["server_name"] == "Slack MCP"
            assert slack_tool["description"] == "Send via Slack"
            assert teams_tool["original_name"] == "send_message"
            assert teams_tool["server_name"] == "Teams MCP"
            assert teams_tool["description"] == "Send via Teams"

    @pytest.mark.asyncio
    async def test_add_server_with_bearer_auth(self):
        """Bearer 認証付き外部サーバーの登録と暗号化保存を検証。"""
        import socket

        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
            req = ServerCreateRequest(
                name="Secure Server",
                url="https://secure.example.com",
                auth_type=AuthType.BEARER,
                auth_token="jwt-secret-abc",
            )

            async def mock_post(url, **kwargs):
                if "/sync" in str(url):
                    return httpx.Response(200, json={"status": "ok"})
                return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": []}})

            with patch("httpx.AsyncClient.post", side_effect=mock_post) as mock_p:
                server = await add_external_server(req, "tenant_auth")
                assert server["auth_type"] == "bearer"

                assert server["has_auth"] is True
                assert "jwt-secret-abc" not in str(server)  # 生トークンが露出していないこと

                # プローブ時に Authorization ヘッダーが付与されていること
                probe_call = mock_p.call_args_list[0]
                called_headers = probe_call[1].get("headers", {})
                assert called_headers.get("Authorization") == "Bearer jwt-secret-abc"

                # get_external_servers_with_auth で復号ヘッダーが取得できること
                servers_with_auth = await get_external_servers_with_auth("tenant_auth")
                target = next(s for s in servers_with_auth if s["url"] == "https://secure.example.com")
                assert target["headers"] == {"Authorization": "Bearer jwt-secret-abc"}
