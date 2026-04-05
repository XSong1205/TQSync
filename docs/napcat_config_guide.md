# NapCat (OneBot v11) 配置指南

为了让 TQSync 能够接收来自 QQ 的消息，你需要正确配置 NapCat 的 **HTTP 上报**（也称为 HTTP 客户端或 Webhook）。

## 1. 访问 NapCat WebUI

启动 NapCat 后，在控制台日志中找到类似以下的地址：
`[WebUi] WebUi Local Panel Url: http://127.0.0.1:6099/webui?token=xxxx`

在浏览器中打开该地址并登录。

## 2. 配置 HTTP 客户端 (关键步骤)

在 WebUI 界面中，按照以下路径操作：

1.  点击左侧菜单的 **“网络配置”** (Network) 或 **“OneBot 配置”**。
2.  点击 **“新建”** 或 **“添加”**。
3.  在弹出的菜单中选择 **HTTP客户端**
4.  填写以下信息：
    *   **上报地址 (URL)**: `http://<你的TQSync服务器IP>:8080/webhook/qq`
        *   如果 TQSync 和 NapCat 在同一台电脑，可以使用 `http://127.0.0.1:8080/webhook/qq`。
    *   **密钥 (Secret/Token)**: 使用napcat默认的即可，为了安全性不要留空。
    *   **消息格式**: 选择 `string` (CQ码) 或 `array` (推荐 array)。
        *   *注意：此选项仅影响 QQ 发给 TQSync 的格式。TQSync 发给 QQ 时会自动使用标准的数组格式，无需在此处额外配置。*
5.  点击 **启用** 按钮并保存。

## 3. 配置 HTTP 服务器

在WebUI中执行如下操作：

1.  点击左侧菜单的**网络配置**
2.  点击 **'新建'**
3.  在弹出菜单中选择 **HTTP服务器**
4.  填写信息：
    *  **Host/Port**：保持和config.yaml一致
    *  **CORS/WebSocket**:启用
    *  **Token**:保持和上面的一致


## 4. 验证配置

1.  确保 TQSync 已经运行 (`python main.py`)。
2.  在 QQ 群组中发送一条测试消息。
3.  观察 TQSync 的控制台输出，如果看到 `QQ Webhook server started` 且没有报错，说明配置成功。

## 常见问题

*   **找不到“HTTP 上报”？**
    不同版本的 NapCat WebUI 布局可能略有不同。请寻找带有 **"Client"**、**"Post"** 或 **"上报"** 字样的选项。它代表 NapCat 主动向你的程序发送数据。
*   **连接失败？**
    请检查防火墙是否放行了 TQSync 的监听端口（默认为 `8080`）。
