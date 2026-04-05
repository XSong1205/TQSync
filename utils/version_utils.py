import subprocess
import os

def get_version():
    """从 VERSION 文件读取版本号"""
    try:
        # 向上查找两层目录到达项目根目录
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version_path = os.path.join(root_dir, 'VERSION')
        with open(version_path, 'r') as f:
            return f.read().strip()
    except Exception:
        return "Unknown"

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
