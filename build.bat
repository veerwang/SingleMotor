@echo off
chcp 65001 >nul 2>&1
title NiMotion 打包工具

echo ================================================
echo   NiMotion 步进电机调试工具 - 一键打包
echo ================================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 检查 Python 环境...
python --version

:: 检查并安装 PyInstaller
echo.
echo [2/4] 检查 PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo       PyInstaller 未安装，正在安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败
        pause
        exit /b 1
    )
)

:: 检查并安装项目依赖
echo.
echo [3/4] 安装项目依赖...
pip install pyserial PyQt5
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: 执行打包
echo.
echo [4/4] 开始打包...
echo.

pyinstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "NiMotion" ^
    --paths src ^
    --hidden-import nimotion.ui.theme ^
    --hidden-import nimotion.ui.main_window ^
    --hidden-import nimotion.ui.motor_tab ^
    --hidden-import nimotion.ui.serial_tab ^
    --hidden-import nimotion.ui.modbus_tab ^
    --hidden-import nimotion.ui.connection_bar ^
    --hidden-import nimotion.ui.motor_status ^
    --hidden-import nimotion.ui.motor_control ^
    --hidden-import nimotion.ui.motor_params ^
    --hidden-import nimotion.ui.motor_alarm ^
    --hidden-import nimotion.ui.turret_panel ^
    --hidden-import nimotion.ui.widgets.hex_input ^
    --hidden-import nimotion.ui.widgets.led_indicator ^
    --hidden-import nimotion.ui.widgets.log_viewer ^
    --hidden-import nimotion.ui.widgets.turret_widget ^
    --hidden-import nimotion.communication.worker ^
    --hidden-import nimotion.communication.serial_port ^
    --hidden-import nimotion.communication.modbus_rtu ^
    --hidden-import nimotion.communication.crc16 ^
    --hidden-import nimotion.services.motor_service ^
    --hidden-import nimotion.models.types ^
    --hidden-import nimotion.models.registers ^
    --hidden-import nimotion.models.error_codes ^
    --hidden-import nimotion.models.turret ^
    src\nimotion\main.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo ================================================
echo   打包成功!
echo   输出文件: dist\NiMotion.exe
echo ================================================
echo.

:: 打开输出目录
explorer dist

pause
