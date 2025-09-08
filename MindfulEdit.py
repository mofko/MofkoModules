__version__ = (1, 0, 0)
# meta developer: @mofkomodules 
# name: mindfuledit



from herokutl.types import Message
from .. import loader, utils
import random
import time
import logging

logger=logging.getLogger("name")

@loader.tds

class MindfulEdit(loader.Module):
    """Модуль для отправки рандомного эдита."""
    
    strings = {
    "name": "MindfulEdit",
    "sending": "🔍 Looking for edit",
    "error": "⚠️ An error accured, check logs",
    }
    
    strings_ru = {
    "sending": "🔍 Ищу эдит",
    "error": "⚠️ Ошибка, проверьте логи",
    }
    
    async def client_ready(self, client, db):
        self.client = client


    @loader.command(
        en_doc="Send random edit",
    ru_doc="Отправить рандомный эдит",
    ) 
    async def edit(self, message):
        """Отправить рандомный эдит"""
        channel = "https://t.me/MindfulEdit"
        choose_video_message = await utils.answer(message, self.strings["sending"])

        try:
            videos = await self.client.get_messages(                  channel,
limit=2500) 
        except Exception:
            return await logger.error(Exception)
    
        mes = random.choice(videos)
        await message.client.send_message(
        message.peer_id,
        message=mes,
        reply_to=getattr(message, "reply_to_msg_id", None)
    )
        time.sleep(0.6)
        await self.client.delete_messages(message.chat_id, choose_video_message)










