#!/usr/bin/env python3
"""
TQSync Web Dashboard 安全检查工具
用于验证部署安全性
"""

import sys
from pathlib import Path
from colorama import init, Fore, Style

# 初始化 colorama
init()

def print_header(text):
    """打印标题"""
    print(f"\n{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{text:^60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")

def print_success(text):
    """打印成功信息"""
    print(f"{Fore.GREEN}✅ {text}{Style.RESET_ALL}")

def print_warning(text):
    """打印警告信息"""
    print(f"{Fore.YELLOW}⚠️  {text}{Style.RESET_ALL}")

def print_error(text):
    """打印错误信息"""
    print(f"{Fore.RED}❌ {text}{Style.RESET_ALL}")

def check_password_file():
    """检查密码文件"""
    print_header("检查密码安全")
    
    password_file = Path(__file__).parent / "admin_password.hash"
    
    if not password_file.exists():
        print_error("管理员密码未设置！")
        print_warning("请运行：python set_admin_password.py")
        return False
    
    # 检查文件权限（仅 Linux/Mac）
    if sys.platform != 'win32':
        import stat
        mode = password_file.stat().st_mode
        
        # 检查是否其他用户可读
        if mode & stat.S_IROTH:
            print_warning("密码文件对其他用户可读，建议修改权限")
            print_warning(f"运行：chmod 600 {password_file}")
        else:
            print_success("密码文件权限设置正确")
    
    # 检查文件大小（应该在合理范围）
    size = password_file.stat().st_size
    if size < 50 or size > 200:
        print_warning(f"密码文件大小异常：{size} bytes")
    else:
        print_success(f"密码文件大小正常：{size} bytes")
    
    return True

def check_secret_key():
    """检查密钥配置"""
    print_header("检查 JWT 密钥")
    
    main_file = Path(__file__).parent / "main.py"
    
    if not main_file.exists():
        print_error("main.py 文件不存在")
        return False
    
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否使用默认密钥
    if 'your-secret-key-change-in-production' in content:
        print_warning("使用默认 SECRET_KEY！")
        print_warning("生产环境必须修改为随机密钥")
        print_warning("建议通过环境变量设置：DASHBOARD_SECRET_KEY")
        return False
    else:
        print_success("SECRET_KEY 已自定义")
        return True

def check_dependencies():
    """检查依赖安装"""
    print_header("检查依赖包")
    
    required_packages = [
        'fastapi',
        'uvicorn',
        'python-jose',
        'passlib',
        'pydantic',
        'aiofiles'
    ]
    
    missing = []
    installed = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            installed.append(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print_error(f"缺少依赖包：{', '.join(missing)}")
        print_warning(f"运行：pip install -r requirements.txt")
        return False
    else:
        print_success(f"所有依赖已安装：{len(installed)} 个包")
        return True

def check_static_files():
    """检查静态文件"""
    print_header("检查前端文件")
    
    static_dir = Path(__file__).parent / "static"
    
    if not static_dir.exists():
        print_error("static 目录不存在")
        return False
    
    index_file = static_dir / "index.html"
    
    if not index_file.exists():
        print_error("index.html 不存在")
        return False
    
    print_success(f"前端文件完整：{index_file.name}")
    
    # 检查文件大小
    size = index_file.stat().st_size
    if size < 1000:
        print_warning(f"index.html 文件过小：{size} bytes")
        return False
    
    print_success(f"文件大小正常：{size/1024:.1f} KB")
    return True

def check_environment():
    """检查环境变量"""
    print_header("检查环境配置")
    
    import os
    
    # 检查是否设置环境变量
    secret_key = os.getenv('DASHBOARD_SECRET_KEY')
    
    if secret_key:
        print_success("已设置 DASHBOARD_SECRET_KEY 环境变量")
    else:
        print_warning("未设置 DASHBOARD_SECRET_KEY 环境变量")
        print_warning("生产环境建议使用环境变量管理密钥")
    
    return True

def run_all_checks():
    """运行所有检查"""
    print_header("TQSync Web Dashboard 安全检查")
    
    checks = [
        ("密码文件", check_password_file),
        ("JWT 密钥", check_secret_key),
        ("依赖包", check_dependencies),
        ("前端文件", check_static_files),
        ("环境变量", check_environment),
    ]
    
    results = []
    
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"检查 {name} 时出错：{e}")
            results.append((name, False))
    
    # 汇总结果
    print_header("检查结果汇总")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        if result:
            print_success(f"{name}: 通过")
        else:
            print_error(f"{name}: 失败")
    
    print(f"\n总计：{passed}/{total} 项通过")
    
    if passed == total:
        print_success("\n🎉 所有检查通过！可以安全运行")
        print_success("\n启动命令：python main.py")
        return True
    else:
        print_error("\n⚠️  存在未通过项，请先修复后再运行")
        return False

if __name__ == "__main__":
    success = run_all_checks()
    sys.exit(0 if success else 1)
