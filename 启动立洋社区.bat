@echo off
chcp 65001 >nul
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title LY 立洋社区（自动安装并启动）

echo ============================================================
echo   LY Community - 首次安装 / 启动（自动装依赖 + 构建 + 启动）
echo ============================================================
echo.

:: 找可用的 Python：优先 py 启动器（可靠、避开微软商店假 python），其次 python，均需验证能跑
py -3 --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未检测到可用的 Python！
        echo 请到 https://www.python.org/downloads/ 下载 3.10+ 版本
        echo 安装时勾选「Add python.exe to PATH」和「py launcher」，然后重新运行本脚本。
        pause
        exit /b 1
    )
    set "PY=python"
) else (
    set "PY=py -3"
)

echo [1/3] 环境自检与自动安装（缺啥补啥，版本低自动升级）...
%PY% "%~dp0backend\scripts\bootstrap.py"
if errorlevel 1 (
    echo.
    echo [错误] 环境自检未通过，请按上方提示处理后重新运行。
    pause
    exit /b 1
)

echo.
echo [2/3] 停止旧服务器进程...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill_old_servers.ps1"
timeout /t 1 /nobreak >nul

echo.
echo [3/3] 启动服务器向导（选账号 / 密钥 / 生产模式）...
"%~dp0backend\.venv\Scripts\python.exe" "%~dp0start_server.py"

echo.
echo 服务器已退出。按任意键关闭窗口。
pause >nul
