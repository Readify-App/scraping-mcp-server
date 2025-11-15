# ピラティススタジオ情報取得 MCPサーバー

WordPress REST APIを使用してピラティススタジオの情報を取得するMCP（Model Context Protocol）サーバーです。

## 📋 概要

このMCPサーバーは、WordPressサイトからピラティススタジオの情報を取得するためのツールを提供します。以下の機能を利用できます：

- スタジオ一覧の取得
- スタジオ詳細情報の取得
- エリア別の検索
- ID指定での取得

## 🚀 セットアップ方法

### 1. リポジトリのクローン

```bash
git clone https://github.com/your-username/pilates-mcp-server.git
cd pilates-mcp-server
```

### 2. 依存関係のインストール

このプロジェクトは`uv`を使用して依存関係を管理しています。

```bash
# uvがインストールされていない場合
curl -LsSf https://astral.sh/uv/install.sh | sh

# 依存関係のインストール
uv sync
```

または、`pip`を使用する場合：

```bash
pip install -r requirements.txt
```

### 3. 環境変数の設定

`.env.example`をコピーして`.env`ファイルを作成します：

```bash
cp .env.example .env
```

`.env`ファイルを編集して、WordPressの認証情報を設定します：

```env
WP_SITE_URL=https://your-wordpress-site.com
WP_USERNAME=your_username
WP_APP_PASSWORD=your_app_password
```

#### WordPressアプリケーションパスワードの取得方法

1. WordPress管理画面にログイン
2. **ユーザー** → **プロフィール** に移動
3. 下にスクロールして「**アプリケーションパスワード**」セクションを探す
4. 新しいアプリケーションパスワードを作成（名前は任意、例：「MCP Server」）
5. 生成されたパスワードをコピーして`.env`ファイルの`WP_APP_PASSWORD`に設定

### 4. MCPクライアントへの登録

#### Claude Desktopの場合

`~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）または`%APPDATA%\Claude\claude_desktop_config.json`（Windows）を編集：

```json
{
  "mcpServers": {
    "pilates-studio-finder": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "/path/to/pilates-mcp-server/server.py"
      ],
      "env": {
        "WP_SITE_URL": "https://your-wordpress-site.com",
        "WP_USERNAME": "your_username",
        "WP_APP_PASSWORD": "your_app_password"
      }
    }
  }
}
```

**注意**: 環境変数は`env`セクションで直接指定することもできます。その場合、`.env`ファイルは不要です。

#### その他のMCPクライアント

各クライアントの設定方法に従って、サーバーを登録してください。

## 🔧 使用方法

### 利用可能なツール

#### 1. `pilates_list` - スタジオ一覧取得

ピラティススタジオの一覧を取得します。

**パラメータ:**
- `店舗名` (str, オプション): 店舗名で検索
- `エリア` (str, オプション): エリアで検索
- `件数` (int, デフォルト: 20): 取得件数

**使用例:**
```
スタジオ一覧を取得してください
渋谷のスタジオを10件取得してください
```

#### 2. `pilates_detail` - スタジオ詳細取得

特定のピラティススタジオの詳細情報を取得します。

**パラメータ:**
- `店舗名` (str, 必須): 店舗名

**使用例:**
```
「スタジオ名」の詳細情報を教えてください
```

#### 3. `pilates_by_id` - ID指定で取得

投稿IDを指定してスタジオ情報を取得します。

**パラメータ:**
- `投稿ID` (int, 必須): WordPressの投稿ID

**使用例:**
```
ID 123のスタジオ情報を取得してください
```

#### 4. `pilates_by_area` - エリア別検索

エリア名でピラティススタジオを検索します。

**パラメータ:**
- `エリア` (str, 必須): エリア名（例: 東京都葛飾区、渋谷、新宿など）
- `件数` (int, デフォルト: 10): 取得件数

**使用例:**
```
渋谷のスタジオを5件検索してください
```

## 🌐 一般公開の方法

### GitHubに公開する手順

#### 1. リポジトリの準備

```bash
# .gitignoreを確認（.envとdebug.logが含まれていることを確認）
cat .gitignore

