#!/usr/bin/env node
/**
 * webui_shots.mjs — TQSync WebUI 无依赖视觉 / 冒烟测试驱动
 * =============================================================================
 * 纯 Node.js（>= 22，内置 fetch / WebSocket）+ 无头 Chrome DevTools Protocol：
 *   - 不依赖 npm 包（不用 Puppeteer / playwright）
 *   - 按 视口 × 主题 × 路由 组合做整页截图（含内部滚动容器的第 2/3 屏）
 *   - 同时采集 console error/warning、未捕获异常、页面指标，输出 report.json
 *   - 任一 console error / 未捕获异常 / 白屏 / 截图缺失 => 进程退出码非 0
 *
 * 用法（默认值即 TQSync 预览环境）：
 *   node scripts/webui_shots.mjs \
 *     --base http://127.0.0.1:8099 \
 *     --out tmp_webui_shots \
 *     --mobile 390x844 --desktop 1440x900 \
 *     --themes light,dark \
 *     --routes dashboard,config,bindings,plugins,settings,logs \
 *     [--only config,logs] [--apikey preview-key] [--chrome <chrome.exe>] \
 *     [--settle 900] [--nav-timeout 20000] [--route-timeout 60000]
 *
 * 输出结构：
 *   tmp_webui_shots/<mobile|desktop>/<light|dark>/<route>-{1,2,3}.png
 *   tmp_webui_shots/report.json
 *
 * 说明：脚本不做 TQSync 专属逻辑，选择器缺失时只是把指标记为 0 / blank=true，
 *       因此可直接用于任意静态页面的自测（见 --base 指向临时 http.server）。
 * =============================================================================
 */

import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const REPO_ROOT = path.resolve(path.dirname(SCRIPT_PATH), '..');

const DEFAULT_CHROME = process.platform === 'win32'
  ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  : 'google-chrome';

const DEFAULTS = {
  base: 'http://127.0.0.1:8099',
  out: path.join(REPO_ROOT, 'tmp_webui_shots'),
  mobile: '390x844',
  desktop: '1440x900',
  themes: 'light,dark',
  routes: 'dashboard,config,bindings,plugins,settings,logs',
  apikey: 'preview-key',
  settle: 900,          // 页面加载完成后的沉降时间（ms）
  navTimeout: 20000,    // 单次导航超时（ms）
  routeTimeout: 60000,  // 单条路由（含 3 张截图）总超时（ms）
  chrome: process.env.CHROME_PATH || DEFAULT_CHROME,
  only: [],             // --only 路由过滤器
};

