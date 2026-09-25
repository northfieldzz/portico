"""
L1 プロセス内インメモリ TTL/LRU キャッシュ実装
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from cachetools import TTLCache

from portico.cache.base import BaseCache
from portico.core.config import CACHE_L1_MAXSIZE, CACHE_L1_TTL_SECONDS

logger = logging.getLogger(__name__)


class MemoryCache(BaseCache):
    """プロセス内インメモリ TTL/LRU キャッシュ (L1)"""

    def __init__(self, maxsize: int = CACHE_L1_MAXSIZE, ttl: int = CACHE_L1_TTL_SECONDS):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            return self._cache.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        async with self._lock:
            self._cache[key] = value

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def delete_prefix(self, prefix: str) -> None:
        async with self._lock:
            keys_to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_del:
                self._cache.pop(k, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
