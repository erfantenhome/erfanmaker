import asyncio
import os
import random
import time
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CreateChatRequest
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

# --- Configuration ---
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing one or more required environment variables in your .env file.")

API_ID = int(API_ID)

# In-memory dictionary to manage login states
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
        del user_sessions[event.sender_id]
    try:
        user_to_add = '@BotFather'
        for i in range(50):
            group_title = f"Automated Group #{random.randint(1000, 9999)} - {i + 1}"
            try:
                await client(CreateChatRequest(users=[user_to_add], title=group_title))
                print(f"Successfully created group: {group_title}")
                sleep_duration = random.randint(400, 1000)
                print(f"Waiting for {sleep_duration} seconds...")
                await asyncio.sleep(sleep_duration)
            except errors.FloodWaitError as fwe:
                print(f"Flood wait requested. Sleeping for {fwe.seconds} seconds.")
                await event.sender.send_message(f"⏳ به دلیل محدودیت تلگرام، عملیات به مدت {fwe.seconds / 60:.2f} دقیقه متوقف شد.")
                await asyncio.sleep(fwe.seconds)
            except Exception as e:
                print(f"Could not create group {group_title}. Error: {e}")
                await event.sender.send_message(f"❌ ساخت گروه به دلیل خطا ناموفق بود: {e}")
                await asyncio.sleep(60)
    finally:
        await event.sender.send_message('🏁 چرخه ساخت گروه‌ها به پایان رسید.')
        await client.disconnect()

# --- Main Application Logic ---
async def main():
    # Initialize the client inside the async function
    client = TelegramClient('bot_session', API_ID, API_HASH)

    # --- Define Event Handlers within main ---
    @client.on(events.NewMessage(pattern='/start'))
    async def start(event):
        user_id = event.sender_id
        await event.reply(
            '**خوش آمدید!**\n'
            'این ربات برای ساخت گروه به صورت اتوماتیک است.\n\n'
            'لطفا شماره تلفن تلگرام خود را با فرمت بین‌المللی ارسال کنید (مثال: +989123456789).'
        )
        user_sessions[user_id] = {'state': 'awaiting_phone'}
        raise events.StopPropagation

    @client.on(events.NewMessage)
    async def handle_all_messages(event):
        user_id = event.sender_id
        if user_id not in user_sessions:
            return
        state = user_sessions[user_id].get('state')
        
        # State machine to guide the user
        if state == 'awaiting_phone':
            await handle_phone_input(event)
        elif state == 'awaiting_code':
            await handle_code_input(event)
        elif state == 'awaiting_password':
            await handle_password_input(event)

    async def handle_phone_input(event):
        user_id = event.sender_id
        phone = event.text.strip()
        user_sessions[user_id]['phone'] = phone
        user_client = create_new_user_client()
        user_sessions[user_id]['client'] = user_client
        try:
            await user_client.connect()
            sent_code = await user_client.send_code_request(phone)
            user_sessions[user_id]['phone_code_hash'] = sent_code.phone_code_hash
            await event.reply('یک کد ورود به حساب تلگرام شما ارسال شد. لطفا آن را اینجا ارسال کنید.')
            user_sessions[user_id]['state'] = 'awaiting_code'
        except Exception as e:
            await event.reply(f'❌ **خطا:** {e}')
            del user_sessions[user_id]

    async def handle_code_input(event):
        user_id = event.sender_id
        code = event.text.strip()
        user_client = user_sessions[user_id]['client']
        phone = user_sessions[user_id]['phone']
        phone_code_hash = user_sessions[user_id]['phone_code_hash']
        try:
            await user_client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            asyncio.create_task(run_group_creation_worker(event, user_client))
        except errors.SessionPasswordNeededError:
            await event.reply('حساب شما دارای تایید دو مرحله‌ای است. لطفا رمز عبور خود را ارسال کنید.')
            user_sessions[user_id]['state'] = 'awaiting_password'
        except Exception as e:
            await event.reply(f'❌ **خطا:** {e}')
            del user_sessions[user_id]

    async def handle_password_input(event):
        user_id = event.sender_id
        password = event.text.strip()
        user_client = user_sessions[user_id]['client']
        try:
            await user_client.sign_in(password=password)
            asyncio.create_task(run_group_creation_worker(event, user_client))
        except Exception as e:
            await event.reply(f'❌ **خطا:** {e}')
            del user_sessions[user_id]

    # --- Start the Bot ---
    print("Starting bot...")
    await client.start(bot_token=BOT_TOKEN)
    print("Bot service has started successfully.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
