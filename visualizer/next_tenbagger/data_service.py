from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import json
import logging
import glob
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

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
        """企業の四半期報告書データを取得"""
        try:
            company_map = DataService.get_company_code_name_map()
            
            if company_code not in company_map:
                return None, "企業が見つかりません"
            
            company_name = company_map[company_code]
            company_dir = f"{IPO_REPORTS_NEW_DIR}/{company_code}_{company_name}"
            
            # 四半期報告書ディレクトリを確認
            quarterly_reports_dir = f"{company_dir}/quarterly_reports"
            securities_registration_statement_dir = f"{company_dir}/securities_registration_statement"
            
            # quarterly_reportsディレクトリが存在しない場合はsecurities_registration_statementディレクトリを試す
            if not os.path.exists(quarterly_reports_dir):
                if os.path.exists(securities_registration_statement_dir):
                    logger.info(f"四半期報告書ディレクトリが見つからないため、securities_registration_statementディレクトリを使用します: {securities_registration_statement_dir}")
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
                        if os.path.exists(dir_path):
                            quarterly_reports_dir = dir_path
                            logger.info(f"代替ディレクトリが見つかりました: {quarterly_reports_dir}")
                            break
                    else:
                        # 企業コードだけで検索
                        code_pattern = f"{IPO_REPORTS_NEW_DIR}/{company_code}_*/quarterly_reports"
                        matching_dirs = glob.glob(code_pattern)
                        
                        if matching_dirs:
                            quarterly_reports_dir = matching_dirs[0]
                            logger.info(f"企業コードで一致するディレクトリが見つかりました: {quarterly_reports_dir}")
                        else:
                            # securities_registration_statementを試す
                            code_pattern = f"{IPO_REPORTS_NEW_DIR}/{company_code}_*/securities_registration_statement"
                            matching_dirs = glob.glob(code_pattern)
                            
                            if matching_dirs:
                                quarterly_reports_dir = matching_dirs[0]
                                logger.info(f"企業コードで一致するsecurities_registration_statementディレクトリが見つかりました: {quarterly_reports_dir}")
                            else:
                                return None, f"四半期報告書またはsecurities_registration_statementディレクトリが見つかりません: {quarterly_reports_dir}"
            
            # 四半期報告書ファイルを取得
            report_files = sorted(glob.glob(f"{quarterly_reports_dir}/*.tsv"))
            
            # TSVファイルがない場合はHTMLファイルを試す
            if not report_files:
                report_files = sorted(glob.glob(f"{quarterly_reports_dir}/*.html"))
            
            # HTMLファイルもない場合はテキストファイルを試す
            if not report_files:
                report_files = sorted(glob.glob(f"{quarterly_reports_dir}/*.txt"))
            
            if not report_files:
                return None, f"四半期報告書ファイルが見つかりません: {quarterly_reports_dir}"
            
            # 最新の四半期報告書を使用
            latest_report = report_files[-1]
            
            # 財務データを読み込む
            financial_data = DataService._read_financial_file(latest_report)
            
            if financial_data is None:
                return None, f"財務データの読み込みに失敗しました: {latest_report}"
            
            return financial_data, None
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
        
        if 'PER（株価収益率）' in metrics_data and '１株当たり四半期純利益（EPS）' in metrics_data:
            DataService._calculate_peg_ratio(metrics_data)
        
        if '当期純利益' in metrics_data and '総資産' in metrics_data:
            DataService._calculate_roa(metrics_data)
        
        if '営業利益' in metrics_data and '従業員数' in metrics_data:
            DataService._calculate_operating_profit_per_employee(metrics_data)
        
        return metrics_data

    @staticmethod
    def _extract_single_metric(data: pd.DataFrame, metric_ids: List[str]) -> Dict[str, float]:
        """単一の指標を抽出"""
        metric_data = {}
        
        try:
            # 指標IDに一致する行を抽出
            for metric_id in metric_ids:
                rows = data[data["要素ID"] == metric_id]
                
                if not rows.empty:
                    # 各行について処理
                    for _, row in rows.iterrows():
                        # コンテキスト情報を取得
                        context_ref = row.get("コンテキスト参照ID", "")
                        
                        # 日付情報を抽出
                        date_match = None
                        if context_ref:
                            # 四半期報告書の日付形式に対応
                            import re
                            date_match = re.search(r'([0-9]{4}-[0-9]{2}-[0-9]{2})', context_ref)
                            if not date_match:
                                date_match = re.search(r'([0-9]{8})', context_ref)
                        
                        if date_match:
                            date_str = date_match.group(1)
                            
                            # 日付形式を統一
                            if len(date_str) == 8:  # YYYYMMDD形式
                                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                            
                            # 値を取得
                            value_str = row.get("値", "")
                            
                            if value_str and value_str.strip():
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
            eps = metrics_data['１株当たり四半期純利益（EPS）']
            
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