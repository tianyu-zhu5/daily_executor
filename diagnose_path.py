#!/usr/bin/env python3
"""
路径诊断工具 - 帮助定位数据库路径问题

Usage:
    python diagnose_path.py
"""

import os
import json
from pathlib import Path

print("=" * 80)
print("数据库路径诊断工具")
print("=" * 80)
print()

# 1. 显示当前工作目录
cwd = os.getcwd()
print(f"1. 当前工作目录 (CWD):")
print(f"   {cwd}")
print()

# 2. 显示脚本所在目录
script_dir = Path(__file__).parent.resolve()
print(f"2. 脚本所在目录:")
print(f"   {script_dir}")
print()

# 3. 加载配置文件
config_path = script_dir / "config.json"
print(f"3. 配置文件:")
print(f"   路径: {config_path}")
print(f"   存在: {config_path.exists()}")

if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    db_path_config = config.get('signal_generation', {}).get('db_path', 'NOT FOUND')
    print(f"   配置的db_path: {db_path_config}")
else:
    print("   ⚠️ 配置文件不存在！")
    db_path_config = None

print()

# 4. 测试相对路径解析
if db_path_config:
    print("4. 相对路径解析测试:")
    db_path = Path(db_path_config)
    print(f"   相对路径: {db_path}")
    print(f"   解析后的绝对路径: {db_path.resolve()}")
    print(f"   文件存在: {db_path.exists()}")
    print()

# 5. 检查可能的目录位置
print("5. 检查可能的CCI目录:")
parent_dir = script_dir.parent
print(f"   父目录: {parent_dir}")

possible_names = ["CCI_Divergence", "CCI-Divergence", "cci_divergence", "cci-divergence"]
found_dirs = []

for name in possible_names:
    check_path = parent_dir / name
    if check_path.exists():
        found_dirs.append(name)
        print(f"   ✓ 找到: {name}")

        # 检查数据目录
        data_dir = check_path / "data"
        if data_dir.exists():
            print(f"     - data/ 目录存在")

            # 检查数据库文件
            db_file = data_dir / "cci_signals.db"
            if db_file.exists():
                size_mb = db_file.stat().st_size / (1024 * 1024)
                print(f"     - cci_signals.db 存在 (大小: {size_mb:.2f} MB)")
            else:
                print(f"     - ⚠️ cci_signals.db 不存在")
        else:
            print(f"     - ⚠️ data/ 目录不存在")
    else:
        print(f"   ✗ 未找到: {name}")

print()

# 6. 给出建议
print("=" * 80)
print("诊断结果和建议:")
print("=" * 80)

if not found_dirs:
    print("❌ 问题: 未找到任何CCI相关目录")
    print()
    print("解决方案:")
    print("1. 确认 CCI_Divergence 项目是否已克隆")
    print("2. 检查目录名是否正确（注意下划线 vs 连字符）")
    print("3. 目录结构应该是:")
    print("   quant/")
    print("   ├── daily_executor/")
    print("   └── CCI_Divergence/")
    print("       └── data/")
    print("           └── cci_signals.db")
elif len(found_dirs) > 1:
    print(f"⚠️ 警告: 找到多个CCI目录: {', '.join(found_dirs)}")
    print()
    print("解决方案:")
    print("1. 删除或重命名多余的目录")
    print("2. 确保配置文件中的路径与实际目录名一致")
else:
    correct_name = found_dirs[0]
    db_file_path = parent_dir / correct_name / "data" / "cci_signals.db"

    if db_file_path.exists():
        print(f"✓ 找到数据库: {correct_name}/data/cci_signals.db")
        print()

        # 检查配置是否匹配
        if db_path_config:
            expected_in_config = f"../{correct_name}/data/cci_signals.db"
            if db_path_config == expected_in_config:
                print("✓ 配置文件路径正确")
                print()
                print("如果仍然报错，可能是CWD问题。建议:")
                print("1. 确保在 daily_executor 目录下运行:")
                print(f"   cd {script_dir}")
                print("2. 然后执行:")
                print("   python daily_executor.py query --date 2025-11-06")
            else:
                print(f"❌ 配置文件路径不匹配")
                print(f"   当前配置: {db_path_config}")
                print(f"   应该是: {expected_in_config}")
                print()
                print("解决方案:")
                print(f"修改 config.json 中的 db_path 为: {expected_in_config}")
    else:
        print(f"❌ 找到目录 {correct_name} 但数据库文件不存在")
        print()
        print("解决方案:")
        print("1. 运行 CCI_Divergence 项目生成数据库")
        print("2. 或者运行 daily_executor 的 step1.5 生成本地数据库:")
        print("   python daily_executor.py run --skip-step1 --skip-step2 --skip-step3")

print()
print("=" * 80)
print("如需更多帮助，请查看 WINDOWS_SETUP.md")
print("=" * 80)
