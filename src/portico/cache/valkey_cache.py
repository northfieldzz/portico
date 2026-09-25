"""
L2 Valkey / Redis 分散キャッシュ実装
"""

from __future__ import annotations

import json
import logging
from typing import Any

from portico.cache.base import BaseCache
from portico.core.config import CACHE_L2_TTL_SECONDS, VALKEY_URL

logger = logging.getLogger(__name__)


class ValkeyCache(BaseCache):
    """Valkey / Redis をバックエンドとする分散キャッシュ (L2)"""

    def __init__(self, url: str = VALKEY_URL, default_ttl: int = CACHE_L2_TTL_SECONDS):
        self.url = url
        self.default_ttl = default_ttl
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self.url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
            except Exception as exc:
                logger.warning("⚠️ Valkey / Redis connection initialization failed: %s", exc)
                return None
        return self._redis

    async def get(self, key: str) -> Any | None:
        client = await self._get_redis()
        if client is None:
            return None
        try:
            val = await client.get(key)
            if val is not None:
                return json.loads(val)
            return None
        except Exception as exc:
            logger.warning("ValkeyCache get error on key '%s': %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        client = await self._get_redis()
        if client is None:
            return
        expire = ttl if ttl is not None else self.default_ttl
        try:
            val_json = json.dumps(value)
            await client.set(key, val_json, ex=expire)
        except Exception as exc:
            logger.warning("ValkeyCache set error on key '%s': %s", key, exc)

    async def delete(self, key: str) -> None:
        client = await self._get_redis()
        if client is None:
            return
        try:
            await client.delete(key)
        except Exception as exc:
            logger.warning("ValkeyCache delete error on key '%s': %s", key, exc)

    async def delete_prefix(self, prefix: str) -> None:
        client = await self._get_redis()
        if client is None:
            return
        try:
            keys = []
            async for k in client.scan_iter(match=f"{prefix}*"):
                keys.append(k)
            if keys:
                await client.delete(*keys)
        except Exception as exc:
            logger.warning("ValkeyCache delete_prefix error on prefix '%s': %s", prefix, exc)

    async def clear(self) -> None:
        client = await self._get_redis()
        if client is None:
            return
        try:
            await client.flushdb()
        except Exception as exc:
            logger.warning("ValkeyCache clear error: %s", exc)
