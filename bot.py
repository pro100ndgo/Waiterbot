import os
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
)

# ================= CONFIG =================
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

# ================= MEMORY =================
user_step = {}          # registration steps
bot_messages = {}       # last 2 bot messages

# ================= HELPERS =================
async def send_clean(msg, text, reply_markup=None):
    uid = msg.from_user.id

    # user xabarini o‘chirish
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except:
        pass

    sent = await msg.answer(text, reply_markup=reply_markup)

    bot_messages.setdefault(uid, []).append(sent.message_id)
    if len(bot_messages[uid]) > 2:
        old = bot_messages[uid].pop(0)
        try:
            await bot.delete_message(msg.chat.id, old)
        except:
            pass

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📊 Bugungi hisobot", "📅 3 kunlik hisobot")
    kb.add("📆 Haftalik hisobot", "🏆 TOP")
    kb.add("📊 Grafik", "⚙️ Sozlamalar")
    return kb

def branch_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("🏢 AKSU Shedevr", "🏢 AKSU Chigatoy")
    return kb

def fixed_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("120000", "150000", "170000")
    return kb

def percent_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("0.7", "1", "3", "5")
    return kb

def build_graph_kb(user_id):
    days = ["Dushanba", "Seshanba", "Chorshanba",
            "Payshanba", "Juma", "Shanba", "Yakshanba"]
    kb = InlineKeyboardMarkup(row_width=2)

    for i, d in enumerate(days):
        cur.execute(
            "SELECT 1 FROM days_off WHERE user_id=? AND weekday=?",
            (user_id, i)
        )
        emoji = "🔴" if cur.fetchone() else "🟢"
        kb.insert(
            InlineKeyboardButton(f"{emoji} {d}", callback_data=f"day_{i}")
        )

    kb.add(InlineKeyboardButton("⬅️ Ortga", callback_data="graph_back"))
    return kb

# ================= START =================
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    cur.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    row = cur.fetchone()

    if row:
        await send_clean(
            msg,
            f"👋 Xush kelibsan, {row[0]}!",
            main_menu()
        )
    else:
        user_step[msg.from_user.id] = "name"
        await send_clean(msg, "👤 Isming nima?")

# ================= REGISTRATION =================
@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "name")
async def step_name(msg):
    cur.execute(
        "INSERT OR IGNORE INTO users(user_id, name) VALUES (?,?)",
        (msg.from_user.id, msg.text)
    )
    conn.commit()
    user_step[msg.from_user.id] = "branch"
    await send_clean(msg, "🏢 Filialni tanla:", branch_kb())

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "branch")
async def step_branch(msg):
    cur.execute(
        "UPDATE users SET branch=? WHERE user_id=?",
        (msg.text, msg.from_user.id)
    )
    conn.commit()
    user_step[msg.from_user.id] = "fixed"
    await send_clean(msg, "💼 Fixed ish haqqini tanla:", fixed_kb())

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "fixed")
async def step_fixed(msg):
    cur.execute(
        "UPDATE users SET fixed=? WHERE user_id=?",
        (int(msg.text), msg.from_user.id)
    )
    conn.commit()
    user_step[msg.from_user.id] = "percent"
    await send_clean(msg, "📊 Foizni tanla:", percent_kb())

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "percent")
async def step_percent(msg):
    percent_map = {"0.7": 0.007, "1": 0.01, "3": 0.03, "5": 0.05}
    cur.execute(
        "UPDATE users SET percent=? WHERE user_id=?",
        (percent_map[msg.text], msg.from_user.id)
    )
    conn.commit()
    user_step.pop(msg.from_user.id)
    await send_clean(msg, "✅ Profil saqlandi!", main_menu())

