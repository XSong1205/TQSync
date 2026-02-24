# TQSync

一个功能完整的 Telegram-QQ 跨平台消息同步机器人，目前支持双平台间简单的文字图片消息同步等功能。由我和Qwen创作

## 🌟 主要特性

- **数据库持久化** - 用户绑定和消息映射永久保存
- **用户绑定系统** - 基于验证码的双向平台绑定
- **精准撤回同步** - 跨平台消息精确删除
- **原生回复支持** - 保持平台原生交互体验
- **媒体文件同步** - 图片、视频、语音等完整支持
- **转发消息解析** - 智能解析QQ合并转发
- **消息重试机制** - 自动重试失败消息
- **智能过滤系统** - 支持前缀命令和消息过滤

## 🚀 快速开始

### 环境要求
- Python 3.14 (更低版本没试过)
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

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件填入你的配置

# 测试功能
python test_database_persistence.py
python test.py

# 启动机器人
python main.py
```

## Linux 支持

TQSync 支持 Linux 系统 (AI说的)

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

## 📖 文档

- [使用说明](USAGE.md)
- [更新日志](CHANGELOG.md)
- [GitHub 发布指南](GITHUB_PUBLISH_GUIDE.md)

