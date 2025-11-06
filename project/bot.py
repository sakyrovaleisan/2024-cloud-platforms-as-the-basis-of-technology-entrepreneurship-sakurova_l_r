from telegram import Update
from telegram.ext import CommandHandler, ApplicationBuilder, ContextTypes
from dotenv import load_dotenv
import os

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your chat_id: {update.effective_chat.id}")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("whoami", whoami))
app.run_polling()
