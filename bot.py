import sys
import logging
import concurrent.futures
import random
import time
import asyncio
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
from telegram.error import BadRequest
from telegram.request import HTTPXRequest
from mega import Mega

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Conversation States for Login Workflow
EMAIL, PASSWORD = range(2)

# Configuration Constants
BOT_TOKEN = os.getenv("BOT_TOKEN")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL")

# Dynamic Multi-User Parallel Engine Execution Pools
GLOBAL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=100)
ACTIVE_TASKS = {}

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
        "👑 **Premium Access Locked!**\n\n"
        f"Is high-speed advanced renamer bot ko use karne ke liye hamare official network channel `{UPDATE_CHANNEL}` ko join karein."
    )
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=reply_markup)

# --- PREMIUM DYNAMIC PROGRESS BAR ---
def make_progress_bar(done, total=100):
    if total == 0:
        total = 100
    percentage = min(int((done / total) * 100), 100)
    block = int(percentage / 10)
    bar = "💎" * block + "░" * (10 - block)
    return f"`{bar}`  **{percentage}%**"

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
        BotCommand("cancel", "❌ Chalu setup ya operation ko cancel karein")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return

    welcome_text = (
        f"👋 **Hello, {update.effective_user.first_name}!**\n\n"
        "🚀 **Fast Global Bulk Renamer Bot (Premium Engine)**.\n"
        "Ab yeh bot dynamic time prediction, premium diamond bar aur non-blocking multi-user tech par chalta hai!\n\n"
        "📋 **How to Use:**\n"
        "1. Pehle **/login** command bhejkar apna MEGA drive connect karein.\n"
        "2. Text badalne ke liye: `/replace purana_naam naya_naam`\n"
        "3. Drive ki saari files ka ek naam karne ke liye bhejye: `/fullrename naya_naam`"
    )
    await update.message.reply_text(welcome_text)

# --- LOGIN STEP-BY-STEP CONVERSATION WORKFLOW ---
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return ConversationHandler.END

    if 'mega_instance' in context.user_data:
        await update.message.reply_text(f"ℹ️ Aap pehle se `{context.user_data.get('email')}` account se logged in hain.")
        return ConversationHandler.END

    await update.message.reply_text("🔒 **MEGA.nz Login Setup**\n\nEnter your MEGA.nz email address:")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_email'] = update.message.text.strip()
    await update.message.reply_text("🔑 Now, enter your MEGA password:")
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
    status_msg = await update.message.reply_text("🔐 **Establishing Secure SSL Connection to MEGA...**")

    try:
        loop = asyncio.get_running_loop()
        m, total_files = await loop.run_in_executor(GLOBAL_EXECUTOR, bg_login, email, password)

        context.user_data['mega_instance'] = m
        context.user_data['email'] = email
        context.user_data['total_files'] = total_files

        await status_msg.edit_text(
            f"✅ **Connected Successfully!**\n\n"
            f"📧 **Account:** `{email}`\n"
            f"📦 **Total Files Indexed:** `{total_files}`\n\n"
            f"👉 Ab aap direct `/replace` ya `/fullrename` use kar sakte hain!"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ **Login Matrix Failed:** {str(e)}")

    if 'temp_email' in context.user_data:
        del context.user_data['temp_email']
    return ConversationHandler.END

# --- ACTION TERMINATION BACKGROUND CALLBACK ---
async def cancel_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("cancel_"):
        task_id = query.data.split("_")[1]
        ACTIVE_TASKS[task_id] = False
        await query.message.edit_text("🛑 **Termination signal sent to engine. Stopping tasks...**")

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
            asyncio.run_coroutine_threadsafe(bot.edit_message_text("❌ **Engine Report:** No target text matching found inside drive.", chat_id, msg_id), loop)
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as file_executor:
            futures = [file_executor.submit(rename_single, node) for node in matching_nodes]
            last_rep = 0
            for _ in concurrent.futures.as_completed(futures):
                if not ACTIVE_TASKS.get(task_key, True):
                    break
                if rename_count % 15 == 0 and rename_count != last_rep:
                    last_rep = rename_count

                    elapsed_time = time.time() - start_time
                    speed = rename_count / elapsed_time if elapsed_time > 0 else 0
                    remaining_files = total_to_process - rename_count
                    estimated_time = remaining_files / speed if speed > 0 else None

                    p_bar = make_progress_bar(rename_count, total_to_process)
                    text = (
                        f"⚡ **Premium Engine Executing Tasks...**\n\n"
                        f"📈 Progress: {p_bar}\n"
                        f"✅ Processed Successfully: `{rename_count}/{total_to_process}` files\n"
                        f"⏱️ Time Elapsed: `{format_time(elapsed_time)}`\n"
                        f"⏳ Time Estimated: `{format_time(estimated_time)}`"
                    )
                    kb = [[InlineKeyboardButton("🛑 Terminate Action", callback_data=f"cancel_{task_key}")]]
                    asyncio.run_coroutine_threadsafe(bot.edit_message_text(text, chat_id, msg_id, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"), loop)

        if ACTIVE_TASKS.get(task_key, True):
            asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"🏁 **Mission Complete!**\n\n✨ Processed Files: `{rename_count}`\n⏱️ Total Time Taken: `{format_time(time.time() - start_time)}`", chat_id, msg_id), loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"❌ **Engine Interrupt Error:** {str(e)}", chat_id, msg_id), loop)

