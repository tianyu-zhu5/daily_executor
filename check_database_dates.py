#!/usr/bin/env python3
"""
数据库日期范围检查工具
检查 CCI 信号数据库中有哪些日期的数据

Usage:
    python check_database_dates.py
"""

import sqlite3
from pathlib import Path
import json

# 读取配置
config_file = Path(__file__).parent / "config.json"
with open(config_file, 'r', encoding='utf-8') as f:
    config = json.load(f)

db_path = Path(__file__).parent / config['signal_generation']['db_path']

print("=" * 80)
print("CCI 信号数据库日期检查")
print("=" * 80)
print(f"数据库路径: {db_path}")
print(f"数据库存在: {db_path.exists()}")
print()

if not db_path.exists():
    print("❌ 数据库文件不存在！")
    exit(1)

# 连接数据库
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# 1. 检查总信号数
cursor.execute('SELECT COUNT(*) FROM divergence_events')
total = cursor.fetchone()[0]
print(f"1. 📊 数据库总信号数: {total:,}")

# 2. 检查日期范围
cursor.execute('SELECT MIN(end_date), MAX(end_date) FROM divergence_events')
min_date, max_date = cursor.fetchone()
print(f"2. 📅 数据库日期范围: {min_date} 至 {max_date}")
print()

# 3. 检查 2025-11 月份的信号分布
print("3. 📈 2025年11月信号分布:")
cursor.execute('''
    SELECT end_date, COUNT(*) as cnt
    FROM divergence_events
    WHERE end_date BETWEEN '2025-11-01' AND '2025-11-30'
    GROUP BY end_date
    ORDER BY end_date
''')
nov_dates = cursor.fetchall()
if nov_dates:
    for date, cnt in nov_dates:
        marker = ' ← 你查询的日期' if date == '2025-11-06' else ''
        print(f"   {date}: {cnt:3d} 个信号{marker}")
else:
    print("   ❌ 2025年11月没有任何信号")
print()

# 4. 检查最近的10个有信号的日期
print("4. 🕐 最近10个有信号的交易日:")
cursor.execute('''
    SELECT end_date, COUNT(*) as cnt
    FROM divergence_events
    GROUP BY end_date
    ORDER BY end_date DESC
    LIMIT 10
''')
recent = cursor.fetchall()
for date, cnt in recent:
    print(f"   {date}: {cnt:3d} 个信号")
print()

# 5. 检查信号的置信度分布（2025-11月）
print("5. 🎯 2025年11月信号的置信度分布:")
cursor.execute('''
    SELECT
        CASE
            WHEN confidence >= 0.7 THEN '高 (≥0.7)'
            WHEN confidence >= 0.4 THEN '中 (0.4-0.7)'
            ELSE '低 (<0.4)'
        END as conf_level,
        COUNT(*) as cnt
    FROM divergence_events
    WHERE end_date BETWEEN '2025-11-01' AND '2025-11-30'
    GROUP BY conf_level
    ORDER BY conf_level DESC
''')
conf_dist = cursor.fetchall()
if conf_dist:
    for level, cnt in conf_dist:
        print(f"   {level}: {cnt:3d} 个信号")
else:
    print("   ❌ 该月份没有信号")
print()

# 6. 建议
print("=" * 80)
print("💡 建议:")
print("=" * 80)

if '2025-11-06' in [d[0] for d in nov_dates]:
    print("✓ 2025-11-06 有信号数据")
    # 检查是否因为置信度过滤
    cursor.execute('''
        SELECT COUNT(*), MIN(confidence), MAX(confidence), AVG(confidence)
        FROM divergence_events
        WHERE end_date = '2025-11-06'
    ''')
    cnt, min_conf, max_conf, avg_conf = cursor.fetchone()
    print(f"  - 该日期有 {cnt} 个信号")
    print(f"  - 置信度范围: {min_conf:.3f} ~ {max_conf:.3f} (平均: {avg_conf:.3f})")
    print(f"  - 当前配置的 min_confidence: {config['signal_generation']['min_confidence']}")
    if min_conf < config['signal_generation']['min_confidence']:
        print(f"  ⚠️  所有信号的置信度都低于配置的最小阈值！")
        print(f"  建议: python daily_executor.py query --date 2025-11-06 --min-confidence 0.0")
else:
    print("❌ 2025-11-06 没有信号数据，可能的原因:")
    print("  1. 该日期不是交易日（周末/节假日）")
    print("  2. 该日期的数据还未计算 CCI 底背离")
    print("  3. 该日期确实没有产生符合条件的底背离信号")
    print()
    if recent:
        print(f"建议尝试查询最近有数据的日期，例如:")
        print(f"  python daily_executor.py query --date {recent[0][0]}")
    print()
    print("或者查询日期范围:")
    print(f"  python daily_executor.py query --start {min_date} --end {max_date}")

conn.close()
print("=" * 80)
