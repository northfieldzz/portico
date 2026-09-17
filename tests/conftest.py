"""
Pytest configuration and shared fixtures for mcp_gateway tests.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Ensure mcp_gateway/src is in sys.path
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from mcp_gateway.db.session import get_memory_external_servers
from mcp_gateway.main import app


@pytest.fixture(autouse=True)
def reset_memory_db():
    """各テスト実行前にインメモリ外部サーバーディクショナリを初期化する。"""
    mem = get_memory_external_servers()
    mem.clear()
    yield
    mem.clear()


@pytest.fixture(autouse=True)
def mock_db_pool_none():
    """DB接続プールをモックし、テスト中はインメモリフォールバックモードで動作させる。"""
    with (
        patch("mcp_gateway.db.session.get_db_pool", new_callable=AsyncMock, return_value=None),
        patch("mcp_gateway.services.server_service.get_db_pool", new_callable=AsyncMock, return_value=None),
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI 同期テストクライアント。"""
    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient]:
    """FastAPI 非同期テストクライアント。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
