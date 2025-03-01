import os
import logging
import pandas as pd
from flask import Flask, render_template, jsonify
from pathlib import Path
import matplotlib
import matplotlib.font_manager as fm
from functools import wraps
from typing import Callable, Any, Tuple

from .config import ALL_COMPANIES_PATH
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
        if os.path.exists(ALL_COMPANIES_PATH):
            df = pd.read_csv(ALL_COMPANIES_PATH, sep='\t')
            
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
    except Exception as e:
        logger.error(f"all_companies.tsvの読み込み中にエラー: {e}", exc_info=True)
    
    return [], False

def create_app():
    app = Flask(__name__)
    setup_japanese_font()
    
    # テンプレートディレクトリが存在しない場合は作成
    os.makedirs('templates', exist_ok=True)
    
    @app.route('/')
    @handle_errors
    def index():
        """トップページ"""
        companies, success = load_companies_data()
        if not success:
            company_map = DataService.get_company_code_name_map()
            companies = [{'code': code, 'name': name} for code, name in company_map.items()]
        return render_template('index.html', companies=companies)

    @app.route('/<company_code>')
    @handle_errors
    def company_view(company_code):
        """企業の詳細ページ"""
        company_map = DataService.get_company_code_name_map()
        
        if company_code not in company_map:
            return "企業が見つかりません", 404
        
        company_name = company_map[company_code]
        competitors = DataService.get_competitors(company_code)
        
        # 役員情報を取得
        officers_info = DataService.get_officers_info(company_code)
        
        # 競合企業の役員情報を取得
        for competitor in competitors:
            competitor['officers_info'] = DataService.get_officers_info(competitor['code'])
        
        chart_service = ChartService(company_code, company_name)
        charts, error = chart_service.generate_comparison_charts()
        
        if error:
            return error, 500
        
        return render_template('company.html',
                             company_code=company_code,
                             company_name=company_name,
                             competitors=competitors,
                             charts=charts,
                             officers_info=officers_info)
    
    return app

if __name__ == '__main__':
    try:
        logger.info("Flaskアプリケーションを起動します（ポート: 8080）...")
        app = create_app()
        app.run(debug=True, host='0.0.0.0', port=8080)
    except Exception as e:
        logger.error(f"アプリケーション起動中にエラー: {e}", exc_info=True) 