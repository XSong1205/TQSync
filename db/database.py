import aiosqlite
import os
import uuid
import asyncio
from config.config_loader import config_loader
from utils.logger import logger


# 缓存未命中（区分“数据库里确实没有”与“还没查过”）
_MISS = object()

# 热路径常用的设置项，写入时同步失效缓存
_SETTING_BLOCKED_WORDS = 'blocked_words'


class _CompatConnection:
    """兼容旧调用方 `async with db._Database__get_connection() as conn` 的短连接封装。

    显式设置 busy_timeout，避免与长连接写入竞争时报 database is locked。
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = None

    async def __aenter__(self):
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute('PRAGMA busy_timeout=5000')
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        return False


class Database:
    """SQLite 访问层。

    性能要点（历史问题：每次查询都 aiosqlite.connect 建连接 + 开新线程，
    单次 4~7ms，一条消息要串行做好几次，直接吃掉几十毫秒事件循环）：
    1. 进程内复用一条长连接（WAL + synchronous=NORMAL），写提交开销从 ~5ms 降到微秒级；
    2. 绑定关系 / 系统设置 / 屏蔽词做进程内缓存，消息热路径不再落库；
    3. 读操作串行化到一把 asyncio.Lock，避免同一连接上 commit 互相踩踏。
    所有写方法都会主动失效相关缓存，WebUI 与命令修改后即时生效。
    """

    def __init__(self):
        self.db_path = config_loader.get('database.path', 'db/tqsync.db')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._conn = None
        self._lock = None

        # 进程内缓存（写方法负责失效）
        self._settings_cache: dict[str, object] = {}
        self._blocked_words_cache: list | None = None
        self._binding_tg_cache: dict[int, object] = {}
        self._binding_qq_cache: dict[int, object] = {}
        self._binding_username_cache: dict[str, object] = {}
        self._prefix_cache: dict[str, object] = {}

    # ---- 连接管理 ------------------------------------------------------
    def _get_lock(self) -> asyncio.Lock:
        """懒创建锁（Database 在模块导入期实例化，此时可能还没有事件循环）"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _connect_locked(self):
        """创建/复用长连接。调用方必须已持有锁。"""
        if self._conn is not None:
            return self._conn
        conn = await aiosqlite.connect(self.db_path)
        # WAL + NORMAL：断电/崩溃只会丢失最后一个事务，性能远高于 FULL
        await conn.execute('PRAGMA journal_mode=WAL')
        await conn.execute('PRAGMA synchronous=NORMAL')
        await conn.execute('PRAGMA busy_timeout=5000')
        await conn.execute('PRAGMA cache_size=-16000')
        await conn.commit()
        self._conn = conn
        return conn

    async def _ensure_conn(self):
        """确保长连接已建立（供 init_db 使用）"""
        async with self._get_lock():
            return await self._connect_locked()

    # ---- 内部读写助手 --------------------------------------------------
    async def _fetch_one(self, sql: str, params: tuple = ()):
        async with self._get_lock():
            conn = await self._connect_locked()
            cursor = await conn.execute(sql, params)
            try:
                return await cursor.fetchone()
            finally:
                await cursor.close()

    async def _fetch_all(self, sql: str, params: tuple = ()):
        async with self._get_lock():
            conn = await self._connect_locked()
            cursor = await conn.execute(sql, params)
            try:
                return await cursor.fetchall()
            finally:
                await cursor.close()

    async def _fetch_one_retry(self, sql: str, params: tuple = (), *, warn: str = None,
                               retries: int = 3, delay: float = 0.2):
        """带重试的单行查询（保持历史行为：失败重试后返回 None）"""
        for attempt in range(retries):
            try:
                return await self._fetch_one(sql, params)
            except Exception as e:
                if warn:
                    logger.warning(f"{warn} failed (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
        return None

    async def _write(self, sql: str, params: tuple = (), *, commit: bool = True):
        """执行写语句并提交（事务由长连接统一持有）。"""
        async with self._get_lock():
            conn = await self._connect_locked()
            cursor = await conn.execute(sql, params)
            await cursor.close()
            if commit:
                await conn.commit()

    # ---- 缓存失效 ------------------------------------------------------
    def _invalidate_bindings(self):
        self._binding_tg_cache.clear()
        self._binding_qq_cache.clear()
        self._binding_username_cache.clear()
        self._prefix_cache.clear()

    def _invalidate_setting(self, key: str):
        self._settings_cache.pop(key, None)
        if key == _SETTING_BLOCKED_WORDS:
            self._blocked_words_cache = None

    async def init_db(self):
        async with self._get_lock():
            conn = await self._connect_locked()
            await self._create_schema_locked(conn)

    async def _create_schema_locked(self, conn):
        await conn.execute('PRAGMA journal_mode=WAL;')
        await conn.execute('PRAGMA busy_timeout=5000;')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bindings (
                tg_user_id INTEGER PRIMARY KEY,
                qq_user_id INTEGER UNIQUE,
                tg_username TEXT,
                qq_nickname TEXT,
                uid TEXT,
                custom_prefix TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 尝试添加新列以兼容旧数据库
        try:
            await conn.execute('ALTER TABLE bindings ADD COLUMN uid TEXT')
            await conn.execute('ALTER TABLE bindings ADD COLUMN custom_prefix TEXT')
        except aiosqlite.OperationalError:
            pass # 列已存在

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS message_mapping (
                local_msg_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_message_id INTEGER,
                qq_message_id INTEGER,
                sender_tg_id INTEGER,
                sender_qq_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建消息映射与绑定索引加速查询和撤回检索
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_map_tg ON message_mapping(tg_message_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_map_qq ON message_mapping(qq_message_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_map_created ON message_mapping(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_bindings_qq ON bindings(qq_user_id)')

        # 验证码表：用于双向绑定验证
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS verification_codes (
                code TEXT PRIMARY KEY,
                qq_user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER DEFAULT 0
            )
        ''')

        # FFmpeg 自动下载确认状态表
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 插件数据存储表（键值对，按插件隔离）
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS plugin_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_name TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(plugin_name, key)
            )
        ''')

        # 群公告同步映射表
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS notice_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                notice_id TEXT,
                tg_message_id INTEGER,
                content_hash TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_notice_hash ON notice_mapping(content_hash)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_notice_id ON notice_mapping(notice_id)')

        await conn.commit()

    async def save_message_mapping(self, tg_message_id: int, qq_message_id: int, sender_tg_id: int = None, sender_qq_id: int = None):
        """保存双端消息 ID 映射关系"""
        for attempt in range(3):
            try:
                await self._write('''
                    INSERT INTO message_mapping (tg_message_id, qq_message_id, sender_tg_id, sender_qq_id)
                    VALUES (?, ?, ?, ?)
                ''', (tg_message_id, qq_message_id, sender_tg_id, sender_qq_id))
                return
            except Exception as e:
                logger.warning(f"DB save mapping failed (attempt {attempt+1}): {e}")
                if attempt < 2: await asyncio.sleep(0.5)

    async def get_tg_msg_id_by_qq(self, qq_message_id: int):
        """根据 QQ 消息 ID 查找 TG 消息 ID (增加重试机制)"""
        row = await self._fetch_one_retry(
            'SELECT tg_message_id FROM message_mapping WHERE qq_message_id = ?',
            (qq_message_id,), warn='DB get_tg_msg_id_by_qq', delay=0.2
        )
        result = row[0] if row else None
        if result:
            logger.debug(f"DB 映射查询成功: QQ {qq_message_id} -> TG {result}")
        else:
            logger.debug(f"DB 中未找到 QQ 消息 {qq_message_id} 的映射")
        return result

    async def get_qq_msg_id_by_tg(self, tg_message_id: int):
        """根据 TG 消息 ID 查找 QQ 消息 ID (增加重试机制)"""
        row = await self._fetch_one_retry(
            'SELECT qq_message_id FROM message_mapping WHERE tg_message_id = ?',
            (tg_message_id,), warn='DB get_qq_msg_id_by_tg', delay=0.2
        )
        return row[0] if row else None

    async def delete_mapping_by_tg(self, tg_message_id: int):
        """删除映射记录（用于撤回同步）"""
        await self._write('DELETE FROM message_mapping WHERE tg_message_id = ?', (tg_message_id,))

    async def delete_mapping_by_qq(self, qq_message_id: int):
        """根据 QQ 消息 ID 删除映射记录（用于 QQ 撤回同步）"""
        await self._write('DELETE FROM message_mapping WHERE qq_message_id = ?', (qq_message_id,))

    async def get_binding_by_tg(self, tg_user_id: int):
        cached = self._binding_tg_cache.get(tg_user_id, _MISS)
        if cached is not _MISS:
            return cached
        row = await self._fetch_one_retry(
            'SELECT * FROM bindings WHERE tg_user_id = ?', (tg_user_id,),
            warn='DB get_binding_by_tg', delay=0.5
        )
        self._binding_tg_cache[tg_user_id] = row
        return row

    async def get_binding_by_qq(self, qq_user_id: int):
        cached = self._binding_qq_cache.get(qq_user_id, _MISS)
        if cached is not _MISS:
            return cached
        row = await self._fetch_one_retry(
            'SELECT * FROM bindings WHERE qq_user_id = ?', (qq_user_id,),
            warn='DB get_binding_by_qq', delay=0.5
        )
        self._binding_qq_cache[qq_user_id] = row
        return row

    async def get_binding_by_tg_username(self, tg_username: str):
        """根据 TG 用户名查找绑定（用于 @mention 解析）"""
        if not tg_username:
            return None
        key = tg_username.lower()
        cached = self._binding_username_cache.get(key, _MISS)
        if cached is not _MISS:
            return cached
        row = await self._fetch_one(
            'SELECT * FROM bindings WHERE LOWER(tg_username) = LOWER(?)',
            (tg_username,)
        )
        self._binding_username_cache[key] = row
        return row

    async def add_binding(self, tg_user_id: int, qq_user_id: int, tg_username: str = None, qq_nickname: str = None):
        async with self._get_lock():
            conn = await self._connect_locked()
            # 检查是否已存在 UID，如果不存在则生成一个新的
            existing_uid = None
            if tg_user_id:
                cursor = await conn.execute('SELECT uid FROM bindings WHERE tg_user_id = ?', (tg_user_id,))
                try:
                    row = await cursor.fetchone()
                finally:
                    await cursor.close()
                if row: existing_uid = row[0]
            if not existing_uid and qq_user_id:
                cursor = await conn.execute('SELECT uid FROM bindings WHERE qq_user_id = ?', (qq_user_id,))
                try:
                    row = await cursor.fetchone()
                finally:
                    await cursor.close()
                if row: existing_uid = row[0]

            final_uid = existing_uid or str(uuid.uuid4())

            await conn.execute('''
                INSERT OR REPLACE INTO bindings (tg_user_id, qq_user_id, tg_username, qq_nickname, uid)
                VALUES (?, ?, ?, ?, ?)
            ''', (tg_user_id, qq_user_id, tg_username, qq_nickname, final_uid))
            await conn.commit()
        self._invalidate_bindings()

    async def update_custom_prefix(self, uid: str, prefix: str):
        """根据 UID 更新自定义前缀"""
        await self._write('UPDATE bindings SET custom_prefix = ? WHERE uid = ?', (prefix, uid))
        self._invalidate_bindings()

    async def get_custom_prefix_by_uid(self, uid: str):
        """根据 UID 获取自定义前缀"""
        if not uid:
            return None
        cached = self._prefix_cache.get(uid, _MISS)
        if cached is not _MISS:
            return cached
        row = await self._fetch_one(
            'SELECT custom_prefix FROM bindings WHERE uid = ? LIMIT 1', (uid,)
        )
        value = row[0] if row else None
        self._prefix_cache[uid] = value
        return value

    async def delete_binding(self, tg_user_id: int = None, qq_user_id: int = None):
        if tg_user_id:
            await self._write('DELETE FROM bindings WHERE tg_user_id = ?', (tg_user_id,))
        elif qq_user_id:
            await self._write('DELETE FROM bindings WHERE qq_user_id = ?', (qq_user_id,))
        self._invalidate_bindings()

    async def get_all_bindings(self):
        return await self._fetch_all('SELECT * FROM bindings')

    async def create_verification_code(self, qq_user_id: int, expire_minutes: int = 5) -> str:
        """为指定 QQ 用户生成6位验证码，返回验证码字符串"""
        import random
        import datetime

        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        now = datetime.datetime.now()
        expires_at = now + datetime.timedelta(minutes=expire_minutes)

        # 删除该用户的旧验证码（如果存在）
        await self.cleanup_user_codes(qq_user_id)

        await self._write('''
            INSERT INTO verification_codes (code, qq_user_id, expires_at)
            VALUES (?, ?, ?)
        ''', (code, qq_user_id, expires_at.isoformat()))

        return code

    async def verify_and_consume_code(self, code: str) -> dict:
        """
        验证验证码并标记为已使用
        返回: {'valid': bool, 'qq_user_id': int or None, 'reason': str}
        """
        import datetime

        async with self._get_lock():
            conn = await self._connect_locked()
            cursor = await conn.execute(
                'SELECT qq_user_id, expires_at, used FROM verification_codes WHERE code = ?',
                (code,)
            )
            try:
                row = await cursor.fetchone()
            finally:
                await cursor.close()

            if not row:
                return {'valid': False, 'qq_user_id': None, 'reason': '无效的验证码'}

            qq_user_id, expires_at_str, used = row
            expires_at = datetime.datetime.fromisoformat(expires_at_str)

            if used:
                return {'valid': False, 'qq_user_id': None, 'reason': '验证码已被使用'}

            if datetime.datetime.now() > expires_at:
                # 清理过期验证码
                await conn.execute('DELETE FROM verification_codes WHERE code = ?', (code,))
                await conn.commit()
                return {'valid': False, 'qq_user_id': None, 'reason': '验证码已过期'}

            # 标记为已使用
            await conn.execute('UPDATE verification_codes SET used = 1 WHERE code = ?', (code,))
            await conn.commit()

            return {'valid': True, 'qq_user_id': qq_user_id, 'reason': 'success'}

    async def cleanup_user_codes(self, qq_user_id: int):
        """清理指定用户的所有未使用验证码（防止重复生成）"""
        await self._write('DELETE FROM verification_codes WHERE qq_user_id = ? AND used = 0', (qq_user_id,))

    async def cleanup_expired_codes(self):
        """清理所有过期的验证码"""
        import datetime

        now = datetime.datetime.now().isoformat()
        await self._write('DELETE FROM verification_codes WHERE expires_at < ? OR used = 1', (now,))

    def _Database__get_connection(self):
        """提供内部连接方法供外部使用（状态统计等一次性查询）。

        注意：返回的是一次性短连接上下文（`async with` 退出即关闭），
        不要用它做热路径查询。
        """
        return _CompatConnection(self.db_path)

    async def close(self):
        """关闭长连接并清空缓存"""
        async with self._get_lock():
            if self._conn is not None:
                try:
                    await self._conn.commit()
                except Exception:
                    pass
                try:
                    await self._conn.close()
                except Exception as e:
                    logger.debug(f"数据库关闭异常（预期内）: {e}")
                self._conn = None
        self._settings_cache.clear()
        self._blocked_words_cache = None
        self._invalidate_bindings()

    # --- FFmpeg Auto-Download Settings ---
    async def get_setting(self, key: str, default: str = None) -> str:
        cached = self._settings_cache.get(key, _MISS)
        if cached is not _MISS:
            return cached if cached is not None else default
        row = await self._fetch_one('SELECT value FROM system_settings WHERE key = ?', (key,))
        value = row[0] if row else None
        self._settings_cache[key] = value
        return value if value is not None else default

    async def set_setting(self, key: str, value: str):
        await self._write('''
            INSERT OR REPLACE INTO system_settings (key, value)
            VALUES (?, ?)
        ''', (key, value))
        self._invalidate_setting(key)

    # --- Blocked Words (屏蔽词) ---
    async def get_blocked_words(self) -> list:
        if self._blocked_words_cache is not None:
            return self._blocked_words_cache
        data = await self.get_setting(_SETTING_BLOCKED_WORDS, '[]')
        try:
            import json
            words = json.loads(data) if data else []
            if not isinstance(words, list):
                words = []
        except Exception:
            words = []
        self._blocked_words_cache = words
        return words

    async def add_blocked_word(self, word: str) -> bool:
        word = word.strip()
        words = list(await self.get_blocked_words())
        if word in words:
            return False
        words.append(word)
        import json
        await self.set_setting(_SETTING_BLOCKED_WORDS, json.dumps(words, ensure_ascii=False))
        return True

    async def remove_blocked_word(self, word: str) -> bool:
        word = word.strip()
        words = list(await self.get_blocked_words())
        if word not in words:
            return False
        words.remove(word)
        import json
        await self.set_setting(_SETTING_BLOCKED_WORDS, json.dumps(words, ensure_ascii=False))
        return True

    async def check_blocked_word_in_text(self, text: str):
        if not text:
            return None
        words = await self.get_blocked_words()
        if not words:
            return None
        text_lower = text.lower()
        for word in words:
            if word and word.lower() in text_lower:
                return word
        return None

    # --- Synced Users (从 message_mapping 获取同步过的用户) ---
    async def get_synced_qq_users(self):
        rows = await self._fetch_all(
            'SELECT DISTINCT sender_qq_id FROM message_mapping WHERE sender_qq_id IS NOT NULL ORDER BY sender_qq_id'
        )
        return [r[0] for r in rows]

    # --- Plugin Data CRUD ---
    async def get_plugin_data(self, plugin_name: str, key: str = None):
        if key:
            row = await self._fetch_one(
                'SELECT value FROM plugin_data WHERE plugin_name = ? AND key = ?',
                (plugin_name, key)
            )
            return row[0] if row else None
        else:
            rows = await self._fetch_all(
                'SELECT key, value, updated_at FROM plugin_data WHERE plugin_name = ? ORDER BY key',
                (plugin_name,)
            )
            return [{'key': r[0], 'value': r[1], 'updated_at': r[2]} for r in rows]

    async def set_plugin_data(self, plugin_name: str, key: str, value: str):
        await self._write('''
            INSERT INTO plugin_data (plugin_name, key, value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(plugin_name, key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        ''', (plugin_name, key, value))

    async def delete_plugin_data(self, plugin_name: str, key: str = None):
        if key:
            await self._write(
                'DELETE FROM plugin_data WHERE plugin_name = ? AND key = ?',
                (plugin_name, key)
            )
        else:
            await self._write(
                'DELETE FROM plugin_data WHERE plugin_name = ?',
                (plugin_name,)
            )

    async def get_all_plugin_names(self):
        rows = await self._fetch_all('SELECT DISTINCT plugin_name FROM plugin_data ORDER BY plugin_name')
        return [r[0] for r in rows]

    # --- Notice Mapping (群公告同步映射) ---
    async def is_notice_synced(self, content_hash: str) -> bool:
        """检查公告内容哈希是否已经同步过"""
        if not content_hash:
            return False
        row = await self._fetch_one(
            'SELECT 1 FROM notice_mapping WHERE content_hash = ? LIMIT 1', (content_hash,)
        )
        return row is not None

    async def is_notice_id_synced(self, notice_id: str) -> bool:
        """检查 QQ notice_id 是否已经同步过"""
        if not notice_id:
            return False
        row = await self._fetch_one(
            'SELECT 1 FROM notice_mapping WHERE notice_id = ? LIMIT 1', (str(notice_id),)
        )
        return row is not None

    async def record_synced_notice(self, source: str, content_hash: str, notice_id: str = None, tg_message_id: int = None):
        """记录已同步的公告"""
        await self._write('''
            INSERT OR REPLACE INTO notice_mapping (source, notice_id, tg_message_id, content_hash)
            VALUES (?, ?, ?, ?)
        ''', (source, str(notice_id) if notice_id else None, tg_message_id, content_hash))

    async def get_all_synced_notice_hashes(self) -> set:
        """获取所有已同步的公告哈希"""
        rows = await self._fetch_all('SELECT content_hash FROM notice_mapping WHERE content_hash IS NOT NULL')
        return {r[0] for r in rows if r[0]}

    async def get_all_synced_notice_ids(self) -> set:
        """获取所有已同步的 QQ notice_id"""
        rows = await self._fetch_all('SELECT notice_id FROM notice_mapping WHERE notice_id IS NOT NULL')
        return {str(r[0]) for r in rows if r[0]}

    async def is_tg_msg_id_synced_notice(self, tg_message_id: int) -> bool:
        """检查指定 TG 消息 ID 是否为已同步的公告消息"""
        if not tg_message_id:
            return False
        row = await self._fetch_one(
            'SELECT 1 FROM notice_mapping WHERE tg_message_id = ? LIMIT 1', (tg_message_id,)
        )
        return row is not None


db = Database()
