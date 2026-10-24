/**
 * 概览页（dashboard）
 * =====================================================================
 * 展示：服务运行状态、运行指标、24 小时消息量、同步方向、插件概况、
 *       快捷操作与最近日志。
 *
 * 数据来源：
 *   GET  /admin/status            系统状态（CPU / 内存 / 磁盘 / 插件 / 群组）
 *   GET  /admin/stats/sync_history 最近 24 小时消息量（UTC 整点桶）
 *   GET  /admin/sync/direction    当前同步方向
 *   PUT  /admin/sync/direction    修改同步方向
 *   GET  /admin/logs?lines=6      最近日志
 *   POST /admin/restart           优雅重启
 *   GET  /health                  重启后存活探测（无需鉴权）
 *
 * 设计要点：
 *   - mount 先同步输出骨架屏，避免白屏；数据到达后一次性建 DOM
 *   - 每 15s 静默刷新（仅页面可见时），就地更新数值，不整页重绘
 *   - 所有异步区域都有 加载 / 空 / 错误 三态
 */
import * as ui from '../ui.js';
import { api } from '../api.js';

const { h } = ui;

const AUTO_REFRESH_MS = 15000;
const RESTART_POLL_MS = 1500;
const RESTART_TIMEOUT_MS = 60000;
const LOG_LINES = 6;

/* 同步方向：值 → 短标签 / 说明 */
const DIRECTION_OPTIONS = [
  { value: 'both', label: '双向' },
  { value: 'tg_to_qq', label: '仅 TG→QQ' },
  { value: 'qq_to_tg', label: '仅 QQ→TG' },
];
const DIRECTION_DESC = {
  both: 'Telegram ↔ QQ 双向同步，两端消息互通',
  tg_to_qq: '仅将 Telegram 消息同步到 QQ，QQ 侧消息不再转发',
  qq_to_tg: '仅将 QQ 消息同步到 Telegram，TG 侧消息不再转发',
};

/* ─────────────────────────────────────────────────────────────────────
   小工具
   ───────────────────────────────────────────────────────────────────── */

/** 统一取错误文案 */
function errorText(err, fallback = '加载失败') {
  if (!err) return fallback;
  if (typeof err === 'string') return err;
  return err.detail || err.message || fallback;
}

/** 带页面左右边距的内容容器 */
function inset(node, extra = {}) {
  return h('div', { style: Object.assign({ padding: '0 var(--mi-page-x) 14px' }, extra) }, node);
}

/** 从 "12.3%" 之类的字符串里解析数值 */
function parsePercent(value) {
  const n = parseFloat(String(value == null ? '' : value).replace(/[^\d.-]/g, ''));
  return Number.isFinite(n) ? n : NaN;
}

/** 百分比阈值 → 颜色语气 */
function percentTone(value, warningAt, dangerAt) {
  const n = parsePercent(value);
  if (!Number.isFinite(n)) return '';
  if (n > dangerAt) return 'danger';
  if (n > warningAt) return 'warning';
  return 'success';
}

/** 群组 ID 展示 */
function isConfigured(value) {
  return value !== null && value !== undefined && String(value).trim() !== '';
}

/** 后端 hour 为 UTC 小时号，转成本地 "HH:00" */
function localHourLabel(hour) {
  const hh = Number(hour);
  if (!Number.isFinite(hh)) return '--:00';
  const offsetHours = Math.round(-new Date().getTimezoneOffset() / 60);
  const local = ((hh + offsetHours) % 24 + 24) % 24;
  return `${String(local).padStart(2, '0')}:00`;
}

/** 日志级别 → .mi-logs__line--* 后缀 */
function logTone(line) {
  const text = String(line || '');
  if (/\b(CRITICAL|FATAL|ERROR)\b/i.test(text)) return 'error';
  if (/\b(WARN|WARNING)\b/i.test(text)) return 'warning';
  if (/\bDEBUG\b/i.test(text)) return 'debug';
  if (/\bINFO\b/i.test(text)) return 'info';
  return '';
}

