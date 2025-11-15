# 開発環境のセットアップ

## VSCodeでの型チェックエラーを解消する方法

このプロジェクトでは、仮想環境内のパッケージを使用しています。VSCodeで型チェックエラーが表示される場合は、以下の手順で解決できます。

### 方法1: VSCodeでPythonインタープリターを選択

1. `Cmd + Shift + P` でコマンドパレットを開く
2. "Python: Select Interpreter" を選択
3. `./.venv/bin/python` を選択

### 方法2: VSCodeウィンドウを再読み込み

1. `Cmd + Shift + P` でコマンドパレットを開く
2. "Developer: Reload Window" を選択

### 方法3: 設定ファイルを確認

以下のファイルが正しく配置されているか確認してください:

- `.vscode/settings.json` - VSCode設定
- `pyrightconfig.json` - Pyright/Pylance設定

これらのファイルは既にプロジェクトに含まれています。

## 仮想環境の確認

仮想環境が正しくセットアップされているか確認:

```bash
# 仮想環境をアクティベート
source .venv/bin/activate

# パッケージが正しくインストールされているか確認
python -c "import mcp; import aiohttp; import playwright; from bs4 import BeautifulSoup; print('All packages imported successfully!')"
```

## トラブルシューティング

### エラー: "インポート XXX を解決できませんでした"

**原因:** VSCodeが仮想環境を認識していない

**解決策:**
1. VSCodeを再起動
2. Pythonインタープリターを再選択
3. `pyrightconfig.json`が正しく配置されているか確認

### 依存関係が見つからない

```bash
# 仮想環境内で再インストール
source .venv/bin/activate
pip install -r requirements.txt
```

### Playwrightブラウザがインストールされていない

```bash
source .venv/bin/activate
playwright install chromium
```

## 開発時のヒント

### デバッグ

ログファイルを確認:
```bash
tail -f debug.log
```

### テスト実行

```bash
source .venv/bin/activate
python test_server.py
```

### コードフォーマット

推奨: Black
```bash
pip install black
black server.py
```

### 型チェック

```bash
pip install pyright
pyright server.py
```
