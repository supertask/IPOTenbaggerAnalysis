import os
import pandas as pd
import json
from pathlib import Path

# プロジェクトのルートディレクトリを取得
project_root = Path(__file__).parent.parent.parent
data_dir = project_root / "data" / "output" / "combiner" / "x_bagger_probability"

def load_conditions():
    """条件データを読み込む"""
    try:
        conditions_file = data_dir / "x_bagger_conditions.tsv"
        if not conditions_file.exists():
            return None, "条件ファイルが見つかりません", 404
        
        df = pd.read_csv(conditions_file, sep='\t')
        return df, None, 200
    except Exception as e:
        return None, f"条件データの読み込みエラー: {str(e)}", 500

def load_probability_data():
    """確率データを読み込む"""
    try:
        probability_file = data_dir / "x_bagger_probability.tsv"
        if not probability_file.exists():
            return None, "確率ファイルが見つかりません", 404
        
        df = pd.read_csv(probability_file, sep='\t')
        return df, None, 200
    except Exception as e:
        return None, f"確率データの読み込みエラー: {str(e)}", 500

def index():
    """X-bagger分析のメインページ"""
    try:
        # 条件データを読み込み
        conditions_df, error, status_code = load_conditions()
        if error:
            return None, error, status_code
        
        # 確率データを読み込み
        probability_df, error, status_code = load_probability_data()
        if error:
            return None, error, status_code
        
        # 条件をカテゴリごとに整理
        conditions_by_category = {}
        for _, row in conditions_df.iterrows():
            category = row['対象の条件']
            if category not in conditions_by_category:
                conditions_by_category[category] = []
            conditions_by_category[category].append({
                'index': row['条件index'],
                'condition': row['条件']
            })
        
        # 単一条件のデータのみを抽出（条件リストにカンマが含まれていないもの）
        single_condition_data = probability_df[~probability_df['条件リスト'].astype(str).str.contains(',', na=False)]
        
        data = {
            'conditions_by_category': conditions_by_category,
            'single_condition_data': single_condition_data.to_dict('records'),
            'x_range': list(range(2, 11))  # 2~10倍のレンジ
        }
        
        return data, None, 200
    except Exception as e:
        return None, f"データ処理エラー: {str(e)}", 500

def get_chart_data(x_bagger=5):
    """特定のX倍に対するチャートデータを取得"""
    try:
        # 条件データを読み込み
        conditions_df, error, status_code = load_conditions()
        if error:
            return None, error, status_code
        
        # 確率データを読み込み
        probability_df, error, status_code = load_probability_data()
        if error:
            return None, error, status_code
        
        # 単一条件のデータのみを抽出
        single_condition_data = probability_df[
            (~probability_df['条件リスト'].astype(str).str.contains(',', na=False)) &
            (probability_df['X倍'] == x_bagger)
        ]
        
        # 条件インデックスと条件内容をマッピング
        condition_map = dict(zip(conditions_df['条件index'], conditions_df['条件']))
        category_map = dict(zip(conditions_df['条件index'], conditions_df['対象の条件']))
        
        # チャートデータを構築
        chart_data = {}
        for _, row in single_condition_data.iterrows():
            condition_index = int(row['条件リスト'])
            category = category_map.get(condition_index, 'Unknown')
            condition = condition_map.get(condition_index, 'Unknown')
            
            if category not in chart_data:
                chart_data[category] = []
            
            # ラベルを「カテゴリ: 条件」形式に変更
            formatted_condition = format_condition_label(category, condition)
            
            chart_data[category].append({
                'condition': formatted_condition,
                'condition_raw': condition,
                'condition_index': condition_index,
                'percentage': row['X倍以上の%'],
                'count': row['X倍以上の企業数'],
                'total': row['対象企業数'],
                'median_years': row['何年かかったかの中央値'] if pd.notna(row['何年かかったかの中央値']) else None
            })
        
        # カテゴリごとにソート（業種のみX倍以上の件数でソート、他は条件インデックス順）
        for category in chart_data:
            if category == '業種':
                chart_data[category].sort(key=lambda x: x['count'], reverse=True)
            else:
                chart_data[category].sort(key=lambda x: x['condition_index'])
        
        return chart_data, None, 200
    except Exception as e:
        return None, f"チャートデータ取得エラー: {str(e)}", 500

