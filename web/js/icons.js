/**
 * TQSync WebUI 图标库 —— 内联 SVG（Miuix / HyperOS 风格）
 *
 * 设计规范：
 *   · 24×24 坐标系，内容区约 3–21，四周留 ~2px 呼吸空间
 *   · 纯线性描边，圆头圆角；统一 stroke-width 1.8（在 <svg> 根节点设置，子节点继承）
 *   · fill 恒为 none；仅少量「点」用 fill=currentColor 做实心小圆
 *   · 无依赖、无外部字体/文件，纯 ES Module，可直接被静态服务器加载
 *
 * 用法：
 *   import { svgIcon, iconPath, ICON_NAMES } from './icons.js';
 *   el.append(svgIcon('home', 20));          // <svg class="mi-icon">，颜色跟随 currentColor
 *   btn.innerHTML = iconPath('chevron-right'); // 只取内部标记字符串
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

/* 未知图标降级为中性圆点，保证 svgIcon 永不抛错、永不返回 null */
const FALLBACK = '<circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none"/>';

/* 图标名 -> 内部 SVG 标记（不含外层 <svg>） */
const ICONS = {
  /* ───────────── 导航 ───────────── */

  home:
    '<path d="M3 11l9-7.5 9 7.5"/>' +
    '<path d="M5.5 9.8v9.2a1.8 1.8 0 0 0 1.8 1.8h9.4a1.8 1.8 0 0 0 1.8-1.8V9.8"/>' +
    '<path d="M9.6 20.8v-4.6h4.8v4.6"/>',

  /* 仪表盘：近 240° 表圈 + 指针 + 两侧刻度 */
  gauge:
    '<path d="M3.7 20.4A9.6 9.6 0 1 1 20.3 20.4"/>' +
    '<path d="M12 15.5l4.9-4.9"/>' +
    '<path d="M4.7 11.4l1.2.7M19.3 11.4l-1.2.7"/>',

  sliders:
    '<path d="M3.6 6.5h3.9M12.1 6.5h8.3"/>' +
    '<circle cx="10.1" cy="6.5" r="2.1"/>' +
    '<path d="M3.6 12h8.4M16.6 12h3.8"/>' +
    '<circle cx="14.6" cy="12" r="2.1"/>' +
    '<path d="M3.6 17.5h2.2M10.5 17.5h9.9"/>' +
    '<circle cx="8.5" cy="17.5" r="2.1"/>',

  users:
    '<circle cx="9.2" cy="8" r="3.3"/>' +
    '<path d="M3.4 20c.4-3.5 2.8-5.7 5.8-5.7s5.4 2.2 5.8 5.7"/>' +
    '<path d="M15.6 5.2a3.3 3.3 0 0 1 0 5.8"/>' +
    '<path d="M16.8 14.9c2.3.7 3.7 2.6 4 5.1"/>',

  /* 拼图：上/右为方肩凸耳，下/左为内凹插座（插件语义） */
  puzzle:
    '<path d="M5 7.2 7.3 7.2A1 1 0 0 0 8.3 6.2L8.3 5.2A2 2 0 0 1 12.3 5.2L12.3 6.2A1 1 0 0 0 13.3 7.2L15.6 7.2A1.2 1.2 0 0 1 16.8 8.4L16.8 10.7A1 1 0 0 0 17.8 11.7L18.8 11.7A2 2 0 0 1 18.8 15.7L17.8 15.7A1 1 0 0 0 16.8 16.7L16.8 19A1.2 1.2 0 0 1 15.6 20.2L13.3 20.2A1 1 0 0 1 12.3 19.2L12.3 18.2A2 2 0 0 0 8.3 18.2L8.3 19.2A1 1 0 0 1 7.3 20.2L5 20.2A1.2 1.2 0 0 1 3.8 19L3.8 16.7A1 1 0 0 1 4.8 15.7L5.8 15.7A2 2 0 0 0 5.8 11.7L4.8 11.7A1 1 0 0 1 3.8 10.7L3.8 8.4A1.2 1.2 0 0 1 5 7.2Z"/>',

  logs:
    '<circle cx="4.9" cy="6.6" r="1.15" fill="currentColor" stroke="none"/>' +
    '<circle cx="4.9" cy="12" r="1.15" fill="currentColor" stroke="none"/>' +
    '<circle cx="4.9" cy="17.4" r="1.15" fill="currentColor" stroke="none"/>' +
    '<path d="M8.9 6.6h10.6M8.9 12h10.6M8.9 17.4h10.6"/>',

  settings:
    '<path d="M21 10.2A9.2 9.2 0 0 1 21 13.8L18.7 13.3A6.8 6.8 0 0 1 17.6 15.8L19.6 17.1A9.2 9.2 0 0 1 17.1 19.6L15.8 17.6A6.8 6.8 0 0 1 13.3 18.7L13.8 21A9.2 9.2 0 0 1 10.2 21L10.7 18.7A6.8 6.8 0 0 1 8.2 17.6L6.9 19.6A9.2 9.2 0 0 1 4.4 17.1L6.4 15.8A6.8 6.8 0 0 1 5.3 13.3L3 13.8A9.2 9.2 0 0 1 3 10.2L5.3 10.7A6.8 6.8 0 0 1 6.4 8.2L4.4 6.9A9.2 9.2 0 0 1 6.9 4.4L8.2 6.4A6.8 6.8 0 0 1 10.7 5.3L10.2 3A9.2 9.2 0 0 1 13.8 3L13.3 5.3A6.8 6.8 0 0 1 15.8 6.4L17.1 4.4A9.2 9.2 0 0 1 19.6 6.9L17.6 8.2A6.8 6.8 0 0 1 18.7 10.7L21 10.2Z"/>' +
    '<circle cx="12" cy="12" r="2.8"/>',

  /* ───────────── 方向 / 翻页 ───────────── */

  'chevron-right': '<path d="M9 5.5 15.5 12 9 18.5"/>',
  'chevron-left': '<path d="M15 5.5 8.5 12 15 18.5"/>',
  'chevron-down': '<path d="M5.5 9 12 15.5 18.5 9"/>',

  'arrow-left':
    '<path d="M20 12H4.5"/>' +
    '<path d="M10.4 6.2 4.6 12l5.8 5.8"/>',

  /* ───────────── 基础操作 ───────────── */

  close: '<path d="M6.2 6.2 17.8 17.8M17.8 6.2 6.2 17.8"/>',
  check: '<path d="M4.8 12.4 9.5 17.2 19.2 6.8"/>',
  plus: '<path d="M12 4.8v14.4M4.8 12h14.4"/>',

  trash:
    '<path d="M4.4 6.5H19.6"/>' +
    '<path d="M9.4 6.5V4.9a1.4 1.4 0 0 1 1.4-1.4h2.4a1.4 1.4 0 0 1 1.4 1.4v1.6"/>' +
    '<path d="M6.4 6.5l.9 12.3a1.7 1.7 0 0 0 1.7 1.6h6a1.7 1.7 0 0 0 1.7-1.6l.9-12.3"/>' +
    '<path d="M10.2 10.7v6.2M13.8 10.7v6.2"/>',

  refresh:
    '<path d="M3.2 12a8.8 8.8 0 0 1 8.8-8.8 9.5 9.5 0 0 1 6.55 2.6L20.8 8.6"/>' +
    '<path d="M20.8 3.8v4.8h-4.8"/>' +
    '<path d="M20.8 12a8.8 8.8 0 0 1-8.8 8.8 9.5 9.5 0 0 1-6.55-2.6L3.2 15.4"/>' +
    '<path d="M3.2 20.2v-4.8h4.8"/>',

  upload:
    '<path d="M12 15.5V4"/>' +
    '<path d="M7.2 8.8 12 4l4.8 4.8"/>' +
    '<path d="M4.4 15v3.3a1.8 1.8 0 0 0 1.8 1.8h11.6a1.8 1.8 0 0 0 1.8-1.8V15"/>',

  download:
    '<path d="M12 4v11.5"/>' +
    '<path d="M7.2 10.7 12 15.5l4.8-4.8"/>' +
    '<path d="M4.4 15v3.3a1.8 1.8 0 0 0 1.8 1.8h11.6a1.8 1.8 0 0 0 1.8-1.8V15"/>',

  /* ───────────── 可见性 / 主题 ───────────── */

  eye:
    '<path d="M2.8 12C5.2 7.9 8.4 6 12 6s6.8 1.9 9.2 6c-2.4 4.1-5.6 6-9.2 6s-6.8-1.9-9.2-6Z"/>' +
    '<circle cx="12" cy="12" r="3"/>',

  'eye-off':
    '<path d="M2.8 12C5.2 7.9 8.4 6 12 6s6.8 1.9 9.2 6c-2.4 4.1-5.6 6-9.2 6s-6.8-1.9-9.2-6Z"/>' +
    '<path d="M3.6 3.6 20.4 20.4"/>',

  lock:
    '<rect x="4.8" y="10.4" width="14.4" height="10" rx="2.6"/>' +
    '<path d="M8 10.4V7.8a4 4 0 0 1 8 0v2.6"/>' +
    '<circle cx="12" cy="14.4" r="1.05" fill="currentColor" stroke="none"/>' +
    '<path d="M12 15v1.9"/>',

  moon: '<path d="M12 3a6.5 6.5 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',

  sun:
    '<circle cx="12" cy="12" r="3.6"/>' +
    '<path d="M12 3.2v3.4M12 17.4v3.4M3.2 12h3.4M17.4 12h3.4"/>' +
    '<path d="M5.8 5.8l2.4 2.4M15.8 15.8l2.4 2.4M18.2 5.8l-2.4 2.4M5.8 18.2l2.4-2.4"/>',

  /* 主题「自动」：对比度圆盘，右半实心 */
  auto:
    '<path d="M12 3.5a8.5 8.5 0 0 1 0 17Z" fill="currentColor" stroke="none"/>' +
    '<circle cx="12" cy="12" r="8.5"/>',

  /* ───────────── 平台 ───────────── */

  telegram:
    '<path d="M21.4 2.6 14.9 21.4l-3.8-8.6-8.6-3.8L21.4 2.6Z"/>' +
    '<path d="M21.4 2.6 11.1 12.8"/>',

  /* QQ：企鹅 —— 身体轮廓 + 翅膀 + 双眼 + 喙 + 双脚 */
  qq:
    '<path d="M12 3.6c-2.8 0-4.7 2.2-4.7 5v.6c0 1.2-.3 2.3-.8 3.4-.7 1.6-2.1 2.6-2.1 4.2 0 1.8 3.2 2.9 7.6 2.9s7.6-1.1 7.6-2.9c0-1.6-1.4-2.6-2.1-4.2-.5-1.1-.8-2.2-.8-3.4v-.6c0-2.8-1.9-5-4.7-5Z"/>' +
    '<path d="M7.3 12.4c-.7 1.7-.5 3.4.4 4.7M16.7 12.4c.7 1.7.5 3.4-.4 4.7"/>' +
    '<circle cx="10.1" cy="8.5" r="1.2" fill="currentColor" stroke="none"/>' +
    '<circle cx="13.9" cy="8.5" r="1.2" fill="currentColor" stroke="none"/>' +
    '<path d="M10.9 11.1h2.2l-1.1 1.2-1.1-1.2Z" fill="currentColor" stroke="none"/>' +
    '<path d="M10.2 19.6l-1.1 1.6M13.8 19.6l1.1 1.6"/>',

  /* ───────────── 硬件 / 状态 ───────────── */

  cpu:
    '<rect x="6" y="6" width="12" height="12" rx="2.6"/>' +
    '<rect x="9.6" y="9.6" width="4.8" height="4.8" rx="1.1"/>' +
    '<path d="M9 3.2v2.8M15 3.2v2.8M9 18v2.8M15 18v2.8M3.2 9h2.8M3.2 15h2.8M18 9h2.8M18 15h2.8"/>',

  /* 内存条：外壳 + 金手指 + 颗粒 */
  memory:
    '<rect x="2.6" y="5" width="18.8" height="12" rx="2.2"/>' +
    '<path d="M2.6 14.6h18.8"/>' +
    '<path d="M7 17v3.4M10.4 17v3.4M13.6 17v3.4M17 17v3.4"/>' +
    '<path d="M7.5 9.4V7.8M12 9.4V7.8M16.5 9.4V7.8"/>',

  /* 磁盘：硬盘盒（分线 + 指示灯） */
  disk:
    '<rect x="3" y="6" width="18" height="12" rx="2.8"/>' +
    '<path d="M3 13.4h18"/>' +
    '<circle cx="16.9" cy="16.6" r="1.05" fill="currentColor" stroke="none"/>' +
    '<path d="M6.6 16.6h4.6"/>',

  database:
    '<ellipse cx="12" cy="6.2" rx="8" ry="2.8"/>' +
    '<path d="M4 6.2v12c0 1.55 3.6 2.8 8 2.8s8-1.25 8-2.8v-12"/>' +
    '<path d="M4 12c0 1.55 3.6 2.8 8 2.8s8-1.25 8-2.8"/>',

  activity: '<path d="M2.8 12h3.9l2.4-6.2 4 12.4 2.4-6.2h5.7"/>',

  wifi:
    '<path d="M2.6 9a14 14 0 0 1 18.8 0"/>' +
    '<path d="M5.6 12.4a9.4 9.4 0 0 1 12.8 0"/>' +
    '<path d="M8.7 15.8a5 5 0 0 1 6.6 0"/>' +
    '<circle cx="12" cy="19.3" r="1.15" fill="currentColor" stroke="none"/>',

  'wifi-off':
    '<path d="M2.6 9a14 14 0 0 1 18.8 0"/>' +
    '<path d="M5.6 12.4a9.4 9.4 0 0 1 12.8 0"/>' +
    '<path d="M8.7 15.8a5 5 0 0 1 6.6 0"/>' +
    '<circle cx="12" cy="19.3" r="1.15" fill="currentColor" stroke="none"/>' +
    '<path d="M3.6 3.6 20.4 20.4"/>',

  /* ───────────── 提示 ───────────── */

  warning:
    '<path d="M10.7 4.4 3.4 17.3a2 2 0 0 0 1.74 3h13.72a2 2 0 0 0 1.74-3L13.3 4.4a1.5 1.5 0 0 0-2.6 0Z"/>' +
    '<path d="M12 9.4v4.4"/>' +
    '<circle cx="12" cy="16.6" r="1" fill="currentColor" stroke="none"/>',

  info:
    '<circle cx="12" cy="12" r="8.6"/>' +
    '<path d="M12 11v5.2"/>' +
    '<circle cx="12" cy="7.9" r="1.05" fill="currentColor" stroke="none"/>',

  /* ───────────── 功能操作 ───────────── */

  copy:
    '<rect x="8.6" y="8.6" width="12.2" height="12.2" rx="2.6"/>' +
    '<path d="M5.2 15.4V6.8a2.6 2.6 0 0 1 2.6-2.6h8.6"/>',

  search:
    '<circle cx="10.7" cy="10.7" r="7.1"/>' +
    '<path d="M15.9 15.9 20.9 20.9"/>',

  more:
    '<circle cx="5.2" cy="12" r="1.5" fill="currentColor" stroke="none"/>' +
    '<circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>' +
    '<circle cx="18.8" cy="12" r="1.5" fill="currentColor" stroke="none"/>',

  power:
    '<path d="M6.34 6.34A8 8 0 1 0 17.66 6.34"/>' +
    '<path d="M12 3.2v8.4"/>',

  clock:
    '<circle cx="12" cy="12" r="8.6"/>' +
    '<path d="M12 7.4V12l3.2 2"/>',

  shield:
    '<path d="M12 3.4 19.4 6v5.4c0 4.6-3 8.2-7.4 9.3-4.4-1.1-7.4-4.7-7.4-9.3V6L12 3.4Z"/>' +
    '<path d="M9.1 12.2l2 2 3.8-3.8"/>',

  filter: '<path d="M3.4 5.2h17.2l-6.8 7.5v5.9l-3.6-1.9v-4L3.4 5.2Z"/>',

  external:
    '<path d="M14 4.4h5.6V10"/>' +
    '<path d="M19.2 4.8 11.2 12.8"/>' +
    '<path d="M19 14.2v4.2a2.2 2.2 0 0 1-2.2 2.2H5.6a2.2 2.2 0 0 1-2.2-2.2V7.2a2.2 2.2 0 0 1 2.2-2.2H10"/>',

  edit:
    '<path d="M4 20l.9-3.6L15.3 6a2 2 0 0 1 2.8 0l.3.3a2 2 0 0 1 0 2.8L7.6 19.1 4 20Z"/>' +
    '<path d="M13.2 7.2l3.5 3.5"/>',

  /* 同步：双向箭头（区别于 refresh 的单向环） */
  sync:
    '<path d="M3.6 8.4h13.8"/>' +
    '<path d="M14.2 5.2 17.4 8.4l-3.2 3.2"/>' +
    '<path d="M20.4 15.6H6.6"/>' +
    '<path d="M9.8 12.4 6.6 15.6l3.2 3.2"/>',

  server:
    '<rect x="3.2" y="3.8" width="17.6" height="7" rx="2.2"/>' +
    '<rect x="3.2" y="13.2" width="17.6" height="7" rx="2.2"/>' +
    '<circle cx="7.2" cy="7.3" r="1.05" fill="currentColor" stroke="none"/>' +
    '<circle cx="7.2" cy="16.7" r="1.05" fill="currentColor" stroke="none"/>' +
    '<path d="M15 7.3h2.6M15 16.7h2.6"/>',

  bell:
    '<path d="M17.8 8.5A6 6 0 0 0 6.2 8.5c0 6.4-1.6 8.6-2.8 8.6h17.2c-1.2 0-2.8-2.2-2.8-8.6Z"/>' +
    '<path d="M10.2 17.4a1.9 1.9 0 0 0 3.6 0"/>',

  /* 星芒：主星 + 右下角小星，用于「智能 / 亮点」 */
  sparkle:
    '<path d="M11 3.8 12.7 9.3 18.2 11 12.7 12.7 11 18.2 9.3 12.7 3.8 11 9.3 9.3 11 3.8Z"/>' +
    '<path d="M18.4 15.3l.6 1.7 1.7.6-1.7.6-.6 1.7-.6-1.7-1.7-.6 1.7-.6.6-1.7Z"/>',
};

/** 全部图标名（顺序与 ICONS 定义一致） */
export const ICON_NAMES = Object.keys(ICONS);

/**
 * 返回某个图标的内部 SVG 标记字符串；未知名称返回空串。
 * @param {string} name 图标名
 * @returns {string}
 */
export function iconPath(name) {
  return typeof name === 'string' && Object.prototype.hasOwnProperty.call(ICONS, name)
    ? ICONS[name]
    : '';
}

/**
 * 按名称创建 <svg> 元素；未知名称降级为圆点，绝不抛错。
 * 描边/填充等表现属性挂在根节点上，子路径自动继承，颜色跟随 CSS currentColor。
 * @param {string} name 图标名
 * @param {number} [size=24] 宽高（px）
 * @returns {SVGSVGElement}
 */
export function svgIcon(name, size = 24) {
  const px = Number(size) > 0 ? Number(size) : 24;
  const svg = document.createElementNS(SVG_NS, 'svg');

  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', px);
  svg.setAttribute('height', px);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.setAttribute('class', 'mi-icon');

  svg.innerHTML = iconPath(name) || FALLBACK;
  return svg;
}
