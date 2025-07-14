import asyncio
import os
import random
import logging
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CreateChatRequest
from dotenv import load_dotenv

# --- Basic Logging Setup ---
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

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing required environment variables in your .env file.")

API_ID = int(API_ID)

# In-memory storage. For a real app, replace this with a database.
user_sessions = {}

# --- Helper Functions ---
def create_new_user_client():
    """Creates a Telethon client with randomized device info."""
    session = StringSession()
    device_params = [
        {'device_model': 'iPhone 14 Pro Max', 'system_version': '17.5.1', 'app_version': '10.9.1'},
        {'device_model': 'Samsung Galaxy S24 Ultra', 'system_version': 'SDK 34', 'app_version': '10.9.1'},
        {'device_model': 'Desktop', 'system_version': 'Windows 11', 'app_version': '4.16.8'},
        {'device_model': 'Pixel 8 Pro', 'system_version': 'SDK 34', 'app_version': '10.9.0'},
        {'device_model': 'iPhone 13', 'system_version': '17.1.1', 'app_version': '10.5.0'},
        {'device_model': 'Samsung Galaxy A54', 'system_version': 'SDK 33', 'app_version': '10.8.0'},
        {'device_model': 'MacBook Pro', 'system_version': 'macOS 14.5', 'app_version': '10.9.1'},
    ]
    selected_device = random.choice(device_params)
    return TelegramClient(session, API_ID, API_HASH, **selected_device)

async def run_group_creation_worker(event, logged_in_client, main_bot_client):
    """The main background task that creates 50 groups for the logged-in user."""
    user_id = event.sender_id
    await main_bot_client.send_message(user_id, '✅ **ورود موفقیت‌آمیز بود!**\n\nفرآیند ساخت ۵۰ گروه در پس‌زمینه آغاز شد. این کار ممکن است چندین ساعت طول بکشد.')
    
    try:
        user_to_add = '@BotFather'
        for i in range(50):
            group_title = f"Automated Group #{random.randint(1000, 9999)} - {i + 1}"
            try:
                await logged_in_client(CreateChatRequest(users=[user_to_add], title=group_title))
                logging.info(f"Successfully created group: {group_title} for user {user_id}")
                
                # --- NEW: Progress update every 10 groups ---
                if (i + 1) % 10 == 0:
                    await main_bot_client.send_message(user_id, f"⏳ پیشرفت: {i + 1} گروه از ۵۰ گروه ساخته شد...")

                sleep_duration = random.randint(400, 1000)
                logging.info(f"Waiting for {sleep_duration} seconds...")
                await asyncio.sleep(sleep_duration)
            except errors.UserRestrictedError:
                logging.error(f"User {user_id} is restricted from creating groups.")
                await main_bot_client.send_message(user_id, '❌ **خطا:** حساب شما به دلیل ریپورت اسپم توسط تلگرام محدود شده و نمی‌تواند گروه بسازد.')
                break
            except errors.FloodWaitError as fwe:
                logging.warning(f"Flood wait for user {user_id}. Sleeping for {fwe.seconds} seconds.")
                await main_bot_client.send_message(user_id, f"⏳ به دلیل محدودیت تلگرام، عملیات به مدت {fwe.seconds / 60:.2f} دقیقه متوقف شد.")
                await asyncio.sleep(fwe.seconds)
            except Exception as e:
                logging.error(f"Could not create group {group_title} for user {user_id}", exc_info=True)
                await main_bot_client.send_message(user_id, f"❌ خطای غیرمنتظره در هنگام ساخت گروه رخ داد.")
                await asyncio.sleep(60)
    finally:
        await main_bot_client.send_message(user_id, '🏁 چرخه ساخت گروه‌ها به پایان رسید.')
        await logged_in_client.disconnect()

async def on_login_success(event, logged_in_client, main_bot_client):
    """Handles the common logic after a successful login."""
    user_id = event.sender_id
    if user_id in user_sessions:
        del user_sessions[user_id]
    asyncio.create_task(run_group_creation_worker(event, logged_in_client, main_bot_client))

