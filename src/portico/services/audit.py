"""
Portico — 監査ログ (Audit Logging) モジュール
ツール実行や外部プロキシ呼び出しの認証コンテキスト (Tollgate) および実行結果を構造化ログとして記録する。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from portico.schemas.context import RequestContext

audit_logger = logging.getLogger("portico.audit")


def log_tool_execution(
    tool_name: str,
    duration_ms: float,
    success: bool,
    context: RequestContext | None = None,
    error_message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    ツール実行イベントの構造化監査ログを出力する。
    """
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": "tool_execution",
        "tool_name": tool_name,
        "duration_ms": round(duration_ms, 2),
        "success": success,
        "tenant_id": context.tenant_id if context else "unknown",
        "key_id": context.key_id if context else None,
        "key_prefix": context.key_prefix if context else None,
        "service_id": context.service_id if context else None,
        "is_proxied": context.is_proxied if context else False,
        "error": error_message,
    }
    if extra:
        record["extra"] = extra

    # 構造化ログを AUDIT プレフィックス付きで出力
    audit_logger.info("AUDIT_EVENT: %s", json.dumps(record, ensure_ascii=False))
    return record
