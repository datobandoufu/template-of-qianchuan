chcp 936 >nul
@echo off
cd /d "%~dp0"
echo ============================================
echo   千川素材监控 - 一键导入（多账户）
echo   将新日报 xlsx 放入任意账户文件夹
echo   本脚本自动扫描全部账户：导入后刷新各账户
echo   Excel 周报(天聚合成周)与网页看板
echo ============================================
echo.
set PYTHONIOENCODING=gbk
set PY=python
where python >nul 2>nul || (echo [错误] 未找到 python，请先安装并加入 PATH & pause & exit /b 1)
"%PY%" monitor\import_daily.py
echo.
echo 导入完成。查看 output\ 下的周报和看板。
pause