# 変更をステージング
git add .

# コミット
git commit -m "Initial commit: Pilates MCP Server"

# リモートリポジトリを追加（GitHubでリポジトリを作成後）
git remote add origin https://github.com/your-username/pilates-mcp-server.git

# プッシュ
git push -u origin main
```

#### 2. リポジトリの設定

1. GitHubでリポジトリを作成
2. **Settings** → **General** → **Features** で以下を有効化：
   - Issues
   - Discussions（オプション）
3. **Settings** → **Pages** でGitHub Pagesを有効化（ドキュメント用、オプション）

#### 3. READMEの充実

- プロジェクトの説明
- セットアップ手順
- 使用例
- コントリビューション方法
- ライセンス情報

#### 4. セキュリティの確認

- ✅ `.env`ファイルが`.gitignore`に含まれている
- ✅ 認証情報がコードにハードコードされていない
- ✅ `.env.example`で必要な環境変数を説明している

### PyPIに公開する方法（オプション）

パッケージとして配布したい場合：

#### 1. `pyproject.toml`の更新

```toml
[project]
name = "pilates-mcp-server"
version = "0.1.0"
description = "WordPress REST APIを使用してピラティススタジオ情報を取得するMCPサーバー"
readme = "README.md"
requires-python = ">=3.13"
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]
license = {text = "MIT"}
dependencies = [
    "httpx>=0.28.1",
    "mcp>=1.20.0",
    "python-dotenv>=1.0.0",
]

[project.scripts]
pilates-mcp-server = "server:main"
```

#### 2. ビルドと公開

```bash
# ビルドツールのインストール
pip install build twine

# パッケージのビルド
python -m build

# PyPIにアップロード（テスト環境）
twine upload --repository-url https://test.pypi.org/legacy/ dist/*

# PyPIにアップロード（本番環境）
twine upload dist/*
```

### 他の人に使ってもらう方法

#### 方法1: GitHubリポジトリを共有

1. リポジトリを公開（Public）にする
2. READMEにセットアップ手順を記載
3. リポジトリのURLを共有

#### 方法2: パッケージとして配布

PyPIに公開すれば、以下のコマンドでインストール可能：

```bash
pip install pilates-mcp-server
```

#### 方法3: MCPサーバー一覧に登録

MCPサーバーの公式ディレクトリやコミュニティリストに登録することで、より多くの人に見つけてもらえます。

## 🔒 セキュリティに関する注意事項

1. **認証情報の管理**
   - `.env`ファイルは絶対にGitにコミットしない
   - `.gitignore`に`.env`が含まれていることを確認
   - 公開リポジトリには認証情報を含めない

2. **アプリケーションパスワード**
   - 必要最小限の権限でアプリケーションパスワードを作成
   - 定期的にパスワードをローテーション
   - 不要になったパスワードは削除

3. **環境変数の使用**
   - 本番環境では環境変数を使用
   - 開発環境では`.env`ファイルを使用
   - シークレット管理サービス（例: AWS Secrets Manager）の使用を検討

## 📝 開発

### ローカルでの実行

```bash
# 環境変数を設定
export WP_SITE_URL="https://your-site.com"
export WP_USERNAME="your_username"
export WP_APP_PASSWORD="your_password"

# サーバーを起動
uv run python server.py
```

### ログの確認

デフォルトでは`debug.log`ファイルにログが出力されます。環境変数`LOG_FILE`で変更可能です。

## 🤝 コントリビューション

プルリクエストやイシューの報告を歓迎します！

1. リポジトリをフォーク
2. 機能ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 📄 ライセンス

このプロジェクトのライセンスを指定してください（例: MIT License）

## 🙏 謝辞

- [MCP (Model Context Protocol)](https://modelcontextprotocol.io/)
- [FastMCP](https://github.com/jlowin/fastmcp)

## 📧 連絡先

質問や提案がある場合は、GitHubのIssuesまたはDiscussionsをご利用ください。

