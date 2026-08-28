# scope: heroku_min 2.1.0
# meta developer: @mofkomodules
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/m_forward_banner.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/m_forward_banner.png
# meta fhsdesc: forward, forwarding, messages, tool, пересылка, mofko
# meta tags: forward, forwarding, messages, tool, пересылка, mofko

__version__ = (2, 1, 0)
# diff: Update strings en

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import secrets
import time

from herokutl import utils as tl_utils
from herokutl.errors import RPCError
from herokutl.errors.rpcerrorlist import FloodWaitError
from herokutl.tl import functions, types
from herokutl.tl.types import (
    InputBotInlineMessageID,
    InputBotInlineMessageID64,
    Message,
)

from .. import loader, utils


logger = logging.getLogger(__name__)

_LINK_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?t\.me/(?:s/)?(?:(c)/)?"
    r"([A-Za-z0-9_+-]+)(?:/(\d+))?(?:/(\d+))?/?$",
    re.IGNORECASE,
)
_EMOJI = {
    "main": "<tg-emoji emoji-id=5445371412900508977>💬</tg-emoji>",
    "source": '<tg-emoji emoji-id="5444965220663458467">📁</tg-emoji>',
    "target": '<tg-emoji emoji-id="6035191085452497972">👤</tg-emoji>',
    "type": '<tg-emoji emoji-id="4904936030232117798">⚙️</tg-emoji>',
    "progress": '<tg-emoji emoji-id="5870921681735781843">📊</tg-emoji>',
    "time": '<tg-emoji emoji-id="5983150113483134607">🕐</tg-emoji>',
    "ok": '<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji>',
    "error": '<tg-emoji emoji-id="5121063440311386962">👎</tg-emoji>',
}
_FILTERS = {
    "all": "📨",
    "text": "📝",
    "media": "📎",
    "photo": "🖼",
    "video": "🎬",
    "audio": "🎵",
    "voice": "🎙",
    "file": "📁",
    "gif": "🎞",
    "sticker": "🧩",
    "inline": "🤖",
}


class _ForwardStopped(Exception):
    pass


class _ForwardProtected(Exception):
    pass


