#!/usr/bin/env python3
"""
Google Sheets読み込み機能のテストスクリプト
"""

import asyncio
import json
import sys
from pathlib import Path

# server.pyの関数をインポート
sys.path.insert(0, str(Path(__file__).parent))
from server import read_google_sheet

async def test_read_sheet():
    """スプレッドシートを読み込むテスト"""
    
    # テスト用のスプレッドシートID
    spreadsheet_id = "17kC3_9nof1m2ReJo-Zq6fX1r42MbbjWQQS78GY54ahw"
    
    print("=" * 60)
    print("Google Sheets読み込みテスト")
    print("=" * 60)
    print(f"スプレッドシートID: {spreadsheet_id}")
    print()
    
    try:
        # テスト1: シート全体を読み込む
        print("【テスト1】シート全体を読み込む...")
        result1 = await read_google_sheet(
            spreadsheet_id=spreadsheet_id,
            range_name="",
            sheet_name=""
        )
        data1 = json.loads(result1)
        if data1.get("success"):
            print(f"✅ 成功: {data1.get('row_count')}行のデータを取得")
            print(f"   ヘッダー数: {data1.get('header_count')}")
            print(f"   利用可能なシート: {', '.join(data1.get('sheet_names', []))}")
            if data1.get('data'):
                print(f"\n   最初の3行のデータ:")
                for i, row in enumerate(data1.get('data', [])[:3], 1):
                    print(f"   行{i}: {json.dumps(row, ensure_ascii=False)}")
        else:
            print(f"❌ 失敗: {data1.get('message', 'Unknown error')}")
        print()
        
        # テスト2: 範囲を指定して読み込む
        print("【テスト2】範囲を指定して読み込む (A1:C10)...")
        result2 = await read_google_sheet(
            spreadsheet_id=spreadsheet_id,
            range_name="A1:C10",
            sheet_name=""
        )
        data2 = json.loads(result2)
        if data2.get("success"):
            print(f"✅ 成功: {data2.get('row_count')}行のデータを取得")
        else:
            print(f"❌ 失敗: {data2.get('message', 'Unknown error')}")
        print()
        
        # テスト3: シート名を指定して読み込む
        print("【テスト3】シート名を指定して読み込む...")
        if data1.get("sheet_names"):
            first_sheet = data1.get("sheet_names")[0]
            print(f"   シート名: {first_sheet}")
            result3 = await read_google_sheet(
                spreadsheet_id=spreadsheet_id,
                range_name="",
                sheet_name=first_sheet
            )
            data3 = json.loads(result3)
            if data3.get("success"):
                print(f"✅ 成功: {data3.get('row_count')}行のデータを取得")
            else:
                print(f"❌ 失敗: {data3.get('message', 'Unknown error')}")
        else:
            print("⚠️  シート名が取得できませんでした")
        print()
        
        print("=" * 60)
        print("テスト完了")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_read_sheet())
