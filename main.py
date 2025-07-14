import asyncio
import os
import random
import time
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CreateChatRequest
from dotenv import load_dotenv

# Load variables from the .env file into the environment
load_dotenv()

# --- Configuration ---
# Now reads the variables loaded from your .env file
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# This check ensures the app doesn't start without its configuration
if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing one or more required environment variables in your .env file.")

# Convert API_ID to integer
API_ID = int(API_ID)

# In-memory dictionary to manage login states
user_sessions = {}

# --- The rest of the bot code is the same as before... ---

# --- 1. The Controller Bot Logic ---
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    """Handles the /start command and begins the login process."""
    user_id = event.sender_id
    await event.reply('**Welcome!**\nThis bot helps automate group creation.\n\n⚠️ **Warning:** Using this service is against Telegram\'s rules and will likely get your account banned.\n\nPlease send your Telegram phone number in international format (e.g., `+15551234567`) to continue.')
    user_sessions[user_id] = {'state': 'awaiting_phone'}

@bot.on(events.NewMessage)
async def handle_all_messages(event):
    """Main message handler that routes messages based on user state."""
    user_id = event.sender_id
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
    """Handles the user's phone number submission."""
    user_id = event.sender_id
    phone = event.text.strip()
    user_sessions[user_id]['phone'] = phone
    client = create_new_user_client()
    user_sessions[user_id]['client'] = client
    try:
        await client.connect()
        sent_code = await client.send_code_request(phone)
        user_sessions[user_id]['phone_code_hash'] = sent_code.phone_code_hash
        await event.reply('A login code was sent to your Telegram account. Please send it here.')
        user_sessions[user_id]['state'] = 'awaiting_code'
    except Exception as e:
        await event.reply(f'❌ **Error:** {e}')
        del user_sessions[user_id]

async def handle_code_input(event):
    """Handles the login code submission."""
    user_id = event.sender_id
    code = event.text.strip()
    client = user_sessions[user_id]['client']
    phone = user_sessions[user_id]['phone']
    phone_code_hash = user_sessions[user_id]['phone_code_hash']
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        asyncio.create_task(run_group_creation_worker(event, client))
    except errors.SessionPasswordNeededError:
        await event.reply('Your account has Two-Factor Authentication enabled. Please send your password.')
        user_sessions[user_id]['state'] = 'awaiting_password'
    except Exception as e:
        await event.reply(f'❌ **Error:** {e}')
        del user_sessions[user_id]

async def handle_password_input(event):
    """Handles the 2FA password submission."""
    user_id = event.sender_id
    password = event.text.strip()
    client = user_sessions[user_id]['client']
    try:
        await client.sign_in(password=password)
        asyncio.create_task(run_group_creation_worker(event, client))
    except Exception as e:
        await event.reply(f'❌ **Error:** {e}')
        del user_sessions[user_id]

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
    await event.reply('✅ **Login successful!**\n\nI will now start creating 50 groups in the background. This will take several hours.')
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
                await event.sender.send_message(f"⏳ Paused by Telegram. Resuming in {fwe.seconds / 60:.2f} minutes.")
                await asyncio.sleep(fwe.seconds)
            except Exception as e:
                print(f"Could not create group {group_title}. Error: {e}")
                await event.sender.send_message(f"❌ Failed to create a group due to error: {e}")
                await asyncio.sleep(60)
    finally:
        await event.sender.send_message('🏁 Group creation cycle finished.')
        await client.disconnect()

async def main():
    """Connects the bot and keeps it running."""
    print("Bot service is starting...")
    await bot.run_until_disconnected()
    print("Bot service has stopped.")

if __name__ == "__main__":
    asyncio.run(main())
