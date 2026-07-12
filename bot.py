import sys
import logging
import concurrent.futures
import random
import time
import asyncio
import os
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

# Python 3.13 asyncio.coroutine compatibility patch for older tenacity/mega versions
if not hasattr(asyncio, 'coroutine'):
    import types
    def dummy_coroutine(f):
        return f
    asyncio.coroutine = dummy_coroutine

from mega import Mega
from h11 import Response

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Conversation States for Login Workflow
EMAIL, PASSWORD = range(2)

# --- Configuration Constants ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "@NEWSBYLAILA")

# 👑 ADMIN SYSTEM SETUP
ADMIN_ID = 8474134621  # <--- IS NUMBER KO APNI ID SE BADLEIN

# Text file to store user IDs database locally in Termux / Render
USER_DB_FILE = "users.txt"

# Dynamic Multi-User Parallel Engine Execution Pools
GLOBAL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=100)
ACTIVE_TASKS = {}

# --- DUMMY WEB SERVER FOR RENDER 24/7 ALIVE HACK ---
async def handle_ping(reader, writer):
    """Render ke port request ko standard HTTP response dekar zinda rakhne ke liye"""
    raw_request = await reader.read(1024)
    response = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html\r\n"
        "Content-Length: 26\r\n"
        "Connection: close\r\n"
        "\r\n"
        "<h1>MEGA Renamer Is Live</h1>"
    )
    writer.write(response.encode('utf-8'))
    await writer.drain()
    writer.close()
    await writer.wait_closed()

async def start_web_server():
    """Render mandatory port mapping setup"""
    port = int(os.environ.get("PORT", 8080))
    server = await asyncio.start_server(handle_ping, "0.0.0.0", port)
    logging.info(f"🌐 [RENDER SHIELD] Dummy Web Portal Active On Port: {port}")
    async with server:
        await server.serve_forever()

# --- ADMIN VERIFICATION CHECK ---
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# --- USER DB MANAGEMENT FUNCTIONS ---
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

# --- FORCE JOIN VERIFICATION ---
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
        "👑 <b>Premium Access Locked!</b>\n\n"
        f"Is high-speed advanced renamer bot ko use karne ke liye hamare official network channel <code>{UPDATE_CHANNEL}</code> ko join karein."
    )
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode="HTML")

# --- PREMIUM DYNAMIC PROGRESS BAR ---
def make_progress_bar(done, total=100):
    if total == 0:
        total = 100
    percentage = min(int((done / total) * 100), 100)
    block = int(percentage / 10)
    bar = "💎" * block + "░" * (10 - block)
    return f"<code>{bar}</code>  <b>{percentage}%</b>"

# --- MATHEMATICAL TIME FORMATTER ---
def format_time(seconds):
    if seconds is None or seconds < 0:
        return "Calculating..."
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"

