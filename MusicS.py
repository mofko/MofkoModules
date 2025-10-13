# meta developer: @mofkomodules
# name: MusicS

__version__ = (1, 1, 0)

import io
import logging
import asyncio
from typing import Optional

from ShazamAPI import Shazam
from .. import loader, utils
from telethon.tl.types import Message, DocumentAttributeVideo, DocumentAttributeFilename

logger = logging.getLogger(__name__)

@loader.tds
class MusicSMod(loader.Module):
    """Ищет треки из видео сообщения. (Находит не все треки)."""
    
    strings = {
        "name": "MusicS",
        "processing": "<emoji document_id=5463107823946717464>🎵</emoji> Обрабатываю видео...",
        "no_video": "<emoji document_id=5210952531676504517>❌</emoji> Ответьте на видео сообщение",
        "recognition_failed": "<emoji document_id=5210952531676504517>❌</emoji> Не удалось распознать музыку",
        "recognition_success": "<emoji document_id=5463107823946717464>🎵</emoji> <b>Найдено:</b>\n\n<code>{title}</code>\n\n<emoji document_id=5271604874419647061>🔗</emoji> <b>Ссылки:</b>\n{links}",
        "downloading": "<emoji document_id=5195377464137753198>🤔</emoji> Скачиваю видео...",
        "file_too_large": "<emoji document_id=5210952531676504517>❌</emoji> Файл слишком большой (макс. {max_size} МБ)",
        "wait_cooldown": "<emoji document_id=5458770564107743497>⏳</emoji> Подождите {} секунд",
        "extracting": "<emoji document_id=5465287090352693530>🎶</emoji> Извлекаю аудио..."
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "max_file_size",
                50,
                "Максимальный размер файла",
                validator=loader.validators.Integer(minimum=10, maximum=100),
            ),
        )
        self.last_request = 0
        self.cooldown = 4

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

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
        if current_time - self.last_request < self.cooldown:
            return False
        self.last_request = current_time
        return True

    async def extract_audio_from_video(self, video_path: str) -> Optional[io.BytesIO]:
        try:
            import subprocess
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as temp_audio:
                audio_path = temp_audio.name
            
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
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0 and os.path.exists(audio_path):
                with open(audio_path, 'rb') as f:
                    audio_data = io.BytesIO(f.read())
                os.unlink(audio_path)
                os.unlink(video_path)
                return audio_data
            
            if os.path.exists(audio_path):
                os.unlink(audio_path)
            if os.path.exists(video_path):
                os.unlink(video_path)
            return None
            
        except Exception as e:
            logger.error(f"Ошибка извлечения аудио: {e}")
            if os.path.exists(video_path):
                os.unlink(video_path)
            return None

    async def download_video(self, message: Message) -> Optional[str]:
        try:
            if not self.is_video_message(message):
                return None

            if hasattr(message.media, 'document'):
                file_size = message.media.document.size / (1024 * 1024)
                if file_size > self.config["max_file_size"]:
                    return None

            video_path = await message.download_media()
            return video_path

        except Exception as e:
            logger.error(f"Ошибка скачивания: {e}")
            return None

    async def recognize_shazam(self, audio_data: io.BytesIO) -> Optional[dict]:
        try:
            shazam = Shazam(audio_data.read())
            recognize_generator = shazam.recognizeSong()
            
            for _ in range(8):
                try:
                    result = next(recognize_generator)
                    if result[1].get('track'):
                        track = result[1]['track']
                        return {
                            'title': track.get('title', 'Неизвестно'),
                            'artist': track.get('subtitle', 'Неизвестно'),
                            'images': track.get('images', {}),
                            'share': track.get('share', {}),
                            'links': self.format_links(track)
                        }
                except StopIteration:
                    break
                except Exception:
                    continue
                    
            return None
            
        except Exception:
            return None

    def format_links(self, track: dict) -> str:
        links = []
        
        title = track.get('title', '')
        artist = track.get('subtitle', '')
        
        if title and artist:
            search_query = f"{artist} {title}".replace(' ', '%20')
            
            youtube_url = f"https://www.youtube.com/results?search_query={search_query}"
            links.append(f"<emoji document_id=5193189878380116505>🧩</emoji> <a href='{youtube_url}'>YouTube</a>")
            
            soundcloud_url = f"https://soundcloud.com/search?q={search_query}"
            links.append(f"<emoji document_id=5287571024500498635>☁️</emoji> <a href='{soundcloud_url}'>SoundCloud</a>")
            
            yandex_url = f"https://music.yandex.ru/search?text={search_query}"
            links.append(f"<emoji document_id=5172447776205702031>🎵</emoji> <a href='{yandex_url}'>Яндекс Музыка</a>")
        
        share_data = track.get('share', {})
        if share_data.get('href'):
            links.append(f"<emoji document_id=5188217332748527444>🔍</emoji> <a href='{share_data['href']}'>Shazam</a>")
        
        return '\n'.join([f"<blockquote>{link}</blockquote>" for link in links]) if links else "Ссылки не найдены"

    @loader.command()
    async def song(self, message: Message):
        """Найти трек из видео"""
        reply = await message.get_reply_message()
        
        if not reply:
            await utils.answer(message, self.strings["no_video"])
            return

        if not await self.check_cooldown():
            wait_time = self.cooldown - int(asyncio.get_event_loop().time() - self.last_request)
            await utils.answer(message, self.strings["wait_cooldown"].format(wait_time))
            return

        if not self.is_video_message(reply):
            await utils.answer(message, self.strings["no_video"])
            return

        status_msg = await utils.answer(message, self.strings["downloading"])
        video_path = await self.download_video(reply)
        
        if not video_path:
            await utils.answer(status_msg, self.strings["file_too_large"].format(max_size=self.config["max_file_size"]))
            return

        await utils.answer(status_msg, self.strings["extracting"])
        audio_data = await self.extract_audio_from_video(video_path)
        
        if not audio_data:
            await utils.answer(status_msg, self.strings["recognition_failed"])
            return

        await utils.answer(status_msg, self.strings["processing"])
        
        result = await self.recognize_shazam(audio_data)
        
        if result:
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
                await status_msg.delete()
            else:
                response = self.strings["recognition_success"].format(
                    title=title_with_artist,
                    links=result['links']
                )
                await utils.answer(status_msg, response)
        else:
            await utils.answer(status_msg, self.strings["recognition_failed"])
