__version__ = (1, 0, 0)
# meta developer: @mofkomodules
# name: M:Forward
# description: крч мне не нравятся уже существующие пересылщики, поэтому я сделал свой. 
# meta banner: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260205_171326_275.jpg 
# meta pic: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260205_171326_275.jpg
# meta fhsdesc: forward, mofko, хуйня, link, tool

import logging
import io
import time
import re
from telethon.tl.types import (
    Message,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    DocumentAttributeAnimated,
    DocumentAttributeSticker,
    DocumentAttributeAudio,
)
from telethon import errors

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class MForwardMod(loader.Module):
    """
    Модуль для пересылки сообщений из каналов, где запрещена пересылка.
    """
    strings = {
        "name": "M:Forward",
        "no_args": "<emoji document_id=5407001145740631266>🤐</emoji> <b>Пожалуйста, укажи ссылку на сообщение в Telegram.</b>\n"
                   "<i>Пример:</i> <code>.mforward https://t.me/username/123</code> "
                   "или <code>.mforward https://t.me/c/123456789/123</code>",
        "invalid_link": "<emoji document_id=5121063440311386962>👎</emoji> <b>Неверный формат ссылки на сообщение в Telegram.</b>",
        "fetching_message": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Получаю сообщение...</b>",
        "message_not_found": "<emoji document_id=5913376703312302899>📣</emoji> <b>Сообщение не найдено или недоступно.</b> "
                             "<i>Убедись, что у тебя есть доступ к каналу и ссылка верна.</i>",
        "error_fetching": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при получении сообщения.</b>",
        "error_sending": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при отправке сообщения.</b>",
        "media_restricted": "<emoji document_id=5121063440311386962>👎</emoji> <b>Не удалось загрузить медиа из этого защищенного чата.</b> "
                            "<i>Telegram запрещает загрузку контента из него.</i>",
        "downloading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Скачиваю медиа:</b> {percentage}% ({current_human}/{total_human})\n"
                             "<i>Скорость:</i> {speed_human}/s, <i>Осталось:</i> {remaining_human}",
        "uploading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Загружаю медиа:</b> {percentage}% ({current_human}/{total_human})\n"
                           "<i>Скорость:</i> {speed_human}/s, <i>Осталось:</i> {remaining_human}",
    }

    strings_ru = {
        "no_args": "<emoji document_id=5407001145740631266>🤐</emoji> <b>Пожалуйста, укажи ссылку на сообщение в Telegram.</b>\n"
                   "<i>Пример:</i> <code>.mforward https://t.me/username/123</code> "
                   "или <code>.mforward https://t.me/c/123456789/123</code>",
        "invalid_link": "<emoji document_id=5121063440311386962>👎</emoji> <b>Неверный формат ссылки на сообщение в Telegram.</b>",
        "fetching_message": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Получаю сообщение...</b>",
        "message_not_found": "<emoji document_id=5913376703312302899>📣</emoji> <b>Сообщение не найдено или недоступно.</b> "
                             "<i>Убедись, что у тебя есть доступ к каналу и ссылка верна.</i>",
        "error_fetching": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при получении сообщения.</b>",
        "error_sending": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при отправке сообщения.</b>",
        "media_restricted": "<emoji document_id=5121063440311386962>👎</emoji> <b>Не удалось загрузить медиа из этого защищенного чата.</b> "
                            "<i>Telegram запрещает загрузку контента из него.</i>",
        "downloading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Скачиваю медиа:</b> {percentage}% ({current_human}/{total_human})\n"
                             "<i>Скорость:</i> {speed_human}/s, <i>Осталось:</i> {remaining_human}",
        "uploading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Загружаю медиа:</b> {percentage}% ({current_human}/{total_human})\n"
                           "<i>Скорость:</i> {speed_human}/s, <i>Осталось:</i> {remaining_human}",
    }
    
    def __init__(self):
        super().__init__()
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "progress_update_interval_sec",
                2,
                lambda: "Интервал обновления прогресса в секундах",
                validator=loader.validators.Integer(minimum=1)
            )
        )
        self._last_progress_update_time = 0

    async def client_ready(self, client, db):
        self.client = client

    def _humanize_bytes(self, num, suffix="B"):
        for unit in ["", "Ki", "Mi", "Gi", "T", "P", "E", "Z"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Yi{suffix}"

    def _humanize_delta(self, seconds):
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            minutes = seconds // 60
            seconds_rem = seconds % 60
            return f"{minutes}m {seconds_rem}s"
        if seconds < 86400:
            hours = seconds // 3600
            minutes_rem = (seconds % 3600) // 60
            return f"{hours}h {minutes_rem}m"
        days = seconds // 86400
        hours_rem = (seconds % 86400) // 3600
        return f"{days}d {hours_rem}h"

    async def _progress_callback(self, current, total, message_entity: Message, start_time: float, action_key: str):
        if not total:
            return

        now = time.time()
        if now - self._last_progress_update_time < self.config["progress_update_interval_sec"]:
            return

        percentage = f"{current * 100 / total:.1f}"
        elapsed_time = now - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        remaining_time = (total - current) / speed if speed > 0 else 0

        speed_str = self._humanize_bytes(speed)
        remaining_time_str = self._humanize_delta(int(remaining_time))
        current_human = self._humanize_bytes(current)
        total_human = self._humanize_bytes(total)

        try:
            await message_entity.edit(
                self.strings(action_key).format(
                    percentage=percentage,
                    current_human=current_human,
                    total_human=total_human,
                    speed_human=speed_str,
                    remaining_human=remaining_time_str
                )
            )
            self._last_progress_update_time = now
        except errors.MessageNotModifiedError:
            pass
        except Exception as e:
            logger.debug(f"Failed to update progress message, it might have been deleted or another error: {e}")


    @loader.command(
        ru_doc="<ссылка> - Пересылает сообщение по ссылке из канала с запретом на пересылку.",
        en_doc="<link> - Forwards a message by link from a channel with restricted forwarding.",
        alias="mforward"
    )
    async def linkforwardcmd(self, message: Message):
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("no_args"))
            return

        link = args.strip()
        
        match = re.match(r"https://t.me/(?:c/(\d+)|([^/]+))/(\d+)", link)

        if not match:
            await utils.answer(message, self.strings("invalid_link"))
            return

        entity_identifier = None
        msg_id = None

        if match.group(1):
            try:
                channel_numeric_id = int(match.group(1))
                entity_identifier = int(f"-100{channel_numeric_id}")
                msg_id = int(match.group(3))
            except ValueError:
                await utils.answer(message, self.strings("invalid_link"))
                return
        elif match.group(2):
            try:
                entity_identifier = match.group(2)
                msg_id = int(match.group(3))
            except ValueError:
                await utils.answer(message, self.strings("invalid_link"))
                return
        
        if not entity_identifier or not msg_id:
            await utils.answer(message, self.strings("invalid_link"))
            return

        status_message = await utils.answer(message, self.strings("fetching_message"))

        try:
            target_message = (await self.client.get_messages(entity_identifier, ids=msg_id))

            if not target_message:
                await status_message.edit(self.strings("message_not_found"))
                return

            reply_to_id = message.reply_to_msg_id if message.reply_to_msg_id else message.id

            if target_message.media:
                try:
                    media_bytes = io.BytesIO()
                    original_file_name = None
                    
                    attributes = []
                    if hasattr(target_message.media, 'document') and target_message.media.document:
                        attributes = list(target_message.media.document.attributes)
                        for attr in target_message.media.document.attributes:
                            if isinstance(attr, DocumentAttributeFilename):
                                original_file_name = attr.file_name
                                break
                    
                    if not original_file_name:
                        if target_message.photo:
                            original_file_name = "photo.jpg"
                        elif target_message.video:
                            original_file_name = "video.mp4"
                        elif target_message.audio:
                            original_file_name = "audio.mp3"
                        elif target_message.document:
                            original_file_name = "document.bin"
                        else:
                            original_file_name = "media.bin"
                    
                    media_bytes.name = original_file_name

                    download_start_time = time.time()
                    await self.client.download_media(
                        target_message,
                        file=media_bytes,
                        progress_callback=lambda current, total: self._progress_callback(
                            current, total, status_message, download_start_time, "downloading_media"
                        )
                    )
                    media_bytes.seek(0)

                    force_document = True
                    if target_message.photo or target_message.video:
                        force_document = False
                        
                    if not any(isinstance(a, DocumentAttributeFilename) for a in attributes):
                        attributes.append(DocumentAttributeFilename(file_name=original_file_name))

                    upload_start_time = time.time()
                    await self.client.send_file(
                        message.peer_id,
                        media_bytes,
                        caption=target_message.text,
                        parse_mode='html',
                        link_preview=bool(target_message.web_preview),
                        reply_to=reply_to_id,
                        attributes=attributes if attributes else None,
                        force_document=force_document,
                        progress_callback=lambda current, total: self._progress_callback(
                            current, total, status_message, upload_start_time, "uploading_media"
                        )
                    )
                except errors.ChatForwardsRestrictedError:
                    await status_message.edit(self.strings("media_restricted"))
                    return
                except Exception as e:
                    logger.exception(e)
                    await status_message.edit(self.strings("error_sending"))
                    return
            else:
                text_to_send = target_message.text
                if len(text_to_send) > 4096:
                    file_content = text_to_send
                    file = io.BytesIO(file_content.encode("utf-8"))
                    file.name = "message.txt"
                    
                    await self.client.send_file(
                        message.peer_id,
                        file,
                        caption="Оригинальное сообщение (слишком длинное для текста)",
                        reply_to=reply_to_id
                    )
                else:
                    await self.client.send_message(
                        message.peer_id,
                        text_to_send,
                        parse_mode='html',
                        link_preview=bool(target_message.web_preview),
                        reply_to=reply_to_id
                    )

            await status_message.delete()

        except errors.RPCError as e:
            logger.exception(e)
            await status_message.edit(self.strings("error_fetching"))
        except Exception as e:
            logger.exception(e)
            await status_message.edit(self.strings("error_sending"))
