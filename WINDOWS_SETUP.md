# Windows 部署指南和兼容性检查

## 系统要求

- Windows 10/11 或 Windows Server 2016+
- Python 3.7+ (推荐 3.9+)
- Anaconda 或 Miniconda
- miniQMT 客户端（用于数据更新）

---

## 兼容性检查清单

### ✅ 已解决的兼容性问题

代码已经针对Windows做了以下优化：

1. **UTF-8 编码支持** ✅
   ```python
   # daily_executor.py:36-43
   if sys.platform == 'win32':
       sys.stdout.reconfigure(encoding='utf-8')
       sys.stderr.reconfigure(encoding='utf-8')
   ```

2. **路径处理** ✅
   - 所有路径使用 `pathlib.Path` 对象，自动处理Windows/Linux路径分隔符
   - 相对路径（`../CCI_Divergence/`）在Windows上正常工作

3. **文件操作编码** ✅
   - 所有文件读写明确指定 `encoding='utf-8'`
   - CSV导出使用 `encoding='utf-8-sig'`（Excel兼容）

4. **subprocess 编码** ✅
   ```python
   # daily_executor.py:135-149
   env['PYTHONIOENCODING'] = 'utf-8'
   env['PYTHONUTF8'] = '1'
   subprocess.run(..., encoding='utf-8', errors='replace')
   ```

### ⚠️ 需要注意的问题

#### 1. Conda 环境激活（重要）

**问题**：
```python
# daily_executor.py:262
command = ['conda', 'run', '-n', 'quant', 'python', script_path.name]
```

**Windows 可能遇到的问题**：
- `conda` 命令可能找不到（PATH 未配置）
- 需要使用 `conda.bat` 或通过完整路径调用

**解决方案 A - 添加 Conda 到 PATH（推荐）**：
1. 打开 Anaconda Prompt（管理员）
2. 运行：
   ```bash
   conda init cmd.exe
   conda init powershell
   ```
3. 重启命令行
4. 验证：`conda --version`

**解决方案 B - 修改代码使用完整路径**：
如果 Conda 安装在 `C:\ProgramData\anaconda3\`：
```python
# 可以在 config.json 中添加：
{
  "conda_path": "C:\\ProgramData\\anaconda3\\Scripts\\conda.exe"
}
```

**解决方案 C - 使用 Anaconda Prompt 运行脚本**：
在 Anaconda Prompt 中运行，自动有 conda 环境。

#### 2. 定时任务设置

**Windows 任务计划程序设置**：

**方法 1 - 使用提供的批处理脚本**：
```bash
# 右键 setup_task.bat，以管理员身份运行
setup_task.bat
```

**方法 2 - 手动创建任务**：
1. 打开"任务计划程序" (Win+R → `taskschd.msc`)
2. 创建基本任务
3. 触发器：每周，周一至周五，16:00
4. 操作：
   - **程序**：`C:\ProgramData\anaconda3\python.exe`
   - **参数**：`daily_executor.py run`
   - **起始于**：`C:\Users\Administrator\Documents\quant\daily_executor`

**重要**：
- 如果使用 Anaconda Prompt，程序应该是 `cmd.exe`
- 参数：`/c "C:\ProgramData\anaconda3\Scripts\activate.bat && python daily_executor.py run"`

#### 3. 路径配置验证

检查 `config.json` 中的路径在 Windows 上是否正确：

```json
{
  "signal_generation": {
    "db_path": "../CCI_Divergence/data/cci_signals.db",  // ✓ 相对路径，Windows自动转换
    "data_dir": "../CCI_Divergence/data/daily",          // ✓
    "stock_pool_file": "../CCI_Divergence/stock_pools/hs300.txt"  // ✓
  }
}
```

**验证方法**：
```python
# 在 Python 中测试
from pathlib import Path
print(Path("../CCI_Divergence/data/cci_signals.db").resolve())
```

---

## 完整部署步骤（Windows）

### 步骤 1: 环境准备

#### 1.1 安装 Anaconda
```bash
# 下载：https://www.anaconda.com/download
# 安装时选择"Add Anaconda to PATH"（可选但推荐）
```

#### 1.2 创建 quant 环境
```bash
conda create -n quant python=3.9
conda activate quant
conda install pandas numpy
pip install xtquant
```

#### 1.3 安装依赖
```bash
cd C:\Users\Administrator\Documents\quant\daily_executor
pip install requests pandas
```

### 步骤 2: 验证目录结构

确保以下目录存在：
```
C:\Users\Administrator\Documents\quant\
├── daily_executor\          # 本项目
│   ├── daily_executor.py
│   ├── query_engine.py
│   ├── signal_types.py
│   ├── formatters.py
│   └── config.json
├── CCI_Divergence\           # CCI项目（注意：下划线，不是连字符）
│   ├── data\
│   │   ├── daily\
│   │   └── cci_signals.db
│   └── stock_pools\
│       └── hs300.txt
└── data\                     # K线数据
    ├── daily\
    └── stock_data_manager.py
