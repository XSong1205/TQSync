#!/usr/bin/env python3
"""
设置管理员密码（首次启动使用）
"""

import sys
from getpass import getpass
from pathlib import Path
from passlib.hash import argon2

def set_admin_password():
    """设置管理员密码"""
    print("=" * 60)
    print("🔐 TQSync Web Dashboard - 管理员密码设置")
    print("=" * 60)
    
    # 获取密码
    while True:
        password = getpass("请输入管理员密码：")
        if len(password) < 8:
            print("❌ 密码长度至少为 8 位，请重新输入")
            continue
        
        password_confirm = getpass("请再次输入密码确认：")
        if password != password_confirm:
            print("❌ 两次输入的密码不一致，请重新输入")
            continue
        
        break
    
    # 生成哈希
    print("\n⏳ 正在加密存储密码...")
    hashed_password = argon2.hash(password)
    
    # 保存到文件
    password_file = Path(__file__).parent / "admin_password.hash"
    with open(password_file, 'w', encoding='utf-8') as f:
        f.write(hashed_password)
    
    print(f"✅ 密码已安全保存到：{password_file}")
    print("\n💡 提示:")
    print("  • 密码使用 Argon2 算法加密存储")
    print("  • 明文密码不会被保存或传输")
    print("  • 如需修改密码，重新运行此脚本即可")
    print("  • 启动面板：python main.py")
    print("=" * 60)

if __name__ == "__main__":
    set_admin_password()
