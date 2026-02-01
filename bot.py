import os
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN")
TOP_LIMIT = 5

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================== DATABASE ==================
conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    branch TEXT,
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

cur.execute("""
CREATE TABLE IF NOT EXISTS days_off (
    user_id INTEGER,
    weekday INTEGER
)
""")
conn.commit()

user_state = {}

# ================== MENUS ==================
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
    KeyboardButton("🗓 Dam kunlari"),
    KeyboardButton("📢 Ofitsant maslahatlari")
)
menu.add(
    KeyboardButton("❤️ Botni qo‘llab-quvvatlash"),
    KeyboardButton("⚙️ Sozlamalar")
)

branches_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
branches_kb.add(
    KeyboardButton("🏢 AKSU Shedevr"),
    KeyboardButton("🏢 AKSU Chigatoy")
)

fixed_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
fixed_kb.add(
    KeyboardButton("120000"),
    KeyboardButton("150000"),
    KeyboardButton("170000")
)

percent_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
percent_kb.add(
    KeyboardButton("0.7"),
    KeyboardButton("1"),
    KeyboardButton("3"),
    KeyboardButton("5")
)

days = [
    "Dushanba", "Seshanba", "Chorshanba",
    "Payshanba", "Juma", "Shanba", "Yakshanba"
]

# ================== START ==================
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (msg.from_user.id,))
    if cur.fetchone():
        await msg.answer("👋 Xush kelibsan!", reply_markup=menu)
    else:
        user_state[msg.from_user.id] = "name"
        await msg.answer("👤 Isming nima?")

# ================== REGISTRATION ==================
@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "name")
async def reg_name(msg: types.Message):
    cur.execute("INSERT OR IGNORE INTO users(user_id, name) VALUES (?,?)",
                (msg.from_user.id, msg.text))
    conn.commit()
    user_state[msg.from_user.id] = "branch"
    await msg.answer("🏢 Filialni tanla:", reply_markup=branches_kb)

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "branch")
async def reg_branch(msg: types.Message):
    cur.execute("UPDATE users SET branch=? WHERE user_id=?",
                (msg.text, msg.from_user.id))
    conn.commit()
    user_state[msg.from_user.id] = "fixed"
    await msg.answer("💼 Kunlik fixed ish haqqingni tanla:", reply_markup=fixed_kb)

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "fixed")
async def reg_fixed(msg: types.Message):
    cur.execute("UPDATE users SET fixed=? WHERE user_id=?",
                (int(msg.text), msg.from_user.id))
    conn.commit()
    user_state[msg.from_user.id] = "percent"
    await msg.answer("📊 Savdodan necha foiz?", reply_markup=percent_kb)

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "percent")
async def reg_percent(msg: types.Message):
    percent = float(msg.text)
    cur.execute("UPDATE users SET percent=? WHERE user_id=?",
                (percent, msg.from_user.id))
    conn.commit()
    user_state.pop(msg.from_user.id)
    await msg.answer("✅ Profil saqlandi!", reply_markup=menu)

