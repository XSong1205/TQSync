#!/bin/bash

# TQSync Web Dashboard Linux 启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "🚀 TQSync Web Dashboard"
echo "============================================================"
echo ""

# 检查密码文件
if [ ! -f "admin_password.hash" ]; then
    echo "⚠️  检测到首次启动..."
    echo ""
    echo "请先运行设置管理员密码："
    echo "  python3 set_admin_password.py"
    echo ""
    exit 1
fi

echo "✅ 密码文件已找到"
echo ""

# 检查依赖
echo "📦 检查依赖包..."
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "❌ 缺少依赖包，正在安装..."
    pip3 install -r requirements.txt
else
    echo "✅ 依赖包已安装"
fi
echo ""

# 安全检查
echo "🔒 运行安全检查..."
python3 security_check.py
if [ $? -ne 0 ]; then
    echo ""
    echo "⚠️  安全检查未通过，是否继续运行？"
    read -p "是否继续 (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# 启动服务
echo "============================================================"
echo "🚀 启动 Web Dashboard..."
echo "============================================================"
echo ""
echo "访问地址：http://localhost:8000"
echo "按 Ctrl+C 停止服务"
echo ""

python3 main.py