/* ─────────────────────────────────────────────────────────────────────
   骨架屏
   ───────────────────────────────────────────────────────────────────── */

function buildSkeleton() {
  const bar = (width, height = 10) => h('div', { class: 'mi-skeleton', style: { width, height } });
  const metric = () =>
    h('div', { class: 'mi-metric' },
      bar('54%', 9),
      h('div', { class: 'mi-skeleton', style: { width: '72%', height: '19px', marginTop: '2px' } }),
      bar('40%', 8)
    );
  return h('div', { class: 'mi-fade-in' },
    inset(
      h('div', { class: 'mi-skeleton mi-skeleton--card', style: { height: '196px' } }),
      { paddingTop: '2px' }
    ),
    h('div', { class: 'mi-metrics' },
      metric(), metric(), metric(), metric(), metric(), metric()
    ),
    inset(h('div', { class: 'mi-skeleton mi-skeleton--card', style: { height: '168px' } })),
    inset(h('div', { class: 'mi-skeleton mi-skeleton--card', style: { height: '150px' } })),
    ui.skeleton({ type: 'list', count: 3 })
  );
}

/* ─────────────────────────────────────────────────────────────────────
   状态 Hero 卡
   ───────────────────────────────────────────────────────────────────── */

function buildConnRow(iconName, title) {
  const valueEl = h('div', {
    style: {
      fontFamily: 'var(--mi-font-mono)',
      fontSize: '13.5px',
      fontWeight: '600',
      lineHeight: '1.3',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
    },
  }, '—');
  const badgeEl = h('span', {
    style: {
      flex: 'none',
      padding: '2px 8px',
      borderRadius: '999px',
      background: 'rgba(255,255,255,0.2)',
      color: '#fff',
      fontSize: '10.5px',
      fontWeight: '600',
      letterSpacing: '0.01em',
    },
  }, '—');

  const el = h('div', {
    class: 'mi-hstack',
    style: { gap: '11px', padding: '7px 0', minHeight: '44px' },
  },
    h('span', {
      class: 'mi-row__icon',
      style: { background: 'rgba(255,255,255,0.16)', color: '#fff' },
    }, ui.icon(iconName, 19)),
    h('div', { class: 'mi-grow', style: { minWidth: '0' } },
      h('div', { style: { fontSize: '11.5px', color: 'rgba(255,255,255,0.72)', marginBottom: '1px' } }, title),
      valueEl
    ),
    badgeEl
  );

  return {
    el,
    update(rawValue) {
      const configured = isConfigured(rawValue);
      valueEl.textContent = configured ? String(rawValue) : '未配置';
      badgeEl.textContent = configured ? '已配置' : '待配置';
      badgeEl.style.background = configured ? 'rgba(255,255,255,0.2)' : 'rgba(255,214,120,0.28)';
      badgeEl.style.color = configured ? '#fff' : '#ffe7ab';
    },
  };
}

