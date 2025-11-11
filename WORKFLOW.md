# Daily Executor 工作流文档

## 系统概述

Daily Executor 是一个股票信号管理系统，支持两种操作模式：

### 模式 1: 日常自动化执行（run 命令）
每个交易日自动执行完整流程：
1. 更新K线数据
2. 检测CCI底背离信号
3. 生成买入信号
4. 推送到微信（通过Server酱）

### 模式 2: 历史信号查询（query 命令）
快速查询历史交易日的信号，无需重新运行数据更新流程。

---

## 系统架构 v2.0

```
daily_executor/
├── daily_executor.py         # 主执行脚本（run + query 命令）⭐
├── query_engine.py           # 查询引擎（统一查询逻辑）⭐
├── signal_types.py           # 信号数据类型定义 ⭐
├── formatters.py             # 输出格式化器（console/CSV/JSON/WeChat）⭐
├── config.json               # 配置文件
├── wechat_pusher.py          # 微信推送模块
├── update_cci_database.py    # CCI数据库更新工具
├── add_database_indexes.py   # 数据库索引工具 ⭐
├── setup_task.bat            # Windows定时任务设置
├── data/                     # 本地数据目录
│   └── cci_signals.db       # CCI底背离数据库
├── signals/                  # 生成的信号文件
│   ├── daily_signals.csv    # 每日买入信号（run 模式）
│   ├── query_*.csv          # 查询结果CSV（query 模式）⭐
│   └── query_*.json         # 查询结果JSON（query 模式）⭐
└── logs/                     # 日志文件
```

### 架构亮点 ⭐

**代码复用设计**：
- `QueryEngine` 类统一封装所有CCI信号查询逻辑
- run 模式的每日信号生成本质上是 query 模式的特例（查询日期 = 今天）
- 消除了约 200 行重复代码

**性能优化**：
- 添加 4 个数据库索引（end_date, expiry_date, stock_code, confidence）
- 查询性能从 O(N) 提升到 O(log N)
- 单日查询 < 0.5 秒，10 天范围 < 1 秒

---

## QueryEngine 架构（v2.0 核心）

### 设计理念

**统一查询接口**：将日常信号生成视为历史查询的特例
```python
# run 模式下的每日信号生成
signals = query_engine.get_signals_for_date(
    signal_date=today,  # 查询今天的信号
    stock_codes=stock_pool,
    min_confidence=0.6
)

# query 模式下的历史查询
signals = query_engine.fetch_signals(
    start_date="2025-09-01",
    end_date="2025-09-10",
    stock_codes=stock_pool,
    min_confidence=0.7
)
```

### QueryEngine 类结构

```python
class QueryEngine:
    def __init__(self, db_path: str, data_dir: str):
        """初始化查询引擎"""

    def fetch_signals(
        self,
        start_date,
        end_date,
        stock_codes=None,
        min_confidence=0.0,
        use_next_day_open=True
    ) -> List[Signal]:
        """核心查询方法，支持日期范围和多种过滤条件"""

    def get_signals_for_date(
        self,
        signal_date,
        stock_codes=None,
        min_confidence=0.0,
        use_next_day_open=True
    ) -> List[Signal]:
        """便捷方法：查询单个日期的信号"""

    def _get_next_trading_day_open_price(
        self,
        stock_code,
        signal_date
    ) -> Optional[float]:
        """防止前视偏差：使用次日开盘价作为入场价"""
```

### 查询逻辑

**SQL 查询核心**：
```sql
SELECT * FROM divergence_events
WHERE end_date >= ?           -- 背离结束日期在范围内
  AND end_date <= ?           -- 背离结束日期在范围内
  AND confidence >= ?         -- 置信度过滤
  AND (? IS NULL OR stock_code IN (?))  -- 股票代码过滤（可选）
ORDER BY end_date, confidence DESC
```

**无前视偏差设计**：
- 查询条件确保 `end_date` <= 目标日期（背离已经形成）
- 入场价使用次日开盘价（`use_next_day_open=True`）
- 避免使用未来数据进行回测

### Signal 数据类型

```python
@dataclass
class Signal:
    stock_code: str
    signal_date: str
    confidence: float
    entry_price: float
    reason: str
    divergence_id: str

    def to_dict(self) -> dict:
        """转换为字典，便于输出"""
```

**统一数据结构的好处**：
- 类型安全（通过 dataclass）
- 易于序列化（to_dict 方法）
- 跨模块一致性（formatters, daily_executor 共用）

### 格式化器架构

```python
# formatters.py 提供 4 种输出格式

def format_console(signals: List[Signal]) -> str:
    """控制台表格输出 + 统计信息"""

def to_csv(signals: List[Signal], output_file: str) -> bool:
    """CSV 导出（UTF-8-sig 编码）"""

def to_json(signals: List[Signal], output_file: str = None) -> str:
    """JSON 导出（包含查询元数据和统计信息）"""

def to_wechat_markdown(signals: List[Signal], query_date: str = None) -> str:
    """Server酱推送格式（Markdown）"""
```

