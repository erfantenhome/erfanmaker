import asyncio
import base64
import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv
# Use the high-level Button helper
from telethon import Button, TelegramClient, errors, events
from telethon.sessions import StringSession
from telethon.tl.functions.messages import CreateChatRequest
from telethon.tl.types import Message

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
# NEW: Key for encrypting session files at rest
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not all([API_ID, API_HASH, BOT_TOKEN, ENCRYPTION_KEY]):
    raise ValueError("Missing required environment variables. Ensure API_ID, API_HASH, BOT_TOKEN, and ENCRYPTION_KEY are set.")

API_ID = int(API_ID)
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
MAX_CONCURRENT_WORKERS = 5

# --- Bot Menu Buttons ---
BTN_START_PROCESS = "🚀 شروع ساخت گروه"
BTN_CANCEL = "❌ لغو عملیات"
BTN_HELP = "ℹ️ راهنما"

MAIN_MENU_KEYBOARD = [
    [Button.text(BTN_START_PROCESS)],
    [Button.text(BTN_CANCEL), Button.text(BTN_HELP)],
]


class GroupCreatorBot:
    """A class to encapsulate the bot's logic, state, and handlers."""

    def __init__(self) -> None:
        """Initializes the bot instance and the encryption engine."""
        self.bot = TelegramClient('bot_session', API_ID, API_HASH)
        self.login_sessions: Dict[int, Dict[str, Any]] = {}
        self.active_workers: Dict[int, asyncio.Task] = {}
        self.worker_semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)

        # Initialize encryption engine
        try:
            self.fernet = Fernet(ENCRYPTION_KEY.encode())
        except (ValueError, TypeError):
            raise ValueError("Invalid ENCRYPTION_KEY. Please generate a valid key.")

    # --- Encryption Helpers ---

    def _encrypt_data(self, data: str) -> bytes:
        """Encrypts a string."""
        return self.fernet.encrypt(data.encode())

    def _decrypt_data(self, encrypted_data: bytes) -> Optional[str]:
        """Decrypts bytes back into a string."""
        try:
            return self.fernet.decrypt(encrypted_data).decode()
        except InvalidToken:
            LOGGER.error("Failed to decrypt session data. The key may have changed or the data is corrupt.")
            return None

    # --- Session Helpers ---

    def _get_session_path(self, user_id: int) -> Path:
        return SESSIONS_DIR / f"user_{user_id}.session"

    def _save_session_string(self, user_id: int, session_string: str) -> None:
        """Encrypts and saves a user's session string to a file."""
        encrypted_session = self._encrypt_data(session_string)
        session_file = self._get_session_path(user_id)
        session_file.write_bytes(encrypted_session)
        LOGGER.info(f"Encrypted session saved for user {user_id}.")

    def _load_session_string(self, user_id: int) -> Optional[str]:
        """Loads and decrypts a user's session string from a file."""
        session_file = self._get_session_path(user_id)
        if not session_file.exists():
            return None

        encrypted_session = session_file.read_bytes()
        if not encrypted_session:
            return None

        return self._decrypt_data(encrypted_session)

    # --- Core Bot Logic (Unchanged from previous version) ---

    def _delete_session_file(self, user_id: int) -> None:
        try:
            self._get_session_path(user_id).unlink(missing_ok=True)
            LOGGER.info(f"Deleted session file for user {user_id}.")
        except OSError as e:
            LOGGER.error(f"Error deleting session file for user {user_id}: {e}")

    def _create_new_user_client(self, session_string: Optional[str] = None) -> TelegramClient:
        session = StringSession(session_string) if session_string else StringSession()
        device_params = [
            {'device_model': 'iPhone 14 Pro Max', 'system_version': '17.5.1', 'app_version': '10.9.1'},
            {'device_model': 'Samsung Galaxy S24 Ultra', 'system_version': 'SDK 34', 'app_version': '10.9.1'},
            {'device_model': 'Desktop', 'system_version': 'Windows 11', 'app_version': '4.16.8'},
        ]
        return TelegramClient(session, API_ID, API_HASH, **random.choice(device_params))

    async def run_group_creation_worker(self, event: events.NewMessage.Event, user_client: TelegramClient) -> None:
        user_id = event.sender_id
        try:
            async with self.worker_semaphore:
                LOGGER.info(f"Worker started for user {user_id}.")
                await self.bot.send_message(user_id, '✅ **ورود موفقیت‌آمیز بود!**\n\nفرآیند ساخت ۵۰ گروه آغاز شد.', buttons=MAIN_MENU_KEYBOARD)

                for i in range(50):
                    group_title = f"Automated Group #{random.randint(1000, 9999)} - {i + 1}"
                    try:
                        await user_client(CreateChatRequest(users=['@BotFather'], title=group_title))
                        LOGGER.info(f"Created group: {group_title} for user {user_id}")

                        if (i + 1) % 10 == 0:
                            await self.bot.send_message(user_id, f"⏳ پیشرفت: {i + 1} گروه از ۵۰ گروه ساخته شد...")

                        await asyncio.sleep(random.randint(400, 800))
                    except errors.UserRestrictedError:
                        LOGGER.error(f"User {user_id} is restricted.")
                        await self.bot.send_message(user_id, '❌ **خطا:** حساب شما محدود شده و نمی‌تواند گروه بسازد.')
                        break
                    except errors.FloodWaitError as fwe:
                        LOGGER.warning(f"Flood wait for user {user_id}. Sleeping for {fwe.seconds}s.")
                        resume_time = datetime.now() + timedelta(seconds=fwe.seconds)
                        await self.bot.send_message(
                            user_id,
                            f"⏳ **عملیات موقتا متوقف شد!**\n\n"
                            f"تلگرام برای جلوگیری از اسپم، درخواست‌ها را به مدت **{fwe.seconds / 60:.1f} دقیقه** محدود کرده است.\n"
                            f"▶️ **زمان تقریبی ادامه:** `{resume_time.strftime('%H:%M:%S')}`"
                        )
                        await asyncio.sleep(fwe.seconds)
                    except Exception as e:
                        LOGGER.error(f"Could not create group {group_title} for {user_id}", exc_info=e)
                        await self.bot.send_message(user_id, f"❌ خطای غیرمنتظره در هنگام ساخت گروه رخ داد.")
                        await asyncio.sleep(60)
        except asyncio.CancelledError:
            LOGGER.info(f"Task for user {user_id} was cancelled.")
            await self.bot.send_message(user_id, "ℹ️ عملیات ساخت گروه لغو شد.")
        finally:
            LOGGER.info(f"Worker finished for user {user_id}.")
            await self.bot.send_message(user_id, '🏁 چرخه ساخت گروه‌ها به پایان رسید.', buttons=MAIN_MENU_KEYBOARD)
            if user_id in self.active_workers:
                del self.active_workers[user_id]
            if user_client.is_connected():
                await user_client.disconnect()

    async def on_login_success(self, event: events.NewMessage.Event, user_client: TelegramClient) -> None:
        user_id = event.sender_id
        self._save_session_string(user_id, user_client.session.save())
        if user_id in self.login_sessions:
            del self.login_sessions[user_id]
        task = asyncio.create_task(self.run_group_creation_worker(event, user_client))
        self.active_workers[user_id] = task

    async def _start_handler(self, event: events.NewMessage.Event) -> None:
        await event.reply(
            '**🤖 به ربات سازنده گروه خوش آمدید!**\n\n'
            'از دکمه‌های زیر برای شروع یا مدیریت فرآیند استفاده کنید.',
            buttons=MAIN_MENU_KEYBOARD
        )
        raise events.StopPropagation

    async def _cancel_handler(self, event: events.NewMessage.Event) -> None:
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
        user_id = event.sender_id
        if user_id in self.active_workers or user_id in self.login_sessions:
            await event.reply('⏳ یک فرآیند برای شما در حال اجراست. لطفا منتظر بمانید یا آن را لغو کنید.')
            return

        saved_session = self._load_session_string(user_id)
        if saved_session:
            await event.reply('🔄 در حال ورود با نشست امن ذخیره شده...')
            user_client = self._create_new_user_client(saved_session)
            try:
                await user_client.connect()
                if await user_client.is_user_authorized():
                    await self.on_login_success(event, user_client)
                else:
                    self._delete_session_file(user_id)
                    await event.reply('⚠️ نشست شما منقضی شده. لطفا دوباره وارد شوید.')
                    await self._initiate_login_flow(event)
            except (errors.UserDeactivatedBanError, errors.AuthKeyUnregisteredError) as e:
                LOGGER.error(f"Saved session for {user_id} is invalid: {e}")
                self._delete_session_file(user_id)
                await event.reply('❌ حساب شما مسدود یا حذف شده و نشست آن پاک شد.')
            except Exception as e:
                LOGGER.error(f"Failed to re-login user {user_id} with session", exc_info=e)
                self._delete_session_file(user_id)
                await event.reply('❌ خطایی در اتصال با نشست قبلی رخ داد. لطفا دوباره وارد شوید.')
                await self._initiate_login_flow(event)
            return
        await self._initiate_login_flow(event)

    async def _initiate_login_flow(self, event: events.NewMessage.Event) -> None:
        self.login_sessions[event.sender_id] = {'state': 'awaiting_phone'}
        await event.reply('📞 لطفا شماره تلفن خود را با فرمت بین‌المللی ارسال کنید (مثال: `+989123456789`).')

    async def _message_router(self, event: events.NewMessage.Event) -> None:
        if not isinstance(getattr(event, 'message', None), Message) or not event.message.text:
            return

        text = event.message.text
        route_map = {
            BTN_START_PROCESS: self._start_process_handler,
            BTN_CANCEL: self._cancel_handler,
            BTN_HELP: self._start_handler,
        }
        if text in route_map:
            await route_map[text](event)
            return

        user_id = event.sender_id
        if user_id in self.login_sessions:
            state_map = {
                'awaiting_phone': self._handle_phone_input,
                'awaiting_code': self._handle_code_input,
                'awaiting_password': self._handle_password_input,
            }
            state = self.login_sessions[user_id].get('state')
            if state in state_map:
                await state_map[state](event)

    async def _handle_phone_input(self, event: events.NewMessage.Event) -> None:
        user_id = event.sender_id
        self.login_sessions[user_id]['phone'] = event.text.strip()
        user_client = self._create_new_user_client()
        self.login_sessions[user_id]['client'] = user_client
        try:
            await user_client.connect()
            sent_code = await user_client.send_code_request(self.login_sessions[user_id]['phone'])
            self.login_sessions[user_id]['phone_code_hash'] = sent_code.phone_code_hash
            await event.reply('💬 کد ورود به تلگرام شما ارسال شد. لطفا آن را اینجا ارسال کنید.')
            self.login_sessions[user_id]['state'] = 'awaiting_code'
        except (errors.PhoneNumberInvalidError, Exception) as e:
            LOGGER.error(f"Phone input error for {user_id}", exc_info=e)
            if user_id in self.login_sessions:
                del self.login_sessions[user_id]
            await event.reply('❌ **خطا:** شماره تلفن نامعتبر است یا مشکلی در ارسال کد رخ داد.')

    async def _handle_code_input(self, event: events.NewMessage.Event) -> None:
        user_id = event.sender_id
        user_client = self.login_sessions[user_id]['client']
        try:
            await user_client.sign_in(
                self.login_sessions[user_id]['phone'],
                code=event.text.strip(),
                phone_code_hash=self.login_sessions[user_id].get('phone_code_hash')
            )
            await self.on_login_success(event, user_client)
        except errors.SessionPasswordNeededError:
            await event.reply('🔑 حساب شما تایید دو مرحله‌ای دارد. لطفا رمز عبور را ارسال کنید.')
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
            LOGGER.error(f"Code input error for {user_id}", exc_info=e)
            if user_id in self.login_sessions:
                del self.login_sessions[user_id]
            await event.reply('❌ **خطا:** یک مشکل داخلی رخ داده است.')

    async def _handle_password_input(self, event: events.NewMessage.Event) -> None:
        user_id = event.sender_id
        user_client = self.login_sessions[user_id]['client']
        try:
            await user_client.sign_in(password=event.text.strip())
            await self.on_login_success(event, user_client)
        except errors.PasswordHashInvalidError:
            await event.reply('❌ **خطا:** رمز عبور اشتباه است. لطفا دوباره تلاش کنید.')
        except Exception as e:
            LOGGER.error(f"Password input error for {user_id}", exc_info=e)
            if user_id in self.login_sessions:
                del self.login_sessions[user_id]
            await event.reply('❌ **خطا:** یک مشکل داخلی رخ داده است.')

    def register_handlers(self) -> None:
        self.bot.add_event_handler(self._start_handler, events.NewMessage(pattern='/start'))
        self.bot.add_event_handler(self._cancel_handler, events.NewMessage(pattern='/cancel'))
        self.bot.add_event_handler(self._message_router, events.NewMessage)

    async def run(self) -> None:
        self.register_handlers()
        LOGGER.info("Starting bot...")
        await self.bot.start(bot_token=BOT_TOKEN)
        LOGGER.info("Bot service has started successfully.")
        await self.bot.run_until_disconnected()

if __name__ == "__main__":
    bot_instance = GroupCreatorBot()
    asyncio.run(bot_instance.run())
