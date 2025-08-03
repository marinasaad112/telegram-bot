import os
from dotenv import load_dotenv

load_dotenv()  # تحميل المتغيرات من ملف .env

BOT_TOKEN = os.getenv("BOT_TOKEN")
