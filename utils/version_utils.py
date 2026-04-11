import os
import subprocess

def get_version():
    """从 VERSION 文件中读取版本号"""
    try:
        version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'VERSION')
        with open(version_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return "1.0.0"

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
