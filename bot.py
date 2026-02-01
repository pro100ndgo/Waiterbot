import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("TOKEN")
TZ = timezone(timedelta(hours=5))  # Toshkent
MIN_AMOUNT = 10000

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================= DB =================
db = sqlite3.connect("data.db", check_same_thread=False)
cur = db.cursor()

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
    user_id INTEGER,
    amount INTEGER,
    date TEXT
)
""")
db.commit()

user_step = {}
last_bot_msg = {}

# ================= HELPERS =================
def clean_text(text: str) -> str:
    # unicode chiziqlarni O‘CHIRISH
    bad = ["\u0336", "\u0335", "\u0337"]
    for b in bad:
        text = text.replace(b, "")
    return text

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

def get_week_start(dt):
    # Shanba start
    offset = (dt.weekday() - 5) % 7
    return dt - timedelta(days=offset)

# ================= START =================
@dp.message_handler(commands=["start"])
async def start(msg):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("▶️ Davom etish")
    await send_clean(
        msg,
        "ℹ️ Ushbu bot ofitsiantlar ish haqqini hisoblash uchun\n\n"
        "• Chekdan FAQAT yakuniy summa olinadi\n"
        "• Ustiga chizilgan narxlar hisoblanmaydi\n"
        "• Ish haftasi: Shanba → Juma 23:30\n\n"
        "by @Shakhzod_2105",
        kb
    )

@dp.message_handler(lambda m: m.text == "▶️ Davom etish")
async def cont(msg):
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (msg.from_user.id,))
    if cur.fetchone():
        await send_clean(msg, "🏠 Menyu", main_menu())
    else:
        user_step[msg.from_user.id] = "name"
        await send_clean(msg, "👤 Ismingni yoz:")

# ================= REG =================
@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "name")
async def reg_name(msg):
    cur.execute("INSERT OR REPLACE INTO users (user_id, name) VALUES (?,?)",
                (msg.from_user.id, msg.text))
    db.commit()
    user_step[msg.from_user.id] = "fixed"
    await send_clean(msg, "💼 Kunlik ish haqqi (masalan 170000):")

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "fixed")
async def reg_fixed(msg):
    cur.execute("UPDATE users SET fixed=? WHERE user_id=?",
                (int(msg.text), msg.from_user.id))
    db.commit()
    user_step[msg.from_user.id] = "percent"
    await send_clean(msg, "📊 Foiz (masalan 0.7):")

@dp.message_handler(lambda m: user_step.get(m.from_user.id) == "percent")
async def reg_percent(msg):
    cur.execute("UPDATE users SET percent=? WHERE user_id=?",
                (float(msg.text) / 100, msg.from_user.id))
    db.commit()
    user_step.pop(msg.from_user.id)
    await send_clean(msg, "✅ Profil tayyor", main_menu())

# ================= SAVE SALES =================
@dp.message_handler(lambda m: m.chat.type in ["group", "supergroup"] and m.text)
async def parse_check(msg):
    text = clean_text(msg.text)
    amount = None

    # Faqat ИТОГО qatoridan OXIRGI summa
    for line in text.splitlines():
        if re.search(r"\b(Итого|Jami)\b", line, re.I):
            nums = re.findall(r"\d[\d\s]{3,}", line)
            if nums:
                amount = int(nums[-1].replace(" ", ""))
            break

    if not amount or amount < MIN_AMOUNT:
        return

    cur.execute(
        "INSERT INTO sales VALUES (?,?,?)",
        (msg.from_user.id, amount, datetime.now(TZ).strftime("%Y-%m-%d"))
    )
    db.commit()

# ================= REPORT =================
@dp.message_handler(lambda m: m.text == "📊 Bugungi hisobot")
async def today(msg):
    cur.execute("SELECT fixed, percent FROM users WHERE user_id=?", (msg.from_user.id,))
    user = cur.fetchone()
    if not user:
        user_step[msg.from_user.id] = "name"
        await send_clean(msg, "❗ Avval ro‘yxatdan o‘ting\nIsmingni yoz:")
        return

    fixed, percent = user
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    cur.execute("SELECT SUM(amount) FROM sales WHERE user_id=? AND date=?",
                (msg.from_user.id, today))
    total = cur.fetchone()[0] or 0

    bonus = int(total * percent)

    await send_clean(
        msg,
        f"📊 Bugungi hisobot\n\n"
        f"📅 {today} {datetime.now(TZ).strftime('%H:%M')}\n\n"
        f"💰 Savdo: {total:,} UZS\n"
        f"📊 Foiz: {bonus:,} UZS\n"
        f"💼 Fixed: {fixed:,} UZS\n"
        f"✅ Jami: {fixed + bonus:,} UZS",
        main_menu()
    )

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
    db.commit()
    await send_clean(msg, "♻️ Hisob tozalandi", main_menu())

@dp.message_handler(lambda m: m.text == "🔁 Qayta ro‘yxatdan o‘tish")
async def rereg(msg):
    cur.execute("DELETE FROM users WHERE user_id=?", (msg.from_user.id,))
    cur.execute("DELETE FROM sales WHERE user_id=?", (msg.from_user.id,))
    db.commit()
    user_step[msg.from_user.id] = "name"
    await send_clean(msg, "👤 Ismingni yoz:")

@dp.message_handler(lambda m: m.text == "⬅️ Ortga")
async def back(msg):
    await send_clean(msg, "🏠 Menyu", main_menu())

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
