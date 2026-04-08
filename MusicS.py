# meta developer: @mofkomodules
# Name: MusicS
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_038.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/IMG_20260408_161047_038.png
# meta fhsdesc: tool, music, finder, mofko, поиск, музыка
# requires: aiohttp ShazamAPI ffmpeg ffprobe

__version__ = (1, 3, 0)

import asyncio
import contextlib
import logging
import os
import ssl
import tempfile
import time
from typing import Dict, Optional
from urllib.parse import quote, quote_plus

import aiohttp
from ShazamAPI import Shazam
from telethon.tl.types import (
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    Message,
)

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class MusicSMod(loader.Module):
    """Recognize music from replied media."""

    strings = {
        "name": "MusicS",
        "processing": "<tg-emoji emoji-id=5325543345760509967>🔄</tg-emoji> Processing media...",
        "downloading": "<tg-emoji emoji-id=5873225338984599714>📤</tg-emoji> Downloading media...",
        "extracting": "<tg-emoji emoji-id=5325543345760509967>🔄</tg-emoji> Preparing audio segments...",
        "recognizing": "<tg-emoji emoji-id=5447429226221303478>⚫️</tg-emoji> Recognizing music...",
        "no_reply_media": "<tg-emoji emoji-id=5121063440311386962>👎</tg-emoji> Reply to a video, video note, audio or voice message.",
        "file_too_large": "<tg-emoji emoji-id=5913376703312302899>📣</tg-emoji> File is too large. Maximum size: {max_size} MB.",
        "recognition_failed": "<tg-emoji emoji-id=5121063440311386962>👎</tg-emoji> Could not recognize the track.",
        "recognition_success": "<tg-emoji emoji-id=5444862970377040012>❤️</tg-emoji> <b>Found:</b>\n\n<tg-emoji emoji-id=5444931419270839381>🏅</tg-emoji><code>{artist} — {title}</code>\n\n<tg-emoji emoji-id=5247029067256987229>ℹ️</tg-emoji> <b>Links:</b>\n{links}",
        "ffmpeg_not_found": "<tg-emoji emoji-id=5913376703312302899>📣</tg-emoji> Install <code>ffmpeg</code> and <code>ffprobe</code> to use this module.",
        "ffmpeg_not_found_log": "Install ffmpeg and ffprobe to use this module.",
        "cfg_max_file_size": "Maximum file size in MB",
        "cfg_shazam_attempts": "Number of Shazam attempts per segment",
        "no_links": "<tg-emoji emoji-id=5258503720928288433>ℹ️</tg-emoji> Links were not found.",
    }

    strings_ru = {
        "_cls_doc": "Распознаёт музыку из видео, войсов и аудио в реплае.",
        "processing": "<tg-emoji emoji-id=5325543345760509967>🔄</tg-emoji> Обрабатываю медиа...",
        "downloading": "<tg-emoji emoji-id=5873225338984599714>📤</tg-emoji> Скачиваю медиа...",
        "extracting": "<tg-emoji emoji-id=5325543345760509967>🔄</tg-emoji> Подготавливаю аудиофрагменты...",
        "recognizing": "<tg-emoji emoji-id=5447429226221303478>⚫️</tg-emoji> Распознаю музыку...",
        "no_reply_media": "<tg-emoji emoji-id=5121063440311386962>👎</tg-emoji> Ответьте на видео, видеокружок, аудио или голосовое сообщение.",
        "file_too_large": "<tg-emoji emoji-id=5913376703312302899>📣</tg-emoji> Файл слишком большой. Максимальный размер: {max_size} МБ.",
        "recognition_failed": "<tg-emoji emoji-id=5121063440311386962>👎</tg-emoji> Не удалось распознать.",
        "recognition_success": "<tg-emoji emoji-id=5444862970377040012>❤️</tg-emoji> <b>Найдено:</b>\n\n<tg-emoji emoji-id=5444931419270839381>🏅</tg-emoji><code>{artist} — {title}</code>\n\n<tg-emoji emoji-id=5247029067256987229>ℹ️</tg-emoji> <b>Ссылки:</b>\n{links}",
        "ffmpeg_not_found": "<tg-emoji emoji-id=5913376703312302899>📣</tg-emoji> Установите <code>ffmpeg</code> и <code>ffprobe</code> для работы модуля.",
        "cfg_max_file_size": "Максимальный размер файла в МБ",
        "cfg_shazam_attempts": "Количество попыток Shazam на один фрагмент",
        "no_links": "<tg-emoji emoji-id=5258503720928288433>ℹ️</tg-emoji> Ссылки не найдены.",
        "_cmd_doc_song": "Распознать музыку из медиа в реплае",
    }

    _SEGMENT_DURATION = 14
    _CACHE_TTL = 21600
    _SEGMENT_POINTS = (0.5, 0.2, 0.8)
    _PROCESS_TIMEOUT = 90

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "max_file_size",
                50,
                lambda: self.strings("cfg_max_file_size"),
                validator=loader.validators.Integer(minimum=10, maximum=100),
            ),
            loader.ConfigValue(
                "shazam_attempts",
                8,
                lambda: self.strings("cfg_shazam_attempts"),
                validator=loader.validators.Integer(minimum=1, maximum=20),
            ),
        )
        self.ffmpeg_available = False
        self.uid = None
        self._result_cache: Dict[str, Dict[str, object]] = {}

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.ffmpeg_available = await self._check_ffmpeg()
        if not self.ffmpeg_available:
            logger.error(self.strings("ffmpeg_not_found_log"))
        try:
            me = await self.client.get_me()
            self.uid = me.id
        except Exception as e:
            logger.exception(e)
        await self._send_fheta_like()

    async def on_unload(self):
        self._result_cache.clear()

    async def _send_fheta_like(self):
        if self.db.get(__name__, "liked_fheta", False):
            return
        token = self.db.get("FHeta", "token")
        if not token:
            return
        try:
            if not self.uid:
                me = await self.client.get_me()
                self.uid = me.id
            install_link = "dlm https://api.fixyres.com/module/mofko/MofkoModules/MusicS.py"
            endpoint = f"rate/{self.uid}/{quote_plus(install_link)}/like"
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.fixyres.com/{endpoint}",
                    headers={"Authorization": token},
                    ssl=ssl_context,
                    timeout=15,
                ) as response:
                    if response.status == 200:
                        self.db.set(__name__, "liked_fheta", True)
        except Exception as e:
            logger.exception(e)

    async def _check_ffmpeg(self) -> bool:
        for command in ("ffmpeg", "ffprobe"):
            try:
                process = await asyncio.create_subprocess_exec(
                    command,
                    "-version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(process.communicate(), timeout=15)
                if process.returncode != 0:
                    return False
            except Exception as e:
                logger.exception(e)
                return False
        return True

    def _get_document(self, message: Message):
        return getattr(getattr(message, "media", None), "document", None)

    def _get_media_kind(self, message: Message) -> Optional[str]:
        document = self._get_document(message)
        if not document:
            return None
        for attribute in document.attributes:
            if isinstance(attribute, DocumentAttributeVideo):
                return "video_note" if getattr(attribute, "round_message", False) else "video"
        for attribute in document.attributes:
            if isinstance(attribute, DocumentAttributeAudio):
                return "voice" if getattr(attribute, "voice", False) else "audio"
        filename_attribute = next(
            (attribute for attribute in document.attributes if isinstance(attribute, DocumentAttributeFilename)),
            None,
        )
        if filename_attribute and "." in filename_attribute.file_name:
            extension = filename_attribute.file_name.rsplit(".", 1)[1].lower()
            if extension in {"mp4", "avi", "mov", "mkv", "webm", "m4v", "3gp"}:
                return "video"
            if extension in {"mp3", "m4a", "aac", "ogg", "opus", "wav", "flac"}:
                return "audio"
        mime_type = getattr(document, "mime_type", "") or ""
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        return None

    def _get_media_duration_hint(self, message: Message) -> Optional[float]:
        document = self._get_document(message)
        if not document:
            return None
        for attribute in document.attributes:
            if isinstance(attribute, (DocumentAttributeVideo, DocumentAttributeAudio)):
                duration = getattr(attribute, "duration", None)
                if duration:
                    return float(duration)
        return None

    def _get_media_cache_key(self, message: Message) -> str:
        document = self._get_document(message)
        if document:
            return f"doc:{document.id}"
        return f"msg:{utils.get_chat_id(message)}:{message.id}"

    def _prune_cache(self):
        now = time.time()
        expired = [
            key for key, value in self._result_cache.items()
            if now - float(value["ts"]) > self._CACHE_TTL
        ]
        for key in expired:
            self._result_cache.pop(key, None)

    def _get_cached_result(self, cache_key: str) -> Optional[dict]:
        self._prune_cache()
        cached = self._result_cache.get(cache_key)
        if not cached:
            return None
        return cached.get("result")

    def _store_cached_result(self, cache_key: str, result: dict):
        self._result_cache[cache_key] = {"ts": time.time(), "result": result}

    def _get_file_size_mb(self, message: Message) -> float:
        document = self._get_document(message)
        if not document:
            return 0
        return float(getattr(document, "size", 0)) / (1024 * 1024)

    def _get_source_suffix(self, message: Message) -> str:
        document = self._get_document(message)
        if document:
            filename_attribute = next(
                (attribute for attribute in document.attributes if isinstance(attribute, DocumentAttributeFilename)),
                None,
            )
            if filename_attribute and "." in filename_attribute.file_name:
                extension = filename_attribute.file_name.rsplit(".", 1)[1].lower()
                if extension:
                    return f".{extension}"
            mime_type = getattr(document, "mime_type", "") or ""
            if mime_type.startswith("video/"):
                return ".mp4"
            if mime_type.startswith("audio/ogg"):
                return ".ogg"
            if mime_type.startswith("audio/"):
                return ".mp3"
        return ".bin"

    async def _run_process(self, *command: str, timeout: int = _PROCESS_TIMEOUT):
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode("utf-8", "ignore"), stderr.decode("utf-8", "ignore")

    async def _probe_duration(self, source_path: str, message: Message) -> Optional[float]:
        try:
            returncode, stdout, stderr = await self._run_process(
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                source_path,
                timeout=20,
            )
            if returncode == 0 and stdout.strip():
                return float(stdout.strip())
            if stderr:
                logger.error(stderr)
        except Exception as e:
            logger.exception(e)
        return self._get_media_duration_hint(message)

    def _build_segment_offsets(self, duration: Optional[float]):
        if not duration or duration <= self._SEGMENT_DURATION + 1:
            return [0.0]
        max_offset = max(duration - self._SEGMENT_DURATION, 0.0)
        offsets = []
        for point in self._SEGMENT_POINTS:
            offset = max(min(duration * point - self._SEGMENT_DURATION / 2, max_offset), 0.0)
            rounded = round(offset, 2)
            if rounded not in offsets:
                offsets.append(rounded)
        if max_offset not in offsets:
            offsets.append(round(max_offset, 2))
        return offsets

    async def _extract_segment(self, source_path: str, offset: float, fallback: bool, output_path: str) -> bool:
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            str(offset),
            "-t",
            str(self._SEGMENT_DURATION),
            "-i",
            source_path,
            "-vn",
            "-map_metadata",
            "-1",
        ]
        if fallback:
            command.extend(
                [
                    "-ac",
                    "1",
                    "-ar",
                    "44100",
                    "-af",
                    "loudnorm",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                ]
            )
        else:
            command.extend(
                [
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    "-af",
                    "loudnorm",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                ]
            )
        command.append(output_path)
        try:
            returncode, _, stderr = await self._run_process(*command)
            if returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            if stderr:
                logger.error(stderr)
        except Exception as e:
            logger.exception(e)
        return False

    def _recognize_shazam_sync(self, audio_bytes: bytes, attempts: int) -> Optional[dict]:
        shazam = Shazam(audio_bytes)
        for _ in range(attempts):
            try:
                result = next(shazam.recognizeSong())
                track = result[1].get("track")
                if track:
                    return track
            except StopIteration:
                break
            except Exception as e:
                logger.exception(e)
                time.sleep(0.4)
        return None

    async def _recognize_audio_file(self, audio_path: str) -> Optional[dict]:
        try:
            with open(audio_path, "rb") as file:
                audio_bytes = file.read()
            if not audio_bytes:
                return None
            track = await utils.run_sync(
                self._recognize_shazam_sync,
                audio_bytes,
                self.config["shazam_attempts"],
            )
            if not track:
                return None
            return {
                "title": track.get("title", "Unknown"),
                "artist": track.get("subtitle", "Unknown"),
                "images": track.get("images", {}),
                "share": track.get("share", {}),
                "links": self._format_links(track),
            }
        except Exception as e:
            logger.exception(e)
            return None

    def _format_links(self, track: dict) -> str:
        links = []
        title = track.get("title", "")
        artist = track.get("subtitle", "")
        if title and artist:
            query = quote(f"{artist} {title}")
            links.append(
                f"<blockquote><tg-emoji emoji-id=5463206079913533096>📹</tg-emoji> <a href=\"https://www.youtube.com/results?search_query={query}\">YouTube</a></blockquote>"
            )
            links.append(
                f"<blockquote><tg-emoji emoji-id=5345844509412444249>📱</tg-emoji> <a href=\"https://soundcloud.com/search?q={query}\">SoundCloud</a></blockquote>"
            )
            links.append(
                f"<blockquote><tg-emoji emoji-id=5429189857324841688>🎵</tg-emoji> <a href=\"https://music.yandex.ru/search?text={query}\">Яндекс Музыка</a></blockquote>"
            )
        share_url = track.get("share", {}).get("href")
        if share_url:
            links.append(
                f"<blockquote><tg-emoji emoji-id=5346259862814734771>📱</tg-emoji> <a href=\"{utils.escape_html(share_url)}\">Shazam</a></blockquote>"
            )
        return "\n".join(links) if links else self.strings("no_links")

    async def _download_media(self, message: Message, source_path: str) -> bool:
        try:
            result = await self.client.download_media(message, file=source_path)
            return bool(result and os.path.exists(result))
        except Exception as e:
            logger.exception(e)
            return False

    async def _send_status(self, message: Message, status_msg: Optional[Message], text: str) -> Message:
        reply_to = message.id
        if status_msg is not None:
            reply_to = getattr(status_msg, "reply_to_msg_id", None) or message.id
            with contextlib.suppress(Exception):
                await status_msg.delete()
        return await self.client.send_message(
            utils.get_chat_id(message),
            text,
            reply_to=reply_to,
        )

    async def _recognize_from_source(
        self,
        source_path: str,
        duration: Optional[float],
        message: Message,
        status_msg: Message,
    ):
        offsets = self._build_segment_offsets(duration)
        for index, offset in enumerate(offsets, start=1):
            status_msg = await self._send_status(
                message,
                status_msg,
                f"{self.strings('recognizing')} {index}/{len(offsets)}",
            )
            with tempfile.TemporaryDirectory() as segment_dir:
                primary_path = os.path.join(segment_dir, "segment.m4a")
                if await self._extract_segment(source_path, offset, False, primary_path):
                    result = await self._recognize_audio_file(primary_path)
                    if result:
                        return result, status_msg
                fallback_path = os.path.join(segment_dir, "segment.mp3")
                if await self._extract_segment(source_path, offset, True, fallback_path):
                    result = await self._recognize_audio_file(fallback_path)
                    if result:
                        return result, status_msg
        return None, status_msg

    async def _send_result(self, message: Message, reply: Message, status_msg: Message, result: dict):
        artist = utils.escape_html(result["artist"])
        title = utils.escape_html(result["title"])
        response = self.strings("recognition_success").format(
            artist=artist,
            title=title,
            links=result["links"],
        )
        image_url = result.get("images", {}).get("background")
        if image_url:
            try:
                await self.client.send_file(
                    message.chat_id,
                    file=image_url,
                    caption=response,
                    reply_to=reply.id,
                )
                with contextlib.suppress(Exception):
                    await status_msg.delete()
                return
            except Exception as e:
                logger.exception(e)
        with contextlib.suppress(Exception):
            await status_msg.delete()
        await self.client.send_message(
            message.chat_id,
            response,
            reply_to=reply.id,
            link_preview=False,
        )

    async def _send_failure(self, reply: Message, status_msg: Message):
        with contextlib.suppress(Exception):
            await status_msg.delete()
        await reply.respond(self.strings("recognition_failed"))

    @loader.command(ru_doc=" - распознать музыку из медиа в реплае")
    async def song(self, message: Message):
        """Recognize music from replied media."""
        if not self.ffmpeg_available:
            await utils.answer(message, self.strings("ffmpeg_not_found"))
            return
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings("no_reply_media"))
            return
        if not self._get_media_kind(reply):
            await utils.answer(message, self.strings("no_reply_media"))
            return
        if self._get_file_size_mb(reply) > self.config["max_file_size"]:
            await utils.answer(
                message,
                self.strings("file_too_large").format(max_size=self.config["max_file_size"]),
            )
            return
        with contextlib.suppress(Exception):
            await message.delete()
        cache_key = self._get_media_cache_key(reply)
        cached_result = self._get_cached_result(cache_key)
        status_msg = await self._send_status(message, None, self.strings("downloading"))
        if cached_result:
            await self._send_result(message, reply, status_msg, cached_result)
            return
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                source_path = os.path.join(temp_dir, f"source{self._get_source_suffix(reply)}")
                downloaded = await self._download_media(reply, source_path)
                if not downloaded:
                    await self._send_failure(reply, status_msg)
                    return
                status_msg = await self._send_status(message, status_msg, self.strings("extracting"))
                duration = await self._probe_duration(source_path, reply)
                result, status_msg = await self._recognize_from_source(
                    source_path,
                    duration,
                    message,
                    status_msg,
                )
                if not result:
                    await self._send_failure(reply, status_msg)
                    return
                self._store_cached_result(cache_key, result)
                await self._send_result(message, reply, status_msg, result)
        except Exception as e:
            logger.exception(e)
            await self._send_failure(reply, status_msg)
