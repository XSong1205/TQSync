# Changelog

所有重要的项目变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [0.2.2] - 2026-02-25

### ✨ 新增功能

#### 配置系统完善
- 📝 添加 `.env.example` 配置模板文件，包含必要的环境变量配置
- 📝 添加 `config.yaml.example` 完整配置模板，支持所有高级选项
- 🔧 优化 `install.py` 安装脚本，自动创建配置文件和目录结构
- 📚 新增配置指南文档：
  - `CONFIG_GUIDE.md` - 完整配置说明
  - `QUICK_CONFIG.md` - 快速开始指南
  - `CONFIG_TEMPLATE_COMPLETE.md` - 配置模板完成报告

#### 媒体消息同步增强
- 🎨 实现 Telegram Sticker (贴纸) 同步到 QQ
- 🎬 实现 Telegram Animation (GIF) 同步到 QQ
- 📹 修复 Video (视频) 同步问题
- 📊 扩展媒体类型映射表，支持 sticker 和 animation 类型
- 🔍 增强媒体消息处理日志，便于调试

#### 回复功能改进
- 💬 完善 `_find_qq_reply_target()` 方法，实现智能查找 QQ 回复目标
- 🔍 使用 NapCat API 的 `get_group_msg_history` 获取历史消息
- 🎯 通过用户 ID 和消息内容双重匹配定位原始消息
- 📝 新增回复功能实现文档：`QQ_REPLY_TARGET_IMPLEMENTATION.md`

#### 测试工具
- ✅ 添加 `test_message_id_mapping.py` - 消息 ID 映射功能测试
- ✅ 添加 `test_ssl_fix.py` - SSL 修复验证测试
- ✅ 添加 `test_telegram_fix.py` - Telegram Bot 初始化测试
- ✅ 添加 `test_telegram_media.py` - 媒体同步功能测试

### 🔧 技术优化

#### 核心模块
- 🐛 修复 `TelegramBot._direct_send_message()` 返回值问题，现在返回消息对象而非布尔值
- ✨ 添加 `send_message_with_result()` 方法，支持获取发送结果
- 🔄 完善消息 ID 映射建立逻辑，确保双向映射正确保存
- 📝 增强错误追踪，添加详细的 traceback 输出

#### 配置文件
- 🔒 增强 `.gitignore` 配置，忽略敏感文件和临时文件
- 📁 规范化项目结构，分离配置模板和实际配置
- 🗑️ 删除过时的文档文件（PROXY_GUIDE.md, USAGE.md 等）

#### 文档系统
- 📖 添加 `GITIGNORE_GUIDE.md` - .gitignore 配置指南
- 📖 添加 `GITIGNORE_UPDATE_REPORT.md` - .gitignore 更新报告
- 📖 添加 `TELEGRAM_MEDIA_SYNC_ENHANCEMENT.md` - 媒体同步增强文档
- 📖 更新 `MESSAGE_ID_MAPPING_FIX.md` - 消息 ID 映射修复指南

### 📦 依赖更新
- 📌 保持现有依赖版本不变
- ✅ 兼容性测试通过

### 🐛 Bug 修复
- 🐛 修复视频同步下载失败的问题
- 🐛 修复消息 ID 映射无法正确建立的严重问题
- 🐛 修复 Telegram Bot 初始化时的 SSL 证书验证错误
- 🐛 修复 python-telegram-bot v20+ API 兼容性问题

### ⚠️ 破坏性变更
- ⚠️ 无

### 📝 迁移指南

#### 从旧版本升级

1. **拉取最新代码**：
   ```bash
   git pull origin main
   ```

2. **运行安装脚本**：
   ```bash
   python install.py
   ```
   会自动创建新的配置文件

3. **配置新参数**：
   - 编辑 `.env` 或 `config.yaml`
   - 确认必要参数已填写

4. **测试功能**：
   ```bash
   python test.py
   ```

#### 配置文件变更

**新增必要参数**（如果使用 .env）：
```bash
# 以下参数已在 .env.example 中提供
TELEGRAM_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
NAPCAT_WS_URL=ws://127.0.0.1:8080/ws
NAPCAT_HTTP_URL=http://127.0.0.1:5700
QQ_GROUP_ID=your_group_id_here
```

**新增可选配置**（如果使用 config.yaml）：
```yaml
sync:
  media:
    supported_types:
      - sticker    # 新增：贴纸
      - animation  # 新增：GIF
```

---

## [0.2.1] - 2026-02-24

### ✨ 新增功能
- 🔄 实现消息重试机制
- 🔍 实现消息过滤系统
- 💬 实现原生回复功能

### 🔧 技术优化
- ♻️ 重构消息同步逻辑
- 📈 性能优化

### 🐛 Bug 修复
- 🐛 修复消息撤回同步问题
- 🐛 修复用户绑定问题

---

## [0.2.0] - 2026-02-23

### ✨ 重大更新
- 💾 实现数据库持久化
- 🔐 实现用户绑定系统
- 🔄 实现精准撤回同步

### 🔧 技术优化
- 🏗️ 重构项目架构
- 📦 模块化设计

---

## 版本说明

### 语义化版本格式

- **主版本号 (Major)**：不兼容的 API 修改
- **次版本号 (Minor)**：向下兼容的功能性新增
- **修订号 (Patch)**：向下兼容的问题修正

### 发布类型

- 🚀 **正式版** - 稳定版本，推荐生产环境使用
- 🧪 **测试版** - 测试版本，可能包含未完全验证的功能
- 🔧 **热修复** - 紧急问题修复版本

### 更新策略

1. **定期检查** - 关注 GitHub Releases
2. **阅读变更** - 查看 Changelog 了解变更内容
3. **备份配置** - 更新前备份配置文件
4. **测试验证** - 在测试环境验证后再部署

---

*最后更新：2026-02-25*
*TQSync Team