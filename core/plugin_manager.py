"""插件管理器 - 负责插件的加载、卸载、热重载和消息路由"""

import os
import sys
import time
import importlib.util
import re
from dataclasses import dataclass, field
from typing import Optional

from core.plugin_base import PluginBase, PluginContext
from utils.logger import logger


@dataclass
class PluginInfo:
    """插件信息"""
    name: str
    version: str
    description: str
    author: str
    file: str
    enabled: bool = True
    loaded: bool = False
    load_time_ms: float = 0.0
    instance: Optional[object] = None
    error: Optional[str] = None
    matchers: list = field(default_factory=list)


class PluginManager:
    """插件管理器单例"""
    _instance = None

    def __init__(self):
        self.plugins: dict[str, PluginInfo] = {}
        self._matchers: list = []  # list of (matcher_dict, plugin_name)
        self._ctx: Optional[PluginContext] = None
        self.plugin_dir = os.path.join(os.getcwd(), 'plugins')

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_context(self, ctx: PluginContext):
        self._ctx = ctx

    def discover_plugins(self) -> list:
        """扫描插件目录，返回所有插件文件名列表"""
        if not os.path.exists(self.plugin_dir):
            os.makedirs(self.plugin_dir, exist_ok=True)
            return []

        plugin_files = []
        for f in os.listdir(self.plugin_dir):
            if f.endswith('.py') and not f.startswith('_'):
                plugin_files.append(f)
        return sorted(plugin_files)

    async def load_plugin(self, filename: str) -> Optional[PluginInfo]:
        """加载单个插件

        Args:
            filename: 插件文件名 (例如 'ThumbsUp.py')

        Returns:
            PluginInfo 或 None (加载失败时)
        """
        name = filename[:-3]  # 去除 .py 后缀
        filepath = os.path.join(self.plugin_dir, filename)

        if not os.path.exists(filepath):
            logger.error(f"插件文件不存在: {filepath}")
            return None

        # 如果已加载，先卸载
        if name in self.plugins:
            await self.unload_plugin(name)

        t0 = time.time()

        try:
            spec = importlib.util.spec_from_file_location(f"plugins.{name}", filepath)
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"plugins.{name}"] = module
            spec.loader.exec_module(module)

            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase:
                    plugin_class = attr
                    break

            if plugin_class is None:
                raise ValueError(f"在 {filename} 中未找到继承自 PluginBase 的类")

            instance = plugin_class(ctx=self._ctx)
            await instance.on_load()

            elapsed_ms = int((time.time() - t0) * 1000)

            info = PluginInfo(
                name=name,
                version=getattr(instance, 'version', '0.1'),
                description=getattr(instance, 'description', ''),
                author=getattr(instance, 'author', ''),
                file=filename,
                enabled=True,
                loaded=True,
                load_time_ms=elapsed_ms,
                instance=instance,
                error=None,
                matchers=instance.get_matchers()
            )

            self.plugins[name] = info
            self._rebuild_matchers()

            logger.info(f"✅ 插件已加载: {name} (耗时 {elapsed_ms}ms)")
            return info

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ 插件加载失败 {filename}: {error_msg}")
            self.plugins[name] = PluginInfo(
                name=name,
                version='-',
                description='',
                author='',
                file=filename,
                enabled=False,
                loaded=False,
                load_time_ms=0,
                instance=None,
                error=error_msg
            )
            return None

    async def unload_plugin(self, name: str) -> None:
        """卸载插件"""
        if name not in self.plugins:
            return

        info = self.plugins[name]
        if info.instance:
            try:
                await info.instance.on_unload()
            except Exception as e:
                logger.warning(f"插件 {name} on_unload 异常: {e}")

        mod_name = f"plugins.{name}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        del self.plugins[name]
        self._rebuild_matchers()

        logger.info(f"🗑 插件已卸载: {name}")

    async def reload_plugin(self, name: str) -> Optional[PluginInfo]:
        """热重载插件（卸载后重新加载）"""
        if name not in self.plugins:
            return None

        filename = self.plugins[name].file
        await self.unload_plugin(name)
        return await self.load_plugin(filename)

    def enable_plugin(self, name: str) -> None:
        """启用插件"""
        if name in self.plugins:
            self.plugins[name].enabled = True
            self._rebuild_matchers()
            logger.info(f"▶ 插件已启用: {name}")

    def disable_plugin(self, name: str) -> None:
        """禁用插件"""
        if name in self.plugins:
            self.plugins[name].enabled = False
            self._rebuild_matchers()
            logger.info(f"⏸ 插件已禁用: {name}")

    async def delete_plugin(self, name: str) -> None:
        """删除插件文件并卸载"""
        if name not in self.plugins:
            return

        filepath = os.path.join(self.plugin_dir, self.plugins[name].file)
        await self.unload_plugin(name)
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"🗑 插件文件已删除: {name}")

    def _rebuild_matchers(self) -> None:
        """从已启用的插件重建匹配器列表"""
        self._matchers = []
        for name, info in self.plugins.items():
            if info.enabled and info.loaded and info.matchers:
                for m in info.matchers:
                    self._matchers.append((m, name))

    async def route_message(self, platform: str, user_id: int, group_id: int, message: str) -> bool:
        """将文本消息路由到匹配的插件

        Returns:
            True 表示消息已被插件拦截处理
            False 表示没有插件处理，应走正常转发流程
        """
        if not message:
            return False

        for matcher, plugin_name in self._matchers:
            info = self.plugins.get(plugin_name)
            if not info or not info.instance:
                continue

            mtype = matcher.get('type', 'exact')
            pattern = matcher.get('pattern', '')

            matched = False
            if mtype == 'exact' and message == pattern:
                matched = True
            elif mtype == 'prefix' and message.startswith(pattern):
                matched = True
            elif mtype == 'regex':
                try:
                    if re.search(pattern, message):
                        matched = True
                except re.error as e:
                    logger.warning(f"插件 {plugin_name} 正则表达式错误: {pattern} - {e}")
                    continue

            if not matched:
                continue

            try:
                await info.instance.on_message(platform, user_id, group_id, message)
                logger.debug(f"插件 {plugin_name} 拦截了消息: {message[:50]}")
                return True
            except Exception as e:
                logger.error(f"插件 {plugin_name} on_message 异常: {e}")
                return True

        return False

    def get_plugins_status(self) -> list:
        """获取所有插件状态列表"""
        result = []
        for name, info in self.plugins.items():
            result.append({
                "name": info.name,
                "version": info.version,
                "description": info.description,
                "author": info.author,
                "file": info.file,
                "enabled": info.enabled,
                "loaded": info.loaded,
                "load_time_ms": info.load_time_ms,
                "error": info.error,
                "matchers": info.matchers
            })
        return result

    async def load_all(self) -> list:
        """加载所有已发现的插件"""
        files = self.discover_plugins()
        results = []
        for f in files:
            info = await self.load_plugin(f)
            results.append(info)
        return results

    async def broadcast_plugin_status(self, name: str, success: bool, elapsed_ms: int, error: str = None) -> None:
        """向双端广播插件加载状态通知"""
        if not self._ctx:
            return

        filename = self.plugins[name].file if name in self.plugins else f"{name}.py"

        if success:
            msg = f"{filename} 插件已加载({elapsed_ms} ms)"
        else:
            msg = f"{filename} 插件加载失败: {error}"

        try:
            await self._ctx.tg_bot.send_message(
                chat_id=self._ctx.tg_group_id,
                text=msg
            )
        except Exception as e:
            logger.warning(f"发送插件状态通知到 TG 失败: {e}")

        try:
            await self._ctx.qq_client.send_group_msg(
                self._ctx.qq_group_id,
                msg
            )
        except Exception as e:
            logger.warning(f"发送插件状态通知到 QQ 失败: {e}")
