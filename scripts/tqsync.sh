#!/usr/bin/env bash
# TQSync 运行管理脚本（tmux 优先，自动回退 screen）
# 用法:
#   ./tqsync.sh start       后台启动机器人
#   ./tqsync.sh stop        停止机器人
#   ./tqsync.sh restart     重启机器人
#   ./tqsync.sh attach      进入日志窗口（滚轮可翻历史）
#   ./tqsync.sh shell       进入命令窗口（可实时执行 tqstart/tqstop 等）
#   ./tqsync.sh status      查看运行状态
#   ./tqsync.sh logs [n]    查看最近日志（自动解析 JSON 行）
#   ./tqsync.sh install     执行一键安装
#
# 会话结构 (tmux):
#   tqsync:logs   机器人进程 + 实时日志（鼠标滚轮可回看历史）
#   tqsync:shell  命令窗口，随时执行 tqstatus / tqrestart / tail 等命令
#   快捷键: Ctrl+b 0 / 1 切换窗口，Ctrl+b d 退出（进程保持后台运行）

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TQSYNC_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_NAME="${TQSYNC_SCREEN:-tqsync}"
RUNNER="$TQSYNC_DIR/scripts/tqsync-run.sh"
VENV_DIR="$TQSYNC_DIR/venv"
LOGFILE="$TQSYNC_DIR/logs/tqsync.log"
HISTORY_LIMIT="${TQSYNC_HISTORY:-100000}"

# ---------- 通用 ----------

require_venv() {
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        echo "[TQSync] 未找到虚拟环境 $VENV_DIR，请先运行: bash $SCRIPT_DIR/install.sh"
        return 1
    fi
}

have_tmux() {
    [ "${TQSYNC_USE_SCREEN:-0}" != "1" ] && command -v tmux >/dev/null 2>&1
}

screen_is_running() {
    screen -ls 2>/dev/null | grep -q "\.${SESSION_NAME}[[:space:].]"
}

# ---------- tmux ----------

tmux_session_exists() {
    tmux has-session -t "=$SESSION_NAME" 2>/dev/null
}

tmux_has_logs() {
    tmux list-windows -t "=$SESSION_NAME" -F '#{window_name}' 2>/dev/null | grep -qx 'logs'
}

tmux_apply_options() {
    # 注意：set-option 的 -t 不支持 "=name" 精确匹配写法，这里用普通会话名
    # 滚轮翻历史：mouse on 后滚轮自动进入 copy-mode；q 退出翻页
    tmux set-option -t "$SESSION_NAME" mouse on 2>/dev/null || true
    tmux set-option -t "$SESSION_NAME" history-limit "$HISTORY_LIMIT" 2>/dev/null || true
    tmux set-option -t "$SESSION_NAME" allow-rename off 2>/dev/null || true
    tmux set-option -t "$SESSION_NAME" status-right " 滚轮翻历史 · Ctrl+b 0/1 切换 · Ctrl+b d 退出 " 2>/dev/null || true
    tmux set-option -t "$SESSION_NAME" status-right-length 80 2>/dev/null || true
    tmux set-window-option -t "$SESSION_NAME" automatic-rename off 2>/dev/null || true
    tmux set-window-option -t "$SESSION_NAME" mode-keys vi 2>/dev/null || true
}

tmux_prepare_server() {
    # 服务器未启动时 -g 设置会失败，先确保 server 存在，再放大全局回滚行数
    tmux start-server 2>/dev/null || true
    tmux set-option -g history-limit "$HISTORY_LIMIT" 2>/dev/null || true
}

tmux_spawn_logs() {
    tmux set-option -t "$SESSION_NAME" history-limit "$HISTORY_LIMIT" 2>/dev/null || true
    tmux new-window -t "=$SESSION_NAME" -n logs -c "$TQSYNC_DIR" "bash '$RUNNER'"
    tmux select-window -t "$SESSION_NAME:logs" 2>/dev/null || true
}

tmux_start() {
    if tmux_session_exists; then
        if tmux_has_logs; then
            echo "[TQSync] 已在运行 (tmux: $SESSION_NAME)"
            return 0
        fi
        require_venv || return 1
        tmux_prepare_server
        tmux_apply_options
        tmux_spawn_logs
        sleep 1
        if tmux_has_logs; then
            echo "[TQSync] 已启动 (tmux: $SESSION_NAME:logs)"
            return 0
        fi
        echo "[TQSync] 启动失败，请检查 venv 与依赖是否正常"
        return 1
    fi

    require_venv || return 1
    echo "[TQSync] 正在 tmux 后台启动..."
    tmux_prepare_server
    tmux new-session -d -s "$SESSION_NAME" -n shell -c "$TQSYNC_DIR"
    tmux set-option -t "$SESSION_NAME" history-limit "$HISTORY_LIMIT" 2>/dev/null || true
    tmux_spawn_logs
    tmux_apply_options
    sleep 1
    if tmux_has_logs; then
        echo "[TQSync] 已启动 (tmux: $SESSION_NAME)"
        echo "[TQSync] 查看日志:  tqlog      (滚轮翻历史，Ctrl+b d 退出)"
        echo "[TQSync] 实时命令:  Ctrl+b 1 切到命令窗口，或执行 tqshell"
        echo "[TQSync] 停止:      tqstop"
    else
        echo "[TQSync] 启动失败，请检查 venv 与依赖是否正常"
        return 1
    fi
}

