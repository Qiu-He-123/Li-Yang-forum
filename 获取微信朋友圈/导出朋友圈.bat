@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] 抓取图片密钥（微信需运行且打开过图片）
python 获取图片密钥.py
echo.
echo [2/3] 解密并下载朋友圈图片
python 下载朋友圈图片.py
echo.
echo [3/3] 导出朋友圈内容
python 导出朋友圈.py
echo.
echo 完成！结果见 朋友圈导出结果.txt
pause
