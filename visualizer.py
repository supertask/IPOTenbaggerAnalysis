import os
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.utils
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # バックエンドをAggに設定

# 日本語フォントの設定
import matplotlib.font_manager as fm
# macOSの場合は以下のフォントを使用
if os.path.exists('/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc'):
    matplotlib.rcParams['font.family'] = 'Hiragino Sans GB'
# Linuxの場合は以下のフォントを使用
elif os.path.exists('/usr/share/fonts/truetype/fonts-japanese-gothic.ttf'):
    matplotlib.rcParams['font.family'] = 'IPAGothic'
# Windowsの場合は以下のフォントを使用
elif os.path.exists('C:/Windows/Fonts/meiryo.ttc'):
    matplotlib.rcParams['font.family'] = 'Meiryo'
# どれも見つからない場合はシステムのデフォルトフォントを使用
else:
    # 利用可能なフォントを探す
    fonts = [f.name for f in fm.fontManager.ttflist if 'gothic' in f.name.lower() or 'meiryo' in f.name.lower() or 'hiragino' in f.name.lower()]
    if fonts:
        matplotlib.rcParams['font.family'] = fonts[0]
    else:
        # 日本語フォントが見つからない場合は警告を表示
        print("警告: 日本語フォントが見つかりません。グラフの日本語が正しく表示されない可能性があります。")

import io
import base64
from flask import Flask, render_template, request, jsonify, send_file
import glob
from pathlib import Path
import traceback
import logging

# ロギングの設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# データディレクトリのパス
IPO_REPORTS_DIR = 'data/output/edinet/edinet_database/ipo_reports'
COMPARISON_DIR = 'data/output/comparison'

# テンプレートディレクトリが存在しない場合は作成
os.makedirs('templates', exist_ok=True)

# 重要な財務指標のリスト
IMPORTANT_METRICS = [
    '売上高',
    '経常利益',
    '当期純利益',
    '総資産',
    '純資産額',
    '自己資本比率',
    '自己資本利益率',
    '株価収益率',
    '営業活動によるキャッシュ・フロー',
    '投資活動によるキャッシュ・フロー',
    '財務活動によるキャッシュ・フロー',
    '現金及び現金同等物の期末残高'
]

# 指標の代替名マッピング
METRIC_ALIASES = {
    '売上高': ['売上高', 'NetSales', '営業収益', '経営成績', '営業収入'],
    '経常利益': ['経常利益', 'OrdinaryIncome', '経常損益', '経常利益又は経常損失'],
    '当期純利益': ['当期純利益', '親会社株主に帰属する当期純利益', 'ProfitLoss', '当期利益', '当期損益', '親会社株主に帰属する当期純損益'],
    '総資産': ['総資産', 'TotalAssets', '資産合計'],
    '純資産額': ['純資産額', '純資産', 'NetAssets', '純資産合計'],
    '自己資本比率': ['自己資本比率', 'EquityToAssetRatio', '株主資本比率'],
    '自己資本利益率': ['自己資本利益率', 'ReturnOnEquity', 'ROE'],
    '株価収益率': ['株価収益率', 'PriceEarningsRatio', 'PER'],
    '営業活動によるキャッシュ・フロー': ['営業活動によるキャッシュ・フロー', 'CashFlowsFromOperatingActivities', '営業活動によるCF'],
    '投資活動によるキャッシュ・フロー': ['投資活動によるキャッシュ・フロー', 'CashFlowsFromInvestingActivities', '投資活動によるCF'],
    '財務活動によるキャッシュ・フロー': ['財務活動によるキャッシュ・フロー', 'CashFlowsFromFinancingActivities', '財務活動によるCF'],
    '現金及び現金同等物の期末残高': ['現金及び現金同等物の期末残高', 'CashAndCashEquivalents', '現金及び現金同等物', '現金及び預金']
}

