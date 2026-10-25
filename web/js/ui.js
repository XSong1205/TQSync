/**
 * TQSync WebUI —— Miuix 组件库（零依赖）
 * =====================================================================
 * 统一导出 DOM 工具 + 组件工厂 + 交互反馈。所有组件返回真实 DOM 节点，
 * 由调用方自由组合，不做虚拟 DOM diff（页面级重绘即可，保证实现简单可靠）。
 *
 * 约定：
 *  - 颜色、圆角、动效全部走 CSS 变量（miuix.css）
 *  - 事件回调里的异常由调用方自行 try/catch；需要提示时用 toastErr()
 *  - 所有文本默认中文
 * =====================================================================
 * 快速索引：
 *   DOM：h, clear, append
 *   ├─ 布局   card, cardGroup, sectionTitle, row, divider, metricsGrid, between
 *   ├─ 展示   badge, chip, avatar, progress, barChart, emptyState, alert,
 *            errorBlock, loadingBlock, skeleton, keyValue
 *   ├─ 控件   button, iconButton, switchControl, field, searchBar, segmented,
 *            selectField, sliderRow, pickFile
 *   └─ 浮层   toast, dialog, confirm, actionSheet, openSheet
 *   工具：  debounce, formatUptime, copyText, vibrate, sleep
 */

import { svgIcon } from './icons.js';

/* ─────────────────────────────────────────────────────────────────────
   DOM helpers
   ───────────────────────────────────────────────────────────────────── */

/**
 * 极简 hyperscript。
 * @param {string} tag
 * @param {object|null} attrs  class/style/dataset/onXxx/属性；值为 null|undefined|false 时忽略
 * @param {...(Node|string|number|false|null|undefined|Array)} children
 */
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class' || k === 'className') {
        el.className = Array.isArray(v) ? v.filter(Boolean).join(' ') : v;
      } else if (k === 'style' && typeof v === 'object') {
        for (const [sk, sv] of Object.entries(v)) {
          if (sv === null || sv === undefined) continue;
          if (sk.startsWith('--')) el.style.setProperty(sk, sv);
          else el.style[sk] = sv;
        }
      } else if (k === 'dataset') {
        Object.assign(el.dataset, v);
      } else if (k === 'html') {
        el.innerHTML = v;
      } else if (k.startsWith('on') && typeof v === 'function') {
        el.addEventListener(k.slice(2).toLowerCase(), v);
      } else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'selected' || k === 'textContent') {
        el[k] = v;
      } else {
        el.setAttribute(k, v === true ? '' : String(v));
      }
    }
  }
  append(el, children);
  return el;
}

/** 递归追加子节点，忽略空值 */
export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false || child === '') continue;
    parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

/** 清空节点 */
export function clear(el) {
  while (el && el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export const icon = (name, size = 24) => svgIcon(name, size);

/**
 * TQSync 品牌标识（白色同步双箭头）。
 * 用 createElementNS 构造，避免 h('svg') 生成 HTML 命名空间元素而不显示。
 * @param {number} size
 * @param {string} color
 */
export function brandMark(size = 32, color = '#fff') {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 48 48');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('fill', 'none');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML =
    `<path d="M15.5 24a8.5 8.5 0 0 1 14.6-5.9M32.5 24a8.5 8.5 0 0 1-14.6 5.9" stroke="${color}" stroke-width="3.2" stroke-linecap="round"/>` +
    `<path d="M29.4 13.2v4.6h-4.6M18.6 34.8v-4.6h4.6" stroke="${color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>`;
  return svg;
}

/** 相对定位容器（水波纹需要） */
function tapFeedback(el) {
  el.style.position = el.style.position || 'relative';
  el.addEventListener('pointerdown', (ev) => {
    const rect = el.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    const span = h('span', {
      class: 'mi-ripple',
      style: {
        width: `${size}px`,
        height: `${size}px`,
        left: `${ev.clientX - rect.left - size / 2}px`,
        top: `${ev.clientY - rect.top - size / 2}px`,
      },
    });
    el.appendChild(span);
    setTimeout(() => span.remove(), 560);
  });
}

/* ─────────────────────────────────────────────────────────────────────
   布局组件
   ───────────────────────────────────────────────────────────────────── */

/**
 * 卡片
 * @param {{children?:any[], padded?:boolean, tone?:'plain'|'outlined'|'accent', className?:string,
 *          onClick?:Function, id?:string}} opts
 */
export function card(opts = {}) {
  const { children = [], padded = true, tone = '', className = '', onClick, id } = opts;
  const classes = ['mi-card', padded && 'mi-card--padded', tone && `mi-card--${tone}`, onClick && 'mi-card--tappable', className];
  const el = h('div', {
    class: classes,
    id: id || null,
    role: onClick ? 'button' : null,
    tabindex: onClick ? '0' : null,
    onClick: onClick || null,
    onKeydown: onClick
      ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick(e);
          }
        }
      : null,
  });
  if (onClick) tapFeedback(el);
  append(el, children);
  return el;
}

/**
 * 分组列表容器（iOS/HyperOS 设置风格）
 * @param {{children?:any[], header?:string, footer?:string, className?:string, flat?:boolean}} opts
 */
export function cardGroup(opts = {}) {
  const { children = [], header, footer, className = '', flat = false } = opts;
  const wrap = h('section', { class: ['mi-group-wrap', className] });
  if (header) wrap.appendChild(h('div', { class: 'mi-group__header' }, header));
  const group = h('div', { class: ['mi-group', flat && 'mi-group--flat'] });
  const body = h('div', { class: 'mi-group__body' });
  append(body, children);
  group.appendChild(body);
  wrap.appendChild(group);
  if (footer) wrap.appendChild(h('div', { class: 'mi-group__footer' }, footer));
  return wrap;
}