function buildStatusHero() {
  const versionChip = h('span', {
    style: {
      flex: 'none',
      maxWidth: '52%',
      padding: '3px 10px',
      borderRadius: '999px',
      background: 'rgba(255,255,255,0.2)',
      fontSize: '11.5px',
      fontWeight: '600',
      letterSpacing: '0.01em',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
    },
  }, '—');

  const uptimeEl = h('span', { class: 'mi-num', style: { fontWeight: '600' } }, '—');
  const updatedEl = h('span', { class: 'mi-num', style: { fontWeight: '600' } }, '—');

  const tg = buildConnRow('telegram', 'Telegram 群组');
  const qq = buildConnRow('qq', 'QQ 群组');

  const el = ui.card({
    tone: 'accent',
    children: [
      h('div', { class: 'mi-between', style: { alignItems: 'flex-start', gap: '10px' } },
        h('div', {
          class: 'mi-hstack',
          style: { gap: '7px', fontSize: '12.5px', fontWeight: '500', color: 'rgba(255,255,255,0.84)' },
        }, ui.icon('shield', 15), h('span', null, '服务运行状态')),
        versionChip
      ),
      h('div', {
        style: { margin: '12px 0 3px', fontSize: '23px', fontWeight: '700', letterSpacing: '-0.02em', lineHeight: '1.2' },
      }, '运行正常'),
      h('div', {
        style: { fontSize: '12.5px', lineHeight: '1.5', color: 'rgba(255,255,255,0.76)' },
      }, 'Telegram ↔ QQ 消息同步服务已就绪'),
      h('div', { style: { marginTop: '10px' } }, tg.el, qq.el),
      h('div', {
        class: 'mi-between',
        style: {
          marginTop: '9px',
          paddingTop: '11px',
          borderTop: '1px solid rgba(255,255,255,0.18)',
          fontSize: '12px',
          color: 'rgba(255,255,255,0.85)',
          gap: '10px',
        },
      },
        h('div', { class: 'mi-hstack', style: { gap: '6px', minWidth: '0' } },
          ui.icon('clock', 14),
          h('span', { style: { whiteSpace: 'nowrap' } }, '已运行'),
          uptimeEl
        ),
        h('div', { class: 'mi-hstack', style: { gap: '5px', flex: 'none' } },
          h('span', null, '更新于'),
          updatedEl
        )
      ),
    ],
  });

  return {
    el,
    update(status) {
      const st = status || {};
      versionChip.textContent = st.version || '—';
      versionChip.title = st.version || '';
      uptimeEl.textContent = ui.formatUptime(st.uptime_seconds);
      updatedEl.textContent = ui.formatClock(new Date());
      tg.update(st.tg_group_id);
      qq.update(st.qq_group_id);
    },
  };
}

/* ─────────────────────────────────────────────────────────────────────
   运行指标
   ───────────────────────────────────────────────────────────────────── */

function buildMetrics(status) {
  const st = status || {};
  return ui.metricsGrid([
    {
      label: '绑定用户',
      value: ui.formatNumber(st.bound_users ?? 0),
      sub: 'TG ↔ QQ 用户对',
      icon: 'users',
    },
    {
      label: '同步消息',
      value: ui.formatNumber(st.sync_count ?? 0),
      sub: '累计消息映射',
      icon: 'activity',
    },
    {
      label: 'CPU',
      value: st.cpu_usage || '—',
      sub: '进程占用',
      icon: 'cpu',
      tone: percentTone(st.cpu_usage, 60, 80),
    },
    {
      label: '内存',
      value: st.memory_usage || '—',
      sub: 'RSS 常驻',
      icon: 'memory',
    },
    {
      label: '磁盘',
      value: st.disk_usage || '—',
      sub: '磁盘占用',
      icon: 'disk',
      tone: percentTone(st.disk_usage, 75, 90),
    },
    {
      label: '数据库',
      value: st.db_size || '—',
      sub: 'SQLite 体积',
      icon: 'database',
    },
  ]);
}

/* ─────────────────────────────────────────────────────────────────────
   24 小时消息量
   ───────────────────────────────────────────────────────────────────── */

function buildHistoryCard(history) {
  const buckets = history && Array.isArray(history.buckets) ? history.buckets : [];
  const data = buckets.map((b) => ({
    label: localHourLabel(b && b.hour),
    value: Math.max(0, Number(b && b.count) || 0),
  }));
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const peak = data.reduce((best, d) => (d.value > best.value ? d : best), { label: '—', value: 0 });

  return ui.card({
    padded: true,
    children: [
      h('div', { class: 'mi-between', style: { alignItems: 'flex-start', gap: '10px', marginBottom: '2px' } },
        h('div', { class: 'mi-grow', style: { minWidth: '0' } },
          h('div', { style: { fontSize: '16px', fontWeight: '600', letterSpacing: '-0.01em' } }, '24 小时消息量'),
          h('div', { class: 'mi-row__subtitle' },
            total > 0 ? '按整点统计的同步消息数' : '最近 24 小时暂无同步消息')
        ),
        ui.badge(`共 ${ui.formatNumber(total)} 条`, 'accent')
      ),
      ui.barChart({ data, height: 96 }),
      h('div', { class: 'mi-field__support', style: { marginTop: '2px' } },
        total > 0 ? `峰值 ${ui.formatNumber(peak.value)} 条 · ${peak.label}` : '新消息同步后将在此显示统计')
    ],
  });
}

