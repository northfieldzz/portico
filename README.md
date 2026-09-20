# Portico — MCP Gateway Integration Hub

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)](https://fastapi.tiangolo.com/)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.0+-green.svg)](https://github.com/jlowin/fastmcp)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791.svg)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Portico** は、Model Context Protocol (MCP) をベースとしたエンタープライズ向け実行ゲートウェイ・統合ハブである。  
AI Engine や MCP クライアント（Claude Desktop, Cursor 等）からのツール呼び出しを受け付け、SaaS（Slack, Google Workspace 等）や各テナント固有の外部カスタム MCP サーバーへ安全にルーティング・プロキシ実行する。

---

## 主な機能

- **二重インターフェース (Dual Protocol)**:
  - **HTTP REST API**: `/v1/tools/{tool_name}` 経由で同期的な JSON ツール呼び出しを提供。
  - **MCP / SSE**: `/v1/sse` にて Model Context Protocol (MCP) 標準に準拠した Server-Sent Events ストリーミングを提供。
- **外部カスタム MCP サーバー管理 & 動的ルーティング**:
  - テナントごとに独自の MCP サーバー（社内 Active Directory、オンプレミスシステム等）を動的に登録・削除・管理。
  - 外部サーバーのツール一覧を並列フェッチし、TTL キャッシュで高速返却。
- **堅牢なマルチテナント & データ分離**:
  - PostgreSQL 独立スキーマ `mcp` および Row Level Security (RLS) によるテナント間データ分離。
  - DB 未接続時はインメモリストアへ自動フォールバック。
- **セキュリティ & ガバナンス**:
  - **Tollgate 連携**: API Gateway（Tollgate）が付与するコンテキストヘッダー（`X-Tenant-ID`, `X-Key-ID` 等）によるテナント検証。
  - **SSRF 防止 & 安全性検証**: 外部 MCP サーバー登録時のプライベート IP・ループバック遮断（本番環境）。
  - **内部シークレット保護**: `X-Internal-Secret` の定数時間比較（`secrets.compare_digest`）によるタイミング攻撃防御。
  - **暗号化キー本番バリデーション**: 本番環境でのキー未設定による脆弱性抑止。
  - **構造化監査ログ**: ツール実行ごとの結果、実行時間、テナント情報を `portico.audit` に記録。
  - **機密情報漏洩防止**: ツール実行時の例外スタックトレースを外部へ非公開化。
- **PoC・デモ用リファレンスツール**:
  - Slack（招待、メッセージ送信）、Google Workspace（アカウント作成、グループ追加）。
  - `MOCK_EXTERNAL_APIS=true` により、実 API クレデンシャル不要で安全にデモ実行可能。

---

## アーキテクチャ

```mermaid
flowchart TD
    AI["AI Engine / MCP クライアント<br/>(Claude Desktop, Cursor 等)"]
    
    subgraph Portico ["Portico (MCP Gateway : 8001)"]
        ROUTER["FastAPI Router / FastMCP Hub"]
        
        subgraph Endpoints ["公開インターフェース"]
            REST["REST API<br/>• POST /v1/tools/{name}<br/>• GET/POST /v1/servers"]
            SSE["MCP SSE<br/>• /v1/sse"]
        end
        
        subgraph CoreServices ["コアサービス"]
            DISPATCH["動的ディスパッチャー / ツール集約"]
            CACHE["TTL ツールキャッシュ"]
            AUDIT["監査ログ・SSRF バリデーター"]
        end
        
        subgraph Adapters ["組み込みリファレンスツール"]
            SLACK["Slack Adapter"]
            GOOGLE["Google Adapter"]
        end
        
        DB_POOL["PostgreSQL プール<br/>• mcp 独立スキーマ (RLS)"]
    end
    
    EXT_SaaS["外部 SaaS (Slack / Google)"]
    EXT_MCP["顧客・外部 MCP サーバー"]

    AI -->|"REST 呼び出し (JSON)"| REST
    AI -->|"MCP プロトコル (SSE)"| SSE
    
    REST --> ROUTER
    SSE --> ROUTER
    ROUTER --> CoreServices
    
    CoreServices --> Adapters
    CoreServices --> DB_POOL
    CoreServices -->|"プロキシ実行"| EXT_MCP
    
    Adapters -->|"API 連携 (モック切替可)"| EXT_SaaS
```

---

## ディレクトリ構成

```text
portico/
├── compose.yaml              # Docker Compose 定義
├── postgres.compose.yaml     # PostgreSQL 17 (pgvector) 定義
├── Dockerfile                # マルチステージビルド Dockerfile
├── pyproject.toml            # プロジェクト定義 & 依存関係 (Hatchling)
├── .env.example              # 環境変数サンプル
├── docs/                     # 詳細仕様書
│   ├── 01_gateway_architecture.md
│   ├── 02_mcp_database_schema.md
│   ├── 03_builtin_tools_implementation.md
│   └── 04_custom_server_dispatch.md
├── src/
│   └── portico/
│       ├── main.py           # FastAPI エントリポイント & ライフサイクル
│       ├── api/              # API ルーティング & 依存性注入 (Tollgate / Secret)
│       ├── core/             # 設定管理、FastMCP ハブ、SSRF バリデーター
│       ├── db/               # PostgreSQL プール & mcp スキーマ管理
│       ├── schemas/          # Pydantic スキーマ
│       ├── services/         # サーバー管理、ツールディスパッチ、監査ログ
│       └── tools/            # テスト・PoC 用リファレンスツール (Slack / Google)
└── tests/                    # pytest 単体・統合テストスイート
```

---

## API エンドポイント一覧

### 1. ツール実行 & 一覧 (`/v1/tools`)
- `GET /v1/tools`: 利用可能なツール（組み込み + 登録済み外部 MCP サーバー）の一覧取得
- `POST /v1/tools/{tool_name}`: 指定ツールの実行

### 2. 外部 MCP サーバー管理 (`/v1/servers`)
- `GET /v1/servers`: 自テナントに登録されている外部 MCP サーバー一覧取得
- `POST /v1/servers`: 新規外部 MCP サーバーの登録（疎通確認 & SSRF 検証付き）
- `DELETE /v1/servers/{server_id}`: 外部 MCP サーバーの登録解除

### 3. MCP SSE ストリーミング (`/v1/sse`)
- `GET /v1/sse`: Model Context Protocol 準拠の SSE 接続エンドポイント

### 4. 内部サービス専用 API (`/v1/internal`)
- `POST /v1/internal/tools/sync`: AI Engine 連携用ツール定義即時同期（`X-Internal-Secret` 必須）

### 5. 運用 & ヘルスチェック
- `GET /health`, `GET /health/live`, `GET /livez`: Liveness プローブ
- `GET /health/ready`, `GET /readyz`: Readiness プローブ（DB 接続状態確認）
- `GET /metrics`: メトリクス確認

---

## 環境変数設定

主要な設定項目（詳細は `.env.example` を参照）：

| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `ENVIRONMENT` | `development` | 実行環境 (`development` / `production`) |
| `POSTGRES_URL` | `postgresql://postgres:password@postgres:5432/itcp_db` | PostgreSQL 接続 URL |
| `MOCK_EXTERNAL_APIS` | `true` | `true` の場合、実 SaaS を呼ばずにモック応答 |
| `ALLOW_LOCAL_MCP_SERVERS` | `true` (dev) / `false` (prod) | ローカル / プライベート IP への外部 MCP サーバー登録可否 |
| `ENFORCE_TOLLGATE_AUTH` | `false` | Tollgate 認証ヘッダーの強制検証フラグ |
| `INTERNAL_SERVICE_SECRET` | 自動生成ランダム値 | 内部サービス間専用通信シークレット |
| `SECRET_ENCRYPTION_KEY` | - | 機密情報暗号化用シークレットキー（本番環境では必須） |
| `TOOL_CACHE_TTL_SECONDS` | `60` | 外部 MCP ツール定義のキャッシュ保持秒数 |
| `EXTERNAL_MCP_TIMEOUT_SECONDS` | `5.0` | 外部 MCP サーバー通信タイムアウト秒数 |
| `LOG_LEVEL` | `INFO` | ログ出力レベル (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## クイックスタート

### 前提条件
- Docker & Docker Compose
- （ローカル実行時）Python 3.13+ および [uv](https://github.com/astral-sh/uv)

### 1. Docker Compose での起動 (推奨)

```bash
# 環境変数の準備
cp .env.example .env

# コンテナ起動 (PostgreSQL + Portico)
docker compose up -d

# ログ確認
docker compose logs -f portico

# ヘルスチェック確認
curl http://localhost:8001/health
```

### 2. ローカル環境での起動

```bash
# 依存関係のインストール
uv sync

# アプリケーション起動
uv run uvicorn portico.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## テスト実行

```bash
# 全テスト実行
uv run pytest

# カバレッジレポート出力
uv run pytest --cov=portico
```

---

## 詳細仕様書 (docs/)

より詳細な仕様については `docs/` 配下の各ドキュメントを参照：

- [01. アーキテクチャ & FastMCP ハブ仕様](docs/01_gateway_architecture.md)
- [02. PostgreSQL mcp スキーマ & 永続化仕様](docs/02_mcp_database_schema.md)
- [03. テスト・デモ用リファレンスツール仕様](docs/03_builtin_tools_implementation.md)
- [04. 外部カスタム MCP サーバー管理 & 動的ディスパッチ仕様](docs/04_custom_server_dispatch.md)