/** 小节标题（Miuix SmallTitle：蓝灰色普通字重，无图标装饰） */
export function sectionTitle(text) {
  return h('div', { class: 'mi-section-title' }, text);
}

/**
 * 列表行
 * @param {{
 *   title: string, subtitle?: string, icon?: string, iconTone?: 'success'|'warning'|'danger'|'neutral'|'plain',
 *   value?: string, chevron?: boolean, onClick?: Function, control?: Node, trailing?: Node|Node[],
 *   danger?: boolean, comfortable?: boolean, compact?: boolean, className?: string, titleAttr?: string
 * }} opts
 */
export function row(opts = {}) {
  const {
    title, subtitle, icon: iconName, iconTone = '', value, chevron = false, onClick,
    control, trailing, danger = false, comfortable = false, compact = false, className = '', titleAttr,
  } = opts;

  const interactive = typeof onClick === 'function' && !control;
  const tag = interactive ? 'button' : 'div';
  const el = h(tag, {
    class: [
      'mi-row',
      interactive && 'mi-row--tappable',
      comfortable && 'mi-row--comfortable',
      compact && 'mi-row--compact',
      danger && 'mi-row--danger',
      className,
    ],
    type: interactive ? 'button' : null,
    onClick: interactive ? onClick : null,
    title: titleAttr || null,
  });

  if (iconName) {
    el.appendChild(
      h('span', { class: ['mi-row__icon', iconTone && `mi-row__icon--${iconTone}`, iconTone === 'plain' && 'mi-row__icon--plain'] }, icon(iconName, 20))
    );
  }

  const content = h('div', { class: 'mi-row__content' });
  content.appendChild(h('div', { class: 'mi-row__title' }, title));
  if (subtitle) content.appendChild(h('div', { class: 'mi-row__subtitle' }, subtitle));
  el.appendChild(content);

  if (value !== undefined && value !== null && value !== '') {
    el.appendChild(h('div', { class: 'mi-row__value', title: String(value) }, String(value)));
  }
  if (control) el.appendChild(h('div', { class: 'mi-row__trailing' }, control));
  if (trailing) el.appendChild(h('div', { class: 'mi-row__trailing' }, trailing));
  if (chevron) el.appendChild(h('span', { class: 'mi-row__chevron' }, icon('chevron-right', 18)));
  if (interactive) tapFeedback(el);
  return el;
}

/** 分割线 */
export function divider() {
  return h('hr', { class: 'mi-divider' });
}

/** 竖向堆叠容器 */
export function stack(...children) {
  return append(h('div', { class: 'mi-stack' }), children);
}

/** 两端对齐容器 */
export function between(left, right) {
  return h('div', { class: 'mi-between' }, h('div', { class: 'mi-grow' }, left), right);
}

/**
 * 指标网格
 * @param {Array<{label:string, value:string, sub?:string, icon?:string, tone?:string}>} items
 */
export function metricsGrid(items) {
  const grid = h('div', { class: 'mi-metrics' });
  for (const it of items) {
    grid.appendChild(
      h(
        'div',
        { class: ['mi-metric', it.tone && `mi-metric--${it.tone}`] },
        h('div', { class: 'mi-metric__head' }, it.icon ? icon(it.icon, 14) : null, it.label),
        h('div', { class: 'mi-metric__value', title: it.value }, it.value),
        it.sub ? h('div', { class: 'mi-metric__sub' }, it.sub) : null
      )
    );
  }
  return grid;
}

/**
 * 键值展示
 * @param {Array<{k:string, v:string}>} pairs
 */
export function keyValue(pairs) {
  const items = pairs.map(({ k, v }) =>
    h('div', { class: 'mi-kv' }, h('div', { class: 'mi-kv__k' }, k), h('div', { class: 'mi-kv__v' }, v))
  );
  return h('div', { class: 'mi-stack', style: { gap: '12px' } }, ...items);
}

/* ─────────────────────────────────────────────────────────────────────
   展示组件
   ───────────────────────────────────────────────────────────────────── */

/** 徽标 */
export function badge(text, tone = 'neutral', iconName) {
  return h('span', { class: ['mi-badge', `mi-badge--${tone}`] }, iconName ? icon(iconName, 12) : null, text);
}

/**
 * 可删除标签
 * @param {{text:string, tone?:string, icon?:string, onRemove?:Function, onClick?:Function, removeLabel?:string}} opts
 */
export function chip(opts = {}) {
  const { text, tone = '', icon: iconName, onRemove, onClick, removeLabel = '移除' } = opts;
  const el = h(
    'span',
    {
      class: ['mi-chip', tone && `mi-chip--${tone}`],
      role: onClick ? 'button' : null,
      tabindex: onClick ? '0' : null,
    },
    iconName ? icon(iconName, 14) : null,
    h('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, text)
  );
  if (onClick) {
    el.addEventListener('click', onClick);
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClick(e);
      }
    });
  }
  if (onRemove) {
    el.appendChild(
      h('button', {
        class: 'mi-chip__remove',
        type: 'button',
        'aria-label': removeLabel || '移除',
        onClick: (e) => {
          e.stopPropagation();
          onRemove(e);
        },
      }, icon('close', 12))
    );
  }
  return el;
}

/** 头像（文字缩写） */
export function avatar({ text = '', tone = '', icon: iconName } = {}) {
  return h('span', { class: ['mi-avatar', tone && `mi-avatar--${tone}`] }, iconName ? icon(iconName, 20) : text);
}