# --- BOT INTERFACE COMMANDS CONFIG ---
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

    welcome_text = (
        f"👋 <b>Hello, {update.effective_user.first_name}!</b>\n\n"
        "🚀 <b>Fast Global Bulk Renamer Bot (Premium Engine)</b>.\n"
        "Ab yeh bot dynamic time prediction, premium diamond bar aur non-blocking multi-user tech par chalta hai!\n\n"
        "📋 <b>How to Use:</b>\n"
        "1. Pehle <code>/login</code> command bhejkar apna MEGA drive connect karein.\n"
        "2. Text badalne ke liye: <code>/replace purana_naam naya_naam</code>\n"
        "3. Drive ki saari files ka ek naam karne ke liye bhejye: <code>/fullrename naya_naam</code>"
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
        await update.message.reply_text("⚠️ <b>Format:</b> Reply to a message with <code>/broadcast</code>", parse_mode="HTML")
        return

    broadcast_msg = update.message.reply_to_message
    all_users = get_total_users()
    
    if not all_users:
        await update.message.reply_text("❌ Database empty.", parse_mode="HTML")
        return

    status_msg = await update.message.reply_text(f"📢 <b>Broadcasting starting...</b>", parse_mode="HTML")
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

# --- LOGIN STEP-BY-STEP CONVERSATION WORKFLOW ---
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return ConversationHandler.END

    if 'mega_instance' in context.user_data:
        await update.message.reply_text(f"ℹ️ Already logged in as <code>{context.user_data.get('email')}</code>.", parse_mode="HTML")
        return ConversationHandler.END

    await update.message.reply_text("🔒 <b>MEGA.nz Login</b>\n\nEnter your email:", parse_mode="HTML")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_email'] = update.message.text.strip()
    await update.message.reply_text("🔑 Enter password:", parse_mode="HTML")
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
    status_msg = await update.message.reply_text("🔐 <b>Connecting to MEGA...</b>", parse_mode="HTML")

    try:
        loop = asyncio.get_running_loop()
        m, total_files = await loop.run_in_executor(GLOBAL_EXECUTOR, bg_login, email, password)

        context.user_data['mega_instance'] = m
        context.user_data['email'] = email
        context.user_data['total_files'] = total_files

        await status_msg.edit_text(
            f"✅ <b>Connected Successfully!</b>\n\n"
            f"📧 <b>Account:</b> <code>{email}</code>\n"
            f"📦 <b>Indexed:</b> <code>{total_files}</code> files",
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Login Failed:</b> {str(e)}", parse_mode="HTML")

    if 'temp_email' in context.user_data:
        del context.user_data['temp_email']
    return ConversationHandler.END

async def cancel_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("cancel_"):
        task_id = query.data.split("_")[1]
        ACTIVE_TASKS[task_id] = False
        await query.message.edit_text("🛑 <b>Termination signal sent. Stopping engine...</b>", parse_mode="HTML")

# --- CORE PARALLEL TEXT REPLACER PIPELINE ---
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
            asyncio.run_coroutine_threadsafe(bot.edit_message_text("❌ No matching files found.", chat_id, msg_id, parse_mode="HTML"), loop)
            return

        rename_count = 0
        total_to_process = len(matching_nodes)

        def rename_single(node_info):
            nonlocal rename_count
            if not ACTIVE_TASKS.get(task_key, True):
                return False
            n_id, n_data, curr_name = node_info
            new_name = curr_name.replace(find_text, replace_text) or "Unnamed_File"
            while ACTIVE_TASKS.get(task_key, True):
                try:
                    m.rename((n_id, n_data), new_name)
                    rename_count += 1
                    return True
                except Exception:
                    new_name = f"{random.randint(100,999)}_{new_name}"
                    time.sleep(1.5)
            return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as file_executor:
            futures = [file_executor.submit(rename_single, node) for node in matching_nodes]
            last_rep = 0
            for _ in concurrent.futures.as_completed(futures):
                if not ACTIVE_TASKS.get(task_key, True):
                    break
                # Live dynamic display configuration
                if rename_count % 5 == 0 and rename_count != last_rep:
                    last_rep = rename_count
                    elapsed_time = time.time() - start_time
                    speed = rename_count / elapsed_time if elapsed_time > 0 else 0
                    remaining_files = total_to_process - rename_count
                    estimated_time = remaining_files / speed if speed > 0 else None

                    p_bar = make_progress_bar(rename_count, total_to_process)
                    text = (
                        f"⚡ <b>Premium Engine Executing Tasks...</b>\n\n"
                        f"📈 Progress: {p_bar}\n"
                        f"✅ Processed: <code>{rename_count}/{total_to_process}</code> files\n"
                        f"⏱️ Time Elapsed: <code>{format_time(elapsed_time)}</code>\n"
                        f"⏳ Time Remaining: <code>{format_time(estimated_time)}</code>"
                    )
                    kb = [[InlineKeyboardButton("🛑 Terminate Action", callback_data=f"cancel_{task_key}")]]
                    asyncio.run_coroutine_threadsafe(bot.edit_message_text(text, chat_id, msg_id, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"), loop)

        if ACTIVE_TASKS.get(task_key, True):
            asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"🏁 <b>Mission Complete!</b>\n\n✨ Processed Files: <code>{rename_count}</code>\n⏱️ Total Time Taken: <code>{format_time(time.time() - start_time)}</code>", chat_id, msg_id, parse_mode="HTML"), loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"❌ <b>Error:</b> {str(e)}", chat_id, msg_id, parse_mode="HTML"), loop)

async def replace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'mega_instance' not in context.user_data:
        await update.message.reply_text("❌ Login required via <code>/login</code>!", parse_mode="HTML")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Format: <code>/replace old_text new_text</code>", parse_mode="HTML")
        return

    find_text = str(context.args[0])
    replace_text = "" if str(context.args[1]).lower() == "blank" else str(context.args[1])
    m = context.user_data['mega_instance']

    progress_msg = await update.message.reply_text("🌀 <b>Initializing Progress Engine Subroutine...</b>", parse_mode="HTML")

    loop = asyncio.get_running_loop()
    bot = context.bot
    chat_id = update.effective_chat.id
    task_key = f"{chat_id}_{random.randint(1000,9999)}"
    ACTIVE_TASKS[task_key] = True

    loop.run_in_executor(GLOBAL_EXECUTOR, core_replace_engine, m, find_text, replace_text, progress_msg.message_id, chat_id, bot, loop, task_key)

# --- CORE PARALLEL FULL OVERWRITE ENGINE PIPELINE ---
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
            asyncio.run_coroutine_threadsafe(bot.edit_message_text("❌ Drive empty!", chat_id, msg_id, parse_mode="HTML"), loop)
            return

        rename_count = 0
        total_to_process = len(all_files)
        indexed_nodes = [(n[0], n[1], n[2], idx) for idx, n in enumerate(all_files, start=1)]

        def rename_absolute(node_info):
            nonlocal rename_count
            if not ACTIVE_TASKS.get(task_key, True):
                return False
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
                    new_name = f"{target_name}_{s_num}_{random.randint(100,999)}.{ext}" if ext else f"{target_name}_{s_num}_{random.randint(100,999)}"
                    time.sleep(1.5)
            return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as file_executor:
            futures = [file_executor.submit(rename_absolute, node) for node in indexed_nodes]
            last_rep = 0
            for _ in concurrent.futures.as_completed(futures):
                if not ACTIVE_TASKS.get(task_key, True):
                    break
                if rename_count % 5 == 0 and rename_count != last_rep:
                    last_rep = rename_count
                    elapsed_time = time.time() - start_time
                    speed = rename_count / elapsed_time if elapsed_time > 0 else 0
                    remaining_files = total_to_process - rename_count
                    estimated_time = remaining_files / speed if speed > 0 else None

                    p_bar = make_progress_bar(rename_count, total_to_process)
                    text = (
                        f"⚡ <b>Bulk System Overwriting Names...</b>\n\n"
                        f"📈 Progress: {p_bar}\n"
                        f"✅ Overwritten: <code>{rename_count}/{total_to_process}</code> files\n"
                        f"⏱️ Time Elapsed: <code>{format_time(elapsed_time)}</code>\n"
                        f"⏳ Time Remaining: <code>{format_time(estimated_time)}</code>"
                    )
                    kb = [[InlineKeyboardButton("🛑 Terminate Action", callback_data=f"cancel_{task_key}")]]
                    asyncio.run_coroutine_threadsafe(bot.edit_message_text(text, chat_id, msg_id, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"), loop)

        if ACTIVE_TASKS.get(task_key, True):
            asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"🏁 <b>Full Overwrite Finished Successfully!</b>\n\n✨ Total Handled: <code>{rename_count}</code> nodes.\n⏱️ Total Time Taken: <code>{format_time(time.time() - start_time)}</code>", chat_id, msg_id, parse_mode="HTML"), loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"❌ Error: {str(e)}", chat_id, msg_id, parse_mode="HTML"), loop)

