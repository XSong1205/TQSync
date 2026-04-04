import aiosqlite
import os
from config.config_loader import config_loader

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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
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
            await db.commit()

    async def save_message_mapping(self, tg_message_id: int, qq_message_id: int, sender_tg_id: int = None, sender_qq_id: int = None):
        """保存双端消息 ID 映射关系"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO message_mapping (tg_message_id, qq_message_id, sender_tg_id, sender_qq_id)
                VALUES (?, ?, ?, ?)
            ''', (tg_message_id, qq_message_id, sender_tg_id, sender_qq_id))
            await db.commit()

    async def get_qq_msg_id_by_tg(self, tg_message_id: int):
        """根据 TG 消息 ID 查找 QQ 消息 ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT qq_message_id FROM message_mapping WHERE tg_message_id = ?', (tg_message_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def get_tg_msg_id_by_qq(self, qq_message_id: int):
        """根据 QQ 消息 ID 查找 TG 消息 ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT tg_message_id FROM message_mapping WHERE qq_message_id = ?', (qq_message_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def delete_mapping_by_tg(self, tg_message_id: int):
        """删除映射记录（用于撤回同步）"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM message_mapping WHERE tg_message_id = ?', (tg_message_id,))
            await db.commit()

    async def get_binding_by_tg(self, tg_user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT * FROM bindings WHERE tg_user_id = ?', (tg_user_id,)) as cursor:
                return await cursor.fetchone()

    async def get_binding_by_qq(self, qq_user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT * FROM bindings WHERE qq_user_id = ?', (qq_user_id,)) as cursor:
                return await cursor.fetchone()

    async def add_binding(self, tg_user_id: int, qq_user_id: int, tg_username: str = None, qq_nickname: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO bindings (tg_user_id, qq_user_id, tg_username, qq_nickname)
                VALUES (?, ?, ?, ?)
            ''', (tg_user_id, qq_user_id, tg_username, qq_nickname))
            await db.commit()

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

db = Database()
