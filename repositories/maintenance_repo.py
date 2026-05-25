"""
メンテナンスリポジトリ

データベースの保守・点検・バックアップ操作を集約。
"""

from repositories.base import get_db_connection, JST

__all__ = [
    'check_history_change_types',
    'backup_inventory_history_to_csv',
    'cleanup_history_change_types',
]


def check_history_change_types() -> dict:
    """
    inventory_historyのchange_type分布を確認

    Returns:
        dict: {change_type: count}
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT change_type, COUNT(*) as count
            FROM inventory_history
            GROUP BY change_type
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        return {row['change_type']: row['count'] for row in rows}


def backup_inventory_history_to_csv(filepath: str = None) -> str:
    """
    inventory_historyをCSVにバックアップ

    Args:
        filepath: バックアップファイルパス（Noneの場合は自動生成）

    Returns:
        str: 保存したファイルパス
    """
    import csv
    from datetime import datetime

    if filepath is None:
        timestamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
        filepath = f"inventory_history_backup_{timestamp}.csv"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory_history ORDER BY created_at DESC")
        rows = cursor.fetchall()

        if not rows:
            raise ValueError("バックアップするデータがありません")

        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

        print(f"Backup saved to {filepath} ({len(rows)} records)")
        return filepath


def cleanup_history_change_types(dry_run: bool = True) -> dict:
    """
    inventory_historyのchange_typeを整理
    - ORDER: 削除
    - INBOUND: INに変換

    Args:
        dry_run: Trueなら実際の変更は行わず、変更内容のみ返す

    Returns:
        dict: {converted, deleted, total_affected}
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM inventory_history WHERE change_type = 'ORDER'")
        order_count = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM inventory_history WHERE change_type = 'INBOUND'")
        inbound_count = cursor.fetchone()['count']

        if not dry_run:
            if order_count > 0:
                cursor.execute("DELETE FROM inventory_history WHERE change_type = 'ORDER'")
            if inbound_count > 0:
                cursor.execute("UPDATE inventory_history SET change_type = 'IN' WHERE change_type = 'INBOUND'")
            conn.commit()

        return {
            'converted': inbound_count,
            'deleted': order_count,
            'total_affected': inbound_count + order_count
        }
