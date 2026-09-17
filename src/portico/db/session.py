"""
MCP Gateway — データベース接続 & mcp スキーマ自己初期化
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from portico.core.config import POSTGRES_URL

logger = logging.getLogger(__name__)

_pg_pool: asyncpg.Pool | None = None
_memory_external_servers: dict[str, dict[str, Any]] = {}


async def init_mcp_db() -> asyncpg.Pool | None:
    """
    MCP Gateway 自身のスキーマ 'mcp' および 'mcp.external_servers' テーブルを自己初期化する。
    """
    global _pg_pool
    try:
        _pg_pool = await asyncpg.create_pool(POSTGRES_URL, min_size=1, max_size=5, timeout=3.0)
        async with _pg_pool.acquire() as conn:
            await conn.execute("""
                CREATE SCHEMA IF NOT EXISTS mcp;

                CREATE TABLE IF NOT EXISTS mcp.external_servers (
                    id VARCHAR PRIMARY KEY,
                    tenant_id VARCHAR NOT NULL,
                    name VARCHAR NOT NULL,
                    url VARCHAR NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'active',
                    last_synced_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_external_servers_tenant_url ON mcp.external_servers (tenant_id, url);

                ALTER TABLE mcp.external_servers ADD COLUMN IF NOT EXISTS auth_type VARCHAR NOT NULL DEFAULT 'none';
                ALTER TABLE mcp.external_servers ADD COLUMN IF NOT EXISTS encrypted_auth_config TEXT;
                ALTER TABLE mcp.external_servers ADD COLUMN IF NOT EXISTS scopes JSONB DEFAULT '[]'::jsonb;

                ALTER TABLE mcp.external_servers ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS mcp_external_servers_tenant_isolation ON mcp.external_servers;
                CREATE POLICY mcp_external_servers_tenant_isolation ON mcp.external_servers
                  FOR ALL
                  USING (
                    tenant_id = current_setting('app.current_tenant_id', true)
                    OR current_setting('app.current_tenant_id', true) IS NULL
                    OR current_setting('app.current_tenant_id', true) = ''
                  );
            """)
        logger.info("🔌 MCP Gateway initialized 'mcp' schema and tables successfully.")
        return _pg_pool
    except Exception as exc:
        logger.warning("⚠️ MCP Gateway database initialization fallback to memory: %s", exc)
        _pg_pool = None
        return None


async def get_db_pool() -> asyncpg.Pool | None:
    global _pg_pool
    if _pg_pool is None:
        await init_mcp_db()
    return _pg_pool


async def close_db_pool() -> None:
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None


def get_memory_external_servers() -> dict[str, dict[str, Any]]:
    return _memory_external_servers
