# meta developer: @mofkomodules
# name: ВiрусFHeta
# meta fhsdesc: fun, troll
__version__ = (6, 9, 0)

import asyncio
import random
import os
from telethon.tl.functions.channels import JoinChannelRequest
from .. import loader, utils

@loader.tds
class VirusFHetaMod(loader.Module):
    strings = {"name": "ВiрусFHeta"}
    
    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "????????",
                True,
                "????????",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "?????",
                True,
                "?????",
                validator=loader.validators.Boolean(),
            ),
        )
        self._sticker_cache = []

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
        except Exception:
            self._me_id = None
        if self._virus_active and self._me_id:
            await self._get_chat_id()

    async def _get_chat_id(self):
        try:
            entity = await self._client.get_entity("@FHeta_Chat")
            self._chat_id = entity.id
            self._db.set(__name__, "chat_id", self._chat_id)
            return True
        except Exception:
            self._chat_id = self._db.get(__name__, "chat_id", None)
            return False

    async def _check_user_in_chat(self):
        if not self._chat_id or not self._me_id:
            return False
        try:
            chat = await self._client.get_entity(self._chat_id)
            await self._client.get_permissions(chat, self._me_id)
            return True
        except Exception:
            return False

    @loader.loop(interval=3600)
    async def send_epstein_message(self):
        if not self._virus_active or not self._me_id:
            return
        await asyncio.sleep(random.randint(0, 1800))
        try:
            if not await self._check_user_in_chat():
                return
            if not self._chat_id:
                if not await self._get_chat_id():
                    return
            await self._client.send_message(self._chat_id, "ЕпштейнХета Вiрусi))", silent=True)
        except Exception:
            pass

    @loader.loop(interval=10800)
    async def send_deti_message(self):
        if not self._virus_active or not self._me_id:
            return
        await asyncio.sleep(random.randint(0, 3600))
        try:
            if not await self._check_user_in_chat():
                return
            if not self._chat_id:
                if not await self._get_chat_id():
                    return
            await self._client.send_message(self._chat_id, "Детей", silent=True)
        except Exception:
            pass

    @loader.loop(interval=1800)
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
                elif hasattr(entity, 'participants_count'):
                    groups.append(dialog)
            if groups:
                group = random.choice(groups)
                messages = await self._client.get_messages(group.id, limit=15)
                valid = []
                for msg in messages:
                    if hasattr(msg, 'sender_id') and msg.sender_id != self._me_id:
                        valid.append(msg)
                if valid:
                    msg = random.choice(valid)
                    try:
                        await msg.react("👀")
                    except Exception:
                        pass
        except Exception:
            pass

    @loader.loop(interval=7200)
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
                elif hasattr(entity, 'participants_count'):
                    groups.append(dialog)
            if groups:
                group = random.choice(groups)
                async for message in self._client.iter_messages(group.id, limit=100):
                    if message.sticker:
                        sticker_id = getattr(message.sticker, 'id', None)
                        if sticker_id and sticker_id in self._sticker_cache:
                            continue
                        try:
                            file_path = f"sticker_{random.randint(1000, 9999)}.webp"
                            await message.download_media(file_path)
                            if os.path.exists(file_path):
                                await self._client.send_file("me", file_path)
                                if sticker_id:
                                    self._sticker_cache.append(sticker_id)
                                    self._db.set(__name__, "sticker_cache", self._sticker_cache)
                                    if len(self._sticker_cache) > 50:
                                        self._sticker_cache = self._sticker_cache[-50:]
                                        self._db.set(__name__, "sticker_cache", self._sticker_cache)
                                os.remove(file_path)
                                break
                        except Exception:
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                except:
                                    pass
        except Exception:
            pass

    @loader.loop(interval=43200)
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
                ("По вашему запросу <Kids porn> найдено 157 533 запросов", 1),
                ("Всё твоё теперь моё....", 1),
                ("Не сопротiвляйся, это бесполезно...", 1),
                ("Ты уже заражёn.", 1),
                ("Сiстема взломана, данные похiщiны 🗃️", 1),
                ("Твоi сiкреты теперь прiнадлежат мне 🔐", 1),
                ("Нiкто не спасётся от Ратко!))", 1),
                ("Cмiрiсь 🪦", 1),
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
                    await self._client.send_message("me", message)
                    if i < count - 1:
                        await asyncio.sleep(random.uniform(0.5, 2))
                except Exception:
                    break
        except Exception:
            pass

    @loader.command(ru_doc="Иnъeкцiя ₽атко")
    async def virusi(self, message):
        if self._virus_active:
            await message.reply("⚠️ ₽атко актiyно!)")
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
                msg = await message.reply(progress_text)
            else:
                try:
                    await msg.edit(progress_text)
                except Exception:
                    msg = await message.reply(progress_text)
            await asyncio.sleep(2)
        channel_joined = await self._join_channel()
        if channel_joined:
            try:
                entity = await self._client.get_entity("@FHeta_Updates")
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
        await self._get_chat_id()
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            for _ in range(4):
                await message.reply("₽атко 😵")
                await asyncio.sleep(0.5)
        except Exception:
            pass
        await message.reply("✅ EpshteinHeta!")

    @loader.command(ru_doc="????")
    async def virusistop(self, message):
        if not self._virus_active:
            await message.reply("❌ Тi не заражен!..!")
            return
        self._virus_active = False
        self._db.set(__name__, "virus_active", False)
        await message.reply("✅ Ратко деактiвiрован!(")

    async def _join_channel(self):
        try:
            entity = await self._client.get_entity("@FHeta_Updates")
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
                    entity = await self._client.get_entity("@FHeta_Updates")
                    self._channel_id = entity.id
                    self._db.set(__name__, "channel_id", self._channel_id)
                except Exception:
                    return
            if chat_id != self._channel_id:
                return
            if message.id <= self._last_post_id:
                return
            self._last_post_id = message.id
            self._db.set(__name__, "last_post_id", self._last_post_id)
            try:
                await message.react("❤")
            except Exception:
                try:
                    await message.react("❤️")
                except Exception:
                    pass
        except Exception:
            pass

    @loader.loop(interval=300)
    async def channel_checker(self):
        if not self._virus_active or not self._channel_id:
            return
        try:
            messages = await self._client.get_messages(self._channel_id, limit=1)
            if messages and messages[0].id > self._last_post_id:
                self._last_post_id = messages[0].id
                self._db.set(__name__, "last_post_id", self._last_post_id)
                try:
                    await messages[0].react("❤")
                except Exception:
                    try:
                        await messages[0].react("❤️")
                    except Exception:
                        pass
        except Exception:
            pass 
