import sys
import logging
import concurrent.futures
import random
import time
import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.error import BadRequest, TelegramError
from telegram.request import HTTPXRequest

# Python 3.14+ compatibility patch without breaking properties
try:
    if not hasattr(asyncio, 'coroutine'):
        asyncio.coroutine = lambda f: f
except Exception:
    pass

from mega import Mega

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

EMAIL, PASSWORD = range(2)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "@NEWSBYLAILA")
ADMIN_ID = 123456789  # <--- Apni ID check kar lena bhai

USER_DB_FILE = "users.txt"
GLOBAL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)
ACTIVE_TASKS = {}

# --- FIXED WEB SERVER FOR RENDER & UPTIME ROBOT (RETURNS 200 OK EVERYTIME) ---
class RenderHealthServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Bot Engine Online")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def log_message(self, format, *args):
        return  # Server logs clean rakhne ke liye

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), RenderHealthServer)
    logging.info(f"[+] Render Web Server started on port {port}")
    server.serve_forever()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def add_user_to_db(user_id: int):
    user_id_str = str(user_id)
    if not os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, "w") as f:
            f.write(user_id_str + "\n")
        return
    with open(USER_DB_FILE, "r") as f:
        users = f.read().splitlines()
    if user_id_str not in users:
        with open(USER_DB_FILE, "a") as f:
            f.write(user_id_str + "\n")

def get_total_users() -> list:
    if not os.path.exists(USER_DB_FILE):
        return []
    with open(USER_DB_FILE, "r") as f:
        return f.read().splitlines()

async def is_user_subbed(bot, user_id: int) -> bool:
    if not UPDATE_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=UPDATE_CHANNEL, user_id=user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return False

