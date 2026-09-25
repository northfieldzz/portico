"""
インメモリストレージリポジトリ実装 (テスト・揮発用)
"""

from __future__ import annotations

import logging
from typing import Any

from portico.storage.base import BaseServerRepository

logger = logging.getLogger(__name__)


class MemoryServerRepository(BaseServerRepository):
    """プロセス内辞書をバックエンドとするサーバーリポジトリ"""

    def __init__(self):
        # {tenant_id: {server_id: server_dict}}
        self._store: dict[str, dict[str, dict[str, Any]]] = {}

    async def init_storage(self) -> None:
        logger.info("🧠 In-Memory Storage initialized")

    async def close(self) -> None:
        self._store.clear()

    async def list_servers(self, tenant_id: str) -> list[dict[str, Any]]:
        return list(self._store.get(tenant_id, {}).values())

    async def get_server(self, tenant_id: str, server_id: str) -> dict[str, Any] | None:
        return self._store.get(tenant_id, {}).get(server_id)

    async def create_server(self, tenant_id: str, server_data: dict[str, Any]) -> dict[str, Any]:
        if tenant_id not in self._store:
            self._store[tenant_id] = {}
        s_id = server_data["id"]
        server_copy = dict(server_data)
        server_copy["tenant_id"] = tenant_id
        self._store[tenant_id][s_id] = server_copy
        return server_copy

    async def update_server(
        self, tenant_id: str, server_id: str, update_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        curr = self._store.get(tenant_id, {}).get(server_id)
        if not curr:
            return None
        curr.update(update_data)
        return curr

    async def delete_server(self, tenant_id: str, server_id: str) -> bool:
        if tenant_id in self._store and server_id in self._store[tenant_id]:
            del self._store[tenant_id][server_id]
            return True
        return False
