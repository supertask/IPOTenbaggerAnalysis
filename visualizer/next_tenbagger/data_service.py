from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import json
import logging
import glob
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import re

from .config import (
    IPO_REPORTS_NEW_DIR,
    COMPARISON_DIR,
    METRIC_ALIASES,
    RECENT_IPO_COMPANIES_PATH
)

# IPO_REPORTS_DIRを追加
IPO_REPORTS_DIR = Path(__file__).parent.parent.parent / 'data/output/edinet_db/ipo_reports'

# カラーフォーマッターの設定
class ColoredFormatter(logging.Formatter):
    """ログメッセージに色を付けるフォーマッター"""
    
    COLORS = {
        'WARNING': '\033[0;33m',  # 黄色
        'ERROR': '\033[0;31m',    # 赤
        'CRITICAL': '\033[0;35m', # マゼンタ
    }

    def format(self, record):
        # ログレベルに応じた色を選択（DEBUGとINFOは色なし）
        color = self.COLORS.get(record.levelname, '')
        # 元のメッセージをフォーマット
        message = super().format(record)
        # 色を適用（色が設定されている場合のみリセット）
        if color:
            return f"{color}{message}\033[0m"
        return message

# ロガーの設定
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class DataService:
    @staticmethod
    def get_company_code_name_map() -> Dict[str, str]:
        """すべての企業コードと名前のマッピングを取得"""
        company_map = {}
        
        try:
            # IPO_REPORTS_NEW_DIRからディレクトリ名を取得
            if os.path.exists(IPO_REPORTS_NEW_DIR):
                for company_dir in os.listdir(IPO_REPORTS_NEW_DIR):
                    if os.path.isdir(os.path.join(IPO_REPORTS_NEW_DIR, company_dir)):
                        # ディレクトリ名から企業コードと名前を抽出（例: 1234_企業名）
                        parts = company_dir.split('_', 1)
                        if len(parts) == 2:
                            code, name = parts
                            company_map[code] = name
            else:
                logger.warning(f"ディレクトリが存在しません: {IPO_REPORTS_NEW_DIR}")
        except Exception as e:
            logger.error(f"企業コードと名前のマッピング取得中にエラー: {e}", exc_info=True)
        
        return company_map

    @staticmethod
    def get_recent_ipo_companies() -> List[Dict[str, Any]]:
        """直近3年でIPOした企業のリストを取得"""
        companies = []
        
        try:
            # 直近3年のIPO企業リストを読み込む
            if os.path.exists(RECENT_IPO_COMPANIES_PATH):
                df = pd.read_csv(RECENT_IPO_COMPANIES_PATH, sep='\t')
                required_columns = ['企業名', 'コード', 'IPO日']
                
                if all(col in df.columns for col in required_columns):
                    # 現在の日付を取得
                    current_date = datetime.now()
                    # 3年前の日付を計算
                    three_years_ago = current_date - timedelta(days=3*365)
                    
                    # IPO日を日付型に変換
                    df['IPO日'] = pd.to_datetime(df['IPO日'], errors='coerce')
                    
                    # 直近3年以内にIPOした企業をフィルタリング
                    recent_ipo_df = df[df['IPO日'] >= three_years_ago]
                    
                    for _, row in recent_ipo_df.iterrows():
                        code = str(row['コード']).split('.')[0]
                        companies.append({
                            'code': code,
                            'name': row['企業名'],
                            'ipo_date': row['IPO日'].strftime('%Y-%m-%d') if pd.notna(row['IPO日']) else None
                        })
                    
                    logger.info(f"直近3年でIPOした企業数: {len(companies)}")
                else:
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    logger.warning(f"recent_ipo_companies.tsvに必要な列がありません: {missing_columns}")
            else:
                logger.warning(f"ファイルが存在しません: {RECENT_IPO_COMPANIES_PATH}")
                
                # ファイルが存在しない場合は、IPO_REPORTS_NEW_DIRから企業を取得
                company_map = DataService.get_company_code_name_map()
                companies = [{'code': code, 'name': name} for code, name in company_map.items()]
        except Exception as e:
            logger.error(f"直近IPO企業の取得中にエラー: {e}", exc_info=True)
            
            # エラーが発生した場合は、IPO_REPORTS_NEW_DIRから企業を取得
            company_map = DataService.get_company_code_name_map()
            companies = [{'code': code, 'name': name} for code, name in company_map.items()]
        
        return companies

    @staticmethod
    def get_competitors(company_code: str) -> List[Dict[str, str]]:
        """競合他社のリストを取得"""
        comparison_files = sorted(glob.glob(f"{COMPARISON_DIR}/companies_*.tsv"), reverse=True)
        
        if not comparison_files:
            return []
        
        try:
            # 全てのファイルを読み込んで統合（空のファイルはスキップ）
            dfs = []
            for file in comparison_files:
                if os.path.getsize(file) > 0:  # 空のファイルをスキップ
                    try:
                        df = pd.read_csv(file, sep='\t')
                        dfs.append(df)
                    except Exception as e:
                        logger.warning(f"ファイル {file} の読み込み中にエラー: {e}")
            
            if not dfs:
                logger.info("有効な競合企業情報ファイルが見つかりません")
                return []
                
            df = pd.concat(dfs, ignore_index=True)
            
            # 重複を削除（同じコードの企業は最新のデータを保持）
            df = df.drop_duplicates(subset=['コード'], keep='first')
            
            # 企業コードに一致する行を探す
            company_row = df[df['コード'].astype(str) == str(company_code)]
            
            if company_row.empty or pd.isna(company_row['競合リスト'].values[0]):
                logger.info(f"企業コード {company_code} の競合企業情報が見つかりません")
                return []
            
            return json.loads(company_row['競合リスト'].values[0])
        except Exception as e:
            logger.error(f"競合他社情報の取得中にエラー: {e}", exc_info=True)
            return []

    @staticmethod
    def get_company_data(company_code: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """企業の財務データを取得"""
        try:
            company_map = DataService.get_company_code_name_map()
            
            if company_code not in company_map:
                return None, "企業が見つかりません"
            
            company_name = company_map[company_code]
            company_dir = f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name}"
            
            # 有価証券届出書と有価証券報告書の両方のデータを取得
            securities_registration_data = None
            annual_report_data = None
            
            # 有価証券届出書ディレクトリを確認
            securities_registration_statement_dir = f"{company_dir}/securities_registration_statement"
            securities_registration_file_path = None
            
            # 有価証券届出書が存在する場合はそれを読み込む
            if os.path.exists(securities_registration_statement_dir):
                logger.info(f"有価証券届出書ディレクトリが見つかりました: {securities_registration_statement_dir}")
                
                # 有価証券届出書ファイルを取得
                report_files = sorted(glob.glob(f"{securities_registration_statement_dir}/*.tsv"))
                
                if report_files:
                    # 最新の有価証券届出書を使用
                    latest_report = report_files[-1]
                    securities_registration_file_path = latest_report
                    
                    # 財務データを読み込む
                    securities_registration_data = DataService._read_financial_file(latest_report)
            
            # 有価証券報告書を探す
            annual_report_file_paths = []
            
            # ipo_reports_newにデータがない場合は、ipo_reportsを試す
            old_company_pattern = f"{IPO_REPORTS_DIR}/{company_code}_*"
            old_company_dirs = glob.glob(old_company_pattern)
            
            if old_company_dirs:
                old_company_dir = old_company_dirs[0]
                logger.info(f"ipo_reportsディレクトリが見つかりました: {old_company_dir}")
                
                # 有価証券報告書ディレクトリを確認
                annual_reports_dir = f"{old_company_dir}/annual_securities_reports"
                
                if os.path.exists(annual_reports_dir):
                    logger.info(f"有価証券報告書ディレクトリが見つかりました: {annual_reports_dir}")
                    
                    # 有価証券報告書ファイルを取得（全てのファイルを取得）
                    report_files = sorted(glob.glob(f"{annual_reports_dir}/*.tsv"))
                    
                    if report_files:
                        annual_report_file_paths = report_files
                        
                        # 全ての有価証券報告書データを結合
                        all_annual_reports_data = []
                        for report_file in report_files:
                            report_data = DataService._read_financial_file(report_file)
                            if report_data is not None:
                                # ファイル名から日付を抽出して列を追加
                                file_name = os.path.basename(report_file)
                                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file_name)
                                report_date = date_match.group(1) if date_match else None
                                
                                report_data["annual_report_date"] = report_date
                                all_annual_reports_data.append(report_data)
                        
                        # 全てのデータを結合
                        if all_annual_reports_data:
                            annual_report_data = pd.concat(all_annual_reports_data, ignore_index=True)
            
            # 条件①: 有価証券届出書に5年分のデータが存在するか確認
            use_securities_registration_data = False
            if securities_registration_data is not None:
                # 売上高の5年分のデータが存在するか確認
                has_five_years_data = True
                for i in range(1, 6):
                    pattern = f"Prior{i}YearDuration_NonConsolidatedMember"
                    rows = securities_registration_data[securities_registration_data["コンテキストID"].str.contains(pattern, na=False)]
                    rows = rows[rows["要素ID"] == "jpcrp_cor:NetSalesSummaryOfBusinessResults"]
                    if rows.empty:
                        has_five_years_data = False
                        break
                
                if has_five_years_data:
                    use_securities_registration_data = True
                    logger.info("有価証券届出書に5年分のデータが存在します。有価証券届出書を使用します。")
            
            # 両方のデータが存在する場合、条件に応じてマージ
            if securities_registration_data is not None and annual_report_data is not None and use_securities_registration_data:
                # 有価証券届出書のファイル名から日付を抽出
                securities_registration_date = None
                if securities_registration_file_path:
                    file_name = os.path.basename(securities_registration_file_path)
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file_name)
                    if date_match:
                        securities_registration_date = date_match.group(1)
                
                # 有価証券届出書に日付情報を追加
                securities_registration_data["securities_registration_date"] = securities_registration_date
                
                # 両方のデータを結合
                combined_data = pd.concat([securities_registration_data, annual_report_data], ignore_index=True)
                
                return combined_data, None
            elif securities_registration_data is not None:
                return securities_registration_data, None
            elif annual_report_data is not None:
                return annual_report_data, None
            
            # 会社名のパターンを変えて試す
            possible_dirs = [
                f"{IPO_REPORTS_NEW_DIR}/{company_code}_株式会社{company_name}/securities_registration_statement",
                f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name.replace('株式会社', '')}/securities_registration_statement",
                f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name.replace('・', '')}/securities_registration_statement",
                f"{IPO_REPORTS_NEW_DIR}/{company_code}_株式会社{company_name}/quarterly_reports",
                f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name.replace('株式会社', '')}/quarterly_reports",
                f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name.replace('・', '')}/quarterly_reports"
            ]
            
            # 可能性のあるディレクトリを試す
            for dir_path in possible_dirs:
                if os.path.exists(dir_path):
                    report_files = sorted(glob.glob(f"{dir_path}/*.tsv"))
                    
                    if report_files:
                        latest_report = report_files[-1]
                        financial_data = DataService._read_financial_file(latest_report)
                        if financial_data is not None:
                            return financial_data, None
            
            return None, f"財務データが見つかりません: {company_code}_{company_name}"
        except Exception as e:
            logger.error(f"企業データの取得中にエラー: {e}", exc_info=True)
            return None, f"企業データの取得中にエラー: {str(e)}"

    @staticmethod
    def _read_financial_file(file_path: str) -> Optional[pd.DataFrame]:
        """財務データファイルを読み込む"""
        try:
            # ファイルのエンコーディングを確認
            encoding = 'utf-16' if 'UTF-16' in os.popen(f'file "{file_path}"').read() else 'utf-8'
            
            # ファイルを読み込む
            df = pd.read_csv(file_path, delimiter="\t", encoding=encoding, dtype=str, on_bad_lines='skip')
            
            # 必要な列が存在するか確認
            required_columns = ["要素ID", "項目名", "値"]
            if not all(col in df.columns for col in required_columns):
                missing_columns = [col for col in required_columns if col not in df.columns]
                logger.warning(f"必要な列がありません: {missing_columns}")
                return None
            
            return df
        except Exception as e:
            logger.error(f"財務データファイルの読み込み中にエラー: {e}", exc_info=True)
            return None

    @staticmethod
    def extract_metrics(data: Optional[pd.DataFrame], metrics_list: List[str] = None) -> Dict[str, Dict[str, float]]:
        """財務指標を抽出"""
        metrics_data = {}
        
        if data is None:
            return metrics_data
        
        # 使用する指標のリスト
        if metrics_list is None:
            metrics_list = list(METRIC_ALIASES.keys())
        
        # 各指標について処理
        for metric_name in metrics_list:
            if metric_name in METRIC_ALIASES:
                # 指標IDのリスト
                metric_ids = METRIC_ALIASES[metric_name]
                
                # 指標データを抽出
                metric_data = DataService._extract_single_metric(data, metric_ids)
                
                if metric_data:
                    metrics_data[metric_name] = metric_data
        
        # 追加の指標を計算
        if '営業利益' in metrics_data and '売上高' in metrics_data:
            DataService._calculate_operating_margin(metrics_data)
        
        if 'PER（株価収益率）' in metrics_data and '１株当たり当期純利益（EPS）' in metrics_data:
            DataService._calculate_peg_ratio(metrics_data)
        
        if '当期純利益' in metrics_data and '総資産' in metrics_data:
            DataService._calculate_roa(metrics_data)
        
        if '営業利益' in metrics_data and '従業員数' in metrics_data:
            DataService._calculate_operating_profit_per_employee(metrics_data)
        
        # 四半期純利益がない場合は親会社株主に帰属する当期純利益を使用
        if '四半期純利益' not in metrics_data and '親会社株主に帰属する当期純利益' in metrics_data:
            metrics_data['四半期純利益'] = metrics_data['親会社株主に帰属する当期純利益']
        
        # １株当たり四半期純利益がない場合は１株当たり当期純利益を使用
        if '１株当たり四半期純利益（EPS）' not in metrics_data and '１株当たり当期純利益（EPS）' in metrics_data:
            metrics_data['１株当たり四半期純利益（EPS）'] = metrics_data['１株当たり当期純利益（EPS）']
        
        return metrics_data

    @staticmethod
    def _extract_single_metric(data: pd.DataFrame, metric_ids: List[str]) -> Dict[str, float]:
        """単一の指標を抽出"""
        metric_data = {}
        
        try:
            # 有価証券届出書と有価証券報告書の日付を取得
            securities_registration_date = None
            annual_report_dates = []
            
            if "securities_registration_date" in data.columns:
                securities_registration_date_values = data["securities_registration_date"].dropna().unique()
                if len(securities_registration_date_values) > 0:
                    securities_registration_date = securities_registration_date_values[0]
            
            if "annual_report_date" in data.columns:
                annual_report_dates = sorted(data["annual_report_date"].dropna().unique())
                logger.debug(f"有価証券報告書の日付: {annual_report_dates}")
            
            # 指標IDに一致する行を抽出
            for metric_id in metric_ids:
                rows = data[data["要素ID"] == metric_id]
                
                if not rows.empty:
                    # 各行について処理
                    for _, row in rows.iterrows():
                        # コンテキスト情報を取得（コンテキストIDまたはコンテキスト参照ID）
                        context_ref = row.get("コンテキストID", row.get("コンテキスト参照ID", ""))
                        
                        # 日付情報を抽出
                        date_str = None
                        
                        # この行の有価証券報告書の日付を取得
                        row_annual_report_date = row.get("annual_report_date", None)
                        
                        # 有価証券届出書の特殊パターンを確認
                        if context_ref and securities_registration_date:
                            import re
                            # Prior[1-5]Year(Instant|Duration)_NonConsolidatedMemberパターンを確認
                            prior_year_match = re.search(r'Prior([1-5])Year(Instant|Duration)_NonConsolidatedMember', context_ref)
                            
                            if prior_year_match:
                                # 何年前かを取得
                                years_ago = int(prior_year_match.group(1))
                                # 有価証券届出書の日付から何年前かを計算
                                sr_date = datetime.strptime(securities_registration_date, '%Y-%m-%d')
                                date = sr_date - timedelta(days=365 * years_ago)
                                date_str = date.strftime('%Y-%m-%d')
                        
                        # 有価証券報告書の特殊パターンを確認
                        if context_ref and row_annual_report_date and not date_str:
                            # CurrentYear(Instant|Duration)_NonConsolidatedMemberパターンを確認
                            current_year_match = re.search(r'CurrentYear(Instant|Duration)_NonConsolidatedMember', context_ref)
                            
                            if current_year_match:
                                # この行の有価証券報告書の日付をそのまま使用
                                date_str = row_annual_report_date
                            else:
                                # Prior[1-5]Year(Instant|Duration)_NonConsolidatedMemberパターンを確認
                                prior_year_match = re.search(r'Prior([1-5])Year(Instant|Duration)_NonConsolidatedMember', context_ref)
                                
                                if prior_year_match:
                                    # 何年前かを取得
                                    years_ago = int(prior_year_match.group(1))
                                    # この行の有価証券報告書の日付から何年前かを計算
                                    ar_date = datetime.strptime(row_annual_report_date, '%Y-%m-%d')
                                    date = ar_date - timedelta(days=365 * years_ago)
                                    date_str = date.strftime('%Y-%m-%d')
                        
                        # 通常の日付パターンを確認（上記の特殊パターンに一致しない場合）
                        if not date_str and context_ref:
                            date_match = re.search(r'([0-9]{4}-[0-9]{2}-[0-9]{2})', context_ref)
                            if not date_match:
                                date_match = re.search(r'([0-9]{8})', context_ref)
                            
                            if date_match:
                                date_str = date_match.group(1)
                                
                                # 日付形式を統一
                                if len(date_str) == 8:  # YYYYMMDD形式
                                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                        
                        # 日付が取得できた場合のみ処理
                        if date_str:
                            # 値を取得
                            value_str = row.get("値", "")
                            
                            if value_str and value_str.strip() and value_str != "－":
                                try:
                                    # カンマを除去して数値に変換
                                    value = float(value_str.replace(",", ""))
                                    metric_data[date_str] = value
                                except ValueError:
                                    logger.warning(f"数値への変換に失敗しました: {value_str}")
            
            return metric_data
        except Exception as e:
            logger.error(f"指標の抽出中にエラー: {e}", exc_info=True)
            return {}

    @staticmethod
    def _calculate_operating_margin(metrics_data: Dict[str, Dict[str, float]]) -> None:
        """営業利益率を計算"""
        try:
            operating_profit = metrics_data['営業利益']
            revenue = metrics_data['売上高']
            
            # 共通する日付のみを処理
            common_dates = set(operating_profit.keys()) & set(revenue.keys())
            
            operating_margin = {}
            for date in common_dates:
                if revenue[date] != 0:  # ゼロ除算を防止
                    operating_margin[date] = operating_profit[date] / revenue[date]
            
            if operating_margin:
                metrics_data['営業利益率'] = operating_margin
        except Exception as e:
            logger.error(f"営業利益率の計算中にエラー: {e}", exc_info=True)

    @staticmethod
    def _calculate_peg_ratio(metrics_data: Dict[str, Dict[str, float]]) -> None:
        """PEGレシオを計算"""
        try:
            per = metrics_data['PER（株価収益率）']
            eps = metrics_data['１株当たり当期純利益（EPS）']
            
            # EPSの成長率を計算
            eps_growth = DataService.calculate_growth_rate(eps)
            
            # 共通する日付のみを処理
            common_dates = set(per.keys()) & set(eps_growth.keys())
            
            peg_ratio = {}
            for date in common_dates:
                if eps_growth[date] != 0:  # ゼロ除算を防止
                    peg_ratio[date] = per[date] / eps_growth[date]
            
            if peg_ratio:
                metrics_data['PEGレシオ（PER / EPS成長率）'] = peg_ratio
        except Exception as e:
            logger.error(f"PEGレシオの計算中にエラー: {e}", exc_info=True)

    @staticmethod
    def calculate_growth_rate(data: Dict[str, float]) -> Dict[str, float]:
        """成長率を計算"""
        growth_rate = {}
        
        try:
            # 日付でソート
            sorted_dates = sorted(data.keys())
            
            if len(sorted_dates) < 2:
                return growth_rate
            
            # 各日付について、前年同期比の成長率を計算
            for i in range(1, len(sorted_dates)):
                current_date = sorted_dates[i]
                prev_date = sorted_dates[i-1]
                
                current_value = data[current_date]
                prev_value = data[prev_date]
                
                if prev_value != 0:  # ゼロ除算を防止
                    growth_rate[current_date] = (current_value - prev_value) / abs(prev_value)
            
            return growth_rate
        except Exception as e:
            logger.error(f"成長率の計算中にエラー: {e}", exc_info=True)
            return {}

    @staticmethod
    def _calculate_roa(metrics_data: Dict[str, Dict[str, float]]) -> None:
        """ROA（総資産利益率）を計算"""
        try:
            if '四半期純利益' in metrics_data and '総資産' in metrics_data:
                net_income = metrics_data['四半期純利益']
                total_assets = metrics_data['総資産']
                
                # 共通する日付のみを処理
                common_dates = set(net_income.keys()) & set(total_assets.keys())
                
                roa = {}
                for date in common_dates:
                    if total_assets[date] != 0:  # ゼロ除算を防止
                        roa[date] = net_income[date] / total_assets[date]
                
                if roa:
                    metrics_data['ROA（総資産利益率）'] = roa
        except Exception as e:
            logger.error(f"ROAの計算中にエラー: {e}", exc_info=True)

    @staticmethod
    def _calculate_operating_profit_per_employee(metrics_data: Dict[str, Dict[str, float]]) -> None:
        """従業員一人当たり営業利益を計算"""
        try:
            operating_profit = metrics_data['営業利益']
            employees = metrics_data['従業員数']
            
            # 共通する日付のみを処理
            common_dates = set(operating_profit.keys()) & set(employees.keys())
            
            profit_per_employee = {}
            for date in common_dates:
                if employees[date] != 0:  # ゼロ除算を防止
                    profit_per_employee[date] = operating_profit[date] / employees[date]
            
            if profit_per_employee:
                metrics_data['従業員一人当たり営業利益'] = profit_per_employee
        except Exception as e:
            logger.error(f"従業員一人当たり営業利益の計算中にエラー: {e}", exc_info=True)

    @staticmethod
    def get_officers_info(company_code: str) -> Optional[str]:
        """役員情報を取得"""
        try:
            company_map = DataService.get_company_code_name_map()
            
            if company_code not in company_map:
                return None
            
            company_name = company_map[company_code]
            
            # 各ディレクトリを確認
            # 有価証券報告書はIPO_REPORTS_DIRから
            annual_reports_dir = f"{IPO_REPORTS_DIR}/{company_code}_{company_name}/annual_securities_reports"
            
            # 有価証券届出書と四半期報告書はIPO_REPORTS_NEW_DIRから
            new_company_dir = f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name}"
            securities_registration_dir = f"{new_company_dir}/securities_registration_statement"
            quarterly_reports_dir = f"{new_company_dir}/quarterly_reports"
            
            # 優先順位: 有価証券報告書 > 有価証券届出書 > 四半期報告書
            if os.path.exists(annual_reports_dir):
                report_files = sorted(glob.glob(f"{annual_reports_dir}/*.tsv"))
                if report_files:
                    report_file = report_files[0]  # 最も古い有価証券報告書を使用
                    logger.info(f"有価証券報告書から役員情報を取得: {report_file}")
                    return DataService._extract_officers_info(report_file)
            
            if os.path.exists(securities_registration_dir):
                report_files = sorted(glob.glob(f"{securities_registration_dir}/*.tsv"))
                if report_files:
                    report_file = report_files[0]  # 最も古い有価証券届出書を使用
                    logger.info(f"有価証券届出書から役員情報を取得: {report_file}")
                    return DataService._extract_officers_info(report_file)
            
            if os.path.exists(quarterly_reports_dir):
                report_files = sorted(glob.glob(f"{quarterly_reports_dir}/*.tsv"))
                if report_files:
                    report_file = report_files[-1]  # 最新の四半期報告書を使用
                    logger.info(f"四半期報告書から役員情報を取得: {report_file}")
                    return DataService._extract_officers_info(report_file)
            
            logger.warning(f"企業コード {company_code} の役員情報が見つかりません")
            return None
        except Exception as e:
            logger.error(f"役員情報の取得中にエラー: {e}", exc_info=True)
            return None

    @staticmethod
    def _extract_officers_info(report_file: str) -> Optional[str]:
        """報告書ファイルから役員情報を抽出"""
        try:
            # ファイルのエンコーディングを確認
            encoding = 'utf-16' if 'UTF-16' in os.popen(f'file "{report_file}"').read() else 'utf-8'
            
            # ファイルを読み込む
            df = pd.read_csv(report_file, delimiter="\t", encoding=encoding, dtype=str, on_bad_lines='skip')
            
            # 役員情報を抽出
            officers_rows = df[df["要素ID"] == "jpcrp_cor:InformationAboutOfficersTextBlock"]
            
            if not officers_rows.empty:
                officers_info = officers_rows.iloc[0].get("値", "")
                # HTMLとして整形
                officers_html = officers_info.replace('\n', '<br>')
                return officers_html
            
            return None
        except Exception as e:
            logger.error(f"役員情報の抽出中にエラー: {e}", exc_info=True)
            return None

    @staticmethod
    def get_business_description(company_code: str) -> Optional[str]:
        """事業の内容を取得"""
        try:
            company_map = DataService.get_company_code_name_map()
            
            if company_code not in company_map:
                return None
            
            company_name = company_map[company_code]
            
            # 各ディレクトリを確認
            # 有価証券報告書はIPO_REPORTS_DIRから
            annual_reports_dir = f"{IPO_REPORTS_DIR}/{company_code}_{company_name}/annual_securities_reports"
            
            # 有価証券届出書と四半期報告書はIPO_REPORTS_NEW_DIRから
            new_company_dir = f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name}"
            securities_registration_dir = f"{new_company_dir}/securities_registration_statement"
            quarterly_reports_dir = f"{new_company_dir}/quarterly_reports"
            
            # 優先順位: 有価証券報告書 > 有価証券届出書 > 四半期報告書
            if os.path.exists(annual_reports_dir):
                report_files = sorted(glob.glob(f"{annual_reports_dir}/*.tsv"))
                if report_files:
                    report_file = report_files[0]  # 最も古い有価証券報告書を使用
                    logger.info(f"有価証券報告書から事業内容を取得: {report_file}")
                    return DataService._extract_business_description(report_file)
            
            if os.path.exists(securities_registration_dir):
                report_files = sorted(glob.glob(f"{securities_registration_dir}/*.tsv"))
                if report_files:
                    report_file = report_files[0]  # 最も古い有価証券届出書を使用
                    logger.info(f"有価証券届出書から事業内容を取得: {report_file}")
                    return DataService._extract_business_description(report_file)
            
            if os.path.exists(quarterly_reports_dir):
                report_files = sorted(glob.glob(f"{quarterly_reports_dir}/*.tsv"))
                if report_files:
                    report_file = report_files[-1]  # 最新の四半期報告書を使用
                    logger.info(f"四半期報告書から事業内容を取得: {report_file}")
                    return DataService._extract_business_description(report_file)
            
            logger.warning(f"企業コード {company_code} の事業内容が見つかりません")
            return None
        except Exception as e:
            logger.error(f"事業内容の取得中にエラー: {e}", exc_info=True)
            return None

    @staticmethod
    def _extract_business_description(report_file: str) -> Optional[str]:
        """報告書ファイルから事業内容を抽出"""
        try:
            # ファイルのエンコーディングを確認
            encoding = 'utf-16' if 'UTF-16' in os.popen(f'file "{report_file}"').read() else 'utf-8'
            
            # ファイルを読み込む
            df = pd.read_csv(report_file, delimiter="\t", encoding=encoding, dtype=str, on_bad_lines='skip')
            
            # 事業の内容を抽出
            business_rows = df[df["要素ID"] == "jpcrp_cor:DescriptionOfBusinessTextBlock"]
            
            if not business_rows.empty:
                business_description = business_rows.iloc[0].get("値", "")
                # HTMLとして整形
                business_html = business_description.replace('\n', '<br>')
                return business_html
            
            return None
        except Exception as e:
            logger.error(f"事業内容の抽出中にエラー: {e}", exc_info=True)
            return None 