"""
二段キャッシュ (L1: In-Memory + L2: Valkey/Redis) 複合実装
"""

from __future__ import annotations

import logging
from typing import Any

from portico.cache.base import BaseCache
from portico.cache.memory_cache import MemoryCache
from portico.cache.valkey_cache import ValkeyCache

logger = logging.getLogger(__name__)


class TwoTierCache(BaseCache):
    """
    L1 (ローカルインメモリ) と L2 (分散 Valkey/Redis) を組み合わせた二段キャッシュ。
    - 参照: L1 -> L2 -> Storage (Cache Miss)
    - 更新/削除: L2 と L1 の両方を即座に同期/無効化
    """

    def __init__(self, l1_cache: MemoryCache | None = None, l2_cache: ValkeyCache | None = None):
        self.l1 = l1_cache or MemoryCache()
        self.l2 = l2_cache or ValkeyCache()

    async def get(self, key: str) -> Any | None:
        # 1. Check L1 In-Memory (0.001ms)
        val = await self.l1.get(key)
        if val is not None:
            return val

        # 2. Check L2 Valkey / Redis (0.5ms)
        val = await self.l2.get(key)
        if val is not None:
            # Populate L1 for future instant accesses
            await self.l1.set(key, val)
            return val

        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        # Write to L2 (shared across pods) and L1 (local fast)
        await self.l2.set(key, value, ttl=ttl)
        await self.l1.set(key, value, ttl=ttl)

    async def delete(self, key: str) -> None:
        await self.l2.delete(key)
        await self.l1.delete(key)

    async def delete_prefix(self, prefix: str) -> None:
        await self.l2.delete_prefix(prefix)
        await self.l1.delete_prefix(prefix)

    async def clear(self) -> None:
        await self.l2.clear()
        await self.l1.clear()
