# Pilates MCP Server - インストールガイド

Claudeでピラティススタジオを検索できるようにするツールです。

## 📥 インストール方法（1コマンドだけ！）

### macOS / Linux

ターミナルを開いて、以下をコピー＆ペーストして Enter キーを押してください：

```bash
curl -sSL https://raw.githubusercontent.com/Readify-App/pilates-mcp-server/main/install.sh | bash
```

### Windows

PowerShellを**管理者権限なしで**開いて、以下をコピー＆ペーストして Enter キーを押してください：

```powershell
irm https://raw.githubusercontent.com/Readify-App/pilates-mcp-server/main/install.ps1 | iex
```

## ✅ インストール後

1. Claude Desktopを起動（または再起動）
2. Claudeに話しかけてみてください：
   - 「渋谷のピラティススタジオを教えて」
   - 「新宿エリアのスタジオを5件検索して」

## ❓ うまく動かない場合

1. Claude Desktopを完全に終了して、もう一度起動してみてください
2. ターミナル（またはPowerShell）を再起動してから、インストールコマンドを再実行してください
3. それでも動かない場合は [Issues](https://github.com/Readify-App/pilates-mcp-server/issues) で質問してください

## 🗑️ アンインストール方法

### macOS / Linux

設定ファイルを編集：
```bash
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

`"pilates-finder"` の行を削除して保存してください。

### Windows

設定ファイルを編集：
```powershell
notepad $env:APPDATA\Claude\claude_desktop_config.json
```

`"pilates-finder"` の行を削除して保存してください。

## 📝 使い方

Claudeに以下のように話しかけてください：

- 「ピラティススタジオを検索して」
- 「渋谷のピラティススタジオを10件教えて」
- 「〇〇スタジオの詳細情報を教えて」
- 「新宿エリアのスタジオを探して」

## 🔒 プライバシー

このツールは以下の情報のみを使用します：
- WordPressサイトからの公開情報のみ
- あなたのローカル環境で動作します
- データは外部に送信されません

## 📧 サポート

質問や問題がある場合は [Issues](https://github.com/Readify-App/pilates-mcp-server/issues) でお知らせください。
