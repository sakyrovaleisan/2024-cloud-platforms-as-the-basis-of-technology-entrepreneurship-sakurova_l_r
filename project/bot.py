from telegram import Update
from telegram.ext import CommandHandler, ApplicationBuilder, ContextTypes

async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your chat_id: {update.effective_chat.id}")

app = ApplicationBuilder().token("ВАШ_BOT_TOKEN").build()
app.add_handler(CommandHandler("whoami", whoami))
app.run_polling()
