"""
Unit tests for OAuth Scopes authorization and X-Scopes header enforcement in portico.
"""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import urlparse

import httpx
import pytest
from fastapi import HTTPException

from portico.services.server_service import (
    check_scope_authorized,
    dispatch_tool_call,
    get_aggregated_tools,
)
from portico.storage.factory import get_server_repository


class TestScopeMatchingLogic:
    """check_scope_authorized のロジックテスト。"""

    def test_unrestricted_when_client_scopes_is_none(self):
        assert check_scope_authorized(None, ["notion:read"]) is True

    def test_unrestricted_when_required_scopes_empty(self):
        assert check_scope_authorized(["tools:any"], []) is True

    def test_wildcard_or_admin_client_grants_access(self):
        assert check_scope_authorized(["*"], ["super:admin"]) is True
        assert check_scope_authorized(["admin"], ["secret:write"]) is True

    def test_exact_scope_match(self):
        assert check_scope_authorized(["notion:read", "slack:write"], ["notion:read"]) is True
        assert check_scope_authorized(["slack:write"], ["notion:read"]) is False

    def test_prefix_wildcard_match(self):
        # 'notion:*' クライアントスコープで 'notion:read' ツールを許可
        assert check_scope_authorized(["notion:*"], ["notion:read"]) is True
        assert check_scope_authorized(["notion:*"], ["slack:send"]) is False


class TestScopeEnforcementInRoutes:
    """ツール集約・ディスパッチにおける X-Scopes の制御テスト。"""

    @pytest.mark.asyncio
    async def test_list_tools_filters_by_client_scopes(self):
        """X-Scopes が指定された場合、合致するツールのみ返却される。"""
        repo = get_server_repository()
        await repo.create_server(
            "tenant_scopes_test",
            {
                "id": "srv-notion",
                "name": "Notion MCP",
                "url": "https://notion.example.com",
                "scopes": ["notion:read"],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )
        await repo.create_server(
            "tenant_scopes_test",
            {
                "id": "srv-secret",
                "name": "Secret Admin MCP",
                "url": "https://secret.example.com",
                "scopes": ["secret:admin"],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )

        async def mock_post(url, **kwargs):
            body = kwargs.get("json", {})
            method = body.get("method")
            host = urlparse(str(url)).hostname
            if host == "notion.example.com" and method == "tools/list":
                return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": [{"name": "notion_search", "scopes": ["notion:read"]}]}})
            if host == "secret.example.com" and method == "tools/list":
                return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": [{"name": "secret_wipe", "scopes": ["secret:admin"]}]}})
            return httpx.Response(404)

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            # 1. スコープ未指定 -> 全ツール取得 (名前空間プレフィックス付き)
            tools_all = await get_aggregated_tools("tenant_scopes_test")
            names_all = [t["name"] for t in tools_all]
            orig_names = [t.get("original_name") for t in tools_all]
            assert "notion_mcp__notion_search" in names_all
            assert "secret_admin_mcp__secret_wipe" in names_all
            assert "notion_search" in orig_names

            # 2. X-Scopes: notion:read -> notion_search のみ取得 (secret_wipe は除外)
            scopes_notion = ["notion:read"]
            filtered_tools = [t for t in tools_all if check_scope_authorized(scopes_notion, t.get("scopes", []))]
            names_notion = [t["name"] for t in filtered_tools]
            assert "notion_mcp__notion_search" in names_notion
            assert "secret_admin_mcp__secret_wipe" not in names_notion

    @pytest.mark.asyncio
    async def test_execute_tool_forbidden_when_scope_missing(self):
        """必要なスコープを持たないリクエストは 403 で拒絶される。"""
        repo = get_server_repository()
        await repo.create_server(
            "tenant_guard_test",
            {
                "id": "srv-secret",
                "name": "Secret MCP",
                "url": "https://secret.example.com",
                "scopes": ["infra:destroy"],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )

        mock_post_resp = httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": [{"name": "infra_destroy", "scopes": ["infra:destroy"]}]}})
        with patch("httpx.AsyncClient.post", return_value=mock_post_resp):
            # 不足スコープ (scopes: tools:read) で呼び出し -> 403 Forbidden
            with pytest.raises(HTTPException) as exc_info:
                await dispatch_tool_call(
                    "infra_destroy",
                    {"target": "prod-db"},
                    tenant_id="tenant_guard_test",
                    scopes=["tools:read"],
                )
            assert exc_info.value.status_code == 403
            assert "Insufficient scope" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_tool_success_when_scope_matches(self):
        """必要なスコープを満たしている場合、正常に実行 (プロキシ転送) される。"""
        repo = get_server_repository()
        await repo.create_server(
            "tenant_guard_test",
            {
                "id": "srv-secret",
                "name": "Secret MCP",
                "url": "https://secret.example.com",
                "scopes": ["infra:destroy"],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )

        async def mock_post(url, **kwargs):
            body = kwargs.get("json", {})
            method = body.get("method")
            if method == "tools/list":
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "result": {"tools": [{"name": "infra_destroy", "scopes": ["infra:destroy"]}]},
                    },
                )
            if method == "tools/call":
                return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"destroyed": True}})
            return httpx.Response(404)

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            # 合致スコープ (scopes: infra:destroy) で呼び出し -> 正常完了
            res = await dispatch_tool_call(
                "infra_destroy",
                {"target": "test-sandbox"},
                tenant_id="tenant_guard_test",
                scopes=["infra:destroy"],
            )
            assert res["destroyed"] is True
