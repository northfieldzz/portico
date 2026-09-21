"""
MCP Gateway — 依存性注入 (DI) モジュール
"""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, Query, status

from portico.core.config import DEFAULT_TENANT_ID, ENFORCE_TOLLGATE_AUTH, INTERNAL_SERVICE_SECRET
from portico.schemas.context import RequestContext


def get_request_context(
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    x_key_id: str | None = Header(None, alias="X-Key-ID"),
    x_key_prefix: str | None = Header(None, alias="X-Key-Prefix"),
    x_service_id: str | None = Header(None, alias="X-Service-ID"),
    tenant_id: str | None = Query(None),
) -> RequestContext:
    """
    Tollgate プロキシヘッダーまたは直接クエリからリクエストコンテキストを解決する。
    ENFORCE_TOLLGATE_AUTH が有効な場合は必須ヘッダー (X-Tenant-ID, X-Key-ID) を検証する。
    """
    if ENFORCE_TOLLGATE_AUTH and (not x_tenant_id or not x_key_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tollgate authentication required: Missing X-Tenant-ID or X-Key-ID header",
        )

    resolved_tenant = (x_tenant_id or tenant_id or DEFAULT_TENANT_ID).strip()
    is_proxied = bool(x_tenant_id and x_key_id)

    return RequestContext(
        tenant_id=resolved_tenant,
        key_id=x_key_id,
        key_prefix=x_key_prefix,
        service_id=x_service_id,
        is_proxied=is_proxied,
    )


def get_tenant_id(
    ctx: RequestContext = Depends(get_request_context),
) -> str:
    """リクエストコンテキストからテナントIDを解決する（後方互換性用）。"""
    return ctx.tenant_id


def require_internal_secret(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
) -> str:
    """内部サービス間専用エンドポイントの共有シークレットを検証する。"""
    # Use secrets.compare_digest to prevent timing attacks
    if not x_internal_secret or not secrets.compare_digest(x_internal_secret, INTERNAL_SERVICE_SECRET):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Invalid or missing internal service secret",
        )
    return x_internal_secret


def get_scopes(
    x_scopes: str | None = Header(None, alias="X-Scopes"),
    x_scope: str | None = Header(None, alias="X-Scope"),
) -> list[str] | None:
    """
    リクエストヘッダーからクライアントの認可スコープ一覧を取得する。
    カンマ区切りまたはスペース区切りに対応。
    ヘッダーが存在しない場合は None を返す (未制限モード)。
    """
    raw = x_scopes or x_scope
    if raw is None:
        return None
    return [t.strip() for t in raw.replace(",", " ").split() if t.strip()]
