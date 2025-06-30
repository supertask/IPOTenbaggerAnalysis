#!/usr/bin/env python3
"""
EDINETインクリメンタル更新システムのテストスクリプト

使用方法:
    python3 test_incremental_update.py [オプション]

オプション:
    --status    : キャッシュ状態を表示
    --test      : インクリメンタル更新をテスト実行
"""

import sys
import os
import argparse
from datetime import datetime

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from collectors.edinet_report_downloader import EdinetReportDownloader

def main():
    parser = argparse.ArgumentParser(description='EDINETインクリメンタル更新システムのテスト')
    parser.add_argument('--status', action='store_true', help='キャッシュ状態を表示')
    parser.add_argument('--test', action='store_true', help='インクリメンタル更新をテスト実行')
    parser.add_argument('--companies', type=str, help='特定企業のみ対象（カンマ区切り）')
    
    args = parser.parse_args()
    
    # EDINET downloaderを初期化
    try:
        downloader = EdinetReportDownloader()
        print(f"🚀 EDINETダウンローダー初期化完了")
        print(f"📅 実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    except Exception as e:
        print(f"❌ 初期化エラー: {e}")
        print("EDINET_API_KEYが設定されているか確認してください")
        return 1
    
    # コマンドライン引数に応じて処理を実行
    if args.status:
        print("=== キャッシュ状態確認 ===")
        downloader.show_cache_status()
            
    elif args.test:
        print("=== インクリメンタル更新テスト ===")
        print("現在のキャッシュ状態:")
        downloader.show_cache_status()
        print()
        
        try:
            # テスト企業のみで実行（高速化のため）
            test_companies = None
            if args.companies:
                company_codes = args.companies.split(',')
                print(f"🎯 対象企業: {company_codes}")
                # 実際の企業リスト形式に変換（必要に応じて実装）
                # test_companies = [[(code.strip(), "テスト企業")] for code in company_codes]
            
            print("🔄 インクリメンタル更新を実行中...")
            start_time = datetime.now()
            
            if test_companies:
                downloader.save_securities_reports(companies_list=test_companies)
            else:
                downloader.save_securities_reports()
            
            end_time = datetime.now()
            elapsed = (end_time - start_time).total_seconds()
            
            print(f"✅ 更新完了（実行時間: {elapsed:.1f}秒）")
            print("\n=== 更新後のキャッシュ状態 ===")
            downloader.show_cache_status()
            
        except Exception as e:
            print(f"❌ インクリメンタル更新エラー: {e}")
            return 1
    
    else:
        # デフォルト: 使用方法を表示
        print("📖 EDINETインクリメンタル更新システム")
        print()
        print("使用可能なオプション:")
        print("  --status   : キャッシュ状態を表示")
        print("  --test     : インクリメンタル更新をテスト実行")
        print()
        print("例:")
        print("  python3 test_incremental_update.py --status")
        print("  python3 test_incremental_update.py --test")
        print()
        
        # 現在の状態も表示
        print("=== 現在のキャッシュ状態 ===")
        downloader.show_cache_status()
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 