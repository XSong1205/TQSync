/**
 * 配置页（config）
 * =====================================================================
 * 数据来源：
 *   GET  /admin/config              读取全部配置项（敏感项带 masked 标记）
 *   PUT  /admin/config/batch        批量保存（经 ctx.saveConfigBatch，旧后端自动降级逐条 PUT）
 *
 * 设计要点：
 *   - 文件内置完整配置元数据（中文标题 / 说明 / 编辑器类型），未知键自动降级
 *   - 按 section 分组渲染，分组标题 + 一句话说明
 *   - 本地脏数据跟踪：修改标记、吸顶保存栏、撤销、校验后再提交
 *   - DOM 只在数据加载时构建一次；输入、开关仅就地更新状态，不重建
 */
import * as ui from '../ui.js';
import { api } from '../api.js';

const { h } = ui;

/* ─────────────────────────────────────────────────────────────────────
   分区定义（顺序即渲染顺序）
   ───────────────────────────────────────────────────────────────────── */
const SECTIONS = [
  { id: 'telegram', title: 'Telegram', desc: '机器人令牌、目标群组与代理设置' },
  { id: 'qq', title: 'QQ / NapCat', desc: 'NapCat HTTP API 与 QQ 群组连接参数' },
  { id: 'server', title: '服务端', desc: '监听地址、端口、Webhook 与管理密钥' },
  { id: 'sync', title: '同步策略', desc: '同步方向、消息类型与队列并发' },
  { id: 'database', title: '数据库', desc: 'SQLite 数据文件位置' },
  { id: 'debug', title: '调试', desc: '贴纸转换等调试选项' },
];
const SECTION_MAP = Object.fromEntries(SECTIONS.map((section) => [section.id, section]));

/* 同步方向可选值 */
const DIRECTION_CHOICES = [
  { value: 'both', label: '双向同步' },
  { value: 'tg_to_qq', label: '仅 TG → QQ' },
  { value: 'qq_to_tg', label: '仅 QQ → TG' },
];

/* 不在界面中展示的内部状态键 */
const HIDDEN_KEYS = new Set(['server.is_initial_token']);

/* 页面分页：配置项 / 消息过滤 */
const CONFIG_TABS = [
  { value: 'config', label: '配置项' },
  { value: 'filter', label: '消息过滤' },
];

/* ─────────────────────────────────────────────────────────────────────
   配置元数据：覆盖 config.yaml.example 中的全部键
   type: text | password | int | bool | select | list
   ───────────────────────────────────────────────────────────────────── */
const META = {
  /* telegram */
  'telegram.bot_token': {
    title: 'Bot Token',
    desc: 'Telegram Bot 访问令牌，从 @BotFather 获取（以掩码显示，点击眼睛可查看）',
    type: 'password',
    required: true,
    placeholder: '123456789:AAxxxx…',
  },
  'telegram.group_id': {
    title: '群组 ID',
    desc: '目标 Telegram 群组 ID，通常为负数，例如 -1001234567890',
    type: 'int',
    required: true,
    placeholder: '-1001234567890',
  },
  'telegram.proxy_url': {
    title: '代理地址',
    desc: '访问 Telegram 使用的代理，留空表示不使用代理',
    type: 'text',
    placeholder: 'http://127.0.0.1:7890',
  },

  /* qq */
  'qq.napcat_api_url': {
    title: 'NapCat API 地址',
    desc: 'NapCat 的 HTTP API 地址，需与控制台可访问的网络一致',
    type: 'text',
    required: true,
    placeholder: 'http://127.0.0.1:3000',
  },
  'qq.access_token': {
    title: 'Access Token',
    desc: 'NapCat 若配置了 Access Token 请填写，留空表示不校验（以掩码显示）',
    type: 'password',
    placeholder: '留空表示不校验',
  },
  'qq.group_id': {
    title: '群组 ID',
    desc: '目标 QQ 群组 ID',
    type: 'int',
    required: true,
    placeholder: '123456789',
  },

  /* server */
  'server.host': {
    title: '监听地址',
    desc: '管理 API 与 Webhook 的监听地址，0.0.0.0 表示监听所有网卡',
    type: 'text',
    required: true,
    placeholder: '0.0.0.0',
  },
  'server.qq_webhook_port': {
    title: 'Webhook 端口',
    desc: '接收 NapCat 事件上报的端口（1–65535）',
    type: 'int',
    required: true,
    min: 1,
    max: 65535,
    inputMode: 'numeric',
    placeholder: '8080',
  },
  'server.admin_api_port': {
    title: '管理 API 端口',
    desc: '管理 API 与 Web 控制台使用的端口（1–65535）',
    type: 'int',
    required: true,
    min: 1,
    max: 65535,
    inputMode: 'numeric',
    placeholder: '8081',
  },
  'server.webhook_path': {
    title: 'Webhook 路径',
    desc: 'QQ 事件上报路径，需与 NapCat 侧的配置保持一致',
    type: 'text',
    required: true,
    placeholder: '/webhook/qq',
  },
  'server.webhook_token': {
    title: 'Webhook 鉴权 Token',
    desc: '非空时要求 NapCat 上报携带 Authorization: Bearer <token>，留空则不校验',
    type: 'password',
    placeholder: '留空表示不校验',
  },
  'server.admin_api_key': {
    title: '管理密钥',
    desc: 'Web 控制台登录密钥（X-API-Key）。修改后需要使用新密钥重新登录',
    type: 'password',
    required: true,
    placeholder: '高强度随机字符串',
  },
  'server.admin_user_ids': {
    title: '指令管理员 ID',
    desc: '可通过机器人指令管理机器人的用户 ID 列表，支持 Telegram 与 QQ 用户 ID',
    type: 'list',
  },

  /* database */
  'database.path': {
    title: '数据库路径',
    desc: 'SQLite 数据文件路径，修改后需重启服务生效',
    type: 'text',
    required: true,
    placeholder: 'db/tqsync.db',
  },

  /* sync */
  'sync.direction': {
    title: '同步方向',
    desc: '控制消息在两个平台之间的同步方向',
    type: 'select',
    options: DIRECTION_CHOICES,
  },
  'sync.sync_notice': {
    title: '同步群公告',
    desc: '群公告变更后自动同步到对端群组',
    type: 'bool',
  },
  'sync.sync_reaction': {
    title: '同步表情回应',
    desc: 'Telegram 表情回应同步为 QQ 消息表情点赞',
    type: 'bool',
  },
  'sync.face_as_image': {
    title: '表情以图片发送',
    desc: '纯表情消息直接发送 QQ 表情原图；关闭后统一使用 [微笑] 文本',
    type: 'bool',
  },
  'sync.worker_count': {
    title: '并发工作者',
    desc: '同步任务并发数，高峰可调至 4–8（1–16）',
    type: 'int',
    required: true,
    min: 1,
    max: 16,
    stepper: true,
    inputMode: 'numeric',
  },
  'sync.queue_size': {
    title: '队列容量',
    desc: '待同步队列上限，队列满时会丢弃新任务（1–1000）',
    type: 'int',
    required: true,
    min: 1,
    max: 1000,
    stepper: true,
    step: 5,
    inputMode: 'numeric',
  },

  /* debug */
  'debug.sticker_conversion_chat_id': {
    title: '贴纸转换调试 Chat ID',
    desc: 'TGS 贴纸转换调试日志发送到的 Telegram Chat ID，留空表示不启用',
    type: 'int',
    optional: true,
    inputMode: 'numeric',
    placeholder: '留空表示不启用',
  },
};

