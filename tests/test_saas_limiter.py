"""
Unit tests for SaaS token bucket rate limiter and backpressure controller.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mcp_gateway.services.saas_limiter import SaaSRateLimiter


class TestSaaSRateLimiter:
    """SaaS 別 Token Bucket レートリミッターの単体テスト。"""

    @pytest.fixture
    def limiter(self) -> SaaSRateLimiter:
        """テストごとに独立したリミッターインスタンスを生成。"""
        lim = SaaSRateLimiter()
        # テスト用に小さい容量とレート (cap=2.0, refill=1.0 req/s) を設定
        lim.default_configs["test_service"] = (2.0, 1.0)
        lim.default_configs["fast_service"] = (5.0, 5.0)
        return lim

    @pytest.mark.asyncio
    async def test_initial_burst_capacity(self, limiter: SaaSRateLimiter):
        """初期状態でバースト容量（2回分）まで即時トークンが消費できる。"""
        ok1 = await limiter.acquire("test_service", max_wait_seconds=1.0)
        ok2 = await limiter.acquire("test_service", max_wait_seconds=1.0)
        assert ok1 is True
        assert ok2 is True

    @pytest.mark.asyncio
    async def test_exceeding_max_wait_rejects_immediately(self, limiter: SaaSRateLimiter):
        """トークンが尽き、必要待機時間が max_wait_seconds を超える場合は False を返す。"""
        # 容量 2.0 をすべて消費
        await limiter.acquire("test_service", max_wait_seconds=1.0)
        await limiter.acquire("test_service", max_wait_seconds=1.0)

        # 残りトークン 0。1秒に1トークン補充。
        # max_wait_seconds=0.1 の場合、1.0秒待てないので即座に拒絶 (False) されるはず
        ok = await limiter.acquire("test_service", max_wait_seconds=0.1)
        assert ok is False

    @pytest.mark.asyncio
    async def test_backpressure_wait_within_threshold(self, limiter: SaaSRateLimiter):
        """待機時間が閾値以内の場合、asyncio.sleep によるバックプレッシャーを経て True を返す。"""
        # 容量 2.0 を消費
        await limiter.acquire("test_service", max_wait_seconds=1.0)
        await limiter.acquire("test_service", max_wait_seconds=1.0)

        # 次のリクエストは max_wait_seconds=2.0 で許可。asyncio.sleep が呼ばれることを確認
        with patch("asyncio.sleep", new_callable=pytest.importorskip("unittest.mock").AsyncMock) as mock_sleep:
            ok = await limiter.acquire("test_service", max_wait_seconds=2.0)
            assert ok is True
            mock_sleep.assert_awaited_once()
            # 待機時間は 1.0 秒前後
            wait_arg = mock_sleep.call_args[0][0]
            assert 0.8 <= wait_arg <= 1.2

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self, limiter: SaaSRateLimiter):
        """時間経過とともにトークンが補充される。"""
        current_time = 1000.0

        with patch("time.monotonic", side_effect=lambda: current_time):
            # 初期化 & 2トークン消費
            await limiter.acquire("test_service", max_wait_seconds=0.1)
            await limiter.acquire("test_service", max_wait_seconds=0.1)

            bucket = limiter._get_bucket("test_service")
            assert bucket.tokens < 0.1

        # 2秒時間を進める (refill_rate=1.0 なので 2.0 トークン補充され満タンになるはず)
        current_time = 1002.0
        with patch("time.monotonic", side_effect=lambda: current_time):
            ok1 = await limiter.acquire("test_service", max_wait_seconds=0.1)
            assert ok1 is True
            ok2 = await limiter.acquire("test_service", max_wait_seconds=0.1)
            assert ok2 is True

    @pytest.mark.asyncio
    async def test_service_isolation(self, limiter: SaaSRateLimiter):
        """異なる SaaS 名のバケットは独立してレート制限される。"""
        # test_service を使い切る
        await limiter.acquire("test_service", max_wait_seconds=0.1)
        await limiter.acquire("test_service", max_wait_seconds=0.1)

        # 別のサービス fast_service は影響を受けず即座にトークンを取得できる
        ok = await limiter.acquire("fast_service", max_wait_seconds=0.1)
        assert ok is True
