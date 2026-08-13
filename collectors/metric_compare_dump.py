"""「財務指標の比較」に出ている数字を、自社と競合ぶんまとめて出す。

詳細ページ下部の比較チャートは20枚近くあり、目で追うのは骨が折れる。
どれを見るべきかを書く（`.claude/skills/metric-reading`）ための材料。

チャートと同じデータ源（`data_service.extract_metrics`）から取るので、
ここに出る数字は画面のグラフと一致する。

  python collectors/metric_compare_dump.py 212A
  python collectors/metric_compare_dump.py --portfolio --brief
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.holding_profile_dump import portfolio_codes

# 見るべきものを決めるときに効く順。config.CHART_DISPLAY_ORDER とほぼ同じだが、
# 先に伸び・採算・効率を置いている
ORDER = [
    "時価総額（PER×当期純利益）",
    "売上高", "営業利益", "営業利益率", "当期純利益", "経常利益",
    "PEGレシオ（PER / EPS成長率）", "PER（株価収益率）",
    "ROE（自己資本利益率）", "ROA（総資産利益率）", "自己資本比率",
    "１株当たり当期純利益（EPS）", "希薄化後EPS", "潜在株式による希薄化率",
    "総人員あたり営業利益", "従業員一人当たり営業利益",
    "総人員（正社員＋臨時）", "臨時雇用の比率", "従業員数", "平均臨時雇用人員",
    "平均年間給与", "平均勤続年数", "平均年齢", "純資産", "総資産",
]


# 割合の指標。0.24 のように小数で入っているので%に直す
RATIO = ("率", "ROE", "ROA", "利益率", "自己資本比率", "比率", "配当性向")
# 倍率で読むもの。%にすると意味が変わる
MULTIPLE = ("PER（", "PEGレシオ", "PSR（", "利益の質", "有利子負債÷純資産",
            "ネットキャッシュ比率")
# 小さいほうが良い指標。順位を逆にしないと「割高な会社が1位」になる。
# 「時価総額（PER×当期純利益）」のように名前にPERを含むだけのものを
# 拾わないよう、頭からの一致で見る。利益の質は大きいほうが良いので入れない
LOWER_IS_BETTER = ("PER（", "PEGレシオ", "PSR（", "有利子負債÷純資産", "在庫の伸び")
# 大小に良し悪しが無い指標。順位を出すと「小さいから4位」と読めてしまう
NO_RANK = ("時価総額", "純資産", "総資産", "従業員数", "総人員（",
           "臨時雇用の比率", "平均年齢", "平均勤続年数", "平均年間給与")


def _kind(name: str) -> str:
    if any(name.startswith(w) for w in MULTIPLE):
        return "倍"
    if any(w in name for w in RATIO):
        return "率"
    return "数"


def _typical(values: list) -> float:
    """代表値。最大値で単位を決めると、分割前のEPSや若い会社の異常なROEに
    引きずられて、直近の値が「0.1千」のように読めなくなる"""
    got = sorted(abs(v) for v in values if v is not None)
    return got[len(got) // 2] if got else 0.0


def _scale(kind: str, values: list) -> tuple:
    """指標ごとに単位を1つ決める。行ごとに変わると競合と見比べられない"""
    typical = _typical(values)
    if kind == "率":
        # 0.24 で入っているものと 24 で入っているものがある
        return (100.0, "%") if typical <= 1.5 else (1.0, "%")
    if kind == "倍":
        return 1.0, "倍"
    if typical >= 1_000_000:
        return 1 / 1_000_000, "百万"
    if typical >= 10_000:
        return 1 / 1_000, "千"
    return 1.0, ""


def _fmt(value, scale=1.0, unit="") -> str:
    if value is None:
        return "–"
    v = value * scale
    text = f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}".rstrip("0").rstrip(".")
    return text + unit


def _cagr(series: dict):
    """いちばん古い年といちばん新しい年から年平均成長率を出す"""
    years = sorted(k for k, v in series.items() if v is not None)
    if len(years) < 2:
        return None
    first, last = series[years[0]], series[years[-1]]
    span = len(years) - 1
    if not first or first <= 0 or last is None or last <= 0:
        return None
    return ((last / first) ** (1 / span) - 1) * 100


def dump(code: str, brief: bool, diagnose: bool = False) -> None:
    from visualizer.next_tenbagger.data_service import DataService

    service = DataService()
    data, error = service.get_company_data(code)
    if error or data is None:
        print(f"■ {code}  データが取れません: {error}")
        return
    metrics = service.extract_metrics(data)
    competitors = service.get_competitors(code) or []

    comp_metrics = {}
    for c in competitors:
        comp_data, err = service.get_company_data(c["code"])
        if comp_data is not None:
            comp_metrics[c["code"]] = (c.get("name") or c["code"],
                                       service.extract_metrics(comp_data))

    print(f"\n{'=' * 74}")
    print(f"■ {code}   競合 {len(comp_metrics)}社: "
          f"{', '.join(n for n, _ in comp_metrics.values()) or '（登録なし）'}")
    print("=" * 74)

    names = [n for n in ORDER if n in metrics]
    names += [n for n in metrics if n not in names]
    for name in names:
        series = metrics.get(name) or {}
        series = {k: v for k, v in series.items() if v is not None}
        if not series:
            continue
        years = sorted(series)
        cagr = _cagr(series)
        latest = series[years[-1]]

        peers = []
        for _, (peer_name, peer_metrics) in comp_metrics.items():
            peer_series = {k: v for k, v in (peer_metrics.get(name) or {}).items()
                           if v is not None}
            if not peer_series:
                continue
            peer_latest = peer_series[sorted(peer_series)[-1]]
            peers.append((peer_name, peer_latest, _cagr(peer_series)))

        kind = _kind(name)
        scale, unit = _scale(kind, list(series.values())
                             + [v for _, v, _ in peers])

        rank = ""
        compared = [latest] + [v for _, v, _ in peers if v is not None]
        lower_better = any(name.startswith(w) for w in LOWER_IS_BETTER)
        if (peers and not any(name.startswith(w) for w in NO_RANK)
                and not (kind == "倍" and min(compared) <= 0)):
            # PER・PEG・D/Eは小さいほうが良いので向きを変える。ただし赤字の会社が
            # 混ざると負の倍率になり、順位に意味がなくなるので出さない
            better = (lambda v: v < latest) if lower_better else (lambda v: v > latest)
            above = sum(1 for _, v, _ in peers if v is not None and better(v))
            rank = f"  自社は{above + 1}位/{len(peers) + 1}社"

        head = f"{name}  直近{years[-1]} {_fmt(latest, scale, unit)}"
        if cagr is not None:
            head += f"  年平均{cagr:+.1f}%"
        print(f"\n{head}{rank}")
        if not brief:
            print("   自社 " + "  ".join(f"{y}:{_fmt(series[y], scale, unit)}"
                                        for y in years))
        for peer_name, peer_latest, peer_cagr in peers:
            growth = f" 年平均{peer_cagr:+.1f}%" if peer_cagr is not None else ""
            print(f"   {peer_name[:16]:18} "
                  f"{_fmt(peer_latest, scale, unit)}{growth}")

    if diagnose:
        show_diagnosis(code, metrics)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes", nargs="*")
    parser.add_argument("--portfolio", action="store_true", help="保有銘柄すべて")
    parser.add_argument("--brief", action="store_true", help="年ごとの値を出さない")
    parser.add_argument("--diagnose", action="store_true",
                        help="所見・業種の中央値・10倍株との比較・データの欠けを足す")
    args = parser.parse_args()

    codes = sorted(portfolio_codes()) if args.portfolio else args.codes
    if not codes:
        parser.error("銘柄コードか --portfolio が要ります")
    for code in codes:
        dump(code, args.brief, args.diagnose)
    return 0


def _one(name: str, v) -> str:
    if v is None:
        return "–"
    if name in ("営業利益率", "ROE", "自己資本比率"):
        return f"{v * 100:.1f}%" if abs(v) <= 1.5 else f"{v:.1f}%"
    if name == "利益の質":
        return f"{v:.2f}倍"
    return f"{v / 1e6:,.0f}百万"


def _fmt_bench(name: str, value, median) -> str:
    return f"自社 {_one(name, value):>12}   中央値 {_one(name, median):>12}"


def show_diagnosis(code: str, metrics: dict) -> None:
    from collectors import metric_diagnose

    d = metric_diagnose.diagnose(code, metrics)
    info = d["info"]
    if info:
        print(f"\n  上場 {info.get('ipo_date') or '不明'}"
              f"（{info.get('market') or ''}）  業種 {info.get('sector') or '不明'}"
              f" / {info.get('industry') or '不明'}"
              f"  最大{info.get('max_multiple') or '?'}倍")

    print(f"\n【所見】組み合わせで読めるもの。人が確かめること")
    for line in d["findings"] or ["  当てはまるものなし"]:
        print(f"  {line}")

    if d["sector"]:
        print(f"\n【同じ業種の中央値】{d.get('sector_name', '')}")
        for row in d["sector"]:
            print(f"  {row['name']:10} {_fmt_bench(row['name'], row['mine'], row['median'])}"
                  f"  {row['rank']}  （{row['n']}社）")

    if d["tenbagger"]:
        print(f"\n【上場後に何倍になったかで分けた比較】{d.get('tenbagger_label', '')}")
        counts = d.get("tenbagger_counts", {})
        labels = ["10倍以上", "3〜10倍", "2倍未満"]
        print(f"  {'':12}{'自社':>12}" + "".join(f"{l:>12}" for l in labels))
        for row in d["tenbagger"]:
            cells = "".join(f"{_one(row['name'], row['groups'].get(l)):>12}"
                            for l in labels)
            mark = "" if row["separates"] else "   ← この指標では見分けられない"
            print(f"  {row['name']:10}{_one(row['name'], row['mine']):>12}{cells}{mark}")
        print(f"  {'（社数）':10}{'':>12}"
              + "".join(f"{counts.get(l, 0):>12}" for l in labels))

    if d["gaps"]:
        print(f"\n【データの欠け・異常】比較できていないことを知らずに比べない")
        for line in d["gaps"][:8]:
            print(f"  ・{line}")


if __name__ == "__main__":
    sys.exit(main())
