import asyncio
import os
import random
import logging
from pathlib import Path

from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CreateChatRequest
from telethon.tl.types import ReplyKeyboardMarkup, KeyboardButton

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
LOGGER = logging.getLogger(__name__)

# --- Configuration ---
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing required environment variables in your .env file.")

API_ID = int(API_ID)
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True) # Ensure the sessions directory exists
MAX_CONCURRENT_WORKERS = 5 # Limit how many users can run the task simultaneously

# --- Bot Menu Buttons ---
# Using constants for button text makes the code cleaner
BTN_START_PROCESS = "🚀 شروع ساخت گروه"
BTN_CANCEL = "❌ لغو عملیات"
BTN_HELP = "ℹ️ راهنما"

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_START_PROCESS)],
        [KeyboardButton(BTN_CANCEL), KeyboardButton(BTN_HELP)],
    ],
    resize=True
)

class GroupCreatorBot:
    """A class to encapsulate the bot's logic, state, and handlers."""
    def __init__(self):
        self.bot = TelegramClient('bot_session', API_ID, API_HASH)
        # In-memory storage for the login flow
        self.login_sessions = {}
        # Tracks active group creation tasks (user_id -> asyncio.Task)
        self.active_workers = {}
        # Limits concurrent group creation tasks to prevent overload
        self.worker_semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)

    # --- Helper Functions ---

    def _get_session_path(self, user_id: int) -> Path:
        """Returns the file path for a user's session."""
        return SESSIONS_DIR / f"user_{user_id}.session"

    def _save_session_string(self, user_id: int, session_string: str):
        """Saves a user's session string to a file."""
        session_file = self._get_session_path(user_id)
        with open(session_file, "w") as f:
            f.write(session_string)
        LOGGER.info(f"Session saved for user {user_id}.")

    def _load_session_string(self, user_id: int) -> str | None:
        """Loads a user's session string from a file if it exists."""
        session_file = self._get_session_path(user_id)
        if session_file.exists():
            with open(session_file, "r") as f:
                return f.read().strip()
        return None

    def _create_new_user_client(self, session_string=None):
        """Creates a Telethon client with randomized device info."""
        session = StringSession(session_string) if session_string else StringSession()
        device_params = [
            {'device_model': 'iPhone 14 Pro Max', 'system_version': '17.5.1'},
            {'device_model': 'Samsung Galaxy S24 Ultra', 'system_version': 'SDK 34'},
            {'device_model': 'Desktop', 'system_version': 'Windows 11'},
            {'device_model': 'Pixel 8 Pro', 'system_version': 'SDK 34'},
        ]
        selected_device = random.choice(device_params)
        return TelegramClient(session, API_ID, API_HASH, **selected_device)

    # --- Main Worker Task ---

    async def run_group_creation_worker(self, event, user_client):
        """The main background task that creates 50 groups for the logged-in user."""
        user_id = event.sender_id
        try:
            async with self.worker_semaphore:
                LOGGER.info(f"Worker started for user {user_id}. Semaphore acquired.")
                await self.bot.send_message(user_id, '✅ **ورود موفقیت‌آمیز بود!**\n\nفرآیند ساخت ۵۰ گروه در پس‌زمینه آغاز شد. این کار ممکن است چندین ساعت طول بکشد.', buttons=MAIN_MENU_KEYBOARD)

                user_to_add = '@BotFather'
                for i in range(50):
                    group_title = f"Automated Group #{random.randint(1000, 9999)} - {i + 1}"
                    try:
                        await user_client(CreateChatRequest(users=[user_to_add], title=group_title))
                        LOGGER.info(f"Successfully created group: {group_title} for user {user_id}")

                        if (i + 1) % 10 == 0:
                            await self.bot.send_message(user_id, f"⏳ پیشرفت: {i + 1} گروه از ۵۰ گروه ساخته شد...")

                        sleep_duration = random.randint(400, 1000)
                        LOGGER.info(f"User {user_id} waiting for {sleep_duration} seconds...")
                        await asyncio.sleep(sleep_duration)
                    except errors.UserRestrictedError:
                        LOGGER.error(f"User {user_id} is restricted from creating groups.")
                        await self.bot.send_message(user_id, '❌ **خطا:** حساب شما به دلیل ریپورت اسپم توسط تلگرام محدود شده و نمی‌تواند گروه بسازد.')
                        break
                    except errors.FloodWaitError as fwe:
                        LOGGER.warning(f"Flood wait for user {user_id}. Sleeping for {fwe.seconds} seconds.")
                        await self.bot.send_message(user_id, f"⏳ به دلیل محدودیت تلگرام، عملیات به مدت {fwe.seconds / 60:.2f} دقیقه متوقف شد.")
                        await asyncio.sleep(fwe.seconds)
                    except Exception as e:
                        LOGGER.error(f"Could not create group {group_title} for user {user_id}", exc_info=True)
                        await self.bot.send_message(user_id, f"❌ خطای غیرمنتظره در هنگام ساخت گروه رخ داد.")
                        await asyncio.sleep(60)
        except asyncio.CancelledError:
            LOGGER.info(f"Group creation task for user {user_id} was cancelled.")
            await self.bot.send_message(user_id, "ℹ️ عملیات ساخت گروه لغو شد.")
        finally:
            LOGGER.info(f"Worker finished for user {user_id}. Releasing semaphore.")
            await self.bot.send_message(user_id, '🏁 چرخه ساخت گروه‌ها به پایان رسید.', buttons=MAIN_MENU_KEYBOARD)
            if user_id in self.active_workers:
                del self.active_workers[user_id]
            if user_client.is_connected():
                await user_client.disconnect()


    async def on_login_success(self, event, user_client):
        """Handles the logic after a successful login."""
        user_id = event.sender_id
        
        # Save the session for future use
        self._save_session_string(user_id, user_client.session.save())
        
        # Clean up temporary login state
        if user_id in self.login_sessions:
            del self.login_sessions[user_id]
            
        # Create and track the worker task
        task = asyncio.create_task(self.run_group_creation_worker(event, user_client))
        self.active_workers[user_id] = task

    # --- Bot Event Handlers ---

    async def _start_handler(self, event):
        """Handles the /start command and shows the main menu."""
        await event.reply(
            '**🤖 به ربات سازنده گروه خوش آمدید!**\n\n'
            'از دکمه‌های زیر برای شروع یا مدیریت فرآیند استفاده کنید.',
            buttons=MAIN_MENU_KEYBOARD
        )
        raise events.StopPropagation

    async def _help_handler(self, event):
        """Handles the help button."""
        await event.reply(
            '**راهنمای ربات**\n\n'
            f'1.  **{BTN_START_PROCESS}**: این دکمه فرآیند ورود به حساب شما و ساخت اتوماتیک گروه‌ها را آغاز می‌کند.\n'
            '2.  **شماره تلفن**: شماره خود را با کد کشور وارد کنید (مثال: +989123456789).\n'
            '3.  **کد و رمز**: کد ورود و در صورت نیاز، رمز تایید دو مرحله‌ای خود را وارد کنید.\n'
            f'4.  **{BTN_CANCEL}**: در هر مرحله‌ای، می‌توانید با این دکمه عملیات را متوقف کنید.',
            buttons=MAIN_MENU_KEYBOARD
        )
        raise events.StopPropagation
    
    async def _cancel_handler(self, event):
        """Handles the cancel command/button."""
        user_id = event.sender_id
        cancelled = False
        
        if user_id in self.active_workers:
            self.active_workers[user_id].cancel()
            del self.active_workers[user_id]
            cancelled = True
        
        if user_id in self.login_sessions:
            if 'client' in self.login_sessions[user_id] and self.login_sessions[user_id]['client'].is_connected():
                await self.login_sessions[user_id]['client'].disconnect()
            del self.login_sessions[user_id]
            cancelled = True

        if cancelled:
            await event.reply('✅ عملیات فعلی با موفقیت لغو شد.', buttons=MAIN_MENU_KEYBOARD)
        else:
            await event.reply('ℹ️ هیچ عملیات فعالی برای لغو وجود ندارد.', buttons=MAIN_MENU_KEYBOARD)
        raise events.StopPropagation

    async def _start_process_handler(self, event):
        """Handles the user clicking 'Start Process'."""
        user_id = event.sender_id

        if user_id in self.active_workers:
            await event.reply('⏳ یک فرآیند ساخت گروه برای شما در حال اجراست. لطفا منتظر بمانید یا آن را لغو کنید.')
            return

        if user_id in self.login_sessions:
            await event.reply('⏳ شما در حال طی کردن مراحل ورود هستید. لطفا ادامه دهید.')
            return
            
        # Check for a saved session first
        saved_session = self._load_session_string(user_id)
        if saved_session:
            await event.reply('🔄 در حال ورود با نشست ذخیره شده... لطفا صبر کنید.')
            user_client = self._create_new_user_client(saved_session)
            try:
                await user_client.connect()
                if await user_client.is_user_authorized():
                    LOGGER.info(f"User {user_id} re-logged in via saved session.")
                    # Start the worker directly
                    task = asyncio.create_task(self.run_group_creation_worker(event, user_client))
                    self.active_workers[user_id] = task
                    return
                else: # Session might be expired
                    LOGGER.warning(f"Session for {user_id} is expired. Deleting.")
                    self._get_session_path(user_id).unlink(missing_ok=True) # Delete expired session
            except Exception as e:
                 LOGGER.error(f"Failed to re-login user {user_id} with session: {e}")
                 self._get_session_path(user_id).unlink(missing_ok=True) # Delete bad session

        # If no valid session, start the normal login flow
        self.login_sessions[user_id] = {'state': 'awaiting_phone'}
        await event.reply('📞 لطفا شماره تلفن تلگرام خود را با فرمت بین‌المللی ارسال کنید (مثال: +989123456789).')

    async def _message_router(self, event):
        """Routes incoming messages to the correct handler based on user state or button press."""
        user_id = event.sender_id
        text = event.text
        
        # Route based on button text
        if text == BTN_START_PROCESS:
            await self._start_process_handler(event)
            return
        if text == BTN_CANCEL:
            await self._cancel_handler(event)
            return
        if text == BTN_HELP:
            await self._help_handler(event)
            return
            
        # Route based on login state
        if user_id in self.login_sessions:
            state = self.login_sessions[user_id].get('state')
            if state == 'awaiting_phone': await self._handle_phone_input(event)
            elif state == 'awaiting_code': await self._handle_code_input(event)
            elif state == 'awaiting_password': await self._handle_password_input(event)

    async def _handle_phone_input(self, event):
        """Handles the user's phone number submission."""
        user_id = event.sender_id
        self.login_sessions[user_id]['phone'] = event.text.strip()
        user_client = self._create_new_user_client()
        self.login_sessions[user_id]['client'] = user_client
        try:
            await user_client.connect()
            sent_code = await user_client.send_code_request(self.login_sessions[user_id]['phone'])
            self.login_sessions[user_id]['phone_code_hash'] = sent_code.phone_code_hash
            await event.reply('💬 یک کد ورود به حساب تلگرام شما ارسال شد. لطفا آن را اینجا ارسال کنید.')
            self.login_sessions[user_id]['state'] = 'awaiting_code'
        except errors.PhoneNumberInvalidError:
            await event.reply('❌ **خطا:** فرمت شماره تلفن نامعتبر است. لطفا دوباره تلاش کنید.')
            del self.login_sessions[user_id]
        except Exception as e:
            LOGGER.error(f"Phone input error for user {user_id}: {e}", exc_info=True)
            await event.reply('❌ **خطا:** یک مشکل داخلی در هنگام ارسال کد رخ داد.')
            del self.login_sessions[user_id]

    async def _handle_code_input(self, event):
        """Handles the user's login code submission."""
        user_id = event.sender_id
        user_client = self.login_sessions[user_id]['client']
        phone_code_hash = self.login_sessions[user_id].get('phone_code_hash')
        try:
            await user_client.sign_in(self.login_sessions[user_id]['phone'], code=event.text.strip(), phone_code_hash=phone_code_hash)
            await self.on_login_success(event, user_client)
        except errors.SessionPasswordNeededError:
            await event.reply('🔑 حساب شما دارای تایید دو مرحله‌ای است. لطفا رمز عبور خود را ارسال کنید.')
            self.login_sessions[user_id]['state'] = 'awaiting_password'
        except (errors.PhoneNumberBannedError, errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError) as e:
            error_map = {
                'PhoneNumberBannedError': 'این شماره تلفن توسط تلگرام مسدود شده و قابل استفاده نیست.',
                'PhoneCodeInvalidError': 'کد وارد شده نامعتبر است.',
                'PhoneCodeExpiredError': 'کد منقضی شده است. لطفا فرآیند را مجددا آغاز کنید.'
            }
            await event.reply(f'❌ **خطا:** {error_map.get(type(e).__name__, "خطای ناشناخته.")}')
            del self.login_sessions[user_id]
        except Exception as e:
            LOGGER.error(f"Code input error for user {user_id}: {e}", exc_info=True)
            await event.reply('❌ **خطا:** یک مشکل داخلی رخ داده است.')
            del self.login_sessions[user_id]

    async def _handle_password_input(self, event):
        """Handles the user's 2FA password submission."""
        user_id = event.sender_id
        user_client = self.login_sessions[user_id]['client']
        try:
            await user_client.sign_in(password=event.text.strip())
            await self.on_login_success(event, user_client)
        except errors.PasswordHashInvalidError:
            await event.reply('❌ **خطا:** رمز عبور اشتباه است. لطفا دوباره تلاش کنید.')
        except Exception as e:
            LOGGER.error(f"Password input error for user {user_id}: {e}", exc_info=True)
            await event.reply('❌ **خطا:** یک مشکل داخلی رخ داده است.')
            del self.login_sessions[user_id]
            
    def register_handlers(self):
        """Registers all event handlers with the bot client."""
        self.bot.add_event_handler(self._start_handler, events.NewMessage(pattern='/start'))
        self.bot.add_event_handler(self._cancel_handler, events.NewMessage(pattern='/cancel'))
        self.bot.add_event_handler(self._message_router, events.NewMessage)

    async def run(self):
        """Starts the bot and runs until disconnected."""
        self.register_handlers()
        LOGGER.info("Starting bot...")
        await self.bot.start(bot_token=BOT_TOKEN)
        LOGGER.info("Bot service has started successfully.")
        await self.bot.run_until_disconnected()

if __name__ == "__main__":
    bot_instance = GroupCreatorBot()
    asyncio.run(bot_instance.run())
