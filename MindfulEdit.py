__version__ = (1, 4, 0)
# meta developer: @mofkomodules
# Name: MindfulEdit
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_101.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_101.png
# meta fhsdesc: random, edits, fun, мофко, эдиты, рандом

from herokutl.types import Message
from .. import loader, utils
from ..inline.types import InlineCall
import random
import asyncio
import logging
import time
from typing import List

logger = logging.getLogger(__name__)

@loader.tds
class MindfulEdit(loader.Module):
    strings = {
        "name": "MindfulEdit",
        "sending": "<emoji document_id=5210956306952758910>👀</emoji> Looking for edit",
        "error": "<emoji document_id=5420323339723881652>⚠️</emoji> An error occurred, check logs",
        "no_videos": "<emoji document_id=5400086192559503700>😳</emoji> No videos found in channel",
        "inline_question": "🔄 Send another edit?",
        "btn_retry": "🔄 Another edit",
        "btn_close": "❌ Close",
        "cfg_show_inline_desc": "Show inline message with buttons after sending an edit",
        "cfg_channels_desc": "Specify a channel to add to the edit selection via @ (limit 19 channels)",
    }
    
    strings_ru = {
        "sending": "<emoji document_id=5210956306952758910>👀</emoji> Ищу эдит",
        "error": "<emoji document_id=5420323339723881652>⚠️</emoji> Ошибка, проверьте логи",
        "no_videos": "<emoji document_id=5400086192559503700>😳</emoji> В канале не найдено видео",
        "inline_question": "🔄 Отправить другой эдит?",
        "btn_retry": "🔄 Другой эдит",
        "btn_close": "❌ Закрыть",
        "cfg_show_inline_desc": "Показывать инлайн-сообщение с кнопками после отправки эдита",
        "cfg_channels_desc": "Укажите канал, который хотите добавить в подборку эдитов через @ (лимит 19 каналов)",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "additional_channels",
                [],
                lambda: self.strings["cfg_channels_desc"],
                validator=loader.validators.Series(
                    validator=loader.validators.Union(
                        loader.validators.Link(),
                        loader.validators.RegExp(r"@\w+")
                    )
                )
            ),
            loader.ConfigValue(
                "show_inline_after_send",
                True,
                lambda: self.strings["cfg_show_inline_desc"],
                validator=loader.validators.Boolean()
            )
        )
        self._videos_cache = {}
        self._cache_time = {}
        self._recent_video_ids = {}
        self._recent_video_limit = 20
        self.main_channel = "https://t.me/MindfulEdit"
        self.cache_ttl = 3600
        self.messages_limit = 1000

    async def client_ready(self, client, db):
        self.client = client
        self._db = db

    async def on_unload(self):
        self._videos_cache.clear()
        self._cache_time.clear()
        self._recent_video_ids.clear()

    def _get_all_channels(self) -> List[str]:
        channels = [self.main_channel]
        if self.config["additional_channels"]:
            additional_channels = []
            for channel in self.config["additional_channels"]:
                if channel.startswith("@"):
                    additional_channels.append(f"https://t.me/{channel[1:]}")
                else:
                    additional_channels.append(channel)
            channels.extend(additional_channels)
        return channels

    async def _get_videos(self, channel: str) -> List[Message]:
        current_time = time.time()
        if (channel in self._videos_cache and 
            channel in self._cache_time and
            current_time - self._cache_time[channel] < self.cache_ttl):
            return self._videos_cache[channel]
        
        try:
            videos = await self.client.get_messages(
                channel,
                limit=self.messages_limit
            )
            videos_with_media = [msg for msg in videos if msg.media]
            if not videos_with_media:
                logger.warning(f"No media found in channel {channel}")
                return []
            self._videos_cache[channel] = videos_with_media
            self._cache_time[channel] = current_time
            logger.info(f"Cache updated for {channel} with {len(videos_with_media)} videos")
            return videos_with_media
        except Exception as e:
            logger.error(f"Error loading videos from {channel}: {e}")
            return self._videos_cache.get(channel, [])

    async def _close_callback(self, call: InlineCall):
        try:
            await call.delete()
        except Exception as e:
            logger.error(f"Error deleting inline message: {e}")

    async def _retry_callback(self, call: InlineCall, chat_id: int):
        try:
            await call.delete()
        except Exception:
            pass
        try:
            await self._send_random_edit_to_chat(chat_id)
        except Exception as e:
            logger.error(f"Error in retry callback: {e}")

    def _pick_random_video(self, videos: List[Message], channel: str) -> Message:
        recent_ids = self._recent_video_ids.setdefault(channel, [])
        available_videos = [
            video for video in videos
            if getattr(video, "id", None) not in recent_ids
        ]
        selected_video = random.choice(available_videos or videos)
        selected_id = getattr(selected_video, "id", None)
        if selected_id is not None:
            recent_ids.append(selected_id)
            if len(recent_ids) > self._recent_video_limit:
                del recent_ids[:-self._recent_video_limit]
        return selected_video

    async def _send_random_edit_to_chat(self, chat_id: int, reply_to_msg_id: int = None):
        try:
            status_msg = await self.client.send_message(
                chat_id,
                self.strings["sending"]
            )
            
            channels = self._get_all_channels()
            random.shuffle(channels)
            selected_video = None
            
            for channel in channels:
                videos = await self._get_videos(channel)
                if videos:
                    selected_video = self._pick_random_video(videos, channel)
                    break
            
            if not selected_video:
                await status_msg.edit(self.strings["no_videos"])
                return

            try:
                await status_msg.delete()
            except Exception as e:
                logger.warning(f"Could not delete status message: {e}")
            
            await self.client.send_message(
                chat_id,
                message=selected_video,
                reply_to=reply_to_msg_id
            )
            
            if self.config["show_inline_after_send"]:
                await asyncio.sleep(2)
                
                await self.inline.form(
                    text=self.strings["inline_question"],
                    message=status_msg,
                    reply_markup=[
                        [
                            {"text": self.strings["btn_retry"], "callback": self._retry_callback, "args": (chat_id,), "style": "success"},
                            {"text": self.strings["btn_close"], "callback": self._close_callback, "style": "danger"}
                        ]
                    ]
                )
                    
        except Exception as e:
            logger.error(f"Error sending edit to chat: {e}")

    async def _send_random_edit(self, message: Message) -> None:
        await self._send_random_edit_to_chat(
            message.chat_id,
            getattr(message, "reply_to_msg_id", None)
        )

    @loader.command(
        en_doc="Send random edit",
        ru_doc="Отправить рандомный эдит",
        alias="эдит"
    ) 
    async def redit(self, message: Message):
        await self._send_random_edit(message)