/** 线性进度条 */
export function progress({ value = 0, tone = '', indeterminate = false } = {}) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  return h(
    'div',
    { class: ['mi-progress', indeterminate && 'mi-progress--indeterminate'], role: 'progressbar', 'aria-valuenow': String(v) },
    h('div', { class: ['mi-progress__fill', tone && `mi-progress__fill--${tone}`], style: { width: `${v}%` } })
  );
}

/**
 * 柱状图（最近 N 小时消息量）
 * @param {{data:Array<{label:string, value:number}>, height?:number}} opts
 */
export function barChart({ data = [], height = 84 } = {}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const wrap = h('div', { class: 'mi-chart', style: { height: `${height}px` } });
  data.forEach((d, i) => {
    const pct = Math.max(4, (d.value / max) * 100);
    const bar = h('div', {
      class: ['mi-chart__bar', d.value === max && max > 0 && 'mi-chart__bar--active'],
      style: {
        height: `${pct}%`,
        animationDelay: `${Math.min(i * 12, 260)}ms`,
      },
      title: `${d.label} · ${d.value}`,
    });
    wrap.appendChild(bar);
  });
  const axis = h(
    'div',
    { class: 'mi-chart__axis' },
    h('span', null, data.length ? data[0].label : ''),
    h('span', null, data.length ? data[data.length - 1].label : '')
  );
  return h('div', null, wrap, axis);
}

/** 空状态 */
export function emptyState({ icon: iconName = 'sparkle', title = '暂无内容', desc = '', actionText = '', onAction = null } = {}) {
  return h(
    'div',
    { class: 'mi-empty' },
    h('div', { class: 'mi-empty__icon' }, icon(iconName, 28)),
    h('div', { class: 'mi-empty__title' }, title),
    desc ? h('div', { class: 'mi-empty__desc' }, desc) : null,
    actionText && onAction ? h('div', { class: 'mi-empty__action' }, button({ text: actionText, variant: 'tonal', size: 'sm', onClick: onAction })) : null
  );
}

/** 内联提示条 */
export function alert({ tone = 'info', text = '', iconName, children } = {}) {
  const ic = iconName || (tone === 'danger' || tone === 'warning' ? 'warning' : tone === 'success' ? 'check' : 'info');
  return h(
    'div',
    { class: ['mi-alert', tone !== 'info' && `mi-alert--${tone}`] },
    h('span', { class: 'mi-alert__icon' }, icon(ic, 17)),
    h('div', { class: 'mi-grow' }, children || text)
  );
}

/** 错误态（带重试） */
export function errorBlock({ title = '加载失败', message = '', onRetry = null } = {}) {
  return h(
    'div',
    { class: 'mi-empty' },
    h('div', { class: 'mi-empty__icon', style: { color: 'var(--mi-danger)' } }, icon('warning', 28)),
    h('div', { class: 'mi-empty__title' }, title),
    message ? h('div', { class: 'mi-empty__desc' }, message) : null,
    onRetry
      ? h('div', { class: 'mi-empty__action' }, button({ text: '重试', variant: 'tonal', size: 'sm', icon: 'refresh', onClick: onRetry }))
      : null
  );
}

/** 加载块 */
export function loadingBlock(text = '加载中…') {
  return h('div', { class: 'mi-loading-block' }, h('div', { class: 'mi-spinner' }), h('span', null, text));
}

/** 骨架屏 */
export function skeleton({ type = 'list', count = 3 } = {}) {
  if (type === 'page') {
    const wrap = h('div', { class: 'mi-stagger' });
    wrap.appendChild(h('div', { class: 'mi-skeleton', style: { height: '34px', width: '46%', margin: '8px 16px 20px' } }));
    for (let i = 0; i < 2; i++) {
      const group = h('div', { class: 'mi-skeleton-group' });
      for (let j = 0; j < 3; j++) {
        group.appendChild(h('div', { style: { display: 'flex', gap: '12px', alignItems: 'center' } },
          h('div', { class: 'mi-skeleton', style: { width: '34px', height: '34px', borderRadius: '10px', flex: 'none' } }),
          h('div', { style: { flex: '1', display: 'flex', flexDirection: 'column', gap: '7px' } },
            h('div', { class: 'mi-skeleton', style: { width: '42%', height: '12px' } }),
            h('div', { class: 'mi-skeleton', style: { width: '68%', height: '10px' } })
          )
        ));
      }
      wrap.appendChild(group);
    }
    return wrap;
  }
  if (type === 'card') {
    const wrap = h('div', { style: { padding: '0 16px', display: 'flex', flexDirection: 'column', gap: '12px' } });
    for (let i = 0; i < count; i++) wrap.appendChild(h('div', { class: 'mi-skeleton mi-skeleton--card' }));
    return wrap;
  }
  const wrap = h('div', { class: 'mi-skeleton-group' });
  for (let i = 0; i < count; i++) {
    wrap.appendChild(
      h('div', { style: { display: 'flex', gap: '12px', alignItems: 'center' } },
        h('div', { class: 'mi-skeleton', style: { width: '22px', height: '22px', borderRadius: '7px', flex: 'none' } }),
        h('div', { class: 'mi-skeleton', style: { flex: '1', height: '13px' } })
      )
    );
  }
  return wrap;
}

/* ─────────────────────────────────────────────────────────────────────
   控件
   ───────────────────────────────────────────────────────────────────── */

