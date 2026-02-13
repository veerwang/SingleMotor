@echo off
chcp 936 >nul 2>&1
title NiMotion Build Tool

echo ================================================
echo   NiMotion - Build EXE
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 goto :NO_PYTHON

echo [1/4] Python OK
python --version
echo.

:: Check and install PyInstaller
echo [2/4] Checking PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo       Installing PyInstaller...
    pip install pyinstaller
)
if errorlevel 1 goto :DEP_FAIL

:: Install project dependencies
echo.
echo [3/4] Installing dependencies...
pip install pyserial PyQt5
if errorlevel 1 goto :DEP_FAIL

:: Build
echo.
echo [4/4] Building EXE...
echo.

pyinstaller --noconfirm --onefile --windowed --name "NiMotion" --paths src --hidden-import nimotion.ui.theme --hidden-import nimotion.ui.main_window --hidden-import nimotion.ui.motor_tab --hidden-import nimotion.ui.serial_tab --hidden-import nimotion.ui.modbus_tab --hidden-import nimotion.ui.connection_bar --hidden-import nimotion.ui.motor_status --hidden-import nimotion.ui.motor_control --hidden-import nimotion.ui.motor_params --hidden-import nimotion.ui.motor_alarm --hidden-import nimotion.ui.turret_panel --hidden-import nimotion.ui.widgets.hex_input --hidden-import nimotion.ui.widgets.led_indicator --hidden-import nimotion.ui.widgets.log_viewer --hidden-import nimotion.ui.widgets.turret_widget --hidden-import nimotion.communication.worker --hidden-import nimotion.communication.serial_port --hidden-import nimotion.communication.modbus_rtu --hidden-import nimotion.communication.crc16 --hidden-import nimotion.services.motor_service --hidden-import nimotion.models.types --hidden-import nimotion.models.registers --hidden-import nimotion.models.error_codes --hidden-import nimotion.models.turret src\nimotion\main.py

if errorlevel 1 goto :BUILD_FAIL

echo.
echo ================================================
echo   BUILD SUCCESS!
echo   Output: dist\NiMotion.exe
echo ================================================
echo.
explorer dist
pause
exit /b 0

:NO_PYTHON
echo [ERROR] Python not found. Please install Python 3.10+
echo https://www.python.org/downloads/
pause
exit /b 1

:DEP_FAIL
echo [ERROR] Dependency install failed.
pause
exit /b 1

:BUILD_FAIL
echo.
echo [ERROR] Build failed. Check errors above.
pause
exit /b 1
