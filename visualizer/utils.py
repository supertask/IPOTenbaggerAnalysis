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
    metric_data: Dict[str, float],
    competitors_data: Dict[str, Dict[str, Dict[str, float]]],
    metric_name: str,
    formatter: Callable[[float], Tuple[float, str]]
) -> Tuple[str, str]:
    """
    データの最大値から適切な単位を決定する
    
    Args:
        metric_data: メイン企業のデータ
        competitors_data: 競合企業のデータ
        metric_name: 指標名
        formatter: 単位変換関数
    
    Returns:
        Tuple[str, str]: (単位を含むY軸ラベルの接尾辞, 強制単位)
    """
    max_value = max(
        max(metric_data.values() if metric_data else [0]),
        *[max(comp_metrics[metric_name].values()) if metric_name in comp_metrics and comp_metrics[metric_name] else [0]
          for comp_metrics in competitors_data.values()]
    )
    _, unit = formatter(max_value)
    return f" ({unit})", unit 