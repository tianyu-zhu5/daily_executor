#!/usr/bin/env python3
"""
Output formatters for signal data

Provides unified formatting for signals across different output types:
- Console: Formatted table output
- CSV: Comma-separated values file
- JSON: Structured JSON format
- WeChat: Markdown format for Server酱推送

Author: Daily Executor System
Date: 2025-11-11
"""

import json
import pandas as pd
from pathlib import Path
from typing import List
from datetime import datetime

from signal_types import Signal


def format_console(signals: List[Signal]) -> str:
    """
    Format signals for console table output.

    Args:
        signals: List of Signal objects

    Returns:
        Formatted string for console display
    """
    if not signals:
        return "未找到符合条件的信号"

    # Create DataFrame for nice formatting
    df = pd.DataFrame([s.to_dict() for s in signals])

    # Reorder columns
    column_order = ['signal_date', 'stock_code', 'confidence', 'entry_price', 'reason', 'divergence_id']
    df = df[column_order]

    # Format confidence as percentage
    df['confidence'] = df['confidence'].apply(lambda x: f"{x*100:.2f}%")

    # Format entry_price
    df['entry_price'] = df['entry_price'].apply(lambda x: f"¥{x:.2f}")

    # Create output
    output = []
    output.append("=" * 120)
    output.append(f"查询结果: 共 {len(signals)} 个信号")
    output.append("=" * 120)
    output.append("")
    output.append(df.to_string(index=False))
    output.append("")
    output.append("=" * 120)
    output.append(f"统计信息:")
    output.append(f"  信号数量: {len(signals)}")
    output.append(f"  唯一股票: {df['stock_code'].nunique()}")
    output.append(f"  日期范围: {df['signal_date'].min()} ~ {df['signal_date'].max()}")

    # Parse confidence back to float for statistics
    confidence_values = [s.confidence for s in signals]
    output.append(f"  平均置信度: {sum(confidence_values)/len(confidence_values)*100:.2f}%")
    output.append(f"  置信度范围: {min(confidence_values)*100:.2f}% ~ {max(confidence_values)*100:.2f}%")
    output.append("=" * 120)

    return "\n".join(output)


def to_csv(signals: List[Signal], output_file: str) -> bool:
    """
    Export signals to CSV file.

    Args:
        signals: List of Signal objects
        output_file: Output file path

    Returns:
        True if successful, False otherwise
    """
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to DataFrame
        df = pd.DataFrame([s.to_dict() for s in signals])

        # Save to CSV
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        print(f"✅ CSV已保存: {output_path.absolute()}")
        print(f"   信号数量: {len(signals)}")

        return True

    except Exception as e:
        print(f"❌ CSV保存失败: {e}")
        return False


def to_json(signals: List[Signal], output_file: str = None) -> str:
    """
    Format signals as JSON.

    Args:
        signals: List of Signal objects
        output_file: Optional output file path

    Returns:
        JSON string
    """
    # Create structured output
    data = {
        'query_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_signals': len(signals),
        'signals': [s.to_dict() for s in signals]
    }

    # Add statistics
    if signals:
        confidence_values = [s.confidence for s in signals]
        dates = [s.signal_date for s in signals]
        stocks = list(set([s.stock_code for s in signals]))

        data['statistics'] = {
            'unique_stocks': len(stocks),
            'date_range': {
                'start': min(dates),
                'end': max(dates)
            },
            'confidence': {
                'average': sum(confidence_values) / len(confidence_values),
                'min': min(confidence_values),
                'max': max(confidence_values)
            }
        }

    # Convert to JSON
    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    # Save to file if specified
    if output_file:
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)

            print(f"✅ JSON已保存: {output_path.absolute()}")
            print(f"   信号数量: {len(signals)}")

        except Exception as e:
            print(f"❌ JSON保存失败: {e}")
            return json_str

    return json_str


def to_wechat_markdown(signals: List[Signal], query_date: str = None) -> str:
    """
    Format signals for WeChat push (Server酱 markdown format).

    Args:
        signals: List of Signal objects
        query_date: Query date for title (optional)

    Returns:
        Markdown formatted string for WeChat
    """
    if not signals:
        if query_date:
            return f"## 📊 {query_date} 查询结果\n\n未找到符合条件的信号"
        else:
            return "## 📊 查询结果\n\n未找到符合条件的信号"

    # Create title
    if query_date:
        title = f"📊 {query_date} CCI底背离信号 ({len(signals)}个)"
    else:
        dates = list(set([s.signal_date for s in signals]))
        if len(dates) == 1:
            title = f"📊 {dates[0]} CCI底背离信号 ({len(signals)}个)"
        else:
            title = f"📊 {min(dates)}~{max(dates)} CCI底背离信号 ({len(signals)}个)"

    lines = []
    lines.append(f"## {title}")
    lines.append("")
    lines.append(f"**信号数量**: {len(signals)}")
    lines.append(f"**唯一股票**: {len(set([s.stock_code for s in signals]))}")
    lines.append("")

    # Group signals by date
    from collections import defaultdict
    signals_by_date = defaultdict(list)
    for signal in signals:
        signals_by_date[signal.signal_date].append(signal)

    # Output signals grouped by date
    for date in sorted(signals_by_date.keys()):
        date_signals = signals_by_date[date]
        lines.append(f"### 📅 {date} ({len(date_signals)}个)")
        lines.append("")

        for idx, signal in enumerate(date_signals, 1):
            lines.append(f"**{idx}. {signal.stock_code}**")
            lines.append(f"- 置信度: {signal.confidence*100:.2f}%")
            lines.append(f"- 入场价: ¥{signal.entry_price:.2f}")
            lines.append(f"- 原因: {signal.reason}")
            lines.append(f"- 背离ID: `{signal.divergence_id}`")
            lines.append("")

    lines.append("---")
    lines.append("🤖 Generated by Daily Executor")

    return "\n".join(lines)


def format_summary(signals: List[Signal]) -> str:
    """
    Create a brief summary of signals.

    Args:
        signals: List of Signal objects

    Returns:
        Summary string
    """
    if not signals:
        return "未找到信号"

    dates = [s.signal_date for s in signals]
    stocks = list(set([s.stock_code for s in signals]))
    confidence_values = [s.confidence for s in signals]

    summary_lines = [
        f"信号数量: {len(signals)}",
        f"唯一股票: {len(stocks)}",
        f"日期范围: {min(dates)} ~ {max(dates)}",
        f"平均置信度: {sum(confidence_values)/len(confidence_values)*100:.2f}%"
    ]

    return " | ".join(summary_lines)
