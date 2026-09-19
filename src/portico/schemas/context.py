"""
Portico — リクエストおよび認証コンテキストスキーマ
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RequestContext(BaseModel):
    """
    リクエスト全体の実行コンテキスト。
    Tollgate プロキシ経由のリクエスト情報、またはスタンドアロン直接呼び出し時のコンテキストを保持する。
    """

    tenant_id: str = Field(description="対象テナントID")
    key_id: str | None = Field(default=None, description="Tollgate APIキーの一意ID (X-Key-ID)")
    key_prefix: str | None = Field(default=None, description="Tollgate APIキーのプレフィックス (X-Key-Prefix)")
    service_id: str | None = Field(default=None, description="Tollgate サービスID (X-Service-ID)")
    is_proxied: bool = Field(default=False, description="Tollgate 等のリバースプロキシ経由で認証されたかどうか")
