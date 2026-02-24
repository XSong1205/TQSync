"""
初始化脚本
用于创建必要的目录和文件
"""

import os
from pathlib import Path

def create_directories():
    """创建必要的目录"""
    directories = [
        'logs',
        'data',
        'temp'
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"创建目录: {directory}")

def create_env_file():
    """创建环境变量文件"""
    env_example = Path('.env.example')
    env_file = Path('.env')
    
    if not env_file.exists() and env_example.exists():
        env_example.rename(env_file)
        print("创建 .env 文件，请编辑填入你的配置")

def create_config_file():
    """创建配置文件"""
    config_template = Path('config.yaml.template')
    config_file = Path('config.yaml')
    
    if not config_file.exists() and config_template.exists():
        config_template.rename(config_file)
        print("创建 config.yaml 文件，请编辑填入你的配置")

def main():
    """主函数"""
    print("正在初始化TQSync项目...")
    
    # 创建目录
    create_directories()
    
    # 创建环境文件
    create_env_file()
    
    # 创建配置文件
    create_config_file()
    
    print("初始化完成！")
    print("\n下一步:")
    print("1. 编辑 .env 和 config.yaml 文件填入你的配置")
    print("2. 确保napcat已正确配置并运行")
    print("3. 运行 python main.py 启动机器人")

if __name__ == "__main__":
    main()