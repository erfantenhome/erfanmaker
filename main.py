import asyncio
import logging
import os
import random
from pathlib import Path
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CreateChatRequest
from telethon.tl.types import ReplyKeyboardMarkup, KeyboardButton, Message

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

# --- Configuration & Security Note ---
# IMPORTANT: Make sure your .env file and the 'sessions' directory are secure.
# In a production environment, set permissions:
# chmod 600 .env
# chmod 700 sessions/
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing required environment variables in your .env file.")

API_ID = int(API_ID)
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)  # Ensure the sessions directory exists
MAX_CONCURRENT_WORKERS = 5  # Limit how many users can run the task simultaneously

# --- Bot Menu Buttons ---
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

    def __init__(self) -> None:
        """Initializes the bot instance."""
        self.bot = TelegramClient('bot_session', API_ID, API_HASH)
        # In-memory storage for the multi-step login flow
        self.login_sessions: Dict[int, Dict[str, Any]] = {}
        # Tracks active group creation tasks (user_id -> asyncio.Task)
        self.active_workers: Dict[int, asyncio.Task] = {}
        # Limits concurrent group creation tasks to prevent overload
        self.worker_semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)

    # --- Helper Functions ---

    def _get_session_path(self, user_id: int) -> Path:
        """Returns the file path for a user's session."""
        return SESSIONS_DIR / f"user_{user_id}.session"

    def _save_session_string(self, user_id: int, session_string: str) -> None:
        """Saves a user's session string to a file."""
        session_file = self._get_session_path(user_id)
        with open(session_file, "w") as f:
            f.write(session_string)
        LOGGER.info(f"Session saved for user {user_id}.")

    def _load_session_string(self, user_id: int) -> Optional[str]:
        """Loads a user's session string from a file if it exists."""
        session_file = self._get_session_path(user_id)
        if session_file.exists():
            return session_file.read_text().strip()
        return None
    
    def _delete_session_file(self, user_id: int) -> None:
        """Deletes a user's session file if it exists."""
        try:
            self._get_session_path(user_id).unlink(missing_ok=True)
            LOGGER.info(f"Deleted session file for user {user_id}.")
        except OSError as e:
            LOGGER.error(f"Error deleting session file for user {user_id}: {e}")

    def _create_new_user_client(self, session_string: Optional[str] = None) -> TelegramClient:
        """Creates a Telethon client with randomized device info."""
        session = StringSession(session_string) if session_string else StringSession()
        # Expanded device pool for more randomness
        device_params = [
            {'device_model': 'iPhone 14 Pro Max', 'system_version': '17.5.1', 'app_version': '10.9.1'},
            {'device_model': 'Samsung Galaxy S24 Ultra', 'system_version': 'SDK 34', 'app_version': '10.9.1'},
            {'device_model': 'Desktop', 'system_version': 'Windows 11', 'app_version': '4.16.8'},
            {'device_model': 'Pixel 8 Pro', 'system_version': 'SDK 34', 'app_version': '10.9.0'},
            {'device_model': 'iPhone 13', 'system_version': '17.1.1', 'app_version': '10.5.0'},
            {'device_model': 'Samsung Galaxy A54', 'system_version': 'SDK 33', 'app_version': '10.8.0'},
            {'device_model': 'MacBook Pro', 'system_version': 'macOS 14.5', 'app_version': '10.9.1'},
            {'device_model': 'Xiaomi 13T Pro', 'system_version': 'SDK 34', 'app_version': '10.9.1'},
        ]
        selected_device = random.choice(device_params)
        return TelegramClient(session, API_ID, API_HASH, **selected_device)

    # --- Main Worker Task ---

    async def run_group_creation_worker(self, event: events.NewMessage.Event, user_client: TelegramClient) -> None:
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

                        sleep_duration = random.randint(400, 800)
                        LOGGER.info(f"User {user_id} waiting for {sleep_duration} seconds...")
                        await asyncio.sleep(sleep_duration)
                    except errors.UserRestrictedError:
                        LOGGER.error(f"User {user_id} is restricted from creating groups.")
                        await self.bot.send_message(user_id, '❌ **خطا:** حساب شما به دلیل ریپورت اسپم توسط تلگرام محدود شده و نمی‌تواند گروه بسازد.')
                        break
                    except errors.FloodWaitError as fwe:
                        LOGGER.warning(f"Flood wait for user {user_id}. Sleeping for {fwe.seconds} seconds.")
                        await self.bot.send_message(
                            user_id,
                            f"⏳ **عملیات موقتا متوقف شد!**\n\n"
                            f"تلگرام برای جلوگیری از اسپم، درخواست‌های ما را به مدت **{fwe.seconds / 60:.1f} دقیقه** محدود کرده است. "
                            f"این یک اقدام استاندارد است و ربات به صورت خودکار ادامه خواهد داد. لطفاً صبور باشید."
                        )
                        await asyncio.sleep(fwe.seconds)
                    except Exception:
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


    async def on_login_success(self, event: events.NewMessage.Event, user_client: TelegramClient) -> None:
        """Handles the logic after a successful login, saving the session and starting the worker."""
        user_id = event.sender_id
        
        self._save_session_string(user_id, user_client.session.save())
        
        if user_id in self.login_sessions:
            del self.login_sessions[user_id]
            
        task = asyncio.create_task(self.run_group_creation_worker(event, user_client))
        self.active_workers[user_id] = task

    # --- Bot Event Handlers ---

    async def _start_handler(self, event: events.NewMessage.Event) -> None:
        """Handles the /start command and shows the main menu."""
        await event.reply(
            '**🤖 به ربات سازنده گروه خوش آمدید!**\n\n'
            'از دکمه‌های زیر برای شروع یا مدیریت فرآیند استفاده کنید.',
            buttons=MAIN_MENU_KEYBOARD
        )
        raise events.StopPropagation

    async def _help_handler(self, event: events.NewMessage.Event) -> None:
        """Handles the help button, providing instructions."""
        await event.reply(
            '**راهنمای ربات**\n\n'
            f'1.  **{BTN_START_PROCESS}**: این دکمه فرآیند ورود به حساب و ساخت اتوماتیک گروه‌ها را آغاز می‌کند.\n'
            '2.  **شماره تلفن**: شماره خود را با کد کشور وارد کنید (مثال: `+989123456789`).\n'
            '3.  **کد و رمز**: کد ورود و در صورت نیاز، رمز تایید دو مرحله‌ای خود را وارد کنید.\n'
            f'4.  **{BTN_CANCEL}**: در هر مرحله‌ای، می‌توانید با این دکمه عملیات را متوقف کنید.',
            buttons=MAIN_MENU_KEYBOARD
        )
        raise events.StopPropagation
    
    async def _cancel_handler(self, event: events.NewMessage.Event) -> None:
        """Handles the cancel command/button, stopping any active task or login flow."""
        user_id = event.sender_id
        cancelled = False
        
        if user_id in self.active_workers:
            self.active_workers[user_id].cancel()
            del self.active_workers[user_id]
            cancelled = True
        
        if user_id in self.login_sessions:
            client = self.login_sessions[user_id].get('client')
            if client and client.is_connected():
                await client.disconnect()
            del self.login_sessions[user_id]
            cancelled = True

        if cancelled:
            await event.reply('✅ عملیات فعلی با موفقیت لغو شد.', buttons=MAIN_MENU_KEYBOARD)
        else:
            await event.reply('ℹ️ هیچ عملیات فعالی برای لغو وجود ندارد.', buttons=MAIN_MENU_KEYBOARD)
        raise events.StopPropagation

    async def _start_process_handler(self, event: events.NewMessage.Event) -> None:
        """Handles the 'Start Process' button, using a saved session or starting a new login."""
        user_id = event.sender_id

        if user_id in self.active_workers:
            await event.reply('⏳ یک فرآیند ساخت گروه برای شما در حال اجراست. لطفا منتظر بمانید یا آن را لغو کنید.')
            return

        if user_id in self.login_sessions:
            await event.reply('⏳ شما در حال طی کردن مراحل ورود هستید. لطفا ادامه دهید.')
            return
            
        saved_session = self._load_session_string(user_id)
        if saved_session:
            await event.reply('🔄 در حال ورود با نشست ذخیره شده... لطفا صبر کنید.')
            user_client = self._create_new_user_client(saved_session)
            try:
                await user_client.connect()
                if await user_client.is_user_authorized():
                    LOGGER.info(f"User {user_id} re-logged in via saved session.")
                    await self.on_login_success(event, user_client)
                else:
                    LOGGER.warning(f"Session for user {user_id} is no longer authorized. Deleting.")
                    self._delete_session_file(user_id)
                    await event.reply(
                        '⚠️ **نشست شما منقضی شده است.**\n\nنشست ذخیره شده حذف شد. لطفاً دوباره وارد شوید.',
                        buttons=MAIN_MENU_KEYBOARD
                    )
                    await self._initiate_login_flow(event)
            except (errors.UserDeactivatedBanError, errors.AuthKeyUnregisteredError) as e:
                LOGGER.error(f"Saved session for user {user_id} is invalid (Banned/Deleted): {e}")
                self._delete_session_file(user_id)
                await event.reply(
                    '❌ **حساب شما مسدود یا حذف شده است.**\n\nنشست ذخیره شده شما نامعتبر است و حذف شد.',
                    buttons=MAIN_MENU_KEYBOARD
                )
            except Exception as e:
                 LOGGER.error(f"Failed to re-login user {user_id} with session: {e}", exc_info=True)
                 self._delete_session_file(user_id)
                 await event.reply('❌ خطایی در اتصال با نشست قبلی رخ داد. لطفا دوباره وارد شوید.', buttons=MAIN_MENU_KEYBOARD)
                 await self._initiate_login_flow(event)
            return

        await self._initiate_login_flow(event)

    async def _initiate_login_flow(self, event: events.NewMessage.Event) -> None:
        """Starts the phone number collection step for a new login."""
        self.login_sessions[event.sender_id] = {'state': 'awaiting_phone'}
        await event.reply('📞 لطفا شماره تلفن تلگرام خود را با فرمت بین‌المللی ارسال کنید (مثال: `+989123456789`).')

    async def _message_router(self, event: events.NewMessage.Event) -> None:
        """Routes all incoming messages to the correct handler based on user state or button press."""
        if not isinstance(getattr(event, 'message', None), Message) or not event.message.text:
             return
        
        user_id = event.sender_id
        text = event.message.text
        
        route_map = {
            BTN_START_PROCESS: self._start_process_handler,
            BTN_CANCEL: self._cancel_handler,
            BTN_HELP: self._help_handler,
        }
        if text in route_map:
            await route_map[text](event)
            return
            
        if user_id in self.login_sessions:
            state = self.login_sessions[user_id].get('state')
            state_map = {
                'awaiting_phone': self._handle_phone_input,
                'awaiting_code': self._handle_code_input,
                'awaiting_password': self._handle_password_input,
            }
            if state in state_map:
                await state_map[state](event)

    async def _handle_phone_input(self, event: events.NewMessage.Event) -> None:
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
            if user_id in self.login_sessions:
                del self.login_sessions[user_id]

    async def _handle_code_input(self, event: events.NewMessage.Event) -> None:
        """Handles the user's login code submission."""
        user_id = event.sender_id
        user_client = self.login_sessions[user_id]['client']
        phone_code_hash = self.login_sessions[user_id].get('phone_code_hash')
        try:
            await user_client.sign_in(
                self.login_sessions[user_id]['phone'],
                code=event.text.strip(),
                phone_code_hash=phone_code_hash
            )
            await self.on_login_success(event, user_client)
        except errors.SessionPasswordNeededError:
            await event.reply('🔑 حساب شما دارای تایید دو مرحله‌ای است. لطفا رمز عبور خود را ارسال کنید.')
            self.login_sessions[user_id]['state'] = 'awaiting_password'
        except (errors.PhoneNumberBannedError, errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError) as e:
            error_map = {
                'PhoneNumberBannedError': 'این شماره تلفن توسط تلگرام مسدود شده.',
                'PhoneCodeInvalidError': 'کد وارد شده نامعتبر است.',
                'PhoneCodeExpiredError': 'کد منقضی شده است. لطفا فرآیند را مجددا آغاز کنید.'
            }
            await event.reply(f'❌ **خطا:** {error_map.get(type(e).__name__, "خطای ناشناخته.")}')
            del self.login_sessions[user_id]
        except Exception as e:
            LOGGER.error(f"Code input error for user {user_id}: {e}", exc_info=True)
            await event.reply('❌ **خطا:** یک مشکل داخلی رخ داده است.')
            if user_id in self.login_sessions:
                del self.login_sessions[user_id]

    async def _handle_password_input(self, event: events.NewMessage.Event) -> None:
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
            if user_id in self.login_sessions:
                del self.login_sessions[user_id]
            
    def register_handlers(self) -> None:
        """Registers all event handlers with the bot client."""
        self.bot.add_event_handler(self._start_handler, events.NewMessage(pattern='/start'))
        self.bot.add_event_handler(self._message_router, events.NewMessage)

    async def run(self) -> None:
        """Starts the bot and runs until disconnected."""
        self.register_handlers()
        LOGGER.info("Starting bot...")
        await self.bot.start(bot_token=BOT_TOKEN)
        LOGGER.info("Bot service has started successfully.")
        await self.bot.run_until_disconnected()

if __name__ == "__main__":
    bot_instance = GroupCreatorBot()
    asyncio.run(bot_instance.run())