/**
 * 按钮
 * @param {{text?:string, icon?:string, variant?:'filled'|'tonal'|'outlined'|'text'|'danger'|'neutral',
 *          size?:'sm'|'md', block?:boolean, onClick?:Function, loading?:boolean, disabled?:boolean, type?:string,
 *          ariaLabel?:string, className?:string}} opts
 * @returns {HTMLButtonElement & {setLoading:(b:boolean)=>void, setText:(t:string)=>void}}
 */
export function button(opts = {}) {
  const {
    text = '', icon: iconName = '', variant = 'filled', size = 'md', block = false,
    onClick = null, loading = false, disabled = false, type = 'button', ariaLabel = '', className = '',
  } = opts;
  const cls = [
    'mi-btn', `mi-btn--${variant}`, size === 'sm' && 'mi-btn--sm',
    block && 'mi-btn--block', !text && iconName && 'mi-btn--icon', className,
  ];
  const label = h('span', { class: 'mi-btn__label' }, text);
  const ic = h('span', { class: 'mi-btn__icon' }, icon(iconName, size === 'sm' ? 16 : 18));
  const spinner = h('span', { class: 'mi-btn__spinner', hidden: true });

  const el = h('button', { class: cls, type, disabled: disabled || loading, 'aria-label': ariaLabel || null, onClick }, spinner, ic, text ? label : null);
  el.setLoading = (b) => {
    el.disabled = Boolean(b) || disabled;
    spinner.hidden = !b;
    ic.hidden = Boolean(b);
  };
  el.setText = (t) => {
    label.textContent = t;
  };
  if (!iconName) ic.remove();
  if (loading) el.setLoading(true);
  if (!text && !iconName) label.remove();
  tapFeedback(el);
  return el;
}

/** 图标按钮 */
export function iconButton({ icon: iconName, label = '', onClick = null, className = '' } = {}) {
  const el = h('button', { class: ['mi-btn mi-btn--icon', className], type: 'button', 'aria-label': label, title: label, onClick }, icon(iconName, 20));
  tapFeedback(el);
  return el;
}

/**
 * 开关（受控 + 乐观更新）
 * @param {{checked?:boolean, onChange?:(v:boolean)=>any, disabled?:boolean, ariaLabel?:string}} opts
 * @returns {HTMLButtonElement & {set:(v:boolean)=>void, isChecked:()=>boolean}}
 */
export function switchControl({ checked = false, onChange = null, disabled = false, ariaLabel = '' } = {}) {
  let value = Boolean(checked);
  let pending = false;
  const thumb = h('span', { class: 'mi-switch__thumb' });
  const el = h('button', {
    class: 'mi-switch',
    type: 'button',
    role: 'switch',
    disabled,
    'aria-checked': String(value),
    'aria-label': ariaLabel || null,
    dataset: { checked: String(value) },
  }, thumb);
  el.set = (v) => {
    value = Boolean(v);
    el.dataset.checked = String(value);
    el.setAttribute('aria-checked', String(value));
  };
  el.isChecked = () => value;
  el.addEventListener('click', async (e) => {
    if (disabled || pending) return;
    const next = !value;
    el.set(next);
    vibrate(8);
    if (typeof onChange === 'function') {
      try {
        const ret = onChange(next, e);
        if (ret && typeof ret.then === 'function') {
          pending = true;
          el.style.opacity = '0.6';
          await ret;
        }
      } catch {
        el.set(!next); // 失败回滚
      } finally {
        if (pending) {
          pending = false;
          el.style.opacity = '';
        }
      }
    }
  });
  return el;
}

/**
 * 输入框
 * @param {{label?:string, value?:string, placeholder?:string, type?:string, multiline?:boolean,
 *          supporting?:string, password?:boolean, onInput?:Function, onChange?:Function,
 *          trailing?:Node, autofocus?:boolean, maxLength?:number, inputMode?:string, rows?:number}} opts
 * @returns {{el:HTMLElement, input:HTMLInputElement|HTMLTextAreaElement, get:()=>string,
 *            set:(v:string)=>void, setError:(msg:string)=>void, focus:()=>void}}
 */
export function field(opts = {}) {
  const {
    label = '', value = '', placeholder = '', type = 'text', multiline = false,
    supporting = '', password = false, onInput = null, onChange = null,
    trailing = null, autofocus = false, maxLength = null, inputMode = null, rows = 3,
  } = opts;

  const id = `mi-field-${Math.random().toString(36).slice(2, 9)}`;
  let inputType = password ? 'password' : type;
  const input = multiline
    ? h('textarea', {
        class: 'mi-field__input', id, placeholder, rows, value,
        onInput: onInput ? (e) => onInput(e.target.value, e) : null,
        onChange: onChange ? (e) => onChange(e.target.value, e) : null,
      })
    : h('input', {
        class: 'mi-field__input', id, placeholder, type: inputType, value,
        autocomplete: password ? 'current-password' : 'off',
        autocapitalize: inputMode === 'numeric' ? 'off' : null,
        inputMode: inputMode || null,
        maxLength: maxLength || null,
        onInput: onInput ? (e) => onInput(e.target.value, e) : null,
        onChange: onChange ? (e) => onChange(e.target.value, e) : null,
      });

  const box = h('div', { class: 'mi-field__box' }, input);
  const support = h('div', { class: 'mi-field__support', hidden: !supporting }, supporting);
  const wrapper = h('div', { class: 'mi-field' }, label ? h('label', { class: 'mi-field__label', for: id }, label) : null, box, support);

  if (password) {
    const toggle = h('button', {
      class: 'mi-field__trailing', type: 'button', 'aria-label': '显示密码',
      onClick: (e) => {
        e.preventDefault();
        const show = inputType === 'password';
        inputType = show ? 'text' : 'password';
        input.type = inputType;
        clear(toggle);
        toggle.appendChild(icon(show ? 'eye-off' : 'eye', 18));
      },
    }, icon('eye', 18));
    box.appendChild(toggle);
  }
  if (trailing) box.appendChild(trailing);

  return {
    el: wrapper,
    input,
    get: () => input.value,
    set: (v) => { input.value = v == null ? '' : String(v); },
    setError: (msg) => {
      wrapper.classList.toggle('mi-field--error', Boolean(msg));
      support.hidden = !msg;
      support.textContent = msg || '';
      support.classList.toggle('mi-field__support--error', Boolean(msg));
    },
    focus: () => input.focus(),
  };
}

