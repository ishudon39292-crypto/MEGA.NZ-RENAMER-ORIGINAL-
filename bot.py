import sys
import logging
import subprocess
import shlex
import time
import asyncio
import os
import random
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.request import HTTPXRequest

import nest_asyncio
nest_asyncio.apply()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

EMAIL, PASSWORD = range(2)

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8834810654:AAFJjvmjdCO6yOYkgkSl2aK2Uc130bJNW1w"      # <-- Apna Token Daalein
UPDATE_CHANNEL = "@NEWSBYLAILA"        # <-- Apna Channel
ADMIN_ID = 8474134621                  # <-- Apni Admin ID
# =======================================================

ACTIVE_TASKS = {}

def setup_mega_cmd():
    check = subprocess.run("which mega-login", shell=True, capture_output=True, text=True)
    if not check.stdout.strip():
        os.system("apt-get update -y > /dev/null 2>&1")
        os.system("apt-get install -y libc-ares2 libcrypto++8b libmediainfo0v5 libpcrecpp0v5 libzen0v5 curl > /dev/null 2>&1")
        os.system("curl -s -O https://mega.nz/linux/repo/xUbuntu_22.04/amd64/megacmd-xUbuntu_22.04_amd64.deb")
        os.system("dpkg -i megacmd-xUbuntu_22.04_amd64.deb > /dev/null 2>&1")
        os.system("apt-get --fix-broken install -y > /dev/null 2>&1")

setup_mega_cmd()

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=90)
        return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    except Exception as e:
        return f"ERROR: {str(e)}"

def make_premium_ui(processed, total, elapsed, task_type="OVERWRITE"):
    if total == 0: total = 100
    percentage = min(int((processed / total) * 100), 100)
    
    filled = int(percentage / 5)
    bar = f"📦 {'🔷' * filled}{'🔹' * (20 - filled)}"
    
    speed = processed / elapsed if elapsed > 0 else 0
    rem_seconds = (total - processed) / speed if speed > 0 else 0
    
    def fmt_t(s):
        if s <= 0: return "⚡ Scaling..."
        return f"{int(s//60)}m {int(s%60)}s" if s >= 60 else f"{int(s)}s"

    mode_title = "⚡ HYPER-DRIVE OVERWRITE" if task_type == "OVERWRITE" else "🚀 HYPER-DRIVE REPLACE"
    
    ui = (
        f"🤖 <b>{mode_title}</b>\n"
        f"<code>┌──────────────────────────────┐</code>\n"
        f"  <b>PROGRESS :</b> {percentage}%\n"
        f"  {bar}\n"
        f"<code>├──────────────────────────────┤</code>\n"
        f"  ▪️ <b>PROCESSED  :</b> <code>{processed} / {total}</code>\n"
        f"  ▪️ <b>NET SPEED  :</b> <code>{speed:.1f} files/sec</code>\n"
        f"  ▪️ <b>TIME RUN   :</b> <code>{fmt_t(elapsed)}</code>\n"
        f"  ▪️ <b>TIME LEFT  :</b> <code>{fmt_t(rem_seconds)}</code>\n"
        f"<code>└──────────────────────────────┘</code>\n"
        f"🔥 <i>Multi-threaded C++ Pipeline active. Maximum speed unlocked.</i>"
    )
    return ui

async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "🚀 Welcome menu"),
        BotCommand("login", "🔒 MEGA CMD Login"),
        BotCommand("replace", "✏️ Replace text globally"),
        BotCommand("fullrename", "📝 Overwrite all names"),
        BotCommand("logout", "🔒 Logout Drive"),
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✨ <b>MEGA CMD CyberRenamer Engine Active!</b>\n\nUse <code>/login</code> to initialize backend pipeline.", parse_mode="HTML")

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    run_cmd("mega-logout")
    await update.message.reply_text("🔒 <b>[AUTHENTICATION GATEWAY]</b>\nEnter your MEGA Email Account:", parse_mode="HTML")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text.strip()
    await update.message.reply_text("🔑 Enter your Secret Password:", parse_mode="HTML")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    email = context.user_data.get('email')
    status_msg = await update.message.reply_text("🎛️ <b>Spawning C++ Subsystem daemon...</b>", parse_mode="HTML")
    
    safe_email = shlex.quote(email)
    safe_password = shlex.quote(password)
    
    login_res = run_cmd(f"mega-login {safe_email} {safe_password}")
    whoami = run_cmd("mega-whoami")
    
    if "Account:" in whoami or email in whoami:
        await status_msg.edit_text("✅ <b>Access Granted!</b>\nC++ System Cache Synced. Ready for Hyper-Speed Operations.", parse_mode="HTML")
    else:
        await status_msg.edit_text(f"❌ <b>Login Refused:</b>\n<code>{login_res}</code>", parse_mode="HTML")
    return ConversationHandler.END

