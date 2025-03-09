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
from typing import Dict, List, Tuple, Optional, Any, Callable
from flask import request

from .config import (
    IPO_REPORTS_NEW_DIR,
    COMPARISON_DIR,
    RECENT_IPO_COMPANIES_PATH,
    ALL_COMPANIES_PATH
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

def handle_errors(func: Callable) -> Callable:
    """エラーハンドリングを行うデコレータ"""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__}の実行中にエラー: {e}", exc_info=True)
            return None, str(e), 500
    return wrapper

def extract_diff(file_old, file_new, date_old, date_new):
    """四半期報告書の差分を抽出する関数"""
    try:
        # ファイルの内容を読み込む
        with open(file_old, 'r', encoding='utf-8') as f:
            old_content = f.readlines()
        with open(file_new, 'r', encoding='utf-8') as f:
            new_content = f.readlines()
        
        # 差分を計算
        diff = difflib.unified_diff(
            old_content, 
            new_content, 
            fromfile=f'四半期報告書 {date_old}', 
            tofile=f'四半期報告書 {date_new}',
            n=3
        )
        
        # 差分テキストを結合
        diff_text = ''.join(diff)
        
        # 差分がない場合のメッセージ
        if not diff_text:
            diff_text = "両方の四半期報告書に差分はありません。"
        
        return diff_text
    except Exception as e:
        logger.error(f"差分抽出中にエラー: {e}", exc_info=True)
        return f"差分の抽出に失敗しました: {str(e)}"

def load_companies_data() -> Tuple[list, bool]:
    """企業データの読み込み"""
    try:
        # all_companies.tsvファイルを使用
        if os.path.exists(ALL_COMPANIES_PATH):
            try:
                # ファイルのエンコーディングを自動検出
                with open(ALL_COMPANIES_PATH, 'rb') as f:
                    sample = f.read(1024)
                    
                # エンコーディングを推測
                encodings = ['utf-8', 'shift-jis', 'euc-jp', 'iso-2022-jp']
                encoding = 'utf-8'  # デフォルトはUTF-8
                
                for enc in encodings:
                    try:
                        sample.decode(enc)
                        encoding = enc
                        break
                    except UnicodeDecodeError:
                        continue
                
                # ファイルを読み込む
                df = pd.read_csv(ALL_COMPANIES_PATH, sep='\t', encoding=encoding, dtype={'コード': str, '企業名': str})
                
                # 必須カラムの存在確認
                required_columns = ['コード', '企業名']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    logger.error(f"必須カラムがありません: {missing_columns}")
                    raise ValueError(f"必須カラムがありません: {missing_columns}")
                
                companies = []
                
                # 現在の年を取得
                current_year = datetime.now().year
                
                # 上場年のカラム名を確認（'上場年'または'IPO年'など）
                ipo_year_column = None
                for column in ['上場年', 'IPO年', 'ipo_year', '上場日', 'IPO日', 'ipo_date']:
                    if column in df.columns:
                        ipo_year_column = column
                        break
                
                # DataServiceから会社コードと名前のマップを取得
                company_code_name_map = DataService.get_company_code_name_map()
                
                if ipo_year_column is None:
                    logger.warning("上場年のカラムが見つかりません。すべての企業を表示します。")
                    # 上場年のカラムがない場合は、すべての企業を表示（ただし、DataServiceに存在する企業のみ）
                    for _, row in df.iterrows():
                        # 企業名が数値の場合は文字列に変換
                        company_name = row['企業名']
                        if isinstance(company_name, (int, float)):
                            company_name = str(company_name)
                        
                        company_code = str(row['コード'])
                        # DataServiceに存在する企業のみを追加
                        if company_code in company_code_name_map:
                            company = {
                                'code': company_code,
                                'name': company_name,
                                'market': row.get('市場', '不明'),
                                'industry': row.get('業種', '不明'),
                                'ipo_year': None  # 上場年がない場合はNoneを設定
                            }
                            companies.append(company)
                else:
                    # 上場年のカラムがある場合は、3年以内の企業をフィルタリング（ただし、DataServiceに存在する企業のみ）
                    for _, row in df.iterrows():
                        # 上場年を取得
                        ipo_year = None
                        if pd.notna(row[ipo_year_column]):
                            # 日付形式の場合は年だけを抽出
                            if isinstance(row[ipo_year_column], str) and '/' in row[ipo_year_column]:
                                ipo_year = int(row[ipo_year_column].split('/')[0])
                            elif isinstance(row[ipo_year_column], str) and '-' in row[ipo_year_column]:
                                ipo_year = int(row[ipo_year_column].split('-')[0])
                            else:
                                try:
                                    ipo_year = int(row[ipo_year_column])
                                except (ValueError, TypeError):
                                    ipo_year = None
                        
                        # 上場年が3年以内の企業のみを追加（ただし、DataServiceに存在する企業のみ）
                        if ipo_year is not None and current_year - ipo_year <= 3:
                            # 企業名が数値の場合は文字列に変換
                            company_name = row['企業名']
                            if isinstance(company_name, (int, float)):
                                company_name = str(company_name)
                            
                            company_code = str(row['コード'])
                            # DataServiceに存在する企業のみを追加
                            if company_code in company_code_name_map:
                                company = {
                                    'code': company_code,
                                    'name': company_name,
                                    'market': row.get('市場', '不明'),
                                    'industry': row.get('業種', '不明'),
                                    'ipo_year': ipo_year
                                }
                                companies.append(company)
                
                if not companies:
                    logger.warning("表示可能な企業が見つかりません。ダミーデータを表示します。")
                    # 企業が見つからない場合はダミーデータを作成
                    dummy_companies = [
                        {
                            'code': '0000',
                            'name': 'サンプル企業',
                            'market': 'サンプル市場',
                            'industry': 'サンプル業種',
                            'ipo_year': current_year
                        }
                    ]
                    return dummy_companies, True
                
                return companies, True
            except Exception as e:
                logger.error(f"企業データの読み込み中にエラー: {e}", exc_info=True)
                return [], False
        else:
            logger.error(f"企業データファイルが見つかりません: {ALL_COMPANIES_PATH}")
            # ダミーデータを作成
            dummy_companies = [
                {
                    'code': '0000',
                    'name': 'サンプル企業',
                    'market': 'サンプル市場',
                    'industry': 'サンプル業種'
                }
            ]
            return dummy_companies, True
    except Exception as e:
        logger.error(f"企業データの読み込み中にエラー: {e}", exc_info=True)
        return [], False

