# WebUI 控制台开发指南

TQSync 的管理面板位于 `web/` 目录，由 FastAPI 以纯静态文件方式托管（`main.py` 中
`admin_app.mount("/", StaticFiles(directory="web", html=True))`），访问
`http://localhost:8081/` 即可。

## 设计语言

界面参考 [Miuix](https://github.com/compose-miuix-ui/miuix)——小米 HyperOS / MIUI 风格的
Compose Multiplatform 组件库——的视觉语言：

- 大圆角卡片（20px）+ 分组列表 + 内嵌细分隔线
- 大标题随滚动折叠为毛玻璃（backdrop-filter）顶栏
- 胶囊按钮、MIUI 风格开关、分段控件、底部动作面板、弹簧动效
- 移动端优先：底部标签栏 + 安全区适配 + 下拉刷新 + 触觉反馈
- 宽屏（≥900px）自动切换为左侧导航栏布局
- 明 / 暗 / 跟随系统三种主题（暗色为纯黑 OLED 背景）

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
        ├── dashboard.js    # 概览：状态、指标、24h 图表、快捷操作、最近日志
        ├── config.js       # 配置：分区编辑、脏数据跟踪、批量保存
        ├── bindings.js     # 成员：绑定关系 / 屏蔽词 / 管理员
        ├── plugins.js      # 插件：启停、重载、上传、键值数据编辑
        ├── logs.js         # 运行日志：级别着色、筛选、自动刷新（二级页）
        └── settings.js     # 设置：同步方向、外观、安全、重启、关于
```

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