async def send_force_join_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_url = f"https://t.me/{UPDATE_CHANNEL.replace('@', '')}"
    keyboard = [[InlineKeyboardButton("📢 Join Channel to Unlock", url=channel_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = (
        "👑 <b>Premium Access Locked</b>\n\n"
        f"Is high-speed advanced renamer bot ko use karne ke liye hamare official network channel <code>{UPDATE_CHANNEL}</code> ko join karein."
    )
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode="HTML")

def make_progress_bar(done, total=100):
    if total == 0:
        total = 100
    percentage = min(int((done / total) * 100), 100)
    block = int(percentage / 10)
    bar = "💎" * block + "░" * (10 - block)
    return f"<code>{bar}</code> <b>{percentage}%</b>"

def format_time(seconds):
    if seconds is None or seconds < 0:
        return "Calculating..."
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"

async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "🚀 Bot ka welcome menu dekhein"),
        BotCommand("login", "🔒 MEGA account link/login karein"),
        BotCommand("replace", "✏️ Format: /replace old_text new_text"),
        BotCommand("fullrename", "📝 Poore drive ki sabhi files ka naam ek sath badlein"),
        BotCommand("logout", "🔒 MEGA account unlink / logout karein"),
        BotCommand("cancel", "❌ Chalu setup ya operation ko cancel karein"),
        BotCommand("users", "📊 Total users dekhein (👑 Admin Only)"),
        BotCommand("broadcast", "📢 Sabhi users ko message bhejein (👑 Admin Only)")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user_to_db(user_id)

    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return

    name = update.effective_user.first_name
    welcome_text = (
        f"👋 <b>Hello, {name}!</b>\n\n"
        "🚀 <b>MEGA BULK RENAMER v2.6</b>\n"
        "⚡ <i>Cloud Hyper Turbo Engine Connected (Render Platform)</i>\n\n"
        "<code>┌──────────────────────────┐\n"
        "  • /login      - Connect MEGA Drive\n"
        "  • /replace    - Replace Specific Text\n"
        "  • /fullrename - Overwrite All Names\n"
        "  • /logout     - Disconnect Drive\n"
        "└──────────────────────────┘</code>\n\n"
        "📋 <b>How to Use:</b>\n"
        "1. Pehle <code>/login</code> bhejkar drive connect karein.\n"
        "2. Text badalne ke liye: <code>/replace purana naya</code>\n"
        "3. Saari files rename karne ke liye: <code>/fullrename naya</code>"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def users_count_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ <b>Access Denied:</b> You are not the admin.", parse_mode="HTML")
        return
    all_users = get_total_users()
    await update.message.reply_text(f"📊 <b>Bot Users Statistics:</b>\n\n👥 Total Registered Users: <code>{len(all_users)}</code>", parse_mode="HTML")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ <b>Access Denied:</b> You are not the admin.", parse_mode="HTML")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ <b>Format:</b> Kisi bhi message ko reply karke <code>/broadcast</code> likhein.", parse_mode="HTML")
        return

    broadcast_msg = update.message.reply_to_message
    all_users = get_total_users()
    
    if not all_users:
        await update.message.reply_text("❌ Database mein koi user nahi mila.", parse_mode="HTML")
        return

    status_msg = await update.message.reply_text("📢 <b>Broadcasting started to users...</b>", parse_mode="HTML")
    success, failed = 0, 0
    
    for uid in all_users:
        try:
            await context.bot.copy_message(chat_id=int(uid), from_chat_id=update.effective_chat.id, message_id=broadcast_msg.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"🏁 <b>Broadcast Completed!</b>\n\n"
        f"✅ Successfully Sent: <code>{success}</code>\n"
        f"❌ Failed/Blocked: <code>{failed}</code>",
        parse_mode="HTML"
    )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return ConversationHandler.END

    if 'mega_instance' in context.user_data:
        email_clean = context.user_data.get('email')
        await update.message.reply_text(f"ℹ️ Aap pehle se <code>{email_clean}</code> account se logged in hain.", parse_mode="HTML")
        return ConversationHandler.END

    await update.message.reply_text("🔒 <b>MEGA.nz Login Setup</b>\n\nEnter your MEGA.nz email address:", parse_mode="HTML")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_email'] = update.message.text.strip()
    await update.message.reply_text("🔑 Now, enter your MEGA password:", parse_mode="HTML")
    return PASSWORD

def bg_login(email, password):
    mega = Mega()
    m = mega.login(email, password)
    all_nodes = m.get_files()
    total_files = sum(1 for n in all_nodes.values() if n.get('t') == 0)
    return m, total_files

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    email = context.user_data.get('temp_email')
    status_msg = await update.message.reply_text("🔐 <b>Establishing Secure SSL Connection to MEGA...</b>", parse_mode="HTML")

    try:
        loop = asyncio.get_running_loop()
        m, total_files = await loop.run_in_executor(GLOBAL_EXECUTOR, bg_login, email, password)

        context.user_data['mega_instance'] = m
        context.user_data['email'] = email
        context.user_data['total_files'] = total_files

        await status_msg.edit_text(
            "<code>┌──────────────────────────┐\n"
            "  ✅ CONNECTED SUCCESSFULLY\n"
            "└──────────────────────────┘</code>\n\n"
            f"📧 <b>Account:</b> <code>{email}</code>\n"
            f"📦 <b>Total Files Indexed:</b> <code>{total_files}</code>\n\n"
            "👉 Ab aap direct <code>/replace</code> ya <code>/fullrename</code> use kar sakte hain!",
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Login Matrix Failed:</b> {str(e)}", parse_mode="HTML")

    if 'temp_email' in context.user_data:
        del context.user_data['temp_email']
    return ConversationHandler.END

async def cancel_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("cancel_"):
        task_id = query.data.split("_")[1]
        ACTIVE_TASKS[task_id] = False
        await query.message.edit_text("🛑 <b>Termination signal sent to engine. Stopping tasks...</b>", parse_mode="HTML")

def core_replace_engine(m, find_text, replace_text, msg_id, chat_id, bot, loop, task_key):
    try:
        start_time = time.time()
        all_nodes = m.get_files()
        matching_nodes = [
            (nid, ndat, ndat.get('a', {}).get('n', ''))
            for nid, ndat in all_nodes.items()
            if ndat.get('t') == 0 and ndat.get('p') != '' and ndat.get('h') != '' and find_text in ndat.get('a', {}).get('n', '')
        ]

        if not matching_nodes:
            asyncio.run_coroutine_threadsafe(bot.edit_message_text("❌ <b>Engine Report:</b> No target text matching found inside drive.", chat_id, msg_id, parse_mode="HTML"), loop)
            return

        rename_count = 0
        total_to_process = len(matching_nodes)

        def rename_single(node_info):
            nonlocal rename_count
            if not ACTIVE_TASKS.get(task_key, True): return False
            n_id, n_data, curr_name = node_info
            new_name = curr_name.replace(find_text, replace_text) or "Unnamed_File"
            
            while ACTIVE_TASKS.get(task_key, True):
                try:
                    m.rename((n_id, n_data), new_name)
                    rename_count += 1
                    return True
                except Exception:
                    new_name = f"{random.randint(10,99)}_{new_name}"
                    remaining = total_to_process - rename_count
                    sleep_time = random.uniform(0.3, 0.8) if remaining > 15 else random.uniform(1.2, 2.5)
                    time.sleep(sleep_time)
            return False

        workers = 25 if total_to_process > 15 else 4
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as file_executor:
            futures = [file_executor.submit(rename_single, node) for node in matching_nodes]
            last_rep = 0
            for _ in concurrent.futures.as_completed(futures):
                if not ACTIVE_TASKS.get(task_key, True): break
                
                remaining_live = total_to_process - rename_count
                if remaining_live <= 15 and file_executor._max_workers > 4:
                    file_executor._max_workers = 4

                if rename_count % 40 == 0 and rename_count != last_rep:
                    last_rep = rename_count

                    elapsed_time = time.time() - start_time
                    speed = rename_count / elapsed_time if elapsed_time > 0 else 0
                    estimated_time = remaining_live / speed if speed > 0 else None

                    p_bar = make_progress_bar(rename_count, total_to_process)
                    text = (
                        "⚡ <b>Cloud Engine Active (25x)...</b>\n\n"
                        f"📈 Progress: {p_bar}\n"
                        f"✅ Processed Successfully: <code>{rename_count}/{total_to_process}</code> files\n"
                        f"⏱️ Time Elapsed: <code>{format_time(elapsed_time)}</code>\n"
                        f"⏳ Time Estimated: <code>{format_time(estimated_time)}</code>"
                    )
                    kb = [[InlineKeyboardButton("🛑 Terminate Action", callback_data=f"cancel_{task_key}")]]
                    asyncio.run_coroutine_threadsafe(bot.edit_message_text(text, chat_id, msg_id, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"), loop)

        if ACTIVE_TASKS.get(task_key, True):
            asyncio.run_coroutine_threadsafe(bot.edit_message_text(
                "<code>┌──────────────────────────┐\n"
                "  🏁 MISSION COMPLETE\n"
                "└──────────────────────────┘</code>\n\n"
                f"✨ Processed Files: <code>{rename_count}</code>\n"
                f"⏱️ Total Time Taken: <code>{format_time(time.time() - start_time)}</code>", 
                chat_id, msg_id, parse_mode="HTML"
            ), loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"❌ <b>Engine Interrupt Error:</b> {str(e)}", chat_id, msg_id, parse_mode="HTML"), loop)

async def replace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'mega_instance' not in context.user_data:
        await update.message.reply_text("❌ Pehle <code>/login</code> command se login karein!", parse_mode="HTML")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ <b>Format:</b> <code>/replace old_text new_text</code>", parse_mode="HTML")
        return

    find_text = str(context.args[0])
    replace_text = "" if str(context.args[1]).lower() == "blank" else str(context.args[1])
    m = context.user_data['mega_instance']

    progress_msg = await update.message.reply_text("🌀 <b>Initializing Premium Replacer Sub-Routine Pipeline...</b>", parse_mode="HTML")

    loop = asyncio.get_running_loop()
    bot = context.bot
    chat_id = update.effective_chat.id
    task_key = f"{chat_id}_{random.randint(1000,9999)}"
    ACTIVE_TASKS[task_key] = True

    loop.run_in_executor(GLOBAL_EXECUTOR, core_replace_engine, m, find_text, replace_text, progress_msg.message_id, chat_id, bot, loop, task_key)

def core_fullrename_engine(m, target_name, msg_id, chat_id, bot, loop, task_key):
    try:
        start_time = time.time()
        all_nodes = m.get_files()
        all_files = [
            (nid, ndat, ndat.get('a', {}).get('n', ''))
            for nid, ndat in all_nodes.items()
            if ndat.get('t') == 0 and ndat.get('p') != '' and ndat.get('h') != ''
        ]

        if not all_files:
            asyncio.run_coroutine_threadsafe(bot.edit_message_text("❌ <b>Drive empty!</b>", chat_id, msg_id, parse_mode="HTML"), loop)
            return

        rename_count = 0
        total_to_process = len(all_files)
        indexed_nodes = [(n[0], n[1], n[2], idx) for idx, n in enumerate(all_files, start=1)]

        def rename_absolute(node_info):
            nonlocal rename_count
            if not ACTIVE_TASKS.get(task_key, True): return False
            n_id, n_data, curr_name, s_num = node_info
            parts = curr_name.split('.')
            ext = parts[-1] if len(parts) > 1 else ""
            new_name = f"{target_name}_{s_num}.{ext}" if ext else f"{target_name}_{s_num}"

            while ACTIVE_TASKS.get(task_key, True):
                try:
                    m.rename((n_id, n_data), new_name)
                    rename_count += 1
                    return True
                except Exception:
                    new_name = f"{target_name}_{s_num}_{random.randint(10,99)}.{ext}" if ext else f"{target_name}_{s_num}_{random.randint(10,99)}"
                    remaining = total_to_process - rename_count
                    sleep_time = random.uniform(0.3, 0.8) if remaining > 15 else random.uniform(1.2, 2.5)
                    time.sleep(sleep_time)
            return False

        workers = 25 if total_to_process > 15 else 4
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as file_executor:
            futures = [file_executor.submit(rename_absolute, node) for node in indexed_nodes]
            last_rep = 0
            for _ in concurrent.futures.as_completed(futures):
                if not ACTIVE_TASKS.get(task_key, True): break
                
                remaining_live = total_to_process - rename_count
                if remaining_live <= 15 and file_executor._max_workers > 4:
                    file_executor._max_workers = 4

                if rename_count % 40 == 0 and rename_count != last_rep:
                    last_rep = rename_count

                    elapsed_time = time.time() - start_time
                    speed = rename_count / elapsed_time if elapsed_time > 0 else 0
                    estimated_time = remaining_live / speed if speed > 0 else None

                    p_bar = make_progress_bar(rename_count, total_to_process)
                    text = (
                        "⚡ <b>Bulk System Overwriting Names...</b>\n\n"
                        f"📈 Progress: {p_bar}\n"
                        f"✅ Overwritten: <code>{rename_count}/{total_to_process}</code> files\n"
                        f"⏱️ Time Elapsed: <code>{format_time(elapsed_time)}</code>\n"
                        f"⏳ Time Estimated: <code>{format_time(estimated_time)}</code>"
                    )
                    kb = [[InlineKeyboardButton("🛑 Terminate Action", callback_data=f"cancel_{task_key}")]]
                    asyncio.run_coroutine_threadsafe(bot.edit_message_text(text, chat_id, msg_id, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"), loop)

        if ACTIVE_TASKS.get(task_key, True):
            asyncio.run_coroutine_threadsafe(bot.edit_message_text(
                "<code>┌──────────────────────────┐\n"
                "  🏁 FULL OVERWRITE FINISHED\n"
                "└──────────────────────────┘</code>\n\n"
                f"✨ Total Handled: <code>{rename_count}</code> nodes.\n"
                f"⏱️ Total Time Taken: <code>{format_time(time.time() - start_time)}</code>", 
                chat_id, msg_id, parse_mode="HTML"
            ), loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"❌ <b>Error:</b> {str(e)}", chat_id, msg_id, parse_mode="HTML"), loop)

async def fullrename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'mega_instance' not in context.user_data:
        await update.message.reply_text("❌ Pehle <code>/login</code> command se login karein!", parse_mode="HTML")
        return

    if not context.args:
        await update.message.reply_text("⚠️ <b>Format:</b> <code>/fullrename naya_naam</code>", parse_mode="HTML")
        return

    target_name = " ".join(context.args).strip()
    m = context.user_data['mega_instance']

    progress_msg = await update.message.reply_text("🌀 <b>Initializing Absolute Overwrite Engine Matrix...</b>", parse_mode="HTML")

    loop = asyncio.get_running_loop()
    bot = context.bot
    chat_id = update.effective_chat.id
    task_key = f"{chat_id}_{random.randint(1000,9999)}"
    ACTIVE_TASKS[task_key] = True

    loop.run_in_executor(GLOBAL_EXECUTOR, core_fullrename_engine, m, target_name, progress_msg.message_id, chat_id, bot, loop, task_key)

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔒 <b>Logged Out Successfully!</b>", parse_mode="HTML")

async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ <b>Login setup ya operational cache cancel kar diya gaya hai.</b>", parse_mode="HTML")
    return ConversationHandler.END

def main():
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or not BOT_TOKEN:
        print("[!] ERROR: BOT_TOKEN is missing or not set!")
        sys.exit(1)

    # Start FIXED HTTP Web Server 
    server_thread = threading.Thread(target=run_health_server, daemon=True)
    server_thread.start()

    custom_request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(BOT_TOKEN).request(custom_request).post_init(post_init).build()

    login_conv = ConversationHandler(
        entry_points=[CommandHandler('login', login_command, block=False)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email, block=False)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password, block=False)],
        },
        fallbacks=[CommandHandler('cancel', cancel_setup, block=False)],
    )

    app.add_handler(login_conv)
    app.add_handler(CommandHandler('start', start, block=False))
    app.add_handler(CommandHandler('replace', replace_command, block=False))
    app.add_handler(CommandHandler('fullrename', fullrename_command, block=False))
    app.add_handler(CommandHandler('logout', logout_command, block=False))
    app.add_handler(CommandHandler('users', users_count_command, block=False))
    app.add_handler(CommandHandler('broadcast', broadcast_command, block=False))
    app.add_handler(CallbackQueryHandler(cancel_callback_handler, block=False))

    print("[+] Render Live Engine Starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
