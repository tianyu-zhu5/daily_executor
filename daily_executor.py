#!/usr/bin/env python3
"""
自动化推送脚本 - 每日执行器

功能：
1. 更新K线数据（运行 stock_data_manager.py）
2. 生成当天买入信号（运行 export_cci_signals_for_simulation.py）
3. 推送信号到微信（通过 wechat_pusher.py）

执行时间：每个交易日16:00（通过Windows计划任务）

Author: Daily Executor System
Date: 2025-11-10
"""

import sys
import os
import json
import subprocess
import logging
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import traceback

# 添加CCI-Divergence到路径
sys.path.append(str(Path(__file__).parent.parent / 'CCI-Divergence'))

# 添加UTF-8编码支持（Windows）
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception as e:
        print(f"Warning: Could not reconfigure stdout/stderr encoding: {e}")


class DailyExecutor:
    """每日自动化执行器"""

    def __init__(self, config_file: str = "config.json"):
        """
        初始化执行器

        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.script_dir = Path(__file__).parent.absolute()
        self.config = self._load_config()
        self.logger = self._setup_logging()

    def _load_config(self) -> dict:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception as e:
            print(f"配置文件加载失败: {e}")
            raise

    def _setup_logging(self) -> logging.Logger:
        """设置日志系统"""
        log_dir = Path(self.config['logging']['log_dir'])
        log_dir.mkdir(parents=True, exist_ok=True)

        log_level = getattr(logging, self.config['logging']['log_level'], logging.INFO)

        # 日志文件名：executor_YYYYMMDD_HHMMSS.log
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f"executor_{timestamp}.log"

        # 配置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)

        # 配置logger
        logger = logging.getLogger('DailyExecutor')
        logger.setLevel(log_level)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        logger.info(f"日志系统初始化成功: {log_file}")

        return logger

    def _run_subprocess(
        self,
        command: list,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
        step_name: str = "执行命令"
    ) -> bool:
        """
        运行子进程

        Args:
            command: 命令列表
            cwd: 工作目录
            timeout: 超时时间（秒）
            step_name: 步骤名称（用于日志）

        Returns:
            是否执行成功
        """
        self.logger.info(f"[{step_name}] 开始执行")
        self.logger.info(f"[{step_name}] 命令: {' '.join(command)}")
        if cwd:
            self.logger.info(f"[{step_name}] 工作目录: {cwd}")

        start_time = datetime.now()

        try:
            # 设置环境变量，确保子进程使用UTF-8编码
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'  # Python 3.7+

            # 运行子进程
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=timeout,
                errors='replace',  # 处理编码错误
                env=env  # 传递环境变量
            )

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # 记录输出
            if result.stdout:
                self.logger.info(f"[{step_name}] 标准输出:\n{result.stdout}")

            if result.stderr:
                if result.returncode == 0:
                    self.logger.warning(f"[{step_name}] 标准错误:\n{result.stderr}")
                else:
                    self.logger.error(f"[{step_name}] 标准错误:\n{result.stderr}")

            # 检查返回码
            if result.returncode == 0:
                self.logger.info(f"[{step_name}] 执行成功 (耗时: {duration:.2f}秒)")
                return True
            else:
                self.logger.error(f"[{step_name}] 执行失败 (返回码: {result.returncode})")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error(f"[{step_name}] 执行超时 (超过 {timeout}秒)")
            return False
        except Exception as e:
            self.logger.error(f"[{step_name}] 执行异常: {e}")
            self.logger.error(traceback.format_exc())
            return False

    def _get_today_date(self, custom_date: str = None) -> str:
        """
        获取今天的日期字符串

        Args:
            custom_date: 自定义日期 (YYYY-MM-DD 格式)，如果为None则使用今天

        Returns:
            YYYY-MM-DD 格式的日期字符串
        """
        if custom_date:
            # 验证日期格式
            try:
                datetime.strptime(custom_date, '%Y-%m-%d')
                return custom_date
            except ValueError:
                self.logger.warning(f"日期格式错误: {custom_date}，使用今天日期")
                return datetime.now().strftime('%Y-%m-%d')
        return datetime.now().strftime('%Y-%m-%d')

    def _read_stock_pool(self, stock_pool_file: str) -> Optional[str]:
        """
        读取股票池文件

        Args:
            stock_pool_file: 股票池文件路径

        Returns:
            逗号分隔的股票代码字符串，失败返回None
        """
        stock_pool_path = Path(stock_pool_file)

        if not stock_pool_path.exists():
            self.logger.error(f"股票池文件不存在: {stock_pool_path}")
            return None

        try:
            with open(stock_pool_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 过滤空行和注释行
            stock_codes = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # 提取股票代码（假设每行一个代码）
                    stock_codes.append(line)

            if not stock_codes:
                self.logger.warning(f"股票池文件为空: {stock_pool_path}")
                return None

            stock_list = ','.join(stock_codes)
            self.logger.info(f"成功读取股票池: {len(stock_codes)} 只股票")

            return stock_list

        except Exception as e:
            self.logger.error(f"读取股票池文件失败: {e}")
            return None

    def step1_update_kline_data(self) -> bool:
        """
        步骤1: 更新K线数据

        Returns:
            是否成功
        """
        self.logger.info("=" * 80)
        self.logger.info("步骤1: 更新K线数据")
        self.logger.info("=" * 80)

        script_path = Path(self.config['data_update']['script_path'])
        timeout = self.config['data_update']['timeout_seconds']

        # 检查脚本是否存在
        if not script_path.exists():
            self.logger.error(f"数据更新脚本不存在: {script_path}")
            return False

        # 运行脚本（使用conda quant环境）
        command = ['conda', 'run', '-n', 'quant', 'python', script_path.name]
        cwd = script_path.parent

        success = self._run_subprocess(
            command=command,
            cwd=cwd,
            timeout=timeout,
            step_name="更新K线数据"
        )

        return success

    def step1_5_update_cci_divergence(self, custom_date: str = None) -> bool:
        """
        步骤1.5: 更新CCI底背离数据

        Args:
            custom_date: 自定义日期 (YYYY-MM-DD 格式)

        Returns:
            是否成功
        """
        self.logger.info("=" * 80)
        self.logger.info("步骤1.5: 更新CCI底背离数据")
        self.logger.info("=" * 80)

        try:
            # 延迟导入（避免启动时加载）
            from src.signals.cci_generator import CCIDivergenceGenerator
            from src.database.cci_database import CCIDatabase
        except ImportError as e:
            self.logger.error(f"导入CCI模块失败: {e}")
            self.logger.error("请确保 CCI-Divergence 项目在正确位置")
            return False

        config = self.config['cci_update']
        signal_config = self.config['signal_generation']

        # 获取日期
        target_date = self._get_today_date(custom_date)
        self.logger.info(f"目标日期: {target_date}")

        # 读取股票池
        stock_pool_file = signal_config.get('stock_pool_file')
        if not stock_pool_file:
            self.logger.warning("未配置股票池，将处理所有股票")
            stock_codes = None
        else:
            stock_list_str = self._read_stock_pool(stock_pool_file)
            if stock_list_str is None:
                self.logger.error("读取股票池失败")
                return False
            stock_codes = stock_list_str.split(',')
            self.logger.info(f"股票池: {len(stock_codes)} 只股票")

        # 初始化生成器和数据库
        generator = CCIDivergenceGenerator(
            cci_period=config['cci_period'],
            pivot_window=config['pivot_window'],
            divergence_validity_days=config['divergence_validity_days']
        )

        db_path = Path(config['local_db_path'])
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # 如果数据库不存在或为空，先初始化
        if not db_path.exists() or db_path.stat().st_size == 0:
            self.logger.info(f"初始化本地CCI数据库: {db_path}")

        data_dir = Path(config['data_dir'])

        # 统计
        total_processed = 0
        total_divergences = 0
        success_count = 0
        error_count = 0

        # 处理股票池（如果有的话）
        stocks_to_process = stock_codes if stock_codes else []

        # 如果没有指定股票池，获取所有CSV文件
        if not stocks_to_process:
            csv_files = list(data_dir.glob("*.csv"))
            stocks_to_process = [f.stem for f in csv_files]
            self.logger.info(f"未指定股票池，将处理 {len(stocks_to_process)} 只股票")

        self.logger.info(f"开始处理 {len(stocks_to_process)} 只股票...")

        # 使用上下文管理器自动提交事务
        with CCIDatabase(str(db_path)) as db:
            # 确保数据库表已创建
            db.create_tables()
            for stock_code in stocks_to_process:
                total_processed += 1

                try:
                    # 读取K线数据
                    csv_path = data_dir / f"{stock_code}.csv"
                    if not csv_path.exists():
                        self.logger.debug(f"{stock_code}: CSV文件不存在")
                        continue

                    df = pd.read_csv(csv_path)

                    if 'date' not in df.columns:
                        self.logger.warning(f"{stock_code}: 缺少date列")
                        continue

                    if len(df) == 0:
                        self.logger.debug(f"{stock_code}: 数据为空")
                        continue

                    # 统一日期格式为 YYYY-MM-DD
                    try:
                        # 先转为字符串，然后检测格式
                        df['date'] = df['date'].astype(str).str.strip()

                        # 检测第一个非空日期的格式
                        first_date = df['date'].iloc[0]

                        # 如果是纯数字格式（YYYYMMDD），转换为 YYYY-MM-DD
                        if first_date.replace('.', '').replace('-', '').isdigit() and len(first_date.replace('.', '').replace('-', '')) == 8:
                            if '-' not in first_date and '.' not in first_date:
                                # 格式：20251108 -> 2025-11-08
                                df['date'] = pd.to_datetime(df['date'], format='%Y%m%d').dt.strftime('%Y-%m-%d')
                            elif '.' in first_date:
                                # 格式：2025.11.08 -> 2025-11-08
                                df['date'] = df['date'].str.replace('.', '-')
                    except Exception as date_err:
                        self.logger.error(f"{stock_code}: 日期格式转换失败 - {type(date_err).__name__}: {date_err}")
                        continue

                    # 过滤到目标日期（包含足够的历史数据用于CCI计算）
                    # 需要至少 cci_period + pivot_window 天的数据
                    min_required_days = config['cci_period'] + config['pivot_window'] + 10

                    # 找到目标日期的位置
                    df_filtered = df[df['date'] <= target_date].tail(min_required_days + 50)

                    if len(df_filtered) < 40:
                        self.logger.debug(f"{stock_code}: 数据不足 ({len(df_filtered)}行)")
                        continue

                    # 重要：重置索引，确保索引从0开始连续
                    # divergence_detector 依赖连续的整数索引
                    df_filtered = df_filtered.reset_index(drop=True)

                    # 检测底背离
                    divergences_df = generator.detect_divergences(df_filtered, stock_code)

                    # 只保存目标日期的背离
                    if len(divergences_df) > 0:
                        # 检查必需的列是否存在
                        required_cols = ['divergence_id', 'stock_code', 'start_date', 'end_date',
                                       'start_price', 'end_price', 'start_cci', 'end_cci',
                                       'confidence', 'days_between', 'validity_days', 'expiry_date', 'status']

                        missing_cols = [col for col in required_cols if col not in divergences_df.columns]
                        if missing_cols:
                            self.logger.error(f"{stock_code}: 底背离DataFrame缺少列: {missing_cols}")
                            self.logger.error(f"{stock_code}: 实际列: {list(divergences_df.columns)}")
                            continue

                        # 规范化日期格式（end_date可能是datetime或带时间戳的字符串）
                        divergences_df['end_date'] = pd.to_datetime(divergences_df['end_date']).dt.strftime('%Y-%m-%d')
                        divergences_df['start_date'] = pd.to_datetime(divergences_df['start_date']).dt.strftime('%Y-%m-%d')
                        divergences_df['expiry_date'] = pd.to_datetime(divergences_df['expiry_date']).dt.strftime('%Y-%m-%d')

                    if len(divergences_df) == 0:
                        continue

                    # 保存到数据库
                    new_divergences = 0
                    duplicate_divergences = 0
                    for _, div in divergences_df.iterrows():
                        divergence_dict = {
                            'divergence_id': div['divergence_id'],
                            'stock_code': div['stock_code'],
                            'start_date': div['start_date'],
                            'end_date': div['end_date'],
                            'start_price': float(div['start_price']),
                            'end_price': float(div['end_price']),
                            'start_cci': float(div['start_cci']),
                            'end_cci': float(div['end_cci']),
                            'confidence': float(div['confidence']),
                            'days_between': int(div['days_between']),
                            'validity_days': int(div['validity_days']),
                            'expiry_date': div['expiry_date'],
                            'status': div['status']
                        }
                        try:
                            db.insert_divergence(divergence_dict)
                            new_divergences += 1
                        except Exception as e:
                            if 'UNIQUE constraint failed' in str(e):
                                duplicate_divergences += 1
                                self.logger.debug(f"{stock_code}: 背离 {div['divergence_id']} 已存在，跳过")
                            else:
                                raise

                    total_divergences += new_divergences
                    success_count += 1

                    if len(divergences_df) > 0:
                        if duplicate_divergences > 0:
                            self.logger.info(f"{stock_code}: 发现 {len(divergences_df)} 个底背离 (新增{new_divergences}个，重复{duplicate_divergences}个)")
                        else:
                            self.logger.info(f"{stock_code}: 发现 {len(divergences_df)} 个底背离")

                except Exception as e:
                    error_count += 1
                    error_msg = str(e) if str(e) else repr(e)
                    self.logger.error(f"{stock_code}: 处理失败 - {type(e).__name__}: {error_msg}")
                    # 打印完整堆栈（即使在INFO级别也显示）
                    import traceback as tb
                    self.logger.error(f"{stock_code}: 完整错误:\n{tb.format_exc()}")

        # 统计结果
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("CCI底背离更新完成")
        self.logger.info("=" * 80)
        self.logger.info(f"处理股票数: {total_processed}")
        self.logger.info(f"成功股票数: {success_count}")
        self.logger.info(f"错误股票数: {error_count}")
        self.logger.info(f"总背离数: {total_divergences}")
        self.logger.info(f"数据库路径: {db_path.absolute()}")
        self.logger.info("=" * 80)

        return True

    def step2_generate_signals(self, custom_date: str = None) -> bool:
        """
        步骤2: 生成买入信号

        Args:
            custom_date: 自定义日期 (YYYY-MM-DD 格式)

        Returns:
            是否成功
        """
        self.logger.info("=" * 80)
        self.logger.info("步骤2: 生成买入信号")
        self.logger.info("=" * 80)

        config = self.config['signal_generation']

        # 获取日期（自定义或今天）
        today = self._get_today_date(custom_date)
        self.logger.info(f"目标日期: {today}")

        # 读取股票池
        stock_list = None
        if config.get('stock_pool_file'):
            stock_list = self._read_stock_pool(config['stock_pool_file'])
            # 如果股票池读取失败，根据配置决定是否继续
            if stock_list is None:
                self.logger.warning("未指定股票池，将生成所有股票的信号")

        # 构建命令
        script_path = Path("../CCI-Divergence/scripts/export_cci_signals_for_simulation.py")

        if not script_path.exists():
            self.logger.error(f"信号生成脚本不存在: {script_path}")
            return False

        command = [
            sys.executable,
            str(script_path),
            '--start-date', today,
            '--end-date', today,
            '--output', config['output_file'],
            '--db-path', config['db_path'],
            '--min-confidence', str(config['min_confidence'])
        ]

        # 如果有股票池，添加股票列表参数
        if stock_list:
            command.extend(['--stocks', stock_list])

        # 运行脚本
        success = self._run_subprocess(
            command=command,
            cwd=self.script_dir,
            timeout=600,  # 10分钟超时
            step_name="生成买入信号"
        )

        return success

    def step3_push_to_wechat(self) -> bool:
        """
        步骤3: 推送到微信

        Returns:
            是否成功
        """
        self.logger.info("=" * 80)
        self.logger.info("步骤3: 推送到微信")
        self.logger.info("=" * 80)

        # 检查信号文件是否存在
        signals_file = Path(self.config['signal_generation']['output_file'])

        if not signals_file.exists():
            self.logger.error(f"信号文件不存在: {signals_file}")
            return False

        # 导入推送模块
        try:
            from wechat_pusher import WechatPusher

            pusher = WechatPusher(config_file=str(self.config_file))
            success = pusher.push_signals(str(signals_file))

            return success

        except Exception as e:
            self.logger.error(f"推送失败: {e}")
            self.logger.error(traceback.format_exc())
            return False

    def execute(self, skip_steps: list = None, custom_date: str = None) -> bool:
        """
        执行完整流程

        Args:
            skip_steps: 要跳过的步骤列表，例如 ['step1', 'step3']
            custom_date: 自定义日期 (YYYY-MM-DD 格式)，用于测试历史日期

        Returns:
            是否全部成功
        """
        skip_steps = skip_steps or []

        self.logger.info("=" * 80)
        self.logger.info("自动化推送脚本开始执行")
        self.logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if custom_date:
            self.logger.info(f"测试日期: {custom_date}")
        if skip_steps:
            self.logger.info(f"跳过步骤: {', '.join(skip_steps)}")
        self.logger.info("=" * 80)

        start_time = datetime.now()

        try:
            # 步骤1: 更新K线数据
            if 'step1' in skip_steps:
                self.logger.info("跳过步骤1: 更新K线数据")
            else:
                if not self.step1_update_kline_data():
                    self.logger.error("步骤1失败，停止执行")
                    return False

            # 步骤1.5: 更新CCI底背离数据
            if 'step1.5' in skip_steps or 'step1_5' in skip_steps:
                self.logger.info("跳过步骤1.5: 更新CCI底背离数据")
            else:
                if not self.step1_5_update_cci_divergence(custom_date=custom_date):
                    self.logger.error("步骤1.5失败，停止执行")
                    return False

            # 步骤2: 生成买入信号
            if 'step2' in skip_steps:
                self.logger.info("跳过步骤2: 生成买入信号")
            else:
                if not self.step2_generate_signals(custom_date=custom_date):
                    self.logger.error("步骤2失败，停止执行")
                    return False

            # 步骤3: 推送到微信
            if 'step3' in skip_steps:
                self.logger.info("跳过步骤3: 推送到微信")
            else:
                if not self.step3_push_to_wechat():
                    self.logger.error("步骤3失败，停止执行")
                    return False

            # 全部成功
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            self.logger.info("=" * 80)
            self.logger.info("执行完成")
            self.logger.info(f"总耗时: {duration:.2f}秒")
            self.logger.info("=" * 80)

            return True

        except Exception as e:
            self.logger.error(f"执行过程中发生异常: {e}")
            self.logger.error(traceback.format_exc())
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='自动化推送脚本 - 每日执行器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 完整执行所有步骤（包含CCI底背离更新）
  python daily_executor.py

  # 跳过K线数据更新（数据已是最新）
  python daily_executor.py --skip-step1

  # 跳过K线和CCI更新（使用现有数据库）
  python daily_executor.py --skip-step1 --skip-step1.5

  # 测试模式：只更新CCI数据，不推送
  python daily_executor.py --skip-step1 --skip-step3

  # 指定历史日期测试（包含CCI更新）
  python daily_executor.py --date 2025-09-04 --skip-step1 --dry-run

  # 只更新本地CCI数据库，不生成信号
  python daily_executor.py --skip-step1 --skip-step2 --skip-step3

  # 使用自定义配置文件
  python daily_executor.py --config my_config.json

步骤说明:
  步骤1 (step1): 更新K线数据
  步骤1.5 (step1.5): 更新CCI底背离数据
  步骤2 (step2): 生成买入信号
  步骤3 (step3): 推送到微信
        """
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config.json',
        help='配置文件路径 (默认: config.json)'
    )

    parser.add_argument(
        '--skip-step1',
        action='store_true',
        help='跳过步骤1: 更新K线数据'
    )

    parser.add_argument(
        '--skip-step1.5',
        action='store_true',
        dest='skip_step1_5',
        help='跳过步骤1.5: 更新CCI底背离数据'
    )

    parser.add_argument(
        '--skip-step2',
        action='store_true',
        help='跳过步骤2: 生成买入信号'
    )

    parser.add_argument(
        '--skip-step3',
        action='store_true',
        help='跳过步骤3: 推送到微信'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='演练模式: 跳过推送步骤（等同于 --skip-step3）'
    )

    parser.add_argument(
        '--date', '-d',
        type=str,
        help='指定日期 (YYYY-MM-DD 格式)，用于测试历史日期的信号生成'
    )

    args = parser.parse_args()

    try:
        # 构建跳过步骤列表
        skip_steps = []
        if args.skip_step1:
            skip_steps.append('step1')
        if args.skip_step1_5:
            skip_steps.append('step1.5')
        if args.skip_step2:
            skip_steps.append('step2')
        if args.skip_step3 or args.dry_run:
            skip_steps.append('step3')

        # 创建执行器
        executor = DailyExecutor(config_file=args.config)

        # 执行
        success = executor.execute(skip_steps=skip_steps, custom_date=args.date)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n用户中断操作")
        sys.exit(130)
    except Exception as e:
        print(f"程序异常: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
