# Database Update Issue - Root Cause and Fix

## Problem Summary

执行 `daily_executor.py run` 后，数据库没有更新到最新日期，查询2025年11月的信号返回空结果。

## Root Cause Analysis

经过 Gemini 深度分析，发现了两个关键问题：

### 1. CRITICAL: Database Path Inconsistency (数据库路径不一致)

**问题描述：**
- Step 1.5 (CCI底背离更新) 写入到：`./data/cci_signals.db` (LOCAL 本地数据库)
- Step 2 (信号生成查询) 读取自：`../CCI-Divergence/data/cci_signals.db` (SOURCE 源数据库)

**证据：**
```
# Step 1.5 日志显示
数据库路径: C:\Users\Administrator\Documents\quant\daily_executor\data\cci_signals.db
总背离数: 21  # 成功更新了本地数据库

# check_database_dates.py 显示
数据库路径: C:\Users\Administrator\Documents\quant\daily_executor\..\CCI-Divergence\data\cci_signals.db
数据库日期范围: 2020-10-26 至 2025-09-16  # 源数据库未更新
```

**后果：**
- 更新操作成功执行（21个新的底背离信号）
- 但是更新到了错误的数据库（本地数据库）
- 查询操作读取源数据库，看到的仍然是旧数据（2025-09-16）
- 造成"数据库没有更新"的假象

### 2. HIGH: Error Masking (错误掩盖)

**问题描述：**
miniQMT 连接失败，但被标记为执行成功。

**证据：**
```
[2025-11-11 10:48:51] ✗ 无法获取测试数据，请检查 miniQMT 配置
[2025-11-11 10:48:51] 程序终止
2025-11-11 10:48:51 - DailyExecutor - INFO - [更新K线数据] 执行成功 (耗时: 1.33秒)
```

**原因：**
- 子进程脚本虽然报告失败，但退出码为 0
- `subprocess.run()` 只检查 `returncode`，认为执行成功
- 失败信息没有被正确传播，导致后续步骤继续执行

## Solutions Implemented

### Fix 1: 统一数据库路径 (config.json)

**修改前：**
```json
{
  "signal_generation": {
    "db_path": "../CCI-Divergence/data/cci_signals.db"
  },
  "cci_update": {
    "local_db_path": "./data/cci_signals.db",  // ❌ 不同的路径！
    "data_dir": "../data/daily"
  }
}
```

**修改后：**
```json
{
  "signal_generation": {
    "db_path": "../CCI-Divergence/data/cci_signals.db"
  },
  "cci_update": {
    "local_db_path": "../CCI-Divergence/data/cci_signals.db",  // ✅ 统一到源数据库
    "data_dir": "../CCI-Divergence/data/daily"  // ✅ 也统一数据目录
  }
}
```

**影响：**
- 所有操作现在使用同一个数据库作为真实来源
- 消除了数据库同步问题
- 无需数据迁移

### Fix 2: 改进错误检测 (daily_executor.py)

**修改前：**
```python
# 只检查返回码
if result.returncode == 0:
    self.logger.info(f"[{step_name}] 执行成功")
    return True
else:
    self.logger.error(f"[{step_name}] 执行失败")
    return False
```

**修改后：**
```python
# 检查返回码和输出内容中的失败指示器
failure_indicators = [
    "程序终止",
    "无法获取",
    "失败",
    "错误",
    "Exception",
    "Error:",
    "Traceback"
]

# 检查输出中是否包含失败指示器
output_text = (result.stdout or "") + (result.stderr or "")
has_failure_indicator = any(indicator in output_text for indicator in failure_indicators)

if result.returncode == 0 and not has_failure_indicator:
    self.logger.info(f"[{step_name}] 执行成功")
    return True
else:
    if result.returncode != 0:
        self.logger.error(f"[{step_name}] 执行失败 (返回码: {result.returncode})")
    else:
        self.logger.error(f"[{step_name}] 执行失败 (检测到失败指示器)")
    return False
```

**影响：**
- 即使子进程返回 0，也能检测到脚本级别的失败
- 防止级联失败（避免在错误数据上继续执行）
- 更准确的错误报告

## Verification Steps

修复后，按以下步骤验证：

1. **运行完整流程**
   ```bash
   cd C:\Users\Administrator\Documents\quant\daily_executor
   conda activate your_env
   python daily_executor.py run
   ```

2. **检查日志中的数据库路径**
   应该显示：`../CCI-Divergence/data/cci_signals.db`

3. **验证数据库已更新**
   ```bash
   python check_database_dates.py
   ```
   应该显示 2025年11月 的数据

4. **测试查询功能**
   ```bash
   python daily_executor.py query --date 2025-11-06
   ```
   应该返回信号结果（如果该日期有交易）

## Expert Recommendations (from Gemini Analysis)

1. **Long-term improvement**: 使用基于项目根目录的绝对路径，而不是依赖当前工作目录的相对路径
2. **Error handling best practice**: 子进程脚本应该在任何异常情况下使用 `sys.exit(1)` 显式返回非零退出码
3. **Clean up**: 可以删除本地数据库文件 `./data/cci_signals.db` 以避免未来混淆

## Files Modified

- `config.json` - 统一数据库路径配置
- `daily_executor.py` - 改进子进程错误检测逻辑

## Confidence Level

**VERY HIGH** - Root cause confirmed through systematic analysis and evidence-based reasoning.
