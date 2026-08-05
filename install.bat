@echo off
setlocal enabledelayedexpansion
rem =====================================================
rem  TQSync Windows 一键安装/更新脚本
rem  双击运行，或命令行执行: install.bat
rem =====================================================
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ================================================
echo    TQSync Windows 一键安装/更新脚本
echo ================================================

set "VENV_DIR=%~dp0venv"
set "PY=!VENV_DIR!\Scripts\python.exe"

rem ---- 1. 检查 Python ----
echo.
echo [1/5] 检查 Python 环境...
set "FOUND="
py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" 2>nul && set "FOUND=py"
if not defined FOUND (
    python -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" 2>nul && set "FOUND=python"
)
if not defined FOUND (
    echo 错误: 未检测到 Python 3.9+，请先安装并勾选 "Add to PATH"。
    goto :fail
)
if "%FOUND%"=="py" (
    py -3 --version
) else (
    python --version
)

rem ---- 2. 创建虚拟环境 ----
echo.
echo [2/5] 检查虚拟环境...
if not exist "!VENV_DIR!" (
    echo 创建虚拟环境 venv ...
    if "%FOUND%"=="py" (
        py -3 -m venv "!VENV_DIR!"
    ) else (
        python -m venv "!VENV_DIR!"
    )
    if errorlevel 1 goto :fail
) else (
    echo venv 已存在。
)

rem ---- 3. 安装依赖 ----
echo.
echo [3/5] 安装项目依赖...
"!PY!" -m pip install --upgrade pip >nul 2>&1
"!PY!" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :fail

rem ---- 4. 配置文件 ----
echo.
echo [4/5] 检查配置文件...
if not exist "%~dp0config.yaml" (
    if exist "%~dp0config.yaml.example" (
        copy /y "%~dp0config.yaml.example" "%~dp0config.yaml" >nul
        echo 已从模板创建 config.yaml，请务必打开并填入你的 Token 和群组 ID！
    ) else (
        echo 警告: 未找到 config.yaml.example 模板文件。
    )
) else (
    echo config.yaml 已存在。
)

rem ---- 5. 目录检查 ----
echo.
echo [5/5] 检查必要目录...
if not exist "%~dp0db"    mkdir "%~dp0db"
if not exist "%~dp0logs"  mkdir "%~dp0logs"
if not exist "%~dp0temp"  mkdir "%~dp0temp"
echo 目录检查完成。

echo.
echo ================================================
echo 安装完成！
echo 下一步：
echo   1. 编辑 config.yaml 填入配置信息
echo   2. 配置 Napcat 的 Webhook 地址
echo   3. 启动机器人:  !PY! main.py
echo ================================================
echo.
pause
exit /b 0

:fail
echo.
echo 安装失败，请根据上方错误信息排查。
pause
exit /b 1
