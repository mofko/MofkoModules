__version__ = (1, 5, 0)
# meta developer: @mofkomodules
# Name: SelfDestruct
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_686.png
#metapic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_686.png
# meta fhsdesc: cleaner, deleter, auto, tool, privacy, mofko, мофко, автоудаление, самоуничтожение, deleteme
# meta tags: cleaner, deleter, auto, tool, privacy, mofko, мофко, автоудаление, самоуничтожение, deleteme

import asyncio
import logging
import re
import time

from herokutl.tl.types import (
    DocumentAttributeAnimated,
    DocumentAttributeAudio,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
)
from herokutl.types import Message
from telethon.errors import ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


@loader.tds
class SelfDestructMod(loader.Module):
    """Periodically deletes your messages in specified chats."""

    strings = {
        "name": "SelfDestruct",
        "_cls_doc": "Periodically deletes your messages in specified chats.",
        "config_title": "<b>Self-Destruct</b>\n<i>Chat: {}</i>",
        "menu_hint": "\n\nThis module periodically deletes <b>only your own messages</b> in this chat.",
        "enabled_status": "\n\n{} Status: <b>Enabled</b>",
        "disabled_status": "\n\n{} Status: <b>Disabled</b>",
        "type_status": "\n{} Delete: <code>{}</code>",
        "interval_status": "\n{} Every: <code>{} min.</code>",
        "scope_status": "\n{} Scope: <code>{}</code>",
        "last_run_status": "\n{} Last cleanup: <code>{}</code>",
        "not_configured": "\n\n<i>Not configured yet. Choose what to delete and enable cleanup.</i>",
        "never": "never",
        "btn_enable": "Enable",
        "btn_disable": "Disable",
        "btn_set_type": "What to delete",
        "btn_set_interval": "Cleanup interval",
        "btn_scope": "Scope",
        "btn_close": "Close",
        "btn_back": "Back",
        "btn_all": "All messages",
        "btn_media": "Any media",
        "btn_text": "Text only",
        "btn_photo": "Photos",
        "btn_video": "Videos",
        "btn_video_note": "Video notes",
        "btn_gif": "GIFs",
        "btn_sticker": "Stickers",
        "btn_voice": "Voice messages",
        "btn_audio": "Music/audio",
        "btn_file": "Files",
        "btn_link": "Links/previews",
        "scope_chat": "whole chat",
        "scope_topic": "current topic",
        "type_menu_title": "<b>What should SelfDestruct delete?</b>\n\nChoose one message type for automatic cleanup.",
        "interval_input": "Enter interval in minutes, from 1 to 10080",
        "interval_saved": "Interval saved!",
        "type_saved": "Type saved!",
        "toggled": "Toggled!",
        "invalid_interval": "Invalid number. Use 1-10080 minutes.",
        "loop_error": "SelfDestruct loop error in chat {}: {}",
        "inline_unavailable": "SelfDestruct for chat: {}\nState: {}\nDelete: {}\nInterval: {} min.",
        "enabled_plain": "enabled",
        "disabled_plain": "disabled",
        "type_all": "all messages",
        "type_media": "any media",
        "type_text": "text only",
        "type_photo": "photos",
        "type_video": "videos",
        "type_video_note": "video notes",
        "type_gif": "GIFs",
        "type_sticker": "stickers",
        "type_voice": "voice messages",
        "type_audio": "music/audio",
        "type_file": "files",
        "type_link": "links/previews",
        "all_plain": "all messages",
        "media_plain": "any media",
    }

    strings_ru = {
        "_cls_doc": "Периодически удаляет ваши сообщения в указанных чатах.",
        "config_title": "<b>Самоуничтожение сообщений</b>\n<i>Чат: {}</i>",
        "menu_hint": "\n\nМодуль периодически удаляет <b>только ваши сообщения</b> в этом чате.",
        "enabled_status": "\n\n{} Статус: <b>Включено</b>",
        "disabled_status": "\n\n{} Статус: <b>Выключено</b>",
        "type_status": "\n{} Удалять: <code>{}</code>",
        "interval_status": "\n{} Каждые: <code>{} мин.</code>",
        "scope_status": "\n{} Область: <code>{}</code>",
        "last_run_status": "\n{} Последняя очистка: <code>{}</code>",
        "not_configured": "\n\n<i>Еще не настроено. Выберите, что удалять, и включите очистку.</i>",
        "never": "никогда",
        "btn_enable": "Включить",
        "btn_disable": "Выключить",
        "btn_set_type": "Что удалять",
        "btn_set_interval": "Интервал очистки",
        "btn_scope": "Область",
        "btn_close": "Закрыть",
        "btn_back": "Назад",
        "btn_all": "Все сообщения",
        "btn_media": "Любые медиа",
        "btn_text": "Только текст",
        "btn_photo": "Фото",
        "btn_video": "Видео",
        "btn_video_note": "Видеокружки",
        "btn_gif": "GIF",
        "btn_sticker": "Стикеры",
        "btn_voice": "Голосовые",
        "btn_audio": "Музыка/аудио",
        "btn_file": "Файлы",
        "btn_link": "Ссылки/превью",
        "scope_chat": "весь чат",
        "scope_topic": "текущий топик",
        "type_menu_title": "<b>Что должен удалять SelfDestruct?</b>\n\nВыберите один тип сообщений для автоочистки.",
        "interval_input": "Введите интервал в минутах, от 1 до 10080",
        "interval_saved": "Интервал сохранен!",
        "type_saved": "Тип сохранен!",
        "toggled": "Переключено!",
        "invalid_interval": "Неверное число. Используйте 1-10080 минут.",
        "loop_error": "Ошибка в цикле SelfDestruct в чате {}: {}",
        "inline_unavailable": "SelfDestruct для чата: {}\nСостояние: {}\nУдалять: {}\nИнтервал: {} мин.",
        "enabled_plain": "включено",
        "disabled_plain": "выключено",
        "type_all": "все сообщения",
        "type_media": "любые медиа",
        "type_text": "только текст",
        "type_photo": "фото",
        "type_video": "видео",
        "type_video_note": "видеокружки",
        "type_gif": "GIF",
        "type_sticker": "стикеры",
        "type_voice": "голосовые",
        "type_audio": "музыка/аудио",
        "type_file": "файлы",
        "type_link": "ссылки/превью",
        "all_plain": "все сообщения",
        "media_plain": "любые медиа",
    }

    _BATCH_SIZE = 100
    _BATCH_DELAY = 3
    _MAX_AUTO_DELETE_PER_RUN = 500
    _MAX_AUTO_SCAN_PER_RUN = 1500
    _MAX_DESTME_DELETE_PER_BATCH = 100
    _MAX_INTERVAL_MINUTES = 10080
    _ERROR_COOLDOWN_SECONDS = 300
    _DELETE_TYPES = {
        "all",
        "media",
        "text",
        "photo",
        "video",
        "video_note",
        "gif",
        "sticker",
        "voice",
        "audio",
        "file",
        "link",
    }
    _URL_RE = re.compile(r"(https?://|t\.me/|www\.)", re.IGNORECASE)

    def __init__(self):
        self.config = loader.ModuleConfig()

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.chats = self.db.get(__name__, "chats", {})

    def _settings_key(self, chat_id: int, topic_id: int = None) -> str:
        return f"{chat_id}:{topic_id or 0}"

    def _legacy_settings_key(self, chat_id: int) -> str:
        return str(chat_id)

    def _parse_settings_key(self, key: str):
        try:
            chat_id_str, topic_id_str = str(key).split(":", 1)
            return int(chat_id_str), int(topic_id_str) or None
        except (TypeError, ValueError):
            try:
                return int(key), None
            except (TypeError, ValueError):
                return None, None

    def _get_settings(self, chat_id: int, topic_id: int = None) -> dict:
        defaults = {
            "enabled": False,
            "type": "all",
            "interval": 60,
            "last_run": 0,
            "error_count": 0,
            "chat_id": chat_id,
            "topic_id": topic_id,
        }
        key = self._settings_key(chat_id, topic_id)
        stored = self.chats.get(key)
        if stored is None and topic_id is None:
            stored = self.chats.get(self._legacy_settings_key(chat_id), {})
        elif stored is None:
            stored = {}
        if not isinstance(stored, dict):
            return defaults
        settings = {**defaults, **stored}
        settings["chat_id"] = chat_id
        settings["topic_id"] = topic_id
        settings["type"] = settings.get("type") if settings.get("type") in self._DELETE_TYPES else "all"
        try:
            interval = int(settings.get("interval", defaults["interval"]))
        except (TypeError, ValueError):
            interval = defaults["interval"]
        settings["interval"] = min(max(interval, 1), self._MAX_INTERVAL_MINUTES)
        return settings

    def _save_settings(self, chat_id: int, settings: dict, topic_id: int = None):
        settings["chat_id"] = chat_id
        settings["topic_id"] = topic_id
        self.chats[self._settings_key(chat_id, topic_id)] = settings
        if topic_id is None:
            self.chats.pop(self._legacy_settings_key(chat_id), None)
        self.db.set(__name__, "chats", self.chats)

    def _premium_emoji(self, emoji_id: str, fallback: str) -> str:
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

    def _format_type_label(self, deletion_type: str) -> str:
        key = f"type_{deletion_type if deletion_type in self._DELETE_TYPES else 'all'}"
        return self.strings(key)

    def _document_attributes(self, msg: Message):
        document = getattr(getattr(msg, "media", None), "document", None)
        return getattr(document, "attributes", []) or []

    def _is_media_message(self, msg: Message) -> bool:
        return bool(getattr(msg, "media", None) and not getattr(msg, "web_preview", None))

    def _has_link(self, msg: Message) -> bool:
        if isinstance(getattr(msg, "media", None), MessageMediaWebPage) or getattr(msg, "web_preview", None):
            return True
        return bool(self._URL_RE.search(getattr(msg, "message", "") or ""))

    def _message_matches_type(self, msg: Message, deletion_type: str) -> bool:
        if deletion_type == "all":
            return True
        if deletion_type == "media":
            return self._is_media_message(msg)
        if deletion_type == "text":
            return bool((getattr(msg, "message", "") or "").strip() and not getattr(msg, "media", None))
        if deletion_type == "link":
            return self._has_link(msg)

        media = getattr(msg, "media", None)
        attrs = self._document_attributes(msg)

        if deletion_type == "photo":
            return isinstance(media, MessageMediaPhoto)
        if deletion_type == "gif":
            return any(isinstance(attr, DocumentAttributeAnimated) for attr in attrs)
        if deletion_type == "sticker":
            return any(isinstance(attr, DocumentAttributeSticker) for attr in attrs)
        if deletion_type == "voice":
            return any(isinstance(attr, DocumentAttributeAudio) and getattr(attr, "voice", False) for attr in attrs)
        if deletion_type == "audio":
            return any(isinstance(attr, DocumentAttributeAudio) and not getattr(attr, "voice", False) for attr in attrs)
        if deletion_type == "video":
            return any(
                isinstance(attr, DocumentAttributeVideo)
                and not getattr(attr, "round_message", False)
                for attr in attrs
            ) and not self._message_matches_type(msg, "gif")
        if deletion_type == "video_note":
            return any(
                isinstance(attr, DocumentAttributeVideo)
                and getattr(attr, "round_message", False)
                for attr in attrs
            )
        if deletion_type == "file":
            return isinstance(media, MessageMediaDocument) and not any(
                self._message_matches_type(msg, kind)
                for kind in ("video", "video_note", "gif", "sticker", "voice", "audio")
            )

        return False

    def _format_scope_label(self, scope_topic_id: int = None) -> str:
        return self.strings("scope_topic") if scope_topic_id else self.strings("scope_chat")

    def _format_last_run(self, timestamp: float) -> str:
        if not timestamp:
            return self.strings("never")
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))

    async def _detect_topic_id(self, message: Message, chat_id: int = None):
        topic_id = utils.get_topic(message)
        if topic_id:
            return topic_id

        reply_to = getattr(message, "reply_to", None)
        if reply_to:
            topic_id = getattr(reply_to, "reply_to_top_id", None)
            if topic_id:
                return topic_id
            if getattr(reply_to, "forum_topic", False):
                topic_id = getattr(reply_to, "reply_to_msg_id", None)
                if topic_id:
                    return topic_id

        topic_id = getattr(message, "reply_to_msg_id", None)
        if not topic_id:
            return None

        try:
            entity = await self.client.get_entity(chat_id or utils.get_chat_id(message))
        except Exception:
            return None

        return topic_id if getattr(entity, "forum", False) else None

    def _build_settings_text(
        self,
        chat_title: str,
        settings: dict,
        premium: bool = True,
        show_scope: bool = False,
    ) -> str:
        settings_icon = self._premium_emoji("4904936030232117798", "⚙️") if premium else "⚙️"
        enabled_icon = self._premium_emoji("5206607081334906820", "✅") if premium else "✅"
        disabled_icon = self._premium_emoji("5121063440311386962", "❌") if premium else "❌"
        type_icon = self._premium_emoji("5879841310902324730", "✏️") if premium else "✏️"
        interval_icon = self._premium_emoji("5258258882022612173", "⏱️") if premium else "⏱️"
        last_run_icon = self._premium_emoji("5870921681735781843", "⏱️") if premium else "⏱️"
        scope_icon = self._premium_emoji("5444965220663458467", "📁") if premium else "📁"
        text = f"{settings_icon} {self.strings('config_title').format(utils.escape_html(chat_title))}"
        text += self.strings("menu_hint")
        text += self.strings("enabled_status").format(enabled_icon) if settings["enabled"] else self.strings("disabled_status").format(disabled_icon)
        if show_scope:
            text += self.strings("scope_status").format(
                scope_icon,
                utils.escape_html(self._format_scope_label(settings.get("topic_id"))),
            )
        text += self.strings("type_status").format(type_icon, utils.escape_html(self._format_type_label(settings["type"])))
        text += self.strings("interval_status").format(interval_icon, settings["interval"])
        text += self.strings("last_run_status").format(last_run_icon, self._format_last_run(settings["last_run"]))
        if settings["last_run"] == 0 and not settings["enabled"]:
            text += self.strings("not_configured")
        return text

    def _build_toggle_button(self, settings: dict, chat_id: int, current_topic_id: int = None) -> dict:
        if settings["enabled"]:
            return {
                "text": f"❌ {self.strings('btn_disable')}",
                "callback": self._toggle_enabled,
                "args": (chat_id, current_topic_id, settings.get("topic_id")),
                "style": "danger",
                "emoji_id": "5121063440311386962",
            }
        return {
            "text": f"🚀 {self.strings('btn_enable')}",
            "callback": self._toggle_enabled,
            "args": (chat_id, current_topic_id, settings.get("topic_id")),
            "style": "success",
            "emoji_id": "5258332798409783582",
        }

    def _build_interval_button(self, chat_id: int, current_topic_id: int = None, scope_topic_id: int = None) -> dict:
        return {
            "text": f"⏱️ {self.strings('btn_set_interval')}",
            "emoji_id": "5258258882022612173",
            "input": self.strings("interval_input"),
            "handler": self._save_interval,
            "args": (chat_id, current_topic_id, scope_topic_id),
        }

    def _build_fallback_text(self, chat_title: str, settings: dict) -> str:
        state = self.strings("enabled_plain") if settings["enabled"] else self.strings("disabled_plain")
        deletion_type = self.strings("media_plain") if settings["type"] == "media" else self.strings("all_plain")
        return self.strings("inline_unavailable").format(
            utils.escape_html(chat_title),
            utils.escape_html(state),
            utils.escape_html(deletion_type),
            settings["interval"],
        )

    def _is_destme_target(self, msg: Message, chat_id: int) -> bool:
        sender_id = getattr(msg, "sender_id", None)
        return bool(getattr(msg, "out", False) or sender_id == chat_id)

    @loader.loop(interval=60, autostart=True)
    async def _deleter_loop(self):
        now = time.time()
        for chat_id_str, raw_settings in self.chats.copy().items():
            if not isinstance(raw_settings, dict) or not raw_settings.get("enabled"):
                continue
            chat_id, topic_id = self._parse_settings_key(chat_id_str)
            if chat_id is None:
                self.chats.pop(chat_id_str, None)
                self.db.set(__name__, "chats", self.chats)
                continue
            settings = self._get_settings(chat_id, topic_id)
            if not settings.get("enabled"):
                continue
            interval_seconds = settings.get("interval", 60) * 60
            last_run = settings.get("last_run", 0)
            if now - last_run < interval_seconds:
                continue
            try:
                deleted_count = 0
                scanned_count = 0
                iter_kwargs = {"from_user": "me"}
                if topic_id:
                    iter_kwargs["reply_to"] = topic_id
                while deleted_count < self._MAX_AUTO_DELETE_PER_RUN and scanned_count < self._MAX_AUTO_SCAN_PER_RUN:
                    remaining_delete = self._MAX_AUTO_DELETE_PER_RUN - deleted_count
                    ids_to_delete = []
                    async for msg in self.client.iter_messages(chat_id, **iter_kwargs):
                        scanned_count += 1
                        if not self._message_matches_type(msg, settings.get("type", "all")):
                            if scanned_count >= self._MAX_AUTO_SCAN_PER_RUN:
                                break
                            continue
                        ids_to_delete.append(msg.id)
                        if (
                            len(ids_to_delete) >= min(self._BATCH_SIZE, remaining_delete)
                            or scanned_count >= self._MAX_AUTO_SCAN_PER_RUN
                        ):
                            break
                    if ids_to_delete:
                        await self.client.delete_messages(chat_id, ids_to_delete)
                        deleted_count += len(ids_to_delete)
                        await asyncio.sleep(self._BATCH_DELAY)
                    if len(ids_to_delete) < self._BATCH_SIZE:
                        break
                settings["last_run"] = time.time()
                settings["error_count"] = 0
                self._save_settings(chat_id, settings, topic_id)
            except (ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError):
                logger.warning(f"No access to chat {chat_id}, removing from config.")
                del self.chats[chat_id_str]
                self.db.set(__name__, "chats", self.chats)
            except Exception as e:
                settings["last_run"] = time.time() + self._ERROR_COOLDOWN_SECONDS - interval_seconds
                settings["error_count"] = int(settings.get("error_count", 0)) + 1
                if settings["error_count"] >= 3:
                    settings["enabled"] = False
                self._save_settings(chat_id, settings, topic_id)
                logger.exception(self.strings("loop_error").format(chat_id, e))

    @loader.command(
        ru_doc="Настроить авто-удаление своих сообщений в этом чате.",
        en_doc="Configure auto-deletion of your messages in this chat.",
    )
    async def deleteme(self, message: Message):
        """Configure self-destruct for this chat."""
        chat_id = utils.get_chat_id(message)
        current_topic_id = await self._detect_topic_id(message, chat_id)
        await self._show_main_menu(message, chat_id, current_topic_id, current_topic_id)

    @loader.command(
        ru_doc="Тихо удалить все свои сообщения в этом чате.",
        en_doc="Silently delete all your messages in this chat.",
    )
    async def destme(self, message: Message):
        """Silently delete all your messages in this chat."""
        chat_id = utils.get_chat_id(message)
        topic_id = await self._detect_topic_id(message, chat_id)
        command_id = message.id
        try:
            try:
                await message.delete()
            except Exception:
                pass
            ids_to_delete = []
            iter_kwargs = {}
            if topic_id:
                iter_kwargs["reply_to"] = topic_id
            async for msg in self.client.iter_messages(chat_id, **iter_kwargs):
                if msg.id == command_id or not self._is_destme_target(msg, chat_id):
                    continue
                ids_to_delete.append(msg.id)
                if len(ids_to_delete) >= self._MAX_DESTME_DELETE_PER_BATCH:
                    await self.client.delete_messages(chat_id, ids_to_delete)
                    await asyncio.sleep(self._BATCH_DELAY)
                    ids_to_delete = []
            if ids_to_delete:
                await self.client.delete_messages(chat_id, ids_to_delete)
        except (ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError):
            logger.warning(f"No access to chat {chat_id} for destme.")
        except Exception as e:
            logger.exception(e)

    async def _show_main_menu(
        self,
        target,
        chat_id: int = None,
        current_topic_id: int = None,
        scope_topic_id: int = None,
    ):
        if chat_id is None:
            chat_id = utils.get_chat_id(target)
        if current_topic_id is None:
            if isinstance(target, Message):
                current_topic_id = await self._detect_topic_id(target, chat_id)
            elif isinstance(target, InlineCall):
                current_topic_id = utils.get_topic(target)
        if scope_topic_id and not current_topic_id:
            scope_topic_id = None
        try:
            chat = await self.client.get_entity(chat_id)
            chat_title = getattr(chat, "title", f"ID {chat_id}")
        except Exception:
            chat_title = f"ID {chat_id}"
        settings = self._get_settings(chat_id, scope_topic_id)
        text = self._build_settings_text(
            chat_title,
            settings,
            premium=True,
            show_scope=bool(current_topic_id),
        )
        markup = [
            [
                self._build_toggle_button(settings, chat_id, current_topic_id),
                {
                    "text": f"✏️ {self.strings('btn_set_type')}",
                    "callback": self._set_type_menu,
                    "args": (chat_id, current_topic_id, scope_topic_id),
                    "emoji_id": "5879841310902324730",
                },
            ],
            [self._build_interval_button(chat_id, current_topic_id, scope_topic_id)],
        ]
        if current_topic_id:
            markup.append(
                [
                    {
                        "text": f"📁 {self.strings('btn_scope')}: {self._format_scope_label(scope_topic_id)}",
                        "callback": self._toggle_scope,
                        "args": (chat_id, current_topic_id, scope_topic_id),
                        "emoji_id": "5444965220663458467",
                    }
                ]
            )
        markup.append(
            [
                {
                    "text": f"❌ {self.strings('btn_close')}",
                    "action": "close",
                    "style": "danger",
                    "emoji_id": "5121063440311386962",
                }
            ]
        )
        if isinstance(target, Message):
            try:
                await self.inline.form(text=text, message=target, reply_markup=markup)
            except Exception:
                await utils.answer(target, self._build_fallback_text(chat_title, settings))
        else:
            await target.edit(text=text, reply_markup=markup)

    async def _toggle_enabled(self, call: InlineCall, chat_id: int, current_topic_id: int = None, scope_topic_id: int = None):
        settings = self._get_settings(chat_id, scope_topic_id)
        settings["enabled"] = not settings["enabled"]
        settings["last_run"] = time.time() if settings["enabled"] else 0
        settings["error_count"] = 0
        self._save_settings(chat_id, settings, scope_topic_id)
        try:
            await call.answer(self.strings("toggled"))
        except Exception:
            pass
        await self._show_main_menu(call, chat_id, current_topic_id, scope_topic_id)

    async def _toggle_scope(self, call: InlineCall, chat_id: int, current_topic_id: int, scope_topic_id: int = None):
        next_scope_topic_id = None if scope_topic_id else current_topic_id
        await self._show_main_menu(call, chat_id, current_topic_id, next_scope_topic_id)

    async def _set_type_menu(self, call: InlineCall, chat_id: int, current_topic_id: int = None, scope_topic_id: int = None):
        type_icon = self._premium_emoji("5879841310902324730", "✏️")
        type_buttons = [
            ("📄", "btn_all", "all", "5877495434124988415"),
            ("🖼", "btn_media", "media", "5258254475386167466"),
            ("✏️", "btn_text", "text", "5879841310902324730"),
            ("🌄", "btn_photo", "photo", "5258254475386167466"),
            ("🎬", "btn_video", "video", "5877495434124988415"),
            ("⭕", "btn_video_note", "video_note", "5877495434124988415"),
            ("🎞", "btn_gif", "gif", "5877495434124988415"),
            ("⭐", "btn_sticker", "sticker", "5325547803936572038"),
            ("🎙", "btn_voice", "voice", "5258258882022612173"),
            ("🎵", "btn_audio", "audio", "5870921681735781843"),
            ("📎", "btn_file", "file", "5444965220663458467"),
            ("🔗", "btn_link", "link", "5247029067256987229"),
        ]
        markup = []
        for index in range(0, len(type_buttons), 2):
            row = []
            for emoji, string_key, delete_type, emoji_id in type_buttons[index:index + 2]:
                row.append(
                    {
                        "text": f"{emoji} {self.strings(string_key)}",
                        "callback": self._set_type,
                        "args": (chat_id, current_topic_id, scope_topic_id, delete_type),
                        "emoji_id": emoji_id,
                    }
                )
            markup.append(row)
        markup.append(
            [
                {
                    "text": f"⬅️ {self.strings('btn_back')}",
                    "callback": self._show_main_menu,
                    "args": (chat_id, current_topic_id, scope_topic_id),
                    "style": "danger",
                    "emoji_id": "5985346521103604145",
                }
            ]
        )
        await call.edit(
            f"{type_icon} {self.strings('type_menu_title')}",
            reply_markup=markup,
        )

    async def _set_type(
        self,
        call: InlineCall,
        chat_id: int,
        current_topic_id: int = None,
        scope_topic_id: int = None,
        new_type: str = "all",
    ):
        settings = self._get_settings(chat_id, scope_topic_id)
        settings["type"] = new_type
        settings["error_count"] = 0
        self._save_settings(chat_id, settings, scope_topic_id)
        try:
            await call.answer(self.strings("type_saved"))
        except Exception:
            pass
        await self._show_main_menu(call, chat_id, current_topic_id, scope_topic_id)

    async def _save_interval(
        self,
        call: InlineCall,
        query: str,
        chat_id: int,
        current_topic_id: int = None,
        scope_topic_id: int = None,
    ):
        try:
            interval = int(query)
            if interval <= 0 or interval > self._MAX_INTERVAL_MINUTES:
                raise ValueError
        except ValueError:
            try:
                await call.answer(self.strings("invalid_interval"), show_alert=True)
            except Exception:
                pass
            return
        settings = self._get_settings(chat_id, scope_topic_id)
        settings["interval"] = interval
        settings["last_run"] = 0
        settings["error_count"] = 0
        self._save_settings(chat_id, settings, scope_topic_id)
        try:
            await call.answer(self.strings("interval_saved"))
        except Exception:
            pass
        await self._show_main_menu(call, chat_id, current_topic_id, scope_topic_id)
