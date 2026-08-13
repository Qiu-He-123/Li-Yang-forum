@echo off
chcp 65001 >nul
setlocal
title 一键同步 GitHub
cd /d "%~dp0.."

echo ============================================
echo   一键同步 GitHub
echo   自动：暂存改动 -^> 提交 -^> 推送（带重试）
echo ============================================
echo.

:: 检查是否 git 仓库
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [错误] 当前目录不是 Git 仓库：%CD%
    echo 请把 一键同步.bat 放在仓库的 方便bat 目录下。
    pause
    exit /b 1
)

:: 1) 暂存所有改动（密钥/数据库/上传文件已在 .gitignore 排除）
echo [1/3] 暂存所有改动...
git add -A
echo    完成
echo.

:: 2) 有改动才提交（无改动则跳过）
git status --porcelain | findstr /r "." >nul
if errorlevel 1 (
    echo [2/3] 没有改动，无需提交
) else (
    echo [2/3] 提交改动...
    git commit -m "Auto sync %date% %time%"
    echo    已提交
)
echo.

:: 3) 推送（网络不稳自动重试 12 次）
echo [3/3] 推送到 GitHub（连接不稳会自动重试）...
set "PUSHED="
for /L %%i in (1,1,12) do (
    git push origin main >nul 2>&1
    if not errorlevel 1 (
        set "PUSHED=1"
        goto :pushed
    )
    echo    第 %%i 次失败，8 秒后重试...
    timeout /t 8 /nobreak >nul
)
goto :done
:pushed
echo.
echo ============================================
echo   [完成] 已同步到 GitHub ✓
echo ============================================
goto :end
:done
echo.
echo ============================================
echo   [失败] 12 次重试后仍未推送成功
echo   请确认：1. 网络/VPN 正常  2. GitHub 已登录
echo   然后重新双击本脚本即可
echo ============================================
:end
echo.
pause