// ---------------------------------------------------------------------------
// 小工具
// ---------------------------------------------------------------------------

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function withTimeout(promise, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`超时 ${ms}ms: ${label}`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function ts() {
  return new Date().toISOString();
}

/** 解析 --key=value / --key value 形式参数 */
function parseArgs(argv) {
  const opts = { ...DEFAULTS, themeList: DEFAULTS.themes.split(',').map((s) => s.trim()).filter(Boolean) };
  for (let i = 0; i < argv.length; i += 1) {
    const raw = argv[i];
    if (!raw.startsWith('--')) throw new Error(`无法识别的参数: ${raw}`);
    let key;
    let value;
    const eq = raw.indexOf('=');
    if (eq >= 0) {
      key = raw.slice(2, eq);
      value = raw.slice(eq + 1);
    } else {
      key = raw.slice(2);
      // 布尔参数：不消费后续参数
      if (key === 'help' || key === 'h') {
        opts.help = true;
        continue;
      }
      value = argv[i + 1];
      i += 1;
    }
    if (value === undefined) throw new Error(`参数 --${key} 缺少值`);
    switch (key) {
      case 'base': opts.base = value.replace(/\/+$/, ''); break;
      case 'out': opts.out = path.resolve(value); break;
      case 'mobile': opts.mobile = value; break;
      case 'desktop': opts.desktop = value; break;
      case 'themes':
        opts.themeList = value.split(',').map((s) => s.trim()).filter(Boolean);
        break;
      case 'routes':
        opts.routes = value.split(',').map((s) => s.trim()).filter(Boolean);
        break;
      case 'only':
        // 支持 --only=a,b 或多次 --only=a
        opts.only.push(...value.split(',').map((s) => s.trim()).filter(Boolean));
        break;
      case 'apikey': opts.apikey = value; break;
      case 'chrome': opts.chrome = value; break;
      case 'settle': opts.settle = Number(value); break;
      case 'nav-timeout': opts.navTimeout = Number(value); break;
      case 'route-timeout': opts.routeTimeout = Number(value); break;
      case 'help':
      case 'h':
        opts.help = true;
        break;
      default:
        throw new Error(`未知参数: --${key}`);
    }
  }
  // 规范化：默认值里 routes 是逗号分隔字符串，--routes 传入后才是数组
  if (!Array.isArray(opts.routes)) {
    opts.routes = String(opts.routes).split(',').map((s) => s.trim()).filter(Boolean);
  }
  if (!opts.themeList.length) throw new Error('--themes 不能为空');
  if (!Number.isFinite(opts.settle) || opts.settle < 0) throw new Error('--settle 必须是非负数');
  return opts;
}

function printHelp() {
  console.log(`用法: node scripts/webui_shots.mjs [选项]
  --base <url>              被测站点根地址（默认 ${DEFAULTS.base}）
  --out <dir>               截图 / report.json 输出目录（默认 <repo>/tmp_webui_shots）
  --mobile <WxH>            移动端视口（默认 390x844）
  --desktop <WxH>           桌面端视口（默认 1440x900）
  --themes <a,b>            主题列表，写入 localStorage.tqsync_theme（默认 light,dark）
  --routes <a,b>            路由列表，访问 #/<route>（默认 dashboard,config,bindings,plugins,settings,logs）
  --only <a,b>              仅跑指定路由（可与 --routes 叠加过滤）
  --apikey <key>            写入 localStorage.tqsync_api_key（默认 preview-key）
  --chrome <path>           Chrome 可执行文件路径
  --settle <ms>             页面 load 后沉降时间（默认 900）
  --nav-timeout <ms>        单次导航超时（默认 20000）
  --route-timeout <ms>      单条路由总超时（默认 60000）
  --help                    显示本帮助`);
}

/** "390x844" -> {label, width, height} */
function parseViewport(label, raw) {
  const m = /^(\d+)x(\d+)$/.exec(String(raw).trim());
  if (!m) throw new Error(`视口格式应为 WxH，收到: ${label}=${raw}`);
  return { label, width: Number(m[1]), height: Number(m[2]) };
}

function resolveChromePath(preferred) {
  const candidates = [
    preferred,
    process.env.CHROME_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ];
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function killChrome(child) {
  if (!child || child.exitCode !== null) return;
  try {
    if (process.platform === 'win32') {
      // Windows 下 chrome 会派生子进程，必须杀进程树
      spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
    } else {
      child.kill('SIGKILL');
    }
  } catch {
    /* 清理失败不影响主流程 */
  }
}

// ---------------------------------------------------------------------------
// 端口 / Chrome 启动 / 调试地址发现
// ---------------------------------------------------------------------------

function canListen(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.unref();
    srv.once('error', () => resolve(false));
    srv.listen(port, '127.0.0.1', () => srv.close(() => resolve(true)));
  });
}