/** 搜索框 */
export function searchBar({ placeholder = '搜索…', value = '', onInput = null } = {}) {
  const input = h('input', {
    class: 'mi-search__input', type: 'search', placeholder, value,
    onInput: onInput ? (e) => onInput(e.target.value) : null,
  });
  const clearBtn = h('button', {
    class: 'mi-search__clear', type: 'button', 'aria-label': '清空',
    hidden: !value,
    onClick: () => {
      input.value = '';
      clearBtn.hidden = true;
      if (onInput) onInput('');
      input.focus();
    },
  }, icon('close', 15));
  input.addEventListener('input', () => { clearBtn.hidden = !input.value; });
  const el = h('div', { class: 'mi-search' }, icon('search', 17), input, clearBtn);
  return { el, input, get: () => input.value, set: (v) => { input.value = v; clearBtn.hidden = !v; } };
}

/**
 * 分段控件
 * @param {{options:Array<{value:string,label:string,icon?:string}>, value?:string, onChange?:(v:string)=>void}} opts
 * @returns {HTMLElement & {set:(v:string)=>void}}
 */
export function segmented({ options = [], value = null, onChange = null } = {}) {
  const current = value ?? (options[0] && options[0].value);
  const el = h('div', { class: 'mi-segmented', role: 'tablist' });
  el.style.setProperty('--seg-n', String(Math.max(1, options.length)));
  const thumb = h('div', { class: 'mi-segmented__thumb' });
  el.appendChild(thumb);
  const items = [];
  options.forEach((opt, idx) => {
    const btn = h('button', {
      class: 'mi-segmented__item', type: 'button', role: 'tab',
      'aria-selected': String(opt.value === current),
      dataset: { value: opt.value },
      onClick: () => {
        if (btn.getAttribute('aria-selected') === 'true') return;
        set(opt.value);
        vibrate(6);
        if (onChange) onChange(opt.value);
      },
    }, opt.icon ? icon(opt.icon, 15) : null, h('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis' } }, opt.label));
    items.push(btn);
    el.appendChild(btn);
  });
  function set(v) {
    const idx = Math.max(0, options.findIndex((o) => o.value === v));
    el.style.setProperty('--seg-i', String(idx));
    items.forEach((it, i) => it.setAttribute('aria-selected', String(i === idx)));
  }
  set(current);
  el.set = set;
  return el;
}

/**
 * 下拉选择
 * @param {{options:Array<{value:string,label:string}>, value?:string, label?:string, onChange?:(v:string)=>void}} opts
 */
export function selectField({ options = [], value = null, label = '', onChange = null } = {}) {
  const sel = h('select', {
    class: 'mi-select',
    onChange: onChange ? (e) => onChange(e.target.value) : null,
  },
    ...options.map((o) => h('option', { value: o.value, selected: o.value === value }, o.label))
  );
  if (!label) return { el: sel, select: sel, get: () => sel.value, set: (v) => { sel.value = v; } };
  return {
    el: h('div', { class: 'mi-field' }, h('div', { class: 'mi-field__label' }, label), h('div', { style: { display: 'flex' } }, sel)),
    select: sel,
    get: () => sel.value,
    set: (v) => { sel.value = v; },
  };
}

/**
 * 滑块行
 * @param {{title:string, value:number, min?:number, max?:number, step?:number, unit?:string,
 *          onChange?:(v:number)=>void, onCommit?:(v:number)=>void, desc?:string}} opts
 */
export function sliderRow(opts = {}) {
  const { title, value = 0, min = 0, max = 100, step = 1, unit = '', onChange = null, onCommit = null, desc = '' } = opts;
  const valueEl = h('span', { class: 'mi-slider-row__value' }, `${value}${unit}`);
  const input = h('input', {
    class: 'mi-slider', type: 'range', min, max, step, value,
    onInput: (e) => {
      const v = Number(e.target.value);
      valueEl.textContent = `${v}${unit}`;
      updatePct(v);
      if (onChange) onChange(v);
    },
    onChange: (e) => {
      if (onCommit) onCommit(Number(e.target.value));
    },
  });
  input.style.setProperty('--mi-slider-pct', `${((value - min) / (max - min)) * 100}%`);
  function updatePct(v) {
    input.style.setProperty('--mi-slider-pct', `${((v - min) / (max - min)) * 100}%`);
  }
  const rowEl = h('div', { class: 'mi-slider-row' },
    h('div', { class: 'mi-slider-row__head' }, h('span', { class: 'mi-row__title' }, title), valueEl),
    desc ? h('div', { class: 'mi-row__subtitle' }, desc) : null,
    input
  );
  rowEl.set = (v) => {
    input.value = v;
    valueEl.textContent = `${v}${unit}`;
    updatePct(v);
  };
  return rowEl;
}

/**
 * 文件选择
 * @param {{accept?:string, multiple?:boolean}} opts
 * @returns {Promise<File[]|null>}
 */