def get_company_code_name_map():
    """すべての企業コードと名前のマッピングを取得"""
    company_map = {}
    
    try:
        # IPOレポートディレクトリから企業コードと名前を取得
        logger.info(f"IPOレポートディレクトリを検索: {IPO_REPORTS_DIR}")
        for company_dir in glob.glob(f"{IPO_REPORTS_DIR}/*"):
            dir_name = os.path.basename(company_dir)
            if '_' in dir_name:
                code, name = dir_name.split('_', 1)
                company_map[code] = name
        
        logger.info(f"企業数: {len(company_map)}")
    except Exception as e:
        logger.error(f"企業コード・名前マッピングの取得中にエラー: {e}")
        logger.error(traceback.format_exc())
    
    return company_map

def get_competitors(company_code):
    """指定された企業コードの競合企業リストを取得"""
    # 最新の年度のファイルを探す
    comparison_files = sorted(glob.glob(f"{COMPARISON_DIR}/companies_*.tsv"), reverse=True)
    
    if not comparison_files:
        return []
    
    # 全てのファイルを読み込んで統合
    dfs = []
    for file in comparison_files:
        temp_df = pd.read_csv(file, sep='\t')
        dfs.append(temp_df)
    
    # データフレームを結合
    df = pd.concat(dfs, ignore_index=True)
    
    # 重複を削除（同じコードの企業は最新のデータを保持）
    df = df.drop_duplicates(subset=['コード'], keep='first')
    
    # 企業コードに一致する行を探す
    company_row = df[df['コード'].astype(str) == str(company_code)]
    
    if company_row.empty or pd.isna(company_row['競合リスト'].values[0]):
        return []
    
    # 競合リストをJSONとして解析
    competitors = json.loads(company_row['競合リスト'].values[0])
    return competitors

def get_company_data(company_code):
    """指定された企業コードの財務データを取得"""
    company_map = get_company_code_name_map()
    
    if company_code not in company_map:
        logger.error(f"企業コード {company_code} が見つかりません")
        return None, "企業が見つかりません"
    
    company_name = company_map[company_code]
    company_dir = f"{IPO_REPORTS_DIR}/{company_code}_{company_name}"
    
    # 有価証券報告書を探す
    report_files = glob.glob(f"{company_dir}/annual_securities_reports/*.tsv")
    
    if not report_files:
        logger.error(f"企業 {company_code}_{company_name} の有価証券報告書が見つかりません")
        return None, "有価証券報告書が見つかりません"
    
    logger.info(f"企業 {company_code}_{company_name} の有価証券報告書: {len(report_files)}件")
    
    # すべての報告書からデータを収集
    all_data = []
    for file_path in sorted(report_files):
        try:
            logger.info(f"ファイル読み込み: {file_path}")
            
            # ファイルのエンコーディングを確認
            import subprocess
            result = subprocess.run(['file', file_path], capture_output=True, text=True)
            file_info = result.stdout
            
            encoding = 'utf-8'  # デフォルトエンコーディング
            
            if 'UTF-16' in file_info:
                if 'little-endian' in file_info:
                    encoding = 'utf-16-le'
                    logger.info(f"UTF-16LE エンコーディングを検出しました: {file_path}")
                elif 'big-endian' in file_info:
                    encoding = 'utf-16-be'
                    logger.info(f"UTF-16BE エンコーディングを検出しました: {file_path}")
                else:
                    encoding = 'utf-16'
                    logger.info(f"UTF-16 エンコーディングを検出しました: {file_path}")
            
            # ファイルを読み込む
            try:
                df = pd.read_csv(file_path, sep='\t', encoding=encoding, on_bad_lines='skip')
                logger.info(f"エンコーディング {encoding} で読み込み成功")
            except Exception as e:
                logger.warning(f"標準的な読み込みに失敗: {e}")
                # 代替方法: バイナリモードで読み込み
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                # BOMを確認
                if content.startswith(b'\xff\xfe'):  # UTF-16LE BOM
                    content = content[2:]
                    encoding = 'utf-16-le'
                elif content.startswith(b'\xfe\xff'):  # UTF-16BE BOM
                    content = content[2:]
                    encoding = 'utf-16-be'
                
                # 一時ファイルに書き込んで読み込む
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False) as temp:
                    temp_path = temp.name
                    temp.write(content)
                
                try:
                    df = pd.read_csv(temp_path, sep='\t', encoding=encoding, on_bad_lines='skip')
                    logger.info(f"一時ファイル経由で読み込み成功")
                except Exception as e:
                    logger.error(f"一時ファイル経由でも読み込み失敗: {e}")
                    os.unlink(temp_path)
                    raise
                
                os.unlink(temp_path)
            
            # カラム名を確認
            logger.info(f"ファイルのカラム: {df.columns.tolist()}")
            
            # EDINETのTSVファイルの構造に合わせて処理
            # カラム名が文字化けしている場合や想定と異なる場合の対応
            if len(df.columns) >= 8:  # 最低限必要なカラム数
                # カラム名を再設定
                new_columns = ['要素ID', '項目名', '期間', '時点', '詳細', '値タイプ', '単位', '値']
                if len(df.columns) >= len(new_columns):
                    df.columns = new_columns + list(df.columns[len(new_columns):])
                else:
                    # カラム数が足りない場合は、足りない分を空の値で埋める
                    df = df.reindex(columns=new_columns)
            
            # ファイル名から年度を抽出
            year = os.path.basename(file_path).split('_')[0][:4]
            df['年度'] = year
            
            # 必要なカラムが存在するか確認
            required_columns = ['項目名', '値']
            if all(col in df.columns for col in required_columns):
                all_data.append(df)
                logger.info(f"ファイル {file_path} を正常に読み込みました。行数: {len(df)}")
            else:
                missing_columns = [col for col in required_columns if col not in df.columns]
                logger.warning(f"ファイル {file_path} に必要なカラムがありません: {missing_columns}")
        except Exception as e:
            logger.error(f"ファイル読み込みエラー {file_path}: {e}")
            logger.error(traceback.format_exc())
    
    if not all_data:
        logger.error(f"企業 {company_code}_{company_name} のデータ読み込みに失敗しました")
        return None, "データの読み込みに失敗しました"
    
    try:
        # すべてのデータを結合
        combined_data = pd.concat(all_data, ignore_index=True)
        logger.info(f"企業 {company_code}_{company_name} のデータを結合しました。合計行数: {len(combined_data)}")
        return combined_data, None
    except Exception as e:
        logger.error(f"データ結合エラー: {e}")
        logger.error(traceback.format_exc())
        return None, "データの結合に失敗しました"

