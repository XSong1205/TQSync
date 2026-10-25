/**
 * TQSync 控制台 —— 应用外壳
 * =====================================================================
 * 负责：启动流程、登录、主题、底部导航/侧栏、哈希路由、顶栏折叠、
 *       下拉刷新、页面生命周期与全局提示。
 *
 * 页面模块契约（js/pages/*.js 的默认导出）：
 * {
 *   id: string,               // 路由 id，如 'dashboard'
 *   label: string,            // 导航文案
 *   icon: string,             // icons.js 图标名
 *   tab: boolean,             // 是否出现在主导航（false 为二级页，显示返回键）
 *   parent: string,           // 二级页归属的 tab id
 *   title: string,            // 大标题
 *   subtitle?: string,        // 大标题下方说明（可被 ctx.setHero 覆盖）
 *   mount(root, ctx): any     // 向 root 渲染页面；可返回清理函数（等同 ctx.onCleanup）
 * }
 *
 * ctx 提供：api, ui, saveConfigBatch, state, isStale(), onCleanup(fn),
 *   onRefresh(fn), refresh(), go(id), back(), reload(), setHero({title,subtitle,actions}),
 *   setAppbarActions(nodes), toast(), toastErr(), confirm(), dialog(), actionSheet(),
 *   openSheet(), formatUptime(), formatClock(), copyText(), debounce(), vibrate(),
 *   scrollToTop(), onThemeChange(cb)
 */
import { api, saveConfigBatch, onUnauthorized } from './api.js';
import * as ui from './ui.js';
import { initTheme, subscribe as subscribeTheme, resolved as resolvedTheme, setMode as setThemeMode, getMode as getThemeMode } from './theme.js';
import { initUpdateCheck } from './update.js';

import dashboardPage from './pages/dashboard.js';
import configPage from './pages/config.js';
import bindingsPage from './pages/bindings.js';
import pluginsPage from './pages/plugins.js';
import logsPage from './pages/logs.js';
import settingsPage from './pages/settings.js';

const { h, clear, append, icon, iconButton, button, errorBlock, toast, toastErr } = ui;

/* ── 路由表 ─────────────────────────────────────────────────────────── */
const PAGES = [dashboardPage, configPage, bindingsPage, pluginsPage, settingsPage, logsPage];
const ROUTES = Object.fromEntries(PAGES.map((p) => [p.id, p]));
const TABS = PAGES.filter((p) => p.tab);
const DEFAULT_ROUTE = 'dashboard';

/* ── 应用状态 ───────────────────────────────────────────────────────── */
const state = {
  status: null,
  version: '',
  initialToken: false,
  navToken: 0,
  currentPage: null,
  cleanups: [],
  refreshFn: null,
};

/* ── DOM 引用 ───────────────────────────────────────────────────────── */
const $boot = document.getElementById('boot');
const $loginRoot = document.getElementById('login-root');
const $appRoot = document.getElementById('app-root');
let viewport = null;
let pageEl = null;
let contentEl = null;
let heroEl = null;
let appbar = null;
let appbarTitle = null;
let appbarLeft = null;
let appbarRight = null;
let ptrEl = null;
let ptrRing = null;

/* ── 启动占位 ───────────────────────────────────────────────────────── */

function hideBoot() {
  if (!$boot) return;
  $boot.classList.add('boot--done');
  setTimeout(() => { if ($boot.parentNode) $boot.remove(); }, 460);
}

/* ── 登录页 ─────────────────────────────────────────────────────────── */

