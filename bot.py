import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN")
MIN_AMOUNT = 10000

TZ = timezone(timedelta(hours=5))  # Toshkent vaqti (GMT+5)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================== DATABASE ==================
conn = sqlite3.connect("data.db", check_same_thread=False)
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

# ================== MEMORY ==================
user_step = {}
bot_messages = {}

# ================== HELPERS ==================
async def send_clean(msg, text, reply_markup=None):
    uid = msg.from_user.id

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
    kb.add("📆 Haftalik hisobot", "📊 Grafik")
    kb.add("🏆 TOP")
    kb.add("⚙️ Sozlamalar")
    return kb

# ================== WORK WEEK ==================
def get_work_week(dt):
    if dt.weekday() == 4 and (dt.hour > 23 or (dt.hour == 23 and dt.minute >= 30)):
        dt += timedelta(days=1)

    days_from_saturday = (dt.weekday() - 5) % 7
    week_start = dt - timedelta(days=days_from_saturday)
    year, week, _ = week_start.isocalendar()
    return f"{year}-W{week:02d}"

# ================== START / BANNER ==================
@dp.message_handler(commands=["start"])
async def start(msg):
    text = (
        "ℹ️ Ushbu bot nima qiladi?\n\n"
        "Bu bot ofitsiantlar ish haqqini hisoblash uchun.\n\n"
        "• Cheklardan faqat oxirgi ИТОГО/JAMI olinadi\n"
        "• Ustiga chizilgan narxlar inkor qilinadi\n"
        "• Oddiy yozilgan raqamlar qabul qilinadi\n"
        "• Ish haftasi: Shanba → Juma 23:30\n\n"
        "👨‍💻 by: @Shakhzod_2105"
    )

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("▶️ Davom etish")
    await send_clean(msg, text, kb)

@dp.message_handler(lambda m: m.text == "▶️ Davom etish")
async def continue_start(msg):
    cur.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    if cur.fetchone():
        await send_clean(msg, "👋 Xush kelibsan!", main_menu())
    else:
        user_step[msg.from_user.id] = "name"
        await send_clean(msg, "👤 Isming nima?")

# ================== REGISTRATION ==================
@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "name")
async def reg_name(msg):
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, name) VALUES (?,?)",
        (msg.from_user.id, msg.text)
    )
    conn.commit()
    user_step[msg.from_user.id] = "branch"

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("🏢 AKSU Shedevr", "🏢 AKSU Chigatoy")
    await send_clean(msg, "🏢 Filialni tanla:", kb)

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "branch")
async def reg_branch(msg):
    cur.execute(
        "UPDATE users SET branch=? WHERE user_id=?",
        (msg.text, msg.from_user.id)
    )
    conn.commit()
    user_step[msg.from_user.id] = "fixed"

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("120000", "150000", "170000")
    await send_clean(msg, "💼 Fixed ish haqqi:", kb)

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "fixed")
async def reg_fixed(msg):
    cur.execute(
        "UPDATE users SET fixed=? WHERE user_id=?",
        (int(msg.text), msg.from_user.id)
    )
    conn.commit()
    user_step[msg.from_user.id] = "percent"

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("0.7", "1", "3", "5")
    await send_clean(msg, "📊 Foizni tanla:", kb)

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "percent")
async def reg_percent(msg):
    percent_map = {"0.7": 0.007, "1": 0.01, "3": 0.03, "5": 0.05}
    cur.execute(
        "UPDATE users SET percent=? WHERE user_id=?",
        (percent_map[msg.text], msg.from_user.id)
    )
    conn.commit()
    user_step.pop(msg.from_user.id, None)
    await send_clean(msg, "✅ Profil tayyor!", main_menu())

# ================== SAVE SALES ==================
@dp.message_handler(lambda m: m.chat.type in ["group", "supergroup"] and m.text)
async def save_sale(msg):
    text = msg.text.replace("\u0336", "")
    amount = None

    total_line = None
    for line in text.splitlines():
        if re.match(r"^\s*(Итого|ИТОГО|Jami)\b", line, re.I):
            total_line = line

    if total_line:
        nums = re.findall(r"\d[\d\s]*", total_line)
        if nums:
            amount = int(nums[-1].replace(" ", ""))

    if amount is None:
        clean = text.replace(" ", "")
        if clean.isdigit():
            amount = int(clean)

    if not amount or amount < MIN_AMOUNT:
        return

    now = datetime.now(TZ)
    cur.execute(
        "INSERT INTO sales VALUES (?,?,?,?,?)",
        (
            msg.chat.id,
            msg.from_user.id,
            amount,
            now.strftime("%Y-%m-%d"),
            get_work_week(now)
        )
    )
    conn.commit()

