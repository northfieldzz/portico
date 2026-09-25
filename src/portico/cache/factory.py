"""
キャッシュサービス ファクトリモジュール
"""

from __future__ import annotations

import logging
from typing import Any

from portico.cache.base import BaseCache
from portico.cache.memory_cache import MemoryCache
from portico.cache.two_tier_cache import TwoTierCache
from portico.cache.valkey_cache import ValkeyCache
from portico.core.config import CACHE_LAYER

logger = logging.getLogger(__name__)


class NoOpCache(BaseCache):
    """キャッシュをバイパスする Null Cache"""

    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass

    async def delete_prefix(self, prefix: str) -> None:
        pass

    async def clear(self) -> None:
        pass


_cache_instance: BaseCache | None = None


def get_cache_service() -> BaseCache:
    """設定された CACHE_LAYER に基づきシングルトンキャッシュを返す"""
    global _cache_instance
    if _cache_instance is None:
        mode = CACHE_LAYER.lower()
        if mode == "two_tier":
            _cache_instance = TwoTierCache()
        elif mode == "memory":
            _cache_instance = MemoryCache()
        elif mode in ("valkey", "redis"):
            _cache_instance = ValkeyCache()
        elif mode == "none":
            _cache_instance = NoOpCache()
        else:
            logger.warning("Unknown CACHE_LAYER '%s', fallback to TwoTierCache", mode)
            _cache_instance = TwoTierCache()
    return _cache_instance


async def clear_all_caches() -> None:
    """全キャッシュをフラッシュ"""
    cache = get_cache_service()
    await cache.clear()
