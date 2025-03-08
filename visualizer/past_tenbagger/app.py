import os
import logging
import pandas as pd
import json
import glob
import difflib
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from pathlib import Path
import matplotlib
import matplotlib.font_manager as fm
from functools import wraps
from typing import Callable, Any, Tuple

from visualizer.past_tenbagger.config import ALL_COMPANIES_PATH, IPO_REPORTS_DIR
from visualizer.past_tenbagger.data_service import DataService
from visualizer.past_tenbagger.chart_service import ChartService

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

def handle_errors(func: Callable) -> Callable:
    """エラーハンドリングを行うデコレータ"""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__}の実行中にエラー: {e}", exc_info=True)
            return str(e), 500
    return wrapper

def load_companies_data() -> Tuple[list, bool]:
    """企業データの読み込み"""
    try:
        logger.info(f"ALL_COMPANIES_PATH: {ALL_COMPANIES_PATH}")
        if os.path.exists(ALL_COMPANIES_PATH):
            logger.info(f"ファイルが存在します: {ALL_COMPANIES_PATH}")
            df = pd.read_csv(ALL_COMPANIES_PATH, sep='\t')
            logger.info(f"データフレームの列: {df.columns.tolist()}")
            logger.info(f"データフレームの行数: {len(df)}")
            
            required_columns = ['企業名', '現在何倍株', '最大何倍株', '社長_株%', '想定時価総額', 'コード']
            if all(col in df.columns for col in required_columns):
                df = df[required_columns].dropna(subset=['現在何倍株', 'コード'])
                df = df.sort_values('現在何倍株', ascending=False)
                
                companies = []
                for _, row in df.iterrows():
                    code = str(row['コード']).split('.')[0]
                    companies.append({
                        'code': code,
                        'name': row['企業名'],
                        'current_multiple': row['現在何倍株'],
                        'max_multiple': row['最大何倍株'] if pd.notna(row['最大何倍株']) else None,
                        'president_share': row['社長_株%'] if pd.notna(row['社長_株%']) else None,
                        'market_cap': row['想定時価総額'] if pd.notna(row['想定時価総額']) else None
                    })
                
                logger.info(f"企業を現在何倍株で並べ替えました。企業数: {len(companies)}")
                return companies, True
            else:
                missing_columns = [col for col in required_columns if col not in df.columns]
                logger.warning(f"all_companies.tsvに必要な列がありません: {missing_columns}")
        else:
            logger.error(f"ファイルが存在しません: {ALL_COMPANIES_PATH}")
    except Exception as e:
        logger.error(f"all_companies.tsvの読み込み中にエラー: {e}", exc_info=True)
    
    # 失敗した場合はダミーデータを返す
    logger.info("ダミーデータを返します")
    dummy_companies = [
        {'code': '1234', 'name': 'サンプル企業1', 'current_multiple': 10.5, 'max_multiple': 15.2, 'president_share': 25.3, 'market_cap': 10000000000},
        {'code': '5678', 'name': 'サンプル企業2', 'current_multiple': 8.3, 'max_multiple': 12.1, 'president_share': 18.7, 'market_cap': 5000000000},
        {'code': '9012', 'name': 'サンプル企業3', 'current_multiple': 5.2, 'max_multiple': 7.8, 'president_share': 10.5, 'market_cap': 3000000000}
    ]
    return dummy_companies, False

def extract_diff(file_old, file_new, date_old, date_new):
    """有価証券報告書の差分を抽出する関数"""
    try:
        # ファイルのエンコーディングを確認
        encoding_old = 'utf-16' if 'UTF-16' in os.popen(f'file "{file_old}"').read() else 'utf-8'
        encoding_new = 'utf-16' if 'UTF-16' in os.popen(f'file "{file_new}"').read() else 'utf-8'
        
        # ファイルを読み込む
        df_old = pd.read_csv(file_old, delimiter="\t", encoding=encoding_old, dtype=str, on_bad_lines='skip')
        df_new = pd.read_csv(file_new, delimiter="\t", encoding=encoding_new, dtype=str, on_bad_lines='skip')

        # 指定した要素ID以降のデータを取得
        target_id = "jpcrp_cor:BusinessResultsOfReportingCompanyTextBlock"
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

