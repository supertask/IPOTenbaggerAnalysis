from typing import Dict, List, Tuple, Any, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging
from datetime import datetime
import json

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

# Noneをnullに変換するカスタムJSONエンコーダー
class NoneToNullEncoder(json.JSONEncoder):
    def default(self, obj):
        if obj is None:
            return None  # JSONではnullに変換される
        return super().default(obj)

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
            logger.info(f"競合企業: {competitors}")
            
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
                    logger.info(f"競合企業 {comp_code} のデータを取得中...")
                    comp_data, error = self.data_service.get_company_data(comp_code)
                    if comp_data is not None:
                        logger.info(f"競合企業 {comp_code} のデータ取得成功")
                        competitors_data[comp_code] = self.data_service.extract_metrics(comp_data)
                        logger.info(f"競合企業 {comp_code} の指標: {list(competitors_data[comp_code].keys())}")
                    else:
                        logger.warning(f"競合企業 {comp_code} のデータ取得失敗: {error}")
            
            charts = []
            
            # 売上高と売上高成長率の複合グラフを生成
            sales_chart = self._generate_metric_growth_chart('売上高', '売上高', main_metrics, competitors_data, competitors)
            if sales_chart:
                charts.append(sales_chart)
            
            # 営業利益と営業利益成長率の複合グラフを生成
            operating_profit_chart = self._generate_metric_growth_chart('営業利益', '営業利益', main_metrics, competitors_data, competitors)
            if operating_profit_chart:
                charts.append(operating_profit_chart)
            
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
            
            # 日付を年月日表示に変換
            display_dates = []
            original_dates = {}  # 表示用日付から元の日付へのマッピング
            for date in dates:
                try:
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    display_date = dt.strftime('%Y/%m/%d')
                    display_dates.append(display_date)
                    original_dates[display_date] = date
                except ValueError:
                    display_dates.append(date)
                    original_dates[date] = date
            
            # 成長率を計算
            growth_rates = DataService.calculate_growth_rate(metric_data)
            growth_dates = sorted(growth_rates.keys())
            growth_values = [growth_rates[date] for date in growth_dates]
            
            # 成長率の日付を年月日表示に変換
            growth_display_dates = []
            for date in growth_dates:
                try:
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    display_date = dt.strftime('%Y/%m/%d')
                    growth_display_dates.append(display_date)
                    original_dates[display_date] = date
                except ValueError:
                    growth_display_dates.append(date)
                    original_dates[date] = date
            
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
            
            # すべての日付を収集（メイン企業と競合企業の両方）
            all_display_dates = display_dates.copy()
            
            # 競合企業のバーチャート
            for i, competitor in enumerate(competitors):
                comp_code = competitor['code']
                if comp_code in competitors_data and metric_name in competitors_data[comp_code]:
                    comp_data = competitors_data[comp_code][metric_name]
                    
                    if not comp_data:
                        logger.warning(f"競合企業 {comp_code} の {metric_name} データが空です")
                        continue
                    
                    # 競合企業のデータを日付でソート
                    comp_dates = sorted(comp_data.keys())
                    comp_values = [comp_data[date] for date in comp_dates]
                    
                    # 競合企業の日付を年月日表示に変換
                    comp_display_dates = []
                    for date in comp_dates:
                        try:
                            dt = datetime.strptime(date, '%Y-%m-%d')
                            display_date = dt.strftime('%Y/%m/%d')
                            comp_display_dates.append(display_date)
                            original_dates[display_date] = date
                            if display_date not in all_display_dates:
                                all_display_dates.append(display_date)
                        except ValueError:
                            comp_display_dates.append(date)
                            original_dates[date] = date
                            if date not in all_display_dates:
                                all_display_dates.append(date)
                    
                    # 単位で割った値
                    scaled_comp_values = [value / divisor for value in comp_values]
                    
                    # 競合企業のバーチャートを追加
                    data.append({
                        'type': 'bar',
                        'x': comp_display_dates,
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
                    
                    if not comp_data:
                        continue
                    
                    # 成長率を計算
                    comp_growth_rates = DataService.calculate_growth_rate(comp_data)
                    
                    if comp_growth_rates:
                        # 競合企業の成長率データを日付でソート
                        comp_growth_dates = sorted(comp_growth_rates.keys())
                        comp_growth_values = [comp_growth_rates[date] for date in comp_growth_dates]
                        
                        # 成長率の日付を年月日表示に変換
                        comp_growth_display_dates = []
                        for date in comp_growth_dates:
                            try:
                                dt = datetime.strptime(date, '%Y-%m-%d')
                                display_date = dt.strftime('%Y/%m/%d')
                                comp_growth_display_dates.append(display_date)
                                original_dates[display_date] = date
                                if display_date not in all_display_dates:
                                    all_display_dates.append(display_date)
                            except ValueError:
                                comp_growth_display_dates.append(date)
                                original_dates[date] = date
                                if date not in all_display_dates:
                                    all_display_dates.append(date)
                        
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
            
            # 日付を時系列順にソート
            all_display_dates_sorted = sorted(all_display_dates, key=lambda x: original_dates[x])
            
            # レイアウト設定
            layout = {
                'title': f'{chart_title}と{chart_title}成長率',
                'xaxis': {
                    'title': {'text': '年月日'},
                    'type': 'category',
                    'categoryorder': 'array',
                    'categoryarray': all_display_dates_sorted
                },
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
            
            logger.info(f"チャート生成: {metric_name}")
            
            # 日付でソート
            dates = sorted(metric_data.keys())
            values = [metric_data[date] for date in dates]
            
            logger.info(f"メイン企業の日付: {dates}")
            logger.info(f"メイン企業の値: {values}")
            
            # 日付を年月日表示に変換
            display_dates = []
            original_dates = {}  # 表示用日付から元の日付へのマッピング
            for date in dates:
                try:
                    dt = datetime.strptime(date, '%Y-%m-%d')
                    display_date = dt.strftime('%Y/%m/%d')
                    display_dates.append(display_date)
                    original_dates[display_date] = date
                except ValueError:
                    display_dates.append(date)
                    original_dates[date] = date
            
            # 単位を決定
            max_value = max(values) if values else 0
            unit_text, divisor = determine_unit_from_max_value(max_value)
            
            # 単位で割った値
            scaled_values = [value / divisor for value in values]
            
            # プロットデータを作成
            data = []
            
            # 売上高、営業利益、EPSの場合は棒グラフ、それ以外は折れ線グラフ
            if metric_name in ['売上高', '営業利益', '１株当たり当期純利益（EPS）', '１株当たり四半期純利益（EPS）']:
                # メイン企業のバーチャート
                data.append({
                    'type': 'bar',
                    'x': display_dates,
                    'y': scaled_values,
                    'name': self.company_name,
                    'marker': {'color': CHART_COLORS['main']['bar']},
                    'hovertemplate': '%{x}: %{y:.2f}<extra></extra>'
                })
            else:
                # メイン企業の折れ線グラフ
                data.append({
                    'type': 'scatter',
                    'mode': 'lines+markers',
                    'x': display_dates,
                    'y': scaled_values,
                    'name': self.company_name,
                    'line': {'color': CHART_COLORS['main']['line'], 'width': 3},
                    'marker': {'size': 8, 'color': CHART_COLORS['main']['line']},
                    'hovertemplate': '%{x}: %{y:.2f}<extra></extra>'
                })
            
            # すべての日付を収集（メイン企業と競合企業の両方）
            all_display_dates = display_dates.copy()
            
            # 競合企業のチャート
            for i, competitor in enumerate(competitors):
                comp_code = competitor['code']
                comp_name = competitor['name']
                logger.info(f"競合企業 {comp_code} ({comp_name}) のチャートデータ処理中...")
                
                if comp_code in competitors_data and metric_name in competitors_data[comp_code]:
                    comp_data = competitors_data[comp_code][metric_name]
                    logger.info(f"競合企業 {comp_code} の {metric_name} データ: {comp_data}")
                    
                    if not comp_data:
                        logger.warning(f"競合企業 {comp_code} の {metric_name} データが空です")
                        continue
                    
                    # 競合企業のデータを日付でソート
                    comp_dates = sorted(comp_data.keys())
                    logger.info(f"競合企業 {comp_code} の日付: {comp_dates}")
                    
                    # 競合企業の値を取得
                    comp_values = [comp_data[date] for date in comp_dates]
                    logger.info(f"競合企業 {comp_code} の値: {comp_values}")
                    
                    # 日付を年月日表示に変換
                    comp_display_dates = []
                    for date in comp_dates:
                        try:
                            dt = datetime.strptime(date, '%Y-%m-%d')
                            display_date = dt.strftime('%Y/%m/%d')
                            comp_display_dates.append(display_date)
                            original_dates[display_date] = date
                            if display_date not in all_display_dates:
                                all_display_dates.append(display_date)
                        except ValueError:
                            comp_display_dates.append(date)
                            original_dates[date] = date
                            if date not in all_display_dates:
                                all_display_dates.append(date)
                    
                    # 単位で割った値
                    scaled_comp_values = [value / divisor for value in comp_values]
                    logger.info(f"競合企業 {comp_code} のスケーリング後の値: {scaled_comp_values}")
                    
                    # 売上高、営業利益、EPSの場合は棒グラフ、それ以外は折れ線グラフ
                    if metric_name in ['売上高', '営業利益', '１株当たり当期純利益（EPS）', '１株当たり四半期純利益（EPS）']:
                        # 競合企業のバーチャートを追加
                        data.append({
                            'type': 'bar',
                            'x': comp_display_dates,
                            'y': scaled_comp_values,
                            'name': competitor['name'],
                            'marker': {'color': self.competitor_bar_colors[i % len(self.competitor_bar_colors)]},
                            'hovertemplate': '%{x}: %{y:.2f}<extra></extra>'
                        })
                    else:
                        # 競合企業の折れ線グラフを追加
                        data.append({
                            'type': 'scatter',
                            'mode': 'lines+markers',
                            'x': comp_display_dates,
                            'y': scaled_comp_values,
                            'name': competitor['name'],
                            'line': {'color': self.competitor_line_colors[i % len(self.competitor_line_colors)], 'width': 2},
                            'marker': {'size': 6, 'color': self.competitor_line_colors[i % len(self.competitor_line_colors)]},
                            'hovertemplate': '%{x}: %{y:.2f}<extra></extra>'
                        })
                else:
                    if comp_code not in competitors_data:
                        logger.warning(f"競合企業 {comp_code} のデータがcompetitors_dataに存在しません")
                    elif metric_name not in competitors_data[comp_code]:
                        logger.warning(f"競合企業 {comp_code} の {metric_name} データが存在しません")
            
            # 特殊な単位表示の処理
            unit_display = unit_text
            if metric_name == '営業利益率' or metric_name == 'ROE（自己資本利益率）':
                # パーセント表示の場合は値を100倍
                for trace in data:
                    new_y = []
                    for value in trace['y']:
                        if value == "null":
                            new_y.append("null")
                        else:
                            new_y.append(value * 100)
                    trace['y'] = new_y
                unit_display = '%'
            
            # 日付を時系列順にソート
            all_display_dates_sorted = sorted(all_display_dates, key=lambda x: original_dates[x])
            
            # レイアウト設定
            layout = {
                'title': metric_name,
                'xaxis': {
                    'title': {'text': '年月日'},
                    'type': 'category',
                    'categoryorder': 'array',
                    'categoryarray': all_display_dates_sorted
                },
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