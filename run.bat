@echo off
chcp 65001 >nul 2>&1
title NiMotion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"

rem 清除代理，防止 pip 解析失败
set "http_proxy="
set "https_proxy="
set "HTTP_PROXY="
set "HTTPS_PROXY="

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo 虚拟环境不存在，正在创建...
    python -m venv "%VENV_DIR%"
    call "%VENV_DIR%\Scripts\activate.bat"
    pip install -e "%SCRIPT_DIR%"
) else (
    call "%VENV_DIR%\Scripts\activate.bat"
)

python -m nimotion.main %*
