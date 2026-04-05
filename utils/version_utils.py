import subprocess
import os

def get_version():
    """通过 Git 提交次数动态计算版本号"""
    try:
        # 获取总提交次数
        count_result = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD'],
            capture_output=True, text=True, check=True
        )
        n = int(count_result.stdout.strip())
        
        # 映射为语义化版本: 0.{N // 10}.{N % 10}
        major = 0
        minor = n // 10
        patch = n % 10
        return f"{major}.{minor}.{patch}"
    except Exception:
        return "0.0.0"

def get_git_commit_hash(short=True):
    """获取 Git Commit Hash"""
    try:
        cmd = ['git', 'rev-parse', '--short', 'HEAD'] if short else ['git', 'rev-parse', 'HEAD']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return "Unknown"

def get_full_version_string():
    """获取完整的版本标识字符串，例如: v0.4.3 (a1b2c3d)"""
    version = get_version()
    commit_hash = get_git_commit_hash()
    return f"v{version} ({commit_hash})"
