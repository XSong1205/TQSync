# 回复功能重构指南

## 📋 概述

已完成对消息回复功能的彻底重构，删除了所有文本格式化的伪回复实现，改用**真正的原生回复 API**。

## ✨ 主要变更

### 1. **Telegram 原生回复**

使用 Telegram Bot API 的 `reply_to_message_id` 参数实现真正的回复功能。

#### API 说明
```python
await bot.send_message(
    chat_id=chat_id,
    text="回复内容",
    reply_to_message_id=message_id  # 被回复的消息 ID
)
```

#### 代码示例
```python
# message_sync.py - 发送 QQ 消息到 Telegram
reply_to_message_id = message_data.get('reply_to_message_id')
formatted_message = self._format_qq_message(message_data)

# 使用原生回复功能发送
success = await self.telegram_bot.send_message(
    text=formatted_message,
    reply_to_message_id=reply_to_message_id  # Telegram 会显示为回复
)
```

### 2. **QQ 原生回复**

使用 NapCat/OneBot 的 CQ码 `[CQ:reply,id=消息ID]` 实现真正的回复功能。

#### API 说明
```json
{
  "group_id": 123456789,
  "message": "[CQ:reply,id=987654321]回复内容"
}
```

#### 代码示例
```python
# qq_bot.py - 发送 Telegram 消息到 QQ
if reply_to_message_id:
    # 使用 CQ 码格式的回复消息
    reply_segment = f"[CQ:reply,id={reply_to_message_id}]"
    final_message = reply_segment + message
else:
    final_message = message

payload = {
    'group_id': int(self.group_id),
    'message': final_message
}
```

## 🔧 删除的代码

以下代码已被删除或简化：

### ❌ 已删除的方法
- `_find_telegram_reply_target()` - 查找 Telegram 回复目标
- `_find_qq_reply_target()` - 查找 QQ 回复目标
- `_extract_qq_reply_info()` - 提取 QQ 回复信息

### ❌ 已简化的格式化方法
- `_format_telegram_message()` - 删除了所有回复相关的复杂逻辑
- `_format_qq_message()` - 删除了所有回复相关的复杂逻辑

### ❌ 已移除的参数
- `is_reply` - 不再需要标记是否为回复
- `replied_to_user` - 不再需要在文本中显示被回复者
- `replied_to_message` - 不再需要在文本中显示原始消息

## 📊 对比

### 之前的伪回复（文本格式化）
```
[QQ] 张三 回复 李四：你好
[TG] [张三 回复 李四] 原始消息：『abc』，新回复：『你好』
```

### 现在的真回复（原生 API）
```
QQ: 张三 ┌─ 回复 ─┐
             │ 李四：你好
             └────────┘

TG: 张三 ┌─ In reply to ─┐
              │ User: Hello
              └──────────────┘
```

## 🎯 工作原理

### QQ → Telegram
1. QQ 收到回复消息（包含 `reply` 段）
2. 提取 `reply_to_message_id`
3. 格式化消息文本为 `[QQ] 昵称：内容`
4. 调用 Telegram API 发送，传入 `reply_to_message_id`
5. Telegram 显示为原生回复样式

### Telegram → QQ
1. Telegram 收到回复消息（包含 `reply_to_message` 对象）
2. 提取被回复消息的 ID 并映射到 QQ 消息 ID
3. 格式化消息文本为 `[TG] 用户名：内容`
4. 使用 CQ码 `[CQ:reply,id=xxx]` 拼接消息
5. QQ 显示为原生回复样式

## 📝 配置要求

### QQ 端
- ✅ NapCat 或其他 OneBot 兼容客户端
- ✅ 支持 CQ码解析
- ✅ 群消息发送权限

### Telegram 端
- ✅ python-telegram-bot v20+
- ✅ Bot API Token
- ✅ 群组管理员权限（可选）

## 🔍 调试技巧

### 检查日志
```bash
# 查看是否使用了原生回复
grep "使用原生回复功能" logs/*.log
```

### 验证 CQ码
```python
# 在 QQ 消息中查看是否包含 CQ 码
[CQ:reply,id=12345] 这是回复内容
```

### 测试步骤
1. 在 QQ 发送一条消息 A
2. 在 Telegram 回复消息 A
3. 检查 QQ 是否显示为原生回复样式
4. 反之亦然

## ⚠️ 注意事项

1. **消息 ID 映射**
   - 需要维护 QQ 和 Telegram 消息 ID 的映射关系
   - 确保 `reply_to_message_id` 能正确对应到目标平台的消息

2. **跨平台限制**
   - Telegram 只能回复 48 小时内的消息
   - QQ 回复可能受到服务器限制

3. **错误处理**
   - 如果 `reply_to_message_id` 无效，API 会忽略回复属性
   - 消息仍会正常发送，只是不作为回复显示

## 🚀 下一步优化

- [ ] 实现消息 ID 自动映射系统
- [ ] 添加回复链检测（多级回复）
- [ ] 支持引用回复（Quote Reply）
- [ ] 优化转发消息中的回复处理

## 📚 相关资源

- [Telegram Bot API - sendMessage](https://core.telegram.org/bots/api#sendmessage)
- [OneBot CQ 码规范](https://github.com/botuniverse/onebot-11/blob/master/message/string.md)
- [NapCat API 文档](https://napcat.apifox.cn/)

---

*最后更新：2026-02-25*
*TQSync 项目文档*
