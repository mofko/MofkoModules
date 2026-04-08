__version__ = (1, 3, 0)
# diff: улучшение стабильности
# meta developer: @mofkomodules
# Name: M:Forward
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_469.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_469.png
# meta fhsdesc: forward, mofko, tool, пересылка, copy, копирование, топики

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
    Модуль для пересылки сообщений (Поддерживает каналы с запретом пересылки и топики). 
    Также имеет функцию "бекапа", путём пересылки всех сообщений из одного канала в другой. 
    Смотреть конфиг ОБЯЗАТЕЛЬНО.
    """
    strings = {
        "name": "M:Forward",
        "_cls_doc": "Модуль для пересылки сообщений (Поддерживает каналы с запретом пересылки и топики). Также имеет функцию \"бекапу\", путём пересылки всех сообщений из одного канала в другой. Смотреть конфиг ОБЯЗАТЕЛЬНО.",
        "no_args": "<emoji document_id=5407001145740631266>🤐</emoji> <b>Пожалуйста, укажи ссылку на сообщение.</b>\n"
                   "<i>Пример:</i> <code>.mfw https://t.me/username/123</code>\n"
                   "или <code>.mfw https://t.me/c/123456789/123</code>,\n"
                   "<i>Для диапазона:</i> <code>.mfw https://t.me/username/123 https://t.me/username/125</code>",
        "invalid_link": "<emoji document_id=5121063440311386962>👎</emoji> <b>Неверный формат ссылки на сообщение.</b>",
        "too_many_links": "<emoji document_id=5121063440311386962>👎</emoji> <b>Укажите одну или две ссылки на сообщения.</b>",
        "same_channel_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Обе ссылки должны быть из одного канала.</b>",
        "same_topic_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Обе ссылки должны быть из одной темы.</b>",
        "invalid_id_range": "<emoji document_id=5121063440311386962>👎</emoji> <b>Начальное ID сообщения не может быть больше конечного.</b>",
        "fetching_message": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Получаю сообщение(я)...</b>",
        "message_not_found": "<emoji document_id=5913376703312302899>📣</emoji> <b>Сообщение(я) не найдено(ы) или недоступно(ы).</b> "
                             "<i>Убедись, что у тебя есть доступ к каналу и ссылка верна.</i>",
        "error_fetching": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при получении сообщения(й).</b>",
        "error_sending": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ошибка при отправке сообщения(й).</b>",
        "downloading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Скачиваю медиа:</b> {percentage}% ({current_human}/{total_human})\n"
                             "<i>Скорость:</i> {speed_human}/s, <i>Осталось:</i> {remaining_human}",
        "uploading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Загружаю медиа:</b> {percentage}% ({current_human}/{total_human})\n"
                           "<i>Скорость:</i> {speed_human}/s, <i>Осталось:</i> {remaining_human}",
        "forward_complete": "<emoji document_id=5206607081334906820>✔️</emoji> <b>Пересылка завершена!</b>\n\n<emoji document_id=5870921681735781843>📊</emoji> <b>Итоги:</b>\nСообщений: {count}\nВремя: {duration}",
        "_cfg_skrit_avtora_doc": "Скрывать автора при пересылке",
        "_cfg_text_opisanie_doc": "Удалять подписи к медиа при пересылке (для открытых каналов)",
        "_cfg_pachka_doc": "Размер пачки сообщений для пересылки из открытых каналов",
        "_cfg_fw_delay_doc": "Задержка между отправкой пачек сообщений (сек). Если вы пересылаете более 1к сообщений, лучше поставить 30+ секунд. ",
    }

    strings_en = {
        "name": "M:Forward",
        "_cls_doc": "Module for forwarding messages (Supports channels with restricted forwarding and topics). Also includes a \"backup\" function, by forwarding all messages from one channel to another. Configuration is MANDATORY.",
        "no_args": "<emoji document_id=5407001145740631266>🤐</emoji> <b>Please provide a message link.</b>\n"
                   "<i>Example:</i> <code>.mfw https://t.me/username/123</code>\n"
                   "or <code>.mfw https://t.me/c/123456789/123</code>,\n"
                   "<i>For a range:</i> <code>.mfw https://t.me/username/123 https://t.me/username/125</code>",
        "invalid_link": "<emoji document_id=5121063440311386962>👎</emoji> <b>Invalid message link format.</b>",
        "too_many_links": "<emoji document_id=5121063440311386962>👎</emoji> <b>Specify one or two message links.</b>",
        "same_channel_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Both links must be from the same channel.</b>",
        "same_topic_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Both links must be from the same topic.</b>",
        "invalid_id_range": "<emoji document_id=5121063440311386962>👎</emoji> <b>Start message ID cannot be greater than end message ID.</b>",
        "fetching_message": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Fetching message(s)...</b>",
        "message_not_found": "<emoji document_id=5913376703312302899>📣</emoji> <b>Message(s) not found or inaccessible.</b> "
                             "<i>Ensure you have access to the channel and the link is correct.</i>",
        "error_fetching": "<emoji document_id=5121063440311386962>👎</emoji> <b>Error fetching message(s).</b>",
        "error_sending": "<emoji document_id=5121063440311386962>👎</emoji> <b>Error sending message(s).</b>",
        "downloading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Downloading media:</b> {percentage}% ({current_human}/{total_human})\n"
                             "<i>Speed:</i> {speed_human}/s, <i>Remaining:</i> {remaining_human}",
        "uploading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Uploading media:</b> {percentage}% ({current_human}/{total_human})\n"
                           "<i>Speed:</i> {speed_human}/s, <i>Remaining:</i> {remaining_human}",
        "forward_complete": "<emoji document_id=5206607081334906820>✔️</emoji> <b>Forwarding complete!</b>\n\n<emoji document_id=5870921681735781843>📊</emoji> <b>Summary:</b>\nMessages: {count}\nTime: {duration}",
        "_cfg_skrit_avtora_doc": "Hide author on forwarding",
        "_cfg_text_opisanie_doc": "Remove media captions on forwarding (for open channels)",
        "_cfg_pachka_doc": "Batch size for forwarding messages from open channels",
        "_cfg_fw_delay_doc": "Delay between sending message batches (sec). If you forward more than 1k messages, it's better to set 30+ seconds. ",
    }

    strings_ua = {
        "name": "M:Forward",
        "_cls_doc": "Модуль для пересилання повідомлень (Підтримує канали із забороною пересилання та топіки). Також має функцію \"бекапу\", шляхом пересилання всіх повідомлень з одного каналу до іншого. Переглянути конфіг ОБОВ'ЯЗКОВО.",
        "no_args": "<emoji document_id=5407001145740631266>🤐</emoji> <b>Будь ласка, вкажіть посилання на повідомлення.</b>\n"
                   "<i>Приклад:</i> <code>.mfw https://t.me/username/123</code>\n"
                   "або <code>.mfw https://t.me/c/123456789/123</code>,\n"
                   "<i>Для діапазону:</i> <code>.mfw https://t.me/username/123 https://t.me/username/125</code>",
        "invalid_link": "<emoji document_id=5121063440311386962>👎</emoji> <b>Невірний формат посилання на повідомлення.</b>",
        "too_many_links": "<emoji document_id=5121063440311386962>👎</emoji> <b>Вкажіть одне або два посилання на повідомлення.</b>",
        "same_channel_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Обидва посилання повинні бути з одного каналу.</b>",
        "same_topic_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Обидва посилання повинні бути з однієї теми.</b>",
        "invalid_id_range": "<emoji document_id=5121063440311386962>👎</emoji> <b>Початковий ID повідомлення не може бути більшим за кінцевий.</b>",
        "fetching_message": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Отримую повідомлення(я)...</b>",
        "message_not_found": "<emoji document_id=5913376703312302899>📣</emoji> <b>Повідомлення(я) не знайдено(і) або недоступно(і).</b> "
                             "<i>Переконайтеся, що маєте доступ до каналу і посилання правильне.</i>",
        "error_fetching": "<emoji document_id=5121063440311386962>👎</emoji> <b>Помилка під час отримання повідомлення(й).</b>",
        "error_sending": "<emoji document_id=5121063440311386962>👎</emoji> <b>Помилка під час надсилання повідомлення(й).</b>",
        "downloading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Завантажую медіа:</b> {percentage}% ({current_human}/{total_human})\n"
                             "<i>Швидкість:</i> {speed_human}/s, <i>Залишилось:</i> {remaining_human}",
        "uploading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Відправляю медіа:</b> {percentage}% ({current_human}/{total_human})\n"
                           "<i>Швидкість:</i> {speed_human}/s, <i>Залишилось:</i> {remaining_human}",
        "forward_complete": "<emoji document_id=5206607081334906820>✔️</emoji> <b>Пересилання завершено!</b>\n\n<emoji document_id=5870921681735781843>📊</emoji> <b>Підсумок:</b>\nПовідомлень: {count}\nЧас: {duration}",
        "_cfg_skrit_avtora_doc": "Приховувати автора при пересиланні",
        "_cfg_text_opisanie_doc": "Видаляти підписи до медіа при пересиланні (для відкритих каналів)",
        "_cfg_pachka_doc": "Розмір пачки повідомлень для пересилання з відкритих каналів",
        "_cfg_fw_delay_doc": "Затримка між відправкою пачок повідомлень (сек). Якщо ви пересилаєте більше 1к повідомлень, краще встановити 30+ секунд. ",
    }

    strings_de = {
        "name": "M:Forward",
        "_cls_doc": "Modul zum Weiterleiten von Nachrichten (Unterstützt Kanäle mit eingeschränkter Weiterleitung und Themen). Beinhaltet auch eine \"Backup\"-Funktion, indem alle Nachrichten von einem Kanal in einen anderen weitergeleitet werden. Konfiguration ist ZWINGEND ERFORDERLICH.",
        "no_args": "<emoji document_id=5407001145740631266>🤐</emoji> <b>Bitte geben Sie einen Nachrichtenlink an.</b>\n"
                   "<i>Beispiel:</i> <code>.mfw https://t.me/username/123</code>\n"
                   "oder <code>.mfw https://t.me/c/123456789/123</code>,\n"
                   "<i>Für einen Bereich:</i> <code>.mfw https://t.me/username/123 https://t.me/username/125</code>",
        "invalid_link": "<emoji document_id=5121063440311386962>👎</emoji> <b>Ungültiges Nachrichtenlinkformat.</b>",
        "too_many_links": "<emoji document_id=5121063440311386962>👎</emoji> <b>Geben Sie ein oder zwei Nachrichtenlinks an.</b>",
        "same_channel_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Beide Links müssen vom selben Kanal stammen.</b>",
        "same_topic_needed": "<emoji document_id=5121063440311386962>👎</emoji> <b>Beide Links müssen aus demselben Thema stammen.</b>",
        "invalid_id_range": "<emoji document_id=5121063440311386962>👎</emoji> <b>Die Startnachrichten-ID darf nicht größer sein als die Endnachrichten-ID.</b>",
        "fetching_message": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Nachricht(en) wird/werden abgerufen...</b>",
        "message_not_found": "<emoji document_id=5913376703312302899>📣</emoji> <b>Nachricht(en) nicht gefunden oder nicht zugänglich.</b> "
                             "<i>Stellen Sie sicher, dass Sie Zugriff auf den Kanal haben und der Link korrekt ist.</i>",
        "error_fetching": "<emoji document_id=5121063440311386962>👎</emoji> <b>Fehler beim Abrufen der Nachricht(en).</b>",
        "error_sending": "<emoji document_id=5121063440311386962>👎</emoji> <b>Fehler beim Senden der Nachricht(en).</b>",
        "downloading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Medien werden heruntergeladen:</b> {percentage}% ({current_human}/{total_human})\n"
                             "<i>Geschwindigkeit:</i> {speed_human}/s, <i>Verbleibend:</i> {remaining_human}",
        "uploading_media": "<emoji document_id=5325543345760509967>🔄</emoji> <b>Medien werden hochgeladen:</b> {percentage}% ({current_human}/{total_human})\n"
                           "<i>Geschwindigkeit:</i> {speed_human}/s, <i>Verbleibend:</i> {remaining_human}",
        "forward_complete": "<emoji document_id=5206607081334906820>✔️</emoji> <b>Weiterleitung abgeschlossen!</b>\n\n<emoji document_id=5870921681735781843>📊</emoji> <b>Zusammenfassung:</b>\nNachrichten: {count}\nZeit: {duration}",
        "_cfg_skrit_avtora_doc": "Autor beim Weiterleiten ausblenden",
        "_cfg_text_opisanie_doc": "Medienunterschriften beim Weiterleiten entfernen (für offene Kanäle)",
        "_cfg_pachka_doc": "Batch-Größe für das Weiterleiten von Nachrichten aus offenen Kanälen",
        "_cfg_fw_delay_doc": "Verzögerung zwischen dem Senden von Nachrichten-Batches (Sek.). Wenn Sie mehr als 1.000 Nachrichten weiterleiten, ist es besser, 30+ Sekunden einzustellen. ",
    }
    
    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "skrit_avtora",
                True,
                lambda: self.strings["_cfg_skrit_avtora_doc"],
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "text_opisanie",
                False,
                lambda: self.strings["_cfg_text_opisanie_doc"],
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "pachka",
                100,
                lambda: self.strings["_cfg_pachka_doc"],
                validator=loader.validators.Integer(minimum=1, maximum=100)
            ),
            loader.ConfigValue(
                "FW_DELAY",
                10,
                lambda: self.strings["_cfg_fw_delay_doc"],
                validator=loader.validators.Integer(minimum=5, maximum=60)
            ),
        )
        self._last_progress_update_time = 0
        self._progress_update_interval_sec_fixed = 5
        self._pinned_msg_data = None
        self._forward_start_time = None

    async def client_ready(self, client, db):
        self.client = client
        self._db_delete("forward_state")
        pinned_data = self.db.get(__name__, "pinned_forward_msg", None)
        if pinned_data:
            try:
                pinned_peer = await self._resolve_stored_peer(pinned_data["peer_id"])
                await self.client(functions.messages.UpdatePinnedMessageRequest(
                    peer=pinned_peer,
                    id=0,
                    silent=True,
                ))
                self._db_delete("pinned_forward_msg")
                logger.info("Unpinned old forward message after crash")
            except Exception as e:
                logger.debug(f"Could not unpin after crash: {e}")
        
        fw_state = None
        if fw_state:
            logger.info(f"Found incomplete forward operation. Progress: {fw_state.get('processed', 0)}/{fw_state.get('total', 0)}")
            return
            await self.client.send_message(
                fw_state["destination_peer_id"],
                f"<emoji document_id=5870921681735781843>📊</emoji> Обнаружена незавершённая пересылка!\n"
                f"Сообщений: {fw_state.get('processed', 0)}/{fw_state.get('total', 0)}\n"
                f"Чтобы продолжить — выполните команду:\n"
                f"<code>.mfw {fw_state.get('source_url', '')}</code>"
            )

    async def on_unload(self):
        self._last_progress_update_time = 0
        pinned_data = self.db.get(__name__, "pinned_forward_msg", None)
        if pinned_data:
            try:
                pinned_peer = await self._resolve_stored_peer(pinned_data["peer_id"])
                await self.client(functions.messages.UpdatePinnedMessageRequest(
                    peer=pinned_peer,
                    id=0,
                    silent=True,
                ))
                self._db_delete("pinned_forward_msg")
            except Exception:
                pass

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
            logger.exception(e)

    async def _safe_edit_status(self, status_msg_entity: Message, text: str):
        try:
            await status_msg_entity.edit(text)
        except Exception as e:
            logger.exception(e)

    async def _safe_delete_message(self, message: Message):
        try:
            await message.delete()
        except Exception as e:
            logger.exception(e)

    def _make_operation_key(self, source_url: str, destination_chat_id: int) -> str:
        normalized_source = " ".join(source_url.split())
        digest = hashlib.sha1(
            f"{destination_chat_id}:{normalized_source}".encode("utf-8")
        ).hexdigest()[:16]
        return f"forward_{digest}"

    async def _resolve_stored_peer(self, chat_id: int):
        try:
            return await self.client.get_input_entity(chat_id)
        except Exception as first_error:
            if isinstance(chat_id, int) and chat_id > 0:
                try:
                    return await self.client.get_input_entity(int(f"-100{chat_id}"))
                except Exception:
                    logger.exception(first_error)
                    raise
            logger.exception(first_error)
            raise

    def _store_forward_state(
        self,
        operation_key: str,
        destination_chat_id: int,
        source_url: str,
        total: int,
        processed_batch_index: int,
        start_time: float,
    ):
        return

    def _clear_forward_state(self, operation_key: str):
        return

    def _db_delete(self, key: str):
        self.db.set(__name__, key, None)

    def _build_message_link(self, source_entity, message_id: int, topic_id: int = None) -> str | None:
        if not message_id:
            return None
        username = getattr(source_entity, "username", None)
        if username:
            if topic_id:
                return f"https://t.me/{username}/{topic_id}/{message_id}"
            return f"https://t.me/{username}/{message_id}"
        source_id = getattr(source_entity, "id", None)
        if not source_id:
            return None
        if topic_id:
            return f"https://t.me/c/{source_id}/{topic_id}/{message_id}"
        return f"https://t.me/c/{source_id}/{message_id}"

    def _get_resume_text(self, fw_state: dict) -> str:
        processed = int(fw_state.get("processed", 0))
        total = int(fw_state.get("total", 0))
        source_url = utils.escape_html(fw_state.get("source_url", ""))
        return (
            "<emoji document_id=5870921681735781843>📊</emoji> <b>Обнаружена незавершённая пересылка.</b>\n\n"
            f"<b>Прогресс:</b> {processed}/{total}\n"
            f"<b>Источник:</b>\n<code>{source_url}</code>\n\n"
            "Нажмите кнопку ниже, чтобы продолжить."
        )

    def _get_resume_fallback_text(self, fw_state: dict) -> str:
        source_url = utils.escape_html(fw_state.get("source_url", ""))
        return (
            f"{self._get_resume_text(fw_state)}\n\n"
            "Если кнопка недоступна, выполните:\n"
            f"<code>.mfw {source_url}</code>"
        )

    async def _delayed_resume_prompt(self, fw_state: dict):
        try:
            await asyncio.sleep(3)
            await self._show_resume_prompt(fw_state)
        except Exception as e:
            logger.exception(e)

    async def _show_resume_prompt(self, fw_state: dict):
        chat_id = fw_state.get("destination_peer_id")
        if not chat_id or not fw_state.get("source_url") or not fw_state.get("operation_key"):
            if fw_state.get("operation_key"):
                self._clear_forward_state(fw_state["operation_key"])
            else:
                self._db_delete("forward_state")
            return
        try:
            target_peer = await self._resolve_stored_peer(chat_id)
        except Exception as e:
            logger.exception(e)
            if fw_state.get("operation_key"):
                self._clear_forward_state(fw_state["operation_key"])
            else:
                self._db_delete("forward_state")
            return
        try:
            prompt_message = await self.client.send_message(
                target_peer,
                self._get_resume_text(fw_state),
                parse_mode="html",
            )
        except Exception as e:
            logger.exception(e)
            return
        try:
            await self.inline.form(
                text=self._get_resume_text(fw_state),
                message=prompt_message,
                reply_markup=[
                    [
                        {
                            "text": "Продолжить",
                            "callback": self._resume_forward_callback,
                            "args": (fw_state["operation_key"],),
                            "style": "success",
                        },
                        {"text": "Закрыть", "action": "close", "style": "danger"},
                    ]
                ],
            )
        except Exception as e:
            logger.exception(e)
            try:
                await prompt_message.edit(
                    self._get_resume_fallback_text(fw_state),
                    parse_mode="html",
                )
            except Exception as fallback_error:
                logger.exception(fallback_error)

    async def _resume_forward_callback(self, call, operation_key: str):
        fw_state = self.db.get(__name__, "forward_state", None)
        if not fw_state or fw_state.get("operation_key") != operation_key or not fw_state.get("source_url"):
            try:
                await call.edit("❌ Состояние незавершённой пересылки не найдено.")
            except Exception as e:
                logger.exception(e)
            return

        destination_chat_id = fw_state.get("destination_peer_id")
        source_url = fw_state.get("source_url")

        try:
            await call.delete()
        except Exception:
            pass

        destination_peer = await self._resolve_stored_peer(destination_chat_id)
        resume_message = await self.client.send_message(destination_peer, "<emoji document_id=5325543345760509967>🔄</emoji> Продолжаю пересылку...", parse_mode="html")
        try:
            await self.invoke("mfw", source_url, message=resume_message)
        except Exception as e:
            logger.exception(e)
            await utils.answer(resume_message, self.strings("error_sending"))

    async def _update_progress_batch(self, status_msg: Message, batch_num: int, total_batches: int, messages_processed: int, total_messages: int, start_time: float, last_message_link: str = None, batch_delay_seconds: int = 0):
        elapsed = time.time() - start_time
        eta_seconds = (elapsed / messages_processed) * (total_messages - messages_processed) if messages_processed > 0 else 0
        eta_seconds += max(total_batches - batch_num, 0) * max(batch_delay_seconds, 0)
        eta_str = self._humanize_delta(int(eta_seconds))
        last_message_block = ""
        if last_message_link:
            safe_link = utils.escape_html(last_message_link)
            last_message_block = (
                "\n\n"
                f"<emoji document_id=5258503720928288433>ℹ️</emoji> <b>Последнее сообщение:</b>\n"
                f"<a href=\"{safe_link}\">{safe_link}</a>"
            )
        progress_text = (
            f"<emoji document_id=5873225338984599714>📤</emoji> <b>Пересылка в процессе</b>\n"
            f"Пачка: {batch_num}/{total_batches}\n"
            f"Сообщений: {messages_processed}/{total_messages}\n"
            f"<emoji document_id=5870921681735781843>📊</emoji> Прогресс: {messages_processed*100//total_messages}%\n"
            f"<emoji document_id=5258258882022612173>⏲️</emoji> Осталось: {eta_str}"
            f"{last_message_block}"
        )
        await self._safe_edit_status(status_msg, progress_text)

    async def _send_summary(self, destination_peer_id, total_messages: int, start_time: float):
        elapsed = time.time() - start_time
        duration_str = self._humanize_delta(int(elapsed))
        speed = elapsed / total_messages if total_messages > 0 else 0
        
        summary_text = self.strings("forward_complete").format(
            count=total_messages,
            duration=duration_str,
            speed=f"{speed:.1f}s"
        )
        
        try:
            await self.client.send_message(destination_peer_id, summary_text, parse_mode='html')
        except Exception as e:
            logger.exception(e)

    def _parse_single_link(self, input_link_str):
        link_pattern_match = re.match(r"https://t.me/(?:c/(\d+)|([^/]+))/(?:(\d+)/)?(\d+)", input_link_str)
        if not link_pattern_match:
            return None, None, None, None

        source_entity_id = None
        topic_id_parsed = None
        message_id_parsed = None

        if link_pattern_match.group(1): 
            try:
                channel_id_numeric = int(link_pattern_match.group(1))
                source_entity_id = int(f"-100{channel_id_numeric}")
                if link_pattern_match.group(3):
                    topic_id_parsed = int(link_pattern_match.group(3))
                    message_id_parsed = int(link_pattern_match.group(4))
                else:
                    message_id_parsed = int(link_pattern_match.group(4))
            except ValueError:
                return None, None, None, None
        elif link_pattern_match.group(2): 
            try:
                source_entity_id = link_pattern_match.group(2)
                if link_pattern_match.group(3):
                    topic_id_parsed = int(link_pattern_match.group(3))
                    message_id_parsed = int(link_pattern_match.group(4))
                else:
                    message_id_parsed = int(link_pattern_match.group(4))
            except ValueError:
                return None, None, None, None
        
        return source_entity_id, message_id_parsed, topic_id_parsed, input_link_str


    async def _send_single_message_restricted_flow(self, frw_target_msg: Message, frw_destination_peer_id, frw_reply_to_target_id, frw_status_message: Message):
        if frw_target_msg.media:
            try:
                frw_media_data_buffer = io.BytesIO()
                frw_media_filename = None
                
                frw_doc_attributes = [] 
                if hasattr(frw_target_msg.media, 'document') and frw_target_msg.media.document:
                    frw_doc_attributes = list(frw_target_msg.media.document.attributes) 
                    for frwd_attr in frw_doc_attributes:
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
                    
                if not any(isinstance(frw_a, DocumentAttributeFilename) for frw_a in frw_doc_attributes):
                    frw_doc_attributes.append(DocumentAttributeFilename(file_name=frw_media_filename))

                frw_up_start_time = time.time()
                await self.client.send_file(
                    frw_destination_peer_id, 
                    frw_media_data_buffer,
                    caption=frw_target_msg.text if frw_target_msg.text else None,
                    parse_mode='html',
                    link_preview=bool(frw_target_msg.web_preview),
                    reply_to=frw_reply_to_target_id,
                    attributes=frw_doc_attributes if frw_doc_attributes else None,
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
            frw_message_text = frw_target_msg.text or frw_target_msg.raw_text or "\u2063"
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
        ru_doc="<ссылка> [ссылка_конец] - Пересылает сообщение по ссылке. Если две ссылки - пересылает диапазон.",
        en_doc="<link> [link_end] - Forwards message(s) by link. If two links, forwards a range.",
        ua_doc="<посилання> [посилання_кінець] - Пересилає повідомлення за посиланням. Якщо два посилання - пересилає діапазон.",
        de_doc="<link> [link_ende] - Leitet Nachricht(en) per Link weiter. Bei zwei Links wird ein Bereich weitergeleitet.",
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

        source_chat_id, range_start_msg_id, source_topic_id_from_link, _ = self._parse_single_link(input_links_list[0])
        
        if not source_chat_id or not range_start_msg_id:
            await utils.answer(original_message, self.strings("invalid_link"))
            return

        range_end_msg_id = range_start_msg_id

        if len(input_links_list) == 2:
            second_link_entity_id, second_link_message_id, second_link_topic_id, _ = self._parse_single_link(input_links_list[1])
            
            if not second_link_entity_id or not second_link_message_id:
                await utils.answer(original_message, self.strings("invalid_link"))
                return
            
            if second_link_entity_id != source_chat_id:
                await utils.answer(original_message, self.strings("same_channel_needed"))
                return

            if second_link_topic_id != source_topic_id_from_link:
                await utils.answer(original_message, self.strings("same_topic_needed"))
                return
            
            if second_link_message_id < range_start_msg_id:
                await utils.answer(original_message, self.strings("invalid_id_range"))
                return
            
            range_end_msg_id = second_link_message_id
            
        status_display_message = await utils.answer(original_message, self.strings("fetching_message"))

        try:
            source_chat_entity = await self.client.get_entity(source_chat_id)
            
            messages_to_process_list = []
            iter_messages_kwargs = {
                "min_id": range_start_msg_id - 1,
                "max_id": range_end_msg_id + 1,
                "reverse": True
            }
            if isinstance(source_chat_entity, Channel) and source_chat_entity.forum and source_topic_id_from_link:
                iter_messages_kwargs["reply_to"] = source_topic_id_from_link

            last_update_time = time.time()
            async for message_from_range in self.client.iter_messages(
                source_chat_entity,
                **iter_messages_kwargs
            ):
                if range_start_msg_id <= message_from_range.id <= range_end_msg_id:
                    messages_to_process_list.append(message_from_range)
                
                current_time = time.time()
                if current_time - last_update_time > 2:
                    await self._safe_edit_status(
                        status_display_message,
                        f"<emoji document_id=5870921681735781843>📊</emoji> Загружено сообщений: {len(messages_to_process_list)}"
                    )
                    last_update_time = current_time

            if not messages_to_process_list:
                await status_display_message.edit(self.strings("message_not_found"))
                return

            destination_chat_id = getattr(original_message, "chat_id", None) or utils.get_chat_id(original_message)
            destination_peer_id = await self.client.get_input_entity(destination_chat_id)
            target_reply_to_id_value = original_message.reply_to_msg_id
            
            reply_to_top_message_id = getattr(
                original_message.reply_to,
                "reply_to_top_id",
                None,
            ) if original_message.reply_to else None

            batch_size_config = self.config["pachka"]
            batch_delay_config = self.config["FW_DELAY"]
            
            operation_key = ""
            saved_state = None
            stale_operation_key = None
            batch_start_index = 0
            operation_start_time = time.time()
            
            if saved_state and saved_state.get("total") == len(messages_to_process_list):
                batch_start_index = saved_state.get("processed_batch_index", 0)
                await utils.answer(
                    status_display_message,
                    f"<emoji document_id=5325543345760509967>🔄</emoji> Продолжаю пересылку!\nПачка: {batch_start_index // batch_size_config + 1}/{(len(messages_to_process_list) + batch_size_config - 1) // batch_size_config}"
                )
                logger.info(f"Resuming forward operation from batch {batch_start_index}")
            self._store_forward_state(
                operation_key,
                destination_chat_id,
                raw_input_args,
                len(messages_to_process_list),
                batch_start_index,
                operation_start_time,
            )
            if stale_operation_key:
                self._db_delete(stale_operation_key)
            
            self._forward_start_time = operation_start_time
            try:
                await self.client(functions.messages.UpdatePinnedMessageRequest(
                    peer=destination_peer_id,
                    id=status_display_message.id,
                    silent=True,
                ))
                self.db.set(__name__, "pinned_forward_msg", {
                    "peer_id": destination_chat_id,
                    "msg_id": status_display_message.id
                })
            except Exception:
                pass

            try:
                for batch_index in range(batch_start_index, len(messages_to_process_list), batch_size_config):
                    current_batch_messages = messages_to_process_list[batch_index:batch_index + batch_size_config]
                    current_batch_message_ids = [msg.id for msg in current_batch_messages]

                    while True:
                        try:
                            await self.client(functions.messages.ForwardMessagesRequest(
                                from_peer=source_chat_entity,
                                id=current_batch_message_ids,
                                to_peer=destination_peer_id,
                                drop_author=self.config["skrit_avtora"],
                                drop_media_captions=self.config["text_opisanie"],
                                top_msg_id=reply_to_top_message_id,
                            ))
                            
                            self._store_forward_state(
                                operation_key,
                                destination_chat_id,
                                raw_input_args,
                                len(messages_to_process_list),
                                min(batch_index + batch_size_config, len(messages_to_process_list)),
                                operation_start_time,
                            )
                            break
                        except errors.FloodWaitError as e:
                            flood_wait_seconds = e.seconds if e.seconds is not None else 60
                            logger.warning(f"FloodWaitError: {flood_wait_seconds}s for open channel batch. Retrying after delay.")
                            await self._safe_edit_status(
                                status_display_message,
                                f"FloodWait: {flood_wait_seconds}s. Retrying..."
                            )
                            await asyncio.sleep(flood_wait_seconds + 5)

                    messages_processed = min(batch_index + batch_size_config, len(messages_to_process_list))
                    total_batches = (len(messages_to_process_list) + batch_size_config - 1) // batch_size_config
                    current_batch_num = (batch_index // batch_size_config) + 1
                    last_message_link = self._build_message_link(
                        source_chat_entity,
                        current_batch_messages[-1].id if current_batch_messages else None,
                        source_topic_id_from_link,
                    )
                    await self._update_progress_batch(
                        status_display_message,
                        current_batch_num,
                        total_batches,
                        messages_processed,
                        len(messages_to_process_list),
                        self._forward_start_time,
                        last_message_link,
                        batch_delay_config,
                    )

                    if batch_index + batch_size_config < len(messages_to_process_list):
                        await asyncio.sleep(batch_delay_config)

            except (errors.ChatForwardsRestrictedError, errors.MessageIdInvalidError) as e:
                logger.warning(f"Обнаружен защищенный канал или недопустимый ID сообщения, переключаюсь на метод скачивания. Ошибка: {type(e).__name__}")
                for processed_index, message_to_send_restricted_flow in enumerate(messages_to_process_list[batch_start_index:], start=batch_start_index + 1):
                    while True:
                        try:
                            await self._send_single_message_restricted_flow(
                                frw_target_msg=message_to_send_restricted_flow,
                                frw_destination_peer_id=original_message.peer_id, 
                                frw_reply_to_target_id=target_reply_to_id_value,
                                frw_status_message=status_display_message
                            )
                            self._store_forward_state(
                                operation_key,
                                destination_chat_id,
                                raw_input_args,
                                len(messages_to_process_list),
                                processed_index,
                                operation_start_time,
                            )
                            break
                        except errors.FloodWaitError as e:
                            flood_wait_seconds = e.seconds if e.seconds is not None else 60
                            await self._safe_edit_status(
                                status_display_message,
                                f"FloodWait: {flood_wait_seconds}s. Retrying..."
                            )
                            await asyncio.sleep(flood_wait_seconds + 5)
            except Exception as e:
                logger.exception(e)
                await status_display_message.edit(self.strings("error_sending"))
                try:
                    await self.client(functions.messages.UpdatePinnedMessageRequest(
                        peer=destination_peer_id, id=0, silent=True,
                    ))
                    self._db_delete("pinned_forward_msg")
                except Exception:
                    pass
                return

            try:
                await self.client(functions.messages.UpdatePinnedMessageRequest(
                    peer=destination_peer_id,
                    id=0,
                    silent=True,
                ))
                self._db_delete("pinned_forward_msg")
            except Exception:
                pass
            
            self._clear_forward_state(operation_key)
            await self._send_summary(original_message.peer_id, len(messages_to_process_list), self._forward_start_time)
            await self._safe_delete_message(status_display_message)

        except errors.RPCError as e:
            logger.exception(e)
            pinned_data = self.db.get(__name__, "pinned_forward_msg", None)
            if pinned_data:
                try:
                    pinned_peer = await self._resolve_stored_peer(pinned_data["peer_id"])
                    await self.client(functions.messages.UpdatePinnedMessageRequest(
                        peer=pinned_peer,
                        id=0,
                        silent=True,
                    ))
                    self._db_delete("pinned_forward_msg")
                except Exception:
                    pass
            await status_display_message.edit(self.strings("error_fetching"))
        except Exception as e:
            logger.exception(e)
            pinned_data = self.db.get(__name__, "pinned_forward_msg", None)
            if pinned_data:
                try:
                    pinned_peer = await self._resolve_stored_peer(pinned_data["peer_id"])
                    await self.client(functions.messages.UpdatePinnedMessageRequest(
                        peer=pinned_peer,
                        id=0,
                        silent=True,
                    ))
                    self._db_delete("pinned_forward_msg")
                except Exception:
                    pass
            await status_display_message.edit(self.strings("error_sending"))
