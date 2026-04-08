__version__ = (1, 4, 0)
# meta developer: @mofkomodules
# Name: SelfDestruct
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_686.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_686.png
# meta fhsdesc: cleaner, deleter, auto, tool, privacy, mofko, мофко, автоудаление, самоуничтожение

import asyncio
import logging
import time

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
        "_cls_doc": "Периодически удаляет ваши сообщения в указанных чатах.",
        "config_title": "<b>Настройки самоуничтожения</b>\n<i>Чат: {}</i>",
        "enabled_status": "\n{} Включено",
        "disabled_status": "\n{} Выключено",
        "type_status": "\n{} Тип: <code>{}</code>",
        "interval_status": "\n{} Интервал: <code>{} мин.</code>",
        "not_configured": "\n<i>Еще не настроено.</i>",
        "btn_enable": "Включить",
        "btn_disable": "Выключить",
        "btn_set_type": "Задать тип",
        "btn_set_interval": "Задать интервал",
        "btn_close": "Закрыть",
        "btn_back": "Назад",
        "btn_all": "Все сообщения",
        "btn_media": "Только медиа",
        "type_menu_title": "<b>Выберите тип удаления:</b>",
        "interval_input": "Введите интервал в минутах (например, 5)",
        "interval_saved": "Интервал сохранен!",
        "type_saved": "Тип сохранен!",
        "toggled": "Переключено!",
        "invalid_interval": "Неверное число. Должно быть > 0.",
        "loop_error": "Ошибка в цикле SelfDestruct в чате {}: {}",
        "inline_unavailable": "Настройки self-destruct для чата: {}\nСостояние: {}\nТип: {}\nИнтервал: {} мин.",
        "enabled_plain": "включено",
        "disabled_plain": "выключено",
        "all_plain": "все сообщения",
        "media_plain": "только медиа",
    }

    strings_en = {
        "_cls_doc": "Periodically deletes your messages in specified chats.",
        "config_title": "<b>Self-Destruct Configuration</b>\n<i>Chat: {}</i>",
        "enabled_status": "\n{} Enabled",
        "disabled_status": "\n{} Disabled",
        "type_status": "\n{} Type: <code>{}</code>",
        "interval_status": "\n{} Interval: <code>{} minutes</code>",
        "not_configured": "\n<i>Not configured yet.</i>",
        "btn_enable": "Enable",
        "btn_disable": "Disable",
        "btn_set_type": "Set Type",
        "btn_set_interval": "Set Interval",
        "btn_close": "Close",
        "btn_back": "Back",
        "btn_all": "All messages",
        "btn_media": "Media only",
        "type_menu_title": "<b>Select deletion type:</b>",
        "interval_input": "Enter interval in minutes (e.g., 5)",
        "interval_saved": "Interval saved!",
        "type_saved": "Type saved!",
        "toggled": "Toggled!",
        "invalid_interval": "Invalid number. Must be > 0.",
        "loop_error": "SelfDestruct loop error in chat {}: {}",
        "inline_unavailable": "Self-destruct settings for chat: {}\nState: {}\nType: {}\nInterval: {} min.",
        "enabled_plain": "enabled",
        "disabled_plain": "disabled",
        "all_plain": "all messages",
        "media_plain": "media only",
    }

    def __init__(self):
        self.config = loader.ModuleConfig()

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.chats = self.db.get(__name__, "chats", {})

    def _get_settings(self, chat_id: int) -> dict:
        return self.chats.get(
            str(chat_id),
            {"enabled": False, "type": "all", "interval": 60, "last_run": 0},
        )

    def _save_settings(self, chat_id: int, settings: dict):
        self.chats[str(chat_id)] = settings
        self.db.set(__name__, "chats", self.chats)

    def _premium_emoji(self, emoji_id: str, fallback: str) -> str:
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

    def _format_type_label(self, deletion_type: str) -> str:
        return self.strings("btn_media") if deletion_type == "media" else self.strings("btn_all")

    def _build_settings_text(self, chat_title: str, settings: dict, premium: bool = True) -> str:
        settings_icon = self._premium_emoji("4904936030232117798", "⚙️") if premium else "⚙️"
        enabled_icon = self._premium_emoji("5206607081334906820", "✅") if premium else "✅"
        disabled_icon = self._premium_emoji("5121063440311386962", "❌") if premium else "❌"
        type_icon = self._premium_emoji("5879841310902324730", "✏️") if premium else "✏️"
        interval_icon = self._premium_emoji("5258258882022612173", "⏱️") if premium else "⏱️"
        text = f"{settings_icon} {self.strings('config_title').format(utils.escape_html(chat_title))}"
        if settings["last_run"] == 0 and not settings["enabled"]:
            text += self.strings("not_configured")
            return text
        text += self.strings("enabled_status").format(enabled_icon) if settings["enabled"] else self.strings("disabled_status").format(disabled_icon)
        text += self.strings("type_status").format(type_icon, utils.escape_html(self._format_type_label(settings["type"])))
        text += self.strings("interval_status").format(interval_icon, settings["interval"])
        return text

    def _build_toggle_button(self, settings: dict, chat_id: int) -> dict:
        if settings["enabled"]:
            return {
                "text": f"❌ {self.strings('btn_disable')}",
                "callback": self._toggle_enabled,
                "args": (chat_id,),
                "style": "danger",
                "emoji_id": "5121063440311386962",
            }
        return {
            "text": f"🚀 {self.strings('btn_enable')}",
            "callback": self._toggle_enabled,
            "args": (chat_id,),
            "style": "success",
            "emoji_id": "5258332798409783582",
        }

    def _build_interval_button(self, chat_id: int, request_interval: bool) -> dict:
        button = {
            "text": f"⏱️ {self.strings('btn_set_interval')}",
            "emoji_id": "5258258882022612173",
        }
        if request_interval:
            button.update(
                {
                    "input": self.strings("interval_input"),
                    "handler": self._save_interval,
                    "args": (chat_id,),
                }
            )
        else:
            button.update(
                {
                    "callback": self._show_main_menu,
                    "args": (chat_id, True),
                }
            )
        return button

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
        for chat_id_str, settings in self.chats.copy().items():
            if not settings.get("enabled"):
                continue
            chat_id = int(chat_id_str)
            interval_seconds = settings.get("interval", 60) * 60
            last_run = settings.get("last_run", 0)
            if now - last_run < interval_seconds:
                continue
            try:
                while True:
                    ids_to_delete = []
                    async for msg in self.client.iter_messages(chat_id, from_user="me"):
                        is_media = bool(msg.media and not msg.web_preview)
                        if settings.get("type") == "media" and not is_media:
                            continue
                        ids_to_delete.append(msg.id)
                        if len(ids_to_delete) >= 100:
                            break
                    if ids_to_delete:
                        await self.client.delete_messages(chat_id, ids_to_delete)
                        await asyncio.sleep(3)
                    if len(ids_to_delete) < 100:
                        break
                settings["last_run"] = time.time()
                self._save_settings(chat_id, settings)
            except (ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError):
                logger.warning(f"No access to chat {chat_id}, removing from config.")
                del self.chats[chat_id_str]
                self.db.set(__name__, "chats", self.chats)
            except Exception as e:
                logger.exception(self.strings("loop_error").format(chat_id, e))

    @loader.command(
        ru_doc="Настроить авто-удаление своих сообщений в этом чате.",
        en_doc="Configure auto-deletion of your messages in this chat.",
    )
    async def deleteme(self, message: Message):
        """Configure self-destruct for this chat."""
        await self._show_main_menu(message)

    @loader.command(
        ru_doc="Тихо удалить все свои сообщения в этом чате.",
        en_doc="Silently delete all your messages in this chat.",
    )
    async def destme(self, message: Message):
        """Silently delete all your messages in this chat."""
        chat_id = utils.get_chat_id(message)
        command_id = message.id
        try:
            try:
                await message.delete()
            except Exception:
                pass
            ids_to_delete = []
            async for msg in self.client.iter_messages(chat_id):
                if msg.id == command_id or not self._is_destme_target(msg, chat_id):
                    continue
                ids_to_delete.append(msg.id)
                if len(ids_to_delete) >= 100:
                    await self.client.delete_messages(chat_id, ids_to_delete)
                    await asyncio.sleep(5)
                    ids_to_delete = []
            if ids_to_delete:
                await self.client.delete_messages(chat_id, ids_to_delete)
        except (ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError):
            logger.warning(f"No access to chat {chat_id} for destme.")
        except Exception as e:
            logger.exception(e)

    async def _show_main_menu(self, target, chat_id: int = None, request_interval: bool = False):
        if chat_id is None:
            chat_id = utils.get_chat_id(target)
        chat = await self.client.get_entity(chat_id)
        chat_title = getattr(chat, "title", f"ID {chat_id}")
        settings = self._get_settings(chat_id)
        text = self._build_settings_text(chat_title, settings, premium=True)
        markup = [
            [
                self._build_toggle_button(settings, chat_id),
                {
                    "text": f"✏️ {self.strings('btn_set_type')}",
                    "callback": self._set_type_menu,
                    "args": (chat_id,),
                    "emoji_id": "5879841310902324730",
                },
            ],
            [self._build_interval_button(chat_id, request_interval)],
        ]
        if request_interval:
            markup.append(
                [
                    {
                        "text": f"⬅️ {self.strings('btn_back')}",
                        "callback": self._show_main_menu,
                        "args": (chat_id, False),
                        "style": "danger",
                        "emoji_id": "5985346521103604145",
                    }
                ]
            )
        else:
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

    async def _toggle_enabled(self, call: InlineCall, chat_id: int):
        settings = self._get_settings(chat_id)
        settings["enabled"] = not settings["enabled"]
        settings["last_run"] = 0
        self._save_settings(chat_id, settings)
        try:
            await call.answer(self.strings("toggled"))
        except Exception:
            pass
        await self._show_main_menu(call, chat_id)

    async def _set_type_menu(self, call: InlineCall, chat_id: int):
        type_icon = self._premium_emoji("5879841310902324730", "✏️")
        await call.edit(
            f"{type_icon} {self.strings('type_menu_title')}",
            reply_markup=[
                [
                    {
                        "text": f"📄 {self.strings('btn_all')}",
                        "callback": self._set_type,
                        "args": (chat_id, "all"),
                        "emoji_id": "5877495434124988415",
                    }
                ],
                [
                    {
                        "text": f"🖼 {self.strings('btn_media')}",
                        "callback": self._set_type,
                        "args": (chat_id, "media"),
                        "emoji_id": "5258254475386167466",
                    }
                ],
                [
                    {
                        "text": f"⬅️ {self.strings('btn_back')}",
                        "callback": self._show_main_menu,
                        "args": (chat_id,),
                        "style": "danger",
                        "emoji_id": "5985346521103604145",
                    }
                ],
            ],
        )

    async def _set_type(self, call: InlineCall, chat_id: int, new_type: str):
        settings = self._get_settings(chat_id)
        settings["type"] = new_type
        self._save_settings(chat_id, settings)
        try:
            await call.answer(self.strings("type_saved"))
        except Exception:
            pass
        await self._show_main_menu(call, chat_id)

    async def _save_interval(self, call: InlineCall, query: str, chat_id: int):
        try:
            interval = int(query)
            if interval <= 0:
                raise ValueError
        except ValueError:
            try:
                await call.answer(self.strings("invalid_interval"), show_alert=True)
            except Exception:
                pass
            return
        settings = self._get_settings(chat_id)
        settings["interval"] = interval
        settings["last_run"] = 0
        self._save_settings(chat_id, settings)
        try:
            await call.answer(self.strings("interval_saved"))
        except Exception:
            pass
        await self._show_main_menu(call, chat_id)
