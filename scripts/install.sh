#!/usr/bin/env bash
# TQSync Linux 一键安装脚本
# 支持 Debian/Ubuntu、CentOS/RHEL、Arch 系发行版
# 用法: bash scripts/install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TQSYNC_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$TQSYNC_DIR/venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

info()  { echo -e "\033[32m[安装]\033[0m $*"; }
warn()  { echo -e "\033[33m[警告]\033[0m $*"; }
error() { echo -e "\033[31m[错误]\033[0m $*"; }

detect_pkgmgr() {
    if command -v apt-get >/dev/null 2>&1; then echo apt; return; fi
    if command -v dnf     >/dev/null 2>&1; then echo dnf; return; fi
    if command -v yum     >/dev/null 2>&1; then echo yum; return; fi
    if command -v pacman  >/dev/null 2>&1; then echo pacman; return; fi
    echo unknown
}

ensure_python() {
    info "检查 Python 3.10+ ..."
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        error "未找到 $PYTHON_BIN，请先安装 Python 3.10+ 后重试。"
        return 1
    fi
    "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
        || { error "Python 版本过低，需要 3.10+，当前: $("$PYTHON_BIN" --version 2>&1)"; return 1; }
    info "Python: $("$PYTHON_BIN" --version 2>&1)"
}

install_system_deps() {
    local pkgmgr="$1"
    local pkgs=()

    if ! command -v ffmpeg >/dev/null 2>&1; then
        case "$pkgmgr" in
            apt)    pkgs+=(ffmpeg) ;;
            dnf|yum) pkgs+=(ffmpeg-free) ;;
            pacman) pkgs+=(ffmpeg) ;;
        esac
    fi
    if ! command -v screen >/dev/null 2>&1; then
        case "$pkgmgr" in
            apt)    pkgs+=(screen) ;;
            dnf|yum) pkgs+=(screen) ;;
            pacman) pkgs+=(screen) ;;
        esac
    fi

    if [ ${#pkgs[@]} -eq 0 ]; then
        info "ffmpeg / screen 已安装，跳过系统依赖安装。"
        return 0
    fi

    if [ "$pkgmgr" = "unknown" ]; then
        warn "未识别到包管理器，请手动安装: ffmpeg screen"
        return 0
    fi

    info "需要安装: ${pkgs[*]}"
    if [ "$(id -u)" -ne 0 ]; then
        warn "将以 sudo 安装，请在弹出的提示中输入密码..."
    fi
    case "$pkgmgr" in
        apt)
            sudo apt-get update
            sudo apt-get install -y "${pkgs[@]}"
            ;;
        dnf)
            sudo dnf install -y "${pkgs[@]}"
            ;;
        yum)
            sudo yum install -y "${pkgs[@]}"
            ;;
        pacman)
            sudo pacman -Sy --noconfirm --needed "${pkgs[@]}"
            ;;
    esac
}

setup_venv() {
    if [ -x "$VENV_DIR/bin/python" ]; then
        info "虚拟环境已存在，跳过创建。"
    else
        info "创建虚拟环境 venv ..."
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
}

install_deps() {
    info "安装项目依赖 (rlottie-python 需编译，耗时较长，请耐心等待)..."
    "$VENV_DIR/bin/pip" install -r "$TQSYNC_DIR/requirements.txt"
}

setup_config() {
    if [ -f "$TQSYNC_DIR/config.yaml" ]; then
        info "config.yaml 已存在，跳过。"
    else
        cp "$TQSYNC_DIR/config.yaml.example" "$TQSYNC_DIR/config.yaml"
        warn "已从模板创建 config.yaml，请编辑填入 Telegram Token、群组 ID 等配置！"
    fi
}

create_dirs() {
    mkdir -p "$TQSYNC_DIR/db" "$TQSYNC_DIR/logs" "$TQSYNC_DIR/temp" "$TQSYNC_DIR/plugins"
    info "目录检查完成 (db/ logs/ temp/ plugins/)"
}

ensure_exec() {
    chmod +x "$SCRIPT_DIR/tqsync.sh" "$SCRIPT_DIR/tqsync-run.sh"
    info "已设置脚本可执行权限。"
}

install_aliases() {
    # 别名文件放在项目根目录，TQSYNC_HOME 通过文件自身位置推导，
    # 项目移动后重新执行 install.sh 即可刷新，避免路径写死。
    local alias_file="$TQSYNC_DIR/.tqsync_aliases"
    cat > "$alias_file" <<'EOF'
# ===== TQSync 快捷命令 (由 scripts/install.sh 生成，修改请谨慎) =====
# 用法示例：
#   tqstart   后台启动机器人 (screen)
#   tqlog     回到运行日志窗口 (退出按 Ctrl+A 再按 D)
#   tqstop    停止机器人
#   tqrestart 重启机器人
#   tqstatus  查看运行状态
#   tqlogs    查看最近日志
export TQSYNC_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
alias tqstart="bash \$TQSYNC_HOME/scripts/tqsync.sh start"
alias tqlog="bash \$TQSYNC_HOME/scripts/tqsync.sh attach"
alias tqstop="bash \$TQSYNC_HOME/scripts/tqsync.sh stop"
alias tqrestart="bash \$TQSYNC_HOME/scripts/tqsync.sh restart"
alias tqstatus="bash \$TQSYNC_HOME/scripts/tqsync.sh status"
alias tqlogs="tail -n 50 \$TQSYNC_HOME/logs/tqsync.log"
EOF

    unalias tqstart tqlog tqstop tqrestart tqstatus tqlogs 2>/dev/null || true
    # shellcheck disable=SC1090
    source "$alias_file"

    local rc
    case "${SHELL:-}" in
        *zsh) rc="$HOME/.zshrc" ;;
        *)    rc="$HOME/.bashrc" ;;
    esac

    if ! grep -qF ".tqsync_aliases" "$rc" 2>/dev/null; then
        printf '\n# TQSync 快捷命令 (tqstart/tqlog/tqstop 等)\ntest -f "%s" && source "%s"\n' "$alias_file" "$alias_file" >> "$rc"
        info "已写入快捷命令到 $rc"
        info "当前终端已立即生效；新终端自动生效，若未生效可执行: source $rc"
    else
        info "快捷命令已配置过，跳过。"
    fi
}

# ---------- 主流程 ----------
echo ""
info "================= TQSync Linux 安装 ================="
ensure_python || exit 1
install_system_deps "$(detect_pkgmgr)"
setup_venv
install_deps
setup_config
create_dirs
ensure_exec
install_aliases
echo ""
info "安装完成！"
info "下一步:"
info "  1. 编辑 $TQSYNC_DIR/config.yaml 填入配置"
info "  2. 启动机器人:  bash $SCRIPT_DIR/tqsync.sh start   (或输入 tqstart)"
info "  3. 回到日志:    bash $SCRIPT_DIR/tqsync.sh attach  (或输入 tqlog，退出按 Ctrl+A D)"
info "  4. 停止机器人:  bash $SCRIPT_DIR/tqsync.sh stop    (或输入 tqstop)"
echo ""
