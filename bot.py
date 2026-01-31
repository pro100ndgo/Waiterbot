import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = "8508671917:AAFp0IeiX_9vkRj6Nv6bTa0_wVl-OhY6I0E"

menu = ReplyKeyboardMarkup(resize_keyboard=True)
menu.add(
    KeyboardButton("📊 Bugungi hisobot"),
    KeyboardButton("📅 3 kunlik hisobot")
)
menu.add(
    KeyboardButton("📆 Haftalik hisobot"),
    KeyboardButton("🏆 TOP")
)
menu.add(
    KeyboardButton("⚙️ Sozlamalar")
)


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

@dp.message_handler(lambda m: m.text == "📊 Bugungi hisobot")
async def today_report(msg: types.Message):
    await report(msg)

@dp.message_handler(lambda m: m.text == "📅 3 kunlik hisobot")
async def three_day_report(msg: types.Message):
    msg.text = "/hisobot 3"
    await report(msg)

@dp.message_handler(lambda m: m.text == "📆 Haftalik hisobot")
async def week_report(msg: types.Message):
    msg.text = "/hisobot 7"
    await report(msg)

@dp.message_handler(lambda m: m.text == "⚙️ Sozlamalar")
async def settings(msg: types.Message):
    await msg.answer(
        "⚙️ Sozlamalar:\n"
        "/start — qayta sozlash\n"
        "Fixed yoki foizni o‘zgartirish keyin qo‘shiladi"
    )


if __name__ == "__main__":
    executor.start_polling(dp)
