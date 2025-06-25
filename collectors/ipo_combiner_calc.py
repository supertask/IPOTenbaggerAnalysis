import os
import pandas as pd
import numpy as np
from collections import defaultdict
from itertools import combinations, product
from collectors.settings import GeneralSettings, CombinerSettings


class IPOCombinerCalc:
    def __init__(self):
        """
        初期化
        """
        self.combiner_settings = CombinerSettings()
        self.output_dir = os.path.join(self.combiner_settings.output_dir, "x_bagger_probability")
        os.makedirs(self.output_dir, exist_ok=True)
        
    def load_all_companies_data(self):
        """
        全企業データを読み込む
        """
        file_path = os.path.join(self.combiner_settings.output_dir, "all_companies.tsv")
        if os.path.exists(file_path):
            return pd.read_csv(file_path, sep='\t')
        else:
            print(f"File not found: {file_path}")
            return pd.DataFrame()

    def create_conditions_tsv(self):
        """
        x_bagger_conditions.tsvを作成
        """
        conditions = []
        condition_index = 0
        
        # 社長_株%の条件
        for i in range(0, 100, 10):
            if i == 0:
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': '社長_株%',
                    '条件': f'[{i}, {i+10})'
                })
            elif i == 90:
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': '社長_株%',
                    '条件': f'[{i}, 100]'
                })
            else:
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': '社長_株%',
                    '条件': f'[{i}, {i+10})'
                })
            condition_index += 1
        
        # 想定時価総額の条件（億円単位）- より細かく区切り
        time_cap_ranges = []
        # 0~500億まで50億刻み
        for i in range(0, 500, 50):
            time_cap_ranges.append((i, i+50))
        # 500億以上
        time_cap_ranges.append((500, float('inf')))
        
        for start, end in time_cap_ranges:
            if end == float('inf'):
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': '想定時価総額',
                    '条件': f'({start}, inf]'
                })
            else:
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': '想定時価総額',
                    '条件': f'({start}, {end}]'
                })
            condition_index += 1
        
        # PERの条件
        per_conditions = [
            ('なし', 'なし'),
            (1, 10), (10, 20), (20, 30), (30, 40), (40, float('inf'))
        ]
        for start, end in per_conditions:
            if start == 'なし':
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': 'PER',
                    '条件': 'なし'
                })
            elif end == float('inf'):
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': 'PER',
                    '条件': f'({start}, inf]'
                })
            else:
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': 'PER',
                    '条件': f'({start}, {end}]'
                })
            condition_index += 1
        
        # 売上成長率の条件
        for i in range(0, 50, 5):
            conditions.append({
                '条件index': condition_index,
                '対象の条件': '売上成長率_平均',
                '条件': f'({i}, {i+5}]'
            })
            condition_index += 1
        
        # 50%以上
        conditions.append({
            '条件index': condition_index,
            '対象の条件': '売上成長率_平均',
            '条件': '(50, inf]'
        })
        condition_index += 1
        
        # 業種の条件（動的に取得）
        df = self.load_all_companies_data()
        if not df.empty and '業種' in df.columns:
            unique_industries = df['業種'].dropna().unique()
            for industry in sorted(unique_industries):
                conditions.append({
                    '条件index': condition_index,
                    '対象の条件': '業種',
                    '条件': industry
                })
                condition_index += 1
        
        # TSVファイルに保存
        conditions_df = pd.DataFrame(conditions)
        conditions_file = os.path.join(self.output_dir, "x_bagger_conditions.tsv")
        conditions_df.to_csv(conditions_file, sep='\t', index=False)
        print(f"条件ファイルを作成しました: {conditions_file}")
        print(f"総条件数: {len(conditions)}")
        
        return conditions_df

    def apply_condition(self, df, condition_row):
        """
        条件を適用してデータをフィルタリング
        """
        target_col = condition_row['対象の条件']
        condition_str = condition_row['条件']
        
        if target_col not in df.columns:
            return df.iloc[0:0]  # 空のDataFrameを返す
        
        if target_col == '業種':
            return df[df[target_col] == condition_str]
        
        elif condition_str == 'なし':
            return df[df[target_col].isna() | (df[target_col] == '')]
        
        elif condition_str.startswith('[') and condition_str.endswith(')'):
            # [start, end) 形式の範囲条件
            condition_str = condition_str[1:-1]  # 括弧を除去
            start, end = map(float, condition_str.split(', '))
            return df[(df[target_col] >= start) & (df[target_col] < end)]
        
        elif condition_str.startswith('[') and condition_str.endswith(']'):
            # [start, end] 形式の範囲条件
            condition_str = condition_str[1:-1]  # 括弧を除去
            start, end = map(float, condition_str.split(', '))
            return df[(df[target_col] >= start) & (df[target_col] <= end)]
        
        elif condition_str.startswith('(') and condition_str.endswith(']'):
            # 範囲条件の解析
            condition_str = condition_str[1:-1]  # 括弧を除去
            if ', inf' in condition_str:
                start = float(condition_str.split(',')[0])
                return df[df[target_col] > start]
            else:
                start, end = map(float, condition_str.split(', '))
                return df[(df[target_col] > start) & (df[target_col] <= end)]
        
        return df.iloc[0:0]  # 条件が不明な場合は空のDataFrameを返す

    def calculate_x_bagger_probability(self, df, x_bagger):
        """
        X倍株確率と年数の中央値を計算
        """
        if len(df) == 0:
            return 0.0, 0, None
        
        # 現在何倍株または最大何倍株のどちらかがx_bagger以上の場合をカウント
        x_bagger_mask = ((df['現在何倍株'] >= x_bagger) | (df['最大何倍株'] >= x_bagger))
        count = x_bagger_mask.sum()
        probability = (count / len(df)) * 100
        
        # X倍以上になった企業の年数データを取得
        median_years = self.calculate_years_median(df[x_bagger_mask], x_bagger)
        
        return probability, count, median_years
    
    def calculate_years_median(self, df, x_bagger):
        """
        X倍に到達するまでの年数の中央値を計算
        """
        if len(df) == 0:
            return None
            
        if x_bagger == 1:
            return None  # 1倍は上場時点なので年数データなし
            
        # X倍まで何年の列名を構築
        years_col = f'{x_bagger}倍まで何年'
        
        if years_col in df.columns:
            years_data = df[years_col].dropna()
            if len(years_data) > 0:
                return round(years_data.median(), 2)
        
        return None

    def run_calculation(self):
        """
        計算を実行してTSVファイルを出力
        """
        print("データを読み込み中...")
        df = self.load_all_companies_data()
        if df.empty:
            print("データが見つかりません。")
            return
        
        print(f"読み込み完了。企業数: {len(df)}")
        
        # 条件ファイルを作成
        conditions_df = self.create_conditions_tsv()
        
        print("計算開始...")
        results = []
        x_bagger_range = range(1, 11)  # 1倍から10倍まで
        
        # 単一条件
        for _, condition_row in conditions_df.iterrows():
            condition_index = condition_row['条件index']
            filtered_df = self.apply_condition(df, condition_row)
            
            for x_bagger in x_bagger_range:
                probability, x_bagger_count, median_years = self.calculate_x_bagger_probability(filtered_df, x_bagger)
                
                results.append({
                    '条件リスト': str(condition_index),
                    'X倍': x_bagger,
                    'X倍以上の%': round(probability, 2),
                    '何年かかったかの中央値': median_years if median_years is not None else '-',
                    'X倍以上の企業数': x_bagger_count,
                    '対象企業数': len(filtered_df)
                })
        
        # 2つの条件の組み合わせ（一部のみ、計算量を抑制）
        print("2つの条件の組み合わせを計算中...")
        important_indices = []
        
        # 社長_株%の条件インデックス（0-9）
        president_indices = list(range(10))
        # 想定時価総額の条件インデックス（10-16）
        market_cap_indices = list(range(10, 17))
        # PERの条件インデックス（17-22）
        per_indices = list(range(17, 23))
        
        important_indices = president_indices + market_cap_indices + per_indices
        
        for i, cond1_idx in enumerate(important_indices):
            for cond2_idx in important_indices[i+1:]:
                cond1_row = conditions_df[conditions_df['条件index'] == cond1_idx].iloc[0]
                cond2_row = conditions_df[conditions_df['条件index'] == cond2_idx].iloc[0]
                
                # 両方の条件を適用
                filtered_df = self.apply_condition(df, cond1_row)
                filtered_df = self.apply_condition(filtered_df, cond2_row)
                
                if len(filtered_df) < 5:  # データが少ない場合はスキップ
                    continue
                
                for x_bagger in x_bagger_range:
                    probability, x_bagger_count, median_years = self.calculate_x_bagger_probability(filtered_df, x_bagger)
                    
                    results.append({
                        '条件リスト': f"{cond1_idx},{cond2_idx}",
                        'X倍': x_bagger,
                        'X倍以上の%': round(probability, 2),
                        '何年かかったかの中央値': median_years if median_years is not None else '-',
                        'X倍以上の企業数': x_bagger_count,
                        '対象企業数': len(filtered_df)
                    })
        
        # 結果をDataFrameに変換して保存
        results_df = pd.DataFrame(results)
        output_file = os.path.join(self.output_dir, "x_bagger_probability.tsv")
        results_df.to_csv(output_file, sep='\t', index=False)
        
        print(f"計算完了。結果を {output_file} に保存しました。")
        print(f"総計算件数: {len(results)}")
        
        # 上位結果を表示
        print("\n=== 確率の高い条件（上位10件） ===")
        top_results = results_df.nlargest(10, 'X倍以上の%')
        for _, row in top_results.iterrows():
            print(f"条件リスト: {row['条件リスト']} | {row['X倍']}倍以上 | {row['X倍以上の%']}% | 中央値: {row['何年かかったかの中央値']}年 | X倍以上企業数: {row['X倍以上の企業数']} | 対象企業数: {row['対象企業数']}")


def main():
    """
    メイン関数
    """
    calc = IPOCombinerCalc()
    calc.run_calculation()


if __name__ == "__main__":
    main() 