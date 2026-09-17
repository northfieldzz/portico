"""
MCP Gateway — Pydantic スキーマ定義
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from portico.core.config import ALLOW_LOCAL_MCP_SERVERS
from portico.services.url_validator import SSRFValidationError, validate_mcp_url


class AuthType(StrEnum):
    NONE = "none"
    BEARER = "bearer"
    API_KEY = "api_key"
    CUSTOM = "custom"


class ServerCreateRequest(BaseModel):
    name: str = Field(..., description="外部 MCP サーバー名 (例: Notion MCP)")
    url: str = Field(..., description="外部 MCP サーバーのエンドポイント URL")
    auth_type: AuthType = Field(AuthType.NONE, description="認証方式 (none, bearer, api_key, custom)")
    auth_token: str | None = Field(None, description="APIキーまたはBearerトークン (保存時にAES-256暗号化)")
    auth_header_name: str | None = Field(None, description="APIキー用のヘッダー名 (デフォルト: X-API-Key)")
    custom_headers: dict[str, str] = Field(default_factory=dict, description="追加のHTTPヘッダー")
    scopes: list[str] = Field(default_factory=list, description="実行に必要なスコープ一覧 (例: ['tools:read', 'tools:write'])")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        try:
            validate_mcp_url(str(v), allow_local=ALLOW_LOCAL_MCP_SERVERS)
        except SSRFValidationError as exc:
            raise ValueError(f"SSRF validation failed: {exc}") from exc
        return str(v)


class ServerResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    url: str
    status: str
    auth_type: str = "none"
    has_auth: bool = False
    scopes: list[str] = Field(default_factory=list)
    is_builtin: bool = False
    tools_count: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ServerDeleteResponse(BaseModel):
    status: str = Field("success", description="処理結果ステータス")
    message: str = Field(..., description="メッセージ")
    id: str = Field(..., description="削除されたサーバーID")


class TenantCleanupResponse(BaseModel):
    status: str = Field("success", description="処理結果ステータス")
    tenant_id: str = Field(..., description="対象テナントID")
    deleted_count: int = Field(..., description="削除された外部サーバー件数")


class ToolCallRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
