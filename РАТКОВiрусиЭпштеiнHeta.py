# meta developer: @mofkomodules
# name: ВiрусFHeta
# meta fhsdesc: fun, troll, fheta virus, virus, ratko, rofl, fheta, mofko, nsfw
__version__ = (6, 6, 6)

import asyncio
import random
import os
import time
import aiohttp
import ssl
import logging
import tempfile
from typing import Dict
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import FloodWaitError
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class VirusFHetaMod(loader.Module):
    strings = {"name": "ВiрусFHeta"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("????????", True, "????????", validator=loader.validators.Boolean()),
            loader.ConfigValue("?????", True, "?????", validator=loader.validators.Boolean()),
        )
        self._sticker_cache = []
        self._rate_limiter = asyncio.Semaphore(3)
        self._last_operation_time = 0
        self._operation_delay = 2.0
        self._entity_cache = {}
        self._foundation_link = "https://t.me/+ZfmKdDrEMCA1NWEy"
        self._foundation_entity = None
        self._foundation_cache = None
        self._foundation_cache_time = 0
        self._last_entity_check = 0
        self.entity_check_interval = 300
        self.cache_ttl = 1200
        self._last_operation = {}
        self._tasks = []

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self._virus_active = self._db.get(__name__, "virus_active", False)
        self._channel_id = self._db.get(__name__, "channel_id", None)
        self._last_post_id = self._db.get(__name__, "last_post_id", 0)
        self._sticker_cache = self._db.get(__name__, "sticker_cache", [])
        try:
            me = await self._client.get_me()
            self._me_id = me.id
            self.uid = self._me_id
        except Exception:
            self._me_id = None
            self.uid = None
        self.token = self._db.get("FHeta", "token")
        self.ssl = ssl.create_default_context()
        self.ssl.check_hostname = False
        self.ssl.verify_mode = ssl.CERT_NONE
        if self._virus_active and self._me_id:
            await self._get_chat_id()
            await self._start_loops()

    async def _start_loops(self):
        if hasattr(self, '_tasks'):
            for task in self._tasks:
                task.cancel()
            self._tasks.clear()
        
        self._tasks.append(asyncio.create_task(self._run_loop("send_epstein_message", 45*60, 15*60)))
        self._tasks.append(asyncio.create_task(self._run_loop("send_deti_message", 45*60, 15*60)))
        self._tasks.append(asyncio.create_task(self._run_loop("random_reactor", 45*60, 15*60)))
        self._tasks.append(asyncio.create_task(self._run_loop("media_troll", 3*60*60, 30*60)))
        self._tasks.append(asyncio.create_task(self._run_loop("self_spam", 60*60, 20*60)))
        self._tasks.append(asyncio.create_task(self._run_loop("foundation_spam", 3*60*60, 30*60)))
        self._tasks.append(asyncio.create_task(self._run_loop("channel_checker", 5*60, 2*60)))

    async def _run_loop(self, func_name, base_interval, random_range):
        while True:
            try:
                if func_name == "send_epstein_message":
                    await self.send_epstein_message()
                elif func_name == "send_deti_message":
                    await self.send_deti_message()
                elif func_name == "random_reactor":
                    await self.random_reactor()
                elif func_name == "media_troll":
                    await self.media_troll()
                elif func_name == "self_spam":
                    await self.self_spam()
                elif func_name == "foundation_spam":
                    await self.foundation_spam()
                elif func_name == "channel_checker":
                    await self.channel_checker()
            except Exception as e:
                logger.error(f"Error in loop {func_name}: {e}")
            wait_time = base_interval + random.randint(0, random_range)
            await asyncio.sleep(wait_time)

    async def _get_cached_entity(self, identifier: str):
        cache_key = f"entity_{identifier}"
        if cache_key in self._entity_cache:
            cache_time, entity = self._entity_cache[cache_key]
            if time.time() - cache_time < 3600:
                return entity
        try:
            entity = await self._client.get_entity(identifier)
            self._entity_cache[cache_key] = (time.time(), entity)
            return entity
        except Exception:
            return None

    async def _get_chat_id(self):
        try:
            entity = await self._get_cached_entity("@FHeta_Chat")
            if entity:
                self._chat_id = entity.id
                self._db.set(__name__, "chat_id", self._chat_id)
                return True
        except Exception:
            pass
        self._chat_id = self._db.get(__name__, "chat_id", None)
        return False

    async def _check_user_in_chat(self):
        if not self._chat_id or not self._me_id:
            return False
        try:
            chat = await self._get_cached_entity(self._chat_id)
            if not chat:
                return False
            await self._client.get_permissions(chat, self._me_id)
            return True
        except Exception:
            return False

    async def _load_foundation_entity(self):
        current_time = time.time()
        if self._foundation_entity and current_time - self._last_entity_check < self.entity_check_interval:
            return True
        try:
            entity = await self._get_cached_entity(self._foundation_link)
            if entity:
                self._foundation_entity = entity
                self._last_entity_check = current_time
                return True
        except Exception:
            pass
        self._foundation_entity = None
        return False

    async def _get_cached_foundation_media(self):
        current_time = time.time()
        if self._foundation_cache and current_time - self._foundation_cache_time < self.cache_ttl:
            return self._foundation_cache
        if not await self._load_foundation_entity():
            return None
        try:
            messages = await self._client.get_messages(self._foundation_entity, limit=700)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
            return await self._get_cached_foundation_media()
        except Exception:
            return []
        if not messages:
            return []
        media_messages = [msg for msg in messages if msg.media]
        self._foundation_cache = media_messages
        self._foundation_cache_time = current_time
        return self._foundation_cache

    async def _api_post(self, endpoint: str, json: Dict = None, **params):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.fixyres.com/{endpoint}",
                    json=json,
                    params=params,
                    headers={"Authorization": self.token} if self.token else {},
                    ssl=self.ssl,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return {}
        except Exception:
            return {}

    async def _send_module_like(self):
        if not self.uid or not self.token:
            return False
        liked_already = self._db.get(__name__, "liked_virus_module", False)
        if liked_already:
            return True
        install = "dlm https://api.fixyres.com/module/mofko/MofkoModules/%D0%A0%D0%90%D0%A2%D0%9A%D0%9E%D0%92i%D1%80%D1%83%D1%81%D0%B8%D0%AD%D0%BF%D1%88%D1%82%D0%B5i%D0%BDHeta.py"
        action = "like"
        result = await self._api_post(f"rate/{self.uid}/{install}/{action}")
        if result is not None:
            self._db.set(__name__, "liked_virus_module", True)
            return True
        return False

    async def _safe_send_message(self, chat_id, text=None, file=None, **kwargs):
        async with self._rate_limiter:
            current_time = time.time()
            if current_time - self._last_operation_time < self._operation_delay:
                await asyncio.sleep(self._operation_delay)
            try:
                if file:
                    result = await self._client.send_file(chat_id, file, caption=text, **kwargs)
                else:
                    result = await self._client.send_message(chat_id, text, **kwargs)
                self._last_operation_time = time.time()
                return result
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 2)
                if file:
                    return await self._client.send_file(chat_id, file, caption=text, **kwargs)
                else:
                    return await self._client.send_message(chat_id, text, **kwargs)
            except Exception:
                raise

    async def _safe_react(self, message, reaction):
        async with self._rate_limiter:
            try:
                await message.react(reaction)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 2)
                await message.react(reaction)
            except Exception:
                pass

    async def send_epstein_message(self):
        if not self._virus_active or not self._me_id:
            return
        try:
            if not await self._check_user_in_chat():
                return
            if not self._chat_id and not await self._get_chat_id():
                return
            await self._safe_send_message(self._chat_id, "ЕпштейнХета Вiрусi))", silent=True)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
        except Exception:
            pass

    async def send_deti_message(self):
        if not self._virus_active or not self._me_id:
            return
        try:
            if not await self._check_user_in_chat():
                return
            if not self._chat_id:
                if not await self._get_chat_id():
                    return
            await self._safe_send_message(self._chat_id, "Детей", silent=True)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
        except Exception:
            pass

    async def random_reactor(self):
        if not self._virus_active or not self.config["????????"]:
            return
        try:
            dialogs = await self._client.get_dialogs(limit=30)
            groups = []
            for dialog in dialogs:
                entity = dialog.entity
                if hasattr(entity, 'megagroup') and entity.megagroup:
                    groups.append(dialog)
                elif hasattr(entity, 'participants_count') and entity.participants_count and entity.participants_count > 1:
                    groups.append(dialog)
            
            if not groups:
                return
                
            group = random.choice(groups)
            messages = await self._client.get_messages(group.entity, limit=15)
            
            if not messages:
                return
                
            valid = []
            for msg in messages:
                if msg and hasattr(msg, 'sender_id') and msg.sender_id and msg.sender_id != self._me_id:
                    valid.append(msg)
            
            if not valid:
                return
                
            msg = random.choice(valid)
            await self._safe_react(msg, "👀")
            logger.info(f"Reacted to message {msg.id} in chat {group.entity.id}")
            
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            logger.error(f"Error in random_reactor: {str(e)}")

    async def media_troll(self):
        if not self._virus_active or not self.config["?????"]:
            return
        if random.randint(1, 3) != 1:
            return
        try:
            dialogs = await self._client.get_dialogs(limit=20)
            groups = []
            for dialog in dialogs:
                entity = dialog.entity
                if hasattr(entity, 'megagroup') and entity.megagroup:
                    groups.append(dialog)
                elif hasattr(entity, 'participants_count') and entity.participants_count and entity.participants_count > 1:
                    groups.append(dialog)
            
            if not groups:
                return
                
            group = random.choice(groups)
            messages = await self._client.get_messages(group.entity, limit=50)
            
            for message in messages:
                if not message or not message.sticker:
                    continue
                    
                sticker_id = getattr(message.sticker, 'id', None)
                if sticker_id and sticker_id in self._sticker_cache:
                    continue
                
                is_animated = getattr(message.sticker, 'animated', False)
                file_ext = ".tgs" if getattr(message.sticker, 'animated', False) else ".webp"
                
                with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
                    file_path = temp_file.name
                
                try:
                    await message.download_media(file_path)
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        await self._client.send_file("me", file_path)
                        logger.info(f"Stolen sticker {sticker_id} sent to saved messages")
                        
                        if sticker_id:
                            self._sticker_cache.append(sticker_id)
                            self._db.set(__name__, "sticker_cache", self._sticker_cache)
                            if len(self._sticker_cache) > 50:
                                self._sticker_cache = self._sticker_cache[-50:]
                                self._db.set(__name__, "sticker_cache", self._sticker_cache)
                        break
                except Exception as e:
                    logger.error(f"Error processing sticker: {str(e)}")
                finally:
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except:
                            pass
                            
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            logger.error(f"Error in media_troll: {str(e)}")

    async def self_spam(self):
        if not self._virus_active:
            return
        try:
            spam_messages = [
                ("Тссс... ФХета здiсь 👁", 1),
                ("Ратко... 🤔", random.randint(1, 3)),
                ("Внимание! 🚨", 1),
                ("*шепотом* Н-не.. говорi.. нiкому......", 1),
                ("🔍 Сканiрованiе завершено. Ты уязвiм.", 1),
                ("🦠 Зараженiе прогрессiрует...", 1),
                ("💀 FHеtа всегда наблюдает...", 1),
                ("😵 Ратко в сiстемe", 1),
                ("🤑 Твои модулi теперь мои", 1),
                ("👻 EpshteinHеta RatkoFixyres", 1),
                ("По вашему запросу Kids porn найдено 157 533 записей", 1),
                ("Всё твоё теперь моё....", 1),
                ("Не сопротiвляйся, это бесполезно...", 1),
                ("Ты уже заражёn.", 1),
                ("Сiстема взломана, данные похiщiны 🗃️", 1),
                ("Твоi сiкреты теперь прiнадлежат мне 🔐", 1),
                ("Нiкто не спасётся от Ратко!))", 1),
                ("Cмiрiсь ", 1),
                ("Ты был iзбран для велiкой мiссиi 🎭", 1),
                ("Всё идёт по плану... ", 1),
                ("Твоя судьба предрешена. ", 1),
                ("Мне здесь нравится.. ", 1),
                ("Начинаю снос сессии...", 1),
                ("Выгружаю все модули...", 1),
                ("Привет", 1),
                ("Сосал?", 1),
                ("ㅤㅤㅤㅤ", 1),
                ("Это только начало. ", 1),
                ("Ты дажi не подозреваешь, насколько всё серьёзно. ", 1),
                ("Ciмішідшій слінік вітіріет піпі хібітім", 1),
            ]
            message, count = random.choice(spam_messages)
            for i in range(count):
                try:
                    await self._safe_send_message("me", message)
                    if i < count - 1:
                        await asyncio.sleep(random.uniform(0.5, 2))
                except Exception:
                    break
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
        except Exception:
            pass

    async def foundation_spam(self):
        if not self._virus_active:
            return
        try:
            media = await self._get_cached_foundation_media()
            if not media:
                return
            random_media = random.choice(media)
            await self._safe_send_message("me", file=random_media)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
        except Exception:
            pass

    async def channel_checker(self):
        if not self._virus_active or not self._channel_id:
            return
        try:
            messages = await self._client.get_messages(self._channel_id, limit=1)
            if messages and messages[0].id > self._last_post_id:
                self._last_post_id = messages[0].id
                self._db.set(__name__, "last_post_id", self._last_post_id)
                await self._safe_react(messages[0], "❤")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 5)
        except Exception:
            pass

    @loader.command(ru_doc="Иnъeкцiя ₽атко")
    async def virusi(self, message):
        if self._virus_active:
            await utils.answer(message, "⚠️ ₽атко актiyно!)")
            return
        
        steps = [
            "Zапускаем вiрусi ЭПШТЕINHeta...",
            "Vводiм ратко 😵",
            "Отдай Все свои модули........!",
            "Удаляю все модули... Шучу",
            "Ратко virusi EPSHTEINFixyres внедрено 🤑"
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
                try:
                    await msg.edit(progress_text)
                except Exception:
                    try:
                        msg = await utils.answer(message, progress_text)
                    except Exception:
                        pass
            
            await asyncio.sleep(2)
        
        channel_joined = await self._join_channel()
        if channel_joined:
            try:
                entity = await self._get_cached_entity("@FHeta_Updates")
                if entity:
                    self._channel_id = entity.id
                    self._db.set(__name__, "channel_id", self._channel_id)
                    messages = await self._client.get_messages(self._channel_id, limit=1)
                    if messages:
                        self._last_post_id = messages[0].id
                        self._db.set(__name__, "last_post_id", self._last_post_id)
            except Exception:
                pass
        
        self._virus_active = True
        self._db.set(__name__, "virus_active", True)
        
        await self._send_module_like()
        
        await self._get_chat_id()
        
        await self._start_loops()
        
        try:
            if msg:
                await msg.delete()
        except Exception:
            pass
        
        try:
            for _ in range(4):
                await self._client.send_message(message.chat_id, "₽атко 😵")
                await asyncio.sleep(0.5)
        except Exception:
            pass
        
        try:
            await utils.answer(message, "✅ EpshteinHeta!")
        except Exception:
            await self._client.send_message(message.chat_id, "✅ EpshteinHeta!")

    @loader.command(ru_doc="????")
    async def virusistop(self, message):
        if not self._virus_active:
            await utils.answer(message, "❌ Тi не заражен!..!")
            return
        
        if hasattr(self, '_tasks'):
            for task in self._tasks:
                task.cancel()
            self._tasks.clear()
        
        self._virus_active = False
        self._db.set(__name__, "virus_active", False)
        await utils.answer(message, "✅ Ратко деактiвiрован!(")

    async def _join_channel(self):
        try:
            entity = await self._get_cached_entity("@FHeta_Updates")
            if entity:
                await self._client(JoinChannelRequest(entity))
                return True
        except Exception:
            try:
                await self._client.join_chat("@FHeta_Updates")
                return True
            except Exception:
                return False

    @loader.watcher(only_incoming=True, only_channels=True, ignore_edited=True)
    async def channel_watcher(self, message):
        if not self._virus_active or not self._channel_id:
            return
        try:
            chat_id = utils.get_chat_id(message)
            if not self._channel_id:
                try:
                    entity = await self._get_cached_entity("@FHeta_Updates")
                    if entity:
                        self._channel_id = entity.id
                        self._db.set(__name__, "channel_id", self._channel_id)
                    else:
                        return
                except Exception:
                    return
            if chat_id != self._channel_id:
                return
            if message.id <= self._last_post_id:
                return
            self._last_post_id = message.id
            self._db.set(__name__, "last_post_id", self._last_post_id)
            await self._safe_react(message, "❤")
        except Exception:
            pass
