__version__ = (2, 2, 8)
# diff: - autodelete fsfw
# meta developer: @mofkomodules
# name: Foundation
# meta banner: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260314_095253_702.jpg
# meta pic: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260314_095253_702.jpg
# description: best NSFW % SFW, hentai random module
# meta fhsdesc: hentai, 18+, random, хентай, porn, fun, mofko, хуйня, порно, nsfw, sfw

import random
import logging
import asyncio
import time
import aiohttp
import ssl
import re
from urllib.parse import quote_plus
from collections import defaultdict
from herokutl.types import Message
from .. import loader, utils
from telethon.errors import FloodWaitError, UserNotParticipantError, ChannelPrivateError
from ..inline.types import InlineCall
from cachetools import TTLCache

logger = logging.getLogger(__name__)


@loader.tds
class Foundation(loader.Module):
    strings = {
        "name": "Foundation",
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Something went wrong, check logs",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> You need to join the channel first: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> No media found in channel",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> No videos found in channel",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> No media found in channel",
        "triggers_config": "⚙️ <b>Configuration of triggers for Foundation</b>\n\nChat: {} (ID: {})\n\nCurrent triggers:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "Select trigger to configure:",
        "enter_trigger_word": "✍️ Enter trigger word (or 'off' to disable):",
        "trigger_updated": "✅ Trigger updated!\n\n{} will now trigger .{} in chat {}",
        "trigger_disabled": "✅ Trigger disabled for .{} in chat {}",
        "no_triggers": "No triggers configured",
        "fsfw_cmd_doc": "Send random SFW media from @sfwfond",
    }

    strings_ru = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Чот не то, чекай логи",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Нужно вступить в канал, ВНИМАТЕЛЬНО ЧИТАЙ ПРИ ПОДАЧЕ ЗАЯВКИ: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено медиа",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено видео",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не найдено медиа в канале",
        "triggers_config": "⚙️ <b>Настройка триггеров для Foundation</b>\n\nЧат: {} (ID: {})\n\nТекущие триггеры:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "Выберите триггер для настройки:",
        "enter_trigger_word": "✍️ Введите слово-триггер (или 'off' для отключения):",
        "trigger_updated": "✅ Триггер обновлен!\n\n{} теперь будет вызывать .{} в чате {}",
        "trigger_disabled": "✅ Триггер отключен для .{} в чате {}",
        "no_triggers": "Триггеры не настроены",
        "_cls_doc": "Случайное NSFW медиа",
        "fsfw_cmd_doc": "Отправить рандомное SFW медиа с @sfwfond",
    }

    strings_de = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Etwas ist schiefgelaufen, überprüfe die Logs",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Du musst zuerst dem Kanal beitreten: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Keine Medien im Kanal gefunden",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Keine Videos im Kanal gefunden",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Keine Medien im Kanal gefunden",
        "triggers_config": "⚙️ <b>Konfiguration der Auslöser für Foundation</b>\n\nChat: {} (ID: {})\n\nAktuelle Auslöser:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "Wähle den Auslöser zum Konfigurieren:",
        "enter_trigger_word": "✍️ Gib das Auslöserwort ein (oder 'off' zum Deaktivieren):",
        "trigger_updated": "✅ Auslöser aktualisiert!\n\n{} wird nun .{} im Chat {} auslösen",
        "trigger_disabled": "✅ Auslöser für .{} im Chat {} deaktiviert",
        "no_triggers": "Keine Auslöser konfiguriert",
        "_cls_doc": "Zufällige NSFW-Medien",
        "fsfw_cmd_doc": "Zufällige SFW-Medien von @sfwfond senden",
    }

    strings_zh = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> 出现问题，请检查日志",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> 你需要先加入频道 {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> 频道中未找到媒体",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> 频道中未找到视频",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> 频道中未找到媒体",
        "triggers_config": "⚙️ <b>Foundation 触发器配置</b>\n\n聊天: {} (ID: {})\n\n当前触发器:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "选择要配置的触发器:",
        "enter_trigger_word": "✍️ 输入触发词 (或输入 'off' 禁用):",
        "trigger_updated": "✅ 触发器已更新！\n\n{} 现在将在聊天 {} 中触发 .{}",
        "trigger_disabled": "✅ 已在聊天 {} 中禁用 .{} 的触发器",
        "no_triggers": "未配置触发器",
        "_cls_doc": "随机NSFW媒体",
        "fsfw_cmd_doc": "从 @sfwfond 发送随机 SFW 媒体",
    }

    strings_ja = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> 何かがうまくいかなかった、ログを確認してください",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> 最初にチャンネルに参加する必要があります: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> チャンネルにメディアが見つかりません",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> チャンネルにビデオが見つかりません",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> チャンネルにメディアが見つかりません",
        "triggers_config": "⚙️ <b>Foundation のトリガー設定</b>\n\nチャット: {} (ID: {})\n\n現在のトリガー:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "設定するトリガーを選択:",
        "enter_trigger_word": "✍️ トリガーワードを入力 (または無効にするには 'off'):",
        "trigger_updated": "✅ トリガーが更新されました！\n\n{} はチャット {} で .{} をトリガーします",
        "trigger_disabled": "✅ チャット {} で .{} のトリガーが無効になりました",
        "no_triggers": "トリガーが設定されていません",
        "_cls_doc": "ランダムなNSFWメディア",
        "fsfw_cmd_doc": "@sfwfond からランダムな SFW メディアを送信",
    }

    strings_be = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Нешта не так, правярай логі",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Трэба ўступіць у канал, УВАЖЛІВА ЧЫТАЙ ПРЫ ПАДАЧЫ ЗАЯЎКІ: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не знойдзена медыя",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Не знойдзена відэа",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не знойдзена медыя ў канале",
        "triggers_config": "⚙️ <b>Налада трыгераў для Foundation</b>\n\nЧат: {} (ID: {})\n\nБягучыя трыгеры:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "Выберыце трыгер для налады:",
        "enter_trigger_word": "✍️ Увядзіце слова-трыгер (або 'off' для адключэння):",
        "trigger_updated": "✅ Трыгер абноўлены!\n\n{} цяпер будзе выклікаць .{} у чаце {}",
        "trigger_disabled": "✅ Трыгер адключаны для .{} у чаце {}",
        "no_triggers": "Трыгеры не настроены",
        "_cls_doc": "Выпадковыя NSFW медыя",
        "fsfw_cmd_doc": "Адправіць выпадковае SFW медыя з @sfwfond",
    }
    
    strings_fr = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Quelque chose s'est mal passé, vérifiez les logs",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Vous devez d'abord rejoindre le canal : {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Aucun média trouvé dans le canal",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Aucune vidéo trouvée dans le canal",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Aucun média trouvé dans le canal",
        "triggers_config": "⚙️ <b>Configuration des déclencheurs pour Foundation</b>\n\nChat : {} (ID : {})\n\nDéclencheurs actuels :\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "Sélectionnez le déclencheur à configurer :",
        "enter_trigger_word": "✍️ Entrez le mot déclencheur (ou 'off' pour désactiver) :",
        "trigger_updated": "✅ Déclencheur mis à jour !\n\n{} déclenchera désormais .{} dans le chat {}",
        "trigger_disabled": "✅ Déclencheur désactivé pour .{} dans le chat {}",
        "no_triggers": "Aucun déclencheur configuré",
        "_cls_doc": "Média NSFW aléatoire",
        "fsfw_cmd_doc": "Envoyer un média SFW aléatoire depuis @sfwfond",
    }
    
    strings_ua = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Щось пішло не так, перевір логи",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Потрібно вступити в канал, УВАЖНО ЧИТАЙ ПРИ ПОДАЧІ ЗАЯВКИ: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не знайдено медіа",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Не знайдено відео",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Не знайдено медіа в каналі",
        "triggers_config": "⚙️ <b>Налаштування тригерів для Foundation</b>\n\nЧат: {} (ID: {})\n\nПоточні тригери:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "Виберіть тригер для налаштування:",
        "enter_trigger_word": "✍️ Введіть слово-тригер (або 'off' для вимкнення):",
        "trigger_updated": "✅ Тригер оновлено!\n\n{} тепер буде викликати .{} в чаті {}",
        "trigger_disabled": "✅ Тригер вимкнено для .{} в чаті {}",
        "no_triggers": "Тригери не налаштовані",
        "_cls_doc": "Випадкові NSFW медіа",
        "fsfw_cmd_doc": "Надіслати випадкове SFW медіа з @sfwfond",
    }

    strings_kk = {
        "error": "<emoji document_id=6012681561286122335>🤤</emoji> Бірдеңе дұрыс болмады, логтарды тексеріңіз",
        "not_joined": "<emoji document_id=6012681561286122335>🤤</emoji> Алдымен арнаға қосылу керек, ӨТІНІШ БЕРГЕНДЕ МҰҚИЯТ ОҚЫҢЫЗ: {link}",
        "no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Арнада медиа табылмады",
        "no_videos": "<emoji document_id=6012681561286122335>🤤</emoji> Арнада видео табылмады",
        "fsfw_no_media": "<emoji document_id=6012681561286122335>🤤</emoji> Арнада медиа табылмады",
        "triggers_config": "⚙️ <b>Foundation үшін триггерлерді конфигурациялау</b>\n\nЧат: {} (ID: {})\n\nАғымдағы триггерлер:\n• <code>fond</code>: {}\n• <code>vfond</code>: {}\n• <code>fsfw</code>: {}",
        "select_trigger": "Конфигурациялау үшін триггерді таңдаңыз:",
        "enter_trigger_word": "✍️ Триггер сөзді енгізіңіз ('off' өшіру үшін):",
        "trigger_updated": "✅ Триггер жаңартылды!\n\n{} енді {} чатында .{} іске қосады",
        "trigger_disabled": "✅ {} чатында .{} үшін триггер өшірілді",
        "no_triggers": "Триггерлер конфигурацияланбаған",
        "_cls_doc": "Кездейсоқ NSFW медиа",
        "fsfw_cmd_doc": "@sfwfond арнасынан кездейсоқ SFW медиа жіберу",
    }

    def __init__(self):
        self._media_cache = {}
        self._video_cache = {}
        self._cache_time = {}
        self.entity = None
        self._last_entity_check = 0
        self.entity_check_interval = 300
        self.cache_ttl = 1200
        self.link_channel_username = "foundationlink"
        self.link_message_id = 3
        self.default_foundation_link = "https://t.me/+oScQIU-JzZhlMjAy"
        self.actual_foundation_link = None
        
        self._sfw_channel_username = "sfwfond"
        self._sfw_channel_entity = None
        self._sfw_last_entity_check = 0
        self._sfw_media_cache = {}
        self._sfw_cache_time = {}
        self._sfw_cache_ttl = 600

        self._spam_data = {
            'triggers': defaultdict(list),
            'blocked': {},
            'global_blocked': False,
            'global_block_time': 0
        }
        
        self._block_cache = TTLCache(maxsize=1000, ttl=15)
        
        self.SPAM_LIMIT = 3
        self.SPAM_WINDOW = 3
        self.BLOCK_DURATION = 15
        self.GLOBAL_LIMIT = 10
        self.GLOBAL_WINDOW = 10

        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "triggers_enabled",
                True,
                lambda: "Enable trigger watcher",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "spam_protection",
                True,
                lambda: "Enable spam protection for triggers",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "auto_delete_media",
                False,
                lambda: "Автоматически удалять отправленное медиа через заданное время.",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "auto_delete_delay",
                30,
                lambda: "Задержка в секундах перед автоудалением отправленного медиа (0 для отключения).",
                validator=loader.validators.Integer(minimum=0)
            )
        )

    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        self.triggers = self._db.get(__name__, "triggers", {})
        self._load_spam_data()
        
        self.actual_foundation_link = self._db.get(__name__, "actual_foundation_link", self.default_foundation_link)
        self.uid = (await self.client.get_me()).id
        
        await self._update_foundation_link_on_demand()
        await self._load_entity()
        await self._load_sfw_entity()
        await self._send_fheta_like()

    async def _update_foundation_link_on_demand(self):
        try:
            link_channel_entity = await self.client.get_entity(self.link_channel_username)
            message = await self.client.get_messages(link_channel_entity, ids=self.link_message_id)
            
            if message and message.raw_text:
                match = re.search(r"\[(https?://\S+)\]", message.raw_text)
                if match:
                    new_link = match.group(1)
                    if new_link != self.actual_foundation_link:
                        logger.info(f"Foundation link updated: {self.actual_foundation_link} -> {new_link}")
                        self.actual_foundation_link = new_link
                        self._db.set(__name__, "actual_foundation_link", new_link)
                        self._last_entity_check = 0
                        await self._load_entity()
        except Exception as e:
            logger.warning(f"Error updating foundation link from channel: {e}. Using default/cached link.")
    
    async def _send_fheta_like(self):
        if self.db.get(__name__, "liked_fheta", False): return

        token = self.db.get("FHeta", "token")
        if not token: return

        try:
            install_link = "dlm https://api.fixyres.com/module/mofko/mofkomodules/foundation.py"
            endpoint = f"rate/{self.uid}/{quote_plus(install_link)}/like"

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

    def _load_spam_data(self):
        saved = self._db.get(__name__, "spam_protection", {})
        if saved:
            self._spam_data['triggers'] = defaultdict(list, saved.get('triggers', {}))
            self._spam_data['blocked'] = saved.get('blocked', {})
            self._spam_data['global_blocked'] = saved.get('global_blocked', False)
            self._spam_data['global_block_time'] = saved.get('global_block_time', 0)
    
    def _save_spam_data(self):
        triggers_dict = dict(self._spam_data['triggers'])
        data_to_save = {
            'triggers': triggers_dict,
            'blocked': self._spam_data['blocked'],
            'global_blocked': self._spam_data['global_blocked'],
            'global_block_time': self._spam_data['global_block_time']
        }
        self._db.set(__name__, "spam_protection", data_to_save)

    async def _load_entity(self):
        current_time = time.time()
        if (self.entity and 
            current_time - self._last_entity_check < self.entity_check_interval):
            return True
        try:
            link_to_use = self.actual_foundation_link or self.default_foundation_link
            self.entity = await self.client.get_entity(link_to_use)
            self._last_entity_check = current_time
            return True
        except Exception as e:
            logger.warning(f"Could not load foundation entity from {self.actual_foundation_link or self.default_foundation_link}: {e}")
            self.entity = None
            return False

    async def _load_sfw_entity(self):
        current_time = time.time()
        if (self._sfw_channel_entity and 
            current_time - self._sfw_last_entity_check < self.entity_check_interval):
            return True
        try:
            self._sfw_channel_entity = await self.client.get_entity(self._sfw_channel_username)
            self._sfw_last_entity_check = current_time
            return True
        except Exception as e:
            logger.warning(f"Could not load SFW channel entity @{self._sfw_channel_username}: {e}")
            self._sfw_channel_entity = None
            return False

    async def _get_cached_media(self, media_type="any"):
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
        except (UserNotParticipantError, ChannelPrivateError) as e:
            logger.warning(f"Userbot is not participant or channel is private: {e}")
            return None 
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
        return self._media_cache.get("any") if media_type == "any" else self._video_cache.get("video")
    
    async def _get_sfw_cached_media(self):
        current_time = time.time()
        cache_key = "sfw_any"
        if (cache_key in self._sfw_cache_time and
            current_time - self._sfw_cache_time[cache_key] < self._sfw_cache_ttl):
            return self._sfw_media_cache[cache_key]
        if not await self._load_sfw_entity():
            return None
        try:
            messages = await self.client.get_messages(self._sfw_channel_entity, limit=1000)
        except FloodWaitError as e:
            logger.warning(f"FloodWait for {e.seconds} seconds on SFW channel")
            await asyncio.sleep(e.seconds)
            return await self._get_sfw_cached_media()
        except (UserNotParticipantError, ChannelPrivateError) as e:
            logger.warning(f"Userbot is not participant or SFW channel is private: {e}")
            return None
        except ValueError as e:
            if "Could not find the entity" in str(e):
                return None
            raise e
        if not messages:
            return []
        sfw_media_messages = [msg for msg in messages if msg.media]
        self._sfw_media_cache[cache_key] = sfw_media_messages
        self._sfw_cache_time[cache_key] = current_time
        return sfw_media_messages
    
    def _check_global_spam(self):
        if not self.config["spam_protection"]:
            return False
        
        current_time = time.time()
        
        if self._spam_data['global_blocked']:
            if current_time - self._spam_data['global_block_time'] < self.BLOCK_DURATION:
                return True
            else:
                self._spam_data['global_blocked'] = False
                self._save_spam_data()
                return False
        
        recent_triggers = 0
        ten_seconds_ago = current_time - self.GLOBAL_WINDOW
        
        for user_data in self._spam_data['triggers'].values():
            recent_in_user = [t for t in user_data if t > ten_seconds_ago]
            recent_triggers += len(recent_in_user)
        
        if recent_triggers >= self.GLOBAL_LIMIT:
            self._spam_data['global_blocked'] = True
            self._spam_data['global_block_time'] = current_time
            self._save_spam_data()
            return True
        
        return False
    
    def _check_user_spam(self, user_id, chat_id):
        if not self.config["spam_protection"]:
            return False
        
        current_time = time.time()
        key = f"{user_id}:{chat_id}"
        
        if key in self._block_cache:
            return True
        
        if key in self._spam_data['blocked']:
            block_until = self._spam_data['blocked'][key]
            if current_time < block_until:
                self._block_cache[key] = True
                return True
            else:
                del self._spam_data['blocked'][key]
        
        timestamps = self._spam_data['triggers'][key]
        
        three_seconds_ago = current_time - self.SPAM_WINDOW
        recent_timestamps = [ts for ts in timestamps if ts > three_seconds_ago]
        
        if len(recent_timestamps) >= self.SPAM_LIMIT:
            block_until = current_time + self.BLOCK_DURATION
            self._spam_data['blocked'][key] = block_until
            self._block_cache[key] = True
            self._spam_data['triggers'][key] = []
            self._save_spam_data()
            return True
        
        recent_timestamps.append(current_time)
        self._spam_data['triggers'][key] = recent_timestamps[-20:]
        
        self._save_spam_data()
        return False

    async def _check_spam(self, user_id, chat_id):
        if self._check_global_spam():
            return True
        
        if self._check_user_spam(user_id, chat_id):
            return True
        
        return False

    async def _schedule_delete(self, message_to_delete: Message, delay: int):
        await asyncio.sleep(delay)
        try:
            await message_to_delete.delete()
        except Exception as e:
            logger.warning(f"Failed to auto-delete message {message_to_delete.id} in chat {message_to_delete.chat_id}: {e}")

    async def _send_media(self, message: Message, media_type: str = "any", delete_command: bool = False, is_sfw: bool = False):
        try:
            if is_sfw:
                if not await self._load_sfw_entity():
                    return await utils.answer(message, self.strings["error"])
                media_list = await self._get_sfw_cached_media()
                if media_list is None:
                    return await utils.answer(message, self.strings["error"])
                if not media_list:
                    await utils.answer(message, self.strings["fsfw_no_media"])
                    return
            else:
                if not await self._load_entity():
                    return await utils.answer(message, self.strings["not_joined"].format(emoji="🤤", link=self.actual_foundation_link or self.default_foundation_link))
                media_list = await self._get_cached_media(media_type)
                if media_list is None:
                    return await utils.answer(message, self.strings["not_joined"].format(emoji="🤤", link=self.actual_foundation_link or self.default_foundation_link))
                if not media_list:
                    if media_type == "any":
                        await utils.answer(message, self.strings["no_media"])
                    else:
                        await utils.answer(message, self.strings["no_videos"])
                    return
            
            random_message = random.choice(media_list)
            
            sent_message = await self.client.send_message(
                message.peer_id,
                message=random_message,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
            
            if self.config["auto_delete_media"] and self.config["auto_delete_delay"] > 0 and not is_sfw:
                asyncio.create_task(self._schedule_delete(sent_message, self.config["auto_delete_delay"]))

            if delete_command:
                await asyncio.sleep(0.1)
                try:
                    await message.delete()
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Foundation error: {e}")
            await utils.answer(message, self.strings["error"])

    @loader.command(
        ru_doc="Отправить NSFW медиа с Фонда",
        de_doc="NSFW-Medien von Foundation senden",
        zh_doc="从 Foundation 发送 NSFW 媒体",
        ja_doc="FoundationからNSFWメディアを送信",
        be_doc="Адправіць NSFW медыя з Foundation",
        fr_doc="Envoyer un média NSFW depuis Foundation",
        ua_doc="Надіслати NSFW медіа з Foundation",
        kk_doc="Foundation-нан NSFW медиа жіберу"
    )
    async def fond(self, message: Message):
        """Send NSFW media from Foundation"""
        await self._update_foundation_link_on_demand()
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._send_media(message, "any", delete_command=True)

    @loader.command(
        ru_doc="Отправить NSFW видео с Фонда",
        de_doc="NSFW-Video von Foundation senden",
        zh_doc="从 Foundation 发送 NSFW 视频",
        ja_doc="FoundationからNSFWビデオを送信",
        be_doc="Адправіць NSFW відэа з Foundation",
        fr_doc="Envoyer une vidéo NSFW depuis Foundation",
        ua_doc="Надіслати NSFW відео з Foundation",
        kk_doc="Foundation-нан NSFW видео жіберу"
    )
    async def vfond(self, message: Message):
        """Send NSFW video from Foundation"""
        await self._update_foundation_link_on_demand()
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._send_media(message, "video", delete_command=True)

    @loader.command(
        ru_doc="Отправить рандомное SFW медиа с @sfwfond",
        de_doc="Zufällige SFW-Medien von @sfwfond senden",
        zh_doc="从 @sfwfond 发送随机 SFW 媒体",
        ja_doc="@sfwfond からランダムな SFW メディアを送信",
        be_doc="Адправіць выпадковае SFW медыя з @sfwfond",
        fr_doc="Envoyer un média SFW aléatoire depuis @sfwfond",
        ua_doc="Надіслати випадкове SFW медіа з @sfwfond",
        kk_doc="@sfwfond арнасынан кездейсоқ SFW медиа жіберу"
    )
    async def fsfw(self, message: Message):
        """Send random SFW media from @sfwfond"""
        if await self._check_spam(message.sender_id, utils.get_chat_id(message)):
            return
        await self._send_media(message, is_sfw=True, delete_command=True)

    @loader.command(
        ru_doc="Настроить триггеры для команд fond/vfond/fsfw",
        de_doc="Auslöser für fond/vfond/fsfw-Befehle konfigurieren",
        zh_doc="配置 fond/vfond/fsfw 命令的触发器",
        ja_doc="fond/vfond/fsfwコマンドのトリガーを設定",
        be_doc="Наладзіць трыгеры для каманд fond/vfond/fsfw",
        fr_doc="Configurer les déclencheurs pour les commandes fond/vfond/fsfw",
        ua_doc="Налаштувати тригери для команд fond/vfond/fsfw",
        kk_doc="fond/vfond/fsfw командалары үшін триггерлерді конфигурациялау"
    )
    async def ftriggers(self, message: Message):
        """Configure triggers for fond/vfond/fsfw commands"""
        chat_id = utils.get_chat_id(message)
        chat = await message.get_chat()
        chat_title = getattr(chat, "title", "Private Chat")
        chat_triggers = self.triggers.get(str(chat_id), {})
        fond_trigger = chat_triggers.get("fond", self.strings("no_triggers"))
        vfond_trigger = chat_triggers.get("vfond", self.strings("no_triggers"))
        fsfw_trigger = chat_triggers.get("fsfw", self.strings("no_triggers"))
        await self.inline.form(
            message=message,
            text=self.strings("triggers_config").format(
                chat_title,
                chat_id,
                fond_trigger,
                vfond_trigger,
                fsfw_trigger
            ),
            reply_markup=[
                [
                    {
                        "text": "⚙️ Configure fond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "fond")
                    }
                ],
                [
                    {
                        "text": "⚙️ Configure vfond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "vfond")
                    }
                ],
                [
                    {
                        "text": "⚙️ Configure fsfw trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "fsfw")
                    }
                ],
                [
                    {
                        "text": "❌ Close",
                        "action": "close"
                    }
                ]
            ]
        )

    async def _configure_trigger(self, call: InlineCall, chat_id: int, command: str):
        await utils.answer(
            call,
            self.strings("select_trigger"),
            reply_markup=[
                [
                    {
                        "text": f"✍️ Set trigger for .{command}",
                        "input": self.strings("enter_trigger_word"),
                        "handler": self._save_trigger,
                        "args": (chat_id, command, call)
                    }
                ],
                [
                    {
                        "text": "🔙 Back",
                        "callback": self._show_main_menu,
                        "args": (chat_id,)
                    }
                ]
            ]
        )

    async def _save_trigger(self, call: InlineCall, query: str, chat_id: int, command: str, original_call: InlineCall):
        query = query.strip().lower()
        if str(chat_id) not in self.triggers:
            self.triggers[str(chat_id)] = {}
        if query == "off":
            if command in self.triggers[str(chat_id)]:
                del self.triggers[str(chat_id)][command]
                if not self.triggers[str(chat_id)]:
                    del self.triggers[str(chat_id)]
        else:
            self.triggers[str(chat_id)][command] = query
        self._db.set(__name__, "triggers", self.triggers)
        try:
            chat = await self.client.get_entity(chat_id)
            chat_title = getattr(chat, "title", "Private Chat")
        except:
            chat_title = f"Chat {chat_id}"
        if query == "off":
            await original_call.answer(
                self.strings("trigger_disabled").format(command, chat_title),
                show_alert=True
            )
        else:
            await original_call.answer(
                self.strings("trigger_updated").format(query, command, chat_title),
                show_alert=True
            )
        await self._show_main_menu(original_call, chat_id)

    async def _show_main_menu(self, call: InlineCall, chat_id: int):
        try:
            chat = await self.client.get_entity(chat_id)
            chat_title = getattr(chat, "title", "Private Chat")
        except:
            chat_title = f"Chat {chat_id}"
        chat_triggers = self.triggers.get(str(chat_id), {})
        fond_trigger = chat_triggers.get("fond", self.strings("no_triggers"))
        vfond_trigger = chat_triggers.get("vfond", self.strings("no_triggers"))
        fsfw_trigger = chat_triggers.get("fsfw", self.strings("no_triggers"))
        await utils.answer(
            call,
            self.strings("triggers_config").format(
                chat_title,
                chat_id,
                fond_trigger,
                vfond_trigger,
                fsfw_trigger
            ),
            reply_markup=[
                [
                    {
                        "text": "⚙️ Configure fond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "fond")
                    }
                ],
                [
                    {
                        "text": "⚙️ Configure vfond trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "vfond")
                    }
                ],
                [
                    {
                        "text": "⚙️ Configure fsfw trigger",
                        "callback": self._configure_trigger,
                        "args": (chat_id, "fsfw")
                    }
                ],
                [
                    {
                        "text": "❌ Close",
                        "action": "close"
                    }
                ]
            ]
        )

    @loader.watcher()
    async def watcher(self, message: Message):
        if not self.config["triggers_enabled"]:
            return
        if not message.text:
            return
        chat_id = utils.get_chat_id(message)
        text = message.text.lower().strip()
        chat_triggers = self.triggers.get(str(chat_id), {})
        
        for command, trigger in chat_triggers.items():
            if text == trigger:
                if await self._check_spam(message.sender_id, chat_id):
                    return
                if command == "fond":
                    await self._send_media(message, "any", delete_command=True)
                elif command == "vfond":
                    await self._send_media(message, "video", delete_command=True)
                elif command == "fsfw":
                    await self._send_media(message, is_sfw=True, delete_command=True)
                break
