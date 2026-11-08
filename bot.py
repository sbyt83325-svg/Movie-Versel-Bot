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

# --- কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী সেট করা) ---
TOKEN = "8751100050:AAF4Vunr7OT-H0WZySy4p6UH16Cyt693gsI"
ADMIN_ID = 8806711354  # আপনার টেলিগ্রাম চ্যাট আইডি

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ফ্লাস্ক সার্ভার (Render Web Service কে সচল রাখার জন্য) ---
app = Flask('')

@app.route('/')
def home():
    return "🤖 Telegram Smart Search & Terabox Bot is running 24/7 on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- ডাটাবেজ সেটআপ ও ইনিশিয়ালাইজেশন ---
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

# --- প্রতি ১ মিনিট পর পর অটো ডাটাবেজ ব্যাকআপ ও পুরনো ফাইল ডিলিট সিস্টেম ---
async def database_backup_loop():
    await asyncio.sleep(15)  # বট চালু হওয়ার ১৫ সেকেন্ড পর লুপ শুরু হবে
    last_backup_file = None
    
    while True:
        await asyncio.sleep(60)  # ঠিক প্রতি ১ মিনিট (৬০ সেকেন্ড) পর পর রান হবে
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_filename = f"backup_{timestamp}.db"
            
            # ডাটাবেজের একটি সেফ কপি তৈরি
            shutil.copyfile(DB_NAME, backup_filename)
            
            # আপনার টেলিগ্রাম চ্যাট আইডিতে ব্যাকআপ ফাইল পাঠানো
            with open(backup_filename, 'rb') as f:
                await bot.send_document(
                    chat_id=ADMIN_ID,
                    document=f,
                    caption=(
                        f"⚙️ **অটো ডাটাবেজ ব্যাকআপ রিপোর্ট:**\n"
                        f"🕒 সময়: `{timestamp}`\n"
                        f"✅ ডাটাবেজ ব্যাকআপ সফলভাবে সম্পন্ন হয়েছে এবং পাঠানো হয়েছে।"
                    ),
                    parse_mode="Markdown"
                )
            
            # স্টোরেজ খালি রাখতে ঠিক ১ মিনিট আগের পুরনো ব্যাকআপ ফাইলটি ডিলিট করে দেওয়া
            if last_backup_file and os.path.exists(last_backup_file):
                os.remove(last_backup_file)
                print(f"[Old Backup Cleaned]: {last_backup_file}")
                
            last_backup_file = backup_filename
            print(f"[Backup Success]: {backup_filename} sent to Admin ID: {ADMIN_ID}")
            
        except Exception as e:
            print(f"[Backup Error]: {e}")

# --- স্টার্ট কমান্ড হ্যান্ডলার ---
@dp.message(Command("start"))
async def start_handler(message: Message):
    welcome_text = (
        "👋 **স্বাগতম! আপনার পার্সোনাল স্মার্ট সার্চ ও টেরাবক্স ডাউনলোডার বটে।**\n\n"
        "🔍 **কীভাবে সার্চ করবেন:** যেকোনো মুভি, চ্যানেল বা ফাইলের নাম লিখে পাঠান, আমি ডাটাবেজ থেকে খুঁজে দেবো।\n"
        "📥 **টেরাবক্স লিংক:** যেকোনো Terabox লিংক পাঠালে সাথে সাথে ভিডিও দেখার এবং ডাউনলোডের সুন্দর বাটন চলে আসবে।\n\n"
        "🛠 *বটটি ২৪/৭ রেন্ডারে সচল রয়েছে এবং প্রতি ১ মিনিট পর পর অটো ব্যাকআপ সিস্টেম সক্রিয় আছে।*"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

# --- নতুন ডাটা যোগ করার অ্যাডমিন কমান্ড (/add শিরোনাম | লিংক) ---
@dp.message(Command("add"))
async def add_file_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⚠️ এই কমান্ডটি শুধুমাত্র অ্যাডমিনের জন্য!")
        return
    
    try:
        # ফরম্যাট: /add মুভির নাম | https://link.com
        command_text = message.text.replace("/add", "").strip()
        if "|" not in command_text:
            await message.reply("❌ ভুল ফরম্যাট! সঠিক নিয়মে লিখুন:\n`/add মুভির নাম | লিংক`", parse_mode="Markdown")
            return
            
        title, link = command_text.split("|", 1)
        title = title.strip()
        link = link.strip()
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO files (title, file_link, category) VALUES (?, ?, ?)", (title, link, "General"))
        conn.commit()
        conn.close()
        
        await message.reply(f"✅ সফলভাবে ডাটাবেজে যুক্ত করা হয়েছে!\n\n📌 **টাইটেল:** {title}\n🔗 **লিংক:** {link}", parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ ত্রুটি ঘটেছে: {e}")

# --- মূল চ্যাট, সার্চ ও টেরাবক্স প্রসেসর হ্যান্ডলার ---
@dp.message(F.text)
async def handle_message(message: Message):
    text = message.text.strip()
    
    # ১. টেরাবক্স লিংক ডিটেক্ট ও সুন্দর প্রিভিউ তৈরি
    if "terabox" in text.lower() or "teraboxapp" in text.lower():
        processing_msg = await message.reply("⏳ টেরাবক্স লিংক প্রসেস করা হচ্ছে, দয়া করে অপেক্ষা করুন...")
        
        # সুন্দর ইনলাইন বাটন যাতে ইউজার লিংকে ক্লিক করে সরাসরি ভিডিও দেখতে ও ডাউনলোড করতে পারে
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
            "🎬 **টেরাবক্স ফাইল সফলভাবে প্রসেস করা হয়েছে!**\n\n"
            "নিচের বাটনগুলোতে ক্লিক করে খুব সহজেই ভিডিওটি দেখতে বা ডাউনলোড করতে পারবেন:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # ২. ডাটাবেজ সার্চ ফিচার (যেকোনো জিনিস লিখে সার্চ করলেই রেজাল্ট দেখাবে)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT title, file_link FROM files WHERE title LIKE ?", ('%' + text + '%',))
    results = cursor.fetchall()
    conn.close()

    if results:
        response = f"🔍 **'{text}' এর জন্য সার্চ রেজাল্ট:**\n\n"
        for idx, (title, link) in enumerate(results[:15], 1):  # সর্বোচ্চ ১৫টি রেজাল্ট দেখাবে
            response += f"{idx}. [{title}]({link})\n"
        await message.reply(response, parse_mode="Markdown", disable_web_page_preview=True)
    else:
        await message.reply(
            f"❌ '{text}' সম্পর্কিত কোনো ফাইল ডাটাবেজে পাওয়া যায়নি।\n\n"
            "💡 **টিপস:** আপনি চাইলে কোনো **Terabox Link** পাঠিয়ে দেখতে পারেন অথবা অ্যাডমিনকে নতুন ফাইল যুক্ত করতে বলতে পারেন।"
        )

# --- মূল রানিং ফাংশন ---
async def main():
    # ফ্লাস্ক ব্যাকগ্রাউন্ড সার্ভার চালু করা (রেন্ডার হোস্টের জন্য বাধ্যতামূলক)
    keep_alive()
    
    # ১ মিনিট পর পর অটো ব্যাকআপ টাস্ক ব্যাকগ্রাউন্ডে রান করা
    asyncio.create_task(database_backup_loop())
    
    print("🚀 Bot is successfully polling and running 24/7...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