def create_app():
    # 現在のファイルのディレクトリパスを取得
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(current_dir, 'templates')
    static_dir = os.path.join(current_dir, 'static')
    
    # テンプレートディレクトリが存在することを確認
    if not os.path.exists(template_dir):
        os.makedirs(template_dir, exist_ok=True)
        logger.warning(f"テンプレートディレクトリを作成しました: {template_dir}")
    else:
        logger.info(f"テンプレートディレクトリが存在します: {template_dir}")
        # テンプレートファイルの存在を確認
        index_path = os.path.join(template_dir, 'index.html')
        if os.path.exists(index_path):
            logger.info(f"index.htmlが存在します: {index_path}")
        else:
            logger.warning(f"index.htmlが見つかりません: {index_path}")
    
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir)
    setup_japanese_font()
    
    @app.route('/past_tenbagger/')
    @handle_errors
    def index():
        """トップページ"""
        companies, success = load_companies_data()
        if not success:
            company_map = DataService.get_company_code_name_map()
            companies = [{'code': code, 'name': name} for code, name in company_map.items()]
        
        try:
            # テンプレートの絶対パスを使用
            return render_template('index.html', companies=companies)
        except Exception as e:
            logger.error(f"テンプレートのレンダリング中にエラー: {e}", exc_info=True)
            # テンプレートの内容を直接返す（デバッグ用）
            template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'index.html')
            if os.path.exists(template_path):
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_content = f.read()
                return f"テンプレートの内容:<br><pre>{template_content}</pre>"
            else:
                return f"テンプレートが見つかりません: {template_path}", 500

    @app.route('/past_tenbagger/<company_code>')
    @handle_errors
    def company_view(company_code):
        """企業の詳細ページ"""
        company_map = DataService.get_company_code_name_map()
        
        if company_code not in company_map:
            return "企業が見つかりません", 404
        
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
            return error, 500
        
        try:
            return render_template('company.html',
                                company_code=company_code,
                                company_name=company_name,
                                competitors=competitors,
                                charts=charts,
                                business_description=business_description,
                                officers_info=officers_info)
        except Exception as e:
            logger.error(f"テンプレートのレンダリング中にエラー: {e}", exc_info=True)
            # テンプレートの存在を確認
            template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'company.html')
            if os.path.exists(template_path):
                return f"テンプレートは存在しますが、レンダリングに失敗しました: {e}", 500
            else:
                return f"テンプレートが見つかりません: {template_path}", 500
    
    @app.route('/past_tenbagger/api/securities_reports/<company_code>')
    @handle_errors
    def get_securities_reports(company_code):
        """有価証券報告書の一覧を取得するAPI"""
        company_map = DataService.get_company_code_name_map()
        
        if company_code not in company_map:
            return jsonify({"error": "企業が見つかりません"}), 404
        
        company_name = company_map[company_code]
        company_dir = f"{IPO_REPORTS_DIR}/{company_code}_{company_name}"
        
        # 年次報告書ディレクトリを確認
        annual_reports_dir = f"{company_dir}/annual_securities_reports"
        if not os.path.exists(annual_reports_dir):
            return jsonify({"reports": []}), 200
        
        # 有価証券報告書ファイルを取得
        report_files = sorted(glob.glob(f"{annual_reports_dir}/*.tsv"))
        
        reports = []
        for file_path in report_files:
            file_name = os.path.basename(file_path)
            # ファイル名から日付を抽出（例: 2019-05-30_有価証券報告書.tsv）
            date_part = file_name.split('_')[0]
            reports.append({
                "file": file_name,
                "date": date_part,
                "path": file_path
            })
        
        return jsonify({"reports": reports}), 200
    
    @app.route('/past_tenbagger/api/securities_report_diff/<company_code>', methods=['POST'])
    @handle_errors
    def get_securities_report_diff(company_code):
        """有価証券報告書の差分を計算するAPI"""
        data = request.json
        
        if not data or 'old_report' not in data or 'new_report' not in data or 'old_date' not in data or 'new_date' not in data:
            return jsonify({"error": "必要なパラメータが不足しています"}), 400
        
        company_map = DataService.get_company_code_name_map()
        
        if company_code not in company_map:
            return jsonify({"error": "企業が見つかりません"}), 404
        
        company_name = company_map[company_code]
        company_dir = f"{IPO_REPORTS_DIR}/{company_code}_{company_name}"
        annual_reports_dir = f"{company_dir}/annual_securities_reports"
        
        old_report_path = f"{annual_reports_dir}/{data['old_report']}"
        new_report_path = f"{annual_reports_dir}/{data['new_report']}"
        
        if not os.path.exists(old_report_path) or not os.path.exists(new_report_path):
            return jsonify({"error": "指定された有価証券報告書が見つかりません"}), 404
        
        # 差分を計算
        diff_text = extract_diff(old_report_path, new_report_path, data['old_date'], data['new_date'])
        
        return jsonify({"diff_text": diff_text}), 200
    
    return app

if __name__ == '__main__':
    try:
        logger.info("Flaskアプリケーションを起動します（ポート: 8080）...")
        app = create_app()
        app.run(debug=True, host='0.0.0.0', port=8080)
    except Exception as e:
        logger.error(f"アプリケーション起動中にエラー: {e}", exc_info=True) 