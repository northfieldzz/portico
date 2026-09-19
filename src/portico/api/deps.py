"""
MCP Gateway — 依存性注入 (DI) モジュール
"""

from __future__ import annotations

import secrets
from fastapi import Header, HTTPException, Query, status

from portico.core.config import INTERNAL_SERVICE_SECRET


def get_tenant_id(
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    tenant_id: str | None = Query(None),
) -> str:
    """ヘッダーまたはクエリパラメータからテナントIDを解決する。"""
    tid = x_tenant_id or tenant_id or "tenant_default"
    return tid.strip()


def require_internal_secret(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
) -> str:
    """内部サービス間専用エンドポイントの共有シークレットを検証する。"""
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
