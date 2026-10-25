/**
 * 用户页 —— 绑定关系 / 管理员
 * =====================================================================
 * 顶部 segmented 切换两个视图；每个视图的数据只在首次进入时拉取，
 * 之后常驻内存（增删改后静默刷新），切换时仅重绘列表区域。
 * 屏蔽词属于消息过滤策略，已移动到「设置 → 消息过滤」。
 *
 * 依赖：../ui.js（唯一组件库）、../api.js
 */

import * as ui from '../ui.js';
import { api } from '../api.js';

const {
  h,
  clear,
  icon,
  cardGroup,
  row,
  badge,
  avatar,
  button,
  iconButton,
  field,
  searchBar,
  segmented,
  skeleton,
  emptyState,
  alert,
  errorBlock,
  keyValue,
  debounce,
} = ui;

const VIEW_OPTIONS = [
  { value: 'bindings', label: '绑定关系' },
  { value: 'admins', label: '管理员' },
];

const HERO_LABELS = {
  bindings: '新增绑定',
  admins: '添加管理员',
};

/** 单行省略文本样式 */
const ELLIPSIS = {
  minWidth: '0',
  flex: '0 1 auto',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

/* ───────────────────────────── 小工具 ───────────────────────────── */

function errorText(err, fallback = '请稍后重试') {
  if (!err) return fallback;
  return err.detail || err.message || fallback;
}

/** 正整数（用户 ID）字符串校验 */
function isPositiveInt(raw) {
  if (!/^\d+$/.test(String(raw == null ? '' : raw))) return false;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n > 0;
}

/** 把按钮高度提到 44px（移动端最小触摸目标） */
function tapify(el) {
  if (el && el.style) el.style.height = '44px';
  return el;
}

/** 32px 平台头像（TG / QQ） */
function makeAvatar(iconName, tone, dimmed = false) {
  const el = avatar({ icon: iconName, tone });
  el.style.width = '32px';
  el.style.height = '32px';
  if (dimmed) el.style.opacity = '0.32';
  return el;
}

/** 44px 删除图标按钮 */
function trashButton(label, onClick) {
  const btn = iconButton({ icon: 'trash', label, onClick });
  btn.style.width = '44px';
  btn.style.height = '44px';
  return btn;
}

/* ───────────────────────────── 页面模块 ───────────────────────────── */

export default {
  id: 'bindings',
  label: '用户',
  icon: 'users',
  tab: true,
  title: '用户',
  subtitle: '绑定关系与管理员权限',
  async mount(root, ctx) {
    mountMembers(root, ctx);
  },
};

function mountMembers(root, ctx) {
  /* ── 内存状态：两个视图各自惰性加载 ── */
  const store = {
    bindings: { loaded: false, loading: false, error: null, data: null },
    admins: { loaded: false, loading: false, error: null, data: null },
  };
  const filters = { bindings: '', admins: '' };
  const views = {};
  const deferred = [];
  let active = 'bindings';

  const FETCHERS = {
    bindings: () => api.get('/admin/bindings'),
    admins: () => api.get('/admin/admins'),
  };
  const PARSERS = {
    bindings: (res) => (Array.isArray(res) ? res : []),
    admins: (res) => ({
      admins: Array.isArray(res && res.admins)
        ? res.admins.map((id) => Number(id)).filter((id) => Number.isFinite(id))
        : [],
    }),
  };

  /* ── 同步渲染骨架 ── */
  const seg = segmented({
    options: VIEW_OPTIONS,
    value: active,
    onChange: (v) => showView(v),
  });
  seg.style.width = '100%'; // 移动端分段控件占满整行
  const segWrap = h('div', { class: 'page-toolbar' }, seg);
  const listHost = h('div');
  root.appendChild(segWrap);
  root.appendChild(listHost);

  ctx.onRefresh(async () => {
    await loadView(active, { force: true, quiet: true });
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

  showView(active);

  /* ────────────────────────── 视图切换 / 加载 ────────────────────────── */

  function ensureView(v) {
    if (views[v]) return views[v];
    const view = v === 'bindings' ? buildBindingsView() : buildAdminsView();
    views[v] = view;
    listHost.appendChild(view.el);
    return view;
  }

  function showView(v) {
    active = v;
    ensureView(v);
    Object.entries(views).forEach(([key, view]) => {
      view.el.hidden = key !== v;
    });
    renderHero(v);
    loadView(v);
  }

  function renderHero(v) {
    const action = tapify(
      button({
        text: HERO_LABELS[v] || '新增',
        icon: 'plus',
        variant: 'tonal',
        onClick: () => primaryAction(v),
      })
    );
    ctx.setHero({ actions: [action] });
  }

  function primaryAction(v) {
    if (v === 'bindings') {
      openAddBinding();
      return;
    }
    const view = views[v];
    if (view && typeof view.focusAdd === 'function') view.focusAdd();
  }

  /**
   * 拉取 / 渲染某个视图。
   * @param {'bindings'|'admins'} v
   * @param {{force?:boolean, quiet?:boolean}} options
   */
  function loadView(v, options = {}) {
    const st = store[v];
    if (!st || st.loading) return Promise.resolve();
    const force = options.force === true;
    const quiet = options.quiet === true;
    if (st.loaded && !force) {
      renderView(v);
      return Promise.resolve();
    }
    st.loading = true;
    st.error = null;
    if (!quiet) renderView(v); // 立即展示骨架屏
    return (async () => {
      try {
        const payload = await FETCHERS[v]();
        st.data = PARSERS[v](payload);
        st.loaded = true;
        st.error = null;
      } catch (err) {
        st.error = err;
        if (st.loaded) ctx.toastErr(err, '刷新失败'); // 有旧数据时保留旧内容
      } finally {
        st.loading = false;
      }
      if (ctx.isStale()) return;
      renderView(v);
    })();
  }

  function renderView(v) {
    const st = store[v];
    const view = views[v];
    if (!view) return;
    if (st.error && !st.loaded) {
      if (view.count) view.count.textContent = '—';
      view.setList(
        errorBlock({
          title: '加载失败',
          message: errorText(st.error),
          onRetry: () => loadView(v, { force: true }),
        })
      );
      return;
    }
    if (!st.loaded) {
      view.setList(skeleton({ type: 'list', count: 5 }));
      return;
    }
    if (v === 'bindings') renderBindings(view, st.data);
    else renderAdmins(view, st.data);
  }

  /* ────────────────────────── A. 绑定关系 ────────────────────────── */

  function buildBindingsView() {
    const listEl = h('div');
    const onSearch = debounce((raw) => {
      filters.bindings = String(raw || '').trim().toLowerCase();
      renderView('bindings');
    }, 160);
    deferred.push(() => onSearch.cancel());
    const search = searchBar({ placeholder: '搜索昵称、ID 或 UID…', onInput: onSearch });
    const count = badge('0 条', 'neutral');
    const toolbar = h(
      'div',
      { class: 'page-toolbar' },
      h('div', { class: 'page-toolbar__grow' }, search.el),
      count
    );
    const el = h('div', { hidden: true }, toolbar, listEl);
    return {
      el,
      listEl,
      search,
      count,
      setList(node) {
        clear(listEl);
        if (node) listEl.appendChild(node);
      },
    };
  }

  function bindingHaystack(b) {
    return [b.tg_username, b.qq_nickname, b.tg_user_id, b.qq_user_id, b.uid, b.status]
      .filter((v) => v !== null && v !== undefined && v !== '')
      .join(' ')
      .toLowerCase();
  }

  function renderBindings(view, data) {
    const list = Array.isArray(data) ? data : [];
    const q = filters.bindings;
    const filtered = q ? list.filter((b) => bindingHaystack(b).includes(q)) : list;
    const boundCount = list.filter((b) => b && b.tg_user_id !== null && b.tg_user_id !== undefined).length;
    const unboundCount = Math.max(0, list.length - boundCount);
    view.count.textContent = q ? `${filtered.length}/${list.length}` : `${list.length} 条`;

    if (!list.length) {
      view.setList(
        emptyState({
          icon: 'users',
          title: '暂无绑定关系',
          desc: '还没有 Telegram ↔ QQ 绑定。可在群内让用户发送 /bind 完成绑定，或点击右上角「新增绑定」手动添加。',
          actionText: '新增绑定',
          onAction: () => openAddBinding(),
        })
      );
      return;
    }
    if (!filtered.length) {
      view.setList(
        emptyState({
          icon: 'search',
          title: '没有匹配的绑定',
          desc: `没有找到与「${q}」相关的绑定关系。`,
          actionText: '清空搜索',
          onAction: () => {
            filters.bindings = '';
            view.search.set('');
            renderView('bindings');
          },
        })
      );
      return;
    }

    view.setList(
      cardGroup({
        header: '绑定关系',
        children: filtered.map((b) => bindingRow(b)),
        footer: `已绑定 ${boundCount} 位 · 未绑定 ${unboundCount} 位（未绑定表示该 QQ 用户同步过消息，但尚未绑定 Telegram）`,
      })
    );
  }

  function bindingRow(b) {
    const bound = b && b.tg_user_id !== null && b.tg_user_id !== undefined;
    const tgName = b.tg_username || (bound ? `TG ${b.tg_user_id}` : '未绑定');
    const qqName = b.qq_nickname || `QQ ${b.qq_user_id}`;
    const status = b.status || (bound ? '已绑定' : '未绑定');
    const idLine = bound
      ? `TG ${b.tg_user_id} · QQ ${b.qq_user_id}`
      : `QQ ${b.qq_user_id} · 仅同步过消息，等待绑定`;
    const uidLine = b.uid ? `UID ${b.uid}` : 'UID 未生成（TG 未绑定）';
    const tgTitleStyle = bound ? ELLIPSIS : { ...ELLIPSIS, color: 'var(--mi-text-tertiary)' };

    const head = h(
      'div',
      { class: 'mi-hstack', style: { gap: '10px', alignItems: 'center' } },
      h(
        'div',
        { class: 'mi-hstack', style: { gap: '6px', flex: 'none' } },
        makeAvatar('telegram', 'tg', !bound),
        makeAvatar('qq', 'qq')
      ),
      h(
        'div',
        { class: 'mi-grow', style: { minWidth: '0' } },
        h(
          'div',
          { class: 'mi-hstack', style: { gap: '6px', minWidth: '0', alignItems: 'center' } },
          h('span', { class: 'mi-row__title mi-row__title--strong', style: tgTitleStyle, title: tgName }, tgName),
          h('span', { class: 'mi-text-tertiary', style: { flex: 'none' } }, bound ? '↔' : '·'),
          h('span', { class: 'mi-row__title', style: ELLIPSIS, title: qqName }, qqName)
        )
      ),
      badge(status, bound ? 'success' : 'neutral')
    );

    const meta = h(
      'div',
      { class: 'mi-stack', style: { gap: '2px', marginTop: '8px' } },
      h('div', { class: 'mi-row__subtitle mi-mono', style: { fontSize: '11.5px' } }, idLine),
      h(
        'div',
        {
          class: 'mi-row__subtitle mi-mono',
          style: {
            fontSize: '11px',
            color: 'var(--mi-text-tertiary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          },
          title: b.uid || '',
        },
        uidLine
      )
    );

    return h(
      'button',
      {
        class: 'mi-row mi-row--tappable',
        type: 'button',
        style: { display: 'block', padding: '12px 16px', textAlign: 'left' },
        title: `${tgName} ↔ ${qqName}`,
        onClick: () => openBindingActions(b),
      },
      head,
      meta
    );
  }

  function bindingTitle(b) {
    const bound = b && b.tg_user_id !== null && b.tg_user_id !== undefined;
    const tg = b.tg_username || (bound ? `TG ${b.tg_user_id}` : '未绑定');
    const qq = b.qq_nickname || `QQ ${b.qq_user_id}`;
    return `${tg} ↔ ${qq}`;
  }

  async function openBindingActions(b) {
    const bound = b && b.tg_user_id !== null && b.tg_user_id !== undefined;
    const items = [
      { text: '查看详情', icon: 'info', value: 'detail' },
      { text: '复制 QQ 号', icon: 'copy', value: 'copy-qq' },
    ];
    if (bound) items.push({ text: '删除绑定', icon: 'trash', tone: 'danger', value: 'delete' });
    else items.push({ text: '绑定到 Telegram', icon: 'users', value: 'bind' });

    const choice = await ctx.actionSheet({ title: bindingTitle(b), items });
    if (choice === 'detail') showBindingDetail(b);
    else if (choice === 'copy-qq') {
      const ok = await ctx.copyText(String(b.qq_user_id == null ? '' : b.qq_user_id));
      ctx.toast(ok ? 'QQ 号已复制' : '复制失败', { type: ok ? 'success' : 'warning' });
    } else if (choice === 'delete') {
      deleteBinding(b.tg_user_id);
    } else if (choice === 'bind') {
      openAddBinding({ qqId: b.qq_user_id });
    }
  }

  function showBindingDetail(b) {
    const bound = b && b.tg_user_id !== null && b.tg_user_id !== undefined;
    const pairs = [
      { k: '状态', v: b.status || (bound ? '已绑定' : '未绑定') },
      { k: 'Telegram 用户 ID', v: bound ? String(b.tg_user_id) : '未绑定' },
      { k: 'Telegram 用户名', v: b.tg_username || '—' },
      { k: 'QQ 用户 ID', v: b.qq_user_id == null ? '—' : String(b.qq_user_id) },
      { k: 'QQ 昵称', v: b.qq_nickname || '—' },
      { k: 'UID', v: b.uid || '—' },
    ];
    const text = pairs.map((p) => `${p.k}：${p.v}`).join('\n');

    const actions = [
      button({
        text: '复制绑定信息',
        icon: 'copy',
        variant: 'tonal',
        block: true,
        onClick: async () => {
          const ok = await ctx.copyText(text);
          ctx.toast(ok ? '绑定信息已复制' : '复制失败，请手动选择文本', {
            type: ok ? 'success' : 'warning',
          });
        },
      }),
    ];
    if (bound) {
      actions.push(
        button({
          text: '删除此绑定',
          icon: 'trash',
          variant: 'danger',
          block: true,
          onClick: () => {
            sheet.close();
            deleteBinding(b.tg_user_id);
          },
        })
      );
    } else {
      actions.push(
        button({
          text: '绑定到 Telegram',
          icon: 'users',
          variant: 'filled',
          block: true,
          onClick: () => {
            sheet.close();
            openAddBinding({ qqId: b.qq_user_id });
          },
        })
      );
    }

    const content = h(
      'div',
      { style: { padding: '2px 20px 10px' } },
      h(
        'div',
        { class: 'mi-stack', style: { gap: '16px' } },
        keyValue(pairs),
        h('div', { class: 'mi-stack', style: { gap: '10px' } }, actions)
      )
    );
    const sheet = ctx.openSheet({ title: '绑定详情', content });
    return sheet;
  }

  async function deleteBinding(tgUserId) {
    const ok = await ctx.confirm({
      title: '删除绑定',
      message: '确定删除这条 Telegram ↔ QQ 绑定吗？删除后双方消息会以「未绑定」身份继续同步。',
      confirmText: '删除',
      danger: true,
    });
    if (!ok) return false;
    try {
      await api.del(`/admin/bindings/${encodeURIComponent(tgUserId)}`);
      ctx.toast('绑定已删除', { type: 'success' });
      await loadView('bindings', { force: true, quiet: true });
      return true;
    } catch (err) {
      ctx.toastErr(err, '删除绑定失败');
      return false;
    }
  }

  function openAddBinding(preset = {}) {
    const tgField = field({
      label: 'Telegram User ID',
      value: preset.tgId == null ? '' : String(preset.tgId),
      placeholder: '例如 7123456789',
      inputMode: 'numeric',
      supporting: '纯数字，可在 Telegram 资料页或 @userinfobot 获取',
    });
    const qqField = field({
      label: 'QQ 用户 ID',
      value: preset.qqId == null ? '' : String(preset.qqId),
      placeholder: '例如 2856231471',
      inputMode: 'numeric',
      supporting: '纯数字，可在 QQ 资料页或群成员列表复制',
    });
    const nameField = field({
      label: '昵称（可选）',
      placeholder: '例如 浅巷墨漓',
      maxLength: 64,
      supporting: '留空则沿用两人现有的昵称 / 用户名',
    });
    const note = h(
      'div',
      { class: 'mi-text-xs mi-text-tertiary', style: { lineHeight: '1.55' } },
      '提示：后端会把此处的「昵称」同时写入 Telegram 用户名与 QQ 昵称两列（历史行为），因此两侧会显示同一个名字。'
    );

    let busy = false;
    const d = ctx.dialog({
      title: '新增绑定',
      content: h(
        'div',
        { class: 'mi-stack', style: { gap: '14px' } },
        tgField.el,
        qqField.el,
        nameField.el,
        note
      ),
      actions: [
        { text: '取消', variant: 'text', value: false },
        {
          text: '保存',
          variant: 'filled',
          value: true,
          onClick: async () => {
            if (busy) return false;
            const tgRaw = tgField.get().trim();
            const qqRaw = qqField.get().trim();
            if (!tgRaw) {
              tgField.setError('请输入 Telegram User ID');
              tgField.focus();
              return false;
            }
            if (!isPositiveInt(tgRaw)) {
              tgField.setError('请输入有效的正整数 ID');
              return false;
            }
            if (!qqRaw) {
              qqField.setError('请输入 QQ 用户 ID');
              qqField.focus();
              return false;
            }
            if (!isPositiveInt(qqRaw)) {
              qqField.setError('请输入有效的正整数 ID');
              return false;
            }
            tgField.setError('');
            qqField.setError('');
            const body = { tg_user_id: Number(tgRaw), qq_user_id: Number(qqRaw) };
            const nickname = nameField.get().trim();
            if (nickname) body.tg_username = nickname;
            busy = true;
            try {
              await api.put('/admin/bindings', body);
              ctx.toast('绑定已保存', { type: 'success' });
              await loadView('bindings', { force: true, quiet: true });
              return true;
            } catch (err) {
              ctx.toastErr(err, '保存绑定失败');
              return false;
            } finally {
              busy = false;
            }
          },
        },
      ],
    });
    return d.result;
  }

  /* ────────────────────────── B. 管理员 ────────────────────────── */

  function buildAdminsView() {
    const listEl = h('div');
    const onSearch = debounce((raw) => {
      filters.admins = String(raw || '').trim().toLowerCase();
      renderView('admins');
    }, 160);
    deferred.push(() => onSearch.cancel());
    const search = searchBar({ placeholder: '搜索管理员 ID…', onInput: onSearch });
    const count = badge('0 位', 'neutral');
    const toolbar = h(
      'div',
      { class: 'page-toolbar' },
      h('div', { class: 'page-toolbar__grow' }, search.el),
      count
    );

    const note = alert({
      tone: 'info',
      text: '管理员可在 Telegram / QQ 使用机器人管理指令（/bind、/status、/blockword 等）。此处填写 Telegram User ID 或 QQ 号。',
    });

    const idField = field({
      label: '管理员 ID',
      placeholder: 'Telegram User ID 或 QQ 号',
      inputMode: 'numeric',
    });
    const addBtn = tapify(
      button({ text: '添加', icon: 'plus', variant: 'filled', onClick: () => addAdmin() })
    );
    idField.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addAdmin();
      }
    });
    const addRow = h(
      'div',
      { class: 'page-toolbar' },
      h('div', { class: 'page-toolbar__grow' }, idField.el),
      addBtn
    );

    const el = h('div', { hidden: true }, note, toolbar, addRow, listEl);
    return {
      el,
      listEl,
      search,
      count,
      idField,
      addBtn,
      setList(node) {
        clear(listEl);
        if (node) listEl.appendChild(node);
      },
      focusAdd() {
        idField.focus();
        idField.el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      },
    };
  }

  function adminRow(id) {
    return h(
      'div',
      { class: 'mi-row' },
      avatar({ icon: 'shield' }),
      h(
        'div',
        { class: 'mi-row__content' },
        h('div', { class: 'mi-row__title mi-row__title--strong mi-mono' }, String(id)),
        h('div', { class: 'mi-row__subtitle' }, '机器人指令管理员')
      ),
      h(
        'div',
        { class: 'mi-row__trailing' },
        trashButton(`移除管理员 ${id}`, () => removeAdmin(id))
      )
    );
  }

  function renderAdmins(view, payload) {
    const admins = payload && Array.isArray(payload.admins) ? payload.admins : [];
    const q = filters.admins;
    const filtered = q ? admins.filter((id) => String(id).includes(q)) : admins;
    view.count.textContent = q ? `${filtered.length}/${admins.length}` : `${admins.length} 位`;

    if (!admins.length) {
      view.setList(
        emptyState({
          icon: 'shield',
          title: '暂无管理员',
          desc: '添加 Telegram User ID 或 QQ 号后，该用户即可在群内使用机器人管理指令。',
          actionText: '添加管理员',
          onAction: () => view.focusAdd(),
        })
      );
      return;
    }
    if (!filtered.length) {
      view.setList(
        emptyState({
          icon: 'search',
          title: '没有匹配的管理员',
          desc: `没有找到 ID 包含「${q}」的管理员。`,
          actionText: '清空搜索',
          onAction: () => {
            filters.admins = '';
            view.search.set('');
            renderView('admins');
          },
        })
      );
      return;
    }

    view.setList(
      cardGroup({
        header: '管理员',
        children: filtered.map((id) => adminRow(id)),
        footer: '修改会立即写入 config.yaml 的 server.admin_user_ids；该接口为切换语义（已存在则移除）。',
      })
    );
  }

  async function addAdmin() {
    const view = views.admins;
    if (!view) return;
    const raw = view.idField.get().trim();
    if (!isPositiveInt(raw)) {
      view.idField.setError('请输入纯数字的用户 ID');
      view.idField.focus();
      return;
    }
    const id = Number(raw);
    const admins = (store.admins.data && store.admins.data.admins) || [];
    if (admins.includes(id)) {
      view.idField.setError('该用户已在管理员列表中');
      ctx.toast('该用户已经是管理员', { type: 'warning' });
      return;
    }
    view.idField.setError('');
    view.addBtn.setLoading(true);
    try {
      // 后端通过 query 参数接收 user_id（不是请求体）；且该接口是切换语义
      const res = await api.post('/admin/admins', undefined, { user_id: id });
      ctx.toast((res && res.message) || '管理员已添加', { type: 'success' });
      view.idField.set('');
      await loadView('admins', { force: true, quiet: true });
      view.idField.focus();
    } catch (err) {
      ctx.toastErr(err, '添加管理员失败');
    } finally {
      view.addBtn.setLoading(false);
    }
  }

  async function removeAdmin(id) {
    const ok = await ctx.confirm({
      title: '移除管理员',
      message: `确定移除管理员 ${id} 吗？移除后该用户将无法使用机器人管理指令。`,
      confirmText: '移除',
      danger: true,
    });
    if (!ok) return;
    try {
      // 同一接口：用户已在列表中时再次 POST 即取消管理员
      const res = await api.post('/admin/admins', undefined, { user_id: id });
      ctx.toast((res && res.message) || '已移除管理员', { type: 'success' });
      await loadView('admins', { force: true, quiet: true });
    } catch (err) {
      ctx.toastErr(err, '移除管理员失败');
    }
  }

  /* 供调试 / 其他页面可能的引用 */
  return { showView, loadView };
}
