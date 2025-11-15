# Web Scraping MCP Server

Webページのスクレイピングを行うMCPサーバーです。通常のHTMLページとJavaScript/SPA/Reactサイトの両方に対応しています。

## 機能

### 📄 fetch_page_content
通常のHTMLページからコンテンツを取得します。高速で軽量です。

**特徴:**
- シンプルなHTTPリクエスト
- BeautifulSoupによるHTML解析
- ヘッダー、フッター、ナビゲーションを自動除外
- メインコンテンツの自動検出

**使用例:**
```
「https://example.com/article のページ内容を取得して」
```

### 🎭 fetch_page_content_with_playwright
JavaScript/SPA/Reactサイトからコンテンツを取得します。動的にレンダリングされるページに対応しています。

**特徴:**
- Playwrightによる実ブラウザレンダリング
- JavaScript実行後のコンテンツ取得
- Shadow DOM対応
- プライバシー同意ダイアログの自動処理
- メール・電話番号の自動抽出

**使用例:**
```
「https://example.com/spa-page のページ内容をPlaywrightで取得して」
```

### 🗺️ extract_site_links
公式サイトからheader/footer/navのリンクを抽出し、仮想サイトマップを作成します。

**特徴:**
- ヘッダー、フッター、ナビゲーションからリンク抽出
- 重複パターンの自動除去
- 各ページの見出し（h2/h3）を自動取得
- 同一ドメイン内のリンクのみ対象

**使用例:**
```
「https://example.com のサイト構造を教えて」
```

### 🗺️ extract_site_links_with_playwright
JavaScript/SPA/Reactサイトから動的にリンクを抽出します。

**使用例:**
```
「https://example.com のサイトマップをPlaywrightで取得して」
```

## インストール

### 🚀 1コマンドインストール（推奨）

#### macOS / Linux
```bash
curl -fsSL https://raw.githubusercontent.com/Readify-App/scraping-mcp-server/main/install.sh | bash
```

#### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/Readify-App/scraping-mcp-server/main/install.ps1 | iex
```

インストール後、**Claude Desktopを再起動**してください。

### 🔧 手動インストール

<details>
<summary>手動インストール手順を表示</summary>

#### 1. リポジトリをクローン
```bash
git clone https://github.com/Readify-App/scraping-mcp-server.git
cd scraping-mcp-server
```

#### 2. uvで依存関係をインストール
```bash
uv sync
```

#### 3. Playwrightのブラウザをインストール
```bash
uv run playwright install chromium
```

#### 4. Claude Desktop設定ファイルを編集

**macOS:**
```bash
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Linux:**
```bash
nano ~/.config/claude-desktop/claude_desktop_config.json
```

**Windows:**
```powershell
notepad %APPDATA%\Claude\claude_desktop_config.json
```

以下の内容を追加（`/path/to/scraping-mcp-server`は実際のパスに置き換え）:

```json
{
  "mcpServers": {
    "scraping-mcp-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/scraping-mcp-server",
        "run",
        "scraping-mcp-server"
      ]
    }
  }
}
```

#### 5. Claude Desktopを再起動

</details>

## 使い方

Claude Desktopで以下のように質問してください:

### 📄 通常のHTMLページを取得
```
「https://example.com/article のページ内容を取得して」
```

### 🎭 JavaScript/SPAページを取得
```
「https://example.com/spa-page のページ内容をPlaywrightで取得して」
```

### 🗺️ サイト構造を分析
```
「https://example.com のサイト構造を教えて」
```

## ツールの選択ガイド

| ツール | 用途 | 例 |
|--------|------|-----|
| **fetch_page_content** | 静的なHTMLページ | ブログ記事、ニュースサイト、Wikipediaなど |
| **fetch_page_content_with_playwright** | 動的なページ | React/Vue/Angular製のSPA、認証ダイアログがあるページ |
| **extract_site_links** | 静的サイトの構造分析 | 企業サイト、公式サイトのナビゲーション |
| **extract_site_links_with_playwright** | 動的サイトの構造分析 | SPAのナビゲーション、動的メニュー |

## トラブルシューティング

### ❌ Playwrightが動かない場合

```bash
# ブラウザを再インストール
uv run playwright install --force chromium

# システムの依存関係を確認（Linux）
uv run playwright install-deps
```

### 📝 ログの確認

```bash
# インストールディレクトリで
tail -f debug.log
```

### 🔄 設定のリセット

もう一度インストールスクリプトを実行してください:

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/Readify-App/scraping-mcp-server/main/install.sh | bash
```

**Windows:**
```powershell
irm https://raw.githubusercontent.com/Readify-App/scraping-mcp-server/main/install.ps1 | iex
```

## 制限事項

- ⚠️ PDFファイルには対応していません
- ⚠️ ログインが必要なページには対応していません
- ⚠️ 複数ページの同時スクレイピングには制限があります（最大5ブラウザ）

## ライセンス

MIT

## 開発者向け情報

### ファイル構成

```
scraping-mcp-server/
├── .gitignore           # 固定（ログファイル除外）
├── pyproject.toml       # 固定（パッケージ設定）
├── server.py            # ツール定義（メインロジック）
├── main.py              # 固定（エントリーポイント）
├── install.sh           # macOS/Linux自動インストーラー
├── install.ps1          # Windows自動インストーラー
└── uv.lock              # 自動生成
```

### ローカル開発

```bash
# 依存関係のインストール
uv sync

# サーバーをテスト実行
uv run scraping-mcp-server

# Playwrightブラウザのインストール
uv run playwright install chromium
```
