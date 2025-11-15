# 🚀 クイックスタート - 5分で始める

## ✅ 現在の状態

すべてのセットアップが完了しています!

- ✅ 依存関係インストール済み
- ✅ Playwrightブラウザインストール済み
- ✅ サーバー動作確認済み

## 📝 次のステップ（3つだけ！）

### ステップ1: Claude Desktop設定ファイルを編集

```bash
# 設定ファイルを開く
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**既に他のMCPサーバーがある場合:**
```json
{
  "mcpServers": {
    "pilates-finder": {
      "command": "uv",
      "args": ["--directory", "/path/to/pilates-mcp-server", "run", "server.py"]
    },
    "scraping": {
      "command": "/Users/yuta/Desktop/02_開発/scraping-mcp-server/.venv/bin/python",
      "args": ["/Users/yuta/Desktop/02_開発/scraping-mcp-server/server.py"]
    }
  }
}
```

**まだMCPサーバーを設定していない場合:**
```json
{
  "mcpServers": {
    "scraping": {
      "command": "/Users/yuta/Desktop/02_開発/scraping-mcp-server/.venv/bin/python",
      "args": ["/Users/yuta/Desktop/02_開発/scraping-mcp-server/server.py"]
    }
  }
}
```

### ステップ2: Claude Desktopを再起動

1. Claude Desktopを完全に終了
2. 再度起動

### ステップ3: テスト!

Claude Desktopで以下を試してみてください:

```
https://example.com のページ内容を取得してください
```

## 🎯 使用例

### 基本的な使い方
```
https://news.example.com/article のニュース記事を要約して
```

### JavaScript/SPAサイトの場合
```
https://react-app.example.com のページ内容をPlaywrightで取得して
```

### 複数ページの比較
```
以下の2つのページを比較してください:
- https://site1.com
- https://site2.com
```

## 🆘 問題が発生したら?

### ツールが表示されない場合:

1. 設定ファイルを確認:
```bash
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

2. Claude Desktopを完全再起動

### エラーが出る場合:

ログを確認:
```bash
tail -f /Users/yuta/Desktop/02_開発/scraping-mcp-server/debug.log
```

## 📚 もっと詳しく知りたい?

- 詳細なドキュメント: `USAGE.md`
- プロジェクト概要: `README.md`

## ✨ 完成!

おめでとうございます!これで、Claude DesktopでWebスクレイピングができるようになりました!
