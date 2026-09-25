"""
ストレージリポジトリ (SQLite, Memory) および 二段キャッシュ (L1/L2) の動作検証テスト
"""

from __future__ import annotations

import pytest

from portico.cache.memory_cache import MemoryCache
from portico.cache.two_tier_cache import TwoTierCache
from portico.storage.sqlite import SQLiteServerRepository


@pytest.mark.asyncio
async def test_sqlite_repository_crud(tmp_path):
    """SQLite ストレージでの CRUD 操作が正常に行えること"""
    db_file = str(tmp_path / "test_portico.db")
    repo = SQLiteServerRepository(db_path=db_file)
    await repo.init_storage()

    tenant_id = "tenant_test_sql"
    server_data = {
        "id": "srv-1",
        "name": "SQLite Server",
        "url": "https://sqlite.example.com",
        "status": "active",
        "auth_type": "bearer",
        "encrypted_auth_config": "enc-123",
        "scopes": ["read", "write"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    # 1. Create
    created = await repo.create_server(tenant_id, server_data)
    assert created["id"] == "srv-1"
    assert created["tenant_id"] == tenant_id
    assert created["scopes"] == ["read", "write"]

    # 2. Get
    fetched = await repo.get_server(tenant_id, "srv-1")
    assert fetched is not None
    assert fetched["name"] == "SQLite Server"
    assert fetched["auth_type"] == "bearer"

    # 3. List
    servers = await repo.list_servers(tenant_id)
    assert len(servers) == 1
    assert servers[0]["url"] == "https://sqlite.example.com"

    # 4. Update
    updated = await repo.update_server(tenant_id, "srv-1", {"name": "Updated Name", "scopes": ["admin"]})
    assert updated["name"] == "Updated Name"
    assert updated["scopes"] == ["admin"]

    # 5. Delete
    deleted = await repo.delete_server(tenant_id, "srv-1")
    assert deleted is True
    assert await repo.get_server(tenant_id, "srv-1") is None

    await repo.close()


@pytest.mark.asyncio
async def test_memory_cache_l1_behavior():
    """L1 メモリキャッシュの set/get/delete/prefix/clear が機能すること"""
    cache = MemoryCache(maxsize=10, ttl=5)

    await cache.set("key1", {"data": 123})
    assert await cache.get("key1") == {"data": 123}

    await cache.set("tools:t1", [1, 2, 3])
    await cache.set("tools:t2", [4, 5])
    await cache.delete_prefix("tools:")
    assert await cache.get("tools:t1") is None
    assert await cache.get("tools:t2") is None
    assert await cache.get("key1") == {"data": 123}

    await cache.clear()
    assert await cache.get("key1") is None


@pytest.mark.asyncio
async def test_two_tier_cache_composite_behavior():
    """TwoTierCache で L1 -> L2 のフォールバックと伝播が機能すること"""
    l1 = MemoryCache(maxsize=10, ttl=10)
    l2 = MemoryCache(maxsize=10, ttl=10)  # L2 モックとして MemoryCache を代用
    two_tier = TwoTierCache(l1_cache=l1, l2_cache=l2)

    # 1. Two-Tier Set (両方に書き込まれる)
    await two_tier.set("user:100", {"name": "Alice"})
    assert await l1.get("user:100") == {"name": "Alice"}
    assert await l2.get("user:100") == {"name": "Alice"}

    # 2. L1 のみ破棄した場合、L2 からフェッチされて L1 に再配置される
    await l1.delete("user:100")
    assert await l1.get("user:100") is None

    val = await two_tier.get("user:100")
    assert val == {"name": "Alice"}
    assert await l1.get("user:100") == {"name": "Alice"}  # L1 にキャッシュ補充された

    # 3. Two-Tier Delete (両方から削除)
    await two_tier.delete("user:100")
    assert await l1.get("user:100") is None
    assert await l2.get("user:100") is None
