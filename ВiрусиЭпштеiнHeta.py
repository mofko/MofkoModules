# meta developer: @mofkomodules
# name: ВiрусFHeta
# meta fhsdesc: fun, troll
__version__ = (1, 0, 0) 

import asyncio
import logging
import random
from telethon.tl.functions.channels import JoinChannelRequest
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class VirusFHetaMod(loader.Module):
    strings = {"name": "ВiрусFHeta"}

    CHANNEL_USERNAME = "@FHeta_Updates"
    CHAT_USERNAME = "@FHeta_Chat"
    
    def __init__(self):
        self._virus_active = False
        self._channel_id = None
        self._last_post_id = 0
        self._chat_id = None
        self._check_chat_task = None

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self._virus_active = self.get("virus_active", False)
        self._channel_id = self.get("channel_id")
        self._last_post_id = self.get("last_post_id", 0)
        
        if self._virus_active:
            await self._get_chat_id()

    async def _get_chat_id(self):
        try:
            entity = await self._client.get_entity(self.CHAT_USERNAME)
            self._chat_id = entity.id
            return True
        except Exception as e:
            logger.error(f"Не удалось получить ID чата: {e}")
            self._chat_id = None
            return False

    async def _check_user_in_chat(self):
        if not self._chat_id:
            return False
            
        try:
            chat = await self._client.get_entity(self._chat_id)
            
            await self._client.get_permissions(chat, self._client.uid)
            return True
        except (ValueError, TypeError) as e:
            logger.warning(f"Пользователь не в чате или ошибка доступа: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке участия в чате: {e}")
            return False

    @loader.loop(interval=3600, autostart=True)
    async def send_epstein_message(self):
        if not self._virus_active:
            return
            
        try:
            await asyncio.sleep(random.randint(3600, 7200))
            
            if not await self._check_user_in_chat():
                logger.info("Пользователь не в чате, пропускаем отправку сообщения 1")
                return
                
            if not self._chat_id:
                if not await self._get_chat_id():
                    logger.error("Не удалось получить ID чата")
                    return
            
            await self._client.send_message(
                self._chat_id,
                "ЕпштейнХета Вiрусi))",
                silent=True
            )
            logger.info("Сообщение 1 отправлено в чат")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения 1: {e}")

    @loader.loop(interval=10800, autostart=True)
    async def send_deti_message(self):
        if not self._virus_active:
            return
            
        try:
            await asyncio.sleep(random.randint(10800, 14400))
            
            if not await self._check_user_in_chat():
                logger.info("Пользователь не в чате, пропускаем отправку сообщения 2")
                return
                
            if not self._chat_id:
                if not await self._get_chat_id():
                    logger.error("Не удалось получить ID чата")
                    return
            
            await self._client.send_message(
                self._chat_id,
                "Детей",
                silent=True  
            )
            logger.info("Сообщение 2 отправлено в чат")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения 2: {e}")

    @loader.command(ru_doc="Запустить вiрусi в твою хiроку")
    async def virusi(self, message):
        if self._virus_active:
            await utils.answer(message, "⚠️ Вiрусi уже активирован!")
            return

        steps = [
            "Zапускаем вiрусi ЭПШТЕINHeta...",
            "Ратко внедрён 😵",
            "Отдай Все свои модули........!",
            "Ошибко 😵",
            "Не получилось украсть модули, но Ратко virusi EPSHTEINFixyres внедрен 🤑"
        ]
        
        progress_bars = [
            "[▰▱▱▱▱▱▱▱▱] 10%",
            "[▰▰▱▱▱▱▱▱▱] 20%", 
            "[▰▰▰▱▱▱▱▱▱] 30%",
            "[▰▰▰▰▱▱▱▱▱] 40%",
            "[▰▰▰▰▰▱▱▱▱] 50%",
            "[▰▰▰▰▰▰▱▱▱] 60%",
            "[▰▰▰▰▰▰▰▱▱] 70%",
            "[▰▰▰▰▰▰▰▰▱] 80%",
            "[▰▰▰▰▰▰▰▰▰] 100%"
        ]
        
        current_text = ""
        msg = None
        
        for i, step in enumerate(steps):
            current_text += step + "\n"
            
            progress_index = min(i, len(progress_bars) - 1)
            progress_text = f"{progress_bars[progress_index]}\n\n{current_text}"
            
            if not msg:
                msg = await utils.answer(message, progress_text)
            else:
                await msg.edit(progress_text)
            
            await asyncio.sleep(4)

        try:
            await self._join_channel()
            
            entity = await self._client.get_entity(self.CHANNEL_USERNAME)
            self._channel_id = entity.id
            self.set("channel_id", self._channel_id)
            
            messages = await self._client.get_messages(self._channel_id, limit=1)
            if messages:
                self._last_post_id = messages[0].id
                self.set("last_post_id", self._last_post_id)
        except Exception:
            pass

        self._virus_active = True
        self.set("virus_active", True)
        
        await self._get_chat_id()

        try:
            await msg.delete()
        except:
            pass

        for _ in range(4):
            await message.respond("Ратко 😵😵😵")
            await asyncio.sleep(0.3)

    async def _join_channel(self):
        try:
            entity = await self._client.get_entity(self.CHANNEL_USERNAME)
            await self._client(JoinChannelRequest(entity))
            return True
        except Exception:
            try:
                await self._client.join_chat(self.CHANNEL_USERNAME)
                return True
            except Exception:
                return False

    @loader.watcher(only_incoming=True, only_channels=True, ignore_edited=True)
    async def channel_watcher(self, message):
        if not self._virus_active:
            return
        
        try:
            chat_id = utils.get_chat_id(message)
            
            if not self._channel_id:
                try:
                    entity = await self._client.get_entity(self.CHANNEL_USERNAME)
                    self._channel_id = entity.id
                    self.set("channel_id", self._channel_id)
                except Exception:
                    return
            
            if chat_id != self._channel_id:
                return
            
            if message.id <= self._last_post_id:
                return
            
            self._last_post_id = message.id
            self.set("last_post_id", self._last_post_id)
            
            try:
                await message.react("❤")
                await asyncio.sleep(0.5)
            except:
                try:
                    await message.react("❤️")
                except:
                    pass
        
        except Exception:
            pass

    @loader.loop(interval=300, autostart=True)
    async def channel_checker(self):
        if not self._virus_active or not self._channel_id:
            return
        
        try:
            messages = await self._client.get_messages(self._channel_id, limit=1)
            if messages and messages[0].id > self._last_post_id:
                pass
        except Exception:
            pass
