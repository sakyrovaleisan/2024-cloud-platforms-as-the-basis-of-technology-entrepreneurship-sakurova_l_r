from dotenv import load_dotenv
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Загружаем переменные окружения из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
print("Loaded BOT_TOKEN:", BOT_TOKEN)  # проверка, что токен прочитан

if not BOT_TOKEN:
    raise ValueError("Не найден BOT_TOKEN в файле .env")

# Функция обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я твой бот.")

# Создаём приложение бота
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Регистрируем обработчик команды /start
app.add_handler(CommandHandler("start", start))

# Запускаем бота
if __name__ == "__main__":
    print("Бот запускается...")
    app.run_polling()
