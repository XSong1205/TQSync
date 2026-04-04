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
