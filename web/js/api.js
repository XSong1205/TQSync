/**
 * TQSync Admin API 客户端
 * ---------------------------------------------------------------
 * 零依赖，基于 fetch。所有请求同源（WebUI 由 FastAPI 静态托管）。
 * - 统一注入 X-API-Key
 * - 统一超时（AbortController）
 * - 统一错误对象 ApiError（携带 status / detail / payload）
 * - 403 时触发 onUnauthorized 回调（由 app.js 切回登录页）
 *
 * 用法：
 *   api.setToken('xxx');
 *   await api.get('/admin/status');
 *   await api.put('/admin/sync/direction', { direction: 'both' });
 */

const TOKEN_KEY = 'tqsync_api_key';
const DEFAULT_TIMEOUT = 15000;

export class ApiError extends Error {
  constructor(message, { status = 0, detail = '', payload = null, path = '' } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail || message;
    this.payload = payload;
    this.path = path;
  }
}

/** 从后端各种错误响应里提取可读文案 */
function extractDetail(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload === 'string') return payload;
  const d = payload.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    // FastAPI 校验错误：[{loc, msg, type}]
    const first = d[0];
    if (first && first.msg) {
      const loc = Array.isArray(first.loc) ? first.loc.filter((p) => p !== 'body').join('.') : '';
      return loc ? `${loc}: ${first.msg}` : first.msg;
    }
  }
  if (typeof payload.message === 'string') return payload.message;
  return fallback;
}

let unauthorizedHandler = null;
/** 注册 403/401 回调（只会保留最后一个） */
export function onUnauthorized(fn) {
  unauthorizedHandler = fn;
}

function buildQuery(params) {
  if (!params) return '';
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    usp.append(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export const api = {
  /** 当前 API Key（写入请求头） */
  _token: '',

  init() {
    try {
      this._token = localStorage.getItem(TOKEN_KEY) || '';
    } catch {
      this._token = '';
    }
    return this._token;
  },

  getToken() {
    return this._token;
  },

  hasToken() {
    return Boolean(this._token);
  },

  setToken(token) {
    this._token = String(token || '');
    try {
      if (this._token) localStorage.setItem(TOKEN_KEY, this._token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* localStorage 不可用时仅保留内存态 */
    }
  },

  clearToken() {
    this.setToken('');
  },

  /**
   * 底层请求
   * @param {string} path  例如 '/admin/status'
   * @param {object} opts  { method, body, params, timeout, raw }
   */
  async request(path, opts = {}) {
    const { method = 'GET', body, params, timeout = DEFAULT_TIMEOUT, raw = false } = opts;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    const headers = { Accept: 'application/json' };
    if (this._token) headers['X-API-Key'] = this._token;

    let payload;
    if (body instanceof FormData) {
      payload = body; // 浏览器自动设置 multipart 边界
    } else if (body !== undefined && body !== null) {
      headers['Content-Type'] = 'application/json';
      payload = JSON.stringify(body);
    }

    const url = path + buildQuery(params);
    let res;
    try {
      res = await fetch(url, { method, headers, body: payload, signal: controller.signal, cache: 'no-store' });
    } catch (err) {
      clearTimeout(timer);
      if (err && err.name === 'AbortError') {
        throw new ApiError('请求超时，请检查后端服务是否在线', { status: 0, path });
      }
      throw new ApiError('无法连接到服务端，请检查网络或后端进程', { status: 0, path });
    }
    clearTimeout(timer);

    let data = null;
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!res.ok) {
      const detail = extractDetail(data, `请求失败 (${res.status})`);
      if (res.status === 401 || res.status === 403) {
        // 仅在已持有 token 时才提示重新登录，避免登录页反复触发
        if (this._token && typeof unauthorizedHandler === 'function') {
          unauthorizedHandler();
        }
      }
      throw new ApiError(detail, { status: res.status, detail, payload: data, path });
    }

    return raw ? { data, res } : data;
  },

  get(path, params) {
    return this.request(path, { method: 'GET', params });
  },

  post(path, body, params) {
    return this.request(path, { method: 'POST', body, params });
  },

  put(path, body, params) {
    return this.request(path, { method: 'PUT', body, params });
  },

  del(path, params) {
    return this.request(path, { method: 'DELETE', params });
  },

  upload(path, formData) {
    return this.request(path, { method: 'POST', body: formData, timeout: 120000 });
  },
};

/**
 * 批量保存配置：优先走后端批量接口，失败（如旧后端 404/405）时退化为逐条 PUT。
 * @param {Array<{key:string, value:string}>} items
 * @returns {Promise<{updated:number, failed:Array<{key:string, error:string}>, fallback:boolean, message:string}>}
 */
export async function saveConfigBatch(items) {
  if (!items.length) return { updated: 0, failed: [], fallback: false, message: '' };
  try {
    const res = await api.put('/admin/config/batch', { items });
    const updated = typeof res?.updated === 'number' ? res.updated : items.length;
    const failed = Array.isArray(res?.failed) ? res.failed : [];
    const message = typeof res?.message === 'string' ? res.message : '';
    return { updated, failed, fallback: false, message };
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 405)) {
      const results = await Promise.allSettled(
        items.map((it) => api.put(`/admin/config/${encodeURIComponent(it.key)}`, { key: it.key, value: it.value }))
      );
      const failed = [];
      let updated = 0;
      results.forEach((r, idx) => {
        if (r.status === 'fulfilled') {
          updated += 1;
        } else {
          const reason = r.reason;
          const errorMsg = (reason && (reason.detail || reason.message)) || String(reason || '保存失败');
          failed.push({ key: items[idx].key, error: errorMsg });
        }
      });
      if (failed.length === items.length) throw results[0].reason;
      const message = `已更新 ${updated} 项配置` + (failed.length ? `，${failed.length} 项失败` : '');
      return { updated, failed, fallback: true, message };
    }
    throw err;
  }
}
