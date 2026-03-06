# Telegram 媒体同步功能增强

## 📋 更新内容

### ✅ 已实现的功能

#### 1. **Sticker (贴纸) 同步**
- Telegram → QQ: Sticker 会自动作为图片发送到 QQ
- 支持静态贴纸和动态贴纸（.webp 格式）
- 映射关系：`sticker` → `image`

#### 2. **Animation (GIF) 同步**
- Telegram → QQ: GIF 动画会自动作为图片发送到 QQ
- 支持所有 Telegram GIF 格式
- 映射关系：`animation` → `image`

#### 3. **Video (视频) 同步修复**
- 增强了日志输出，便于调试
- 添加了详细的错误追踪
- 改进了文件下载处理

## 🔧 技术实现

### 1. 媒体类型识别扩展

**文件**: `bots/telegram_bot.py`

```python
def _identify_media_type(self, message) -> str:
    """识别媒体类型"""
    if message.sticker:
        return 'sticker'
    elif message.animation:
        return 'animation'  # GIF
    elif message.photo:
        return 'photo'
    elif message.video:
        return 'video'
    # ... 其他类型
```

### 2. 文件 ID 提取

```python
def _get_file_id(self, message, media_type: str) -> Optional[str]:
    """获取文件 ID"""
    if media_type == 'sticker':
        return message.sticker.file_id
    elif media_type == 'animation':
        return message.animation.file_id
    # ... 其他类型
```

### 3. 媒体类型映射

**文件**: `core/message_sync.py`

```python
def _map_telegram_type_to_qq(self, telegram_media_type: str) -> str:
    """将 Telegram 媒体类型映射到 QQ 文件类型"""
    mapping = {
        'photo': 'image',
        'video': 'video',
        'audio': 'audio',
        'voice': 'record',
        'document': 'file',
        'sticker': 'image',      # 新增：贴纸作为图片
        'animation': 'image'     # 新增：GIF 作为图片
    }
    return mapping.get(telegram_media_type.lower(), 'file')
```

### 4. 特殊媒体处理

```python
async def _handle_telegram_media_message(self, message_data: Dict[Any, Any]):
    """处理Telegram 媒体消息"""
    media_type = message_data.get('media_type')
    
    # 特殊处理贴纸和 GIF
    if media_type in ['sticker', 'animation']:
        logger.info(f"正在处理特殊媒体类型：{media_type}")
        local_file_path = await self.media_handler.download_media(
            file_url, 
            f"{media_type}_{message_data.get('message_id', '')}.webp"
        )
    else:
        local_file_path = await self.media_handler.download_media(file_url)
    
    # 后续发送逻辑...
```

## 📊 数据流程

### Sticker/GIF 同步流程

```mermaid
graph LR
    A[TG Sticker/GIF] --> B[识别媒体类型]
    B --> C[获取 File ID]
    C --> D[下载为.webp 文件]
    D --> E[映射为 image 类型]
    E --> F[QQ 图片发送]
    F --> G[完成]
```

### Video 同步流程

```mermaid
graph LR
    A[TG Video] --> B[识别媒体类型]
    B --> C[获取 File ID]
    C --> D[下载视频文件]
    D --> E[映射为 video 类型]
    E --> F[QQ 视频发送]
    F --> G[完成]
```

## 🔍 调试信息

### 日志输出示例

正常运行时会看到：

```
处理Telegram 媒体消息：sticker - https://api.telegram.org/file/...
正在处理特殊媒体类型：sticker
Telegram 媒体文件已下载到：temp/media/sticker_12345.webp
映射媒体类型：sticker -> image
Telegram 媒体消息已成功发送到 QQ: 67890
```

视频同步时会看到：

```
处理Telegram 媒体消息：video - https://api.telegram.org/file/...
Telegram 媒体文件已下载到：temp/media/video_12345.mp4
映射媒体类型：video -> video
Telegram 媒体消息已成功发送到 QQ: 67890
```

### 错误追踪

如果出现问题，会显示详细错误：

