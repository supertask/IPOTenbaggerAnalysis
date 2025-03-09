from typing import Dict, List, Tuple, Any, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging

from .config import CHART_COLORS, CHART_DISPLAY_ORDER
from .data_service import DataService
from .utils import (
    format_currency_unit,
    format_per_person_unit,
    determine_unit_from_max_value,
    format_value_with_unit,
    format_percentage,
    format_percentage_raw
)

logger = logging.getLogger(__name__)

class ChartService:
    def __init__(self, company_code: str, company_name: str):
        self.company_code = company_code
        self.company_name = company_name
        self.data_service = DataService()
        
        # 競合企業の色を生成
        self.competitor_bar_colors = [
            f'rgba({r}, {g}, {b}, {CHART_COLORS["competitor_alpha"]["bar"]})'
            for r, g, b in CHART_COLORS['competitor_base']
        ]
        self.competitor_line_colors = [
            f'rgba({r}, {g}, {b}, {CHART_COLORS["competitor_alpha"]["line"]})'
            for r, g, b in CHART_COLORS['competitor_base']
        ]

    def generate_comparison_charts(self) -> Tuple[List[Dict[str, str]], Optional[str]]:
        """企業と競合他社の比較チャートを生成"""
        try:
            competitors = self.data_service.get_competitors(self.company_code)
            
            # メイン企業のデータを取得
            main_company_data, error = self.data_service.get_company_data(self.company_code)
            if error:
                return [], error
            
            main_metrics = self.data_service.extract_metrics(main_company_data)
            
            # 競合企業のデータを取得
            competitors_data = {}
            if competitors:
                for competitor in competitors:
                    comp_code = competitor['code']
                    comp_data, _ = self.data_service.get_company_data(comp_code)
                    if comp_data is not None:
                        competitors_data[comp_code] = self.data_service.extract_metrics(comp_data)
            
            charts = []
            
            # 売上高と売上高成長率の複合グラフを生成
            sales_chart = self._generate_metric_growth_chart('売上高', '売上高', main_metrics, competitors_data, competitors)
            if sales_chart:
                charts.append(sales_chart)
            
            # 営業利益と営業利益成長率の複合グラフを生成
            profit_chart = self._generate_metric_growth_chart('営業利益', '営業利益', main_metrics, competitors_data, competitors)
            if profit_chart:
                charts.append(profit_chart)
            
            # １株当たり四半期純利益と１株当たり四半期純利益成長率の複合グラフを生成
            eps_chart = self._generate_metric_growth_chart('１株当たり四半期純利益（EPS）', '１株当たり四半期純利益（EPS）', main_metrics, competitors_data, competitors)
            if eps_chart:
                charts.append(eps_chart)
            
            # その他の指標のチャートを生成
            for metric_name, metric_data in main_metrics.items():
                if not metric_data or metric_name in ['売上高', '営業利益', '１株当たり四半期純利益（EPS）']:
                    continue
                
                chart = self._generate_metric_chart(metric_name, metric_data, competitors_data, competitors)
                if chart:
                    charts.append(chart)
            
            # 設定に基づいてグラフを並べ替え
            def get_chart_order(chart):
                title = chart['title']
                try:
                    return CHART_DISPLAY_ORDER.index(title)
                except ValueError:
                    # リストに含まれていない場合は最後に表示
                    return len(CHART_DISPLAY_ORDER)
            
            sorted_charts = sorted(charts, key=get_chart_order)
            
            return sorted_charts, None
        except Exception as e:
            logger.error(f"チャート生成中にエラー: {e}", exc_info=True)
            return [], "チャートの生成に失敗しました"

    def _generate_metric_growth_chart(
        self,
        metric_name: str,
        chart_title: str,
        main_metrics: Dict[str, Dict[str, float]],
        competitors_data: Dict[str, Dict[str, Dict[str, float]]],
        competitors: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """指標と成長率の複合グラフを生成"""
        try:
            if metric_name not in main_metrics or not main_metrics[metric_name]:
                return None
            
            # 指標データを取得
            metric_data = main_metrics[metric_name]
            
            # 年度のリストを取得（ソート済み）
            years = sorted(metric_data.keys())
            if len(years) < 2:
                # 成長率を計算するには少なくとも2年分のデータが必要
                return self._generate_metric_chart(metric_name, metric_data, competitors_data, competitors)
            
            # 成長率を計算
            growth_rates = {}
            for i in range(1, len(years)):
                prev_year = years[i-1]
                curr_year = years[i]
                prev_value = metric_data[prev_year]
                curr_value = metric_data[curr_year]
                
                if prev_value != 0:
                    growth_rate = (curr_value - prev_value) / abs(prev_value) * 100
                    growth_rates[curr_year] = growth_rate
            
            # 競合企業の成長率を計算
            competitors_growth_rates = {}
            for comp_code, comp_metrics in competitors_data.items():
                if metric_name in comp_metrics and comp_metrics[metric_name]:
                    comp_metric_data = comp_metrics[metric_name]
                    comp_years = sorted(comp_metric_data.keys())
                    
                    if len(comp_years) >= 2:
                        comp_growth_rates = {}
                        for i in range(1, len(comp_years)):
                            prev_year = comp_years[i-1]
                            curr_year = comp_years[i]
                            prev_value = comp_metric_data[prev_year]
                            curr_value = comp_metric_data[curr_year]
                            
                            if prev_value != 0:
                                growth_rate = (curr_value - prev_value) / abs(prev_value) * 100
                                comp_growth_rates[curr_year] = growth_rate
                        
                        competitors_growth_rates[comp_code] = comp_growth_rates
            
            # サブプロットを作成（左軸：指標値、右軸：成長率）
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 単位を決定
            all_values = list(metric_data.values())
            for comp_metrics in competitors_data.values():
                if metric_name in comp_metrics and comp_metrics[metric_name]:
                    all_values.extend(comp_metrics[metric_name].values())
            
            unit, divisor = determine_unit_from_max_value(max(all_values) if all_values else 0)
            
            # メイン企業の指標値を棒グラフとして追加
            fig.add_trace(
                go.Bar(
                    x=list(metric_data.keys()),
                    y=[value / divisor for value in metric_data.values()],
                    name=f"{self.company_name} {metric_name}",
                    marker_color=CHART_COLORS["main"]["bar"],
                    hovertemplate=f"%{{x}}: %{{y:.2f}}{unit}<extra></extra>"
                ),
                secondary_y=False
            )
            
            # メイン企業の成長率を折れ線グラフとして追加
            if growth_rates:
                fig.add_trace(
                    go.Scatter(
                        x=list(growth_rates.keys()),
                        y=list(growth_rates.values()),
                        name=f"{self.company_name} 成長率",
                        mode="lines+markers",
                        line=dict(color=CHART_COLORS["main"]["line"], width=3),
                        marker=dict(size=8),
                        hovertemplate="%{x}: %{y:.2f}%<extra></extra>"
                    ),
                    secondary_y=True
                )
            
            # 競合企業のデータを追加
            for i, competitor in enumerate(competitors):
                comp_code = competitor['code']
                comp_name = competitor['name']
                
                if comp_code in competitors_data and metric_name in competitors_data[comp_code]:
                    comp_metric_data = competitors_data[comp_code][metric_name]
                    
                    if comp_metric_data:
                        # 競合企業の指標値を棒グラフとして追加
                        fig.add_trace(
                            go.Bar(
                                x=list(comp_metric_data.keys()),
                                y=[value / divisor for value in comp_metric_data.values()],
                                name=f"{comp_name} {metric_name}",
                                marker_color=self.competitor_bar_colors[i % len(self.competitor_bar_colors)],
                                hovertemplate=f"%{{x}}: %{{y:.2f}}{unit}<extra></extra>"
                            ),
                            secondary_y=False
                        )
                        
                        # 競合企業の成長率を折れ線グラフとして追加
                        if comp_code in competitors_growth_rates and competitors_growth_rates[comp_code]:
                            comp_growth_rates = competitors_growth_rates[comp_code]
                            fig.add_trace(
                                go.Scatter(
                                    x=list(comp_growth_rates.keys()),
                                    y=list(comp_growth_rates.values()),
                                    name=f"{comp_name} 成長率",
                                    mode="lines+markers",
                                    line=dict(
                                        color=self.competitor_line_colors[i % len(self.competitor_line_colors)],
                                        width=2,
                                        dash="dot"
                                    ),
                                    marker=dict(size=6),
                                    hovertemplate="%{x}: %{y:.2f}%<extra></extra>"
                                ),
                                secondary_y=True
                            )
            
            # グラフのレイアウトを設定
            fig.update_layout(
                title=f"{chart_title}と{chart_title}成長率",
                barmode="group",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                margin=dict(l=50, r=50, t=80, b=50),
                height=500
            )
            
            # 軸のタイトルを設定
            fig.update_yaxes(title_text=f"{metric_name} ({unit})", secondary_y=False)
            fig.update_yaxes(title_text="成長率 (%)", secondary_y=True)
            
            # HTMLに変換
            chart_html = fig.to_html(full_html=False, include_plotlyjs=False)
            
            return {
                "title": f"{chart_title}と{chart_title}成長率",
                "html": chart_html
            }
        except Exception as e:
            logger.error(f"{metric_name}の成長率チャート生成中にエラー: {e}", exc_info=True)
            return None

    def _generate_metric_chart(
        self,
        metric_name: str,
        metric_data: Dict[str, float],
        competitors_data: Dict[str, Dict[str, Dict[str, float]]],
        competitors: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """単一指標のチャートを生成"""
        try:
            if not metric_data:
                return None
            
            # 年度のリストを取得（ソート済み）
            years = sorted(metric_data.keys())
            
            # 単位を決定
            all_values = list(metric_data.values())
            for comp_metrics in competitors_data.values():
                if metric_name in comp_metrics and comp_metrics[metric_name]:
                    all_values.extend(comp_metrics[metric_name].values())
            
            unit, divisor = determine_unit_from_max_value(max(all_values) if all_values else 0)
            
            # グラフを作成
            fig = go.Figure()
            
            # メイン企業のデータを追加
            fig.add_trace(
                go.Bar(
                    x=years,
                    y=[value / divisor for value in [metric_data[year] for year in years]],
                    name=self.company_name,
                    marker_color=CHART_COLORS["main"]["bar"],
                    hovertemplate=f"%{{x}}: %{{y:.2f}}{unit}<extra></extra>"
                )
            )
            
            # 競合企業のデータを追加
            for i, competitor in enumerate(competitors):
                comp_code = competitor['code']
                comp_name = competitor['name']
                
                if comp_code in competitors_data and metric_name in competitors_data[comp_code]:
                    comp_metric_data = competitors_data[comp_code][metric_name]
                    
                    if comp_metric_data:
                        comp_years = sorted(comp_metric_data.keys())
                        fig.add_trace(
                            go.Bar(
                                x=comp_years,
                                y=[value / divisor for value in [comp_metric_data[year] for year in comp_years]],
                                name=comp_name,
                                marker_color=self.competitor_bar_colors[i % len(self.competitor_bar_colors)],
                                hovertemplate=f"%{{x}}: %{{y:.2f}}{unit}<extra></extra>"
                            )
                        )
            
            # グラフのレイアウトを設定
            fig.update_layout(
                title=metric_name,
                barmode="group",
                yaxis=dict(title=f"{metric_name} ({unit})"),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                margin=dict(l=50, r=50, t=80, b=50),
                height=400
            )
            
            # HTMLに変換
            chart_html = fig.to_html(full_html=False, include_plotlyjs=False)
            
            return {
                "title": metric_name,
                "html": chart_html
            }
        except Exception as e:
            logger.error(f"{metric_name}のチャート生成中にエラー: {e}", exc_info=True)
            return None 