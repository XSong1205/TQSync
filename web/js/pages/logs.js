/**
 * 运行日志页（logs）—— 二级页，归属概览
 * =====================================================================
 * 功能：
 *   - 读取 logs/tqsync.log 末尾 N 行（GET /admin/logs?lines=N）
 *   - 行数分段（100/200/500/1000）、自动刷新（5s，仅页面可见时）、
 *     复制全部、手动刷新
 *   - 关键词搜索（防抖、不区分大小写）+ 级别筛选（全部 / WARN+ / 仅 ERROR）
 *   - 按级别着色（`.mi-logs__line--error/warning/info/debug`，SUCCESS 用成功色）
 *   - 粘底滚动：首次加载与自动刷新时自动滚到底部，用户上滚后不再打扰，
 *     并显示「回到底部」悬浮按钮
 *
 * 数据来源：GET /admin/logs?lines=N → { logs: string[] }（服务端上限 5000）
 *
 * 实现要点：一次性建好工具栏 / 筛选 / 日志块外壳（同步输出，不白屏），
 * 之后只在数据变化时用 DocumentFragment 重建日志行（≤1000 行）。
 */
import * as ui from '../ui.js';
import { api } from '../api.js';

const { h } = ui;

const LOG_FILE = 'logs/tqsync.log';
const PAGE_SIZES = [100, 200, 500, 1000];
const DEFAULT_LINES = 200;
const AUTO_REFRESH_MS = 5000;
const BOTTOM_EPS = 24; // 距底部多少 px 内视为「粘底」

const LEVEL_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'warn', label: 'WARN+' },
  { value: 'error', label: '仅 ERROR' },
];

const LEGEND = [
  { label: 'ERROR', color: '#ff8b80' },
  { label: 'WARN', color: '#ffcc80' },
  { label: 'INFO', color: '#9ad4ff' },
  { label: 'DEBUG', color: '#8b949e' },
];

/* 级别 → 严重度，用于 "WARN+" 筛选 */
const SEVERITY = { error: 3, warning: 2, success: 1, info: 1, debug: 0, plain: 0 };

/* ─────────────────────────────────────────────────────────────────────
   工具
   ───────────────────────────────────────────────────────────────────── */

/** 统一取错误文案 */
function errorText(err, fallback = '加载失败') {
  if (!err) return fallback;
  if (typeof err === 'string') return err;
  return err.detail || err.message || fallback;
}

/** 单行日志 → 级别 */
function classifyLine(raw) {
  const text = String(raw == null ? '' : raw);
  if (/\b(?:ERROR|CRITICAL|FATAL)\b/i.test(text) || /失败|错误|异常/.test(text)) return 'error';
  if (/\b(?:WARNING|WARN)\b/i.test(text) || /警告|告警/.test(text)) return 'warning';
  if (/\bSUCCESS\b/i.test(text) || /成功/.test(text)) return 'success';
  if (/\b(?:DEBUG|TRACE)\b/i.test(text)) return 'debug';
  if (/\bINFO\b/i.test(text)) return 'info';
  return 'plain';
}

/** 分段控件提升到 44px 触控高度（Miuix 默认 34px 视觉高度） */
function enlargeSegment(seg, height = 44) {
  seg.style.height = `${height + 6}px`;
  seg.style.boxSizing = 'border-box';
  seg.querySelectorAll('.mi-segmented__item').forEach((item) => {
    item.style.height = `${height}px`;
  });
  return seg;
}

/** 搜索框提升到 46px 触控高度 */
function enlargeSearch(search) {
  search.el.style.height = '46px';
  return search;
}

/** 图标按钮提升到 44px 触控尺寸 */
function enlargeIconButton(btn) {
  btn.style.width = '44px';
  btn.style.height = '44px';
  return btn;
}

/** 带页面左右边距的容器 */
function inset(node, extra = {}) {
  return h('div', { style: Object.assign({ margin: '0 var(--mi-page-x) 14px' }, extra) }, node);
}

/* ─────────────────────────────────────────────────────────────────────
   页面模块
   ───────────────────────────────────────────────────────────────────── */