function showLogin(message = '') {
  document.title = '登录 · TQSync 控制台';
  clear($loginRoot);
  $loginRoot.hidden = false;
  $appRoot.hidden = true;
  $appRoot.innerHTML = '';

  const errorText = h('span', null, message);
  const errorBox = h('div', { class: 'login-error', hidden: !message }, icon('warning', 15), errorText);

  const pwdField = h('input', {
    class: 'mi-field__input',
    type: 'password',
    placeholder: '请输入管理密钥',
    autocomplete: 'current-password',
    autocapitalize: 'off',
    spellcheck: 'false',
    'aria-label': '管理密钥',
  });
  const showBtn = h('button', {
    class: 'mi-field__trailing',
    type: 'button',
    'aria-label': '显示密钥',
    onClick: (e) => {
      e.preventDefault();
      const show = pwdField.type === 'password';
      pwdField.type = show ? 'text' : 'password';
      clear(showBtn);
      showBtn.appendChild(icon(show ? 'eye-off' : 'eye', 18));
    },
  }, icon('eye', 18));

  const submit = button({ text: '进入控制台', variant: 'filled', block: true, type: 'submit' });

  const form = h('form', { class: 'login-form' },
    errorBox,
    h('div', { class: 'mi-field' },
      h('label', { class: 'mi-field__label', for: 'login-token' }, '管理密钥'),
      h('div', { class: 'mi-field__box', style: { minHeight: '50px' } }, pwdField, showBtn),
      h('div', { class: 'mi-field__support' }, '对应 config.yaml 中的 server.admin_api_key')
    ),
    submit
  );
  pwdField.id = 'login-token';

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const token = pwdField.value.trim();
    if (!token) {
      errorText.textContent = '请输入管理密钥';
      errorBox.hidden = false;
      return;
    }
    submit.setLoading(true);
    errorBox.hidden = true;
    api.setToken(token);
    try {
      const data = await api.get('/admin/status');
      state.status = data;
      state.version = data.version || '';
      state.initialToken = Boolean(data.is_initial_token);
      showApp();
    } catch (err) {
      api.clearToken();
      errorText.textContent =
        err && (err.status === 403 || err.status === 401)
          ? '密钥不正确，请重试'
          : (err && err.detail) || '无法连接到后端服务';
      errorBox.hidden = false;
      pwdField.focus();
      pwdField.select();
    } finally {
      submit.setLoading(false);
    }
  });

  const logo = h('div', { class: 'login-brand__logo' }, ui.brandMark(34));

  const card = h('div', { class: 'login-card' },
    h('div', { class: 'login-brand' },
      logo,
      h('div', { class: 'login-brand__name' }, 'TQSync'),
      h('div', { class: 'login-brand__desc' }, 'Telegram × QQ 跨群组双向消息同步控制台')
    ),
    form,
    h('div', { class: 'login-footer' },
      h('div', null, '登录信息仅保存在本机浏览器'),
      state.version ? h('div', null, `版本 ${state.version}`) : null
    )
  );

  $loginRoot.appendChild(card);
  hideBoot();
  setTimeout(() => pwdField.focus(), 320);
}

/* ── 导航结构 ───────────────────────────────────────────────────────── */

function navItems() {
  return TABS.map((p) => ({ id: p.id, label: p.label, icon: p.icon }));
}

function buildTabbar() {
  const tabbar = h('nav', { class: 'tabbar', 'aria-label': '主导航' });
  for (const item of navItems()) {
    tabbar.appendChild(h('button', {
      class: 'tabbar__item', type: 'button', dataset: { route: item.id },
      onClick: () => go(item.id),
    },
      h('span', { class: 'tabbar__icon' }, icon(item.icon, 22)),
      h('span', { class: 'tabbar__label' }, item.label)
    ));
  }
  return tabbar;
}

function buildRail() {
  const rail = h('aside', { class: 'rail' });
  rail.appendChild(h('div', { class: 'rail__brand' },
    h('div', { class: 'rail__logo' }, ui.brandMark(22)),
    h('div', null,
      h('div', { class: 'rail__brand-name' }, 'TQSync'),
      h('div', { class: 'rail__brand-sub' }, '消息同步控制台')
    )
  ));

  const nav = h('nav', { class: 'rail__nav', 'aria-label': '主导航' });
  for (const item of navItems()) {
    nav.appendChild(h('button', {
      class: 'rail__item', type: 'button', dataset: { route: item.id },
      onClick: () => go(item.id),
    }, icon(item.icon, 19), h('span', null, item.label)));
  }
  rail.appendChild(nav);

  const themeBtn = iconButton({
    icon: 'auto',
    label: '切换主题',
    onClick: () => {
      setThemeMode(resolvedTheme() === 'dark' ? 'light' : 'dark');
      themeBtn.replaceWith(buildThemeBtn());
    },
  });
  function buildThemeBtn() {
    const btn = iconButton({
      icon: resolvedTheme() === 'dark' ? 'moon' : 'sun',
      label: '切换主题',
      onClick: () => { setThemeMode(resolvedTheme() === 'dark' ? 'light' : 'dark'); btn.replaceWith(buildThemeBtn()); },
    });
    return btn;
  }
  // 用实际主题图标替换初始按钮
  const realThemeBtn = buildThemeBtn();
  rail.appendChild(h('div', { class: 'rail__footer' },
    h('div', { class: 'mi-hstack', style: { justifyContent: 'space-between' } },
      h('span', { class: 'rail__version' }, state.version ? `${state.version}` : ''),
      realThemeBtn
    )
  ));
  return rail;
}

