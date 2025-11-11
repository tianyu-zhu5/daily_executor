# 数据库路径问题 - 完整解决方案

## 问题描述

```
FileNotFoundError: Database not found: ..\CCI_Divergence\data\cci_signals.db
```

## 根本原因（Gemini深度分析结果）

**核心问题**：代码依赖**当前工作目录 (CWD)**，但运行时的CWD可能不是预期的位置。

相对路径 `../CCI_Divergence/...` 的解析基准不确定，导致路径错误。

---

## 🩺 第一步：运行诊断工具

```bash
cd C:\Users\Administrator\Documents\quant\daily_executor
python diagnose_path.py
```

这个诊断工具会：
1. 显示当前工作目录
2. 显示配置的路径
3. 检查所有可能的CCI目录位置
4. 检查数据库文件是否存在
5. 给出具体的修复建议

---

## 🔧 解决方案（按优先级）

### 方案 1：确认目录名和数据库存在（最常见原因）

**检查步骤**：
```powershell
# 1. 确认目录名（注意下划线！）
Get-ChildItem C:\Users\Administrator\Documents\quant | Where-Object {$_.Name -like "*CCI*"}

# 2. 检查数据库是否存在
Test-Path "C:\Users\Administrator\Documents\quant\CCI_Divergence\data\cci_signals.db"
```

**如果目录名是 `CCI-Divergence`（连字符）而不是 `CCI_Divergence`（下划线）**：

**选项 A - 重命名目录（推荐）**：
```powershell
Rename-Item "C:\Users\Administrator\Documents\quant\CCI-Divergence" -NewName "CCI_Divergence"
```

**选项 B - 修改配置文件**：
编辑 `config.json`，将所有 `CCI_Divergence` 改为 `CCI-Divergence`。

### 方案 2：使用绝对路径（Gemini推荐的最佳实践）

修改 `config.json`，使用绝对路径：

```json
{
  "signal_generation": {
    "db_path": "C:\\Users\\Administrator\\Documents\\quant\\CCI_Divergence\\data\\cci_signals.db",
    "data_dir": "C:\\Users\\Administrator\\Documents\\quant\\CCI_Divergence\\data\\daily",
    "stock_pool_file": "C:\\Users\\Administrator\\Documents\\quant\\CCI_Divergence\\stock_pools\\hs300.txt"
  }
}
```

**优点**：
- ✅ 不依赖当前工作目录
- ✅ 无论从哪里运行都能正常工作
- ✅ 错误信息清晰

**缺点**：
- ❌ 不可移植（换机器需要修改）
- ❌ 路径较长

### 方案 3：使用项目根目录相对路径（最推荐）

这是Gemini建议的**最佳实践**。

#### 步骤 1：修改 daily_executor.py

在加载配置后，添加路径解析逻辑：

```python
# daily_executor.py - 在 _load_config() 方法中
def _load_config(self) -> dict:
    """加载配置文件"""
    try:
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # === 新增：将相对路径转换为绝对路径 ===
        project_root = self.script_dir.parent  # daily_executor的父目录就是项目根目录

        # 处理 signal_generation 路径
        if 'signal_generation' in config:
            sg = config['signal_generation']

            # 处理 db_path
            if 'db_path' in sg and not Path(sg['db_path']).is_absolute():
                sg['db_path'] = str(project_root / sg['db_path'])

            # 处理 data_dir
            if 'data_dir' in sg and not Path(sg['data_dir']).is_absolute():
                sg['data_dir'] = str(project_root / sg['data_dir'])

            # 处理 stock_pool_file
            if 'stock_pool_file' in sg and not Path(sg['stock_pool_file']).is_absolute():
                sg['stock_pool_file'] = str(project_root / sg['stock_pool_file'])

        return config
    except Exception as e:
        print(f"配置文件加载失败: {e}")
        raise
```

#### 步骤 2：修改 config.json（移除 `../`）

```json
{
  "signal_generation": {
    "db_path": "CCI_Divergence/data/cci_signals.db",
    "data_dir": "CCI_Divergence/data/daily",
    "stock_pool_file": "CCI_Divergence/stock_pools/hs300.txt"
  }
}
```

**优点**：
- ✅ 完全不依赖CWD
- ✅ 可移植（整个项目可以移动）
- ✅ 配置文件清晰（无 `../`）
- ✅ 跨平台兼容

### 方案 4：确保运行时在正确目录

如果不想修改代码，确保始终在 `daily_executor` 目录下运行：

```powershell
cd C:\Users\Administrator\Documents\quant\daily_executor
python daily_executor.py query --date 2025-11-06
```

**修改定时任务的"起始于"目录**：
```
起始于: C:\Users\Administrator\Documents\quant\daily_executor
```

---

## 🎯 推荐执行顺序

### 1. 立即诊断（3分钟）

```bash
cd C:\Users\Administrator\Documents\quant\daily_executor
python diagnose_path.py
```

根据诊断结果：
- 如果目录名错误 → 方案 1
- 如果数据库不存在 → 创建数据库
- 如果路径配置错误 → 方案 2 或 方案 3

### 2. 快速修复（5分钟）

**选择方案 2（绝对路径）**：
1. 运行诊断工具获取正确的绝对路径
2. 修改 `config.json`
3. 测试：`python daily_executor.py query --date 2025-11-06`

### 3. 长期解决（15分钟）

**实施方案 3（项目根目录相对路径）**：
1. 修改 `daily_executor.py` 的 `_load_config()` 方法
2. 修改 `config.json` 移除 `../`
3. 测试运行
4. 提交到Git

---

## 📋 验证清单

修复后，运行以下命令验证：

```powershell
# 1. 诊断工具应该显示"✓ 配置文件路径正确"
python diagnose_path.py

# 2. query 命令应该成功
python daily_executor.py query --date 2025-11-06

# 3. 从其他目录运行也应该成功（如果使用了方案2或3）
cd C:\Users\Administrator
python C:\Users\Administrator\Documents\quant\daily_executor\daily_executor.py query --date 2025-11-06
```

---

## 🐛 如果仍然失败

1. **检查数据库文件是否存在**：
   ```powershell
   Get-ChildItem C:\Users\Administrator\Documents\quant\CCI_Divergence\data\
   ```

2. **手动创建数据库**（如果不存在）：
   ```bash
   cd C:\Users\Administrator\Documents\quant\CCI_Divergence
   python scripts/create_database.py  # 或相应的数据库创建脚本
   ```

3. **检查权限**：
   ```powershell
   Get-Acl "C:\Users\Administrator\Documents\quant\CCI_Divergence\data\cci_signals.db"
   ```

4. **使用增强的错误信息**：
   现在 `query_engine.py` 已经增强了错误信息，会显示：
   - 当前工作目录
   - 解析后的绝对路径
   - 父目录中的其他 .db 文件

---

## 📚 参考资料

- **Gemini分析报告**：见上面的对话
- **Windows部署指南**：`WINDOWS_SETUP.md`
- **pathlib文档**：https://docs.python.org/3/library/pathlib.html

---

## ✅ 成功标志

当看到以下输出时，问题解决：

```
================================================================================
历史信号查询
================================================================================
查询条件: 日期: 2025-11-06

📊 查询结果
...
```
