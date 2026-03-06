# TQSync .gitignore 配置说明

## 📋 概述

`.gitignore` 文件用于指定 Git 应该忽略的文件和目录，避免将敏感信息、临时文件、编译产物等提交到版本控制系统。

## 🔧 主要分类

### 1. **Python 相关**

```gitignore
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
...
```

- Python 编译产物
- 包构建目录
- Python 环境文件

### 2. **虚拟环境**

```gitignore
.venv/
venv/
ENV/
env/
.env.local
.env.production
```

- Python 虚拟环境目录
- 本地和生产环境变量（保留 `.env.example`）

### 3. **日志和数据库**

```gitignore
logs/
data/
temp/
*.db
*.sqlite
*.log
*.backup
```

- **重要**：忽略日志文件、数据库文件、临时数据
- 这些目录包含运行时数据和敏感信息

### 4. **配置文件**

```gitignore
.env
config.yaml
*.backup
```

- **重要**：忽略实际配置文件
- 保留模板文件：`.env.example` 和 `config.yaml.example`

### 5. **IDE 配置**

```gitignore
.lingma/
.idea/
.vscode/
*.swp
*.swo
*~
```

- 各种 IDE 的配置目录
- 编辑器临时文件

### 6. **操作系统文件**

```gitignore
.DS_Store
Thumbs.db
Desktop.ini
```

- macOS: `.DS_Store`
- Windows: `Thumbs.db`, `Desktop.ini`

### 7. **媒体文件**

```gitignore
media/
uploads/
cache/
```

- 可选：根据项目需求决定是否忽略
- TQSync 的媒体文件通常是临时的

### 8. **测试文件**

```gitignore
test_*.py
demo_*.py
*_test.py
!test_ssl_fix.py
!test_telegram_fix.py
!test_message_id_mapping.py
!test_telegram_media.py
```

- 忽略可能包含敏感信息的测试文件
- **例外**：公开的测试脚本（使用 `!` 取消忽略）

### 9. **TQSync 特定配置**

```gitignore
# Private keys and secrets
*.pem
*.key
*.crt
secrets/
credentials/

# Local scripts and custom configurations
local_*.py
local_*.yaml
local_*.json
custom_*.py
custom_*.yaml
```

- 私钥和证书文件
- 本地自定义配置
- 凭证信息

## 🎯 关键策略

### 保留 vs 忽略

| 文件类型 | 保留 | 忽略 | 说明 |
|---------|------|------|------|
| 配置模板 | ✅ `.env.example` | ❌ | 提供配置参考 |
| 实际配置 | ❌ | ✅ `.env` | 包含敏感信息 |
| 数据库 | ❌ | ✅ `*.db` | 用户数据不应提交 |
| 日志 | ❌ | ✅ `*.log` | 运行日志，体积大 |
| 测试脚本 | ⚠️ 部分 | ⚠️ 部分 | 公开测试保留 |

### 白名单机制

使用 `!` 可以取消之前的忽略规则：

```gitignore
# 忽略所有 test_*.py
test_*.py

# 但保留这些公开测试脚本
!test_ssl_fix.py
!test_telegram_fix.py
!test_message_id_mapping.py
!test_telegram_media.py
```

## 📁 项目结构示例

```
TQSync/
├── .gitignore          # ✅ 保留
├── .env.example        # ✅ 保留（配置模板）
├── config.yaml.example # ✅ 保留（配置模板）
├── .env                # ❌ 忽略（实际配置）
├── config.yaml         # ❌ 忽略（实际配置）
├── data/               # ❌ 忽略（数据库）
│   └── tqsync.db
├── logs/               # ❌ 忽略（日志）
│   └── bot.log
├── temp/               # ❌ 忽略（临时文件）
├── bots/               # ✅ 保留（源代码）
├── core/               # ✅ 保留（源代码）
├── utils/              # ✅ 保留（工具模块）
├── test_ssl_fix.py     # ✅ 保留（公开测试）
└── test_private.py     # ❌ 忽略（私有测试）
```

## 🔍 验证 .gitignore

### 检查哪些文件会被忽略

```bash
# 查看当前被忽略的文件
git status --ignored

# 检查特定文件是否被忽略
git check-ignore -v <file_path>
```

### 测试 .gitignore 规则

```bash
# 创建一个测试文件
touch test_ignore.tmp

# 查看是否被忽略
git status

# 强制添加（不推荐）
git add -f test_ignore.tmp
```

## ⚠️ 常见错误

### 错误 1：忽略了已经追踪的文件

如果文件之前已经被 Git 追踪，修改 `.gitignore` 不会自动忽略它。

**解决方案**：
```bash
# 从 Git 缓存中移除
git rm --cached <file>

# 提交更改
git commit -m "Remove sensitive file from tracking"
```

### 错误 2：忘记忽略敏感文件

**紧急处理**：
1. 立即添加到 `.gitignore`
2. 从历史中删除（如果需要）：
   ```bash
   git filter-branch --force --index-filter \
     'git rm --cached --ignore-unmatch <file>' \
     --prune-empty --tag-name-filter cat -- --all
   ```
3. 强制推送：
   ```bash
   git push origin --force --all
   ```

### 错误 3：过度忽略

导致正常文件无法提交。

**解决方案**：
- 使用 `!` 创建例外
- 细化忽略规则
- 使用更具体的路径

## 🛡️ 安全建议

### 必须忽略的文件

- ✅ `.env` - 包含 API Token
- ✅ `config.yaml` - 包含配置信息
- ✅ `*.db` - 包含用户数据
- ✅ `*.log` - 可能泄露敏感信息
- ✅ `*.key`, `*.pem` - 私钥文件

### 可以保留的文件

- ✅ 源代码文件（`.py`）
- ✅ 配置模板（`.example`）
- ✅ 文档（`.md`）
- ✅ 公开测试脚本

## 📚 相关资源

- [GitHub .gitignore 模板](https://github.com/github/gitignore)
- [Git 官方文档 - Ignoring files](https://git-scm.com/docs/gitignore)
- [Atlassian .gitignore 指南](https://www.atlassian.com/git/tutorials/saving-changes/gitignore)

---

*更新日期：2026-02-25*
*TQSync 项目文档*
