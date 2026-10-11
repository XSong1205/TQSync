# NapCat QQ API 规范 (v4.18.37)

> **文档来源**: [NapCatQQ 官方 API (4.18.37)](https://napneko.github.io/api/4.18.37)
> **版本**: 4.18.37 | **端点总数**: 178

本文档同步自 NapCatQQ 官方 4.18.37 接口规范，包含所有 HTTP API 接口路径、请求方法、摘要说明与核心数据模型，供 TQSync 项目调用与扩展 QQ 接口时参考。

## 目录
- [流式传输扩展 (4)](#流式传输扩展)
- [流式接口 (2)](#流式接口)
- [群组扩展 (18)](#群组扩展)
- [核心接口 (6)](#核心接口)
- [群组接口 (25)](#群组接口)
- [扩展接口 (12)](#扩展接口)
- [系统接口 (13)](#系统接口)
- [用户接口 (6)](#用户接口)
- [系统扩展 (16)](#系统扩展)
- [消息扩展 (9)](#消息扩展)
- [文件接口 (5)](#文件接口)
- [Go-CQHTTP (27)](#Go-CQHTTP)
- [消息接口 (10)](#消息接口)
- [文件扩展 (17)](#文件扩展)
- [用户扩展 (4)](#用户扩展)
- [频道接口 (2)](#频道接口)
- [AI 扩展 (2)](#AI 扩展)
- [数据模型 / Schemas (39)](#数据模型--schemas)

## 流式传输扩展

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/clean_stream_temp_file` | `POST` | 清理流式传输临时文件 | - |
| `/download_file_record_stream` | `POST` | 下载语音文件流 | - |
| `/download_file_image_stream` | `POST` | 下载图片文件流 | - |
| `/test_download_stream` | `POST` | 测试下载流 | - |

## 流式接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/download_file_stream` | `POST` | 下载文件流 | 以流式方式从网络或本地下载文件 |
| `/upload_file_stream` | `POST` | 上传文件流 | 以流式方式上传文件数据到机器人 |

## 群组扩展

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/del_group_album_media` | `POST` | 删除群相册媒体 | - |
| `/set_group_album_media_like` | `POST` | 点赞群相册媒体 | - |
| `/cancel_group_album_media_like` | `POST` | 取消点赞群相册媒体 | - |
| `/do_group_album_comment` | `POST` | 发表群相册评论 | - |
| `/get_group_album_media_list` | `POST` | 获取群相册媒体列表 | - |
| `/get_qun_album_list` | `POST` | 获取群相册列表 | - |
| `/upload_image_to_qun_album` | `POST` | 上传图片到群相册 | - |
| `/upload_images_to_qun_album` | `POST` | 上传多张图片到群相册 | 一次上传多张图片，这些图片在群相册里显示为同一条上传 |
| `/upload_video_to_qun_album` | `POST` | 上传视频到群相册 | 上传视频到群相册，封面自动抽取首帧（失败时使用内置默认封面） |
| `/set_group_add_option` | `POST` | 设置群加群选项 | - |
| `/set_group_robot_add_option` | `POST` | 设置群机器人加群选项 | - |
| `/set_group_search` | `POST` | 设置群搜索选项 | - |
| `/set_group_remark` | `POST` | 设置群备注 | 设置群备注 |
| `/get_group_info_ex` | `POST` | 获取群详细信息 (扩展) | - |
| `/get_group_share_link` | `POST` | 获取群分享链接 | 通过 NTQQ 原生 getJoinGroupLink 获取群的 H5 分享/加群链接 (qm.qq.com/q/xxx 或 qun.qq.com/uni... |
| `/set_group_sign` | `POST` | 群打卡 | - |
| `/send_group_sign` | `POST` | 群打卡 | - |
| `/get_group_signed_list` | `POST` | 获取群组今日打卡列表 | - |

## 核心接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/set_group_todo` | `POST` | 设置群待办 | 将指定消息设置为群待办 |
| `/complete_group_todo` | `POST` | 完成群待办 | 将指定消息对应的群待办标记为已完成 |
| `/cancel_group_todo` | `POST` | 取消群待办 | 将指定消息对应的群待办取消 |
| `/group_poke` | `POST` | 发送戳一戳 | 在群聊或私聊中发送戳一戳动作 |
| `/friend_poke` | `POST` | 发送戳一戳 | 在群聊或私聊中发送戳一戳动作 |
| `/send_poke` | `POST` | 发送戳一戳 | 在群聊或私聊中发送戳一戳动作 |

## 群组接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/get_group_detail_info` | `POST` | 获取群详细信息 | 获取群聊的详细信息，包括成员数、最大成员数等 |
| `/set_group_member_invite_policy` | `POST` | 设置群成员邀请策略 | 设置是否允许群成员邀请好友进群，以及邀请是否需要管理员审核 |
| `/set_group_member_permissions` | `POST` | 设置群成员功能权限 | 设置群成员上传相册、发起临时会话和发起新群聊的权限；未传入的项目保持不变 |
| `/set_group_new_member_history_visibility` | `POST` | 设置新成员历史消息可见性 | 设置新入群成员默认是否可以查看最近聊天记录 |
| `/get_group_list` | `POST` | 获取群列表 | 获取当前帐号的群聊列表 |
| `/get_group_info` | `POST` | 获取群信息 | 获取群聊的基本信息 |
| `/get_group_member_list` | `POST` | 获取群成员列表 | 获取群聊中的所有成员列表 |
| `/get_group_member_info` | `POST` | 获取群成员信息 | 获取群聊中指定成员的信息 |
| `/send_group_msg` | `POST` | 发送群消息 | 发送群消息 |
| `/set_group_add_request` | `POST` | 处理加群请求 | 同意或拒绝加群请求或邀请 |
| `/set_group_leave` | `POST` | 退出群组 | 退出或解散指定群聊 |
| `/set_group_whole_ban` | `POST` | 全员禁言 | 开启或关闭指定群聊的全员禁言 |
| `/set_group_ban` | `POST` | 群组禁言 | 禁言群聊中的指定成员 |
| `/set_group_kick` | `POST` | 群组踢人 | 将指定成员踢出群聊 |
| `/set_group_admin` | `POST` | 设置群管理员 | 设置或取消群聊中的管理员 |
| `/set_group_name` | `POST` | 设置群名称 | 修改指定群聊的名称 |
| `/set_group_card` | `POST` | 设置群名片 | 设置群聊中指定成员的群名片 |
| `/_get_group_notice` | `POST` | 获取群公告 | 获取指定群聊中的公告列表 |
| `/get_essence_msg_list` | `POST` | 获取群精华消息 | 获取指定群聊中的精华消息列表 |
| `/get_group_ignored_notifies` | `POST` | 获取群忽略通知 | 获取被忽略的入群申请和邀请通知 |
| `/delete_essence_msg` | `POST` | 移出精华消息 | 将一条消息从群精华消息列表中移出 |
| `/set_essence_msg` | `POST` | 设置精华消息 | 将一条消息设置为群精华消息 |
| `/_del_group_notice` | `POST` | 删除群公告 | 删除群聊中的公告 |
| `/get_group_shut_list` | `POST` | 获取群禁言列表 | - |
| `/get_group_ignore_add_request` | `POST` | 获取群被忽略的加群请求 | - |

## 扩展接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/set_group_kick_members` | `POST` | 批量踢出群成员 | 从指定群聊中批量踢出多个成员 |
| `/create_collection` | `POST` | 创建收藏 | - |
| `/set_self_longnick` | `POST` | 设置个性签名 | 修改当前登录帐号的个性签名 |
| `/set_qq_avatar` | `POST` | 设置QQ头像 | 修改当前账号的QQ头像 |
| `/translate_en2zh` | `POST` | 英文单词翻译 | 将英文单词列表翻译为中文 |
| `/get_clientkey` | `POST` | 获取ClientKey | 获取当前登录帐号的ClientKey |
| `/send_qzone_msg` | `POST` | 发表QQ空间说说 | 在QQ空间(Qzone)发表说说, 支持纯文字或带(多)图, 可设置查看权限 |
| `/delete_qzone_msg` | `POST` | 删除QQ空间说说 | 删除QQ空间(Qzone)的一条说说, 按 tid 删除 |
| `/ocr_image` | `POST` | 图片 OCR 识别 | 识别图片中的文字内容(仅Windows端支持) |
| `/.ocr_image` | `POST` | 图片 OCR 识别 (内部) | 识别图片中的文字内容(仅Windows端支持) |
| `/set_group_special_title` | `POST` | 设置专属头衔 | 设置群聊中指定成员的专属头衔 |
| `/get_ai_characters` | `POST` | 获取AI角色列表 | 获取群聊中的AI角色列表 |

## 系统接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/set_doubt_friends_add_request` | `POST` | 处理可疑好友申请 | 同意或拒绝系统的可疑好友申请 |
| `/get_doubt_friends_add_request` | `POST` | 获取可疑好友申请 | 获取系统的可疑好友申请列表 |
| `/get_login_info` | `POST` | 获取登录号信息 | 获取当前登录帐号的信息 |
| `/get_version_info` | `POST` | 获取版本信息 | 获取版本信息 |
| `/can_send_record` | `POST` | 是否可以发送语音 | 检查是否可以发送语音 |
| `/can_send_image` | `POST` | 是否可以发送图片 | 检查是否可以发送图片 |
| `/get_status` | `POST` | 获取运行状态 | 获取运行状态 |
| `/get_csrf_token` | `POST` | 获取 CSRF Token | 获取 CSRF Token |
| `/get_credentials` | `POST` | 获取登录凭证 | 获取登录凭证 |
| `/nc_get_packet_status` | `POST` | 获取Packet状态 | 获取底层Packet服务的运行状态 |
| `/set_restart` | `POST` | 重启服务 | 重启服务 |
| `/get_group_system_msg` | `POST` | 获取群系统消息 | 获取群系统消息 |
| `/clean_cache` | `POST` | 清理缓存 | 清理缓存 |

## 用户接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/set_friend_remark` | `POST` | 设置好友备注 | 设置好友备注 |
| `/send_like` | `POST` | 点赞 | 给指定用户点赞 |
| `/get_friend_list` | `POST` | 获取好友列表 | 获取当前帐号的好友列表 |
| `/set_friend_add_request` | `POST` | 处理加好友请求 | 同意或拒绝加好友请求 |
| `/get_cookies` | `POST` | 获取 Cookies | 获取指定域名的 Cookies |
| `/get_recent_contact` | `POST` | 获取最近会话 | 获取最近会话 |

## 系统扩展

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/get_rkey` | `POST` | 获取扩展 RKey | - |
| `/get_rkey_server` | `POST` | 获取 RKey 服务器 | - |
| `/set_online_status` | `POST` | 设置在线状态 | ## 状态列表  ### 在线 ```json5; { "status": 10, "ext_status": 0, "battery_status": ... |
| `/get_robot_uin_range` | `POST` | 获取机器人 UIN 范围 | - |
| `/fetch_custom_face` | `POST` | 获取自定义表情 | - |
| `/fetch_custom_face_detail` | `POST` | 获取自定义表情详情 | - |
| `/add_custom_face` | `POST` | 添加自定义表情 | - |
| `/delete_custom_face` | `POST` | 删除自定义表情 | - |
| `/set_custom_face_desc` | `POST` | 修改自定义表情描述 | - |
| `/set_input_status` | `POST` | 设置输入状态 | - |
| `/nc_get_user_status` | `POST` | 获取用户在线状态 | - |
| `/nc_get_rkey` | `POST` | 获取 RKey | - |
| `/get_mini_app_ark` | `POST` | 获取小程序 Ark | - |
| `/send_packet` | `POST` | 发送原始数据包 | - |
| `/bot_exit` | `POST` | 退出登录 | - |
| `/get_collection_list` | `POST` | 获取收藏列表 | - |

## 消息扩展

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/fetch_emoji_like` | `POST` | 获取表情点赞详情 | - |
| `/get_emoji_likes` | `POST` | 获取消息表情点赞列表 | - |
| `/fetch_ptt_text` | `POST` | 获取语音转文字结果 | - |
| `/ArkShareGroup` | `POST` | 分享群 (Ark) | 获取群分享的 Ark 内容 |
| `/ArkSharePeer` | `POST` | 分享用户 (Ark) | 获取用户推荐的 Ark 内容 |
| `/send_group_ark_share` | `POST` | 分享群 (Ark) | 获取群分享的 Ark 内容 |
| `/send_ark_share` | `POST` | 分享用户 (Ark) | 获取用户推荐的 Ark 内容 |
| `/set_msg_emoji_like` | `POST` | 设置消息表情点赞 | - |
| `/click_inline_keyboard_button` | `POST` | 点击内联键盘按钮 | - |

## 文件接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/get_file` | `POST` | 获取文件 | 获取指定文件的详细信息及下载路径 |
| `/get_image` | `POST` | 获取图片 | 获取指定图片的信息及路径 |
| `/get_record` | `POST` | 获取语音 | 获取指定语音文件的信息，并支持格式转换 |
| `/get_group_file_url` | `POST` | 获取群文件URL | 获取指定群文件的下载链接 |
| `/get_private_file_url` | `POST` | 获取私聊文件URL | 获取指定私聊文件的下载链接 |

## Go-CQHTTP

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/set_qq_profile` | `POST` | 设置QQ资料 | 修改当前账号的昵称、个性签名等资料 |
| `/get_group_root_files` | `POST` | 获取群根目录文件列表 | 获取群文件根目录下的所有文件和文件夹 |
| `/delete_friend` | `POST` | 删除好友 | 从好友列表中删除指定用户 |
| `/check_url_safely` | `POST` | 检查URL安全性 | 检查指定URL的安全等级 |
| `/get_online_clients` | `POST` | 获取在线客户端 | 获取当前登录账号的在线客户端列表 |
| `/get_group_honor_info` | `POST` | 获取群荣誉信息 | 获取指定群聊的荣誉信息，如龙王等 |
| `/_send_group_notice` | `POST` | 发送群公告 | 在指定群聊中发布新的公告 |
| `/get_group_at_all_remain` | `POST` | 获取群艾特全体剩余次数 | 获取指定群聊中艾特全体成员的剩余次数 |
| `/send_forward_msg` | `POST` | 发送合并转发消息 | 发送合并转发消息 |
| `/send_group_forward_msg` | `POST` | 发送群合并转发消息 | - |
| `/send_private_forward_msg` | `POST` | 发送私聊合并转发消息 | - |
| `/get_stranger_info` | `POST` | 获取陌生人信息 | 获取指定非好友用户的信息 |
| `/download_file` | `POST` | 下载文件 | 下载网络文件到本地临时目录 |
| `/upload_group_file` | `POST` | 上传群文件 | 上传资源路径或URL指定的文件到指定群聊的文件系统中 |
| `/get_group_msg_history` | `POST` | 获取群历史消息 | 获取指定群聊的历史聊天记录 |
| `/get_forward_msg` | `POST` | 获取合并转发消息 | 获取合并转发消息的具体内容 |
| `/get_friend_msg_history` | `POST` | 获取好友历史消息 | 获取指定好友的历史聊天记录 |
| `/.handle_quick_operation` | `POST` | 处理快速操作 | 处理来自事件上报的快速操作请求 |
| `/set_group_portrait` | `POST` | 设置群头像 | 修改指定群聊的头像 |
| `/upload_private_file` | `POST` | 上传私聊文件 | 上传本地文件到指定私聊会话中 |
| `/_get_model_show` | `POST` | 获取机型显示 | 获取当前账号可用的设备机型显示名称列表 |
| `/_set_model_show` | `POST` | 设置机型 | 设置当前账号的设备机型名称 |
| `/delete_group_file` | `POST` | 删除群文件 | 在群文件系统中删除指定的文件 |
| `/create_group_file_folder` | `POST` | 创建群文件目录 | 在群文件系统中创建新的文件夹 |
| `/delete_group_folder` | `POST` | 删除群文件目录 | 在群文件系统中删除指定的文件夹 |
| `/get_group_file_system_info` | `POST` | 获取群文件系统信息 | 获取群聊文件系统的空间及状态信息 |
| `/get_group_files_by_folder` | `POST` | 获取群文件夹文件列表 | 获取指定群文件夹下的文件及子文件夹列表 |

## 消息接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/forward_friend_single_msg` | `POST` | 转发单条消息 | 转发单条消息 |
| `/forward_group_single_msg` | `POST` | 转发单条消息 | 转发单条消息 |
| `/mark_group_msg_as_read` | `POST` | 标记群聊已读 | 标记指定渠道的消息为已读 |
| `/mark_private_msg_as_read` | `POST` | 标记私聊已读 | 标记指定渠道的消息为已读 |
| `/get_msg` | `POST` | 获取消息 | 根据消息 ID 获取消息详细信息 |
| `/send_private_msg` | `POST` | 发送私聊消息 | 发送私聊消息 |
| `/send_msg` | `POST` | 发送消息 | 发送私聊或群聊消息 |
| `/delete_msg` | `POST` | 撤回消息 | 撤回已发送的消息 |
| `/mark_msg_as_read` | `POST` | 标记消息已读 (Go-CQHTTP) | 标记指定渠道的消息为已读 |
| `/_mark_all_as_read` | `POST` | 标记所有消息已读 | - |

## 文件扩展

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/move_group_file` | `POST` | 移动群文件 | - |
| `/rename_group_file` | `POST` | 重命名群文件 | - |
| `/trans_group_file` | `POST` | 传输群文件 | - |
| `/create_flash_task` | `POST` | 创建闪传任务 | - |
| `/get_flash_file_list` | `POST` | 获取闪传文件列表 | - |
| `/get_flash_file_url` | `POST` | 获取闪传文件链接 | - |
| `/send_flash_msg` | `POST` | 发送闪传消息 | - |
| `/get_share_link` | `POST` | 获取文件分享链接 | - |
| `/get_fileset_info` | `POST` | 获取文件集信息 | - |
| `/get_online_file_msg` | `POST` | 获取在线文件消息 | - |
| `/send_online_file` | `POST` | 发送在线文件 | - |
| `/send_online_folder` | `POST` | 发送在线文件夹 | - |
| `/receive_online_file` | `POST` | 接收在线文件 | - |
| `/refuse_online_file` | `POST` | 拒绝在线文件 | - |
| `/cancel_online_file` | `POST` | 取消在线文件 | - |
| `/download_fileset` | `POST` | 下载文件集 | - |
| `/get_fileset_id` | `POST` | 获取文件集 ID | - |

## 用户扩展

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/get_friends_with_category` | `POST` | 获取带分组的好友列表 | - |
| `/get_profile_like` | `POST` | 获取资料点赞 | - |
| `/set_diy_online_status` | `POST` | 设置自定义在线状态 | 设置自定义在线状态 |
| `/get_unidirectional_friend_list` | `POST` | 获取单向好友列表 | - |

## 频道接口

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/get_guild_list` | `POST` | 获取频道列表 | 获取当前帐号已加入的频道列表 |
| `/get_guild_service_profile` | `POST` | 获取频道个人信息 | 获取当前帐号在频道中的个人资料 |

## AI 扩展

| 端点 (Endpoint) | 请求方式 | 摘要 | 说明 |
| :--- | :--- | :--- | :--- |
| `/get_ai_record` | `POST` | 获取 AI 语音 | 通过 AI 语音引擎获取指定文本的语音 URL |
| `/send_group_ai_record` | `POST` | 发送群 AI 语音 | 发送 AI 生成的语音到指定群聊 |

## 数据模型 / Schemas

### `BaseResponse`
| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `status` | `string` | 状态 (ok/failed) |
| `retcode` | `number` | 返回码 |
| `data` | `any` | 业务数据（具体结构由各接口定义） |
| `message` | `string` | 消息 |
| `wording` | `string` | 提示 |
| `stream` | `string` | 流式响应 |

### `EmptyData`
无数据

*无特殊字段定义或为空对象*

### `FileBaseData`
文件消息段基础数据

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `file` | `string` | 文件路径/URL/file:/// |
| `path` | `string` | 文件路径 |
| `url` | `string` | 文件URL |
| `name` | `string` | 文件名 |
| `thumb` | `string` | 缩略图 |

### `OB11MessageAt`
@消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageContact`
联系人消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageCustomMusic`
自定义音乐消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageData`
OneBot 11 消息段

*无特殊字段定义或为空对象*

### `OB11MessageDice`
骰子消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageFace`
QQ表情消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageFileBase`
文件消息基础接口

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `data` | `any` | - |

### `OB11MessageFile`
文件消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `any` | - |

### `OB11MessageFlashTransfer`
QQ闪传消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageForward`
合并转发消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageIdMusic`
ID音乐消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageImage`
图片消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageJson`
JSON消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageLocation`
位置消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageMFace`
商城表情消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageMarkdown`
Markdown消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageMiniApp`
小程序消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageMixType`
OneBot 11 消息混合类型

*无特殊字段定义或为空对象*

### `OB11MessageNode`
合并转发消息节点

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageOnlineFile`
在线文件消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessagePoke`
戳一戳消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageRPS`
猜拳消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageRecord`
语音消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `any` | - |

### `OB11MessageReply`
回复消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11Message`
OneBot 11 完整消息对象

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `real_seq` | `string` | 真实序列号 |
| `temp_source` | `number` | 临时会话来源 |
| `message_sent_type` | `string` | 消息发送类型 |
| `target_id` | `number` | 目标ID |
| `self_id` | `number` | 机器人QQ号 |
| `time` | `number` | 消息时间戳 |
| `message_id` | `number` | 消息ID |
| `message_seq` | `number` | 消息序列号 |
| `real_id` | `number` | 真实ID |
| `user_id` | `any` | 发送者QQ号 |
| `group_id` | `any` | 群号 |
| `group_name` | `string` | 群名称 |
| `message_type` | `string` | 消息类型 |
| `sub_type` | `string` | 消息子类型 |
| `sender` | `any` | - |
| `message` | `any` | 消息内容 |
| `message_format` | `string` | 消息格式 |
| `raw_message` | `string` | 原始消息 |
| `font` | `number` | 字体 |
| `post_type` | `string` | 上报类型 |
| `raw` | `object` | 原始消息对象 |
| `emoji_likes_list` | `array` | 表情点赞列表 |

### `OB11MessageText`
纯文本消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11MessageVideo`
视频消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `any` | - |

### `OB11MessageXml`
XML消息段

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `type` | `string` | - |
| `data` | `object` | - |

### `OB11PostSendMsg`
OneBot 11 发送消息请求

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `message_type` | `string` | 消息类型 |
| `user_id` | `string` | 用户QQ号 |
| `group_id` | `string` | 群号 |
| `message` | `any` | - |
| `messages` | `any` | - |
| `auto_escape` | `any` | 是否作为纯文本发送 |
| `source` | `string` | 消息来源 |
| `news` | `array` | - |
| `summary` | `string` | 摘要 |
| `prompt` | `string` | 提示 |
| `time` | `string` | 时间 |

### `OB11Sender`
OneBot 11 发送者信息

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `user_id` | `any` | 发送者QQ号 |
| `nickname` | `string` | 发送者昵称 |
| `card` | `string` | 群名片 |
| `role` | `string` | 角色 |
| `sex` | `string` | 性别 |
| `age` | `number` | 年龄 |
| `area` | `string` | 地区 |
| `level` | `string` | 等级 |
| `title` | `string` | 头衔 |

### `OB11GroupMember`
OneBot 11 群成员信息

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `group_id` | `number` | 群号 |
| `user_id` | `number` | QQ号 |
| `nickname` | `string` | 昵称 |
| `card` | `string` | 名片 |
| `sex` | `string` | 性别 |
| `age` | `number` | 年龄 |
| `join_time` | `number` | 入群时间戳 |
| `last_sent_time` | `number` | 最后发言时间戳 |
| `level` | `string` | 等级 |
| `qq_level` | `number` | QQ等级 |
| `role` | `string` | 角色 (owner/admin/member) |
| `title` | `string` | 头衔 |
| `area` | `string` | 地区 |
| `unfriendly` | `boolean` | 是否不良记录 |
| `title_expire_time` | `number` | 头衔过期时间 |
| `card_changeable` | `boolean` | 是否允许修改名片 |
| `shut_up_timestamp` | `number` | 禁言截止时间戳 |
| `is_robot` | `boolean` | 是否为机器人 |
| `qage` | `number` | Q龄 |

### `OB11Group`
OneBot 11 群信息

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `group_all_shut` | `number` | 是否全员禁言 |
| `group_remark` | `string` | 群备注 |
| `group_id` | `number` | 群号 |
| `group_name` | `string` | 群名称 |
| `member_count` | `number` | 成员人数 |
| `max_member_count` | `number` | 最大成员人数 |

### `OB11ActionMessage`
OneBot 11 消息信息

*无特殊字段定义或为空对象*

### `OB11Notify`
OneBot 11 通知信息

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `request_id` | `number` | 请求ID |
| `invitor_uin` | `number` | 邀请者QQ |
| `invitor_nick` | `string` | 邀请者昵称 |
| `group_id` | `number` | 群号 |
| `group_name` | `string` | 群名称 |
| `message` | `string` | 附言 |
| `checked` | `boolean` | 是否已处理 |
| `actor` | `number` | 操作者QQ |
| `requester_nick` | `string` | 申请者昵称 |

### `OB11User`
OneBot 11 用户信息

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `birthday_year` | `number` | 出生年份 |
| `birthday_month` | `number` | 出生月份 |
| `birthday_day` | `number` | 出生日期 |
| `phone_num` | `string` | 手机号 |
| `email` | `string` | 邮箱 |
| `category_id` | `number` | 分组ID |
| `user_id` | `number` | QQ号 |
| `nickname` | `string` | 昵称 |
| `remark` | `string` | 备注 |
| `sex` | `string` | 性别 |
| `level` | `number` | 等级 |
| `age` | `number` | 年龄 |
| `qid` | `string` | QID |
| `login_days` | `number` | 登录天数 |
| `categoryName` | `string` | 分组名称 |
| `categoryId` | `number` | 分组ID |

### `OB11LatestMessage`
最后一条消息

| 字段 | 类型 | 说明 / 描述 |
| :--- | :--- | :--- |
| `self_id` | `number` | 发送者QQ号 |
| `user_id` | `number` | 接收者QQ号 |
| `time` | `number` | 时间戳 |
| `real_seq` | `string` | 消息序号 |
| `message_type` | `string` | 消息类型 |
| `sender` | `object` | - |
| `raw_message` | `string` | 原始消息 |
| `font` | `number` | 字体大小 |
| `sub_type` | `string` | 子类型 |
| `message` | `object` | 消息内容 |
| `message_format` | `string` | 消息格式 |
| `post_type` | `string` | 发布类型 |
| `group_id` | `number` | 群号 |
| `group_name` | `string` | 群名称 |

