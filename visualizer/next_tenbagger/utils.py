from typing import Tuple, Dict, List, Callable

def format_currency_unit(value: float, force_unit: str = None) -> Tuple[float, str]:
    """
    金額を適切な単位に変換する
    
    Args:
        value (float): 変換する金額（円）
        force_unit (str): 強制的に使用する単位（'兆円', '億円', '万円', '円'のいずれか）
    
    Returns:
        Tuple[float, str]: 変換後の値と単位の組み合わせ
    """
    if force_unit:
        if force_unit == '兆円':
            return value / 1e12, '兆円'
        elif force_unit == '億円':
            return value / 1e8, '億円'
        elif force_unit == '万円':
            return value / 1e4, '万円'
        else:
            return value, '円'

    if abs(value) >= 1e12:  # 1兆円以上
        return value / 1e12, '兆円'
    elif abs(value) >= 1e8:  # 1億円以上
        return value / 1e8, '億円'
    elif abs(value) >= 1e4:  # 1万円以上
        return value / 1e4, '万円'
    else:
        return value, '円'

def format_percentage(value: float) -> Tuple[float, str]:
    """
    比率を百分率に変換する
    
    Args:
        value (float): 変換する値（0.0 ~ 1.0）
    
    Returns:
        Tuple[float, str]: 変換後の値と単位の組み合わせ
    """
    return value * 100, '%'

def format_percentage_raw(value: float) -> Tuple[float, str]:
    """
    すでにパーセント表示の値に単位を付ける
    
    Args:
        value (float): 変換する値（すでにパーセント表示）
    
    Returns:
        Tuple[float, str]: 値と単位の組み合わせ
    """
    return value, '%'

def format_per_person_unit(value: float) -> Tuple[float, str]:
    """
    一人当たりの金額を適切な単位に変換する
    
    Args:
        value (float): 変換する金額（円/人）
    
    Returns:
        Tuple[float, str]: 変換後の値と単位の組み合わせ
    """
    converted_value, unit = format_currency_unit(value)
    return converted_value, f'{unit}/人'

def format_value_with_unit(value: float, formatter: Callable[[float], Tuple[float, str]]) -> str:
    """
    数値を単位付きでフォーマットする
    
    Args:
        value: フォーマットする値
        formatter: 単位変換関数
    
    Returns:
        str: フォーマットされた文字列（例: "1.2 億円"）
    """
    if value is None:
        return "N/A"
    converted_value, unit = formatter(value)
    return f"{converted_value:.1f}{unit}"

def determine_unit_from_max_value(
    max_value_or_data,
    competitors_data=None,
    metric_name=None,
    formatter=None
) -> Tuple[str, float]:
    """
    データの最大値から適切な単位を決定する
    
    Args:
        max_value_or_data: 最大値または指標データ辞書
        competitors_data: 競合企業のデータ（オプション）
        metric_name: 指標名（オプション）
        formatter: 単位変換関数（オプション）
    
    Returns:
        Tuple[str, float]: (単位, 除数)
    """
    # 単一の値が渡された場合
    if isinstance(max_value_or_data, (int, float)):
        max_value = max_value_or_data
        
        # 単位を決定
        if max_value >= 1e12:  # 1兆以上
            return '兆', 1e12
        elif max_value >= 1e9:  # 10億以上
            return '十億', 1e9
        elif max_value >= 1e8:  # 1億以上
            return '億', 1e8
        elif max_value >= 1e6:  # 100万以上
            return '百万', 1e6
        elif max_value >= 1e4:  # 1万以上
            return '万', 1e4
        else:
            return '', 1
    
    # 辞書が渡された場合（従来の動作）
    else:
        metric_data = max_value_or_data
        max_value = max(
            max(metric_data.values() if metric_data else [0]),
            *[max(comp_metrics[metric_name].values()) if metric_name in comp_metrics and comp_metrics[metric_name] else [0]
              for comp_metrics in competitors_data.values()]
        )
        
        if formatter:
            _, unit = formatter(max_value)
            return unit, 1  # 既にformatterで変換されているので除数は1
        else:
            # 単位を決定
            if max_value >= 1e12:  # 1兆以上
                return '兆', 1e12
            elif max_value >= 1e9:  # 10億以上
                return '十億', 1e9
            elif max_value >= 1e8:  # 1億以上
                return '億', 1e8
            elif max_value >= 1e6:  # 100万以上
                return '百万', 1e6
            elif max_value >= 1e4:  # 1万以上
                return '万', 1e4
            else:
                return '', 1 