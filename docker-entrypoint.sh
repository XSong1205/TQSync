#!/bin/sh
set -e

# 确保必要的运行时数据目录存在
mkdir -p /app/db /app/logs /app/temp /app/plugins

# 检查是否由于宿主机未提前创建 config.yaml 而被 Docker 误挂载为了目录
if [ -d "/app/config.yaml" ]; then
    echo "======================================================================"
    echo "❌ 启动失败: /app/config.yaml 是一个目录，而非文件！"
    echo ""
    echo "💡 原因分析:"
    echo "   在宿主机执行 'docker compose up' 前，如果宿主机当前目录下不存在 config.yaml 文件，"
    echo "   Docker 会默认自动将其作为空目录创建并挂载进容器。"
    echo ""
    echo "👉 解决方法 (请在宿主机执行):"
    echo "   1. 停止容器: docker compose down"
    echo "   2. 删除该目录: rm -rf config.yaml"
    echo "   3. 从模板创建配置: cp config.yaml.example config.yaml"
    echo "   4. 编辑 config.yaml 填入真实配置后重新启动: docker compose up -d"
    echo "======================================================================"
    exit 1
fi

# 如果未挂载 config.yaml 且文件不存在，但存在模板文件，则友好提示
if [ ! -f "/app/config.yaml" ]; then
    if [ -f "/app/config.yaml.example" ]; then
        echo "⚠️ 未检测到 /app/config.yaml 配置文件，正在从模板生成..."
        cp /app/config.yaml.example /app/config.yaml
        echo "✅ 已生成初始 config.yaml，请记得映射并修改真实信息。"
    else
        echo "❌ 错误: 未找到 /app/config.yaml 配置文件！"
        exit 1
    fi
fi

# 如果当前以 root 身份运行，则修复挂载目录的所有权并降权至 tqsync 用户运行
if [ "$(id -u)" = "0" ]; then
    chown -R tqsync:tqsync /app/db /app/logs /app/temp /app/plugins 2>/dev/null || true
    exec gosu tqsync "$@"
fi

# 否则直接执行传入的命令
exec "$@"
