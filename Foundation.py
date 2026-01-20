__version__ = (2, 0, 1)
# meta developer: @mofkomodules
# name: Foundation
# description: best NSFW random module
# meta fhsdesc: hentai, 18+, random, хентай, porn, fun

import random
import logging
import asyncio
import time
from collections import defaultdict
from herokutl.types import Message
from .. import loader, utils
from telethon.errors import FloodWaitError
from ..inline.types import InlineCall
from cachetools import TTLCache

logger = logging.getLogger(__name__)

FOUNDATION_LINK = "https://t.me/+ZfmKdDrEMCA1NWEy"

@loader.tds
class Foundation(loader.Module):
    strings = {
        "name": "Foundation",
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Something went wrong, check logs",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> You need to join the channel first: https://t.me/+ZfmKdDrEMCA1NWEy",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> No media found in channel",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> No videos found in channel",
        "triggers_config": "⚙️ <b>Configuration of triggers for Foundation</b>\n\nChat: {} (ID: {})\n\nCurrent triggers:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}",
        "select_trigger": "Select trigger to configure:",
        "enter_trigger_word": "✍️ Enter trigger word (or 'off' to disable):",
        "trigger_updated": "✅ Trigger updated!\n\n{} will now trigger .{} in chat {}",
        "trigger_disabled": "✅ Trigger disabled for .{} in chat {}",
        "no_triggers": "No triggers configured",
    }

    strings_ru = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Чот не то, чекай логи",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Нужно вступить в канал, ВНИМАТЕЛЬНО ЧИТАЙ ПРИ ПОДАЧЕ ЗАЯВКИ: https://t.me/+ZfmKdDrEMCA1NWEy",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено медиа",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено видео",
        "triggers_config": "⚙️ <b>Настройка триггеров для Foundation</b>\n\nЧат: {} (ID: {})\n\nТекущие триггеры:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}",
        "select_trigger": "Выберите триггер для настройки:",
        "enter_trigger_word": "✍️ Введите слово-триггер (или 'off' для отключения):",
        "trigger_updated": "✅ Триггер обновлен!\n\n{} теперь будет вызывать .{} в чате {}",
        "trigger_disabled": "✅ Триггер отключен для .{} в чате {}",
        "no_triggers": "Триггеры не настроены",
        "_cls_doc": "Случайное NSFW медиа",
    }

    def __init__(self):
        self._media_cache = {}
        self._video_cache = {}
        self._cache_time = {}
        self.entity = None
        self._last_entity_check = 0
        self.entity_check_interval = 300
        self.cache_ttl = 1200
        
        self._spam_data = {
            'triggers': defaultdict(list),
            'blocked': {},
            'global_blocked': False,
            'global_block_time': 0
        }
        
        self._block_cache = TTLCache(maxsize=1000, ttl=15)
        
        self.SPAM_LIMIT = 3
        self.SPAM_WINDOW = 3
        self.BLOCK_DURATION = 15
        self.GLOBAL_LIMIT = 10
        self.GLOBAL_WINDOW = 10

        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "triggers_enabled",
                True,
                lambda: "Enable trigger watcher",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "spam_protection",
                True,
                lambda: "Enable spam protection for triggers",
                validator=loader.validators.Boolean()
            )
        )

    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        self.triggers = self._db.get(__name__, "triggers", {})
        self._load_spam_data()
        await self._load_entity()
    
    def _load_spam_data(self):
        saved = self._db.get(__name__, "spam_protection", {})
        if saved:
            self._spam_data['triggers'] = defaultdict(list, saved.get('triggers', {}))
            self._spam_data['blocked'] = saved.get('blocked', {})
            self._spam_data['global_blocked'] = saved.get('global_blocked', False)
            self._spam_data['global_block_time'] = saved.get('global_block_time', 0)
    
    def _save_spam_data(self):
        triggers_dict = dict(self._spam_data['triggers'])
        data_to_save = {
            'triggers': triggers_dict,
            'blocked': self._spam_data['blocked'],
            'global_blocked': self._spam_data['global_blocked'],
            'global_block_time': self._spam_data['global_block_time']
        }
        self._db.set(__name__, "spam_protection", data_to_save)

    async def _load_entity(self):
        current_time = time.time()
        if (self.entity and 
            current_time - self._last_entity_check < self.entity_check_interval):
            return True
        try:
            self.entity = await self.client.get_entity(FOUNDATION_LINK)
            self._last_entity_check = current_time
            return True
        except Exception as e:
            logger.warning(f"Could not load foundation entity: {e}")
            self.entity = None
            return False

    async def _get_cached_media(self, media_type="any"):
        current_time = time.time()
        cache_key = media_type
        if (cache_key in self._cache_time and 
            current_time - self._cache_time[cache_key] < self.cache_ttl):
            if cache_key == "any" and cache_key in self._media_cache:
                return self._media_cache[cache_key]
            elif cache_key == "video" and cache_key in self._video_cache:
                return self._video_cache[cache_key]
        if not await self._load_entity():
            return None
        try:
            messages = await self.client.get_messages(self.entity, limit=2500)
        except FloodWaitError as e:
            logger.warning(f"FloodWait for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return await self._get_cached_media(media_type)
        except ValueError as e:
            if "Could not find the entity" in str(e):
                return None
            raise e
        if not messages:
            return []
        if media_type == "any":
            media_messages = [msg for msg in messages if msg.media]
            self._media_cache["any"] = media_messages
        else:
            video_messages = []
            for msg in messages:
                if msg.media and hasattr(msg.media, 'document'):
                    attr = getattr(msg.media.document, 'mime_type', '')
                    if 'video' in attr:
                        video_messages.append(msg)
            self._video_cache["video"] = video_messages
        self._cache_time[cache_key] = current_time
        return self._media_cache.get("any") if media_type == "any" else self._video_cache.get("video")
    
    def _check_global_spam(self):
        if not self.config["spam_protection"]:
            return False
        
        current_time = time.time()
        
        if self._spam_data['global_blocked']:
            if current_time - self._spam_data['global_block_time'] < self.BLOCK_DURATION:
                return True
            else:
                self._spam_data['global_blocked'] = False
                self._save_spam_data()
                return False
        
        recent_triggers = 0
        ten_seconds_ago = current_time - self.GLOBAL_WINDOW
        
        for user_data in self._spam_data['triggers'].values():
            recent_in_user = [t for t in user_data if t > ten_seconds_ago]
            recent_triggers += len(recent_in_user)
        
        if recent_triggers >= self.GLOBAL_LIMIT:
            self._spam_data['global_blocked'] = True
            self._spam_data['global_block_time'] = current_time
            self._save_spam_data()
            return True
        
        return False
    
    def _check_user_spam(self, user_id, chat_id):
        if not self.config["spam_protection"]:
            return False
        
        current_time = time.time()
        key = f"{user_id}:{chat_id}"
        
        if key in self._block_cache:
            return True
        
        if key in self._spam_data['blocked']:
            block_until = self._spam_data['blocked'][key]
            if current_time < block_until:
                self._block_cache[key] = True
                return True
            else:
                del self._spam_data['blocked'][key]
        
        timestamps = self._spam_data['triggers'][key]
        
        three_seconds_ago = current_time - self.SPAM_WINDOW
        recent_timestamps = [ts for ts in timestamps if ts > three_seconds_ago]
        
        if len(recent_timestamps) >= self.SPAM_LIMIT:
            block_until = current_time + self.BLOCK_DURATION
            self._spam_data['blocked'][key] = block_until
            self._block_cache[key] = True
            self._spam_data['triggers'][key] = []
            self._save_spam_data()
            return True
        
        recent_timestamps.append(current_time)
        self._spam_data['triggers'][key] = recent_timestamps[-20:]
        
        self._save_spam_data()
        return False

    async def _check_spam(self, user_id, chat_id):
        if self._check_global_spam():
            return True
        
        if self._check_user_spam(user_id, chat_id):
            return True
        
        return False

    async def _send_media(self, message: Message, media_type: str = "any", delete_command: bool = False):
        try:
            if not await self._load_entity():
                return await utils.answer(message, self.strings["not_joined"])
            media_list = await self._get_cached_media(media_type)
            if media_list is None:
                await utils.answer(message, self.strings["not_joined"])
                return
            if not media_list:
                if media_type == "any":
                    await utils.answer(message, self.strings["no_media"])
                else:
                    await utils.answer(message, self.strings["no_videos"])
                return
            random_message = random.choice(media_list)
            await self.client.send_message(
                message.peer_id,
                message=random_message,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
            if delete_command:
                await asyncio.sleep(0.1)
                try:
                    await message.delete()
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Foundation error: {e}")
            await utils.answer(message, self.strings["error"])

    @loader.command(
        en_doc="Send NSFW media from Foundation",
        ru_doc="Отправить NSFW медиа с Фонда",
    )
    async def fond(self, message: Message):
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._send_media(message, "any", delete_command=True)

    @loader.command(
        en_doc="Send NSFW video from Foundation",
        ru_doc="Отправить NSFW видео с Фонда",
    )
    async def vfond(self, message: Message):
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._send_media(message, "video", delete_command=True)

    @loader.command(
        en_doc="Configure triggers for fond/vfond commands",
        ru_doc="Настроить триггеры для команд fond/vfond",
    )
    async def ftriggers(self, message: Message):
        chat_id = utils.get_chat_id(message)
        chat = await message.get_chat()
        chat_title = getattr(chat, "title", "Private Chat")
        chat_triggers = self.triggers.get(str(chat_id), {})
        fond_trigger = chat_triggers.get("fond", self.strings("no_triggers"))
        vfond_trigger = chat_triggers.get("vfond", self.strings("no_triggers"))
        await self.inline.form(
            message=message,
            text=self.strings("triggers_config").format(
                chat_title,
                chat_id,
                fond_trigger,
                vfond_trigger
            ),
            reply_markup=[
                [
                    {
                        "text": "⚙️ Configure fond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "fond")
                    }
                ],
                [
                    {
                        "text": "⚙️ Configure vfond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "vfond")
                    }
                ],
                [
                    {
                        "text": "❌ Close",
                        "action": "close"
                    }
                ]
            ]
        )

    async def _configure_trigger(self, call: InlineCall, chat_id: int, command: str):
        await call.edit(
            self.strings("select_trigger"),
            reply_markup=[
                [
                    {
                        "text": f"✍️ Set trigger for .{command}",
                        "input": self.strings("enter_trigger_word"),
                        "handler": self._save_trigger,
                        "args": (chat_id, command, call)
                    }
                ],
                [
                    {
                        "text": "🔙 Back",
                        "callback": self._show_main_menu,
                        "args": (call, chat_id)
                    }
                ]
            ]
        )

    async def _save_trigger(self, call: InlineCall, query: str, chat_id: int, command: str, original_call: InlineCall):
        query = query.strip().lower()
        if str(chat_id) not in self.triggers:
            self.triggers[str(chat_id)] = {}
        if query == "off":
            if command in self.triggers[str(chat_id)]:
                del self.triggers[str(chat_id)][command]
                if not self.triggers[str(chat_id)]:
                    del self.triggers[str(chat_id)]
        else:
            self.triggers[str(chat_id)][command] = query
        self._db.set(__name__, "triggers", self.triggers)
        try:
            chat = await self.client.get_entity(chat_id)
            chat_title = getattr(chat, "title", "Private Chat")
        except:
            chat_title = f"Chat {chat_id}"
        if query == "off":
            await original_call.answer(
                self.strings("trigger_disabled").format(command, chat_title),
                show_alert=True
            )
        else:
            await original_call.answer(
                self.strings("trigger_updated").format(query, command, chat_title),
                show_alert=True
            )
        await self._show_main_menu(original_call, chat_id)

    async def _show_main_menu(self, call: InlineCall, chat_id: int):
        try:
            chat = await self.client.get_entity(chat_id)
            chat_title = getattr(chat, "title", "Private Chat")
        except:
            chat_title = f"Chat {chat_id}"
        chat_triggers = self.triggers.get(str(chat_id), {})
        fond_trigger = chat_triggers.get("fond", self.strings("no_triggers"))
        vfond_trigger = chat_triggers.get("vfond", self.strings("no_triggers"))
        await call.edit(
            self.strings("triggers_config").format(
                chat_title,
                chat_id,
                fond_trigger,
                vfond_trigger
            ),
            reply_markup=[
                [
                    {
                        "text": "⚙️ Configure fond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "fond")
                    }
                ],
                [
                    {
                        "text": "⚙️ Configure vfond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "vfond")
                    }
                ],
                [
                    {
                        "text": "❌ Close",
                        "action": "close"
                    }
                ]
            ]
        )

    @loader.watcher()
    async def watcher(self, message: Message):
        if not self.config["triggers_enabled"]:
            return
        if not message.text:
            return
        chat_id = utils.get_chat_id(message)
        text = message.text.lower().strip()
        chat_triggers = self.triggers.get(str(chat_id), {})
        
        for command, trigger in chat_triggers.items():
            if text == trigger:
                if await self._check_spam(message.sender_id, chat_id):
                    return
                await self._send_media(message, "video" if command == "vfond" else "any", delete_command=True)
                break