@loader.tds
class MForwardMod(loader.Module):
    """Forward messages within a selected range."""

    strings = {
        "name": "M:Forward",
        "_cls_doc": "Forward messages within a selected range.",
        "_cmd_doc_mfw": "Open the forwarding menu.",
        "source_missing": "Source is not specified",
        "source_invalid": "Could not recognize the source",
        "source_not_found": "Source chat was not found",
        "target_missing": "Target is not specified",
        "target_invalid": "Could not recognize the target",
        "target_not_found": "Target chat was not found",
        "target_unselected": "not selected",
        "source_unselected": "not selected",
        "topic": "topic",
        "range_unset": "not set",
        "range_latest": "latest",
        "status_hidden": "hidden",
        "status_shown": "shown",
        "status_removed": "removed",
        "status_kept": "kept",
        "status_removing": "removed",
        "status_keeping": "kept",
        "messages_label": "Messages",
        "menu_text": (
            "{main} <b>M:Forward</b>\n\n<blockquote expandable>"
            "{source_emoji} <b>Source (From):</b> {source}\n"
            "{target_emoji} <b>Target:</b> {target}\n"
            "{progress} <b>Range:</b> {range}\n"
            "{type_emoji} <b>Type:</b> {filter}\n"
            "<b>Author:</b> {author} · <b>Text:</b> {captions}{messages}</blockquote>{notice}"
        ),
        "menu_source": "📥 Source (From)",
        "menu_source_input": "Enter a message or chat link:",
        "menu_target": "🎯 Target",
        "menu_range": "🔢 Range",
        "menu_type": "📎 Type",
        "menu_options": "⚙️ Options",
        "menu_jobs": "📋 Jobs · {}",
        "btn_start": "▶️ Start",
        "btn_reset": "🔄 Reset",
        "btn_close": "✖️ Close",
        "btn_back": "⬅️ Back",
        "menu_expired": "Menu has expired",
        "protected_source": "Choose a channel where forwarding is allowed",
        "target_title": "{emoji} <b>Forwarding target</b>",
        "target_description": "Target is the chat or topic where messages will be forwarded.",
        "target_topic_help": (
            "<blockquote expandable><b>How to specify a topic:</b>\n"
            "<code>@chat 123</code> or <code>@chat:123</code>\n"
            "<code>https://t.me/chat/123</code>\n"
            "<code>https://t.me/c/1234567890/123</code>\n\n"
            "The link must contain the ID of the topic's first message.</blockquote>"
        ),
        "btn_edit": "✏️ Edit",
        "target_input": "Enter chat_id, @username, or a chat/topic link:",
        "btn_current_chat": "↩️ Current chat",
        "source_required": "Choose a source first",
        "range_title": "{emoji} <b>Range</b>",
        "range_text": "<blockquote><b>Start:</b> <code>{start}</code>\n<b>End:</b> <code>{end}</code></blockquote>",
        "btn_range_start": "🔢 Start",
        "range_start_input": "Enter the ID or link of the first message:",
        "btn_range_end": "🏁 End",
        "range_end_input": "Enter the ID or link of the last message:",
        "btn_range_single": "1️⃣ One message",
        "btn_range_latest": "⏭ To latest",
        "range_other_source": "The message must be from the selected source",
        "range_id_positive": "ID must be greater than zero",
        "range_end_before_start": "The final ID is less than the first one",
        "type_title": "{emoji} <b>Forwarding type</b>",
        "type_selected": "<blockquote>Selected: <b>{}</b></blockquote>",
        "options_title": "{emoji} <b>Forwarding options</b>",
        "options_text": "<blockquote><b>Author:</b> {author}\n<b>Text:</b> {captions}{extra}</blockquote>",
        "options_messages": "\n<b>Text messages:</b> {}",
        "btn_author": "👤 Author: {}",
        "btn_captions": "💬 Text: {}",
        "btn_messages": "📝 Messages: {}",
        "jobs_title": "{emoji} <b>Jobs</b>",
        "jobs_empty": "<blockquote>No jobs</blockquote>",
        "job_queued": "queued",
        "job_running": "running",
        "job_stopping": "stopping",
        "job_paused": "paused",
        "btn_stop_number": "🛑 Stop {}",
        "btn_refresh": "🔄 Refresh",
        "source_required_start": "Choose a source",
        "target_required_start": "Choose a target",
        "queue_full": "Queue is full",
        "range_empty": "There are no messages in the selected range",
        "job_added": "Job added",
        "duration_hours": "{}h {}m",
        "duration_minutes": "{}m {}s",
        "duration_seconds": "{}s",
        "job_state_queued": "Queued · {}",
        "job_state_flood": "FloodWait · {}",
        "job_state_stopping": "Stopping",
        "job_state_done": "Completed",
        "job_state_stopped": "Stopped",
        "job_state_error": "Error",
        "job_state_paused": "Paused",
        "job_state_running": "Running",
        "job_pin_failed": "\n⚠️ Could not pin progress",
        "job_text": (
            "{main} <b>M:Forward</b>\n<b>{state}</b>\n\n"
            "<blockquote expandable>{source_emoji} <b>Source (From):</b> {source}\n"
            "{target_emoji} <b>Target:</b> {target}\n"
            "{type_emoji} <b>Type:</b> {filter}\n"
            "<b>Author:</b> {author} · <b>Text:</b> {captions}\n{messages}"
            "<b>Range:</b> <code>{start} → {end}</code>\n\n{bar} <b>{percent}%</b>\n"
            "Forwarded: <code>{forwarded}</code>\nSkipped: <code>{skipped}</code>\n"
            "Speed: <code>{speed:.1f}/min</code>\nRemaining: <code>{eta}</code>\n"
            "FloodWait: <code>{flood}</code>{extra}</blockquote>"
        ),
        "job_messages": "<b>Text messages:</b> {}\n",
        "btn_resume": "▶️ Resume",
        "btn_pause": "⏸ Pause",
        "btn_stop": "🛑 Stop",
        "job_finished": "Job has already finished",
        "job_paused_notice": "Paused",
        "job_resumed_notice": "Resumed",
        "job_stopping_notice": "Stopping",
        "job_protected": "Forwarding is prohibited in the source",
        "filter_all": "All",
        "filter_text": "Text",
        "filter_media": "Media",
        "filter_photo": "Photo",
        "filter_video": "Video",
        "filter_audio": "Music",
        "filter_voice": "Voice messages",
        "filter_file": "Files",
        "filter_gif": "GIF",
        "filter_sticker": "Stickers",
        "filter_inline": "Inline",
    }

    strings_ru = {
        "name": "M:Forward",
        "_cls_doc": "Пересылает сообщения в выбранном диапазоне.",
        "_cmd_doc_mfw": "Открыть меню пересылки.",
        "source_missing": "Источник не указан",
        "source_invalid": "Не удалось распознать источник",
        "source_not_found": "Чат источника не найден",
        "target_missing": "Цель не указана",
        "target_invalid": "Не удалось распознать цель",
        "target_not_found": "Целевой чат не найден",
        "target_unselected": "не выбрана",
        "source_unselected": "не выбран",
        "topic": "топик",
        "range_unset": "не задан",
        "range_latest": "последнее",
        "status_hidden": "скрыт",
        "status_shown": "показан",
        "status_removed": "убран",
        "status_kept": "сохранён",
        "status_removing": "убираются",
        "status_keeping": "сохраняются",
        "messages_label": "Сообщения",
        "menu_text": (
            "{main} <b>M:Forward</b>\n\n<blockquote expandable>"
            "{source_emoji} <b>Источник (Откуда):</b> {source}\n"
            "{target_emoji} <b>Цель:</b> {target}\n"
            "{progress} <b>Диапазон:</b> {range}\n"
            "{type_emoji} <b>Тип:</b> {filter}\n"
            "<b>Автор:</b> {author} · <b>Текст:</b> {captions}{messages}</blockquote>{notice}"
        ),
        "menu_source": "📥 Источник (Откуда)",
        "menu_source_input": "Введите ссылку на сообщение или чат:",
        "menu_target": "🎯 Цель",
        "menu_range": "🔢 Диапазон",
        "menu_type": "📎 Тип",
        "menu_options": "⚙️ Параметры",
        "menu_jobs": "📋 Задачи · {}",
        "btn_start": "▶️ Запустить",
        "btn_reset": "🔄 Сбросить",
        "btn_close": "✖️ Закрыть",
        "btn_back": "⬅️ Назад",
        "menu_expired": "Меню устарело",
        "protected_source": "Выберите канал, где доступна пересылка",
        "target_title": "{emoji} <b>Цель пересылки</b>",
        "target_description": "Цель — чат или топик, куда будут пересылаться сообщения.",
        "target_topic_help": (
            "<blockquote expandable><b>Как указать топик:</b>\n"
            "<code>@chat 123</code> или <code>@chat:123</code>\n"
            "<code>https://t.me/chat/123</code>\n"
            "<code>https://t.me/c/1234567890/123</code>\n\n"
            "В ссылке должен быть ID первого сообщения топика.</blockquote>"
        ),
        "btn_edit": "✏️ Изменить",
        "target_input": "Введите chat_id, @username или ссылку на чат/топик:",
        "btn_current_chat": "↩️ Текущий чат",
        "source_required": "Сначала выберите источник",
        "range_title": "{emoji} <b>Диапазон</b>",
        "range_text": "<blockquote><b>Начало:</b> <code>{start}</code>\n<b>Конец:</b> <code>{end}</code></blockquote>",
        "btn_range_start": "🔢 Начало",
        "range_start_input": "Введите ID или ссылку на начальное сообщение:",
        "btn_range_end": "🏁 Конец",
        "range_end_input": "Введите ID или ссылку на конечное сообщение:",
        "btn_range_single": "1️⃣ Одно сообщение",
        "btn_range_latest": "⏭ До последнего",
        "range_other_source": "Сообщение должно быть из выбранного источника",
        "range_id_positive": "ID должен быть больше нуля",
        "range_end_before_start": "Конечный ID меньше начального",
        "type_title": "{emoji} <b>Тип пересылки</b>",
        "type_selected": "<blockquote>Выбрано: <b>{}</b></blockquote>",
        "options_title": "{emoji} <b>Параметры пересылки</b>",
        "options_text": "<blockquote><b>Автор:</b> {author}\n<b>Текст:</b> {captions}{extra}</blockquote>",
        "options_messages": "\n<b>Текстовые сообщения:</b> {}",
        "btn_author": "👤 Автор: {}",
        "btn_captions": "💬 Текст: {}",
        "btn_messages": "📝 Сообщения: {}",
        "jobs_title": "{emoji} <b>Задачи</b>",
        "jobs_empty": "<blockquote>Нет задач</blockquote>",
        "job_queued": "ожидает",
        "job_running": "выполняется",
        "job_stopping": "останавливается",
        "job_paused": "пауза",
        "btn_stop_number": "🛑 Остановить {}",
        "btn_refresh": "🔄 Обновить",
        "source_required_start": "Выберите источник",
        "target_required_start": "Выберите цель",
        "queue_full": "Очередь заполнена",
        "range_empty": "В диапазоне нет сообщений",
        "job_added": "Задача добавлена",
        "duration_hours": "{}ч {}м",
        "duration_minutes": "{}м {}с",
        "duration_seconds": "{}с",
        "job_state_queued": "В очереди · {}",
        "job_state_flood": "FloodWait · {}",
        "job_state_stopping": "Останавливается",
        "job_state_done": "Завершено",
        "job_state_stopped": "Остановлено",
        "job_state_error": "Ошибка",
        "job_state_paused": "Пауза",
        "job_state_running": "Выполняется",
        "job_pin_failed": "\n⚠️ Не удалось закрепить прогресс",
        "job_text": (
            "{main} <b>M:Forward</b>\n<b>{state}</b>\n\n"
            "<blockquote expandable>{source_emoji} <b>Источник (Откуда):</b> {source}\n"
            "{target_emoji} <b>Цель:</b> {target}\n"
            "{type_emoji} <b>Тип:</b> {filter}\n"
            "<b>Автор:</b> {author} · <b>Текст:</b> {captions}\n{messages}"
            "<b>Диапазон:</b> <code>{start} → {end}</code>\n\n{bar} <b>{percent}%</b>\n"
            "Переслано: <code>{forwarded}</code>\nПропущено: <code>{skipped}</code>\n"
            "Скорость: <code>{speed:.1f}/мин</code>\nОсталось: <code>{eta}</code>\n"
            "FloodWait: <code>{flood}</code>{extra}</blockquote>"
        ),
        "job_messages": "<b>Текстовые сообщения:</b> {}\n",
        "btn_resume": "▶️ Продолжить",
        "btn_pause": "⏸ Пауза",
        "btn_stop": "🛑 Остановить",
        "job_finished": "Задача уже завершена",
        "job_paused_notice": "Пауза",
        "job_resumed_notice": "Продолжено",
        "job_stopping_notice": "Останавливаю",
        "job_protected": "У источника запрещена пересылка",
        "filter_all": "Всё",
        "filter_text": "Текст",
        "filter_media": "Медиа",
        "filter_photo": "Фото",
        "filter_video": "Видео",
        "filter_audio": "Музыка",
        "filter_voice": "Голосовые",
        "filter_file": "Файлы",
        "filter_gif": "GIF",
        "filter_sticker": "Стикеры",
        "filter_inline": "Инлайн",
    }

    def __init__(self):
        self._menus = {}
        self._jobs = {}
        self._queue = asyncio.Queue()
        self._pause_events = {}
        self._worker_task = None
        self._active_job_id = None

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        stored = self.get("jobs", {})
        self._jobs = stored if isinstance(stored, dict) else {}
        for job_id, job in sorted(
            list(self._jobs.items()),
            key=lambda item: item[1].get("created", 0),
        ):
            if not isinstance(job, dict) or job.get("status") in {
                "done",
                "error",
                "stopped",
            }:
                self._jobs.pop(job_id, None)
                continue
            job["filters"] = self._normalize_filters(
                job.pop("filter", job.get("filters", ["all"]))
            )
            job.setdefault("hide_author", True)
            job.setdefault("remove_captions", False)
            job.setdefault("remove_text_messages", False)
            job.setdefault(
                "target_ref",
                self._peer_reference(
                    job.get("target_peer"),
                    job.get("target_topic"),
                ),
            )
            if job.get("status") in {"running", "flood", "stopping"}:
                job["status"] = "queued"
            event = asyncio.Event()
            if not job.get("paused"):
                event.set()
            self._pause_events[job_id] = event
            self._queue.put_nowait(job_id)
        self._save_jobs()
        for job in self._jobs.values():
            await self._edit_job(job, True)
        self._worker_task = asyncio.create_task(self._worker())

    async def on_unload(self):
        self._save_jobs()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

    def _save_jobs(self):
        self.set("jobs", self._jobs)

    @staticmethod
    def _pack_inline_id(value):
        if isinstance(value, (InputBotInlineMessageID, InputBotInlineMessageID64)):
            return value.to_json()
        return value

    @staticmethod
    def _unpack_inline_id(value):
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            return value
        if not isinstance(data, dict):
            return value
        if data.get("_") == "InputBotInlineMessageID":
            return InputBotInlineMessageID(
                dc_id=data["dc_id"],
                id=data["id"],
                access_hash=data["access_hash"],
            )
        if data.get("_") == "InputBotInlineMessageID64":
            return InputBotInlineMessageID64(
                dc_id=data["dc_id"],
                owner_id=data["owner_id"],
                id=data["id"],
                access_hash=data["access_hash"],
            )
        return value

    @staticmethod
    def _call_source(call):
        source_id = getattr(call, "form", {}).get("inline_message_id")
        if source_id:
            call.inline_message_id = source_id
        return call

    @staticmethod
    def _topic_from_message(message):
        reply = getattr(message, "reply_to", None)
        if not reply:
            return None
        return (
            getattr(reply, "reply_to_top_id", None)
            or (
                getattr(reply, "reply_to_msg_id", None)
                if getattr(reply, "forum_topic", False)
                else None
            )
        )

    @staticmethod
    def _entity_title(entity):
        return (
            getattr(entity, "title", None)
            or getattr(entity, "first_name", None)
            or getattr(entity, "username", None)
            or str(getattr(entity, "id", "—"))
        )

    @staticmethod
    def _peer_id(entity):
        return int(tl_utils.get_peer_id(entity))

    @staticmethod
    def _peer_reference(peer, topic=None, username=None):
        if username:
            value = f"https://t.me/{username}"
        else:
            value = str(peer)
            if value.startswith("-100"):
                value = f"https://t.me/c/{value[4:]}"
        if topic:
            separator = "/" if value.startswith("https://t.me/") else ":"
            value = f"{value}{separator}{topic}"
        return value

    @staticmethod
    def _is_forum(entity):
        return bool(getattr(entity, "forum", False))

    @staticmethod
    def _normalize_filters(value):
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            return ["all"]
        result = [item for item in value if item in _FILTERS]
        result = list(dict.fromkeys(result))
        if not result or "all" in result:
            return ["all"]
        return result

    async def _resolve_entity(self, value, private=False):
        value = str(value).strip()
        variants = []
        if private and value.lstrip("-").isdigit():
            value = value.lstrip("-")
            variants.append(int(f"-100{value}"))
        elif value.lstrip("-").isdigit():
            variants.append(int(value))
            digits = value.lstrip("-")
            if not value.startswith("-100") and len(digits) >= 9:
                variants.append(int(f"-100{digits}"))
        else:
            variants.append(value.lstrip("@"))
        for variant in variants:
            with contextlib.suppress(Exception):
                return await self.client.get_entity(variant)
        return None

    async def _get_message(self, entity, message_id):
        with contextlib.suppress(Exception):
            result = await self.client.get_messages(entity, ids=int(message_id))
            if isinstance(result, (list, tuple)):
                return result[0] if result else None
            return result
        return None

    async def _source_is_protected(self, entity, message=None):
        if getattr(entity, "noforwards", False) or getattr(
            message,
            "noforwards",
            False,
        ):
            return True
        try:
            async for recent in self.client.iter_messages(entity, limit=3):
                if getattr(recent, "noforwards", False):
                    return True
        except Exception:
            pass
        return False

    async def _parse_source(self, raw):
        raw = str(raw or "").strip()
        if not raw:
            raise ValueError(self.strings("source_missing"))
        match = _LINK_RE.match(raw)
        private = False
        identifier = None
        first = None
        second = None
        if match:
            private = bool(match.group(1))
            identifier = match.group(2)
            first = int(match.group(3)) if match.group(3) else None
            second = int(match.group(4)) if match.group(4) else None
        else:
            parts = raw.split()
            if len(parts) > 3:
                raise ValueError(self.strings("source_invalid"))
            identifier = parts[0]
            numbers = [int(part) for part in parts[1:] if part.isdigit()]
            if len(numbers) == 1:
                first = numbers[0]
            elif len(numbers) == 2:
                first, second = numbers
        entity = await self._resolve_entity(identifier, private)
        if not entity:
            raise ValueError(self.strings("source_not_found"))
        channel_only = first is None and second is None
        topic_id = first if second is not None else None
        message_id = second or first or 1
        message = (
            None
            if channel_only
            else await self._get_message(entity, message_id)
        )
        if self._is_forum(entity) and topic_id is None and message:
            topic_id = self._topic_from_message(message)
        if await self._source_is_protected(entity, message):
            raise _ForwardProtected
        return {
            "peer": self._peer_id(entity),
            "title": self._entity_title(entity),
            "topic": int(topic_id) if topic_id else None,
            "message": int(message_id),
            "channel_only": channel_only,
        }

    async def _parse_target(self, raw):
        raw = str(raw or "").strip()
        if not raw:
            raise ValueError(self.strings("target_missing"))
        match = _LINK_RE.match(raw)
        private = False
        identifier = None
        first = None
        second = None
        if match:
            private = bool(match.group(1))
            identifier = match.group(2)
            first = int(match.group(3)) if match.group(3) else None
            second = int(match.group(4)) if match.group(4) else None
        elif ":" in raw and not raw.lower().startswith(("http://", "https://")):
            identifier, topic = raw.rsplit(":", 1)
            first = int(topic) if topic.isdigit() else None
        else:
            parts = raw.split()
            if len(parts) > 2:
                raise ValueError(self.strings("target_invalid"))
            identifier = parts[0]
            first = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None
        entity = await self._resolve_entity(identifier, private)
        if not entity:
            raise ValueError(self.strings("target_not_found"))
        topic_id = first if self._is_forum(entity) else None
        if second is not None:
            topic_id = first
        return {
            "peer": self._peer_id(entity),
            "title": self._entity_title(entity),
            "topic": int(topic_id) if topic_id else None,
            "reference": self._peer_reference(
                self._peer_id(entity),
                topic_id,
                getattr(entity, "username", None),
            ),
        }

    async def _latest_id(self, peer, topic):
        entity = await self.client.get_entity(peer)
        kwargs = {"limit": 1}
        if topic:
            kwargs["reply_to"] = topic
        result = await self.client.get_messages(entity, **kwargs)
        if isinstance(result, (list, tuple)):
            message = result[0] if result else None
        else:
            message = result
        return int(getattr(message, "id", 0) or 0)

    def _filter_label(self, filter_type):
        return self.strings(f"filter_{filter_type}")

    def _display_target(self, data):
        if not data:
            return self.strings("target_unselected")
        value = utils.escape_html(str(data["title"]))
        reference = data.get("reference")
        if reference:
            value += f" (<code>{utils.escape_html(str(reference))}</code>)"
        return value

    def _display_source(self, data):
        if not data:
            return self.strings("source_unselected")
        value = utils.escape_html(str(data["title"]))
        if data.get("topic"):
            value += f" · {self.strings('topic')} <code>{data['topic']}</code>"
        return value

    def _menu_text(self, state):
        source = self._display_source(state.get("source"))
        target = self._display_target(state.get("target"))
        if not state.get("source"):
            range_text = self.strings("range_unset")
        elif state["range_mode"] == "latest":
            range_text = f"<code>{state['start']}</code> → {self.strings('range_latest')}"
        else:
            range_text = f"<code>{state['start']}</code> → <code>{state['end']}</code>"
        filter_name = ", ".join(self._filter_label(item) for item in state["filters"])
        author = self.strings("status_hidden") if state["hide_author"] else self.strings("status_shown")
        captions = self.strings("status_removed") if state["remove_captions"] else self.strings("status_kept")
        text_messages = (
            self.strings("status_removing")
            if state["remove_text_messages"]
            else self.strings("status_keeping")
        )
        notice = ""
        if state.get("notice"):
            notice = (
                f"\n\n{_EMOJI['error']} "
                f"<b>{utils.escape_html(state['notice'])}</b>"
            )
        messages = (
            f" · <b>{self.strings('messages_label')}:</b> {text_messages}"
            if state["remove_captions"]
            else ""
        )
        return self.strings("menu_text").format(
            main=_EMOJI["main"],
            source_emoji=_EMOJI["source"],
            target_emoji=_EMOJI["target"],
            progress=_EMOJI["progress"],
            type_emoji=_EMOJI["type"],
            source=source,
            target=target,
            range=range_text,
            filter=utils.escape_html(filter_name),
            author=author,
            captions=captions,
            messages=messages,
            notice=notice,
        )

    def _menu_markup(self, token):
        rows = [
            [
                {
                    "text": self.strings("menu_source"),
                    "input": self.strings("menu_source_input"),
                    "handler": self._source_input,
                    "args": (token,),
                },
                {
                    "text": self.strings("menu_target"),
                    "callback": self._target_menu,
                    "args": (token,),
                    "style": "primary",
                },
            ],
            [
                {
                    "text": self.strings("menu_range"),
                    "callback": self._range_menu,
                    "args": (token,),
                },
                {
                    "text": self.strings("menu_type"),
                    "callback": self._type_menu,
                    "args": (token,),
                },
            ],
            [
                {
                    "text": self.strings("menu_options"),
                    "callback": self._options_menu,
                    "args": (token,),
                }
            ],
        ]
        if self._jobs:
            rows.append(
                [
                    {
                        "text": self.strings("menu_jobs").format(len(self._jobs)),
                        "callback": self._jobs_menu,
                        "args": (token,),
                    }
                ]
            )
        rows.extend(
            [
                [
                    {
                        "text": self.strings("btn_start"),
                        "callback": self._start,
                        "args": (token,),
                        "style": "success",
                    }
                ],
                [
                    {
                        "text": self.strings("btn_reset"),
                        "callback": self._reset,
                        "args": (token,),
                    },
                    {
                        "text": self.strings("btn_close"),
                        "callback": self._close,
                        "args": (token,),
                        "style": "danger",
                    },
                ],
            ]
        )
        return rows

    async def _render_main(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        call = self._call_source(call)
        await call.edit(
            self._menu_text(state),
            reply_markup=self._menu_markup(token),
        )

    async def _input_error(self, call, token, text):
        state = self._menus.get(token)
        if not state:
            return
        state["notice"] = text
        with contextlib.suppress(Exception):
            await call.answer(text, show_alert=False)
        await self._render_main(call, token)
        await asyncio.sleep(2)
        state = self._menus.get(token)
        if state and state.get("notice") == text:
            state["notice"] = None
            with contextlib.suppress(Exception):
                await self._render_main(call, token)

    async def _source_input(self, call, query, token):
        call = self._call_source(call)
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        if not str(query or "").strip() and state.get("source"):
            state["notice"] = None
            return await self._render_main(call, token)
        try:
            source = await self._parse_source(query)
        except _ForwardProtected:
            return await self._input_error(
                call,
                token,
                self.strings("protected_source"),
            )
        except Exception as error:
            return await self._input_error(call, token, str(error))
        state["notice"] = None
        state["source"] = source
        state["start"] = source["message"]
        state["end"] = source["message"]
        state["range_mode"] = (
            "latest" if source.get("channel_only") else "fixed"
        )
        await self._render_main(call, token)

    async def _target_menu(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        call = self._call_source(call)
        text = "\n\n".join(
            (
                self.strings("target_title").format(emoji=_EMOJI["target"]),
                f"<blockquote>{self._display_target(state.get('target'))}</blockquote>",
                self.strings("target_description"),
                self.strings("target_topic_help"),
            )
        )
        await call.edit(
            text,
            reply_markup=[
                [
                    {
                        "text": self.strings("btn_edit"),
                        "input": self.strings("target_input"),
                        "handler": self._target_input,
                        "args": (token,),
                    }
                ],
                [
                    {
                        "text": self.strings("btn_current_chat"),
                        "callback": self._target_current,
                        "args": (token,),
                    }
                ],
                [
                    {
                        "text": self.strings("btn_back"),
                        "callback": self._render_main,
                        "args": (token,),
                        "style": "primary",
                    },
                    {
                        "text": self.strings("btn_close"),
                        "callback": self._close,
                        "args": (token,),
                        "style": "danger",
                    },
                ],
            ],
        )

    async def _target_input(self, call, query, token):
        call = self._call_source(call)
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        if not str(query or "").strip() and state.get("target"):
            state["notice"] = None
            return await self._render_main(call, token)
        try:
            state["target"] = await self._parse_target(query)
        except Exception as error:
            return await self._input_error(call, token, str(error))
        state["notice"] = None
        await self._render_main(call, token)

    async def _target_current(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        state["target"] = dict(state["default_target"])
        state["notice"] = None
        await self._render_main(call, token)

    async def _range_menu(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        if not state.get("source"):
            return await call.answer(self.strings("source_required"), show_alert=True)
        call = self._call_source(call)
        end = self.strings("range_latest") if state["range_mode"] == "latest" else str(state["end"])
        text = "\n\n".join(
            (
                self.strings("range_title").format(emoji=_EMOJI["progress"]),
                self.strings("range_text").format(start=state["start"], end=end),
            )
        )
        await call.edit(
            text,
            reply_markup=[
                [
                    {
                        "text": self.strings("btn_range_start"),
                        "input": self.strings("range_start_input"),
                        "handler": self._range_start_input,
                        "args": (token,),
                    },
                    {
                        "text": self.strings("btn_range_end"),
                        "input": self.strings("range_end_input"),
                        "handler": self._range_end_input,
                        "args": (token,),
                    },
                ],
                [
                    {
                        "text": self.strings("btn_range_single"),
                        "callback": self._range_single,
                        "args": (token,),
                    },
                    {
                        "text": self.strings("btn_range_latest"),
                        "callback": self._range_latest,
                        "args": (token,),
                    },
                ],
                [
                    {
                        "text": self.strings("btn_back"),
                        "callback": self._render_main,
                        "args": (token,),
                        "style": "primary",
                    },
                    {
                        "text": self.strings("btn_close"),
                        "callback": self._close,
                        "args": (token,),
                        "style": "danger",
                    },
                ],
            ],
        )

    async def _range_value(self, query, state):
        query = str(query or "").strip()
        if query.isdigit():
            return int(query)
        source = await self._parse_source(query)
        current = state["source"]
        if source["peer"] != current["peer"] or source.get("topic") != current.get(
            "topic"
        ):
            raise ValueError(self.strings("range_other_source"))
        return source["message"]

    async def _range_start_input(self, call, query, token):
        call = self._call_source(call)
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        if not str(query or "").strip():
            state["notice"] = None
            return await self._range_menu(call, token)
        try:
            value = await self._range_value(query, state)
            if value < 1:
                raise ValueError(self.strings("range_id_positive"))
        except _ForwardProtected:
            return await self._input_error(
                call,
                token,
                self.strings("protected_source"),
            )
        except Exception as error:
            return await self._input_error(call, token, str(error))
        state["notice"] = None
        state["start"] = value
        if state["range_mode"] != "latest" and state["end"] < value:
            state["end"] = value
        await self._range_menu(call, token)

    async def _range_end_input(self, call, query, token):
        call = self._call_source(call)
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        if not str(query or "").strip():
            state["notice"] = None
            return await self._range_menu(call, token)
        try:
            value = await self._range_value(query, state)
            if value < state["start"]:
                raise ValueError(self.strings("range_end_before_start"))
        except _ForwardProtected:
            return await self._input_error(
                call,
                token,
                self.strings("protected_source"),
            )
        except Exception as error:
            return await self._input_error(call, token, str(error))
        state["notice"] = None
        state["end"] = value
        state["range_mode"] = "fixed"
        await self._range_menu(call, token)

    async def _range_single(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        state["end"] = state["start"]
        state["range_mode"] = "fixed"
        await self._range_menu(call, token)

    async def _range_latest(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        state["range_mode"] = "latest"
        await self._range_menu(call, token)

    async def _type_menu(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        call = self._call_source(call)
        rows = []
        row = []
        for key, icon in _FILTERS.items():
            selected = key in state["filters"]
            row.append(
                {
                    "text": f"{'✅' if selected else icon} {self._filter_label(key)}",
                    "callback": self._set_type,
                    "args": (token, key),
                    "style": "success" if selected else None,
                }
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append(
            [
                {
                    "text": self.strings("btn_back"),
                    "callback": self._render_main,
                    "args": (token,),
                    "style": "primary",
                },
                {
                    "text": self.strings("btn_close"),
                    "callback": self._close,
                    "args": (token,),
                    "style": "danger",
                },
            ]
        )
        await call.edit(
            "\n\n".join(
                (
                    self.strings("type_title").format(emoji=_EMOJI["type"]),
                    self.strings("type_selected").format(
                        utils.escape_html(
                            ", ".join(self._filter_label(item) for item in state["filters"])
                        )
                    ),
                )
            ),
            reply_markup=rows,
        )

    async def _set_type(self, call, token, filter_type):
        state = self._menus.get(token)
        if not state or filter_type not in _FILTERS:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        selected = list(state["filters"])
        if filter_type == "all":
            selected = ["all"]
        else:
            selected = [item for item in selected if item != "all"]
            if filter_type in selected:
                selected.remove(filter_type)
            else:
                selected.append(filter_type)
            if not selected:
                selected = ["all"]
        state["filters"] = selected
        await self._type_menu(call, token)

    async def _options_menu(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        call = self._call_source(call)
        author = self.strings("status_hidden") if state["hide_author"] else self.strings("status_shown")
        captions = self.strings("status_removed") if state["remove_captions"] else self.strings("status_kept")
        text_messages = (
            self.strings("status_removing")
            if state["remove_text_messages"]
            else self.strings("status_keeping")
        )
        extra = (
            self.strings("options_messages").format(text_messages)
            if state["remove_captions"]
            else ""
        )
        rows = [
            [
                {
                    "text": self.strings("btn_author").format(author),
                    "callback": self._toggle_author,
                    "args": (token,),
                }
            ],
            [
                {
                    "text": self.strings("btn_captions").format(captions),
                    "callback": self._toggle_captions,
                    "args": (token,),
                }
            ],
        ]
        if state["remove_captions"]:
            rows.append(
                [
                    {
                        "text": self.strings("btn_messages").format(text_messages),
                        "callback": self._toggle_text_messages,
                        "args": (token,),
                    }
                ]
            )
        rows.append(
            [
                {
                    "text": self.strings("btn_back"),
                    "callback": self._render_main,
                    "args": (token,),
                    "style": "primary",
                },
                {
                    "text": self.strings("btn_close"),
                    "callback": self._close,
                    "args": (token,),
                    "style": "danger",
                },
            ]
        )
        await call.edit(
            "\n\n".join(
                (
                    self.strings("options_title").format(emoji=_EMOJI["type"]),
                    self.strings("options_text").format(
                        author=author,
                        captions=captions,
                        extra=extra,
                    ),
                )
            ),
            reply_markup=rows,
        )

    async def _toggle_author(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        state["hide_author"] = not state["hide_author"]
        if not state["hide_author"]:
            state["remove_captions"] = False
            state["remove_text_messages"] = False
        await self._options_menu(call, token)

    async def _toggle_captions(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        state["remove_captions"] = not state["remove_captions"]
        if state["remove_captions"]:
            state["hide_author"] = True
        else:
            state["remove_text_messages"] = False
        await self._options_menu(call, token)

    async def _toggle_text_messages(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        if not state["remove_captions"]:
            state["remove_text_messages"] = False
        else:
            state["remove_text_messages"] = not state[
                "remove_text_messages"
            ]
        await self._options_menu(call, token)

    async def _reset(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        state.update(
            {
                "source": None,
                "start": 1,
                "end": 1,
                "range_mode": "fixed",
                "filters": ["all"],
                "hide_author": True,
                "remove_captions": False,
                "remove_text_messages": False,
                "notice": None,
                "target": dict(state["default_target"]),
            }
        )
        await self._render_main(call, token)

    async def _close(self, call, token):
        self._menus.pop(token, None)
        with contextlib.suppress(Exception):
            await call.delete()

    def _jobs_text(self):
        if not self._jobs:
            return "\n\n".join(
                (
                    self.strings("jobs_title").format(emoji=_EMOJI["progress"]),
                    self.strings("jobs_empty"),
                )
            )
        lines = []
        labels = {
            "queued": self.strings("job_queued"),
            "running": self.strings("job_running"),
            "flood": "FloodWait",
            "stopping": self.strings("job_stopping"),
        }
        for index, job in enumerate(
            sorted(self._jobs.values(), key=lambda item: item.get("created", 0)),
            1,
        ):
            status = self.strings("job_paused") if job.get("paused") else labels.get(
                job.get("status"),
                job.get("status", "—"),
            )
            lines.append(
                f"<b>{index}.</b> {utils.escape_html(job['source_title'])} → "
                f"{utils.escape_html(job['target_title'])} · <code>{status}</code>"
            )
        return (
            f"{self.strings('jobs_title').format(emoji=_EMOJI['progress'])}\n\n"
            f"<blockquote expandable>{chr(10).join(lines)}</blockquote>"
        )

    async def _jobs_menu(self, call, token):
        if token not in self._menus:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        call = self._call_source(call)
        rows = []
        for index, job in enumerate(
            sorted(self._jobs.values(), key=lambda item: item.get("created", 0)),
            1,
        ):
            rows.append(
                [
                    {
                        "text": self.strings("btn_stop_number").format(index),
                        "callback": self._stop_from_menu,
                        "args": (token, job["id"]),
                        "style": "danger",
                    }
                ]
            )
        rows.append(
            [
                {
                    "text": self.strings("btn_refresh"),
                    "callback": self._jobs_menu,
                    "args": (token,),
                },
                {
                    "text": self.strings("btn_back"),
                    "callback": self._render_main,
                    "args": (token,),
                    "style": "primary",
                },
            ]
        )
        rows.append(
            [
                {
                    "text": self.strings("btn_close"),
                    "callback": self._close,
                    "args": (token,),
                    "style": "danger",
                }
            ]
        )
        await call.edit(self._jobs_text(), reply_markup=rows)

    async def _stop_from_menu(self, call, token, job_id):
        await self._request_stop(job_id)
        await self._jobs_menu(call, token)

    async def _start(self, call, token):
        state = self._menus.get(token)
        if not state:
            return await call.answer(self.strings("menu_expired"), show_alert=True)
        if not state.get("source"):
            return await call.answer(self.strings("source_required_start"), show_alert=True)
        if not state.get("target"):
            return await call.answer(self.strings("target_required_start"), show_alert=True)
        if len(self._jobs) >= 10:
            return await call.answer(self.strings("queue_full"), show_alert=True)
        try:
            source_entity = await self.client.get_entity(state["source"]["peer"])
            start_message = await self._get_message(source_entity, state["start"])
            if await self._source_is_protected(
                source_entity,
                start_message,
            ):
                raise _ForwardProtected
            end_id = state["end"]
            if state["range_mode"] == "latest":
                end_id = await self._latest_id(
                    state["source"]["peer"],
                    state["source"].get("topic"),
                )
            if end_id < state["start"]:
                raise ValueError(self.strings("range_empty"))
        except _ForwardProtected:
            return await self._input_error(
                call,
                token,
                self.strings("protected_source"),
            )
        except Exception as error:
            return await call.answer(str(error), show_alert=True)
        form = getattr(call, "form", {})
        job_id = secrets.token_hex(8)
        now = time.time()
        job = {
            "id": job_id,
            "source_peer": state["source"]["peer"],
            "source_title": state["source"]["title"],
            "source_topic": state["source"].get("topic"),
            "target_peer": state["target"]["peer"],
            "target_title": state["target"]["title"],
            "target_topic": state["target"].get("topic"),
            "target_ref": state["target"].get("reference"),
            "start_id": state["start"],
            "end_id": end_id,
            "last_id": state["start"] - 1,
            "filters": list(state["filters"]),
            "hide_author": state["hide_author"],
            "remove_captions": state["remove_captions"],
            "remove_text_messages": state["remove_text_messages"],
            "status": "queued",
            "paused": False,
            "forwarded": 0,
            "skipped": 0,
            "scanned": 0,
            "flood_count": 0,
            "flood_seconds": 0,
            "flood_until": 0,
            "created": now,
            "started": 0,
            "last_refresh": 0,
            "last_save": 0,
            "pin_failed": False,
            "pinned": False,
            "control_chat": form.get("chat") or state["control_chat"],
            "control_message": form.get("message_id"),
            "inline_message_id": self._pack_inline_id(
                form.get("inline_message_id")
                or getattr(call, "inline_message_id", None)
            ),
        }
        self._menus.pop(token, None)
        self._jobs[job_id] = job
        event = asyncio.Event()
        event.set()
        self._pause_events[job_id] = event
        self._queue.put_nowait(job_id)
        self._save_jobs()
        await call.answer(self.strings("job_added"))
        await call.edit(
            self._job_text(job),
            reply_markup=self._job_markup(job),
        )

    def _queue_position(self, job_id):
        waiting = [
            job["id"]
            for job in sorted(
                self._jobs.values(),
                key=lambda item: item.get("created", 0),
            )
            if job.get("status") == "queued"
        ]
        try:
            return waiting.index(job_id) + 1
        except ValueError:
            return 0

    def _duration(self, seconds):
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return self.strings("duration_hours").format(hours, minutes)
        if minutes:
            return self.strings("duration_minutes").format(minutes, seconds)
        return self.strings("duration_seconds").format(seconds)

    def _job_text(self, job):
        status = job.get("status")
        if status == "queued":
            state = self.strings("job_state_queued").format(self._queue_position(job["id"]))
        elif status == "flood":
            left = max(0, int(job.get("flood_until", 0) - time.time()))
            state = self.strings("job_state_flood").format(self._duration(left))
        elif status == "stopping":
            state = self.strings("job_state_stopping")
        elif status == "done":
            state = self.strings("job_state_done")
        elif status == "stopped":
            state = self.strings("job_state_stopped")
        elif status == "error":
            state = self.strings("job_state_error")
        elif job.get("paused"):
            state = self.strings("job_state_paused")
        else:
            state = self.strings("job_state_running")
        span = max(1, job["end_id"] - job["start_id"] + 1)
        passed = max(0, min(span, job.get("last_id", 0) - job["start_id"] + 1))
        percent = 100 if status == "done" else round(passed * 100 / span, 1)
        blocks = min(10, int(percent // 10))
        bar = "█" * blocks + "░" * (10 - blocks)
        elapsed = max(0, time.time() - (job.get("started") or time.time()))
        active = max(1, elapsed - job.get("flood_seconds", 0))
        speed = job.get("forwarded", 0) * 60 / active
        scan_speed = passed / active
        remaining = max(0, span - passed)
        eta = self._duration(remaining / scan_speed) if scan_speed > 0 else "—"
        target = utils.escape_html(str(job["target_title"]))
        target_ref = job.get("target_ref") or self._peer_reference(
            job["target_peer"],
            job.get("target_topic"),
        )
        target += f" (<code>{utils.escape_html(str(target_ref))}</code>)"
        source = utils.escape_html(str(job["source_title"]))
        if job.get("source_topic"):
            source += f" · {self.strings('topic')} <code>{job['source_topic']}</code>"
        filter_name = utils.escape_html(
            ", ".join(self._filter_label(item) for item in job["filters"])
        )
        author = self.strings("status_hidden") if job["hide_author"] else self.strings("status_shown")
        captions = self.strings("status_removed") if job["remove_captions"] else self.strings("status_kept")
        text_messages = (
            self.strings("status_removing")
            if job["remove_text_messages"]
            else self.strings("status_keeping")
        )
        extra = ""
        if job.get("pin_failed"):
            extra += self.strings("job_pin_failed")
        if job.get("error"):
            extra += f"\n<code>{utils.escape_html(str(job['error']))}</code>"
        return self.strings("job_text").format(
            main=_EMOJI["main"],
            state=state,
            source_emoji=_EMOJI["source"],
            target_emoji=_EMOJI["target"],
            type_emoji=_EMOJI["type"],
            source=source,
            target=target,
            filter=filter_name,
            author=author,
            captions=captions,
            messages=self.strings("job_messages").format(text_messages) if job["remove_captions"] else "",
            start=job["start_id"],
            end=job["end_id"],
            bar=bar,
            percent=percent,
            forwarded=job.get("forwarded", 0),
            skipped=job.get("skipped", 0),
            speed=speed,
            eta=eta,
            flood=job.get("flood_count", 0),
            extra=extra,
        )

    def _job_markup(self, job):
        if job.get("status") in {"done", "error", "stopped"}:
            return [
                [
                    {
                        "text": self.strings("btn_close"),
                        "callback": self._close_result,
                        "args": (
                            job.get("control_chat"),
                            job.get("control_message"),
                        ),
                        "style": "danger",
                    }
                ]
            ]
        rows = []
        if job.get("status") != "queued":
            if job.get("paused"):
                rows.append(
                    [
                        {
                            "text": self.strings("btn_resume"),
                            "callback": self._resume_job,
                            "args": (job["id"],),
                            "style": "success",
                        }
                    ]
                )
            else:
                rows.append(
                    [
                        {
                            "text": self.strings("btn_pause"),
                            "callback": self._pause_job,
                            "args": (job["id"],),
                        }
                    ]
                )
        rows.append(
            [
                {
                    "text": self.strings("btn_stop"),
                    "callback": self._stop_job,
                    "args": (job["id"],),
                    "style": "danger",
                }
            ]
        )
        return rows

    async def _close_result(self, call, chat_id=None, message_id=None):
        if chat_id and message_id:
            with contextlib.suppress(Exception):
                await self.client.delete_messages(chat_id, [message_id])
                return
        with contextlib.suppress(Exception):
            await call.delete()

    async def _edit_job(self, job, force=False):
        now = time.time()
        if not force and now - job.get("last_refresh", 0) < 2:
            return
        job["last_refresh"] = now
        markup = self.inline.generate_markup(self._job_markup(job))
        kwargs = {
            "text": self._job_text(job),
            "reply_markup": markup,
            "disable_web_page_preview": True,
        }
        inline_id = self._unpack_inline_id(job.get("inline_message_id"))
        if inline_id:
            kwargs["inline_message_id"] = inline_id
        elif job.get("control_chat") and job.get("control_message"):
            kwargs["chat_id"] = job["control_chat"]
            kwargs["message_id"] = job["control_message"]
        else:
            return
        with contextlib.suppress(Exception):
            await self.inline.bot.edit_message_text(**kwargs)

    async def _pause_job(self, call, job_id):
        job = self._jobs.get(job_id)
        if not job or job.get("status") in {"done", "error", "stopped"}:
            return await call.answer(self.strings("job_finished"), show_alert=True)
        job["paused"] = True
        self._pause_events.setdefault(job_id, asyncio.Event()).clear()
        self._save_jobs()
        await call.answer(self.strings("job_paused_notice"))
        await self._edit_job(job, True)

    async def _resume_job(self, call, job_id):
        job = self._jobs.get(job_id)
        if not job or job.get("status") in {"done", "error", "stopped"}:
            return await call.answer(self.strings("job_finished"), show_alert=True)
        job["paused"] = False
        self._pause_events.setdefault(job_id, asyncio.Event()).set()
        self._save_jobs()
        await call.answer(self.strings("job_resumed_notice"))
        await self._edit_job(job, True)

    async def _stop_job(self, call, job_id):
        await self._request_stop(job_id)
        await call.answer(self.strings("job_stopping_notice"))

    async def _request_stop(self, job_id):
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.get("status") == "queued":
            await self._finish_job(job, "stopped")
            return
        job["status"] = "stopping"
        job["paused"] = False
        self._pause_events.setdefault(job_id, asyncio.Event()).set()
        self._save_jobs()
        await self._edit_job(job, True)

    async def _pin_job(self, job):
        if not job.get("control_chat") or not job.get("control_message"):
            job["pin_failed"] = True
            return
        try:
            peer = await self.client.get_input_entity(job["control_chat"])
            await self.client(
                functions.messages.UpdatePinnedMessageRequest(
                    peer=peer,
                    id=job["control_message"],
                    silent=True,
                )
            )
            job["pinned"] = True
            job["pin_failed"] = False
        except Exception:
            job["pin_failed"] = True
        self._save_jobs()

    async def _wait_job(self, job):
        if job.get("status") == "stopping":
            raise _ForwardStopped
        event = self._pause_events.setdefault(job["id"], asyncio.Event())
        if not job.get("paused"):
            event.set()
        while job.get("paused"):
            await event.wait()
            if job.get("status") == "stopping":
                raise _ForwardStopped
        if job.get("status") == "stopping":
            raise _ForwardStopped

    async def _sleep_job(self, job, seconds):
        end = time.time() + max(0, seconds)
        while time.time() < end:
            if job.get("status") == "stopping":
                raise _ForwardStopped
            await asyncio.sleep(min(2, end - time.time()))
        await self._wait_job(job)

    @staticmethod
    def _protected_error(error):
        value = f"{type(error).__name__}: {error}".lower()
        return any(
            marker in value
            for marker in (
                "forwardsrestricted",
                "noforwards",
                "content is protected",
                "forwards restricted",
                "forbidden to forward",
            )
        )

    @staticmethod
    def _random_id(job_id, message_id):
        digest = hashlib.blake2b(
            f"{job_id}:{message_id}".encode(),
            digest_size=8,
        ).digest()
        return int.from_bytes(digest, "big") & ((1 << 63) - 1)

    async def _send_batch(self, job, source, target, messages):
        attempts = 0
        ids = [message.id for message in messages]
        random_ids = [self._random_id(job["id"], message_id) for message_id in ids]
        while True:
            await self._wait_job(job)
            try:
                kwargs = {
                    "from_peer": source,
                    "id": ids,
                    "random_id": random_ids,
                    "to_peer": target,
                    "drop_author": job["hide_author"],
                    "drop_media_captions": job["remove_captions"],
                    "with_my_score": False,
                }
                if job.get("target_topic"):
                    kwargs["top_msg_id"] = job["target_topic"]
                await self.client(
                    functions.messages.ForwardMessagesRequest(**kwargs)
                )
                await self._wait_job(job)
                return
            except FloodWaitError as error:
                seconds = int(getattr(error, "seconds", 60) or 60) + 2
                job["status"] = "flood"
                job["flood_count"] += 1
                job["flood_seconds"] += seconds
                job["flood_until"] = time.time() + seconds
                self._save_jobs()
                await self._edit_job(job, True)
                await self._sleep_job(job, seconds)
                job["status"] = "running"
                job["flood_until"] = 0
            except RPCError as error:
                if self._protected_error(error):
                    raise _ForwardProtected from error
                attempts += 1
                if attempts >= 3:
                    raise
                await self._sleep_job(job, 2**attempts)

    @staticmethod
    def _is_service(message):
        return isinstance(message, types.MessageService)

    @staticmethod
    def _is_gif(message):
        if bool(getattr(message, "gif", False)):
            return True
        document = getattr(message, "document", None)
        for attribute in getattr(document, "attributes", None) or []:
            if isinstance(attribute, types.DocumentAttributeAnimated):
                return True
        return False

    def _matches(self, message, filters):
        filters = self._normalize_filters(filters)
        if "all" in filters:
            return True
        media = getattr(message, "media", None)
        media_name = type(media).__name__
        webpage = media_name == "MessageMediaWebPage"
        photo = bool(getattr(message, "photo", None))
        sticker = bool(getattr(message, "sticker", None))
        gif = self._is_gif(message)
        voice = bool(getattr(message, "voice", None))
        audio = bool(getattr(message, "audio", None)) and not voice
        video = bool(getattr(message, "video", None)) and not gif
        document = bool(getattr(message, "document", None))
        file_document = (
            document
            and not sticker
            and not gif
            and not voice
            and not audio
            and not video
        )
        text = bool(getattr(message, "message", None)) and (
            media is None or webpage
        )
        values = {
            "text": text,
            "media": media is not None and not webpage,
            "photo": photo,
            "video": video,
            "audio": audio,
            "voice": voice,
            "file": file_document,
            "gif": gif,
            "sticker": sticker,
            "inline": bool(getattr(message, "via_bot_id", None)),
        }
        return any(values.get(filter_type, False) for filter_type in filters)

    @staticmethod
    def _is_text_message(message):
        media = getattr(message, "media", None)
        return bool(getattr(message, "message", None)) and (
            media is None or type(media).__name__ == "MessageMediaWebPage"
        )

    async def _message_units(self, job, source_entity):
        kwargs = {
            "min_id": job["last_id"],
            "max_id": job["end_id"] + 1,
            "reverse": True,
        }
        if job.get("source_topic"):
            kwargs["reply_to"] = job["source_topic"]
        current = []
        grouped_id = None
        async for message in self.client.iter_messages(source_entity, **kwargs):
            if message.id < job["start_id"] or message.id > job["end_id"]:
                continue
            await self._wait_job(job)
            current_group = getattr(message, "grouped_id", None)
            if current and (current_group is None or current_group != grouped_id):
                yield current
                current = []
                grouped_id = None
            if current_group is not None:
                current.append(message)
                grouped_id = current_group
            else:
                yield [message]
        if current:
            yield current

    async def _checkpoint(self, job, force=False):
        now = time.time()
        if force or now - job.get("last_save", 0) >= 3:
            job["last_save"] = now
            self._save_jobs()
        await self._edit_job(job, force)

    async def _run_job(self, job):
        source_entity = await self.client.get_entity(job["source_peer"])
        target_entity = await self.client.get_entity(job["target_peer"])
        if await self._source_is_protected(source_entity):
            raise _ForwardProtected
        source = await self.client.get_input_entity(source_entity)
        target = await self.client.get_input_entity(target_entity)
        pending = []
        checkpoint_id = job["last_id"]
        async for unit in self._message_units(job, source_entity):
            await self._wait_job(job)
            unit_last = max(message.id for message in unit)
            job["scanned"] += len(unit)
            selected = []
            for message in unit:
                if self._is_service(message):
                    job["skipped"] += 1
                    continue
                if getattr(message, "noforwards", False):
                    raise _ForwardProtected
                if job["remove_text_messages"] and self._is_text_message(
                    message
                ):
                    job["skipped"] += 1
                elif self._matches(message, job["filters"]):
                    selected.append(message)
                else:
                    job["skipped"] += 1
            if selected and pending and len(pending) + len(selected) > 100:
                await self._send_batch(job, source, target, pending)
                job["forwarded"] += len(pending)
                job["last_id"] = checkpoint_id
                pending = []
                await self._checkpoint(job)
                await self._sleep_job(job, 1)
            pending.extend(selected)
            checkpoint_id = unit_last
            if not pending:
                job["last_id"] = checkpoint_id
                await self._checkpoint(job)
        if pending:
            await self._send_batch(job, source, target, pending)
            job["forwarded"] += len(pending)
            job["last_id"] = checkpoint_id
        job["last_id"] = job["end_id"]
        await self._checkpoint(job, True)

    async def _finish_job(self, job, status, error=None):
        job["status"] = status
        job["paused"] = False
        job["flood_until"] = 0
        if error:
            job["error"] = str(error)
        self._save_jobs()
        await self._edit_job(job, True)
        self._jobs.pop(job["id"], None)
        self._pause_events.pop(job["id"], None)
        self._save_jobs()

    async def _worker(self):
        while True:
            job_id = await self._queue.get()
            try:
                job = self._jobs.get(job_id)
                if not job:
                    continue
                self._active_job_id = job_id
                if job.get("status") == "stopping":
                    await self._finish_job(job, "stopped")
                    continue
                job["status"] = "running"
                if not job.get("started"):
                    job["started"] = time.time()
                self._save_jobs()
                await self._pin_job(job)
                await self._edit_job(job, True)
                try:
                    await self._run_job(job)
                except _ForwardStopped:
                    await self._finish_job(job, "stopped")
                except _ForwardProtected:
                    await self._finish_job(
                        job,
                        "error",
                        self.strings("job_protected"),
                    )
                except asyncio.CancelledError:
                    self._save_jobs()
                    raise
                except Exception as error:
                    logger.exception("M:Forward task failed")
                    await self._finish_job(job, "error", error)
                else:
                    await self._finish_job(job, "done")
            finally:
                self._active_job_id = None
                self._queue.task_done()

    @loader.command()
    async def mfw(self, message: Message):
        """Open the forwarding menu."""
        now = time.time()
        self._menus = {
            key: value
            for key, value in self._menus.items()
            if now - value.get("created", now) < 7200
        }
        entity = await self.client.get_entity(message.peer_id)
        target = {
            "peer": self._peer_id(entity),
            "title": self._entity_title(entity),
            "topic": int(utils.get_topic(message) or 0) or None,
            "reference": self._peer_reference(
                self._peer_id(entity),
                int(utils.get_topic(message) or 0) or None,
                getattr(entity, "username", None),
            ),
        }
        token = secrets.token_hex(8)
        self._menus[token] = {
            "created": now,
            "control_chat": target["peer"],
            "default_target": dict(target),
            "target": dict(target),
            "source": None,
            "start": 1,
            "end": 1,
            "range_mode": "fixed",
            "filters": ["all"],
            "hide_author": True,
            "remove_captions": False,
            "remove_text_messages": False,
            "notice": None,
        }
        await self.inline.form(
            text=self._menu_text(self._menus[token]),
            message=message,
            reply_markup=self._menu_markup(token),
        )
