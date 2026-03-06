@echo off
chcp 65001 >nul
echo ============================================================
echo 🚀 TQSync Web Dashboard 快速启动脚本
echo ============================================================
echo.

REM 检查密码文件是否存在
if not exist "admin_password.hash" (
    echo ⚠️  检测到首次启动...
    echo.
    echo 请先运行设置管理员密码：
    echo   python set_admin_password.py
    echo.
    pause
    exit /b 1
)

echo ✅ 密码文件已找到
echo.

REM 检查依赖
echo 📦 检查依赖包...
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo ❌ 缺少依赖包，正在安装...
    pip install -r requirements.txt
) else (
    echo ✅ 依赖包已安装
)
echo.

REM 安全检查
echo 🔒 运行安全检查...
python security_check.py
if errorlevel 1 (
    echo.
    echo ⚠️  安全检查未通过，是否继续运行？
    choice /C YN /M "是否继续"
    if errorlevel 2 (
        exit /b 1
    )
)
echo.

REM 启动服务
echo ============================================================
echo 🚀 启动 Web Dashboard...
echo ============================================================
echo.
echo 访问地址：http://localhost:8000
echo 按 Ctrl+C 停止服务
echo.

python main.py

pause
