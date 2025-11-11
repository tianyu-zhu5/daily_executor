@echo off
REM ========================================
REM 自动化推送脚本 - Windows定时任务设置
REM ========================================
REM
REM 功能：创建Windows计划任务，每个工作日16:00执行daily_executor.py
REM
REM 使用方法：
REM   1. 右键以管理员身份运行此脚本
REM   2. 确认创建任务
REM   3. 检查任务是否创建成功
REM
REM Author: Daily Executor System
REM Date: 2025-11-10
REM ========================================

echo.
echo ========================================
echo 自动化推送脚本 - 定时任务设置
echo ========================================
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 需要管理员权限！
    echo 请右键此脚本，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

echo [信息] 管理员权限检查通过
echo.

REM 获取当前目录
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

echo [信息] 脚本目录: %SCRIPT_DIR%
echo.

REM 获取Python路径
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python！请确保Python已安装并添加到PATH
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%i in ('where python') do set PYTHON_PATH=%%i
echo [信息] Python路径: %PYTHON_PATH%
echo.

REM 定义任务参数
set TASK_NAME=QuantDailyExecutor
set SCRIPT_PATH=%SCRIPT_DIR%\daily_executor.py
set LOG_PATH=%SCRIPT_DIR%\logs\task_output.log

REM 检查脚本是否存在
if not exist "%SCRIPT_PATH%" (
    echo [错误] 找不到执行脚本: %SCRIPT_PATH%
    echo.
    pause
    exit /b 1
)

echo [信息] 执行脚本: %SCRIPT_PATH%
echo.

REM 询问用户确认
echo 即将创建以下定时任务：
echo   任务名称: %TASK_NAME%
echo   执行脚本: %SCRIPT_PATH%
echo   执行时间: 每个工作日（周一至周五）16:00
echo   工作目录: %SCRIPT_DIR%
echo.
set /p CONFIRM=是否继续? (Y/N):

if /i not "%CONFIRM%"=="Y" (
    echo 用户取消操作
    echo.
    pause
    exit /b 0
)

echo.
echo [信息] 正在创建定时任务...
echo.

REM 删除已存在的任务（如果有）
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [信息] 检测到已存在的任务，正在删除...
    schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
    echo [信息] 已删除旧任务
    echo.
)

REM 创建新任务
REM 参数说明：
REM   /Create      - 创建任务
REM   /TN          - 任务名称
REM   /TR          - 要运行的程序/命令
REM   /SC          - 计划类型（WEEKLY = 每周）
REM   /D           - 星期几（MON-FRI = 周一至周五）
REM   /ST          - 开始时间（16:00）
REM   /F           - 强制创建（覆盖已存在的任务）
REM   /RL HIGHEST  - 以最高权限运行

schtasks /Create /TN "%TASK_NAME%" /TR "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:00 /F /RL HIGHEST

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo [成功] 定时任务创建成功！
    echo ========================================
    echo.
    echo 任务详情：
    echo   任务名称: %TASK_NAME%
    echo   执行时间: 每个工作日 16:00
    echo.
    echo 你可以通过以下方式管理任务：
    echo   1. 打开"任务计划程序" (taskschd.msc)
    echo   2. 查找任务: %TASK_NAME%
    echo   3. 可以手动运行、禁用或删除任务
    echo.
    echo 立即测试任务：
    schtasks /Run /TN "%TASK_NAME%"
    echo.
    echo [信息] 任务已手动触发，请检查执行结果
    echo.
) else (
    echo.
    echo ========================================
    echo [错误] 定时任务创建失败！
    echo ========================================
    echo.
    echo 错误码: %errorlevel%
    echo.
    echo 可能的原因：
    echo   1. 权限不足（需要管理员权限）
    echo   2. 任务计划程序服务未启动
    echo   3. 命令参数错误
    echo.
)

pause