async def replace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'mega_instance' not in context.user_data:
        await update.message.reply_text("❌ Pehle `/login` command se login karein!")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Format: `/replace old_text new_text`")
        return

    find_text = str(context.args[0])
    replace_text = "" if str(context.args[1]).lower() == "blank" else str(context.args[1])
    m = context.user_data['mega_instance']

    progress_msg = await update.message.reply_text("🌀 **Initializing Premium Replacer Sub-Routine Pipeline...**")

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
            asyncio.run_coroutine_threadsafe(bot.edit_message_text("❌ Drive empty!", chat_id, msg_id), loop)
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as file_executor:
            futures = [file_executor.submit(rename_absolute, node) for node in indexed_nodes]
            last_rep = 0
            for _ in concurrent.futures.as_completed(futures):
                if not ACTIVE_TASKS.get(task_key, True):
                    break
                if rename_count % 15 == 0 and rename_count != last_rep:
                    last_rep = rename_count

                    elapsed_time = time.time() - start_time
                    speed = rename_count / elapsed_time if elapsed_time > 0 else 0
                    remaining_files = total_to_process - rename_count
                    estimated_time = remaining_files / speed if speed > 0 else None

                    p_bar = make_progress_bar(rename_count, total_to_process)
                    text = (
                        f"⚡ **Bulk System Overwriting Names...**\n\n"
                        f"📈 Progress: {p_bar}\n"
                        f"✅ Overwritten: `{rename_count}/{total_to_process}` files\n"
                        f"⏱️ Time Elapsed: `{format_time(elapsed_time)}`\n"
                        f"⏳ Time Estimated: `{format_time(estimated_time)}`"
                    )
                    kb = [[InlineKeyboardButton("🛑 Terminate Action", callback_data=f"cancel_{task_key}")]]
                    asyncio.run_coroutine_threadsafe(bot.edit_message_text(text, chat_id, msg_id, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"), loop)

        if ACTIVE_TASKS.get(task_key, True):
            asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"🏁 **Full Overwrite Finished Successfully!**\n\n✨ Total Handled: `{rename_count}` nodes.\n⏱️ Total Time Taken: `{format_time(time.time() - start_time)}`", chat_id, msg_id), loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(bot.edit_message_text(f"❌ Error: {str(e)}", chat_id, msg_id), loop)

async def fullrename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'mega_instance' not in context.user_data:
        await update.message.reply_text("❌ Pehle `/login` command se login karein!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format: `/fullrename naya_naam`")
        return

    target_exact_name = " ".join(context.args).strip()
    m = context.user_data['mega_instance']

    progress_msg = await update.message.reply_text("🌀 **Initializing Absolute Overwrite Engine Matrix...**")

    loop = asyncio.get_running_loop()
    bot = context.bot
    chat_id = update.effective_chat.id
    task_key = f"{chat_id}_{random.randint(1000,9999)}"
    ACTIVE_TASKS[task_key] = True

    loop.run_in_executor(GLOBAL_EXECUTOR, core_fullrename_engine, m, target_exact_name, progress_msg.message_id, chat_id, bot, loop, task_key)

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔒 **Logged Out Successfully!**")

async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Login setup ya operational cache cancel kar diya gaya hai.")
    return ConversationHandler.END

# --- APPLICATION RUN ENGINE MAIN LOOP ---
def main():
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
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
    app.add_handler(CallbackQueryHandler(cancel_callback_handler, block=False))

    print("[+] Premium Dynamic Time Engine Running with No Errors...")
    app.run_polling()

if __name__ == '__main__':
    main()