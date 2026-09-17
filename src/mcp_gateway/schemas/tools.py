"""
MCP Gateway — ツール関連 Pydantic スキーマ定義
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ToolDefinition(BaseModel):
    name: str = Field(..., description="ツール名 (例: core_id_create_user)")
    app: str | None = Field(default=None, description="所属サービスまたはアプリ名 (例: Core-ID)")
    description: str = Field(default="", description="ツールの機能概要")
    parameters: dict[str, Any] = Field(default_factory=dict, description="ツールの引数スキーマ (JSON Schema)")
    params_schema: dict[str, Any] = Field(default_factory=dict, description="パラメータスキーマエイリアス")
    server_id: str | None = Field(default=None, description="提供元の外部 MCP サーバー ID")
    server_name: str | None = Field(default=None, description="提供元の外部 MCP サーバー表示名")
    original_name: str | None = Field(default=None, description="名前空間付与前の元のツール名")
    scopes: list[str] = Field(default_factory=list, description="実行に必要なスコープ一覧")
    is_builtin: bool = Field(default=True, description="ビルトインツールかどうか")

    @model_validator(mode="before")
    @classmethod
    def sync_parameters_and_schema(cls, data: Any) -> Any:
        if isinstance(data, dict):
            params = data.get("parameters") or data.get("params_schema") or {}
            data["parameters"] = params
            data["params_schema"] = params
        return data


class ToolExecutionResponse(BaseModel):
    tool: str = Field(..., description="実行されたツール名")
    result: Any = Field(..., description="ツール実行結果ペイロード")
