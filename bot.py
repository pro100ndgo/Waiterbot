import os
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================= DATABASE =================
conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    branch TEXT,
    fixed INTEGER,
    percent REAL,
    show_in_leaderboard INTEGER DEFAULT 1
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
last_bot_messages = {}

# ================= HELPERS =================
async def send_clean(msg, text, reply_markup=None):
    uid = msg.from_user.id
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except:
        pass

    sent = await msg.answer(text, reply_markup=reply_markup)

    last_bot_messages.setdefault(uid, []).append(sent.message_id)
    if len(last_bot_messages[uid]) > 2:
        old = last_bot_messages[uid].pop(0)
        try:
            await bot.delete_message(msg.chat.id, old)
        except:
            pass

# ================= MENUS =================
menu = ReplyKeyboardMarkup(resize_keyboard=True)
menu.add("📊 Bugungi hisobot", "📅 3 kunlik hisobot")
menu.add("📆 Haftalik hisobot", "🏆 TOP")
menu.add("📊 Grafik", "⚙️ Sozlamalar")

@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    cur.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    row = cur.fetchone()

    if row:
        await send_clean(
            msg,
            f"👋 Xush kelibsan, {row[0]}!",
            menu
        )
    else:
        user_state[msg.from_user.id] = "name"
        await send_clean(
            msg,
            "👤 Isming nima?"
        )

# ================= SETTINGS =================
@dp.message_handler(lambda m: m.text == "⚙️ Sozlamalar")
async def settings(msg):
    cur.execute("SELECT show_in_leaderboard FROM users WHERE user_id=?", (msg.from_user.id,))
    show = cur.fetchone()[0]

    status = "ON 👁" if show else "OFF 🙈"

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔄 Bugungi savdoni nol qilish")
    kb.add("🗑 Butun savdoni tozalash")
    kb.add("👁 Leaderboardda ko‘rinish")
    kb.add("⬅️ Ortga")

    await send_clean(
        msg,
        f"⚙️ Sozlamalar\n"
        f"👁 Leaderboard holati: {status}",
        kb
    )

# ================= TOGGLE LEADERBOARD =================
@dp.message_handler(lambda m: m.text == "👁 Leaderboardda ko‘rinish")
async def toggle_leaderboard(msg):
    cur.execute(
        "UPDATE users SET show_in_leaderboard = 1 - show_in_leaderboard WHERE user_id=?",
        (msg.from_user.id,)
    )
    conn.commit()
    await settings(msg)

# ================= RESET ALL SALES =================
@dp.message_handler(lambda m: m.text == "🗑 Butun savdoni tozalash")
async def reset_all_confirm(msg):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("❗ Ha, hammasini o‘chir", callback_data="reset_all_yes"),
        InlineKeyboardButton("❌ Yo‘q", callback_data="reset_all_no")
    )
    await send_clean(
        msg,
        "❗ BARCHA savdoni o‘chirmoqchimisiz?\nBu amalni ortga qaytarib bo‘lmaydi!",
        kb
    )

@dp.callback_query_handler(lambda c: c.data == "reset_all_yes")
async def reset_all(call):
    cur.execute("DELETE FROM sales WHERE user_id=?", (call.from_user.id,))
    conn.commit()
    await call.message.edit_text("✅ Barcha savdolar tozalandi")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "reset_all_no")
async def reset_all_no(call):
    await call.message.edit_text("❌ Bekor qilindi")
    await call.answer()

# ================= LEADERBOARD =================
@dp.message_handler(lambda m: m.text == "🏆 TOP")
async def leaderboard(msg):
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
    SELECT u.name, u.branch, SUM(s.amount)
    FROM sales s
    JOIN users u ON u.user_id = s.user_id
    WHERE s.date=? AND u.show_in_leaderboard=1
    GROUP BY s.user_id
    ORDER BY SUM(s.amount) DESC
    LIMIT 5
    """, (today,))
    rows = cur.fetchall()

    if not rows:
        await send_clean(msg, "Leaderboard bo‘sh.", menu)
        return

    text = "🏆 BUGUNGI TOP 5\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, r in enumerate(rows):
        text += f"{medals[i]} {r[0]} ({r[1]}) — {r[2]:,} UZS\n"

    await send_clean(msg, text, menu)

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
