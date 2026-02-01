import os
import re
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
MIN_AMOUNT = 10000  # 10 mingdan kichik summa olinmaydi

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
    percent REAL,
    show_in_leaderboard INTEGER DEFAULT 1
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS sales (
    group_id INTEGER,
    user_id INTEGER,
    amount INTEGER,
    date TEXT,
    work_week TEXT
)
""")

conn.commit()

# ================= MEMORY =================
user_step = {}
bot_messages = {}

# ================= HELPERS =================
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
    kb.add("📆 Haftalik hisobot", "🏆 TOP")
    kb.add("⚙️ Sozlamalar")
    return kb

# ================= ISH HAFTASI =================
def get_work_week(dt: datetime):
    # Juma 23:30 dan keyin — yangi hafta
    if dt.weekday() == 4 and (dt.hour > 23 or (dt.hour == 23 and dt.minute >= 30)):
        dt += timedelta(days=1)

    # Shanba — hafta boshi
    days_from_saturday = (dt.weekday() - 5) % 7
    week_start = dt - timedelta(days=days_from_saturday)

    year, week, _ = week_start.isocalendar()
    return f"{year}-W{week:02d}"

# ================= INTRO / BANNER =================
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    intro = (
        "ℹ️ Ushbu bot nima qiladi?\n\n"
        "Bu bot ofitsiantlar ish haqqini hisoblashni avtomatlashtirish\n"
        "uchun mo‘ljallangan.\n\n"
        "• Cheklardan faqat yakuniy (Итого / Jami) summani oladi\n"
        "• Ustiga chizilgan eski summalarni inkor qiladi\n"
        "• Qo‘lda yozilgan toza raqamlarni ham hisoblaydi\n"
        "• Ish haftasi: shanba → juma 23:30\n"
        "• Kunlik, 3 kunlik va haftalik hisobotlar\n\n"
        "👨‍💻 Muallif: @Shakhzod_2105"
    )

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("▶️ Davom etish")

    await send_clean(msg, intro, kb)

# ================= CONTINUE =================
@dp.message_handler(lambda m: m.text == "▶️ Davom etish")
async def after_intro(msg):
    cur.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    u = cur.fetchone()

    if u:
        await send_clean(msg, f"👋 Xush kelibsan, {u[0]}!", main_menu())
    else:
        user_step[msg.from_user.id] = "name"
        await send_clean(msg, "👤 Isming nima?")

# ================= REGISTRATION =================
@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "name")
async def reg_name(msg):
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, name) VALUES (?,?)",
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

    user_step.pop(msg.from_user.id)
    await send_clean(msg, "✅ Profil tayyor!", main_menu())

# ================= SAVE SALES (ENG MUHIM JOY) =================
@dp.message_handler(lambda m: m.chat.type in ["group", "supergroup"] and m.text)
async def save_sale(msg: types.Message):
    # 1️⃣ Ustiga chizilgan belgilarni olib tashlaymiz (Telegram strikethrough)
    text = msg.text.replace("\u0336", "")
    amount = None

    # 2️⃣ Qatorlarga bo‘lamiz
    lines = text.splitlines()

    # 3️⃣ Faqat ИТОГО / JAMI bilan BOSHLANADIGAN qatorni olamiz
    total_line = None
    for line in lines:
        if re.match(r"^\s*(Итого|ИТОГО|Итог|Jami)\b", line, re.IGNORECASE):
            total_line = line  # oxirgisi qoladi

    # 4️⃣ O‘sha qatordan faqat OXIRGI summani olamiz
    if total_line:
        numbers = re.findall(r"\d[\d\s]*", total_line)
        if numbers:
            amount = int(numbers[-1].replace(" ", ""))

    # 5️⃣ Agar Итого yo‘q bo‘lsa → faqat toza raqam
    if amount is None:
        clean = text.replace(" ", "")
        if clean.isdigit():
            amount = int(clean)

    # 6️⃣ Himoya
    if not amount or amount < MIN_AMOUNT:
        return

    now = datetime.now()
    work_week = get_work_week(now)

    cur.execute(
        "INSERT INTO sales VALUES (?,?,?,?,?)",
        (
            msg.chat.id,
            msg.from_user.id,
            amount,
            now.strftime("%Y-%m-%d"),
            work_week
        )
    )
    conn.commit()

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