/** 消息统计独立重试（初始加载失败时使用） */
function buildHistoryError(message, onRetry) {
  return ui.card({
    padded: true,
    children: [
      ui.errorBlock({
        title: '消息统计加载失败',
        message: message || '请稍后重试',
        onRetry,
      }),
    ],
  });
}

/* ─────────────────────────────────────────────────────────────────────
   同步方向
   ───────────────────────────────────────────────────────────────────── */

function buildDirectionBody(currentDirection, setDirection) {
  const descEl = h('div', { class: 'mi-row__subtitle', style: { marginTop: '9px', minHeight: '18px' } },
    DIRECTION_DESC[currentDirection] || '');
  const seg = ui.segmented({
    options: DIRECTION_OPTIONS,
    value: currentDirection,
    onChange: (value) => setDirection(value),
  });
  const body = h('div', null,
    seg,
    descEl,
    h('div', { class: 'mi-field__support', style: { marginTop: '5px' } }, '修改后立即生效，无需重启服务')
  );
  return { body, seg, descEl };
}

/* ─────────────────────────────────────────────────────────────────────
   插件概况 / 快捷操作 / 最近日志
   ───────────────────────────────────────────────────────────────────── */

function buildPluginGroup(status, onOpen) {
  const plugins = (status && status.plugins) || {};
  const total = Number(plugins.total) || 0;
  const enabled = Number(plugins.enabled) || 0;
  const loaded = Number(plugins.loaded) || 0;

  return ui.cardGroup({
    children: [
      ui.row({
        title: '插件概况',
        subtitle: `已加载 ${loaded} 个 · 点击管理插件`,
        icon: 'puzzle',
        value: `已启用 ${enabled}/${total}`,
        chevron: true,
        onClick: onOpen,
      }),
    ],
  });
}

function buildQuickActions(ctx, onRestart) {
  return ui.cardGroup({
    children: [
      ui.row({
        title: '查看日志',
        subtitle: '查看最近运行记录与错误信息',
        icon: 'logs',
        chevron: true,
        onClick: () => ctx.go('logs'),
      }),
      ui.row({
        title: '修改管理密钥',
        subtitle: '前往设置页更新控制台访问密钥',
        icon: 'shield',
        chevron: true,
        onClick: () => ctx.go('settings'),
      }),
      ui.row({
        title: '重启服务',
        subtitle: '重启后服务会短暂中断，随后自动恢复',
        icon: 'power',
        iconTone: 'warning',
        chevron: true,
        onClick: onRestart,
      }),
    ],
  });
}

function buildLogsBlock(ctx) {
  const head = h('div', {
    class: 'mi-logs__head',
    role: 'button',
    tabindex: '0',
    style: { cursor: 'pointer' },
    onClick: () => ctx.go('logs'),
    onKeydown: (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        ctx.go('logs');
      }
    },
  },
    ui.icon('logs', 14),
    h('span', { class: 'mi-grow' }, '最近日志'),
    h('span', { style: { opacity: '0.8' } }, '查看全部'),
    ui.icon('chevron-right', 14)
  );
  const body = h('div', { class: 'mi-logs__body' },
    h('span', { class: 'mi-logs__line mi-logs__line--debug' }, '加载日志…'));
  const el = h('div', { class: 'mi-logs', style: { marginBottom: '18px' } }, head, body);
  return { el, body };
}

/* ─────────────────────────────────────────────────────────────────────
   页面模块
   ───────────────────────────────────────────────────────────────────── */

