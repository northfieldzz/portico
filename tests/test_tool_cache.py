"""
外部 MCP サーバーのツール並列フェッチおよび TTL キャッシュ動作テスト
"""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import urlparse

import httpx
import pytest

from portico.schemas.server import ServerCreateRequest
from portico.services.server_service import (
    add_external_server,
    get_aggregated_tools,
    invalidate_tool_cache,
)
from portico.storage.factory import get_server_repository


@pytest.mark.asyncio
async def test_tool_cache_hit_avoids_repeated_http_calls():
    """1回目の取得後はキャッシュから返却され、外部通信が繰り返されないこと"""
    await invalidate_tool_cache()
    repo = get_server_repository()
    await repo.create_server(
        "tenant_cache_test",
        {
            "id": "srv-cache-test",
            "name": "Cache MCP",
            "url": "https://cache.example.com",
            "scopes": [],
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    mock_resp = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "result": {"tools": [{"name": "fast_calc", "parameters": {}}]}},
    )

    with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
        # 1回目: キャッシュミス -> HTTP リクエスト発生
        tools1 = await get_aggregated_tools("tenant_cache_test")
        assert len(tools1) == 1
        assert tools1[0]["name"] == "cache_mcp__fast_calc"
        assert mock_post.call_count == 1

        # 2回目: キャッシュヒット -> HTTP リクエストは追加されない
        tools2 = await get_aggregated_tools("tenant_cache_test")
        assert len(tools2) == 1
        assert mock_post.call_count == 1  # 呼び出し回数は 1 のまま！


@pytest.mark.asyncio
async def test_tool_cache_invalidated_on_server_mutation():
    """サーバーの登録または削除時にキャッシュが自動パージされること"""
    await invalidate_tool_cache()
    tenant = "tenant_mutation_test"
    repo = get_server_repository()
    await repo.create_server(
        tenant,
        {
            "id": "srv-m1",
            "name": "M1",
            "url": "https://m1.example.com",
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    mock_resp = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "result": {"tools": [{"name": "tool_1"}]}},
    )

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        tools = await get_aggregated_tools(tenant)
        assert len(tools) == 1

    # 新しいサーバーを登録 -> キャッシュが無効化されるはず
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            await add_external_server(
                ServerCreateRequest(name="M2", url="https://m2.example.com"),
                tenant_id=tenant,
            )

    # 再度取得した際、キャッシュミスとなって最新情報（2台分）が取得されること
    mock_resp2 = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "result": {"tools": [{"name": "tool_x"}]}},
    )
    with patch("httpx.AsyncClient.post", return_value=mock_resp2):
        tools_updated = await get_aggregated_tools(tenant)
        assert len(tools_updated) == 2


@pytest.mark.asyncio
async def test_parallel_tool_fetch_resilience():
    """1台の外部サーバーがエラーになっても、他のサーバーのツール取得が成功すること"""
    await invalidate_tool_cache()
    tenant = "tenant_resilience_test"
    repo = get_server_repository()
    await repo.create_server(
        tenant,
        {
            "id": "srv-ok",
            "name": "OK Server",
            "url": "https://ok.example.com",
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    await repo.create_server(
        tenant,
        {
            "id": "srv-ng",
            "name": "NG Server",
            "url": "https://ng.example.com",
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    async def mock_post(url, **kwargs):
        hostname = urlparse(str(url)).hostname
        if hostname == "ok.example.com":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"tools": [{"name": "ok_tool"}]}})
        raise httpx.ConnectTimeout("Connection timeout to NG server")

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        tools = await get_aggregated_tools(tenant)
        assert len(tools) == 1
        assert tools[0]["original_name"] == "ok_tool"
