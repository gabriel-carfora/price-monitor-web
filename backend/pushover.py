import os
import httpx
from dotenv import load_dotenv
load_dotenv()

PUSHOVER_APP_TOKEN = os.getenv("PUSHOVER_APP_TOKEN")

async def send_pushover(user_key, message):
    async with httpx.AsyncClient() as client:
        data = {
            "token": PUSHOVER_APP_TOKEN,
            "user": user_key,
            "message": message
        }
        response = await client.post("https://api.pushover.net/1/messages.json", data=data)
        return response.status_code == 200
