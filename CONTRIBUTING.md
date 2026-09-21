# Portico コントリビューションガイド

Portico への貢献を検討していただき、ありがとうございます！  
本プロジェクトは、安全でスケーラブルな Model Context Protocol (MCP) 実行ゲートウェイを提供することを目指しています。新機能の提案、バグ報告、ドキュメントの改善など、あらゆる貢献を歓迎します。

---

## 目次

1. [行動規範 (Code of Conduct)](#行動規範-code-of-conduct)
2. [開発ワークフロー](#開発ワークフロー)
   - [1. Issue の作成](#1-issue-の作成)
   - [2. ブランチ戦略](#2-ブランチ戦略)
   - [3. コミットメッセージ規約](#3-コミットメッセージ規約)
3. [ローカル開発環境のセットアップ](#ローカル開発環境のセットアップ)
   - [前提ツール](#前提ツール)
   - [手順](#手順)
4. [アーキテクチャと設計原則](#アーキテクチャと設計原則)
   - [ディレクトリ構成と役割](#ディレクトリ構成と役割)
   - [コア設計・セキュリティ方針](#コア設計セキュリティ方針)
5. [コーディング規約](#コーディング規約)
6. [テスト規約](#テスト規約)
7. [プルリクエスト (PR) チェックリスト](#プルリクエスト-pr-チェックリスト)

---

## 行動規範 (Code of Conduct)

すべての参加者が安全かつ敬意を持ってコラボレーションできるよう、オープンで歓迎されるコミュニティの維持に努めてください。相手を尊重した建設的なフィードバックと対話を心がけてください。

---

## 開発ワークフロー

### 1. Issue の作成
- バグの報告や新機能の提案を行う場合は、まず [GitHub Issues](https://github.com/northfieldzz/portico/issues) を作成してください。
- 既存の Issue や PR で類似の議論がないか事前に確認してください。

### 2. ブランチ戦略
- `main` ブランチから作業用ブランチを作成してください。
- ブランチ名は以下のプレフィックスを使用してください：
  - `feature/<機能名>`: 新機能の追加
  - `fix/<バグ内容>`: バグ修正
  - `docs/<ドキュメント名>`: ドキュメント修正
  - `refactor/<リファクタ内容>`: 振る舞いを変えないコード整理

```bash
git checkout -b feature/external-server-health-monitor
```

### 3. コミットメッセージ規約
コミットメッセージには [Conventional Commits](https://www.conventionalcommits.org/) 形式を採用しています。

形式: `<type>(<scope>): <description>`

| Type | 説明 | 例 |
|---|---|---|
| `feat` | 新機能の追加 | `feat(servers): add automatic health probe for external MCP servers` |
| `fix` | バグ修正 | `fix(validator): prevent ssrf bypass via ipv4-mapped ipv6 addresses` |
| `docs` | ドキュメントの変更 | `docs(readme): add API usage examples and endpoint tables` |
| `test` | テストの追加・修正 | `test(cache): add parallel tool fetch resilience test` |
| `refactor`| リファクタリング | `refactor(dispatch): streamline namespaced tool routing` |
| `chore` | ビルド設定や補助ツールの変更 | `chore(deps): bump fastmcp from 2.14.7 to 3.2.0` |

---

## ローカル開発環境のセットアップ

### 前提ツール
- **Python**: 3.14+ (推奨)
- **uv**: 高速な Python パッケージマネージャー ([インストール手順](https://github.com/astral-sh/uv))
- **Docker** & **Docker Compose**
- **Git**

### 手順

```bash
# 1. リポジトリのクローン
git clone https://github.com/northfieldzz/portico.git
cd portico

# 2. 仮想環境の作成と依存関係の同期
uv sync

# 3. 開発用データベース (PostgreSQL) の起動
docker compose up -d postgres
# (DB を起動しない場合でも、自動的にインメモリストアへフォールバックします)

# 4. 環境変数の設定
cp .env.example .env

# 5. ローカルサーバー起動
uv run uvicorn portico.main:app --host 0.0.0.0 --port 8001 --reload
```

サーバーが起動したら、別ターミナルでヘルスチェックを確認します：
```bash
curl -i http://localhost:8001/livez
curl -i http://localhost:8001/readyz
```

---

## アーキテクチャと設計原則

Portico は FastAPI と FastMCP をベースとしたレイヤード構造を採用しています。依存関係は内側に向かって整理してください。

### ディレクトリ構成と役割

```text
src/portico/
├── api/              # API ルーティング & 依存性注入 (FastAPI router, deps)
├── core/             # グローバル設定 (config)、FastMCP ハブ初期化
├── db/               # PostgreSQL コネクションプール & mcp スキーマ管理 (RLS)
├── schemas/          # Pydantic リクエスト/レスポンススキーマ
├── services/         # サーバー管理、ツールディスパッチ、監査ログ、URL 検証、暗号化
└── tools/            # テスト・PoC 用組み込みリファレンスツール (Slack / Google)
```

### コア設計・セキュリティ方針

開発時は以下のセキュリティおよび設計方針を厳守してください：

1. **Fail-Fast 原則（コンフリクト・不正入力の即時遮断）**:
   - API Gateway（Tollgate）との連携において、クライアント指定ヘッダーとキー属性値の不一致（コンフリクト）を暗黙的に上書きして処理を継続させてはならない。なりすまし防止および設定ミスの即時検知のため、コンフリクト時は `403 Forbidden`（または `400 Bad Request`）で即座に拒絶すること。
   - 外部 MCP サーバー登録時は、プライベート IP、ループバック、クラウドメタデータ IP（`169.254.169.254` 等）へのアクセスを即時検証・遮断すること。
2. **ハードコードされたシークレットの排除**:
   - API キー、認証トークン、マスター管理者シークレット等の認証情報において、コード内にデフォルト値をフォールバックとしてハードコードしてはならない。環境変数未設定時は明示的な認証無効または起動時エラー（Fail-Fast）とすること。開発環境用の既知シークレットは、ローカル用環境設定ファイル（`.env` や Compose 定義の初期値など）でのみ明示的に注入すること。
3. **タイミング攻撃防御（定数時間比較）**:
   - 内部サービス間専用通信シークレット（`X-Internal-Secret`）の照合には、通常の文字列比較演算子（`==`）ではなく、必ず `secrets.compare_digest` を使用してタイミング攻撃を防止すること。
4. **機密情報および生スタックトレースの非公開化**:
   - ツール実行時や API ハンドリング時の内部例外において、生のスタックトレースをクライアントへのレスポンスに露出させてはならない。構造化エラーとしてラップし、詳細はサーバー側ログ（`logger.error`）でのみ記録すること。
5. **クラウドネイティブ・プローブ体系**:
   - プロセスの死活監視には `/livez`（`/health/live`）、外部依存（PostgreSQL）を含めた準備状態監視には `/readyz`（`/health/ready`）、総合疎通には `/health` を使用すること。

---

## コーディング規約

- **フォーマット & リント**: 
  - コミット前にコードスタイルを整えてください。
  ```bash
  uv run ruff format .
  uv run ruff check .
  ```
- **型ヒント**:
  - すべての関数およびメソッドに適切な型ヒントを付与してください（`from __future__ import annotations` を推奨）。
  - Pydantic スキーマを活用してリクエスト/レスポンスの境界防御を行ってください。
- **非同期 I/O**:
  - I/O バウンドな処理（HTTP 通信、DB アクセス）は必ず `async` / `await` を使用し、ブロッキング処理を避けてください。
  - 外部 HTTP 通信には `httpx.AsyncClient` を使用し、必ずタイムアウトを設定してください。
- **エラーハンドリング**:
  - 例外を握りつぶさず、FastAPI の `HTTPException` を適切に使い分けてクライアントへ通知してください。
  - 重要な操作（外部サーバー登録・削除、ツール実行等）は構造化ログ（`portico.audit` 等）を出力してください。

---

## テスト規約

Portico では高い品質と安全性を担保するため、機能追加・バグ修正には必ず対応する単体テスト（ユニットテスト）を同梱してください。

```bash
# 全テスト実行
uv run pytest

# 詳細出力付き実行
uv run pytest -v

# カバレッジレポート出力
uv run pytest --cov=portico --cov-report=term-missing
```

- **高速かつ独立したテスト設計**:
  - `unittest.mock.patch` やインメモリストアを活用し、外部 DB や実 SaaS 接続なしで単体テストが完結できるように設計してください。
- **セキュリティ & エッジケースの網羅**:
  - 正常系だけでなく、SSRF 禁止 IP（IPv4/IPv6 マップド IP、リンクローカル等）、認証不備、タイムアウト、並列フェッチ失敗時の耐障害性など、エッジケースを確実に検証してください。

---

## プルリクエスト (PR) チェックリスト

PR を提出する前に、以下の項目を確認してください：

- [ ] 最新の `main` ブランチを取り込んでいるか（`git pull origin main` または `git rebase main`）
- [ ] すべてのテストが成功するか（`uv run pytest`）
- [ ] リンター・フォーマッターを通過しているか（`uv run ruff check .` / `uv run ruff format .`）
- [ ] 新機能・修正内容に対するテストコードが含まれているか
- [ ] コミットメッセージが Conventional Commits 規約に準拠しているか
- [ ] コード内にハードコードされたシークレットや既定値フォールバックが含まれていないか
- [ ] 必要に応じて `README.md` や `docs/` のドキュメントを更新しているか

PR が作成されると、CI による自動テストおよびメンテナーによるコードレビューが行われます。建設的なディスカッションを通じて、より良いコードに仕上げていきましょう！
