#!/usr/bin/env bash
# TQSync 运行管理脚本（tmux 优先，自动回退 screen）
# 用法:
#   ./tqsync.sh start             后台启动机器人
#   ./tqsync.sh stop              停止机器人
#   ./tqsync.sh restart           重启机器人
#   ./tqsync.sh attach            进入日志窗口（滚轮可翻历史）
#   ./tqsync.sh attach -l 200     直接查看最近 200 行
#   ./tqsync.sh attach -c 200     导出最近 200 行到文件（方便 scp）
#   ./tqsync.sh console           命令控制台（输入 start/stop/status 等）
#   ./tqsync.sh shell             打开一个普通 bash 窗口
#   ./tqsync.sh status            查看运行状态
#   ./tqsync.sh logs [n]          查看最近日志（自动解析 JSON 行）
#   ./tqsync.sh install           执行一键安装
#
# 会话结构 (tmux):
#   tqsync:cmd    命令控制台（start/stop/restart/status/logs/copy/help）
#   tqsync:logs   机器人进程 + 实时日志（鼠标滚轮可回看历史）
#   快捷键: Ctrl+b 0 命令 / 1 日志，Ctrl+b d 退出（进程保持后台运行）
#   复制日志: Ctrl+b m 关闭鼠标捕获后可直接框选/右键；或按住 Shift 拖动临时绕过

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TQSYNC_DIR="$(dirname "$SCRIPT_DIR")"
SELF="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
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
    tmux set-option -t "$SESSION_NAME" status-right " Ctrl+b 0 命令 · 1 日志 · m 鼠标捕获 · d 退出 " 2>/dev/null || true
    tmux set-option -t "$SESSION_NAME" status-right-length 96 2>/dev/null || true
    tmux set-window-option -t "$SESSION_NAME" automatic-rename off 2>/dev/null || true
    tmux set-window-option -t "$SESSION_NAME" mode-keys vi 2>/dev/null || true

    # 复制支持：
    #   1) Ctrl+b m 切换鼠标捕获 —— 关闭后可直接用终端原生框选 / 右键复制（滚轮也交还终端）
    #   2) 临时框选：按住 Shift 拖动可绕过 tmux 鼠标捕获，使用终端自身的复制
    #   3) set-clipboard on：tmux 内的复制通过 OSC52 写入本地剪贴板（Windows Terminal 等支持）
    tmux set-option -g set-clipboard on 2>/dev/null || true
    tmux bind-key m set-option mouse \; display-message "鼠标捕获: 关闭后可用原生框选/右键复制，开启后滚轮翻历史" 2>/dev/null || true
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

# 旧版本会话里窗口名是 shell，这里统一升级成 cmd（TQSync 命令控制台）
tmux_ensure_console() {
    local names
    names=$(tmux list-windows -t "=$SESSION_NAME" -F '#{window_name}' 2>/dev/null || true)
    if printf '%s\n' "$names" | grep -qx 'cmd'; then
        return 0
    fi
    if printf '%s\n' "$names" | grep -qx 'shell'; then
        tmux respawn-window -k -t "$SESSION_NAME:shell" -c "$TQSYNC_DIR" "bash '$SELF' console" 2>/dev/null \
            && tmux rename-window -t "$SESSION_NAME:shell" cmd 2>/dev/null \
            && return 0
    fi
    tmux new-window -t "=$SESSION_NAME" -n cmd -c "$TQSYNC_DIR" "bash '$SELF' console"
}