**格式化器特点**：
- 解耦查询逻辑和输出格式
- 支持多种输出格式组合
- 统一的统计信息计算

---

## 工作流程详解

### 步骤1：更新K线数据（仅 run 模式）

**目标**：从miniQMT获取最新的股票K线数据

**执行命令**：
```bash
conda run -n quant python ../data/stock_data_manager.py
```

**关键点**：
- 使用conda quant环境（包含xtquant库）
- 更新../data/daily/目录下的所有股票CSV文件
- 数据格式：date, open, high, low, close, volume, amount

**常见问题**：
- `xtquant库未找到`：需要在quant环境中安装xtquant
- `miniQMT未连接`：确保miniQMT客户端运行中

---

### 步骤1.5：更新CCI底背离数据

**目标**：检测股票池中的CCI底背离形态，保存到本地数据库

**核心逻辑**：
```python
1. 读取股票池（默认：沪深300）
2. 对每只股票：
   a. 读取K线数据（截止到目标日期）
   b. 使用CCIDivergenceGenerator检测底背离
   c. 将新检测到的背离保存到./data/cci_signals.db
3. 自动跳过重复的背离记录
```

**配置参数**：
```json
{
  "cci_update": {
    "local_db_path": "./data/cci_signals.db",
    "data_dir": "../data/daily",
    "cci_period": 20,          // CCI指标周期
    "pivot_window": 10,        // 极值窗口
    "divergence_validity_days": 20,  // 背离有效期
    "timeout_seconds": 600
  }
}
```

**数据库表结构**：
```sql
CREATE TABLE divergence_events (
    divergence_id TEXT PRIMARY KEY,
    stock_code TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    start_price REAL,
    end_price REAL,
    start_cci REAL,
    end_cci REAL,
    confidence REAL,
    days_between INTEGER,
    validity_days INTEGER,
    expiry_date TEXT,
    status TEXT
);
```

**重要特性**：
- **无前视偏差设计**：检测到的背离end_date会早于目标日期
- **自动去重**：使用divergence_id主键防止重复插入
- **增量更新**：新背离会累积到数据库中

---

### 步骤2：生成买入信号（run 和 query 模式共用）⭐

**目标**：从CCI数据库中筛选出有效的买入信号

**架构升级（v2.0）**：
- **之前**：调用外部脚本 `export_cci_signals_for_simulation.py`
- **现在**：使用 `QueryEngine` 类直接查询数据库
- **好处**：代码复用，消除重复逻辑，统一维护

**run 模式执行逻辑**：
```python
# daily_executor.py step2_generate_signals()

# 初始化查询引擎
query_engine = QueryEngine(
    db_path=config['db_path'],
    data_dir=config['data_dir']
)

# 查询今日信号（本质上是查询 signal_date = today）
signals = query_engine.get_signals_for_date(
    signal_date=today,
    stock_codes=stock_codes,
    min_confidence=config['min_confidence'],
    use_next_day_open=config.get('use_next_day_open', True)
)

# 转换为DataFrame并保存CSV
signals_data = [signal.to_dict() for signal in signals]
signals_df = pd.DataFrame(signals_data)
signals_df.to_csv(output_file, index=False, encoding='utf-8-sig')
```

**query 模式执行逻辑**：
```python
# daily_executor.py run_query_command()

# 初始化查询引擎
query_engine = QueryEngine(
    db_path=config['db_path'],
    data_dir=config['data_dir']
)

# 查询指定日期范围的信号
signals = query_engine.fetch_signals(
    start_date=start_date,
    end_date=end_date,
    stock_codes=stock_codes if args.stock_code else None,
    min_confidence=args.min_confidence or config['min_confidence']
)

# 使用 formatters 输出多种格式
for fmt in output_formats:
    if fmt == 'console':
        print(formatters.format_console(signals))
    elif fmt == 'csv':
        formatters.to_csv(signals, csv_file)
    elif fmt == 'json':
        formatters.to_json(signals, json_file)
```

**输出格式**：
```csv
stock_code,signal_date,confidence,entry_price,reason,divergence_id
600000_SH,2025-11-04,0.6229,11.36,"CCI底背离(CCI:-105.4→-102.5, 39天)",600000_SH_20251104
```

**关键配置**：
```json
{
  "signal_generation": {
    "db_path": "../CCI_Divergence/data/cci_signals.db",
    "data_dir": "../CCI_Divergence/data/daily",
    "output_file": "./signals/daily_signals.csv",
    "min_confidence": 0.6,
    "use_next_day_open": true  // 使用次日开盘价
  }
}
```

