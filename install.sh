#!/bin/bash
set -e

echo "🚀 Pilates MCP Server インストーラー"
echo "========================================"
echo ""

# 1. uvのインストール確認
echo "📦 Step 1/4: uvのインストール確認..."
if ! command -v uv &> /dev/null; then
    echo "uvをインストールしています..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo "✅ uvをインストールしました"
else
    echo "✅ uvは既にインストールされています"
fi

# 2. jqのインストール確認
echo ""
echo "📦 Step 2/4: jqのインストール確認..."
if ! command -v jq &> /dev/null; then
    echo "jqをインストールしています..."
    if command -v brew &> /dev/null; then
        brew install jq
        echo "✅ jqをインストールしました"
    else
        echo "⚠️  Homebrewがインストールされていません"
        echo "👉 https://brew.sh からHomebrewをインストールしてください"
        echo ""
        echo "Homebrewインストール後、再度このスクリプトを実行してください："
        echo "curl -sSL https://raw.githubusercontent.com/Readify-App/pilates-mcp-server/main/install.sh | bash"
        exit 1
    fi
else
    echo "✅ jqは既にインストールされています"
fi

# 3. 設定ファイルのパス
echo ""
echo "⚙️  Step 3/4: Claude Desktop設定ファイルの更新..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    CONFIG_FILE="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
else
    CONFIG_FILE="$HOME/.config/Claude/claude_desktop_config.json"
fi

# 4. 設定ファイルがなければ作成
if [ ! -f "$CONFIG_FILE" ]; then
    echo "設定ファイルを作成しています..."
    mkdir -p "$(dirname "$CONFIG_FILE")"
    echo '{"mcpServers":{}}' > "$CONFIG_FILE"
fi

# 5. jqで設定を追加（既存の設定を保持）
echo "MCPサーバーを設定ファイルに追加しています..."
jq '.mcpServers["pilates-finder"] = {
  "command": "uvx",
  "args": ["pilates-mcp-server"]
}' "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"

echo "✅ 設定ファイルを更新しました"

# 6. Claude Desktop再起動
echo ""
echo "🔄 Step 4/4: Claude Desktopを再起動..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    if pgrep -x "Claude" > /dev/null; then
        killall Claude 2>/dev/null || true
        sleep 1
        open -a Claude 2>/dev/null || true
        echo "✅ Claude Desktopを再起動しました"
    else
        echo "ℹ️  Claude Desktopは起動していません"
        echo "👉 Claude Desktopを起動してください"
    fi
else
    echo "ℹ️  手動でClaude Desktopを再起動してください"
fi

echo ""
echo "========================================"
echo "✨ インストール完了！"
echo ""
echo "📋 次のステップ："
echo "1. Claude Desktopを起動（または再起動）"
echo "2. Claudeに「ピラティススタジオを検索して」と話しかける"
echo ""
echo "🎉 お疲れ様でした！"
