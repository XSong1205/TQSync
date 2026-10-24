/**
 * 插件页 —— 热插拔消息处理插件
 * =====================================================================
 * 数据：GET /admin/plugins → { total, loaded, enabled, plugins[] }
 * 布局：指标卡 → 搜索 → 插件卡片（可点按进入操作）→ 上传入口。
 *
 * 依赖：../ui.js（唯一组件库）、../api.js
 */

import * as ui from '../ui.js';
import { api } from '../api.js';

const {
  h,
  clear,
  icon,
  card,
  button,
  iconButton,
  field,
  searchBar,
  skeleton,
  emptyState,
  errorBlock,
  alert,
  badge,
  chip,
  metricsGrid,
  switchControl,
  loadingBlock,
  debounce,
} = ui;

const MATCHER_LABELS = {
  exact: '精确',
  prefix: '前缀',
  regex: '正则',
};

/* ───────────────────────────── 小工具 ───────────────────────────── */

function errorText(err, fallback = '请稍后重试') {
  if (!err) return fallback;
  return err.detail || err.message || fallback;
}

function safeInt(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n) : fallback;
}

/** 卡片点击时忽略开关 / 按钮等内部可交互元素 */
function isInteractiveTarget(target) {
  if (!target || typeof target.closest !== 'function') return false;
  return Boolean(
    target.closest('.mi-switch') ||
      target.closest('button') ||
      target.closest('a') ||
      target.closest('input') ||
      target.closest('select') ||
      target.closest('textarea')
  );
}

/* ───────────────────────────── 页面模块 ───────────────────────────── */

export default {
  id: 'plugins',
  label: '插件',
  icon: 'puzzle',
  tab: true,
  title: '插件',
  subtitle: '热插拔消息处理插件',
  async mount(root, ctx) {
    mountPlugins(root, ctx);
  },
};