tmux_stop() {
    if ! tmux_has_logs; then
        echo "[TQSync] 未在运行"
        return 0
    fi
    echo "[TQSync] 正在停止 (tmux: $SESSION_NAME)..."
    tmux send-keys -t "=$SESSION_NAME:logs" C-c
    for _ in $(seq 1 15); do
        tmux_has_logs || break
        sleep 1
    done
    if tmux_has_logs; then
        echo "[TQSync] 超时未退出，强制关闭日志窗口..."
        tmux kill-window -t "=$SESSION_NAME:logs" 2>/dev/null || true
    fi
    echo "[TQSync] 已停止 (命令窗口仍可用，执行 tqstart 可重新启动)"
}

# ---------- screen（旧版回退） ----------

screen_start() {
    if screen_is_running; then
        echo "[TQSync] 已在运行 (screen: $SESSION_NAME)"
        return 0
    fi
    require_venv || return 1
    cd "$TQSYNC_DIR" || return 1
    echo "[TQSync] 正在 screen 后台启动..."
    screen -dmS "$SESSION_NAME" bash "$RUNNER"
    sleep 1
    if screen_is_running; then
        echo "[TQSync] 已启动 (screen: $SESSION_NAME)"
        echo "[TQSync] 查看日志: bash $SCRIPT_DIR/tqsync.sh attach"
        echo "[TQSync] 提示: 安装 tmux 后可支持鼠标滚轮翻历史 (apt install tmux)"
    else
        echo "[TQSync] 启动失败，请检查 venv 与依赖是否正常"
        return 1
    fi
}

screen_stop() {
    echo "[TQSync] 正在停止 (screen: $SESSION_NAME)..."
    screen -S "$SESSION_NAME" -X stuff $'\003'
    for _ in $(seq 1 15); do
        screen_is_running || break
        sleep 1
    done
    if screen_is_running; then
        echo "[TQSync] 超时未退出，强制终止..."
        screen -S "$SESSION_NAME" -X quit
    fi
    echo "[TQSync] 已停止"
}

# ---------- 命令 ----------

cmd_start() {
    if screen_is_running; then
        echo "[TQSync] 检测到旧的 screen 会话仍在运行"
        echo "[TQSync] 先执行 tqstop 停止旧会话，再执行 tqstart 即可切换到 tmux（支持滚轮翻历史）"
        return 0
    fi
    if have_tmux; then
        tmux_start
    else
        screen_start
    fi
}

cmd_stop() {
    if screen_is_running; then
        screen_stop
        return 0
    fi
    if have_tmux && tmux_session_exists; then
        tmux_stop
        return 0
    fi
    echo "[TQSync] 未在运行"
}

cmd_restart() {
    cmd_stop
    cmd_start
}

cmd_attach() {
    if screen_is_running; then
        echo "[TQSync] 检测到旧的 screen 会话（不支持鼠标滚轮）"
        echo "[TQSync] 翻页: 先按 Ctrl+A 再按 [ ，用 PgUp/PgDn 滚动，q 退出"
        echo "[TQSync] 退出会话: Ctrl+A 然后按 D"
        echo ""
        screen -r "$SESSION_NAME"
        return
    fi

    if have_tmux && tmux_session_exists; then
        tmux_apply_options
        if tmux_has_logs; then
            tmux select-window -t "=$SESSION_NAME:logs" 2>/dev/null || true
        else
            tmux select-window -t "=$SESSION_NAME:shell" 2>/dev/null || true
            echo "[TQSync] 机器人当前未运行，已进入命令窗口（执行 tqstart 启动）"
        fi
        tmux attach -t "=$SESSION_NAME"
        return
    fi

    echo "[TQSync] 未在运行，请先执行: bash $SCRIPT_DIR/tqsync.sh start"
    return 1
}

cmd_shell() {
    if ! have_tmux || ! tmux_session_exists; then
        echo "[TQSync] 未在运行（或未安装 tmux），请先执行: bash $SCRIPT_DIR/tqsync.sh start"
        return 1
    fi
    tmux_apply_options
    tmux select-window -t "=$SESSION_NAME:shell" 2>/dev/null || true
    if [ -n "${TMUX:-}" ]; then
        # 已在 tmux 内：切窗口即可
        tmux select-window -t "=$SESSION_NAME:shell"
    else
        tmux attach -t "=$SESSION_NAME:shell"
    fi
}

cmd_status() {
    local running=0
    if screen_is_running; then
        echo "[TQSync] 状态: 运行中 (screen: $SESSION_NAME)"
        running=1
    elif have_tmux && tmux_has_logs; then
        echo "[TQSync] 状态: 运行中 (tmux: $SESSION_NAME:logs)"
        tmux list-windows -t "=$SESSION_NAME" -F '  - #{window_index}:#{window_name} (#{pane_current_command})' 2>/dev/null
        running=1
    elif have_tmux && tmux_session_exists; then
        echo "[TQSync] 状态: 已停止 (tmux 会话仍保留命令窗口)"
    else
        echo "[TQSync] 状态: 未运行"
    fi
    pgrep -af "main.py|tqsync-run.sh" | grep -v "grep\|tqsync.sh" || true
    [ "$running" = "1" ] && return 0
}

cmd_logs() {
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
    attach)    cmd_attach ;;
    shell)     cmd_shell ;;
    logs)      cmd_logs "${2:-50}" ;;
    status)    cmd_status ;;
    install)   cmd_install ;;
    help|--help|-h) cmd_help ;;
    *)         cmd_help ;;
esac
