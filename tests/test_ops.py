"""
システム・運用系エンドポイント (/health, /health/live, /health/ready, /livez, /readyz, /metrics) のテスト
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from portico.main import app


client = TestClient(app)


def test_health():
    """基本ヘルスチェック /health が 200 OK を返すこと"""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "portico"
    assert "mock" in data


def test_liveness():
    """Liveness プローブ (/health/live および /livez) が 200 OK を返すこと"""
    res1 = client.get("/health/live")
    assert res1.status_code == 200
    assert res1.json()["status"] == "ok"

    res2 = client.get("/livez")
    assert res2.status_code == 200
    assert res2.json()["status"] == "ok"


def test_readiness():
    """Readiness プローブ (/health/ready および /readyz) が 200 OK を返すこと"""
    res1 = client.get("/health/ready")
    assert res1.status_code == 200
    assert res1.json()["status"] == "ok"

    res2 = client.get("/readyz")
    assert res2.status_code == 200
    assert res2.json()["status"] == "ok"


def test_metrics():
    """Prometheus 互換メトリクス /metrics が 200 OK かつテキスト形式で返ること"""
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers.get("content-type", "")
    assert "portico_up 1" in res.text