function mountPlugins(root, ctx) {
  const state = { loaded: false, loading: false, error: null, data: null };
  const deferred = [];
  let query = '';

  /* ── 同步渲染骨架 ── */
  const metricsHost = h('div');
  const listHost = h('div');
  const onSearch = debounce((raw) => {
    query = String(raw || '').trim().toLowerCase();
    renderPlugins();
  }, 160);
  deferred.push(() => onSearch.cancel());
  const search = searchBar({ placeholder: '搜索插件名称或描述…', onInput: onSearch });
  const countBadge = badge('0 个', 'neutral');
  const toolbar = h(
    'div',
    { class: 'page-toolbar' },
    h('div', { class: 'page-toolbar__grow' }, search.el),
    countBadge
  );
  root.appendChild(metricsHost);
  root.appendChild(toolbar);
  root.appendChild(listHost);

  const uploadBtn = button({
    text: '上传插件',
    icon: 'upload',
    variant: 'tonal',
    onClick: () => uploadPlugin(uploadBtn),
  });
  uploadBtn.style.height = '44px';
  ctx.setHero({ actions: [uploadBtn] });

  ctx.onRefresh(async () => {
    await loadPlugins({ force: true, quiet: true });
  });
  ctx.onCleanup(() => {
    deferred.forEach((fn) => {
      try {
        fn();
      } catch {
        /* 忽略清理异常 */
      }
    });
  });

  renderMetrics();
  renderPlugins();
  loadPlugins();

  /* ────────────────────────── 数据加载 ────────────────────────── */

  function normalize(res) {
    const plugins = Array.isArray(res && res.plugins)
      ? res.plugins.filter((p) => p && typeof p === 'object')
      : [];
    return {
      plugins,
      total: safeInt(res && res.total, plugins.length),
      loaded: safeInt(res && res.loaded, plugins.filter((p) => p.loaded).length),
      enabled: safeInt(res && res.enabled, plugins.filter((p) => p.enabled).length),
    };
  }

  async function loadPlugins(options = {}) {
    const force = options.force === true;
    const quiet = options.quiet === true;
    if (state.loading) return;
    if (state.loaded && !force) {
      renderMetrics();
      renderPlugins();
      return;
    }
    state.loading = true;
    state.error = null;
    if (!quiet) {
      renderMetrics();
      renderPlugins();
    }
    try {
      state.data = normalize(await api.get('/admin/plugins'));
      state.loaded = true;
    } catch (err) {
      state.error = err;
      if (state.loaded) ctx.toastErr(err, '刷新插件列表失败');
    } finally {
      state.loading = false;
    }
    if (ctx.isStale()) return;
    renderMetrics();
    renderPlugins();
  }

  function recomputeCounts() {
    const data = state.data;
    if (!data) return;
    data.total = data.plugins.length;
    data.loaded = data.plugins.filter((p) => p && p.loaded).length;
    data.enabled = data.plugins.filter((p) => p && p.enabled).length;
  }

  /* ────────────────────────── 指标 / 列表 ────────────────────────── */

  function renderMetrics() {
    clear(metricsHost);
    if (!state.data) {
      if (!state.error) metricsHost.appendChild(skeleton({ type: 'card', count: 1 }));
      return;
    }
    const data = state.data;
    const grid = metricsGrid([
      { label: '插件总数', value: String(data.total), icon: 'puzzle', tone: 'accent' },
      { label: '已加载', value: String(data.loaded), icon: 'check', tone: 'success' },
      { label: '已启用', value: String(data.enabled), icon: 'activity' },
    ]);
    grid.style.gridTemplateColumns = 'repeat(3, minmax(0, 1fr))'; // 3 个指标一排，移动端也放得下
    metricsHost.appendChild(grid);
  }

  function matchesQuery(plugin) {
    if (!query) return true;
    const name = String(plugin.name || '').toLowerCase();
    const desc = String(plugin.description || '').toLowerCase();
    return name.includes(query) || desc.includes(query);
  }

  function renderPlugins() {
    clear(listHost);
    if (!state.data) {
      countBadge.textContent = state.error ? '—' : '…';
      listHost.appendChild(
        state.error
          ? errorBlock({
              title: '插件列表加载失败',
              message: errorText(state.error),
              onRetry: () => loadPlugins({ force: true }),
            })
          : skeleton({ type: 'card', count: 3 })
      );
      return;
    }

    const plugins = state.data.plugins;
    const filtered = query ? plugins.filter(matchesQuery) : plugins;
    countBadge.textContent = query ? `${filtered.length}/${plugins.length}` : `${plugins.length} 个`;

    if (!plugins.length) {
      listHost.appendChild(
        emptyState({
          icon: 'puzzle',
          title: '暂无插件',
          desc: '把 .py 插件文件放入 plugins/ 目录，或点击右上角「上传插件」添加。',
          actionText: '上传插件',
          onAction: () => uploadPlugin(uploadBtn),
        })
      );
      return;
    }
    if (!filtered.length) {
      listHost.appendChild(
        emptyState({
          icon: 'search',
          title: '没有匹配的插件',
          desc: `没有找到名称或描述包含「${query}」的插件。`,
          actionText: '清空搜索',
          onAction: () => {
            query = '';
            search.set('');
            renderPlugins();
          },
        })
      );
      return;
    }

    const list = h('div', {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        padding: '0 var(--mi-page-x)',
      },
    });
    filtered.forEach((plugin) => list.appendChild(pluginCard(plugin)));
    listHost.appendChild(list);
    listHost.appendChild(
      h(
        'div',
        { class: 'page-note', style: { marginTop: '12px' } },
        '插件热插拔：启用后立即参与消息匹配；删除会移除 plugins/ 目录下的 .py 文件。'
      )
    );
  }

  /* ────────────────────────── 插件卡片 ────────────────────────── */

  function matcherChips(matchers) {
    const chips = matchers.map((matcher) => {
      const type = String((matcher && matcher.type) || 'exact');
      const label = MATCHER_LABELS[type] || type;
      const pattern =
        matcher && matcher.pattern !== null && matcher.pattern !== undefined ? String(matcher.pattern) : '';
      const el = chip({ text: `${label} ${pattern}`, tone: 'accent' });
      const desc = matcher && matcher.description ? String(matcher.description) : '';
      el.title = desc ? `${desc}（${type}: ${pattern}）` : `匹配方式 ${type}：${pattern}`;
      return el;
    });
    return h(
      'div',
      { class: 'mi-stack', style: { gap: '6px' } },
      h('div', { class: 'mi-text-xs mi-text-tertiary' }, `触发方式 · ${matchers.length} 个`),
      h('div', { class: 'mi-hstack mi-wrap', style: { gap: '6px' } }, chips)
    );
  }

  function pluginCard(plugin) {
    const name = String(plugin.name || '未命名插件');
    const version = plugin.version && String(plugin.version) !== '-' ? String(plugin.version) : '';
    const author = plugin.author ? String(plugin.author) : '';
    const file = plugin.file ? String(plugin.file) : '';
    const matchers = Array.isArray(plugin.matchers) ? plugin.matchers : [];
    const loadMs = Math.max(0, safeInt(plugin.load_time_ms, 0));
    const loadTimeText = plugin.loaded || loadMs > 0 ? `加载耗时 ${loadMs} ms` : '未加载';
    let pending = false;

    const enabledBadge = badge(plugin.enabled ? '已启用' : '已禁用', plugin.enabled ? 'success' : 'neutral');
    const loadedBadge = badge(plugin.loaded ? '加载正常' : '加载失败', plugin.loaded ? 'success' : 'danger');

    const head = h(
      'div',
      { class: 'mi-hstack', style: { gap: '12px', alignItems: 'flex-start' } },
      h(
        'span',
        { class: 'mi-row__icon', style: { width: '44px', height: '44px', borderRadius: '14px', flex: 'none' } },
        icon('puzzle', 22)
      ),
      h(
        'div',
        { class: 'mi-grow', style: { minWidth: '0', display: 'flex', flexDirection: 'column', gap: '3px' } },
        h(
          'div',
          { class: 'mi-hstack', style: { gap: '7px', minWidth: '0', flexWrap: 'wrap' } },
          h(
            'span',
            {
              class: 'mi-row__title mi-row__title--strong',
              style: {
                fontSize: '16.5px',
                minWidth: '0',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              },
              title: name,
            },
            name
          ),
          version ? badge(`v${version}`, 'neutral') : null
        ),
        h(
          'div',
          { class: 'mi-row__subtitle' },
          [author ? `作者 ${author}` : '作者未知', file].filter(Boolean).join(' · ')
        )
      )
    );

    const desc = plugin.description
      ? h(
          'div',
          {
            class: 'mi-text-sm',
            style: { color: 'var(--mi-text-secondary)', lineHeight: '1.55', overflowWrap: 'anywhere' },
          },
          String(plugin.description)
        )
      : null;

    const matcherBlock = matchers.length ? matcherChips(matchers) : null;

    let errAlert = null;
    if (plugin.error) {
      errAlert = alert({ tone: 'warning', text: String(plugin.error) });
      errAlert.style.margin = '2px 0 0';
    }

    const footer = h(
      'div',
      {
        class: 'mi-between',
        style: {
          marginTop: '2px',
          paddingTop: '10px',
          borderTop: '1px solid var(--mi-separator)',
          gap: '10px',
        },
      },
      h(
        'div',
        { class: 'mi-grow', style: { minWidth: '0', display: 'flex', flexDirection: 'column', gap: '4px' } },
        h('div', { class: 'mi-hstack mi-wrap', style: { gap: '6px' } }, enabledBadge, loadedBadge),
        h('div', { class: 'mi-text-xs mi-text-tertiary mi-num' }, loadTimeText)
      ),
      switchControl({
        checked: Boolean(plugin.enabled),
        onChange: async (next) => {
          if (pending) throw new Error('操作进行中');
          pending = true;
          try {
            await togglePlugin(plugin, next, enabledBadge);
          } finally {
            pending = false;
          }
        },
      })
    );

    const body = h(
      'div',
      { class: 'mi-stack', style: { gap: '10px' } },
      head,
      desc,
      matcherBlock,
      errAlert,
      footer
    );

    return card({
      children: [body],
      onClick: (event) => {
        if (isInteractiveTarget(event.target)) return;
        openPluginActions(plugin);
      },
    });
  }

  function syncEnabledBadge(el, enabled) {
    el.textContent = enabled ? '已启用' : '已禁用';
    el.className = `mi-badge mi-badge--${enabled ? 'success' : 'neutral'}`;
  }

  async function togglePlugin(plugin, next, enabledBadgeEl) {
    const prev = Boolean(plugin.enabled);
    plugin.enabled = next;
    syncEnabledBadge(enabledBadgeEl, next);
    recomputeCounts();
    renderMetrics();
    try {
      const res = await api.post(
        `/admin/plugins/${encodeURIComponent(plugin.name)}/${next ? 'enable' : 'disable'}`
      );
      ctx.toast((res && res.message) || (next ? '插件已启用' : '插件已禁用'), {
        type: 'success',
        duration: 1800,
      });
    } catch (err) {
      plugin.enabled = prev;
      syncEnabledBadge(enabledBadgeEl, prev);
      recomputeCounts();
      renderMetrics();
      ctx.toastErr(err, next ? '启用插件失败' : '禁用插件失败');
      throw err; // 让 switchControl 回滚开关
    }
  }

  /* ────────────────────────── 卡片操作 ────────────────────────── */

  async function openPluginActions(plugin) {
    const name = String(plugin.name || '插件');
    const choice = await ctx.actionSheet({
      title: name,
      items: [
        { text: '重载插件', icon: 'refresh', value: 'reload' },
        { text: '查看 / 编辑数据', icon: 'database', value: 'data' },
        { text: '删除插件', icon: 'trash', tone: 'danger', value: 'delete' },
      ],
    });
    if (choice === 'reload') await reloadPlugin(plugin);
    else if (choice === 'data') openPluginData(plugin);
    else if (choice === 'delete') await deletePlugin(plugin);
  }

  async function reloadPlugin(plugin) {
    const name = String(plugin.name || '');
    const tip = ctx.toast(`正在重载 ${name}…`, { duration: 8000 });
    try {
      const res = await api.post(`/admin/plugins/${encodeURIComponent(name)}/reload`);
      if (tip && typeof tip.close === 'function') tip.close();
      if (res && res.error) {
        ctx.toast(`重载完成，但加载失败：${res.error}`, { type: 'warning', duration: 4200 });
      } else {
        ctx.toast(`重载成功 · ${Math.max(0, safeInt(res && res.load_time_ms, 0))} ms`, {
          type: 'success',
        });
      }
    } catch (err) {
      if (tip && typeof tip.close === 'function') tip.close();
      ctx.toastErr(err, '重载插件失败');
    }
    await loadPlugins({ force: true, quiet: true });
  }

  async function deletePlugin(plugin) {
    const name = String(plugin.name || '');
    const ok = await ctx.confirm({
      title: '删除插件',
      message: `确定删除插件「${name}」吗？插件文件将从 plugins/ 目录移除，且无法通过页面恢复。`,
      confirmText: '删除',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/admin/plugins/${encodeURIComponent(name)}`);
      ctx.toast(`已删除插件 ${name}`, { type: 'success' });
    } catch (err) {
      ctx.toastErr(err, '删除插件失败');
    }
    await loadPlugins({ force: true, quiet: true });
  }

  /* ────────────────────────── 插件数据面板 ────────────────────────── */

  function openPluginData(plugin) {
    const pluginName = String(plugin.name || '');
    const body = h('div', { style: { padding: '2px 20px 12px' } });
    let closed = false;
    let current = {};

    ctx.openSheet({
      title: `${pluginName} · 数据`,
      content: body,
      onClose: () => {
        closed = true;
      },
    });

    function loadData() {
      if (closed) return;
      clear(body);
      body.appendChild(loadingBlock('正在读取插件数据…'));
      api
        .get(`/admin/plugins/${encodeURIComponent(pluginName)}/data`)
        .then((res) => {
          if (closed) return;
          const data = res && res.data && typeof res.data === 'object' && !Array.isArray(res.data) ? res.data : {};
          current = data;
          renderData();
        })
        .catch((err) => {
          if (closed) return;
          clear(body);
          body.appendChild(
            errorBlock({
              title: '插件数据加载失败',
              message: errorText(err),
              onRetry: () => loadData(),
            })
          );
        });
    }

    function dataEntry(key, value) {
      const valueText = value === null || value === undefined ? '' : String(value);
      const editBtn = iconButton({ icon: 'edit', label: `编辑 ${key}`, onClick: () => editEntry(key, valueText) });
      const delBtn = iconButton({ icon: 'trash', label: `删除 ${key}`, onClick: () => deleteEntry(key) });
      [editBtn, delBtn].forEach((btn) => {
        btn.style.width = '44px';
        btn.style.height = '44px';
      });
      return card({
        children: [
          h(
            'div',
            { class: 'mi-hstack', style: { alignItems: 'flex-start', gap: '8px' } },
            h(
              'div',
              { class: 'mi-grow', style: { minWidth: '0' } },
              h(
                'div',
                { class: 'mi-mono mi-text-sm', style: { fontWeight: '600', overflowWrap: 'anywhere' } },
                key
              ),
              h(
                'div',
                { class: 'mi-text-xs mi-text-tertiary', style: { marginTop: '3px' } },
                valueText ? `${valueText.length} 字符` : '空值'
              )
            ),
            h('div', { class: 'mi-hstack', style: { gap: '0', flex: 'none' } }, editBtn, delBtn)
          ),
          h(
            'div',
            {
              class: 'mi-mono mi-text-xs',
              style: {
                marginTop: '10px',
                padding: '9px 11px',
                borderRadius: 'var(--mi-radius-sm)',
                background: 'var(--mi-surface-sunken)',
                color: 'var(--mi-text-secondary)',
                whiteSpace: 'pre-wrap',
                overflowWrap: 'anywhere',
                maxHeight: '140px',
                overflowY: 'auto',
              },
            },
            valueText || '（空）'
          ),
        ],
      });
    }

    function renderData() {
      clear(body);
      const keys = Object.keys(current || {});
      body.appendChild(
        h(
          'div',
          { class: 'mi-between', style: { margin: '2px 0 12px', gap: '10px' } },
          h(
            'div',
            { class: 'mi-grow', style: { minWidth: '0' } },
            h('div', { class: 'mi-title', style: { fontSize: '17px' } }, '键值数据'),
            h(
              'div',
              { class: 'mi-text-xs mi-text-tertiary', style: { marginTop: '3px' } },
              `共 ${keys.length} 个键值 · 修改后立即生效`
            )
          ),
          button({
            text: '刷新',
            icon: 'refresh',
            variant: 'text',
            size: 'sm',
            onClick: () => loadData(),
          })
        )
      );

      if (!keys.length) {
        body.appendChild(
          emptyState({
            icon: 'database',
            title: '暂无存储数据',
            desc: '该插件还没有写入任何键值。可在下方新增，或由插件运行时通过 ctx.db 写入。',
          })
        );
      } else {
        const listWrap = h('div', { class: 'mi-stack', style: { gap: '10px' } });
        keys.forEach((key) => listWrap.appendChild(dataEntry(key, current[key])));
        body.appendChild(listWrap);
      }

      body.appendChild(
        h('div', { class: 'mi-section-title', style: { margin: '20px 0 8px' } }, '新增键值')
      );
      const keyField = field({ label: '键名', placeholder: '例如 target_time' });
      const valueField = field({ label: '值', placeholder: '任意文本，支持多行', multiline: true, rows: 3 });
      const addBtn = button({
        text: '保存键值',
        icon: 'plus',
        variant: 'filled',
        block: true,
        onClick: () => addEntry(keyField, valueField, addBtn),
      });
      addBtn.style.height = '44px';
      body.appendChild(h('div', { class: 'mi-stack', style: { gap: '12px' } }, keyField.el, valueField.el, addBtn));
      body.appendChild(
        h(
          'div',
          { class: 'page-note', style: { margin: '14px 0 0' } },
          '键值保存在 SQLite 的 plugin_data 表中，插件与 WebUI 共享同一份数据。'
        )
      );
    }

    function editEntry(key, value) {
      const valueField = field({ value, multiline: true, rows: 4 });
      ctx.dialog({
        title: `编辑「${key}」`,
        content: h(
          'div',
          { class: 'mi-stack', style: { gap: '10px' } },
          h(
            'div',
            { class: 'mi-mono mi-text-xs mi-text-tertiary', style: { overflowWrap: 'anywhere' } },
            key
          ),
          valueField.el
        ),
        actions: [
          { text: '取消', variant: 'text', value: false },
          {
            text: '保存',
            variant: 'filled',
            value: true,
            onClick: async () => {
              try {
                await api.put(`/admin/plugins/${encodeURIComponent(pluginName)}/data`, {
                  key,
                  value: valueField.get(),
                });
                ctx.toast('键值已更新', { type: 'success' });
                loadData();
                return true;
              } catch (err) {
                ctx.toastErr(err, '保存键值失败');
                return false;
              }
            },
          },
        ],
      });
    }

    async function deleteEntry(key) {
      const ok = await ctx.confirm({
        title: '删除键值',
        message: `确定删除「${key}」吗？此操作不可恢复。`,
        confirmText: '删除',
        danger: true,
      });
      if (!ok) return;
      try {
        await api.del(
          `/admin/plugins/${encodeURIComponent(pluginName)}/data/${encodeURIComponent(key)}`
        );
        ctx.toast('键值已删除', { type: 'success' });
        loadData();
      } catch (err) {
        // 后端该路由使用普通路径参数，键名含 / 时无法匹配（兼容提示）
        if (err && (err.status === 404 || err.status === 405)) {
          ctx.toast('该键无法通过该接口删除（键名可能包含 / 等路径字符）', {
            type: 'error',
            duration: 4200,
          });
        } else {
          ctx.toastErr(err, '删除键值失败');
        }
      }
    }

    async function addEntry(keyField, valueField, addBtn) {
      const key = keyField.get().trim();
      if (!key) {
        keyField.setError('键名不能为空');
        keyField.focus();
        return;
      }
      keyField.setError('');
      if (Object.prototype.hasOwnProperty.call(current, key)) {
        const ok = await ctx.confirm({
          title: '覆盖已有键值',
          message: `键「${key}」已存在，是否覆盖它的值？`,
          confirmText: '覆盖',
        });
        if (!ok) return;
      }
      addBtn.setLoading(true);
      try {
        await api.put(`/admin/plugins/${encodeURIComponent(pluginName)}/data`, {
          key,
          value: valueField.get(),
        });
        ctx.toast('键值已保存', { type: 'success' });
        loadData();
      } catch (err) {
        ctx.toastErr(err, '保存键值失败');
      } finally {
        addBtn.setLoading(false);
      }
    }

    loadData();
  }

  /* ────────────────────────── 上传 ────────────────────────── */

  async function uploadPlugin(trigger) {
    let files = [];
    try {
      files = await ui.pickFile({ accept: '.py' });
    } catch {
      files = [];
    }
    if (!files || !files.length) return;
    const file = files[0];
    if (!/\.py$/i.test(file.name || '')) {
      ctx.toast('只支持上传 .py 插件文件', { type: 'warning' });
      return;
    }
    if (trigger && typeof trigger.setLoading === 'function') trigger.setLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.upload('/admin/plugins/upload', form);
      const info = (res && res.plugin) || {};
      if (info.error) {
        ctx.toast(`已上传但加载失败：${info.error}`, { type: 'warning', duration: 4600 });
      } else {
        const name = info.name || file.name;
        const ms = Number.isFinite(Number(info.load_time_ms))
          ? ` · ${Math.max(0, Math.round(Number(info.load_time_ms)))} ms`
          : '';
        ctx.toast(`插件 ${name} 已上传并加载${ms}`, { type: 'success' });
      }
    } catch (err) {
      ctx.toastErr(err, '上传插件失败');
    } finally {
      if (trigger && typeof trigger.setLoading === 'function') trigger.setLoading(false);
    }
    await loadPlugins({ force: true, quiet: true });
  }

  /* 供调试 / 其他页面可能的引用 */
  return { load: loadPlugins };
}