def extract_metrics(data, metrics_list=IMPORTANT_METRICS):
    """指定された指標のデータを抽出"""
    if data is None:
        logger.warning("データがNoneのため、指標を抽出できません")
        return {}
    
    metrics_data = {}
    try:
        # EDINETのデータ構造に合わせて指標を抽出
        # 項目名カラムが存在するか確認
        if '項目名' not in data.columns:
            logger.warning("データに '項目名' カラムがありません")
            # 代替方法: 2番目のカラムを項目名として使用
            if len(data.columns) >= 2:
                item_column = data.columns[1]
                logger.info(f"代替カラムを使用: {item_column}")
                
                # 売上高などの指標を含む行を探す
                for metric in metrics_list:
                    try:
                        # 代替名を含めて検索
                        aliases = METRIC_ALIASES.get(metric, [metric])
                        metric_rows = pd.DataFrame()
                        
                        for alias in aliases:
                            # 部分一致で検索
                            alias_rows = data[data[item_column].str.contains(alias, na=False, regex=True)]
                            if not alias_rows.empty:
                                metric_rows = pd.concat([metric_rows, alias_rows])
                        
                        if metric_rows.empty:
                            logger.info(f"指標 '{metric}' のデータがありません")
                            continue
                        
                        # 年度ごとのデータを収集
                        years_data = {}
                        for _, row in metric_rows.iterrows():
                            if '年度' not in row:
                                continue
                            
                            year = row['年度']
                            
                            # 値カラムを特定
                            value_column = None
                            for col in row.index:
                                if col == '値' or '値' in col:
                                    value_column = col
                                    break
                            
                            if value_column is None and len(row) >= 8:
                                value_column = row.index[7]  # 8番目のカラムを値として使用
                            
                            if value_column is None:
                                continue
                            
                            # 値を取得（シリーズの場合は最初の値を使用）
                            value = row[value_column]
                            if isinstance(value, pd.Series):
                                logger.info(f"値がシリーズです: {value}")
                                # シリーズから最初の非NaN値を取得
                                non_nan_values = value.dropna()
                                if not non_nan_values.empty:
                                    value = non_nan_values.iloc[0]
                                else:
                                    continue
                            
                            # 数値に変換できる場合のみ追加
                            try:
                                if pd.notna(value) and value != '－' and value != '-':
                                    if isinstance(value, str):
                                        # カンマを削除して数値に変換
                                        value = float(value.replace(',', ''))
                                    else:
                                        value = float(value)
                                    years_data[year] = value
                            except (ValueError, AttributeError) as e:
                                logger.warning(f"値の変換エラー: {value}, {e}")
                        
                        if years_data:
                            metrics_data[metric] = years_data
                            logger.info(f"指標 '{metric}' のデータを {len(years_data)} 年分抽出しました")
                    except Exception as e:
                        logger.error(f"指標 '{metric}' の抽出中にエラー: {e}")
                        logger.error(traceback.format_exc())
            return metrics_data
        
        # 通常の処理（項目名カラムが存在する場合）
        for metric in metrics_list:
            try:
                # 代替名を含めて検索
                aliases = METRIC_ALIASES.get(metric, [metric])
                metric_rows = pd.DataFrame()
                
                for alias in aliases:
                    # 完全一致で検索
                    exact_rows = data[data['項目名'] == alias]
                    if not exact_rows.empty:
                        metric_rows = pd.concat([metric_rows, exact_rows])
                        continue
                    
                    # 部分一致で検索
                    alias_rows = data[data['項目名'].str.contains(alias, na=False, regex=True)]
                    if not alias_rows.empty:
                        metric_rows = pd.concat([metric_rows, alias_rows])
                
                if metric_rows.empty:
                    logger.info(f"指標 '{metric}' のデータがありません")
                    continue
                
                # 年度ごとのデータを収集
                years_data = {}
                for _, row in metric_rows.iterrows():
                    if '年度' not in row or '値' not in row:
                        continue
                    
                    year = row['年度']
                    value = row['値']
                    
                    # 値がシリーズの場合は最初の値を使用
                    if isinstance(value, pd.Series):
                        logger.info(f"値がシリーズです: {value}")
                        # シリーズから最初の非NaN値を取得
                        non_nan_values = value.dropna()
                        if not non_nan_values.empty:
                            value = non_nan_values.iloc[0]
                        else:
                            continue
                    
                    # 数値に変換できる場合のみ追加
                    try:
                        if pd.notna(value) and value != '－' and value != '-':
                            if isinstance(value, str):
                                value = float(value.replace(',', ''))
                            else:
                                value = float(value)
                            years_data[year] = value
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"値の変換エラー: {value}, {e}")
                
                if years_data:
                    metrics_data[metric] = years_data
                    logger.info(f"指標 '{metric}' のデータを {len(years_data)} 年分抽出しました")
            except Exception as e:
                logger.error(f"指標 '{metric}' の抽出中にエラー: {e}")
                logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"指標抽出中に予期しないエラー: {e}")
        logger.error(traceback.format_exc())
    
    return metrics_data

