# Pilates MCP Server インストーラー (Windows)
# 管理者権限で実行する必要はありません

Write-Host "🚀 Pilates MCP Server インストーラー" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. uvのインストール確認
Write-Host "📦 Step 1/3: uvのインストール確認..." -ForegroundColor Yellow
try {
    $uvVersion = uv --version 2>$null
    Write-Host "✅ uvは既にインストールされています" -ForegroundColor Green
} catch {
    Write-Host "uvをインストールしています..." -ForegroundColor Yellow
    irm https://astral.sh/uv/install.ps1 | iex
    Write-Host "✅ uvをインストールしました" -ForegroundColor Green
}

# 2. 設定ファイルのパス
Write-Host ""
Write-Host "⚙️  Step 2/3: Claude Desktop設定ファイルの更新..." -ForegroundColor Yellow
$configPath = "$env:APPDATA\Claude\claude_desktop_config.json"

# 3. 設定ファイルがなければ作成
if (!(Test-Path $configPath)) {
    Write-Host "設定ファイルを作成しています..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path (Split-Path $configPath) | Out-Null
    @{mcpServers = @{}} | ConvertTo-Json | Out-File -FilePath $configPath -Encoding UTF8
}

# 4. 既存の設定を読み込んで追加
Write-Host "MCPサーバーを設定ファイルに追加しています..." -ForegroundColor Yellow
$config = Get-Content $configPath -Raw | ConvertFrom-Json

if (!$config.mcpServers) {
    $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue @{} -Force
}

$config.mcpServers | Add-Member -NotePropertyName "pilates-finder" -NotePropertyValue @{
    command = "uvx"
    args = @("pilates-mcp-server")
} -Force

$config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8
Write-Host "✅ 設定ファイルを更新しました" -ForegroundColor Green

# 5. Claude Desktop再起動
Write-Host ""
Write-Host "🔄 Step 3/3: Claude Desktopを再起動..." -ForegroundColor Yellow
$claudeProcess = Get-Process -Name "Claude" -ErrorAction SilentlyContinue
if ($claudeProcess) {
    Stop-Process -Name "Claude" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Start-Process "Claude" -ErrorAction SilentlyContinue
    Write-Host "✅ Claude Desktopを再起動しました" -ForegroundColor Green
} else {
    Write-Host "ℹ️  Claude Desktopは起動していません" -ForegroundColor Blue
    Write-Host "👉 Claude Desktopを起動してください" -ForegroundColor Blue
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✨ インストール完了！" -ForegroundColor Green
Write-Host ""
Write-Host "📋 次のステップ：" -ForegroundColor Yellow
Write-Host "1. Claude Desktopを起動（または再起動）"
Write-Host "2. Claudeに「ピラティススタジオを検索して」と話しかける"
Write-Host ""
Write-Host "🎉 お疲れ様でした！" -ForegroundColor Green