/* ─────────────────────────────────────────────────────────────────────
   工具函数
   ───────────────────────────────────────────────────────────────────── */

function errorText(err, fallback = '加载失败') {
  if (!err) return fallback;
  if (typeof err === 'string') return err;
  return err.detail || err.message || fallback;
}

/** 未知键的降级元数据（惰性缓存，避免每次渲染重建） */
const fallbackMetaCache = new Map();

function inferType(rawValue) {
  const value = String(rawValue == null ? '' : rawValue).trim().toLowerCase();
  if (value === 'true' || value === 'false') return 'bool';
  if (/^-?\d+$/.test(value)) return 'int';
  return 'text';
}

function metaFor(key, rawValue) {
  if (META[key]) return META[key];
  if (fallbackMetaCache.has(key)) return fallbackMetaCache.get(key);
  const segment = key.includes('.') ? key.split('.').pop() : key;
  const meta = {
    title: segment || key,
    desc: `配置项 ${key}`,
    type: inferType(rawValue),
  };
  fallbackMetaCache.set(key, meta);
  return meta;
}

/** 逗号串 / 数组 → 字符串数组 */
function parseList(value) {
  if (Array.isArray(value)) {
    return Array.from(new Set(value.map((item) => String(item).trim()).filter(Boolean)));
  }
  return Array.from(
    new Set(String(value == null ? '' : value).split(',').map((item) => item.trim()).filter(Boolean))
  );
}

/** 编辑值归一化（用于脏数据比较与提交） */
function normalize(meta, raw) {
  const value = raw === null || raw === undefined ? '' : raw;
  const type = meta && meta.type;
  if (type === 'bool') {
    return String(value).trim().toLowerCase() === 'true' ? 'true' : 'false';
  }
  if (type === 'int') {
    const text = String(value).trim();
    if (!text) return '';
    return /^-?\d+$/.test(text) ? String(Number(text)) : text;
  }
  if (type === 'list') return parseList(value).join(',');
  return String(value);
}

/** 保存前校验，返回错误文案（空串表示通过） */
function validateValue(key, raw, meta) {
  const info = meta || metaFor(key, raw);
  const value = String(raw == null ? '' : raw);
  const trimmed = value.trim();

  if (info.required && !trimmed) return '不能为空';

  if (info.type === 'int') {
    if (!trimmed) return info.required ? '请输入数字' : '';
    if (!/^-?\d+$/.test(trimmed)) return '请输入整数';
    const number = Number(trimmed);
    if (!Number.isFinite(number)) return '请输入有效整数';
    if (info.min !== undefined && number < info.min) return `不能小于 ${info.min}`;
    if (info.max !== undefined && number > info.max) return `不能大于 ${info.max}`;
  }

  if (info.type === 'bool' && !/^(true|false)$/i.test(trimmed)) return '取值应为 true 或 false';

  if (info.type === 'select' && Array.isArray(info.options) && !info.options.some((o) => o.value === value)) {
    return '请选择有效选项';
  }

  if (info.type === 'list') {
    const invalid = parseList(value).find((id) => !/^-?\d+$/.test(id));
    if (invalid) return `「${invalid}」不是有效数字 ID`;
  }

  return '';
}

