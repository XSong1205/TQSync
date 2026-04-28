# TQSync 插件开发规范

## 目录

1. [概述](#概述)
2. [快速开始](#快速开始)
3. [插件文件结构](#插件文件结构)
4. [PluginBase API](#pluginbase-api)
5. [PluginContext 上下文](#plugincontext-上下文)
6. [消息匹配器](#消息匹配器)
7. [消息处理流程](#消息处理流程)
8. [平台通信](#平台通信)
9. [生命周期](#生命周期)
10. [错误处理](#错误处理)
11. [Admin API 管理接口](#admin-api-管理接口)
12. [完整示例](#完整示例)
13. [最佳实践](#最佳实践)

---

## 概述

TQSync 插件系统允许开发者在不修改主程序的前提下，扩展 Telegeram↔QQ 双端群组的消息处理能力。

### 核心特性

- **热插拔**：支持运行时加载、卸载、启用、禁用，无需重启主程序
- **双端通信**：插件可通过统一 API 向 Telegram 和 QQ 两个平台发送消息
- **灵活匹配**：支持精确匹配、前缀匹配、正则匹配三种文本匹配模式
- **插件隔离**：单个插件崩溃不会影响主程序和其他插件运行
- **Admin API**：所有插件管理操作通过 REST API 完成，支持 WebUI 和外部工具调用

### 插件目录

所有插件文件存放在 `plugins/` 目录下，文件名即插件名（除去 `.py` 后缀）：

```
plugins/
├── ThumbsUp.py      # 插件名: ThumbsUp
├── Weather.py       # 插件名: Weather
└── MyPlugin.py      # 插件名: MyPlugin
```

---

## 快速开始

创建一个最小可运行的插件，只需继承 `PluginBase` 并定义一个类：

```python
from core.plugin_base import PluginBase


class Hello(PluginBase):
    """自动回复你好"""
    name = "Hello"                    # 必填: 插件名称
    version = "1.0"                   # 必填: 版本号
    description = "收到你好时自动回复"    # 必填: 功能描述
    author = "YourName"               # 选填: 作者名

    def get_matchers(self):
        return [
            {"type": "exact", "pattern": "你好", "description": "回复你好"},
        ]

    async def on_message(self, platform, user_id, group_id, message):
        if platform == 'tg':
            await self.ctx.tg_bot.send_message(
                chat_id=group_id,
                text="你好！有什么可以帮你的吗？"
            )
        elif platform == 'qq':
            await self.ctx.qq_client.send_group_msg(
                group_id,
                "你好！有什么可以帮你的吗？"
            )
```

将文件保存为 `plugins/Hello.py`，重启系统即可自动加载。

---

## 插件文件结构

```
plugins/YourPlugin.py
    │
    ├── [导入区]  from core.plugin_base import PluginBase
    │
    ├── [插件类]  class YourPlugin(PluginBase):
    │       ├── name: str                 # 插件名称（必填，与文件名一致）
    │       ├── version: str              # 版本号（必填）
    │       ├── description: str          # 功能描述（必填）
    │       ├── author: str               # 作者（选填）
    │       │
    │       ├── def get_matchers(self)    # 消息匹配器（选填，返回 list[dict]）
    │       │
    │       ├── async def on_load(self)   # 加载时回调（选填）
    │       ├── async def on_unload(self) # 卸载时回调（选填）
    │       └── async def on_message(self, platform, user_id, group_id, message)
    │                                     # 消息处理（有 matchers 则必须实现）
    │
    └── [其他辅助代码]  可定义任意辅助函数/类
```

### 命名规范

| 规范 | 说明 |
|------|------|
| 文件名 | PascalCase，如 `Weather.py`、`AutoReply.py` |
| 类名 | 必须与文件名（不含 `.py`）完全一致 |
| 单文件单类 | 一个 `.py` 文件仅包含一个继承 `PluginBase` 的类 |
| 模块隔离 | 不要修改 `sys.path` 或修改全局状态 |

---

## PluginBase API

插件基类位于 `core.plugin_base`，所有插件必须继承此类。

### 基类属性

```python
class PluginBase:
    name: str = "base"           # 插件名称（必覆写）
    version: str = "0.1"         # 版本号（必覆写）
    description: str = ""        # 插件描述（必覆写）
    author: str = ""             # 作者名（选填）
    ctx: PluginContext | None    # 插件上下文实例（由系统注入）
```

### 基类方法

```python
async def on_load(self) -> None:
    """插件加载时调用。
    调用时机: 系统启动加载插件、API 上传插件、API 热重载插件。
    用途: 初始化资源（打开文件、连接数据库、初始化 HTTP 客户端等）。
    """
    pass

async def on_unload(self) -> None:
    """插件卸载时调用。
    调用时机: 系统关闭、API 删除/重载插件。
    用途: 释放资源（关闭连接、清理临时文件、保存状态等）。
    """
    pass

def get_matchers(self) -> list[dict]:
    """返回消息匹配规则列表。
    调用时机: 插件加载后立即调用一次，结果被缓存。
    注意: 此方法不能是 async。
    """
    return []

async def on_message(self, platform: str, user_id: int, group_id: int, message: str) -> None:
    """消息匹配后调用。
    调用时机: 匹配器命中后（包括 /command 形式）。
    注意: 此方法执行期间，消息不会被同步到对端。
    """
    pass
```

---

## PluginContext 上下文

`self.ctx` 提供对主程序资源的只读访问：

```python
class PluginContext:
    tg_bot: telegram.Bot         # python-telegram-bot 的 Bot 实例
    qq_client: OneBotClient      # QQ OneBot HTTP 客户端
    config: ConfigLoader         # 配置加载器（可按需读取配置）
    db: Database                 # 数据库访问层
    tg_group_id: int             # 目标 Telegram 群组 ID
    qq_group_id: int             # 目标 QQ 群组 ID
```

### 使用示例

```python
# 发送消息到 Telegram
await self.ctx.tg_bot.send_message(
    chat_id=self.ctx.tg_group_id,
    text="这是一条消息"
)

# 发送消息到 QQ
await self.ctx.qq_client.send_group_msg(
    self.ctx.qq_group_id,
    "这是一条消息"
)

# 读取配置项
token = self.ctx.config.get('telegram.bot_token')

# 查询绑定用户
bindings = await self.ctx.db.get_all_bindings()

# 查询数据库
async with self.ctx.db._Database__get_connection() as conn:
    cursor = await conn.execute('SELECT * FROM message_mapping LIMIT 10')
    rows = await cursor.fetchall()
```

### 可用权限

| 资源 | 可用操作 |
|------|----------|
| `tg_bot` | `send_message`, `send_photo`, `send_document`, `send_video`, `send_sticker`, `send_voice`, `delete_message`, `get_chat` 等 |
| `qq_client` | `send_group_msg`, `send_private_msg`, `delete_msg`, `get_bot_id` |
| `config` | `get(key, default)` 读取配置 |
| `db` | `get_all_bindings()`, `get_setting()`, `get_binding_by_qq()`, `get_binding_by_tg()` |

---

## 消息匹配器

`get_matchers()` 返回一个匹配规则列表。每条规则是一个字典，支持三种匹配类型：

### 匹配类型

| 类型 | key | 说明 | 示例 |
|------|-----|------|------|
| 精确匹配 | `"exact"` | 消息文本与 pattern 完全相同时命中 | 用户发 `"赞我"` → 命中 |
| 前缀匹配 | `"prefix"` | 消息文本以 pattern 开头时命中 | 用户发 `"/weather 北京"` → 命中 |
| 正则匹配 | `"regex"` | 消息文本匹配正则表达式时命中 | 用户发 `"签到"` → 命中 `r"^(签到|打卡)$"` |

### 匹配器字典结构

```python
{
    "type": "exact",           # 必填: "exact" | "prefix" | "regex"
    "pattern": "赞我",          # 必填: 匹配模式
    "description": "回复点赞",   # 必填: 功能说明
}
```

### 完整示例

```python
def get_matchers(self):
    return [
        # 精确匹配：用户必须发送完全相同的文字
        {"type": "exact", "pattern": "赞我", "description": "回复大拇指表情"},

        # 前缀匹配：用户发送以 /weather 开头的消息时触发
        {"type": "prefix", "pattern": "/weather", "description": "查询天气"},

        # 正则匹配：匹配任意包含 6 位数字的消息
        {"type": "regex", "pattern": r"\b\d{6}\b", "description": "识别验证码格式"},
    ]
```

### 匹配优先级

- 同一插件内的多个匹配器，**任一命中**即触发 `on_message`
- 多个插件之间，按**加载顺序**先匹配先触发，一个消息最多触发一个插件
- 收到 `/command` 时，先由系统内置命令处理（`/bind`, `/status` 等），未命中才路由到插件匹配器

### 匹配时机

| 场景 | 插件是否检查 |
|------|-------------|
| 纯文本消息（TG/QQ） | ✅ 检查 |
| 带图片/视频/文件的消息 | ❌ 不检查（走正常转发） |
| 系统内置 `/command` | ❌ 不检查（被系统拦截） |
| 自定义 `/command` | ✅ 检查（如 `/weather`） |

---

## 消息处理流程

### TG → QQ 方向

```
TG 消息到达
    │
    ├─ 是 /command 且为内置命令? ──→ 系统处理，结束
    │
    ├─ 是 /command 且非内置? ──→ 插件匹配
    │       │
    │       ├─ 命中 ──→ 插件处理（不转发到 QQ），结束
    │       └─ 未命中 ──→ 回复"未知命令"，结束
    │
    ├─ 非命令文本? ──→ 插件匹配
    │       │
    │       ├─ 命中 ──→ 插件处理（不转发到 QQ），结束
    │       └─ 未命中 ──→ 转发到 QQ，结束
    │
    └─ 媒体消息? ──→ 转发到 QQ，结束
```

### QQ → TG 方向

```
QQ 消息到达
    │
    ├─ 是 /command 且为内置命令? ──→ 系统处理，结束
    │
    ├─ 是 /command 且非内置? ──→ 插件匹配
    │       │
    │       ├─ 命中 ──→ 插件处理（不转发到 TG），结束
    │       └─ 未命中 ──→ 回复"未知命令"，结束
    │
    ├─ 非命令文本? ──→ 插件匹配
    │       │
    │       ├─ 命中 ──→ 插件处理（不转发到 TG），结束
    │       └─ 未命中 ──→ 转发到 TG，结束
    │
    └─ 媒体消息? ──→ 转发到 TG，结束
```

### 关键规则

1. **插件优先于转发**：插件命中后，消息**不会**同步到对端
2. **插件互斥**：一条消息最多触发一个插件
3. **媒体不拦截**：含图片/视频/语音等附件时，插件不介入，直接转发
4. **内置命令优先**：`/bind` `/status` `/reboot` `/setprefix` `/help` `/confirm` `/cancel` 由系统独占

---

## 平台通信

### 识别来源平台

```python
async def on_message(self, platform, user_id, group_id, message):
    if platform == 'tg':
        # 消息来自 Telegram
        # 可以调用 self.ctx.tg_bot.* 发送响应
        pass
    elif platform == 'qq':
        # 消息来自 QQ
        # 可以调用 self.ctx.qq_client.* 发送响应
        pass
```

### TG Bot 常用 API

通过 `self.ctx.tg_bot` 调用，详见 [python-telegram-bot 文档](https://python-telegram-bot.readthedocs.io/)：

```python
# 发送文本
await self.ctx.tg_bot.send_message(chat_id=group_id, text="回复内容")

# 回复特定消息
await self.ctx.tg_bot.send_message(
    chat_id=group_id,
    text="回复内容",
    reply_to_message_id=original_message_id   # 需要自行传入
)

# 发送图片（需要先上传或使用 file_id）
await self.ctx.tg_bot.send_photo(chat_id=group_id, photo=open('image.jpg', 'rb'))

# 撤回消息
await self.ctx.tg_bot.delete_message(chat_id=group_id, message_id=msg_id)
```

### QQ OneBot 常用 API

通过 `self.ctx.qq_client` 调用，遵循 OneBot v11 协议：

```python
# 发送文本
await self.ctx.qq_client.send_group_msg(group_id, "回复内容")

# 发送带 @ 的消息（消息段数组）
await self.ctx.qq_client.send_group_msg(group_id, [
    {"type": "at", "data": {"qq": str(user_id)}},
    {"type": "text", "data": {"text": " 你好"}}
])

# 发送图片（需要提供 URL 或 base64）
await self.ctx.qq_client.send_group_msg(group_id, [
    {"type": "image", "data": {"file": "https://example.com/image.jpg"}}
])

# 发送私聊消息
await self.ctx.qq_client.send_private_msg(user_id, "私聊消息内容")

# 撤回消息
await self.ctx.qq_client.delete_msg(message_id)
```

---

## 生命周期

### 完整生命周期图

```
[写入 plugins/YourPlugin.py]
        │
        ▼
[系统启动 / API 上传 / API 热重载]
        │
        ▼
[PluginManager.load_plugin()]
        │
        ├── importlib 动态导入模块
        │
        ├── 查找继承 PluginBase 的类
        │
        ├── 实例化: instance = YourClass(ctx=plugin_context)
        │
        ├── 调用 matchers = instance.get_matchers()  # 同步调用
        │
        ├── await instance.on_load()                  # 异步调用
        │
        ├── 记录加载耗时 (ms)
        │
        ├── 双端广播: "✅ YourPlugin.py 插件已加载(启动耗时 XXX ms)"
        │
        └── 注册匹配器，开始监听消息
                │
                ▼
        [插件运行期间: on_message 被调用]
                │
                ▼
        [API 禁用 / API 删除 / 系统关闭]
                │
                ├── await instance.on_unload()        # 异步调用
                │
                ├── 从 sys.modules 中移除
                │
                └── 移除匹配器，停止监听
```

### 状态说明

| 状态 | loaded | enabled | 说明 |
|------|--------|---------|------|
| 🟢 正常 | true | true | 插件已加载且启用，正常响应消息 |
| 🟡 禁用 | true | false | 插件已加载但被禁用，消息不路由到该插件 |
| 🔴 异常 | false | false | 插件加载失败，`error` 字段包含错误原因 |

### on_load 示例

```python
async def on_load(self):
    """加载时打开数据库连接"""
    import aiosqlite
    db_path = os.path.join(os.path.dirname(__file__), '..', 'plugin_data', 'weather.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    self.db = await aiosqlite.connect(db_path)
    await self.db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)')
```

### on_unload 示例

```python
async def on_unload(self):
    """卸载时关闭数据库连接"""
    if hasattr(self, 'db') and self.db:
        await self.db.close()
```

### on_message 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `platform` | `str` | 来源平台：`"tg"` 或 `"qq"` |
| `user_id` | `int` | 发送者用户 ID |
| `group_id` | `int` | 群组 ID |
| `message` | `str` | 消息文本内容 |

---

## 错误处理

### 插件内部异常

插件内任何未捕获的异常会被 PluginManager 捕获并记录，**不会导致主程序崩溃**：

```python
async def on_message(self, platform, user_id, group_id, message):
    try:
        result = await self.risky_operation()
        await self.reply(result)
    except Exception as e:
        # 手动错误处理，向用户显示友好提示
        if platform == 'tg':
            await self.ctx.tg_bot.send_message(group_id, f"操作失败: {e}")
        else:
            await self.ctx.qq_client.send_group_msg(group_id, f"操作失败: {e}")
```

### 超时保护

`on_message` 没有内置超时限制，如果插件可能执行长时间操作，应自行处理：

```python
import asyncio

async def on_message(self, platform, user_id, group_id, message):
    try:
        result = await asyncio.wait_for(self.heavy_operation(), timeout=30)
        await self.reply(result)
    except asyncio.TimeoutError:
        await self.reply("操作超时，请稍后重试")
```

### 日志记录

```python
from utils.logger import logger

async def on_message(self, platform, user_id, group_id, message):
    logger.info(f"[{self.name}] 收到消息: platform={platform}, user={user_id}, text={message[:50]}")
    # ... 业务逻辑
    logger.debug(f"[{self.name}] 处理完成")
```

---

## Admin API 管理接口

所有插件管理操作通过 REST API 完成，需要 `X-API-Key` 认证头。

### 端点列表

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/admin/plugins` | User | 查看所有插件状态和详细信息 |
| POST | `/admin/plugins/{name}/enable` | Admin | 启用指定插件 |
| POST | `/admin/plugins/{name}/disable` | Admin | 禁用指定插件 |
| POST | `/admin/plugins/{name}/reload` | Admin | 热重载指定插件 |
| DELETE | `/admin/plugins/{name}` | Admin | 删除插件（卸载+删除文件） |
| POST | `/admin/plugins/upload` | Admin | 上传新插件并自动加载 |

### 查看插件状态

```
GET /admin/plugins
```

响应示例：

```json
{
  "total": 2,
  "loaded": 1,
  "enabled": 1,
  "plugins": [
    {
      "name": "ThumbsUp",
      "version": "1.0",
      "description": "自动检测'赞我'消息并回复大拇指表情",
      "author": "TQSync",
      "file": "ThumbsUp.py",
      "enabled": true,
      "loaded": true,
      "load_time_ms": 12,
      "error": null,
      "matchers": [{"type": "exact", "pattern": "赞我", "description": "回复👍"}]
    },
    {
      "name": "BrokenPlugin",
      "version": "-",
      "description": "",
      "file": "BrokenPlugin.py",
      "enabled": false,
      "loaded": false,
      "load_time_ms": 0,
      "error": "SyntaxError: invalid syntax",
      "matchers": []
    }
  ]
}
```

### 上传新插件

```
POST /admin/plugins/upload
Content-Type: multipart/form-data
```

- 表单字段 `file`：要上传的 `.py` 插件文件
- 上传后自动加载，并向双端发送加载结果通知

### 热重载

```
POST /admin/plugins/Weather/reload
```

响应示例：

```json
{
  "status": "success",
  "message": "插件 Weather 已重载",
  "load_time_ms": 15,
  "error": null
}
```

---

## 完整示例

### 示例一：天气查询插件

```python
import asyncio
import aiohttp
from core.plugin_base import PluginBase
from utils.logger import logger


class Weather(PluginBase):
    name = "Weather"
    version = "1.0"
    description = "查询城市天气，格式: /weather <城市名>"
    author = "YourName"

    def get_matchers(self):
        return [
            {"type": "prefix", "pattern": "/weather", "description": "查询天气 /weather 北京"},
            {"type": "prefix", "pattern": "天气 ", "description": "查询天气 天气 北京"},
        ]

    async def on_message(self, platform, user_id, group_id, message):
        # 提取城市名
        parts = message.split(maxsplit=1)
        if len(parts) < 2:
            await self._reply(platform, group_id, "请输入城市名，例如: /weather 北京")
            return

        city = parts[1].strip()
        weather_info = await self._fetch_weather(city)

        if weather_info:
            await self._reply(platform, group_id, f"{city} 天气: {weather_info}")
        else:
            await self._reply(platform, group_id, f"未找到 {city} 的天气信息")

    async def _fetch_weather(self, city: str) -> str | None:
        """模拟天气查询（实际应替换为真实 API）"""
        try:
            await asyncio.sleep(0.5)
            return f"晴天 25°C，湿度 60%"
        except Exception as e:
            logger.error(f"[{self.name}] 查询失败: {e}")
            return None

    async def _reply(self, platform: str, group_id: int, text: str):
        """统一回复方法"""
        if platform == 'tg':
            await self.ctx.tg_bot.send_message(chat_id=group_id, text=text)
        elif platform == 'qq':
            await self.ctx.qq_client.send_group_msg(group_id, text)
```

### 示例二：数据持久化插件

```python
import os
import aiosqlite
from core.plugin_base import PluginBase
from utils.logger import logger


class DailySign(PluginBase):
    name = "DailySign"
    version = "1.0"
    description = "每日签到打卡"
    author = "YourName"

    def get_matchers(self):
        return [
            {"type": "regex", "pattern": r"^(签到|打卡)$", "description": "每日签到"},
        ]

    async def on_load(self):
        """初始化本地数据库"""
        db_dir = os.path.join(os.path.dirname(__file__), '..', 'plugin_data')
        os.makedirs(db_dir, exist_ok=True)
        self.db = await aiosqlite.connect(os.path.join(db_dir, 'sign.db'))
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS sign_records (
                user_id INTEGER,
                date TEXT,
                PRIMARY KEY (user_id, date)
            )
        ''')
        await self.db.commit()
        logger.info(f"[{self.name}] 签到数据库已初始化")

    async def on_unload(self):
        """关闭数据库连接"""
        if hasattr(self, 'db') and self.db:
            await self.db.close()
            logger.info(f"[{self.name}] 签到数据库已关闭")

    async def on_message(self, platform, user_id, group_id, message):
        from datetime import date
        today = date.today().isoformat()

        # 检查今日是否已签到
        cursor = await self.db.execute(
            'SELECT 1 FROM sign_records WHERE user_id = ? AND date = ?',
            (user_id, today)
        )
        if await cursor.fetchone():
            await self._reply(platform, group_id, "你今天已经签到过了！")
            return

        # 记录签到
        await self.db.execute(
            'INSERT INTO sign_records (user_id, date) VALUES (?, ?)',
            (user_id, today)
        )
        await self.db.commit()
        await self._reply(platform, group_id, "✅ 签到成功！")

    async def _reply(self, platform, group_id, text):
        if platform == 'tg':
            await self.ctx.tg_bot.send_message(chat_id=group_id, text=text)
        elif platform == 'qq':
            await self.ctx.qq_client.send_group_msg(group_id, text)
```

---

## 最佳实践

### 1. 消息路由

```python
# ✅ 推荐: 通过 platform 参数区分平台响应
async def on_message(self, platform, user_id, group_id, message):
    if platform == 'tg':
        await self.ctx.tg_bot.send_message(chat_id=group_id, text="TG 响应")
    elif platform == 'qq':
        await self.ctx.qq_client.send_group_msg(group_id, "QQ 响应")

# ❌ 避免: 同时向两个平台发送响应（会造成跨平台信息泄露）
```

### 2. 副作用隔离

```python
# ✅ 推荐: 插件数据存放在 plugin_data/<PluginName>/ 目录
async def on_load(self):
    data_dir = os.path.join('plugin_data', self.name)
    os.makedirs(data_dir, exist_ok=True)
    self.data_path = data_dir

# ❌ 避免: 直接操作主程序数据目录（db/, logs/, temp/）
```

### 3. 异常处理

```python
# ✅ 推荐: 捕获异常并通知用户
async def on_message(self, platform, user_id, group_id, message):
    try:
        await self.do_something()
    except Exception as e:
        await self._reply(platform, group_id, f"操作失败: {e}")
        logger.error(f"[{self.name}] {e}")

# ❌ 避免: 抛出未捕获异常（虽然不会导致主程序崩溃，但用户得不到反馈）
```

### 4. 资源清理

```python
# ✅ 推荐: 在 on_unload 中清理所有资源
async def on_unload(self):
    for resource in self._resources:
        await resource.close()

# ❌ 避免: 不实现 on_unload，资源泄漏到下次加载
```

### 5. 匹配器设计

```python
# ✅ 推荐: 明确的匹配模式，避免过度宽泛的正则
def get_matchers(self):
    return [
        {"type": "prefix", "pattern": "/poll", "description": "投票功能"},
    ]

# ❌ 避免: 过于宽泛的正则可能拦截正常消息
def get_matchers(self):
    return [
        {"type": "regex", "pattern": r".*", "description": "匹配所有消息"},
    ]
```

### 6. 性能考虑

- `get_matchers()` 仅调用一次，避免在其中执行耗时操作
- `on_message` 中避免同步阻塞调用，使用 `asyncio` 异步操作
- 长时间操作使用 `asyncio.wait_for` 设置超时
- 插件不应在当前事件循环中长时间占用，超过 30 秒的操作建议使用后台任务

### 7. 版本号规范

遵循语义化版本 `MAJOR.MINOR`：

```
版本格式: <主版本>.<次版本>
例如: 1.0, 2.1, 3.14
不兼容的 API 变更递增主版本
向后兼容的功能新增递增次版本
```

### 8. 文件命名与目录

```
plugins/
├── YourPlugin.py          # 插件主体
└── ...
plugin_data/               # 插件私有数据目录（由插件自行创建管理）
├── YourPlugin/
│   ├── config.json        # 插件配置文件
│   └── data.db            # 插件数据库
└── ...
```

---

## 附录

### 内置命令列表（不可被插件覆盖）

| 命令 | 说明 |
|------|------|
| `/bind` | 绑定 TG↔QQ 账号 |
| `/setprefix` | 设置统一显示昵称 |
| `/help` | 显示帮助信息 |
| `/status` | 查看系统运行状态（含插件列表） |
| `/reboot` | 远程重启机器人 |
| `/confirm` | 确认自动下载 FFmpeg |
| `/cancel` | 取消自动下载 FFmpeg |

### 查看运行日志

```bash
# 实时查看日志
tail -f logs/tqsync.log

# 搜索插件相关日志
grep "插件" logs/tqsync.log
```

### 调试技巧

1. 使用 `logger.info/debug` 输出调试日志
2. 通过 Admin API `GET /admin/plugins` 查看插件加载状态和错误信息
3. 开发阶段可频繁使用 `POST /admin/plugins/{name}/reload` 热重载
4. `/status` 命令可查看插件运行状态概览