async function findFreePort(start = 9400, count = 120) {
  for (let port = start; port < start + count; port += 1) {
    // eslint-disable-next-line no-await-in-loop
    if (await canListen(port)) return port;
  }
  // 兜底：让系统分配
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

/** 启动无头 Chrome，返回子进程 */
function launchChrome(opts, port, profileDir, extraArgs = []) {
  const args = [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-gpu',
    '--hide-scrollbars',
    '--force-device-scale-factor=1',
    '--allow-running-insecure-content',
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--window-size=1440,900',
    ...extraArgs,
    'about:blank',
  ];
  const child = spawn(opts.chrome, args, { stdio: 'ignore', windowsHide: true });
  child.once('error', (err) => console.error(`[chrome] 启动失败: ${err.message}`));
  return child;
}

async function fetchJson(url, timeoutMs = 1500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/** 轮询 /json/list，返回第一个页面级 target 的 webSocketDebuggerUrl */
async function waitForPageTarget(port, timeoutMs, child) {
  const deadline = Date.now() + timeoutMs;
  let lastErr = null;
  while (Date.now() < deadline) {
    if (child && child.exitCode !== null) {
      throw new Error(`Chrome 提前退出（exitCode=${child.exitCode}），无法连接调试端口 ${port}`);
    }
    try {
      // eslint-disable-next-line no-await-in-loop
      const targets = await fetchJson(`http://127.0.0.1:${port}/json/list`, 1200);
      const pages = (Array.isArray(targets) ? targets : []).filter(
        (t) => t && t.type === 'page' && t.webSocketDebuggerUrl,
      );
      if (pages.length) return pages[0].webSocketDebuggerUrl;
      lastErr = new Error('调试端口已就绪但暂无 page target');
    } catch (err) {
      lastErr = err;
    }
    // eslint-disable-next-line no-await-in-loop
    await sleep(150);
  }
  throw new Error(`等待 Chrome 调试端口 ${port} 超时: ${lastErr ? lastErr.message : 'unknown'}`);
}

/** 优先 /json/list；退化到 /json/version + Target.createTarget */
async function resolvePageWebSocket(port, timeoutMs, child) {
  try {
    return await waitForPageTarget(port, Math.min(timeoutMs, 6000), child);
  } catch {
    /* 继续走 fallback */
  }
  const version = await fetchJson(`http://127.0.0.1:${port}/json/version`, 2000);
  if (!version || !version.webSocketDebuggerUrl) {
    throw new Error('无法从 /json/version 获取 webSocketDebuggerUrl');
  }
  const browser = await CDP.connect(version.webSocketDebuggerUrl, 'browser', 8000);
  try {
    await browser.send('Target.createTarget', { url: 'about:blank' });
  } finally {
    browser.close();
  }
  return waitForPageTarget(port, timeoutMs, child);
}

// ---------------------------------------------------------------------------
// 极简 CDP 客户端（页面级 WebSocket）
// ---------------------------------------------------------------------------

class CDP {
  constructor(url, label = 'cdp') {
    this.url = url;
    this.label = label;
    this.nextId = 1;
    this.pending = new Map();
    this.handlers = new Map();
    this.waiters = new Map();
    this.closed = false;
    this.ws = new WebSocket(url);
    this.ws.addEventListener('message', (ev) => this._onMessage(ev.data));
    this.ws.addEventListener('close', () => this._onClose());
    this.ws.addEventListener('error', () => { /* 由 opened()/close 处理 */ });
  }

  /** 等待 WebSocket open（带超时） */
  static async connect(url, label = 'cdp', timeoutMs = 10000) {
    if (typeof WebSocket === 'undefined') {
      throw new Error('当前 Node 缺少全局 WebSocket，请使用 Node >= 22（本机 v24 可用）');
    }
    const client = new CDP(url, label);
    await client._opened(timeoutMs);
    return client;
  }

  _opened(timeoutMs) {
    return new Promise((resolve, reject) => {
      if (this.ws.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }
      const timer = setTimeout(() => {
        cleanup();
        reject(new Error(`${this.label}: WebSocket 连接超时（${timeoutMs}ms）`));
      }, timeoutMs);
      const onOpen = () => {
        cleanup();
        resolve();
      };
      const onError = () => {
        cleanup();
        reject(new Error(`${this.label}: WebSocket 连接失败（可能被 --remote-allow-origins 拒绝）`));
      };
      const cleanup = () => {
        clearTimeout(timer);
        this.ws.removeEventListener('open', onOpen);
        this.ws.removeEventListener('error', onError);
      };
      this.ws.addEventListener('open', onOpen);
      this.ws.addEventListener('error', onError);
    });
  }

  _onMessage(data) {
    let msg;
    try {
      msg = JSON.parse(typeof data === 'string' ? data : String(data));
    } catch {
      return;
    }
    if (msg.id) {
      const pending = this.pending.get(msg.id);
      if (!pending) return;
      this.pending.delete(msg.id);
      if (msg.error) pending.reject(new Error(`${this.label}: ${msg.method || 'CDP'} 失败: ${msg.error.message}`));
      else pending.resolve(msg.result || {});
      return;
    }
    if (msg.method) {
      const handlers = this.handlers.get(msg.method);
      if (handlers) for (const fn of handlers) { try { fn(msg.params || {}); } catch { /* 采集器异常不影响主流程 */ } }
      const list = this.waiters.get(msg.method);
      if (list && list.length) {
        const waiter = list.shift();
        clearTimeout(waiter.timer);
        waiter.resolve(msg.params || {});
      }
    }
  }

  _onClose() {
    this.closed = true;
    const err = new Error(`${this.label}: WebSocket 已关闭`);
    for (const pending of this.pending.values()) pending.reject(err);
    this.pending.clear();
    for (const list of this.waiters.values()) {
      for (const waiter of list) {
        clearTimeout(waiter.timer);
        waiter.reject(err);
      }
    }
    this.waiters.clear();
  }

  on(method, fn) {
    if (!this.handlers.has(method)) this.handlers.set(method, []);
    this.handlers.get(method).push(fn);
  }

  send(method, params = {}, timeoutMs = 15000) {
    if (this.closed) return Promise.reject(new Error(`${this.label}: CDP 已关闭，无法发送 ${method}`));
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${this.label}: CDP ${method} 超时（${timeoutMs}ms）`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (value) => { clearTimeout(timer); resolve(value); },
        reject: (err) => { clearTimeout(timer); reject(err); },
      });
      try {
        this.ws.send(JSON.stringify({ id, method, params }));
      } catch (err) {
        this.pending.delete(id);
        clearTimeout(timer);
        reject(err);
      }
    });
  }

  /** 等待某个 CDP 事件一次 */
  waitFor(method, timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
      const waiter = { resolve, reject, timer: null };
      waiter.timer = setTimeout(() => {
        const list = this.waiters.get(method) || [];
        const idx = list.indexOf(waiter);
        if (idx >= 0) list.splice(idx, 1);
        reject(new Error(`${this.label}: 等待事件 ${method} 超时（${timeoutMs}ms）`));
      }, timeoutMs);
      if (!this.waiters.has(method)) this.waiters.set(method, []);
      this.waiters.get(method).push(waiter);
    });
  }

  close() {
    this.closed = true;
    try {
      this.ws.close();
    } catch {
      /* ignore */
    }
  }
}

// ---------------------------------------------------------------------------
// 页面操作辅助
// ---------------------------------------------------------------------------

function remoteArgToString(arg) {
  if (!arg) return '';
  if (arg.value !== undefined) {
    return typeof arg.value === 'string' ? arg.value : JSON.stringify(arg.value);
  }
  if (arg.unserializableValue) return String(arg.unserializableValue);
  if (arg.description) return String(arg.description);
  return `<${arg.type || 'object'}>`;
}

/** 把 issue 加到列表（同文本合并计数），便于报告去重 */
function addIssue(list, item) {
  const key = `${item.source}|${item.text}|${item.url || ''}`;
  const found = list.find((entry) => entry.key === key);
  if (found) {
    found.count += 1;
    return;
  }
  list.push({ ...item, key, count: 1 });
}

/** 订阅 console / exception / log(网络) 事件，写入 state.current（当前路由记录） */
function wireDiagnostics(cdp, state) {
  cdp.on('Runtime.consoleAPICalled', (payload) => {
    const rec = state.current;
    if (!rec) return;
    const type = payload.type || 'log';
    if (type !== 'error' && type !== 'warning' && type !== 'assert') return;
    const text = (payload.args || []).map(remoteArgToString).join(' ').slice(0, 4000);
    if (!text) return;
    if (type === 'warning') addIssue(rec.consoleWarnings, { text, source: 'console', url: '' });
    else addIssue(rec.consoleErrors, { text, source: 'console', url: '' });
  });

  cdp.on('Runtime.exceptionThrown', (payload) => {
    const rec = state.current;
    if (!rec) return;
    const detail = payload.exceptionDetails || {};
    const text = (detail.exception && detail.exception.description)
      || detail.text
      || '未知未捕获异常';
    addIssue(rec.exceptions, {
      text: String(text).slice(0, 4000),
      source: 'exception',
      url: detail.url || '',
    });
  });

  cdp.on('Log.entryAdded', (payload) => {
    const rec = state.current;
    if (!rec) return;
    const entry = payload.entry || {};
    if (entry.level !== 'error' && entry.level !== 'warning') return;
    const text = String(entry.text || '').slice(0, 4000);
    if (!text) return;
    const item = { text, source: entry.source || 'log', url: entry.url || '' };
    if (entry.level === 'warning') addIssue(rec.consoleWarnings, item);
    else addIssue(rec.consoleErrors, item);
  });
}

/** Runtime.evaluate 取值（returnByValue） */
async function evalValue(cdp, expression, timeoutMs = 8000) {
  const res = await cdp.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
    userGesture: true,
  }, timeoutMs);
  if (res.exceptionDetails) {
    const detail = res.exceptionDetails;
    const text = (detail.exception && detail.exception.description) || detail.text || 'Runtime.evaluate 异常';
    throw new Error(String(text));
  }
  return res.result ? res.result.value : undefined;
}

/** 导航并等待 Page.loadEventFired */
async function navigate(cdp, url, timeoutMs) {
  const loaded = cdp.waitFor('Page.loadEventFired', timeoutMs);
  let result;
  try {
    result = await cdp.send('Page.navigate', { url }, timeoutMs);
  } catch (err) {
    loaded.catch(() => {});
    throw err;
  }
  if (result && result.errorText) {
    loaded.catch(() => {});
    throw new Error(`导航失败（${url}）: ${result.errorText}`);
  }
  await loaded;
}

/** 等 SPA 挂载出 .page（失败不抛错，交给 blank 判定） */
async function waitForAppMount(cdp, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      // eslint-disable-next-line no-await-in-loop
      const mounted = await evalValue(cdp, "!!document.querySelector('.page')", 4000);
      if (mounted) return true;
    } catch {
      /* 页面可能正在导航，继续等 */
    }
    // eslint-disable-next-line no-await-in-loop
    await sleep(100);
  }
  return false;
}

const METRICS_EXPR = `(() => ({
  title: document.title,
  textLen: (document.body && document.body.innerText ? document.body.innerText : '').trim().length,
  page: !!document.querySelector('.page'),
  hero: (document.querySelector('.page-hero__title') || {}).textContent || '',
  cards: document.querySelectorAll('.mi-card, .mi-group, .mi-metric').length,
  w: window.innerWidth,
  h: window.innerHeight,
  hasViewport: !!document.getElementById('viewport'),
  hash: location.hash
}))()`;

const SCROLL_INFO_EXPR = `(() => {
  const el = document.getElementById('viewport') || document.scrollingElement;
  if (!el) return { found: false, scrollTop: 0, scrollHeight: 0, clientHeight: 0 };
  return {
    found: true,
    scrollTop: el.scrollTop,
    scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight
  };
})()`;

async function getScrollInfo(cdp) {
  try {
    return await evalValue(cdp, SCROLL_INFO_EXPR, 6000);
  } catch {
    return null;
  }
}

/** 内部滚动容器下移 amount 像素 */
async function scrollInner(cdp, amount) {
  const expr = `(() => {
    const el = document.getElementById('viewport') || document.scrollingElement;
    if (!el) return null;
    el.scrollTop = Math.min(el.scrollHeight, el.scrollTop + ${Math.max(0, Math.round(amount))});
    return { scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
  })()`;
  try {
    return await evalValue(cdp, expr, 6000);
  } catch {
    return null;
  }
}

async function capturePng(cdp, outDir, dir, fileName) {
  const filePath = path.join(dir, fileName);
  const result = await cdp.send('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false,
  }, 20000);
  if (!result || !result.data) throw new Error(`captureScreenshot 返回空数据: ${fileName}`);
  await fsp.writeFile(filePath, Buffer.from(result.data, 'base64'));
  return path.relative(outDir, filePath).split(path.sep).join('/');
}

/** 注入到每个新文档开头的 localStorage 种子脚本 */
function seedScript(apiKey, theme) {
  return `(() => {
  try {
    localStorage.setItem('tqsync_api_key', ${JSON.stringify(apiKey)});
    localStorage.setItem('tqsync_theme', ${JSON.stringify(theme)});
  } catch (e) { /* about:blank 等无 origin 场景会抛错，忽略 */ }
})();`;
}

/** 判定白屏：文本过少 或 没有 .page 骨架 */
function isBlank(metrics) {
  if (!metrics) return true;
  return metrics.textLen < 80 || !metrics.page;
}

// ---------------------------------------------------------------------------
// 单条路由采集
// ---------------------------------------------------------------------------

async function captureCombo(env, viewport, theme, route) {
  const { cdp, opts } = env;
  const outDir = opts.out;
  const started = Date.now();
  const rec = {
    route,
    viewport: viewport.label,
    theme,
    viewportSize: { width: viewport.width, height: viewport.height },
    shots: [],
    metrics: null,
    blank: true,
    error: null,
    consoleErrors: [],
    consoleWarnings: [],
    exceptions: [],
    durationMs: 0,
  };
  env.state.current = rec;

  const dir = path.join(outDir, viewport.label, theme);
  await fsp.mkdir(dir, { recursive: true });

  try {
    // 1) 视口仿真（deviceScaleFactor=2 => PNG 为 CSS 尺寸的 2 倍，便于查看细节）
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: viewport.width,
      height: viewport.height,
      deviceScaleFactor: 2,
      mobile: viewport.width < 600,
    }, 10000);
    await cdp.send('Emulation.setTouchEmulationEnabled', {
      enabled: viewport.width < 600,
      maxTouchPoints: viewport.width < 600 ? 5 : 1,
    }, 10000);

    // 2) 先回 about:blank，确保 hash 变化也触发整页重载（主题在启动时读取）
    await navigate(cdp, 'about:blank', opts.navTimeout);
    // 3) 进入目标 hash 路由
    await navigate(cdp, `${opts.base}/#/${route}`, opts.navTimeout);
    // 4) 等 SPA 挂载 + 沉降
    await waitForAppMount(cdp, Math.min(2500, opts.navTimeout));
    await sleep(opts.settle);

    // 5) 采样页面指标 + 首屏截图
    rec.metrics = await evalValue(cdp, METRICS_EXPR, 8000);
    rec.blank = isBlank(rec.metrics);
    rec.shots.push(await capturePng(cdp, outDir, dir, `${route}-1.png`));

    // 6) 滚动内部容器，补第 2/3 屏
    const info = await getScrollInfo(cdp);
    if (info && info.found) {
      await scrollInner(cdp, info.clientHeight * 0.8);
      await sleep(450);
      rec.shots.push(await capturePng(cdp, outDir, dir, `${route}-2.png`));
      const next = await getScrollInfo(cdp);
      if (next && next.found && next.scrollTop + next.clientHeight < next.scrollHeight - 2) {
        await scrollInner(cdp, next.clientHeight * 0.8);
        await sleep(450);
        rec.shots.push(await capturePng(cdp, outDir, dir, `${route}-3.png`));
      }
    }
  } catch (err) {
    rec.error = err && err.message ? err.message : String(err);
  } finally {
    env.state.current = null;
    rec.durationMs = Date.now() - started;
  }
  return rec;
}

// ---------------------------------------------------------------------------
// 报告 / 汇总 / 输出
// ---------------------------------------------------------------------------

function shotExists(outDir, relativeShot) {
  if (!relativeShot) return false;
  return fs.existsSync(path.join(outDir, relativeShot.split('/').join(path.sep)));
}

function collectIssues(runs) {
  const issues = [];
  for (const run of runs) {
    for (const err of run.consoleErrors) {
      issues.push({ kind: 'console-error', route: run.route, viewport: run.viewport, theme: run.theme, text: err.text, url: err.url, count: err.count });
    }
    for (const exc of run.exceptions) {
      issues.push({ kind: 'exception', route: run.route, viewport: run.viewport, theme: run.theme, text: exc.text, url: exc.url, count: exc.count });
    }
    if (run.error) {
      issues.push({ kind: 'harness-error', route: run.route, viewport: run.viewport, theme: run.theme, text: run.error, url: '', count: 1 });
    }
    if (!run.error && run.blank) {
      issues.push({ kind: 'blank-page', route: run.route, viewport: run.viewport, theme: run.theme, text: `blank page (textLen=${run.metrics ? run.metrics.textLen : '?'}, page=${run.metrics ? run.metrics.page : '?'})`, url: '', count: 1 });
    }
    if (!run.error && run.shots.length === 0) {
      issues.push({ kind: 'missing-screenshot', route: run.route, viewport: run.viewport, theme: run.theme, text: '未生成任何截图', url: '', count: 1 });
    }
    for (const shot of run.shots) {
      if (!shotExists(run._outDir || '', shot)) {
        issues.push({ kind: 'missing-screenshot', route: run.route, viewport: run.viewport, theme: run.theme, text: `截图文件缺失: ${shot}`, url: '', count: 1 });
      }
    }
  }
  return issues;
}

function buildSummary(report, opts) {
  const runs = report.runs;
  const issues = report.issues;
  const failedRuns = new Set();
  for (const issue of issues) failedRuns.add(`${issue.viewport}|${issue.theme}|${issue.route}`);
  const passed = runs.filter((run) => !failedRuns.has(`${run.viewport}|${run.theme}|${run.route}`)).length;
  const totals = {
    runs: runs.length,
    passed,
    failed: runs.length - passed,
    shots: runs.reduce((acc, run) => acc + run.shots.length, 0),
    consoleErrors: runs.reduce((acc, run) => acc + run.consoleErrors.reduce((a, i) => a + i.count, 0), 0),
    consoleWarnings: runs.reduce((acc, run) => acc + run.consoleWarnings.reduce((a, i) => a + i.count, 0), 0),
    exceptions: runs.reduce((acc, run) => acc + run.exceptions.reduce((a, i) => a + i.count, 0), 0),
    blankPages: issues.filter((i) => i.kind === 'blank-page').length,
    missingScreenshots: issues.filter((i) => i.kind === 'missing-screenshot').length,
    harnessErrors: issues.filter((i) => i.kind === 'harness-error').length,
  };
  const byRoute = {};
  for (const route of opts.routes) {
    const routeIssues = issues.filter((i) => i.route === route);
    byRoute[route] = {
      issues: routeIssues.length,
      consoleErrors: routeIssues.filter((i) => i.kind === 'console-error').length,
      exceptions: routeIssues.filter((i) => i.kind === 'exception').length,
      blank: routeIssues.filter((i) => i.kind === 'blank-page').length,
    };
  }
  return {
    result: issues.length === 0 ? 'PASS' : 'FAIL',
    ...totals,
    byRoute,
  };
}

function printRunSummary(run) {
  const flags = [];
  if (run.error) flags.push(`error=${run.error}`);
  if (run.blank) flags.push('blank');
  if (run.consoleErrors.length) flags.push(`consoleErrors=${run.consoleErrors.reduce((a, i) => a + i.count, 0)}`);
  if (run.exceptions.length) flags.push(`exceptions=${run.exceptions.reduce((a, i) => a + i.count, 0)}`);
  const status = flags.length ? 'FAIL' : ' OK ';
  const m = run.metrics || {};
  console.log(
    `[${status}] ${run.viewport}/${run.theme}/${run.route}`.padEnd(40)
    + ` shots=${run.shots.length} textLen=${m.textLen ?? '?'} cards=${m.cards ?? '?'}`
    + ` hero=${JSON.stringify(String(m.hero || '').slice(0, 24))} w=${m.w ?? '?'}`,
  );
  if (run.error) console.log(`        ✗ ${run.error}`);
  for (const issue of [...run.exceptions, ...run.consoleErrors].slice(0, 8)) {
    console.log(`        ✗ [${issue.source}] ${issue.text.split('\n')[0].slice(0, 220)}${issue.url ? `  <${issue.url}>` : ''} ×${issue.count}`);
  }
  const extra = run.exceptions.length + run.consoleErrors.length - 8;
  if (extra > 0) console.log(`        ... 另有 ${extra} 条问题（详见 report.json）`);
}

function printReport(report) {
  const summary = report.summary;
  console.log('');
  console.log('='.repeat(78));
  console.log(`TQSync WebUI 截图/冒烟结果 — ${report.finishedAt}`);
  console.log(`base=${report.base}  out=${report.outDir}`);
  console.log(`runs=${summary.runs}  PASS=${summary.passed}  FAIL=${summary.failed}  shots=${summary.shots}`);
  console.log(`consoleError=${summary.consoleErrors}  exception=${summary.exceptions}  blank=${summary.blankPages}  missingPng=${summary.missingScreenshots}  warnings=${summary.consoleWarnings}`);
  console.log('='.repeat(78));
  if (report.issues.length) {
    console.log('问题明细（去重后）:');
    for (const issue of report.issues) {
      console.log(`  • [${issue.kind}] ${issue.viewport}/${issue.theme}/${issue.route}: ${issue.text.split('\n')[0].slice(0, 300)}${issue.url ? `  <${issue.url}>` : ''}${issue.count > 1 ? ` ×${issue.count}` : ''}`);
    }
    console.log('');
  }
  console.log(`RESULT: ${summary.result}${summary.result === 'PASS' ? '' : '（存在 console error / 异常 / 白屏 / 缺图）'}`);
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------

async function checkBase(base) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(`${base}/`, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    console.log(`[base] ${base}/ -> HTTP ${res.status}`);
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    printHelp();
    return 0;
  }

  const chromePath = resolveChromePath(opts.chrome);
  if (!chromePath) throw new Error(`找不到 Chrome 可执行文件（--chrome 或 CHROME_PATH）: ${opts.chrome}`);
  opts.chrome = chromePath;

  const viewports = [parseViewport('mobile', opts.mobile), parseViewport('desktop', opts.desktop)];
  const themes = opts.themeList;
  const routes = opts.routes.filter((route) => (opts.only.length ? opts.only.includes(route) : true));
  if (!routes.length) throw new Error(`没有可执行的路由（routes=${opts.routes.join(',')}, only=${opts.only.join(',') || '-'}）`);

  await fsp.mkdir(opts.out, { recursive: true });
  await checkBase(opts.base);

  console.log(`[run] chrome=${opts.chrome}`);
  console.log(`[run] viewports=${viewports.map((v) => `${v.label}(${v.width}x${v.height})`).join(', ')}`);
  console.log(`[run] themes=${themes.join(',')}  routes=${routes.join(',')}  out=${opts.out}`);

  const state = { current: null };
  let chrome = null;
  let profileDir = null;
  let cdp = null;

  const report = {
    startedAt: ts(),
    finishedAt: null,
    base: opts.base,
    outDir: opts.out,
    chrome: opts.chrome,
    viewports: Object.fromEntries(viewports.map((v) => [v.label, { width: v.width, height: v.height }])),
    themes,
    routes,
    only: opts.only,
    apikey: opts.apikey,
    runs: [],
    issues: [],
    summary: null,
  };

  // Ctrl+C 时尽量清理
  const onSignal = () => {
    killChrome(chrome);
    process.exit(130);
  };
  process.once('SIGINT', onSignal);
  process.once('SIGTERM', onSignal);

  try {
    const port = await findFreePort(9400);
    profileDir = fs.mkdtempSync(path.join(os.tmpdir(), 'tqsync-webui-shots-'));
    console.log(`[chrome] debug port=${port} profile=${profileDir}`);

    let pageWs = null;
    chrome = launchChrome(opts, port, profileDir, []);
    try {
      pageWs = await resolvePageWebSocket(port, 15000, chrome);
    } catch (firstErr) {
      // 典型场景：WebSocket 握手被 Origin 校验拒绝（需要 --remote-allow-origins=*）
      console.warn(`[warn] 首次连接 Chrome 失败: ${firstErr.message}`);
      console.warn('[warn] 使用 --remote-allow-origins=* 重启 Chrome 后重试');
      killChrome(chrome);
      chrome = null;
      await sleep(600);
      chrome = launchChrome(opts, port, profileDir, ['--remote-allow-origins=*']);
      pageWs = await resolvePageWebSocket(port, 15000, chrome);
    }

    cdp = await CDP.connect(pageWs, 'page', 10000);
    await Promise.all([
      cdp.send('Page.enable', {}, 10000),
      cdp.send('Runtime.enable', {}, 10000),
      cdp.send('Log.enable', {}, 10000),
    ]);
    wireDiagnostics(cdp, state);

    for (const viewport of viewports) {
      for (const theme of themes) {
        // 每个 (viewport, theme) 组合注入一次 localStorage 种子（文档级）
        const scriptResult = await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
          source: seedScript(opts.apikey, theme),
        }, 10000);
        const identifier = scriptResult && scriptResult.identifier;
        try {
          for (const route of routes) {
            console.log(`  → ${viewport.label}/${theme}/${route}`);
            // eslint-disable-next-line no-await-in-loop
            const rec = await withTimeout(
              captureCombo({ cdp, opts, outDir: opts.out, state }, viewport, theme, route),
              opts.routeTimeout,
              `${viewport.label}/${theme}/${route}`,
            ).catch((err) => ({
              route,
              viewport: viewport.label,
              theme,
              viewportSize: { width: viewport.width, height: viewport.height },
              shots: [],
              metrics: null,
              blank: true,
              error: err && err.message ? err.message : String(err),
              consoleErrors: [],
              consoleWarnings: [],
              exceptions: [],
              durationMs: 0,
            }));
            rec._outDir = opts.out;
            report.runs.push(rec);
            printRunSummary(rec);
          }
        } finally {
          if (identifier) {
            try {
              await cdp.send('Page.removeScriptToEvaluateOnNewDocument', { identifier }, 10000);
            } catch {
              /* ignore */
            }
          }
        }
      }
    }
  } finally {
    process.removeListener('SIGINT', onSignal);
    process.removeListener('SIGTERM', onSignal);
    if (cdp) cdp.close();
    killChrome(chrome);
    if (profileDir) {
      try {
        await fsp.rm(profileDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
      } catch {
        /* 临时目录清理失败不影响报告 */
      }
    }
  }

  report.finishedAt = ts();
  report.issues = collectIssues(report.runs);
  report.summary = buildSummary(report, opts);

  const reportPath = path.join(opts.out, 'report.json');
  await fsp.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(`[report] ${reportPath}`);
  printReport(report);

  return report.summary.result === 'PASS' ? 0 : 1;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(`[fatal] ${err && err.stack ? err.stack : err}`);
    process.exit(2);
  });