function buildAppbar() {
  return h('header', { class: 'appbar', dataset: { large: 'true', elevated: 'false' } },
    h('div', { class: 'appbar__bar' },
      h('div', { class: 'appbar__side', id: 'appbar-left' }),
      h('div', { class: 'appbar__title', id: 'appbar-title' }),
      h('div', { class: 'appbar__side appbar__side--right', id: 'appbar-right' })
    )
  );
}

/* ── 应用外壳 ───────────────────────────────────────────────────────── */

function showApp() {
  document.title = 'TQSync 控制台';
  $loginRoot.hidden = true;
  $loginRoot.innerHTML = '';
  $appRoot.hidden = false;
  clear($appRoot);

  appbar = buildAppbar();
  ptrRing = h('div', { class: 'ptr__ring' });
  ptrEl = h('div', { class: 'ptr', 'aria-hidden': 'true' }, ptrRing);
  viewport = h('div', { class: 'viewport', id: 'viewport', tabindex: '-1' });

  const main = h('div', { class: 'app-main' }, appbar, ptrEl, viewport, buildTabbar());
  $appRoot.appendChild(buildRail());
  $appRoot.appendChild(main);

  appbarTitle = appbar.querySelector('#appbar-title');
  appbarLeft = appbar.querySelector('#appbar-left');
  appbarRight = appbar.querySelector('#appbar-right');

  bindScrollEffects();
  bindPullToRefresh();
  onUnauthorized(() => {
    api.clearToken();
    toast('登录凭证已失效，请重新登录', { type: 'error' });
    showLogin('登录凭证已失效，请重新输入');
  });
  window.addEventListener('hashchange', onHashChange);

  hideBoot();

  const initial = parseHash() || DEFAULT_ROUTE;
  if (!location.hash) history.replaceState(null, '', `#/${initial}`);
  navigate(initial, { restoreScroll: true });

  // 静默检查更新：延迟执行，失败/无网络不打扰用户
  initUpdateCheck();

  if (state.initialToken) setTimeout(promptInitialPassword, 900);
}

function promptInitialPassword() {
  const d = ui.dialog({
    title: '安全提示',
    message: '当前仍在使用初始管理密钥。为了控制台安全，建议立即修改为一个高强度密钥。',
    actions: [
      { text: '稍后再说', variant: 'text', value: false },
      { text: '去修改', variant: 'filled', value: true },
    ],
  });
  d.result.then((ok) => { if (ok) go('settings'); });
}

/* ── 路由 ───────────────────────────────────────────────────────────── */