export function pickFile({ accept = '.py', multiple = false } = {}) {
  return new Promise((resolve) => {
    let settled = false;
    let focusTimer = null;
    const input = h('input', { type: 'file', accept, multiple, style: { display: 'none' } });
    document.body.appendChild(input);

    function cleanup() {
      if (focusTimer) clearTimeout(focusTimer);
      window.removeEventListener('focus', onWindowFocus);
      if (input.parentNode) input.remove();
    }

    function done(files) {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(files);
    }

    input.addEventListener('change', () => {
      done(Array.from(input.files || []));
    });

    input.addEventListener('cancel', () => {
      done(null);
    });

    function onWindowFocus() {
      focusTimer = setTimeout(() => {
        if (!settled && (!input.files || input.files.length === 0)) {
          done(null);
        }
      }, 300);
    }

    window.addEventListener('focus', onWindowFocus, { once: true });

    input.click();
  });
}

/* ─────────────────────────────────────────────────────────────────────
   浮层：Toast / Dialog / ActionSheet / BottomSheet
   ───────────────────────────────────────────────────────────────────── */

const TOAST_ICON = { success: 'check', error: 'warning', warning: 'warning', default: 'info' };
const MAX_TOASTS = 3;
const TOAST_DEDUP_WINDOW = 800;
const activeToasts = [];

/**
 * 轻提示
 * @param {string} message
 * @param {{type?:'default'|'success'|'error'|'warning', duration?:number}} opts
 */
export function toast(message, { type = 'default', duration = 2400 } = {}) {
  const root = document.getElementById('toast-root');
  if (!root) return { close: () => {} };

  const now = Date.now();
  const existing = activeToasts.find((t) => t.message === message && now - t.createdAt < TOAST_DEDUP_WINDOW);
  if (existing) {
    existing.createdAt = now;
    existing.resetTimer(duration);
    return { close: existing.close };
  }

  while (activeToasts.length >= MAX_TOASTS) {
    const oldest = activeToasts.shift();
    if (oldest) oldest.close();
  }

  const el = h('div', { class: ['mi-toast', type !== 'default' && `mi-toast--${type}`] },
    h('span', { class: 'mi-toast__icon' }, icon(TOAST_ICON[type] || 'info', 16)),
    h('span', null, message)
  );
  root.appendChild(el);
  requestAnimationFrame(() => el.classList.add('mi-toast--show'));

  let closed = false;
  let timer = null;

  const remove = () => {
    if (closed) return;
    closed = true;
    if (timer) clearTimeout(timer);
    const idx = activeToasts.indexOf(item);
    if (idx !== -1) activeToasts.splice(idx, 1);
    el.classList.remove('mi-toast--show');
    setTimeout(() => el.remove(), 260);
  };

  const resetTimer = (dur) => {
    if (timer) clearTimeout(timer);
    if (dur === 0) {
      timer = null;
    } else {
      timer = setTimeout(remove, Math.max(1200, dur));
    }
  };

  const item = {
    message,
    el,
    close: remove,
    createdAt: now,
    resetTimer,
  };

  activeToasts.push(item);
  resetTimer(duration);

  el.addEventListener('click', () => {
    remove();
  });
  return { close: remove };
}

/** 简化错误提示：自动提取 ApiError.detail */
export function toastErr(err, fallback = '操作失败') {
  const msg = err && (err.detail || err.message) ? err.detail || err.message : fallback;
  return toast(msg || fallback, { type: 'error', duration: 3200 });
}

const overlayStack = [];

function focusOverlay(container) {
  if (!container || !document.contains(container)) return;
  let target = container.querySelector('[data-autofocus]');
  if (!target) {
    const list = getFocusableElements(container);
    if (list.length > 0) target = list[0];
  }
  if (target && typeof target.focus === 'function') {
    target.focus({ preventScroll: true });
  } else {
    if (!container.hasAttribute('tabindex')) {
      container.setAttribute('tabindex', '-1');
    }
    container.focus({ preventScroll: true });
  }
}

function getFocusableElements(container) {
  const elements = container.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  );
  return Array.from(elements).filter((el) => {
    return !el.disabled && el.getAttribute('aria-hidden') !== 'true' && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
  });
}

function trapFocus(e, container) {
  const focusables = getFocusableElements(container);
  if (focusables.length === 0) {
    e.preventDefault();
    if (!container.hasAttribute('tabindex')) {
      container.setAttribute('tabindex', '-1');
    }
    container.focus({ preventScroll: true });
    return;
  }
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement;

  if (e.shiftKey) {
    if (active === first || !container.contains(active)) {
      e.preventDefault();
      last.focus();
    }
  } else {
    if (active === last || !container.contains(active)) {
      e.preventDefault();
      first.focus();
    }
  }
}

function restoreFocus(prevActive) {
  if (prevActive && typeof prevActive.focus === 'function' && document.contains(prevActive)) {
    try {
      prevActive.focus({ preventScroll: true });
    } catch { /* 忽略聚焦失败 */ }
  }
}

document.addEventListener('keydown', (e) => {
  if (overlayStack.length === 0) return;
  const top = overlayStack[overlayStack.length - 1];
  if (!top) return;

  if (e.key === 'Escape') {
    e.stopPropagation();
    if (typeof top.onEscape === 'function') {
      top.onEscape(e);
    } else if (typeof top.close === 'function') {
      top.close();
    }
    return;
  }

  if (e.key === 'Tab' && top.el) {
    trapFocus(e, top.el);
  }
});

function overlayRoot() {
  return document.getElementById('overlay-root');
}

