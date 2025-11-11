#!/usr/bin/env python3
"""
微信推送模块 - 通过Server酱推送买入信号到微信

功能：
1. 读取配置文件获取多个接收人的SendKey
2. 读取买入信号CSV文件
3. 格式化推送消息（Markdown格式）
4. 支持股票名称显示（如果有本地缓存）
5. 循环推送给所有配置的接收人

Author: Daily Executor System
Date: 2025-11-10
"""

import json
import requests
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WechatPusher:
    """Server酱微信推送器"""

    SERVER_SAUCE_API = "https://sctapi.ftqq.com/{sendkey}.send"

    def __init__(self, config_file: str = "config.json"):
        """
        初始化推送器

        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.config = self._load_config()
        self.stock_name_map = self._load_stock_names()

    def _load_config(self) -> dict:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"配置文件加载成功: {self.config_file}")
            return config
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}")
            raise

    def _load_stock_names(self) -> Dict[str, str]:
        """
        加载股票名称缓存

        Returns:
            股票代码 -> 股票名称的映射字典
        """
        stock_name_map = {}

        if not self.config['push_settings']['include_stock_name']:
            return stock_name_map

        cache_file = Path(self.config['push_settings']['stock_name_cache'])

        if not cache_file.exists():
            logger.warning(f"股票名称缓存文件不存在: {cache_file}")
            return stock_name_map

        try:
            # 尝试读取stock_list.txt（miniQMT格式）
            with open(cache_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # 尝试解析不同格式
                    # 格式1: 代码,名称 (例如: 000001_SZ,平安银行)
                    if ',' in line:
                        parts = line.split(',')
                        if len(parts) >= 2:
                            code = parts[0].strip()
                            name = parts[1].strip()
                            stock_name_map[code] = name
                    # 格式2: 代码 名称 (空格分隔)
                    elif ' ' in line or '\t' in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            code = parts[0].strip()
                            name = parts[1].strip()
                            stock_name_map[code] = name

            logger.info(f"成功加载 {len(stock_name_map)} 个股票名称")

        except Exception as e:
            logger.warning(f"加载股票名称缓存失败: {e}")

        return stock_name_map

    def _get_stock_display_name(self, stock_code: str) -> str:
        """
        获取股票显示名称

        Args:
            stock_code: 股票代码（例如：000001_SZ）

        Returns:
            显示名称（例如：000001_SZ 平安银行 或 000001_SZ）
        """
        if stock_code in self.stock_name_map:
            return f"{stock_code} {self.stock_name_map[stock_code]}"
        return stock_code

    def _format_message(self, signals_df: pd.DataFrame, date_str: str) -> tuple:
        """
        格式化推送消息

        Args:
            signals_df: 买入信号DataFrame
            date_str: 日期字符串

        Returns:
            (title, content) 元组
        """
        signal_count = len(signals_df)

        # 标题
        title = f"📈 {date_str} CCI底背离买入信号 ({signal_count}个)"

        # 内容（Markdown格式）
        content_lines = []
        content_lines.append(f"## 交易日期: {date_str}")
        content_lines.append(f"## 信号数量: {signal_count}")
        content_lines.append("")
        content_lines.append("---")
        content_lines.append("")

        # 遍历每个信号
        for idx, signal in signals_df.iterrows():
            stock_code = signal['stock_code']
            stock_display = self._get_stock_display_name(stock_code)

            content_lines.append(f"### {idx + 1}. {stock_display}")
            content_lines.append("")

            # 基本信息
            content_lines.append(f"- **信号类型**: {signal.get('reason', 'CCI底背离')}")
            content_lines.append(f"- **置信度**: {signal['confidence']:.2%}")
            content_lines.append(f"- **建议价格**: ¥{signal['entry_price']:.2f}")

            # 技术指标信息（从reason字段解析）
            if 'reason' in signal and pd.notna(signal['reason']):
                reason = signal['reason']
                content_lines.append(f"- **技术详情**: {reason}")

            # 背离ID（用于追溯）
            if 'divergence_id' in signal and pd.notna(signal['divergence_id']):
                content_lines.append(f"- **背离ID**: `{signal['divergence_id']}`")

            content_lines.append("")
            content_lines.append("---")
            content_lines.append("")

        # 底部说明
        content_lines.append("*本消息由自动化系统生成*")
        content_lines.append(f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        content = "\n".join(content_lines)

        return title, content

    def _send_to_recipient(self, sendkey: str, title: str, content: str, recipient_name: str) -> bool:
        """
        发送消息给单个接收人

        Args:
            sendkey: Server酱SendKey
            title: 消息标题
            content: 消息内容
            recipient_name: 接收人姓名

        Returns:
            是否发送成功
        """
        try:
            url = self.SERVER_SAUCE_API.format(sendkey=sendkey)

            data = {
                'title': title,
                'desp': content
            }

            logger.info(f"正在推送给 {recipient_name}...")

            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()

            result = response.json()

            if result.get('code') == 0:
                logger.info(f"推送成功: {recipient_name}")
                return True
            else:
                logger.error(f"推送失败: {recipient_name} - {result.get('message', '未知错误')}")
                return False

        except requests.exceptions.Timeout:
            logger.error(f"推送超时: {recipient_name}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"推送网络错误: {recipient_name} - {e}")
            return False
        except Exception as e:
            logger.error(f"推送异常: {recipient_name} - {e}")
            return False

    def push_signals(self, signals_file: str) -> bool:
        """
        推送买入信号

        Args:
            signals_file: 信号CSV文件路径

        Returns:
            是否全部推送成功
        """
        logger.info("=" * 80)
        logger.info("开始推送买入信号")
        logger.info("=" * 80)

        # 1. 检查信号文件
        signals_path = Path(signals_file)
        if not signals_path.exists():
            logger.error(f"信号文件不存在: {signals_path}")
            return False

        # 2. 读取信号
        try:
            signals_df = pd.read_csv(signals_path, encoding='utf-8-sig')
            logger.info(f"成功读取信号文件: {len(signals_df)} 个信号")
        except Exception as e:
            logger.error(f"读取信号文件失败: {e}")
            return False

        # 3. 检查是否有信号
        if len(signals_df) == 0:
            if self.config['push_settings']['push_on_no_signals']:
                logger.info("今日无买入信号，将推送空信号通知")
                title = f"📊 {datetime.now().strftime('%Y-%m-%d')} 无买入信号"
                content = "今日CCI底背离系统未检测到买入信号。\n\n*本消息由自动化系统生成*"
            else:
                logger.info("今日无买入信号，跳过推送")
                return True
        else:
            # 4. 格式化消息
            date_str = datetime.now().strftime('%Y-%m-%d')
            if 'signal_date' in signals_df.columns and len(signals_df) > 0:
                date_str = signals_df['signal_date'].iloc[0]

            title, content = self._format_message(signals_df, date_str)

        # 5. 推送给所有接收人
        recipients = self.config['server_sauce']['recipients']
        enabled_recipients = [r for r in recipients if r.get('enabled', True)]

        if not enabled_recipients:
            logger.warning("没有启用的接收人，跳过推送")
            return True

        logger.info(f"将推送给 {len(enabled_recipients)} 个接收人")

        success_count = 0
        fail_count = 0

        for recipient in enabled_recipients:
            name = recipient['name']
            sendkey = recipient['sendkey']

            if not sendkey or 'xxx' in sendkey.lower():
                logger.warning(f"跳过 {name}: SendKey未配置或为示例值")
                continue

            if self._send_to_recipient(sendkey, title, content, name):
                success_count += 1
            else:
                fail_count += 1

        # 6. 汇总结果
        logger.info("")
        logger.info("=" * 80)
        logger.info("推送结果统计")
        logger.info("=" * 80)
        logger.info(f"成功: {success_count}")
        logger.info(f"失败: {fail_count}")
        logger.info("=" * 80)

        return fail_count == 0


def main():
    """测试函数"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python wechat_pusher.py <信号文件路径>")
        print("示例: python wechat_pusher.py signals/daily_signals.csv")
        sys.exit(1)

    signals_file = sys.argv[1]

    pusher = WechatPusher()
    success = pusher.push_signals(signals_file)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