function parseHash() {
  const raw = (location.hash || '').replace(/^#\/?/, '').split('?')[0];
  const id = raw.trim();
  return ROUTES[id] ? id : '';
}

function go(routeId, { replace = false } = {}) {
  if (!ROUTES[routeId]) return;
  const target = `#/${routeId}`;
  if (location.hash === target) {
    refresh();
    return;
  }
  if (replace) { history.replaceState(null, '', target); onHashChange(); }
  else location.hash = target;
}

function back() {
  const page = state.currentPage;
  const fallback = (page && !page.tab && page.parent) || DEFAULT_ROUTE;
  if (history.length > 1 && parseHash()) history.back();
  else go(fallback, { replace: true });
}

function onHashChange() {
  navigate(parseHash() || DEFAULT_ROUTE, { restoreScroll: true });
}

function updateNav(activeId) {
  const page = ROUTES[activeId];
  const activeTab = page && page.tab ? page.id : (page && page.parent) || activeId;
  document.querySelectorAll('.tabbar__item, .rail__item').forEach((el) => {
    if (el.dataset.route === activeTab) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  });
}

const scrollMemory = new Map();

function navigate(routeId, { restoreScroll = false } = {}) {
  const page = ROUTES[routeId] || ROUTES[DEFAULT_ROUTE];
  if (!page) return;

  if (state.currentPage && viewport) scrollMemory.set(state.currentPage.id, viewport.scrollTop);

  state.cleanups.forEach((fn) => { try { fn(); } catch (err) { console.warn('[page cleanup]', err); } });
  state.cleanups = [];
  state.refreshFn = null;
  state.currentPage = page;
  state.navToken += 1;
  const token = state.navToken;

  clear(viewport);
  pageEl = h('div', { class: 'page page--enter' });
  heroEl = buildHero(page);
  contentEl = h('div', { class: 'page-content' });
  pageEl.appendChild(heroEl);
  pageEl.appendChild(contentEl);
  viewport.appendChild(pageEl);

  appbar.dataset.elevated = 'false';
  appbar.dataset.large = 'true';
  appbarTitle.textContent = page.title || page.label || '';
  clear(appbarLeft);
  clear(appbarRight);
  if (!page.tab) appbarLeft.appendChild(iconButton({ icon: 'chevron-left', label: '返回', onClick: back }));
  appbarRight.appendChild(iconButton({ icon: 'refresh', label: '刷新', onClick: () => refresh(true) }));

  updateNav(page.id);
  document.title = `${page.title || page.label} · TQSync 控制台`;

  const ctx = createContext(page, token);
  let result;
  try {
    result = page.mount(contentEl, ctx);
  } catch (err) {
    console.error('[page mount]', err);
    contentEl.appendChild(errorBlock({ title: '页面渲染失败', message: err.message || String(err) }));
    result = null;
  }
  Promise.resolve(result)
    .then((cleanup) => { if (typeof cleanup === 'function') state.cleanups.push(cleanup); })
    .catch((err) => {
      console.error('[page mount async]', err);
      if (token === state.navToken) {
        contentEl.appendChild(errorBlock({ title: '页面加载失败', message: (err && err.detail) || '请稍后重试', onRetry: () => refresh() }));
      }
    });

  requestAnimationFrame(() => {
    if (token !== state.navToken) return;
    viewport.scrollTop = restoreScroll && scrollMemory.has(page.id) ? scrollMemory.get(page.id) : 0;
  });
}

function buildHero(page) {
  const sub = page.subtitle || '';
  return h('div', { class: 'page-hero' },
    h('div', { class: 'page-hero__row' },
      h('div', { class: 'mi-grow' },
        h('h1', { class: 'page-hero__title' }, page.title || page.label || ''),
        h('div', { class: 'page-hero__sub', hidden: !sub }, sub)
      ),
      h('div', { class: 'page-hero__actions' })
    )
  );
}

/* ── 页面上下文 ─────────────────────────────────────────────────────── */

function createContext(page, token) {
  return {
    /* 数据 */
    api,
    saveConfigBatch,
    state,
    /* 常用 UI 快捷方式 */
    ui,
    h, clear, append, icon, button, iconButton,
    toast,
    toastErr,
    confirm: (opts) => ui.confirm(opts),
    dialog: (opts) => ui.dialog(opts),
    actionSheet: (opts) => ui.actionSheet(opts),
    openSheet: (opts) => ui.openSheet(opts),
    /* 页面生命周期 */
    isStale: () => token !== state.navToken,
    onCleanup(fn) { if (typeof fn === 'function') state.cleanups.push(fn); },
    onRefresh(fn) { state.refreshFn = fn; },
    refresh: () => refresh(),
    reload: () => navigate(page.id, { restoreScroll: false }),
    /* 导航 */
    go: (id) => go(id),
    back,
    scrollToTop: () => { if (viewport) viewport.scrollTop = 0; },
    viewport: () => viewport,
    /* 顶栏 / 大标题 */
    setHero({ title, subtitle, actions } = {}) {
      const t = heroEl && heroEl.querySelector('.page-hero__title');
      const s = heroEl && heroEl.querySelector('.page-hero__sub');
      const a = heroEl && heroEl.querySelector('.page-hero__actions');
      if (t && title !== undefined) {
        t.textContent = title;
        if (appbarTitle) appbarTitle.textContent = title;
      }
      if (s && subtitle !== undefined) {
        s.textContent = subtitle || '';
        s.hidden = !subtitle;
      }
      if (a && actions) { clear(a); append(a, actions); }
    },
    setAppbarActions(nodes) {
      if (!appbarRight) return;
      const refreshBtn = appbarRight.querySelector('button[aria-label="刷新"]');
      clear(appbarRight);
      append(appbarRight, nodes || []);
      if (refreshBtn) appbarRight.appendChild(refreshBtn);
    },
    /* 主题 */
    getThemeMode: () => getThemeMode(),
    setThemeMode: (m) => setThemeMode(m),
    onThemeChange: (cb) => subscribeTheme(cb),
    /* 格式化 / 工具 */
    formatUptime: ui.formatUptime,
    formatNumber: ui.formatNumber,
    formatClock: ui.formatClock,
    copyText: ui.copyText,
    debounce: ui.debounce,
    vibrate: ui.vibrate,
  };
}

/* ── 刷新 ───────────────────────────────────────────────────────────── */

let refreshing = false;
async function refresh(showToast = false) {
  if (refreshing) return;
  refreshing = true;
  try {
    if (state.refreshFn) await state.refreshFn();
    else if (state.currentPage) navigate(state.currentPage.id, { restoreScroll: false });
    if (showToast) toast('已刷新', { type: 'success', duration: 1200 });
  } catch (err) {
    toastErr(err, '刷新失败');
  } finally {
    refreshing = false;
  }
}

/* ── 顶栏折叠 + 下拉刷新 ───────────────────────────────────────────── */

function bindScrollEffects() {
  let ticking = false;
  viewport.addEventListener('scroll', () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const top = viewport.scrollTop;
      if (appbar) {
        appbar.dataset.elevated = top > 12 ? 'true' : 'false';
        appbar.dataset.large = top > 42 ? 'false' : 'true';
      }
      ticking = false;
    });
  }, { passive: true });
}

