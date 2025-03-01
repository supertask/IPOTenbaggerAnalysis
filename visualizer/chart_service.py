from typing import Dict, List, Tuple, Any, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging

from .config import CHART_COLORS, CHART_DISPLAY_ORDER
from .data_service import DataService

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
            
            # その他の指標のチャートを生成
            for metric_name, metric_data in main_metrics.items():
                if not metric_data or metric_name in ['売上高', '営業利益']:
                    continue
                
                chart = self._generate_metric_chart(metric_name, metric_data, competitors_data, competitors)
                if chart:
                    charts.append(chart)
            
            # 設定に基づいてグラフを並べ替え
            sorted_charts = sorted(charts, key=lambda x: CHART_DISPLAY_ORDER.get(x['title'], 999))
            
            return sorted_charts, None
        except Exception as e:
            logger.error(f"チャート生成中にエラー: {e}", exc_info=True)
            return [], "チャートの生成に失敗しました"

    def _generate_metric_growth_chart(
        self,
        metric_name: str,
        metric_label: str,
        main_metrics: Dict[str, Dict[str, float]],
        competitors_data: Dict[str, Dict[str, Dict[str, float]]],
        competitors: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """指標と成長率の複合グラフを生成する"""
        try:
            if metric_name not in main_metrics or not main_metrics[metric_name]:
                return None
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 全ての年度を収集
            all_years = set(main_metrics[metric_name].keys())
            for comp_metrics in competitors_data.values():
                if metric_name in comp_metrics:
                    all_years.update(comp_metrics[metric_name].keys())
            
            sorted_years = sorted(all_years)
            
            # 競合企業のデータをプロット
            for i, (comp_code, comp_metrics) in enumerate(competitors_data.items()):
                if metric_name in comp_metrics and comp_metrics[metric_name]:
                    comp_name = next((c['name'] for c in competitors if c['code'] == comp_code), comp_code)
                    color_index = i % len(self.competitor_bar_colors)
                    
                    # 競合企業の指標（棒グラフ）
                    comp_values = [comp_metrics[metric_name].get(year, None) for year in sorted_years]
                    fig.add_trace(
                        go.Bar(
                            x=sorted_years,
                            y=comp_values,
                            name=f"{comp_name} {metric_label}",
                            marker_color=self.competitor_bar_colors[color_index]
                        ),
                        secondary_y=False
                    )
                    
                    # 競合企業の成長率（折れ線グラフ）
                    comp_growth_rates = self.data_service.calculate_growth_rate(comp_metrics[metric_name])
                    if comp_growth_rates:
                        comp_growth_values = [comp_growth_rates.get(year, None) for year in sorted_years]
                        fig.add_trace(
                            go.Scatter(
                                x=sorted_years,
                                y=comp_growth_values,
                                mode='lines+markers',
                                name=f"{comp_name} {metric_label}成長率",
                                line=dict(color=self.competitor_line_colors[color_index], width=2),
                                marker=dict(size=6),
                                connectgaps=True
                            ),
                            secondary_y=True
                        )
            
            # メイン企業のデータをプロット
            values = [main_metrics[metric_name].get(year, None) for year in sorted_years]
            fig.add_trace(
                go.Bar(
                    x=sorted_years,
                    y=values,
                    name=f"{self.company_name} {metric_label}",
                    marker_color=CHART_COLORS['main']['bar'],
                    opacity=0.8,
                ),
                secondary_y=False
            )
            
            # メイン企業の成長率をプロット
            growth_rates = self.data_service.calculate_growth_rate(main_metrics[metric_name])
            if growth_rates:
                growth_values = [growth_rates.get(year, None) for year in sorted_years]
                fig.add_trace(
                    go.Scatter(
                        x=sorted_years,
                        y=growth_values,
                        mode='lines+markers',
                        name=f"{self.company_name} {metric_label}成長率",
                        line=dict(color=CHART_COLORS['main']['line'], width=3),
                        marker=dict(size=8),
                        connectgaps=True
                    ),
                    secondary_y=True
                )
            
            # グラフのレイアウトを設定
            fig.update_layout(
                title=f"{metric_label}と{metric_label}成長率の比較",
                xaxis_title="年度",
                yaxis_title=metric_label,
                yaxis2_title="成長率 (%)",
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
        except Exception as e:
            logger.error(f"成長率チャート生成中にエラー: {e}", exc_info=True)
            return None

    def _generate_metric_chart(
        self,
        metric_name: str,
        metric_data: Dict[str, float],
        competitors_data: Dict[str, Dict[str, Dict[str, float]]],
        competitors: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """通常の指標のチャートを生成"""
        try:
            fig = go.Figure()
            
            # 全ての年度を収集
            all_years = set(metric_data.keys())
            for comp_metrics in competitors_data.values():
                if metric_name in comp_metrics:
                    all_years.update(comp_metrics[metric_name].keys())
            
            sorted_years = sorted(all_years)
            
            # 競合企業のデータをプロット
            for i, (comp_code, comp_metrics) in enumerate(competitors_data.items()):
                if metric_name in comp_metrics and comp_metrics[metric_name]:
                    comp_values = [comp_metrics[metric_name].get(year, None) for year in sorted_years]
                    comp_name = next((c['name'] for c in competitors if c['code'] == comp_code), comp_code)
                    color_index = i % len(self.competitor_line_colors)
                    
                    fig.add_trace(
                        go.Scatter(
                            x=sorted_years,
                            y=comp_values,
                            mode='lines+markers',
                            name=f"{comp_name} ({comp_code})",
                            line=dict(color=self.competitor_line_colors[color_index], width=2),
                            marker=dict(size=6),
                            connectgaps=True,
                            opacity=0.8
                        )
                    )
            
            # メイン企業のデータをプロット
            values = [metric_data.get(year, None) for year in sorted_years]
            fig.add_trace(
                go.Scatter(
                    x=sorted_years,
                    y=values,
                    mode='lines+markers',
                    name=f"{self.company_name} ({self.company_code})",
                    line=dict(color=CHART_COLORS['main']['line'], width=3),
                    marker=dict(size=8),
                    connectgaps=True
                )
            )
            
            # グラフのレイアウトを設定
            fig.update_layout(
                title=f"{metric_name}の比較",
                xaxis_title="年度",
                yaxis_title=metric_name,
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
                    type='category',
                    categoryorder='array',
                    categoryarray=sorted_years
                )
            )
            
            return {
                'title': metric_name,
                'plotly_data': fig.to_json()
            }
        except Exception as e:
            logger.error(f"指標チャート生成中にエラー: {e}", exc_info=True)
            return None 
