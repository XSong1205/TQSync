import yaml
import os
from typing import Dict, Any

# 容器环境下 config.yaml 以只读方式挂载，禁止写盘
IS_CONTAINER = os.environ.get('TQSYNC_CONTAINER', '0') == '1'


class ConfigLoader:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

    def get(self, key: str, default=None):
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

    def update_config(self, key: str, value: Any):
        keys = key.split('.')
        current = self.config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
        self.save_config()

    def save_config(self):
        if IS_CONTAINER:
            # 容器内配置只读，跳过写盘（避免 Read-only file system 报错）
            return
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True)

# 全局配置实例
config_loader = ConfigLoader()
