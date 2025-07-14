import asyncio
import os
import random
import time
from telethon.sync import TelegramClient, events
from telethon.sessions import StringSession

# --- Configuration (Load from Environment Variables on Render) ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# In-memory dictionary to store user's state during the login process.
# For a real-world app, you should use a database (e.g., Redis, PostgreSQL) for this.
user_sessions = {}

# --- 1. The Controller Bot Logic ---
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply('Welcome! I can help you automate group creation.\n\nPlease send me your Telegram phone number in international format (e.g., +15551234567).')

    # Store the state that we are waiting for a phone number
    user_id = event.sender_id
    user_sessions[user_id] = {'state': 'awaiting_phone'}

@bot.on(events.NewMessage)
async def handle_messages(event):
    user_id = event.sender_id
    if user_id not in user_sessions:
        return # Ignore messages from users not in a login flow

    state = user_sessions[user_id].get('state')

    # Using a simple state machine to manage the conversation
    if state == 'awaiting_phone':
        await handle_phone(event)
    elif state == 'awaiting_code':
        await handle_code(event)
    elif state == 'awaiting_password':
        await handle_password(event)

async def handle_phone(event):
    user_id = event.sender_id
    phone = event.text.strip()

    user_sessions[user_id]['phone'] = phone

    # Create a new client for this user with randomized device info
    client = create_new_client(user_id)

    try:
        # Connect and send the login code
        await client.connect()
        sent_code = await client.send_code_request(phone)
        user_sessions[user_id]['phone_code_hash'] = sent_code.phone_code_hash
        user_sessions[user_id]['client'] = client # Store the client instance

        await event.reply('A login code has been sent to your Telegram account. Please send it to me.')
        user_sessions[user_id]['state'] = 'awaiting_code'
    except Exception as e:
        await event.reply(f'Error: {e}')
        del user_sessions[user_id]

async def handle_code(event):
    user_id = event.sender_id
    code = event.text.strip()
    client = user_sessions[user_id]['client']
    phone = user_sessions[user_id]['phone']
    phone_code_hash = user_sessions[user_id]['phone_code_hash']

    try:
        # Sign in with the code
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        # If we reach here, login was successful (or a password is required)
        # Start the group creation process in the background
        asyncio.create_task(run_group_creation(event, client))
    except telethon.errors.SessionPasswordNeededError:
        await event.reply('Your account has Two-Factor Authentication enabled. Please send me your password.')
        user_sessions[user_id]['state'] = 'awaiting_password'
    except Exception as e:
        await event.reply(f'Error: {e}')
        del user_sessions[user_id]

async def handle_password(event):
    user_id = event.sender_id
    password = event.text.strip()
    client = user_sessions[user_id]['client']

    try:
        # Sign in with the password
        await client.sign_in(password=password)
        # Start the group creation process in the background
        asyncio.create_task(run_group_creation(event, client))
    except Exception as e:
        await event.reply(f'Error: {e}')
        del user_sessions[user_id]

# --- 2. The Worker Client Logic ---
def create_new_client(user_id):
    """Creates a Telethon client with randomized device info."""
    # Storing the session in memory. For Render, StringSession is better.
    # The session string should be stored in a database after login.
    session = StringSession()

    device_params = [
        {'device_model': 'iPhone 14 Pro Max', 'system_version': '16.5.1', 'app_version': '9.6.3'},
        {'device_model': 'Samsung Galaxy S23 Ultra', 'system_version': 'SDK 33', 'app_version': '9.6.3'},
        {'device_model': 'Google Pixel 7 Pro', 'system_version': 'SDK 33', 'app_version': '9.6.3'},
        {'device_model': 'Desktop', 'system_version': 'Windows 11', 'app_version': '4.8.1'},
    ]
    selected_device = random.choice(device_params)

    return TelegramClient(session, API_ID, API_HASH, **selected_device)

async def run_group_creation(event, client):
    """The main background task for creating groups."""
    await event.reply('Login successful! I will now start creating 50 groups. This will take a long time. You will be notified when it is complete.')
    del user_sessions[event.sender_id] # Clean up session state

    try:
        # You need at least one other user to create a group.
        # This could be a public bot username or another user you control.
        user_to_add = 'username_of_user_to_add'

        for i in range(50):
            group_title = f"Automated Group {i + 1}"
            try:
                await client(telethon.tl.functions.messages.CreateChatRequest(
                    users=[user_to_add],
                    title=group_title
                ))
                print(f"Successfully created group: {group_title}")
                # IMPORTANT: Wait a long, random time between creations to avoid bans
                await asyncio.sleep(random.randint(300, 900)) # 5 to 15 minutes
            except telethon.errors.FloodWaitError as fwe:
                print(f"Flood wait requested. Sleeping for {fwe.seconds} seconds.")
                await event.sender.send_message(f"Rate limited by Telegram. Pausing for {fwe.seconds / 60:.2f} minutes.")
                await asyncio.sleep(fwe.seconds)
            except Exception as e:
                print(f"Could not create group {group_title}. Error: {e}")

    finally:
        await event.sender.send_message('Group creation cycle finished.')
        await client.disconnect()

# --- 3. Main execution loop ---
async def main():
    print("Bot is running...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