/**
 * 对话框
 * @param {{title?:string, message?:string, content?:Node|string, actions?:Array<{text:string, variant?:string,
 *          value?:any, onClick?:Function}>, dismissible?:boolean, stackActions?:boolean}} opts
 * @returns {{el:HTMLElement, close:(result?:any)=>void, result:Promise<any>}}
 */
export function dialog(opts = {}) {
  const {
    title = '', message = '', content = null, actions = [{ text: '好的', variant: 'filled', value: true }],
    dismissible = true, stackActions = false,
  } = opts;

  const prevActive = document.activeElement;
  let resolveFn;
  const result = new Promise((res) => { resolveFn = res; });
  let closed = false;
  let stackRemoved = false;

  const scrim = h('div', { class: 'mi-scrim' });
  const bodyChildren = [];
  if (title) bodyChildren.push(h('div', { class: 'mi-dialog__title' }, title));
  if (message) bodyChildren.push(h('div', { class: 'mi-dialog__message' }, message));
  if (content) bodyChildren.push(h('div', { class: 'mi-dialog__content' }, content));
  const dialogEl = h('div', { class: 'mi-dialog', role: 'dialog', 'aria-modal': 'true', 'aria-label': title || '对话框' },
    h('div', { class: 'mi-dialog__body' }, ...bodyChildren)
  );

  const actionsEl = h('div', { class: ['mi-dialog__actions', stackActions && 'mi-dialog__actions--stack'] });
  actions.forEach((act) => {
    actionsEl.appendChild(button({
      text: act.text,
      variant: act.variant || 'text',
      onClick: async () => {
        if (act.onClick) {
          const ret = await act.onClick();
          if (ret === false) return; // 允许外部阻止关闭
        }
        close(act.value !== undefined ? act.value : act.text);
      },
    }));
  });
  dialogEl.appendChild(actionsEl);

  const wrap = h('div', { class: 'mi-dialog-wrap' }, dialogEl);
  const root = overlayRoot();
  root.appendChild(scrim);
  root.appendChild(wrap);

  const overlayItem = {
    el: dialogEl,
    close: () => close(undefined),
    onEscape: () => { if (dismissible) close(undefined); },
  };
  overlayStack.push(overlayItem);

  function close(value) {
    if (closed) return;
    closed = true;
    if (!stackRemoved) {
      stackRemoved = true;
      const idx = overlayStack.lastIndexOf(overlayItem);
      if (idx !== -1) overlayStack.splice(idx, 1);
    }
    restoreFocus(prevActive);
    scrim.classList.remove('mi-scrim--show');
    dialogEl.classList.remove('mi-dialog--show');
    setTimeout(() => {
      scrim.remove();
      wrap.remove();
    }, 280);
    resolveFn(value);
  }

  scrim.addEventListener('click', () => { if (dismissible) close(undefined); });

  requestAnimationFrame(() => {
    scrim.classList.add('mi-scrim--show');
    dialogEl.classList.add('mi-dialog--show');
  });

  setTimeout(() => {
    focusOverlay(dialogEl);
  }, 120);

  return { el: dialogEl, close, result };
}

/**
 * 确认对话框
 * @returns {Promise<boolean>}
 */
export async function confirm({ title = '确认操作', message = '', confirmText = '确定', cancelText = '取消', danger = false } = {}) {
  const d = dialog({
    title,
    message,
    actions: [
      { text: cancelText, variant: 'text', value: false },
      { text: confirmText, variant: danger ? 'danger' : 'filled', value: true },
    ],
  });
  const res = await d.result;
  return res === true;
}

/**
 * 底部动作面板
 * @param {{title?:string, items:Array<{text:string, icon?:string, tone?:'danger', value:any, onClick?:Function}>,
 *          cancelText?:string}} opts
 * @returns {Promise<any>} 选中项的 value，取消为 null
 */
export async function actionSheet({ title = '', items = [], cancelText = '取消' } = {}) {
  return new Promise((resolve) => {
    const prevActive = document.activeElement;
    let done = false;
    let stackRemoved = false;
    const scrim = h('div', { class: 'mi-scrim' });
    const list = h('div', { class: 'mi-actionsheet' });
    items.forEach((it) => {
      list.appendChild(h('button', {
        class: ['mi-actionsheet__item', it.tone === 'danger' && 'mi-actionsheet__item--danger'],
        type: 'button',
        onClick: () => {
          finish(it.value);
          if (it.onClick) it.onClick();
        },
      }, it.icon ? icon(it.icon, 20) : null, it.text));
    });
    list.appendChild(h('div', { class: 'mi-actionsheet__sep' }));
    list.appendChild(h('button', {
      class: 'mi-actionsheet__item', type: 'button', style: { justifyContent: 'center', color: 'var(--mi-text-secondary)' },
      onClick: () => finish(null),
    }, cancelText));

    const sheetEl = h('div', { class: 'mi-sheet mi-sheet--wide' },
      h('div', { class: 'mi-sheet__grabber' }),
      title ? h('div', { class: 'mi-sheet__header' }, h('div', { class: 'mi-sheet__title' }, title)) : null,
      h('div', { class: 'mi-sheet__body' }, list)
    );
    const root = overlayRoot();
    root.appendChild(scrim);
    root.appendChild(sheetEl);

    const overlayItem = {
      el: sheetEl,
      close: () => finish(null),
      onEscape: () => finish(null),
    };
    overlayStack.push(overlayItem);

    function finish(value) {
      if (done) return;
      done = true;
      if (!stackRemoved) {
        stackRemoved = true;
        const idx = overlayStack.lastIndexOf(overlayItem);
        if (idx !== -1) overlayStack.splice(idx, 1);
      }
      restoreFocus(prevActive);
      scrim.classList.remove('mi-scrim--show');
      sheetEl.classList.remove('mi-sheet--show');
      setTimeout(() => { scrim.remove(); sheetEl.remove(); }, 320);
      resolve(value);
    }
    scrim.addEventListener('click', () => finish(null));
    requestAnimationFrame(() => {
      scrim.classList.add('mi-scrim--show');
      sheetEl.classList.add('mi-sheet--show');
    });
    setTimeout(() => {
      focusOverlay(sheetEl);
    }, 120);
  });
}

