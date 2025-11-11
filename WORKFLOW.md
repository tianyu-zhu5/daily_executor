# Daily Executor 工作流文档

## 系统概述

Daily Executor 是一个自动化股票信号推送系统，每个交易日自动执行以下流程：
1. 更新K线数据
2. 检测CCI底背离信号
3. 生成买入信号
4. 推送到微信（通过Server酱）

---

## 系统架构

```
daily_executor/
├── daily_executor.py      # 主执行脚本
├── config.json            # 配置文件
├── wechat_pusher.py       # 微信推送模块
├── update_cci_database.py # CCI数据库更新工具
├── setup_task.bat         # Windows定时任务设置
├── data/                  # 本地数据目录
│   └── cci_signals.db    # CCI底背离数据库
├── signals/               # 生成的信号文件
│   └── daily_signals.csv # 每日买入信号
└── logs/                  # 日志文件
```

---

## 工作流程详解

### 步骤1：更新K线数据

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

### 步骤2：生成买入信号

**目标**：从CCI数据库中筛选出当日有效的买入信号

**执行逻辑**：
```python
1. 调用export_cci_signals_for_simulation.py
2. 查询条件：
   - end_date < target_date <= expiry_date（背离在有效期内）
   - stock_code in 股票池
   - confidence >= min_confidence（默认0.1）
3. 生成./signals/daily_signals.csv
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
    "db_path": "./data/cci_signals.db",
    "output_file": "./signals/daily_signals.csv",
    "min_confidence": 0.1,
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

### 基本用法
```bash
# 执行完整流程（当日数据）
python daily_executor.py

# 测试指定日期
python daily_executor.py --date 2025-11-06

# 跳过某些步骤
python daily_executor.py --skip-step1 --skip-step3

# 干跑模式（不推送）
python daily_executor.py --dry-run
```

### 完整参数列表
| 参数 | 说明 | 示例 |
|------|------|------|
| `--date` | 指定日期（YYYY-MM-DD） | `--date 2025-11-06` |
| `--skip-step1` | 跳过K线数据更新 | |
| `--skip-step1.5` | 跳过CCI背离检测 | |
| `--skip-step2` | 跳过信号生成 | |
| `--skip-step3` | 跳过微信推送 | |
| `--dry-run` | 干跑模式 | |
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

```
miniQMT
   ↓
[步骤1] stock_data_manager.py
   ↓
../data/daily/*.csv
   ↓
[步骤1.5] CCIDivergenceGenerator
   ↓
./data/cci_signals.db (divergence_events表)
   ↓
[步骤2] export_cci_signals_for_simulation.py
   ↓
./signals/daily_signals.csv
   ↓
[步骤3] wechat_pusher.py → Server酱 → 微信
```

---

## 性能指标

- **步骤1**：约1-5分钟（取决于股票数量和网络）
- **步骤1.5**：约1-2秒（311只沪深300股票）
- **步骤2**：约0.5秒
- **步骤3**：约1秒/人

**总耗时**：通常在2-7分钟内完成

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

### 2025-11-11
- ✅ 修复数据库事务提交问题（使用context manager）
- ✅ 添加重复背离自动跳过逻辑
- ✅ 修改步骤1使用conda quant环境
- ✅ 完善日志输出和错误处理

### 初始版本
- ✅ 实现三步工作流
- ✅ 支持多人微信推送
- ✅ 集成CCI底背离检测
