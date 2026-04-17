import aiosqlite
import os
import uuid
import asyncio
from config.config_loader import config_loader
from utils.logger import logger

class Database:
    def __init__(self):
        self.db_path = config_loader.get('database.path', 'db/tqsync.db')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
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
                await db.execute('ALTER TABLE bindings ADD COLUMN uid TEXT')
                await db.execute('ALTER TABLE bindings ADD COLUMN custom_prefix TEXT')
            except aiosqlite.OperationalError:
                pass # 列已存在
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS message_mapping (
                    local_msg_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_message_id INTEGER,
                    qq_message_id INTEGER,
                    sender_tg_id INTEGER,
                    sender_qq_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 验证码表：用于双向绑定验证
            await db.execute('''
                CREATE TABLE IF NOT EXISTS verification_codes (
                    code TEXT PRIMARY KEY,
                    qq_user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    used INTEGER DEFAULT 0
                )
            ''')
            
            # FFmpeg 自动下载确认状态表
            await db.execute('''
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()

    async def save_message_mapping(self, tg_message_id: int, qq_message_id: int, sender_tg_id: int = None, sender_qq_id: int = None):
        """保存双端消息 ID 映射关系"""
        for attempt in range(3):
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('''
                        INSERT INTO message_mapping (tg_message_id, qq_message_id, sender_tg_id, sender_qq_id)
                        VALUES (?, ?, ?, ?)
                    ''', (tg_message_id, qq_message_id, sender_tg_id, sender_qq_id))
                    await db.commit()
                return
            except Exception as e:
                logger.warning(f"DB save mapping failed (attempt {attempt+1}): {e}")
                if attempt < 2: await asyncio.sleep(0.5)

    async def get_tg_msg_id_by_qq(self, qq_message_id: int):
        """根据 QQ 消息 ID 查找 TG 消息 ID (增加重试机制)"""
        for attempt in range(3):
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute('SELECT tg_message_id FROM message_mapping WHERE qq_message_id = ?', (qq_message_id,)) as cursor:
                        row = await cursor.fetchone()
                        result = row[0] if row else None
                        if result:
                            logger.debug(f"DB 映射查询成功: QQ {qq_message_id} -> TG {result}")
                        else:
                            logger.debug(f"DB 中未找到 QQ 消息 {qq_message_id} 的映射")
                        return result
            except Exception as e:
                logger.warning(f"DB get_tg_msg_id_by_qq failed (attempt {attempt+1}): {e}")
                if attempt < 2: await asyncio.sleep(0.2)
        return None

    async def get_qq_msg_id_by_tg(self, tg_message_id: int):
        """根据 TG 消息 ID 查找 QQ 消息 ID (增加重试机制)"""
        for attempt in range(3):
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute('SELECT qq_message_id FROM message_mapping WHERE tg_message_id = ?', (tg_message_id,)) as cursor:
                        row = await cursor.fetchone()
                        return row[0] if row else None
            except Exception as e:
                logger.warning(f"DB get_qq_msg_id_by_tg failed (attempt {attempt+1}): {e}")
                if attempt < 2: await asyncio.sleep(0.2)
        return None

    async def delete_mapping_by_tg(self, tg_message_id: int):
        """删除映射记录（用于撤回同步）"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM message_mapping WHERE tg_message_id = ?', (tg_message_id,))
            await db.commit()

    async def get_binding_by_tg(self, tg_user_id: int):
        for attempt in range(3):
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute('SELECT * FROM bindings WHERE tg_user_id = ?', (tg_user_id,)) as cursor:
                        return await cursor.fetchone()
            except Exception as e:
                logger.warning(f"DB get_binding_by_tg failed (attempt {attempt+1}): {e}")
                if attempt < 2: await asyncio.sleep(0.5)
        return None

    async def get_binding_by_qq(self, qq_user_id: int):
        for attempt in range(3):
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute('SELECT * FROM bindings WHERE qq_user_id = ?', (qq_user_id,)) as cursor:
                        return await cursor.fetchone()
            except Exception as e:
                logger.warning(f"DB get_binding_by_qq failed (attempt {attempt+1}): {e}")
                if attempt < 2: await asyncio.sleep(0.5)
        return None

    async def add_binding(self, tg_user_id: int, qq_user_id: int, tg_username: str = None, qq_nickname: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            # 检查是否已存在 UID，如果不存在则生成一个新的
            existing_uid = None
            if tg_user_id:
                async with db.execute('SELECT uid FROM bindings WHERE tg_user_id = ?', (tg_user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row: existing_uid = row[0]
            if not existing_uid and qq_user_id:
                async with db.execute('SELECT uid FROM bindings WHERE qq_user_id = ?', (qq_user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row: existing_uid = row[0]
            
            final_uid = existing_uid or str(uuid.uuid4())

            await db.execute('''
                INSERT OR REPLACE INTO bindings (tg_user_id, qq_user_id, tg_username, qq_nickname, uid)
                VALUES (?, ?, ?, ?, ?)
            ''', (tg_user_id, qq_user_id, tg_username, qq_nickname, final_uid))
            await db.commit()

    async def update_custom_prefix(self, uid: str, prefix: str):
        """根据 UID 更新自定义前缀"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE bindings SET custom_prefix = ? WHERE uid = ?', (prefix, uid))
            await db.commit()

    async def get_custom_prefix_by_uid(self, uid: str):
        """根据 UID 获取自定义前缀"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT custom_prefix FROM bindings WHERE uid = ? LIMIT 1', (uid,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def delete_binding(self, tg_user_id: int = None, qq_user_id: int = None):
        async with aiosqlite.connect(self.db_path) as db:
            if tg_user_id:
                await db.execute('DELETE FROM bindings WHERE tg_user_id = ?', (tg_user_id,))
            elif qq_user_id:
                await db.execute('DELETE FROM bindings WHERE qq_user_id = ?', (qq_user_id,))
            await db.commit()

    async def get_all_bindings(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT * FROM bindings') as cursor:
                return await cursor.fetchall()

    async def create_verification_code(self, qq_user_id: int, expire_minutes: int = 5) -> str:
        """为指定 QQ 用户生成6位验证码，返回验证码字符串"""
        import random
        import datetime
        
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        now = datetime.datetime.now()
        expires_at = now + datetime.timedelta(minutes=expire_minutes)
        
        # 删除该用户的旧验证码（如果存在）
        await self.cleanup_user_codes(qq_user_id)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO verification_codes (code, qq_user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (code, qq_user_id, expires_at.isoformat()))
            await db.commit()
        
        return code

    async def verify_and_consume_code(self, code: str) -> dict:
        """
        验证验证码并标记为已使用
        返回: {'valid': bool, 'qq_user_id': int or None, 'reason': str}
        """
        import datetime
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT qq_user_id, expires_at, used FROM verification_codes WHERE code = ?',
                (code,)
            ) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    return {'valid': False, 'qq_user_id': None, 'reason': '无效的验证码'}
                
                qq_user_id, expires_at_str, used = row
                expires_at = datetime.datetime.fromisoformat(expires_at_str)
                
                if used:
                    return {'valid': False, 'qq_user_id': None, 'reason': '验证码已被使用'}
                
                if datetime.datetime.now() > expires_at:
                    # 清理过期验证码
                    await db.execute('DELETE FROM verification_codes WHERE code = ?', (code,))
                    await db.commit()
                    return {'valid': False, 'qq_user_id': None, 'reason': '验证码已过期'}
                
                # 标记为已使用
                await db.execute('UPDATE verification_codes SET used = 1 WHERE code = ?', (code,))
                await db.commit()
                
                return {'valid': True, 'qq_user_id': qq_user_id, 'reason': 'success'}

    async def cleanup_user_codes(self, qq_user_id: int):
        """清理指定用户的所有未使用验证码（防止重复生成）"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM verification_codes WHERE qq_user_id = ? AND used = 0', (qq_user_id,))
            await db.commit()

    async def cleanup_expired_codes(self):
        """清理所有过期的验证码"""
        import datetime
        
        now = datetime.datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM verification_codes WHERE expires_at < ? OR used = 1', (now,))
            await db.commit()

    def _Database__get_connection(self):
        """提供内部连接方法供外部使用（用于 status 统计）"""
        return aiosqlite.connect(self.db_path)

    async def close(self):
        """关闭数据库连接池（虽然 aiosqlite 是短连接，但预留接口以备未来扩展）"""
        pass

    # --- FFmpeg Auto-Download Settings ---
    async def get_setting(self, key: str, default: str = None) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT value FROM system_settings WHERE key = ?', (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO system_settings (key, value)
                VALUES (?, ?)
            ''', (key, value))
            await db.commit()

db = Database()
