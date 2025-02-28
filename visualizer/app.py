import os
import logging
import pandas as pd
from flask import Flask, render_template, jsonify
from pathlib import Path
import matplotlib
import matplotlib.font_manager as fm

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
    matplotlib.use('Agg')  # バックエンドをAggに設定
    
    font_paths = [
        '/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc',  # macOS
        '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',  # Linux
        'C:/Windows/Fonts/meiryo.ttc',  # Windows
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            matplotlib.rcParams['font.family'] = {
                'ヒラギノ角ゴシック W3.ttc': 'Hiragino Sans GB',
                'fonts-japanese-gothic.ttf': 'IPAGothic',
                'meiryo.ttc': 'Meiryo'
            }.get(os.path.basename(font_path))
            return
    
    # 利用可能なフォントを探す
    fonts = [f.name for f in fm.fontManager.ttflist 
             if any(keyword in f.name.lower() 
                   for keyword in ['gothic', 'meiryo', 'hiragino'])]
    if fonts:
        matplotlib.rcParams['font.family'] = fonts[0]
    else:
        logger.warning("警告: 日本語フォントが見つかりません。グラフの日本語が正しく表示されない可能性があります。")

def create_app():
    app = Flask(__name__)
    setup_japanese_font()
    
    # テンプレートディレクトリが存在しない場合は作成
    os.makedirs('templates', exist_ok=True)
    
    @app.route('/')
    def index():
        """トップページ"""
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
                    return render_template('index.html', companies=companies)
                else:
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    logger.warning(f"all_companies.tsvに必要な列がありません: {missing_columns}")
            else:
                logger.warning(f"ファイルが見つかりません: {ALL_COMPANIES_PATH}")
        except Exception as e:
            logger.error(f"all_companies.tsvの読み込み中にエラーが発生しました: {str(e)}", exc_info=True)
        
        # エラーが発生した場合や必要なファイルがない場合は、従来の方法でデータを表示
        company_map = DataService.get_company_code_name_map()
        companies = [{'code': code, 'name': name} for code, name in company_map.items()]
        return render_template('index.html', companies=companies)

    @app.route('/<company_code>')
    def company_view(company_code):
        """企業の詳細ページ"""
        company_map = DataService.get_company_code_name_map()
        
        if company_code not in company_map:
            return "企業が見つかりません", 404
        
        company_name = company_map[company_code]
        competitors = DataService.get_competitors(company_code)
        
        chart_service = ChartService(company_code, company_name)
        charts, error = chart_service.generate_comparison_charts()
        
        if error:
            return error, 500
        
        return render_template('company.html',
                             company_code=company_code,
                             company_name=company_name,
                             competitors=competitors,
                             charts=charts)
    
    return app

if __name__ == '__main__':
    try:
        logger.info("Flaskアプリケーションを起動します（ポート: 8080）...")
        app = create_app()
        app.run(debug=True, host='0.0.0.0', port=8080)
    except Exception as e:
        logger.error(f"アプリケーション起動中にエラー: {e}", exc_info=True) 