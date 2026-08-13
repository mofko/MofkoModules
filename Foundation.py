__version__ = (2, 7, 2)
# diff: Добавлен резервный канал для тех у кого перестал открываться основной канал.
# meta developer: @mofkomodules
# Original author module: @HaloperidolPills 
# Name: Foundation
# requires: aiohttp
# scope: heroku_min 2.1.0
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_275.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_275.png
# meta fhsdesc: hentai, 18+, random, porn, fun, mofko, хуйня, говно, nsfw, sfw
# meta tags: hentai, 18+, random, porn, fun, mofko, хуйня, говно, nsfw, sfw

import random
import logging
import asyncio
import time
import aiohttp
import re
from collections import defaultdict, deque
from herokutl.errors import FloodWaitError
from herokutl.errors.rpcerrorlist import ChannelPrivateError, UserNotParticipantError
from herokutl.tl.types import Message
from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


@loader.tds
class Foundation(loader.Module):
    """Send random NSFW and SFW media from Foundation sources."""

    SOURCE_MAIN = "main"
    SOURCE_RESERVE = "reserve"

    strings = {
        "name": "Foundation",
        "_cls_doc": "Random NSFW and SFW media",
        "error": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> Something went wrong, check logs",
        "not_joined": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> You need to join the channel first: {link}",
        "no_media": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> No media found in channel",
        "no_videos": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> No videos found in channel",
        "fsfw_no_media": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> No media found in channel",
        "triggers_config": '<tg-emoji emoji-id="4904936030232117798">⚙️</tg-emoji> <b>Configuration of triggers for Foundation</b>\n\nChat: {} (ID: {})\n\nCurrent triggers:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}',
        "select_trigger": "Select trigger to configure:",
        "enter_trigger_word": "✍️ Enter trigger word (or 0 to disable):",
        "no_triggers": "No triggers configured",
        "fsfw_cmd_doc": "Send random SFW media from @sfwfond",
        "access_main_text": "To use the module, you need to join the main channel.\n\nThe reserve channel is optional and is used as a backup source.",
        "access_reserve_text": "The reserve source is selected. To receive media, you need to join the reserve channel.",
        "main_channel_button": "Main channel",
        "reserve_channel_button": "Reserve channel",
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
        "cfg_source_channel": "Where to get media for Fond commands.",
        "source_main_option": "Main",
        "source_reserve_option": "Reserve",
        "private_chat": "Private chat",
        "chat_fallback": "Chat {}",
    }

    strings_ru = {
        "name": "Foundation",
        "error": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> Чот не то, чекай логи",
        "not_joined": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> Нужно вступить в канал, ВНИМАТЕЛЬНО ЧИТАЙ ПРИ ПОДАЧЕ ЗАЯВКИ: {link}",
        "no_media": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> Не найдено медиа",
        "no_videos": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> Не найдено видео",
        "fsfw_no_media": "<tg-emoji emoji-id=6012681561286122335>🤤</tg-emoji> Не найдено медиа в канале",
        "triggers_config": '<tg-emoji emoji-id="4904936030232117798">⚙️</tg-emoji> <b>Настройка триггеров для Foundation</b>\n\nЧат: {} (ID: {})\n\nТекущие триггеры:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}',
        "select_trigger": "Выберите триггер для настройки:",
        "enter_trigger_word": "✍️ Введите слово-триггер (или 0 для отключения):",
        "no_triggers": "Триггеры не настроены",
        "_cls_doc": "Случайное NSFW и SFW медиа",
        "fsfw_cmd_doc": "Отправить рандомное SFW медиа с @sfwfond",
        "access_main_text": "Для работы модуля необходимо вступить в основной канал.\n\nРезервный канал необязателен и используется как запасной источник.",
        "access_reserve_text": "Выбран резервный источник. Для получения медиа необходимо вступить в резервный канал.",
        "main_channel_button": "Основной канал",
        "reserve_channel_button": "Резервный канал",
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
        "cfg_source_channel": "Откуда брать медиа для команд Fond.",
        "source_main_option": "Основная",
        "source_reserve_option": "Резерв",
        "private_chat": "Личный чат",
        "chat_fallback": "Чат {}",
    }

    def __init__(self):
        self._foundation_links = {
            self.SOURCE_MAIN: None,
            self.SOURCE_RESERVE: None,
        }
        self._foundation_entities = {
            self.SOURCE_MAIN: None,
            self.SOURCE_RESERVE: None,
        }
        self._foundation_entity_times = {
            self.SOURCE_MAIN: 0,
            self.SOURCE_RESERVE: 0,
        }
        self._media_cache = {
            self.SOURCE_MAIN: {},
            self.SOURCE_RESERVE: {},
        }
        self._video_cache = {
            self.SOURCE_MAIN: {},
            self.SOURCE_RESERVE: {},
        }
        self._cache_time = {
            self.SOURCE_MAIN: {},
            self.SOURCE_RESERVE: {},
        }
        self._recent_media_ids = {
            f"{self.SOURCE_MAIN}:any": [],
            f"{self.SOURCE_MAIN}:video": [],
            f"{self.SOURCE_RESERVE}:any": [],
            f"{self.SOURCE_RESERVE}:video": [],
            "sfw_any": [],
        }
        self._recent_media_limit = 20
        self.entity_check_interval = 300
        self.reserve_membership_check_interval = 60
        self.cache_ttl = 1200
        self.link_channel_username = "foundationlink"
        self.link_message_id = 4
        self.update_source_url = "https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/Foundation.py"
        self.update_check_interval = 21600
        self.update_notice_repeat_interval = 5 * 24 * 60 * 60
        self._update_check_task = None
        self._update_notice_lock = asyncio.Lock()
        self.foundation_link_update_interval = 300
        self.foundation_link_retry_interval = 30
        self._last_foundation_link_update = 0
        self._foundation_link_lock = asyncio.Lock()
        self._nsfw_cache_locks = {
            self.SOURCE_MAIN: asyncio.Lock(),
            self.SOURCE_RESERVE: asyncio.Lock(),
        }
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
            ),
            loader.ConfigValue(
                "source_channel",
                self.SOURCE_MAIN,
                lambda: self.strings("cfg_source_channel"),
                validator=loader.validators.Choice(
                    [
                        self.SOURCE_MAIN,
                        self.SOURCE_RESERVE,
                        "Main",
                        "Reserve",
                        "Основная",
                        "Резерв",
                    ]
                ),
                on_change=self._on_source_channel_change,
            )
        )

    def config_complete(self):
        source = self._source_code(self.config["source_channel"])
        options = [
            self.strings("source_main_option"),
            self.strings("source_reserve_option"),
        ]
        self.config.change_validator(
            "source_channel",
            loader.validators.Choice(options),
        )
        self.config._config["source_channel"].default = options[0]
        self.config["source_channel"] = self._source_option(source)

    def _source_code(self, value):
        return {
            self.SOURCE_MAIN: self.SOURCE_MAIN,
            self.SOURCE_RESERVE: self.SOURCE_RESERVE,
            "Main": self.SOURCE_MAIN,
            "Reserve": self.SOURCE_RESERVE,
            "Основная": self.SOURCE_MAIN,
            "Резерв": self.SOURCE_RESERVE,
        }.get(value, self.SOURCE_MAIN)

    def _source_option(self, source):
        return self.strings(
            "source_reserve_option"
            if source == self.SOURCE_RESERVE
            else "source_main_option"
        )

    def _on_source_channel_change(self):
        source = self._source_code(self.config["source_channel"])
        if source in self._foundation_links:
            self._reset_foundation_source(source)

    async def client_ready(self):
        await self._migrate_legacy_storage()
        self.triggers = self.get("triggers", {})
        self._foundation_links[self.SOURCE_MAIN] = self.get(
            "main_foundation_link",
            self.get("actual_foundation_link", None),
        )
        self._foundation_links[self.SOURCE_RESERVE] = self.get(
            "reserve_foundation_link",
            None,
        )
        await self._update_foundation_link_on_demand()
        await self._load_entity(self._source_code(self.config["source_channel"]))
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

    @staticmethod
    def _parse_foundation_links(text):
        main = re.search(r"\[\s*(https?://t\.me/[^\s\]]+)\s*\]", text)
        reserve = re.search(r"\{\s*(https?://t\.me/[^\s}]+)\s*\}", text)
        return (
            main.group(1).rstrip(".,)") if main else None,
            reserve.group(1).rstrip(".,)") if reserve else None,
        )

    def _reset_foundation_source(self, source):
        self._foundation_entities[source] = None
        self._foundation_entity_times[source] = 0
        self._media_cache[source].clear()
        self._video_cache[source].clear()
        self._cache_time[source].clear()
        self._recent_media_ids[f"{source}:any"].clear()
        self._recent_media_ids[f"{source}:video"].clear()

    async def _update_foundation_link_on_demand(self):
        current_time = time.time()
        links_available = any(self._foundation_links.values())
        interval = (
            self.foundation_link_update_interval
            if links_available
            else self.foundation_link_retry_interval
        )
        if current_time - self._last_foundation_link_update < interval:
            return links_available
        async with self._foundation_link_lock:
            current_time = time.time()
            links_available = any(self._foundation_links.values())
            interval = (
                self.foundation_link_update_interval
                if links_available
                else self.foundation_link_retry_interval
            )
            if current_time - self._last_foundation_link_update < interval:
                return links_available
            try:
                link_channel_entity = await self.client.get_entity(self.link_channel_username)
                message = await self.client.get_messages(link_channel_entity, ids=self.link_message_id)
                main_link, reserve_link = self._parse_foundation_links(
                    getattr(message, "raw_text", "") or ""
                )
                if not main_link:
                    raise RuntimeError("Main Foundation link is missing in the source message")
                old_main_link = self._foundation_links[self.SOURCE_MAIN]
                if main_link != old_main_link:
                    logger.info(
                        "Main Foundation link updated: %s -> %s",
                        old_main_link,
                        main_link,
                    )
                    self._foundation_links[self.SOURCE_MAIN] = main_link
                    self.set("main_foundation_link", main_link)
                    self.set("actual_foundation_link", main_link)
                    self._reset_foundation_source(self.SOURCE_MAIN)
                    if old_main_link:
                        self.config["source_channel"] = self._source_option(
                            self.SOURCE_MAIN
                        )
                if reserve_link and reserve_link != self._foundation_links[self.SOURCE_RESERVE]:
                    logger.info(
                        "Reserve Foundation link updated: %s -> %s",
                        self._foundation_links[self.SOURCE_RESERVE],
                        reserve_link,
                    )
                    self._foundation_links[self.SOURCE_RESERVE] = reserve_link
                    self.set("reserve_foundation_link", reserve_link)
                    self._reset_foundation_source(self.SOURCE_RESERVE)
                self._last_foundation_link_update = current_time
                return True
            except Exception as e:
                logger.warning(
                    "Error updating Foundation link from channel: %s. Using cached link if available.",
                    e,
                )
                return any(self._foundation_links.values())
    
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

    async def _load_entity(self, source):
        current_time = time.time()
        check_interval = (
            self.reserve_membership_check_interval
            if source == self.SOURCE_RESERVE
            else self.entity_check_interval
        )
        if (
            self._foundation_entities[source]
            and current_time - self._foundation_entity_times[source]
            < check_interval
        ):
            return True
        link = self._foundation_links[source]
        if not link:
            self._foundation_entities[source] = None
            return False
        try:
            self._foundation_entities[source] = await self.client.get_entity(link)
            self._foundation_entity_times[source] = current_time
            return True
        except Exception as e:
            logger.warning("Could not load %s Foundation entity from %s: %s", source, link, e)
            self._foundation_entities[source] = None
            return False

    async def _has_source_access(self, source):
        if not await self._load_entity(source):
            return False
        if (
            source == self.SOURCE_RESERVE
            and getattr(self._foundation_entities[source], "left", False)
        ):
            self._foundation_entity_times[source] = 0
            return False
        return True

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

    async def _show_access_required(self, message: Message, source):
        selected_link = self._foundation_links[source]
        if not selected_link:
            await utils.answer(message, self.strings("source_unavailable"))
            return
        order = (
            (self.SOURCE_RESERVE, self.SOURCE_MAIN)
            if source == self.SOURCE_RESERVE
            else (self.SOURCE_MAIN, self.SOURCE_RESERVE)
        )
        markup = []
        for item in order:
            link = self._foundation_links[item]
            if not link:
                continue
            markup.append(
                [
                    {
                        "text": self.strings(
                            "reserve_channel_button"
                            if item == self.SOURCE_RESERVE
                            else "main_channel_button"
                        ),
                        "url": link,
                        "style": "primary",
                    }
                ]
            )
        text = self.strings(
            "access_reserve_text"
            if source == self.SOURCE_RESERVE
            else "access_main_text"
        )
        form = None
        try:
            form = await self.inline.form(
                message=message,
                text=text,
                reply_markup=markup,
            )
        except Exception as e:
            logger.warning("Could not show Foundation access form: %s", e)
        if form:
            return
        links = "\n".join(
            utils.escape_html(self._foundation_links[item])
            for item in order
            if self._foundation_links[item]
        )
        await utils.answer(
            message,
            f"{text}\n\n{links}",
        )

    async def _dispatch_media(
        self,
        message: Message,
        media_type: str = "any",
        delete_command: bool = False,
        is_sfw: bool = False,
    ):
        if not is_sfw:
            await self._update_foundation_link_on_demand()
        await self._send_media(message, media_type, delete_command, is_sfw)

    async def _get_cached_media(self, source, media_type="any"):
        if (
            source == self.SOURCE_RESERVE
            and not await self._has_source_access(source)
        ):
            return None
        current_time = time.time()
        cache_key = "messages"
        if (
            cache_key in self._cache_time[source]
            and current_time - self._cache_time[source][cache_key] < self.cache_ttl
        ):
            if media_type == "any":
                if "any" in self._media_cache[source]:
                    return self._media_cache[source]["any"]
            elif "video" in self._video_cache[source]:
                return self._video_cache[source]["video"]
        async with self._nsfw_cache_locks[source]:
            current_time = time.time()
            if (
                cache_key in self._cache_time[source]
                and current_time - self._cache_time[source][cache_key] < self.cache_ttl
            ):
                if media_type == "any":
                    if "any" in self._media_cache[source]:
                        return self._media_cache[source]["any"]
                elif "video" in self._video_cache[source]:
                    return self._video_cache[source]["video"]
            if not await self._load_entity(source):
                return None
            while True:
                try:
                    messages = await self.client.get_messages(
                        self._foundation_entities[source],
                        limit=1500,
                    )
                    break
                except FloodWaitError as e:
                    logger.warning("FloodWait for %s seconds on %s Foundation", e.seconds, source)
                    await asyncio.sleep(e.seconds)
                except (UserNotParticipantError, ChannelPrivateError) as e:
                    logger.warning("No access to %s Foundation source: %s", source, e)
                    return None
                except ValueError as e:
                    if "Could not find the entity" in str(e):
                        return None
                    raise e
            if not messages:
                self._media_cache[source]["any"] = []
                self._video_cache[source]["video"] = []
                self._cache_time[source][cache_key] = time.time()
                return []
            media_messages = [msg for msg in messages if msg.media]
            video_messages = []
            for msg in media_messages:
                if hasattr(msg.media, 'document'):
                    attr = getattr(msg.media.document, 'mime_type', '')
                    if 'video' in attr:
                        video_messages.append(msg)
            self._media_cache[source]["any"] = media_messages
            self._video_cache[source]["video"] = video_messages
            self._cache_time[source][cache_key] = time.time()
            return (
                self._media_cache[source]["any"]
                if media_type == "any"
                else self._video_cache[source]["video"]
            )
    
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

    @staticmethod
    def _filter_random_media(media_list):
        return [
            item
            for item in media_list
            if not re.search(
                r"(?<!\w)#игра(?!\w)",
                str(
                    getattr(item, "raw_text", None)
                    or getattr(item, "message", None)
                    or getattr(item, "text", None)
                    or ""
                ),
                flags=re.IGNORECASE,
            )
        ]

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
                media_list = self._filter_random_media(media_list)
                if not media_list:
                    await utils.answer(message, self.strings("fsfw_no_media"))
                    return
            else:
                source = self._source_code(self.config["source_channel"])
                media_list = await self._get_cached_media(source, media_type)
                if media_list is None:
                    return await self._show_access_required(message, source)
                media_list = self._filter_random_media(media_list)
                if (
                    not media_list
                    and media_type == "any"
                    and source == self.SOURCE_MAIN
                    and self._foundation_links[self.SOURCE_RESERVE]
                ):
                    self.config["source_channel"] = self._source_option(
                        self.SOURCE_RESERVE
                    )
                    source = self.SOURCE_RESERVE
                    media_list = await self._get_cached_media(source, media_type)
                    if media_list is None:
                        return await self._show_access_required(message, source)
                    media_list = self._filter_random_media(media_list)
                if not media_list:
                    if media_type == "any":
                        await utils.answer(message, self.strings("no_media"))
                    else:
                        await utils.answer(message, self.strings("no_videos"))
                    return
            
            pool_key = "sfw_any" if is_sfw else f"{source}:{media_type}"
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
        await self._dispatch_media(message, "any", delete_command=True)

    @loader.command(ru_doc="Отправить NSFW видео с Фонда")
    async def vfond(self, message: Message):
        """Send NSFW video from Foundation"""
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._dispatch_media(message, "video", delete_command=True)

    @loader.command(ru_doc="Отправить рандомное SFW медиа с @sfwfond")
    async def fsfw(self, message: Message):
        """Send random SFW media from @sfwfond"""
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._dispatch_media(message, delete_command=True, is_sfw=True)

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
        chat_title = utils.escape_html(
            getattr(chat, "title", self.strings("private_chat"))
        )
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
            chat_title = utils.escape_html(
                getattr(chat, "title", self.strings("private_chat"))
            )
        except Exception as e:
            logger.warning(f"Could not load chat title for {chat_id}: {e}")
            chat_title = utils.escape_html(
                self.strings("chat_fallback").format(chat_id)
            )
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
                    await self._dispatch_media(message, "any", delete_command=True)
                elif command == "vfond":
                    await self._dispatch_media(message, "video", delete_command=True)
                elif command == "fsfw":
                    await self._dispatch_media(message, delete_command=True, is_sfw=True)
                break
        except Exception as e:
            logger.exception(e)
