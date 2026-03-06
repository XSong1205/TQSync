#!/usr/bin/env python3
"""
Web Dashboard 安装验证脚本
"""

import sys
from pathlib import Path

def check_installation():
    """检查安装状态"""
    print("=" * 60)
    print("🔍 TQSync Web Dashboard 安装验证")
    print("=" * 60)
    
    # 检查 Python 版本
    print(f"\n✅ Python 版本：{sys.version}")
    
    # 检查必要文件
    required_files = [
        "main.py",
        "set_admin_password.py",
        "security_check.py",
        "requirements.txt",
        "static/index.html"
    ]
    
    print("\n📁 检查文件...")
    for file in required_files:
        if Path(file).exists():
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} (缺失)")
            return False
    
    # 检查依赖
    print("\n📦 检查依赖包...")
    packages = {
        'fastapi': 'FastAPI',
        'uvicorn': 'Uvicorn',
        'passlib': 'Passlib',
        'jose': 'Python-Jose',
        'pydantic': 'Pydantic',
        'aiofiles': 'AIOFiles'
    }
    
    missing = []
    for import_name, display_name in packages.items():
        try:
            __import__(import_name)
            print(f"  ✅ {display_name}")
        except ImportError:
            print(f"  ❌ {display_name}")
            missing.append(display_name)
    
    if missing:
        print(f"\n⚠️  缺少依赖包：{', '.join(missing)}")
        print("请运行：pip install -r requirements.txt")
        return False
    
    print("\n" + "=" * 60)
    print("✅ 安装验证通过！")
    print("=" * 60)
    print("\n下一步:")
    print("1. 首次启动请运行：python set_admin_password.py")
    print("2. 启动面板：python main.py")
    print("3. 访问：http://localhost:8000")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = check_installation()
    sys.exit(0 if success else 1)
