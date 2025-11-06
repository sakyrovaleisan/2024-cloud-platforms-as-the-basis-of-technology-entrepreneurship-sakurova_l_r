from dotenv import load_dotenv
import os

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

print("Loaded BOT_TOKEN:", BOT_TOKEN)
