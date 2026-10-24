/**
 * 设置页（settings）—— 主 Tab
 * =====================================================================
 * 分区：
 *   1. 同步方向  GET/PUT /admin/sync/direction（核心功能，单选列表 + 组尾说明）
 *   2. 外观      跟随系统 / 浅色 / 深色（与 theme.js 双向同步）
 *   3. 安全      修改管理密钥（POST /admin/change-password）、退出登录
 *   4. 系统      重启服务（POST /admin/restart + /health 轮询恢复）
 *   5. 运行信息  只读展示 ctx.state.status
 *   6. 关于      版本、运行日志入口、GitHub 项目主页与脚注
 *
 * 数据来源：
 *   GET  /admin/sync/direction  { direction, options:[{value,label,desc}] }
 *   PUT  /admin/sync/direction  { direction }
 *   POST /admin/change-password { new_password }
 *   POST /admin/restart
 *   GET  /health（重启后探活，无需鉴权）
 *   GET  /admin/status（运行信息，与 app.js 共享 ctx.state.status）
 */
import * as ui from '../ui.js';
import { api } from '../api.js';

const { h } = ui;

const REPO_URL = 'https://github.com/XSong1205/TQSync';
const REPO_LABEL = 'github.com/XSong1205/TQSync';

const RESTART_POLL_MS = 1200;
const RESTART_TIMEOUT_MS = 60000;
const HEALTH_TIMEOUT_MS = 2000;
const RESTART_MIN_MS = 3500; // 旧进程退出前的 /health 不可信，最短等待时间

const THEME_OPTIONS = [
  { value: 'auto', label: '跟随系统' },
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
];

/* 后端不可用时的兜底选项（与 admin_api.py 保持一致） */
const DEFAULT_DIRECTIONS = [
  { value: 'both', label: '双向同步', desc: 'TG ↔ QQ 消息互通' },
  { value: 'tg_to_qq', label: '仅 TG → QQ', desc: 'TG 消息同步到 QQ，反之不转发' },
  { value: 'qq_to_tg', label: '仅 QQ → TG', desc: 'QQ 消息同步到 TG，反之不转发' },
];

const delay = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });

/* ─────────────────────────────────────────────────────────────────────
   工具
   ───────────────────────────────────────────────────────────────────── */

function errorText(err, fallback = '加载失败') {
  if (!err) return fallback;
  if (typeof err === 'string') return err;
  return err.detail || err.message || fallback;
}

/** "1.3.66 (abc)" / "v1.3.66 (abc)" → "v1.3.66 (abc)" */
function versionLabel(value) {
  if (value === null || value === undefined || value === '') return '';
  const text = String(value).trim();
  return /^v/i.test(text) ? text : `v${text}`;
}

/** 全量版本号 → "v1.3.66"（用于徽标） */
function shortVersion(value) {
  const match = String(value == null ? '' : value).match(/v?(\d+\.\d+(?:\.\d+)?)/);
  return match ? `v${match[1]}` : '';
}

function formatGroupId(value) {
  if (value === null || value === undefined || String(value).trim() === '') return '未配置';
  return String(value);
}

/** 只读信息行：值使用等宽字体 */
function infoRow(label, value) {
  const el = ui.row({ title: label, value: String(value) });
  const valueEl = el.querySelector('.mi-row__value');
  if (valueEl) valueEl.classList.add('mi-mono');
  return el;
}

/** 分段控件提升到 44px 触控高度 */
function enlargeSegment(seg, height = 44) {
  seg.style.height = `${height + 6}px`;
  seg.style.boxSizing = 'border-box';
  seg.querySelectorAll('.mi-segmented__item').forEach((item) => {
    item.style.height = `${height}px`;
  });
  return seg;
}

/* ─────────────────────────────────────────────────────────────────────
   页面模块
   ───────────────────────────────────────────────────────────────────── */