---

### 步骤3：推送到微信

**目标**：通过Server酱将信号推送到多个微信账户

**配置示例**：
```json
{
  "server_sauce": {
    "recipients": [
      {
        "name": "张三",
        "sendkey": "SCT123xxx实际的SendKey",
        "enabled": true
      },
      {
        "name": "李四",
        "sendkey": "SCT456xxx实际的SendKey",
        "enabled": true
      }
    ]
  }
}
```

**消息格式**：
```markdown
## 📈 今日买入信号 (2025-11-06)

找到 3 个买入信号：

### 信号列表
- **600000_SH** (浦发银行)
  - 置信度: 62.29%
  - 入场价: 11.36
  - 原因: CCI底背离(CCI:-105.4→-102.5, 39天)

---
🤖 Generated with Claude Code
```

---

## 命令行参数

### run 命令（日常自动化）

**基本用法**：
```bash
# 执行完整流程（当日数据）
python daily_executor.py run
# 或直接运行（默认为 run 模式）
python daily_executor.py

# 测试指定日期
python daily_executor.py run --date 2025-11-06

# 跳过某些步骤
python daily_executor.py run --skip-step1 --skip-step3
```

**完整参数列表**：
| 参数 | 说明 | 示例 |
|------|------|------|
| `--date` | 指定日期（YYYY-MM-DD） | `--date 2025-11-06` |
| `--skip-step1` | 跳过K线数据更新 | |
| `--skip-step1.5` | 跳过CCI背离检测 | |
| `--skip-step2` | 跳过信号生成 | |
| `--skip-step3` | 跳过微信推送 | |
| `--config` | 自定义配置文件 | `--config my_config.json` |

### query 命令（历史查询）⭐

**基本用法**：
```bash
# 查询单个日期
python daily_executor.py query --date 2025-09-04

# 查询日期范围
python daily_executor.py query --date-range 2025-09-01 2025-09-10

# 带过滤条件查询
python daily_executor.py query --date 2025-09-04 --min-confidence 0.7 --stock-code 600000_SH

# 多种输出格式
python daily_executor.py query --date 2025-09-04 --output csv --output json --push-wechat
```

**完整参数列表**：
| 参数 | 说明 | 示例 |
|------|------|------|
| `--date` | 查询单个日期（YYYY-MM-DD） | `--date 2025-09-04` |
| `--date-range` | 查询日期范围（start end） | `--date-range 2025-09-01 2025-09-10` |
| `--stock-code` | 查询特定股票 | `--stock-code 600000_SH` |
| `--min-confidence` | 最小置信度过滤 | `--min-confidence 0.7` |
| `--output` | 输出格式（可多次指定） | `--output csv --output json` |
| | 可选值：console, csv, json | |
| `--push-wechat` | 推送到微信 | |
| `--config` | 自定义配置文件 | `--config my_config.json` |

---

## 定时任务设置

### Windows 任务计划程序

**运行 setup_task.bat**（管理员权限）：
```batch
@echo off
schtasks /create /tn "DailyExecutor" /tr "C:\ProgramData\anaconda3\python.exe C:\Users\Administrator\Documents\quant\daily_executor\daily_executor.py" /sc daily /st 16:00 /f
```

**手动创建**：
1. 打开"任务计划程序"
2. 创建基本任务
3. 触发器：每天下午4:00
4. 操作：启动程序
   - 程序：`C:\ProgramData\anaconda3\python.exe`
   - 参数：`C:\Users\Administrator\Documents\quant\daily_executor\daily_executor.py`
   - 起始于：`C:\Users\Administrator\Documents\quant\daily_executor`

---

## 故障排查

### 问题1：步骤1失败 - xtquant库未找到
**原因**：未激活conda quant环境
**解决**：
```bash
conda activate quant
pip install xtquant
```

### 问题2：步骤1.5找到大量重复背离
**原因**：正常现象，CCI检测算法的无前视偏差设计导致每次运行会检测到历史背离
**解决**：系统会自动跳过重复记录，只统计新增背离

### 问题3：步骤2未找到信号
**原因**：
- 目标日期没有在有效期内的背离
- 所有背离的expiry_date早于目标日期

**解决**：
```bash
# 查询数据库中的背离
sqlite3 data/cci_signals.db "SELECT end_date, expiry_date, stock_code FROM divergence_events ORDER BY end_date DESC LIMIT 10"

# 使用有背离的日期测试
python daily_executor.py --date 2025-11-04
```

### 问题4：微信推送失败
**原因**：Server酱SendKey无效
**解决**：
1. 访问 https://sct.ftqq.com/
2. 微信扫码登录
3. 获取SendKey
4. 更新config.json中的sendkey

---

## 数据流图

