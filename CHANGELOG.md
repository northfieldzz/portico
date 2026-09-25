# 変更履歴 (Changelog)

すべての重要な変更は本ドキュメントに記録されます。  
バージョニングは [Semantic Versioning 2.0.0](https://semver.org/lang/ja/) に準拠しています。

---

## [1.0.0] - 2026-09-26

### 🎉 初版リリース (Initial Release)

Portico の最初のバージョンです。Model Context Protocol (MCP) をベースとしたマルチテナント向け実行ゲートウェイ・統合ハブとして、AI Engine や MCP クライアント（Claude Desktop, Cursor, LangGraph 等）と外部ツール（SaaS、顧客・テナント独自の外部カスタム MCP サーバー等）を安全に仲介します。

### ✨ 主な機能

#### 1. FastMCP ハブ & SSE ストリーミング (`/v1/sse`)
- **MCP プロトコル一本化**:
  - FastMCP 3.2+ ベースの SSE（Server-Sent Events）ゲートウェイエンドポイント。
  - ツール一覧探索（`tools/list`）およびツール実行（`tools/call`）を MCP プロトコルに完全一本化。
- **動的コンテキスト注入**:
  - リクエストごとのテナントコンテキスト（`X-Tenant-ID`）に基づき、ビルトインツールおよび登録済みカスタム MCP サーバーのツールを動的集約・提供。

#### 2. 外部カスタム MCP サーバー管理 & 動的ディスパッチ
- **サーバー登録 CRUD API (`/v1/servers`)**:
  - テナント固有の外部 MCP サーバー（SSE エンドポイント）の登録・一覧・更新・削除。
- **SSRF 防止 & 安全性検証**:
  - 登録 URL の厳格なバリデーション（HTTP/HTTPS スキーム検証、プライベート IP・ループバック・リンクローカル・クラウドメタデータアドレスの拒絶）。
- **暗号化認証情報管理**:
  - カスタムサーバーへの接続に必要な認証情報（Bearer トークン、API キー等）を AES-256-GCM で暗号化して永続化。
- **動的プロキシディスパッチ**:
  - ツール実行時に外部カスタム MCP サーバーへセキュアにリクエストを転送。

#### 3. ゲートウェイ共有シークレット認証 (Kura / Tollgate 準拠)
- **相互信頼検証**:
  - 前段のリバースプロキシ・認可ゲートウェイ（[Tollgate](https://github.com/northfieldzz/tollgate) 等）からのリクエストを `X-Gateway-Secret` ヘッダーと定数時間比較（`secrets.compare_digest`）で照合。
- **ゼロダウンタイム・シークレットローテーション**:
  - `GATEWAY_SHARED_SECRET_PREVIOUS` により移行期間中の新旧シークレット並行受付をサポート。
- **Fail-Fast 原則**:
  - 本番環境でのシークレット未設定時は起動時エラー（Fail-Fast）。
  - クライアント指定ヘッダーと認可コンテキストの不一致時は `403 Forbidden` で即座に遮断。
- **開発モード**:
  - ローカル検証用の `INSECURE_NO_GATEWAY_AUTH=true` による認証バイパス設定。

#### 4. マルチクラウド・ゼロ運用ストレージ & 二段キャッシュ
- **ゼロ運用マスターストア (`STORAGE_BACKEND`)**:
  - **SQLite**: ゼロ依存・単一ファイルでローカル開発・テスト・単体コンテナ運用。
  - **AWS DynamoDB**: AWS サーバーレス環境（Kura と同一インフラ）。
  - **GCP Cloud Firestore**: Google Cloud サーバーレス NoSQL。
  - **Azure Cosmos DB**: Microsoft Azure サーバーレス NoSQL。
- **二段キャッシュ (`CACHE_LAYER`)**:
  - **L1 In-Memory Cache**: CPU メモリ上の TTL/LRU キャッシュによりマイクロ秒レイテンシでツール定義を即時返却。
  - **L2 Valkey / Redis**: 複数コンテナ間で共有される分散キャッシュ。

#### 5. テスト・デモ用リファレンスツール
- テストおよびデモ実行用のビルトインツール群（電卓、Slack メッセージ送信、Google Calendar 連携）。
- `MOCK_EXTERNAL_APIS=true` による外部 SaaS 呼び出しの安全なモック実行。

#### 6. オブザーバビリティ & ドキュメント
- **ヘルスチェック**: `/health`, `/livez`, `/readyz`
- **Prometheus メトリクス**: `/metrics`
- **OpenAPI 3.1 仕様**: `/v1/openapi.json`
