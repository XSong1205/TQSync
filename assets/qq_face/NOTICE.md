# QQ 表情原图资源

本目录内置了 QQ 系统表情（小黄脸）的静态 PNG 原图，用于把「纯表情消息」原样转发到 Telegram。

## 来源

- 仓库：<https://github.com/koishijs/QFace>（MIT License）
- 路径：`public/assets/qq_emoji/<id>/png/<id>.png`
- 内置范围：id ≤ 199 且上游存在的 109 个表情（约 1.6 MB），文件名即 OneBot `face.id`

## 版权说明

上游仓库以 MIT 协议发布其代码与整理工作，但**表情美术资源的著作权归腾讯所有**。
本仓库内置这些图片仅用于自建机器人把 QQ 消息转发到 Telegram 时的显示需求；
如需对外分发或商用，请自行评估并替换为自有资源。

## 用法

- 图文混排消息：用 `[微笑]` 之类的文本占位（`utils/qq_text.format_qq_face`）；
- 纯表情消息：直接发送本目录下的原图（`utils/qq_text.face_image_path`）；
- 找不到对应 id 的图片时自动回退为文本占位。

更新资源：重新从上游拉取同路径文件覆盖本目录即可，文件名不要改。
