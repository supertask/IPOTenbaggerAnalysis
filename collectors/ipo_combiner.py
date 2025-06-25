import os
import pandas as pd
from collectors.settings import GeneralSettings, CombinerSettings
import time

from skopt import gp_minimize
from skopt.space import Real

from collectors.ipo_analyzer_core import IPOAnalyzerCore
from collectors.ipo_combiner_calc import IPOCombinerCalc

class NBaggerFinder:
    def __init__(self, data, n_bagger=5):
        """
        :param data: 全企業データを含むDataFrame
        :param n_bagger: n倍株の閾値
        """
        self.data = data
        self.n_bagger = n_bagger

        # 探索空間の定義（売上成長率、利益率、時価総額、オーナー株%）
        self.space = [
            Real(0, 100, name='売上成長率_最小値'),      # 売上成長率の最小値
            Real(0, 100, name='経常利益率_最小値'),      # 経常利益率の最小値
            Real(0, 50_000_000_000, name='想定時価総額_最大値'),  # 想定時価総額の最大値
            Real(0, 100, name='オーナー株比率_最小値')   # オーナー株%の最小値
        ]
        
    def filter_data(self, sales_growth_min, profit_margin_min, market_cap_max, owner_share_min):
        """
        フィルタリングされたデータを取得
        """
        filtered_df = self.data[
            (self.data['売上成長率_平均'] >= sales_growth_min) &
            (self.data['経常利益率_平均'] >= profit_margin_min) &
            (self.data['想定時価総額'] <= market_cap_max) &
            (self.data['オーナー株%'] >= owner_share_min)
        ]
        return filtered_df

    def objective(self, params):
        """
        最適化のための目的関数
        """
        sales_growth_min, profit_margin_min, market_cap_max, owner_share_min = params
        
        filtered_df = self.filter_data(sales_growth_min, profit_margin_min, market_cap_max, owner_share_min)
        total_companies = len(filtered_df)
        
        if total_companies == 0:
            return 0  # フィルタ結果がゼロの場合、0を返す
        
        ratio = (filtered_df['現在何倍株'] > self.n_bagger).sum() / total_companies * 100
        return -ratio  # 最小化問題として扱うため、負の値を返す

    def find_best_params(self, n_calls=50):
        """
        ベイズ最適化を使用して最適なフィルター条件を探索
        """
        result = gp_minimize(self.objective, self.space, n_calls=n_calls, random_state=42)
        
        best_params = dict(zip([dim.name for dim in self.space], result.x))
        best_ratio = -result.fun
        
        print(f"最適な条件: {best_params}")
        print(f"{self.n_bagger}倍株の割合: {best_ratio:.2f}%")
        
        return best_params, best_ratio

