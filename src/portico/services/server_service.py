"""
MCP Gateway — 外部 MCP サーバー管理 & ツール集約サービス
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException
from fastapi import status as http_status

from portico.cache.factory import get_cache_service
from portico.core.config import (
    ALLOW_LOCAL_MCP_SERVERS,
    ENVIRONMENT,
    EXTERNAL_MCP_TIMEOUT_SECONDS,
    MAX_SERVERS_PER_TENANT,
    MOCK_EXTERNAL_APIS,
    TOOL_CACHE_TTL_SECONDS,
)
from portico.schemas.context import RequestContext
from portico.schemas.server import ServerCreateRequest
from portico.services.audit import log_tool_execution
from portico.services.crypto import (
    build_auth_headers,
    decrypt_auth_config,
    encrypt_auth_config,
)
from portico.services.url_validator import validate_mcp_url
from portico.storage.factory import get_server_repository

logger = logging.getLogger(__name__)


async def invalidate_tool_cache(tenant_id: str | None = None) -> None:
    """ツール・サーバー定義キャッシュを無効化する。tenant_id 未指定時は全パージ。"""
    cache = get_cache_service()
    if tenant_id:
        await cache.delete(f"tools:{tenant_id}")
        await cache.delete(f"servers:{tenant_id}")
    else:
        await cache.clear()


def to_server_slug(name: str) -> str:
    """サーバー名から名前空間用スラッグ (英数字とアンダースコア) を生成する。"""
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()).strip("_")
    return slug or "ext"


def _parse_scopes(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [str(x) for x in parsed] if isinstance(parsed, list) else []
        except Exception:
            return [s.strip() for s in raw.split(",") if s.strip()]
    return []


async def list_servers_for_tenant(tenant_id: str) -> list[dict[str, Any]]:
    """
    テナントの MCP サーバー一覧 (外部登録) を取得する (二段キャッシュ対応)。
    """
    cache = get_cache_service()
    cache_key = f"servers:{tenant_id}"
    cached = await cache.get(cache_key)
    if cached is not None and isinstance(cached, list):
        return cached

    repo = get_server_repository()
    raw_servers = await repo.list_servers(tenant_id)
    servers = []
    for r in raw_servers:
        atype = r.get("auth_type", "none")
        has_a = bool(r.get("encrypted_auth_config")) or atype != "none"
        created_val = r.get("created_at")
        updated_val = r.get("updated_at")
        servers.append(
            {
                "id": r["id"],
                "tenant_id": r["tenant_id"],
                "name": r["name"],
                "url": r["url"],
                "status": r.get("status", "active"),
                "auth_type": atype,
                "has_auth": has_a,
                "scopes": _parse_scopes(r.get("scopes")),
                "is_builtin": False,
                "created_at": created_val.isoformat() if hasattr(created_val, "isoformat") else str(created_val) if created_val else None,
                "updated_at": updated_val.isoformat() if hasattr(updated_val, "isoformat") else str(updated_val) if updated_val else None,
            }
        )

    await cache.set(cache_key, servers)
    return servers


async def delete_all_servers_for_tenant(tenant_id: str) -> int:
    """
    テナント削除時に呼び出され、該当テナントの全外部 MCP サーバーを完全消去する。
    """
    repo = get_server_repository()
    servers = await repo.list_servers(tenant_id)
    deleted_count = 0
    for s in servers:
        if await repo.delete_server(tenant_id, s["id"]):
            deleted_count += 1

    await invalidate_tool_cache(tenant_id)
    return deleted_count


async def add_external_server(data: ServerCreateRequest, tenant_id: str) -> dict[str, Any]:
    """
    外部 MCP サーバーを登録する。
    インフラ保護のため、テナントあたりの最大登録数 (MAX_SERVERS_PER_TENANT) を検証する。
    """
    if MAX_SERVERS_PER_TENANT > 0:
        current_servers = await list_servers_for_tenant(tenant_id)
        ext_count = sum(1 for s in current_servers if not s.get("is_builtin"))
        if ext_count >= MAX_SERVERS_PER_TENANT:
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Tenant infrastructure limit reached ({ext_count}/{MAX_SERVERS_PER_TENANT} servers). Cannot register more MCP servers.",
            )

    server_id = f"ext-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    # 認証ヘッダー構築
    auth_headers = build_auth_headers(
        auth_type=data.auth_type,
        auth_token=data.auth_token,
        auth_header_name=data.auth_header_name,
        custom_headers=data.custom_headers,
    )
    has_auth = bool(auth_headers) or data.auth_type != "none"
    encrypted_auth = (
        encrypt_auth_config(
            {
                "auth_type": data.auth_type,
                "headers": auth_headers,
            }
        )
        if has_auth
        else None
    )

    # 接続確認テスト (MCP JSON-RPC 2.0 tools/list によるプローブ)
    normalized_url = data.url.rstrip("/")
    try:
        validate_mcp_url(normalized_url, allow_local=ALLOW_LOCAL_MCP_SERVERS)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid MCP server URL: {exc}",
        ) from exc

    probe_ok = False
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            rpc_req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            resp = await client.post(normalized_url, headers=auth_headers, json=rpc_req)
            if resp.status_code in (200, 401, 403):
                # 200: 疎通＆プロトコル正常
                # 401/403: サーバー存在＆プロトコル受付 (認証情報設定待ち)
                probe_ok = True
        except Exception:
            probe_ok = False

    status = "active" if probe_ok else "connected"

    server_data = {
        "id": server_id,
        "tenant_id": tenant_id,
        "name": data.name,
        "url": data.url,
        "status": status,
        "auth_type": data.auth_type,
        "encrypted_auth_config": encrypted_auth,
        "scopes": data.scopes,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    repo = get_server_repository()
    saved = await repo.create_server(tenant_id, server_data)

    await invalidate_tool_cache(tenant_id)
    return {
        "id": saved["id"],
        "tenant_id": tenant_id,
        "name": saved["name"],
        "url": saved["url"],
        "status": saved["status"],
        "auth_type": saved["auth_type"],
        "has_auth": has_auth,
        "scopes": _parse_scopes(saved.get("scopes")),
        "is_builtin": False,
        "created_at": saved.get("created_at"),
    }


async def remove_external_server(server_id: str, tenant_id: str) -> bool:
    """
    外部 MCP サーバーを削除する。
    """
    repo = get_server_repository()
    deleted = await repo.delete_server(tenant_id, server_id)
    if deleted:
        await invalidate_tool_cache(tenant_id)
    return deleted


async def get_external_servers_with_auth(tenant_id: str) -> list[dict[str, Any]]:
    """
    テナントの全外部 MCP サーバーの URL と復号された認証ヘッダー、スコープ、識別情報のリストを取得する。
    """
    repo = get_server_repository()
    raw_servers = await repo.list_servers(tenant_id)
    results = []
    for r in raw_servers:
        auth_cfg = decrypt_auth_config(r.get("encrypted_auth_config"))
        headers = auth_cfg.get("headers", {})
        s_name = r.get("name") or "External"
        results.append(
            {
                "id": r["id"],
                "url": r["url"],
                "headers": headers,
                "name": s_name,
                "slug": to_server_slug(s_name),
                "scopes": _parse_scopes(r.get("scopes")),
            }
        )
    return results


async def get_aggregated_tools(tenant_id: str, force_refresh: bool = False) -> list[dict[str, Any]]:
    """
    外部 MCP サーバーからクロールした全ツールを統合して返却する。
    二段キャッシュ (L1: Memory + L2: Valkey) を活用してマイクロ秒応答。
    """
    cache = get_cache_service()
    cache_key = f"tools:{tenant_id}"
    if not force_refresh:
        cached = await cache.get(cache_key)
        if cached is not None and isinstance(cached, list):
            return cached

    servers = await get_external_servers_with_auth(tenant_id)
    if not servers:
        await cache.set(cache_key, [], ttl=TOOL_CACHE_TTL_SECONDS)
        return []

    async def _fetch_from_single_server(s: dict[str, Any], client: httpx.AsyncClient) -> list[dict[str, Any]]:
        normalized = s["url"].rstrip("/")
        headers = s["headers"]
        server_scopes = s.get("scopes", [])
        server_id = s.get("id")
        server_name = s.get("name", "External")
        server_slug = s.get("slug") or to_server_slug(server_name)

        # 実行時動的 SSRF / DNS Rebinding 再検証
        try:
            validate_mcp_url(normalized, allow_local=ALLOW_LOCAL_MCP_SERVERS)
        except Exception as exc:
            if (MOCK_EXTERNAL_APIS or ENVIRONMENT != "production") and "Could not resolve hostname" in str(exc):
                logger.debug("DNS resolution bypassed for %s in dev/mock mode: %s", normalized, exc)
            else:
                logger.warning("SSRF / DNS Rebinding check blocked request to %s (%s): %s", server_name, normalized, exc)
                return []

        # MCP 公式仕様 (JSON-RPC 2.0 / Streamable HTTP POST tools/list) でツール一覧を取得
        try:
            rpc_req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            rpc_resp = await client.post(normalized, headers=headers, json=rpc_req)
            if rpc_resp.status_code == 200:
                rdata = rpc_resp.json()
                tools_list = []
                if isinstance(rdata, dict):
                    if "result" in rdata and isinstance(rdata["result"], dict):
                        tools_list = rdata["result"].get("tools", [])
                    elif "tools" in rdata:
                        tools_list = rdata["tools"]
                server_tools = []
                for item in tools_list:
                    if isinstance(item, dict) and "name" in item:
                        orig_name = item["name"]
                        namespaced_name = f"{server_slug}__{orig_name}"
                        item["original_name"] = orig_name
                        item["name"] = namespaced_name
                        item["server_id"] = server_id
                        item["server_name"] = server_name
                        item["is_builtin"] = False
                        item.setdefault("app", server_name)
                        item.setdefault("scopes", server_scopes)
                        server_tools.append(item)
                return server_tools
        except Exception as exc:
            logger.warning("Failed to fetch tools via MCP JSON-RPC from %s (%s): %s", server_name, normalized, exc)
        return []

    async with httpx.AsyncClient(timeout=EXTERNAL_MCP_TIMEOUT_SECONDS) as client:
        tasks = [_fetch_from_single_server(s, client) for s in servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_tools: list[dict[str, Any]] = []
    for res in results:
        if isinstance(res, list):
            all_tools.extend(res)

    await cache.set(cache_key, all_tools, ttl=TOOL_CACHE_TTL_SECONDS)
    return all_tools


def check_scope_authorized(client_scopes: list[str] | None, required_scopes: list[str]) -> bool:
    """
    クライアントのスコープが必要スコープを満たしているか判定する。
    """
    if client_scopes is None:
        return True
    if not required_scopes:
        return True
    if "*" in client_scopes or "admin" in client_scopes:
        return True

    for req in required_scopes:
        if req in client_scopes:
            return True
        prefix = req.split(":")[0] + ":*" if ":" in req else None
        if prefix and prefix in client_scopes:
            return True
    return False


async def dispatch_tool_call(
    tool_name: str,
    params: dict[str, Any],
    tenant_id: str,
    scopes: list[str] | None = None,
    context: RequestContext | None = None,
) -> Any:
    """
    ツール呼び出しのディスパッチ（ローカル実行または外部 MCP サーバーへのプロキシ）。
    FastMCP SSE ハンドラーおよび REST API の共通実行コア。
    監査ログ (log_tool_execution) を自動記録する。
    """
    start_time = time.perf_counter()
    success = False
    err_detail = None

    try:
        aggregated = await get_aggregated_tools(tenant_id)
        target_tool = next(
            (t for t in aggregated if t.get("name") == tool_name or t.get("original_name") == tool_name),
            None,
        )
        required_scopes = target_tool.get("scopes", []) if target_tool else []

        if not check_scope_authorized(scopes, required_scopes):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: Insufficient scope for tool '{tool_name}'. Required: {required_scopes}, Provided: {scopes or []}",
            )

        # 外部 MCP サーバーへの転送を試行 (認証ヘッダー & スコープ付きプロキシ)
        servers = await get_external_servers_with_auth(tenant_id)

        target_server = None
        exec_tool_name = tool_name
        if "__" in tool_name:
            prefix, _, orig = tool_name.partition("__")
            for s in servers:
                if s.get("slug") == prefix or s.get("id") == prefix or to_server_slug(s.get("name", "")) == prefix:
                    target_server = s
                    exec_tool_name = orig
                    break

        async with httpx.AsyncClient(timeout=max(EXTERNAL_MCP_TIMEOUT_SECONDS, 10.0)) as client:
            # 2-A. 名前空間付きツール名の場合、対象サーバーにピンポイント送信
            if target_server:
                srv_scopes = target_server.get("scopes", [])
                if not check_scope_authorized(scopes, srv_scopes):
                    raise HTTPException(
                        status_code=http_status.HTTP_403_FORBIDDEN,
                        detail=f"Access forbidden: Insufficient scope for server '{target_server.get('name')}'. Required: {srv_scopes}",
                    )

                # 実行時動的 SSRF / DNS Rebinding 再検証
                target_url = target_server["url"].rstrip("/")
                try:
                    validate_mcp_url(target_url, allow_local=ALLOW_LOCAL_MCP_SERVERS)
                except Exception as exc:
                    if (MOCK_EXTERNAL_APIS or ENVIRONMENT != "production") and "Could not resolve hostname" in str(exc):
                        logger.debug("DNS resolution bypassed for %s in dev/mock mode: %s", target_url, exc)
                    else:
                        raise HTTPException(
                            status_code=http_status.HTTP_403_FORBIDDEN,
                            detail=f"Target MCP URL blocked by runtime SSRF validation: {exc}",
                        ) from exc

                headers = target_server.get("headers", {})
                try:
                    rpc_body = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": exec_tool_name, "arguments": params},
                    }
                    resp = await client.post(target_url, headers=headers, json=rpc_body)
                    if resp.status_code == 200:
                        payload = resp.json()
                        if isinstance(payload, dict):
                            if "error" in payload:
                                raise HTTPException(
                                    status_code=http_status.HTTP_502_BAD_GATEWAY,
                                    detail=f"External MCP server returned error: {payload['error']}",
                                )
                            if "result" in payload:
                                success = True
                                return payload["result"]
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.warning("Failed MCP JSON-RPC call to %s: %s", target_server.get("name"), exc)
                    raise HTTPException(
                        status_code=http_status.HTTP_502_BAD_GATEWAY,
                        detail=f"Failed to communicate with external MCP server '{target_server.get('name')}': {exc}",
                    ) from exc

            # 2-B. 汎用フォールバック
            for s in servers:
                srv_scopes = s.get("scopes", [])
                if not check_scope_authorized(scopes, srv_scopes):
                    continue

                fallback_url = s["url"].rstrip("/")
                try:
                    validate_mcp_url(fallback_url, allow_local=ALLOW_LOCAL_MCP_SERVERS)
                except Exception as exc:
                    if (MOCK_EXTERNAL_APIS or ENVIRONMENT != "production") and "Could not resolve hostname" in str(exc):
                        pass
                    else:
                        continue

                headers = s.get("headers", {})
                try:
                    rpc_body = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": exec_tool_name, "arguments": params},
                    }
                    resp = await client.post(fallback_url, headers=headers, json=rpc_body)
                    if resp.status_code == 200:
                        payload = resp.json()
                        if isinstance(payload, dict) and "result" in payload and "error" not in payload:
                            success = True
                            return payload["result"]
                except Exception:
                    continue

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Unknown tool: '{tool_name}'. No matching registered tool or external MCP server found.",
        )
    except HTTPException as exc:
        err_detail = str(exc.detail)
        raise
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        ctx = context or RequestContext(tenant_id=tenant_id)
        log_tool_execution(
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=success,
            context=ctx,
            error_message=err_detail,
        )