export default {
  id: 'dashboard',
  label: '概览',
  icon: 'gauge',
  tab: true,
  title: '概览',
  subtitle: '',

  async mount(root, ctx) {
    let disposed = false;
    let status = null;
    let history = null;
    let mounted = false;
    let lastHistorySig = null;
    let timer = null;
    let restarting = false;
    let direction = 'both';
    let directionBusy = false;
    let directionSaving = false;
    let quietRefreshing = false;

    const refs = {
      hero: null,
      metricsSlot: null,
      chartSlot: null,
      directionSlot: null,
      directionSeg: null,
      directionDesc: null,
      pluginSlot: null,
      logsBody: null,
    };

    /* ── 清理 / 下拉刷新注册 ─────────────────────────────────────── */
    ctx.onCleanup(() => {
      disposed = true;
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    });
    ctx.onRefresh(loadAll);

    /* ── 主数据加载（状态 + 统计，失败时抛错由调用方展示） ──────── */
    async function loadAll() {
      const results = await Promise.allSettled([
        api.get('/admin/status'),
        api.get('/admin/stats/sync_history'),
      ]);
      if (disposed) return;
      const statusResult = results[0];
      const historyResult = results[1];
      if (statusResult.status === 'rejected') throw statusResult.reason;

      status = statusResult.value;
      if (!mounted) {
        history = historyResult.status === 'fulfilled' ? historyResult.value : null;
        buildContent();
      } else {
        applyStatus(status);
        if (historyResult.status === 'fulfilled') applyHistory(historyResult.value);
      }
      await Promise.allSettled([loadDirection(), loadLogs()]);
    }

    /* ── 静默刷新（定时器；不整页重绘、不弹 toast） ─────────────── */
    async function silentRefresh() {
      if (disposed || restarting || quietRefreshing) return;
      quietRefreshing = true;
      try {
        const results = await Promise.allSettled([
          api.get('/admin/status'),
          api.get('/admin/stats/sync_history'),
        ]);
        if (disposed) return;
        const statusResult = results[0];
        const historyResult = results[1];

        if (statusResult.status === 'fulfilled') {
          status = statusResult.value;
          if (!mounted) {
            history = historyResult.status === 'fulfilled' ? historyResult.value : null;
            buildContent();
            loadDirection();
            loadLogs();
          } else {
            applyStatus(status);
            if (historyResult.status === 'fulfilled') applyHistory(historyResult.value);
          }
        } else if (historyResult.status === 'fulfilled' && mounted) {
          applyHistory(historyResult.value);
        }
      } finally {
        quietRefreshing = false;
      }
    }

    /* ── 首次加载：骨架 → 内容 / 错误态 ─────────────────────────── */
    async function loadWithFeedback() {
      root.setAttribute('aria-busy', 'true');
      root.replaceChildren(buildSkeleton());
      try {
        await loadAll();
      } catch (err) {
        if (disposed) return;
        root.replaceChildren(ui.errorBlock({
          title: '概览加载失败',
          message: errorText(err, '无法获取系统状态，请检查后端服务'),
          onRetry: () => loadWithFeedback(),
        }));
      } finally {
        root.removeAttribute('aria-busy');
      }
    }

    /* ── 建 DOM（只建一次；此后刷新就地更新） ───────────────────── */
    function buildContent() {
      const hero = buildStatusHero();
      refs.hero = hero;

      const metricsSlot = h('div', null, buildMetrics(status));
      const chartSlot = h('div', null);
      const directionSlot = h('div', null, ui.loadingBlock('加载同步方向…'));
      const pluginSlot = h('div', null);
      const logs = buildLogsBlock(ctx);

      refs.metricsSlot = metricsSlot;
      refs.chartSlot = chartSlot;
      refs.directionSlot = directionSlot;
      refs.pluginSlot = pluginSlot;
      refs.logsBody = logs.body;

      if (history) {
        lastHistorySig = historySignature(history);
        chartSlot.appendChild(buildHistoryCard(history));
      } else {
        chartSlot.appendChild(buildHistoryError('消息统计暂时不可用', () => loadHistory()));
      }

      hero.update(status);
      pluginSlot.appendChild(buildPluginGroup(status, () => ctx.go('plugins')));

      const quickCard = buildQuickActions(ctx, restartService);

      root.replaceChildren(
        inset(hero.el, { paddingTop: '2px' }),
        ui.sectionTitle('运行指标', { iconName: 'activity' }),
        metricsSlot,
        inset(chartSlot),
        ui.sectionTitle('同步方向', { iconName: 'sync' }),
        inset(ui.card({ padded: true, children: [directionSlot] })),
        ui.sectionTitle('插件', { iconName: 'puzzle' }),
        pluginSlot,
        ui.sectionTitle('快捷操作', { iconName: 'sparkle' }),
        quickCard,
        ui.sectionTitle('最近日志', { iconName: 'logs' }),
        logs.el
      );
      mounted = true;
      root.removeAttribute('aria-busy');
    }

    /* ── 就地更新：状态 / 指标 / 插件 ───────────────────────────── */
    function applyStatus(nextStatus) {
      status = nextStatus;
      if (!mounted) return;
      if (refs.hero) refs.hero.update(status);
      if (refs.metricsSlot) refs.metricsSlot.replaceChildren(buildMetrics(status));
      if (refs.pluginSlot) refs.pluginSlot.replaceChildren(buildPluginGroup(status, () => ctx.go('plugins')));
    }

    /* ── 就地更新：24 小时统计（数据未变化时跳过重绘） ─────────── */
    function historySignature(nextHistory) {
      const buckets = nextHistory && Array.isArray(nextHistory.buckets) ? nextHistory.buckets : [];
      return buckets.map((b) => `${b && b.hour}:${Math.max(0, Number(b && b.count) || 0)}`).join('|');
    }

    function applyHistory(nextHistory) {
      history = nextHistory;
      if (!mounted || !refs.chartSlot) return;
      const sig = historySignature(nextHistory);
      if (sig === lastHistorySig) return;
      lastHistorySig = sig;
      refs.chartSlot.replaceChildren(buildHistoryCard(nextHistory));
    }

    async function loadHistory() {
      try {
        const data = await api.get('/admin/stats/sync_history');
        if (disposed) return;
        applyHistory(data);
      } catch (err) {
        if (disposed) return;
        ctx.toastErr(err, '加载消息统计失败');
      }
    }

    /* ── 同步方向 ───────────────────────────────────────────────── */
    function applyDirection(value) {
      if (!refs.directionSeg || !refs.directionDesc) return;
      refs.directionSeg.set(value);
      refs.directionDesc.textContent = DIRECTION_DESC[value] || '';
    }

    function renderDirectionBody() {
      if (!refs.directionSlot) return;
      const built = buildDirectionBody(direction, (value) => setDirection(value));
      refs.directionSeg = built.seg;
      refs.directionDesc = built.descEl;
      refs.directionSlot.replaceChildren(built.body);
    }

    async function loadDirection() {
      if (directionBusy) return;
      directionBusy = true;
      try {
        const data = await api.get('/admin/sync/direction');
        if (disposed) return;
        direction = data && data.direction ? data.direction : 'both';
        if (refs.directionSlot) renderDirectionBody();
      } catch (err) {
        if (disposed) return;
        if (refs.directionSlot) {
          refs.directionSlot.replaceChildren(ui.errorBlock({
            title: '同步方向加载失败',
            message: errorText(err),
            onRetry: () => loadDirection(),
          }));
        }
      } finally {
        directionBusy = false;
      }
    }

    async function setDirection(next) {
      if (!next || next === direction) return;
      if (directionSaving) {
        // 上一次修改仍在提交：把分段控件回滚到当前值
        applyDirection(direction);
        return;
      }
      const previous = direction;
      direction = next;
      directionSaving = true;
      refs.directionDesc && (refs.directionDesc.textContent = DIRECTION_DESC[next] || '');
      try {
        await api.put('/admin/sync/direction', { direction: next });
        if (disposed) return;
        ctx.toast('同步方向已更新', { type: 'success' });
      } catch (err) {
        if (disposed) return;
        direction = previous;
        applyDirection(previous);
        ctx.toastErr(err, '修改同步方向失败');
      } finally {
        directionSaving = false;
      }
    }

    /* ── 最近日志 ───────────────────────────────────────────────── */
    async function loadLogs() {
      if (!refs.logsBody) return;
      try {
        const data = await api.get('/admin/logs', { lines: LOG_LINES });
        if (disposed) return;
        const lines = data && Array.isArray(data.logs) ? data.logs : [];
        if (!lines.length) {
          refs.logsBody.replaceChildren(
            h('span', { class: 'mi-logs__line mi-logs__line--debug' }, '暂无日志'));
          return;
        }
        refs.logsBody.replaceChildren(...lines.map((line) => {
          const tone = logTone(line);
          return h('span', {
            class: ['mi-logs__line', tone && `mi-logs__line--${tone}`],
          }, String(line));
        }));
      } catch (err) {
        if (disposed) return;
        refs.logsBody.replaceChildren(
          h('div', { style: { padding: '2px 0 4px' } },
            h('span', { class: 'mi-logs__line mi-logs__line--error' },
              `日志加载失败：${errorText(err, '请稍后重试')}`),
            h('div', { style: { marginTop: '9px' } },
              ui.button({ text: '重试', variant: 'tonal', size: 'sm', onClick: () => loadLogs() }))
          )
        );
      }
    }

    /* ── 重启服务 ───────────────────────────────────────────────── */
    async function restartService() {
      if (restarting) return;
      const confirmed = await ctx.confirm({
        title: '重启服务',
        message: '重启期间服务会短暂中断，完成后页面将自动刷新。确认立即重启吗？',
        confirmText: '立即重启',
        cancelText: '取消',
        danger: true,
      });
      if (!confirmed || disposed) return;

      restarting = true;
      const dialog = ctx.dialog({
        title: '正在重启…',
        message: '服务正在重启，页面将在服务恢复后自动刷新。',
        content: h('div', { class: 'mi-loading-block', style: { padding: '14px 0 2px' } },
          h('div', { class: 'mi-spinner' }),
          h('span', null, '等待服务恢复…')),
        dismissible: false,
        actions: [],
      });

      try {
        await api.post('/admin/restart');
      } catch (err) {
        // 服务可能已经关闭连接；403/401 等鉴权错误则应中止
        if (err && err.status && err.status !== 0) {
          restarting = false;
          dialog.close();
          if (!disposed) ctx.toastErr(err, '重启请求失败');
          return;
        }
      }
      if (disposed) {
        restarting = false;
        dialog.close();
        return;
      }

      const startedAt = Date.now();
      let ready = false;
      while (!disposed && Date.now() - startedAt < RESTART_TIMEOUT_MS) {
        await ui.sleep(RESTART_POLL_MS);
        if (disposed) break;
        try {
          const res = await fetch('/health', { cache: 'no-store' });
          if (!res.ok) continue;
          const body = await res.json().catch(() => null);
          if (body && body.status && body.status !== 'ok') continue;
          // 等待旧进程彻底退出，避免刷新回旧页面
          if (Date.now() - startedAt >= 4000) {
            ready = true;
            break;
          }
        } catch {
          /* 服务重启中，继续轮询 */
        }
      }
      restarting = false;
      if (disposed) return;
      if (ready) {
        location.reload();
        return;
      }
      dialog.close();
      ctx.toast('重启超时，请手动刷新页面确认服务状态', { type: 'error', duration: 3600 });
    }

    /* ── 定时自动刷新（仅页面可见时） ───────────────────────────── */
    function startAutoRefresh() {
      if (timer) clearInterval(timer);
      timer = setInterval(() => {
        if (disposed) return;
        if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
        if (restarting) return;
        silentRefresh();
      }, AUTO_REFRESH_MS);
    }

    /* ── 启动 ───────────────────────────────────────────────────── */
    await loadWithFeedback();
    if (!disposed) startAutoRefresh();
  },
};