class IPOCombiner(IPOAnalyzerCore):
    def __init__(self):
        """
        各データフォルダと出力先フォルダを初期化
        """
        super().__init__()
        self.combiner_settings = CombinerSettings()
        os.makedirs(self.combiner_settings.output_dir, exist_ok=True)
        self.all_combined_df = pd.DataFrame() 

    def load_tsv(self, directory, filename):
        """
        指定されたフォルダからTSVファイルを読み込む
        """
        file_path = os.path.join(directory, filename)
        if os.path.exists(file_path):
            return pd.read_csv(file_path, sep='\t')
        else:
            print(f"File not found: {file_path}")
            return pd.DataFrame()

    def reorder_columns(self, df):
        # 優先するカラムのリスト
        priority_columns = [
            '企業名', '現在何倍株', '最大何倍株', '上場日', '3,5,7,10,N倍まで何年', 
            'オーナー株%', '売上成長率_平均', '経常利益率_平均', '想定時価総額', '売買回転率',
            '公募%', '売り出し%', 'オーバーアロットメント%',
            '事業内容', '上場までの年数'
        ]

        # 残りのカラム
        remaining_columns = [col for col in df.columns if col not in priority_columns]
        
        # カラムを再配置
        new_column_order = priority_columns + remaining_columns
        return df[new_column_order]


    def combine_files(self, year):
        """
        指定された年のTSVファイルを結合する
        """
        kiso_file = f"companies_{year}.tsv"
        traders_file = f"companies_{year}.tsv"
        yfinance_file = f"companies_{year}.tsv"

        # 各データフレームを読み込み
        kiso_df = self.load_tsv(self.combiner_settings.kiso_output_dir, kiso_file)
        traders_df = self.load_tsv(self.combiner_settings.traders_output_dir, traders_file)
        yfinance_df = self.load_tsv(self.combiner_settings.yfinance_output_dir, yfinance_file)

        kiso_df = kiso_df.drop(columns=['企業名', '上場日', '想定時価総額（億円）', '会社設立', '市場'], errors='ignore')
        yfinance_df = yfinance_df.drop(columns=['企業名'], errors='ignore')
        
        print(year)
        kiso_df["コード"] = kiso_df["コード"].astype(str)
        traders_df["コード"] = traders_df["コード"].astype(str)
        yfinance_df["コード"] = yfinance_df["コード"].astype(str)
        #edinet_df["コード"] = edinet_df["コード"].astype(str)

        # データをコードで結合
        combined_df = kiso_df.merge(traders_df, on="コード", how="outer")
        combined_df = combined_df.merge(yfinance_df, on="コード", how="outer")
        #combined_df = combined_df.merge(edinet_df, on="コード", how="outer")

        ipo_datetime_str = traders_df['上場日']
        ipo_year = pd.to_datetime(ipo_datetime_str).dt.year
        # 設立年にNaNが含まれている場合の対処
        combined_df['上場までの年数'] = ipo_year - combined_df['設立年'].fillna(0).astype(int)
        combined_df['上場年'] = ipo_year
        combined_df['売買回転率'] = round(combined_df["上場後の取引量"].astype(float) / combined_df["上場時発行済株数"].astype(float), 3)

        combined_df = self.reorder_columns(combined_df)

        # 出力ファイルパス
        output_file = os.path.join(self.combiner_settings.output_dir, f"companies_{year}.tsv")

        # データをTSV形式で保存
        combined_df.to_csv(output_file, sep='\t', index=False)
        #print(f"Combined data saved to {output_file}")
        
        return combined_df