# ================== SAVE SALES ==================
@dp.message_handler(lambda m: m.text and m.text.isdigit())
async def save_sale(msg: types.Message):
    if msg.chat.type in ["group", "supergroup"]:
        cur.execute(
            "INSERT INTO sales VALUES (?,?,?,?)",
            (msg.chat.id, msg.from_user.id, int(msg.text),
             datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()

# ================== REPORT LOGIC ==================
def working_days(user_id, days_back):
    count = 0
    for i in range(days_back):
        day = datetime.now() - timedelta(days=i)
        weekday = day.weekday()
        cur.execute(
            "SELECT 1 FROM days_off WHERE user_id=? AND weekday=?",
            (user_id, weekday)
        )
        if not cur.fetchone():
            count += 1
    return count

async def send_report(msg, days_back):
    since = (datetime.now() - timedelta(days=days_back-1)).strftime("%Y-%m-%d")

    cur.execute("""
    SELECT SUM(amount) FROM sales
    WHERE user_id=? AND date>=?
    """, (msg.from_user.id, since))
    total = cur.fetchone()[0] or 0

    cur.execute("""
    SELECT name, fixed, percent FROM users WHERE user_id=?
    """, (msg.from_user.id,))
    name, fixed, percent = cur.fetchone()

    work_days = working_days(msg.from_user.id, days_back)
    fixed_sum = fixed * work_days
    bonus = int(total * (percent / 100 if percent >= 1 else percent))
    final = fixed_sum + bonus

    await msg.answer(
        f"👤 {name}\n"
        f"📅 Oxirgi {days_back} kun\n"
        f"💰 Savdo: {total:,} UZS\n"
        f"💼 Fixed: {fixed_sum:,} UZS\n"
        f"📊 Foiz: {bonus:,} UZS\n"
        f"✅ Jami: {final:,} UZS",
        reply_markup=menu
    )

# ================== REPORT BUTTONS ==================
@dp.message_handler(lambda m: m.text == "📊 Bugungi hisobot")
async def today(msg: types.Message):
    await send_report(msg, 1)

@dp.message_handler(lambda m: m.text == "📅 3 kunlik hisobot")
async def three(msg: types.Message):
    await send_report(msg, 3)

@dp.message_handler(lambda m: m.text == "📆 Haftalik hisobot")
async def week(msg: types.Message):
    await send_report(msg, 7)

# ================== DAYS OFF ==================
@dp.message_handler(lambda m: m.text == "🗓 Dam kunlari")
async def show_days(msg: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    for i, d in enumerate(days):
        cur.execute(
            "SELECT 1 FROM days_off WHERE user_id=? AND weekday=?",
            (msg.from_user.id, i)
        )
        emoji = "🔴" if cur.fetchone() else "🟢"
        kb.insert(
            InlineKeyboardButton(
                f"{emoji} {d}", callback_data=f"day_{i}"
            )
        )
    await msg.answer("🗓 Dam kunlarini belgila:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("day_"))
async def toggle_day(call: types.CallbackQuery):
    d = int(call.data.split("_")[1])
    cur.execute(
        "SELECT 1 FROM days_off WHERE user_id=? AND weekday=?",
        (call.from_user.id, d)
    )
    if cur.fetchone():
        cur.execute(
            "DELETE FROM days_off WHERE user_id=? AND weekday=?",
            (call.from_user.id, d)
        )
    else:
        cur.execute(
            "INSERT INTO days_off VALUES (?,?)",
            (call.from_user.id, d)
        )
    conn.commit()
    await call.message.delete()
    await show_days(call.message)
    await call.answer()

# ================== LEADERBOARD ==================
@dp.message_handler(lambda m: m.text == "🏆 TOP")
async def top(msg: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
    SELECT u.name, u.branch, SUM(s.amount) total
    FROM sales s
    JOIN users u ON u.user_id = s.user_id
    WHERE s.date=?
    GROUP BY s.user_id
    ORDER BY total DESC
    LIMIT ?
    """, (today, TOP_LIMIT))
    rows = cur.fetchall()

    if not rows:
        await msg.answer("Bugun hali savdo yo‘q.", reply_markup=menu)
        return

    text = "🏆 BUGUNGI TOP 5\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    for i, r in enumerate(rows):
        text += f"{medals[i]} {r[0]} ({r[1]}) — {r[2]:,} UZS\n"

    await msg.answer(text, reply_markup=menu)

# ================== INFO BUTTONS ==================
@dp.message_handler(lambda m: m.text == "📢 Ofitsant maslahatlari")
async def tips(msg: types.Message):
    await msg.answer(
        "📢 Ofitsantlar uchun foydali maslahatlar kanali\n"
        "⏳ Tez kunda ishga tushadi!",
        reply_markup=menu
    )

@dp.message_handler(lambda m: m.text == "❤️ Botni qo‘llab-quvvatlash")
async def donate(msg: types.Message):
    await msg.answer(
        "❤️ Bot foydali bo‘lsa, qo‘llab-quvvatlashing mumkin:\n\n"
        "⭐ Telegram Stars\n"
        "💳 Click / Payme\n\n"
        "Rahmat 🙏",
        reply_markup=menu
    )

@dp.message_handler(lambda m: m.text == "⚙️ Sozlamalar")
async def settings(msg: types.Message):
    await msg.answer(
        "⚙️ Sozlamalar\n"
        "/start — profilni qayta sozlash",
        reply_markup=menu
    )

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp)
