# WebUI 控制台开发指南

TQSync 的管理面板位于 `web/` 目录，由 FastAPI 以纯静态文件方式托管（`main.py` 中
`admin_app.mount("/", StaticFiles(directory="web", html=True))`），访问
`http://localhost:8081/` 即可。

## 设计语言

界面遵循 [Miuix](https://github.com/compose-miuix-ui/miuix)（HyperOS / MIUI 风格的
Compose Multiplatform 组件库）的官方默认视觉规格，而不是自创样式：

- **配色直接取自 Miuix `lightColorScheme()` / `darkColorScheme()`**
  - 浅色：页面背景 `#F7F7F7`、卡片 `#FFFFFF`、正文 `#000000`、分区标题 `#8C93B0`、
    分隔线 `#E0E0E0`、主色 `#3482FF`
  - 深色：页面背景 `#000000`、卡片 `#242424`、正文 `#F2F2F2`、分区标题 `#787E96`、
    分隔线 `#393939`、主色 `#277AF7`
- 组件按官方默认值实现：卡片/按钮圆角 16px、输入框 12px、弹窗 28px；
  卡片**无投影**、分组列表**无行间分割线**、按钮为圆角矩形（非胶囊）
- 底部导航对齐 Miuix `NavigationBar`：选中项为正文色 + 加粗，未选中项 40% 透明度，
  无选中胶囊背景；宽屏（≥900px）切换为左侧 `NavigationRail` 布局
- 大标题随滚动折叠为毛玻璃顶栏；保留下拉刷新、触觉反馈与轻量过渡动效
- 移动端优先：安全区适配、44px 触控目标、1.5 秒指标轮询的监控型概览页
- 明 / 暗 / 跟随系统三种主题（暗色使用官方纯黑背景 + #242424 卡片）
- **尺寸与触控规范**：
  - 严格遵循**触控目标 ≥44px** 原则：图标按钮（`iconButton`）为 44×44px，搜索框（`searchBar`）高度 44px；
  - 普通按钮（`button`）默认高度 40px；页面内的主要操作按钮（新增/上传/保存等）按 44px 放大以保证触控；分段控件（`segmented`）高度 40px；
  - 日志页：搜索框 44px、分段控件 40px、日志块圆角与卡片一致（16px）。
- **令牌命名规范（字号与颜色解耦）**：
  - 字号统一使用 `--mi-text-size-*`（如 `--mi-text-size-secondary: 14px`）；
  - 颜色统一使用 `--mi-text-*`（如 `--mi-text-secondary` 是颜色）；
  - 两者严禁同名（历史曾因同名导致 3 处 `font-size` 失效）。
- **浮层行为与无障碍**：
  - **栈式关闭**：按 `Esc` 只关闭栈顶浮层，不连带关闭多层；
  - **焦点陷阱**：弹窗打开后启用焦点陷阱，关闭后焦点自动归还触发元素。

**零依赖、零构建**：不使用 Vue / Element Plus / CDN，全部为原生 ES Module + CSS，
断网环境也能正常打开，升级后无需清缓存（后端已对静态资源下发 `Cache-Control: no-cache`）。

## 目录结构

```
web/
├── index.html              # 应用外壳（启动占位 / 登录 / 根容器）
├── assets/
│   ├── miuix.css           # 设计令牌 + Miuix 组件样式
│   └── app.css             # 应用框架：导航、顶栏、页面容器、下拉刷新
└── js/
    ├── app.js              # 启动流程、登录、路由、页面生命周期、下拉刷新
    ├── api.js              # API 客户端（X-API-Key / 超时 / 错误归一化）
    ├── ui.js               # 组件库：card/row/switch/field/dialog/sheet/toast…
    ├── icons.js            # 48 个内联 SVG 线条图标
    ├── theme.js            # auto/light/dark 主题管理
    └── pages/
        ├── dashboard.js    # 概览：状态监控（1.5s 轮询）、指标、24h 图表、快捷操作、最近日志
        ├── config.js       # 配置：配置项分页（分区编辑/批量保存）+ 消息过滤分页（屏蔽词）
        ├── bindings.js     # 用户：绑定关系 / 管理员
        ├── plugins.js      # 插件：启停、重载、上传、键值数据编辑
        ├── logs.js         # 运行日志（主导航）：级别着色、筛选、自动刷新
        └── settings.js     # 设置：同步方向、外观、安全、系统、关于
```

> 信息架构：主导航共 6 项（概览 / 配置 / 用户 / 插件 / 日志 / 设置），日志不再藏在二级页；
> 概览页只做状态监控，不放同步方向等设置项；屏蔽词属于消息过滤策略，
> 入口在「配置 → 消息过滤」分页，不再混在用户管理里。

## 监控与指标口径

- 概览页「运行指标」每 **1.5 秒**轮询一次 `GET /admin/status`；24 小时统计与最近日志
  每 15 秒刷新一次；页面不可见时自动暂停轮询。
- 「内存」显示进程的 **USS（独占物理内存）**，比 RSS 更接近任务管理器里的实际占用；
  平台不支持 `memory_full_info()` 时自动回退到 RSS。
- **插件状态口径**：插件包含「启停状态」（已启用 / 已禁用）与「加载状态」（已加载 / 加载失败 / 未启用）。其中 disabled 的插件属于「未启用」，**不算加载失败**。
- **业务计数口径**：绑定关系计数一律用「**条**」（如“共 6 条绑定”）；管理员计数一律用「**位**」（如“共 2 位管理员”）。

## 新增一个页面

页面模块默认导出一个对象：

```js
export default {
  id: 'example',        // 路由 id，对应 #/example
  label: '示例',         // 导航文案
  icon: 'sparkle',      // icons.js 中的图标名
  tab: true,            // true=主导航；false=二级页（顶栏出现返回键）
  parent: 'dashboard',  // 二级页归属的标签（用于高亮父级与返回）
  title: '示例页面',
  subtitle: '副标题',
  async mount(root, ctx) {
    root.appendChild(ctx.ui.card({ children: [ctx.ui.row({ title: 'Hello' })] }));
    ctx.onRefresh(async () => { /* 下拉刷新 / 顶栏刷新按钮触发 */ });
    ctx.onCleanup(() => { /* 清理定时器等 */ });
  },
};
```

然后在 `js/app.js` 的 `PAGES` 数组里注册即可。

`ctx` 提供：`api`、`ui`（整个组件库）、`state`（全局状态如 `version`）、
`isStale()`、`onRefresh()`、`onCleanup()`、`go()`、`back()`、`setHero()`、
`setAppbarActions()`、`toast()`、`toastErr()`、`confirm()`、`dialog()`、
`actionSheet()`、`openSheet()`、`copyText()`、`formatUptime()` 等。

## 本地预览（不启动机器人）

真实机器人需要 Telegram / NapCat 才能运行，调试界面时可用内置的 Mock 服务：

```bash
# 需先安装 requirements.txt（fastapi / uvicorn）
python scripts/webui_preview.py --port 8099

# 浏览器打开 http://127.0.0.1:8099/
# 管理密钥：preview-key（可用 --api-key 自定义）
```

Mock 服务会原样托管 `web/`，并按 `api/admin_api.py` 的契约返回演示数据（5 个插件、
6 条绑定、屏蔽词、日志、24h 统计等），所有修改仅保存在内存中，重启即恢复。

## 接口约定

- 所有 `/admin/*` 请求需带 `X-API-Key`（即 `config.yaml` 的 `server.admin_api_key`）。
- 配置保存优先调用 `PUT /admin/config/batch`（一次往返），后端不支持时自动退化为
  逐条 `PUT /admin/config/{key}`。
- 静态资源统一 `Cache-Control: no-cache`，升级后刷新即可生效。

## 更新提示

WebUI 启动后会**静默检查**一次 GitHub 更新（`GET /admin/update/check`，后端只读执行
`git fetch`，结果缓存 10 分钟），有新提交时弹出 Miuix 对话框展示更新日志：

- 对话框顶部显示 `本地 commit → 远端 commit · 分支 · 提交数`；
- 更新日志逐条列出 commit 短哈希与提交说明（等宽字体）；
- 「忽略此版本」会记住该远端 commit，之后不再自动打扰，直至出现更新的提交；
- 「查看变更」在 GitHub 打开对应的 compare 页面（后端从 `origin` 推导仓库地址）；
- 手动检查入口：概览页「快捷操作 → 检查更新」、设置页「关于 → 检查更新」。
  手动检查会跳过缓存（`force=true`）并始终给出结果反馈。

容器部署（`TQSYNC_CONTAINER=1`）没有 `.git` 目录，接口直接返回「请通过
`docker compose pull` 更新镜像」的说明，不会报错。

预览更新弹窗效果：启动 Mock 服务时加上 `--demo-update`：

```bash
python scripts/webui_preview.py --port 8099 --demo-update
```
