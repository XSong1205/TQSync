![路边野狗](https://files.seeusercontent.com/2026/04/05/Qi0u/Screenshot_2026-04-05-08-40-33-0.jpg)

> [!TIP]
> 抱歉各位，这人太恶心了，只能先挂到仓库一段时间，影响大家的心情实在抱歉



# TQSync

不完整的 Telegram-QQ 跨平台消息同步机器人，目前支持双平台间简单的文字图片消息同步等功能。由我和Qwen创作

## 🌟 主要特性

- **数据库持久化** - 用户绑定和消息映射永久保存
- **用户绑定系统** - 基于验证码的双向平台绑定
- **精准撤回同步** - 跨平台消息精确删除
- **原生回复支持** - 保持平台原生交互体验
- **媒体文件同步** - 图片、视频、语音等完整支持
- **转发消息解析** - 智能解析QQ合并转发
- **消息重试机制** - 自动重试失败消息
- **智能过滤系统** - 支持前缀命令和消息过滤

## 📖 演示截图

## 🚀 快速开始

### 环境要求
- Python 3.14 + (更低版本没试过)
- 能连接 Telegram 的网络
- NapCatQQ 较新版本
- Windows Server 2016 及以上；能安装 Python 3.14 的 Linux 系统

### 安装步骤
```bash
# 克隆仓库
git clone https://github.com/XSong1205/TQSync.git
cd TQSync

# 运行安装脚本
python install.py

# 初始化 Bot
python init.py
# 编辑 .env 或 config.yaml 文件填入你的配置
> Telegram的机器人创建详见仓库中 TGBotGuide.md

# 测试功能
python test_database_persistence.py
python test.py

# 启动 NapCat
安装 NapCat，然后创建一个HTTP Server 和 Websocket Server，端口默认；您也可以通过初始化后的.env文件对端口进行更改来自定义

# 启动机器人
python main.py
```

## Linux 支持

警告：目前 TQSync **没有**在 Linux 环境上进行过**任何**测试，能不能跑起来我也不知道（）

### Linux 快速安装
```bash
# Ubuntu/Debian
git clone https://github.com/XSong1205/TQSync.git
cd TQSync
chmod +x install_linux.sh
./install_linux.sh

# 或手动安装
pip3 install -r requirements.txt
mkdir -p logs data temp
cp .env.example .env
cp config.yaml.template config.yaml
```

### Linux 运行
```bash
# 测试功能
python3 test_database_persistence.py
python3 test.py

# 启动机器人
python3 main.py

# 后台运行
nohup python3 main.py > bot.log 2>&1 &
```

## 代理配置方法

编辑 `config.yaml` 文件：

```yaml
telegram:
  token: "YOUR_TELEGRAM_BOT_TOKEN"
  chat_id: "YOUR_TELEGRAM_CHAT_ID"
  proxy:
    enable: true
    type: "socks5"  # 或 "http"
    host: "127.0.0.1"
    port: 1080
    username: ""  # 可选
    password: ""  # 可选
```

