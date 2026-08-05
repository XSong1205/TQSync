# NapCat (OneBot v11) 配置指南

TQSync 与 NapCat 之间存在**两条独立的 HTTP 通道**：

*   **上行通道（HTTP 客户端）**：NapCat 主动 POST 事件到 TQSync → TQSync 接收消息/事件
*   **下行通道（HTTP 服务器）**：TQSync 调用 NapCat 的 API → TQSync 发消息、撤回等

两者需要在 NapCat WebUI 中分别配置，缺一不可。

## 1. 访问 NapCat WebUI

启动 NapCat 后，在控制台日志中找到类似以下的地址：
`[WebUi] WebUi Local Panel Url: http://127.0.0.1:6099/webui?token=xxxx`

在浏览器中打开该地址并登录。

## 2. 配置 HTTP 客户端（上行：NapCat → TQSync）

在 WebUI 界面中，按照以下路径操作：

1.  点击左侧菜单的 **"网络配置"** (Network) 或 **"OneBot 配置"**。
2.  点击 **"新建"** 或 **"添加"**。
3.  在弹出的菜单中选择 **HTTP客户端**
4.  填写以下信息：
    *   **上报地址 (URL)**: `http://<你的TQSync服务器IP>:8080/webhook/qq`
        *   如果 TQSync 和 NapCat 在同一台电脑，可以使用 `http://127.0.0.1:8080/webhook/qq`。
        *   端口 `8080` 和路径 `/webhook/qq` 对应 `config.yaml` 中的 `server.qq_webhook_port` 和 `server.webhook_path`。
    *   **密钥 (Secret/Token)**: 可留空。如果填写，TQSync 侧无需额外配置，但建议与下方 HTTP 服务器的 Token 保持一致以便记忆。
    *   **消息格式**: 选择 `string` (CQ码) 或 `array` (推荐 array)。
        *   *注意：此选项仅影响 QQ 发给 TQSync 的格式。TQSync 发给 QQ 时会自动使用标准的数组格式，无需在此处额外配置。*
5.  点击 **启用** 按钮并保存。

## 3. 配置 HTTP 服务器（下行：TQSync → NapCat）

在WebUI中执行如下操作：

1.  点击左侧菜单的**网络配置**
2.  点击 **'新建'**
3.  在弹出菜单中选择 **HTTP服务器**
4.  填写信息：
    *   **Host**: `0.0.0.0`（允许远程访问）或 `127.0.0.1`（仅本机访问，推荐同机部署时使用）
    *   **Port**: `3000`（必须与 `config.yaml` 中 `qq.napcat_api_url` 的端口一致）
    *   **启用 CORS**: 建议勾选
    *   **启用 WebSocket**: 建议勾选
    *   **Token**: 必须与 `config.yaml` 中的 `qq.access_token` 一致（默认 `1111111`）
5.  点击 **启用** 按钮并保存。

## 4. 验证配置

1.  确保 TQSync 已经运行（Windows: `venv\Scripts\python.exe main.py`；Linux: 运行 `bash scripts/tqsync.sh start` 后台启动）。
2.  观察 TQSync 控制台输出，应同时看到：
    *   `QQ Webhook server started on port 8080`（表明 TQSync 已启动接收服务）
    *   无 `OneBot API` 相关报错（表明 TQSync 能正常连接 NapCat 的 HTTP 服务器）
3.  在 QQ 群组中发送一条测试消息，TQSync 控制台应有相应日志输出。
4.  如果 TQSync 成功将消息转发到 Telegram，则说明上下行通道均已正常工作。

## 常见问题

*   **找不到“网络配置”？**
    不同版本的 NapCat WebUI 布局可能略有不同。请寻找带有 **"Client"**、**"Post"**、**"上报"** 或 **"OneBot"** 字样的选项。
*   **连接失败 / TQSync 收不到消息？**
    请检查防火墙是否放行了 TQSync 的监听端口（默认为 `8080`），并确认 HTTP 客户端的上报 URL 端口和路径是否正确。
*   **TQSync 能收到消息但发不出去？**
    检查 HTTP 服务器的 **Token** 是否与 `config.yaml` 中的 `qq.access_token` 一致，以及端口 `3000` 未被其他程序占用。
