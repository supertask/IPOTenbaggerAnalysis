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
    '従業員数',
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
    '現金及び現金同等物の期末残高',
    '営業利益',
    '営業利益率'
]

# 指標の代替名マッピング
METRIC_ALIASES = {
    '売上高': ['jpcrp_cor:NetSalesSummaryOfBusinessResults', 'jpcrp_cor:RevenueIFRSSummaryOfBusinessResults', 'jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults'],
    '営業利益': ['jppfs_cor:OperatingIncome'],
    '経常利益': ['jppfs_cor:OrdinaryIncome', 'jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults'],
    '当期純利益': ['jppfs_cor:ProfitLoss', 'jpcrp_cor:NetIncomeLossSummaryOfBusinessResults'],

    '総資産': ['jpcrp_cor:Assets', 'jpcrp_cor:TotalAssets'],
    '純資産額': ['jpcrp_cor:NetAssets', 'jpcrp_cor:TotalNetAssets'],
    '自己資本比率': ['jpcrp_cor:EquityToAssetRatio', 'jpcrp_cor:ShareholdersEquityRatio'],
    '自己資本利益率': ['jpcrp_cor:ReturnOnEquity', 'jpcrp_cor:ROE'],
    '株価収益率': ['jpcrp_cor:PriceEarningsRatio', 'jpcrp_cor:PER'],
    '営業活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromOperatingActivities', 'jpcrp_cor:NetCashProvidedByUsedInOperatingActivities'],
    '投資活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromInvestingActivities', 'jpcrp_cor:NetCashProvidedByUsedInInvestingActivities'],
    '財務活動によるキャッシュ・フロー': ['jpcrp_cor:CashFlowsFromFinancingActivities', 'jpcrp_cor:NetCashProvidedByUsedInFinancingActivities'],
    '現金及び現金同等物の期末残高': ['jpcrp_cor:CashAndCashEquivalents', 'jpcrp_cor:CashAndDeposits'],
    '従業員数': ['jpcrp_cor:NumberOfEmployees'],
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
            if len(df.columns) >= 9:  # 最低限必要なカラム数
                # カラム名を再設定
                new_columns = ['要素ID', '項目名', 'コンテキストID', '相対年度', '連結・個別', '期間・時点', 'ユニットID', '単位', '値']
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
        # 要素IDカラムが存在するか確認
        if '要素ID' not in data.columns:
            logger.warning("データに '要素ID' カラムがありません")
            # 代替方法: 1番目のカラムを要素IDとして使用
            if len(data.columns) >= 1:
                element_id_column = data.columns[0]
                logger.info(f"代替カラムを使用: {element_id_column}")
                
                # 指標を含む行を探す
                for metric in metrics_list:
                    try:
                        # 代替名を含めて検索
                        aliases = METRIC_ALIASES.get(metric, [])
                        metric_rows = pd.DataFrame()
                        
                        for alias in aliases:
                            # 部分一致で検索
                            alias_rows = data[data[element_id_column].str.contains(alias, na=False, regex=False)]
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
        
        # 通常の処理（要素IDカラムが存在する場合）
        for metric in metrics_list:
            try:
                # 代替名を含めて検索
                aliases = METRIC_ALIASES.get(metric, [])
                metric_rows = pd.DataFrame()
                
                for alias in aliases:
                    # 完全一致で検索
                    exact_rows = data[data['要素ID'] == alias]
                    if not exact_rows.empty:
                        metric_rows = pd.concat([metric_rows, exact_rows])
                        continue
                    
                    # 部分一致で検索
                    alias_rows = data[data['要素ID'].str.contains(alias, na=False, regex=False)]
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
    
    # 営業利益率を計算（データに含まれていない場合）
    if '営業利益率' not in metrics_data and '営業利益' in metrics_data and '売上高' in metrics_data:
        try:
            operating_profit = metrics_data['営業利益']
            sales = metrics_data['売上高']
            
            # 共通する年度で営業利益率を計算
            operating_profit_ratio = {}
            for year in set(operating_profit.keys()) & set(sales.keys()):
                if sales[year] != 0:  # ゼロ除算を防ぐ
                    operating_profit_ratio[year] = (operating_profit[year] / sales[year]) * 100
            
            if operating_profit_ratio:
                metrics_data['営業利益率'] = operating_profit_ratio
                logger.info(f"営業利益率を計算しました。{len(operating_profit_ratio)} 年分のデータがあります。")
        except Exception as e:
            logger.error(f"営業利益率の計算中にエラー: {e}")
            logger.error(traceback.format_exc())
    
    return metrics_data

