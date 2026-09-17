# MCP Gateway — テスト・デモ用リファレンスツール実装仕様書

> **重要**: 本モジュール群（Slack, Google Workspace）は、**PoC 動作確認およびテスト・デモ検証を目的としたリファレンス実装（サンプルコード）** です。  
> プラットフォーム本来の設計としては特定ツールに依存せず、オープンな **Model Context Protocol (MCP)** を介して本番用 MCP サーバーや顧客独自の社内システムを動的に接続・実行するゲートウェイ基盤として機能します。

---

## 1. テスト・デモ用リファレンスツール一覧

| モジュール | ツール関数名 | 目的（デモシナリオ） | 想定外部 API |
|------------|--------------|----------------------|--------------|
| `tools/slack_tool.py` | `slack_invite_user` | 新入社員の Slack ワークスペース招待デモ | Slack Web API (`admin.users.invite` または SCIM) |
| `tools/slack_tool.py` | `slack_send_message` | チャンネルへのウェルカム通知投稿デモ | Slack Web API (`chat.postMessage`) |
| `tools/google_tool.py` | `google_create_account`| Google Workspace アカウント作成デモ | Google Admin SDK (`Directory.Users: insert`) |
| `tools/google_tool.py` | `google_assign_group` | 配属先部署の Google グループ追加デモ | Google Admin SDK (`Directory.Members: insert`) |

---

## 2. ツール実装詳細とパラメータ契約 (リファレンス)

### 2.1. Slack アダプター (`tools/slack_tool.py`)

#### `slack_invite_user(email: str, channel: str = "#general")`
- **引数**:
  - `email`: 招待対象ユーザーのメールアドレス
  - `channel`: 参加させる初期チャンネル（デフォルト: `#general`）
- **必要 Slack OAuth スコープ**:
  - `users:read`, `users:write` または `admin.users:write`
- **戻り値 JSON**:
  ```json
  {
    "status": "invited",
    "email": "jane.doe@example.com",
    "channel": "#general",
    "slack_user_id": "U0123456789"
  }
  ```

#### `slack_send_message(channel: str, text: str)`
- **引数**:
  - `channel`: 送信先チャンネル名または ID
  - `text`: 送信本文（マークダウン対応）
- **必要 Slack OAuth スコープ**: `chat:write`, `chat:write.public`

---

### 2.2. Google Workspace アダプター (`tools/google_tool.py`)

#### `google_create_account(email: str, full_name: str, department: str)`
- **認証方式**:
  - Google Cloud サービスアカウントによるドメイン全体の委任（Domain-Wide Delegation）。
  - `GOOGLE_SERVICE_ACCOUNT_FILE` の秘密鍵を用い、`GOOGLE_ADMIN_EMAIL` の権限を委任借用して Admin SDK を実行。
- **必要 OAuth スコープ**:
  - `https://www.googleapis.com/auth/admin.directory.user`
- **戻り値 JSON**:
  ```json
  {
    "status": "created",
    "email": "jane.doe@example.com",
    "full_name": "Jane Doe",
    "department": "engineering",
    "google_id": "10987654321"
  }
  ```

#### `google_assign_group(user_email: str, group_email: str)`
- **必要 OAuth スコープ**:
  - `https://www.googleapis.com/auth/admin.directory.group.member`

---

## 3. モックモード仕様 (`MOCK_EXTERNAL_APIS=true`)

ローカル開発環境やテスト・デモ環境において、実際の外部 SaaS アカウントを消費・変更することなく安全にエンドツーエンド検証を可能にするため、デフォルトでモック分岐が有効化されている。

```python
# tools/slack_tool.py 内の実装パターン
from core.config import MOCK_EXTERNAL_APIS


async def slack_invite_user(email: str, channel: str = "#general") -> dict:
    if MOCK_EXTERNAL_APIS:
        logger.info("🎭 [MOCK] Slack invite: %s to %s", email, channel)
        return {"status": "invited (mock)", "email": email, "channel": channel, "mock": True}

    # 本番 API 呼び出し (実クレデンシャル設定時)
    ...
```

- **本設定の役割**:
  - 外部 SaaS の実クレデンシャルがない開発者でも、即座にリポジトリを起動して Webhook 受信から AI 推論、承認、ツール実行完了までのデモフローを一気通貫で確認できる。
  - レスポンスのデータ構造は本番 API と同一であり、AI Engine 側の動作検証に影響を与えない。
