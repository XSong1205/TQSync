# NapCat (OneBot v11) 配置指南

为了让 TQSync 能够接收来自 QQ 的消息，你需要正确配置 NapCat 的 **HTTP 上报**（也称为 HTTP 客户端或 Webhook）。

## 1. 访问 NapCat WebUI

启动 NapCat 后，在控制台日志中找到类似以下的地址：
`[WebUi] WebUi Local Panel Url: http://127.0.0.1:6099/webui?token=xxxx`

在浏览器中打开该地址并登录。

## 2. 配置 HTTP 上报 (关键步骤)

在 WebUI 界面中，按照以下路径操作：

1.  点击左侧菜单的 **“网络配置”** (Network) 或 **“OneBot 配置”**。
2.  找到 **“HTTP 客户端”** 或 **“HTTP 上报”** (HTTP Client / Post) 选项卡。
    *   *注意：不要与“HTTP 服务器”混淆，那是用来接收 API 调用的。*
3.  点击 **“新建”** 或 **“添加”**。
4.  填写以下信息：
    *   **上报地址 (URL)**: `http://<你的TQSync服务器IP>:8080/webhook/qq`
        *   如果 TQSync 和 NapCat 在同一台电脑，可以使用 `http://127.0.0.1:8080/webhook/qq`。
    *   **密钥 (Secret/Token)**: 留空（除非你在 TQSync 配置中设置了验证）。
    *   **消息格式**: 选择 `string` (CQ码) 或 `array` (推荐 array，但 TQSync 目前主要处理文本，两者皆可)。
5.  点击 **“保存”** 或 **“启用”**。

## 3. 验证配置

1.  确保 TQSync 已经运行 (`python main.py`)。
2.  在 QQ 群组中发送一条测试消息。
3.  观察 TQSync 的控制台输出，如果看到 `QQ Webhook server started` 且没有报错，说明配置成功。

## 常见问题

*   **找不到“HTTP 上报”？**
    不同版本的 NapCat WebUI 布局可能略有不同。请寻找带有 **"Client"**、**"Post"** 或 **"上报"** 字样的选项。它代表 NapCat 主动向你的程序发送数据。
*   **连接失败？**
    请检查防火墙是否放行了 TQSync 的监听端口（默认为 `8080`）。
