import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import ReportRequest
from telethon.errors.rpcerrorlist import FloodWaitError, SessionPasswordNeededError

# Load environment variables from a .env file
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PHONE, CODE, PASSWORD, REPORT_TARGET = range(4)
temp_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to our Telegram Bot Business App!\n\n"
        "Use this bot to manage your accounts and automate reports.\n\n"
        "Commands:\n"
        "/add_account - Add a Telegram account\n"
        "/report - Report a target channel\n"
        "/help - View help\n"
        "/about - About this bot"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Help:\n"
        "/start - Start the bot\n"
        "/add_account - Add a user account\n"
        "/report - Report a channel\n"
        "/about - Bot info"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 This is a Telegram automation bot built with ❤️ using Python."
    )

async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return ConversationHandler.END
    await update.message.reply_text("📲 Send phone number (with + country code):")
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    temp_data['phone'] = phone
    client = TelegramClient(f'sessions/{phone}', API_ID, API_HASH)
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            temp_data['client'] = client
            await update.message.reply_text("✅ Code sent! Enter it:")
            return CODE
        else:
            await update.message.reply_text("⚠️ Already logged in.")
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error while connecting to Telegram: {e}")
        await update.message.reply_text("❌ Failed to connect to Telegram. Please try again.")
    finally:
        await client.disconnect()

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    client = temp_data.get('client')
    phone = temp_data.get('phone')
    
    if not client:
        await update.message.reply_text("❌ No session found. Please restart the process.")
        return ConversationHandler.END

    try:
        await client.sign_in(phone, code)
        await update.message.reply_text("🎉 Account added successfully!")
    except SessionPasswordNeededError:
        await update.message.reply_text("🔑 Two-step verification is enabled. Please enter your password:")
        return PASSWORD  # Switch to PASSWORD state for password entry
    except Exception as e:
        logger.error(f"Login failed for {phone}: {str(e)}")
        await update.message.reply_text(f"❌ Login failed: {str(e)}")
    finally:
        await client.disconnect()
        
    return ConversationHandler.END

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    client = temp_data.get('client')
    phone = temp_data.get('phone')

    if not client:
        await update.message.reply_text("❌ No session found. Please restart the process.")
        return ConversationHandler.END

    try:
        await client.sign_in(phone, password=password)
        await update.message.reply_text("🎉 Account added successfully with password!")
    except Exception as e:
        logger.error(f"Password login failed for {phone}: {str(e)}")
        await update.message.reply_text(f"❌ Password login failed: {str(e)}")
    finally:
        await client.disconnect()

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation canceled.")
    temp_data.clear()  # Clear temp data to prevent stale session data
    return ConversationHandler.END

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return ConversationHandler.END
    await update.message.reply_text("🔗 Send @channelname to report:")
    return REPORT_TARGET

async def get_report_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return ConversationHandler.END

    target_username = update.message.text.strip()
    if not target_username.startswith("@"):
        await update.message.reply_text("❗ Invalid format. Use @channelname")
        return ConversationHandler.END

    await update.message.reply_text(f"🚨 Reporting {target_username} from all sessions...")

    session_dir = 'sessions'
    sessions = [f for f in os.listdir(session_dir) if f.endswith('.session')]
    count = 0
    
    for session_file in sessions:
        phone = session_file.replace(".session", "")
        client = TelegramClient(f"sessions/{phone}", API_ID, API_HASH)
        
        try:
            await client.start()
            entity = await client.get_entity(target_username)

            await client(ReportRequest(
                peer=entity,
                id=[],  # Specify message ID for reporting if needed
                reason=1,
                message="Illegal content promotion"
            ))

            count += 1
            await update.message.reply_text(f"✅ Report sent from: {phone}")
            await asyncio.sleep(2)  # Short delay to respect rate limits

        except FloodWaitError as e:
            await update.message.reply_text(f"⏳ FloodWait: {e.seconds}s for {phone}.")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            logger.error(f"Error with {phone}: {str(e)}")
            await update.message.reply_text(f"❌ Error with {phone}: {str(e)}")
        finally:
            await client.disconnect()

    await update.message.reply_text(f"📊 Total reports sent: {count}")
    return ConversationHandler.END

# Create sessions directory if it doesn't exist
if not os.path.exists("sessions"):
    os.makedirs("sessions")

# Run the bot
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_add = ConversationHandler(
        entry_points=[CommandHandler('add_account', add_account)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],  # New state for password entry
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    conv_report = ConversationHandler(
        entry_points=[CommandHandler("report", report)],
        states={
            REPORT_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_report_target)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(conv_add)
    app.add_handler(conv_report)

    logger.info("✅ Bot is running... Press Ctrl+C to stop.")
    app.run_polling()
  
