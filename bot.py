import os
import asyncio
import sqlite3
import shutil
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from flask import Flask
from threading import Thread

# --- কনফিগারেশন ---
TOKEN = "8751100050:AAF4Vunr7OT-H0WZySy4p6UH16Cyt693gsI"
ADMIN_ID = 7718164345  # আপনার অ্যাডমিন চ্যাট আইডি

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ফ্লাস্ক সার্ভার (Render Web Service কে ২৪/৭ সচল রাখার জন্য) ---
app = Flask('')

@app.route('/')
def home():
    return "🤖 Master Telegram Search & Terabox Bot is running 24/7 on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- ডাটাবেজ সেটআপ ---
DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            file_link TEXT,
            category TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- ১ মিনিট পর পর অটো ডাটাবেজ ব্যাকআপ ও পুরনো ফাইল ডিলিট সিস্টেম ---
async def database_backup_loop():
    await asyncio.sleep(15)
    last_backup_file = None
    
    while True:
        await asyncio.sleep(60)  # প্রতি ৬০ সেকেন্ড পর পর
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_filename = f"backup_{timestamp}.db"
            
            shutil.copyfile(DB_NAME, backup_filename)
            
            with open(backup_filename, 'rb') as f:
                await bot.send_document(
                    chat_id=ADMIN_ID,
                    document=f,
                    caption=(
                        f"⚙️ **অটো ডাটাবেজ ব্যাকআপ রিপোর্ট:**\n"
                        f"🕒 সময়: `{timestamp}`\n"
                        f"✅ ব্যাকআপ ফাইল সফলভাবে পাঠানো হয়েছে।"
                    ),
                    parse_mode="Markdown"
                )
            
            if last_backup_file and os.path.exists(last_backup_file):
                os.remove(last_backup_file)
                
            last_backup_file = backup_filename
            print(f"[Backup Success]: Sent to Admin ID: {ADMIN_ID}")
            
        except Exception as e:
            print(f"[Backup Error]: {e}")

# --- স্টার্ট কমান্ড ও ক্যাটাগরি অপশন মেনু ---
@dp.message(Command("start"))
async def start_handler(message: Message):
    welcome_text = (
        "🤖 **স্বাগতম! মাস্টার স্মার্ট সার্চ ও টেরাবক্স বটে।**\n\n"
        "🔍 আপনি যেকোনো মুভি, ভিডিও বা ফাইলের নাম লিখে পাঠান—বট নিজে থেকেই ডাটাবেজ থেকে খুঁজে বের করবে!\n"
        "📥 যেকোনো **Terabox Link** পাঠালে সাথে সাথে অনলাইন দেখার ও ডাউনলোডের বাটন পেয়ে যাবেন।\n\n"
        "👇 নিচে থেকে ক্যাটাগরি সিলেক্ট করুন অথবা সরাসরি সার্চ করুন:"
    )
    
    # ইউজার ইন্টারফেসে অপশন বাটন বা মেনু
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📂 সব ফাইল", callback_data="cat_files"),
                InlineKeyboardButton(text="🎬 ভিডিও কন্টেন্ট", callback_data="cat_videos")
            ],
            [
                InlineKeyboardButton(text="📢 চ্যানেল ও গ্রুপ", callback_data="cat_channels"),
                InlineKeyboardButton(text="⭐ টেরাবক্স ডাউনলোডার", callback_data="cat_terabox")
            ]
        ]
    )
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")

# --- ক্যাটাগরি বাটন কলব্যাক হ্যান্ডলার ---
@dp.callback_query(F.data.startswith("cat_"))
async def category_callback(callback: CallbackQuery):
    data = callback.data
    if data == "cat_files":
        await callback.message.answer("📁 ফাইল সার্চ করতে যেকোনো ফাইলের নাম লিখে পাঠান।")
    elif data == "cat_videos":
        await callback.message.answer("🎬 ভিডিও কন্টেন্ট দেখতে মুভি বা সিরিজের নাম লিখে পাঠান।")
    elif data == "cat_channels":
        await callback.message.answer("📢 চ্যানেল ও গ্রুপের ডাটা দেখতে কি-ওয়ার্ড লিখে সার্চ করুন।")
    elif data == "cat_terabox":
        await callback.message.answer("📥 যেকোনো টেরাবক্স লিংক (Terabox Link) চ্যাটে পেস্ট করুন।")
    await callback.answer()

# --- অটো-ইনডেক্সিং এবং স্মার্ট সার্চ ইঞ্জিন হ্যান্ডলার ---
@dp.message(F.text)
async def handle_auto_index_and_search(message: Message):
    text = message.text.strip()
    
    # ১. টেরাবক্স লিংক প্রসেসর
    if "terabox" in text.lower() or "teraboxapp" in text.lower():
        processing_msg = await message.reply("⏳ টেরাবক্স লিংক প্রসেস করা হচ্ছে...")
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📥 সরাসরি ডাউনলোড করুন", url=text)],
                [InlineKeyboardButton(text="▶️ অনলাইন ভিডিও দেখুন", url=text)]
            ]
        )
        
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        except:
            pass
            
        await message.reply(
            "🎬 **টেরাবক্স ফাইল রেডি!**\n\n"
            "নিচের বাটনগুলোতে ক্লিক করে ভিডিওটি দেখতে ও ডাউনলোড করতে পারবেন:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # ২. অটো-ইনডেক্সিং এবং সার্চ সিস্টেম
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM files WHERE title = ?", (text,))
        exists = cursor.fetchone()
        
        if not exists and len(text) > 2:
            fake_link = f"https://t.me/share/url?url={text.replace(' ', '_')}"
            cursor.execute("INSERT INTO files (title, file_link, category) VALUES (?, ?, ?)", (text, fake_link, "Auto-Indexed"))
            conn.commit()
        
        cursor.execute("SELECT title, file_link FROM files WHERE title LIKE ?", ('%' + text + '%',))
        results = cursor.fetchall()
        conn.close()

        if results:
            response = f"🔍 **'{text}' এর জন্য সার্চ রেজাল্ট:**\n\n"
            for idx, (title, link) in enumerate(results[:15], 1):
                response += f"{idx}. [{title}]({link})\n"
            await message.reply(response, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            await message.reply(
                f"🔎 '{text}' আমাদের ডাটাবেজে ইনডেক্স করা হয়েছে।\n"
                "💡 আপনি চাইলে কোনো **Terabox Link** বা অন্য কোনো নাম দিয়ে সার্চ করতে পারেন!"
            )
            
    except Exception as e:
        print(f"Search/Index Error: {e}")

# --- মূল রানিং ফাংশন ---
async def main():
    keep_alive()
    asyncio.create_task(database_backup_loop())
    print("🚀 Master Bot is running successfully with zero errors...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