def format_condition_label(category, condition):
    """条件ラベルを整形"""
    if category == '社長_株%':
        # [0, 10) -> 0~10%
        if condition.startswith('[') and condition.endswith(')'):
            condition_clean = condition[1:-1]
            start, end = condition_clean.split(', ')
            return f"{start}~{end}%"
        elif condition.startswith('[') and condition.endswith(']'):
            condition_clean = condition[1:-1]
            start, end = condition_clean.split(', ')
            return f"{start}~{end}%"
    elif category == '想定時価総額':
        # (0, 50] -> 0~50億
        if 'inf' in condition:
            start = condition.split(',')[0][1:]
            return f"{start}億以上"
        else:
            condition_clean = condition[1:-1]
            start, end = condition_clean.split(', ')
            return f"{start}~{end}億"
    elif category == 'PER':
        if condition == 'なし':
            return 'なし'
        elif 'inf' in condition:
            start = condition.split(',')[0][1:]
            return f"{start}倍以上"
        else:
            condition_clean = condition[1:-1]
            start, end = condition_clean.split(', ')
            return f"{start}~{end}倍"
    elif category == '売上成長率_平均':
        if 'inf' in condition:
            start = condition.split(',')[0][1:]
            return f"{start}%以上"
        else:
            condition_clean = condition[1:-1]
            start, end = condition_clean.split(', ')
            return f"{start}~{end}%"
    elif category == '業種':
        return condition
    
    return condition

def get_combination_data(sort_by1='何年かかったかの中央値', sort_order1='asc', 
                        sort_by2='X倍以上の%', sort_order2='desc', 
                        sort_by3='対象企業数', sort_order3='desc', 
                        x_bagger=10, limit=50):
    """複数条件の組み合わせデータを取得（3段階ソート対応）"""
    try:
        # 条件データを読み込み
        conditions_df, error, status_code = load_conditions()
        if error:
            return None, error, status_code
        
        # 確率データを読み込み
        probability_df, error, status_code = load_probability_data()
        if error:
            return None, error, status_code
        
        # 複数条件のデータのみを抽出（条件リストにカンマが含まれているもの）
        combination_data = probability_df[
            (probability_df['条件リスト'].astype(str).str.contains(',', na=False)) &
            (probability_df['X倍'] == x_bagger)
        ].copy()
        
        # 条件インデックスと条件内容をマッピング
        condition_map = dict(zip(conditions_df['条件index'], conditions_df['条件']))
        category_map = dict(zip(conditions_df['条件index'], conditions_df['対象の条件']))
        
        # 条件リストを人間可読な形式に変換
        def format_condition_list(condition_list_str):
            indices = [int(x.strip()) for x in condition_list_str.split(',')]
            formatted_conditions = []
            for idx in indices:
                category = category_map.get(idx, 'Unknown')
                condition = condition_map.get(idx, 'Unknown')
                formatted_conditions.append(f"{category}: {condition}")
            return " & ".join(formatted_conditions)
        
        combination_data['条件内容'] = combination_data['条件リスト'].apply(format_condition_list)
        
        # 中央値が'-'または計測不能（負の値、NaN）のデータをフィルタリング
        def is_valid_median(value):
            if pd.isna(value) or value == '-':
                return False
            try:
                numeric_value = float(value)
                return numeric_value >= 0  # 0以上の値のみ有効
            except (ValueError, TypeError):
                return False
        
        # 中央値が有効なデータのみを残す
        valid_mask = combination_data['何年かかったかの中央値'].apply(is_valid_median)
        combination_data = combination_data[valid_mask].copy()
        
        if len(combination_data) == 0:
            return [], None, 200
        
        # 3段階ソート
        ascending1 = (sort_order1 == 'asc')
        ascending2 = (sort_order2 == 'asc')
        ascending3 = (sort_order3 == 'asc')
        
        # 何年かかったかの中央値の処理（既に有効な値のみなので特別な処理は不要）
        sort_by1_actual = sort_by1
        
        combination_data = combination_data.sort_values(
            by=[sort_by1_actual, sort_by2, sort_by3], 
            ascending=[ascending1, ascending2, ascending3]
        )
        
        # 上位N件に制限
        combination_data = combination_data.head(limit)
        
        return combination_data.to_dict('records'), None, 200
    except Exception as e:
        return None, f"組み合わせデータ取得エラー: {str(e)}", 500 