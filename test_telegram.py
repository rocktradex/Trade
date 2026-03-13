sd
back
--
cd bot
import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TELEGRAM_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

text = """✅ ROCKTRADE AI

Telegram подключен
Сервер: OK
Бот: OK
"""

url = f"https://api.telegram.org/bot{token}/sendMessage"
r = requests.post(url, json={"chat_id": chat_id, "text": text})
print(r.text)
