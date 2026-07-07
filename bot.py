import sys
import logging
import concurrent.futures
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.error import BadRequest
from telegram.request import HTTPXRequest
from mega import Mega

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Conversation States
EMAIL, PASSWORD = range(2)

# CONFIGURATION (Yahan apni sahi details dalein)
BOT_TOKEN = "8834810654:AAFBaOn6k-9CXheg-qmDlLmWSy81gyO87xQ"
UPDATE_CHANNEL = "@NEWSBYLAILA"  # Include @, blank rkhne ke liye "" kar dein

# --- DUMMY SERVER FOR RENDER PORT CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is Running Perfectly on Web Service!")
    def log_message(self, format, *args):
        return  # Render ke logs clean rakhne ke liye

def run_health_check():
    # Render Free Web Service default 10000 port scan karti hai
    server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
    server.serve_forever()

# --- FORCE JOIN CHECK FUNCTION ---
async def is_user_subbed(bot, user_id: int) -> bool:
    if not UPDATE_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=UPDATE_CHANNEL, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except BadRequest:
        print(f"[-] Error: Bot ko {UPDATE_CHANNEL} ka admin banayein ya username check karein.")
        return True
    except Exception:
        return False

async def send_force_join_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_url = f"https://t.me/{UPDATE_CHANNEL.replace('@', '')}"
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=channel_url)],
        [InlineKeyboardButton("🔄 Try Again", callback_data="check_again")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg_text = (
        "⚠️ **Access Denied!**\n\n"
        f"Is bot ko use karne ke liye aapko hamare official channel `{UPDATE_CHANNEL}` ko join karna hoga.\n\n"
        "Join karne ke baad dobara **/start** bhejkar check karein!"
    )
    
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=reply_markup)

# --- BOT HANDLERS ---