def generate_comparison_charts(company_code):
    """企業と競合他社の比較チャートを生成"""
    company_map = get_company_code_name_map()
    
    if company_code not in company_map:
        return [], "企業が見つかりません"
    
    company_name = company_map[company_code]
    competitors = get_competitors(company_code)
    
    # メイン企業のデータを取得
    main_company_data, error = get_company_data(company_code)
    if error:
        return [], error
    
    main_metrics = extract_metrics(main_company_data)
    
    # 競合企業のデータを取得
    competitors_data = {}
    if competitors:
        for competitor in competitors:
            comp_code = competitor['code']
            comp_data, _ = get_company_data(comp_code)
            if comp_data is not None:
                competitors_data[comp_code] = extract_metrics(comp_data)
    
    # チャートを生成
    charts = []
    for metric_name, metric_data in main_metrics.items():
        if not metric_data:
            continue
        
        # Plotlyのグラフオブジェクトを作成
        fig = go.Figure()
        
        # 全ての年度を収集
        all_years = set(metric_data.keys())
        for comp_metrics in competitors_data.values():
            if metric_name in comp_metrics:
                all_years.update(comp_metrics[metric_name].keys())
        
        # 年度を昇順にソート
        sorted_years = sorted(all_years)
        
        # メイン企業のデータをプロット
        values = [metric_data.get(year, None) for year in sorted_years]
        fig.add_trace(
            go.Scatter(
                x=sorted_years,
                y=values,
                mode='lines+markers',
                name=f"{company_name} ({company_code})",
                line=dict(width=3),
                connectgaps=True  # 欠損値をスキップして線を接続
            )
        )
        
        # 競合企業のデータをプロット
        for comp_code, comp_metrics in competitors_data.items():
            if metric_name in comp_metrics and comp_metrics[metric_name]:
                comp_values = [comp_metrics[metric_name].get(year, None) for year in sorted_years]
                comp_name = next((c['name'] for c in competitors if c['code'] == comp_code), comp_code)
                fig.add_trace(
                    go.Scatter(
                        x=sorted_years,
                        y=comp_values,
                        mode='lines+markers',
                        name=f"{comp_name} ({comp_code})",
                        line=dict(width=2, dash='dot'),
                        connectgaps=True  # 欠損値をスキップして線を接続
                    )
                )
        
        # グラフのレイアウトを設定
        fig.update_layout(
            title=f"{metric_name}の比較",
            xaxis_title="年度",
            yaxis_title="値 (円)",
            hovermode='x unified',
            template='plotly_white',
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            ),
            xaxis=dict(
                type='category',  # カテゴリとして扱う
                categoryorder='array',  # 配列順で表示
                categoryarray=sorted_years  # ソートされた年度を指定
            )
        )
        
        # グラフをJSONに変換
        chart_json = fig.to_json()
        
        charts.append({
            'title': metric_name,
            'plotly_data': chart_json
        })
    
    return charts, None

