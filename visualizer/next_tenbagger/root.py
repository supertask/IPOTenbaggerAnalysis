import os
import logging
import pandas as pd
import json
import glob
import difflib
from datetime import datetime, timedelta
from pathlib import Path
import matplotlib
import matplotlib.font_manager as fm
from functools import wraps
from typing import Dict, List, Tuple, Optional, Any

from .config import (
    IPO_REPORTS_NEW_DIR,
    COMPARISON_DIR,
    RECENT_IPO_COMPANIES_PATH
)
from .data_service import DataService
from .chart_service import ChartService

# ロギングの設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 日本語フォントの設定
def setup_japanese_font():
    """日本語フォントの設定"""
    matplotlib.use('Agg')
    matplotlib.rcParams['font.family'] = 'IPAexGothic'

# 日本語フォントの設定を適用
setup_japanese_font()

def handle_errors(func):
    """エラーハンドリングを行うデコレータ"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__}の実行中にエラー: {e}", exc_info=True)
            return str(e), 500
    return wrapper

def extract_diff(file_old, file_new, date_old, date_new):
    """四半期報告書の差分を抽出する関数"""
    try:
        # ファイルのエンコーディングを確認
        encoding_old = 'utf-16' if 'UTF-16' in os.popen(f'file "{file_old}"').read() else 'utf-8'
        encoding_new = 'utf-16' if 'UTF-16' in os.popen(f'file "{file_new}"').read() else 'utf-8'
        
        # ファイルを読み込む
        df_old = pd.read_csv(file_old, delimiter="\t", encoding=encoding_old, dtype=str, on_bad_lines='skip')
        df_new = pd.read_csv(file_new, delimiter="\t", encoding=encoding_new, dtype=str, on_bad_lines='skip')

        # 指定した要素ID以降のデータを取得
        target_id = "jpcrp_qcor:BusinessResultsOfReportingCompanyTextBlock"
        start_index_old = df_old[df_old["要素ID"] == target_id].index
        start_index_new = df_new[df_new["要素ID"] == target_id].index

        if len(start_index_old) == 0 or len(start_index_new) == 0:
            logger.warning("指定した要素IDが見つかりませんでした。")
            return "指定した要素IDが見つかりませんでした。"
            
        # 指定した要素ID以降のデータをフィルタリング
        df_old_filtered = df_old.loc[start_index_old[0]:, ["要素ID", "項目名", "値"]].reset_index(drop=True)
        df_new_filtered = df_new.loc[start_index_new[0]:, ["要素ID", "項目名", "値"]].reset_index(drop=True)

        # 要素IDごとにグループ化し、最初の値を取得
        dict_old = df_old_filtered.groupby("要素ID").first().to_dict(orient="index")
        dict_new = df_new_filtered.groupby("要素ID").first().to_dict(orient="index")

        # 両方に存在する要素IDだけ比較
        common_keys = set(dict_old.keys()) & set(dict_new.keys())
        
        added_texts = ""
        removed_texts = ""

        for key in common_keys:
            item_name = dict_new[key]["項目名"] if key in dict_new else dict_old[key]["項目名"]
            if item_name is not None:
                item_name = str(item_name).replace(" [テキストブロック]", "")  # [テキストブロック] を削除
            v_old = str(dict_old[key]["値"]) if dict_old[key]["値"] is not None else ""
            v_new = str(dict_new[key]["値"]) if dict_new[key]["値"] is not None else ""
            diff = difflib.ndiff(v_old, v_new)
            added = [line[2:] for line in diff if line.startswith("+ ")]
            removed = [line[2:] for line in diff if line.startswith("- ")]
            
            if added or removed:
                if added:
                    if item_name:
                        added_texts += f"項目名: {item_name}\n"
                    else:
                        added_texts += f"要素ID: {key}\n"
                    added_texts += "".join(added) + "\n"
                    added_texts += "-\n"
                if removed:
                    if item_name:
                        removed_texts += f"項目名: {item_name}\n"
                    else:
                        removed_texts += f"要素ID: {key}\n"
                    removed_texts += "".join(removed) + "\n"
                    removed_texts += "-\n"
        
        # 日付オブジェクトを作成
        try:
            date_old_obj = datetime.strptime(date_old, "%Y-%m-%d")
            date_new_obj = datetime.strptime(date_new, "%Y-%m-%d")
        except ValueError:
            date_old_obj = datetime.strptime(date_old, "%Y%m%d")
            date_new_obj = datetime.strptime(date_new, "%Y%m%d")

        texts = ""
        if added_texts or removed_texts:
            if added_texts:
                texts += f"「{date_old_obj.strftime('%Y年%m月%d日')} -> {date_new_obj.strftime('%Y年%m月%d日')} 」で追加された項目：\n"
                texts += "-" * 3 + "\n"
                texts += added_texts
                texts += "-" * 3 + "\n"
            if removed_texts:
                texts += f"「{date_old_obj.strftime('%Y年%m月%d日')} -> {date_new_obj.strftime('%Y年%m月%d日')} 」で削除された項目：\n"
                texts += "-" * 3 + "\n"
                texts += removed_texts
                texts += "-" * 3 + "\n"
        else:
            texts = "差分はありませんでした。"

        return texts
    except Exception as e:
        logger.error(f"差分抽出中にエラー: {e}", exc_info=True)
        return f"差分抽出中にエラーが発生しました: {str(e)}"

# ビジネスロジック関数
def index():
    """トップページ - 直近3年でIPOした企業一覧"""
    companies = DataService.get_recent_ipo_companies()
    
    # テンプレートの絶対パスを使用
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'index.html')
    print(f"next_tenbagger: テンプレートパス = {template_path}")
    print(f"next_tenbagger: テンプレートが存在するか = {os.path.exists(template_path)}")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
        print(f"next_tenbagger: テンプレートの先頭100文字 = {template_content[:100]}")
    
    return companies, None, 200

def company_view(company_code):
    """企業の詳細ページ"""
    company_map = DataService.get_company_code_name_map()
    
    if company_code not in company_map:
        return None, "企業が見つかりません", 404
    
    company_name = company_map[company_code]
    competitors = DataService.get_competitors(company_code)
    
    # 事業の内容を取得
    business_description = DataService.get_business_description(company_code)
    
    # 競合企業の事業の内容を取得
    for competitor in competitors:
        competitor['business_description'] = DataService.get_business_description(competitor['code'])
    
    # 役員情報を取得
    officers_info = DataService.get_officers_info(company_code)
    
    # 競合企業の役員情報を取得
    for competitor in competitors:
        competitor['officers_info'] = DataService.get_officers_info(competitor['code'])
    
    chart_service = ChartService(company_code, company_name)
    charts, error = chart_service.generate_comparison_charts()
    
    if error:
        return None, error, 500
    
    data = {
        'company_code': company_code,
        'company_name': company_name,
        'competitors': competitors,
        'charts': charts,
        'business_description': business_description,
        'officers_info': officers_info
    }
    
    return data, None, 200

def get_securities_reports(company_code):
    """四半期報告書の一覧を取得するAPI"""
    company_map = DataService.get_company_code_name_map()
    
    if company_code not in company_map:
        return {"error": "企業が見つかりません"}, 404
    
    company_name = company_map[company_code]
    company_dir = f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name}"
    
    # 四半期報告書ディレクトリを確認
    quarterly_reports_dir = f"{company_dir}/quarterly_securities_reports"
    if not os.path.exists(quarterly_reports_dir):
        return {"reports": []}, 200
    
    # 四半期報告書ファイルを取得
    report_files = sorted(glob.glob(f"{quarterly_reports_dir}/*.tsv"))
    
    reports = []
    for file_path in report_files:
        file_name = os.path.basename(file_path)
        # ファイル名から日付を抽出（例: 2019-05-30_四半期報告書.tsv）
        date_part = file_name.split('_')[0]
        reports.append({
            "file": file_name,
            "date": date_part,
            "path": file_path
        })
    
    return {"reports": reports}, 200

def get_securities_report_diff(company_code, data):
    """四半期報告書の差分を計算するAPI"""
    if not data or 'old_report' not in data or 'new_report' not in data or 'old_date' not in data or 'new_date' not in data:
        return {"error": "必要なパラメータが不足しています"}, 400
    
    company_map = DataService.get_company_code_name_map()
    
    if company_code not in company_map:
        return {"error": "企業が見つかりません"}, 404
    
    company_name = company_map[company_code]
    company_dir = f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name}"
    quarterly_reports_dir = f"{company_dir}/quarterly_securities_reports"
    
    old_report_path = f"{quarterly_reports_dir}/{data['old_report']}"
    new_report_path = f"{quarterly_reports_dir}/{data['new_report']}"
    
    if not os.path.exists(old_report_path) or not os.path.exists(new_report_path):
        return {"error": "指定された四半期報告書が見つかりません"}, 404
    
    # 差分を計算
    diff_text = extract_diff(old_report_path, new_report_path, data['old_date'], data['new_date'])
    
    return {"diff_text": diff_text}, 200 