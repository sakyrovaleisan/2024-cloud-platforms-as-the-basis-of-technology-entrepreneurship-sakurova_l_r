from dotenv import load_dotenv
import os

load_dotenv()  # загружает переменные из .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
print("BOT_TOKEN =", BOT_TOKEN) 
