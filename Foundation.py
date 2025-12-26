__version__ = (1, 1, 0)
# meta developer: @mofkomodules & @Haloperidol_Pills
# name: Foundation
# description: Sends NSFW media from foundation

import random
import logging
import asyncio
import time
from herokutl.types import Message
from .. import loader, utils
from telethon.errors import FloodWaitError

logger = logging.getLogger(__name__)

FOUNDATION_LINK = "https://t.me/+ZfmKdDrEMCA1NWEy"

@loader.tds
class Foundation(loader.Module):
    """Sends NSFW media from foundation"""
    
    strings = {
        "name": "Foundation",
        "sending": "<emoji document_id=6012681561286122335>🤤</emoji> Searching...",
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Something went wrong, check logs",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> You need to join the channel first: https://t.me/+ZfmKdDrEMCA1NWEy",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> No media found in channel",
        "no_messages": "<emoji document_id=6012681561286122335>🤤</emoji> No messages found in channel",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> No videos found in channel",
    }

    strings_ru = {
        "sending": "<emoji document_id=6012681561286122335>🤤</emoji> Ищем...",
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Чот не то, чекай логи",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Нужно вступить в канал, внимательно читай при подаче заявки: https://t.me/+ZfmKdDrEMCA1NWEy",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено медиа в канале",
        "no_messages": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено сообщений в канале",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено видео в канале",
    }

    def __init__(self):
        self._media_cache = {}
        self._video_cache = {}
        self._cache_time = {}
        self.entity = None
        self._last_entity_check = 0
        self.entity_check_interval = 300
        self.cache_ttl = 1200  # 20 минут вроде

    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        await self._load_entity()

    async def _load_entity(self):
        """Загружает entity канала с кешированием"""
        current_time = time.time()
        
        if (self.entity and 
            current_time - self._last_entity_check < self.entity_check_interval):
            return True
        
        try:
            self.entity = await self.client.get_entity(FOUNDATION_LINK)
            self._last_entity_check = current_time
            logger.info(f"Entity loaded: {self.entity.id}")
            return True
        except Exception as e:
            logger.warning(f"Could not load foundation entity: {e}")
            self.entity = None
            return False

    async def _get_cached_media(self, media_type="any"):
        """Получает медиа из кеша с обработкой FloodWait"""
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
            messages = await self.client.get_messages(self.entity, limit=1500)
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
        logger.info(f"Cache updated for {media_type}: {len(self._media_cache.get('any') or self._video_cache.get('video'))} items")
        
        return self._media_cache.get("any") if media_type == "any" else self._video_cache.get("video")

    async def _send_media(self, message: Message, media_type: str = "any"):
        try:
            if not await self._load_entity():
                return await utils.answer(message, self.strings["not_joined"])
            
            send = await utils.answer(message, self.strings["sending"])
            
            media_list = await self._get_cached_media(media_type)
            
            if media_list is None:
                await utils.answer(send, self.strings["not_joined"])
                return
            
            if not media_list:
                if media_type == "any":
                    await utils.answer(send, self.strings["no_media"])
                else:
                    await utils.answer(send, self.strings["no_videos"])
                return
            
            random_message = random.choice(media_list)
            
            await self.client.send_message(
                message.peer_id,
                message=random_message,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
            
            await asyncio.sleep(0.2)
            try:
                await send.delete()
            except Exception as e:
                logger.warning(f"Could not delete status message: {e}")
            
        except Exception as e:
            logger.error(f"Foundation error: {e}")
            await utils.answer(message, self.strings["error"])

    @loader.command(
        en_doc="Send NSFW media from Foundation",
        ru_doc="Отправить NSFW медиа с Фонда",
    )
    async def fond(self, message: Message):
        """Отправить NSFW медиа с Фонда"""
        await self._send_media(message, "any")

    @loader.command(
        en_doc="Send NSFW video from Foundation",
        ru_doc="Отправить NSFW видео с Фонда",
    )
    async def vfond(self, message: Message):
        """Отправить NSFW видео с Фонда"""
        await self._send_media(message, "video")
