#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
隐私信息清理脚本
自动检测和清理项目中的敏感信息
"""

import os
import re
import shutil
from pathlib import Path

def clean_sensitive_files():
    """清理包含敏感信息的文件"""
    project_root = Path(".")
    
    print("=" * 60)
    print("🔒 隐私信息清理工具")
    print("=" * 60)
    
    # 1. 检查并处理 .env 文件
    env_file = project_root / ".env"
    if env_file.exists():
        print(f"\n⚠️  发现敏感配置文件: {env_file}")
        print("   该文件包含真实的 Telegram Token 和 QQ 群信息")
        
        # 备份原始文件
        backup_file = project_root / ".env.backup"
        shutil.copy2(env_file, backup_file)
        print(f"   ✓ 已备份到: {backup_file}")
        
        # 删除敏感文件
        env_file.unlink()
        print("   ✓ 已删除敏感的 .env 文件")
    
    # 2. 检查 config.yaml 中的敏感信息
    config_file = project_root / "config.yaml"
    if config_file.exists():
        print(f"\n⚠️  检查配置文件: {config_file}")
        
        # 读取文件内容
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检测敏感模式
        sensitive_patterns = [
            (r'token: "([^"]+)"', 'Telegram Token'),
            (r'chat_id: "(-?\d+)"', 'Telegram Chat ID'),
            (r'group_id: "(\d+)"', 'QQ Group ID')
        ]
        
        found_sensitive = False
        for pattern, description in sensitive_patterns:
            matches = re.findall(pattern, content)
            if matches:
                found_sensitive = True
                print(f"   ⚠️  发现 {description}: {matches}")
        
        if found_sensitive:
            # 创建安全的配置模板
            template_content = content
            for pattern, _ in sensitive_patterns:
                template_content = re.sub(pattern, lambda m: pattern.replace(r'([^"]+)', 'your_token_here').replace(r'(-?\d+)', 'your_chat_id_here').replace(r'(\d+)', 'your_group_id_here'), template_content)
            
            template_file = project_root / "config.yaml.template"
            with open(template_file, 'w', encoding='utf-8') as f:
                f.write(template_content)
            
            print(f"   ✓ 已创建安全模板: {template_file}")
            print("   建议：删除原始 config.yaml 文件")
    
    # 3. 检查日志文件
    logs_dir = project_root / "logs"
    if logs_dir.exists():
        log_files = list(logs_dir.glob("*.log"))
        if log_files:
            print(f"\n⚠️  发现日志文件 ({len(log_files)} 个):")
            total_size = 0
            for log_file in log_files:
                size = log_file.stat().st_size
                total_size += size
                print(f"   - {log_file.name} ({size} bytes)")
            
            print(f"   总大小: {total_size} bytes")
            print("   日志文件可能包含敏感信息（Token、消息内容等）")
    
    # 4. 检查测试文件中的假数据
    test_files = list(project_root.glob("test_*.py")) + list(project_root.glob("demo_*.py"))
    fake_user_ids = []
    
    for test_file in test_files:
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 查找可能的假用户ID（纯数字，长度较长）
        user_id_pattern = r"'id': (\d{8,})"
        matches = re.findall(user_id_pattern, content)
        fake_user_ids.extend(matches)
    
    if fake_user_ids:
        print(f"\nℹ️  测试文件中的假用户ID: {set(fake_user_ids)}")
        print("   这些是测试用的假数据，通常不敏感")
    
    print("\n" + "=" * 60)
    print("✅ 隐私清理建议:")
    print("=" * 60)
    print("1. 删除或重命名 .env 文件（已自动处理）")
    print("2. 使用 config.yaml.template 替代 config.yaml")
    print("3. 清理 logs 目录中的日志文件")
    print("4. 检查 .gitignore 确保敏感文件不会被提交")
    print("5. 发布前再次确认没有敏感信息")
    
    return True

def create_secure_gitignore():
    """创建或更新安全的 .gitignore 文件"""
    gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Logs and databases
logs/
data/
temp/
*.db
*.sqlite
*.log

# Environment variables and configs
.env
.env.local
.env.production
config.yaml
*.backup

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Media files
media/
uploads/

# Test files with sensitive data
test_*.py
demo_*.py
*_test.py

# Backup files
*.backup
*.bak
"""

    gitignore_file = Path(".gitignore")
    if gitignore_file.exists():
        print("⚠️  .gitignore 文件已存在，建议检查是否包含所有敏感文件类型")
    else:
        with open(gitignore_file, 'w', encoding='utf-8') as f:
            f.write(gitignore_content)
        print("✓ 已创建安全的 .gitignore 文件")

if __name__ == "__main__":
    try:
        clean_sensitive_files()
        create_secure_gitignore()
        print("\n🎉 隐私信息清理完成！")
        print("\n💡 发布前最后检查清单:")
        print("• 确认没有 .env 文件")
        print("• 确认 config.yaml 已被模板替代") 
        print("• 确认 logs/ 目录已清理")
        print("• 确认 .gitignore 配置正确")
        print("• 运行 git status 检查待提交文件")
    except Exception as e:
        print(f"❌ 清理过程中出现错误: {e}")