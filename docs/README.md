# MCP Gateway — コンポーネント内部仕様書インデックス

本ディレクトリ（`apps/mcp_gateway/docs/`）には、MCP Gateway サービス固有の**内部アーキテクチャ、FastMCP ハブ設計、PostgreSQL `mcp` スキーマ仕様、標準 SaaS アダプター実装、および外部カスタム MCP サーバー連携**をまとめています。

※ 全社横断的な認証・認可規約、全体アーキテクチャ、マルチテナント運用方針については、ルートの [docs/](../../docs/README.md) を参照してください。

---

## ドキュメント一覧

| # | ドキュメント名 | 概要・対象領域 |
|---|----------------|----------------|
| **01** | [アーキテクチャ & FastMCP ハブ仕様](01_gateway_architecture.md) | REST / SSE 二重インターフェース、FastAPI ライフサイクル、環境変数マッピング |
| **02** | [PostgreSQL `mcp` スキーマ & 永続化仕様](02_mcp_database_schema.md) | 独立 `mcp` スキーマ定義、`mcp.external_servers`、Row Level Security (RLS)、インメモリフォールバック |
| **03** | [テスト・デモ用ツール実装 & モック仕様](03_builtin_tools_implementation.md) | PoC 検証用リファレンス (Slack / Google Workspace)、OAuth スコープ、`MOCK_EXTERNAL_APIS` 分岐 |
| **04** | [外部カスタム MCP サーバー管理 & 動的ディスパッチ仕様](04_custom_server_dispatch.md) | 外部 MCP サーバー登録・ヘルスチェック (`/servers`)、動的ルーティング、プロキシ実行 |

---

## 関連リンク
- [全体システム横断仕様書 (ルート docs/)](../../docs/README.md)
- [全体開発ガイドライン (CONTRIBUTING.md)](../../CONTRIBUTING.md)
- [AI Engine 内部仕様書 (apps/ai_engine/docs/)](../../apps/ai_engine/docs/README.md)