```python
处理Telegram 媒体消息时出错：<错误信息>
Traceback (most recent call last):
  <详细堆栈跟踪>
```

## ✅ 测试验证

运行测试脚本：

```bash
python test_telegram_media.py
```

预期输出：

```
🎬 Telegram 媒体同步功能测试
================================================================================

📊 Telegram 媒体类型映射测试
================================================================================

测试 _map_telegram_type_to_qq:
  ✅ photo -> image (期望：image)
  ✅ video -> video (期望：video)
  ✅ audio -> audio (期望：audio)
  ✅ voice -> record (期望：record)
  ✅ document -> file (期望：file)
  ✅ sticker -> image (期望：image)
  ✅ animation -> image (期望：image)

🔍 Telegram 媒体类型识别测试
================================================================================
  Sticker 检测：sticker ✅
  Animation 检测：animation ✅

================================================================================
📋 测试结果
================================================================================
✅ 所有测试通过!

✨ 已实现功能:
  • Sticker (贴纸) 同步 - 作为图片发送到 QQ
  • Animation (GIF) 同步 - 作为图片发送到 QQ
  • Video (视频) 同步 - 正常支持
  • Photo (照片) 同步 - 正常支持
  • Audio/Voice 同步 - 正常支持
```

## 💡 使用说明

### 在 Telegram 中发送

1. **发送 Sticker**:
   - 在 Telegram 群组发送任意贴纸
   - 机器人会自动同步到 QQ 群
   - 以图片形式显示

2. **发送 GIF**:
   - 在 Telegram 群组发送 GIF 动画
   - 机器人会自动同步到 QQ 群
   - 以图片形式显示（.webp 格式）

3. **发送视频**:
   - 在 Telegram 群组发送视频
   - 机器人会自动同步到 QQ 群
   - 以视频形式显示

### 查看同步状态

```bash
# 查看实时日志
tail -f logs/tqsync.log | grep "媒体消息"

# 查看 Sticker 同步
grep "sticker" logs/tqsync.log

# 查看 GIF 同步
grep "animation" logs/tqsync.log

# 查看视频同步
grep "video" logs/tqsync.log
```

## ⚠️ 注意事项

### Sticker 限制
-  animated stickers (.tgs) 会被转换为 .webp 格式
- 视频 stickers 会以 .webp 格式发送
- QQ 端可能无法显示动画效果（取决于 QQ 版本）

### GIF 限制
- GIF 会以 .webp 格式保存和发送
- 动画效果会保留
- 文件大小受 Telegram 和 QQ 的限制

### 视频限制
- 视频大小不能超过 Telegram 限制（50MB）
- 视频格式需要 QQ 支持
- 超大视频可能会下载失败

## 🐛 故障排查

### 问题 1: Sticker/GIF 没有同步

**检查步骤**:
1. 查看日志是否有 "正在处理特殊媒体类型" 字样
2. 确认下载是否成功
3. 检查 QQ  Bot 的媒体发送权限

**解决方案**:
```bash
# 查看详细日志
grep -A 10 "sticker" logs/tqsync.log
```

### 问题 2: 视频同步失败

**检查步骤**:
1. 查看日志中的错误信息
2. 检查视频文件大小
3. 确认网络连通性

**常见错误**:
- 下载超时：增加 `ClientTimeout` 值
- 文件过大：视频超过限制
- 格式不支持：转换视频格式

### 问题 3: 所有媒体都降级为文本

**可能原因**:
- 媒体下载失败
- NapCat 服务未运行
- 文件路径权限问题

**解决方案**:
```bash
# 检查临时目录权限
ls -la temp/media/

# 检查 NapCat 状态
# 确保 WebSocket 连接正常
```

## 📚 相关文件

- `bots/telegram_bot.py` - Telegram 媒体识别
- `core/message_sync.py` - 媒体类型映射和处理
- `utils/media_handler.py` - 媒体文件下载
- `bots/qq_bot.py` - QQ 媒体发送

---

*更新日期：2026-02-25*
*TQSync 项目文档*