function bindPullToRefresh() {
  let startY = 0;
  let pulling = false;
  let distance = 0;
  const THRESHOLD = 64;
  const MAX = 104;

  const reset = () => {
    pulling = false;
    distance = 0;
    if (ptrEl) {
      ptrEl.classList.remove('ptr--visible', 'ptr--refreshing');
      ptrEl.style.transform = '';
      ptrRing.style.transform = '';
      ptrRing.style.opacity = '';
    }
  };

  viewport.addEventListener('touchstart', (e) => {
    if (viewport.scrollTop > 0 || e.touches.length !== 1) return;
    startY = e.touches[0].clientY;
    pulling = true;
    distance = 0;
  }, { passive: true });

  viewport.addEventListener('touchmove', (e) => {
    if (!pulling) return;
    const dy = e.touches[0].clientY - startY;
    if (dy <= 0 || viewport.scrollTop > 0) {
      if (distance > 0) reset();
      return;
    }
    distance = Math.min(MAX, dy * 0.55);
    if (e.cancelable) e.preventDefault();
    if (ptrEl) {
      ptrEl.classList.add('ptr--visible');
      ptrEl.style.transform = `translateY(${distance}px) scale(1)`;
      ptrRing.style.transform = `rotate(${distance * 2.4}deg)`;
      ptrRing.style.opacity = String(Math.min(1, distance / THRESHOLD));
    }
  }, { passive: false });

  const finish = async () => {
    if (!pulling) return;
    pulling = false;
    if (distance >= THRESHOLD) {
      if (ptrEl) {
        ptrEl.classList.add('ptr--refreshing');
        ptrEl.style.transform = 'translateY(64px) scale(1)';
      }
      ui.vibrate(10);
      await refresh();
      reset();
    } else {
      reset();
    }
  };

  viewport.addEventListener('touchend', finish, { passive: true });
  viewport.addEventListener('touchcancel', reset, { passive: true });
}

/* ── 启动 ───────────────────────────────────────────────────────────── */

async function boot() {
  initTheme();
  api.init();

  window.addEventListener('error', (e) => console.error('[window error]', e.error || e.message));
  window.addEventListener('unhandledrejection', (e) => console.error('[unhandled rejection]', e.reason));
  window.addEventListener('offline', () => toast('网络已断开，部分操作可能失败', { type: 'warning', duration: 3000 }));
  window.addEventListener('online', () => toast('网络已恢复', { type: 'success', duration: 1800 }));

  if (!api.hasToken()) {
    showLogin();
    return;
  }
  try {
    const data = await api.get('/admin/status');
    state.status = data;
    state.version = data.version || '';
    state.initialToken = Boolean(data.is_initial_token);
    showApp();
  } catch (err) {
    if (err && (err.status === 403 || err.status === 401)) {
      api.clearToken();
      showLogin('登录凭证已失效，请重新输入');
    } else {
      showApp();
      setTimeout(() => toast((err && err.detail) || '无法获取系统状态', { type: 'error', duration: 3600 }), 400);
    }
  }
}

boot();