# ================= GROUP SALES =================
@dp.message_handler(lambda m: m.text.isdigit())
async def save_sale(msg):
    if msg.chat.type in ["group", "supergroup"]:
        cur.execute(
            "INSERT INTO sales VALUES (?,?,?,?)",
            (msg.chat.id, msg.from_user.id, int(msg.text),
             datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()

# ================= REPORTS =================
def working_days(uid, days_back):
    c = 0
    for i in range(days_back):
        d = datetime.now() - timedelta(days=i)
        cur.execute(
            "SELECT 1 FROM days_off WHERE user_id=? AND weekday=?",
            (uid, d.weekday())
        )
        if not cur.fetchone():
            c += 1
    return c

async def report(msg, days_back):
    since = (datetime.now() - timedelta(days=days_back-1)).strftime("%Y-%m-%d")
    cur.execute(
        "SELECT SUM(amount) FROM sales WHERE user_id=? AND date>=?",
        (msg.from_user.id, since)
    )
    total = cur.fetchone()[0] or 0

    cur.execute(
        "SELECT name, fixed, percent FROM users WHERE user_id=?",
        (msg.from_user.id,)
    )
    name, fixed, percent = cur.fetchone()

    fixed_sum = fixed * working_days(msg.from_user.id, days_back)
    bonus = int(total * percent)
    jami = fixed_sum + bonus

    await send_clean(
        msg,
        f"👤 {name}\n"
        f"💰 Savdo: {total:,} UZS\n"
        f"💼 Fixed: {fixed_sum:,} UZS\n"
        f"📊 Foiz: {bonus:,} UZS\n"
        f"✅ Jami: {jami:,} UZS",
        main_menu()
    )

@dp.message_handler(lambda m: m.text == "📊 Bugungi hisobot")
async def r1(msg): await report(msg, 1)

@dp.message_handler(lambda m: m.text == "📅 3 kunlik hisobot")
async def r3(msg): await report(msg, 3)

@dp.message_handler(lambda m: m.text == "📆 Haftalik hisobot")
async def r7(msg): await report(msg, 7)

# ================= GRAPH =================
@dp.message_handler(lambda m: m.text == "📊 Grafik")
async def graph(msg):
    await send_clean(
        msg,
        "📊 Ish / Dam kunlarini belgila:",
        build_graph_kb(msg.from_user.id)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("day_"))
async def toggle_day(c):
    d = int(c.data.split("_")[1])
    cur.execute(
        "SELECT 1 FROM days_off WHERE user_id=? AND weekday=?",
        (c.from_user.id, d)
    )
    if cur.fetchone():
        cur.execute(
            "DELETE FROM days_off WHERE user_id=? AND weekday=?",
            (c.from_user.id, d)
        )
    else:
        cur.execute(
            "INSERT INTO days_off VALUES (?,?)",
            (c.from_user.id, d)
        )
    conn.commit()

    await c.message.edit_reply_markup(
        reply_markup=build_graph_kb(c.from_user.id)
    )
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "graph_back")
async def graph_back(c):
    await c.message.edit_text("⬅️ Menyu", reply_markup=main_menu())
    await c.answer()

# ================= LEADERBOARD =================
@dp.message_handler(lambda m: m.text == "🏆 TOP")
async def top(msg):
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
    SELECT u.name, u.branch, SUM(s.amount)
    FROM sales s
    JOIN users u ON u.user_id=s.user_id
    WHERE s.date=? AND u.show_in_leaderboard=1
    GROUP BY s.user_id
    ORDER BY SUM(s.amount) DESC
    LIMIT 5
    """, (today,))
    rows = cur.fetchall()

    if not rows:
        await send_clean(msg, "Leaderboard bo‘sh.", main_menu())
        return

    medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    text = "🏆 TOP 5\n\n"
    for i,r in enumerate(rows):
        text += f"{medals[i]} {r[0]} ({r[1]}) — {r[2]:,} UZS\n"

    await send_clean(msg, text, main_menu())

# ================= SETTINGS =================
@dp.message_handler(lambda m: m.text == "⚙️ Sozlamalar")
async def settings(msg):
    cur.execute(
        "SELECT show_in_leaderboard FROM users WHERE user_id=?",
        (msg.from_user.id,)
    )
    show = cur.fetchone()[0]
    status = "ON 👁" if show else "OFF 🙈"

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👁 Leaderboardni yoq/o‘chir")
    kb.add("🗑 Barcha savdoni tozalash")
    kb.add("⬅️ Ortga")

    await send_clean(
        msg,
        f"⚙️ Sozlamalar\n"
        f"Leaderboard: {status}",
        kb
    )

@dp.message_handler(lambda m: m.text == "👁 Leaderboardni yoq/o‘chir")
async def toggle_lb(msg):
    cur.execute(
        "UPDATE users SET show_in_leaderboard=1-show_in_leaderboard WHERE user_id=?",
        (msg.from_user.id,)
    )
    conn.commit()
    await settings(msg)

@dp.message_handler(lambda m: m.text == "🗑 Barcha savdoni tozalash")
async def reset_all(msg):
    cur.execute("DELETE FROM sales WHERE user_id=?", (msg.from_user.id,))
    conn.commit()
    await send_clean(msg, "✅ Barcha savdolar tozalandi.", main_menu())

@dp.message_handler(lambda m: m.text == "⬅️ Ortga")
async def back(msg):
    await send_clean(msg, "⬅️ Menyu", main_menu())

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
