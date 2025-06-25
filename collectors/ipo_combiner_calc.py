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
    
    def define_filter_conditions(self, df):
        """
        フィルタ条件を定義する
        """
        conditions = {
            'オーナー株%': [
                ('0~10%', lambda x: (x >= 0) & (x < 10)),
                ('10~20%', lambda x: (x >= 10) & (x < 20)),
                ('20~30%', lambda x: (x >= 20) & (x < 30)),
                ('30%以上', lambda x: x >= 30)
            ],
            '想定時価総額': [
                ('0~50億', lambda x: (x >= 0) & (x < 5_000_000_000)),
                ('50~100億', lambda x: (x >= 5_000_000_000) & (x < 10_000_000_000)),
                ('100~150億', lambda x: (x >= 10_000_000_000) & (x < 15_000_000_000)),
                ('150~200億', lambda x: (x >= 15_000_000_000) & (x < 20_000_000_000)),
                ('200~250億', lambda x: (x >= 20_000_000_000) & (x < 25_000_000_000)),
                ('250~300億', lambda x: (x >= 25_000_000_000) & (x < 30_000_000_000)),
                ('300億以上', lambda x: x >= 30_000_000_000)
            ],
            'PER': [
                ('なし', lambda x: pd.isna(x) | (x <= 0)),
                ('1~10倍', lambda x: (x > 0) & (x < 10)),
                ('10~20倍', lambda x: (x >= 10) & (x < 20)),
                ('20~30倍', lambda x: (x >= 20) & (x < 30)),
                ('30~40倍', lambda x: (x >= 30) & (x < 40)),
                ('40倍以上', lambda x: x >= 40)
            ],
            '売上成長率_平均': []
        }
        
        # 売上成長率を5%刻みで生成
        for i in range(0, 50, 5):
            label = f'{i}~{i+5}%'
            conditions['売上成長率_平均'].append((label, lambda x, min_val=i, max_val=i+5: (x >= min_val) & (x < max_val)))
        conditions['売上成長率_平均'].append(('50%以上', lambda x: x >= 50))
        
        # 業種を動的に取得
        industries = df['業種'].dropna().unique()
        conditions['業種'] = [(industry, lambda x, ind=industry: x == ind) for industry in industries]
        
        return conditions
    
    def apply_filter(self, df, condition_name, condition_func):
        """
        単一条件でフィルタを適用
        """
        if condition_name == '業種':
            return condition_func(df['業種'])
        else:
            return condition_func(df[condition_name])
    
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
        
        # X倍に対応する年数のカラム名を取得
        years_column = f'{x_bagger}倍まで何年'
        
        if years_column not in df.columns:
            return None
            
        # 年数データを取得（-1は除外）
        years_data = df[years_column].dropna()
        years_data = years_data[years_data != -1]
        
        if len(years_data) == 0:
            return None
            
        # 中央値を計算
        median = years_data.median()
        return round(median, 2) if not pd.isna(median) else None
    
    def generate_combinations(self, conditions):
        """
        条件の組み合わせを生成
        """
        results = []
        
        # 各カテゴリの条件名とフィルタ関数のリスト
        categories = list(conditions.keys())
        
        # 単一条件
        for category in categories:
            for condition_name, condition_func in conditions[category]:
                results.append(([f"{category}が{condition_name}"], {category: (condition_name, condition_func)}))
        
        # 2つの条件の組み合わせ
        for cat1, cat2 in combinations(categories, 2):
            for (cond1_name, cond1_func), (cond2_name, cond2_func) in product(conditions[cat1], conditions[cat2]):
                condition_desc = [f"{cat1}が{cond1_name}", f"{cat2}が{cond2_name}"]
                condition_dict = {cat1: (cond1_name, cond1_func), cat2: (cond2_name, cond2_func)}
                results.append((condition_desc, condition_dict))
        
        # 3つの条件の組み合わせ（一部のみ、計算量を抑制）
        important_categories = ['オーナー株%', '想定時価総額', 'PER']
        if all(cat in categories for cat in important_categories):
            for (cond1_name, cond1_func), (cond2_name, cond2_func), (cond3_name, cond3_func) in product(
                conditions[important_categories[0]][:2],  # 最初の2つの条件のみ
                conditions[important_categories[1]][:3],  # 最初の3つの条件のみ
                conditions[important_categories[2]][:2]   # 最初の2つの条件のみ
            ):
                condition_desc = [
                    f"{important_categories[0]}が{cond1_name}",
                    f"{important_categories[1]}が{cond2_name}",
                    f"{important_categories[2]}が{cond3_name}"
                ]
                condition_dict = {
                    important_categories[0]: (cond1_name, cond1_func),
                    important_categories[1]: (cond2_name, cond2_func),
                    important_categories[2]: (cond3_name, cond3_func)
                }
                results.append((condition_desc, condition_dict))
        
        return results
    
    def run_calculation(self):
        """
        メイン計算処理
        """
        print("データを読み込み中...")
        df = self.load_all_companies_data()
        
        if df.empty:
            print("データが見つかりません。")
            return
        
        print(f"読み込み完了。企業数: {len(df)}")
        
        # 条件定義
        conditions = self.define_filter_conditions(df)
        
        # 組み合わせ生成
        print("条件の組み合わせを生成中...")
        combinations_list = self.generate_combinations(conditions)
        print(f"組み合わせ数: {len(combinations_list)}")
        
        # X倍株の範囲
        x_bagger_range = range(1, 11)  # 1倍から10倍まで
        
        # 結果格納用リスト
        results = []
        
        print("計算開始...")
        total_combinations = len(combinations_list)
        
        for idx, (condition_desc, condition_dict) in enumerate(combinations_list):
            if idx % 100 == 0:
                print(f"進捗: {idx}/{total_combinations} ({idx/total_combinations*100:.1f}%)")
            
            # フィルタを適用
            filtered_df = df.copy()
            for category, (cond_name, cond_func) in condition_dict.items():
                mask = self.apply_filter(filtered_df, category, cond_func)
                filtered_df = filtered_df[mask]
            
            # 各X倍株について計算
            for x_bagger in x_bagger_range:
                probability, x_bagger_count, median_years = self.calculate_x_bagger_probability(filtered_df, x_bagger)
                
                # 条件文字列を作成
                condition_str = " かつ ".join(condition_desc)
                
                results.append({
                    '条件': condition_str,
                    'X倍': x_bagger,
                    'X倍以上の%': round(probability, 2),
                    '何年かかったかの中央値': median_years if median_years is not None else '-',
                    'X倍以上の企業数': x_bagger_count,
                    '対象企業数': len(filtered_df)
                })
        
        # 結果をDataFrameに変換
        results_df = pd.DataFrame(results)
        
        # 結果を保存
        output_file = os.path.join(self.output_dir, "x_bagger_probability.tsv")
        results_df.to_csv(output_file, sep='\t', index=False)
        
        print(f"計算完了。結果を {output_file} に保存しました。")
        print(f"総計算件数: {len(results_df)}")
        
        # 上位結果を表示
        print("\n=== 確率の高い条件（上位10件） ===")
        top_results = results_df.nlargest(10, 'X倍以上の%')
        for _, row in top_results.iterrows():
            print(f"{row['条件']} | {row['X倍']}倍以上 | {row['X倍以上の%']}% | 中央値: {row['何年かかったかの中央値']}年 | X倍以上企業数: {row['X倍以上の企業数']} | 対象企業数: {row['対象企業数']}")


if __name__ == "__main__":
    calc = IPOCombinerCalc()
    calc.run_calculation() 