async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "🚀 Bot ka welcome menu dekhein"),
        BotCommand("login", "🔒 MEGA account link/login karein"),
        BotCommand("replace", "✏️ Format: /replace old_text new_text"),
        BotCommand("logout", "🔒 MEGA account unlink / logout karein"),
        BotCommand("cancel", "❌ Chalu operation ko cancel karein")
    ]
    await application.bot.set_my_commands(commands)
    print("[+] Telegram Menu Commands successfully set!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return

    welcome_text = (
        f"👋 **Hello, {first_name}!**\n\n"
        "🚀 Welcome to **Fast Global Bulk Renamer Bot**.\n"
        "Yeh bot aapke MEGA cloud drive ki hazaaron files ko kuch hi seconds mein ek sath rename kar sakta hai!\n\n"
        "⚡ **Bot Features:**\n"
        "• 30 Optimized Multi-Threaded Workers (Stable Speed).\n"
        "• Anti-Freeze Live Progress System.\n"
        "• Super fast and secure text replacing.\n\n"
        "📋 **How to Use:**\n"
        "1. Pehle **/login** command bhejkar apna MEGA drive connect karein.\n"
        "2. Connect hone ke baad, files ko rename karne ke liye niche diye format mein command bhejein:\n"
        "👉 `/replace purana_naam naya_naam`"
    )
    await update.message.reply_text(welcome_text)

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return ConversationHandler.END

    if 'email' in context.user_data:
        await update.message.reply_text(
            f"ℹ️ Aap pehle se `{context.user_data['email']}` account se logged in hain.\n"
            f"Naye account ke liye pehle **/logout** command bhejein."
        )
        return ConversationHandler.END
        
    await update.message.reply_text("🔒 **MEGA.nz Login Setup**\n\nEnter your MEGA.nz email address to link account:")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text.strip()
    await update.message.reply_text("🔑 Now, enter your MEGA password:")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    email = context.user_data['email']
    status_msg = await update.message.reply_text("🔄 Logging in and indexing your MEGA Drive (Fast Mode)...")
    
    try:
        mega = Mega()
        m = mega.login(email, password)
        all_nodes = m.get_files()
        
        context.user_data['password'] = password
        total_files = sum(1 for n in all_nodes.values() if n.get('t') == 0)
        total_folders = sum(1 for n in all_nodes.values() if n.get('t') == 1)

        await status_msg.edit_text(
            f"✅ **Connected & Indexed Successfully!**\n\n"
            f"📊 **Drive Overview:**\n"
            f"📁 Total Folders: {total_folders}\n"
            f"📄 Total Files: {total_files}\n\n"
            f"🚀 Ready! Direct command bhejein:\n"
            f"👉 `/replace old_text new_text`"
        )
        return ConversationHandler.END
    except Exception as e:
        await status_msg.edit_text(f"❌ Login failed: {str(e)}\n\nSend /login to try again.")
        context.user_data.clear()
        return ConversationHandler.END

async def replace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return

    if 'email' not in context.user_data or 'password' not in context.user_data:
        await update.message.reply_text("❌ Pehle /login command bhejkar login karein!")
        return
        
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Format: `/replace old_text new_text` (Use `blank` to delete text)\n\nExample: `/replace _1080p blank`")
        return
        
    find_text = str(context.args[0])
    replace_text = str(context.args[1])
    if replace_text.lower() == "blank":
        replace_text = ""
        
    email = context.user_data['email']
    password = context.user_data['password']
    
    progress_msg = await update.message.reply_text("🔍 Scanning files instantly...")
    
    try:
        mega = Mega()
        m = mega.login(email, password)
        all_nodes = m.get_files()
        
        matching_nodes = []
        for node_id, node_data in all_nodes.items():
            if node_data.get('t') == 0:
                current_name = node_data.get('a', {}).get('n', '')
                if find_text in current_name:
                    matching_nodes.append((node_id, node_data, current_name))
        
        total_matches = len(matching_nodes)
        if total_matches == 0:
            await progress_msg.edit_text(f"❌ Poore drive par kisi bhi file mein '{find_text}' nahi mila!")
            return
            
        await progress_msg.edit_text(f"⏳ Found {total_matches} files. Renaming in progress with 30 Stable Workers...")
        
        rename_count = 0
        processed_count = 0
        last_edit_time = time.time()  # Non-blocking live progress tracking

        def rename_single_file(node_info):
            n_id, n_data, curr_name = node_info
            new_name = curr_name.replace(find_text, replace_text)
            try:
                m.rename((n_id, n_data), new_name)
                return True
            except Exception:
                return False

        # Fixed to 30 Workers for safe and superfast execution on free hosting
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            future_to_node = {executor.submit(rename_single_file, node): node for node in matching_nodes}
            
            for future in concurrent.futures.as_completed(future_to_node):
                processed_count += 1
                if future.result():
                    rename_count += 1
                
                # Anti-freeze rule: Message sirf har 5 seconds mein ek baar edit hoga
                current_time = time.time()
                if current_time - last_edit_time >= 5.0 or processed_count == total_matches:
                    try:
                        await progress_msg.edit_text(
                            f"⚡ **Turbo Progress (30 Workers):**\n"
                            f"🔄 Processed: {processed_count}/{total_matches} files...\n"
                            f"✅ Successfully Renamed: {rename_count}\n\n"
                            f"🚀 Status: Background threads running seamlessly..."
                        )
                        last_edit_time = current_time
                    except Exception:
                        pass
                        
        await progress_msg.edit_text(
            f"🎉 **Global Rename Finished!**\n\n"
            f"🔍 Text Found: '{find_text}'\n"
            f"✏️ Replaced with: '{replace_text if replace_text else '[DELETED]'}'\n"
            f"🔄 Successfully Renamed: {rename_count}/{total_matches} files."
        )
    except Exception as e:
        await progress_msg.edit_text(f"❌ Error: {str(e)}")

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'email' in context.user_data:
        old_email = context.user_data['email']
        context.user_data.clear()
        await update.message.reply_text(f"🔒 **Logged Out!**\n\nAccount `{old_email}` data cleared.")
    else:
        await update.message.reply_text("ℹ️ Aap pehle se hi logged out hain!")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Session closed safely.")
    return ConversationHandler.END

def main():
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("[-] Error: Token add karein!")
        sys.exit(1)

    # Start dummy port checker thread for Render Web Service compatibility
    threading.Thread(target=run_health_check, daemon=True).start()
    print("[+] Dummy Port Web Server successfully started on port 10000...")

    custom_request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(BOT_TOKEN).request(custom_request).post_init(post_init).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('login', login_command)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Concurrency control: block=False handles multiple users without bottleneck
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('start', start, block=False))
    app.add_handler(CommandHandler('replace', replace_command, block=False))
    app.add_handler(CommandHandler('logout', logout_command, block=False))
    
    print("[+] Fast Global Bulk Renamer Bot successfully loaded!")
    app.run_polling()

if __name__ == '__main__':
    main()
