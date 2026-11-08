import os
import asyncio
import sqlite3
import shutil
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
from threading import Thread

# --- কনফিগারেশন ---
TOKEN = "8751100050:AAF4Vunr7OT-H0WZySy4p6UH16Cyt693gsI"
ADMIN_ID = 7718164345  # আপনার নতুন অ্যাডমিন চ্যাট আইডি

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ফ্লাস্ক সার্ভার (Render Web Service কে ২৪/৭ সচল রাখার জন্য) ---
app = Flask('')

@app.route('/')
def home():
    return "🤖 Auto-Indexing Telegram Search & Terabox Bot is running 24/7 on Render!"

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
            
            # আপনার নতুন অ্যাডমিন আইডিতে ব্যাকআপ পাঠানো
            with open(backup_filename, 'rb') as f:
                await bot.send_document(
                    chat_id=ADMIN_ID,
                    document=f,
                    caption=(
                        f"⚙️ **অটো ডাটাবেজ ব্যাকআপ রিপোর্ট:**\n"
                        f"🕒 সময়: `{timestamp}`\n"
                        f"✅ ডাটাবেজ সফলভাবে ব্যাকআপ হয়ে আপনার কাছে এসেছে।"
                    ),
                    parse_mode="Markdown"
                )
            
            # আগের ব্যাকআপ ফাইলটি ডিলিট করে স্টোরেজ ক্লিন রাখা
            if last_backup_file and os.path.exists(last_backup_file):
                os.remove(last_backup_file)
                
            last_backup_file = backup_filename
            print(f"[Backup Success]: Sent to Admin ID: {ADMIN_ID}")
            
        except Exception as e:
            print(f"[Backup Error]: {e}")

# --- স্টার্ট কমান্ড ---
@dp.message(Command("start"))
async def start_handler(message: Message):
    welcome_text = (
        "🤖 **স্বাগতম! এটি একটি অটো-ইনডেক্সিং স্মার্ট সার্চ ও টেরাবক্স বট।**\n\n"
        "🔍 **অটো সার্চ:** আপনি যেকোনো মুভি, সফটওয়্যার বা ফাইলের নাম লিখে পাঠান—বট নিজে থেকেই ডাটাবেজ থেকে সেরা রেজাল্ট খুঁজে বের করবে!\n"
        "📥 **টেরাবক্স লিংক:** যেকোনো Terabox লিংক পাঠালে সাথে সাথে অনলাইন দেখার ও ডাউনলোডের বাটন পেয়ে যাবেন।\n"
        "⚙️ *বটটি নিজে নিজে ডাটা ইনডেক্স করে এবং ২৪/৭ রেন্ডারে সচল থাকে।*"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

# --- অটো-ইনডেক্সিং এবং সার্চ ইঞ্জিন হ্যান্ডলার ---
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

    # ২. অটো-ইনডেক্সিং সিস্টেম: ইউজার বা চ্যানেল থেকে আসা যেকোনো টেক্সট/লিংক বা নাম নিজে নিজেই ডাটাবেজে সেভ হয়ে যাবে
    # যাতে পরবর্তীতে কেউ সার্চ করলেই এটি নিজে নিজে খুঁজে পায়।
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # চেক করা হচ্ছে ডাটাটি আগে থেকেই আছে কি না, না থাকলে অটো সেভ হবে
        cursor.execute("SELECT id FROM files WHERE title = ?", (text,))
        exists = cursor.fetchone()
        
        if not exists and len(text) > 3: # ৩ অক্ষরের বেশি হলে অটো ইনডেক্স করবে
            # যদি টেক্সটে কোনো লিংক থাকে অথবা সাধারণ নাম হয়
            fake_link = f"https://t.me/share/url?url={text.replace(' ', '_')}"
            cursor.execute("INSERT INTO files (title, file_link, category) VALUES (?, ?, ?)", (text, fake_link, "Auto-Indexed"))
            conn.commit()
        
        # ৩. পাওয়ারফুল সার্চ সিস্টেম (ডাটাবেজ থেকে ম্যাচিং রেজাল্ট খোঁজা)
        cursor.execute("SELECT title, file_link FROM files WHERE title LIKE ?", ('%' + text + '%',))
        results = cursor.fetchall()
        conn.close()

        if results:
            response = f"🔍 **'{text}' এর জন্য অটো-সার্চ রেজাল্ট:**\n\n"
            for idx, (title, link) in enumerate(results[:15], 1):
                response += f"{idx}. [{title}]({link})\n"
            await message.reply(response, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            await message.reply(
                f"🔎 '{text}' কিওয়ার্ডটি আমাদের অটো-ইনডেক্সে যুক্ত করা হয়েছে।\n"
                "💡 আপনি চাইলে কোনো **Terabox Link** পাঠিয়ে দেখতে পারেন!"
            )
            
    except Exception as e:
        print(f"Search/Index Error: {e}")

# --- মূল রানিং ফাংশন ---
async def main():
    keep_alive()
    asyncio.create_task(database_backup_loop())
    print("🚀 Smart Auto-Indexing Bot is running successfully...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