# Async command runner for true concurrency
async def run_cmd_async(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()

# 🔥 MULTI-THREADED ASYNC REPLACE ENGINE
async def exec_mega_cmd_replace_async(find_text, replace_text, msg_id, chat_id, bot, task_key):
    start_time = time.time()
    last_ui = time.time()
    
    raw_files = run_cmd("mega-find / --pattern=*")
    if not raw_files or "ERROR" in raw_files or "Login required" in raw_files:
        await bot.edit_message_text("❌ Drive error or unauthorized session.", chat_id, msg_id)
        return
        
    all_lines = raw_files.splitlines()
    matching_files = [line for line in all_lines if line.strip() and find_text in os.path.basename(line)]
    
    total = len(matching_files)
    if total == 0:
        await bot.edit_message_text("❌ No target files found.", chat_id, msg_id)
        return

    processed = 0
    # Higher worker pool for insane concurrency
    chunk_size = 25 
    
    for i in range(0, total, chunk_size):
        if not ACTIVE_TASKS.get(task_key, True): break
        
        current_chunk = matching_files[i:i+chunk_size]
        tasks = []
        
        for path in current_chunk:
            base = os.path.basename(path)
            new_base = base.replace(find_text, replace_text) or "File"
            dest = f"{os.path.dirname(path)}/{new_base}"
            # '&' sends it to shell background execution instantly
            cmd = f"mega-mv {shlex.quote(path)} {shlex.quote(dest)} &"
            tasks.append(run_cmd_async(cmd))
            
        # Fire all commands parallelly 
        await asyncio.gather(*tasks)
        
        processed += len(current_chunk)
        now = time.time()
        
        if now - last_ui > 2.0 or processed >= total:
            last_ui = now
            ui_text = make_premium_ui(processed, total, now - start_time, "REPLACE")
            try:
                await bot.edit_message_text(ui_text, chat_id, msg_id, parse_mode="HTML")
            except Exception:
                pass

    await bot.edit_message_text(f"🏁 <b>Hyper-Task Completed!</b>\nTotal <code>{processed}</code> items successfully modified in cache.", chat_id, msg_id, parse_mode="HTML")

async def replace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Syntax: <code>/replace old_text new_text</code>", parse_mode="HTML")
        return
    find_text = str(context.args[0])
    replace_text = "" if str(context.args[1]).lower() == "blank" else str(context.args[1])
    
    p_msg = await update.message.reply_text("🛸 <b>Initializing Multi-Thread Matrix...</b>", parse_mode="HTML")
    task_key = f"{update.effective_chat.id}_{random.randint(100,999)}"
    ACTIVE_TASKS[task_key] = True
    
    asyncio.create_task(
        exec_mega_cmd_replace_async(find_text, replace_text, p_msg.message_id, update.effective_chat.id, context.bot, task_key)
    )

# 🔥 MULTI-THREADED ASYNC OVERWRITE ENGINE
async def exec_mega_cmd_fullrename_async(target_name, msg_id, chat_id, bot, task_key):
    start_time = time.time()
    last_ui = time.time()
    
    raw_files = run_cmd("mega-find / --pattern=*")
    if not raw_files or "Login required" in raw_files:
        await bot.edit_message_text("❌ Authentication Session Missing.", chat_id, msg_id)
        return
        
    all_lines = [l for l in raw_files.splitlines() if l.strip()]
    total = len(all_lines)
    
    if total == 0:
        await bot.edit_message_text("❌ Target Cloud Storage is Empty.", chat_id, msg_id)
        return

    processed = 0
    chunk_size = 25 
    for i in range(0, total, chunk_size):
        if not ACTIVE_TASKS.get(task_key, True): break
        
        current_chunk = all_lines[i:i+chunk_size]
        tasks = []
        
        for offset, path in enumerate(current_chunk):
            idx = i + offset + 1
            base = os.path.basename(path)
            parts = base.split('.')
            ext = parts[-1] if len(parts) > 1 else ""
            new_base = f"{target_name}_{idx}.{ext}" if ext else f"{target_name}_{idx}"
            dest = f"{os.path.dirname(path)}/{new_base}"
            cmd = f"mega-mv {shlex.quote(path)} {shlex.quote(dest)} &"
            tasks.append(run_cmd_async(cmd))
            
        await asyncio.gather(*tasks)
        
        processed += len(current_chunk)
        now = time.time()
        
        if now - last_ui > 2.0 or processed >= total:
            last_ui = now
            ui_text = make_premium_ui(processed, total, now - start_time, "OVERWRITE")
            try:
                await bot.edit_message_text(ui_text, chat_id, msg_id, parse_mode="HTML")
            except Exception:
                pass

    await bot.edit_message_text(f"🏁 <b>Hyper-Task Completed!</b>\nTotal <code>{processed}</code> items completely overwritten.", chat_id, msg_id, parse_mode="HTML")

async def fullrename_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Syntax: <code>/fullrename new_name</code>", parse_mode="HTML")
        return
    target_name = " ".join(context.args).strip()
    
    p_msg = await update.message.reply_text("🛸 <b>Initializing Multi-Thread Matrix...</b>", parse_mode="HTML")
    task_key = f"{update.effective_chat.id}_{random.randint(100,999)}"
    ACTIVE_TASKS[task_key] = True
    
    asyncio.create_task(
        exec_mega_cmd_fullrename_async(target_name, p_msg.message_id, update.effective_chat.id, context.bot, task_key)
    )

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    run_cmd("mega-logout")
    await update.message.reply_text("🔒 Securely unlinked current Cloud cache.")

async def start_bot_async():
    custom_request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(BOT_TOKEN).request(custom_request).post_init(post_init).build()

    login_conv = ConversationHandler(
        entry_points=[CommandHandler('login', login_command, block=False)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email, block=False)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password, block=False)],
        },
        fallbacks=[],
    )

    app.add_handler(login_conv)
    app.add_handler(CommandHandler('start', start, block=False))
    app.add_handler(CommandHandler('replace', replace_command, block=False))
    app.add_handler(CommandHandler('fullrename', fullrename_command, block=False))
    app.add_handler(CommandHandler('logout', logout_command, block=False))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("[+] CyberRenamer Turbo Engine Running on Colab!")
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(start_bot_async())
