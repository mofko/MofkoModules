__version__ = (2, 0, 0)
# meta developer: @mofkomodules
# name: M:Forward
# meta banner: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260210_160819_562.jpg
# meta pic: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260210_160819_562.jpg
# meta fhsdesc: forward, mofko, хуйня, link, tool, Пересылка, copy, копирование 

import logging
import io
import time
import re
import asyncio
from telethon.tl.types import (
    Message,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    DocumentAttributeAnimated,
    DocumentAttributeSticker,
    DocumentAttributeAudio,
    Channel,
)
from telethon import errors, functions

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class MForwardMod(loader.Module):
    """
    Модуль для пересылки сообщений (Поддерживает каналы с запретом пересылки). 
    Также имеет функцию "бекапа", путём пересылки всех сообщений из одного канала в другой. 
    Смотри конфиг.
    """
    strings = {
        "name": "M:Forward",
        "no_args": "<emoji document_id=5407001145740631266>🤐</emoji> <b>Пожалуйста, укажи ссылку на сообщение.</b>\n"
                   "<i>Пример:</i> <code>.mfw https://t.me/username/123</code>\n"
                   "или <code>.mfw https://t.me/c/123456789/123</code>,\n"
                   "<i>Для диапазона:</i> <code>.mfw https://t.me/username/123 https://t.me/username/125</code>",
        "invalid_link": "<emoji document_id=5121063440311386962>👎</emoji> <b>Неверный формат ссылки на сообщение.</b>",
        "too_many_links": "<emoji document_id=5121063440311386962>👎</emoji> <b>Укажите одну или две ссылки на сообщения.</b>",
        "same_channel_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Обе ссылки должны быть из одного канала.</b>",
        "invalid_id_range": "<emoji document_id=5121063440311386962>👎</emoji> <b>Начальное ID сообщения не может быть больше конечного.</b>",
        "fetching_message": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Получаю сообщение(я)...</b>",
        "message_not_found": "<emoji document_id=5913376703312302899>📣</emoji> <b>Сообщение(я) не найдено(ы) или недоступно(ы).</b> "
                             "<i>Убедись, что у тебя есть доступ к каналу и ссылка верна.</i>",
        "error_fetching": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при получении сообщения(й).</b>",
        "error_sending": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при отправке сообщения(й).</b>",
        "media_restricted": "<emoji document_id=5121063440311386962>👎</emoji> <b>Не удалось загрузить медиа из этого защищенного канала.</b> "
                            "<i>Telegram запрещает загрузку контента из него.</i>",
        "downloading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Скачиваю медиа:</b> {percentage}% ({current_human}/{total_human})\n"
                             "<i>Скорость:</i> {speed_human}/s, <i>Осталось:</i> {remaining_human}",
        "uploading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Загружаю медиа:</b> {percentage}% ({current_human}/{total_human})\n"
                           "<i>Скорость:</i> {speed_human}/s, <i>Осталось:</i> {remaining_human}",
    }

    strings_ru = {
        "no_args": "<emoji document_id=5407001145740631266>🤐</emoji> <b>Пожалуйста, укажи ссылку на сообщение.</b>\n"
                   "<i>Пример:</i> <code>.mfw https://t.me/username/123</code>\n"
                   "или <code>.mfw https://t.me/c/123456789/123</code>,\n"
                   "<i>Для диапазона:</i> <code>.mfw https://t.me/username/123 https://t.me/username/125</code>",
        "invalid_link": "<emoji document_id=5121063440311386962>👎</emoji> <b>Неверный формат ссылки на сообщение.</b>",
        "too_many_links": "<emoji document_id=5121063440311386962>👎</emoji> <b>Укажите одну или две ссылки на сообщения.</b>",
        "same_channel_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Обе ссылки должны быть из одного канала.</b>",
        "invalid_id_range": "<emoji document_id=5121063440311386962>👎</emoji> <b>Начальное ID сообщения не может быть больше конечного.</b>",
        "fetching_message": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Получаю сообщение(я)...</b>",
        "message_not_found": "<emoji document_id=5913376703312302899>📣</emoji> <b>Сообщение(я) не найдено(ы) или недоступно(ы).</b> "
                             "<i>Убедись, что у тебя есть доступ к каналу и ссылка верна.</i>",
        "error_fetching": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при получении сообщения(й).</b>",
        "error_sending": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при отправке сообщения(й).</b>",
        "media_restricted": "<emoji document_id=5121063440311386962>👎</emoji> <b>Не удалось загрузить медиа из этого защищенного канала.</b> "
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
                "skrit_avtora",
                True,
                lambda: "Скрывать автора при пересылке",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "text_opisanie",
                False,
                lambda: "Удалять подписи к медиа при пересылке (для открытых каналов)",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "pachka",
                100,
                lambda: "Размер пачки сообщений для пересылки из открытых каналов",
                validator=loader.validators.Integer(minimum=1, maximum=100)
            ),
            loader.ConfigValue(
                "FW_DELAY",
                10,
                lambda: "Задержка между отправкой пачек сообщений (сек). Если вы пересылаете более 1к сообщений, лучше поставить 30+ секунд. ",
                validator=loader.validators.Integer(minimum=5, maximum=60)
            ),
        )
        self._last_progress_update_time = 0
        self._progress_update_interval_sec_fixed = 5

    async def client_ready(self, client, db):
        self.client = client

    def _humanize_bytes(self, num_bytes, suffix_str="B"):
        for unit_str in ["", "Ki", "Mi", "Gi", "T", "P", "E", "Z"]:
            if abs(num_bytes) < 1024.0:
                return f"{num_bytes:3.1f}{unit_str}{suffix_str}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f}Yi{suffix_str}"

    def _humanize_delta(self, seconds_total):
        if seconds_total < 60:
            return f"{seconds_total}s"
        if seconds_total < 3600:
            minutes_val = seconds_total // 60
            seconds_rem_val = seconds_total % 60
            return f"{minutes_val}m {seconds_rem_val}s"
        if seconds_total < 86400:
            hours_val = seconds_total // 3600
            minutes_rem_val = (seconds_total % 3600) // 60
            return f"{hours_val}h {minutes_rem_val}m"
        days_val = seconds_total // 86400
        hours_rem_val = (seconds_total % 86400) // 3600
        return f"{days_val}d {hours_rem_val}h"

    async def _progress_callback(self, current_bytes, total_bytes, status_msg_entity: Message, operation_start_time: float, action_str_key: str):
        if not total_bytes:
            return

        current_time_stamp = time.time()
        if current_time_stamp - self._last_progress_update_time < self._progress_update_interval_sec_fixed:
            return

        progress_percentage = f"{current_bytes * 100 / total_bytes:.1f}"
        time_elapsed = current_time_stamp - operation_start_time
        bytes_per_sec = current_bytes / time_elapsed if time_elapsed > 0 else 0
        time_remaining = (total_bytes - current_bytes) / bytes_per_sec if bytes_per_sec > 0 else 0

        speed_human_readable = self._humanize_bytes(bytes_per_sec)
        time_remaining_human_readable = self._humanize_delta(int(time_remaining))
        current_human_readable = self._humanize_bytes(current_bytes)
        total_human_readable = self._humanize_bytes(total_bytes)

        try:
            await status_msg_entity.edit(
                self.strings(action_str_key).format(
                    percentage=progress_percentage,
                    current_human=current_human_readable,
                    total_human=total_human_readable,
                    speed_human=speed_human_readable,
                    remaining_human=time_remaining_human_readable
                )
            )
            self._last_progress_update_time = current_time_stamp
        except errors.MessageNotModifiedError:
            pass
        except Exception as e:
            logger.debug(f"Failed to update progress message, it might have been deleted or another error: {e}")

    def _parse_single_link(self, input_link_str):
        link_pattern_match = re.match(r"https://t.me/(?:c/(\d+)|([^/]+))/(\d+)", input_link_str)
        if not link_pattern_match:
            return None, None, None

        source_entity_id = None
        message_id_parsed = None

        if link_pattern_match.group(1):
            try:
                channel_id_numeric = int(link_pattern_match.group(1))
                source_entity_id = int(f"-100{channel_id_numeric}")
                message_id_parsed = int(link_pattern_match.group(3))
            except ValueError:
                return None, None, None
        elif link_pattern_match.group(2):
            try:
                source_entity_id = link_pattern_match.group(2)
                message_id_parsed = int(link_pattern_match.group(3))
            except ValueError:
                return None, None, None
        
        return source_entity_id, message_id_parsed, input_link_str


    async def _send_single_message_restricted_flow(self, frw_target_msg: Message, frw_destination_peer_id, frw_reply_to_target_id, frw_status_message: Message):
        if frw_target_msg.media:
            try:
                frw_media_data_buffer = io.BytesIO()
                frw_media_filename = None
                
                frw_doc_attributes = [] # Инициализация здесь
                if hasattr(frw_target_msg.media, 'document') and frw_target_msg.media.document:
                    frw_doc_attributes = list(frw_target_msg.media.document.attributes) # Теперь присваивание в уже инициализированную
                    for frwd_attr in frw_doc_attributes: # Итерация по frw_doc_attributes
                        if isinstance(frwd_attr, DocumentAttributeFilename):
                            frw_media_filename = frwd_attr.file_name
                            break
                
                if not frw_media_filename:
                    if frw_target_msg.photo:
                        frw_media_filename = "photo.jpg"
                    elif frw_target_msg.video:
                        frw_media_filename = "video.mp4"
                    elif frw_target_msg.audio:
                        frw_media_filename = "audio.mp3"
                    elif frw_target_msg.document:
                        frw_media_filename = "document.bin"
                    else:
                        frw_media_filename = "media.bin"
                
                frw_media_data_buffer.name = frw_media_filename

                frw_dl_start_time = time.time()
                await self.client.download_media(
                    frw_target_msg,
                    file=frw_media_data_buffer,
                    progress_callback=lambda current, total: self._progress_callback(
                        current, total, frw_status_message, frw_dl_start_time, "downloading_media"
                    )
                )
                frw_media_data_buffer.seek(0)

                frw_force_doc_upload = True
                if frw_target_msg.photo or frw_target_msg.video:
                    frw_force_doc_upload = False
                    
                if not any(isinstance(frw_a, DocumentAttributeFilename) for frw_a in frw_doc_attributes): # Использование frw_doc_attributes
                    frw_doc_attributes.append(DocumentAttributeFilename(file_name=frw_media_filename))

                frw_up_start_time = time.time()
                await self.client.send_file(
                    frw_destination_peer_id, 
                    frw_media_data_buffer,
                    caption=frw_target_msg.text,
                    parse_mode='html',
                    link_preview=bool(frw_target_msg.web_preview),
                    reply_to=frw_reply_to_target_id,
                    attributes=frw_doc_attributes if frw_doc_attributes else None, # Использование frw_doc_attributes
                    force_document=frw_force_doc_upload,
                    progress_callback=lambda current, total: self._progress_callback(
                        current, total, frw_status_message, frw_up_start_time, "uploading_media"
                    )
                )
            except errors.ChatForwardsRestrictedError:
                raise 
            except Exception as e:
                logger.exception(e)
                raise 
        else:
            frw_message_text = frw_target_msg.text
            if len(frw_message_text) > 4096:
                frw_long_text_content = frw_message_text
                frw_long_text_buffer = io.BytesIO(frw_long_text_content.encode("utf-8"))
                frw_long_text_buffer.name = "message.txt"
                
                await self.client.send_file(
                    frw_destination_peer_id, 
                    frw_long_text_buffer,
                    caption="Оригинальное сообщение (слишком длинное для текста)",
                    reply_to=frw_reply_to_target_id
                )
            else:
                await self.client.send_message(
                    frw_destination_peer_id, 
                    frw_message_text,
                    parse_mode='html',
                    link_preview=bool(frw_target_msg.web_preview),
                    reply_to=frw_reply_to_target_id
                )

    @loader.command(
        ru_doc="<ссылка> [ссылка_конец] - Пересылает сообщение(я) по ссылке из канала. Если две ссылки - пересылает диапазон.",
        en_doc="<link> [link_end] - Forwards message(s) by link from a channel. If two links, forwards a range.",
        alias="mfw"
    )
    async def mfwcmd(self, original_message: Message):
        raw_input_args = utils.get_args_raw(original_message)
        if not raw_input_args:
            await utils.answer(original_message, self.strings("no_args"))
            return

        input_links_list = raw_input_args.split()

        if not (1 <= len(input_links_list) <= 2):
            await utils.answer(original_message, self.strings("too_many_links"))
            return

        source_chat_id, range_start_msg_id, _ = self._parse_single_link(input_links_list[0])
        
        if not source_chat_id or not range_start_msg_id:
            await utils.answer(original_message, self.strings("invalid_link"))
            return

        range_end_msg_id = range_start_msg_id

        if len(input_links_list) == 2:
            second_link_entity_id, second_link_message_id, _ = self._parse_single_link(input_links_list[1])
            
            if not second_link_entity_id or not second_link_message_id:
                await utils.answer(original_message, self.strings("invalid_link"))
                return
            
            if second_link_entity_id != source_chat_id:
                await utils.answer(original_message, self.strings("same_channel_needed"))
                return
            
            if second_link_message_id < range_start_msg_id:
                await utils.answer(original_message, self.strings("invalid_id_range"))
                return
            
            range_end_msg_id = second_link_message_id
            
        status_display_message = await utils.answer(original_message, self.strings("fetching_message"))

        try:
            source_chat_entity = await self.client.get_entity(source_chat_id)
            
            messages_to_process_list = []
            async for message_from_range in self.client.iter_messages(
                source_chat_entity,
                min_id=range_start_msg_id - 1,
                max_id=range_end_msg_id + 1,
                reverse=True
            ):
                if range_start_msg_id <= message_from_range.id <= range_end_msg_id:
                    messages_to_process_list.append(message_from_range)

            if not messages_to_process_list:
                await status_display_message.edit(self.strings("message_not_found"))
                return

            destination_peer_id = await self.client.get_input_entity(original_message.peer_id)
            target_reply_to_id = original_message.reply_to_msg_id if original_message.reply_to_msg_id else original_message.id
            
            message_ids_for_batch = [msg.id for msg in messages_to_process_list]
            
            reply_to_top_message_id = None
            if original_message.reply_to and hasattr(original_message.reply_to, 'reply_to_top_id'):
                reply_to_top_message_id = original_message.reply_to.reply_to_top_id

            batch_size_config = self.config["pachka"]
            batch_delay_config = self.config["FW_DELAY"]

            try:
                for batch_index in range(0, len(message_ids_for_batch), batch_size_config):
                    current_batch_message_ids = message_ids_for_batch[batch_index:batch_index + batch_size_config]
                    
                    await self.client(functions.messages.ForwardMessagesRequest(
                        from_peer=source_chat_entity,
                        id=current_batch_message_ids,
                        to_peer=destination_peer_id,
                        drop_author=self.config["skrit_avtora"],
                        drop_media_captions=self.config["text_opisanie"],
                        top_msg_id=reply_to_top_message_id,
                    ))

                    if batch_index + batch_size_config < len(message_ids_for_batch):
                        await asyncio.sleep(batch_delay_config)

            except errors.ChatForwardsRestrictedError as e:
                logger.warning(f"Обнаружен защищенный канал, переключаюсь на метод скачивания. Ошибка: {e}")
                for message_to_send_restricted in messages_to_process_list:
                    await self._send_single_message_restricted_flow(
                        frw_target_msg=message_to_send_restricted,
                        frw_destination_peer_id=original_message.peer_id, 
                        frw_reply_to_target_id=target_reply_to_id,
                        frw_status_message=status_display_message
                    )
            except errors.FloodWaitError as e:
                flood_wait_seconds = e.seconds if e.seconds is not None else 60
                logger.warning(f"FloodWaitError: {flood_wait_seconds}s for open channel batch. Retrying after delay.")
                await asyncio.sleep(flood_wait_seconds + 5)
                
                pass 
            except Exception as e:
                logger.exception(e)
                await status_display_message.edit(self.strings("error_sending"))
                return

            await status_display_message.delete()

        except errors.RPCError as e:
            logger.exception(e)
            await status_display_message.edit(self.strings("error_fetching"))
        except Exception as e:
            logger.exception(e)
            await status_display_message.edit(self.strings("error_sending"))
