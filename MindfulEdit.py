__version__ = (2, 0, 0)
# meta developer: @mofkomodules
# Name: MindfulEdit
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161046_829.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161046_829.png
# meta fhsdesc: random, edits, mofko, эдиты, рандом
# meta tags: random, edits, mofko, эдиты, рандом
# diff: Фиксы под 2.1.0
# scope: heroku_min 2.1.0

import asyncio
import contextlib
import logging
import random
import time
from collections import defaultdict

from herokutl.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall


logger = logging.getLogger(__name__)


@loader.tds
class MindfulEdit(loader.Module):
    """Random edits with source configuration."""

    strings = {
        "name": "MindfulEdit",
        "sending": '<tg-emoji emoji-id="5210956306952758910">👀</tg-emoji> Looking for edit',
        "error": '<tg-emoji emoji-id="5420323339723881652">⚠️</tg-emoji> An error occurred, check logs',
        "no_videos": '<tg-emoji emoji-id="5400086192559503700">😳</tg-emoji> No videos found in channel',
        "inline_question": "🔄 Send another edit?",
        "btn_retry": "🔄 Another edit",
        "btn_close": "❌ Close",
        "cfg_show_inline_desc": "Show inline message with buttons after sending an edit",
        "cfg_channels_desc": "Channels used as edit sources (up to 20).",
    }

    strings_ru = {
        "sending": '<tg-emoji emoji-id="5210956306952758910">👀</tg-emoji> Ищу эдит',
        "error": '<tg-emoji emoji-id="5420323339723881652">⚠️</tg-emoji> Ошибка, проверьте логи',
        "no_videos": '<tg-emoji emoji-id="5400086192559503700">😳</tg-emoji> В канале не найдено видео',
        "inline_question": "🔄 Отправить другой эдит?",
        "btn_retry": "🔄 Другой эдит",
        "btn_close": "❌ Закрыть",
        "cfg_show_inline_desc": "Показывать инлайн-сообщение с кнопками после отправки эдита",
        "cfg_channels_desc": "Каналы-источники эдитов (до 20).",
        "_cls_doc": "Рандомные эдиты с настройкой источника.",
    }

    def __init__(self):
        self._main_channel = "https://t.me/MindfulEdit"
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "additional_channels",
                [self._main_channel],
                lambda: self.strings("cfg_channels_desc"),
                validator=loader.validators.Series(
                    validator=loader.validators.Union(
                        loader.validators.Link(),
                        loader.validators.RegExp(r"@\w+"),
                    ),
                    max_len=20,
                ),
            ),
            loader.ConfigValue(
                "show_inline_after_send",
                True,
                lambda: self.strings("cfg_show_inline_desc"),
                validator=loader.validators.Boolean(),
            ),
        )
        self._cache_ttl = 3600
        self._messages_limit = 1000
        self._recent_video_limit = 20
        self._videos_cache = {}
        self._cache_time = {}
        self._cache_locks = defaultdict(asyncio.Lock)
        self._recent_video_ids = {}

    def config_complete(self):
        if self.get("source_list_v2_migrated", False):
            return
        channels = list(self.config["additional_channels"] or [])
        main_key = self._normalise_channel(self._main_channel).casefold()
        if main_key not in {
            self._normalise_channel(channel).casefold()
            for channel in channels
        }:
            self.config["additional_channels"] = [self._main_channel, *channels][:20]
        self.set("source_list_v2_migrated", True)

    async def on_unload(self):
        self._videos_cache.clear()
        self._cache_time.clear()
        self._cache_locks.clear()
        self._recent_video_ids.clear()

    @staticmethod
    def _normalise_channel(value) -> str:
        channel = str(value or "").strip().rstrip("/")
        if channel.startswith("@"):
            return f"https://t.me/{channel[1:]}"
        return channel

    def _get_all_channels(self) -> list[str]:
        result = []
        seen = set()
        raw_channels = list(self.config["additional_channels"] or [])[:20]
        for raw_channel in raw_channels:
            channel = self._normalise_channel(raw_channel)
            key = channel.casefold()
            if channel and key not in seen:
                seen.add(key)
                result.append(channel)
        return result

    @staticmethod
    def _is_video_message(message: Message) -> bool:
        if not getattr(message, "media", None):
            return False
        if getattr(message, "video", None):
            return True
        document = getattr(getattr(message, "media", None), "document", None)
        mime_type = getattr(document, "mime_type", "") or getattr(
            getattr(message, "file", None), "mime_type", ""
        )
        return str(mime_type).lower().startswith("video/")

    def _cache_is_fresh(self, channel: str, current_time: float) -> bool:
        return (
            channel in self._videos_cache
            and current_time - self._cache_time.get(channel, 0) < self._cache_ttl
        )

    async def _get_videos(self, channel: str) -> tuple[list[Message], bool]:
        current_time = time.time()
        if self._cache_is_fresh(channel, current_time):
            return self._videos_cache[channel], False

        async with self._cache_locks[channel]:
            current_time = time.time()
            if self._cache_is_fresh(channel, current_time):
                return self._videos_cache[channel], False
            try:
                messages = await self.client.get_messages(
                    channel,
                    limit=self._messages_limit,
                )
                videos = [
                    item for item in messages or [] if self._is_video_message(item)
                ]
                self._videos_cache[channel] = videos
                self._cache_time[channel] = current_time
                return videos, False
            except Exception:
                logger.exception("Could not load videos from %s", channel)
                cached = self._videos_cache.get(channel, [])
                return cached, not bool(cached)

    def _pick_random_video(self, videos: list[Message], channel: str) -> Message:
        recent_ids = self._recent_video_ids.setdefault(channel, [])
        available_videos = [
            video
            for video in videos
            if getattr(video, "id", None) not in recent_ids
        ]
        selected_video = random.choice(available_videos or videos)
        selected_id = getattr(selected_video, "id", None)
        if selected_id is not None:
            recent_ids.append(selected_id)
            del recent_ids[:-self._recent_video_limit]
        return selected_video

    async def _edit_status(self, status_message, text: str, chat_id: int):
        if status_message is not None:
            with contextlib.suppress(Exception):
                await status_message.edit(text)
                return
        with contextlib.suppress(Exception):
            await self.client.send_message(chat_id, text)

    async def _delete_status(self, status_message):
        if status_message is not None:
            with contextlib.suppress(Exception):
                await status_message.delete()

    async def _close_callback(self, call: InlineCall):
        with contextlib.suppress(Exception):
            await call.delete()

    async def _retry_callback(
        self,
        call: InlineCall,
        chat_id: int,
        reply_to_msg_id: int | None = None,
    ):
        with contextlib.suppress(Exception):
            await call.answer()
        await self._close_callback(call)
        await self._send_random_edit_to_chat(chat_id, reply_to_msg_id)

    async def _show_retry_form(self, chat_id: int, reply_to_msg_id: int | None):
        try:
            await self.inline.form(
                text=self.strings("inline_question"),
                message=chat_id,
                reply_markup=[
                    [
                        {
                            "text": self.strings("btn_retry"),
                            "callback": self._retry_callback,
                            "args": (chat_id, reply_to_msg_id),
                            "style": "success",
                        },
                        {
                            "text": self.strings("btn_close"),
                            "callback": self._close_callback,
                            "style": "danger",
                        },
                    ]
                ],
                force_me=True,
                silent=True,
            )
        except Exception:
            logger.exception("Could not show MindfulEdit retry form")

    async def _send_random_edit_to_chat(
        self,
        chat_id: int,
        reply_to_msg_id: int | None = None,
    ) -> bool:
        status_message = None
        try:
            status_message = await self.client.send_message(
                chat_id,
                self.strings("sending"),
            )
            channels = self._get_all_channels()
            random.shuffle(channels)
            selected_video = None
            source_failed = False

            for channel in channels:
                videos, failed = await self._get_videos(channel)
                source_failed = source_failed or failed
                if videos:
                    selected_video = self._pick_random_video(videos, channel)
                    break

            if selected_video is None:
                await self._edit_status(
                    status_message,
                    self.strings("error" if source_failed else "no_videos"),
                    chat_id,
                )
                return False

            await self.client.send_message(
                chat_id,
                message=selected_video,
                reply_to=reply_to_msg_id,
            )
            await self._delete_status(status_message)

            if self.config["show_inline_after_send"]:
                await self._show_retry_form(chat_id, reply_to_msg_id)
            return True
        except Exception:
            logger.exception("Could not send a random MindfulEdit video")
            await self._edit_status(status_message, self.strings("error"), chat_id)
            return False

    @loader.command(
        en_doc="Send random edit",
        ru_doc="Отправить рандомный эдит",
    )
    async def redit(self, message: Message):
        await self._send_random_edit_to_chat(
            message.chat_id,
            getattr(message, "reply_to_msg_id", None),
        )