@app.route('/')
def index():
    """トップページ"""
    company_map = get_company_code_name_map()
    
    # all_companies.tsvファイルを読み込む
    try:
        all_companies_path = 'data/output/combiner/all_companies.tsv'
        if os.path.exists(all_companies_path):
            df = pd.read_csv(all_companies_path, sep='\t')
            
            # 必要な列が存在するか確認
            required_columns = ['企業名', '現在何倍株', 'コード']
            additional_columns = ['最大何倍株', '社長_株%', '想定時価総額']
            
            if all(col in df.columns for col in required_columns):
                # 必須列のNaNを除外し、現在何倍株で降順にソート
                df = df[['企業名', '現在何倍株', 'コード'] + [col for col in additional_columns if col in df.columns]]
                df = df.dropna(subset=['現在何倍株', 'コード'])
                df = df.sort_values('現在何倍株', ascending=False)
                
                # 企業リストを作成
                companies = []
                for _, row in df.iterrows():
                    code = str(row['コード']).split('.')[0]  # 小数点以下を削除
                    company_data = {
                        'code': code,
                        'name': row['企業名'],
                        'multiple': row['現在何倍株']
                    }
                    
                    # 追加情報を含める
                    if '最大何倍株' in df.columns and pd.notna(row['最大何倍株']):
                        company_data['max_multiple'] = row['最大何倍株']
                    
                    if '社長_株%' in df.columns and pd.notna(row['社長_株%']):
                        company_data['president_share'] = row['社長_株%']
                    
                    if '想定時価総額' in df.columns and pd.notna(row['想定時価総額']):
                        # 想定時価総額を億円または兆円単位に変換
                        market_cap = float(row['想定時価総額'])
                        if market_cap >= 10000000000:  # 1兆円以上
                            company_data['market_cap'] = f"{market_cap / 10000000000:.1f}兆円"
                        else:  # 億円単位
                            company_data['market_cap'] = f"{market_cap / 100000000:.1f}億円"
                    
                    companies.append(company_data)
                
                logger.info(f"企業を現在何倍株で並べ替えました。企業数: {len(companies)}")
                return render_template('index.html', companies=companies)
            else:
                missing_cols = [col for col in required_columns if col not in df.columns]
                logger.warning(f"all_companies.tsvに必要な列がありません: {missing_cols}")
        else:
            logger.warning(f"ファイルが見つかりません: {all_companies_path}")
    except Exception as e:
        logger.error(f"all_companies.tsvの読み込み中にエラーが発生しました: {str(e)}")
        logger.error(traceback.format_exc())
    
    # エラーが発生した場合や必要なファイルがない場合は、従来の方法でデータを表示
    companies = [{'code': code, 'name': name} for code, name in company_map.items()]
    return render_template('index.html', companies=companies)

