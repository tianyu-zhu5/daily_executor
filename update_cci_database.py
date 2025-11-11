#!/usr/bin/env python3
"""
更新CCI底背离数据库

功能：
1. 读取所有股票的K线数据
2. 检测CCI底背离
3. 保存到数据库

使用方法：
    python update_cci_database.py --start-date 2025-09-17 --end-date 2025-11-11

Author: Daily Executor System
Date: 2025-11-11
"""

import sys
import os

# 修复Windows UTF-8编码问题
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / 'CCI-Divergence'))

import pandas as pd
import argparse
from datetime import datetime
import logging
from tqdm import tqdm

from src.signals.cci_generator import CCIDivergenceGenerator
from src.database.cci_database import CCIDatabase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CCIDatabaseUpdater:
    """CCI数据库更新器"""

    def __init__(
        self,
        data_dir: str = "../data/daily",
        db_path: str = "../CCI-Divergence/data/cci_signals.db",
        stock_pool_file: str = None
    ):
        """
        初始化更新器

        Args:
            data_dir: K线数据目录
            db_path: CCI数据库路径
            stock_pool_file: 股票池文件（可选，None表示处理所有股票）
        """
        self.data_dir = Path(data_dir)
        self.db_path = db_path
        self.stock_pool_file = stock_pool_file

        # 初始化生成器和数据库
        self.generator = CCIDivergenceGenerator(
            cci_period=20,
            pivot_window=10,
            divergence_validity_days=20
        )
        self.db = CCIDatabase(db_path)

        logger.info(f"数据目录: {self.data_dir}")
        logger.info(f"数据库路径: {self.db_path}")

    def load_stock_pool(self) -> list:
        """
        加载股票池

        Returns:
            股票代码列表
        """
        if self.stock_pool_file:
            pool_path = Path(self.stock_pool_file)
            if pool_path.exists():
                with open(pool_path, 'r', encoding='utf-8') as f:
                    stocks = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                logger.info(f"从股票池加载 {len(stocks)} 只股票")
                return stocks
            else:
                logger.warning(f"股票池文件不存在: {pool_path}")

        # 从数据目录获取所有CSV文件
        csv_files = list(self.data_dir.glob("*.csv"))
        stocks = [f.stem for f in csv_files]  # 文件名作为股票代码
        logger.info(f"从数据目录发现 {len(stocks)} 只股票")
        return stocks

    def process_stock(
        self,
        stock_code: str,
        start_date: str = None,
        end_date: str = None
    ) -> int:
        """
        处理单只股票

        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            检测到的背离数量
        """
        try:
            # 读取K线数据
            csv_path = self.data_dir / f"{stock_code}.csv"
            if not csv_path.exists():
                logger.warning(f"{stock_code}: CSV文件不存在")
                return 0

            df = pd.read_csv(csv_path)

            if 'date' not in df.columns:
                logger.warning(f"{stock_code}: 缺少date列")
                return 0

            # 过滤日期范围
            if start_date:
                df = df[df['date'] >= start_date]
            if end_date:
                df = df[df['date'] <= end_date]

            if len(df) < 40:
                logger.debug(f"{stock_code}: 数据不足 ({len(df)}行)")
                return 0

            # 检测底背离
            divergences_df = self.generator.detect_divergences(df, stock_code)

            if len(divergences_df) == 0:
                return 0

            # 保存到数据库
            for _, div in divergences_df.iterrows():
                self.db.add_divergence_event(
                    divergence_id=div['divergence_id'],
                    stock_code=div['stock_code'],
                    start_date=div['start_date'],
                    end_date=div['end_date'],
                    start_price=float(div['start_price']),
                    end_price=float(div['end_price']),
                    start_cci=float(div['start_cci']),
                    end_cci=float(div['end_cci']),
                    confidence=float(div['confidence']),
                    days_between=int(div['days_between']),
                    validity_days=int(div['validity_days'])
                )

            return len(divergences_df)

        except Exception as e:
            logger.error(f"{stock_code}: 处理失败 - {e}")
            return 0

    def update(
        self,
        start_date: str = None,
        end_date: str = None
    ):
        """
        批量更新CCI数据库

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        logger.info("=" * 80)
        logger.info("开始更新CCI底背离数据库")
        logger.info("=" * 80)

        if start_date:
            logger.info(f"开始日期: {start_date}")
        if end_date:
            logger.info(f"结束日期: {end_date}")

        # 加载股票池
        stocks = self.load_stock_pool()

        if not stocks:
            logger.error("没有找到任何股票")
            return

        # 处理所有股票
        total_divergences = 0
        success_count = 0

        logger.info(f"开始处理 {len(stocks)} 只股票...")

        for stock_code in tqdm(stocks, desc="处理股票"):
            div_count = self.process_stock(stock_code, start_date, end_date)
            if div_count > 0:
                total_divergences += div_count
                success_count += 1

        # 统计
        logger.info("=" * 80)
        logger.info("更新完成")
        logger.info("=" * 80)
        logger.info(f"处理股票数: {len(stocks)}")
        logger.info(f"有信号股票: {success_count}")
        logger.info(f"总背离数: {total_divergences}")
        logger.info("=" * 80)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='更新CCI底背离数据库',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 更新最近一个月的数据
  python update_cci_database.py --start-date 2025-10-11 --end-date 2025-11-11

  # 更新所有历史数据（耗时较长）
  python update_cci_database.py

  # 只更新沪深300
  python update_cci_database.py --stock-pool ../CCI-Divergence/stock_pools/hs300.txt
        """
    )

    parser.add_argument(
        '--start-date',
        type=str,
        help='开始日期 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--end-date',
        type=str,
        help='结束日期 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--data-dir',
        type=str,
        default='../data/daily',
        help='K线数据目录 (默认: ../data/daily)'
    )

    parser.add_argument(
        '--db-path',
        type=str,
        default='../CCI-Divergence/data/cci_signals.db',
        help='CCI数据库路径 (默认: ../CCI-Divergence/data/cci_signals.db)'
    )

    parser.add_argument(
        '--stock-pool',
        type=str,
        help='股票池文件路径（可选）'
    )

    args = parser.parse_args()

    try:
        updater = CCIDatabaseUpdater(
            data_dir=args.data_dir,
            db_path=args.db_path,
            stock_pool_file=args.stock_pool
        )

        updater.update(
            start_date=args.start_date,
            end_date=args.end_date
        )

    except KeyboardInterrupt:
        print("\n用户中断操作")
        sys.exit(130)
    except Exception as e:
        logger.error(f"更新失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
