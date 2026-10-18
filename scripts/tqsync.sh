#!/usr/bin/env bash
# TQSync screen 运行管理脚本
# 用法:
#   ./tqsync.sh start             后台启动机器人
#   ./tqsync.sh stop              停止机器人
#   ./tqsync.sh restart           重启机器人
#   ./tqsync.sh attach            进入日志窗口（退出按 Ctrl+A 再按 D）
#   ./tqsync.sh attach -l 200     直接查看最近 200 行
#   ./tqsync.sh attach -c 200     导出最近 200 行到文件（方便 scp）
#   ./tqsync.sh status            查看运行状态
#   ./tqsync.sh logs [n]          查看最近日志（自动解析 JSON 行）
#   ./tqsync.sh install           执行一键安装
#
# 会话说明 (screen):
#   screen 会话名 tqsync，机器人日志直接输出在窗口里
#   翻页: 先按 Ctrl+A 再按 [ ，用 PgUp/PgDn 滚动，q 退出翻页
#   退出会话: 先按 Ctrl+A 再按 D（进程保持后台运行）

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TQSYNC_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_NAME="${TQSYNC_SCREEN:-tqsync}"
RUNNER="$TQSYNC_DIR/scripts/tqsync-run.sh"
VENV_DIR="$TQSYNC_DIR/venv"
LOGFILE="$TQSYNC_DIR/logs/tqsync.log"

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
        echo "[TQSync] 查看日志:  tqlog      (退出按 Ctrl+A D)"
        echo "[TQSync] 查看/导出: tqlog -l 300 直接看；tqlog -c 300 导出到文件"
        echo "[TQSync] 停止:      tqstop"
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
    for _ in $(seq 1 15); do
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
    # tqlog 兼容用法：
    #   tqlog              进入日志窗口
    #   tqlog -l 300       直接打印最近 300 行
    #   tqlog -c 300       导出最近 300 行到文件
    #   tqlog 300 / -300   等同于 -l 300
    local mode="${1:-}"
    local lines="${2:-}"
    case "$mode" in
        -c|--copy)  cmd_copy "${lines:-300}"; return 0 ;;
        -l|--lines) cmd_logs "${lines:-50}"; return 0 ;;
        -h|--help)  cmd_help; return 0 ;;
        -[0-9]*)    cmd_logs "${mode#-}"; return 0 ;;
        [0-9]*)     cmd_logs "$mode"; return 0 ;;
    esac

    if ! is_running; then
        echo "[TQSync] 未在运行，请先执行: bash $SCRIPT_DIR/tqsync.sh start"
        return 1
    fi
    echo "[TQSync] 查看日志窗口：退出按 Ctrl+A 再按 D"
    echo "[TQSync] 回看历史：先按 Ctrl+A 再按 [ ，PgUp/PgDn 滚动，q 退出翻页"
    echo ""
    screen -r "$SESSION_NAME"
}

cmd_status() {
    if is_running; then
        echo "[TQSync] 状态: 运行中 (screen: $SESSION_NAME)"
    else
        echo "[TQSync] 状态: 未运行"
    fi
    pgrep -af "main.py|tqsync-run.sh" | grep -v "grep\|tqsync.sh" || true
}

format_logs() {
    local lines="${1:-50}"
    if [ ! -f "$LOGFILE" ]; then
        echo "[TQSync] 暂无日志文件: $LOGFILE"
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        tail -n "$lines" "$LOGFILE" | python3 -c '
import json, sys
for line in sys.stdin:
    line = line.rstrip("\n")
    try:
        rec = json.loads(line)["record"]
        ts = rec.get("time", {}).get("repr", "")[:19].replace("T", " ")
        level = rec.get("level", {}).get("name", "INFO")
        msg = str(rec.get("message", "")).rstrip("\n")
        print(f"{ts} | {level:<7} | {msg}")
    except Exception:
        print(line)
'
    else
        tail -n "$lines" "$LOGFILE"
    fi
}

cmd_logs() {
    format_logs "${1:-50}"
}

cmd_copy() {
    local lines="${1:-300}"
    if [ ! -f "$LOGFILE" ]; then
        echo "[TQSync] 暂无日志文件: $LOGFILE"
        return 1
    fi
    local out="$TQSYNC_DIR/logs/tqlog-$(date +%Y%m%d-%H%M%S).log"
    format_logs "$lines" > "$out"
    echo "[TQSync] 已导出最近 $lines 行到: $out"
    echo "[TQSync] 下载到本地: scp root@<服务器>:$out ./"
    echo "[TQSync] 也可以直接:  cat $out"
}

cmd_install() {
    echo "[TQSync] 执行一键安装..."
    bash "$SCRIPT_DIR/install.sh"
}

cmd_help() {
    sed -n '3,15p' "$0" | sed 's/^# *//'
}

cmd="${1:-help}"
case "$cmd" in
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    attach)    cmd_attach "${2:-}" "${3:-}" ;;
    logs)      cmd_logs "${2:-50}" ;;
    status)    cmd_status ;;
    install)   cmd_install ;;
    help|--help|-h) cmd_help ;;
    *)         cmd_help ;;
esac