@app.route('/<company_code>')
def company_view(company_code):
    """企業の詳細ページ"""
    company_map = get_company_code_name_map()
    
    if company_code not in company_map:
        return "企業が見つかりません", 404
    
    company_name = company_map[company_code]
    competitors = get_competitors(company_code)
    charts, error = generate_comparison_charts(company_code)
    
    if error:
        return error, 500
    
    return render_template('company.html', 
                          company_code=company_code,
                          company_name=company_name,
                          competitors=competitors,
                          charts=charts)

# HTMLテンプレートを作成
@app.route('/create_templates')
def create_templates():
    """HTMLテンプレートを作成"""
    # index.html
    index_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>IPO企業分析ツール</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding-top: 20px; }
            .company-card { margin-bottom: 20px; transition: transform 0.3s; }
            .company-card:hover { transform: translateY(-5px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="mb-4 text-center">IPO企業分析ツール</h1>
            <div class="row">
                {% for company in companies %}
                <div class="col-md-4">
                    <div class="card company-card">
                        <div class="card-body">
                            <h5 class="card-title">{{ company.name }}</h5>
                            <h6 class="card-subtitle mb-2 text-muted">コード: {{ company.code }}</h6>
                            <a href="/{{ company.code }}" class="btn btn-primary">詳細を見る</a>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    
    # company.html
    company_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ company_name }} ({{ company_code }}) - 分析</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body { padding-top: 20px; }
            .chart-container { margin-bottom: 30px; height: 500px; }
            .competitor-badge { margin-right: 5px; margin-bottom: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <nav aria-label="breadcrumb">
                <ol class="breadcrumb">
                    <li class="breadcrumb-item"><a href="/">ホーム</a></li>
                    <li class="breadcrumb-item active" aria-current="page">{{ company_name }}</li>
                </ol>
            </nav>
            
            <h1 class="mb-3">{{ company_name }} <small class="text-muted">({{ company_code }})</small></h1>
            
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0">競合企業</h5>
                </div>
                <div class="card-body">
                    {% if competitors %}
                        {% for competitor in competitors %}
                        <span class="badge bg-secondary competitor-badge">{{ competitor.name }} ({{ competitor.code }})</span>
                        {% endfor %}
                    {% else %}
                        <div class="alert alert-info">
                            この企業の競合企業情報はまだ登録されていません。以下のグラフでは、この企業の財務指標のみを表示しています。
                        </div>
                    {% endif %}
                </div>
            </div>
            
            <h2 class="mb-4">財務指標の比較</h2>
            
            {% if charts %}
                {% for chart in charts %}
                <div class="chart-container">
                    <div id="chart-{{ loop.index }}" style="width: 100%; height: 100%;"></div>
                </div>
                <script>
                    var chartData = JSON.parse('{{ chart.plotly_data | safe }}');
                    Plotly.newPlot('chart-{{ loop.index }}', chartData.data, chartData.layout);
                </script>
                {% endfor %}
            {% else %}
                <div class="alert alert-warning">
                    グラフを生成するためのデータが不足しています。
                </div>
            {% endif %}
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    
    # テンプレートを保存
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(index_html)
    
    with open('templates/company.html', 'w', encoding='utf-8') as f:
        f.write(company_html)
    
    return "テンプレートを作成しました"

if __name__ == '__main__':
    try:
        # テンプレートを作成
        with app.test_request_context():
            create_templates()
        
        logger.info("Flaskアプリケーションを起動します...")
        # アプリケーションを実行
        app.run(debug=True, host='0.0.0.0', port=8080)
    except Exception as e:
        logger.error(f"アプリケーション起動中にエラー: {e}")
        logger.error(traceback.format_exc()) 