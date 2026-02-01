import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
MIN_AMOUNT = 10000
TZ = timezone(timedelta(hours=5))  # Toshkent vaqti

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================= DATABASE =================
conn = sqlite3.connect("data.db", check_same_thread=False)
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
    chat_id INTEGER,
    user_id INTEGER,
    amount INTEGER,
    date TEXT,
    work_week TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS workdays (
    user_id INTEGER,
    day INTEGER,
    is_work INTEGER,
    PRIMARY KEY (user_id, day)
)
""")
conn.commit()

# ================= MEMORY =================
user_step = {}
last_bot_msg = {}

# ================= HELPERS =================
def clean_unicode(text: str) -> str:
    # Ustiga chizish va boshqa combining belgilarni O‘CHIRADI
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

async def send_clean(msg, text, kb=None):
    uid = msg.from_user.id
    try:
        if uid in last_bot_msg:
            await bot.delete_message(msg.chat.id, last_bot_msg[uid])
    except:
        pass

    sent = await msg.answer(text, reply_markup=kb)
    last_bot_msg[uid] = sent.message_id

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📊 Bugungi hisobot", "📆 Haftalik hisobot")
    kb.add("📊 Grafik", "⚙️ Sozlamalar")
    return kb

# ================= WORK WEEK =================
def get_work_week(dt):
    if dt.weekday() == 4 and (dt.hour > 23 or (dt.hour == 23 and dt.minute >= 30)):
        dt += timedelta(days=1)

    days_from_saturday = (dt.weekday() - 5) % 7
    start = dt - timedelta(days=days_from_saturday)
    year, week, _ = start.isocalendar()
    return f"{year}-W{week:02d}"

# ================= START =================
@dp.message_handler(commands=["start"])
async def start(msg):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("▶️ Davom etish")

    await send_clean(
        msg,
        "ℹ️ Ofitsiantlar ish haqqini hisoblash boti\n\n"
        "• Chekdan faqat YAKUNIY summa olinadi\n"
        "• Ustiga chizilgan narxlar hisoblanmaydi\n"
        "• Ish haftasi: Shanba → Juma 23:30\n\n"
        "by @Shakhzod_2105",
        kb
    )

@dp.message_handler(lambda m: m.text == "▶️ Davom etish")
async def cont(msg):
    cur.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    if cur.fetchone():
        await send_clean(msg, "🏠 Menyu", main_menu())
    else:
        user_step[msg.from_user.id] = "name"
        await send_clean(msg, "👤 Isming nima?")

# ================= REG =================
@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "name")
async def reg_name(msg):
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, name) VALUES (?,?)",
        (msg.from_user.id, msg.text)
    )
    conn.commit()
    user_step[msg.from_user.id] = "fixed"
    await send_clean(msg, "💼 Kunlik ish haqqi (masalan: 170000)")

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "fixed")
async def reg_fixed(msg):
    cur.execute(
        "UPDATE users SET fixed=? WHERE user_id=?",
        (int(msg.text), msg.from_user.id)
    )
    conn.commit()
    user_step[msg.from_user.id] = "percent"
    await send_clean(msg, "📊 Foiz (masalan: 0.7)")

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "percent")
async def reg_percent(msg):
    cur.execute(
        "UPDATE users SET percent=? WHERE user_id=?",
        (float(msg.text) / 100, msg.from_user.id)
    )
    conn.commit()
    user_step.pop(msg.from_user.id)
    await send_clean(msg, "✅ Tayyor", main_menu())

# ================= SAVE SALE (100% ISHONCHLI) =================
@dp.message_handler(lambda m: m.chat.type in ["group", "supergroup"] and m.text)
async def save_sale(msg):
    text = clean_unicode(msg.text)
    amount = None

    for line in text.splitlines():
        if re.match(r"^\s*(Итого|ИТОГО|Jami)\b", line, re.I):
            m = re.search(r"(\d[\d\s]*)\s*(UZS|so['`]?m|сум)", line, re.I)
            if m:
                amount = int(m.group(1).replace(" ", ""))
            break

    if amount is None:
        clean = text.replace(" ", "")
        if clean.isdigit():
            amount = int(clean)

    if not amount or amount < MIN_AMOUNT:
        return

    now = datetime.now(TZ)
    cur.execute(
        "INSERT INTO sales VALUES (?,?,?,?,?)",
        (msg.chat.id, msg.from_user.id, amount,
         now.strftime("%Y-%m-%d"), get_work_week(now))
    )
    conn.commit()

# ================= REPORT =================
@dp.message_handler(lambda m: m.text == "📊 Bugungi hisobot")
async def today(msg):
    now = datetime.now(TZ)
    cur.execute(
        "SELECT SUM(amount) FROM sales WHERE user_id=? AND date=?",
        (msg.from_user.id, now.strftime("%Y-%m-%d"))
    )
    total = cur.fetchone()[0] or 0

    cur.execute("SELECT fixed, percent FROM users WHERE user_id=?", (msg.from_user.id,))
    fixed, percent = cur.fetchone()

    bonus = int(total * percent)
    await send_clean(
        msg,
        f"📊 Bugungi hisobot\n\n"
        f"📅 {now.strftime('%d-%m-%Y')} {now.strftime('%H:%M')}\n\n"
        f"💰 Savdo: {total:,} UZS\n"
        f"📊 Foiz: {bonus:,} UZS\n"
        f"💼 Fixed: {fixed:,} UZS\n"
        f"✅ Jami: {fixed + bonus:,} UZS",
        main_menu()
    )

# ================= GRAPH =================
days = ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]

def graph_kb(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    for i, d in enumerate(days):
        cur.execute("SELECT is_work FROM workdays WHERE user_id=? AND day=?", (uid,i))
        r = cur.fetchone()
        is_work = r[0] if r else 1
        kb.insert(InlineKeyboardButton(
            f"{'🟢' if is_work else '🔴'} {d}",
            callback_data=f"day:{i}"
        ))
    return kb

@dp.message_handler(lambda m: m.text == "📊 Grafik")
async def graph(msg):
    await send_clean(msg, "📊 Ish / Dam kunlari", graph_kb(msg.from_user.id))

@dp.callback_query_handler(lambda c: c.data.startswith("day:"))
async def toggle(call):
    d = int(call.data.split(":")[1])
    uid = call.from_user.id
    cur.execute("SELECT is_work FROM workdays WHERE user_id=? AND day=?", (uid,d))
    r = cur.fetchone()
    new = 0 if r and r[0] == 1 else 1
    cur.execute("REPLACE INTO workdays VALUES (?,?,?)", (uid,d,new))
    conn.commit()
    await call.message.edit_reply_markup(graph_kb(uid))

# ================= SETTINGS =================
@dp.message_handler(lambda m: m.text == "⚙️ Sozlamalar")
async def settings(msg):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔄 Hisobni yangilash")
    kb.add("🔁 Qayta ro‘yxatdan o‘tish")
    kb.add("⬅️ Ortga")
    await send_clean(msg, "⚙️ Sozlamalar", kb)

@dp.message_handler(lambda m: m.text == "🔄 Hisobni yangilash")
async def reset(msg):
    cur.execute("DELETE FROM sales WHERE user_id=?", (msg.from_user.id,))
    conn.commit()
    await send_clean(msg, "♻️ Hisob yangilandi", main_menu())

@dp.message_handler(lambda m: m.text == "🔁 Qayta ro‘yxatdan o‘tish")
async def rereg(msg):
    cur.execute("DELETE FROM users WHERE user_id=?", (msg.from_user.id,))
    conn.commit()
    user_step[msg.from_user.id] = "name"
    await send_clean(msg, "👤 Isming nima?")

@dp.message_handler(lambda m: m.text == "⬅️ Ortga")
async def back(msg):
    await send_clean(msg, "🏠 Menyu", main_menu())

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
