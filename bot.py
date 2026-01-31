import os
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("8508671917:AAFp0IeiX_9vkRj6Nv6bTa0_wVl-OhY6I0E")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ---------- DATABASE ----------
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

# ---------- MENU ----------
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

# ---------- START ----------
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    cur.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    user = cur.fetchone()

    if user:
        await msg.answer("👋 Xush kelibsan!", reply_markup=menu)
    else:
        user_state[msg.from_user.id] = "name"
        await msg.answer("👋 Isming nima?")

# ---------- SETUP ----------
@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "name")
async def get_name(msg: types.Message):
    cur.execute("INSERT OR IGNORE INTO users(user_id, name) VALUES (?,?)",
                (msg.from_user.id, msg.text))
    conn.commit()
    user_state[msg.from_user.id] = "fixed"
    await msg.answer("💼 Kunlik fixed ish haqqing? (faqat raqam)")

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "fixed")
async def get_fixed(msg: types.Message):
    cur.execute("UPDATE users SET fixed=? WHERE user_id=?",
                (int(msg.text), msg.from_user.id))
    conn.commit()
    user_state[msg.from_user.id] = "percent"
    await msg.answer("📊 Savdodan necha foiz? (masalan 0.7)")

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "percent")
async def get_percent(msg: types.Message):
    cur.execute("UPDATE users SET percent=? WHERE user_id=?",
                (float(msg.text), msg.from_user.id))
    conn.commit()
    user_state.pop(msg.from_user.id)
    await msg.answer("✅ Tayyor!", reply_markup=menu)

# ---------- SAVE SALES ----------
@dp.message_handler(lambda m: m.text and m.text.isdigit())
async def save_sale(msg: types.Message):
    if msg.chat.type in ["group", "supergroup"]:
        cur.execute(
            "INSERT INTO sales VALUES (?,?,?,?)",
            (msg.chat.id, msg.from_user.id, int(msg.text),
             datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()

# ---------- REPORT FUNCTION ----------
async def send_report(msg, days):
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

    await msg.answer(
        f"👤 {name}\n"
        f"📅 Oxirgi {days} kun\n"
        f"💰 Savdo: {total:,} so‘m\n"
        f"💼 Fixed: {fixed*days:,}\n"
        f"📊 Foiz: {bonus:,}\n"
        f"✅ Jami: {final:,}",
        reply_markup=menu
    )

# ---------- BUTTON HANDLERS ----------
@dp.message_handler(lambda m: m.text == "📊 Bugungi hisobot")
async def today(msg: types.Message):
    await send_report(msg, 1)

@dp.message_handler(lambda m: m.text == "📅 3 kunlik hisobot")
async def three_days(msg: types.Message):
    await send_report(msg, 3)

@dp.message_handler(lambda m: m.text == "📆 Haftalik hisobot")
async def week(msg: types.Message):
    await send_report(msg, 7)

# ---------- LEADERBOARD ----------
@dp.message_handler(lambda m: m.text == "🏆 TOP")
async def leaderboard(msg: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
    SELECT users.name, SUM(sales.amount) as total
    FROM sales
    JOIN users ON users.user_id = sales.user_id
    WHERE date=?
    GROUP BY sales.user_id
    ORDER BY total DESC
    LIMIT 5
    """, (today,))
    rows = cur.fetchall()

    if not rows:
        await msg.answer("Bugun hali savdo yo‘q.")
        return

    text = "🏆 BUGUNGI TOP OFITSANTLAR\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    for i, row in enumerate(rows):
        text += f"{medals[i]} {row[0]} — {row[1]:,} so‘m\n"

    await msg.answer(text, reply_markup=menu)

# ---------- SETTINGS ----------
@dp.message_handler(lambda m: m.text == "⚙️ Sozlamalar")
async def settings(msg: types.Message):
    await msg.answer(
        "⚙️ Sozlamalar\n"
        "/start — qayta sozlash\n"
        "(keyin o‘zgartirishlar qo‘shiladi)",
        reply_markup=menu
    )

# ---------- RUN ----------
if __name__ == "__main__":
    executor.start_polling(dp)
