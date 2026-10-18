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

    # Debian / Ubuntu 环境下检查 ensurepip 与 python3-venv
    if [ "$pkgmgr" = "apt" ]; then
        if ! "$PYTHON_BIN" -c 'import ensurepip' >/dev/null 2>&1; then
            local py_ver
            py_ver=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "3")
            pkgs+=(python3-venv "python${py_ver}-venv" python3-pip)
        fi
        if ! dpkg -s build-essential >/dev/null 2>&1; then
            pkgs+=(build-essential)
        fi
    fi

    if [ ${#pkgs[@]} -eq 0 ]; then
        info "系统依赖已就绪，跳过系统依赖安装。"
        return 0
    fi

    if [ "$pkgmgr" = "unknown" ]; then
        warn "未识别到包管理器，请手动安装: ffmpeg screen python3-venv"
        return 0
    fi

    info "需要安装系统依赖: ${pkgs[*]}"
    local SUDO=""
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
            warn "将以 sudo 安装，请在弹出的提示中输入密码..."
        else
            error "当前非 root 用户且未安装 sudo，请切换到 root 或安装 sudo。"
            return 1
        fi
    fi

    case "$pkgmgr" in
        apt)
            $SUDO apt-get update
            $SUDO apt-get install -y "${pkgs[@]}"
            ;;
        dnf)
            $SUDO dnf install -y "${pkgs[@]}"
            ;;
        yum)
            $SUDO yum install -y "${pkgs[@]}"
            ;;
        pacman)
            $SUDO pacman -Sy --noconfirm --needed "${pkgs[@]}"
            ;;
    esac
}

setup_venv() {
    if [ -d "$VENV_DIR" ] && [ ! -x "$VENV_DIR/bin/pip" ]; then
        warn "检测到损坏或未初始化的 venv，正在清理并重新创建..."
        rm -rf "$VENV_DIR"
    fi

    if [ -x "$VENV_DIR/bin/python" ] && [ -x "$VENV_DIR/bin/pip" ]; then
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
    # 1. 尝试在 /usr/local/bin 或 ~/.local/bin 创建全局快捷脚本（无需 source，终端立即生效）
    local bin_dirs=("/usr/local/bin" "$HOME/.local/bin")
    for dir in "${bin_dirs[@]}"; do
        if [ -w "$dir" ] 2>/dev/null || ([ "$(id -u)" -eq 0 ] && mkdir -p "$dir" 2>/dev/null); then
            for cmd in start stop restart status attach logs; do
                local alias_name="tq$cmd"
                [ "$cmd" = "attach" ] && alias_name="tqlog"
                cat > "$dir/$alias_name" <<EOF
#!/usr/bin/env bash
exec bash "$SCRIPT_DIR/tqsync.sh" $cmd "\$@"
EOF
                chmod +x "$dir/$alias_name"
            done
            info "已创建全局快捷命令至 $dir (tqstart/tqlog/tqstop 等立即生效)"
            break
        fi
    done

    # 2. 写入别名文件到项目根目录，作为用户级别名兜底
    local alias_file="$TQSYNC_DIR/.tqsync_aliases"
    cat > "$alias_file" <<'EOF'
# ===== TQSync 快捷命令 (由 scripts/install.sh 生成，修改请谨慎) =====
# 用法示例：
#   tqstart   后台启动机器人 (screen)
#   tqlog     回到日志窗口（退出按 Ctrl+A 再按 D）
#              tqlog -l 300 直接查看最近 300 行；tqlog -c 300 导出到文件
#   tqstop    停止机器人
#   tqrestart 重启机器人
#   tqstatus  查看运行状态
#   tqlogs    查看最近日志（自动解析）
export TQSYNC_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
alias tqstart="bash \$TQSYNC_HOME/scripts/tqsync.sh start"
alias tqlog="bash \$TQSYNC_HOME/scripts/tqsync.sh attach"
alias tqstop="bash \$TQSYNC_HOME/scripts/tqsync.sh stop"
alias tqrestart="bash \$TQSYNC_HOME/scripts/tqsync.sh restart"
alias tqstatus="bash \$TQSYNC_HOME/scripts/tqsync.sh status"
alias tqlogs="bash \$TQSYNC_HOME/scripts/tqsync.sh logs 50"
EOF

    local rc
    case "${SHELL:-}" in
        *zsh) rc="$HOME/.zshrc" ;;
        *)    rc="$HOME/.bashrc" ;;
    esac

    if ! grep -qF ".tqsync_aliases" "$rc" 2>/dev/null; then
        printf '\n# TQSync 快捷命令 (tqstart/tqlog/tqstop 等)\ntest -f "%s" && source "%s"\n' "$alias_file" "$alias_file" >> "$rc"
        info "已写入快捷命令到 $rc"
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
info "  3. 查看日志:    bash $SCRIPT_DIR/tqsync.sh attach  (或输入 tqlog，退出按 Ctrl+A D)"
info "     查看/导出:   tqlog -l 300 直接看；tqlog -c 300 导出到文件"
info "  4. 停止机器人:  bash $SCRIPT_DIR/tqsync.sh stop    (或输入 tqstop)"
echo ""
