__version__ = (1, 0, 2)
# meta developer: @mofkomodules & @Haloperidol_Pills
# name: Foundation
# description: Sends NSFW media from foundation

import random
import logging
import asyncio
from herokutl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

FOUNDATION_LINK = "https://t.me/+s8GoAISy21ZjZWEy"

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
    }

    strings_ru = {
        "sending": "<emoji document_id=6012681561286122335>🤤</emoji> Ищем...",
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Чот не то, чекай логи",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Нужно вступить в канал: https://t.me/+ZfmKdDrEMCA1NWEy",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено медиа в канале",
        "no_messages": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено сообщений в канале",
    }

    async def client_ready(self, client, db):
        self.client = client
        try:
            self.entity = await client.get_entity(FOUNDATION_LINK)
        except Exception as e:
            logger.warning(f"Could not load foundation entity: {e}")
            self.entity = None

    @loader.command(
        en_doc="Send NSFW media from Foundation",
        ru_doc="Отправить NSFW медиа с Фонда",
    )
    async def fond(self, message: Message):
        """Отправить NSFW медиа с Фонда"""
        try:
            if not self.entity:
                return await utils.answer(message, self.strings("not_joined"))
            
            send = await utils.answer(message, self.strings("sending"))
            
            try:
                messages = await self.client.get_messages(self.entity, limit=1500)
                if not messages:
                    return await utils.answer(message, self.strings("no_messages"))
            except ValueError as e:
                if "Could not find the entity" in str(e):
                    return await utils.answer(message, self.strings("not_joined"))
                raise e
            
            media_messages = [msg for msg in messages if msg.media]
            if not media_messages:
                return await utils.answer(message, self.strings("no_media"))
            
            random_message = random.choice(media_messages)
            
            await self.client.send_message(
                message.peer_id,
                message=random_message,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
            
            await asyncio.sleep(0.2)
            await send.delete()
            
        except Exception as e:
            logger.error(f"Foundation error: {e}")
            await utils.answer(message, self.strings("error"))
