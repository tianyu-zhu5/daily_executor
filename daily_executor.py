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

# Import local modules
from query_engine import QueryEngine
from signal_types import Signal

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

        Uses QueryEngine to fetch signals from database instead of calling
        external script. This improves code reuse and maintainability.

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

        try:
            # 读取股票池
            stock_codes = None
            if config.get('stock_pool_file'):
                stock_list_str = self._read_stock_pool(config['stock_pool_file'])
                if stock_list_str:
                    stock_codes = stock_list_str.split(',')
                    self.logger.info(f"股票池: {len(stock_codes)} 只股票")
                else:
                    self.logger.warning("未指定股票池，将生成所有股票的信号")

            # Initialize QueryEngine
            query_engine = QueryEngine(
                db_path=config['db_path'],
                data_dir=config['data_dir']
            )

            # Fetch signals using QueryEngine
            signals = query_engine.get_signals_for_date(
                signal_date=today,
                stock_codes=stock_codes,
                min_confidence=config['min_confidence'],
                use_next_day_open=config.get('use_next_day_open', True)
            )

            if len(signals) == 0:
                self.logger.warning("未找到符合条件的信号")
            else:
                self.logger.info(f"生成 {len(signals)} 个买入信号")

            # Save signals to CSV
            output_file = Path(config['output_file'])
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert signals to DataFrame
            signals_data = [signal.to_dict() for signal in signals]
            signals_df = pd.DataFrame(signals_data)

            # Save to CSV
            signals_df.to_csv(output_file, index=False, encoding='utf-8-sig')

            self.logger.info(f"信号已保存到: {output_file}")

            return True

        except Exception as e:
            self.logger.error(f"生成信号失败: {e}")
            self.logger.error(traceback.format_exc())
            return False

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
    """主函数 - 支持run和query两种模式"""
    # 创建主解析器
    parser = argparse.ArgumentParser(
        description='Daily Executor - 自动化股票信号推送系统',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # 全局参数
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config.json',
        help='配置文件路径 (默认: config.json)'
    )

    # 创建子命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # ============================================================================
    # RUN 命令 - 每日自动执行
    # ============================================================================
    run_parser = subparsers.add_parser(
        'run',
        help='执行每日自动化流程',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 完整执行所有步骤
  python daily_executor.py run

  # 跳过K线数据更新
  python daily_executor.py run --skip-step1

  # 测试模式（不推送）
  python daily_executor.py run --dry-run

  # 指定历史日期测试
  python daily_executor.py run --date 2025-11-06 --skip-step1
        """
    )

    run_parser.add_argument(
        '--skip-step1',
        action='store_true',
        help='跳过步骤1: 更新K线数据'
    )

    run_parser.add_argument(
        '--skip-step1.5',
        action='store_true',
        dest='skip_step1_5',
        help='跳过步骤1.5: 更新CCI底背离数据'
    )

    run_parser.add_argument(
        '--skip-step2',
        action='store_true',
        help='跳过步骤2: 生成买入信号'
    )

    run_parser.add_argument(
        '--skip-step3',
        action='store_true',
        help='跳过步骤3: 推送到微信'
    )

    run_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='演练模式: 跳过推送步骤'
    )

    run_parser.add_argument(
        '--date', '-d',
        type=str,
        help='指定日期 (YYYY-MM-DD)'
    )

    # ============================================================================
    # QUERY 命令 - 历史信号查询
    # ============================================================================
    query_parser = subparsers.add_parser(
        'query',
        help='查询历史买入信号',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 查询指定日期的信号
  python daily_executor.py query --date 2025-11-06

  # 查询日期范围的信号
  python daily_executor.py query --date-range 2025-11-01 2025-11-10

  # 查询并输出为JSON
  python daily_executor.py query --date 2025-11-06 --output json

  # 查询并推送到微信
  python daily_executor.py query --date 2025-11-06 --push-wechat

  # 高置信度信号查询
  python daily_executor.py query --date-range 2025-11-01 2025-11-10 --min-confidence 0.8

  # 查询特定股票
  python daily_executor.py query --date 2025-11-06 --stock-code 600519_SH
        """
    )

    # 日期参数（互斥）
    date_group = query_parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        '--date', '-d',
        type=str,
        help='查询单个日期 (YYYY-MM-DD)'
    )

    date_group.add_argument(
        '--date-range',
        nargs=2,
        metavar=('START', 'END'),
        help='查询日期范围 (START END, YYYY-MM-DD)'
    )

    # 过滤参数
    query_parser.add_argument(
        '--stock-code',
        type=str,
        help='指定股票代码 (如: 600519_SH)'
    )

    query_parser.add_argument(
        '--min-confidence',
        type=float,
        help='最小置信度 (0.0-1.0)'
    )

    # 输出参数
    query_parser.add_argument(
        '--output',
        action='append',
        choices=['console', 'csv', 'json'],
        help='输出格式 (可多次指定)'
    )

    query_parser.add_argument(
        '--push-wechat',
        action='store_true',
        help='推送查询结果到微信'
    )

    query_parser.add_argument(
        '--output-file',
        type=str,
        help='输出文件路径 (用于csv/json)'
    )

    # 解析参数
    args = parser.parse_args()

    # 如果没有指定命令，默认使用run（向后兼容）
    if args.command is None:
        args.command = 'run'
        # 保留旧参数的向后兼容性
        args.skip_step1 = False
        args.skip_step1_5 = False
        args.skip_step2 = False
        args.skip_step3 = False
        args.dry_run = False
        args.date = None

    try:
        if args.command == 'run':
            # RUN模式 - 执行每日自动化流程
            skip_steps = []
            if args.skip_step1:
                skip_steps.append('step1')
            if args.skip_step1_5:
                skip_steps.append('step1.5')
            if args.skip_step2:
                skip_steps.append('step2')
            if args.skip_step3 or args.dry_run:
                skip_steps.append('step3')

            executor = DailyExecutor(config_file=args.config)
            success = executor.execute(skip_steps=skip_steps, custom_date=args.date)
            sys.exit(0 if success else 1)

        elif args.command == 'query':
            # QUERY模式 - 历史信号查询（Phase 2实现）
            run_query_command(args)

    except KeyboardInterrupt:
        print("\n用户中断操作")
        sys.exit(130)
    except Exception as e:
        print(f"程序异常: {e}")
        traceback.print_exc()
        sys.exit(1)


