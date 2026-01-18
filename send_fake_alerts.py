 import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

async def send_alerts():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        return

    bot = Bot(token=token)
    
    # Use provided chat ID
    chat_id = -5294408763
    print(f"Using provided chat_id: {chat_id}")

    msg1 = """[DOWNVOTED] u/DangerousBullfrog236
Order #4748304
Downvotes: 30"""

    msg2 = """[DOWNVOTED] u/KenDrakebot
Order #4748306
Downvotes: 30"""

    print(f"Sending alert 1 to {chat_id}...")
    await bot.send_message(chat_id=chat_id, text=msg1)
    
    print(f"Sending alert 2 to {chat_id}...")
    await bot.send_message(chat_id=chat_id, text=msg2)
    
    print("Done!")

if __name__ == "__main__":
    asyncio.run(send_alerts())