def calculate_growth_rate(data):
    """年度ごとのデータから成長率を計算する"""
    if not data or len(data) < 2:
        return {}
    
    # 年度を昇順にソート
    sorted_years = sorted(data.keys())
    growth_rates = {}
    
    for i in range(1, len(sorted_years)):
        current_year = sorted_years[i]
        prev_year = sorted_years[i-1]
        
        current_value = data.get(current_year)
        prev_value = data.get(prev_year)
        
        if current_value is not None and prev_value is not None and prev_value != 0:
            growth_rate = ((current_value - prev_value) / abs(prev_value)) * 100
            growth_rates[current_year] = growth_rate
    
    return growth_rates

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
    
    # 企業ごとの色を定義（メイン企業と競合企業で一貫した色を使用）
    # メイン企業用の色
    main_bar_color = 'rgba(255, 0, 0, 1.0)'  # 鮮やかな赤
    main_line_color = 'rgba(255, 0, 0, 1.0)'  # 鮮やかな赤（実線）
    
    # 透明度の共通パラメータ
    comp_bar_alpha = 0.3  # 棒グラフの透明度
    comp_line_alpha = 0.4  # 線グラフの透明度
    
    # 競合企業の基本色（RGB値のみ）
    comp_base_colors = [
        [0, 128, 255],    # 鮮やかな青
        [0, 180, 0],      # 鮮やかな緑
        [255, 128, 0],    # オレンジ
        [128, 0, 255],    # 紫
        [0, 180, 180],    # ターコイズ
        [180, 0, 180],    # マゼンタ
        [180, 180, 0],    # 黄色
        [90, 90, 90],     # グレー
    ]
    
    # 透明度を適用した色配列を生成
    comp_bar_colors = [f'rgba({r}, {g}, {b}, {comp_bar_alpha})' for r, g, b in comp_base_colors]
    comp_line_colors = [f'rgba({r}, {g}, {b}, {comp_line_alpha})' for r, g, b in comp_base_colors]
    
    def generate_metric_growth_chart(metric_name, metric_label):
        """指標と成長率の複合グラフを生成する共通関数"""
        if metric_name not in main_metrics or not main_metrics[metric_name]:
            return None
            
        # 複合グラフ用のFigureを作成
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # 全ての年度を収集
        all_years = set(main_metrics[metric_name].keys())
        for comp_metrics in competitors_data.values():
            if metric_name in comp_metrics:
                all_years.update(comp_metrics[metric_name].keys())
        
        # 年度を昇順にソート
        sorted_years = sorted(all_years)
        
        # 競合企業のデータを先にプロット（メイン企業を前面に表示するため）
        for i, (comp_code, comp_metrics) in enumerate(competitors_data.items()):
            if metric_name in comp_metrics and comp_metrics[metric_name]:
                comp_name = next((c['name'] for c in competitors if c['code'] == comp_code), comp_code)
                
                # 競合企業ごとに色を変える（色パレットの範囲内でループ）
                color_index = i % len(comp_bar_colors)
                comp_bar_color = comp_bar_colors[color_index]
                comp_line_color = comp_line_colors[color_index]
                
                # 競合企業の指標（棒グラフ）
                comp_values = [comp_metrics[metric_name].get(year, None) for year in sorted_years]
                fig.add_trace(
                    go.Bar(
                        x=sorted_years,
                        y=comp_values,
                        name=f"{comp_name} {metric_label}",
                        marker_color=comp_bar_color
                    ),
                    secondary_y=False
                )
                
                # 競合企業の成長率（折れ線グラフ）
                comp_growth_rates = calculate_growth_rate(comp_metrics[metric_name])
                if comp_growth_rates:
                    comp_growth_values = [comp_growth_rates.get(year, None) for year in sorted_years]
                    fig.add_trace(
                        go.Scatter(
                            x=sorted_years,
                            y=comp_growth_values,
                            mode='lines+markers',
                            name=f"{comp_name} {metric_label}成長率",
                            line=dict(color=comp_line_color, width=2),  # 点線から実線に変更、太さも調整
                            marker=dict(size=6),  # マーカーサイズを調整
                            connectgaps=True
                        ),
                        secondary_y=True
                    )
        
        # メイン企業のデータをプロット（棒グラフ）- 最後にプロットして前面に表示
        values = [main_metrics[metric_name].get(year, None) for year in sorted_years]
        fig.add_trace(
            go.Bar(
                x=sorted_years,
                y=values,
                name=f"{company_name} {metric_label}",
                marker_color=main_bar_color,  # メイン企業の色
                opacity=0.8,  # 透明度を調整
            ),
            secondary_y=False
        )
        
        # メイン企業の成長率を計算してプロット（折れ線グラフ）
        growth_rates = calculate_growth_rate(main_metrics[metric_name])
        if growth_rates:
            growth_values = [growth_rates.get(year, None) for year in sorted_years]
            fig.add_trace(
                go.Scatter(
                    x=sorted_years,
                    y=growth_values,
                    mode='lines+markers',
                    name=f"{company_name} {metric_label}成長率",
                    line=dict(color=main_line_color, width=3),
                    marker=dict(size=8),  # マーカーを大きく
                    connectgaps=True
                ),
                secondary_y=True
            )
        
        # グラフのレイアウトを設定
        fig.update_layout(
            title=f"{metric_label}と{metric_label}成長率の比較",
            xaxis_title="年度",
            hovermode='x unified',
            template='plotly_white',
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            ),
            barmode='group',
            xaxis=dict(
                type='category',
                categoryorder='array',
                categoryarray=sorted_years
            )
        )
        
        # Y軸のタイトルを設定
        fig.update_yaxes(title_text=metric_label, secondary_y=False)
        fig.update_yaxes(title_text="成長率 (%)", secondary_y=True)
        
        return {
            'title': f'{metric_label}と{metric_label}成長率',
            'plotly_data': fig.to_json()
        }
    
    # 売上高と売上高成長率の複合グラフを生成
    sales_chart = generate_metric_growth_chart('売上高', '売上高')
    if sales_chart:
        charts.append(sales_chart)
    
    # 営業利益と営業利益成長率の複合グラフを生成
    profit_chart = generate_metric_growth_chart('営業利益', '営業利益')
    if profit_chart:
        charts.append(profit_chart)
    
    # 通常の指標のチャートを生成
    for metric_name, metric_data in main_metrics.items():
        if not metric_data or metric_name in ['売上高', '営業利益']:
            continue  # 売上高、営業利益は複合グラフで別途処理
        
        # Plotlyのグラフオブジェクトを作成
        fig = go.Figure()
        
        # 全ての年度を収集
        all_years = set(metric_data.keys())
        for comp_metrics in competitors_data.values():
            if metric_name in comp_metrics:
                all_years.update(comp_metrics[metric_name].keys())
        
        # 年度を昇順にソート
        sorted_years = sorted(all_years)
        
        # 競合企業のデータを先にプロット
        for i, (comp_code, comp_metrics) in enumerate(competitors_data.items()):
            if metric_name in comp_metrics and comp_metrics[metric_name]:
                comp_values = [comp_metrics[metric_name].get(year, None) for year in sorted_years]
                comp_name = next((c['name'] for c in competitors if c['code'] == comp_code), comp_code)
                
                # 競合企業ごとに色を変える（色パレットの範囲内でループ）
                color_index = i % len(comp_line_colors)
                comp_line_color = comp_line_colors[color_index]
                
                fig.add_trace(
                    go.Scatter(
                        x=sorted_years,
                        y=comp_values,
                        mode='lines+markers',
                        name=f"{comp_name} ({comp_code})",
                        line=dict(color=comp_line_color, width=2),  # 点線から実線に変更
                        marker=dict(size=6),  # マーカーサイズを調整
                        connectgaps=True,  # 欠損値をスキップして線を接続
                        opacity=0.8  # 透明度を下げて目立たせる
                    )
                )
        
        # メイン企業のデータを最後にプロット（前面に表示）
        values = [metric_data.get(year, None) for year in sorted_years]
        fig.add_trace(
            go.Scatter(
                x=sorted_years,
                y=values,
                mode='lines+markers',
                name=f"{company_name} ({company_code})",
                line=dict(color=main_line_color, width=3),  # メイン企業の色
                marker=dict(size=8),  # マーカーを大きく
                connectgaps=True  # 欠損値をスキップして線を接続
            )
        )
        
        # グラフのレイアウトを設定
        fig.update_layout(
            title=f"{metric_name}の比較",
            xaxis_title="年度",
            yaxis_title="値",
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
            
            # 必要な列だけを抽出
            required_columns = ['企業名', '現在何倍株', '最大何倍株', '社長_株%', '想定時価総額', 'コード']
            if all(col in df.columns for col in required_columns):
                # NaNを除外し、現在何倍株で降順にソート
                df = df[required_columns].dropna(subset=['現在何倍株', 'コード'])
                df = df.sort_values('現在何倍株', ascending=False)
                
                # 企業リストを作成
                companies = []
                for _, row in df.iterrows():
                    code = str(row['コード']).split('.')[0]  # 小数点以下を削除
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

if __name__ == '__main__':
    try:
        logger.info("Flaskアプリケーションを起動します（ポート: 8080）...")
        # アプリケーションを実行
        app.run(debug=True, host='0.0.0.0', port=8080)
    except Exception as e:
        logger.error(f"アプリケーション起動中にエラー: {e}")
        logger.error(traceback.format_exc()) 