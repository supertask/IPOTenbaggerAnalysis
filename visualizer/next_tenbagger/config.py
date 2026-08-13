from pathlib import Path
from typing import List, Dict
from collections import OrderedDict

# ディレクトリパス設定
BASE_DIR = Path(__file__).parent.parent.parent
print(f"BASE_DIR: {BASE_DIR}")
IPO_REPORTS_NEW_DIR = BASE_DIR / 'data/output/edinet_db/ipo_reports_new'
COMPARISON_DIR = BASE_DIR / 'data/output/comparison'
ALL_COMPANIES_PATH = BASE_DIR / 'data/output/combiner/all_companies.tsv'
RECENT_IPO_COMPANIES_PATH = BASE_DIR / 'data/output/combiner/recent_ipo_companies.tsv'

# 指標の代替名マッピング（順序付き）
# 辞書のキーの順序が指標の処理順序を決定します
# 四半期報告書用の指標IDを追加
METRIC_ALIASES: Dict[str, List[str]] = OrderedDict([
    ('売上高', ['jpcrp_cor:NetSalesSummaryOfBusinessResults', 
               'jpcrp_cor:RevenueIFRSSummaryOfBusinessResults', 
               'jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults',
               'jpcrp_qcor:NetSalesQuarterlySummaryOfBusinessResults',
               'jpcrp_qcor:RevenueIFRSQuarterlySummaryOfBusinessResults',
               'jpcrp_qcor:RevenuesUSGAAPQuarterlySummaryOfBusinessResults']),
    ('営業利益', ['jppfs_cor:OperatingIncome',
                 'jppfs_qcor:OperatingIncomeQuarterly']),
    ('経常利益', ['jppfs_cor:OrdinaryIncome', 
                 'jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults',
                 'jppfs_qcor:OrdinaryIncomeQuarterly',
                 'jpcrp_qcor:OrdinaryIncomeLossQuarterlySummaryOfBusinessResults']),
    ('ROE（自己資本利益率）', ['jpcrp_cor:RateOfReturnOnEquitySummaryOfBusinessResults',
                          'jpcrp_qcor:RateOfReturnOnEquityQuarterlySummaryOfBusinessResults']),
    ('純資産', ['jpcrp_cor:NetAssetsSummaryOfBusinessResults',
               'jpcrp_qcor:NetAssetsQuarterlySummaryOfBusinessResults']),
    ('総資産', ['jpcrp_cor:TotalAssetsSummaryOfBusinessResults',
               'jpcrp_qcor:TotalAssetsQuarterlySummaryOfBusinessResults']),
    # 当期純利益。ROAの計算に要る。これが無いとROAのグラフが一度も描かれない
    ('当期純利益', ['jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults',
                 'jpcrp_cor:NetIncomeLossSummaryOfBusinessResults',
                 'jppfs_cor:ProfitLossAttributableToOwnersOfParent',
                 'jpcrp_qcor:ProfitLossAttributableToOwnersOfParentQuarterlySummaryOfBusinessResults']),
    # 末尾のsが抜けていた。next側は要素IDを完全一致で引くので、
    # 4,021社ぶんデータがあるのにグラフが一度も出ていなかった
    ('自己資本比率', ['jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults',
                   'jpcrp_qcor:EquityToAssetRatioQuarterlySummaryOfBusinessResults']),
    ('PER（株価収益率）', ['jpcrp_cor:PriceEarningsRatioSummaryOfBusinessResults',
                        'jpcrp_qcor:PriceEarningsRatioQuarterlySummaryOfBusinessResults']),
    ('従業員数', ['jpcrp_cor:NumberOfEmployees', 'jpcrp_qcor:NumberOfEmployeesQuarterly']),
    ('平均臨時雇用人員', ['jpcrp_cor:AverageNumberOfTemporaryWorkers']),
    ('１株当たり当期純利益（EPS）', ['jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults']),
    # 潜在株式を織り込んだEPS。基本EPSとの差が新株予約権などによる希薄化。
    # 小型株は発行株数が少ないぶん希薄化がリターンを食いやすい（オニールのS）
    ('希薄化後EPS', ['jpcrp_cor:DilutedEarningsPerShareSummaryOfBusinessResults']),
    ('平均年齢', ['jpcrp_cor:AverageAgeYearsInformationAboutReportingCompanyInformationAboutEmployees']),
    ('平均勤続年数', ['jpcrp_cor:AverageLengthOfServiceYearsInformationAboutReportingCompanyInformationAboutEmployees']),
    ('平均年間給与', ['jpcrp_cor:AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees']),

    # --- ここから下は 2026-08 に追加。伝説的な投資家が共通して見るもののうち、
    # インデックスに入っていなかったもの。有報120件を実際に走査してタグ名と
    # 出現率を確かめてある（括弧内が120件中の出現数）
    ('営業キャッシュフロー', [  # バフェットのowner earnings。利益が現金になっているか (119)
        'jpcrp_cor:NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults',
        'jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults',
        'jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesUSGAAPSummaryOfBusinessResults']),
    ('投資キャッシュフロー', [  # フリーCFの計算に使う (119)
        'jpcrp_cor:NetCashProvidedByUsedInInvestingActivitiesSummaryOfBusinessResults',
        'jpcrp_cor:CashFlowsFromUsedInInvestingActivitiesIFRSSummaryOfBusinessResults',
        'jpcrp_cor:CashFlowsFromUsedInInvestingActivitiesUSGAAPSummaryOfBusinessResults']),
    ('現金及び現金同等物', [  # 手元資金。リンチはネットキャッシュを見る (119)
        'jpcrp_cor:CashAndCashEquivalentsSummaryOfBusinessResults']),
    ('売上総利益', ['jppfs_cor:GrossProfit']),        # フィッシャーの価格決定力 (109)
    ('発行済株式数', [  # オニールのS。増資で1株あたりが薄まっていないか (120)
        'jpcrp_cor:TotalNumberOfIssuedSharesSummaryOfBusinessResults']),
    ('1株当たり配当', [  # 株主還元の姿勢 (120)
        'jpcrp_cor:DividendPaidPerShareSummaryOfBusinessResults']),
    # 有利子負債は1つのタグに無く、足し合わせる。リンチ「無借金なら潰れない」
    ('短期借入金', ['jppfs_cor:ShortTermLoansPayable']),                    # (77)
    ('長期借入金', ['jppfs_cor:LongTermLoansPayable']),                     # (86)
    ('1年内返済予定の長期借入金', ['jppfs_cor:CurrentPortionOfLongTermLoansPayable']),  # (77)
    ('社債', ['jppfs_cor:BondsPayable']),                                  # (19)
    # リンチの在庫シグナル。在庫の伸びが売上の伸びを超えたら赤信号
    ('商品及び製品', ['jppfs_cor:MerchandiseAndFinishedGoods']),             # (70)
    # 清原達郎のネットキャッシュ比率に要る3つ。貸借対照表の合計行なので
    # ほぼ全社にある（有報120件を走査した出現数を括弧内に）
    ('流動資産', ['jppfs_cor:CurrentAssets']),                              # (117)
    ('投資有価証券', ['jppfs_cor:InvestmentSecurities']),                    # (105)
    ('負債合計', ['jppfs_cor:Liabilities']),                                # (120)
])

