
import aiosqlite

DB = "db.sqlite"

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute('''
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            gender TEXT,
            city TEXT,
            about TEXT,
            min_age INTEGER,
            max_age INTEGER,
            city_filter TEXT,
            vip INTEGER DEFAULT 0
        )''')
        await db.execute('''
        CREATE TABLE IF NOT EXISTS queue(user_id INTEGER UNIQUE)''')
        await db.execute('''
        CREATE TABLE IF NOT EXISTS dialogs(u1 INTEGER, u2 INTEGER)''')
        await db.execute('''
        CREATE TABLE IF NOT EXISTS complaints(from_id INTEGER,to_id INTEGER,reason TEXT)''')
        await db.commit()
