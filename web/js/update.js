/**
 * 在线更新提示
 * =====================================================================
 * 打开 WebUI 后静默检查一次（GET /admin/update/check），发现新版本时
 * 用 Miuix 对话框展示更新日志；同一次会话只提示一次，用户可选择
 * 「忽略此版本」（记住远端 commit，下次不再自动打扰）。
 *
 * 手动检查入口：概览页「快捷操作 → 检查更新」、设置页「关于 → 检查更新」。
 */
import { api } from './api.js';
import * as ui from './ui.js';

/** 忽略提示的远端 commit（localStorage） */
const IGNORE_KEY = 'tqsync_update_ignored_commit';
/** 兜底仓库地址（后端未返回 repo_url 时使用） */
const FALLBACK_REPO = 'https://github.com/XSong1205/TQSync';

/** 本次会话是否已经提示过，避免重复弹窗 */
let promptedThisSession = false;
/** 正在检查时复用同一个 Promise，避免并发请求 */
let inflight = null;
/** 对话框被占用时的延迟提示计时器 */
let autoPromptTimer = null;

function readIgnored() {
  try {
    return localStorage.getItem(IGNORE_KEY) || '';
  } catch {
    return '';
  }
}

function writeIgnored(commit) {
  try {
    if (commit) localStorage.setItem(IGNORE_KEY, commit);
    else localStorage.removeItem(IGNORE_KEY);
  } catch { /* 隐私模式忽略 */ }
}

/** 拉取更新信息（force=true 跳过后端缓存） */
export function fetchUpdateInfo({ force = false } = {}) {
  if (inflight) return inflight;
  inflight = api
    .request('/admin/update/check', {
      method: 'GET',
      params: force ? { force: 'true' } : undefined,
      timeout: 35000,
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/** 更新日志列表（对话框内容） */
function buildChangelog(info) {
  const wrap = h_div('update-changelog');
  const items = Array.isArray(info.changelog) ? info.changelog : [];
  if (!items.length) {
    wrap.appendChild(h_div('update-note', info.result || '远程仓库存在新的提交，但未获取到提交说明。'));
    return wrap;
  }
  const list = document.createElement('div');
  list.className = 'update-list';
  for (const item of items) {
    const row = document.createElement('div');
    row.className = 'update-item';
    if (item.commit) {
      const commit = document.createElement('span');
      commit.className = 'update-item__commit mi-mono';
      commit.textContent = item.commit;
      row.appendChild(commit);
    }
    const subject = document.createElement('span');
    subject.className = 'update-item__subject';
    subject.textContent = item.subject || '';
    row.appendChild(subject);
    list.appendChild(row);
  }
  wrap.appendChild(list);
  return wrap;
}

function h_div(className, text) {
  const el = document.createElement('div');
  el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

/** 打开「发现新版本」对话框 */
export function showUpdateDialog(info, { auto = false } = {}) {
  const local = info.local_commit || '当前版本';
  const remote = info.remote_commit || '最新版本';
  const branch = info.branch ? ` · 分支 ${info.branch}` : '';
  const repoUrl = info.repo_url || FALLBACK_REPO;
  const compareUrl = info.compare_url || `${repoUrl}/commits`;
  const count = Array.isArray(info.changelog) ? info.changelog.length : 0;

  const content = buildChangelog(info);
  const meta = document.createElement('div');
  meta.className = 'update-meta';
  meta.textContent = `${local} → ${remote}${branch}${count ? ` · ${count} 个新提交` : ''}`;
  content.prepend(meta);

  const actions = auto
    ? [
        { text: '忽略此版本', variant: 'text', value: 'ignore' },
        { text: '查看变更', variant: 'filled', value: 'open' },
      ]
    : [
        { text: '稍后提醒', variant: 'text', value: false },
        { text: '查看变更', variant: 'filled', value: 'open' },
      ];

  const d = ui.dialog({
    title: '发现新版本',
    message: '检测到远程仓库有新的提交，更新后重启即可生效。',
    content,
    actions,
  });

  d.result.then((value) => {
    if (value === 'ignore') {
      writeIgnored(info.remote_commit || '');
      ui.toast('已忽略此版本，下次有新版本时会再次提醒', { type: 'default', duration: 2600 });
    } else if (value === 'open') {
      window.open(compareUrl, '_blank', 'noopener,noreferrer');
      if (auto) writeIgnored(info.remote_commit || '');
    }
  });

  return d;
}

/**
 * 检查更新。
 * @param {{force?:boolean, interactive?:boolean}} opts
 *   interactive=true 时用于手动检查：无论是否有忽略记录都会弹窗/提示结果。
 * @returns {Promise<object|null>} 更新信息，失败返回 null
 */
export async function checkForUpdate({ force = false, interactive = false } = {}) {
  let info = null;
  try {
    info = await fetchUpdateInfo({ force });
  } catch (err) {
    if (interactive) {
      ui.toastErr(err, '检查更新失败，请检查网络后重试');
    }
    return null;
  }
  if (!info) return null;

  if (info.reason === 'container') {
    if (interactive) {
      ui.dialog({
        title: '容器部署',
        message: info.result || '容器环境请通过 docker compose pull 更新镜像。',
        actions: [{ text: '知道了', variant: 'filled', value: true }],
      });
    }
    return info;
  }

  if (!info.available) {
    if (interactive) {
      const version = shortVersion(info.current_version) || '当前版本';
      ui.toast(`已是最新版本${version ? `（${version}）` : ''}`, { type: 'success', duration: 2200 });
    }
    return info;
  }

  const ignored = readIgnored();
  if (info.remote_commit && ignored === info.remote_commit) {
    // 用户已忽略该版本：手动检查时仍给出轻提示，自动检查保持静默
    if (interactive) {
      ui.toast('该版本已被忽略，可在下方查看变更', { type: 'default', duration: 2000 });
      showUpdateDialog(info, { auto: false });
    }
    return info;
  }

  if (interactive) {
    showUpdateDialog(info, { auto: false });
    promptedThisSession = true;
  } else if (!promptedThisSession) {
    scheduleAutoPrompt(info);
  }
  return info;
}

/** 页面已有对话框/面板时先等待，避免弹窗叠加 */
function overlayBusy() {
  return Boolean(document.querySelector('.mi-dialog, .mi-sheet'));
}

function scheduleAutoPrompt(info, attempt = 0) {
  if (promptedThisSession) return;
  const ignored = readIgnored();
  if (!info.remote_commit || ignored === info.remote_commit) return;
  if (overlayBusy()) {
    if (attempt >= 4) return; // 用户一直在操作其它弹窗，本次会话不再打扰
    clearTimeout(autoPromptTimer);
    autoPromptTimer = setTimeout(() => scheduleAutoPrompt(info, attempt + 1), 1600);
    return;
  }
  promptedThisSession = true;
  showUpdateDialog(info, { auto: true });
}

function shortVersion(value) {
  const m = String(value || '').match(/v?(\d+\.\d+(?:\.\d+)?)/);
  return m ? `v${m[1]}` : '';
}

/**
 * WebUI 启动后静默检查（延迟执行，失败不打扰用户）。
 * @param {{delay?:number}} opts
 */
export function initUpdateCheck({ delay = 2600 } = {}) {
  if (!api.hasToken()) return;
  const run = () => {
    checkForUpdate({ force: false, interactive: false }).catch(() => {});
  };
  const timer = setTimeout(run, delay);
  // 页面隐藏时若计时器未触发，延后执行即可，无需额外处理
  return () => clearTimeout(timer);
}