# 計算に使うだけでグラフにはしないもの。出しても単独では読めない
HIDDEN_METRICS = frozenset({
    '投資キャッシュフロー', '売上総利益', '短期借入金', '長期借入金',
    '1年内返済予定の長期借入金', '社債', '商品及び製品', '希薄化後EPS',
    '１株当たり四半期純利益（EPS）',
    '流動資産', '投資有価証券', '負債合計',
})

# グラフの表示順序設定
# リスト内の位置が表示順序を決定します（先頭が最初に表示）
# 小型の成長株を探す前提で、上から順に「規模 → 成長 → 採算 → 価格 → 財務の質」。
# 括弧内はその指標を重く見る投資家
# 並べ替えはグラフの「タイトル」と突き合わせる。売上高・営業利益・EPSは
# 成長率との複合グラフだが、タイトルは素の指標名なので、ここもその名前で書く。
# 「売上高と売上高成長率」と書いていたときは一致せず、末尾に飛ばされていた。
#
# 小型の成長株を探す前提で「規模 → 成長 → 価格 → 資本効率 → 財務の質 → 人」の順。
# 括弧内はその指標を重く見る投資家
CHART_DISPLAY_ORDER = [
    # 規模 — 小さいほど倍率が伸びる（リンチ、オニールのS）
    '時価総額（PER×当期純利益）',
    # 成長 — リンチのfast grower、オニールのA（年25%以上）
    '売上高',
    '営業利益',
    '１株当たり当期純利益（EPS）',
    # 価格 — 成長に対して割高でないか（リンチ。PEG 1.0が適正、0.5未満で割安）
    'PEGレシオ（PER / EPS成長率）',
    'PER（株価収益率）',
    'PSR（時価総額÷売上高）',      # エミンの一次スクリーニング。1倍未満が目安
    # 利益の質 — 伸びが本物か（バフェットのowner earnings）
    '利益の質（営業CF÷営業利益）',
    '営業キャッシュフロー',
    'フリーキャッシュフロー',
    # 採算 — 価格決定力と資本効率（フィッシャー、バフェット、オニール）
    '売上総利益率',
    '営業利益率',
    'ROE（自己資本利益率）',
    'ROA（総資産利益率）',
    # 財務の安全 — リンチ「借金のない会社は倒産しない」、清原のネットキャッシュ
    'ネットキャッシュ比率',
    'ネットキャッシュ',
    '自己資本比率',
    '有利子負債÷純資産',
    '有利子負債',
    '現金及び現金同等物',
    # 1株あたりが薄まっていないか（オニールのS）
    '潜在株式による希薄化率',
    '発行済株式数',
    '配当性向',
    # 変調のサイン — リンチの在庫シグナル
    '在庫の伸び − 売上の伸び',
    # 人の効率
    '総人員あたり営業利益',
    '従業員一人当たり営業利益',
    '総人員（正社員＋臨時）',
    '臨時雇用の比率',
    '従業員数',
    '平均臨時雇用人員',
    # 以下は判断に効きにくい。残してあるが下に置く
    '当期純利益',
    '経常利益',
    '純資産',
    '総資産',
    '平均年間給与',
    '平均勤続年数',
    '平均年齢',
]

# チャートの色設定
CHART_COLORS = {
    "main": {
        "bar": "rgba(0, 123, 255, 0.7)",  # メイン企業の棒グラフの色
        "line": "rgba(220, 53, 69, 1)"    # メイン企業の線グラフの色
    },
    "competitor_base": [
        (108, 117, 125),  # グレー
        (40, 167, 69),    # 緑
        (255, 193, 7),    # 黄色
        (23, 162, 184),   # シアン
        (111, 66, 193),   # 紫
        (253, 126, 20)    # オレンジ
    ],
    "competitor_alpha": {
        "bar": 0.5,       # 競合企業の棒グラフの透明度
        "line": 0.8       # 競合企業の線グラフの透明度
    }
} 