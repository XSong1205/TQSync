/**
 * 主题管理：auto / light / dark
 * - auto 跟随系统，系统切换时自动重绘
 * - 用户选择持久化到 localStorage
 */

const KEY = 'tqsync_theme';
const listeners = new Set();
let mode = 'auto';
const media = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: dark)')
  : null;

/** 当前模式：'auto' | 'light' | 'dark' */
export function getMode() {
  return mode;
}

/** 解析后的实际主题：'light' | 'dark' */
export function resolved() {
  if (mode === 'light' || mode === 'dark') return mode;
  return media && media.matches ? 'dark' : 'light';
}

const COLOR_LIGHT = '#f5f5f7';
const COLOR_DARK = '#000000';

function apply() {
  const actual = resolved();
  document.documentElement.setAttribute('data-theme', actual);
  const metas = document.querySelectorAll('meta[name="theme-color"]');
  metas.forEach((meta) => {
    if (mode === 'auto') {
      const m = meta.getAttribute('media') || '';
      if (m.includes('dark')) {
        meta.setAttribute('content', COLOR_DARK);
      } else if (m.includes('light')) {
        meta.setAttribute('content', COLOR_LIGHT);
      } else {
        meta.setAttribute('content', actual === 'dark' ? COLOR_DARK : COLOR_LIGHT);
      }
    } else {
      meta.setAttribute('content', actual === 'dark' ? COLOR_DARK : COLOR_LIGHT);
    }
  });
  listeners.forEach((fn) => {
    try {
      fn(actual, mode);
    } catch { /* 忽略单个订阅者异常 */ }
  });
}

/** 设置模式并持久化 */
export function setMode(next) {
  mode = next === 'light' || next === 'dark' ? next : 'auto';
  try {
    if (mode === 'auto') localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, mode);
  } catch { /* 隐私模式下忽略 */ }
  apply();
}

/** 订阅主题变化，返回取消订阅函数 */
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** 初始化（app.js 启动时调用一次） */
export function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem(KEY);
  } catch { /* ignore */ }
  if (saved === 'light' || saved === 'dark') mode = saved;
  else {
    // 兼容旧版 WebUI 的主题键
    try {
      const legacy = localStorage.getItem('tqsync_theme_legacy');
      if (legacy === 'light' || legacy === 'dark') mode = legacy;
    } catch { /* ignore */ }
  }
  if (media) {
    const handler = () => { if (mode === 'auto') apply(); };
    if (media.addEventListener) media.addEventListener('change', handler);
    else if (media.addListener) media.addListener(handler);
  }
  apply();
  return mode;
}

/** 在明暗之间快速切换（保持 auto 时切到相反主题） */
export function toggle() {
  setMode(resolved() === 'dark' ? 'light' : 'dark');
}