```

### 步骤 3: 配置文件检查

#### 3.1 编辑 config.json
```json
{
  "server_sauce": {
    "recipients": [
      {
        "name": "实际姓名",
        "sendkey": "实际的SendKey",
        "enabled": true
      }
    ]
  }
}
```

#### 3.2 验证路径
```bash
# 在 daily_executor 目录下运行
python -c "from pathlib import Path; print(Path('../CCI_Divergence/data/cci_signals.db').resolve())"
```

### 步骤 4: 测试运行

#### 4.1 测试 query 命令（不需要 miniQMT）
```bash
cd C:\Users\Administrator\Documents\quant\daily_executor
python daily_executor.py query --date 2025-09-04
```

如果成功，会显示查询结果。

#### 4.2 测试完整流程（需要 miniQMT）
```bash
# 确保 miniQMT 运行中
python daily_executor.py run --skip-step1 --date 2025-11-10
```

### 步骤 5: 添加数据库索引（推荐）

```bash
cd C:\Users\Administrator\Documents\quant\daily_executor
python add_database_indexes.py ..\CCI_Divergence\data\cci_signals.db
```

**预期输出**：
```
✓ 索引创建成功: idx_divergence_events_end_date
✓ 索引创建成功: idx_divergence_events_expiry_date
...
```

### 步骤 6: 设置定时任务

#### 方法 1 - 使用批处理脚本
```bash
# 右键 setup_task.bat，以管理员身份运行
```

#### 方法 2 - 手动创建
参见上面"定时任务设置"部分。

---

## 常见问题排查（Windows 特定）

### 问题 1: `conda: command not found`

**错误信息**：
```
'conda' 不是内部或外部命令...
```

**解决方法**：
1. 在 Anaconda Prompt 中运行脚本
2. 或添加 Conda 到 PATH：
   ```bash
   # PowerShell（管理员）
   $env:Path += ";C:\ProgramData\anaconda3\Scripts"
   ```

### 问题 2: 编码错误（中文乱码）

**错误信息**：
```
UnicodeDecodeError: 'gbk' codec can't decode...
```

**解决方法**：
代码已经处理了这个问题，但如果仍然出现：
1. 设置系统环境变量：
   ```bash
   # 控制面板 → 系统 → 高级系统设置 → 环境变量
   PYTHONUTF8=1
   PYTHONIOENCODING=utf-8
   ```

2. 或在运行脚本前设置：
   ```bash
   set PYTHONUTF8=1
   python daily_executor.py run
   ```

### 问题 3: 路径不存在

**错误信息**：
```
FileNotFoundError: [WinError 3] 系统找不到指定的路径
```

**排查步骤**：
1. 检查目录结构是否正确
2. 确认 `CCI_Divergence` 目录名（注意下划线）
3. 使用绝对路径测试：
   ```python
   from pathlib import Path
   print(Path("../CCI_Divergence").resolve())
   print(Path("../CCI_Divergence").exists())
   ```

### 问题 4: miniQMT 连接失败

**错误信息**：
```
xtquant 库未找到 或 miniQMT未连接
```

**解决方法**：
1. 确保 miniQMT 客户端运行中
2. 在 quant 环境中安装 xtquant：
   ```bash
   conda activate quant
   pip install xtquant
   ```
3. 测试连接：
   ```python
   import xtquant as xt
   print(xt.get_market_data(['600000.SH'], period='1d', count=1))
   ```

### 问题 5: 定时任务不执行

**排查步骤**：
1. 打开"任务计划程序"
2. 找到 "QuantDailyExecutor" 任务
3. 查看"上次运行结果"（0=成功）
4. 查看"历史记录"标签页
5. 手动运行任务测试

**常见原因**：
- 计算机在16:00关机
- 任务被禁用
- 权限不足
- 路径错误（起始于目录）

---

## 性能优化（Windows）

### 1. 使用 SSD 存储数据库
将 `cci_signals.db` 放在 SSD 上可提升查询速度。

### 2. 添加数据库索引
```bash
python add_database_indexes.py ..\CCI_Divergence\data\cci_signals.db
```

### 3. 调整日志级别
```json
// config.json
{
  "logging": {
    "log_level": "WARNING"  // 减少日志输出
  }
}
```

---

## 验证清单

运行以下命令验证部署：

```bash
# 1. Python 版本
python --version  # 应该 >= 3.7

# 2. Conda 可用
conda --version

# 3. 依赖安装
python -c "import pandas, requests; print('OK')"

# 4. 目录结构
python -c "from pathlib import Path; print(Path('../CCI_Divergence/data/cci_signals.db').exists())"

# 5. 配置文件
python -c "import json; json.load(open('config.json', encoding='utf-8')); print('OK')"

# 6. query 命令
python daily_executor.py query --date 2025-09-04

# 7. 索引状态
python -c "import sqlite3; conn = sqlite3.connect('../CCI_Divergence/data/cci_signals.db'); print(conn.execute(\"SELECT name FROM sqlite_master WHERE type='index'\").fetchall())"
```

全部通过则部署完成！

---

## 技术支持

遇到问题？

1. 查看日志：`logs\executor_*.log`
2. 检查本文档对应章节
3. 验证环境：运行上面的验证清单
4. 测试组件：单独测试每个步骤

---

## 附录：setup_task.bat 内容

```batch
@echo off
echo ========================================
echo 创建 Daily Executor 定时任务
echo ========================================
echo.

REM 获取当前目录
set "CURRENT_DIR=%CD%"

REM Python 路径（根据实际情况修改）
set "PYTHON_PATH=C:\ProgramData\anaconda3\python.exe"

REM 创建任务（每个工作日16:00执行）
schtasks /create ^
  /tn "QuantDailyExecutor" ^
  /tr "\"%PYTHON_PATH%\" \"%CURRENT_DIR%\daily_executor.py\" run" ^
  /sc weekly ^
  /d MON,TUE,WED,THU,FRI ^
  /st 16:00 ^
  /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✓ 任务创建成功！
    echo.
    echo 任务名称: QuantDailyExecutor
    echo 执行时间: 每周一至周五 16:00
    echo 执行命令: "%PYTHON_PATH%" "%CURRENT_DIR%\daily_executor.py" run
    echo.
) else (
    echo.
    echo ✗ 任务创建失败！
    echo 请确保以管理员身份运行此脚本。
    echo.
)

pause
```

保存为 `setup_task.bat`，右键"以管理员身份运行"。
