#!/usr/bin/env python3
"""
一键安装和配置脚本
"""

import os
import sys
import subprocess
from pathlib import Path

def run_command(command, description=""):
    """运行命令并处理错误"""
    if description:
        print(f"🔄 {description}...")
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            capture_output=True, 
            text=True
        )
        if description:
            print(f"✅ {description}完成")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"❌ {description}失败: {e}")
        print(f"错误详情: {e.stderr}")
        return None

def check_python_version():
    """检查Python版本"""
    print("🔍 检查Python环境...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python版本过低，请使用Python 3.8或更高版本")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro} 满足要求")
    return True

def install_dependencies():
    """安装依赖"""
    print("\n📦 安装Python依赖...")
    
    # 尝试使用 requirements.txt
    if Path('requirements.txt').exists():
        print("  使用 requirements.txt 安装依赖...")
        result = run_command("python -m pip install -r requirements.txt", "安装依赖包")
        if result is not None:
            return True
        else:
            print("  requirements.txt 安装失败，尝试逐个安装...")
    
    # 逐个安装依赖（备用方案）
    deps = [
        "python-telegram-bot==21.0.1",
        "aiohttp", 
        "websockets",
        "pyyaml",
        "loguru",
        "python-dotenv",
        "httpx[socks]",
        "aiosqlite",
        "aiofiles"
    ]
    
    success_count = 0
    for dep in deps:
        print(f"  安装 {dep}...")
        result = run_command(f"python -m pip install {dep}", "")
        if result is not None:
            success_count += 1
    
    print(f"\n✅ 成功安装 {success_count}/{len(deps)} 个依赖包")
    return success_count > 0

def setup_project():
    """设置项目"""
    print("\n🔧 初始化项目配置...")
    
    # 创建必要目录
    dirs = ['logs', 'data', 'temp']
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
        print(f"  创建目录: {dir_name}")
    
    # 复制环境文件
    env_example = Path('.env.example')
    env_file = Path('.env')
    
    if env_example.exists() and not env_file.exists():
        env_example.rename(env_file)
        print("  创建 .env 配置文件")
    
    return True

def main():
    """主函数"""
    print("=" * 60)
    print("🚀 Telegram-QQ机器人完整版一键安装脚本")
    print("=" * 60)
    print("✨ 完整功能：数据库持久化、用户绑定、精准撤回、原生回复")
    print("=" * 60)
    
    # 检查Python版本
    if not check_python_version():
        sys.exit(1)
    
    # 安装依赖
    if not install_dependencies():
        print("\n❌ 依赖安装失败，请手动运行:")
        print("   pip install -r requirements.txt")
        sys.exit(1)
    
    # 设置项目
    if not setup_project():
        print("\n❌ 项目初始化失败")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("🎉 安装完成！完整功能已就绪")
    print("=" * 60)
    print("\n完整功能说明:")
    print("• 💾 数据库持久化 - 用户绑定和消息映射永久保存")
    print("• 🔐 用户绑定系统 - 基于验证码的双向平台绑定")
    print("• 🔄 精准撤回同步 - 跨平台消息精确删除")
    print("• 🎯 原生回复支持 - 保持平台原生交互体验")
    print("• 📱 媒体文件同步 - 图片、视频、语音等完整支持")
    print("• 📋 转发消息解析 - 智能解析QQ合并转发")
    print("• ⚡ 消息重试机制 - 自动重试失败消息")
    print("• 🔍 智能过滤系统 - 支持前缀命令和消息过滤")
    print("\n下一步:")
    print("1. 编辑 .env 文件配置你的机器人信息")
    print("2. 运行 python test_database_persistence.py 测试数据库功能")
    print("3. 运行 python test.py 测试所有核心功能")
    print("4. 运行 python main.py 启动机器人")
    print("\n详细使用说明请查看 USAGE.md 文件")
    print("更新日志请查看 CHANGELOG.md 文件")

if __name__ == "__main__":
    main()
