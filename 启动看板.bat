chcp 936 >nul
@echo off
cd /d "%~dp0"
set PORT=8931

rem ===== 数据检查：看板目录必须已生成，否则是空服务/误连到别的项目 =====
if not exist "%~dp0output\dashboard\index.html" (
    echo [错误] 当前项目尚未生成看板数据。
    echo        请先运行 一键导入.bat（或 python monitor\import_daily.py）
    echo        将日报 xlsx 放入账户文件夹后导入，生成 output\dashboard\index.html 后再启动本脚本。
    echo.
    pause
    exit /b 1
)

rem ===== 端口检查：被占用则提示，避免打开的是其他项目的服务 =====
set PORT_BUSY=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do set PORT_BUSY=1
if defined PORT_BUSY (
    echo [错误] 端口 %PORT% 已被其他程序占用（可能已有真实项目在看板服务）。
    echo        当前项目应使用独立端口，请修改本脚本与 monitor\dashboard_app.py 中的 PORT 后重试。
    echo.
    pause
    exit /b 1
)

set APP=千川素材监控看板.exe
if exist "%APP%" (
    echo 启动桌面应用（系统托盘运行，无命令行窗口）...
    echo 服务地址 http://127.0.0.1:%PORT%
    echo 如需停止：右键托盘图标 - 退出
    start "" "%APP%"
    exit /b
)

echo 未找到 %APP%，使用 Python 方式启动（旧模式）...
set PYTHONIOENCODING=gbk
set PY=python
where python >nul 2>nul || (echo [错误] 未找到 python，请先安装并加入 PATH & pause & exit /b 1)
echo 千川素材监控看板 - 正在启动服务...
start "看板服务" /min "%PY%" -m http.server %PORT% --directory "%~dp0output\dashboard"
powershell -NoProfile -Command "$c=New-Object System.Net.Sockets.TcpClient; $ok=$false; for($i=0;$i -lt 30;$i++){ try{ $c.Connect('127.0.0.1',%PORT%); $ok=$true; break } catch { Start-Sleep -Milliseconds 500 } }; if($ok){ Start-Process ('http://127.0.0.1:%PORT%'); Write-Host '看板已打开' } else { Write-Host '启动失败：端口无法访问，请检查是否有程序占用' }"
echo.
echo 服务运行于 http://127.0.0.1:%PORT% ，关闭"看板服务"最小化窗口即停止。
pause