# ================== REPORTS ==================
async def send_report(msg, mode):
    uid = msg.from_user.id
    now = datetime.now(TZ)

    if mode == "today":
        where, params, title = "date=?", (now.strftime("%Y-%m-%d"),), "📊 Bugungi hisobot"
    elif mode == "3":
        since = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        where, params, title = "date>=?", (since,), "📅 3 kunlik hisobot"
    else:
        ww = get_work_week(now)
        where, params, title = "work_week=?", (ww,), "📆 Haftalik hisobot"

    cur.execute(
        f"SELECT SUM(amount) FROM sales WHERE user_id=? AND {where}",
        (uid, *params)
    )
    total = cur.fetchone()[0] or 0

    cur.execute("SELECT name, fixed, percent FROM users WHERE user_id=?", (uid,))
    name, fixed, percent = cur.fetchone()

    bonus = int(total * percent)
    jami = fixed + bonus

    await send_clean(
        msg,
        f"{title}\n\n"
        f"📅 Sana: {now.strftime('%d-%m-%Y')}\n"
        f"⏰ Vaqt: {now.strftime('%H:%M')}\n\n"
        f"👤 {name}\n"
        f"💰 Savdo: {total:,} UZS\n"
        f"📊 Foiz: {bonus:,} UZS\n"
        f"💼 Fixed: {fixed:,} UZS\n"
        f"✅ Jami: {jami:,} UZS",
        main_menu()
    )

@dp.message_handler(lambda m: m.text == "📊 Bugungi hisobot")
async def r1(msg): await send_report(msg, "today")

@dp.message_handler(lambda m: m.text == "📅 3 kunlik hisobot")
async def r2(msg): await send_report(msg, "3")

@dp.message_handler(lambda m: m.text == "📆 Haftalik hisobot")
async def r3(msg): await send_report(msg, "week")

# ================== GRAPH ==================
days = [("Dushanba",0),("Seshanba",1),("Chorshanba",2),
        ("Payshanba",3),("Juma",4),("Shanba",5),("Yakshanba",6)]

def graph_kb(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    for name, d in days:
        cur.execute("SELECT is_work FROM workdays WHERE user_id=? AND day=?", (uid,d))
        r = cur.fetchone()
        work = r[0] if r else 1
        kb.insert(
            InlineKeyboardButton(
                f"{'🟢' if work else '🔴'} {name}",
                callback_data=f"day:{d}"
            )
        )
    kb.add(InlineKeyboardButton("⬅️ Ortga", callback_data="back"))
    return kb

@dp.message_handler(lambda m: m.text == "📊 Grafik")
async def graph(msg):
    await send_clean(
        msg,
        "📊 Ish / Dam kunlari\n(Bosib o‘zgartiring)",
        graph_kb(msg.from_user.id)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("day:"))
async def toggle_day(call):
    uid = call.from_user.id
    d = int(call.data.split(":")[1])
    cur.execute("SELECT is_work FROM workdays WHERE user_id=? AND day=?", (uid,d))
    r = cur.fetchone()
    new = 0 if r and r[0] == 1 else 1
    cur.execute("REPLACE INTO workdays VALUES (?,?,?)", (uid,d,new))
    conn.commit()
    await call.message.edit_reply_markup(reply_markup=graph_kb(uid))

@dp.callback_query_handler(lambda c: c.data == "back")
async def back(call):
    await call.message.delete()

# ================== SETTINGS ==================
@dp.message_handler(lambda m: m.text == "⚙️ Sozlamalar")
async def settings(msg):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔄 Hisobni yangilash")
    kb.add("👁 Leaderboard’da ko‘rinmaslik")
    kb.add("🔁 Qayta ro‘yxatdan o‘tish")
    kb.add("⬅️ Ortga")
    await send_clean(msg, "⚙️ Sozlamalar", kb)

@dp.message_handler(lambda m: m.text == "🔄 Hisobni yangilash")
async def reset_sales(msg):
    cur.execute("DELETE FROM sales WHERE user_id=?", (msg.from_user.id,))
    conn.commit()
    await send_clean(msg, "♻️ Hisob yangilandi.", main_menu())

@dp.message_handler(lambda m: m.text == "👁 Leaderboard’da ko‘rinmaslik")
async def hide_lb(msg):
    cur.execute(
        "UPDATE users SET show_in_leaderboard=0 WHERE user_id=?",
        (msg.from_user.id,)
    )
    conn.commit()
    await send_clean(msg, "🙈 Endi leaderboard’da ko‘rinmaysiz.", main_menu())

@dp.message_handler(lambda m: m.text == "🔁 Qayta ro‘yxatdan o‘tish")
async def rereg(msg):
    cur.execute("DELETE FROM users WHERE user_id=?", (msg.from_user.id,))
    conn.commit()
    user_step[msg.from_user.id] = "name"
    await send_clean(msg, "♻️ Qayta ro‘yxatdan o‘tish boshlandi.\n\n👤 Isming nima?")

@dp.message_handler(lambda m: m.text == "⬅️ Ortga")
async def back_menu(msg):
    await send_clean(msg, "⬅️ Menyu", main_menu())

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp)
