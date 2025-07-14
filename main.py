import asyncio
import logging
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
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
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not all([API_ID, API_HASH, BOT_TOKEN, ENCRYPTION_KEY]):
    raise ValueError("Missing required environment variables. Ensure API_ID, API_HASH, BOT_TOKEN, and ENCRYPTION_KEY are set.")

API_ID = int(API_ID)
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
MAX_CONCURRENT_WORKERS = 5

# --- Bot Menu Buttons ---
BTN_MANAGE_ACCOUNTS = "👤 مدیریت حساب‌ها"
BTN_HELP = "ℹ️ راهنما"
BTN_BACK = "⬅️ بازگشت"
BTN_ADD_ACCOUNT = "➕ افزودن حساب جدید"

MAIN_MENU_KEYBOARD = [
    [Button.text(BTN_MANAGE_ACCOUNTS)],
    [Button.text(BTN_HELP)],
]

class GroupCreatorBot:
    """A class to encapsulate the bot's logic for managing multiple accounts."""

    def __init__(self) -> None:
        """Initializes the bot instance and the encryption engine."""
        self.bot = TelegramClient('bot_session', API_ID, API_HASH)
        self.login_sessions: Dict[int, Dict[str, Any]] = {}
        self.active_workers: Dict[str, asyncio.Task] = {}  # Key is "user_id:account_name"
        self.worker_semaphore = asyncio.Semaphore(MAX_CONCURRENT_WORKERS)
        try:
            self.fernet = Fernet(ENCRYPTION_KEY.encode())
        except (ValueError, TypeError):
            raise ValueError("Invalid ENCRYPTION_KEY. Please generate a valid key.")

    # --- Encryption & Session Helpers ---
    def _encrypt_data(self, data: str) -> bytes:
        return self.fernet.encrypt(data.encode())

    def _decrypt_data(self, encrypted_data: bytes) -> Optional[str]:
        try:
            return self.fernet.decrypt(encrypted_data).decode()
        except InvalidToken:
            LOGGER.error("Failed to decrypt session data. Key may have changed or data is corrupt.")
            return None

    def _get_session_path(self, user_id: int, account_name: str) -> Path:
        """Gets the session path for a specific user and account name."""
        safe_account_name = re.sub(r'[^a-zA-Z0-9_-]', '', account_name)
        return SESSIONS_DIR / f"user_{user_id}__{safe_account_name}.session"

    def _get_user_accounts(self, user_id: int) -> List[str]:
        """Scans the session directory and returns a list of account names for a user."""
        accounts = []
        for f in SESSIONS_DIR.glob(f"user_{user_id}__*.session"):
            match = re.search(f"user_{user_id}__(.*)\\.session", f.name)
            if match:
                accounts.append(match.group(1))
        return accounts

    def _save_session_string(self, user_id: int, account_name: str, session_string: str) -> None:
        """Encrypts and saves a user's session for a specific account."""
        encrypted_session = self._encrypt_data(session_string)
        session_file = self._get_session_path(user_id, account_name)
        session_file.write_bytes(encrypted_session)
        LOGGER.info(f"Encrypted session saved for user {user_id} as account '{account_name}'.")

    def _load_session_string(self, user_id: int, account_name: str) -> Optional[str]:
        """Loads and decrypts a session for a specific account."""
        session_file = self._get_session_path(user_id, account_name)
        if not session_file.exists():
            return None
        return self._decrypt_data(session_file.read_bytes())

    def _delete_session_file(self, user_id: int, account_name: str) -> bool:
        """Deletes a session file for a specific account."""
        session_path = self._get_session_path(user_id, account_name)
        if session_path.exists():
            try:
                session_path.unlink()
                LOGGER.info(f"Deleted session file for user {user_id}, account '{account_name}'.")
                return True
            except OSError as e:
                LOGGER.error(f"Error deleting session file for user {user_id}, account '{account_name}': {e}")
        return False

    def _create_new_user_client(self, session_string: Optional[str] = None) -> TelegramClient:
        session = StringSession(session_string) if session_string else StringSession()
        device_params = [{'device_model': 'iPhone 14 Pro Max', 'system_version': '17.5.1'}, {'device_model': 'Samsung Galaxy S24 Ultra', 'system_version': 'SDK 34'}]
        return TelegramClient(session, API_ID, API_HASH, **random.choice(device_params))
        
    # --- Dynamic UI Builder ---
    def _build_accounts_menu(self, user_id: int) -> List[List[Button]]:
        """Builds the keyboard for the account management menu."""
        accounts = self._get_user_accounts(user_id)
        keyboard = []
        if not accounts:
            keyboard.append([Button.text("هنوز هیچ حسابی اضافه نشده است.")])
        else:
            for acc_name in accounts:
                worker_key = f"{user_id}:{acc_name}"
                status_icon = "⏳" if worker_key in self.active_workers else "🟢"
                keyboard.append([
                    Button.text(f"{status_icon} شروع برای {acc_name}"),
                    Button.text(f"🗑️ حذف {acc_name}")
                ])
        
        keyboard.append([Button.text(BTN_ADD_ACCOUNT)])
        keyboard.append([Button.text(BTN_BACK)])
        return keyboard

    # --- Main Worker Task ---
    async def run_group_creation_worker(self, user_id: int, account_name: str, user_client: TelegramClient) -> None:
        worker_key = f"{user_id}:{account_name}"
        try:
            async with self.worker_semaphore:
                LOGGER.info(f"Worker started for {worker_key}. Semaphore acquired.")
                
                # CHANGED: Increased sleep time for production use
                min_sleep, max_sleep = 300, 600
                avg_sleep_per_group = (min_sleep + max_sleep) / 2
                estimated_total_minutes = (50 * avg_sleep_per_group) / 60
                
                # ADDED: Initial time estimate message
                await self.bot.send_message(user_id, f"✅ **عملیات برای حساب `{account_name}` آغاز شد!**\n\n⏳ تخمین زمان کل عملیات: حدود {estimated_total_minutes:.0f} دقیقه.")

                for i in range(50):
                    group_title = f"{account_name} Group #{random.randint(1000, 9999)} - {i + 1}"
                    try:
                        await user_client(CreateChatRequest(users=['@BotFather'], title=group_title))
                        
                        # ADDED: Progress and time remaining message
                        groups_made = i + 1
                        groups_remaining = 50 - groups_made
                        time_remaining_minutes = (groups_remaining * avg_sleep_per_group) / 60
                        await self.bot.send_message(user_id, f"📊 [{account_name}] {groups_made}/50 گروه ساخته شد. زمان تقریبی باقی‌مانده: {time_remaining_minutes:.0f} دقیقه.")
                        
                        await asyncio.sleep(random.randint(min_sleep, max_sleep))

                    # ADDED: Better error handling for restricted users
                    except errors.UserRestrictedError:
                        LOGGER.error(f"Worker for {worker_key} failed: User is restricted.")
                        await self.bot.send_message(user_id, f"❌ حساب `{account_name}` توسط تلگرام محدود شده و قادر به ساخت گروه نیست. عملیات متوقف شد.")
                        break
                    except errors.FloodWaitError as fwe:
                        resume_time = datetime.now() + timedelta(seconds=fwe.seconds)
                        await self.bot.send_message(user_id, f"⏳ [{account_name}] به دلیل محدودیت تلگرام، عملیات به مدت {fwe.seconds / 60:.1f} دقیقه تا ساعت {resume_time:%H:%M:%S} متوقف شد.")
                        await asyncio.sleep(fwe.seconds)
                    except Exception as e:
                        LOGGER.error(f"Worker error for {worker_key}", exc_info=e)
                        await self.bot.send_message(user_id, f"❌ [{account_name}] خطای غیرمنتظره در ساخت گروه رخ داد.")
                        break
        except asyncio.CancelledError:
            LOGGER.info(f"Task for {worker_key} was cancelled.")
        finally:
            LOGGER.info(f"Worker finished for {worker_key}.")
            await self.bot.send_message(user_id, f"🏁 چرخه ساخت گروه برای حساب `{account_name}` به پایان رسید.")
            if worker_key in self.active_workers:
                del self.active_workers[worker_key]
            if user_client.is_connected():
                await user_client.disconnect()


    async def on_login_success(self, event: events.NewMessage.Event, user_client: TelegramClient) -> None:
        user_id = event.sender_id
        account_name = self.login_sessions[user_id]['account_name']
        self._save_session_string(user_id, account_name, user_client.session.save())
        
        if user_id in self.login_sessions:
            del self.login_sessions[user_id]
        
        await self.bot.send_message(user_id, f"✅ حساب `{account_name}` با موفقیت اضافه شد!")
        await self._manage_accounts_handler(event) # Show the updated accounts menu
        
    # --- Bot Event Handlers ---
    async def _start_handler(self, event: events.NewMessage.Event) -> None:
        await event.reply('**🤖 به ربات سازنده گروه خوش آمدید!**', buttons=MAIN_MENU_KEYBOARD)
        raise events.StopPropagation

    async def _manage_accounts_handler(self, event: events.NewMessage.Event) -> None:
        """Shows the account management menu."""
        user_id = event.sender_id
        accounts_keyboard = self._build_accounts_menu(user_id)
        await event.reply("👤 **مدیریت حساب‌ها**\n\nاز این منو می‌توانید حساب‌های خود را مدیریت کرده و عملیات ساخت گروه را برای هرکدام آغاز کنید.", buttons=accounts_keyboard)
        raise events.StopPropagation

    async def _initiate_login_flow(self, event: events.NewMessage.Event) -> None:
        """Starts the phone number collection step for a new login."""
        self.login_sessions[event.sender_id] = {'state': 'awaiting_phone'}
        await event.reply('📞 لطفا شماره تلفن حساب جدید را با فرمت بین‌المللی ارسال کنید (مثال: `+989123456789`).', buttons=Button.clear())

    async def _message_router(self, event: events.NewMessage.Event) -> None:
        """Routes all incoming messages to the correct handler."""
        if not isinstance(getattr(event, 'message', None), Message) or not event.message.text:
            return

        text = event.message.text
        user_id = event.sender_id

        # Static button routing
        route_map = { BTN_MANAGE_ACCOUNTS: self._manage_accounts_handler, BTN_HELP: self._start_handler, BTN_BACK: self._start_handler, BTN_ADD_ACCOUNT: self._initiate_login_flow }
        if text in route_map:
            await route_map[text](event)
            return

        # Regex-based routing for dynamic buttons
        start_match = re.match(r".* شروع برای (.*)", text)
        if start_match:
            acc_name = start_match.group(1)
            await self._start_process_handler(event, acc_name)
            return

        delete_match = re.match(r".* حذف (.*)", text)
        if delete_match:
            acc_name = delete_match.group(1)
            await self._delete_account_handler(event, acc_name)
            return

        # State machine for login flow
        if user_id in self.login_sessions:
            state_map = { 'awaiting_phone': self._handle_phone_input, 'awaiting_code': self._handle_code_input, 'awaiting_password': self._handle_password_input, 'awaiting_account_name': self._handle_account_name_input }
            state = self.login_sessions[user_id].get('state')
            if state in state_map:
                await state_map[state](event)

    async def _start_process_handler(self, event: events.NewMessage.Event, account_name: str) -> None:
        """Starts the group creation worker for a specific account."""
        user_id = event.sender_id
        worker_key = f"{user_id}:{account_name}"

        if worker_key in self.active_workers:
            await event.reply('⏳ عملیات برای این حساب در حال اجراست.')
            return

        session_str = self._load_session_string(user_id, account_name)
        if not session_str:
            await event.reply('❌ نشست برای این حساب یافت نشد. لطفا آن را حذف و دوباره اضافه کنید.')
            return

        await event.reply(f'🚀 در حال آماده‌سازی برای شروع عملیات حساب `{account_name}`...')
        user_client = self._create_new_user_client(session_str)
        try:
            await user_client.connect()
            if await user_client.is_user_authorized():
                task = asyncio.create_task(self.run_group_creation_worker(user_id, account_name, user_client))
                self.active_workers[worker_key] = task
            else:
                self._delete_session_file(user_id, account_name)
                await event.reply(f'⚠️ نشست برای حساب `{account_name}` منقضی شده و حذف شد. لطفا دوباره آن را اضافه کنید.')
        except Exception as e:
            LOGGER.error(f"Failed to start process for {worker_key}", exc_info=e)
            await event.reply(f'❌ خطایی در اتصال به حساب `{account_name}` رخ داد.')

    async def _delete_account_handler(self, event: events.NewMessage.Event, account_name: str) -> None:
        """Deletes a specific account and cancels its running worker, if any."""
        user_id = event.sender_id
        worker_key = f"{user_id}:{account_name}"

        # PATCHED: Cancel the worker if it's running
        if worker_key in self.active_workers:
            self.active_workers[worker_key].cancel()
            # The task will remove itself from the dict in its `finally` block,
            # but we can remove it here to update the UI faster.
            del self.active_workers[worker_key]
            LOGGER.info(f"Worker cancelled for {worker_key} due to account deletion.")
        
        # Delete the session file
        if self._delete_session_file(user_id, account_name):
            await event.reply(f"✅ حساب `{account_name}` با موفقیت حذف شد و عملیات مرتبط متوقف گردید.")
        else:
            # This can happen if the file was already deleted but a worker was somehow active.
            await event.reply(f"✅ عملیات برای حساب `{account_name}` متوقف شد (نشست از قبل وجود نداشت).")
        
        await self._manage_accounts_handler(event) # Refresh the menu

    # --- Login Flow Handlers ---
    async def _handle_phone_input(self, event: events.NewMessage.Event) -> None:
        user_id = event.sender_id
        self.login_sessions[user_id]['phone'] = event.text.strip()
        user_client = self._create_new_user_client()
        self.login_sessions[user_id]['client'] = user_client
        try:
            await user_client.connect()
            sent_code = await user_client.send_code_request(self.login_sessions[user_id]['phone'])
            self.login_sessions[user_id]['phone_code_hash'] = sent_code.phone_code_hash
            self.login_sessions[user_id]['state'] = 'awaiting_code'
            await event.reply('💬 کد ورود ارسال شد. لطفا آن را اینجا ارسال کنید.')
        except Exception as e:
            LOGGER.error(f"Phone input error for {user_id}", exc_info=e)
            del self.login_sessions[user_id]
            await event.reply('❌ **خطا:** شماره تلفن نامعتبر است یا مشکلی در ارسال کد رخ داد.', buttons=MAIN_MENU_KEYBOARD)

    async def _handle_code_input(self, event: events.NewMessage.Event) -> None:
        user_id = event.sender_id
        user_client = self.login_sessions[user_id]['client']
        try:
            await user_client.sign_in(self.login_sessions[user_id]['phone'], code=event.text.strip(), phone_code_hash=self.login_sessions[user_id].get('phone_code_hash'))
            self.login_sessions[user_id]['state'] = 'awaiting_account_name'
            await event.reply('✅ ورود موفق! لطفاً یک نام مستعار برای این حساب وارد کنید (مثلا: `حساب اصلی` یا `شماره دوم`).')
        except errors.SessionPasswordNeededError:
            self.login_sessions[user_id]['state'] = 'awaiting_password'
            await event.reply('🔑 این حساب تایید دو مرحله‌ای دارد. لطفا رمز عبور را ارسال کنید.')
        except Exception as e:
            LOGGER.error(f"Code input error for {user_id}", exc_info=e)
            del self.login_sessions[user_id]
            await event.reply('❌ **خطا:** کد وارد شده نامعتبر است یا مشکلی رخ داده.', buttons=MAIN_MENU_KEYBOARD)

    async def _handle_password_input(self, event: events.NewMessage.Event) -> None:
        user_id = event.sender_id
        try:
            await self.login_sessions[user_id]['client'].sign_in(password=event.text.strip())
            self.login_sessions[user_id]['state'] = 'awaiting_account_name'
            await event.reply('✅ ورود موفق! لطفاً یک نام مستعار برای این حساب وارد کنید (مثلا: `حساب اصلی` یا `شماره دوم`).')
        except Exception as e:
            LOGGER.error(f"Password input error for {user_id}", exc_info=e)
            del self.login_sessions[user_id]
            await event.reply('❌ **خطا:** رمز عبور اشتباه است یا مشکلی رخ داده.', buttons=MAIN_MENU_KEYBOARD)

    async def _handle_account_name_input(self, event: events.NewMessage.Event) -> None:
        """Final step of login: gets the account nickname and saves the session."""
        user_id = event.sender_id
        account_name = event.text.strip()
        if not account_name:
            await event.reply("❌ نام مستعار نمی‌تواند خالی باشد. لطفا یک نام وارد کنید.")
            return
        
        existing_accounts = self._get_user_accounts(user_id)
        if account_name in existing_accounts:
            await event.reply(f"❌ شما قبلا حسابی با نام `{account_name}` اضافه کرده‌اید. لطفا یک نام دیگر انتخاب کنید.")
            return
            
        self.login_sessions[user_id]['account_name'] = account_name
        user_client = self.login_sessions[user_id]['client']
        await self.on_login_success(event, user_client)

    # --- Main Run Method ---
    def register_handlers(self) -> None:
        self.bot.add_event_handler(self._start_handler, events.NewMessage(pattern='/start'))
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
