import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types

TOKEN = "8508671917:AAFp0IeiX_9vkRj6Nv6bTa0_wVl-OhY6I0E"

bot = Bot(TOKEN)
dp = Dispatcher(bot)

conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    fixed INTEGER,
    percent REAL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS sales (
    group_id INTEGER,
    user_id INTEGER,
    amount INTEGER,
    date TEXT
)
""")
conn.commit()

user_state = {}

@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    user_state[msg.from_user.id] = "name"
    await msg.answer("👋 Isming nima?")

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "name")
async def get_name(msg: types.Message):
    user_state[msg.from_user.id] = "fixed"
    cur.execute("INSERT OR IGNORE INTO users(user_id, name) VALUES (?,?)",
                (msg.from_user.id, msg.text))
    conn.commit()
    await msg.answer("💼 Kunlik fixed ish haqqing? (masalan 170000)")

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "fixed")
async def get_fixed(msg: types.Message):
    user_state[msg.from_user.id] = "percent"
    cur.execute("UPDATE users SET fixed=? WHERE user_id=?",
                (int(msg.text), msg.from_user.id))
    conn.commit()
    await msg.answer("📊 Savdodan necha foiz olasan? (masalan 0.7)")

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "percent")
async def get_percent(msg: types.Message):
    cur.execute("UPDATE users SET percent=? WHERE user_id=?",
                (float(msg.text), msg.from_user.id))
    conn.commit()
    user_state.pop(msg.from_user.id)
    await msg.answer("✅ Tayyor! Endi guruhda faqat summalarni yozaver.")

@dp.message_handler(lambda m: m.text and m.text.isdigit())
async def save_sale(msg: types.Message):
    if msg.chat.type in ["group", "supergroup"]:
        cur.execute(
            "INSERT INTO sales VALUES (?,?,?,?)",
            (msg.chat.id, msg.from_user.id, int(msg.text),
             datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()

@dp.message_handler(commands=["hisobot"])
async def report(msg: types.Message):
    days = 1
    if len(msg.text.split()) > 1:
        days = int(msg.text.split()[1])

    since = (datetime.now() - timedelta(days=days-1)).strftime("%Y-%m-%d")

    cur.execute("""
    SELECT SUM(amount) FROM sales
    WHERE user_id=? AND date>=?
    """, (msg.from_user.id, since))
    total = cur.fetchone()[0] or 0

    cur.execute("SELECT fixed, percent, name FROM users WHERE user_id=?",
                (msg.from_user.id,))
    fixed, percent, name = cur.fetchone()

    bonus = int(total * (percent / 100 if percent > 1 else percent))
    final = fixed * days + bonus

    await msg.reply(
        f"👤 {name}\n"
        f"📅 Oxirgi {days} kun\n"
        f"💰 Savdo: {total:,} so‘m\n"
        f"💼 Fixed: {fixed*days:,}\n"
        f"📊 Foiz: {bonus:,}\n"
        f"✅ Jami: {final:,}"
    )

if __name__ == "__main__":
    executor.start_polling(dp)