@handle_errors
def index():
    """トップページ"""
    companies, success = load_companies_data()
    
    if not success:
        return "企業データの読み込みに失敗しました", 500
    
    # 企業をフラットなリストとして返す（past_tenbaggerと同じ形式）
    # 企業名が数値の場合は文字列に変換
    for company in companies:
        if isinstance(company['name'], (int, float)):
            company['name'] = str(company['name'])
    
    # 企業を上場年が新しい順（降順）で並べる
    try:
        # 上場年がない企業は最後に表示
        def sort_key(company):
            ipo_year = company.get('ipo_year')
            if ipo_year is None:
                return -9999  # 上場年がない場合は最後に表示
            return ipo_year
        
        companies = sorted(companies, key=sort_key, reverse=True)
    except TypeError as e:
        logger.warning(f"企業のソートに失敗しました: {e}")
    
    return {
        'companies': companies
    }, None, 200

@handle_errors
def company_view(company_code):
    """企業の詳細ページ"""
    companies, success = load_companies_data()
    if not success:
        return None, "企業データの読み込みに失敗しました", 500
    
    # 企業コードで検索
    company = next((c for c in companies if c['code'] == company_code), None)
    if not company:
        # 企業コードマップから企業名を取得
        company_map = DataService.get_company_code_name_map()
        if company_code not in company_map:
            return None, "企業が見つかりません", 404
        company_name = company_map[company_code]
    else:
        company_name = company['name']
    
    # 競合企業を取得
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
    
    # チャートを生成
    chart_service = ChartService(company_code, company_name)
    charts, error = chart_service.generate_comparison_charts()
    
    if error:
        return None, error, 500
    
    data = {
        'company_code': company_code,
        'company_name': company_name,
        'company': company,
        'competitors': competitors,
        'charts': charts,
        'business_description': business_description,
        'officers_info': officers_info
    }
    
    return data, None, 200

