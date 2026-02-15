__version__ = (2, 2, 8)
# meta developer: @mofkomodules
# name: FavoriteMusic
# meta fhsdesc: music, random, favorite, chill, mofko, музыка, хуйня, funny

import random
import logging
import asyncio
import time
import aiohttp
import ssl
from urllib.parse import quote_plus

from herokutl.types import Message
from telethon.errors import FloodWaitError

from .. import loader, utils

logger = logging.getLogger(__name__)

FAVORITE_MUSIC_CHANNEL_LINK = "https://t.me/+l9ewEixIglUzODMy"

@loader.tds
class FavoriteMusicMod(loader.Module):
    """Рандомная прекрасная музыка из секретного канала"""

    strings = {
        "name": "FavoriteMusic",
        "error": "<emoji document_id=5121063440311386962>👎</emoji> Что-то пошло не так, проверьте логи.",
        "not_joined": "<emoji document_id=5407001145740631266>🤐</emoji> Нужно вступить в канал с любимой музыкой: {channel_link}",
        "no_audio": "<emoji document_id=5407001145740631266>🤐</emoji> В канале не найдено аудиозаписей.",
    }

    strings_ru = {
        "_cls_doc": "Рандомная прекрасная музыка из секретного канала",
        "error": "<emoji document_id=5121063440311386962>👎</emoji> Чот не то, чекай логи.",
        "not_joined": "<emoji document_id=5407001145740631266>🤐</emoji> Нужно вступить в канал с любимой музыкой: {channel_link}",
        "no_audio": "<emoji document_id=5407001145740631266>🤐</emoji> В канале не найдено аудиозаписей.",
    }

    def __init__(self):
        self._audio_cache = {}
        self._cache_time = {}
        self.entity = None
        self._last_entity_check = 0
        self.entity_check_interval = 300
        self.cache_ttl = 1200
        
        self.config = loader.ModuleConfig()

    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        await self._load_entity()
        await self._send_fheta_like()
    
    async def _send_fheta_like(self):
        if self.db.get(__name__, "liked_fheta", False): return

        token = self.db.get("FHeta", "token")
        if not token: return

        try:
            uid = getattr(self, "uid", (await self.client.get_me()).id)
            install_link = "dlm https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/FavoriteMusic.py"
            endpoint = f"rate/{uid}/{quote_plus(install_link)}/like"

            _ssl = ssl.create_default_context()
            _ssl.check_hostname = False
            _ssl.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"https://api.fixyres.com/{endpoint}",
                    headers={"Authorization": token},
                    ssl=_ssl,
                    timeout=15
                ) as r:
                    if r.status == 200:
                        self.db.set(__name__, "liked_fheta", True)
        except Exception:
            pass

    async def _load_entity(self):
        current_time = time.time()
        if (self.entity and 
            current_time - self._last_entity_check < self.entity_check_interval):
            return True
        try:
            self.entity = await self.client.get_entity(FAVORITE_MUSIC_CHANNEL_LINK)
            self._last_entity_check = current_time
            return True
        except Exception as e:
            logger.warning(f"Не удалось загрузить сущность канала: {e}")
            self.entity = None
            return False

    async def _get_cached_audio(self):
        current_time = time.time()
        cache_key = "audio"
        
        if (cache_key in self._cache_time and 
            current_time - self._cache_time[cache_key] < self.cache_ttl):
            if cache_key in self._audio_cache:
                return self._audio_cache[cache_key]
        
        if not await self._load_entity():
            return None
        
        try:
            messages = await self.client.get_messages(self.entity, limit=1500)
        except FloodWaitError as e:
            logger.warning(f"FloodWait для get_messages в канале: {e.seconds} секунд")
            await asyncio.sleep(e.seconds)
            return await self._get_cached_audio()
        except ValueError as e:
            if "Could not find the entity" in str(e):
                logger.error(f"Не удалось найти канал: {FAVORITE_MUSIC_CHANNEL_LINK}")
                return None
            logger.exception("Неожиданная ошибка при получении сообщений из канала")
            raise e
        
        if not messages:
            return []
        
        audio_messages = []
        for msg in messages:
            if msg.media and hasattr(msg.media, 'document'):
                attr = getattr(msg.media.document, 'mime_type', '')
                if 'audio' in attr:
                    audio_messages.append(msg)
        
        self._audio_cache[cache_key] = audio_messages
        self._cache_time[cache_key] = current_time
        return self._audio_cache[cache_key]
    
    async def _send_audio_media(self, message: Message, delete_command: bool = False):
        try:
            if not await self._load_entity():
                return await utils.answer(message, self.strings["not_joined"].format(channel_link=FAVORITE_MUSIC_CHANNEL_LINK))
            
            audio_list = await self._get_cached_audio()
            
            if audio_list is None:
                return await utils.answer(message, self.strings["not_joined"].format(channel_link=FAVORITE_MUSIC_CHANNEL_LINK))
            
            if not audio_list:
                return await utils.answer(message, self.strings["no_audio"])
            
            random_message = random.choice(audio_list)
            
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
            logger.error(f"Ошибка в модуле FavoriteMusic: {e}", exc_info=True)
            await utils.answer(message, self.strings["error"])

    @loader.command(
        ru_doc="Отправь музыку для души",
        en_doc="Send music for the soul",
    )
    async def fmusiccmd(self, message: Message):
        """Send music for the soul"""
        await self._send_audio_media(message, delete_command=True)
