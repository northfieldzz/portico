# Portico — アーキテクチャ & FastMCP ハブ仕様書

本ドキュメントは、Portico におけるサービス構造、FastAPI と FastMCP の統合設計、提供エンドポイント、および起動ライフサイクルについて定義する。

---

## 1. サービス概要とアーキテクチャ

MCP Gateway は、AI Engine からの指示を受け取り、実際の外部 SaaS や社内システムへの安全な API 呼び出しを行う実行レイヤーである。

```mermaid
flowchart TD
    AI["AI Engine / MCP クライアント<br/>(Claude Desktop, Cursor, LangGraph 等)"]
    
    subgraph Gateway ["MCP Gateway (Port 8001: 実行基盤)"]
        ROUTER["FastAPI Router / FastMCP Hub"]
        
        subgraph Endpoints ["インターフェース"]
            SSE["MCP/SSE エンドポイント<br/>• /v1/sse (Model Context Protocol 準拠)"]
            REST["外部 MCP 管理 REST API<br/>• GET/POST/DELETE /v1/servers"]
        end
        
        subgraph Adapters ["テスト・デモ用ツール (tools/)<br/>※ PoC 検証用サンプル実装"]
            SLACK["slack_tool.py (招待・メッセージ通知)"]
            GOOGLE["google_tool.py (アカウント・グループ作成)"]
        end
        
        DB_POOL["PostgreSQL プール (db/session.py)<br/>• mcp 独立スキーマ管理"]
    end
    
    EXT_SaaS["外部 SaaS API (Slack, Google 等)"]
    EXT_MCP["本番 / 顧客専用外部 MCP サーバー"]

    AI -->|"MCP プロトコル (SSE)"| SSE
    AI -.->|"サーバー管理 (REST)"| REST
    
    SSE --> Adapters
    SSE --> DB_POOL
    SSE -->|"プロキシ実行"| EXT_MCP
    
    Adapters -->|"OAuth / サービスアカウント"| EXT_SaaS
```

---

## 2. インターフェース設計

MCP Gateway は、ツール探索・実行を MCP プロトコルに一本化し、管理用 API を REST で提供する。

1. **MCP / SSE エンドポイント (`/v1/sse`)**:
   - Model Context Protocol (MCP) 標準に準拠した Server-Sent Events (SSE) ストリーミングインターフェース。
   - ツール一覧取得（`tools/list`）およびツール実行（`tools/call`）を処理。
   - `X-Gateway-Secret` 共有シークレット認証（新旧ローテーション対応）および Tollgate 連携ヘッダー透過に対応。
2. **外部 MCP サーバー管理 REST API (`/v1/servers`)**:
   - テナント別の外部 MCP サーバー登録・一覧・削除を行う管理インターフェース。



---

## 3. アプリケーションライフサイクル (`lifespan`)

`main.py` の起動時処理において、以下が実行される。

```mermaid
sequenceDiagram
    participant Main as FastAPI (main.py)
    participant Hub as FastMCP Hub
    participant DB as PostgreSQL (mcp schema)

    Note over Main: 起動処理開始 (Startup)
    Main->>DB: init_mcp_db() 呼び出し
    DB->>DB: CREATE SCHEMA IF NOT EXISTS mcp;
    DB->>DB: CREATE TABLE mcp.external_servers & RLS ポリシー作成
    Main->>Hub: 標準ツール (Slack, Google) のディスパッチ登録
    Note over Main: 起動完了 (ポート 8001 受付開始)

    Note over Main: 終了処理 (Shutdown)
    Main->>DB: コネクションプールの解放
    Note over Main: シャットダウン完了
```

---

## 4. 環境変数マッピング (`core/config.py`)

MCP Gateway が利用する環境変数一覧。

| 環境変数名 | デフォルト値 | 説明 |
|------------|--------------|------|
| `ROOT_PATH` | `/gateway` | リバースプロキシ（Nginx / ALB）配下用のルートパス |
| `LOG_LEVEL` | `INFO` | ログ出力レベル (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MOCK_EXTERNAL_APIS` | `true` | `true` の場合、外部 SaaS を実際に叩かずモックレスポンスを返却 |
| `POSTGRES_URL` | `postgresql://...` | PostgreSQL 接続 URL (asyncpg) |
