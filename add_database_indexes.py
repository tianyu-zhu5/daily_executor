#!/usr/bin/env python3
"""
Add database indexes for performance optimization

This script adds indexes to the CCI signals database to improve query performance.
The indexes are designed for common query patterns in historical signal queries.

Author: Daily Executor System
Date: 2025-11-11
"""

import sqlite3
import sys
from pathlib import Path


def add_indexes(db_path: str):
    """
    Add indexes to CCI signals database.

    Indexes created:
    - idx_divergence_events_end_date: For date range queries
    - idx_divergence_events_expiry_date: For validity checks
    - idx_divergence_events_stock_code: For stock filtering
    - idx_divergence_events_confidence: For confidence filtering

    Args:
        db_path: Path to database file
    """
    db_file = Path(db_path)

    if not db_file.exists():
        print(f"错误: 数据库文件不存在: {db_path}")
        return False

    print(f"正在为数据库添加索引: {db_path}")
    print("=" * 80)

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    # Check existing indexes
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND tbl_name='divergence_events'
    """)
    existing_indexes = {row[0] for row in cursor.fetchall()}

    indexes_to_create = {
        'idx_divergence_events_end_date': 'CREATE INDEX IF NOT EXISTS idx_divergence_events_end_date ON divergence_events(end_date)',
        'idx_divergence_events_expiry_date': 'CREATE INDEX IF NOT EXISTS idx_divergence_events_expiry_date ON divergence_events(expiry_date)',
        'idx_divergence_events_stock_code': 'CREATE INDEX IF NOT EXISTS idx_divergence_events_stock_code ON divergence_events(stock_code)',
        'idx_divergence_events_confidence': 'CREATE INDEX IF NOT EXISTS idx_divergence_events_confidence ON divergence_events(confidence)'
    }

    created_count = 0
    skipped_count = 0

    for index_name, create_sql in indexes_to_create.items():
        if index_name in existing_indexes:
            print(f"✓ 索引已存在: {index_name}")
            skipped_count += 1
        else:
            try:
                cursor.execute(create_sql)
                print(f"✅ 创建索引: {index_name}")
                created_count += 1
            except Exception as e:
                print(f"❌ 创建索引失败 ({index_name}): {e}")
                return False

    conn.commit()
    conn.close()

    print("=" * 80)
    print(f"索引操作完成:")
    print(f"  新建索引: {created_count}")
    print(f"  已存在索引: {skipped_count}")
    print(f"  总索引数: {created_count + skipped_count}")

    # Show index info
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, sql FROM sqlite_master
        WHERE type='index' AND tbl_name='divergence_events'
        ORDER BY name
    """)

    print("\n当前数据库索引:")
    print("-" * 80)
    for name, sql in cursor.fetchall():
        if sql:  # Skip auto-created indexes
            print(f"  {name}")

    conn.close()

    return True


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python add_database_indexes.py <database_path>")
        print("\n示例:")
        print("  python add_database_indexes.py ../CCI_Divergence/data/cci_signals.db")
        print("  python add_database_indexes.py ./data/cci_signals.db")
        sys.exit(1)

    db_path = sys.argv[1]

    try:
        success = add_indexes(db_path)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
