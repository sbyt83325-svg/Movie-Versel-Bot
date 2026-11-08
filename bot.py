import asyncio
import logging
import os
import re
import shutil
from datetime import datetime

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from terabox_downloader import TeraboxDL

# -------------------------------------------------------------------
#  Configuration
# -------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8751100050:AAF4Vunr7OT-H0WZySy4p6UH16Cyt693gsI")
ADMIN_ID = int(os.getenv("ADMIN_ID", 7718164345))
# Make sure this environment variable is set in Render, e.g., https://my-bot.onrender.com
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_URL", "https://your-service.onrender.com")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"

TERABOX_COOKIE = os.getenv("TERABOX_COOKIE", "") 

DB_PATH = "bot_database.db"
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
#  Bot & Dispatcher Initialization
# -------------------------------------------------------------------
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# -------------------------------------------------------------------
#  Database Setup (SQLite + FTS5)
# -------------------------------------------------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                message_id INTEGER,
                title TEXT,
                content TEXT,
                link TEXT,
                kind TEXT DEFAULT 'file',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
                title, content, link, content='items', content_rowid='id'
            )
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
                INSERT INTO items_fts(rowid, title, content, link)
                VALUES (new.id, new.title, new.content, new.link);
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
                INSERT INTO items_fts(items_fts, rowid, title, content, link)
                VALUES ('delete', old.id, old.title, old.content, old.link);
            END
        """)
        await db.commit()
        logger.info("✅ Database initialised.")

async def index_item(chat_id: int, message_id: int, title: str, content: str = "", link: str = "", kind: str = "file"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO items (chat_id, message_id, title, content, link, kind)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, message_id, title, content, link, kind),
        )
        await db.commit()

async def search_items(query: str, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT i.id, i.title, i.link, i.kind
               FROM items_fts f
               JOIN items i ON f.rowid = i.id
               WHERE items_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        )
        return await cursor.fetchall()

# -------------------------------------------------------------------
#  Terabox Handler
# -------------------------------------------------------------------
TERABOX_PATTERN = re.compile(r"(terabox|teraboxapp)", re.IGNORECASE)

async def handle_terabox_link(message: types.Message, link: str):
    if not TERABOX_COOKIE:
        await message.reply("⚠️ Terabox কুকি সেট করা হয়নি। অনুগ্রহ করে অ্যাডমিনকে জানান।")
        return

    terabox = TeraboxDL(TERABOX_COOKIE)
    try:
        info = terabox.get_file_info(link, direct_url=True)
    except Exception as exc:
        logger.exception("Terabox error")
        await message.reply(f"❌ Terabox লিঙ্ক প্রসেস করতে সমস্যা হয়েছে: {exc}")
        return

    if "error" in info:
        await message.reply(f"❌ Terabox এরর: {info['error']}")
        return

    download_link = info.get("download_link", "")
    stream_link = info.get("stream_link") or download_link

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 সরাসরি ডাউনলোড করুন", url=download_link)],
            [InlineKeyboardButton(text="▶️ অনলাইন ভিডিও দেখুন", url=stream_link)],
        ]
    )

    await message.reply(
        f"<b>🎬 {info.get('file_name', 'Terabox File')}</b>\n"
        f"📦 সাইজ: {info.get('file_size', 'N/A')}\n\n"
        f"নিচের বাটন থেকে ডাউনলোড বা স্ট্রিম করুন:",
        reply_markup=keyboard,
    )

# -------------------------------------------------------------------
#  Bot Handlers
# -------------------------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📂 সব ফাইল", callback_data="cat_all")],
            [InlineKeyboardButton(text="🎬 ভিডিও কন্টেন্ট", callback_data="cat_video")],
            [InlineKeyboardButton(text="📢 চ্যানেল ও গ্রুপ", callback_data="cat_channel")],
            [InlineKeyboardButton(text="⭐ টেরাবক্স ডাউনলোডার", callback_data="cat_terabox")],
        ]
    )
    await message.answer(
        "👋 <b>স্বাগতম!</b>\n\n"
        "আমি একটি অটোমেটিক সার্চ ইঞ্জিন ও মিডিয়া ডাউনলোডার বট।\n"
        "যেকোনো কীওয়ার্ড সার্চ করতে <code>/search &lt;কীওয়ার্ড&gt;</code> ব্যবহার করুন।\n"
        "অথবা নিচের মেনু থেকে ক্যাটাগরি বেছে নিন।",
        reply_markup=keyboard,
    )

@dp.callback_query(F.data.startswith("cat_"))
async def handle_category(callback: types.CallbackQuery):
    category = callback.data.split("_")[1]
    if category == "terabox":
        await callback.message.answer(
            "🔗 <b>টেরাবক্স ডাউনলোডার</b>\n\n"
            "অনুগ্রহ করে একটি Terabox লিঙ্ক পাঠান (যেমন: https://www.terabox.app/s/... )"
        )
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT title, link FROM items WHERE kind = ? ORDER BY id DESC LIMIT 10",
                (category,),
            )
            rows = await cursor.fetchall()
        if not rows:
            await callback.message.answer("📭 এই ক্যাটাগরিতে কোনো আইটেম নেই।")
        else:
            text = "\n".join(f"{i+1}. <a href='{row[1]}'>{row[0]}</a>" for i, row in enumerate(rows))
            await callback.message.answer(f"<b>{category.capitalize()} আইটেম:</b>\n{text}")

    await callback.answer()

@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    query = message.text.replace("/search", "").strip()
    if not query:
        await message.reply("🔍 অনুগ্রহ করে একটি কীওয়ার্ড দিন। উদাহরণ: <code>/search movie</code>")
        return

    rows = await search_items(query)
    if not rows:
        await message.reply("❌ কোনো ফলাফল পাওয়া যায়নি।")
        return

    lines = [f"{idx}. <a href='{link}'>{title}</a> <i>({kind})</i>" for idx, (_, title, link, kind) in enumerate(rows, start=1)]
    await message.reply(f"<b>🔎 সার্চ ফলাফল – “{query}”</b>\n\n" + "\n".join(lines), disable_web_page_preview=True)

@dp.message()
async def auto_index(message: types.Message):
    text = message.text or message.caption or ""
    if not text:
        return

    if TERABOX_PATTERN.search(text):
        urls = re.findall(r"https?://\S+", text)
        if urls:
            await handle_terabox_link(message, urls[0])
            return

    title = text.split("\n")[0][:100]
    link_match = re.search(r"https?://\S+", text)
    link = link_match.group(0) if link_match else ""
    kind = "file"
    if "video" in text.lower() or "movie" in text.lower():
        kind = "video"
    elif "channel" in text.lower() or "group" in text.lower() or "@" in text:
        kind = "channel"

    await index_item(
        chat_id=message.chat.id,
        message_id=message.message_id,
        title=title,
        content=text,
        link=link,
        kind=kind,
    )
    logger.info(f"📥 Indexed: {title[:50]}")

# -------------------------------------------------------------------
#  Automated Backup Loop
# -------------------------------------------------------------------
async def backup_loop():
    while True:
        await asyncio.sleep(60)  # 1 minute
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(BACKUP_DIR, f"bot_database_{timestamp}.db")
            shutil.copy2(DB_PATH, backup_path)

            with open(backup_path, "rb") as f:
                await bot.send_document(
                    chat_id=ADMIN_ID,
                    document=types.InputFile(f, filename=f"backup_{timestamp}.db"),
                    caption=f"🗄️ ডেটাবেস ব্যাকআপ\n⏰ {timestamp}",
                )

            os.remove(backup_path)
            logger.info(f"✅ Backup sent: {backup_path}")
        except Exception as exc:
            logger.exception("Backup failed")

# -------------------------------------------------------------------
#  Startup/Shutdown Webhook Logic
# -------------------------------------------------------------------
async def on_startup(bot: Bot):
    await init_db()
    # Start the backup loop inside the main event loop
    asyncio.create_task(backup_loop())
    # Set Webhook
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"🚀 Webhook set to {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logger.info("🛑 Webhook deleted")

# -------------------------------------------------------------------
#  Main Entry Point (aiohttp Web Server for Render)
# -------------------------------------------------------------------
def main():
    # Create the aiohttp web application
    app = web.Application()

    # Set up the webhook request handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    # Set up startup and shutdown hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    setup_application(app, dp, bot=bot)

    # Route for Render health check
    app.router.add_get("/", lambda r: web.Response(text="Bot is running!"))

    # Bind to Render's assigned PORT (default is 10000)
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🌐 Starting web server on port {port}...")
    
    # Run the web application (This blocks the main thread, which is correct for Render)
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
