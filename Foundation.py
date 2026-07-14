__version__ = (2, 5, 0)
# diff: Обновлены триггеры + блеклист, уведомления об обновлениях, кэш, убраны все языкы кроме EN/RU.
# meta developer: @mofkomodules
# Original author module: @HaloperidolPills 
# Name: Foundation
# requires: aiohttp
# scope: heroku_min 2.0.0
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_275.png
#metapic:https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_275.png
# meta fhsdesc: hentai, 18+, random, хентай, porn, fun, mofko, хуйня, порно, говно, nsfw, sfw
# meta tags: hentai, 18+, random, хентай, porn, fun, mofko, хуйня, порно, говно, nsfw, sfw

import random
import logging
import asyncio
import time
import aiohttp
import re
from collections import defaultdict, deque
from herokutl.errors import FloodWaitError
from herokutl.errors.rpcerrorlist import ChannelPrivateError, UserNotParticipantError
from herokutl.tl import functions
from herokutl.tl.types import Message
from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


@loader.tds
class Foundation(loader.Module):
    """Send random NSFW and SFW media from Foundation sources."""

    strings = {
        "name": "Foundation",
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Something went wrong, check logs",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> You need to join the channel first: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> No media found in channel",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> No videos found in channel",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> No media found in channel",
        "triggers_config": '<tg-emoji emoji-id="4904936030232117798">⚙️</tg-emoji> <b>Configuration of triggers for Foundation</b>\n\nChat: {} (ID: {})\n\nCurrent triggers:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}',
        "select_trigger": "Select trigger to configure:",
        "enter_trigger_word": "✍️ Enter trigger word (or 0 to disable):",
        "no_triggers": "No triggers configured",
        "fsfw_cmd_doc": "Send random SFW media from @sfwfond",
        "access_required_text": "To use this command, you must be in the channel and the channel chat!",
        "channel_button": "Channel",
        "chat_button": "Chat",
        "source_unavailable": "<b>Foundation source is temporarily unavailable.</b> Try again later.",
        "update_available": '<tg-emoji emoji-id="5361979468887893611">🆕</tg-emoji> <b>Foundation update</b>\n\n<code>{}</code> -> <code>{}</code>{}\n\n<b>Install:</b>\n<code>{}</code>',
        "update_diff": "\n\n<b>What's new:</b>\n<blockquote expandable>{}</blockquote>",
        "trigger_reply_required": "Reply to a user message.",
        "trigger_user_required": "This trigger blacklist only supports users.",
        "trigger_blacklist_added": "<b>{}</b> is blocked from trigger generation.",
        "trigger_blacklist_removed": "<b>{}</b> is removed from the trigger blacklist.",
        "trigger_empty": "Trigger cannot be empty.",
        "trigger_btn_fond": "Configure fond trigger",
        "trigger_btn_vfond": "Configure vfond trigger",
        "trigger_btn_fsfw": "Configure fsfw trigger",
        "trigger_btn_set": "Set trigger for .{}",
        "trigger_btn_delete": "Delete trigger",
        "trigger_btn_back": "Back",
        "trigger_btn_close": "Close",
        "cfg_triggers_enabled": "Enable trigger watcher.",
        "cfg_spam_protection": "Enable spam protection for commands and triggers.",
        "cfg_auto_delete_media": "Automatically delete sent NSFW media after the configured delay.",
        "cfg_auto_delete_delay": "Delay before auto-deleting NSFW media in seconds (0 disables it).",
        "cfg_trigger_blacklist": "Global trigger blacklist. Entries are stored as @username - user_id.",
    }

    strings_ru = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Чот не то, чекай логи",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Нужно вступить в канал, ВНИМАТЕЛЬНО ЧИТАЙ ПРИ ПОДАЧЕ ЗАЯВКИ: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено медиа",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено видео",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено медиа в канале",
        "triggers_config": '<tg-emoji emoji-id="4904936030232117798">⚙️</tg-emoji> <b>Настройка триггеров для Foundation</b>\n\nЧат: {} (ID: {})\n\nТекущие триггеры:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}',
        "select_trigger": "Выберите триггер для настройки:",
        "enter_trigger_word": "✍️ Введите слово-триггер (или 0 для отключения):",
        "no_triggers": "Триггеры не настроены",
        "_cls_doc": "Случайное NSFW медиа",
        "fsfw_cmd_doc": "Отправить рандомное SFW медиа с @sfwfond",
        "access_required_text": "Для использования команды необходимо состоять в канале и чате канала!",
        "channel_button": "Канал",
        "chat_button": "Чат",
        "source_unavailable": "<b>Источник Foundation временно недоступен.</b> Попробуйте позже.",
        "update_available": '<tg-emoji emoji-id="5361979468887893611">🆕</tg-emoji> <b>Обновление Foundation</b>\n\n<code>{}</code> -> <code>{}</code>{}\n\n<b>Установка:</b>\n<code>{}</code>',
        "update_diff": "\n\n<b>Что изменилось:</b>\n<blockquote expandable>{}</blockquote>",
        "trigger_reply_required": "Ответьте на сообщение пользователя.",
        "trigger_user_required": "Чёрный список триггеров поддерживает только пользователей.",
        "trigger_blacklist_added": "<b>{}</b> заблокирован для генерации по триггеру.",
        "trigger_blacklist_removed": "<b>{}</b> удалён из чёрного списка триггеров.",
        "trigger_empty": "Триггер не может быть пустым.",
        "trigger_btn_fond": "Настроить триггер fond",
        "trigger_btn_vfond": "Настроить триггер vfond",
        "trigger_btn_fsfw": "Настроить триггер fsfw",
        "trigger_btn_set": "Задать триггер для .{}",
        "trigger_btn_delete": "Удалить триггер",
        "trigger_btn_back": "Назад",
        "trigger_btn_close": "Закрыть",
        "cfg_triggers_enabled": "Включить watcher триггеров.",
        "cfg_spam_protection": "Включить защиту от спама для команд и триггеров.",
        "cfg_auto_delete_media": "Автоматически удалять отправленное NSFW медиа через заданное время.",
        "cfg_auto_delete_delay": "Задержка автоудаления NSFW медиа в секундах (0 отключает).",
        "cfg_trigger_blacklist": "Глобальный чёрный список триггеров. Формат: @ник - ID пользователя.",
    }

    def __init__(self):
        self._media_cache = {}
        self._video_cache = {}
        self._cache_time = {}
        self._recent_media_ids = {"any": [], "video": [], "sfw_any": []}
        self._recent_media_limit = 20
        self.entity = None
        self._last_entity_check = 0
        self.entity_check_interval = 300
        self.cache_ttl = 1200
        self.link_channel_username = "foundationlink"
        self.link_message_id = 4
        self.actual_foundation_link = None
        self.required_chat_link = "https://t.me/weirdcorp"
        self.required_chat_username = "weirdcorp"
        self._required_chat_entity = None
        self._required_chat_last_entity_check = 0
        self.update_source_url = "https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/Foundation.py"
        self.update_check_interval = 21600
        self.update_notice_repeat_interval = 5 * 24 * 60 * 60
        self._update_check_task = None
        self._update_notice_lock = asyncio.Lock()
        self.foundation_link_update_interval = 300
        self.foundation_link_retry_interval = 30
        self._last_foundation_link_update = 0
        self._foundation_link_lock = asyncio.Lock()
        self._nsfw_cache_lock = asyncio.Lock()
        self._membership_cache = {}
        self._membership_cache_ttl = 60
        self._auto_delete_tasks = set()
        
        self._sfw_channel_username = "sfwfond"
        self._sfw_channel_entity = None
        self._sfw_last_entity_check = 0
        self._sfw_media_cache = {}
        self._sfw_cache_time = {}
        self._sfw_cache_ttl = 600
        self._sfw_cache_lock = asyncio.Lock()

        self._spam_events = defaultdict(deque)
        self._chat_spam_events = defaultdict(deque)
        self._spam_blocks = {}
        self._chat_spam_blocks = {}
        self._spam_lock = asyncio.Lock()
        self._last_spam_cleanup = 0
        
        self.SPAM_LIMIT = 3
        self.SPAM_WINDOW = 3
        self.BLOCK_DURATION = 15
        self.GLOBAL_LIMIT = 10
        self.GLOBAL_WINDOW = 10

        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "triggers_enabled",
                True,
                lambda: self.strings("cfg_triggers_enabled"),
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "spam_protection",
                True,
                lambda: self.strings("cfg_spam_protection"),
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "auto_delete_media",
                False,
                lambda: self.strings("cfg_auto_delete_media"),
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "auto_delete_delay",
                30,
                lambda: self.strings("cfg_auto_delete_delay"),
                validator=loader.validators.Integer(minimum=0)
            ),
            loader.ConfigValue(
                "trigger_blacklist",
                [],
                lambda: self.strings("cfg_trigger_blacklist"),
                validator=loader.validators.Series(),
            )
        )

    async def client_ready(self):
        await self._migrate_legacy_storage()
        self.triggers = self.get("triggers", {})
        self.actual_foundation_link = self.get("actual_foundation_link", None)
        await self._update_foundation_link_on_demand()
        await self._load_entity()
        await self._load_required_chat_entity()
        await self._load_sfw_entity()
        if self._update_check_task and not self._update_check_task.done():
            self._update_check_task.cancel()
        self._update_check_task = asyncio.create_task(self._update_check_loop())

    async def on_unload(self):
        if self._update_check_task and not self._update_check_task.done():
            self._update_check_task.cancel()
            try:
                await self._update_check_task
            except asyncio.CancelledError:
                pass
        for task in tuple(self._auto_delete_tasks):
            task.cancel()
        self._auto_delete_tasks.clear()

    async def _migrate_legacy_storage(self):
        if self.get("storage_v2_migrated", False):
            return

        for key in ("triggers", "actual_foundation_link"):
            if self.get(key, None) is not None:
                continue
            value = self.db.get(__name__, key, None)
            if value is not None:
                self.set(key, value)

        legacy_notice = self.db.get(__name__, "last_update_notified_version", None)
        if legacy_notice and not self.get("update_notice", None):
            self.set(
                "update_notice",
                {"version": list(legacy_notice), "sent_at": 0},
            )
        self.set("storage_v2_migrated", True)

    def _format_version(self, version):
        if not isinstance(version, (tuple, list)):
            return str(version)
        return ".".join(map(str, version))

    def _parse_remote_version(self, module_source):
        match = re.search(r"__version__\s*=\s*\(([^)]+)\)", module_source)
        if not match:
            return None
        parts = [part.strip() for part in match.group(1).split(",") if part.strip()]
        try:
            version = tuple(int(part) for part in parts)
        except ValueError:
            return None
        return version if len(version) == 3 else None

    def _parse_remote_diff(self, module_source):
        match = re.search(
            r"#\s*diff:\s*(.*?)(?=\s+#\s*[A-Za-zА-Яа-я_ -]{1,40}:|$)",
            module_source,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        return re.sub(r"\s+", " ", match.group(1).strip())[:1200]

    @staticmethod
    def _is_remote_version_newer(remote_version):
        return remote_version > __version__

    async def _fetch_remote_module_info(self):
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                self.update_source_url,
                headers={"Cache-Control": "no-cache"},
                params={"t": int(time.time())},
            ) as response:
                if response.status != 200:
                    logger.warning(
                        "Could not check Foundation updates: HTTP %s", response.status
                    )
                    return None, ""
                module_source = await response.text()
        return self._parse_remote_version(module_source), self._parse_remote_diff(module_source)

    def _update_notice_is_due(self, remote_version):
        notice = self.get("update_notice", {})
        if not isinstance(notice, dict):
            return True
        saved_version = notice.get("version")
        if saved_version != list(remote_version):
            return True
        sent_at = notice.get("sent_at", 0)
        try:
            return time.time() - float(sent_at) >= self.update_notice_repeat_interval
        except (TypeError, ValueError):
            return True

    def _mark_update_notice_sent(self, remote_version):
        self.set(
            "update_notice",
            {"version": list(remote_version), "sent_at": int(time.time())},
        )

    async def _send_update_notice(self, text):
        try:
            await self.inline.bot.send_message(
                self.tg_id,
                text,
                disable_web_page_preview=True,
            )
            return True
        except Exception as e:
            logger.debug("Inline update notice failed: %s", e)

        try:
            await self.client.send_message(
                self.tg_id,
                text,
                link_preview=False,
            )
            return True
        except Exception as e:
            logger.debug("Saved Messages update notice fallback failed: %s", e)
            return False

    async def _check_module_update(self):
        try:
            async with self._update_notice_lock:
                remote_version, diff = await self._fetch_remote_module_info()
                if not remote_version:
                    return False
                if not self._is_remote_version_newer(remote_version):
                    if remote_version == __version__:
                        self.set("update_notice", {})
                    return False
                if not self._update_notice_is_due(remote_version):
                    return False

                install_command = f"{self.get_prefix()}dlm {self.update_source_url}"
                diff_text = (
                    self.strings("update_diff").format(utils.escape_html(diff))
                    if diff
                    else ""
                )
                text = self.strings("update_available").format(
                    self._format_version(__version__),
                    self._format_version(remote_version),
                    diff_text,
                    utils.escape_html(install_command),
                )
                if await self._send_update_notice(text):
                    self._mark_update_notice_sent(remote_version)
                    return True
                return False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Could not check Foundation updates: %s", e)
            return False

    async def _update_check_loop(self):
        while True:
            try:
                await self._check_module_update()
                await asyncio.sleep(self.update_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(e)

    async def _update_foundation_link_on_demand(self):
        current_time = time.time()
        interval = (
            self.foundation_link_update_interval
            if self.actual_foundation_link
            else self.foundation_link_retry_interval
        )
        if current_time - self._last_foundation_link_update < interval:
            return bool(self.actual_foundation_link)
        async with self._foundation_link_lock:
            current_time = time.time()
            interval = (
                self.foundation_link_update_interval
                if self.actual_foundation_link
                else self.foundation_link_retry_interval
            )
            if current_time - self._last_foundation_link_update < interval:
                return bool(self.actual_foundation_link)
            try:
                link_channel_entity = await self.client.get_entity(self.link_channel_username)
                message = await self.client.get_messages(link_channel_entity, ids=self.link_message_id)
                match = re.search(
                    r"(https?://t\.me/[^\s\]]+)",
                    getattr(message, "raw_text", "") or "",
                )
                if not match:
                    raise RuntimeError("Foundation link is missing in the source message")
                new_link = match.group(1).rstrip(".,)")
                if new_link != self.actual_foundation_link:
                    logger.info(
                        "Foundation link updated: %s -> %s",
                        self.actual_foundation_link,
                        new_link,
                    )
                    self.actual_foundation_link = new_link
                    self.set("actual_foundation_link", new_link)
                    self._last_entity_check = 0
                    await self._load_entity()
                self._last_foundation_link_update = current_time
                return True
            except Exception as e:
                logger.warning(
                    "Error updating Foundation link from channel: %s. Using cached link if available.",
                    e,
                )
                return bool(self.actual_foundation_link)
    
    def _prune_spam_events(self, events, current_time, window):
        while events and current_time - events[0] > window:
            events.popleft()

    def _is_spam_blocked(self, blocks, key, current_time):
        block_until = blocks.get(key)
        if not block_until:
            return False
        if current_time < block_until:
            return True
        del blocks[key]
        return False

    def _cleanup_spam_state(self, current_time):
        for events, window in (
            (self._spam_events, self.SPAM_WINDOW),
            (self._chat_spam_events, self.GLOBAL_WINDOW),
        ):
            for key, timestamps in tuple(events.items()):
                self._prune_spam_events(timestamps, current_time, window)
                if not timestamps:
                    del events[key]
        for blocks in (self._spam_blocks, self._chat_spam_blocks):
            for key, block_until in tuple(blocks.items()):
                if current_time >= block_until:
                    del blocks[key]

    def _spam_user_key(self, user_id, chat_id):
        if user_id is None:
            return f"unknown:{chat_id}"
        return f"{user_id}:{chat_id}"

    async def _check_spam(self, user_id, chat_id):
        if not self.config["spam_protection"]:
            return False
        
        current_time = time.time()
        user_key = self._spam_user_key(user_id, chat_id)
        chat_key = str(chat_id)
        
        async with self._spam_lock:
            if current_time - self._last_spam_cleanup >= 60:
                self._cleanup_spam_state(current_time)
                self._last_spam_cleanup = current_time
            if self._is_spam_blocked(self._chat_spam_blocks, chat_key, current_time):
                return True
            if self._is_spam_blocked(self._spam_blocks, user_key, current_time):
                return True
            
            user_events = self._spam_events[user_key]
            chat_events = self._chat_spam_events[chat_key]
            
            self._prune_spam_events(user_events, current_time, self.SPAM_WINDOW)
            self._prune_spam_events(chat_events, current_time, self.GLOBAL_WINDOW)
            
            if len(user_events) >= self.SPAM_LIMIT:
                self._spam_blocks[user_key] = current_time + self.BLOCK_DURATION
                user_events.clear()
                return True
            
            if len(chat_events) >= self.GLOBAL_LIMIT:
                self._chat_spam_blocks[chat_key] = current_time + self.BLOCK_DURATION
                chat_events.clear()
                return True
            
            user_events.append(current_time)
            chat_events.append(current_time)
            return False

    async def _load_entity(self):
        current_time = time.time()
        if (self.entity and 
            current_time - self._last_entity_check < self.entity_check_interval):
            return True
        if not self.actual_foundation_link:
            self.entity = None
            return False
        try:
            self.entity = await self.client.get_entity(self.actual_foundation_link)
            self._last_entity_check = current_time
            return True
        except Exception as e:
            logger.warning(f"Could not load foundation entity from {self.actual_foundation_link}: {e}")
            self.entity = None
            return False

    async def _load_sfw_entity(self):
        current_time = time.time()
        if (self._sfw_channel_entity and 
            current_time - self._sfw_last_entity_check < self.entity_check_interval):
            return True
        try:
            self._sfw_channel_entity = await self.client.get_entity(self._sfw_channel_username)
            self._sfw_last_entity_check = current_time
            return True
        except Exception as e:
            logger.warning(f"Could not load SFW channel entity @{self._sfw_channel_username}: {e}")
            self._sfw_channel_entity = None
            return False

    async def _load_required_chat_entity(self):
        current_time = time.time()
        if (
            self._required_chat_entity and
            current_time - self._required_chat_last_entity_check < self.entity_check_interval
        ):
            return True
        try:
            self._required_chat_entity = await self.client.get_entity(self.required_chat_username)
            self._required_chat_last_entity_check = current_time
            return True
        except Exception as e:
            logger.warning(f"Could not load required chat entity @{self.required_chat_username}: {e}")
            self._required_chat_entity = None
            return False

    async def _has_channel_access(self, channel_entity, participant):
        if not channel_entity or participant is None:
            return False
        channel_id = getattr(channel_entity, "id", channel_entity)
        cache_key = f"{channel_id}:{participant}"
        cached = self._membership_cache.get(cache_key)
        current_time = time.time()
        if cached and current_time - cached[1] < self._membership_cache_ttl:
            return cached[0]
        try:
            await self.client(
                functions.channels.GetParticipantRequest(
                    channel=channel_entity,
                    participant=participant,
                )
            )
            result = True
        except (UserNotParticipantError, ChannelPrivateError, ValueError):
            result = False
        except Exception as e:
            logger.warning(f"Could not verify membership for participant {participant}: {e}")
            result = False
        self._membership_cache[cache_key] = (result, current_time)
        return result

    async def _has_required_chat_access(self, participant):
        if not await self._load_required_chat_entity():
            return False
        return await self._has_channel_access(self._required_chat_entity, participant)

    async def _show_access_required(self, message: Message):
        if not self.actual_foundation_link:
            await utils.answer(message, self.strings("source_unavailable"))
            return
        markup = [
            [
                {
                    "text": self.strings("channel_button"),
                    "url": self.actual_foundation_link,
                    "style": "primary",
                },
                {
                    "text": self.strings("chat_button"),
                    "url": self.required_chat_link,
                    "style": "primary",
                },
            ]
        ]
        try:
            await self.inline.form(
                message=message,
                text=self.strings("access_required_text"),
                reply_markup=markup,
            )
        except Exception as e:
            logger.exception(e)
            await utils.answer(
                message,
                "{}\n{}\n{}".format(
                    self.strings("access_required_text"),
                    utils.escape_html(self.actual_foundation_link),
                    utils.escape_html(self.required_chat_link),
                ),
            )

    async def _ensure_foundation_access(self, message: Message):
        participant = "me"
        if not await self._load_entity():
            await self._show_access_required(message)
            return False
        if not await self._has_channel_access(self.entity, participant):
            await self._show_access_required(message)
            return False
        if not await self._has_required_chat_access(participant):
            await self._show_access_required(message)
            return False
        return True

    async def _get_cached_media(self, media_type="any"):
        current_time = time.time()
        cache_key = "messages"
        if (
            cache_key in self._cache_time and
            current_time - self._cache_time[cache_key] < self.cache_ttl
        ):
            if media_type == "any":
                if "any" in self._media_cache:
                    return self._media_cache["any"]
            elif "video" in self._video_cache:
                return self._video_cache["video"]
        async with self._nsfw_cache_lock:
            current_time = time.time()
            if (
                cache_key in self._cache_time and
                current_time - self._cache_time[cache_key] < self.cache_ttl
            ):
                if media_type == "any":
                    if "any" in self._media_cache:
                        return self._media_cache["any"]
                elif "video" in self._video_cache:
                    return self._video_cache["video"]
            if not await self._load_entity():
                return None
            while True:
                try:
                    messages = await self.client.get_messages(self.entity, limit=1500)
                    break
                except FloodWaitError as e:
                    logger.warning(f"FloodWait for {e.seconds} seconds")
                    await asyncio.sleep(e.seconds)
                except (UserNotParticipantError, ChannelPrivateError) as e:
                    logger.warning(f"Userbot is not participant or channel is private: {e}")
                    return None
                except ValueError as e:
                    if "Could not find the entity" in str(e):
                        return None
                    raise e
            if not messages:
                self._media_cache["any"] = []
                self._video_cache["video"] = []
                self._cache_time[cache_key] = time.time()
                return []
            media_messages = [msg for msg in messages if msg.media]
            video_messages = []
            for msg in media_messages:
                if hasattr(msg.media, 'document'):
                    attr = getattr(msg.media.document, 'mime_type', '')
                    if 'video' in attr:
                        video_messages.append(msg)
            self._media_cache["any"] = media_messages
            self._video_cache["video"] = video_messages
            self._cache_time[cache_key] = time.time()
            return self._media_cache["any"] if media_type == "any" else self._video_cache["video"]
    
    async def _get_sfw_cached_media(self):
        current_time = time.time()
        cache_key = "sfw_any"
        if (cache_key in self._sfw_cache_time and
            current_time - self._sfw_cache_time[cache_key] < self._sfw_cache_ttl):
            return self._sfw_media_cache[cache_key]
        async with self._sfw_cache_lock:
            current_time = time.time()
            if (cache_key in self._sfw_cache_time and
                current_time - self._sfw_cache_time[cache_key] < self._sfw_cache_ttl):
                return self._sfw_media_cache[cache_key]
            if not await self._load_sfw_entity():
                return None
            while True:
                try:
                    messages = await self.client.get_messages(self._sfw_channel_entity, limit=1000)
                    break
                except FloodWaitError as e:
                    logger.warning(f"FloodWait for {e.seconds} seconds on SFW channel")
                    await asyncio.sleep(e.seconds)
                except (UserNotParticipantError, ChannelPrivateError) as e:
                    logger.warning(f"Userbot is not participant or SFW channel is private: {e}")
                    return None
                except ValueError as e:
                    if "Could not find the entity" in str(e):
                        return None
                    raise e
            if not messages:
                self._sfw_media_cache[cache_key] = []
                self._sfw_cache_time[cache_key] = time.time()
                return []
            sfw_media_messages = [msg for msg in messages if msg.media]
            self._sfw_media_cache[cache_key] = sfw_media_messages
            self._sfw_cache_time[cache_key] = time.time()
            return sfw_media_messages

    async def _schedule_delete(self, message_to_delete: Message, delay: int):
        await asyncio.sleep(delay)
        try:
            await message_to_delete.delete()
        except Exception as e:
            logger.warning(f"Failed to auto-delete message {message_to_delete.id} in chat {message_to_delete.chat_id}: {e}")

    def _schedule_auto_delete(self, message_to_delete: Message, delay: int):
        task = asyncio.create_task(self._schedule_delete(message_to_delete, delay))
        self._auto_delete_tasks.add(task)
        task.add_done_callback(self._auto_delete_tasks.discard)

    def _pick_random_media(self, media_list, pool_key: str):
        recent_ids = self._recent_media_ids.setdefault(pool_key, [])
        available_media = [
            item for item in media_list
            if getattr(item, "id", None) not in recent_ids
        ]
        selected = random.choice(available_media or media_list)
        selected_id = getattr(selected, "id", None)
        if selected_id is not None:
            recent_ids.append(selected_id)
            if len(recent_ids) > self._recent_media_limit:
                del recent_ids[:-self._recent_media_limit]
        return selected

    async def _send_media(self, message: Message, media_type: str = "any", delete_command: bool = False, is_sfw: bool = False):
        try:
            if is_sfw:
                if not await self._load_sfw_entity():
                    return await utils.answer(message, self.strings("error"))
                media_list = await self._get_sfw_cached_media()
                if media_list is None:
                    return await utils.answer(message, self.strings("error"))
                if not media_list:
                    await utils.answer(message, self.strings("fsfw_no_media"))
                    return
            else:
                if not await self._load_entity():
                    return await self._show_access_required(message)
                media_list = await self._get_cached_media(media_type)
                if media_list is None:
                    return await self._show_access_required(message)
                if not media_list:
                    if media_type == "any":
                        await utils.answer(message, self.strings("no_media"))
                    else:
                        await utils.answer(message, self.strings("no_videos"))
                    return
            
            pool_key = "sfw_any" if is_sfw else media_type
            random_message = self._pick_random_media(media_list, pool_key)
            
            sent_message = await self.client.send_message(
                message.peer_id,
                message=random_message,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
            
            if self.config["auto_delete_media"] and self.config["auto_delete_delay"] > 0 and not is_sfw:
                self._schedule_auto_delete(sent_message, self.config["auto_delete_delay"])

            if delete_command:
                await asyncio.sleep(0.1)
                try:
                    await message.delete()
                except Exception:
                    pass
        except Exception as e:
            logger.exception(e)
            await utils.answer(message, self.strings("error"))

    @loader.command(ru_doc="Отправить NSFW медиа с Фонда")
    async def fond(self, message: Message):
        """Send NSFW media from Foundation"""
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._update_foundation_link_on_demand()
        if not await self._ensure_foundation_access(message):
            return
        await self._send_media(message, "any", delete_command=True)

    @loader.command(ru_doc="Отправить NSFW видео с Фонда")
    async def vfond(self, message: Message):
        """Send NSFW video from Foundation"""
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._update_foundation_link_on_demand()
        if not await self._ensure_foundation_access(message):
            return
        await self._send_media(message, "video", delete_command=True)

    @loader.command(ru_doc="Отправить рандомное SFW медиа с @sfwfond")
    async def fsfw(self, message: Message):
        """Send random SFW media from @sfwfond"""
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._send_media(message, is_sfw=True, delete_command=True)

    @staticmethod
    def _trigger_sender_user_id(message):
        sender_id = getattr(message, "sender_id", None)
        from_id = getattr(message, "from_id", None)
        if not sender_id or getattr(message, "post", False):
            return None
        if from_id is not None and "peeruser" not in type(from_id).__name__.lower():
            return None
        try:
            return int(sender_id)
        except (TypeError, ValueError):
            return None

    def _trigger_blacklist_entries(self):
        entries = self.config["trigger_blacklist"]
        return list(entries) if isinstance(entries, (list, tuple)) else []

    def _trigger_blacklist_ids(self):
        result = set()
        for entry in self._trigger_blacklist_entries():
            match = re.search(r"(-?\d+)\s*$", str(entry))
            if match:
                result.add(int(match.group(1)))
        return result

    def _trigger_main_markup(self, chat_id: int):
        return [
            [
                {
                    "text": self.strings("trigger_btn_fond"),
                    "callback": self._configure_trigger,
                    "args": (chat_id, "fond"),
                    "style": "primary",
                    "emoji_id": "4904936030232117798",
                }
            ],
            [
                {
                    "text": self.strings("trigger_btn_vfond"),
                    "callback": self._configure_trigger,
                    "args": (chat_id, "vfond"),
                    "style": "primary",
                    "emoji_id": "5258391252914676042",
                }
            ],
            [
                {
                    "text": self.strings("trigger_btn_fsfw"),
                    "callback": self._configure_trigger,
                    "args": (chat_id, "fsfw"),
                    "style": "primary",
                    "emoji_id": "5258254475386167466",
                }
            ],
            [
                {
                    "text": self.strings("trigger_btn_close"),
                    "action": "close",
                    "style": "danger",
                    "emoji_id": "5121063440311386962",
                }
            ],
        ]

    @loader.command(ru_doc="Настроить триггеры для команд fond/vfond/fsfw")
    async def ftriggers(self, message: Message):
        """Configure triggers for fond/vfond/fsfw commands"""
        chat_id = utils.get_chat_id(message)
        chat = await message.get_chat()
        chat_title = utils.escape_html(getattr(chat, "title", "Private Chat"))
        chat_triggers = self.triggers.get(str(chat_id), {})
        fond_trigger = utils.escape_html(str(chat_triggers.get("fond", self.strings("no_triggers"))))
        vfond_trigger = utils.escape_html(str(chat_triggers.get("vfond", self.strings("no_triggers"))))
        fsfw_trigger = utils.escape_html(str(chat_triggers.get("fsfw", self.strings("no_triggers"))))
        await self.inline.form(
            message=message,
            text=self.strings("triggers_config").format(
                chat_title,
                chat_id,
                fond_trigger,
                vfond_trigger,
                fsfw_trigger
            ),
            reply_markup=self._trigger_main_markup(chat_id),
        )

    async def _configure_trigger(self, call: InlineCall, chat_id: int, command: str):
        await utils.answer(
            call,
            self.strings("select_trigger"),
            reply_markup=[
                [
                    {
                        "text": self.strings("trigger_btn_set").format(command),
                        "input": self.strings("enter_trigger_word"),
                        "handler": self._save_trigger,
                        "args": (chat_id, command),
                        "style": "primary",
                        "emoji_id": "5879841310902324730"
                    }
                ],
                [
                    {
                        "text": self.strings("trigger_btn_delete"),
                        "callback": self._delete_trigger,
                        "args": (chat_id, command),
                        "style": "danger",
                        "emoji_id": "5121063440311386962"
                    }
                ],
                [
                    {
                        "text": self.strings("trigger_btn_back"),
                        "callback": self._show_main_menu,
                        "args": (chat_id,),
                        "style": "danger",
                        "emoji_id": "5985346521103604145"
                    }
                ]
            ]
        )

    async def _save_trigger(self, call: InlineCall, query: str, chat_id: int, command: str):
        query = query.strip().lower()
        if not query:
            try:
                await call.answer(self.strings("trigger_empty"), show_alert=True)
            except Exception:
                pass
            return
        if query == "0":
            chat_triggers = self.triggers.get(str(chat_id), {})
            chat_triggers.pop(command, None)
            if chat_triggers:
                self.triggers[str(chat_id)] = chat_triggers
            else:
                self.triggers.pop(str(chat_id), None)
        else:
            if str(chat_id) not in self.triggers:
                self.triggers[str(chat_id)] = {}
            self.triggers[str(chat_id)][command] = query
        self.set("triggers", self.triggers)
        await self._show_main_menu(call, chat_id)

    async def _delete_trigger(self, call: InlineCall, chat_id: int, command: str):
        chat_key = str(chat_id)
        chat_triggers = self.triggers.get(chat_key, {})
        chat_triggers.pop(command, None)
        if chat_triggers:
            self.triggers[chat_key] = chat_triggers
        else:
            self.triggers.pop(chat_key, None)
        self.set("triggers", self.triggers)
        await self._show_main_menu(call, chat_id)

    async def _show_main_menu(self, call: InlineCall, chat_id: int):
        try:
            chat = await self.client.get_entity(chat_id)
            chat_title = utils.escape_html(getattr(chat, "title", "Private Chat"))
        except Exception as e:
            logger.warning(f"Could not load chat title for {chat_id}: {e}")
            chat_title = utils.escape_html(f"Chat {chat_id}")
        chat_triggers = self.triggers.get(str(chat_id), {})
        fond_trigger = utils.escape_html(str(chat_triggers.get("fond", self.strings("no_triggers"))))
        vfond_trigger = utils.escape_html(str(chat_triggers.get("vfond", self.strings("no_triggers"))))
        fsfw_trigger = utils.escape_html(str(chat_triggers.get("fsfw", self.strings("no_triggers"))))
        await utils.answer(
            call,
            self.strings("triggers_config").format(
                chat_title,
                chat_id,
                fond_trigger,
                vfond_trigger,
                fsfw_trigger
            ),
            reply_markup=self._trigger_main_markup(chat_id),
        )

    @loader.command(ru_doc="Добавить/удалить в чёрный список триггеров")
    async def fbl(self, message: Message):
        """Toggle a replied user's global trigger blacklist status."""
        reply = await message.get_reply_message()
        if not reply:
            return await utils.answer(message, self.strings("trigger_reply_required"))

        user_id = self._trigger_sender_user_id(reply)
        if user_id is None:
            return await utils.answer(message, self.strings("trigger_user_required"))

        entries = self._trigger_blacklist_entries()
        remaining_entries = [
            entry
            for entry in entries
            if not re.search(rf"{re.escape(str(user_id))}\s*$", str(entry))
        ]
        user = None
        try:
            user = await self.client.get_entity(user_id)
            username = getattr(user, "username", None)
        except Exception:
            username = None
        if user is not None and "user" not in type(user).__name__.lower():
            return await utils.answer(message, self.strings("trigger_user_required"))
        label = f"@{username}" if username else str(user_id)

        if len(remaining_entries) != len(entries):
            self.config["trigger_blacklist"] = remaining_entries
            return await utils.answer(
                message,
                self.strings("trigger_blacklist_removed").format(
                    utils.escape_html(label)
                ),
            )

        entries.append(f"{label} - {user_id}")
        self.config["trigger_blacklist"] = entries
        await utils.answer(
            message,
            self.strings("trigger_blacklist_added").format(utils.escape_html(label)),
        )

    @loader.watcher()
    async def watcher(self, message: Message):
        try:
            if not self.config["triggers_enabled"]:
                return
            text = (getattr(message, "raw_text", None) or message.text or "").strip().lower()
            if not text:
                return
            chat_id = utils.get_chat_id(message)
            chat_triggers = self.triggers.get(str(chat_id), {})
            if not chat_triggers:
                return
            sender_id = self._trigger_sender_user_id(message)
            if sender_id is not None and sender_id in self._trigger_blacklist_ids():
                return
            for command, trigger in chat_triggers.items():
                normalized_trigger = (trigger or "").strip().lower()
                if text != normalized_trigger:
                    continue
                if await self._check_spam(message.sender_id, chat_id):
                    return
                if command == "fond":
                    await self._update_foundation_link_on_demand()
                    if not await self._ensure_foundation_access(message):
                        return
                    await self._send_media(message, "any", delete_command=True)
                elif command == "vfond":
                    await self._update_foundation_link_on_demand()
                    if not await self._ensure_foundation_access(message):
                        return
                    await self._send_media(message, "video", delete_command=True)
                elif command == "fsfw":
                    await self._send_media(message, is_sfw=True, delete_command=True)
                break
        except Exception as e:
            logger.exception(e)
