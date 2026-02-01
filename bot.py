import os
import sqlite3
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup
)

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
TZ = timezone(timedelta(hours=5))  # Toshkent vaqti

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================= DATABASE =================
db = sqlite3.connect("data.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    fixed INTEGER,
    percent REAL,
    dashboard_msg INTEGER
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

# ================= STATES =================
user_state = {}

# ================= KEYBOARDS =================
def kb_main():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Bugun", callback_data="today"),
        InlineKeyboardButton("📆 Haftalik", callback_data="week"),
        InlineKeyboardButton("📈 Grafik", callback_data="graph"),
        InlineKeyboardButton("⚙️ Sozlamalar", callback_data="settings"),
    )
    return kb

def kb_fixed():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("120 000", callback_data="fixed_120000"),
        InlineKeyboardButton("150 000", callback_data="fixed_150000"),
        InlineKeyboardButton("170 000", callback_data="fixed_170000"),
    )
    return kb

def kb_percent():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("0.7 %", callback_data="percent_0.7"),
        InlineKeyboardButton("1 %", callback_data="percent_1"),
        InlineKeyboardButton("3 %", callback_data="percent_3"),
        InlineKeyboardButton("5 %", callback_data="percent_5"),
    )
    return kb

def kb_settings():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔄 Hisobni tozalash", callback_data="reset"),
        InlineKeyboardButton("🔁 Qayta ro‘yxatdan o‘tish", callback_data="rereg"),
        InlineKeyboardButton("⬅️ Ortga", callback_data="back"),
    )
    return kb

# ================= START =================
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    cur.execute("SELECT dashboard_msg FROM users WHERE user_id=?", (msg.from_user.id,))
    user = cur.fetchone()

    if user:
        await show_dashboard(msg.from_user.id, msg.chat.id)
        return

    user_state[msg.from_user.id] = "name"
    await msg.answer(
        "👋 Xush kelibsiz!\n\n"
        "Bu bot ofitsiantlar ish haqqini hisoblash uchun.\n\n"
        "Boshlash uchun ismingizni yozing:"
    )

# ================= REGISTRATION =================
@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "name")
async def reg_name(msg: types.Message):
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, name) VALUES (?,?)",
        (msg.from_user.id, msg.text.strip())
    )
    db.commit()
    user_state[msg.from_user.id] = "fixed"

    await msg.answer("💼 Kunlik ish haqqini tanlang:", reply_markup=kb_fixed())

@dp.callback_query_handler(lambda c: c.data.startswith("fixed_"))
async def reg_fixed(call: types.CallbackQuery):
    fixed = int(call.data.split("_")[1])
    cur.execute(
        "UPDATE users SET fixed=? WHERE user_id=?",
        (fixed, call.from_user.id)
    )
    db.commit()
    user_state[call.from_user.id] = "percent"

    await call.message.edit_text(
        "📊 Savdodan olinadigan foizni tanlang:",
        reply_markup=kb_percent()
    )

@dp.callback_query_handler(lambda c: c.data.startswith("percent_"))
async def reg_percent(call: types.CallbackQuery):
    percent = float(call.data.split("_")[1]) / 100
    cur.execute(
        "UPDATE users SET percent=? WHERE user_id=?",
        (percent, call.from_user.id)
    )
    db.commit()
    user_state.pop(call.from_user.id, None)

    await show_dashboard(call.from_user.id, call.message.chat.id)

# ================= DASHBOARD =================
async def show_dashboard(user_id: int, chat_id: int):
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")

    cur.execute("SELECT fixed, percent, dashboard_msg FROM users WHERE user_id=?", (user_id,))
    fixed, percent, dash_id = cur.fetchone()

    cur.execute("SELECT SUM(amount) FROM sales WHERE user_id=? AND date=?", (user_id, today))
    total = cur.fetchone()[0] or 0
    bonus = int(total * percent)

    text = (
        "📊 <b>Bugungi hisobot</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"📅 {now.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"💰 Savdo: <b>{total:,} UZS</b>\n"
        f"📊 Foiz: <b>{bonus:,} UZS</b>\n"
        f"💼 Fixed: <b>{fixed:,} UZS</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"✅ <b>Jami: {fixed + bonus:,} UZS</b>"
    )

    if dash_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=dash_id,
                text=text,
                reply_markup=kb_main(),
                parse_mode="HTML"
            )
            return
        except:
            pass

    msg = await bot.send_message(
        chat_id,
        text,
        reply_markup=kb_main(),
        parse_mode="HTML"
    )
    cur.execute("UPDATE users SET dashboard_msg=? WHERE user_id=?", (msg.message_id, user_id))
    db.commit()

# ================= CALLBACKS =================
@dp.callback_query_handler(lambda c: c.data == "today")
async def cb_today(call: types.CallbackQuery):
    await show_dashboard(call.from_user.id, call.message.chat.id)

@dp.callback_query_handler(lambda c: c.data == "week")
async def cb_week(call: types.CallbackQuery):
    await call.answer("📆 Haftalik hisobot tez kunda 👌", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "graph")
async def cb_graph(call: types.CallbackQuery):
    await call.answer("📈 Grafik keyingi bosqichda qo‘shiladi", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "settings")
async def cb_settings(call: types.CallbackQuery):
    await call.message.edit_reply_markup(kb_settings())

@dp.callback_query_handler(lambda c: c.data == "back")
async def cb_back(call: types.CallbackQuery):
    await call.message.edit_reply_markup(kb_main())

@dp.callback_query_handler(lambda c: c.data == "reset")
async def cb_reset(call: types.CallbackQuery):
    cur.execute("DELETE FROM sales WHERE user_id=?", (call.from_user.id,))
    db.commit()
    await call.answer("♻️ Hisob tozalandi", show_alert=True)
    await show_dashboard(call.from_user.id, call.message.chat.id)

@dp.callback_query_handler(lambda c: c.data == "rereg")
async def cb_rereg(call: types.CallbackQuery):
    cur.execute("DELETE FROM users WHERE user_id=?", (call.from_user.id,))
    cur.execute("DELETE FROM sales WHERE user_id=?", (call.from_user.id,))
    db.commit()
    user_state[call.from_user.id] = "name"
    await call.message.edit_text("👤 Ismingizni yozing:")

# ================= GROUP SALES =================
@dp.message_handler(lambda m: m.chat.type in ["group", "supergroup"] and m.text)
async def group_sale(msg: types.Message):
    text = msg.text.replace(" ", "")
    if text.isdigit():
        amount = int(text)
        if amount > 10000:
            cur.execute(
                "INSERT INTO sales VALUES (?,?,?)",
                (msg.from_user.id, amount, datetime.now(TZ).strftime("%Y-%m-%d"))
            )
            db.commit()

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp)
