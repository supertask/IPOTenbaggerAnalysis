from typing import Dict, List, Tuple, Any, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging
from datetime import datetime

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
            
            # 営業利益のチャートはスキップ
            
            # １株当たり当期純利益と１株当たり当期純利益成長率の複合グラフを生成
            eps_chart = self._generate_metric_growth_chart('１株当たり当期純利益（EPS）', '１株当たり当期純利益（EPS）', main_metrics, competitors_data, competitors)
            if eps_chart:
                charts.append(eps_chart)
            
            # 純資産のチャートを生成
            net_assets_chart = self._generate_metric_chart('純資産', main_metrics.get('純資産', {}), competitors_data, competitors)
            if net_assets_chart:
                charts.append(net_assets_chart)
                
            # 総資産のチャートを生成
            total_assets_chart = self._generate_metric_chart('総資産', main_metrics.get('総資産', {}), competitors_data, competitors)
            if total_assets_chart:
                charts.append(total_assets_chart)
                
            # 平均臨時雇用人員のチャートを生成
            temp_workers_chart = self._generate_metric_chart('平均臨時雇用人員', main_metrics.get('平均臨時雇用人員', {}), competitors_data, competitors)
            if temp_workers_chart:
                charts.append(temp_workers_chart)
            
            # その他の指標のチャートを生成
            for metric_name, metric_data in main_metrics.items():
                if not metric_data or metric_name in ['売上高', '営業利益', '１株当たり四半期純利益（EPS）', '１株当たり当期純利益（EPS）', '純資産', '総資産', '平均臨時雇用人員']:
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
            
            # メイン企業のデータを取得
            metric_data = main_metrics[metric_name]
            
            # 日付でソート
            dates = sorted(metric_data.keys())
            values = [metric_data[date] for date in dates]
            
            # 日付を年月表示に変換
            display_dates = []
            for date in dates:
                try:
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    display_dates.append(dt.strftime('%Y/%m'))
                except ValueError:
                    display_dates.append(date)
            
            # 成長率を計算
            growth_rates = DataService.calculate_growth_rate(metric_data)
            growth_dates = sorted(growth_rates.keys())
            growth_values = [growth_rates[date] for date in growth_dates]
            
            # 成長率の日付を年月表示に変換
            growth_display_dates = []
            for date in growth_dates:
                try:
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    growth_display_dates.append(dt.strftime('%Y/%m'))
                except ValueError:
                    growth_display_dates.append(date)
            
            # 単位を決定
            max_value = max(values) if values else 0
            unit_text, divisor = determine_unit_from_max_value(max_value)
            
            # 単位で割った値
            scaled_values = [value / divisor for value in values]
            
            # プロットデータを作成
            data = []
            
            # メイン企業のバーチャート
            data.append({
                'type': 'bar',
                'x': display_dates,
                'y': scaled_values,
                'name': self.company_name,
                'marker': {'color': CHART_COLORS['main']['bar']},
                'hovertemplate': '%{x}: %{y:.2f}<extra></extra>'
            })
            
            # 競合企業のバーチャート
            for i, competitor in enumerate(competitors):
                comp_code = competitor['code']
                if comp_code in competitors_data and metric_name in competitors_data[comp_code]:
                    comp_data = competitors_data[comp_code][metric_name]
                    
                    # 競合企業のデータを日付でソート
                    comp_dates = sorted(comp_data.keys())
                    comp_values = [comp_data[date] if date in comp_data else None for date in dates]
                    
                    # 単位で割った値
                    scaled_comp_values = [value / divisor if value is not None else None for value in comp_values]
                    
                    # 競合企業のバーチャートを追加
                    data.append({
                        'type': 'bar',
                        'x': display_dates,
                        'y': scaled_comp_values,
                        'name': competitor['name'],
                        'marker': {'color': self.competitor_bar_colors[i % len(self.competitor_bar_colors)]},
                        'hovertemplate': '%{x}: %{y:.2f}<extra></extra>'
                    })
            
            # メイン企業の成長率ラインチャート
            if growth_values:
                data.append({
                    'type': 'scatter',
                    'x': growth_display_dates,
                    'y': [rate * 100 for rate in growth_values],  # パーセント表示
                    'name': f'{self.company_name} 成長率',
                    'yaxis': 'y2',
                    'line': {'color': CHART_COLORS['main']['line'], 'width': 3},
                    'hovertemplate': '%{x}: %{y:.2f}%<extra></extra>'
                })
            
            # 競合企業の成長率ラインチャート
            for i, competitor in enumerate(competitors):
                comp_code = competitor['code']
                if comp_code in competitors_data and metric_name in competitors_data[comp_code]:
                    comp_data = competitors_data[comp_code][metric_name]
                    
                    # 成長率を計算
                    comp_growth_rates = DataService.calculate_growth_rate(comp_data)
                    
                    if comp_growth_rates:
                        # 競合企業の成長率データを日付でソート
                        comp_growth_dates = sorted(comp_growth_rates.keys())
                        comp_growth_values = [comp_growth_rates[date] for date in comp_growth_dates]
                        
                        # 成長率の日付を年月表示に変換
                        comp_growth_display_dates = []
                        for date in comp_growth_dates:
                            try:
                                dt = datetime.strptime(date, '%Y-%m-%d')
                                comp_growth_display_dates.append(dt.strftime('%Y/%m'))
                            except ValueError:
                                comp_growth_display_dates.append(date)
                        
                        # 競合企業の成長率ラインチャートを追加
                        data.append({
                            'type': 'scatter',
                            'x': comp_growth_display_dates,
                            'y': [rate * 100 for rate in comp_growth_values],  # パーセント表示
                            'name': f'{competitor["name"]} 成長率',
                            'yaxis': 'y2',
                            'line': {'color': self.competitor_line_colors[i % len(self.competitor_line_colors)], 'width': 2},
                            'hovertemplate': '%{x}: %{y:.2f}%<extra></extra>'
                        })
            
            # レイアウト設定
            layout = {
                'title': f'{chart_title}と{chart_title}成長率',
                'xaxis': {'title': {'text': '年月'}},
                'yaxis': {
                    'title': {'text': f'{chart_title}（{unit_text}）'},
                    'side': 'left'
                },
                'yaxis2': {
                    'title': {'text': '成長率（%）'},
                    'side': 'right',
                    'overlaying': 'y',
                    'showgrid': 'false'
                },
                'barmode': 'group',
                'legend': {
                    'orientation': 'h',
                    'yanchor': 'bottom',
                    'y': 1.02,
                    'xanchor': 'right',
                    'x': 1
                },
                'margin': {'l': 50, 'r': 50, 't': 80, 'b': 50},
                'height': 500
            }
            
            return {
                'title': chart_title,
                'data': data,
                'layout': layout
            }
        except Exception as e:
            logger.error(f"指標と成長率の複合グラフ生成中にエラー: {e}", exc_info=True)
            return None

    def _generate_metric_chart(
        self,
        metric_name: str,
        metric_data: Dict[str, float],
        competitors_data: Dict[str, Dict[str, Dict[str, float]]],
        competitors: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """指標のチャートを生成"""
        try:
            if not metric_data:
                return None
            
            # 日付でソート
            dates = sorted(metric_data.keys())
            values = [metric_data[date] for date in dates]
            
            # 日付を年月表示に変換
            display_dates = []
            for date in dates:
                try:
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    display_dates.append(dt.strftime('%Y/%m'))
                except ValueError:
                    display_dates.append(date)
            
            # 単位を決定
            max_value = max(values) if values else 0
            unit_text, divisor = determine_unit_from_max_value(max_value)
            
            # 単位で割った値
            scaled_values = [value / divisor for value in values]
            
            # プロットデータを作成
            data = []
            
            # メイン企業のバーチャート
            data.append({
                'type': 'bar',
                'x': display_dates,
                'y': scaled_values,
                'name': self.company_name,
                'marker': {'color': CHART_COLORS['main']['bar']},
                'hovertemplate': '%{x}: %{y:.2f}<extra></extra>'
            })
            
            # 競合企業のバーチャート
            for i, competitor in enumerate(competitors):
                comp_code = competitor['code']
                if comp_code in competitors_data and metric_name in competitors_data[comp_code]:
                    comp_data = competitors_data[comp_code][metric_name]
                    
                    # 競合企業のデータを日付でソート
                    comp_dates = sorted(comp_data.keys())
                    comp_values = [comp_data[date] if date in comp_data else None for date in dates]
                    
                    # 単位で割った値
                    scaled_comp_values = [value / divisor if value is not None else None for value in comp_values]
                    
                    # 競合企業のバーチャートを追加
                    data.append({
                        'type': 'bar',
                        'x': display_dates,
                        'y': scaled_comp_values,
                        'name': competitor['name'],
                        'marker': {'color': self.competitor_bar_colors[i % len(self.competitor_bar_colors)]},
                        'hovertemplate': '%{x}: %{y:.2f}<extra></extra>'
                    })
            
            # 特殊な単位表示の処理
            unit_display = unit_text
            if metric_name == '営業利益率' or metric_name == 'ROE（自己資本利益率）':
                # パーセント表示の場合は値を100倍
                for trace in data:
                    trace['y'] = [value * 100 if value is not None else None for value in trace['y']]
                unit_display = '%'
            
            # レイアウト設定
            layout = {
                'title': metric_name,
                'xaxis': {'title': {'text': '年月'}},
                'yaxis': {'title': {'text': f'{metric_name}（{unit_display}）'}},
                'barmode': 'group',
                'legend': {
                    'orientation': 'h',
                    'yanchor': 'bottom',
                    'y': 1.02,
                    'xanchor': 'right',
                    'x': 1
                },
                'margin': {'l': 50, 'r': 50, 't': 80, 'b': 50},
                'height': 500
            }
            
            return {
                'title': metric_name,
                'data': data,
                'layout': layout
            }
        except Exception as e:
            logger.error(f"指標チャート生成中にエラー: {e}", exc_info=True)
            return None 