### run 模式（日常自动化）
```
miniQMT
   ↓
[步骤1] stock_data_manager.py
   ↓
../CCI_Divergence/data/daily/*.csv
   ↓
[步骤1.5] CCIDivergenceGenerator
   ↓
../CCI_Divergence/data/cci_signals.db (divergence_events表)
   ↓
[步骤2] QueryEngine.get_signals_for_date(today) ⭐
   ↓
List[Signal] → DataFrame → CSV
   ↓
./signals/daily_signals.csv
   ↓
[步骤3] wechat_pusher.py → Server酱 → 微信
```

### query 模式（历史查询）⭐
```
用户指定日期/日期范围
   ↓
QueryEngine.fetch_signals(start_date, end_date, filters) ⭐
   ↓
查询 ../CCI_Divergence/data/cci_signals.db
   ↓
List[Signal] ← 统一数据结构
   ↓
   ├─→ formatters.format_console() → 控制台输出
   ├─→ formatters.to_csv() → ./signals/query_*.csv
   ├─→ formatters.to_json() → ./signals/query_*.json
   └─→ formatters.to_wechat_markdown() → Server酱 → 微信
```

### 架构统一性 ⭐
```
run 模式的步骤2 本质上是：
QueryEngine.get_signals_for_date(today)
↓
QueryEngine.fetch_signals(
    start_date=today,
    end_date=today,
    ...
)
```

**代码复用好处**：
- 维护一套查询逻辑
- 保证两种模式结果一致
- 新增过滤条件只需改一处

---

## 性能指标

### run 模式性能

- **步骤1**：约1-5分钟（取决于股票数量和网络）
- **步骤1.5**：约1-2秒（311只沪深300股票）
- **步骤2**（使用 QueryEngine）：约 0.12-0.19 秒 ⭐
- **步骤3**：约1秒/人

**总耗时**：通常在2-7分钟内完成

### query 模式性能 ⭐

**无索引时**（初次使用）：
- 单日查询：约 2-5 秒
- 10 天范围：约 5-10 秒

**添加索引后**（推荐）：
```bash
python add_database_indexes.py ../CCI_Divergence/data/cci_signals.db
```

- 单日查询：< 0.5 秒
- 10 天范围：< 1 秒
- 30 天范围：< 2 秒

**性能提升**：10x - 20x 加速（从 O(N) 到 O(log N)）

---

## 日志说明

### 日志位置
```
logs/executor_YYYYMMDD_HHMMSS.log
```

### 日志级别
- **INFO**：正常流程信息
- **WARNING**：警告（如文件不存在）
- **ERROR**：错误（如执行失败）

### 关键日志
```
[步骤1.5] 000001_SZ: 发现 1 个底背离 (新增0个，重复1个)
[步骤2] 总信号数: 3
[步骤3] 成功推送到: 张三
```

---

## 最佳实践

1. **首次运行**：
   - 先跳过步骤1（`--skip-step1`）测试步骤1.5和2
   - 使用历史日期验证信号生成逻辑
   - 使用`--dry-run`避免真实推送

2. **日常运行**：
   - 每天16:00自动执行
   - 检查logs/确认执行成功
   - 监控微信消息接收情况

3. **数据库维护**：
   - 定期清理过期背离（expiry_date < today - 30天）
   - 备份cci_signals.db

4. **配置调整**：
   - 根据回测结果调整min_confidence
   - 扩展或缩小股票池

---

## 更新日志

### v2.0.0 - 2025-11-11 ⭐ 重大架构升级
- ✅ **新增 query 命令**：支持查询历史交易日信号
  - 单日查询：`--date`
  - 日期范围：`--date-range`
  - 过滤条件：`--stock-code`, `--min-confidence`
  - 多格式输出：console/CSV/JSON/WeChat

- ✅ **架构重构**：
  - 创建 `QueryEngine` 类统一查询逻辑
  - 创建 `signal_types.py` 统一数据结构
  - 创建 `formatters.py` 模块化输出格式
  - 步骤2 重构为使用 `QueryEngine`（消除 ~200 行重复代码）

- ✅ **性能优化**：
  - 添加 4 个数据库索引（end_date, expiry_date, stock_code, confidence）
  - 查询性能提升 10x-20x（O(N) → O(log N)）
  - 单日查询 < 0.5 秒，10 天范围 < 1 秒

- ✅ **开发体验改进**：
  - argparse 子命令架构（run/query）
  - 向后兼容（无命令默认为 run）
  - 添加 `add_database_indexes.py` 索引工具

### v1.0.0 - 2025-11-11
- ✅ 修复数据库事务提交问题（使用context manager）
- ✅ 添加重复背离自动跳过逻辑
- ✅ 修改步骤1使用conda quant环境
- ✅ 完善日志输出和错误处理

### 初始版本
- ✅ 实现三步工作流
- ✅ 支持多人微信推送
- ✅ 集成CCI底背离检测