# --- Main Application Logic ---
async def main():
    bot = TelegramClient('bot_session', API_ID, API_HASH)

    @bot.on(events.NewMessage(pattern='/start'))
    async def start(event):
        """Handles the initial /start command from a user."""
        user_id = event.sender_id
        await event.reply(
            '**خوش آمدید!**\n'
            'این ربات برای ساخت گروه به صورت اتوماتیک است.\n\n'
            'لطفا شماره تلفن تلگرام خود را با فرمت بین‌المللی ارسال کنید (مثال: +989123456789).'
        )
        user_sessions[user_id] = {'state': 'awaiting_phone'}
        raise events.StopPropagation

    @bot.on(events.NewMessage)
    async def handle_all_messages(event):
        """Routes incoming messages to the correct handler based on user state."""
        user_id = event.sender_id
        if user_id not in user_sessions: return
        state = user_sessions[user_id].get('state')
        
        if state == 'awaiting_phone': await handle_phone_input(event)
        elif state == 'awaiting_code': await handle_code_input(event, bot)
        elif state == 'awaiting_password': await handle_password_input(event, bot)

    async def handle_phone_input(event):
        """Handles the user's phone number submission."""
        user_id = event.sender_id
        user_sessions[user_id]['phone'] = event.text.strip()
        user_client = create_new_user_client()
        user_sessions[user_id]['client'] = user_client
        try:
            await user_client.connect()
            sent_code = await user_client.send_code_request(user_sessions[user_id]['phone'])
            user_sessions[user_id]['phone_code_hash'] = sent_code.phone_code_hash
            await event.reply('یک کد ورود به حساب تلگرام شما ارسال شد. لطفا آن را اینجا ارسال کنید.')
            user_sessions[user_id]['state'] = 'awaiting_code'
        except errors.PhoneNumberInvalidError:
            await event.reply('❌ **خطا:** فرمت شماره تلفن نامعتبر است. لطفا دوباره تلاش کنید.')
            del user_sessions[user_id]
        except Exception as e:
            logging.error(f"Phone input error for user {user_id}: {e}", exc_info=True)
            await event.reply('❌ **خطا:** یک مشکل داخلی در هنگام ارسال کد رخ داد.')
            del user_sessions[user_id]

    async def handle_code_input(event, main_bot_client):
        """Handles the user's login code submission."""
        user_id = event.sender_id
        user_client = user_sessions[user_id]['client']
        phone_code_hash = user_sessions[user_id].get('phone_code_hash')
        try:
            await user_client.sign_in(user_sessions[user_id]['phone'], code=event.text.strip(), phone_code_hash=phone_code_hash)
            await on_login_success(event, user_client, main_bot_client)
        except errors.SessionPasswordNeededError:
            await event.reply('حساب شما دارای تایید دو مرحله‌ای است. لطفا رمز عبور خود را ارسال کنید.')
            user_sessions[user_id]['state'] = 'awaiting_password'
        except errors.PhoneNumberBannedError:
            await event.reply('❌ **خطا:** این شماره تلفن توسط تلگرام مسدود شده و قابل استفاده نیست.')
            del user_sessions[user_id]
        except errors.PhoneCodeInvalidError:
            await event.reply('❌ **خطا:** کد وارد شده نامعتبر است.')
        except errors.PhoneCodeExpiredError:
            await event.reply('❌ **خطا:** کد منقضی شده است. لطفا فرآیند را با /start مجددا آغاز کنید.')
            del user_sessions[user_id]
        except Exception as e:
            logging.error(f"Code input error for user {user_id}: {e}", exc_info=True)
            await event.reply('❌ **خطا:** یک مشکل داخلی رخ داده است.')
            del user_sessions[user_id]

    async def handle_password_input(event, main_bot_client):
        """Handles the user's 2FA password submission."""
        user_id = event.sender_id
        user_client = user_sessions[user_id]['client']
        try:
            await user_client.sign_in(password=event.text.strip())
            await on_login_success(event, user_client, main_bot_client)
        except errors.PasswordHashInvalidError:
            await event.reply('❌ **خطا:** رمز عبور اشتباه است. لطفا دوباره تلاش کنید.')
        except Exception as e:
            logging.error(f"Password input error for user {user_id}: {e}", exc_info=True)
            await event.reply('❌ **خطا:** یک مشکل داخلی رخ داده است.')
            del user_sessions[user_id]

    # --- Start the Bot ---
    logging.info("Starting bot...")
    await bot.start(bot_token=BOT_TOKEN)
    logging.info("Bot service has started successfully.")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
