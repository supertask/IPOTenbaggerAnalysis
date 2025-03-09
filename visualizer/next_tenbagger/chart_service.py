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
                    competitor_code = competitor['code']
                    competitor_data, _ = self.data_service.get_company_data(competitor_code)
                    if competitor_data is not None:
                        competitors_data[competitor_code] = self.data_service.extract_metrics(competitor_data)
            
            # チャートを生成
            charts = []
            
            # 売上高と成長率のチャート
            if '売上高' in main_metrics:
                revenue_growth_chart = self._generate_metric_growth_chart(
                    '売上高', '売上高', main_metrics, competitors_data, competitors
                )
                if revenue_growth_chart:
                    charts.append(revenue_growth_chart)
            
            # 営業利益と成長率のチャート
            if '営業利益' in main_metrics:
                operating_profit_growth_chart = self._generate_metric_growth_chart(
                    '営業利益', '営業利益', main_metrics, competitors_data, competitors
                )
                if operating_profit_growth_chart:
                    charts.append(operating_profit_growth_chart)
            
            # EPSと成長率のチャート
            if '１株当たり四半期純利益（EPS）' in main_metrics:
                eps_growth_chart = self._generate_metric_growth_chart(
                    '１株当たり四半期純利益（EPS）', '１株当たり四半期純利益（EPS）', main_metrics, competitors_data, competitors
                )
                if eps_growth_chart:
                    charts.append(eps_growth_chart)
            
            # その他の指標のチャート
            for metric_name in CHART_DISPLAY_ORDER:
                if metric_name in main_metrics and metric_name not in ['売上高', '営業利益', '１株当たり四半期純利益（EPS）']:
                    metric_chart = self._generate_metric_chart(
                        metric_name, main_metrics[metric_name], competitors_data, competitors
                    )
                    if metric_chart:
                        charts.append(metric_chart)
            
            # チャートを表示順に並べ替え
            def get_chart_order(chart):
                title = chart['title']
                for i, metric in enumerate(CHART_DISPLAY_ORDER):
                    if metric in title:
                        return i
                return len(CHART_DISPLAY_ORDER)
            
            charts.sort(key=get_chart_order)
            
            return charts, None
        except Exception as e:
            logger.error(f"チャート生成中にエラー: {e}", exc_info=True)
            return [], f"チャート生成中にエラー: {str(e)}"

    def _generate_metric_growth_chart(
        self,
        metric_name: str,
        metric_label: str,
        main_metrics: Dict[str, Dict[str, float]],
        competitors_data: Dict[str, Dict[str, Dict[str, float]]],
        competitors: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """指標と成長率のチャートを生成"""
        try:
            if metric_name not in main_metrics:
                return None
            
            metric_data = main_metrics[metric_name]
            
            # 日付でソート
            dates = sorted(metric_data.keys())
            
            if len(dates) < 2:
                return None
            
            # 成長率を計算
            growth_data = self.data_service.calculate_growth_rate(metric_data)
            
            # 単位を決定
            if metric_name == '売上高' or metric_name == '営業利益':
                y_suffix, force_unit = determine_unit_from_max_value(
                    metric_data, competitors_data, metric_name, format_currency_unit
                )
                formatter = lambda x: format_currency_unit(x, force_unit)
            elif metric_name == '１株当たり四半期純利益（EPS）':
                y_suffix = " (円)"
                formatter = lambda x: (x, "円")
            else:
                y_suffix = ""
                formatter = lambda x: (x, "")
            
            # サブプロットを作成
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # メイン企業の指標データを追加
            fig.add_trace(
                go.Bar(
                    x=dates,
                    y=[metric_data[date] for date in dates],
                    name=f"{self.company_name}の{metric_label}",
                    marker_color=CHART_COLORS['main']['bar']
                ),
                secondary_y=False
            )
            
            # メイン企業の成長率データを追加
            growth_dates = sorted(growth_data.keys())
            if growth_dates:
                fig.add_trace(
                    go.Scatter(
                        x=growth_dates,
                        y=[growth_data[date] * 100 for date in growth_dates],  # パーセント表示に変換
                        name=f"{self.company_name}の{metric_label}成長率",
                        mode='lines+markers',
                        line=dict(color=CHART_COLORS['main']['line'], width=3),
                        marker=dict(size=8)
                    ),
                    secondary_y=True
                )
            
            # 競合企業のデータを追加
            for i, competitor in enumerate(competitors):
                competitor_code = competitor['code']
                competitor_name = competitor['name']
                
                if competitor_code in competitors_data and metric_name in competitors_data[competitor_code]:
                    comp_metric_data = competitors_data[competitor_code][metric_name]
                    comp_dates = sorted(comp_metric_data.keys())
                    
                    if comp_dates:
                        # 競合企業の指標データを追加
                        fig.add_trace(
                            go.Bar(
                                x=comp_dates,
                                y=[comp_metric_data[date] for date in comp_dates],
                                name=f"{competitor_name}の{metric_label}",
                                marker_color=self.competitor_bar_colors[i % len(self.competitor_bar_colors)]
                            ),
                            secondary_y=False
                        )
                        
                        # 競合企業の成長率データを追加
                        comp_growth_data = self.data_service.calculate_growth_rate(comp_metric_data)
                        comp_growth_dates = sorted(comp_growth_data.keys())
                        
                        if comp_growth_dates:
                            fig.add_trace(
                                go.Scatter(
                                    x=comp_growth_dates,
                                    y=[comp_growth_data[date] * 100 for date in comp_growth_dates],  # パーセント表示に変換
                                    name=f"{competitor_name}の{metric_label}成長率",
                                    mode='lines+markers',
                                    line=dict(color=self.competitor_line_colors[i % len(self.competitor_line_colors)], width=2),
                                    marker=dict(size=6)
                                ),
                                secondary_y=True
                            )
            
            # レイアウトを設定
            fig.update_layout(
                title=f"{metric_label}と{metric_label}成長率の推移（四半期）",
                barmode='group',
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
            
            # Y軸のタイトルを設定
            fig.update_yaxes(title_text=f"{metric_label}{y_suffix}", secondary_y=False)
            fig.update_yaxes(title_text="成長率 (%)", secondary_y=True)
            
            # ホバー情報をカスタマイズ
            fig.update_traces(
                hovertemplate='%{x}<br>%{y}',
                selector=dict(type='bar')
            )
            fig.update_traces(
                hovertemplate='%{x}<br>%{y:.1f}%',
                selector=dict(type='scatter')
            )
            
            # チャートをHTMLに変換
            chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
            
            return {
                'title': f"{metric_label}と{metric_label}成長率",
                'html': chart_html
            }
        except Exception as e:
            logger.error(f"{metric_name}と成長率のチャート生成中にエラー: {e}", exc_info=True)
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
            # 日付でソート
            dates = sorted(metric_data.keys())
            
            if not dates:
                return None
            
            # フォーマッターを選択
            if metric_name in ['ROE（自己資本利益率）', '営業利益率', '自己資本比率', 'ROA（総資産利益率）']:
                formatter = format_percentage
                y_suffix = " (%)"
            elif metric_name in ['PER（株価収益率）', 'PEGレシオ（PER / EPS成長率）']:
                formatter = format_percentage_raw
                y_suffix = ""
            elif metric_name == '従業員一人当たり営業利益':
                formatter = format_per_person_unit
                y_suffix, force_unit = determine_unit_from_max_value(
                    metric_data, competitors_data, metric_name, format_per_person_unit
                )
            elif metric_name in ['売上高', '営業利益', '経常利益', '四半期純利益', '純資産', '総資産']:
                y_suffix, force_unit = determine_unit_from_max_value(
                    metric_data, competitors_data, metric_name, format_currency_unit
                )
                formatter = lambda x: format_currency_unit(x, force_unit)
            else:
                formatter = lambda x: (x, "")
                y_suffix = ""
            
            # グラフを作成
            fig = go.Figure()
            
            # メイン企業のデータを追加
            fig.add_trace(
                go.Bar(
                    x=dates,
                    y=[metric_data[date] for date in dates],
                    name=f"{self.company_name}",
                    marker_color=CHART_COLORS['main']['bar'],
                    hovertemplate='%{x}<br>' + metric_name + ': %{y}'
                )
            )
            
            # 競合企業のデータを追加
            for i, competitor in enumerate(competitors):
                competitor_code = competitor['code']
                competitor_name = competitor['name']
                
                if competitor_code in competitors_data and metric_name in competitors_data[competitor_code]:
                    comp_metric_data = competitors_data[competitor_code][metric_name]
                    comp_dates = sorted(comp_metric_data.keys())
                    
                    if comp_dates:
                        fig.add_trace(
                            go.Bar(
                                x=comp_dates,
                                y=[comp_metric_data[date] for date in comp_dates],
                                name=f"{competitor_name}",
                                marker_color=self.competitor_bar_colors[i % len(self.competitor_bar_colors)],
                                hovertemplate='%{x}<br>' + metric_name + ': %{y}'
                            )
                        )
            
            # レイアウトを設定
            fig.update_layout(
                title=f"{metric_name}の推移（四半期）",
                barmode='group',
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
            
            # Y軸のタイトルを設定
            fig.update_yaxes(title_text=f"{metric_name}{y_suffix}")
            
            # チャートをHTMLに変換
            chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
            
            return {
                'title': metric_name,
                'html': chart_html
            }
        except Exception as e:
            logger.error(f"{metric_name}のチャート生成中にエラー: {e}", exc_info=True)
            return None 