def run_query_command(args):
    """
    执行query命令 - 历史信号查询

    Args:
        args: 命令行参数
    """
    import formatters

    print("=" * 80)
    print("历史信号查询")
    print("=" * 80)

    try:
        # Load config
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"❌ 配置文件不存在: {config_path}")
            sys.exit(1)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        signal_config = config['signal_generation']

        # Determine date range
        if args.date:
            start_date = args.date
            end_date = args.date
            query_desc = f"日期: {args.date}"
        elif args.date_range:
            start_date = args.date_range[0]
            end_date = args.date_range[1]
            query_desc = f"日期范围: {start_date} ~ {end_date}"
        else:
            print("❌ 必须指定 --date 或 --date-range")
            sys.exit(1)

        # Parse stock codes filter
        stock_codes = None
        if args.stock_code:
            stock_codes = [args.stock_code]
            query_desc += f" | 股票: {args.stock_code}"

        # Parse confidence filter
        min_confidence = args.min_confidence if args.min_confidence else signal_config.get('min_confidence', 0.0)
        if args.min_confidence:
            query_desc += f" | 最小置信度: {min_confidence}"

        print(f"查询条件: {query_desc}")
        print()

        # Initialize QueryEngine
        query_engine = QueryEngine(
            db_path=signal_config['db_path'],
            data_dir=signal_config['data_dir']
        )

        # Execute query
        print("⏳ 查询中...")
        signals = query_engine.fetch_signals(
            start_date=start_date,
            end_date=end_date,
            stock_codes=stock_codes,
            min_confidence=min_confidence,
            use_next_day_open=signal_config.get('use_next_day_open', True)
        )

        if not signals:
            print()
            print("⚠️  未找到符合条件的信号")
            print()
            print("提示:")
            print("  - 检查指定日期是否在数据库范围内")
            print("  - 尝试降低 --min-confidence 阈值")
            print("  - 确认CCI数据库已包含该时期的数据")
            print()
            sys.exit(0)

        print(f"✅ 找到 {len(signals)} 个信号")
        print()

        # Determine output formats
        output_formats = args.output if args.output else ['console']

        # Process each output format
        for fmt in output_formats:
            if fmt == 'console':
                console_output = formatters.format_console(signals)
                print(console_output)
                print()

            elif fmt == 'csv':
                # Determine output file
                if args.output_file:
                    csv_file = args.output_file
                else:
                    # Auto-generate filename
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    csv_file = f"./signals/query_{start_date}_{timestamp}.csv"

                formatters.to_csv(signals, csv_file)
                print()

            elif fmt == 'json':
                # Determine output file
                if args.output_file:
                    json_file = args.output_file
                else:
                    # Auto-generate filename
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    json_file = f"./signals/query_{start_date}_{timestamp}.json"

                formatters.to_json(signals, json_file)
                print()

        # Push to WeChat if requested
        if args.push_wechat:
            print("📱 推送到微信...")
            try:
                # Create markdown message
                markdown_msg = formatters.to_wechat_markdown(
                    signals,
                    query_date=args.date if args.date else f"{start_date}~{end_date}"
                )

                # Use WechatPusher to send
                from wechat_pusher import WechatPusher

                pusher = WechatPusher(config_file=args.config)

                # Create a temporary message for push
                title = f"📊 查询结果 ({len(signals)}个信号)"

                # Push to all enabled recipients
                server_sauce_config = config['server_sauce']
                success_count = 0
                total_count = 0

                for recipient in server_sauce_config['recipients']:
                    if not recipient.get('enabled', True):
                        continue

                    total_count += 1

                    import requests
                    sendkey = recipient['sendkey']
                    url = f"https://sctapi.ftqq.com/{sendkey}.send"

                    response = requests.post(url, data={
                        'title': title,
                        'desp': markdown_msg
                    })

                    if response.status_code == 200:
                        result = response.json()
                        if result.get('code') == 0:
                            print(f"  ✅ 成功推送到: {recipient['name']}")
                            success_count += 1
                        else:
                            print(f"  ❌ 推送失败: {recipient['name']} - {result.get('message')}")
                    else:
                        print(f"  ❌ 推送失败: {recipient['name']} - HTTP {response.status_code}")

                print()
                print(f"推送完成: {success_count}/{total_count} 成功")

            except Exception as e:
                print(f"❌ 推送失败: {e}")
                traceback.print_exc()

        print()
        print("=" * 80)
        print(f"查询完成: {formatters.format_summary(signals)}")
        print("=" * 80)

        sys.exit(0)

    except Exception as e:
        print(f"\n❌ 查询失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
