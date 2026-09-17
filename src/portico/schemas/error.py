from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BaseResponseSchema(BaseModel):
    """全レスポンスモデル共通の基底クラス ($schema プロパティ対応)"""

    model_config = ConfigDict(populate_by_name=True)

    schema_: str | None = Field(
        default=None,
        alias="$schema",
        description="A URL to the JSON Schema for this object.",
        examples=["https://example.com/schemas/ResponseModel.json"],
    )


class ErrorResponse(BaseResponseSchema):
    """共通エラーレスポンスモデル"""

    detail: str = Field(..., description="エラーメッセージまたは詳細情報")


class ValidationErrorDetail(BaseModel):
    """バリデーションエラー詳細"""

    loc: list[str | int] = Field(..., description="エラー発生箇所のパス")
    msg: str = Field(..., description="エラー内容メッセージ")
    type: str = Field(..., description="バリデーションエラー種別")


class HTTPValidationError(BaseResponseSchema):
    """HTTP 422 バリデーションエラーモデル"""

    detail: list[ValidationErrorDetail] = Field(..., description="バリデーションエラー詳細リスト")
