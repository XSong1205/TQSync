#!/usr/bin/env bash
# TQSync screen 会话内循环 wrapper
# 由 scripts/tqsync.sh start 在 screen 中调用，配合 main.py 的 screen 感知重启：
#   - main.py 检测到 STY 时写 logs/.restart_marker 后退出 (code 42)
#   - 本脚本检测到 marker 时自动重新拉起，实现进程内 /reboot 与自动更新
#   - 未检测到 marker 则视为异常退出，最多重试 5 次后停止，避免无限循环
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TQSYNC_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$TQSYNC_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
RESTART_MARKER="$TQSYNC_DIR/logs/.restart_marker"

cd "$TQSYNC_DIR" || exit 1

MAX_RESTARTS=5
RESTART_BASE_DELAY=10
STABLE_RUN_THRESHOLD=60
restart_count=0

while :; do
    if [ -f "$RESTART_MARKER" ]; then
        echo ""
        echo "[TQSync-runner] 检测到重启标记，正在重新启动..."
        rm -f "$RESTART_MARKER"
    fi

    loop_start=$(date +%s)
    "$PYTHON" main.py
    code=$?

    if [ -f "$RESTART_MARKER" ]; then
        # 程序主动请求重启 (/reboot /confirm 自动更新等)
        rm -f "$RESTART_MARKER"
        continue
    fi

    if [ "$code" -eq 0 ]; then
        echo "[TQSync-runner] 程序正常退出，停止守护"
        break
    fi

    elapsed=$(( $(date +%s) - loop_start ))
    if [ "$elapsed" -ge "$STABLE_RUN_THRESHOLD" ]; then
        restart_count=0
    fi
    restart_count=$((restart_count + 1))

    if [ "$restart_count" -ge "$MAX_RESTARTS" ]; then
        echo "[TQSync-runner] 已达最大重启次数 $MAX_RESTARTS，停止守护"
        break
    fi

    cooldown=$((RESTART_BASE_DELAY * restart_count))
    echo "[TQSync-runner] 程序异常退出 (code=$code, 运行 ${elapsed}s)，${cooldown}s 后第 $restart_count 次重启"
    sleep "$cooldown"
done

# 会话结束前发送换行，便于 screen 中区分程序结束与提示
echo ""
