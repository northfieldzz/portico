"""
IT Context Platform — SaaS Token Bucket Rate Limiter & Backpressure Controller
外部 SaaS（Slack, Google 等）に対する API 呼び出しの集中を緩和し、短時間待機で平滑化する。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float
    last_updated: float


class SaaSRateLimiter:
    """外部 SaaS 別 Token Bucket レートリミッター。"""

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()

        # デフォルト設定 (汎用: 10 バースト, 10 req/秒)
        self.default_configs: dict[str, tuple[float, float]] = {
            "default": (10.0, 10.0),
        }

    def _get_bucket(self, saas_name: str) -> TokenBucket:
        saas_key = saas_name.lower()
        if saas_key not in self._buckets:
            cap, rate = self.default_configs.get(saas_key, self.default_configs["default"])
            self._buckets[saas_key] = TokenBucket(
                capacity=cap,
                refill_rate=rate,
                tokens=cap,
                last_updated=time.monotonic(),
            )
        return self._buckets[saas_key]

    async def acquire(self, saas_name: str, max_wait_seconds: float = 3.0) -> bool:
        """
        指定された SaaS の呼び出しトークンを 1 個消費する。
        必要に応じて非同期スリープ（バックプレッシャー）を行い、待機時間が上限を超える場合は False を返す。
        """
        async with self._lock:
            bucket = self._get_bucket(saas_name)
            now = time.monotonic()
            elapsed = now - bucket.last_updated
            bucket.last_updated = now

            # トークンの補充
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True

            # トークン不足時の待機時間計算
            needed = 1.0 - bucket.tokens
            wait_time = needed / bucket.refill_rate

            if wait_time > max_wait_seconds:
                logger.warning(
                    "⚠️ SaaS rate limit reached for '%s'. Estimated wait %.2fs exceeds max wait %.2fs.",
                    saas_name,
                    wait_time,
                    max_wait_seconds,
                )
                return False

            # 短時間ならバックプレッシャー待機してトークンを確保
            logger.info("⏳ SaaS backpressure: throttling '%s' for %.2fs", saas_name, wait_time)
            bucket.tokens = 0.0

        await asyncio.sleep(wait_time)
        return True


# グローバルシングルトン
saas_limiter = SaaSRateLimiter()