tmux_start() {
    if tmux_session_exists; then
        if tmux_has_logs; then
            echo "[TQSync] 已在运行 (tmux: $SESSION_NAME)"
            tmux_ensure_console
            return 0
        fi
        require_venv || return 1
        tmux_prepare_server
        tmux_ensure_console
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
    tmux new-session -d -s "$SESSION_NAME" -n cmd -c "$TQSYNC_DIR" "bash '$SELF' console"
    tmux set-option -t "$SESSION_NAME" history-limit "$HISTORY_LIMIT" 2>/dev/null || true
    tmux_spawn_logs
    tmux_apply_options
    sleep 1
    if tmux_has_logs; then
        echo "[TQSync] 已启动 (tmux: $SESSION_NAME)"
        echo "[TQSync] 查看日志:  tqlog          (滚轮翻历史，Ctrl+b d 退出)"
        echo "[TQSync] 实时命令:  Ctrl+b 0 进入命令控制台，直接输入 start/stop/status 等"
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
    # tqlog 兼容用法：
    #   tqlog              进入日志窗口
    #   tqlog -l 300       直接打印最近 300 行
    #   tqlog -c 300       导出最近 300 行到文件（原 tqcopy）
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
            tmux select-window -t "=$SESSION_NAME:cmd" 2>/dev/null || true
            echo "[TQSync] 机器人当前未运行，已进入命令控制台（输入 start 启动）"
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
    if ! tmux list-windows -t "=$SESSION_NAME" -F '#{window_name}' 2>/dev/null | grep -qx 'shell'; then
        tmux new-window -t "=$SESSION_NAME" -n shell -c "$TQSYNC_DIR"
    fi
    if [ -n "${TMUX:-}" ]; then
        # 已在 tmux 内：切窗口即可
        tmux select-window -t "=$SESSION_NAME:shell"
    else
        tmux attach -t "=$SESSION_NAME:shell"
    fi
}

# ---------- 命令控制台 ----------

console_help() {
    cat <<'EOF'
可用命令:
  start          启动机器人
  stop           停止机器人
  restart        重启机器人
  status         查看运行状态
  logs [n]       查看最近 n 行日志（默认 50）
  copy [n]       导出最近 n 行日志到文件（默认 300）
  attach         跳到日志窗口
  shell          打开一个普通 bash 窗口
  clear          清屏
  help           显示本帮助
  exit           退出控制台（机器人继续后台运行）
EOF
}

cmd_console() {
    # 控制台里 Ctrl+C 不应该把窗口关掉
    trap '' INT
    echo "TQSync 命令控制台 —— 输入 help 查看命令，exit 退出（机器人不受影响）"
    echo
    while :; do
        printf 'tqsync> '
        if ! IFS= read -r line; then
            echo
            break
        fi
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [ -z "$line" ] && continue

        cmd="${line%% *}"
        if [ "$cmd" = "$line" ]; then arg=""; else arg="${line#* }"; fi

        case "$cmd" in
            start)       cmd_start ;;
            stop)        cmd_stop ;;
            restart)     cmd_restart ;;
            status)      cmd_status ;;
            logs)        cmd_logs "${arg:-50}" ;;
            copy)        cmd_copy "${arg:-300}" ;;
            attach)      tmux select-window -t "$SESSION_NAME:logs" 2>/dev/null || echo "[TQSync] 机器人未运行，暂无日志窗口" ;;
            shell)       cmd_shell ;;
            clear|cls)   clear ;;
            help|h|\?)   console_help ;;
            exit|quit|q) break ;;
            *)           echo "未知命令: $cmd（输入 help 查看可用命令）" ;;
        esac
        echo
    done
    echo "[TQSync] 控制台已退出；机器人仍在后台运行（Ctrl+b 1 可回到日志窗口）"
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

# 把最近日志导出成纯文本文件，方便 scp 下来 / 在编辑器里复制
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

# 对已存在的 tmux 会话重新应用鼠标/复制/状态栏设置
cmd_apply() {
    if have_tmux && tmux_session_exists; then
        tmux_apply_options
        echo "[TQSync] 已刷新 tmux 选项 (mouse on / set-clipboard on / Ctrl+b m 切换鼠标)"
        return 0
    fi
    echo "[TQSync] 没有正在运行的 tmux 会话"
    return 1
}

cmd_install() {
    echo "[TQSync] 执行一键安装..."
    bash "$SCRIPT_DIR/install.sh"
}

cmd_help() {
    sed -n '3,14p' "$0" | sed 's/^# *//'
}

cmd="${1:-help}"
case "$cmd" in
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    attach)    cmd_attach "${2:-}" "${3:-}" ;;
    shell)     cmd_shell ;;
    console)   cmd_console ;;
    logs)      cmd_logs "${2:-50}" ;;
    apply)     cmd_apply ;;
    status)    cmd_status ;;
    install)   cmd_install ;;
    help|--help|-h) cmd_help ;;
    *)         cmd_help ;;
esac
