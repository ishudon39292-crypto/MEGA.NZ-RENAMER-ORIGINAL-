import sys
import logging
import concurrent.futures
import threading
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

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# States
EMAIL, PASSWORD = range(2)

BOT_TOKEN = "8834810654:AAFBaOn6k-9CXheg-qmDlLmWSy81gyO87xQ"
UPDATE_CHANNEL = "@NEWSBYLAILA" 

# --- DUMMY SERVER FOR RENDER PORT CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is Running Perfectly on Web Service!")
    def log_message(self, format, *args):
        return  # Render ke faltu logs rokne ke liye

def run_health_check():
    # Render default port 10000 use karta hai
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
        print(f"[-] Error: Bot ko {UPDATE_CHANNEL} ka admin banayein.")
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
    msg_text = f"⚠️ **Access Denied!**\n\nIs bot ko use karne ke liye aapko `{UPDATE_CHANNEL}` join karna hoga."
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=reply_markup)

async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "🚀 Bot ka welcome menu dekhein"),
        BotCommand("login", "🔒 MEGA account link/login karein"),
        BotCommand("replace", "✏️ Format: /replace old_text new_text"),
        BotCommand("logout", "🔒 MEGA account unlink / logout karein"),
        BotCommand("cancel", "❌ Chalu operation ko cancel karein")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return
    await update.message.reply_text("👋 Hello! Welcome to **Fast Global Bulk Renamer Bot**.\n\nSend /login to start.")

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subbed(context.bot, user_id):
        await send_force_join_msg(update, context)
        return ConversationHandler.END
    if 'email' in context.user_data:
        await update.message.reply_text("ℹ️ logged in hain. /logout karein naye account ke liye.")
        return ConversationHandler.END
    await update.message.reply_text("🔒 Enter your MEGA.nz email:")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text.strip()
    await update.message.reply_text("🔑 Enter your MEGA password:")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    email = context.user_data['email']
    status_msg = await update.message.reply_text("🔄 Logging in & indexing MEGA Drive...")
    try:
        mega = Mega()
        m = mega.login(email, password)
        all_nodes = m.get_files()
        context.user_data['password'] = password
        total_files = sum(1 for n in all_nodes.values() if n.get('t') == 0)
        await status_msg.edit_text(f"✅ Connected!\n📄 Total Files: {total_files}\n\n👉 `/replace old_text new_text`")
        return ConversationHandler.END
    except Exception as e:
        await status_msg.edit_text(f"❌ Login failed: {str(e)}")
        context.user_data.clear()
        return ConversationHandler.END

async def replace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'email' not in context.user_data:
        await update.message.reply_text("❌ Pehle /login karein!")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Format: `/replace old_text new_text`")
        return
    find_text, replace_text = str(context.args[0]), str(context.args[1])
    if replace_text.lower() == "blank": replace_text = ""
    
    progress_msg = await update.message.reply_text("🔍 Scanning files...")
    try:
        mega = Mega()
        m = mega.login(context.user_data['email'], context.user_data['password'])
        all_nodes = m.get_files()
        matching_nodes = [(nid, ndata, ndata.get('a', {}).get('n', '')) for nid, ndata in all_nodes.items() if ndata.get('t') == 0 and find_text in ndata.get('a', {}).get('n', '')]
        
        total_matches = len(matching_nodes)
        if total_matches == 0:
            await progress_msg.edit_text("❌ Koi file nahi mili!")
            return
            
        await progress_msg.edit_text(f"⏳ Found {total_matches} files. Renaming with 30 Workers...")
        rename_count, processed_count = 0, 0

        def rename_single_file(node_info):
            n_id, n_data, curr_name = node_info
            try:
                m.rename((n_id, n_data), curr_name.replace(find_text, replace_text))
                return True
            except Exception: return False

        # Safe spot 30 workers for Web Service stability
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            future_to_node = {executor.submit(rename_single_file, node): node for node in matching_nodes}
            for future in concurrent.futures.as_completed(future_to_node):
                processed_count += 1
                if future.result(): rename_count += 1
                if processed_count % 10 == 0 or processed_count == total_matches:
                    try: await progress_msg.edit_text(f"⚡ **Live Progress:**\n🔄 Processed: {processed_count}/{total_matches}\n✅ Renamed: {rename_count}")
                    except Exception: pass
        await progress_msg.edit_text(f"🎉 Finished! Successfully Renamed: {rename_count}/{total_matches} files.")
    except Exception as e: await progress_msg.edit_text(f"❌ Error: {str(e)}")

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔒 Logged Out Successfully!")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return ConversationHandler.END

def main():
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        sys.exit(1)

    # Web service port satisfy karne ke liye dummy server thread start karein
    threading.Thread(target=run_health_check, daemon=True).start()
    print("[+] Dummy Port Server successfully started on port 10000...")

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
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('replace', replace_command))
    app.add_handler(CommandHandler('logout', logout_command))
    app.run_polling()

if __name__ == '__main__':
    main()
