#!/usr/bin/env bash
# TQSync Linux screen 运行管理脚本
# 用法:
#   ./tqsync.sh start    在 screen 后台启动机器人
#   ./tqsync.sh stop     停止机器人
#   ./tqsync.sh restart  重启机器人
#   ./tqsync.sh attach   回到运行日志窗口 (退出用 Ctrl+A D)
#   ./tqsync.sh status   查看运行状态
#   ./tqsync.sh logs     查看最近日志
#   ./tqsync.sh install  执行一键安装

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TQSYNC_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_NAME="${TQSYNC_SCREEN:-tqsync}"
RUNNER="$(dirname "$SCRIPT_DIR")/scripts/tqsync-run.sh"
VENV_DIR="$TQSYNC_DIR/venv"

require_venv() {
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        echo "[TQSync] 未找到虚拟环境 $VENV_DIR，请先运行: bash $SCRIPT_DIR/install.sh"
        return 1
    fi
}

is_running() {
    screen -ls 2>/dev/null | grep -q "\.${SESSION_NAME}[[:space:].]"
}

cmd_start() {
    if is_running; then
        echo "[TQSync] 已在运行 (screen: $SESSION_NAME)，执行 stop/restart 可重新启动"
        return 0
    fi
    require_venv || return 1
    cd "$TQSYNC_DIR" || return 1
    echo "[TQSync] 正在 screen 后台启动..."
    screen -dmS "$SESSION_NAME" bash "$RUNNER"
    sleep 1
    if is_running; then
        echo "[TQSync] 已启动 (screen: $SESSION_NAME)"
        echo "[TQSync] 查看实时日志:   bash $SCRIPT_DIR/tqsync.sh attach"
        echo "[TQSync] 停止:           bash $SCRIPT_DIR/tqsync.sh stop"
    else
        echo "[TQSync] 启动失败，请检查 venv 与依赖是否正常"
        return 1
    fi
}

cmd_stop() {
    if ! is_running; then
        echo "[TQSync] 未在运行"
        return 0
    fi
    echo "[TQSync] 正在停止 (screen: $SESSION_NAME)..."
    screen -S "$SESSION_NAME" -X stuff $'\003'
    for i in $(seq 1 15); do
        is_running || break
        sleep 1
    done
    if is_running; then
        echo "[TQSync] 超时未退出，强制终止..."
        screen -S "$SESSION_NAME" -X quit
    fi
    echo "[TQSync] 已停止"
}

cmd_restart() {
    cmd_stop
    cmd_start
}

cmd_attach() {
    if ! is_running; then
        echo "[TQSync] 未在运行，请先执行: bash $SCRIPT_DIR/tqsync.sh start"
        return 1
    fi
    echo "[TQSync] 已进入运行窗口，按 Ctrl+A 然后按 D 退出 (回到当前终端)"
    echo ""
    screen -r "$SESSION_NAME"
}

cmd_status() {
    if is_running; then
        echo "[TQSync] 状态: 运行中 (screen: $SESSION_NAME)"
        pgrep -af "main.py|$RUNNER" | grep -v "grep\|tqsync.sh" || true
    else
        echo "[TQSync] 状态: 未运行"
    fi
}

cmd_logs() {
    local logfile="$TQSYNC_DIR/logs/tqsync.log"
    if [ -f "$logfile" ]; then
        tail -n "${1:-50}" "$logfile"
    else
        echo "[TQSync] 暂无日志文件: $logfile"
    fi
}

cmd_install() {
    echo "[TQSync] 执行一键安装..."
    bash "$SCRIPT_DIR/install.sh"
}

cmd_help() {
    sed -n '3,11p' "$0" | sed 's/^# *//'
}

cmd="$1"
case "$cmd" in
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    attach)    cmd_attach ;;
    logs)      cmd_logs "$2" ;;
    status)    cmd_status ;;
    install)   cmd_install ;;
    help|--help|-h) cmd_help ;;
    *)         cmd_help ;;
esac