async def fullrename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'mega_instance' not in context.user_data:
        await update.message.reply_text("❌ Login required via <code>/login</code>!", parse_mode="HTML")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format: <code>/fullrename naya_naam</code>", parse_mode="HTML")
        return

    target_exact_name = " ".join(context.args).strip()
    m = context.user_data['mega_instance']

    progress_msg = await update.message.reply_text("🌀 <b>Initializing Absolute Overwrite Engine Matrix...</b>", parse_mode="HTML")

    loop = asyncio.get_running_loop()
    bot = context.bot
    chat_id = update.effective_chat.id
    task_key = f"{chat_id}_{random.randint(1000,9999)}"
    ACTIVE_TASKS[task_key] = True

    loop.run_in_executor(GLOBAL_EXECUTOR, core_fullrename_engine, m, target_exact_name, progress_msg.message_id, chat_id, bot, loop, task_key)

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔒 <b>Logged Out Successfully!</b>", parse_mode="HTML")

async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.", parse_mode="HTML")
    return ConversationHandler.END

# --- APPLICATION RUN ENGINE MAIN COROUTINE ---
async def main_async():
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or not BOT_TOKEN:
        print("[!] ERROR: BOT_TOKEN is missing!")
        sys.exit(1)

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

    # Async Loop integration: Dono Web server aur bot polling saath chalenge
    await app.initialize()
    await app.start()
    
    # Run server task background and polling loop together
    await asyncio.gather(
        start_web_server(),
        app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    )

if __name__ == '__main__':
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[-] Engine Shutdown complete.")
