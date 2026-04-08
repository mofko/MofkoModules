# meta developer: @mofkomodules
# name: Bredik
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161046_829.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161046_829.png
# meta fhsdesc: fun, trash, random, funny, бред

__version__ = (1, 2, 0)

import logging
import random
import time

from telethon.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class BredMod(loader.Module):
    """Send a random absurd text."""

    strings = {
        "name": "Bredik",
        "no_messages": "Nothing suitable was found in <code>{}</code>.",
        "load_error": "Could not load texts from the source channel. Check logs.",
        "inline_title": "Random bred",
        "inline_description": "Send a random absurd text",
        "inline_empty_title": "No texts found",
        "inline_empty_description": "There are no suitable text posts in the source channel",
        "inline_error_title": "Source unavailable",
        "inline_error_description": "Could not load texts from the source channel",
        "inline_empty_message": "Nothing suitable was found in the source channel.",
        "inline_error_message": "Could not load texts from the source channel. Check logs.",
    }

    strings_ru = {
        "no_messages": "В <code>{}</code> не найдено подходящих текстовых сообщений.",
        "load_error": "Не удалось загрузить тексты из исходного канала. Проверьте логи.",
        "inline_title": "Случайный бред",
        "inline_description": "Отправить случайный бред",
        "inline_empty_title": "Тексты не найдены",
        "inline_empty_description": "В исходном канале нет подходящих текстовых постов",
        "inline_error_title": "Источник недоступен",
        "inline_error_description": "Не удалось загрузить тексты из исходного канала",
        "inline_empty_message": "В исходном канале не найдено подходящих текстов.",
        "inline_error_message": "Не удалось загрузить тексты из исходного канала. Проверьте логи.",
        "_cls_doc": "Отправляет случайный бред.",
    }

    def __init__(self):
        self.source_channel = "https://t.me/neuralmachine"
        self.cache_ttl = 3600
        self.messages_limit = 600
        self._messages_cache = None
        self._cache_time = 0.0
        self._last_error = False
        self._recent_texts = []
        self._recent_texts_limit = 20

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

    async def on_unload(self):
        self._messages_cache = None
        self._cache_time = 0.0
        self._last_error = False
        self._recent_texts.clear()

    def _get_source_channel(self) -> str:
        return self.source_channel.strip()

    def _normalize_text(self, item) -> str | None:
        text = getattr(item, "raw_text", None) or getattr(item, "text", None)
        if not text:
            return None
        text = text.strip()
        return text or None

    def _inline_preview(self, text: str) -> str:
        preview = " ".join(text.split())
        return preview[:100] + ("..." if len(preview) > 100 else "")

    async def _get_messages(self) -> list[str]:
        current_time = time.time()
        if (
            self._messages_cache is not None
            and self.cache_ttl >= 0
            and current_time - self._cache_time < self.cache_ttl
        ):
            return self._messages_cache

        self._last_error = False

        try:
            messages = await self.client.get_messages(
                self._get_source_channel(),
                limit=self.messages_limit,
            )
            filtered_messages = []

            for item in messages or []:
                if getattr(item, "media", None):
                    continue

                text = self._normalize_text(item)
                if not text:
                    continue

                filtered_messages.append(text)

            self._messages_cache = filtered_messages
            self._cache_time = current_time
            return filtered_messages
        except Exception as e:
            self._last_error = True
            logger.exception(e)
            if self._messages_cache is not None:
                return self._messages_cache
            return []

    async def _get_random_text(self) -> str | None:
        messages = await self._get_messages()
        if not messages:
            return None
        available_messages = [
            item for item in messages
            if item not in self._recent_texts
        ]
        selected_text = random.choice(available_messages or messages)
        self._recent_texts.append(selected_text)
        if len(self._recent_texts) > self._recent_texts_limit:
            del self._recent_texts[:-self._recent_texts_limit]
        return selected_text

    def _get_unavailable_message(self) -> str:
        if self._last_error:
            return self.strings("load_error")
        return self.strings("no_messages").format(
            utils.escape_html(self._get_source_channel())
        )

    def _build_inline_result(self, text: str) -> dict:
        return {
            "title": self.strings("inline_title"),
            "description": self._inline_preview(text) or self.strings("inline_description"),
            "message": utils.escape_html(text),
        }

    def _build_inline_fallback(self) -> dict:
        if self._last_error:
            return {
                "title": self.strings("inline_error_title"),
                "description": self.strings("inline_error_description"),
                "message": self.strings("inline_error_message"),
            }

        return {
            "title": self.strings("inline_empty_title"),
            "description": self.strings("inline_empty_description"),
            "message": self.strings("inline_empty_message"),
        }

    @loader.command(ru_doc=" - отправить случайный бред", alias="бред")
    async def bred(self, message: Message):
        """Send a random absurd text."""
        try:
            text = await self._get_random_text()
            if not text:
                return await utils.answer(message, self._get_unavailable_message())

            await self.client.send_message(
                message.peer_id,
                text,
                reply_to=getattr(message, "reply_to_msg_id", None),
            )

            try:
                await message.delete()
            except Exception:
                pass
        except Exception as e:
            logger.exception(e)
            await utils.answer(message, self.strings("load_error"))

    @loader.inline_handler(ru_doc="Отправить случайный бред")
    async def bred_inline_handler(self, query):
        """Send a random absurd text inline."""
        try:
            text = await self._get_random_text()
            if not text:
                return self._build_inline_fallback()
            return self._build_inline_result(text)
        except Exception as e:
            logger.exception(e)
            return self._build_inline_fallback()