/**
 * 通用底部面板（可放任意内容，支持下拉关闭）
 * @param {{title?:string, content:Node|Node[], wide?:boolean, onClose?:Function}} opts
 * @returns {{el:HTMLElement, body:HTMLElement, close:()=>void}}
 */
export function openSheet({ title = '', content = null, wide = true, onClose = null } = {}) {
  const prevActive = document.activeElement;
  let closed = false;
  let stackRemoved = false;
  const scrim = h('div', { class: 'mi-scrim' });
  const body = h('div', { class: 'mi-sheet__body' },
    content ? (content instanceof Node ? content : append(h('div'), content)) : null
  );
  const grabber = h('div', { class: 'mi-sheet__grabber' });
  const sheetEl = h('div', { class: ['mi-sheet', wide && 'mi-sheet--wide'] },
    grabber,
    title ? h('div', { class: 'mi-sheet__header' },
      h('div', { class: 'mi-sheet__title' }, title),
      iconButton({ icon: 'close', label: '关闭', onClick: () => close() })
    ) : null,
    body
  );
  const root = overlayRoot();
  root.appendChild(scrim);
  root.appendChild(sheetEl);

  const overlayItem = {
    el: sheetEl,
    close: () => close(),
    onEscape: () => close(),
  };
  overlayStack.push(overlayItem);

  function close() {
    if (closed) return;
    closed = true;
    if (!stackRemoved) {
      stackRemoved = true;
      const idx = overlayStack.lastIndexOf(overlayItem);
      if (idx !== -1) overlayStack.splice(idx, 1);
    }
    restoreFocus(prevActive);
    scrim.classList.remove('mi-scrim--show');
    sheetEl.classList.remove('mi-sheet--show');
    setTimeout(() => { scrim.remove(); sheetEl.remove(); }, 320);
    if (onClose) onClose();
  }
  scrim.addEventListener('click', close);

  /* 拖拽关闭：仅当面板内容滚动到顶部时生效 */
  let startY = 0;
  let dragging = false;
  let delta = 0;
  grabber.addEventListener('pointerdown', (e) => {
    startY = e.clientY;
    dragging = true;
    delta = 0;
    sheetEl.classList.add('mi-sheet--dragging');
    grabber.setPointerCapture(e.pointerId);
  });
  grabber.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    delta = Math.max(0, e.clientY - startY);
    sheetEl.style.transform = `translateY(${delta}px)`;
  });
  const endDrag = () => {
    if (!dragging) return;
    dragging = false;
    sheetEl.classList.remove('mi-sheet--dragging');
    sheetEl.style.transform = '';
    if (delta > 96) close();
  };
  grabber.addEventListener('pointerup', endDrag);
  grabber.addEventListener('pointercancel', endDrag);

  requestAnimationFrame(() => {
    scrim.classList.add('mi-scrim--show');
    sheetEl.classList.add('mi-sheet--show');
  });
  setTimeout(() => {
    focusOverlay(sheetEl);
  }, 120);
  return { el: sheetEl, body, close };
}

/* ─────────────────────────────────────────────────────────────────────
   工具函数
   ───────────────────────────────────────────────────────────────────── */

/** 防抖 */
export function debounce(fn, wait = 250) {
  let timer = null;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
  wrapped.cancel = () => clearTimeout(timer);
  return wrapped;
}

/** 秒数 → 友好运行时长 */
export function formatUptime(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const d = Math.floor(s / 86400);
  const hh = Math.floor((s % 86400) / 3600);
  const mm = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d} 天 ${hh} 小时`;
  if (hh > 0) return `${hh} 小时 ${mm} 分`;
  if (mm > 0) return `${mm} 分 ${s % 60} 秒`;
  return `${s} 秒`;
}

/** 数字千分位 */
export function formatNumber(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return String(n ?? '—');
  return v.toLocaleString('zh-CN');
}

/** 本地时间 HH:mm:ss */
export function formatClock(date = new Date()) {
  const d = date instanceof Date ? date : new Date(date);
  return d.toLocaleTimeString('zh-CN', { hour12: false });
}

/** 复制到剪贴板 */
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* 走降级 */ }
  try {
    const ta = h('textarea', { style: { position: 'fixed', top: '-1000px', opacity: '0' } });
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}

/** 触觉反馈（支持的设备；无用户手势时跳过，避免控制台报错） */
export function vibrate(ms = 10) {
  try {
    if (!navigator.vibrate) return;
    if (navigator.userActivation && !navigator.userActivation.isActive) return;
    navigator.vibrate(ms);
  } catch { /* 忽略 */ }
}

export function sleep(ms) {
  return new Promise((res) => setTimeout(res, ms));
}

/** 元素进入/离开视口观察（大标题折叠等） */
export function onIntersect(el, callback, options = { threshold: 0.1 }) {
  if (!el || typeof IntersectionObserver === 'undefined') return () => {};
  const io = new IntersectionObserver((entries) => callback(entries[0], entries), options);
  io.observe(el);
  return () => io.disconnect();
}
