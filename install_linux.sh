#!/bin/bash
# TQSync Linux 安装脚本

set -e  # 遇到错误时退出

echo "========================================="
echo "🐧 TQSync Linux 安装脚本"
echo "========================================="

# 检查 Python 版本
echo "🔍 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.8+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python 版本: $PYTHON_VERSION"

# 检查 pip
echo "🔍 检查 pip..."
if ! command -v pip3 &> /dev/null; then
    echo "❌ 未找到 pip3，正在安装..."
    sudo apt update
    sudo apt install python3-pip -y
fi

# 安装依赖
echo "📦 安装 Python 依赖..."
pip3 install -r requirements.txt

# 创建必要目录
echo "🔧 创建项目目录..."
mkdir -p logs data temp

# 设置执行权限
echo "🔐 设置执行权限..."
chmod +x *.py

# 复制配置文件模板
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ 创建 .env 配置文件，请编辑填入你的配置"
fi

if [ -f "config.yaml.template" ] && [ ! -f "config.yaml" ]; then
    cp config.yaml.template config.yaml
    echo "✅ 创建 config.yaml 配置文件，请编辑填入你的配置"
fi

echo ""
echo "========================================="
echo "🎉 安装完成！"
echo "========================================="
echo ""
echo "下一步:"
echo "1. 编辑 .env 和 config.yaml 文件配置你的机器人信息"
echo "2. 运行 python3 test_database_persistence.py 测试数据库功能"
echo "3. 运行 python3 test.py 测试所有核心功能"
echo "4. 运行 python3 main.py 启动机器人"
echo ""
