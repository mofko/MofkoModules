# meta developer: @mofkomodules
# name: MusicS
# meta banner: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260209_182634_445.jpg
# meta pic: https://raw.githubusercontent.com/mofko/hass/refs/heads/main/IMG_20260209_182634_445.jpg
# meta fhsdesc: tool, music, finder, mofko, хуйня, поиск, музыка 

__version__ = (1, 2, 0)

import io
import logging
import asyncio
import subprocess
import tempfile
import os
import contextlib
import time
import aiohttp
import ssl
from urllib.parse import quote_plus
from typing import Optional, Dict

from ShazamAPI import Shazam
from .. import loader, utils
from telethon.tl.types import Message, DocumentAttributeVideo, DocumentAttributeFilename

logger = logging.getLogger(__name__)

@loader.tds
class MusicSMod(loader.Module):
    """Ищет треки из видео сообщения. (Находит не все треки)."""
    
    strings = {
        "name": "MusicS",
        "processing": "🎵 Обрабатываю видео...",
        "no_video": "❌ Ответьте на видео сообщение",
        "recognition_failed": "❌ Не удалось распознать музыку",
        "recognition_success": "🎵 <b>Найдено:</b>\n\n<code>{title}</code>\n\n🔗 <b>Ссылки:</b>\n{links}",
        "downloading": "🤔 Скачиваю видео...",
        "file_too_large": "❌ Файл слишком большой (макс. {max_size} МБ)",
        "wait_cooldown": "⏳ Подождите {} секунд",
        "extracting": "🎶 Извлекаю аудио...",
        "ffmpeg_not_found": "❌ Установите <code>ffmpeg</code> и <code>ffprobe</code> для работы модуля. (<code>apt install ffmpeg</code>)",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "max_file_size",
                50,
                "Максимальный размер файла",
                validator=loader.validators.Integer(minimum=10, maximum=100),
            ),
            loader.ConfigValue(
                "shazam_attempts",
                8,
                "Количество попыток распознавания Shazam",
                validator=loader.validators.Integer(minimum=1, maximum=20),
            ),
        )
        self.last_request = 0
        self.cooldown = 4
        self.ffmpeg_available = False
        self.uid = None

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.ffmpeg_available = await self._check_ffmpeg()
        if not self.ffmpeg_available:
            logger.error(self.strings["ffmpeg_not_found"])
        
        try:
            me = await self.client.get_me()
            self.uid = me.id
        except Exception:
            logger.warning("Не удалось получить ID пользователя для F-Heta лайка.")
        
        await self._send_fheta_like()

    async def _send_fheta_like(self):
        if self.db.get(__name__, "liked_fheta", False): return

        token = self.db.get("FHeta", "token")
        if not token: return

        try:
            if not self.uid:
                me = await self.client.get_me()
                self.uid = me.id

            install_link = "dlm https://api.fixyres.com/module/mofko/MofkoModules/MusicS.py"
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
        except Exception as e:
            logger.exception(e)

    async def _check_ffmpeg(self) -> bool:
        for cmd in ["ffmpeg", "ffprobe"]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    cmd, "-version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
                if proc.returncode != 0:
                    return False
            except FileNotFoundError:
                return False
            except Exception as e:
                logger.exception(e)
                return False
        return True

    def is_video_message(self, message: Message) -> bool:
        if not message.media:
            return False
        
        if hasattr(message.media, 'document'):
            doc = message.media.document
            if any(isinstance(attr, DocumentAttributeVideo) for attr in doc.attributes):
                return True
            
            filename_attr = next((attr for attr in doc.attributes if isinstance(attr, DocumentAttributeFilename)), None)
            if filename_attr:
                ext = filename_attr.file_name.split('.')[-1].lower()
                return ext in ['mp4', 'avi', 'mov', 'mkv', 'webm', 'm4v', '3gp']
        
        return False

    async def check_cooldown(self) -> bool:
        current_time = asyncio.get_event_loop().time()
        return current_time - self.last_request >= self.cooldown

    async def extract_audio_from_video(self, video_path: str, status_msg: Message) -> Optional[io.BytesIO]:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.m4a")
            cmd = [
                'ffmpeg', '-i', video_path, 
                '-vn',
                '-acodec', 'aac',
                '-ab', '256k',
                '-ac', '2',
                '-ar', '48000',
                '-af', 'loudnorm',
                '-y', audio_path
            ]
            
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                start_time = asyncio.get_event_loop().time()
                while proc.returncode is None:
                    await asyncio.sleep(0.5)
                    elapsed = asyncio.get_event_loop().time() - start_time
                    try:
                        await status_msg.edit(f"{self.strings['extracting']} ({int(elapsed)}с)")
                    except Exception:
                        pass
                
                if proc.returncode == 0 and os.path.exists(audio_path):
                    with open(audio_path, 'rb') as f:
                        return io.BytesIO(f.read())
                else:
                    stderr = (await proc.stderr.read()).decode('utf-8')
                    logger.error(f"FFmpeg failed with return code {proc.returncode}. Stderr: {stderr}")
                    return None
            except Exception as e:
                logger.exception(e)
                return None
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(video_path)

    async def download_video(self, message: Message, status_msg: Message) -> Optional[str]:
        try:
            if not self.is_video_message(message):
                return None

            if hasattr(message.media, 'document'):
                file_size = message.media.document.size / (1024 * 1024)
                if file_size > self.config["max_file_size"]:
                    await utils.answer(status_msg, self.strings["file_too_large"].format(max_size=self.config["max_file_size"]))
                    return None
            
            start_time = asyncio.get_event_loop().time()
            
            last_update_time = 0
            
            def progress_callback(current, total):
                nonlocal last_update_time
                current_time = asyncio.get_event_loop().time()
                
                if current_time - last_update_time > 1:
                    try:
                        percent = int(current / total * 100)
                        asyncio.run_coroutine_threadsafe(
                            status_msg.edit(f"{self.strings['downloading']} {percent}%"),
                            asyncio.get_event_loop()
                        )
                        last_update_time = current_time
                    except Exception:
                        pass

            video_path = await self.client.download_media(message, progress_callback=progress_callback)
            return video_path

        except Exception as e:
            logger.exception(e)
            return None
    
    def _recognize_shazam_sync(self, shazam_instance: Shazam, attempts: int) -> Optional[dict]:
        for _ in range(attempts):
            try:
                result = next(shazam_instance.recognizeSong())
                if result[1].get('track'):
                    return result[1]['track']
            except StopIteration:
                break 
            except Exception as e:
                logger.exception(e)
                time.sleep(0.5) 
                continue
        return None

    async def recognize_shazam(self, audio_data: io.BytesIO) -> Optional[dict]:
        try:
            shazam = Shazam(audio_data.read())
            track_info = await utils.run_sync(self._recognize_shazam_sync, shazam, self.config["shazam_attempts"])
            
            if track_info:
                return {
                    'title': track_info.get('title', 'Неизвестно'),
                    'artist': track_info.get('subtitle', 'Неизвестно'),
                    'images': track_info.get('images', {}),
                    'share': track_info.get('share', {}),
                    'links': self.format_links(track_info)
                }
            return None
            
        except Exception as e:
            logger.exception(e)
            return None

    def format_links(self, track: dict) -> str:
        links = []
        
        title = track.get('title', '')
        artist = track.get('subtitle', '')
        
        if title and artist:
            search_query = f"{artist} {title}".replace(' ', '%20')
            
            youtube_url = f"https://www.youtube.com/results?search_query={search_query}"
            links.append(f"🧩 <a href='{youtube_url}'>YouTube</a>")
            
            soundcloud_url = f"https://soundcloud.com/search?q={search_query}"
            links.append(f"☁️ <a href='{soundcloud_url}'>SoundCloud</a>")
            
            yandex_url = f"https://music.yandex.ru/search?text={search_query}"
            links.append(f"🎵 <a href='{yandex_url}'>Яндекс Музыка</a>")
        
        share_data = track.get('share', {})
        if share_data.get('href'):
            links.append(f"🔍 <a href='{share_data['href']}'>Shazam</a>")
        
        return '\n'.join([f"<blockquote>{link}</blockquote>" for link in links]) if links else "Ссылки не найдены"

    @loader.command()
    async def song(self, message: Message):
        """Найти трек из видео"""
        if not self.ffmpeg_available:
            await utils.answer(message, self.strings["ffmpeg_not_found"])
            return

        reply = await message.get_reply_message()
        
        if not reply:
            await utils.answer(message, self.strings["no_video"])
            return

        if not await self.check_cooldown():
            wait_time = self.cooldown - int(asyncio.get_event_loop().time() - self.last_request)
            await utils.answer(message, self.strings["wait_cooldown"].format(wait_time + 1))
            return

        if not self.is_video_message(reply):
            await utils.answer(message, self.strings["no_video"])
            return

        status_msg = await utils.answer(message, self.strings["downloading"])
        video_path = None
        try: 
            video_path = await self.download_video(reply, status_msg)
            
            if not video_path:
                return 

            await utils.answer(status_msg, self.strings["extracting"])
            audio_data = await self.extract_audio_from_video(video_path, status_msg)
            
            if not audio_data:
                await utils.answer(status_msg, self.strings["recognition_failed"])
                return

            await utils.answer(status_msg, self.strings["processing"])
            
            result = await self.recognize_shazam(audio_data)
            
            if result:
                self.last_request = asyncio.get_event_loop().time()

                title_with_artist = f"{result['artist']} - {result['title']}"
                
                images = result.get('images', {})
                if images.get('background'):
                    await self.client.send_file(
                        message.chat_id,
                        file=images['background'],
                        caption=self.strings["recognition_success"].format(
                            title=title_with_artist,
                            links=result['links']
                        ),
                        reply_to=reply.id
                    )
                    with contextlib.suppress(Exception):
                        await status_msg.delete()
                else:
                    response = self.strings["recognition_success"].format(
                        title=title_with_artist,
                        links=result['links']
                    )
                    await utils.answer(status_msg, response)
            else:
                await utils.answer(status_msg, self.strings["recognition_failed"])
        except Exception as e:
            logger.exception(e)
            with contextlib.suppress(Exception):
                await status_msg.edit(f"{self.strings['recognition_failed']}: {e}")
        finally:
            with contextlib.suppress(FileNotFoundError):
                if video_path and os.path.exists(video_path):
                    os.unlink(video_path) 
