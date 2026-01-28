# meta developer: @mofkomodules
# meta name: SelfDestruct
# meta desc: Периодически удаляет соо в выбранной чате
# meta banner: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260128_232806_896.jpg
# meta pic: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260128_232806_896.jpg
# meta fhsdesk: cleaner, deleter, auto, tool, privacy, mofko
__version__ = (1, 1, 1)

import asyncio
import time
import logging
from herokutl.types import Message
from .. import loader, utils
from ..inline.types import InlineCall
from telethon.errors import ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError

logger = logging.getLogger(__name__)

@loader.tds
class SelfDestructMod(loader.Module):
    """Periodically deletes your messages in specified chats."""

    strings = {
        "name": "SelfDestruct",
        "_cls_doc": "Периодически удаляет ваши сообщения в указанных чатах.",
        "config_title": "⚙️ <b>Настройки самоуничтожения</b>\n<i>Чат: {}</i>",
        "enabled_status": "\n✅ Включено",
        "disabled_status": "\n❌ Выключено",
        "type_status": "\n🧹 Тип: <code>{}</code>",
        "interval_status": "\n⏱ Интервал: <code>{} мин.</code>",
        "not_configured": "\n<i>Еще не настроено.</i>",
        "btn_toggle": "🚀 Вкл/Выкл",
        "btn_set_type": "🧹 Задать тип",
        "btn_set_interval": "⏱ Задать интервал",
        "btn_close": "❌ Закрыть",
        "btn_back": "🔙 Назад",
        "btn_all": "💥 Все сообщения",
        "btn_media": "🏞 Только медиа",
        "type_menu_title": "🧹 <b>Выберите тип удаления:</b>",
        "interval_input": "✍️ Введите интервал в минутах (например, 5)",
        "interval_saved": "✅ Интервал сохранен!",
        "type_saved": "✅ Тип сохранен!",
        "toggled": "✅ Переключено!",
        "invalid_interval": "🚫 Неверное число. Должно быть > 0.",
        "loop_error": "Ошибка в цикле SelfDestruct в чате {}: {}",
    }

    strings_en = {
        "config_title": "⚙️ <b>Self-Destruct Configuration</b>\n<i>Chat: {}</i>",
        "enabled_status": "\n✅ Enabled",
        "disabled_status": "\n❌ Disabled",
        "type_status": "\n🧹 Type: <code>{}</code>",
        "interval_status": "\n⏱ Interval: <code>{} minutes</code>",
        "not_configured": "\n<i>Not configured yet.</i>",
        "btn_toggle": "🚀 Toggle On/Off",
        "btn_set_type": "🧹 Set Type",
        "btn_set_interval": "⏱ Set Interval",
        "btn_close": "❌ Close",
        "btn_back": "🔙 Back",
        "btn_all": "💥 All messages",
        "btn_media": "🏞 Media only",
        "type_menu_title": "🧹 <b>Select deletion type:</b>",
        "interval_input": "✍️ Enter interval in minutes (e.g., 5)",
        "interval_saved": "✅ Interval saved!",
        "type_saved": "✅ Type saved!",
        "toggled": "✅ Toggled!",
        "invalid_interval": "🚫 Invalid number. Must be > 0.",
        "loop_error": "SelfDestruct loop error in chat {}: {}",
        "_cls_doc": "Periodically deletes your messages in specified chats.",
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

    @loader.loop(interval=60, autostart=True) # <<< ИСПРАВЛЕНО: Интервал 60 секунд, а не 1
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

            logger.debug(f"Running SelfDestruct for chat {chat_id}")
            
            try:
                # <<< ИСПРАВЛЕНО: Логика удаления в цикле, чтобы удалить все, а не 100
                while True:
                    ids_to_delete = []
                    async for msg in self.client.iter_messages(chat_id, from_user="me"):
                        is_media = msg.media and not msg.web_preview
                        
                        if settings.get("type") == "media" and not is_media:
                            continue
                        
                        ids_to_delete.append(msg.id)
                        if len(ids_to_delete) >= 100:
                            break
                    
                    if ids_to_delete:
                        await self.client.delete_messages(chat_id, ids_to_delete)
                        await asyncio.sleep(1) # Небольшая задержка между пачками
                    
                    if len(ids_to_delete) < 100:
                        break # Сообщений меньше 100, значит, все удалили

                settings["last_run"] = time.time()
                self._save_settings(chat_id, settings)

            except (ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError):
                logger.warning(f"No access to chat {chat_id}, removing from config.")
                del self.chats[chat_id_str]
                self.db.set(__name__, "chats", self.chats)
            except Exception as e:
                logger.error(self.strings["loop_error"].format(chat_id, e))

    @loader.command(
        ru_doc="Настроить авто-удаление своих сообщений в этом чате.",
        en_doc="Configure auto-deletion of your messages in this chat."
    )
    async def deletemecmd(self, message: Message):
        """Configure self-destruct for this chat."""
        await self._show_main_menu(message)

    async def _show_main_menu(self, target: [Message, InlineCall], chat_id: int = None, request_interval: bool = False):
        if chat_id is None:
            chat_id = utils.get_chat_id(target)

        chat = await self.client.get_entity(chat_id)
        chat_title = getattr(chat, "title", f"ID {chat_id}")

        settings = self._get_settings(chat_id)
        
        text = self.strings["config_title"].format(utils.escape_html(chat_title))
        if settings["last_run"] == 0 and not settings["enabled"]:
            text += self.strings["not_configured"]
        else:
            text += self.strings["enabled_status"] if settings["enabled"] else self.strings["disabled_status"]
            text += self.strings["type_status"].format(settings["type"])
            text += self.strings["interval_status"].format(settings["interval"])
        
        interval_button = {
            "text": self.strings["btn_set_interval"],
            "callback": self._show_main_menu,
            "args": (chat_id, True), # <<< ИСПРАВЛЕНО: Просто перерисовываем меню с запросом ввода
        }

        if request_interval:
            interval_button = {
                "text": self.strings["btn_set_interval"],
                "input": self.strings["interval_input"],
                "handler": self._save_interval,
                "args": (chat_id,),
            }

        markup = [
            [
                {"text": self.strings["btn_toggle"], "callback": self._toggle_enabled, "args": (chat_id,)},
                {"text": self.strings["btn_set_type"], "callback": self._set_type_menu, "args": (chat_id,)},
            ],
            [interval_button],
            [{"text": self.strings["btn_back"] if request_interval else self.strings["btn_close"], 
              "callback": self._show_main_menu, "args": (chat_id, False)} if request_interval else {"action": "close"}],
        ]

        if isinstance(target, Message):
            await self.inline.form(text=text, message=target, reply_markup=markup)
        else:
            await target.edit(text=text, reply_markup=markup)

    async def _toggle_enabled(self, call: InlineCall, chat_id: int):
        settings = self._get_settings(chat_id)
        settings["enabled"] = not settings["enabled"]
        settings["last_run"] = time.time() if settings["enabled"] else 0
        self._save_settings(chat_id, settings)
        await call.answer(self.strings["toggled"])
        await self._show_main_menu(call, chat_id)

    async def _set_type_menu(self, call: InlineCall, chat_id: int):
        await call.edit(
            self.strings["type_menu_title"],
            reply_markup=[
                [{"text": self.strings["btn_all"], "callback": self._set_type, "args": (chat_id, "all")}],
                [{"text": self.strings["btn_media"], "callback": self._set_type, "args": (chat_id, "media")}],
                [{"text": self.strings["btn_back"], "callback": self._show_main_menu, "args": (chat_id,)}],
            ],
        )

    async def _set_type(self, call: InlineCall, chat_id: int, new_type: str):
        settings = self._get_settings(chat_id)
        settings["type"] = new_type
        self._save_settings(chat_id, settings)
        await call.answer(self.strings["type_saved"])
        await self._show_main_menu(call, chat_id)

    async def _save_interval(self, call: InlineCall, query: str, chat_id: int):
        if not query.isdigit() or int(query) <= 0:
            await call.answer(self.strings["invalid_interval"], show_alert=True)
            return

        settings = self._get_settings(chat_id)
        settings["interval"] = int(query)
        settings["last_run"] = time.time() # Reset timer on interval change
        self._save_settings(chat_id, settings)
        
        await call.answer(self.strings["interval_saved"])
        await self._show_main_menu(call, chat_id)
