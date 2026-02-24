# 使用指南

## 新增功能详细介绍

### 1. 媒体文件同步功能

#### 支持的媒体类型
- 📷 图片 (photo)
- 🎥 视频 (video)  
- 🎵 音频 (audio)
- 🎙️ 语音 (voice)
- 📎 文件 (document)

#### 使用方法
媒体文件会自动在两个平台间同步，无需特殊操作：

**Telegram → QQ:**
- 发送图片/视频等媒体文件到Telegram群组
- 机器人会自动转发到对应的QQ群组
- 格式：`[TG-PHOTO] 用户名: 发送了一个photo`

**QQ → Telegram:**
- 在QQ群组发送媒体文件
- 机器人会自动转发到Telegram群组
- 格式：`[QQ-IMAGE] 昵称: 发送了一个image`

#### 配置选项
```yaml
sync:
  media:
    enable: true                    # 是否启用媒体同步
    supported_types:                # 支持的媒体类型
      - "photo"
      - "video" 
      - "audio"
      - "voice"
      - "document"
    max_file_size: 50              # 最大文件大小(MB)
    temp_file_retention: 24        # 临时文件保留时间(小时)
```

### 2. 消息回复同步功能

#### 功能说明
智能识别和同步跨平台的回复消息，在另一平台以适当的格式显示回复关系。

#### 使用示例
**场景一（Telegram→QQ）：**
1. QQ用户发送："今天的天气真好"
2. Telegram用户回复该消息："是啊，适合出去走走"
3. QQ端显示：`[回复 @QQ用户名] 是啊，适合出去走走`

**场景二（QQ→Telegram）：**
1. Telegram用户发送："会议几点开始？"
2. QQ用户回复该消息："下午3点"
3. Telegram端显示：`[回复 @TG用户名] 下午3点`

#### 配置选项
```yaml
sync:
  reply:
    enable: true                           # 是否启用回复功能
    format: "[回复 @{username}] {message}"  # 回复格式
```

#### 注意事项
- 回复功能默认启用
- 支持从机器人转发的消息中提取原始发送者信息
- 自动清理用户名中的特殊字符
- 处理边界情况（如空回复用户、特殊字符等）

### 3. Telegram消息重试机制

#### 功能说明
当Telegram消息发送失败时，机器人会自动进行指数退避重试：

- 最大重试次数：5次
- 基础延迟：1秒
- 最大延迟：300秒
- 采用指数退避算法

#### 重试队列管理
失败的消息会被存储在SQLite数据库中，即使程序重启也不会丢失。

#### 查看重试状态
```python
# 在代码中获取重试队列统计
from utils.retry_manager import get_retry_manager
retry_manager = await get_retry_manager()
stats = await retry_manager.get_queue_stats()
print(stats)  # {'total': 5, 'pending': 2, 'processing': 3}
```

### 4. 消息过滤前缀功能

#### 功能说明
使用特定前缀可以让消息不被同步，并将其作为机器人命令处理。

#### 默认前缀
默认前缀为 `!`，可在配置文件中修改。

#### 内置命令
```
!ping          - 测试机器人连通性
!status        - 查看机器人运行状态  
!stats         - 查看详细统计信息
!help          - 显示帮助信息
!filter add    - 添加过滤关键词
!filter remove - 移除过滤关键词
!filter list   - 列出当前过滤关键词
```

#### 使用示例
```
!ping                    # 返回: pong!
!stats                   # 返回详细统计信息
!filter add 广告         # 添加"广告"为过滤词
!filter list             # 显示当前过滤词列表
```

#### 配置选项
```yaml
sync:
  filter_prefix: "!"      # 过滤前缀符号
```

### 5. QQ合并转发解析功能

#### 功能说明
智能解析QQ的合并转发消息，将其转换为适合Telegram阅读的格式。

#### 解析效果
**原始QQ合并转发：**
```
[聊天记录]
张三: 早上好
李四: 早安
王五: 大家今天有什么安排？
```

**解析后在Telegram显示：**
```
[转发消息 1/3]
👤 张三 (2024-01-01 09:00:00)
💬 早上好

[转发消息 2/3]  
👤 李四 (2024-01-01 09:01:00)
💬 早安

[转发消息 3/3]
👤 王五 (2024-01-01 09:02:00) 
💬 大家今天有什么安排？
```

### 6. 详细统计信息

#### 统计指标
机器人提供丰富的统计信息：

```python
stats = message_sync.get_stats()
# 返回:
{
    'telegram_received': 100,    # Telegram接收消息数
    'qq_received': 80,           # QQ接收消息数
    'telegram_sent': 80,         # Telegram发送消息数
    'qq_sent': 100,              # QQ发送消息数
    'filtered': 5,               # 关键词过滤数
    'prefix_filtered': 3,        # 前缀过滤数
    'commands_processed': 12,    # 命令处理数
    'total_received': 180,       # 总接收数
    'total_sent': 180,           # 总发送数
    'total_filtered': 8,         # 总过滤数
    'sync_rate': 100.0           # 同步成功率(%)
}
```

## 高级配置

### 环境变量配置
除了config.yaml外，还可以使用环境变量：

```env
# 基础配置
TELEGRAM_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
QQ_GROUP_ID=your_qq_group
NAPCAT_WS_URL=ws://localhost:3001
NAPCAT_HTTP_URL=http://localhost:3000

# 代理配置
TELEGRAM_PROXY_ENABLE=true
TELEGRAM_PROXY_TYPE=socks5
TELEGRAM_PROXY_HOST=127.0.0.1
TELEGRAM_PROXY_PORT=1080

# 同步配置
SYNC_BIDIRECTIONAL=true
SYNC_MAX_MESSAGE_LENGTH=4096
SYNC_COOLDOWN_TIME=1
SYNC_FILTER_PREFIX=!
```

### 性能优化建议

1. **合理设置冷却时间**
   ```yaml
   sync:
     cooldown_time: 2  # 避免发送过于频繁
   ```

2. **配置合适的文件大小限制**
   ```yaml
   sync:
     media:
       max_file_size: 20  # 根据网络情况调整
   ```

3. **定期清理临时文件**
   ```python
   from utils.media_handler import get_media_handler
   media_handler = await get_media_handler()
   await media_handler.cleanup_temp_files(max_age_hours=12)
   ```

## 故障排除

### 媒体文件同步问题
- 检查文件大小是否超出限制
- 确认网络连接稳定
- 查看temp目录权限

### 消息重试失败
- 检查Telegram API限制
- 确认网络连接
- 查看重试队列状态

### 过滤前缀不生效
- 确认前缀符号正确
- 检查配置文件语法
- 重启机器人使配置生效

### 转发消息解析异常
- 确认QQ消息格式符合标准
- 检查napcat版本兼容性
- 查看详细日志信息