@handle_errors
def get_securities_reports(company_code):
    """四半期報告書の一覧を取得するAPI"""
    companies, success = load_companies_data()
    if not success:
        return None, "企業データの読み込みに失敗しました", 500
    
    # 企業コードで検索
    company = next((c for c in companies if c['code'] == company_code), None)
    company_name = None
    
    if company:
        company_name = company['name']
        print(f"企業コード {company_code} の企業名: {company_name}")
    else:
        print(f"企業コード {company_code} が見つかりません。ディレクトリ検索を試みます。")
    
    # 最初から企業コードだけで検索（最も優先度高）
    code_pattern = f"{IPO_REPORTS_NEW_DIR}/{company_code}_*/quarterly_reports"
    matching_dirs = glob.glob(code_pattern)
    
    if matching_dirs:
        quarterly_reports_dir = matching_dirs[0]
        print(f"企業コードで一致するディレクトリが見つかりました: {quarterly_reports_dir}")
        
        # ディレクトリ名から企業名を抽出
        if not company_name:
            dir_name = os.path.basename(os.path.dirname(quarterly_reports_dir))
            if '_' in dir_name:
                company_name = dir_name.split('_', 1)[1]
                print(f"ディレクトリ名から企業名を抽出しました: {company_name}")
    else:
        # quarterly_reportsが見つからない場合はsecurities_registration_statementを試す
        code_pattern = f"{IPO_REPORTS_NEW_DIR}/{company_code}_*/securities_registration_statement"
        matching_dirs = glob.glob(code_pattern)
        
        if matching_dirs:
            securities_registration_statement_dir = matching_dirs[0]
            print(f"企業コードで一致するsecurities_registration_statementディレクトリが見つかりました: {securities_registration_statement_dir}")
            
            # ディレクトリ名から企業名を抽出
            if not company_name:
                dir_name = os.path.basename(os.path.dirname(securities_registration_statement_dir))
                if '_' in dir_name:
                    company_name = dir_name.split('_', 1)[1]
                    print(f"ディレクトリ名から企業名を抽出しました: {company_name}")
        else:
            # 会社名を使った検索（会社名がある場合のみ）
            if company_name:
                company_dir = f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name}"
                quarterly_reports_dir = f"{company_dir}/quarterly_reports"
                securities_registration_statement_dir = f"{company_dir}/securities_registration_statement"
                
                # quarterly_reportsディレクトリが見つからない場合
                if not os.path.exists(quarterly_reports_dir):
                    # securities_registration_statementディレクトリを試す
                    if os.path.exists(securities_registration_statement_dir):
                        quarterly_reports_dir = securities_registration_statement_dir
                    else:
                        # 会社名のパターンを変えて試す
                        possible_dirs = [
                            f"{IPO_REPORTS_NEW_DIR}/{company_code}_株式会社{company_name}/quarterly_reports",
                            f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name.replace('株式会社', '')}/quarterly_reports",
                            f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name.replace('・', '')}/quarterly_reports",
                            f"{IPO_REPORTS_NEW_DIR}/{company_code}_株式会社{company_name}/securities_registration_statement",
                            f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name.replace('株式会社', '')}/securities_registration_statement",
                            f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name.replace('・', '')}/securities_registration_statement"
                        ]
                        
                        # 可能性のあるディレクトリを試す
                        for dir_path in possible_dirs:
                            print(f"試行: {dir_path}")
                            if os.path.exists(dir_path):
                                quarterly_reports_dir = dir_path
                                print(f"代替ディレクトリが見つかりました: {quarterly_reports_dir}")
                                break
                        else:
                            # どのディレクトリも見つからなかった場合
                            return {"reports": []}, "四半期報告書またはsecurities_registration_statementディレクトリが見つかりません", 404
            else:
                # 会社名がない場合
                return {"reports": []}, "企業情報が見つかりません", 404
    
    # 四半期報告書ファイルを取得
    report_files = glob.glob(f"{quarterly_reports_dir}/*.html")
    
    if not report_files:
        # HTMLファイルがない場合はテキストファイルを試す
        report_files = glob.glob(f"{quarterly_reports_dir}/*.txt")
    
    if not report_files:
        # TSVファイルを試す
        report_files = glob.glob(f"{quarterly_reports_dir}/*.tsv")
    
    if not report_files:
        return {"reports": []}, "四半期報告書ファイルが見つかりません", 404
    
    # ファイル情報を整理
    reports = []
    for file_path in sorted(report_files):
        file_name = os.path.basename(file_path)
        # ファイル名から日付を抽出（例: 2023_Q1.html -> 2023 Q1）
        date_parts = os.path.splitext(file_name)[0].split('_')
        if len(date_parts) >= 2:
            date = f"{date_parts[0]} {date_parts[1]}"
        else:
            date = file_name
        
        reports.append({
            "file": file_path,
            "date": date
        })
    
    return {"reports": reports}, None, 200

@handle_errors
def securities_report_diff(company_code):
    """四半期報告書の差分を取得するAPI"""
    data = request.get_json()
    
    if not data or 'old_report' not in data or 'new_report' not in data:
        return None, "リクエストデータが不正です", 400
    
    old_report = data['old_report']
    new_report = data['new_report']
    old_date = data.get('old_date', '不明')
    new_date = data.get('new_date', '不明')
    
    # ファイルの存在確認
    if not os.path.exists(old_report) or not os.path.exists(new_report):
        return None, "指定されたファイルが見つかりません", 404
    
    # 差分を抽出
    diff_text = extract_diff(old_report, new_report, old_date, new_date)
    
    return {"diff_text": diff_text}, None, 200 