#    def combine_all_files(self):
#        """
#        設定されたすべての年のTSVファイルを結合する
#        """
#        for year in self.combiner_settings.years:
#            #print(f"Processing year: {year}")
#            combined_df = self.combine_files(year)
#            #if year > 2019:
#            #if year <= 2019:
#            self.all_combined_df = pd.concat([self.all_combined_df, combined_df], ignore_index=True)  # 結果を連結
#        output_file = os.path.join(self.combiner_settings.output_dir, f"all_companies.tsv")
#        self.all_combined_df.to_csv(output_file, sep='\t', index=False)



    def static(self):
        #
        # 統計
        #
        filtered_df = self.all_combined_df[
            (self.all_combined_df['上場年'] <= 2019) &
            (self.all_combined_df['売上成長率_平均'] >= 0.4) &
            (self.all_combined_df['経常利益率_平均'] >= 39) &
            (self.all_combined_df['想定時価総額'] <= 120_000_000_000) &
            (self.all_combined_df['オーナー株%'] >= 6)
        ]
        # 指定条件に基づく割合の計算
        total_companies = len(filtered_df)
        n_bagger = 5
        if total_companies > 0:
            more_than_n_current = (filtered_df['現在何倍株'] > n_bagger).sum() / total_companies * 100
            more_than_n_max = (filtered_df['最大何倍株'] > n_bagger).sum() / total_companies * 100
        else:
            more_than_n_current = more_than_5_max = 0
        print(f"条件を満たす企業のうち、現在何倍株が{n_bagger}より大きい割合: {more_than_n_current:.2f}%")
        print(f"条件を満たす企業のうち、最大何倍株が{n_bagger}より大きい割合: {more_than_n_max:.2f}%")
        
        num_current_gt_5 = filtered_df[filtered_df['現在何倍株'] > n_bagger].shape[0]
        num_max_gt_5 = filtered_df[filtered_df['最大何倍株'] > n_bagger].shape[0]
        total_companies = filtered_df.shape[0]
        print(f"現在何倍株が5より大きい企業の数: {num_current_gt_5}")
        print(f"最大何倍株が5より大きい企業の数: {num_max_gt_5}")
        print(f"条件を満たす企業の総数: {total_companies}")


    def calculate_and_save_distributions(self):
        """
        最大何倍株が特定の条件（3, 5, 7, 10以上）を満たす場合に、各列の分布を計算して結果をTSVで保存
        """
        # 分布を計算する列と対応する範囲を定義
        columns_and_bins = {
            'オーナー株%': [0, 1] + list(range(10, 101, 10)),  # 0 ~ 1%, 1 ~ 10%, ..., 90 ~ 100%
            '売上成長率_平均': [-float('inf')] + list(range(-100, 101, 10)) + [float('inf')],  # -100%より低い, -100% ~ -90%, ..., 90% ~ 100%, 100%より高い
            '経常利益率_平均': [-float('inf')] + list(range(-100, 101, 10)) + [float('inf')],  # -100%より低い, -100% ~ -90%, ..., 90% ~ 100%, 100%より高い
            '想定時価総額': list(range(0, 100_000_000_000 + 1, 5_000_000_000)) + [float('inf')],  # 0 ~ 50億, ..., 1000億以上
            '売買回転率':  [0, 1] + list(range(10, 101, 10)) + [float('inf')]  # 0 ~ 10%, ..., 100%以上
        }


        # 特定の最大何倍株条件
        max_n_bagger_conditions = [3, 5, 7, 10]

        for condition in max_n_bagger_conditions:
            # 条件に一致する行をフィルタリング
            filtered_df = self.all_combined_df[self.all_combined_df['最大何倍株'] >= condition]

            # 条件に応じた保存先フォルダを作成
            condition_dir = os.path.join(self.combiner_settings.output_dir, f"max_n_bagger_{condition}")
            os.makedirs(condition_dir, exist_ok=True)

            # 各列ごとに分布を計算して保存
            for column, bins in columns_and_bins.items():
                # 条件を満たすデータの分布を計算
                filtered_counts = pd.cut(filtered_df[column], bins=bins).value_counts(sort=False)

                # 全体の分布を計算
                total_counts = pd.cut(self.all_combined_df[column], bins=bins).value_counts(sort=False)

                # 区間名を文字列に変換
                interval_strings = total_counts.index.astype(str)

                # `想定時価総額_区間`の場合、数値を1億で割る
                if column == '想定時価総額':
                    interval_strings = interval_strings.map(
                        lambda x: f"({float(x.split(',')[0][1:]) / 1e8}, {float(x.split(',')[1][:-1]) / 1e8}]"
                        if x != "nan" else "nan"
                    )

                # 結果をデータフレームに変換
                dist_df = pd.DataFrame({
                    f'{column}_区間': interval_strings,       # 区間名
                    f'{condition}倍株件数': filtered_counts.values,  # 条件を満たす件数
                    '全体件数': total_counts.values         # 全体の件数
                })

                # データフレームをTSVで保存
                output_file = os.path.join(condition_dir, f"{column}_distribution.tsv")
                dist_df.to_csv(output_file, sep='\t', index=False)

            print(f"最大何倍株 >= {condition} の分布計算結果を {condition_dir} に保存しました")


    def combine_all_files(self):
        """
        設定されたすべての年のTSVファイルを結合する
        """
        for year in self.combiner_settings.years:
            #print(f"Processing year: {year}")
            combined_df = self.combine_files(year)
            #if year > 2019:
            #if year <= 2019:
            self.all_combined_df = pd.concat([self.all_combined_df, combined_df], ignore_index=True)  # 結果を連結
        output_file = os.path.join(self.combiner_settings.output_dir, f"all_companies.tsv")
        self.all_combined_df.to_csv(output_file, sep='\t', index=False)

    def run(self):
        for year in self.combiner_settings.years:
            self.combine_files(year)
        self.combine_all_files()
        #self.calculate_and_save_distributions()
        #self.static()
        
        # IPOCombinerCalcを実行
        print("X倍株確率計算を開始します...")
        calc = IPOCombinerCalc()
        calc.run_calculation()

# 使用例
if __name__ == "__main__":
    combiner = IPOCombiner()
    combiner.run()
    all_combined_df = combiner.all_combined_df
    #combined_df = all_combined_df[all_combined_df['上場年'] <= 2020]

    # NBaggerFinderの実行時間を計測
    #start_time = time.time()
    #finder = NBaggerFinder(combined_df, n_bagger=5)
    #best_params, best_ratio = finder.find_best_params()
    #print("NBaggerFinder (CPU) - 実行時間: {:.2f}秒".format(time.time() - start_time))
    #print("最適な条件:", best_params)
    #print(f"5倍株の割合: {best_ratio:.2f}%\n")
