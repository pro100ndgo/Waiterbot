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
    # Juma 23:30 dan keyin — yangi ish haftasi
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
        "• Guruhdagi cheklardan faqat yakuniy (Итого) summani oladi\n"
        "• Qo‘lda yozilgan toza summalarni hisobga qo‘shadi\n"
        "• Ish haftasini shanbadan jumaga (23:30 gacha) hisoblaydi\n"
        "• Kunlik, 3 kunlik va haftalik hisobot chiqaradi\n"
        "• TOP ofitsiantlar reytingini ko‘rsatadi\n\n"
        "Bot restoran jamoasi uchun qulay va aniq hisob-kitob\n"
        "olib borish maqsadida yaratilgan.\n\n"
        "👨‍💻 Muallif: @Shakhzod_2105"
    )

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("▶️ Davom etish")

    await send_clean(msg, intro, kb)

# ================= CONTINUE AFTER INTRO =================
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

# ================= SAVE SALES (GROUP) =================
@dp.message_handler(lambda m: m.chat.type in ["group", "supergroup"] and m.text)
async def save_sale(msg: types.Message):
    text = msg.text.strip()
    amount = None

    # ИТОГО / JAMI → oxirgi summani olish
    match = re.search(
        r"(Итого|ИТОГО|Итог|Jami)\s*[:\-]?\s*([\d\s]+)",
        text,
        re.IGNORECASE
    )
    if match:
        numbers = re.findall(r"\d[\d\s]*", match.group(2))
        if numbers:
            amount = int(numbers[-1].replace(" ", ""))

    # Agar yo‘q bo‘lsa → faqat toza raqam
    if amount is None:
        clean = text.replace(" ", "")
        if clean.isdigit():
            amount = int(clean)

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

# ================= REPORTS =================
async def send_report(msg, mode):
    uid = msg.from_user.id
    now = datetime.now()

    if mode == "today":
        where = "date=?"
        params = (now.strftime("%Y-%m-%d"),)
        title = "📊 Bugungi hisobot"
    elif mode == "3days":
        since = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        where = "date>=?"
        params = (since,)
        title = "📅 3 kunlik hisobot"
    else:
        ww = get_work_week(now)
        where = "work_week=?"
        params = (ww,)
        title = "📆 Haftalik hisobot"

    cur.execute(
        f"SELECT SUM(amount) FROM sales WHERE user_id=? AND {where}",
        (uid, *params)
    )
    total = cur.fetchone()[0] or 0

    cur.execute(
        "SELECT name, fixed, percent FROM users WHERE user_id=?",
        (uid,)
    )
    name, fixed, percent = cur.fetchone()

    bonus = int(total * percent)
    jami = fixed + bonus

    await send_clean(
        msg,
        f"{title}\n\n"
        f"👤 {name}\n"
        f"💰 Savdo: {total:,} UZS\n"
        f"📊 Foiz: {bonus:,} UZS\n"
        f"💼 Fixed: {fixed:,} UZS\n"
        f"✅ Jami: {jami:,} UZS",
        main_menu()
    )

@dp.message_handler(lambda m: m.text == "📊 Bugungi hisobot")
async def r_today(msg): await send_report(msg, "today")

@dp.message_handler(lambda m: m.text == "📅 3 kunlik hisobot")
async def r_3(msg): await send_report(msg, "3days")

@dp.message_handler(lambda m: m.text == "📆 Haftalik hisobot")
async def r_week(msg): await send_report(msg, "weekly")

# ================= LEADERBOARD =================
@dp.message_handler(lambda m: m.text == "🏆 TOP")
async def leaderboard(msg):
    ww = get_work_week(datetime.now())
    cur.execute("""
        SELECT u.name, u.branch, SUM(s.amount)
        FROM sales s
        JOIN users u ON u.user_id=s.user_id
        WHERE s.work_week=? AND u.show_in_leaderboard=1
        GROUP BY s.user_id
        ORDER BY SUM(s.amount) DESC
        LIMIT 5
    """, (ww,))
    rows = cur.fetchall()

    if not rows:
        await send_clean(msg, "🏆 Leaderboard bo‘sh.", main_menu())
        return

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    text = "🏆 TOP 5 (joriy ish haftasi)\n\n"
    for i, r in enumerate(rows):
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
    kb.add("🔄 Qayta ro‘yxatdan o‘tish")
    kb.add("🗑 Barcha savdoni tozalash")
    kb.add("⬅️ Ortga")

    await send_clean(msg, f"⚙️ Sozlamalar\nLeaderboard: {status}", kb)

@dp.message_handler(lambda m: m.text == "👁 Leaderboardni yoq/o‘chir")
async def toggle_lb(msg):
    cur.execute(
        "UPDATE users SET show_in_leaderboard=1-show_in_leaderboard WHERE user_id=?",
        (msg.from_user.id,)
    )
    conn.commit()
    await settings(msg)

@dp.message_handler(lambda m: m.text == "🔄 Qayta ro‘yxatdan o‘tish")
async def re_register(msg):
    cur.execute("DELETE FROM users WHERE user_id=?", (msg.from_user.id,))
    conn.commit()
    user_step[msg.from_user.id] = "name"
    await send_clean(msg, "♻️ Qayta ro‘yxatdan o‘tish boshlandi.\n\n👤 Isming nima?")

@dp.message_handler(lambda m: m.text == "🗑 Barcha savdoni tozalash")
async def reset_sales(msg):
    cur.execute("DELETE FROM sales WHERE user_id=?", (msg.from_user.id,))
    conn.commit()
    await send_clean(msg, "✅ Barcha savdolar o‘chirildi.", main_menu())

@dp.message_handler(lambda m: m.text == "⬅️ Ortga")
async def back(msg):
    await send_clean(msg, "⬅️ Menyu", main_menu())

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