export default {
  id: 'logs',
  label: '日志',
  icon: 'logs',
  tab: false,
  parent: 'dashboard',
  title: '运行日志',
  subtitle: '',

  async mount(root, ctx) {
    /* ── 可变状态 ─────────────────────────────────────────────────── */
    let disposed = false;
    let lines = []; // string[]
    let levels = []; // 与 lines 同下标：error/warning/success/debug/info/plain
    let keyword = '';
    let levelFilter = 'all';
    let lineCount = DEFAULT_LINES;
    let auto = false;
    let updatedAt = null;
    let loadedOnce = false;
    let loading = false;
    let stick = true;
    let timer = null;
    let requestSeq = 0;
    let lastError = '';

    /* ── 派生数据 ─────────────────────────────────────────────────── */
    function visibleIndices() {
      const kw = keyword.toLowerCase();
      const result = [];
      for (let i = 0; i < lines.length; i += 1) {
        if (levelFilter === 'warn' && (SEVERITY[levels[i]] || 0) < 2) continue;
        if (levelFilter === 'error' && levels[i] !== 'error') continue;
        if (kw && lines[i].toLowerCase().indexOf(kw) === -1) continue;
        result.push(i);
      }
      return result;
    }

    /* ── 工具栏（同步构建，先出外壳） ────────────────────────────── */
    const countBadge = ui.badge(`${DEFAULT_LINES} 行`, 'accent');
    const captionEl = h('div', {
      class: 'mi-text-xs mi-text-tertiary',
      style: { marginTop: '12px', lineHeight: '1.5', minHeight: '18px' },
    }, '正在读取日志…');

    const countSeg = enlargeSegment(ui.segmented({
      options: PAGE_SIZES.map((n) => ({ value: String(n), label: String(n) })),
      value: String(lineCount),
      onChange: (value) => {
        const next = Number(value);
        if (!Number.isFinite(next) || next === lineCount) return;
        lineCount = next;
        countBadge.textContent = `${next} 行`;
        load({ quiet: false }).catch(() => {});
      },
    }));

    const refreshBtn = enlargeIconButton(ui.iconButton({
      icon: 'refresh',
      label: '刷新日志',
      onClick: () => {
        if (loading) return;
        load({ quiet: false }).catch(() => {});
      },
    }));

    const copyBtn = enlargeIconButton(ui.iconButton({
      icon: 'copy',
      label: '复制全部日志',
      onClick: async () => {
        const indices = visibleIndices();
        if (!indices.length) {
          ctx.toast('没有可复制的日志', { type: 'warning', duration: 1600 });
          return;
        }
        try {
          const ok = await ctx.copyText(indices.map((i) => lines[i]).join('\n'));
          if (ok) ctx.toast(`已复制 ${indices.length} 行日志`, { type: 'success', duration: 1600 });
          else ctx.toastErr(new Error('复制失败，请长按选择文本'), '复制失败');
        } catch (err) {
          ctx.toastErr(err, '复制失败');
        }
      },
    }));

    const autoSwitch = ui.switchControl({ checked: false, onChange: (on) => setAutoRefresh(on) });
    const autoRow = h('div', {
      class: 'mi-hstack',
      style: { minHeight: '44px', cursor: 'pointer' },
      onClick: (e) => {
        if (!autoSwitch.contains(e.target)) autoSwitch.click();
      },
    },
      autoSwitch,
      h('span', { class: 'mi-row__title', style: { fontWeight: '500' } }, '自动刷新'),
      ui.badge('5 秒', 'neutral')
    );

    const toolbar = inset(ui.card({
      children: [
        h('div', { class: 'mi-between', style: { marginBottom: '12px', gap: '10px' } },
          h('div', { class: 'mi-grow', style: { minWidth: '0' } },
            h('div', { class: 'mi-row__title', style: { fontWeight: '600' } }, '显示行数'),
            h('div', { class: 'mi-row__subtitle' }, '读取日志文件末尾的 N 行')
          ),
          countBadge
        ),
        countSeg,
        h('div', { class: 'mi-between', style: { marginTop: '6px', gap: '8px' } },
          autoRow,
          h('div', { class: 'mi-hstack', style: { gap: '2px' } }, copyBtn, refreshBtn)
        ),
        captionEl,
      ],
    }));

    /* ── 筛选卡 ───────────────────────────────────────────────────── */
    const keywordDebounced = ui.debounce((value) => {
      keyword = String(value || '').trim();
      render({ scrollMode: 'top' });
      updateCaption();
    }, 220);

    const search = enlargeSearch(ui.searchBar({
      placeholder: '搜索日志内容（不区分大小写）',
      onInput: (value) => keywordDebounced(value),
    }));

    const levelSeg = enlargeSegment(ui.segmented({
      options: LEVEL_OPTIONS,
      value: 'all',
      onChange: (value) => {
        levelFilter = value;
        render({ scrollMode: 'top' });
        updateCaption();
      },
    }));

    const filterHint = h('div', {
      class: 'mi-text-xs mi-text-tertiary',
      style: { marginTop: '10px', minHeight: '17px' },
    }, '');

    const filterCard = inset(ui.card({ children: [search.el, h('div', { style: { marginTop: '12px' } }, levelSeg), filterHint] }));

    /* ── 日志查看器 ───────────────────────────────────────────────── */
    const headEl = h('div', { class: 'mi-logs__head' },
      h('span', { class: 'mi-hstack', style: { gap: '6px', minWidth: '0' } },
        ui.icon('logs', 14),
        h('span', {
          class: 'mi-mono',
          style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
        }, LOG_FILE)
      ),
      h('span', { class: 'mi-grow' }),
      h('span', { class: 'mi-hstack', style: { gap: '9px', justifyContent: 'flex-end', flex: 'none' } },
        LEGEND.map((item) => h('span', { class: 'mi-hstack', style: { gap: '4px', flex: 'none' } },
          h('span', {
            style: {
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: item.color,
              flex: 'none',
            },
          }),
          h('span', null, item.label)
        ))
      )
    );

    const bodyEl = h('div', {
      class: 'mi-logs__body',
      role: 'log',
      'aria-label': '日志内容',
      tabindex: '0',
    });
    bodyEl.appendChild(ui.loadingBlock('正在读取日志…'));

    const logsCard = h('div', { class: 'mi-logs' }, headEl, bodyEl);

    const backToBottomBtn = ui.button({
      text: '回到底部',
      icon: 'chevron-down',
      variant: 'tonal',
      size: 'sm',
      className: 'logs-back-bottom',
      onClick: () => scrollToBottom('smooth'),
    });
    backToBottomBtn.style.position = 'absolute';
    backToBottomBtn.style.right = '24px';
    backToBottomBtn.style.bottom = '24px';
    backToBottomBtn.style.zIndex = '4';
    backToBottomBtn.style.height = '44px';
    backToBottomBtn.style.boxShadow = 'var(--mi-shadow-2)';
    backToBottomBtn.hidden = true;

    const viewerHost = h('div', { style: { position: 'relative' } }, logsCard, backToBottomBtn);

    /* 空 / 错误态挂载点（日志块隐藏时显示在主题背景上，避免暗底配色冲突） */
    const stateHost = h('div', { hidden: true });

    root.appendChild(toolbar);
    root.appendChild(filterCard);
    root.appendChild(viewerHost);
    root.appendChild(stateHost);

    /* ── 渲染 ─────────────────────────────────────────────────────── */
    function lineNode(text, level) {
      const cls = ['mi-logs__line'];
      let style = null;
      if (level === 'error') cls.push('mi-logs__line--error');
      else if (level === 'warning') cls.push('mi-logs__line--warning');
      else if (level === 'debug') cls.push('mi-logs__line--debug');
      else if (level === 'success') style = { color: 'var(--mi-success)' };
      else cls.push('mi-logs__line--info');
      return h('div', { class: cls, style }, text);
    }

    function syncStick() {
      if (!bodyEl.clientHeight) return;
      const atBottom = bodyEl.scrollHeight - bodyEl.scrollTop - bodyEl.clientHeight <= BOTTOM_EPS;
      stick = atBottom;
      backToBottomBtn.hidden = atBottom;
    }

    function scrollToBottom(behavior = 'auto') {
      stick = true;
      backToBottomBtn.hidden = true;
      try {
        bodyEl.scrollTo({ top: bodyEl.scrollHeight, behavior });
      } catch {
        bodyEl.scrollTop = bodyEl.scrollHeight;
      }
    }

    function updateCaption() {
      const filtering = Boolean(keyword) || levelFilter !== 'all';
      const parts = [`共 ${lines.length} 行`];
      if (filtering) parts.push(`筛选 ${visibleIndices().length} 行`);
      parts.push(updatedAt ? `更新于 ${ui.formatClock(updatedAt)}` : '等待更新');
      if (lastError && loadedOnce) parts.push('刷新失败');
      captionEl.textContent = parts.join(' · ');
    }

    function updateFilterHint(visible) {
      const filtering = Boolean(keyword) || levelFilter !== 'all';
      if (filtering) filterHint.textContent = `匹配 ${visible} / ${lines.length} 行`;
      else filterHint.textContent = '';
    }

    function clearFilters() {
      keyword = '';
      levelFilter = 'all';
      search.set('');
      levelSeg.set('all');
      render({ scrollMode: 'top' });
      updateCaption();
    }

    function render({ scrollMode = 'keep' } = {}) {
      const indices = visibleIndices();
      updateFilterHint(indices.length);

      if (!indices.length) {
        viewerHost.hidden = true;
        backToBottomBtn.hidden = true;
        stateHost.hidden = false;
        if (!lines.length) {
          stateHost.replaceChildren(ui.emptyState({
            icon: 'logs',
            title: '暂无日志',
            desc: '日志文件 logs/tqsync.log 暂时没有内容。',
          }));
        } else {
          stateHost.replaceChildren(ui.emptyState({
            icon: 'search',
            title: '没有匹配的日志',
            desc: '试试更换关键词，或把级别筛选切回「全部」。',
            actionText: '清除筛选',
            onAction: () => clearFilters(),
          }));
        }
        return;
      }

      viewerHost.hidden = false;
      stateHost.hidden = true;
      stateHost.replaceChildren();

      const prevTop = bodyEl.scrollTop;
      const frag = document.createDocumentFragment();
      for (const idx of indices) frag.appendChild(lineNode(lines[idx], levels[idx]));
      bodyEl.replaceChildren(frag);

      requestAnimationFrame(() => {
        if (disposed) return;
        if (scrollMode === 'bottom') scrollToBottom('auto');
        else if (scrollMode === 'top') bodyEl.scrollTop = 0;
        else bodyEl.scrollTop = prevTop;
        syncStick();
      });
    }

    function showError(err) {
      viewerHost.hidden = true;
      backToBottomBtn.hidden = true;
      stateHost.hidden = false;
      stateHost.replaceChildren(ui.errorBlock({
        title: '日志读取失败',
        message: errorText(err, '请检查后端服务是否正常运行'),
        onRetry: () => load({ quiet: false }),
      }));
    }

    /* ── 数据加载 ─────────────────────────────────────────────────── */
    async function load({ quiet = false } = {}) {
      const seq = (requestSeq += 1);
      loading = true;
      refreshBtn.setAttribute('aria-busy', 'true');
      if (!loadedOnce) captionEl.textContent = '正在读取日志…';
      else if (!quiet) captionEl.textContent = '正在刷新日志…';

      try {
        const data = await api.get('/admin/logs', { lines: lineCount });
        if (disposed || ctx.isStale() || seq !== requestSeq) return;

        const next = data && Array.isArray(data.logs) ? data.logs.map((line) => String(line == null ? '' : line)) : [];
        const nextLevels = next.map(classifyLine);
        // 自动刷新且内容完全未变时跳过逐行重建（日志尾部未追加新行）
        const unchanged = quiet && loadedOnce && next.length === lines.length
          && (next.length === 0 || (next[0] === lines[0] && next[next.length - 1] === lines[lines.length - 1]));

        lines = next;
        levels = nextLevels;
        updatedAt = new Date();
        lastError = '';
        loadedOnce = true;

        if (unchanged) {
          updateCaption();
          updateFilterHint(visibleIndices().length);
        } else {
          render({ scrollMode: stick ? 'bottom' : 'keep' });
          updateCaption();
        }
      } catch (err) {
        if (disposed || ctx.isStale() || seq !== requestSeq) return;
        lastError = errorText(err, '日志读取失败');
        if (!loadedOnce) showError(err);
        else if (!quiet) ctx.toastErr(err, '日志刷新失败');
        updateCaption();
      } finally {
        if (seq === requestSeq) {
          loading = false;
          refreshBtn.removeAttribute('aria-busy');
        }
      }
    }

    /* ── 自动刷新（仅页面可见时） ─────────────────────────────────── */
    function setAutoRefresh(on) {
      auto = Boolean(on);
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      if (!auto) return;
      timer = setInterval(() => {
        if (document.hidden || disposed) return;
        load({ quiet: true }).catch(() => {});
      }, AUTO_REFRESH_MS);
    }

    function onVisibilityChange() {
      if (disposed || document.hidden || !auto) return;
      load({ quiet: true }).catch(() => {});
    }

    bodyEl.addEventListener('scroll', () => {
      const atBottom = bodyEl.scrollHeight - bodyEl.scrollTop - bodyEl.clientHeight <= BOTTOM_EPS;
      stick = atBottom;
      backToBottomBtn.hidden = atBottom;
    }, { passive: true });

    document.addEventListener('visibilitychange', onVisibilityChange);

    ctx.onRefresh(() => load({ quiet: false }));

    ctx.onCleanup(() => {
      disposed = true;
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      document.removeEventListener('visibilitychange', onVisibilityChange);
      keywordDebounced.cancel();
    });

    await load({ quiet: false });
  },
};
