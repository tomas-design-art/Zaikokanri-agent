"""
統計・KPIリポジトリ

月次出庫数・在庫回転率・出庫トレンドなど
統計・分析関連のクエリを集約。
"""

from db import (
    get_monthly_outbound_total,
    get_stock_alert_count,
    get_expired_count,
    get_outbound_trend_data,
    get_item_kpi,
    get_top_outbound_items,
)

__all__ = [
    'get_monthly_outbound_total',
    'get_stock_alert_count',
    'get_expired_count',
    'get_outbound_trend_data',
    'get_item_kpi',
    'get_top_outbound_items',
]