export default {
  id: 'settings',
  label: '设置',
  icon: 'settings',
  tab: true,
  title: '设置',
  subtitle: '',

  async mount(root, ctx) {
    let disposed = false;

    /* 同步方向 */
    let directions = DEFAULT_DIRECTIONS;
    let direction = '';
    let directionLoaded = false;
    let directionFailed = false;
    let directionError = '';
    let savingDirection = false;

    /* 重启流程 */
    let restarting = false;
    let activeRestartDialog = null;

    /* 其它动态引用 */
    let themeSeg = null;
    let themeHint = null;
    let versionBadge = null;

    ctx.onCleanup(() => {
      disposed = true;
      if (activeRestartDialog) {
        try { activeRestartDialog.close(); } catch { /* 忽略 */ }
        activeRestartDialog = null;
      }
    });

    /* ══════════════════════════════════════════════════════════════
       1. 同步方向（首屏即占位，数据到达后就地重绘）
       ══════════════════════════════════════════════════════════════ */
    const syncHost = h('div');
    root.appendChild(syncHost);

    function syncOptionRow(option) {
      const active = option.value === direction;
      const radio = h('span', {
        style: {
          flex: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '24px',
          height: '24px',
          borderRadius: '50%',
          border: active ? '0' : '2px solid var(--mi-border)',
          background: active ? 'var(--mi-accent)' : 'transparent',
          color: 'var(--mi-on-accent)',
          transition: 'background-color 160ms linear, border-color 160ms linear',
        },
        'aria-hidden': 'true',
      }, active ? ui.icon('check', 15) : null);

      return h('button', {
        class: ['mi-row', 'mi-row--tappable', 'mi-row--comfortable'],
        type: 'button',
        role: 'radio',
        'aria-checked': String(active),
        style: { width: '100%' },
        onClick: () => selectDirection(option.value),
      },
        h('span', { class: 'mi-row__content' },
          h('span', {
            class: 'mi-row__title',
            style: active ? { fontWeight: '600', color: 'var(--mi-accent)' } : null,
          }, option.label)
        ),
        radio
      );
    }

    function renderSync() {
      syncHost.replaceChildren();

      if (!directionLoaded && directionFailed) {
        syncHost.appendChild(ui.cardGroup({
          header: '同步方向',
          children: [ui.errorBlock({
            title: '同步方向加载失败',
            message: directionError,
            onRetry: () => loadSync(),
          })],
        }));
        return;
      }

      if (!directionLoaded) {
        syncHost.appendChild(ui.cardGroup({
          header: '同步方向',
          children: [ui.loadingBlock('正在读取同步方向…')],
        }));
        return;
      }

      const current = directions.find((item) => item.value === direction) || directions[0];
      const footer = h('div', { class: 'mi-hstack', style: { alignItems: 'flex-start', gap: '6px' } },
        ui.icon('info', 14),
        h('span', { style: { minWidth: '0' } },
          savingDirection
            ? '正在保存新的同步方向…'
            : `当前生效：${current && current.desc ? current.desc : '—'}`)
      );

      syncHost.appendChild(ui.cardGroup({
        header: '同步方向',
        children: directions.map((option) => syncOptionRow(option)),
        footer,
      }));
    }

    async function selectDirection(next) {
      if (savingDirection || next === direction) return;
      const previous = direction;
      direction = next;
      savingDirection = true;
      renderSync(); // 乐观更新
      try {
        await api.put('/admin/sync/direction', { direction: next });
        if (disposed || ctx.isStale()) return;
        const target = directions.find((item) => item.value === next);
        ctx.toast(`同步方向已设为「${target ? target.label : next}」`, { type: 'success' });
      } catch (err) {
        if (disposed || ctx.isStale()) return;
        direction = previous;
        ctx.toastErr(err, '修改同步方向失败');
      } finally {
        savingDirection = false;
        if (!disposed && !ctx.isStale()) renderSync();
      }
    }

    async function loadSync() {
      try {
        const data = await api.get('/admin/sync/direction');
        if (disposed || ctx.isStale()) return;
        if (data && Array.isArray(data.options) && data.options.length) {
          directions = data.options
            .filter((item) => item && item.value)
            .map((item) => ({
              value: String(item.value),
              label: String(item.label || item.value),
              desc: String(item.desc || ''),
            }));
        }
        if (data && data.direction) direction = String(data.direction);
        if (!direction && directions.length) direction = directions[0].value;
        directionLoaded = true;
        directionFailed = false;
        directionError = '';
        renderSync();
      } catch (err) {
        if (disposed || ctx.isStale()) return;
        directionError = errorText(err, '请检查后端服务是否正常运行');
        if (directionLoaded) {
          ctx.toastErr(err, '同步方向刷新失败');
          return;
        }
        directionFailed = true;
        renderSync();
      }
    }

    /* ══════════════════════════════════════════════════════════════
       2. 外观
       ══════════════════════════════════════════════════════════════ */
    themeSeg = enlargeSegment(ui.segmented({
      options: THEME_OPTIONS,
      value: ctx.getThemeMode() || 'auto',
      onChange: (value) => {
        ctx.setThemeMode(value);
        renderThemeHint();
        ctx.vibrate(6);
      },
    }));

    themeHint = h('div', {
      class: 'mi-text-xs mi-text-tertiary',
      style: { lineHeight: '1.5', minHeight: '17px' },
    }, '');

    const appearanceGroup = ui.cardGroup({
      header: '外观',
      children: [
        h('div', { style: { padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '10px' } },
          h('div', { class: 'mi-row__title', style: { fontWeight: '600' } }, '主题模式'),
          themeSeg,
          themeHint
        ),
      ],
    });
    root.appendChild(appearanceGroup);

    function renderThemeHint() {
      const mode = ctx.getThemeMode();
      if (mode === 'auto') themeHint.textContent = '跟随系统设置自动切换明暗主题';
      else themeHint.textContent = `固定使用${mode === 'dark' ? '深色' : '浅色'}主题`;
    }

    /* 侧栏/其他入口切换主题时保持分段控件同步；离开页面时退订 */
    const unsubscribeTheme = ctx.onThemeChange(() => {
      if (disposed) return;
      if (themeSeg) themeSeg.set(ctx.getThemeMode());
      renderThemeHint();
    });
    if (typeof unsubscribeTheme === 'function') ctx.onCleanup(unsubscribeTheme);

    /* ══════════════════════════════════════════════════════════════
       3. 安全
       ══════════════════════════════════════════════════════════════ */
    const securityAlertHost = h('div');
    root.appendChild(securityAlertHost);

    const securityGroup = ui.cardGroup({
      header: '安全',
      children: [
        ui.row({
          title: '修改管理密钥',
          subtitle: '至少 6 位，建议使用高强度密钥',
          icon: 'lock',
          iconTone: 'warning',
          chevron: true,
          onClick: () => openChangePassword(),
        }),
        ui.row({
          title: '退出登录',
          subtitle: '需要重新输入管理密钥',
          icon: 'power',
          iconTone: 'danger',
          danger: true,
          chevron: true,
          onClick: () => logout(),
        }),
      ],
    });
    root.appendChild(securityGroup);

    function renderInitialAlert() {
      securityAlertHost.replaceChildren();
      if (!ctx.state.initialToken) return;
      securityAlertHost.appendChild(ui.alert({
        tone: 'warning',
        text: '当前仍在使用初始管理密钥。为了控制台安全，建议立即修改为高强度密钥。',
      }));
    }

    function openChangePassword() {
      const newPwd = ui.field({
        label: '新密钥',
        placeholder: '至少 6 位',
        password: true,
        maxLength: 128,
        autofocus: true,
        supporting: '修改成功后当前登录会自动切换到新密钥',
      });
      const confirmPwd = ui.field({
        label: '确认新密钥',
        placeholder: '再次输入新密钥',
        password: true,
        maxLength: 128,
      });
      newPwd.input.addEventListener('input', () => newPwd.setError(''));
      confirmPwd.input.addEventListener('input', () => confirmPwd.setError(''));
      let busy = false;

      ctx.dialog({
        title: '修改管理密钥',
        message: '密钥用于登录本控制台，修改后需要重新登录。',
        content: h('div', { style: { display: 'flex', flexDirection: 'column', gap: '14px' } },
          newPwd.el, confirmPwd.el),
        actions: [
          { text: '取消', variant: 'text', value: false },
          {
            text: '保存',
            variant: 'filled',
            onClick: async () => {
              if (busy) return false;
              const pwd = newPwd.get().trim();
              const pwdAgain = confirmPwd.get().trim();
              newPwd.setError('');
              confirmPwd.setError('');
              if (pwd.length < 6) {
                newPwd.setError('新密钥长度不能少于 6 位');
                newPwd.focus();
                return false;
              }
              if (pwd !== pwdAgain) {
                confirmPwd.setError('两次输入的新密钥不一致');
                confirmPwd.focus();
                return false;
              }
              busy = true;
              try {
                await api.post('/admin/change-password', { new_password: pwd });
                api.setToken(pwd);
                if (ctx.state.status) ctx.state.status.is_initial_token = false;
                ctx.state.initialToken = false;
                renderInitialAlert();
                ctx.toast('管理密钥已更新', { type: 'success' });
                return true;
              } catch (err) {
                ctx.toastErr(err, '修改管理密钥失败');
                return false;
              } finally {
                busy = false;
              }
            },
          },
        ],
      });
    }

    async function logout() {
      const confirmed = await ctx.confirm({
        title: '退出登录',
        message: '退出后需要重新输入管理密钥才能访问控制台，确定退出吗？',
        confirmText: '退出登录',
        cancelText: '取消',
        danger: true,
      });
      if (!confirmed) return;
      api.clearToken();
      location.reload();
    }

    /* ══════════════════════════════════════════════════════════════
       4. 系统：重启服务
       ══════════════════════════════════════════════════════════════ */
    const systemGroup = ui.cardGroup({
      header: '系统',
      children: [
        ui.row({
          title: '重启服务',
          subtitle: '重启会短暂中断消息同步，完成后页面自动刷新',
          icon: 'refresh',
          iconTone: 'danger',
          danger: true,
          chevron: true,
          onClick: () => restartService(),
        }),
      ],
    });
    root.appendChild(systemGroup);

    function restartStep(text, state) {
      const color = state === 'done'
        ? 'var(--mi-success)'
        : state === 'active'
          ? 'var(--mi-accent)'
          : 'var(--mi-fill-strong)';
      return h('div', { class: 'mi-hstack', style: { gap: '8px' } },
        h('span', {
          style: { width: '6px', height: '6px', borderRadius: '50%', flex: 'none', background: color },
        }),
        h('span', null, text)
      );
    }

    function openRestartDialog() {
      const spinner = h('div', { class: 'mi-spinner mi-spinner--lg', style: { margin: '2px auto 14px' } });
      const statusEl = h('div', {
        style: {
          fontSize: 'var(--mi-text-secondary)',
          lineHeight: '1.5',
          textAlign: 'center',
          color: 'var(--mi-text-secondary)',
        },
      }, '正在重启服务，请稍候…');
      const stepsEl = h('div', {
        style: {
          marginTop: '14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '7px',
          fontSize: 'var(--mi-text-caption)',
          color: 'var(--mi-text-tertiary)',
        },
      },
        restartStep('重启请求已发送', 'done'),
        restartStep('等待服务恢复', 'active'),
        restartStep('自动刷新页面', 'pending')
      );
      const dialog = ctx.dialog({
        title: '正在重启服务…',
        content: h('div', { style: { padding: '6px 0 2px' } }, spinner, statusEl, stepsEl),
        dismissible: false,
        actions: [],
      });
      return { dialog, spinner, statusEl, stepsEl };
    }

    async function restartService() {
      if (restarting) return;
      const confirmed = await ctx.confirm({
        title: '重启服务',
        message: '重启会中断当前 Telegram ↔ QQ 消息同步，通常需要 5–15 秒恢复。重启期间页面会自动等待，请勿重复操作。',
        confirmText: '立即重启',
        cancelText: '取消',
        danger: true,
      });
      if (!confirmed || disposed) return;

      restarting = true;
      const uiRef = openRestartDialog();
      activeRestartDialog = uiRef.dialog;

      try {
        await api.post('/admin/restart');
      } catch (err) {
        // 服务可能已开始退出导致连接中断（status 0），继续等待恢复；
        // 鉴权/参数等真实错误则中止。
        if (err && err.status && err.status !== 0) {
          restarting = false;
          activeRestartDialog = null;
          uiRef.dialog.close();
          if (!disposed) ctx.toastErr(err, '重启请求失败');
          return;
        }
      }
      if (disposed) return;

      const startedAt = Date.now();
      const deadline = startedAt + RESTART_TIMEOUT_MS;
      let ready = false;

      while (!disposed && Date.now() < deadline) {
        await delay(RESTART_POLL_MS);
        if (disposed) break;
        const elapsed = Math.round((Date.now() - startedAt) / 1000);
        uiRef.statusEl.textContent = `正在等待服务恢复…（已等待 ${elapsed} 秒）`;
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
          let res;
          try {
            res = await fetch('/health', { cache: 'no-store', signal: controller.signal });
          } finally {
            clearTimeout(timeoutId);
          }
          // 旧进程可能在重启生效前仍响应 /health，因此要求最短等待时间
          if (res && res.ok && Date.now() - startedAt >= RESTART_MIN_MS) {
            ready = true;
            break;
          }
        } catch {
          /* 服务尚未恢复，继续轮询 */
        }
      }

      if (disposed) {
        restarting = false;
        return;
      }

      if (ready) {
        restarting = false;
        uiRef.statusEl.textContent = '重启完成，正在重新加载页面…';
        uiRef.statusEl.style.color = 'var(--mi-success)';
        const okIcon = h('div', {
          style: {
            display: 'flex',
            justifyContent: 'center',
            color: 'var(--mi-success)',
            marginBottom: '14px',
          },
        }, ui.icon('check', 30));
        uiRef.spinner.replaceWith(okIcon);
        ctx.toast('服务已重启', { type: 'success', duration: 1200 });
        setTimeout(() => location.reload(), 800);
        return;
      }

      restarting = false;
      activeRestartDialog = null;
      uiRef.dialog.close();
      ctx.toastErr(new Error('服务未在 60 秒内恢复，请前往「运行日志」检查错误'), '重启超时');
    }

    /* ══════════════════════════════════════════════════════════════
       5. 运行信息（只读，来自 ctx.state.status）
       ══════════════════════════════════════════════════════════════ */
    const runtimeHost = h('div');
    root.appendChild(runtimeHost);

    function renderRuntime() {
      const status = ctx.state && ctx.state.status;
      runtimeHost.replaceChildren();

      if (!status) {
        runtimeHost.appendChild(ui.cardGroup({
          header: '运行信息',
          children: [ui.loadingBlock('正在获取运行信息…')],
        }));
        return;
      }

      runtimeHost.appendChild(ui.cardGroup({
        header: '运行信息',
        children: [
          infoRow('版本', versionLabel(status.version) || '—'),
          infoRow('运行时长', status.uptime_seconds !== null && status.uptime_seconds !== undefined
            ? ctx.formatUptime(status.uptime_seconds)
            : '—'),
          infoRow('Telegram 群组', formatGroupId(status.tg_group_id)),
          infoRow('QQ 群组', formatGroupId(status.qq_group_id)),
          infoRow('数据库大小', status.db_size || '—'),
          infoRow('进程内存', status.memory_usage || '—'),
        ],
      }));
    }

    function renderRuntimeError(err) {
      runtimeHost.replaceChildren(ui.cardGroup({
        header: '运行信息',
        children: [ui.errorBlock({
          title: '运行信息加载失败',
          message: errorText(err, '无法获取系统状态'),
          onRetry: () => loadStatus(),
        })],
      }));
    }

    /* ══════════════════════════════════════════════════════════════
       6. 关于
       ══════════════════════════════════════════════════════════════ */
    versionBadge = ui.badge(shortVersion(ctx.state.version) || 'WebUI', 'accent');

    const aboutGroup = ui.cardGroup({
      header: '关于',
      children: [
        h('div', { style: { display: 'flex', alignItems: 'center', gap: '12px', padding: '16px' } },
          h('div', {
            style: {
              flex: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '52px',
              height: '52px',
              borderRadius: '16px',
              background: 'linear-gradient(135deg, #4c93ff, #2c6ff0)',
              boxShadow: '0 8px 20px rgba(52, 130, 255, 0.3)',
            },
          }, ui.brandMark(30)),
          h('div', { class: 'mi-grow', style: { minWidth: '0' } },
            h('div', { class: 'mi-hstack', style: { flexWrap: 'wrap', gap: '8px' } },
              h('span', { style: { fontSize: '18px', fontWeight: '700', letterSpacing: '-0.01em' } }, 'TQSync'),
              versionBadge
            ),
            h('div', { class: 'mi-text-xs mi-text-secondary', style: { marginTop: '3px' } },
              'Telegram ↔ QQ 双向消息同步')
          )
        ),
        ui.row({
          title: '查看运行日志',
          subtitle: '实时查看后端运行日志',
          icon: 'logs',
          chevron: true,
          onClick: () => ctx.go('logs'),
        }),
        ui.row({
          title: '项目主页',
          subtitle: REPO_LABEL,
          icon: 'external',
          iconTone: 'neutral',
          onClick: () => window.open(REPO_URL, '_blank', 'noopener,noreferrer'),
        }),
      ],
      footer: '控制台使用 Miuix 风格零依赖 Web 实现',
    });
    root.appendChild(aboutGroup);

    /* ── Hero / 版本徽标 ─────────────────────────────────────────── */
    function updateVersionBadge() {
      if (versionBadge) versionBadge.textContent = shortVersion(ctx.state.version) || 'WebUI';
    }

    function updateHero() {
      const version = versionLabel(ctx.state.version);
      ctx.setHero({
        subtitle: version
          ? `${version} · Telegram ↔ QQ 消息同步`
          : 'Telegram ↔ QQ 双向消息同步控制台',
      });
    }

    /* ══════════════════════════════════════════════════════════════
       数据加载
       ══════════════════════════════════════════════════════════════ */
    async function loadStatus({ quiet = false } = {}) {
      try {
        const data = await api.get('/admin/status');
        if (disposed || ctx.isStale()) return;
        ctx.state.status = data;
        ctx.state.version = data.version || ctx.state.version;
        ctx.state.initialToken = Boolean(data.is_initial_token);
        renderInitialAlert();
        renderRuntime();
        updateVersionBadge();
        updateHero();
      } catch (err) {
        if (disposed || ctx.isStale()) return;
        if (!ctx.state.status) renderRuntimeError(err);
        else if (!quiet) ctx.toastErr(err, '运行信息刷新失败');
      }
    }

    async function load() {
      await Promise.all([loadSync(), loadStatus()]);
    }

    ctx.onRefresh(load);

    /* ── 首屏同步渲染（数据未到也有完整结构） ───────────────────── */
    updateHero();
    renderInitialAlert();
    renderRuntime();
    renderSync();
    renderThemeHint();

    await load();
  },
};
