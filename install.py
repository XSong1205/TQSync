"""TQSync 一键安装/更新脚本 (Windows / Linux / macOS)。

用法:
    python install.py            # 系统 Python
    python install.bat           # Windows: 双击或命令行执行，等价于本脚本
    bash scripts/install.sh      # Linux: 额外安装 ffmpeg/screen 并配置快捷命令
"""
import os
import shutil
import subprocess
import sys

VENV_DIR = os.path.join(os.getcwd(), "venv")

if sys.platform == "win32":
    PY = os.path.join(VENV_DIR, "Scripts", "python.exe")
else:
    PY = os.path.join(VENV_DIR, "bin", "python")


def print_banner():
    print("=" * 50)
    print("   TQSync 一键安装/更新脚本")
    print("=" * 50)


def check_python():
    print("\n[1/5] 检查 Python 环境...")
    try:
        version = subprocess.check_output([sys.executable, "--version"], stderr=subprocess.STDOUT).decode().strip()
        print(f"检测到: {version}")
        return True
    except Exception:
        print("错误: 未检测到 Python。请确保已安装 Python 3.9+ 并添加到系统 PATH。")
        return False


def setup_venv():
    print("\n[2/5] 检查虚拟环境...")
    if not os.path.exists(PY):
        print("创建虚拟环境 venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    else:
        print("venv 已存在。")
    subprocess.check_call([PY, "-m", "pip", "install", "--upgrade", "pip"], stdout=subprocess.DEVNULL)


def install_dependencies():
    print("\n[3/5] 安装项目依赖...")
    try:
        subprocess.check_call([PY, "-m", "pip", "install", "-r", "requirements.txt"])
        print("依赖安装成功！")
    except subprocess.CalledProcessError:
        print("错误: 依赖安装失败。请检查网络连接或手动运行 'venv 对应 pip install -r requirements.txt'")
        return False
    return True


def setup_config():
    print("\n[4/5] 检查配置文件...")
    if not os.path.exists("config.yaml"):
        if os.path.exists("config.yaml.example"):
            shutil.copy("config.yaml.example", "config.yaml")
            print("已从模板创建 config.yaml，请务必打开并填入你的 Token 和群组 ID！")
        else:
            print("警告: 未找到 config.yaml.example 模板文件。")
    else:
        print("config.yaml 已存在。")
    return True


def create_directories():
    print("\n[5/5] 检查必要目录...")
    dirs = ["db", "logs", "temp"]
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d)
            print(f"创建目录: {d}")
    print("目录检查完成。")
    return True


def main():
    print_banner()
    if not check_python():
        sys.exit(1)

    setup_venv()

    if not install_dependencies():
        sys.exit(1)

    setup_config()
    create_directories()

    print("\n" + "=" * 50)
    print("安装完成！")
    print("下一步：")
    print("1. 编辑 config.yaml 填入配置信息")
    print("2. 配置 Napcat 的 Webhook 地址")
    print(f"3. 运行 '{PY} main.py' 启动机器人")
    print("=" * 50)
    if sys.stdin and sys.stdin.isatty():
        input("\n按回车键退出...")
    return 0


if __name__ == "__main__":
    main()