function labelForKey(key) {
  const meta = metaFor(key, '');
  return (meta && meta.title) || key;
}

/* ─────────────────────────────────────────────────────────────────────
   骨架屏
   ───────────────────────────────────────────────────────────────────── */

function buildSkeleton() {
  return h('div', { class: 'mi-fade-in' },
    h('div', { style: { padding: '0 var(--mi-page-x) 12px' } },
      h('div', { class: 'mi-skeleton', style: { height: '62px', borderRadius: 'var(--mi-radius-lg)' } })),
    h('div', { style: { padding: '0 var(--mi-page-x) 16px' } },
      h('div', { class: 'mi-skeleton', style: { height: '40px', borderRadius: 'var(--mi-radius-sm)' } })),
    ui.skeleton({ type: 'list', count: 4 }),
    ui.skeleton({ type: 'list', count: 4 }),
    ui.skeleton({ type: 'list', count: 3 })
  );
}

/* ─────────────────────────────────────────────────────────────────────
   页面模块
   ───────────────────────────────────────────────────────────────────── */

export default {
  id: 'config',
  label: '配置',
  icon: 'sliders',
  tab: true,
  title: '配置',
  subtitle: '修改后点击保存生效',

  async mount(root, ctx) {
    let disposed = false;
    let saving = false;
    let activeTab = 'config';
    let dataEntries = [];
    let entryByKey = new Map();
    let dataGroups = [];

    const originals = new Map();
    const draft = new Map();
    const editors = new Map();
    const itemNodes = [];
    const sectionNodes = [];

    let saveBtn = null;
    let undoBtn = null;
    let saveHint = null;
    let saveFailHint = '';
    let searchApi = null;
    let noResultsEl = null;

    ctx.onCleanup(() => {
      disposed = true;
    });

    /* ────────────────────────────────────────────────────────────────
       数据整理
       ──────────────────────────────────────────────────────────────── */

    /** 把 API 返回项 + 已知元数据合并为有序 entry 列表 */
    function buildEntries(apiItems) {
      const map = new Map();
      for (const item of apiItems) {
        if (!item || typeof item.key !== 'string' || !item.key) continue;
        if (HIDDEN_KEYS.has(item.key)) continue;
        const meta = metaFor(item.key, item.value);
        map.set(item.key, {
          key: item.key,
          meta,
          value: normalize(meta, item.value),
          masked: Boolean(item.masked),
        });
      }
      // 补齐配置文件中缺失的已知键，保证界面完整可配置
      for (const key of Object.keys(META)) {
        if (HIDDEN_KEYS.has(key) || map.has(key)) continue;
        const meta = META[key];
        map.set(key, {
          key,
          meta,
          value: normalize(meta, ''),
          masked: meta.type === 'password',
        });
      }
      // 已知键按元数据声明顺序；未知键追加到末尾
      const knownKeys = Object.keys(META).filter((key) => !HIDDEN_KEYS.has(key));
      const knownSet = new Set(knownKeys);
      const ordered = [];
      for (const key of knownKeys) {
        if (map.has(key)) ordered.push(map.get(key));
      }
      for (const [key, entry] of map) {
        if (!knownSet.has(key)) ordered.push(entry);
      }
      return ordered;
    }

    function buildGroups(entries) {
      const bySection = new Map();
      for (const entry of entries) {
        const sectionId = entry.key.includes('.') ? entry.key.split('.')[0] : 'other';
        if (!bySection.has(sectionId)) bySection.set(sectionId, []);
        bySection.get(sectionId).push(entry);
      }
      const groups = [];
      for (const section of SECTIONS) {
        const items = bySection.get(section.id);
        if (items && items.length) groups.push(Object.assign({}, section, { items }));
      }
      for (const [sectionId, items] of bySection) {
        if (SECTION_MAP[sectionId]) continue;
        groups.push({ id: sectionId, title: sectionId, desc: '其他配置项', items });
      }
      return groups;
    }

    function resetMaps() {
      originals.clear();
      draft.clear();
      for (const entry of dataEntries) {
        const value = normalize(entry.meta, entry.value);
        originals.set(entry.key, value);
        draft.set(entry.key, value);
      }
    }

    function getDirtyKeys() {
      const keys = [];
      for (const [key, value] of draft) {
        if ((originals.get(key) ?? '') !== value) keys.push(key);
      }
      return keys;
    }

    /* ────────────────────────────────────────────────────────────────
       编辑器构建（每种 type 返回统一 API）
       ──────────────────────────────────────────────────────────────── */

    function makeDirtyBadge() {
      const badge = ui.badge('未保存', 'accent');
      badge.hidden = true;
      badge.style.height = '18px';
      badge.style.padding = '0 7px';
      badge.style.fontSize = '10px';
      return badge;
    }

    function makeSupport(meta) {
      const el = h('div', { class: 'mi-field__support' }, meta.desc || '');
      return {
        el,
        setError(message) {
          el.textContent = message || meta.desc || '';
          el.classList.toggle('mi-field__support--error', Boolean(message));
        },
      };
    }

    function scrollToNode(node) {
      try {
        if (node && typeof node.scrollIntoView === 'function') {
          node.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
      } catch {
        /* 忽略滚动失败 */
      }
    }

    /** 布尔型：row + switchControl */
    function createBoolEditor(entry) {
      const badge = makeDirtyBadge();
      const switcher = ui.switchControl({
        checked: entry.value === 'true',
        ariaLabel: entry.meta.title,
        onChange: (checked) => updateDraft(entry.key, checked ? 'true' : 'false'),
      });
      const el = ui.row({
        title: entry.meta.title,
        subtitle: entry.meta.desc,
        control: h('div', { class: 'mi-hstack', style: { gap: '8px' } }, badge, switcher),
      });
      return {
        el,
        setValue(value) {
          switcher.set(String(value) === 'true');
        },
        setDirty(dirty) {
          badge.hidden = !dirty;
        },
        setError() {},
        focus() {
          scrollToNode(el);
          switcher.focus();
        },
      };
    }

    /** 文本 / 密码 / 整数：field（整数可选步进器） */
    function createInputEditor(entry) {
      const { meta } = entry;
      const isPassword = meta.type === 'password' || Boolean(entry.masked);
      const badge = makeDirtyBadge();
      const support = makeSupport(meta);

      const field = ui.field({
        value: entry.value,
        password: isPassword,
        placeholder: meta.placeholder || '',
        inputMode: meta.inputMode || (meta.type === 'int' ? 'numeric' : undefined),
        onInput: (value) => updateDraft(entry.key, value),
      });
      field.input.setAttribute('aria-label', meta.title);
      field.el.style.flex = '1 1 auto';
      field.el.style.minWidth = '0';

      let control = field.el;
      if (meta.type === 'int' && meta.stepper) {
        const step = meta.step || 1;
        const applyStep = (dir) => {
          let current = parseInt(field.get(), 10);
          if (!Number.isFinite(current)) current = meta.min !== undefined ? meta.min : 0;
          let next = current + dir * step;
          if (meta.min !== undefined) next = Math.max(meta.min, next);
          if (meta.max !== undefined) next = Math.min(meta.max, next);
          field.set(String(next));
          updateDraft(entry.key, String(next));
        };
        const stepBtn = (label, onClick) => h('button', {
          class: 'mi-btn mi-btn--tonal',
          type: 'button',
          style: {
            width: '44px',
            height: '44px',
            minWidth: '44px',
            padding: '0',
            flex: 'none',
            borderRadius: '14px',
            fontSize: '20px',
            fontWeight: '500',
            lineHeight: '1',
          },
          onClick,
        }, label);
        control = h('div', { class: 'mi-hstack', style: { gap: '8px', alignItems: 'stretch' } },
          field.el,
          h('div', { class: 'mi-hstack', style: { gap: '6px', flex: 'none', alignItems: 'center' } },
            stepBtn('−', () => applyStep(-1)),
            stepBtn('+', () => applyStep(1))
          )
        );
      }

      const titleRow = h('div', { class: 'mi-hstack', style: { gap: '8px', minWidth: '0' } },
        h('div', {
          class: 'mi-row__title',
          style: { flex: '1 1 auto', minWidth: '0', fontWeight: '500' },
        }, meta.title),
        badge
      );
      const el = h('div', {
        style: { padding: '12px 16px 13px', display: 'flex', flexDirection: 'column', gap: '7px' },
      }, titleRow, control, support.el);

      return {
        el,
        setValue(value) {
          field.set(value);
        },
        setDirty(dirty) {
          badge.hidden = !dirty;
        },
        setError(message) {
          support.setError(message);
        },
        focus() {
          scrollToNode(el);
          field.focus();
        },
      };
    }

    /** 下拉选择（sync.direction） */
    function createSelectEditor(entry) {
      const { meta } = entry;
      const badge = makeDirtyBadge();
      const support = makeSupport(meta);
      const select = ui.selectField({
        options: meta.options || [],
        value: entry.value,
        onChange: (value) => updateDraft(entry.key, value),
      });
      select.select.setAttribute('aria-label', meta.title);
      select.el.style.width = '100%';
      select.el.style.height = '44px';

      const titleRow = h('div', { class: 'mi-hstack', style: { gap: '8px', minWidth: '0' } },
        h('div', {
          class: 'mi-row__title',
          style: { flex: '1 1 auto', minWidth: '0', fontWeight: '500' },
        }, meta.title),
        badge
      );
      const el = h('div', {
        style: { padding: '12px 16px 13px', display: 'flex', flexDirection: 'column', gap: '7px' },
      }, titleRow, select.el, support.el);

      return {
        el,
        setValue(value) {
          select.set(value);
        },
        setDirty(dirty) {
          badge.hidden = !dirty;
        },
        setError(message) {
          support.setError(message);
        },
        focus() {
          scrollToNode(el);
          select.el.focus();
        },
      };
    }

    /** 列表（admin_user_ids）：chip 编辑器 */
    function createListEditor(entry) {
      const { meta } = entry;
      const badge = makeDirtyBadge();
      const support = makeSupport(meta);
      let items = parseList(entry.value);

      const chipsEl = h('div', { class: 'mi-hstack mi-wrap', style: { gap: '7px' } });
      const input = h('input', {
        class: 'mi-field__input',
        type: 'text',
        inputMode: 'numeric',
        autocomplete: 'off',
        autocapitalize: 'off',
        placeholder: '输入用户 ID 后回车添加',
        'aria-label': meta.title,
      });
      const addBtn = ui.button({
        text: '添加',
        variant: 'tonal',
        size: 'sm',
        ariaLabel: `添加 ${meta.title}`,
        onClick: () => addFromInput(),
      });
      addBtn.style.height = '44px';
      addBtn.style.borderRadius = '14px';
      addBtn.style.flex = 'none';

      const inputRow = h('div', { class: 'mi-hstack', style: { gap: '8px', alignItems: 'center' } },
        h('div', { class: 'mi-field__box', style: { flex: '1 1 auto', minWidth: '0' } }, input),
        addBtn
      );

      const emitChange = () => updateDraft(entry.key, items.join(','));

      function renderChips() {
        chipsEl.replaceChildren(...items.map((id) => ui.chip({
          text: id,
          tone: 'accent',
          removeLabel: `移除 ${meta.title} ${id}`,
          onRemove: () => {
            items = items.filter((item) => item !== id);
            renderChips();
            emitChange();
          },
        })));
      }

      function addFromInput() {
        const raw = input.value.trim();
        if (!raw) {
          input.focus();
          return;
        }
        const candidates = raw.split(/[,，\s]+/).filter(Boolean);
        for (const candidate of candidates) {
          if (!/^-?\d+$/.test(candidate)) {
            support.setError('只支持数字用户 ID');
            input.focus();
            return;
          }
          if (!items.includes(candidate)) items.push(candidate);
        }
        input.value = '';
        support.setError('');
        renderChips();
        emitChange();
      }

      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          addFromInput();
        }
      });

      const titleRow = h('div', { class: 'mi-hstack', style: { gap: '8px', minWidth: '0' } },
        h('div', {
          class: 'mi-row__title',
          style: { flex: '1 1 auto', minWidth: '0', fontWeight: '500' },
        }, meta.title),
        badge
      );
      const el = h('div', {
        style: { padding: '12px 16px 13px', display: 'flex', flexDirection: 'column', gap: '8px' },
      }, titleRow, chipsEl, inputRow, support.el);

      renderChips();

      return {
        el,
        setValue(value) {
          items = parseList(value);
          input.value = '';
          renderChips();
        },
        setDirty(dirty) {
          badge.hidden = !dirty;
        },
        setError(message) {
          support.setError(message);
        },
        focus() {
          scrollToNode(el);
          input.focus();
        },
      };
    }

    function createEditor(entry) {
      const type = entry.meta.type;
      if (type === 'bool') return createBoolEditor(entry);
      if (type === 'select') return createSelectEditor(entry);
      if (type === 'list') return createListEditor(entry);
      return createInputEditor(entry);
    }

    /* ────────────────────────────────────────────────────────────────
       脏数据 / 保存
       ──────────────────────────────────────────────────────────────── */

    function updateDraft(key, rawValue) {
      saveFailHint = '';
      const meta = metaFor(key, rawValue);
      draft.set(key, normalize(meta, rawValue));
      const editor = editors.get(key);
      if (editor) editor.setError('');
      refreshDirtyUI();
    }

    function refreshDirtyUI() {
      const dirty = new Set(getDirtyKeys());
      for (const [key, editor] of editors) editor.setDirty(dirty.has(key));

      if (saveHint) {
        if (saving) {
          saveHint.textContent = '正在保存…';
          saveHint.style.color = 'var(--mi-text-secondary)';
        } else if (saveFailHint) {
          saveHint.textContent = saveFailHint;
          saveHint.style.color = 'var(--mi-danger)';
        } else if (dirty.size) {
          saveHint.textContent = `${dirty.size} 项修改未保存`;
          saveHint.style.color = 'var(--mi-accent)';
        } else {
          saveHint.textContent = '所有修改已保存';
          saveHint.style.color = 'var(--mi-text-secondary)';
        }
      }
      if (saveBtn) {
        saveBtn.disabled = saving || dirty.size === 0;
        saveBtn.setText(saving ? '保存中…' : (dirty.size ? `保存 (${dirty.size})` : '保存'));
      }
      if (undoBtn) undoBtn.disabled = saving || dirty.size === 0;
    }

    function undoChanges() {
      saveFailHint = '';
      const dirtyKeys = getDirtyKeys();
      if (!dirtyKeys.length) return;
      for (const key of dirtyKeys) {
        const value = originals.get(key) ?? '';
        draft.set(key, value);
        const editor = editors.get(key);
        if (editor) {
          editor.setValue(value);
          editor.setError('');
        }
      }
      refreshDirtyUI();
      ui.vibrate(6);
      ctx.toast('已撤销修改', { type: 'success', duration: 1400 });
    }

    async function saveChanges() {
      if (saving) return;
      saveFailHint = '';
      const dirtyKeys = getDirtyKeys();
      if (!dirtyKeys.length) {
        refreshDirtyUI();
        return;
      }
      saving = true;
      refreshDirtyUI();

      const items = [];
      const errors = [];
      for (const key of dirtyKeys) {
        const rawValue = draft.get(key) ?? '';
        const meta = metaFor(key, rawValue);
        const message = validateValue(key, rawValue, meta);
        const editor = editors.get(key);
        if (message) {
          errors.push({ key, message, editor });
          if (editor) editor.setError(message);
        } else {
          if (editor) editor.setError('');
          items.push({ key, value: String(rawValue) });
        }
      }

      if (errors.length) {
        saving = false;
        refreshDirtyUI();
        if (errors[0].editor) errors[0].editor.focus();
        ctx.toast(`请检查「${labelForKey(errors[0].key)}」：${errors[0].message}`, { type: 'error', duration: 3200 });
        return;
      }

      if (saveBtn) saveBtn.setLoading(true);
      try {
        const res = await ctx.saveConfigBatch(items);
        if (disposed) return;

        // 兼容新返回值：若存在 failed 且有失败项
        if (res && Array.isArray(res.failed) && res.failed.length > 0) {
          const failedKeys = new Set(res.failed.map((f) => f && f.key));
          const successItems = items.filter((it) => !failedKeys.has(it.key));
          for (const item of successItems) {
            const normalized = normalize(metaFor(item.key, item.value), item.value);
            originals.set(item.key, normalized);
            draft.set(item.key, normalized);
            const entry = entryByKey.get(item.key);
            if (entry) entry.value = normalized;
          }
          const updated = typeof res.updated === 'number' ? res.updated : successItems.length;
          ctx.toast(`已保存 ${updated} 项，${res.failed.length} 项失败`, { type: 'warning' });

          const failedNames = res.failed.map((f) => labelForKey(f.key) || f.key);
          const display = failedNames.length > 3
            ? `${failedNames.slice(0, 3).join('、')} 等`
            : failedNames.join('、');
          saveFailHint = `保存失败：${display}`;

          for (const f of res.failed) {
            const editor = editors.get(f.key);
            if (editor && typeof editor.setError === 'function') {
              editor.setError(f.error || '保存失败');
            }
          }
          return;
        }

        // 全部成功（含兼容旧返回值）
        for (const item of items) {
          const normalized = normalize(metaFor(item.key, item.value), item.value);
          originals.set(item.key, normalized);
          draft.set(item.key, normalized);
          const entry = entryByKey.get(item.key);
          if (entry) entry.value = normalized;
        }
        ctx.toast(`已保存 ${items.length} 项配置`, { type: 'success' });
        saving = false;
        refreshDirtyUI();
        // 静默回读，确保界面与磁盘配置一致
        refreshFromServer({ force: false }).catch(() => {});
      } catch (err) {
        if (disposed) return;
        ctx.toastErr(err, '保存失败，请稍后重试');
      } finally {
        saving = false;
        if (saveBtn) saveBtn.setLoading(false);
        refreshDirtyUI();
      }
    }

    /* ────────────────────────────────────────────────────────────────
       渲染
       ──────────────────────────────────────────────────────────────── */

    function buildSaveBar() {
      saveHint = h('div', {
        class: 'mi-row__title',
        style: {
          fontSize: '13px',
          fontWeight: '500',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          color: 'var(--mi-text-secondary)',
        },
      }, '所有修改已保存');

      undoBtn = ui.button({
        text: '撤销',
        variant: 'text',
        size: 'sm',
        onClick: undoChanges,
      });
      undoBtn.style.flex = 'none';
      undoBtn.style.height = '44px';
      undoBtn.disabled = true;

      saveBtn = ui.button({
        text: '保存',
        variant: 'filled',
        size: 'sm',
        icon: 'check',
        onClick: saveChanges,
      });
      saveBtn.style.flex = 'none';
      saveBtn.style.height = '44px';
      saveBtn.disabled = true;

      return h('div', {
        style: {
          position: 'sticky',
          top: 'calc(var(--appbar-h) + var(--safe-top, 0px) + 6px)',
          zIndex: '30',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          margin: '0 var(--mi-page-x) 12px',
          padding: '9px 12px 9px 16px',
          background: 'var(--mi-surface-translucent)',
          backdropFilter: 'saturate(180%) blur(18px)',
          WebkitBackdropFilter: 'saturate(180%) blur(18px)',
          borderRadius: 'var(--mi-radius-lg)',
          boxShadow: 'var(--mi-shadow-2)',
        },
      },
        h('div', { class: 'mi-grow', style: { minWidth: '0' } }, saveHint),
        undoBtn,
        saveBtn
      );
    }

    function buildItem(entry, group) {
      const editor = createEditor(entry);
      editors.set(entry.key, editor);

      const searchText = [
        entry.key,
        entry.meta.title || '',
        entry.meta.desc || '',
        group.title || '',
        group.desc || '',
        group.id || '',
      ].join(' ').toLowerCase();
      editor.el.dataset.search = searchText;
      itemNodes.push(editor.el);
      return editor.el;
    }

    function buildNoResults() {
      const el = h('div', { hidden: true, style: { padding: '0 var(--mi-page-x) 14px' } },
        ui.emptyState({
          icon: 'search',
          title: '未找到匹配的配置',
          desc: '试试其他关键词，或清空搜索查看全部配置项',
          actionText: '清除搜索',
          onAction: () => {
            if (searchApi) searchApi.set('');
            applyFilter('');
          },
        })
      );
      return el;
    }

    function renderPage() {
      editors.clear();
      itemNodes.length = 0;
      sectionNodes.length = 0;

      dataGroups = buildGroups(dataEntries);

      const sectionsEl = h('div', null);
      for (const group of dataGroups) {
        const itemEls = group.items.map((entry) => buildItem(entry, group));
        const cardEl = ui.cardGroup({ children: itemEls, footer: group.desc || '' });
        const sectionEl = h('div', null,
          ui.sectionTitle(group.title),
          cardEl
        );
        sectionNodes.push({ el: sectionEl, items: itemEls });
        sectionsEl.appendChild(sectionEl);
      }

      const stickyBar = buildSaveBar();
      searchApi = ui.searchBar({
        placeholder: '搜索配置项、分区或说明…',
        onInput: (value) => applyFilter(value),
      });
      noResultsEl = buildNoResults();

      configPane.replaceChildren(
        stickyBar,
        h('div', { style: { padding: '0 var(--mi-page-x) 12px' } }, searchApi.el),
        sectionsEl,
        noResultsEl
      );

      refreshDirtyUI();
      applyFilter(searchApi.get());
    }

    function applyFilter(rawQuery) {
      const query = String(rawQuery || '').trim().toLowerCase();
      let visibleCount = 0;
      for (const node of itemNodes) {
        const match = !query || (node.dataset.search || '').includes(query);
        node.hidden = !match;
        if (match) visibleCount += 1;
      }
      for (const section of sectionNodes) {
        const anyVisible = section.items.some((item) => !item.hidden);
        section.el.hidden = !anyVisible;
      }
      if (noResultsEl) noResultsEl.hidden = !(query && visibleCount === 0);
    }

    /* ────────────────────────────────────────────────────────────────
       分页：配置项 / 消息过滤（屏蔽词）
       ──────────────────────────────────────────────────────────────── */

    const blockedState = { loaded: false, loading: false, error: '', words: [] };
    let blockedQuery = '';
    let blockedCount = null;
    let blockedListHost = null;

    const blockedSearch = ui.searchBar({
      placeholder: '搜索屏蔽词…',
      onInput: ui.debounce((value) => {
        blockedQuery = String(value || '').trim().toLowerCase();
        renderBlockedList();
      }, 160),
    });
    blockedSearch.el.style.height = '44px';

    function blockedMatches() {
      return blockedQuery
        ? blockedState.words.filter((word) => word.toLowerCase().includes(blockedQuery))
        : blockedState.words;
    }

    function renderBlockedList() {
      if (!blockedListHost) return;
      const filtered = blockedMatches();
      if (blockedCount) {
        blockedCount.textContent = blockedQuery
          ? `${filtered.length}/${blockedState.words.length}`
          : `${blockedState.words.length} 个`;
      }
      const children = [];
      if (blockedState.loading && !blockedState.loaded) {
        children.push(ui.loadingBlock('正在读取屏蔽词…'));
      } else if (blockedState.error) {
        children.push(ui.errorBlock({
          title: '屏蔽词加载失败',
          message: blockedState.error,
          onRetry: () => loadBlocked({ force: true }),
        }));
      } else if (!filtered.length) {
        children.push(h('div', { class: 'mi-row' },
          h('div', { class: 'mi-row__content' },
            h('div', { class: 'mi-row__title' }, blockedQuery ? '没有匹配的屏蔽词' : '暂无屏蔽词'),
            h('div', { class: 'mi-row__subtitle' },
              blockedQuery
                ? `没有找到包含「${blockedQuery}」的屏蔽词`
                : '添加后，消息内容命中这些词的同步会被拦截，不再转发到对端')
          )
        ));
      } else {
        for (const word of filtered) {
          children.push(ui.row({
            title: word,
            icon: 'shield',
            trailing: ui.iconButton({
              icon: 'close',
              label: `删除屏蔽词 ${word}`,
              onClick: () => removeBlockedWord(word),
            }),
          }));
        }
      }
      children.push(ui.row({
        title: '添加屏蔽词',
        icon: 'plus',
        chevron: true,
        onClick: () => openAddBlocked(),
      }));
      blockedListHost.replaceChildren(ui.cardGroup({
        header: '屏蔽词',
        children,
        footer: '同步前会逐条检查消息内容，命中后不再转发；包含 / 的屏蔽词同样可正常删除。',
      }));
    }

    function buildFilterPane() {
      blockedCount = ui.badge('—', 'neutral');
      const toolbar = h('div', { class: 'page-toolbar' },
        h('div', { class: 'page-toolbar__grow' }, blockedSearch.el),
        blockedCount
      );
      blockedListHost = h('div');
      return h('div', null, toolbar, blockedListHost);
    }

    async function loadBlocked({ force = false } = {}) {
      if (blockedState.loading) return;
      if (blockedState.loaded && !force) {
        renderBlockedList();
        return;
      }
      blockedState.loading = true;
      renderBlockedList();
      try {
        const res = await api.get('/admin/blocked_words');
        if (disposed) return;
        blockedState.words = Array.isArray(res && res.words) ? res.words.map((word) => String(word)) : [];
        blockedState.error = '';
        blockedState.loaded = true;
      } catch (err) {
        if (disposed) return;
        blockedState.error = errorText(err, '请稍后重试');
      } finally {
        blockedState.loading = false;
        if (!disposed) renderBlockedList();
      }
    }

    function openAddBlocked() {
      const wordField = ui.field({
        label: '屏蔽词',
        placeholder: '例如：加微信',
        maxLength: 200,
        autofocus: true,
        supporting: '支持包含 / 的文本，最长 200 字符',
      });
      let busy = false;
      ctx.dialog({
        title: '添加屏蔽词',
        message: '消息内容包含该词时将不会同步到对端。',
        content: wordField.el,
        actions: [
          { text: '取消', variant: 'text', value: false },
          {
            text: '添加',
            variant: 'filled',
            onClick: async () => {
              if (busy) return false;
              const word = wordField.get().trim();
              if (!word) {
                wordField.setError('屏蔽词不能为空');
                wordField.focus();
                return false;
              }
              busy = true;
              try {
                await api.post('/admin/blocked_words', { word });
                ctx.toast('已添加屏蔽词', { type: 'success' });
                await loadBlocked({ force: true });
                return true;
              } catch (err) {
                if (err && err.status === 409) {
                  wordField.setError('该屏蔽词已存在');
                  wordField.focus();
                } else {
                  ctx.toastErr(err, '添加屏蔽词失败');
                }
                return false;
              } finally {
                busy = false;
              }
            },
          },
        ],
      });
    }

    async function removeBlockedWord(word) {
      const confirmed = await ctx.confirm({
        title: '删除屏蔽词',
        message: `确定删除「${word}」吗？删除后命中该词的消息会恢复同步。`,
        confirmText: '删除',
        danger: true,
      });
      if (!confirmed || disposed) return;
      try {
        await api.del(`/admin/blocked_words/${encodeURIComponent(word)}`);
        ctx.toast('已删除屏蔽词', { type: 'success' });
        await loadBlocked({ force: true });
      } catch (err) {
        ctx.toastErr(err, '删除屏蔽词失败');
      }
    }

    /* 分页骨架：切换页签时隐藏另一页，保存栏只属于「配置项」 */
    const tabSeg = ui.segmented({
      options: CONFIG_TABS,
      value: activeTab,
      onChange: (value) => switchTab(value),
    });
    tabSeg.style.width = '100%';
    const tabWrap = h('div', { class: 'page-toolbar', style: { paddingTop: '2px' } }, tabSeg);
    const configPane = h('div');
    const filterPane = h('div', { hidden: true }, buildFilterPane());
    root.replaceChildren(tabWrap, configPane, filterPane);

    function switchTab(value) {
      if (value === activeTab) return;
      activeTab = value;
      tabSeg.set(value);
      configPane.hidden = value !== 'config';
      filterPane.hidden = value !== 'filter';
      ctx.setHero({
        subtitle: value === 'config' ? '修改后点击保存生效' : '命中屏蔽词的消息不再转发',
      });
      if (value === 'filter' && !blockedState.loaded) loadBlocked();
      ui.vibrate(6);
    }

    /* ────────────────────────────────────────────────────────────────
       加载 / 刷新
       ──────────────────────────────────────────────────────────────── */

    async function loadConfig() {
      configPane.setAttribute('aria-busy', 'true');
      configPane.replaceChildren(buildSkeleton());
      try {
        const data = await api.get('/admin/config');
        if (disposed) return;
        dataEntries = buildEntries(data && Array.isArray(data.config) ? data.config : []);
        entryByKey = new Map(dataEntries.map((entry) => [entry.key, entry]));
        resetMaps();
        renderPage();
      } catch (err) {
        if (disposed) return;
        configPane.replaceChildren(ui.errorBlock({
          title: '配置加载失败',
          message: errorText(err, '无法读取配置，请检查后端服务'),
          onRetry: () => loadConfig(),
        }));
      } finally {
        configPane.removeAttribute('aria-busy');
      }
    }

    /** 静默回读：不改结构，只在键集合不变时就地更新；force=true 丢弃本地修改 */
    async function refreshFromServer({ force = false } = {}) {
      const data = await api.get('/admin/config');
      if (disposed) return;
      const incoming = buildEntries(data && Array.isArray(data.config) ? data.config : []);
      const sameKeyset = incoming.length === dataEntries.length
        && incoming.every((entry, index) => entry.key === dataEntries[index].key);

      if (!sameKeyset) {
        dataEntries = incoming;
        entryByKey = new Map(dataEntries.map((entry) => [entry.key, entry]));
        resetMaps();
        renderPage();
        return;
      }

      for (const entry of incoming) {
        const current = entryByKey.get(entry.key);
        if (!current) continue;
        const value = normalize(entry.meta, entry.value);
        current.value = value;
        current.masked = entry.masked;
        const dirty = force ? false : (draft.get(entry.key) ?? '') !== (originals.get(entry.key) ?? '');
        if (dirty) continue;
        originals.set(entry.key, value);
        draft.set(entry.key, value);
        const editor = editors.get(entry.key);
        if (editor) {
          editor.setValue(value);
          editor.setError('');
        }
      }
      refreshDirtyUI();
    }

    async function handleRefresh() {
      const dirtyKeys = getDirtyKeys();
      if (dirtyKeys.length) {
        const confirmed = await ctx.confirm({
          title: '放弃未保存的修改？',
          message: `当前有 ${dirtyKeys.length} 项修改尚未保存，刷新将丢弃这些修改。`,
          confirmText: '放弃并刷新',
          cancelText: '继续编辑',
          danger: true,
        });
        if (!confirmed || disposed) return;
        await refreshFromServer({ force: true });
        return;
      }
      await refreshFromServer({ force: true });
    }

    /* ────────────────────────────────────────────────────────────────
       启动
       ──────────────────────────────────────────────────────────────── */
    /* 下拉刷新 / 顶栏刷新：按当前页签刷新对应数据 */
    ctx.onRefresh(async () => {
      if (activeTab === 'filter') {
        await loadBlocked({ force: true });
        return;
      }
      await handleRefresh();
    });
    await loadConfig();
  },
};
