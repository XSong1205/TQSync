# Telegram-QQ Sync Bot 项目概览

## 🎯 项目介绍

这是一个基于Python开发的Telegram和QQ群组消息同步机器人，使用napcat接入QQ协议，实现两个平台间的实时消息互通。

## 📁 项目结构

```
TQSync/
├── bots/                    # 机器人客户端模块
│   ├── telegram_bot.py     # Telegram机器人实现
│   └── qq_bot.py          # QQ机器人实现(基于napcat)
├── core/                   # 核心业务逻辑
│   └── message_sync.py    # 消息同步核心
├── utils/                  # 工具模块
│   ├── config.py          # 配置管理
│   └── logger.py          # 日志系统
├── logs/                   # 日志文件目录
├── data/                   # 数据存储目录
├── temp/                   # 临时文件目录
├── main.py                # 主程序入口
├── init.py                # 初始化脚本
├── test.py                # 测试脚本
├── config.yaml            # 主配置文件
├── .env                   # 环境变量配置
├── requirements.txt       # Python依赖列表
├── README.md             # 项目说明文档
└── USAGE.md              # 使用指南
```

## 🔧 核心功能

### 已实现功能
- ✅ Telegram机器人接入和消息处理
- ✅ QQ机器人接入(napcat协议)
- ✅ 双向消息同步
- ✅ 消息格式化和平台标识
- ✅ 消息过滤和关键词屏蔽
- ✅ 防刷机制和冷却时间控制
- ✅ 消息去重和缓存机制
- ✅ 详细的日志记录系统
- ✅ 配置文件和环境变量支持
- ✅ 优雅的启动和关闭机制
- ✅ 运行统计和监控
- ✅ 内置测试脚本

### 技术特性
- 🚀 基于asyncio的异步架构
- 🛡️ 完善的错误处理和重连机制
- 📝 结构化的日志系统(loguru)
- ⚙️ 灵活的配置管理(yaml + env)
- 🔧 模块化设计，易于扩展

## 🚀 快速开始

### 1. 环境要求
- Python 3.8+
- pip包管理器

### 2. 安装步骤
```bash
# 1. 初始化项目
python init.py

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置机器人(编辑.env文件)
# 4. 测试配置
python test.py

# 5. 启动机器人
python main.py
```

### 3. 配置说明
在 `.env` 文件中配置：
```env
# Telegram配置
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# QQ配置
QQ_GROUP_ID=your_qq_group_id
NAPCAT_WS_URL=ws://127.0.0.1:3001
NAPCAT_HTTP_URL=http://127.0.0.1:3000
```

## 📊 系统架构

```
┌─────────────────┐    ┌─────────────────┐
│   Telegram      │    │      QQ         │
│    Bot API      │    │   (napcat)      │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          ▼                      ▼
┌─────────────────────────────────────────┐
│           Message Sync Core             │
│  • 消息路由                             │
│  • 格式转换                             │
│  • 过滤处理                             │
│  • 冷却控制                             │
└─────────────────────────────────────────┘
          │                      │
          ▼                      ▼
┌─────────────────┐    ┌─────────────────┐
│  Telegram Bot   │    │    QQ Bot       │
│   Client        │    │   Client        │
└─────────────────┘    └─────────────────┘
```

## 🛠️ 开发指南

### 代码结构说明

**bots/** - 机器人客户端
- `telegram_bot.py`: 处理Telegram消息收发
- `qq_bot.py`: 处理QQ消息收发(WebSocket连接)

**core/** - 核心逻辑
- `message_sync.py`: 消息同步主逻辑，协调两个平台

**utils/** - 工具模块
- `config.py`: 配置加载和管理
- `logger.py`: 日志系统配置

### 扩展建议

1. **添加更多平台支持**
   - 可以添加Discord、微信等平台
   - 继承现有机器人基类模式

2. **增强消息处理功能**
   - 添加表情符号转换
   - 支持图片/文件转发
   - 消息翻译功能

3. **完善管理功能**
   - Web管理界面
   - 更丰富的统计报表
   - 动态配置更新

## 📈 性能优化

- 使用异步IO避免阻塞
- 消息缓存减少重复处理
- 连接池管理WebSocket连接
- 合理的重试机制

## 🐛 故障排除

常见问题和解决方案请参考 `USAGE.md` 文件。

## 📄 许可证

MIT License

## 👥 贡献

欢迎提交Issue和Pull Request来改进项目！