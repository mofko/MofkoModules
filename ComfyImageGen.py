__version__ = (1, 0, 2)
# meta developer: @mofkomodules, @pureoffic
# Name: ComfyImageGen
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/comfy_imagegen_banner.png
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/comfy_imagegen_banner.png
# meta fhsdesc: image generation, imagegen, comfy, comfyui, mofko, image, генерация, ии, комфи, изображения
# meta link: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/ComfyImageGen.py
# Diff: Добавлено: команда .cmon (мониторинг задач), расчёт примерного времени генерации, пинг юб в .ci для удобства. Фиксы: исправлена генерация от имени канала, исправлена генерация в под постом, исправлено получение рандом промпта (-i), другие мини-фиксы.
# requires: aiohttp pillow cachetools google-genai

import logging
import asyncio
import base64
import io
import json
import os
import time
import uuid
import random
import re
import string
import tempfile
import mimetypes
from urllib.parse import urlparse

import aiohttp
from cachetools import TTLCache
from PIL import Image
from herokutl.extensions import html
from herokutl.errors.rpcerrorlist import ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError
from herokutl.tl.functions.messages import GetForumTopicsByIDRequest, SendMediaRequest, SendMessageRequest

try:
    from google import genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from herokutl.tl.types import ForumTopicDeleted, Message, PeerChannel
try:
    from herokutl.tl.types import (
        DocumentAttributeFilename,
        InputMediaUploadedDocument,
        InputMediaUploadedPhoto,
        InputReplyToMessage,
        InputReplyToMonoForum,
    )
except ImportError:
    DocumentAttributeFilename = None
    InputMediaUploadedDocument = None
    InputMediaUploadedPhoto = None
    InputReplyToMessage = None
    InputReplyToMonoForum = None
from .. import loader, utils
from ..inline.types import InlineCall


logger = logging.getLogger(__name__)


class ComfyUIHTTPError(ValueError):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:500]}")

    @property
    def temporary(self):
        return self.status in (502, 503, 504)


class ComfyUIExecutionError(ValueError):
    pass


class UserFacingError(ValueError):
    def __init__(self, key, plain_message=None, **kwargs):
        self.key = key
        self.kwargs = kwargs
        super().__init__(plain_message or key)


_ASSETS_BASE_URL = "https://github.com/mofko/MofkoModules/raw/refs/heads/main/assets"
_ANIME_WF_URL = f"{_ASSETS_BASE_URL}/Anime_workflow.json"
_ANIME_V2_WF_URL = f"{_ASSETS_BASE_URL}/anime_v2_workflow.json"
_Z_IMAGE_TURBO_WF_URL = f"{_ASSETS_BASE_URL}/z_image_turbo_workflow.json"
_SDXL_REAL1_WF_URL = f"{_ASSETS_BASE_URL}/sdxl_real1_workflow.json"
_SDXL_REAL2_WF_URL = f"{_ASSETS_BASE_URL}/sdxl_real2_workflow.json"
_ERNIE_WF_URL = f"{_ASSETS_BASE_URL}/ernie_workflow.json"
_FLUX_EDIT_WF_URL = f"{_ASSETS_BASE_URL}/flux_i2i.json"
_UPSCALE_WF_URL = f"{_ASSETS_BASE_URL}/UpscaleWF1_clean.json"
_BGRM_WF_URL = f"{_ASSETS_BASE_URL}/bgremove.json"
_FRAMES_WF_URL = f"{_ASSETS_BASE_URL}/frames.json"
_MODULE_UPDATE_URL = "https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/ComfyImageGen.py"
_CIVITAI_IMAGES_URL = "https://civitai.com/api/v1/images"
_CSHARE_TOP_CHAT = "comfyideas"
_CSHARE_TOP_MESSAGE_ID = 5
_ENHANCE_PROMPT_URL = f"{_ASSETS_BASE_URL}/enhance_system_prompt.txt"
_DEFAULT_INFO_BANNER_URL = "https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/comfy_imagegen_banner_assets.png"
_UPDATE_NOTICE_LIMIT = 2
_STARTUP_UPDATE_CHECK_DELAY = 30
_STARTUP_UPDATE_CHECK_ATTEMPTS = 3
_ULT_GENS_TOPIC_EMOJI_ID = 5326048107497026134
_PREFLIGHT_EYES_INLINE = '<tg-emoji emoji-id="5424885441100782420">\U0001f440</tg-emoji>'
_EMOJI_THEME_DEFAULT = "default"
_EMOJI_THEME_COLORED = "colored"
_EMOJI_THEME_CUTE = "cute"
_EMOJI_THEME_BLACK = "black"
_EMOJI_THEME_TROLLFACE = "trollface"
_EMOJI_THEME_TAG_RE = re.compile(
    r'<(?P<tag>emoji|tg-emoji)\s+'
    r'(?:document_id|emoji-id)=["\']?(?P<id>\d+)["\']?\s*>'
    r'(?P<char>.*?)</(?P=tag)>',
    re.DOTALL,
)
_EMOJI_THEME_REPLACEMENTS = {
    _EMOJI_THEME_COLORED: {
        ("5121063440311386962", "\U0001f44e"): ("5278578973595427038", "\U0001f6ab"),
        ("5121063440311386962", "\u274c"): ("5278578973595427038", "\U0001f6ab"),
        ("5206607081334906820", "\u2705"): ("5206401524200145033", "\U0001f53c"),
        ("4904936030232117798", "\u2699"): ("5206626000665868017", "\U0001f4da"),
        ("4904936030232117798", "\u26a0"): ("5206222720416643915", "\U0001f514"),
        ("5985346521103604145", "\u2b1c"): ("5278578973595427038", "\U0001f6ab"),
        ("5444965220663458467", "\U0001f4c1"): ("5278227821364275264", "\U0001f4c1"),
        ("5188678912883827293", "\U0001f916"): ("5276127848644503161", "\U0001f916"),
        ("5764779661028495989", "\U0001f3a8"): ("5206211858444354221", "\U0001f9ea"),
        ("5206591666697306436", "\U0001f36d"): ("5276314275994954605", "\U0001f528"),
        ("5879841310902324730", "\u270f"): ("5276381204470329471", "\U0001f9d1\u200d\U0001f4bb"),
        ("5407001145740631266", "\U0001f910"): ("5278578973595427038", "\U0001f6ab"),
        ("5839354140261619193", "\U0001f6dc"): ("5278647306525108244", "\U0001f5a5"),
        ("5873225338984599714", "\U0001f4e4"): ("5206702193385700709", "\U0001f4e6"),
        ("5373342633798167891", "\U0001f4be"): ("5278753302023004775", "\u2139\ufe0f"),
        ("5870921681735781843", "\u23f1"): ("5276412364458059956", "\U0001f553"),
        ("5325547803936572038", "\u2764"): ("5206476089127372379", "\u2b50\ufe0f"),
        ("5334544901428229844", "\U0001f3b2"): ("5276395476646653290", "\U0001f50d"),
        ("5361979468887893611", "\U0001f195"): ("5276220667182736079", "\U0001f4e5"),
    },
    _EMOJI_THEME_CUTE: {
        ("5121063440311386962", "\U0001f44e"): ("5388955127681942181", "\U0001f970"),
        ("5121063440311386962", "\u274c"): ("5258506985103436605", "\U0001f97a"),
        ("5206607081334906820", "\u2705"): ("5386592741050326951", "\u2764\ufe0f"),
        ("4904936030232117798", "\u2699"): ("5386382721444519116", "\U0001f431"),
        ("4904936030232117798", "\u26a0"): ("5258033280275459503", "\U0001f606"),
        ("5985346521103604145", "\u2b1c"): ("5260600313508799670", "\U0001f408\u200d\u2b1b"),
        ("5444965220663458467", "\U0001f4c1"): ("5260681054598999309", "\U0001f43e"),
        ("5188678912883827293", "\U0001f916"): ("5260281691359946611", "\u2328\ufe0f"),
        ("5764779661028495989", "\U0001f3a8"): ("5364244578805250897", "\U0001f970"),
        ("5206591666697306436", "\U0001f36d"): ("5366052158741443031", "\U0001f9b4"),
        ("5879841310902324730", "\u270f"): ("5366263484017306348", "\U0001f430"),
        ("5407001145740631266", "\U0001f910"): ("5366337546433359364", "\U0001f44e"),
        ("5839354140261619193", "\U0001f6dc"): ("5341331263288538681", "\u2728"),
        ("5873225338984599714", "\U0001f4e4"): ("5258493176783581223", "\U0001f970"),
        ("5373342633798167891", "\U0001f4be"): ("5470076494283818173", "\U0001f97a"),
        ("5870921681735781843", "\u23f1"): ("5258210194273349779", "\U0001f970"),
        ("5325547803936572038", "\u2764"): ("5260281691359946611", "\u2328\ufe0f"),
        ("5334544901428229844", "\U0001f3b2"): ("5260450698323044545", "\U0001f970"),
        ("5361979468887893611", "\U0001f195"): ("5260323928068337625", "\U0001f431"),
    },
    _EMOJI_THEME_BLACK: {
        ("5121063440311386962", "\U0001f44e"): ("5192941702284864123", "\U0001f642"),
        ("5121063440311386962", "\u274c"): ("5193178101579803928", "\U0001f494"),
        ("5206607081334906820", "\u2705"): ("5192871045777879072", "\U0001f493"),
        ("4904936030232117798", "\u2699"): ("5454143866422706796", "\U0001f52b"),
        ("4904936030232117798", "\u26a0"): ("5456424949323412497", "\U0001f52f"),
        ("5985346521103604145", "\u2b1c"): ("5307569813864858174", "\u2753"),
        ("5444965220663458467", "\U0001f4c1"): ("5458739584508640009", "\u2626\ufe0f"),
        ("5188678912883827293", "\U0001f916"): ("5456556306603195188", "\U0001f642"),
        ("5764779661028495989", "\U0001f3a8"): ("5192858556012980770", "\U0001f470\u200d\u2642\ufe0f"),
        ("5206591666697306436", "\U0001f36d"): ("5456231044434902696", "\U0001f5a4"),
        ("5879841310902324730", "\u270f"): ("5458640512498022912", "\U0001f441"),
        ("5407001145740631266", "\U0001f910"): ("5307559991274651061", "\U0001f5a4"),
        ("5839354140261619193", "\U0001f6dc"): ("5303394457113083917", "\U0001f577\ufe0f"),
        ("5873225338984599714", "\U0001f4e4"): ("5456542094556414568", "\U0001f431"),
        ("5373342633798167891", "\U0001f4be"): ("5456664526894154591", "\U0001f431"),
        ("5870921681735781843", "\u23f1"): ("5353023431283591325", "\u23f3"),
        ("5325547803936572038", "\u2764"): ("5445243616148602729", "\U0001f5b1\ufe0f"),
        ("5334544901428229844", "\U0001f3b2"): ("5192859565330296406", "\U0001f595"),
        ("5361979468887893611", "\U0001f195"): ("5469946464148933378", "\U0001f62d"),
    },
    _EMOJI_THEME_TROLLFACE: {
        ("5121063440311386962", "\U0001f44e"): ("5422458393736536101", "\u26d1"),
        ("5121063440311386962", "\u274c"): ("5424679926915683083", "\u2620\ufe0f"),
        ("5206607081334906820", "\u2705"): ("5422604134861790377", "\U0001f642"),
        ("4904936030232117798", "\u2699"): ("5422732614513484798", "\u2620\ufe0f"),
        ("4904936030232117798", "\u26a0"): ("5422458561240259846", "\u2620\ufe0f"),
        ("5985346521103604145", "\u2b1c"): ("5422750421447891308", "\u2620\ufe0f"),
        ("5444965220663458467", "\U0001f4c1"): ("5422846817693884363", "\u263a\ufe0f"),
        ("5188678912883827293", "\U0001f916"): ("5422732614513484798", "\u2620\ufe0f"),
        ("5764779661028495989", "\U0001f3a8"): ("5422611986062006798", "\U0001f617"),
        ("5206591666697306436", "\U0001f36d"): ("5424747649960007887", "\U0001f697"),
        ("5879841310902324730", "\u270f"): ("5422376767883074291", "\U0001f5bc"),
        ("5407001145740631266", "\U0001f910"): ("5424599752761168855", "\U0001f5bc"),
        ("5839354140261619193", "\U0001f6dc"): ("5424794589657586686", "\U0001f603"),
        ("5873225338984599714", "\U0001f4e4"): ("5422874331254380688", "\U0001f642"),
        ("5373342633798167891", "\U0001f4be"): ("5422474044597360882", "\U0001f642"),
        ("5870921681735781843", "\u23f1"): ("5425146304529454719", "\U0001f4ef"),
        ("5325547803936572038", "\u2764"): ("5422732614513484798", "\u2620\ufe0f"),
        ("5334544901428229844", "\U0001f3b2"): ("5422727821329979692", "\U0001f453"),
        ("5361979468887893611", "\U0001f195"): ("5424679926915683083", "\u2620\ufe0f"),
    },
}
_EMOJI_THEME_ID_FALLBACKS = {
    _EMOJI_THEME_COLORED: {
        "5121063440311386962": ("5278578973595427038", "\U0001f6ab"),
        "5985346521103604145": ("5278578973595427038", "\U0001f6ab"),
        "5206607081334906820": ("5206401524200145033", "\U0001f53c"),
        "5444965220663458467": ("5278227821364275264", "\U0001f4c1"),
        "5188678912883827293": ("5276127848644503161", "\U0001f916"),
        "5764779661028495989": ("5206211858444354221", "\U0001f9ea"),
        "5206591666697306436": ("5276314275994954605", "\U0001f528"),
        "5879841310902324730": ("5276381204470329471", "\U0001f9d1\u200d\U0001f4bb"),
        "5407001145740631266": ("5278578973595427038", "\U0001f6ab"),
        "5839354140261619193": ("5278647306525108244", "\U0001f5a5"),
        "5873225338984599714": ("5206702193385700709", "\U0001f4e6"),
        "5373342633798167891": ("5278753302023004775", "\u2139\ufe0f"),
        "5870921681735781843": ("5276412364458059956", "\U0001f553"),
        "5325547803936572038": ("5206476089127372379", "\u2b50\ufe0f"),
        "5334544901428229844": ("5276395476646653290", "\U0001f50d"),
        "5361979468887893611": ("5276220667182736079", "\U0001f4e5"),
    },
    _EMOJI_THEME_CUTE: {
        "5206607081334906820": ("5386592741050326951", "\u2764\ufe0f"),
        "5985346521103604145": ("5260600313508799670", "\U0001f408\u200d\u2b1b"),
        "5444965220663458467": ("5260681054598999309", "\U0001f43e"),
        "5188678912883827293": ("5260281691359946611", "\u2328\ufe0f"),
        "5764779661028495989": ("5364244578805250897", "\U0001f970"),
        "5206591666697306436": ("5366052158741443031", "\U0001f9b4"),
        "5879841310902324730": ("5366263484017306348", "\U0001f430"),
        "5407001145740631266": ("5366337546433359364", "\U0001f44e"),
        "5839354140261619193": ("5341331263288538681", "\u2728"),
        "5873225338984599714": ("5258493176783581223", "\U0001f970"),
        "5373342633798167891": ("5470076494283818173", "\U0001f97a"),
        "5870921681735781843": ("5258210194273349779", "\U0001f970"),
        "5325547803936572038": ("5260281691359946611", "\u2328\ufe0f"),
        "5334544901428229844": ("5260450698323044545", "\U0001f970"),
        "5361979468887893611": ("5260323928068337625", "\U0001f431"),
    },
    _EMOJI_THEME_BLACK: {
        "5206607081334906820": ("5192871045777879072", "\U0001f493"),
        "5985346521103604145": ("5307569813864858174", "\u2753"),
        "5444965220663458467": ("5458739584508640009", "\u2626\ufe0f"),
        "5188678912883827293": ("5456556306603195188", "\U0001f642"),
        "5764779661028495989": ("5192858556012980770", "\U0001f470\u200d\u2642\ufe0f"),
        "5206591666697306436": ("5456231044434902696", "\U0001f5a4"),
        "5879841310902324730": ("5458640512498022912", "\U0001f441"),
        "5407001145740631266": ("5307559991274651061", "\U0001f5a4"),
        "5839354140261619193": ("5303394457113083917", "\U0001f577\ufe0f"),
        "5873225338984599714": ("5456542094556414568", "\U0001f431"),
        "5373342633798167891": ("5456664526894154591", "\U0001f431"),
        "5870921681735781843": ("5353023431283591325", "\u23f3"),
        "5325547803936572038": ("5445243616148602729", "\U0001f5b1\ufe0f"),
        "5334544901428229844": ("5192859565330296406", "\U0001f595"),
        "5361979468887893611": ("5469946464148933378", "\U0001f62d"),
    },
    _EMOJI_THEME_TROLLFACE: {
        "5206607081334906820": ("5422604134861790377", "\U0001f642"),
        "5985346521103604145": ("5422750421447891308", "\u2620\ufe0f"),
        "5444965220663458467": ("5422846817693884363", "\u263a\ufe0f"),
        "5188678912883827293": ("5422732614513484798", "\u2620\ufe0f"),
        "5764779661028495989": ("5422611986062006798", "\U0001f617"),
        "5206591666697306436": ("5424747649960007887", "\U0001f697"),
        "5879841310902324730": ("5422376767883074291", "\U0001f5bc"),
        "5407001145740631266": ("5424599752761168855", "\U0001f5bc"),
        "5839354140261619193": ("5424794589657586686", "\U0001f603"),
        "5873225338984599714": ("5422874331254380688", "\U0001f642"),
        "5373342633798167891": ("5422474044597360882", "\U0001f642"),
        "5870921681735781843": ("5425146304529454719", "\U0001f4ef"),
        "5325547803936572038": ("5422732614513484798", "\u2620\ufe0f"),
        "5334544901428229844": ("5422727821329979692", "\U0001f453"),
        "5361979468887893611": ("5424679926915683083", "\u2620\ufe0f"),
    },
}
_EMOJI_THEME_ERROR_ID_FALLBACKS = {
    _EMOJI_THEME_CUTE: {
        "\u274c": ("5258506985103436605", "\U0001f97a"),
        "*": ("5388955127681942181", "\U0001f970"),
    },
    _EMOJI_THEME_BLACK: {
        "\u274c": ("5193178101579803928", "\U0001f494"),
        "*": ("5192941702284864123", "\U0001f642"),
    },
    _EMOJI_THEME_TROLLFACE: {
        "\u274c": ("5424679926915683083", "\u2620\ufe0f"),
        "*": ("5422458393736536101", "\u26d1"),
    },
}
_GENERATION_TIMEOUT = 7200
_CUPSCALE_TIMEOUT = 1800
_GENERATION_IDLE_WARNING = 360
_QUEUE_POLL_INTERVAL = 5
_HISTORY_POLL_INTERVAL = 5
_CMON_POLL_INTERVAL = 10
_CMON_IDLE_CLOSE_AFTER = 600
_GENERATION_STATS_LIMIT = 30
_CT_PROBE_TIMEOUT = 180
_INLINE_TEXT_SOFT_LIMIT = 3800
_INLINE_TEXT_RETRY_LIMITS = (3500, 3000, 2500, 2000, 1500, 1000)
_COMFY_TIMEOUTS = {
    "ws_connect": 15,
    "queue_prompt": 60,
    "queue_status": 10,
    "queue_delete": 10,
    "interrupt": 10,
    "history_request": 15,
    "object_info": 15,
    "object_info_all": 30,
    "retrieve_media": 60,
    "upload_image": 60,
}
_ANIME_WORKFLOW_NAME = "Anime"
_ANIME_V2_WORKFLOW_NAME = "Anima"
_Z_IMAGE_TURBO_WORKFLOW_NAME = "ZImageTurbo"
_SDXL_REAL1_WORKFLOW_NAME = "SDXLReal1"
_SDXL_REAL2_WORKFLOW_NAME = "SDXLReal2"
_ERNIE_WORKFLOW_NAME = "Ernie"
_FLUX_EDIT_WORKFLOW_NAME = "FluxEdit"
_DEFAULT_WORKFLOW_NAME = _ANIME_WORKFLOW_NAME
_ANIME_POSITIVE_EMBEDDING = "embedding:lazypos,"
_GLOBAL_POSITIVE_DEFAULT = ""
_BUILTIN_WORKFLOW_POSITIVE_DEFAULTS = {
    _ANIME_WORKFLOW_NAME: _ANIME_POSITIVE_EMBEDDING,
}
_GLOBAL_NEGATIVE_DEFAULT = "worst quality, low quality, lowres, blurry, jpeg artifacts, sepia, bad anatomy, watermark, artist name,"
_REALISTIC_NEGATIVE_DEFAULT = "text, motion lines, effects, border, frame. (worst quality, low quality, normal quality, lowres, low details, oversaturated, undersaturated, overexposed, underexposed, grayscale, bad photo, bad photography, bad art:1.4)"
_BUILTIN_WORKFLOW_NEGATIVE_DEFAULTS = {
    _ANIME_WORKFLOW_NAME: "embedding:lazyneg,",
    _ANIME_V2_WORKFLOW_NAME: "Score_6, score_5, score_4, worst quality, low quality, jpeg artifacts, blurry, text, watermark, logo, signature, bad anatomy, bad hands, extra limbs, missing limbs, fused fingers, bad face, realistic, photorealistic, 3d, render, flat shading, unnatural shadows, aliasing, distortion, compression artifacts, corrupted, oversaturated, washed out colors",
    _SDXL_REAL1_WORKFLOW_NAME: _REALISTIC_NEGATIVE_DEFAULT,
    _SDXL_REAL2_WORKFLOW_NAME: _REALISTIC_NEGATIVE_DEFAULT,
    _Z_IMAGE_TURBO_WORKFLOW_NAME: "lowres,",
    _ERNIE_WORKFLOW_NAME: "lowres,",
    _FLUX_EDIT_WORKFLOW_NAME: "",
}
_BUILTIN_WORKFLOW_URLS = {
    _ANIME_WORKFLOW_NAME: _ANIME_WF_URL,
    _ANIME_V2_WORKFLOW_NAME: _ANIME_V2_WF_URL,
    _Z_IMAGE_TURBO_WORKFLOW_NAME: _Z_IMAGE_TURBO_WF_URL,
    _SDXL_REAL1_WORKFLOW_NAME: _SDXL_REAL1_WF_URL,
    _SDXL_REAL2_WORKFLOW_NAME: _SDXL_REAL2_WF_URL,
    _ERNIE_WORKFLOW_NAME: _ERNIE_WF_URL,
    _FLUX_EDIT_WORKFLOW_NAME: _FLUX_EDIT_WF_URL,
}
_BUILTIN_WORKFLOW_TELEGRAM_URLS = {
    _ANIME_WORKFLOW_NAME: "https://t.me/comfystorage/12",
    _ANIME_V2_WORKFLOW_NAME: "https://t.me/comfystorage/15",
    _SDXL_REAL1_WORKFLOW_NAME: "https://t.me/comfystorage/16",
    _SDXL_REAL2_WORKFLOW_NAME: "https://t.me/comfystorage/18",
    _Z_IMAGE_TURBO_WORKFLOW_NAME: "https://t.me/comfystorage/19",
    _ERNIE_WORKFLOW_NAME: "https://t.me/comfystorage/20",
    _FLUX_EDIT_WORKFLOW_NAME: "https://t.me/comfystorage/27",
}
_UPSCALE_WORKFLOW_TELEGRAM_URL = "https://t.me/comfystorage/21"
_BGRM_WORKFLOW_TELEGRAM_URL = "https://t.me/comfystorage/25"
_FRAMES_WORKFLOW_TELEGRAM_URL = "https://t.me/comfystorage/26"
_CTOOL_UPSCALE = "upscale"
_CTOOL_RMBG = "rmbg"
_CTOOL_FPS = "fps"

@loader.tds
class ComfyImageGenMod(loader.Module):
    """Image generation module via ComfyUI
    Модуль генерации изображений через ComfyUI.
    Поддерживает локальную генерацию любых изображений/видео и т.д. Примеры генераций через модуль можно посмотреть здесь: @comfyideas.
    Перед использованием модуля рекомендуется открыть справку командой .chelp.
    """

    strings = {
        "name": "ComfyImageGen",
        "cfg_url": "ComfyUI Base URL (e.g., http://127.0.0.1:8188)",
        "cfg_model": "Default model file (e.g., waiIllustriousSDXL_v170)",
        "cfg_max_mb": "Max input image size in MB for img2img",
        "cfg_max_output_mb": "Max output media size in MB",
        "cfg_output_format": "Result output format: photo (Telegram compressed image), document_png (PNG file lossless)",
        "cfg_ws_update_interval": "Generation status update interval in seconds: 1-5, 0 disables",
        "cfg_gemini_api_key": "Gemini API key for AI prompt enhancement",
        "cfg_groq_api_key": "Groq API key for AI prompt enhancement",
        "cfg_openrouter_api_key": "OpenRouter API key for AI prompt enhancement",
        "cfg_grok_api_key": "Grok/xAI API key for AI prompt enhancement",
        "cfg_deepseek_api_key": "DeepSeek API key for AI prompt enhancement",
        "cfg_update_assets": "Background module assets update interval in seconds. 0 disables it. Range: 60-14400.",
        "cfg_info_banner_url": "Banner URL for .ci and .chelp inline menus. Set 0 to disable.",
        "lora_title": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> LoRA selection',
        "lora_prompt_label": "Prompt",
        "lora_page": "Page {}/{}",
        "lora_detail_title": '<tg-emoji emoji-id="4904936030232117798">\u2699</tg-emoji> {}\nWeight: {:.1f}\nStatus: {}',
        "lora_on": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Enabled',
        "lora_off": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji> Disabled',
        "lora_loading": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Loading LoRA list from ComfyUI...",
        "lora_load_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed to load LoRA list from ComfyUI.",
        "lora_none_available": "No LoRA models found on ComfyUI server.",
        "preflight_preparing": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Preparing generation...",
        "preflight_workflow": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Loading workflow...",
        "preflight_model": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Preparing model...",
        "preflight_image": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Preparing input image...",
        "preflight_launch": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Starting generation...",
        "fmt_loras": "LoRA:",
        "fmt_loras_more": "and {} more",
        "no_url": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> ComfyUI URL is not specified. Use .cfg ComfyImageGen comfyui_url",
        "no_prompt": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Please provide a prompt.",
        "prompt_empty": "No prompt",
        "status_civitai_inspire": "<emoji document_id=5334544901428229844>\U0001f3b2</emoji> Getting a random Civitai prompt...",
        "civitai_no_prompt": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Could not find a random Civitai prompt.",
        "civitai_error": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed to get a prompt from Civitai.",
        "connecting": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Connecting to ComfyUI...",
        "connecting_retry": "ComfyUI did not respond, retrying connection... {}/{}",
        "uploading": "<emoji document_id=5873225338984599714>\U0001f4e4</emoji> Uploading result...",
        "success": "<emoji document_id=5206607081334906820>\u2705</emoji> Generated!\n<emoji document_id=5879841310902324730>\u270f\ufe0f</emoji> Prompt: {}\n<emoji document_id=5407001145740631266>\U0001f910</emoji> Negative: {}\n<emoji document_id=5206591666697306436>\U0001f36d</emoji> Model: {}\n<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Workflow: {}",

        "timeout": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Generation timeout.",
        "unavailable": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> ComfyUI is unavailable.",
        "img_too_large": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Input image is too large (max. {} MB).",
        "output_too_large": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Output media is too large (max. {} MB).",
        "no_reply_photo": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Reply to a photo for img2img.",
        "wf_not_found": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Workflow '{}' not found. Available: {}",
        "add_wf_no_reply": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Reply to a JSON file to add a workflow.",
        "add_wf_bad_json": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Invalid JSON workflow file.",
        "wf_file_too_large": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Workflow JSON is too large. Max size: 10 MB.",
        "add_wf_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Workflow '{}' added.",
        "add_wf_exists": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Workflow '{}' already exists.",
        "add_wf_no_name": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Specify the workflow name to add.",
        "add_wf_force_btn": "\u2705 Add anyway",
        "add_wf_forced_note": "<emoji document_id=4904936030232117798>\u26a0\ufe0f</emoji> Added despite validation errors.",
        "add_wf_force_expired": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> This add workflow request expired. Run addwf again.",
        "del_wf_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Workflow '{}' deleted.",
        "del_wf_all_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Deleted all custom workflows: {}.",
        "del_wf_fail": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Workflow '{}' not found.",
        "del_wf_builtin": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Cannot delete built-in workflow '{}'.",
        "wf_title": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Select workflow',
        "wf_builtin_btn": "\U0001f4e6 Built-in",
        "wf_custom_btn": "\U0001f4dd Custom",
        "wf_list_title_builtin": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Built-in workflows',
        "wf_list_title_custom": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Custom workflows',
        "wf_desc_anime": "Anime image generation, accepts all ill, pony, SD models and similar ones.",
        "wf_desc_anime_v2": "Second anime workflow, works on Anima models. MiaoMiao is recommended [https://civitai.red/models/934764/miaomiao-harem?modelVersionId=2967371].",
        "wf_desc_zimage_turbo": "Realistic image generation, does not support i2i. Made for intorealism_zit [https://civitai.red/models/1609320/intorealism?modelVersionId=2912231], but you can try other models too.",
        "wf_desc_sdxl_real1": "Realistic SDXL 1.0 workflow made for mopMixtureOfPerverts_v20 [https://civitai.red/models/1854124?modelVersionId=2159501].",
        "wf_desc_sdxl_real2": "If you do not really like SDXLReal1, this is the second realistic SDXL workflow, using xxxRay_dmd2 [https://civitai.red/models/1064836/xxx-ray].",
        "wf_desc_ernie": "Workflow with the newest Ernie model. On a mid-range GPU generation takes about 2-3 minutes on average. Works great with text, infographics and any requests when the prompt is good. Uses RedCraft [https://civitai.red/models/958009/redcraft-or].",
        "wf_desc_fluxedit": "Image editing for mid-range PCs, uses Flux2-Klein.",
        "wf_page": "Page {}/{}",
        "wf_current": "Current: {}",
        "wf_limited_hint": 'Second tap on a workflow enables <tg-emoji emoji-id="5271842287326863410">🔵</tg-emoji> limited mode. Only positive prompt, negative prompt, and media inputs remain editable. This beta feature is mainly made for video generation.',
        "wf_limited_set": "Workflow set: {} (limited mode)",
        "toast_wf_limited_on": "Limited mode enabled: {}",
        "toast_wf_limited_off": "Limited mode disabled: {}",
        "info_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> ComfyUI Status",
        "ci_loading": "Checking ComfyUI...",
        "info_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Connected",
        "info_fail": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Unavailable",
        "info_model": "<emoji document_id=5206591666697306436>\U0001f36d</emoji> Model: {}",
        "info_wf": "<emoji document_id=5444965220663458467>\U0001f4c1</emoji> Current Workflow: {}",
        "info_gpu": "<emoji document_id=5839354140261619193>\U0001f6dc</emoji> GPU: {}",
        "info_cpu": "<emoji document_id=5839354140261619193>\U0001f6dc</emoji> CPU: {}",
        "info_device": "<emoji document_id=5839354140261619193>\U0001f6dc</emoji> Device: {}",
        "info_no_device": "not detected",
        "info_vram": "<emoji document_id=5373342633798167891>\U0001f4be</emoji> VRAM: {} / {}",
        "info_ram": "<emoji document_id=5373342633798167891>\U0001f4be</emoji> RAM: {} / {}",
        "info_version": "Version: {}",
        "info_python": "Python: {}",
        "info_pytorch": "PyTorch: {}",
        "info_frontend": "Frontend: {}",
        "info_total_generations": "Total generations: {}",
        "info_userbot_ping": "Userbot ping: {} ms",
        "ct_checking": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Checking ComfyUI tunnel API...",
        "ct_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> ComfyUI tunnel probe",
        "ct_url": "URL: <code>{}</code>",
        "ct_status": "Status: {}",
        "ct_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> OK",
        "ct_fail": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed",
        "ct_no_checks": "No checks were run.",
        "ct_bad_url": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Invalid URL.",
        "ct_upload_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Probe image generated, but Telegram upload failed: <code>{}</code>",
        "no_images": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> No images in ComfyUI response.",

        "no_mapping_pos": "<emoji document_id=5913376703312302899>\U0001f4e3</emoji> Could not find positive prompt node in workflow.",
        "models_title": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> Select ComfyUI model',
        "models_loading": "Loading ComfyUI models...",
        "models_page": "Page {}/{}",
        "models_set": "<emoji document_id=5206607081334906820>\u2705</emoji> Model set: {}",
        "models_empty": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> No checkpoint or UNET models found.",
        "models_manual_btn": "\u270f\ufe0f Enter manually",
        "models_manual_input": "Enter model filename:",

        "setwf_ok": "Workflow set: {}",
        "mlwf_no_name": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Specify workflow name to export.",
        "mlwf_not_found": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Workflow '{}' not found.",
        "mlwf_success": "<emoji document_id=5206607081334906820>\u2705</emoji> Workflow '{}' exported.",
        "unexpected_comfy_response": "ComfyUI returned unexpected content. Check ComfyUI logs for errors.",
        "enhance_no_key": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} API key not set. Open {}",
        "enhance_dependency_missing": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> google-genai is not installed. Install module requirements or reinstall the module.",
        "enhance_key_expired": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} API key is invalid or exhausted.",
        "enhance_censored": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} blocked the prompt (censorship). Try another provider.",
        "enhance_rate_limit": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} rate limit exceeded. Try again later.",
        "enhance_timeout": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} did not respond in time while enhancing the prompt. Try again later.",
        "enhance_service_error": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} returned an unexpected error while enhancing the prompt. Try again later.",
        "enhance_vision_unsupported": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> The selected AI provider/model ({}) does not support image input. Use a vision-capable provider/model or run without -ai.",
        "enhance_error": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} error during prompt enhancement: {}",
        "enhance_cmd_title": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> Enhanced prompt',
        "enhance_cmd_provider": "Provider: {}",
        "enhance_cmd_model": "AI model: <code>{}</code>",
        "enhance_cmd_original": "Original prompt:",
        "enhance_cmd_result": "Enhanced prompt:",
        "enhanced_label": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> AI prompt:',
        "enhance_chat_title": "AI prompt edit [{}/100]",
        "enhance_chat_edit_btn": "\u270f\ufe0f Edit prompt",
        "enhance_chat_input": "What should be changed in the prompt?",
        "enhance_chat_limit": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Edit limit reached: 100/100.",
        "enhance_chat_empty": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Send what should be changed.",
        "err_connection": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed to connect to ComfyUI. Make sure the server is running and the URL is correct.",
        "err_node_missing": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Component '{}' is not installed in ComfyUI. Install the missing custom node.",
        "err_model_not_found": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Model '{}' not found on server. Check the name or download the model.",
        "err_model_value_not_in_list": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Selected model does not exist or is not suitable for this workflow.\n\nModel: <code>{}</code>\nAvailable models:\n{}",
        "err_vram": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Insufficient VRAM. Try reducing image size or number of steps.",
        "err_image_invalid": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed to process image. File is corrupted or format is not supported.",
        "err_img2img_unsupported": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> This workflow does not support img2img. Add an image input or latent switch node.",
        "err_upload_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed to upload image to ComfyUI server.",
        "err_retrieve_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed to retrieve generation result from server.",
        "err_send_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed to send result to Telegram. Check chat permissions or try document_png.",
        "err_workflow_invalid": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Workflow is corrupted or contains errors.",
        "err_workflow_invalid_details": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Workflow validation failed:\n{}",
        "err_vae_not_found": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Could not determine VAE for img2img. Check your workflow.",
        "err_prompt_queue": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> ComfyUI rejected the generation task. Check server logs.",
        "err_execution": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Error during generation in ComfyUI. Check server logs.",
        "err_none_input": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> One of the workflow components did not receive input data. Make sure all models are loaded and nodes are connected correctly.",
        "err_generic": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> An unexpected error occurred. Details in logs.",
        "err_workflow_download": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Failed to download built-in workflow. Check internet connection.",
        "err_server_unavailable": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> ComfyUI temporarily unavailable (502/503/504). Server is overloaded or restarting. Try again in a minute.",
        "status_enhancing": "<emoji document_id=5325547803936572038>\u2764\ufe0f</emoji> Enhancing prompt with AI...",
        "argset_title": '<tg-emoji emoji-id="4904936030232117798">\u2699\ufe0f</tg-emoji> Default generation arguments',
        "argset_limited_mode": "🔵 Limited workflow mode is enabled. Workflow-changing settings are ignored.",
        "argset_params": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> Generation parameters (defaults come from the current workflow)',
        "argset_enhancements": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> Enhancements',
        "argset_on": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji>',
        "argset_off": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji>',
        "argset_input_width": "Enter Width (64-4096):",
        "argset_input_height": "Enter Height (64-4096):",
        "argset_input_steps": "Enter Steps (1-100):",
        "argset_input_cfg": "Enter CFG (1.0-30.0):",
        "argset_input_denoise": "Enter Denoise (0.0-1.0):",
        "argset_input_sampler_name": "Enter sampler_name:",
        "argset_input_scheduler": "Enter scheduler:",
        "label_sampler_name": "Sampler",
        "label_scheduler": "Scheduler",
        "argset_choice_workflow": "In workflow: {}",
        "argset_choice_used": "Used: {}",
        "argset_choice_as_workflow": "As in workflow",
        "argset_choice_custom": "\u270d Custom",
        "argset_choice_clear": "\U0001f5d1 Clear",
        "argset_choice_saved": "Saved: {}",
        "argset_pin_model": "📌 Pin for model",
        "argset_pin_model_ok": "Pinned for model: {}",
        "provider_title": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> AI enhancement provider',
        "provider_current": "Current: {}",
        "provider_status": "Status: {}",
        "provider_selected": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Selected',
        "provider_not_selected": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji> Not selected',
        "provider_api_key": "API key: {}",
        "provider_api_key_set": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> set',
        "provider_api_key_missing": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji> not set',
        "provider_model": "Model: {}",
        "provider_btn_select": "\u2705 Select",
        "provider_btn_api_key": "\U0001f511 API key",
        "provider_btn_model": "\U0001f9e0 Model",
        "provider_btn_menu": "\U0001f916 AI provider",
        "enhance_prompt_btn_menu": "\U0001f4dd Model prompts",
        "enhance_prompts_title": '<tg-emoji emoji-id="5879780659840499724">\U0001f4dd</tg-emoji> Model prompts',
        "enhance_prompt_current_url": "URL: {}",
        "enhance_prompt_source": "Source: {}",
        "enhance_prompt_source_default": "default",
        "enhance_prompt_source_custom": "custom",
        "enhance_prompt_btn_set": "\u270d Set URL",
        "enhance_prompt_btn_reset": "\U0001f504 Reset to default",
        "enhance_prompt_btn_download": "\U0001f4c4 Download",
        "enhance_prompt_input_url": "Enter prompt URL for {}:",
        "enhance_prompt_saved": "Prompt URL saved",
        "enhance_prompt_reset": "Prompt URL reset to default",
        "enhance_prompt_invalid_url": "Invalid URL",
        "enhance_prompt_download_failed": "Failed to download prompt",
        "enhance_prompt_file_caption": "Enhance prompt for {}",
        "provider_input_api_key": "Enter API key for {}:",
        "provider_input_model": "Enter model:",
        "provider_saved": "Provider selected: {}",
        "provider_key_saved": "API key saved",
        "provider_model_saved": "Model saved",
        "lora_presets_title": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> LoRA presets',
        "lora_presets_empty": "No LoRA presets selected.",
        "lora_presets_selected": "Selected: {}",
        "lora_presets_clear": "\U0001f5d1 Clear all",
        "lora_presets_saved": "LoRA presets saved",
        "lora_weight_btn": "\u270d Weight",
        "lora_weight_input": "Enter LoRA weight (0.1-2.0):",
        "lora_weight_saved": "LoRA weight saved",
        "label_lora_presets": "LoRA presets",
        "positive_menu_title": '<tg-emoji emoji-id="5879841310902324730">\u270f\ufe0f</tg-emoji> Positive prompts',
        "positive_global": "Global positive",
        "positive_workflows": "Workflow positives",
        "positive_current": "Current:",
        "positive_custom": "Custom:",
        "positive_global_label": "Global:",
        "positive_btn_global": "\U0001f310 Global positive",
        "positive_btn_set": "\u270d Set new",
        "positive_btn_reset": "\U0001f504 Reset to default",
        "positive_btn_clear": "\U0001f5d1 Clear",
        "positive_input_global": "Enter global positive prompt:",
        "positive_input_workflow": "Enter positive prompt for {}:",
        "positive_saved": "Positive prompt saved",
        "positive_reset": "Positive prompt reset",
        "positive_cleared": "Positive prompt cleared",
        "negative_menu_title": '<tg-emoji emoji-id="5407001145740631266">\U0001f910</tg-emoji> Negative prompts',
        "negative_global": "Global negative",
        "negative_workflows": "Workflow negatives",
        "negative_source_custom": "custom",
        "negative_source_global": "global",
        "negative_source_workflow": "workflow",
        "negative_source_empty": "empty",
        "negative_current": "Current:",
        "negative_custom": "Custom:",
        "negative_global_label": "Global:",
        "negative_workflow_default": "Workflow default:",
        "negative_source": "Source: {}",
        "negative_not_set": "not set",
        "negative_btn_global": "\U0001f310 Global negative",
        "negative_btn_set": "\u270d Set new",
        "negative_btn_reset": "\U0001f504 Reset to default",
        "negative_btn_clear": "\U0001f5d1 Clear",
        "negative_input_global": "Enter global negative prompt:",
        "negative_input_workflow": "Enter negative prompt for {}:",
        "negative_saved": "Negative prompt saved",
        "negative_reset": "Negative prompt reset",
        "negative_cleared": "Negative prompt cleared",
        "err_reserved_wf": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Name 'i2i' is reserved by built-in module. Try another.",
        "del_wf_no_name_with_list": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Specify workflow name to delete.\n\nAvailable custom workflows:\n{}\n\nExample:\n<code>.delwf {}</code>",
        "del_wf_no_custom": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> No custom workflows to delete.",
        "repeat_no_last": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> No saved generation to repeat.",
        "progress": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Generating... {}%\n<emoji document_id=5879841310902324730>\u270f\ufe0f</emoji> Prompt: {}\n<emoji document_id=5407001145740631266>\U0001f910</emoji> Negative: {}\n<emoji document_id=5206591666697306436>\U0001f36d</emoji> Model: {}\n<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Workflow: {}",
        "inline_uploading": '<tg-emoji emoji-id="5873225338984599714">\U0001f4e4</tg-emoji> Uploading result...',
        "cancelled": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Generation cancelled.',
        "cancel_btn": "\u274c Cancel",
        "help_text": (
            "<b>ComfyImageGen guide</b>\n\n"
            '1. <a href="https://t.me/ComfyUIGuide/3">Установка ComfyUI</a>\n'
            '2. <a href="https://t.me/ComfyUIGuide/7">Как генерировать?</a>\n'
            '3. <a href="https://t.me/ComfyUIGuide/8">Терминология</a>\n'
            '4. <a href="https://t.me/ComfyUIGuide/9">.comfy</a>\n'
            '5. <a href="https://t.me/ComfyUIGuide/10">.cshare</a>\n'
            '6. <a href="https://t.me/ComfyUIGuide/11">.ctools</a>\n'
            '7. <a href="https://t.me/ComfyUIGuide/12">.setarg</a>\n'
            '8. <a href="https://t.me/ComfyUIGuide/13">.ultcomfy</a>\n'
            '9. <a href="https://t.me/ComfyUIGuide/14">Свой вф</a>\n'
            '10. <a href="https://t.me/ComfyUIGuide/15">Ссылочки</a>'
        ),
        "fmt_generating": "Generating...",
        "fmt_generating_pct": "Generating... {}%",
        "fmt_loading_model": "Loading model...",
        "fmt_encoding_prompt": "Encoding prompt...",
        "queue_local_waiting": "Waiting in generation queue...",
        "queue_comfy_submitted": "Task submitted to ComfyUI. Waiting for status... <i>(WebSocket may be unavailable)</i>",
        "queue_comfy_pending": "Waiting in ComfyUI queue... Position: {}",
        "queue_comfy_pending_unknown": "Waiting in ComfyUI queue...",
        "queue_comfy_other_running": "Another ComfyUI task is running. Waiting in queue... Position: {}",
        "queue_comfy_other_running_unknown": "Another ComfyUI task is running. Waiting in ComfyUI queue...",
        "queue_comfy_running": "ComfyUI is still executing the task...",
        "queue_comfy_running_ws_fallback": "ComfyUI is still executing the task... <i>(websocket temporarily unavailable)</i>",
        "queue_idle_warning": "No progress from ComfyUI for 6 minutes. Checking queue...",
        "fmt_generation_eta": "Remaining: {}",
        "cmon_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> ComfyUI task monitor",
        "cmon_starting": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Monitoring...",
        "cmon_loading": "Checking ComfyUI tasks...",
        "cmon_no_tasks": "No active tasks.",
        "cmon_closed_idle": "No active tasks for 10 minutes. Monitor closed.",
        "cmon_active": "Active task: <code>{}</code>",
        "cmon_active_other": "Active task: <code>{}</code> <i>(not ours)</i>",
        "cmon_active_unknown": "Active task: detected",
        "cmon_current_node": "Current process: {}",
        "cmon_progress": "Progress: {}%",
        "cmon_last_check": "Updated: {}",
        "cmon_unavailable": "Could not read ComfyUI queue.",
        "fmt_decoding_image": "Decoding image...",
        "fmt_processing_image": "Processing image...",
        "fmt_upscaling_image": "Upscaling image...",
        "fmt_detailing_face": "Detailing face...",
        "fmt_saving_result": "Saving result...",
        "fmt_applying_lora": "Applying LoRA...",
        "fmt_running_node": "Running: {}",
        "fmt_cached_nodes": "Using cached nodes: {}",
        "easter_nothing": "Nothing already exists. Try generating something.",
        "easter_ritual_progress": "Ritual progress: {}%",
        "easter_dream_unavailable": "<emoji document_id=5121063440311386962>👎</emoji> ComfyUI is not responding. Maybe it went to watch its dreams.",
        "easter_noise_form": "Noise is taking shape...",
        "easter_long_prompt": "ComfyUI is reading this novel...",
        "easter_long_prompt_rare": "ComfyUI is sorting details onto shelves...",
        "easter_backrooms": "ComfyUI is looking for the exit from level {}...",
        "easter_short_prompt": "The prompt is too modest. Comfy will think for you...",
        "fmt_prompt": "Prompt:",
        "fmt_model": "Model:",
        "fmt_workflow": "Workflow:",
        "fmt_generation_time": "Time: {}",
        "fmt_done": "Generated!",
        "btn_params": "\U0001f3a8 Parameters",
        "btn_enhancements": "\U0001f916 Enhancements",
        "btn_reset_all": "\U0001f504 Reset all",
        "btn_close": "\u274c Close",
        "btn_back": "\U0001f519 Back",
        "btn_generate": "\U0001f680 Generate",
        "btn_cancel": "\u274c Cancel",
        "btn_toggle_on": "\u2705 On",
        "btn_toggle_off": "\u274c Off",
        "label_ai_enhance": "AI Enhancement",
        "toast_model_set": "Model set: {}",
        "toast_wf_set": "Workflow set: {}",
        "toast_no_custom_wf": "No custom workflows",
        "toast_invalid_value": "Invalid value: {}",
        "toast_defaults_reset": "Defaults reset to workflow values",
        "free_btn": "\U0001f9f9 Free memory",
        "force_free_btn": "\U0001f9ef Force clear",
        "refresh_btn": "\U0001f504 Refresh",
        "free_ok": "ComfyUI memory freed.",
        "force_free_ok": "ComfyUI generation interrupted and memory cleared.",
        "free_fail": "Failed to free ComfyUI memory.",
        "free_busy": "Generation is running, memory was not freed.",
        "checkwf_no_reply": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Reply to a workflow JSON file.",
        "checkwf_bad_json": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Invalid workflow JSON.",
        "checkwf_checking": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Checking workflow: {}...",
        "checkwf_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Workflow check: {}",
        "checkwf_saved_title": "<emoji document_id=5206607081334906820>\u2705</emoji> Workflow added: {}",
        "wf_validation_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Workflow passed validation.",
        "wf_validation_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Workflow failed validation.",
        "wf_validation_found": "\n<b>Found:</b>",
        "wf_validation_warnings": "\n<b>Warnings:</b>",
        "wf_validation_critical": "\n<b>Critical errors:</b>",
        "wf_validation_missing_nodes": "\n<b>Missing nodes:</b>",
        "wf_validation_node_pack": "{} — possible pack: {}",
        "wf_validation_object_info_fail": "Could not fetch installed node list from ComfyUI.",
        "wf_validation_missing_optional": "{} not found.",
        "wf_validation_missing_inputs": "Node {} ({}) missing required inputs: {}.",
        "wf_validation_empty": "Workflow is empty or invalid.",
        "wf_validation_node_invalid": "Workflow contains invalid node data.",
        "wf_validation_no_positive": "Positive prompt node not found.",
        "wf_validation_no_model": "Model node not found.",
        "wf_validation_no_output": "Output node not found.",
        "wf_icon_found": "<emoji document_id=5206607081334906820>\u2705</emoji>",
        "wf_icon_missing": "<emoji document_id=5985346521103604145>\u2b1c</emoji>",
        "wf_icon_error": "<emoji document_id=5121063440311386962>\u274c</emoji>",
        "wf_icon_warning": "<emoji document_id=4904936030232117798>\u26a0\ufe0f</emoji>",
        "wf_check_positive": "Positive prompt",
        "wf_check_negative": "Negative prompt",
        "wf_check_model": "Model",
        "wf_check_seed": "Seed",
        "wf_check_steps": "Steps",
        "wf_check_cfg": "CFG",
        "wf_check_output": "Output",
        "wf_check_size": "Size",
        "wf_check_denoise": "Denoise",
        "wf_check_img2img": "Img2Img input",
        "wf_check_output_kind": "Output kind: {}",
        "wf_check_input_kind": "Input kind: {}",
        "wf_check_frames": "Frames",
        "wf_check_fps": "FPS",
        "ult_title": '<tg-emoji emoji-id="4904936030232117798">\u2699\ufe0f</tg-emoji> Additional settings',
        "ult_ai_title": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> AI enhancement',
        "ult_ai_auto": "Auto enhancement: {}",
        "ult_ai_prompt_confirm": "Prompt confirmation: {}",
        "ult_ai_provider": "Provider: {}",
        "ult_ai_model": "Model: {}",
        "ult_ai_key": "API key: {}",
        "ult_ai_desc": "The -ai flag still enables AI enhancement for one generation.",
        "ult_ai_key_path": ".ultcomfy -> AI enhancement -> AI provider",
        "ult_btn_ai": "\U0001f916 AI enhancement",
        "ult_btn_ai_auto": "\U0001f916 Auto enhancement",
        "ult_btn_prompt_confirm": "\U0001f916 Prompt confirmation",
        "ult_gens_title": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Generation archive',
        "ult_gens_desc": "Save every successful generation to the generation archive in maximum quality with the prompt and model.",
        "ult_trigger_title": '<tg-emoji emoji-id="4904936030232117798">\u2699\ufe0f</tg-emoji> Trigger generation',
        "ult_trigger_desc": "Generate images when a message starts with the trigger word in this chat.",
        "ult_time_title": '<tg-emoji emoji-id="5870921681735781843">\u23f1</tg-emoji> Generation time',
        "ult_theme_title": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> Emoji theme',
        "ult_theme_status": "Emoji theme: {}",
        "ult_censorship_status": "Censorship: {}",
        "ult_btn_censorship_on": "\U0001f910 Censorship Enabled",
        "ult_btn_censorship_off": "\U0001f910 Censorship Disabled",
        "ult_time_progress": "Generation time while running: {}",
        "ult_time_result": "Generation time after result: {}",
        "ult_trigger_chat": "Chat: <code>{}</code>",
        "ult_trigger_word": "Trigger: <code>{}</code>",
        "ult_trigger_autodelete": "Auto-delete result: {}",
        "ult_trigger_delay": "Auto-delete after: {}",
        "ult_trigger_queue": "Max queue: {}",
        "ult_trigger_steps_limit": "Max steps: {}",
        "ult_trigger_active": "Active now: {}",
        "ult_trigger_russian_guard": "Reject Russian prompt without -ai: {}",
        "ult_trigger_blacklist": "Blacklist: <code>{}</code>",
        "ult_trigger_word_input": "Enter trigger word:",
        "ult_trigger_delay_input": "Enter auto-delete time in seconds:",
        "ult_trigger_queue_input": "Enter max queue size:",
        "ult_trigger_steps_input": "Enter trigger max steps (1-100):",
        "ult_trigger_saved": "Trigger settings updated",
        "ult_trigger_reject_russian": "Block Russian prompt",
        "ult_trigger_blacklist_empty": "Trigger blacklist is empty.",
        "ult_trigger_blacklist_title": "<b>Trigger blacklist</b>",
        "ult_trigger_blacklist_added": "User added to trigger blacklist.",
        "ult_trigger_blacklist_removed": "User removed from trigger blacklist.",
        "ult_trigger_blacklist_no_user": "Reply to a user or specify @username/user id.",
        "ult_btn_trigger_blacklist": "🚫 Blacklist",
        "trigger_russian_requires_ai": "<emoji document_id=5121063440311386962>👎</emoji> Trigger generation with Russian prompt is allowed only with -ai.",
        "trigger_too_often": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Too often.",
        "ult_status_on": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Enabled',
        "ult_status_off": '<tg-emoji emoji-id="5121063440311386962">\u274c</tg-emoji> Disabled',
        "ult_btn_prompt": "\U0001f916 Prompt confirmation",
        "ult_btn_gens": "\U0001f4c1 Generation archive",
        "ult_btn_trigger": "\u26a1 Trigger generation",
        "ult_btn_time": "\u23f1 Generation time",
        "ult_btn_theme": "Theme",
        "ult_btn_theme_default": "Default",
        "ult_btn_theme_colored": "Colored",
        "ult_btn_theme_cute": "Cute",
        "ult_btn_theme_black": "Black",
        "ult_btn_theme_trollface": "Trollface",
        "ult_btn_time_progress": "\u23f1 During",
        "ult_btn_time_result": "\u23f1 Result",
        "ult_btn_trigger_word": "\u270d Trigger word",
        "ult_btn_trigger_delay": "\u23f1 Delete time",
        "ult_btn_trigger_queue": "\U0001f4e6 Queue",
        "ult_btn_trigger_steps": "\U0001f3a8 Steps limit",
        "ult_btn_create_chat": "\U0001f3d7 Create archive",
        "ult_btn_recreate_chat": "\U0001f504 Add archive",
        "ult_btn_bind_chat": "\U0001f517 Bind archive",
        "ult_btn_remove_chat": "\U0001f5d1 Remove target",
        "ult_btn_clear_chats": "\U0001f9f9 Clear targets",
        "ult_btn_generate": "\U0001f680 Generate",
        "ult_btn_regenerate": "\U0001f504 Regenerate",
        "ult_btn_cancel": "\u274c Cancel",
        "ult_chat_missing": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Generation archive is not created yet.',
        "ult_chat_targets": "Archive targets: {}",
        "ult_chat_target_topic": "chat <code>{}</code>, topic <code>{}</code>",
        "ult_chat_target_chat": "chat <code>{}</code>",
        "ult_chat_targets_title": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Archive targets',
        "ult_chat_targets_empty": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji> No archive targets.',
        "ult_chat_need_create": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> First create the generation archive.',
        "ult_chat_created": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Generation archive created and linked.',
        "ult_chat_recreated": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Generation archive added.',
        "ult_chat_create_failed": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Failed to create generation archive: {}',
        "ult_chat_access_lost": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Access to the generation archive is lost. Create a new archive.',
        "ult_chat_about": "This is the Comfy ImageGen generation archive. Every generation is saved here without quality loss, together with full generation metadata. Use .cshare as a reply to an archived generation to share it to the public SFW channel @ComfyIdeas.",
        "ult_chat_bind_input": "Enter chat_id, chat_id topic_id, chat_id:topic_id, or a t.me/c link:",
        "ult_chat_bind_bad": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Could not parse chat/topic.',
        "ult_chat_bind_failed": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Could not bind archive: {}',
        "ult_chat_bound": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Archive target linked.',
        "ult_chat_already_bound": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> This archive target is already linked.',
        "ult_chat_target_removed": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Archive target removed.',
        "ult_chat_targets_cleared": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Archive targets cleared.',
        "archive_full_prompt_caption": "Full prompt",
        "archive_full_prompt_title": "Full prompt #{}",
        "cshare_no_reply": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Reply to a generation from the archive.",
        "cshare_no_archive": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Reply to a generation from the archive.",
        "cshare_no_prompt_info": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Full prompt message not found. Reply to a generation from the archive.",
        "cshare_no_image": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Could not download the generation image.",
        "cshare_target_error": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Could not send the submission to @ComfyIdeas: {}",
        "cshare_done": "<emoji document_id=5206607081334906820>\u2705</emoji> Sent to @ComfyIdeas.",
        "cshare_top_unavailable": "<emoji document_id=5121063440311386962>👎</emoji> ComfyIdeas top is unavailable.",
        "cshare_direct_unavailable": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Open https://t.me/comfyideas?direct, send any message there once, then run <code>.cshare</code> again.",
        "cshare_unknown_workflow": "Неизвестно",
        "cshare_author": "Автор: {}",
        "cshare_author_anon": "анонимно",
        "cshare_preview_title": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> ComfyIdeas preview',
        "cshare_preview_expired": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Preview expired. Run <code>.cshare</code> again.",
        "cshare_preview_cancelled": "<emoji document_id=5206607081334906820>\u2705</emoji> ComfyIdeas submission cancelled.",
        "cshare_preview_send_btn": "\u2705 Send",
        "ult_confirm_title": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> Confirm AI prompt',
        "ult_confirm_source": "Original prompt",
        "ult_confirm_result": "Enhanced prompt",
        "ult_confirm_censored": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Provider censorship triggered. Generation will use the original prompt.',
        "ult_confirm_model": "Model: {}",
        "ult_confirm_workflow": "Workflow: {}",
        "ult_toggle_saved": "Setting updated",
        "ult_state_expired": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> This action expired. Start again.',
        "trigger_queue_full": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Generation queue is full. Try again later.",
        "ctools_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Comfy tools",
        "ctools_usage": "Use <code>.ctools -upscale (0.1-8x)</code>, <code>.ctools -rmbg</code>, or <code>.ctools -fps</code> in reply to media.",
        "ctools_btn_upscale": "Upscale",
        "ctools_btn_rmbg": "Remove background",
        "ctools_btn_fps": "FPS boost",
        "ctools_desc_upscale": "<code>-upscale (0.1-8x)</code> - upscale image.",
        "ctools_desc_rmbg": "<code>-rmbg</code> - remove background.",
        "ctools_desc_fps": "<code>-fps</code> - boost video FPS.",
        "ctools_bad_mode": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Unknown tool. Available: <code>-upscale</code>, <code>-rmbg</code>, <code>-fps</code>.",
        "ctools_bad_scale": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Scale must be from 0.1x to 8x. Recommended: 2x.",
        "ctools_no_reply_image": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Reply to an image.",
        "ctools_no_reply_video": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Reply to a video.",
        "ctools_processing_upscale": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Upscaling image...",
        "ctools_processing_rmbg": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Removing background...",
        "ctools_processing_fps": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Boosting video FPS...",
        "ctools_uploading": "<emoji document_id=5873225338984599714>\U0001f4e4</emoji> Uploading tool result...",
        "ctools_done": "<emoji document_id=5206607081334906820>\u2705</emoji> {} done.",
        "ctools_done_rmbg": "<emoji document_id=5206607081334906820>\u2705</emoji> Background removed.",
        "ctools_done_fps": "<emoji document_id=5206607081334906820>\u2705</emoji> FPS boost is ready.",
        "ctools_workflow_no_input": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Tool workflow has no suitable {} input node.",
        "ctools_workflow_no_output": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Tool workflow has no suitable save output node.",
        "ctools_state_expired": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> This tool menu expired. Run <code>.ctools</code> again.",
        "trigger_autodelete_caption": "Auto-delete in: {}",
        "update_available": '<tg-emoji emoji-id="5361979468887893611">\U0001f195</tg-emoji> <b>ComfyImageGen update</b>\n\n<code>{}</code> -> <code>{}</code>{}\n\n<b>Install:</b>\n<code>{}</code>',
        "update_diff": "\n\n<b>What's new:</b>\n<blockquote expandable>{}</blockquote>",
        "not_set": "not set",
    }

    strings_ru = {
        "name": "ComfyImageGen",
        "cfg_url": "Базовый URL ComfyUI (например: http://127.0.0.1:8188)",
        "cfg_model": "Файл модели по умолчанию (например: waiIllustriousSDXL_v170)",
        "cfg_max_mb": "Макс. размер входного изображения в МБ для img2img",
        "cfg_max_output_mb": "Макс. размер результата в МБ",
        "cfg_output_format": "Формат отправки результата: photo (сжатое изображение Telegram), document_png (PNG файлом без потерь)",
        "cfg_ws_update_interval": "Обновление статуса генераций в секундах: 1-5, 0 отключить",
        "cfg_gemini_api_key": "API ключ Gemini для AI улучшения промпта",
        "cfg_groq_api_key": "API ключ Groq для AI улучшения промпта",
        "cfg_openrouter_api_key": "API ключ OpenRouter для AI улучшения промпта",
        "cfg_grok_api_key": "API ключ Grok/xAI для AI улучшения промпта",
        "cfg_deepseek_api_key": "API ключ DeepSeek для AI улучшения промпта",
        "cfg_update_assets": "Фоновое обновление ресурсов модуля в секундах. 0 отключает. Диапазон: 60-14400.",
        "cfg_info_banner_url": "URL баннера для меню ci и chelp. 0 - отключает.",
        "lora_title": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> Выбор LoRA',
        "lora_prompt_label": "Промпт",
        "lora_page": "Стр. {}/{}",
        "lora_detail_title": '<tg-emoji emoji-id="4904936030232117798">\u2699</tg-emoji> {}\nВес: {:.1f}\nСтатус: {}',
        "lora_on": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Включена',
        "lora_off": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji> Выключена',
        "lora_loading": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Загружаю список LoRA из ComfyUI...",
        "lora_load_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось загрузить список LoRA из ComfyUI.",
        "lora_none_available": "LoRA модели не найдены на сервере ComfyUI.",
        "preflight_preparing": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Подготавливаю генерацию...",
        "preflight_workflow": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Загружаю воркфлоу...",
        "preflight_model": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Готовлю модель...",
        "preflight_image": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Готовлю входное изображение...",
        "preflight_launch": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Запускаю генерацию...",
        "fmt_loras": "LoRA:",
        "fmt_loras_more": "и ещё {}",
        "no_url": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> URL ComfyUI не указан. Используйте .cfg ComfyImageGen comfyui_url",
        "no_prompt": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Укажите промпт.",
        "prompt_empty": "Без промпта",
        "status_civitai_inspire": "<emoji document_id=5334544901428229844>\U0001f3b2</emoji> Беру случайный промпт с Civitai...",
        "civitai_no_prompt": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось найти случайный промпт на Civitai.",
        "civitai_error": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось получить промпт с Civitai.",
        "connecting": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Подключение к ComfyUI...",
        "connecting_retry": "ComfyUI не ответил, повторяю подключение... {}/{}",
        "progress": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Генерация... {}%\n<emoji document_id=5879841310902324730>\u270f\ufe0f</emoji> Промпт: {}\n<emoji document_id=5407001145740631266>\U0001f910</emoji> Негатив: {}\n<emoji document_id=5206591666697306436>\U0001f36d</emoji> Модель: {}\n<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Воркфлоу: {}",
        "uploading": "<emoji document_id=5873225338984599714>\U0001f4e4</emoji> Загрузка результата...",
        "success": "<emoji document_id=5206607081334906820>\u2705</emoji> Сгенерировано!\n<emoji document_id=5879841310902324730>\u270f\ufe0f</emoji> Промпт: {}\n<emoji document_id=5407001145740631266>\U0001f910</emoji> Негатив: {}\n<emoji document_id=5206591666697306436>\U0001f36d</emoji> Модель: {}\n<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Воркфлоу: {}",

        "timeout": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Таймаут генерации.",
        "unavailable": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> ComfyUI недоступен.",
        "img_too_large": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Входное изображение слишком большое (макс. {} МБ).",
        "output_too_large": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Результат слишком большой (макс. {} МБ).",
        "no_reply_photo": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ответьте на фото для img2img.",
        "wf_not_found": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Воркфлоу '{}' не найден. Доступные: {}",
        "add_wf_no_reply": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ответьте на JSON-файл для добавления воркфлоу.",
        "add_wf_bad_json": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Невалидный JSON-файл воркфлоу.",
        "wf_file_too_large": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> JSON воркфлоу слишком большой. Максимум: 10 МБ.",
        "add_wf_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Воркфлоу '{}' добавлен.",
        "add_wf_exists": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Воркфлоу '{}' уже существует.",
        "add_wf_no_name": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Укажите имя воркфлоу для добавления.",
        "add_wf_force_btn": "\u2705 Всё равно добавить",
        "add_wf_forced_note": "<emoji document_id=4904936030232117798>\u26a0\ufe0f</emoji> Добавлено несмотря на ошибки проверки.",
        "add_wf_force_expired": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Это действие устарело. Запустите addwf заново.",
        "del_wf_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Воркфлоу '{}' удалён.",
        "del_wf_all_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Все пользовательские воркфлоу удалены: {}.",
        "del_wf_fail": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Воркфлоу '{}' не найден.",
        "del_wf_builtin": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Нельзя удалить встроенный воркфлоу '{}'.",
        "wf_title": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Выбор воркфлоу',
        "wf_builtin_btn": "\U0001f4e6 Встроенные",
        "wf_custom_btn": "\U0001f4dd Пользовательские",
        "wf_list_title_builtin": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Встроенные воркфлоу',
        "wf_list_title_custom": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Пользовательские воркфлоу',
        "wf_desc_anime": "Генерация аниме изображений, принимает все ill, pony, sd модели и похожие.",
        "wf_desc_anime_v2": "Второй аниме воркфлоу, работает на модельках Anima, рекомендую MiaoMiao [https://civitai.red/models/934764/miaomiao-harem?modelVersionId=2967371]",
        "wf_desc_zimage_turbo": "Генерация реалистичных изображений, не поддерживает i2i. Сделан под модель intorealism_zit [https://civitai.red/models/1609320/intorealism?modelVersionId=2912231], но можно попробовать и другие.",
        "wf_desc_sdxl_real1": "Реалистичная модель на SDXL 1.0, сделано под модель mopMixtureOfPerverts_v20 [https://civitai.red/models/1854124?modelVersionId=2159501].",
        "wf_desc_sdxl_real2": "Если вам не особо нравится SDXLReal1, то это второй реалистичный SDXL workflow, тут уже модель xxxRay_dmd2 [https://civitai.red/models/1064836/xxx-ray].",
        "wf_desc_ernie": "Воркфлоу с новейшей моделью Ernie (На средней видюхе генерация в среднем 2-3 минуты), отлично работает с текстами, инфографикой и любыми запросами, главное хороший промпт. Используется модель RedCraft [https://civitai.red/models/958009/redcraft-or].",
        "wf_desc_fluxedit": "Редактирование изображений для средних пк, использует Flux2-Klein",
        "wf_page": "Стр. {}/{}",
        "wf_current": "Текущий: {}",
        "wf_limited_hint": 'Второе нажатие по воркфлоу включает <tg-emoji emoji-id="5271842287326863410">🔵</tg-emoji> ограниченный режим, для изменения становятся доступны только инпуты позитивного, негативного промпта и медиа. Функция в бете, сделано в основном под генерацию видео',
        "wf_limited_set": "Воркфлоу установлен: {} (ограниченный режим)",
        "toast_wf_limited_on": "Ограниченный режим включён: {}",
        "toast_wf_limited_off": "Ограниченный режим выключен: {}",
        "info_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Статус ComfyUI",
        "ci_loading": "Проверяю ComfyUI...",
        "info_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Подключено",
        "info_fail": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Недоступен",
        "info_model": "<emoji document_id=5206591666697306436>\U0001f36d</emoji> Модель: {}",
        "info_wf": "<emoji document_id=5444965220663458467>\U0001f4c1</emoji> Текущий воркфлоу: {}",
        "info_gpu": "<emoji document_id=5839354140261619193>\U0001f6dc</emoji> GPU: {}",
        "info_cpu": "<emoji document_id=5839354140261619193>\U0001f6dc</emoji> CPU: {}",
        "info_device": "<emoji document_id=5839354140261619193>\U0001f6dc</emoji> Устройство: {}",
        "info_no_device": "не обнаружено",
        "info_vram": "<emoji document_id=5373342633798167891>\U0001f4be</emoji> VRAM: {} / {}",
        "info_ram": "<emoji document_id=5373342633798167891>\U0001f4be</emoji> ОЗУ: {} / {}",
        "info_version": "Версия: {}",
        "info_python": "Python: {}",
        "info_pytorch": "PyTorch: {}",
        "info_frontend": "Frontend: {}",
        "info_total_generations": "Генераций всего: {}",
        "info_userbot_ping": "Пинг юзербота: {} ms",
        "ct_checking": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Проверяю API туннеля ComfyUI...",
        "ct_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Проверка туннеля ComfyUI",
        "ct_url": "URL: <code>{}</code>",
        "ct_status": "Статус: {}",
        "ct_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> OK",
        "ct_fail": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ошибка",
        "ct_no_checks": "Проверки не были выполнены.",
        "ct_bad_url": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Некорректный URL.",
        "ct_upload_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Пробная картинка сгенерирована, но Telegram upload не удался: <code>{}</code>",
        "no_images": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Нет изображений в ответе ComfyUI.",

        "no_mapping_pos": "<emoji document_id=5913376703312302899>\U0001f4e3</emoji> Не удалось найти ноду позитивного промпта в воркфлоу.",
        "models_title": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> Выберите модель ComfyUI',
        "models_loading": "Загружаю список моделей...",
        "models_page": "Стр. {}/{}",
        "models_set": "<emoji document_id=5206607081334906820>\u2705</emoji> Модель установлена: {}",
        "models_empty": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Checkpoint и UNET модели не найдены.",
        "models_manual_btn": "\u270f\ufe0f Ввести вручную",
        "models_manual_input": "Введите имя файла модели:",

        "help_text": (
            "<b>Руководство ComfyImageGen</b>\n\n"
            '1. <a href="https://t.me/ComfyUIGuide/3">Установка ComfyUI</a>\n'
            '2. <a href="https://t.me/ComfyUIGuide/7">Как генерировать?</a>\n'
            '3. <a href="https://t.me/ComfyUIGuide/8">Терминология</a>\n'
            '4. <a href="https://t.me/ComfyUIGuide/9">.comfy</a>\n'
            '5. <a href="https://t.me/ComfyUIGuide/10">.cshare</a>\n'
            '6. <a href="https://t.me/ComfyUIGuide/11">.ctools</a>\n'
            '7. <a href="https://t.me/ComfyUIGuide/12">.setarg</a>\n'
            '8. <a href="https://t.me/ComfyUIGuide/13">.ultcomfy</a>\n'
            '9. <a href="https://t.me/ComfyUIGuide/14">Свой вф</a>\n'
            '10. <a href="https://t.me/ComfyUIGuide/15">Ссылочки</a>'
        ),
        "setwf_ok": "Воркфлоу установлен: {}",
        "mlwf_no_name": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Укажите название воркфлоу для выгрузки.",
        "mlwf_not_found": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Воркфлоу '{}' не найден.",
        "mlwf_success": "<emoji document_id=5206607081334906820>\u2705</emoji> Воркфлоу '{}' выгружен.",
        "unexpected_comfy_response": "ComfyUI вернул неожиданный контент. Проверьте логи ComfyUI на ошибки.",
        "inline_uploading": '<tg-emoji emoji-id="5873225338984599714">\U0001f4e4</tg-emoji> Загрузка результата...',
        "cancelled": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Генерация отменена.',
        "cancel_btn": "\u274c Отмена",
        "err_connection": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось подключиться к ComfyUI. Проверьте, что сервер запущен и URL указан верно.",
        "err_node_missing": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Компонент «{}» не установлен в ComfyUI. Установите недостающий кастомный узел.",
        "err_model_not_found": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Модель «{}» не найдена на сервере. Проверьте название или загрузите модель.",
        "err_model_value_not_in_list": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Выбранная модель не существует или не подходит для этого воркфлоу.\n\nМодель: <code>{}</code>\nДоступные модели:\n{}",
        "err_vram": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Недостаточно видеопамяти. Попробуйте уменьшить размер изображения или количество шагов.",
        "err_image_invalid": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось обработать изображение. Файл повреждён или формат не поддерживается.",
        "err_img2img_unsupported": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Этот воркфлоу не поддерживает img2img. Добавьте вход изображения или latent switch ноду.",
        "err_upload_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось загрузить изображение на сервер ComfyUI.",
        "err_retrieve_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось получить результат генерации с сервера.",
        "err_send_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось отправить результат в Telegram. Проверьте права в чате или попробуйте document_png.",
        "err_workflow_invalid": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Воркфлоу повреждён или содержит ошибки.",
        "err_workflow_invalid_details": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ошибка валидации workflow:\n{}",
        "err_vae_not_found": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось определить VAE для img2img. Проверьте воркфлоу.",
        "err_prompt_queue": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> ComfyUI не принял задание на генерацию. Проверьте логи сервера.",
        "err_execution": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ошибка во время генерации в ComfyUI. Проверьте логи сервера.",
        "err_none_input": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Один из компонентов воркфлоу не получил входные данные. Проверьте, что все модели загружены и узлы подключены правильно.",
        "err_generic": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Произошла непредвиденная ошибка. Подробности в логах.",
        "err_workflow_download": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось загрузить встроенный воркфлоу. Проверьте подключение к интернету.",
        "err_server_unavailable": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> ComfyUI временно недоступен (502/503/504). Сервер перегружен или перезапускается. Попробуйте через минуту.",
        "status_enhancing": "<emoji document_id=5325547803936572038>\u2764\ufe0f</emoji> Улучшение промпта с помощью AI...",
        "enhance_no_key": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> API ключ {} не указан. Откройте {}",
        "enhance_dependency_missing": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> google-genai не установлен. Установите зависимости модуля или переустановите модуль.",
        "enhance_key_expired": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> API ключ {} недействителен или исчерпан.",
        "enhance_censored": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} заблокировал промпт (цензура). Попробуйте другой провайдер.",
        "enhance_rate_limit": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> У {} исчерпан лимит запросов. Попробуйте позже.",
        "enhance_timeout": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} не ответил вовремя при улучшении промпта. Попробуйте позже.",
        "enhance_service_error": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> {} вернул непредвиденную ошибку при улучшении промпта. Попробуйте позже.",
        "enhance_vision_unsupported": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Выбранная AI-модель/провайдер ({}) не поддерживает входные изображения. Выберите vision-модель/провайдера или запустите без -ai.",
        "enhance_error": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ошибка {} при улучшении промпта: {}",
        "enhance_cmd_title": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> Улучшенный промпт',
        "enhance_cmd_provider": "Провайдер: {}",
        "enhance_cmd_model": "AI модель: <code>{}</code>",
        "enhance_cmd_original": "Исходный промпт:",
        "enhance_cmd_result": "Улучшенный промпт:",
        "enhanced_label": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> ИИ промпт:',
        "enhance_chat_title": "AI правка промпта [{}/100]",
        "enhance_chat_edit_btn": "\u270f\ufe0f Внести правки",
        "enhance_chat_input": "Что изменить в промпте?",
        "enhance_chat_limit": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Лимит правок достигнут: 100/100.",
        "enhance_chat_empty": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Напишите, что изменить.",
        "argset_title": '<tg-emoji emoji-id="4904936030232117798">\u2699\ufe0f</tg-emoji> Дефолтные аргументы генерации',
        "argset_limited_mode": "🔵 Включён ограниченный режим воркфлоу. Настройки, меняющие workflow, игнорируются.",
        "argset_params": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> Параметры генерации (значения по дефолту берутся из текущего воркфлоу)',
        "argset_enhancements": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> Улучшения',
        "argset_on": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji>',
        "argset_off": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji>',
        "argset_input_width": "Введите ширину (64-4096):",
        "argset_input_height": "Введите высоту (64-4096):",
        "argset_input_steps": "Введите количество шагов (1-100):",
        "argset_input_cfg": "Введите CFG (1.0-30.0):",
        "argset_input_denoise": "Введите denoise (0.0-1.0):",
        "argset_input_sampler_name": "Введите sampler_name:",
        "argset_input_scheduler": "Введите scheduler:",
        "label_sampler_name": "Sampler",
        "label_scheduler": "Scheduler",
        "argset_choice_workflow": "В воркфлоу: {}",
        "argset_choice_used": "Используется: {}",
        "argset_choice_as_workflow": "Как в воркфлоу",
        "argset_choice_custom": "\u270d Ввести своё",
        "argset_choice_clear": "\U0001f5d1 Очистить",
        "argset_choice_saved": "Сохранено: {}",
        "argset_pin_model": "📌 Закрепить для модели",
        "argset_pin_model_ok": "Закреплено для модели: {}",
        "provider_title": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> Провайдер ИИ-улучшения',
        "provider_current": "Текущий: {}",
        "provider_status": "Статус: {}",
        "provider_selected": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Выбран',
        "provider_not_selected": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji> Не выбран',
        "provider_api_key": "API ключ: {}",
        "provider_api_key_set": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> задан',
        "provider_api_key_missing": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji> не задан',
        "provider_model": "Модель: {}",
        "provider_btn_select": "\u2705 Выбрать",
        "provider_btn_api_key": "\U0001f511 API ключ",
        "provider_btn_model": "\U0001f9e0 Модель",
        "provider_btn_menu": "\U0001f916 ИИ-провайдер",
        "enhance_prompt_btn_menu": "\U0001f4dd Промпты для моделей",
        "enhance_prompts_title": '<tg-emoji emoji-id="5879780659840499724">\U0001f4dd</tg-emoji> Промпты для моделей',
        "enhance_prompt_current_url": "URL: {}",
        "enhance_prompt_source": "Источник: {}",
        "enhance_prompt_source_default": "дефолт",
        "enhance_prompt_source_custom": "свой",
        "enhance_prompt_btn_set": "\u270d Вписать ссылку",
        "enhance_prompt_btn_reset": "\U0001f504 Вернуть дефолт",
        "enhance_prompt_btn_download": "\U0001f4c4 Выгрузить",
        "enhance_prompt_input_url": "Введите ссылку на промпт для {}:",
        "enhance_prompt_saved": "Ссылка на промпт сохранена",
        "enhance_prompt_reset": "Ссылка сброшена на дефолт",
        "enhance_prompt_invalid_url": "Некорректная ссылка",
        "enhance_prompt_download_failed": "Не удалось скачать промпт",
        "enhance_prompt_file_caption": "Промпт улучшения для {}",
        "provider_input_api_key": "Введите API ключ для {}:",
        "provider_input_model": "Введите модель:",
        "provider_saved": "Провайдер выбран: {}",
        "provider_key_saved": "API ключ сохранён",
        "provider_model_saved": "Модель сохранена",
        "lora_presets_title": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> Пресеты LoRA',
        "lora_presets_empty": "Нет выбранных пресетов LoRA.",
        "lora_presets_selected": "Выбрано: {}",
        "lora_presets_clear": "\U0001f5d1 Очистить все",
        "lora_presets_saved": "Пресеты LoRA сохранены",
        "lora_weight_btn": "\u270d Вес",
        "lora_weight_input": "Введите вес LoRA (0.1-2.0):",
        "lora_weight_saved": "Вес LoRA сохранён",
        "label_lora_presets": "Пресеты LoRA",
        "positive_menu_title": '<tg-emoji emoji-id="5879841310902324730">\u270f\ufe0f</tg-emoji> Позитивные промпты',
        "positive_global": "Общий позитив",
        "positive_workflows": "Позитивы воркфлоу",
        "positive_current": "Текущий:",
        "positive_custom": "Свой:",
        "positive_global_label": "Общий:",
        "positive_btn_global": "\U0001f310 Общий позитив",
        "positive_btn_set": "\u270d Вписать новый",
        "positive_btn_reset": "\U0001f504 Вернуть к дефолту",
        "positive_btn_clear": "\U0001f5d1 Очистить",
        "positive_input_global": "Введите общий позитивный промпт:",
        "positive_input_workflow": "Введите позитивный промпт для {}:",
        "positive_saved": "Позитив сохранён",
        "positive_reset": "Позитив сброшен",
        "positive_cleared": "Позитив очищен",
        "err_reserved_wf": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Имя 'i2i' зарезервировано встроенным модулем. Попробуйте другое.",
        "del_wf_no_name_with_list": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Укажите имя воркфлоу для удаления.\n\nДоступные пользовательские воркфлоу:\n{}\n\nПример:\n<code>.delwf {}</code>",
        "del_wf_no_custom": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Нет пользовательских воркфлоу для удаления.",
        "repeat_no_last": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Нет сохранённой генерации для повтора.",
        "fmt_generating": "Генерация...",
        "fmt_generating_pct": "Генерация... {}%",
        "fmt_loading_model": "Гружу модель...",
        "fmt_encoding_prompt": "Кодирую промпт...",
        "queue_local_waiting": "Ожидание в очереди генерации...",
        "queue_comfy_submitted": "Задача отправлена в ComfyUI. Жду статус... <i>(возможно, WebSocket недоступен)</i>",
        "queue_comfy_pending": "Ожидание в очереди ComfyUI... Место: {}",
        "queue_comfy_pending_unknown": "Ожидание в очереди ComfyUI...",
        "queue_comfy_other_running": "Сейчас выполняется чужая задача ComfyUI. Ожидание в очереди... Место: {}",
        "queue_comfy_other_running_unknown": "Сейчас выполняется чужая задача ComfyUI. Ожидание в очереди...",
        "queue_comfy_running": "ComfyUI всё еще выполняет задачу...",
        "queue_comfy_running_ws_fallback": "ComfyUI всё еще выполняет задачу... <i>(websocket временно недоступен)</i>",
        "queue_idle_warning": "Нет прогресса от ComfyUI 6 минут. Проверяю очередь...",
        "fmt_generation_eta": "Осталось: {}",
        "cmon_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Мониторинг задач ComfyUI",
        "cmon_starting": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Мониторим...",
        "cmon_loading": "Проверяю задачи ComfyUI...",
        "cmon_no_tasks": "Активных задач нет.",
        "cmon_closed_idle": "Активных задач нет 10 минут. Мониторинг закрыт.",
        "cmon_active": "Активная задача: <code>{}</code>",
        "cmon_active_other": "Активная задача: <code>{}</code> <i>(не наша)</i>",
        "cmon_active_unknown": "Активная задача: обнаружена",
        "cmon_current_node": "Текущий процесс: {}",
        "cmon_progress": "Прогресс: {}%",
        "cmon_last_check": "Обновлено: {}",
        "cmon_unavailable": "Не удалось прочитать очередь ComfyUI.",
        "fmt_decoding_image": "Декодирую изображение...",
        "fmt_processing_image": "Обрабатываю изображение...",
        "fmt_upscaling_image": "Апскейлю изображение...",
        "fmt_detailing_face": "Детализирую лицо...",
        "fmt_saving_result": "Сохраняю результат...",
        "fmt_applying_lora": "Применяю LoRA...",
        "fmt_running_node": "Выполняю: {}",
        "fmt_cached_nodes": "Использую кэшированные ноды: {}",
        "easter_nothing": "Ничего уже существует. Попробуй сгенерировать что-нибудь.",
        "easter_ritual_progress": "Ритуальный прогресс: {}%",
        "easter_dream_unavailable": "<emoji document_id=5121063440311386962>👎</emoji> ComfyUI не отвечает. Возможно, он ушёл смотреть свои сны.",
        "easter_noise_form": "Шум собирается в форму...",
        "easter_long_prompt": "ComfyUI читает этот роман...",
        "easter_long_prompt_rare": "ComfyUI раскладывает детали по полкам...",
        "easter_backrooms": "ComfyUI ищет выход из уровня {}...",
        "easter_short_prompt": "Промпт слишком скромный. Комфи додумает за тебя...",
        "fmt_prompt": "Промпт:",
        "fmt_model": "Модель:",
        "fmt_workflow": "Воркфлоу:",
        "fmt_generation_time": "Время: {}",
        "fmt_done": "Сгенерировано!",
        "btn_params": "\U0001f3a8 Параметры",
        "btn_enhancements": "\U0001f916 Улучшения",
        "btn_reset_all": "\U0001f504 Сбросить всё",
        "btn_close": "\u274c Закрыть",
        "btn_back": "\U0001f519 Назад",
        "btn_generate": "\U0001f680 Генерировать",
        "btn_cancel": "\u274c Отмена",
        "btn_toggle_on": "\u2705 Вкл",
        "btn_toggle_off": "\u274c Выкл",
        "label_ai_enhance": "ИИ-улучшение",
        "toast_model_set": "Модель установлена: {}",
        "toast_wf_set": "Воркфлоу установлен: {}",
        "toast_no_custom_wf": "Нет пользовательских воркфлоу",
        "toast_invalid_value": "Неверное значение: {}",
        "toast_defaults_reset": "Дефолты сброшены до значений воркфлоу",
        "negative_menu_title": '<tg-emoji emoji-id="5407001145740631266">\U0001f910</tg-emoji> Негативные промпты',
        "negative_global": "Общий негатив",
        "negative_workflows": "Негативы воркфлоу",
        "negative_source_custom": "свой",
        "negative_source_global": "общий",
        "negative_source_workflow": "воркфлоу",
        "negative_source_empty": "пусто",
        "negative_current": "Текущий:",
        "negative_custom": "Свой:",
        "negative_global_label": "Общий:",
        "negative_workflow_default": "Дефолт воркфлоу:",
        "negative_source": "Источник: {}",
        "negative_not_set": "не задан",
        "negative_btn_global": "\U0001f310 Общий негатив",
        "negative_btn_set": "\u270d Вписать новый",
        "negative_btn_reset": "\U0001f504 Вернуть к дефолту",
        "negative_btn_clear": "\U0001f5d1 Очистить",
        "negative_input_global": "Введите общий негативный промпт:",
        "negative_input_workflow": "Введите негативный промпт для {}:",
        "negative_saved": "Негатив сохранён",
        "negative_reset": "Негатив сброшен",
        "negative_cleared": "Негатив очищен",
        "free_btn": "\U0001f9f9 Очистить память",
        "force_free_btn": "\U0001f9ef Принудительная очистка",
        "refresh_btn": "\U0001f504 Обновить",
        "free_ok": "Память ComfyUI очищена.",
        "force_free_ok": "Генерация ComfyUI прервана, память очищена.",
        "free_fail": "Не удалось очистить память ComfyUI.",
        "free_busy": "Сейчас идёт генерация, память не очищаю.",
        "checkwf_no_reply": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ответьте на JSON-файл воркфлоу.",
        "checkwf_bad_json": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Невалидный JSON воркфлоу.",
        "checkwf_checking": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Проверяю воркфлоу: {}...",
        "checkwf_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Проверка воркфлоу: {}",
        "checkwf_saved_title": "<emoji document_id=5206607081334906820>\u2705</emoji> Воркфлоу добавлен: {}",
        "wf_validation_ok": "<emoji document_id=5206607081334906820>\u2705</emoji> Воркфлоу прошёл проверку.",
        "wf_validation_failed": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Воркфлоу не прошёл проверку.",
        "wf_validation_found": "\n<b>Найдено:</b>",
        "wf_validation_warnings": "\n<b>Предупреждения:</b>",
        "wf_validation_critical": "\n<b>Критические ошибки:</b>",
        "wf_validation_missing_nodes": "\n<b>Недостающие ноды:</b>",
        "wf_validation_node_pack": "{} — возможный пак: {}",
        "wf_validation_object_info_fail": "Не удалось получить список установленных нод ComfyUI.",
        "wf_validation_missing_optional": "{} не найден.",
        "wf_validation_missing_inputs": "Нода {} ({}) без обязательных входов: {}.",
        "wf_validation_empty": "Воркфлоу пустой или невалидный.",
        "wf_validation_node_invalid": "Воркфлоу содержит невалидные данные ноды.",
        "wf_validation_no_positive": "Нода позитивного промпта не найдена.",
        "wf_validation_no_model": "Нода модели не найдена.",
        "wf_validation_no_output": "Нода результата не найдена.",
        "wf_icon_found": "<emoji document_id=5206607081334906820>\u2705</emoji>",
        "wf_icon_missing": "<emoji document_id=5985346521103604145>\u2b1c</emoji>",
        "wf_icon_error": "<emoji document_id=5121063440311386962>\u274c</emoji>",
        "wf_icon_warning": "<emoji document_id=4904936030232117798>\u26a0\ufe0f</emoji>",
        "wf_check_positive": "Позитивный промпт",
        "wf_check_negative": "Негативный промпт",
        "wf_check_model": "Модель",
        "wf_check_seed": "Сид",
        "wf_check_steps": "Steps",
        "wf_check_cfg": "CFG",
        "wf_check_output": "Результат",
        "wf_check_size": "Размер",
        "wf_check_denoise": "Denoise",
        "wf_check_img2img": "Img2Img input",
        "ult_title": '<tg-emoji emoji-id="4904936030232117798">\u2699\ufe0f</tg-emoji> Дополнительные настройки/функции',
        "ult_ai_title": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> ИИ-улучшение',
        "ult_ai_auto": "Автоулучшение: {}",
        "ult_ai_prompt_confirm": "Подтверждение промпта: {}",
        "ult_ai_provider": "Провайдер: {}",
        "ult_ai_model": "Модель: {}",
        "ult_ai_key": "API ключ: {}",
        "ult_ai_desc": "Флаг -ai всё ещё включает ИИ-улучшение для одной генерации.",
        "ult_ai_key_path": ".ultcomfy -> ИИ-улучшение -> ИИ-провайдер",
        "ult_btn_ai": "\U0001f916 ИИ-улучшение",
        "ult_btn_ai_auto": "\U0001f916 Автоулучшение",
        "ult_btn_prompt_confirm": "\U0001f916 Подтверждение промпта",
        "ult_gens_title": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Архив генераций',
        "ult_gens_desc": "Сохранять каждую успешную генерацию в архив генераций без сжатия (в лучшем качестве).",
        "ult_trigger_title": '<tg-emoji emoji-id="4904936030232117798">\u2699\ufe0f</tg-emoji> Генерация по триггеру',
        "ult_trigger_desc": "Генерировать изображения, когда сообщение начинается с триггер-слова в этом чате.",
        "ult_time_title": '<tg-emoji emoji-id="5870921681735781843">\u23f1</tg-emoji> Время генерации',
        "ult_theme_title": '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji> Тема эмодзи',
        "ult_theme_status": "Тема эмодзи: {}",
        "ult_censorship_status": "Цензура: {}",
        "ult_btn_censorship_on": "\U0001f910 Цензура Включена",
        "ult_btn_censorship_off": "\U0001f910 Цензура Выключена",
        "ult_time_progress": "Время генерации в процессе: {}",
        "ult_time_result": "Время генерации в результате: {}",
        "ult_trigger_chat": "Чат: <code>{}</code>",
        "ult_trigger_word": "Триггер: <code>{}</code>",
        "ult_trigger_autodelete": "Автоудаление результата: {}",
        "ult_trigger_delay": "Автоудаление через: {}",
        "ult_trigger_queue": "Макс. очередь: {}",
        "ult_trigger_steps_limit": "Макс. steps: {}",
        "ult_trigger_active": "Активно сейчас: {}",
        "ult_trigger_russian_guard": "Запрет русского промпта без -ai: {}",
        "ult_trigger_blacklist": "Блэклист: <code>{}</code>",
        "ult_trigger_word_input": "Введите триггер-слово:",
        "ult_trigger_delay_input": "Введите время автоудаления в секундах:",
        "ult_trigger_queue_input": "Введите максимум очереди:",
        "ult_trigger_steps_input": "Введите максимум steps для триггера (1-100):",
        "ult_trigger_saved": "Настройки триггера обновлены",
        "ult_trigger_reject_russian": "Блокировать русский промпт",
        "ult_trigger_blacklist_empty": "Блэклист триггеров пуст.",
        "ult_trigger_blacklist_title": "<b>Блэклист триггеров</b>",
        "ult_trigger_blacklist_added": "Пользователь добавлен в блэклист триггеров.",
        "ult_trigger_blacklist_removed": "Пользователь удалён из блэклиста триггеров.",
        "ult_trigger_blacklist_no_user": "Ответьте на пользователя или укажите @username/id.",
        "ult_btn_trigger_blacklist": "🚫 Блэклист",
        "trigger_russian_requires_ai": "<emoji document_id=5121063440311386962>👎</emoji> Для генерации по триггеру русский промпт разрешён только с -ai.",
        "ult_status_on": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Включено',
        "ult_status_off": '<tg-emoji emoji-id="5121063440311386962">\u274c</tg-emoji> Выключено',
        "ult_btn_prompt": "\U0001f916 Подтверждение промпта",
        "ult_btn_gens": "\U0001f4c1 Архив генераций",
        "ult_btn_trigger": "\u26a1 Генерация по триггеру",
        "ult_btn_time": "\u23f1 Время генерации",
        "ult_btn_theme": "Тема",
        "ult_btn_theme_default": "Дефолт",
        "ult_btn_theme_colored": "Цветная",
        "ult_btn_theme_cute": "Милая",
        "ult_btn_theme_black": "Чёрная",
        "ult_btn_theme_trollface": "Trollface",
        "ult_btn_time_progress": "\u23f1 В процессе",
        "ult_btn_time_result": "\u23f1 В результате",
        "ult_btn_trigger_word": "\u270d Триггер-слово",
        "ult_btn_trigger_delay": "\u23f1 Время удаления",
        "ult_btn_trigger_queue": "\U0001f4e6 Очередь",
        "ult_btn_trigger_steps": "\U0001f3a8 Лимит steps",
        "ult_btn_create_chat": "\U0001f3d7 Создать архив",
        "ult_btn_recreate_chat": "\U0001f504 Добавить архив",
        "ult_btn_bind_chat": "\U0001f517 Привязать архив",
        "ult_btn_remove_chat": "\U0001f5d1 Удалить цель",
        "ult_btn_clear_chats": "\U0001f9f9 Очистить цели",
        "ult_btn_generate": "\U0001f680 Генерировать",
        "ult_btn_regenerate": "\U0001f504 Перегенерировать",
        "ult_btn_cancel": "\u274c Отменить",
        "ult_chat_missing": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Архив генераций ещё не создан.',
        "ult_chat_targets": "Цели архива: {}",
        "ult_chat_target_topic": "чат <code>{}</code>, топик <code>{}</code>",
        "ult_chat_target_chat": "чат <code>{}</code>",
        "ult_chat_targets_title": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Цели архива',
        "ult_chat_targets_empty": '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji> Целей архива нет.',
        "ult_chat_need_create": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Сначала создайте архив генераций.',
        "ult_chat_created": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Архив генераций создан и привязан.',
        "ult_chat_recreated": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Архив генераций добавлен.',
        "ult_chat_create_failed": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Не удалось создать архив генераций: {}',
        "ult_chat_access_lost": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Доступ к архиву генераций потерян. Создайте новый архив.',
        "ult_chat_about": "Это архив генераций модуля Comfy ImageGen. Тут сохраняется каждая ваша генерация без потери качества и полная мета-информация о генерации. Используя команду .cshare ответом на генерацию, можно поделиться вашей генерацией в публичный SFW-канал @ComfyIdeas.",
        "ult_chat_bind_input": "Введите chat_id, chat_id topic_id, chat_id:topic_id или ссылку t.me/c:",
        "ult_chat_bind_bad": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Не удалось распознать чат/топик.',
        "ult_chat_bind_failed": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Не удалось привязать архив: {}',
        "ult_chat_bound": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Архив привязан.',
        "ult_chat_already_bound": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Эта цель архива уже привязана.',
        "ult_chat_target_removed": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Цель архива удалена.',
        "ult_chat_targets_cleared": '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji> Цели архива очищены.',
        "archive_full_prompt_caption": "Полный промпт",
        "archive_full_prompt_title": "Полный промпт #{}",
        "cshare_no_reply": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ответьте на генерацию из архива.",
        "cshare_no_archive": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ответьте на генерацию из архива.",
        "cshare_no_prompt_info": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не найдено сообщение с полным промптом. Ответьте на генерацию из архива.",
        "cshare_no_image": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось скачать изображение генерации.",
        "cshare_target_error": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Не удалось отправить предложку в @ComfyIdeas: {}",
        "cshare_done": "<emoji document_id=5206607081334906820>\u2705</emoji> Отправлено в @ComfyIdeas.",
        "cshare_top_unavailable": "<emoji document_id=5121063440311386962>👎</emoji> Топ ComfyIdeas недоступен.",
        "cshare_direct_unavailable": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Откройте https://t.me/comfyideas?direct, отправьте туда любое сообщение один раз, затем повторите <code>.cshare</code>.",
        "cshare_unknown_workflow": "Неизвестно",
        "cshare_author": "Автор: {}",
        "cshare_author_anon": "анонимно",
        "cshare_preview_title": '<tg-emoji emoji-id="5444965220663458467">\U0001f4c1</tg-emoji> Предпросмотр ComfyIdeas',
        "cshare_preview_expired": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Предпросмотр устарел. Запустите <code>.cshare</code> заново.",
        "cshare_preview_cancelled": "<emoji document_id=5206607081334906820>\u2705</emoji> Отправка в ComfyIdeas отменена.",
        "cshare_preview_send_btn": "\u2705 Отправить",
        "ult_confirm_title": '<tg-emoji emoji-id="5188678912883827293">\U0001f916</tg-emoji> Подтверждение AI-промпта',
        "ult_confirm_source": "Исходный промпт",
        "ult_confirm_result": "Улучшенный промпт",
        "ult_confirm_censored": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Сработала цензура провайдера. Генерация пойдёт с исходным промптом.',
        "ult_confirm_model": "Модель: {}",
        "ult_confirm_workflow": "Воркфлоу: {}",
        "ult_toggle_saved": "Настройка обновлена",
        "ult_state_expired": '<tg-emoji emoji-id="5121063440311386962">\U0001f44e</tg-emoji> Это действие устарело. Запустите заново.',
        "trigger_queue_full": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Очередь генерации заполнена. Попробуйте позже.",
        "ctools_title": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Comfy tools",
        "ctools_usage": "Используйте <code>.ctools -upscale (0.1-8x)</code>, <code>.ctools -rmbg</code> или <code>.ctools -fps</code> в ответ на медиа.",
        "ctools_btn_upscale": "Апскейл",
        "ctools_btn_rmbg": "Убрать фон",
        "ctools_btn_fps": "Повысить FPS",
        "ctools_desc_upscale": "<code>-upscale (0.1-8x)</code> - апскейл изображения.",
        "ctools_desc_rmbg": "<code>-rmbg</code> - убрать фон.",
        "ctools_desc_fps": "<code>-fps</code> - повысить FPS видео.",
        "ctools_bad_mode": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Неизвестный инструмент. Доступно: <code>-upscale</code>, <code>-rmbg</code>, <code>-fps</code>.",
        "ctools_bad_scale": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Размер должен быть от 0.1x до 8x. Рекомендуется: 2x.",
        "ctools_no_reply_image": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ответьте на изображение.",
        "ctools_no_reply_video": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Ответьте на видео.",
        "ctools_processing_upscale": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Апскейлю изображение...",
        "ctools_processing_rmbg": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Убираю фон...",
        "ctools_processing_fps": "<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji> Повышаю FPS видео...",
        "ctools_uploading": "<emoji document_id=5873225338984599714>\U0001f4e4</emoji> Загружаю результат инструмента...",
        "ctools_done": "<emoji document_id=5206607081334906820>\u2705</emoji> {} готов.",
        "ctools_done_rmbg": "<emoji document_id=5206607081334906820>\u2705</emoji> фон убран.",
        "ctools_done_fps": "<emoji document_id=5206607081334906820>\u2705</emoji> повышение fps готово.",
        "ctools_workflow_no_input": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> В tool workflow нет подходящего {} input node.",
        "ctools_workflow_no_output": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> В tool workflow нет подходящей save output node.",
        "ctools_state_expired": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Это меню инструментов устарело. Запустите <code>.ctools</code> снова.",
        "trigger_autodelete_caption": "Автоудаление через: {}",
        "update_available": '<tg-emoji emoji-id="5361979468887893611">\U0001f195</tg-emoji> <b>Обновление ComfyImageGen</b>\n\n<code>{}</code> -> <code>{}</code>{}\n\n<b>Установка:</b>\n<code>{}</code>',
        "update_diff": "\n\n<b>Что изменилось:</b>\n<blockquote expandable>{}</blockquote>",
        "not_set": "не задано",
        "trigger_too_often": "<emoji document_id=5121063440311386962>\U0001f44e</emoji> Слишком часто.",
        "wf_check_output_kind": "Output kind: {}",
        "wf_check_input_kind": "Input kind: {}",
        "wf_check_frames": "Frames",
        "wf_check_fps": "FPS",
    }
    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "comfyui_url",
                "http://127.0.0.1:8188",
                lambda: self.strings("cfg_url"),
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "model_name",
                "waiIllustriousSDXL_v170.safetensors",
                lambda: self.strings("cfg_model"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "max_input_mb",
                10,
                lambda: self.strings("cfg_max_mb"),
                validator=loader.validators.Integer(minimum=1, maximum=50),
            ),
            loader.ConfigValue(
                "max_output_mb",
                300,
                lambda: self.strings("cfg_max_output_mb"),
                validator=loader.validators.Integer(minimum=1, maximum=2000),
            ),
            loader.ConfigValue(
                "output_format",
                "photo",
                lambda: self.strings("cfg_output_format"),
                validator=loader.validators.Choice(["photo", "document_png"]),
            ),
            loader.ConfigValue(
                "ws_update_interval",
                2,
                lambda: self.strings("cfg_ws_update_interval"),
                validator=loader.validators.Integer(minimum=0, maximum=5),
            ),
            loader.ConfigValue(
                "gemini_api_key",
                "",
                lambda: self.strings("cfg_gemini_api_key"),
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "groq_api_key",
                "",
                lambda: self.strings("cfg_groq_api_key"),
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "openrouter_api_key",
                "",
                lambda: self.strings("cfg_openrouter_api_key"),
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "grok_api_key",
                "",
                lambda: self.strings("cfg_grok_api_key"),
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "deepseek_api_key",
                "",
                lambda: self.strings("cfg_deepseek_api_key"),
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "update_assets",
                0,
                lambda: self.strings("cfg_update_assets"),
                validator=loader.validators.Integer(minimum=0, maximum=14400),
            ),
            loader.ConfigValue(
                "info_banner_url",
                _DEFAULT_INFO_BANNER_URL,
                lambda: self.strings("cfg_info_banner_url"),
                validator=loader.validators.String(),
            ),
        )
        self._session = None
        self._semaphore = asyncio.Semaphore(1)
        self._enhance_system_prompt = None
        self._enhance_system_prompts = {}
        self._impact_wildcard_select_text = None
        self._BUILTIN_WORKFLOWS = (
            _ERNIE_WORKFLOW_NAME,
            _FLUX_EDIT_WORKFLOW_NAME,
            _SDXL_REAL1_WORKFLOW_NAME,
            _SDXL_REAL2_WORKFLOW_NAME,
            _ANIME_WORKFLOW_NAME,
            _ANIME_V2_WORKFLOW_NAME,
            _Z_IMAGE_TURBO_WORKFLOW_NAME,
        )
        self._available_sam_models = None
        self._lora_states = TTLCache(maxsize=50, ttl=600)
        self._models_page_cache = TTLCache(maxsize=50, ttl=300)
        self._wf_page_cache = TTLCache(maxsize=50, ttl=300)
        self._addwf_force_states = TTLCache(maxsize=20, ttl=1800)
        self._cancel_flags = TTLCache(maxsize=100, ttl=600)
        self._generation_runtime = TTLCache(maxsize=100, ttl=7200)
        self._comfy_cache = TTLCache(maxsize=256, ttl=300)
        self._enhance_confirm_states = TTLCache(maxsize=50, ttl=1800)
        self._enhance_chat_states = TTLCache(maxsize=50, ttl=1800)
        self._argset_lora_states = TTLCache(maxsize=20, ttl=1800)
        self._cshare_preview_states = TTLCache(maxsize=30, ttl=900)
        self._ctools_states = TTLCache(maxsize=30, ttl=600)
        self._cmon_tasks = {}
        self._trigger_queue_counts = {}
        self._trigger_queue_lock = asyncio.Lock()
        self._trigger_queue_cooldowns = TTLCache(maxsize=1000, ttl=180)
        self._trigger_generation_cooldowns = TTLCache(maxsize=1000, ttl=10)
        self._trigger_rate_limit_cooldowns = TTLCache(maxsize=1000, ttl=10)
        self._trigger_unavailable_cooldowns = TTLCache(maxsize=1000, ttl=180)
        self._genai_client = None
        self._genai_api_key = None
        self._active_generations = 0
        self._unloading = False
        self._last_builtin_wf_retry = {}
        self._builtin_wf_retry_interval = 60
        self._builtin_wf_load_failed = False
        self._builtin_wf_lock = asyncio.Lock()
        self._update_check_task = None
        self._startup_update_check_task = None
        self._assets_update_task = None
        self._input_cleanup_task = None
        self._update_notice_lock = asyncio.Lock()
        self._auto_delete_tasks = set()
        self._input_temp_paths = set()
        self._self_has_premium = False

    def _ensure_session(self):
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120)
            )
        return self._session

    def _input_tmp_dir(self):
        path = os.path.join(tempfile.gettempdir(), "heroku_comfyimagegen_inputs")
        os.makedirs(path, exist_ok=True)
        return path

    def _is_own_input_temp_path(self, path):
        if not path:
            return False
        try:
            base = os.path.abspath(self._input_tmp_dir())
            target = os.path.abspath(path)
            return os.path.commonpath([base, target]) == base
        except Exception:
            return False

    def _cleanup_input_file(self, state_or_path):
        if isinstance(state_or_path, dict):
            paths = [
                state_or_path.get("input_image_path"),
                state_or_path.get("input_video_path"),
            ]
            for path in paths:
                self._cleanup_input_file(path)
            state_or_path["input_image_path"] = None
            state_or_path["input_video_path"] = None
            return
        path = state_or_path
        if not self._is_own_input_temp_path(path):
            return
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.debug("Failed to remove temporary input image: %s", e)
        finally:
            self._input_temp_paths.discard(path)

    def _cleanup_stale_input_files(self, max_age=3600):
        try:
            base = self._input_tmp_dir()
            now = time.time()
            for name in os.listdir(base):
                path = os.path.join(base, name)
                if not os.path.isfile(path):
                    continue
                if now - os.path.getmtime(path) >= max_age:
                    self._cleanup_input_file(path)
        except Exception as e:
            logger.debug("Failed to cleanup stale input images: %s", e)

    def _cleanup_all_input_files(self):
        for cache in (self._enhance_confirm_states, self._lora_states):
            for state in list(cache.values()):
                self._cleanup_input_file(state)
        for path in list(self._input_temp_paths):
            self._cleanup_input_file(path)
        try:
            base = self._input_tmp_dir()
            for name in os.listdir(base):
                self._cleanup_input_file(os.path.join(base, name))
        except Exception as e:
            logger.debug("Failed to cleanup input image directory: %s", e)

    async def _input_cleanup_loop(self):
        while not self._unloading:
            await asyncio.sleep(900)
            self._cleanup_stale_input_files()

    async def _download_input_image_to_temp(self, reply):
        return await self._download_input_media_to_temp(
            reply,
            prefix="input",
            default_suffix=".jpg",
        )

    def _media_suffix_from_reply(self, reply, default=".bin"):
        name = getattr(getattr(reply, "file", None), "name", None)
        if name and "." in name:
            suffix = "." + name.rsplit(".", 1)[-1].lower()
            if len(suffix) <= 12:
                return suffix
        mime = getattr(getattr(reply, "file", None), "mime_type", None)
        suffix = mimetypes.guess_extension(str(mime or "").split(";", 1)[0].strip())
        return suffix or default

    async def _download_input_media_to_temp(self, reply, prefix="input", default_suffix=".bin"):
        max_mb = self.config["max_input_mb"]
        if reply.file and reply.file.size > max_mb * 1024 * 1024:
            raise UserFacingError("input_too_large", max_mb=max_mb)
        self._cleanup_stale_input_files()
        suffix = self._media_suffix_from_reply(reply, default_suffix)
        input_name = f"{prefix}_{uuid.uuid4().hex}{suffix}"
        path = os.path.join(self._input_tmp_dir(), input_name)
        try:
            downloaded = await self.client.download_media(reply, path)
            path = downloaded or path
            self._input_temp_paths.add(path)
            if os.path.getsize(path) > max_mb * 1024 * 1024:
                self._cleanup_input_file(path)
                raise UserFacingError("input_too_large", max_mb=max_mb)
            return path, os.path.basename(path)
        except Exception:
            self._cleanup_input_file(path)
            raise

    async def _upload_input_path_to_comfyui(self, path, filename, attempts=3, delay=2, content_type=None):
        last_err = None
        for i in range(attempts):
            try:
                with open(path, "rb") as img_bio:
                    return await self._upload_to_comfyui(img_bio, filename, content_type=content_type)
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ComfyUIHTTPError) as e:
                last_err = e
                temporary = getattr(e, "temporary", False) or isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError, OSError))
                if not temporary:
                    raise
                if i < attempts - 1:
                    await asyncio.sleep(delay)
        raise last_err or ValueError("upload failed")

    async def _upload_state_input_image(self, state):
        input_filename = state.get("input_filename")
        if input_filename:
            return input_filename
        path = state.get("input_image_path")
        if not path:
            return None
        if not os.path.exists(path):
            raise UserFacingError("upload_failed", self._plain_text(self.strings("err_upload_failed")))
        filename = state.get("input_image_name") or f"input_{uuid.uuid4().hex}.png"
        try:
            input_filename = await self._upload_input_path_to_comfyui(path, filename)
            state["input_filename"] = input_filename
            return input_filename
        finally:
            self._cleanup_input_file(state)

    async def _upload_state_input_video(self, state):
        input_filename = state.get("input_video_filename")
        if input_filename:
            return input_filename
        path = state.get("input_video_path")
        if not path:
            return None
        if not os.path.exists(path):
            raise UserFacingError("upload_failed", self._plain_text(self.strings("err_upload_failed")))
        filename = state.get("input_video_name") or f"input_{uuid.uuid4().hex}.mp4"
        try:
            input_filename = await self._upload_input_path_to_comfyui(
                path,
                filename,
                content_type=mimetypes.guess_type(filename)[0],
            )
            state["input_video_filename"] = input_filename
            return input_filename
        finally:
            self._cleanup_input_file(state)

    def _track_auto_delete(self, message_to_delete, delay):
        if self._unloading:
            return None
        task = asyncio.create_task(self._schedule_delete_message(message_to_delete, delay))
        self._auto_delete_tasks.add(task)
        task.add_done_callback(self._auto_delete_tasks.discard)
        return task

    def _session_get(self, *args, **kwargs):
        return self._ensure_session().get(*args, **kwargs)

    def _session_post(self, *args, **kwargs):
        return self._ensure_session().post(*args, **kwargs)

    def _session_ws_connect(self, *args, **kwargs):
        return self._ensure_session().ws_connect(*args, **kwargs)

    def _builtin_workflow_cache_key(self, wf_name):
        return "builtin_anime_wf" if wf_name == _ANIME_WORKFLOW_NAME else f"builtin_wf_{wf_name}"

    def _builtin_workflow_version_key(self, wf_name):
        return "builtin_anime_wf_version" if wf_name == _ANIME_WORKFLOW_NAME else f"builtin_wf_version_{wf_name}"

    def _builtin_workflow_source_key(self, wf_name):
        return "builtin_anime_wf_source" if wf_name == _ANIME_WORKFLOW_NAME else f"builtin_wf_source_{wf_name}"

    @staticmethod
    def _parse_telegram_message_url(url):
        parsed = urlparse(str(url or ""))
        path_parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc not in ("t.me", "telegram.me") or len(path_parts) < 2:
            raise ValueError("Invalid Telegram message URL")
        if path_parts[0] == "c" and len(path_parts) >= 3:
            chat = int(f"-100{path_parts[1]}")
            msg_id = int(path_parts[2])
            return chat, msg_id
        return path_parts[0], int(path_parts[1])

    def _normalize_builtin_workflow_payload(self, wf):
        workflow = self._normalize_workflow_format(wf)
        if not isinstance(workflow, dict) or not workflow:
            raise ValueError("Invalid workflow JSON")
        return workflow

    async def _fetch_builtin_workflow_from_github(self, wf_name, url):
        async with self._session_get(
            url,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Cache-Control": "no-cache"},
            params={"t": int(time.time())},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {text[:200]}")
            return self._normalize_builtin_workflow_payload(await resp.json(content_type=None))

    async def _fetch_builtin_workflow_from_telegram(self, wf_name, url):
        chat, msg_id = self._parse_telegram_message_url(url)
        message = await self.client.get_messages(chat, ids=msg_id)
        if not message:
            raise RuntimeError("Telegram message not found")
        raw = None
        if getattr(message, "media", None):
            raw = await message.download_media(bytes)
        if not raw:
            text = getattr(message, "raw_text", None) or getattr(message, "text", None)
            raw = text.encode("utf-8") if isinstance(text, str) else None
        if not raw:
            raise RuntimeError("Telegram message has no workflow file")
        if len(raw) > 10 * 1024 * 1024:
            raise RuntimeError("Telegram workflow file is too large")
        try:
            wf = json.loads(raw.decode("utf-8-sig"))
        except UnicodeDecodeError:
            wf = json.loads(raw.decode("utf-8", errors="ignore"))
        return self._normalize_builtin_workflow_payload(wf)

    def _save_builtin_workflow(self, wf_name, workflow, source):
        cache_key = self._builtin_workflow_cache_key(wf_name)
        version_key = self._builtin_workflow_version_key(wf_name)
        source_key = self._builtin_workflow_source_key(wf_name)
        self.set(cache_key, workflow)
        self.set(version_key, __version__)
        self.set(source_key, source)

    async def _fetch_builtin_workflow(self, wf_name=_ANIME_WORKFLOW_NAME, force=False):
        wf_name = self._canonical_workflow_name(wf_name)
        cache_key = self._builtin_workflow_cache_key(wf_name)
        version_key = self._builtin_workflow_version_key(wf_name)
        cached_version = self.get(version_key)
        if not force and cached_version == __version__ and self.get(cache_key):
            return

        url = _BUILTIN_WORKFLOW_URLS.get(wf_name)
        if not url:
            raise RuntimeError(self._plain_text(self.strings("err_workflow_download")))

        github_error = None
        try:
            wf = await self._fetch_builtin_workflow_from_github(wf_name, url)
            self._save_builtin_workflow(wf_name, wf, "github")
            logger.debug("Loaded builtin workflow %s from GitHub", wf_name)
            return
        except Exception as e:
            github_error = e
            logger.warning("Failed to fetch builtin workflow %s from GitHub: %s", wf_name, e)

        telegram_url = _BUILTIN_WORKFLOW_TELEGRAM_URLS.get(wf_name)
        telegram_error = None
        if telegram_url:
            try:
                wf = await self._fetch_builtin_workflow_from_telegram(wf_name, telegram_url)
                self._save_builtin_workflow(wf_name, wf, "telegram")
                logger.info("Loaded builtin workflow %s from Telegram fallback", wf_name)
                return
            except Exception as e:
                telegram_error = e
                logger.warning("Failed to fetch builtin workflow %s from Telegram: %s", wf_name, e)

        if not self.get(cache_key):
            if telegram_error:
                logger.error(
                    "Builtin workflow %s unavailable; GitHub failed: %s; Telegram failed: %s",
                    wf_name,
                    github_error,
                    telegram_error,
                )
            else:
                logger.error("Builtin workflow %s unavailable; GitHub failed: %s", wf_name, github_error)
            raise RuntimeError(self._plain_text(self.strings("err_workflow_download")))
        self.set(self._builtin_workflow_source_key(wf_name), "cache")
        logger.warning("Using cached builtin workflow %s after remote fetch failure", wf_name)

    def _ctool_definitions(self):
        return {
            _CTOOL_UPSCALE: {
                "label": self.strings("ctools_btn_upscale"),
                "processing_key": "ctools_processing_upscale",
                "input_kind": "image",
                "output_kind": "image",
                "url": _UPSCALE_WF_URL,
                "telegram_url": _UPSCALE_WORKFLOW_TELEGRAM_URL,
            },
            _CTOOL_RMBG: {
                "label": self.strings("ctools_btn_rmbg"),
                "processing_key": "ctools_processing_rmbg",
                "done_key": "ctools_done_rmbg",
                "input_kind": "image",
                "output_kind": "image",
                "url": _BGRM_WF_URL,
                "telegram_url": _BGRM_WORKFLOW_TELEGRAM_URL,
            },
            _CTOOL_FPS: {
                "label": self.strings("ctools_btn_fps"),
                "processing_key": "ctools_processing_fps",
                "done_key": "ctools_done_fps",
                "input_kind": "video",
                "output_kind": "video",
                "url": _FRAMES_WF_URL,
                "telegram_url": _FRAMES_WORKFLOW_TELEGRAM_URL,
            },
        }

    def _canonical_ctool_id(self, raw):
        value = str(raw or "").strip().lower().lstrip("-")
        aliases = {
            "cupscale": _CTOOL_UPSCALE,
            "upscale": _CTOOL_UPSCALE,
            "scale": _CTOOL_UPSCALE,
            "rmbg": _CTOOL_RMBG,
            "bgremove": _CTOOL_RMBG,
            "removebg": _CTOOL_RMBG,
            "remove-background": _CTOOL_RMBG,
            "fps": _CTOOL_FPS,
            "frames": _CTOOL_FPS,
            "v2v": _CTOOL_FPS,
        }
        return aliases.get(value)

    async def _fetch_ctool_workflow(self, tool_id, force=False):
        tool = self._ctool_definitions().get(tool_id)
        if not tool:
            raise ValueError("unknown ctool")
        cache_key = f"ctool_wf_{tool_id}"
        version_key = f"ctool_wf_version_{tool_id}"
        cached = self.get(cache_key)
        if not force and self.get(version_key) == __version__ and cached:
            return self._normalize_builtin_workflow_payload(cached)

        github_error = None
        try:
            workflow = await self._fetch_builtin_workflow_from_github(tool_id, tool["url"])
            self.set(cache_key, workflow)
            self.set(version_key, __version__)
            return workflow
        except Exception as e:
            github_error = e
            logger.warning("Failed to fetch ctool workflow %s from GitHub: %s", tool_id, e)

        try:
            workflow = await self._fetch_builtin_workflow_from_telegram(tool_id, tool["telegram_url"])
            self.set(cache_key, workflow)
            self.set(version_key, __version__)
            return workflow
        except Exception as e:
            logger.warning("Failed to fetch ctool workflow %s from Telegram: %s", tool_id, e)
            if cached:
                return self._normalize_builtin_workflow_payload(cached)
            raise RuntimeError(f"{github_error}; telegram fallback: {e}") from e

    def _normalize_enhance_prompt_url(self, url):
        url = str(url or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ""
        return url

    def _get_enhance_prompt_urls(self):
        urls = self.get("enhance_prompt_urls", {})
        if not isinstance(urls, dict):
            urls = {}
        normalized = {}
        for provider, url in urls.items():
            provider = str(provider or "").strip().lower()
            if provider in self._provider_ids():
                url = self._normalize_enhance_prompt_url(url)
                if url:
                    normalized[provider] = url
        if normalized != urls:
            self.set("enhance_prompt_urls", normalized)
        return normalized

    def _get_enhance_prompt_url(self, provider):
        provider = str(provider or "").strip().lower()
        return self._get_enhance_prompt_urls().get(provider) or _ENHANCE_PROMPT_URL

    def _set_enhance_prompt_url(self, provider, url):
        provider = str(provider or "").strip().lower()
        url = self._normalize_enhance_prompt_url(url)
        if provider not in self._provider_ids() or not url:
            return False
        urls = self._get_enhance_prompt_urls()
        urls[provider] = url
        self.set("enhance_prompt_urls", urls)
        self._enhance_system_prompts.pop(provider, None)
        return True

    def _reset_enhance_prompt_url(self, provider):
        provider = str(provider or "").strip().lower()
        urls = self._get_enhance_prompt_urls()
        urls.pop(provider, None)
        self.set("enhance_prompt_urls", urls)
        self._enhance_system_prompts.pop(provider, None)

    def _get_enhance_prompt_cache(self):
        cache = self.get("enhance_system_prompt_cache", {})
        return cache if isinstance(cache, dict) else {}

    async def _fetch_enhance_prompt(self, provider=None, force=False):
        provider = str(provider or self._get_prompt_provider() or "gemini").strip().lower()
        if provider not in self._provider_ids():
            provider = "gemini"
        url = self._get_enhance_prompt_url(provider)
        cache = self._get_enhance_prompt_cache()
        cached = cache.get(provider, {})
        if not isinstance(cached, dict):
            cached = {}
        cached_text = cached.get("text")
        if not force and cached.get("version") == __version__ and cached.get("url") == url and cached_text:
            self._enhance_system_prompts[provider] = cached_text
            if provider == self._get_prompt_provider():
                self._enhance_system_prompt = cached_text
            return cached_text

        try:
            async with self._session_get(
                url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Cache-Control": "no-cache"},
                params={"t": int(time.time())},
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"HTTP {resp.status}: {body[:200]}")
                text = await resp.text()
                if text and len(text) > 100:
                    self._enhance_system_prompts[provider] = text
                    if provider == self._get_prompt_provider():
                        self._enhance_system_prompt = text
                    cache[provider] = {"text": text, "url": url, "version": __version__}
                    self.set("enhance_system_prompt_cache", cache)
                    if url == _ENHANCE_PROMPT_URL:
                        self.set("enhance_system_prompt", text)
                        self.set("enhance_prompt_version", __version__)
                    return text
                raise ValueError("Invalid enhance system prompt")
        except Exception as e:
            logger.warning("Failed to fetch enhance system prompt for %s from %s: %s", provider, url, e)

        if cached_text:
            self._enhance_system_prompts[provider] = cached_text
            if provider == self._get_prompt_provider():
                self._enhance_system_prompt = cached_text
            logger.warning("Using cached enhance system prompt after remote fetch failure")
            return cached_text

        legacy_text = self.get("enhance_system_prompt")
        if url == _ENHANCE_PROMPT_URL and legacy_text:
            self._enhance_system_prompts[provider] = legacy_text
            if provider == self._get_prompt_provider():
                self._enhance_system_prompt = legacy_text
            logger.warning("Using legacy cached enhance system prompt after remote fetch failure")
            return legacy_text

        logger.warning("Enhance system prompt not available for %s, AI prompt enhancement will be disabled", provider)
        return None

    def _format_module_version(self, version_tuple):
        return ".".join(map(str, version_tuple))

    def _is_remote_version_newer(self, remote_version):
        return tuple(remote_version) > tuple(__version__)

    def _update_notice_key(self, installed_version_text, remote_version_text):
        return f"{installed_version_text}->{remote_version_text}"

    def _get_update_notice_counts(self):
        counts = self.get("update_notice_counts", {})
        return counts if isinstance(counts, dict) else {}

    def _get_update_notice_count(self, notice_key, remote_version_text):
        counts = self._get_update_notice_counts()
        count = self._coerce_int(
            counts.get(notice_key),
            0,
            0,
            _UPDATE_NOTICE_LIMIT,
        )
        if count == 0 and self.get("last_update_notice_version") == remote_version_text:
            count = 1
        return count

    def _mark_update_notice_sent(self, notice_key, remote_version_text):
        counts = self._get_update_notice_counts()
        current = self._get_update_notice_count(notice_key, remote_version_text)
        counts[notice_key] = min(_UPDATE_NOTICE_LIMIT, current + 1)
        self.set("update_notice_counts", counts)
        self.set("last_update_notice_version", remote_version_text)

    def _parse_remote_module_version(self, text):
        match = re.search(r"__version__\s*=\s*(\([^)]+\))", text)
        if not match:
            return None
        try:
            version = tuple(
                int(part.strip())
                for part in match.group(1).strip("()").split(",")
                if part.strip()
            )
        except Exception:
            return None
        return version if len(version) == 3 else None

    def _parse_remote_module_diff(self, text):
        inline_match = re.search(
            r"#\s*Diff:\s*(.*?)(?=\s+#\s*[A-Za-zА-Яа-я_ -]{1,40}:|$)",
            text,
            re.S,
        )
        if inline_match:
            diff = inline_match.group(1).strip()
            return re.sub(r"\s+", " ", diff)[:1200]

        lines = text.splitlines()
        diff_lines = []
        capture = False
        for line in lines:
            normalized = line.strip().lstrip("#").strip()
            if not capture:
                if normalized.lower().startswith("diff:"):
                    value = normalized[5:].strip()
                    if value:
                        diff_lines.append(value)
                    capture = True
                continue
            if not line.strip().startswith("#"):
                break
            if normalized and re.match(r"^[A-Za-zА-Яа-я_ -]{1,40}:", normalized) and not normalized.lower().startswith("diff:"):
                break
            if normalized:
                diff_lines.append(normalized)
        return "\n".join(diff_lines).strip()[:1200]

    async def _fetch_remote_module_info(self):
        async with self._session_get(
            _MODULE_UPDATE_URL,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Cache-Control": "no-cache"},
            params={"t": int(time.time())},
        ) as resp:
            if resp.status != 200:
                return None, ""
            text = await resp.text()
        return self._parse_remote_module_version(text), self._parse_remote_module_diff(text)

    async def _send_update_notice(self, text):
        try:
            await self.inline.bot.send_message(
                self.tg_id,
                text,
                disable_web_page_preview=True,
            )
            return True
        except Exception as e:
            logger.debug("Inline update notice failed: %s", e)

        try:
            await self.client.send_message(
                self.tg_id,
                text,
                link_preview=False,
            )
            return True
        except Exception as e:
            logger.debug("Client update notice failed: %s", e)
            return False

    async def _check_github_update(self):
        try:
            async with self._update_notice_lock:
                remote_version, diff = await self._fetch_remote_module_info()
                if not remote_version:
                    return None
                if not self._is_remote_version_newer(remote_version):
                    if remote_version == __version__:
                        self.set("last_update_notice_version", None)
                    return False

                remote_version_text = self._format_module_version(remote_version)
                installed_version_text = self._format_module_version(__version__)
                notice_key = self._update_notice_key(installed_version_text, remote_version_text)
                if self._get_update_notice_count(notice_key, remote_version_text) >= _UPDATE_NOTICE_LIMIT:
                    return False

                prefix = self.get_prefix()
                install_command = f"{prefix}dlm {_MODULE_UPDATE_URL}"
                diff_text = (
                    self.strings("update_diff").format(utils.escape_html(diff))
                    if diff
                    else ""
                )
                text = self.strings("update_available").format(
                    installed_version_text,
                    remote_version_text,
                    diff_text,
                    utils.escape_html(install_command),
                )
                if await self._send_update_notice(text):
                    self._mark_update_notice_sent(notice_key, remote_version_text)
                    return True
                return None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("GitHub update check failed: %s", e)
            return None

    async def _github_update_poller(self):
        while not self._unloading:
            await asyncio.sleep(21600)
            await self._check_github_update()

    async def _startup_update_check(self):
        await asyncio.sleep(_STARTUP_UPDATE_CHECK_DELAY)
        for attempt in range(_STARTUP_UPDATE_CHECK_ATTEMPTS):
            if self._unloading:
                return
            result = await self._check_github_update()
            if result is not None:
                return
            if attempt < _STARTUP_UPDATE_CHECK_ATTEMPTS - 1:
                await asyncio.sleep(30 * (attempt + 1))

    def _assets_update_interval(self):
        interval = self._coerce_int(
            self.config["update_assets"],
            0,
            0,
            14400,
        )
        if interval == 0:
            return 0
        return max(60, interval)

    async def _update_assets(self, force=False):
        ok = True
        for wf_name in self._BUILTIN_WORKFLOWS:
            if not await self._ensure_builtin_workflow(wf_name, force=force):
                ok = False
        for tool_id in self._ctool_definitions():
            try:
                await self._fetch_ctool_workflow(tool_id, force=force)
            except Exception as e:
                ok = False
                logger.warning("Failed to update ctool workflow %s: %s", tool_id, e)
        try:
            for provider in self._provider_ids():
                await self._fetch_enhance_prompt(provider, force=force)
        except Exception as e:
            ok = False
            logger.warning("Failed to update enhance prompt: %s", e)
        return ok

    async def _assets_update_loop(self):
        while not self._unloading:
            interval = self._assets_update_interval()
            if not interval:
                await asyncio.sleep(30)
                continue
            try:
                await self._update_assets(force=True)
            except Exception as e:
                logger.warning("Background assets update failed: %s", e)
            await asyncio.sleep(interval)

    async def client_ready(self, client, db):
        self._unloading = False
        self._ensure_session()
        self._cleanup_all_input_files()

        try:
            me = await client.get_me()
            self._self_has_premium = bool(getattr(me, "premium", False))
        except Exception as e:
            self._self_has_premium = False
            logger.debug("Failed to detect account premium state: %s", e)

        try:
            await self._fetch_builtin_workflow()
            self._builtin_wf_load_failed = False
        except Exception as e:
            self._builtin_wf_load_failed = True
            logger.exception(e)
        await self._fetch_enhance_prompt()

        try:
            object_info = await self._get_object_info("ImpactWildcardProcessor")
            if object_info:
                wc_list = self._parse_object_info_list(
                    object_info, "ImpactWildcardProcessor", "Select to add Wildcard"
                )
                if wc_list:
                    self._impact_wildcard_select_text = wc_list[0]
        except Exception as e:
            logger.exception(e)

        if self._impact_wildcard_select_text is None:
            self._impact_wildcard_select_text = "Select the Wildcard to add to the text"

        try:
            self._available_sam_models = self._parse_object_info_list(
                await self._get_object_info("SAMLoader"), "SAMLoader", "model_name"
            )
        except Exception as e:
            logger.exception(e)
            self._available_sam_models = []

        current_workflow = self.get("default_workflow", _DEFAULT_WORKFLOW_NAME)
        canonical_workflow = self._canonical_workflow_name(current_workflow)
        if canonical_workflow != current_workflow:
            self.set("default_workflow", canonical_workflow)

        if canonical_workflow in self._BUILTIN_WORKFLOWS:
            await self._ensure_builtin_workflow(canonical_workflow)
        self._ensure_positive_settings()
        self._ensure_negative_settings()
        self._ensure_default_args()
        self._ensure_ult_settings()
        await self._ensure_gens_archive_autocreated()
        self._ensure_ai_settings()
        if self._update_check_task is None or self._update_check_task.done():
            self._update_check_task = asyncio.create_task(self._github_update_poller())
        if self._startup_update_check_task is None or self._startup_update_check_task.done():
            self._startup_update_check_task = asyncio.create_task(self._startup_update_check())
        if self._assets_update_task is None or self._assets_update_task.done():
            self._assets_update_task = asyncio.create_task(self._assets_update_loop())
        if self._input_cleanup_task is None or self._input_cleanup_task.done():
            self._input_cleanup_task = asyncio.create_task(self._input_cleanup_loop())

    async def on_unload(self):
        self._unloading = True
        if self._auto_delete_tasks:
            for task in list(self._auto_delete_tasks):
                task.cancel()
            await asyncio.gather(*self._auto_delete_tasks, return_exceptions=True)
            self._auto_delete_tasks.clear()
        if self._cmon_tasks:
            cmon_entries = list(self._cmon_tasks.values())
            cmon_tasks = [
                entry.get("task") if isinstance(entry, dict) else entry
                for entry in cmon_entries
            ]
            cmon_tasks = [task for task in cmon_tasks if task]
            for task in cmon_tasks:
                task.cancel()
            await asyncio.gather(*cmon_tasks, return_exceptions=True)
            self._cmon_tasks.clear()
        if self._input_cleanup_task:
            self._input_cleanup_task.cancel()
            try:
                await self._input_cleanup_task
            except asyncio.CancelledError:
                pass
        if self._assets_update_task:
            self._assets_update_task.cancel()
            try:
                await self._assets_update_task
            except asyncio.CancelledError:
                pass
        if self._startup_update_check_task:
            self._startup_update_check_task.cancel()
            try:
                await self._startup_update_check_task
            except asyncio.CancelledError:
                pass
        if self._update_check_task:
            self._update_check_task.cancel()
            try:
                await self._update_check_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed and self._active_generations > 0:
            try:
                await self._interrupt_generation()
            except Exception as e:
                logger.exception(e)
        self._cancel_flags.clear()
        self._generation_runtime.clear()
        self._cshare_preview_states.clear()
        self._cleanup_all_input_files()
        if self._session:
            await self._session.close()

    def _default_ai_settings(self):
        return {
            "provider": "gemini",
            "gemini": {
                "model": "gemini-2.5-flash",
            },
            "groq": {},
            "openrouter": {
                "model": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
            },
            "grok": {
                "model": "grok-4.20",
            },
            "deepseek": {
                "model": "deepseek-reasoner",
            },
        }

    @staticmethod
    def _provider_ids():
        return ("gemini", "groq", "openrouter", "grok", "deepseek")

    @staticmethod
    def _provider_config_key(provider):
        keys = {
            "gemini": "gemini_api_key",
            "groq": "groq_api_key",
            "openrouter": "openrouter_api_key",
            "grok": "grok_api_key",
            "deepseek": "deepseek_api_key",
        }
        return keys.get(provider)

    @staticmethod
    def _provider_model_presets(provider):
        if provider == "deepseek":
            return (
                "deepseek-reasoner",
                "deepseek-chat",
                "deepseek-v4-pro",
                "deepseek-v4-flash",
            )
        return ()

    @staticmethod
    def _provider_has_model_input(provider):
        return provider in ("gemini", "openrouter", "grok", "deepseek")

    def _ensure_ai_settings(self):
        settings = self.get("ai_provider_settings")

        if not isinstance(settings, dict):
            settings = self._default_ai_settings()

        defaults = self._default_ai_settings()
        provider = settings.get("provider")
        if provider not in self._provider_ids():
            settings["provider"] = defaults["provider"]
        for provider_name, provider_defaults in defaults.items():
            if provider_name == "provider":
                continue
            if not isinstance(settings.get(provider_name), dict):
                settings[provider_name] = dict(provider_defaults)
            for key, value in provider_defaults.items():
                settings[provider_name].setdefault(key, value)
            config_key = self._provider_config_key(provider_name)
            saved_api_key = settings[provider_name].pop("api_key", "") or ""
            if saved_api_key and config_key and not self.config[config_key]:
                self.config[config_key] = saved_api_key

        self.set("ai_provider_settings", settings)
        return settings

    def _get_ai_settings(self):
        return self._ensure_ai_settings()

    def _set_ai_settings(self, settings):
        self.set("ai_provider_settings", settings)

    def _get_prompt_provider(self):
        return self._get_ai_settings().get("provider", "gemini")

    def _get_provider_api_key(self, provider):
        self._ensure_ai_settings()
        config_key = self._provider_config_key(provider)
        return self.config[config_key] if config_key else ""

    def _get_gemini_model(self):
        return self._get_provider_model("gemini")

    def _get_provider_model(self, provider):
        defaults = self._default_ai_settings().get(provider, {})
        default_model = defaults.get("model", "")
        return self._get_ai_settings().get(provider, {}).get("model", default_model) or default_model

    def _get_provider_model_chain(self, provider):
        selected = self._get_provider_model(provider)
        models = []
        if selected:
            models.append(selected)
        for model in self._provider_model_presets(provider):
            if model and model not in models:
                models.append(model)
        return models

    def _set_prompt_provider(self, provider):
        settings = self._get_ai_settings()
        settings["provider"] = provider
        self._set_ai_settings(settings)

    def _set_provider_api_key(self, provider, api_key):
        self._ensure_ai_settings()
        config_key = self._provider_config_key(provider)
        if config_key:
            self.config[config_key] = api_key.strip()

    def _set_provider_model(self, provider, model):
        settings = self._get_ai_settings()
        settings.setdefault(provider, {})
        default_model = self._default_ai_settings().get(provider, {}).get("model", "")
        settings[provider]["model"] = model.strip() or default_model
        self._set_ai_settings(settings)

    @staticmethod
    def _coerce_int(value, default, minimum=None, maximum=None):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _get_total_generation_count(self):
        value = self.get("total_generation_counter")
        if value is None:
            value = self._coerce_int(self.get("archive_generation_counter"), 0, 0)
            self.set("total_generation_counter", value)
        return self._coerce_int(value, 0, 0)

    def _increment_total_generation_count(self):
        value = self._get_total_generation_count() + 1
        self.set("total_generation_counter", value)
        return value

    @staticmethod
    def _format_comfy_device_name(device):
        raw = str((device or {}).get("name") or "").strip()
        if not raw:
            return "Unknown"
        cleaned = re.sub(
            r"^(?:cuda|hip|mps|xpu|privateuseone):\d+\s*",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = re.sub(r"\s+:\s+.*$", "", cleaned).strip()
        if cleaned.lower() == "cpu":
            return "CPU"
        return cleaned or raw

    @staticmethod
    def _device_info_key(device, name):
        raw = f"{(device or {}).get('type', '')} {(device or {}).get('name', '')} {name}".lower()
        if "cpu" in raw:
            return "info_cpu"
        if any(token in raw for token in ("cuda", "nvidia", "gpu", "vram")):
            return "info_gpu"
        return "info_device"

    @staticmethod
    def _device_is_cpu(device, name):
        raw = f"{(device or {}).get('type', '')} {(device or {}).get('name', '')} {name}".lower()
        return "cpu" in raw

    @staticmethod
    def _format_memory_gb(value):
        return f"{value / (1024**3):.1f}GB"

    @staticmethod
    def _first_present(mapping, keys):
        if not isinstance(mapping, dict):
            return None
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
        return None

    def _default_trigger_settings(self):
        return {
            "enabled": False,
            "trigger": "comfy",
            "auto_delete": False,
            "auto_delete_delay": 150,
            "max_queue": 4,
            "max_steps": 40,
            "max_steps_user_set": False,
            "reject_russian_prompt": False,
            "blacklist": [],
        }

    def _normalize_trigger_settings(self, settings):
        if not isinstance(settings, dict):
            settings = {}
        trigger = str(settings.get("trigger") or "comfy").strip()
        if not trigger:
            trigger = "comfy"
        blacklist = settings.get("blacklist", [])
        if not isinstance(blacklist, list):
            blacklist = []
        max_steps_user_set = bool(settings.get("max_steps_user_set", False))
        raw_max_steps = settings.get("max_steps")
        max_steps = self._coerce_int(raw_max_steps, 40, 1, 100)
        if not max_steps_user_set and max_steps == 100:
            max_steps = 40
        return {
            "enabled": bool(settings.get("enabled", False)),
            "trigger": trigger,
            "auto_delete": bool(settings.get("auto_delete", False)),
            "auto_delete_delay": self._coerce_int(settings.get("auto_delete_delay"), 150, 10, 86400),
            "max_queue": self._coerce_int(settings.get("max_queue"), 4, 1, 50),
            "max_steps": max_steps,
            "max_steps_user_set": max_steps_user_set,
            "reject_russian_prompt": bool(settings.get("reject_russian_prompt", False)),
            "blacklist": [
                int(user_id)
                for user_id in blacklist
                if str(user_id).lstrip("-").isdigit()
            ],
        }

    def _ensure_ult_settings(self):
        settings = self.get("ultimate_settings", {})
        if not isinstance(settings, dict):
            settings = {}

        prompt_confirm = settings.get("prompt_confirm")
        if not isinstance(prompt_confirm, dict):
            prompt_confirm = {}

        gens_chat = settings.get("gens_chat")
        if not isinstance(gens_chat, dict):
            gens_chat = {}

        generation_time = settings.get("generation_time")
        if not isinstance(generation_time, dict):
            generation_time = {}

        telegram_censorship = settings.get("telegram_censorship")
        if not isinstance(telegram_censorship, dict):
            telegram_censorship = {}

        ui = settings.get("ui")
        if not isinstance(ui, dict):
            ui = {}
        theme = str(ui.get("theme") or _EMOJI_THEME_DEFAULT).strip().lower()
        if theme not in {
            _EMOJI_THEME_DEFAULT,
            _EMOJI_THEME_COLORED,
            _EMOJI_THEME_CUTE,
            _EMOJI_THEME_BLACK,
            _EMOJI_THEME_TROLLFACE,
        }:
            theme = _EMOJI_THEME_DEFAULT

        ai_enhance = settings.get("ai_enhance")
        legacy_default_args = self.get("default_args", {})
        legacy_ai_enabled = False
        if isinstance(legacy_default_args, dict):
            legacy_ai_enabled = self._argset_enabled(legacy_default_args.get("ai", {}))
        if not isinstance(ai_enhance, dict):
            ai_enhance = {"enabled": legacy_ai_enabled}

        gens_targets = gens_chat.get("targets")
        if not isinstance(gens_targets, list):
            gens_targets = []
        normalized_targets = []
        seen_targets = set()
        for target in gens_targets:
            if not isinstance(target, dict):
                continue
            chat_id = target.get("chat_id")
            if not chat_id:
                continue
            topic_id = target.get("topic_id")
            key = (str(chat_id), str(topic_id) if topic_id is not None else None)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            normalized_targets.append(
                {
                    "chat_id": chat_id,
                    "topic_id": topic_id,
                    "managed": bool(target.get("managed", False)),
                }
            )
        if gens_chat.get("chat_id"):
            legacy_key = (
                str(gens_chat.get("chat_id")),
                str(gens_chat.get("topic_id")) if gens_chat.get("topic_id") is not None else None,
            )
            if legacy_key not in seen_targets:
                normalized_targets.append(
                    {
                        "chat_id": gens_chat.get("chat_id"),
                        "topic_id": gens_chat.get("topic_id"),
                        "managed": bool(gens_chat.get("managed", False)),
                    }
                )
                seen_targets.add(legacy_key)

        trigger_generation = settings.get("trigger_generation")
        if not isinstance(trigger_generation, dict):
            trigger_generation = {}

        trigger_chats = trigger_generation.get("chats")
        if not isinstance(trigger_chats, dict):
            trigger_chats = {}

        normalized = {
            "prompt_confirm": {
                "enabled": bool(prompt_confirm.get("enabled", False)),
            },
            "gens_chat": {
                "enabled": bool(gens_chat.get("enabled", True)),
                "chat_id": normalized_targets[0]["chat_id"] if normalized_targets else None,
                "topic_id": normalized_targets[0]["topic_id"] if normalized_targets else None,
                "targets": normalized_targets,
                "title": gens_chat.get("title") or "ComfyUI Gens",
                "managed": bool(gens_chat.get("managed", False)),
                "save_full_prompt": True,
            },
            "generation_time": {
                "progress": bool(generation_time.get("progress", True)),
                "result": bool(generation_time.get("result", True)),
            },
            "telegram_censorship": {
                "enabled": bool(telegram_censorship.get("enabled", False)),
            },
            "ui": {
                "theme": theme,
            },
            "ai_enhance": {
                "enabled": bool(ai_enhance.get("enabled", False)),
            },
            "trigger_generation": {
                "chats": {
                    str(chat_id): self._normalize_trigger_settings(chat_settings)
                    for chat_id, chat_settings in trigger_chats.items()
                },
            },
        }

        if settings != normalized:
            self.set("ultimate_settings", normalized)

        return normalized

    def _get_ult_settings(self):
        return self._ensure_ult_settings()

    def _set_ult_settings(self, settings: dict):
        self.set("ultimate_settings", settings)

    def _prompt_confirm_enabled(self) -> bool:
        return self._get_ult_settings()["prompt_confirm"]["enabled"]

    def _get_gens_chat_config(self) -> dict:
        return self._get_ult_settings()["gens_chat"]

    def _get_generation_time_config(self) -> dict:
        return self._get_ult_settings()["generation_time"]

    def _show_generation_time_progress(self) -> bool:
        return bool(self._get_generation_time_config().get("progress", True))

    def _show_generation_time_result(self) -> bool:
        return bool(self._get_generation_time_config().get("result", True))

    def _telegram_censorship_enabled(self) -> bool:
        return bool(
            self._get_ult_settings()
            .get("telegram_censorship", {})
            .get("enabled", False)
        )

    def _ai_enhance_enabled(self) -> bool:
        return bool(self._get_ult_settings().get("ai_enhance", {}).get("enabled", False))

    def _state_toggle_text(self, enabled: bool) -> str:
        return self.strings("btn_toggle_on") if enabled else self.strings("btn_toggle_off")

    @staticmethod
    def _state_toggle_style(enabled: bool) -> str:
        return "success" if enabled else "danger"

    @staticmethod
    def _state_toggle_emoji(enabled: bool) -> str:
        return "5206607081334906820" if enabled else "5121063440311386962"

    def _get_trigger_settings_for_chat(self, chat_id, create=True) -> dict:
        settings = self._get_ult_settings()
        chat_key = str(chat_id)
        chats = settings["trigger_generation"]["chats"]
        if chat_key not in chats:
            if not create:
                return self._default_trigger_settings()
            chats[chat_key] = self._default_trigger_settings()
            self._set_ult_settings(settings)
        return dict(chats[chat_key])

    def _set_trigger_settings_for_chat(self, chat_id, chat_settings):
        settings = self._get_ult_settings()
        chat_key = str(chat_id)
        settings["trigger_generation"]["chats"][chat_key] = self._normalize_trigger_settings(chat_settings)
        self._set_ult_settings(settings)

    def _get_target_chat_id(self, target):
        if isinstance(target, Message):
            return utils.get_chat_id(target)
        form = getattr(target, "form", {}) or {}
        if isinstance(target, dict):
            form = target
        caller = form.get("caller")
        if isinstance(caller, Message):
            return utils.get_chat_id(caller)
        if isinstance(caller, int):
            return caller
        message = form.get("message")
        if isinstance(message, Message):
            return utils.get_chat_id(message)
        return None

    @staticmethod
    def _is_inline_too_long_error(error):
        text = f"{type(error).__name__}: {error}".lower()
        return any(
            marker in text
            for marker in (
                "message_too_long",
                "message is too long",
                "message text is too long",
                "text is too long",
                "caption is too long",
                "entities too long",
            )
        )

    def _truncate_inline_text_for_retry(self, text, limit):
        plain = self._plain_text(str(text or "")).replace("\r", "")
        plain = re.sub(r"[ \t]+\n", "\n", plain)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        if not plain:
            plain = self.strings("negative_not_set")
        suffix = "\n..."
        budget = max(100, int(limit) - len(suffix))
        if len(plain) > budget:
            plain = plain[:budget].rstrip() + suffix
        return utils.escape_html(plain)

    def _inline_text_retry_candidates(self, text):
        seen = {text}
        candidates = []
        for limit in _INLINE_TEXT_RETRY_LIMITS:
            candidate = self._truncate_inline_text_for_retry(text, limit)
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
        return candidates

    async def _create_inline_form(self, message, text, reply_markup=None, **kwargs):
        if not self._self_has_premium:
            return await self.inline.form(
                message=message,
                text=text,
                reply_markup=reply_markup,
                **kwargs,
            )

        form = await self.inline.form(message=message, text="👀")
        try:
            await form.edit(text=text, reply_markup=reply_markup, **kwargs)
            return form
        except Exception as e:
            logger.debug("Premium dummy inline form edit failed: %s", e)
            try:
                if hasattr(form, "delete") and callable(form.delete):
                    await form.delete()
            except Exception as delete_error:
                logger.debug("Failed to delete dummy inline form: %s", delete_error)
            if self._is_inline_too_long_error(e):
                raise
            return await self.inline.form(
                message=message,
                text=text,
                reply_markup=reply_markup,
                **kwargs,
            )

    async def _render_inline(self, target, text, reply_markup=None, **kwargs):
        text = self._apply_emoji_theme(text)
        candidates = [text]
        retry_candidates = None
        last_error = None
        index = 0
        while index < len(candidates):
            candidate = candidates[index]
            index += 1
            try:
                rendered = await self._render_inline_once(target, candidate, reply_markup, **kwargs)
                if rendered:
                    return rendered
                too_long = len(self._plain_text(candidate)) > _INLINE_TEXT_SOFT_LIMIT
            except Exception as e:
                last_error = e
                if not self._is_inline_too_long_error(e):
                    logger.debug("Inline render failed: %s", e)
                    return False
                logger.debug("Inline render text is too long, retrying with shorter text: %s", e)
                too_long = True

            if too_long and retry_candidates is None:
                retry_candidates = self._inline_text_retry_candidates(text)
                candidates.extend(retry_candidates)

        if last_error:
            logger.debug("Inline render failed after text shortening: %s", last_error)
        return False

    async def _render_inline_once(self, target, text, reply_markup=None, **kwargs):
        try:
            if isinstance(target, Message):
                return await self._create_inline_form(
                    message=target,
                    text=text,
                    reply_markup=reply_markup,
                    **kwargs,
                )
            if hasattr(target, "edit") and callable(target.edit):
                try:
                    edited = await target.edit(text=text, reply_markup=reply_markup, **kwargs)
                    if edited:
                        return edited
                except Exception as e:
                    if self._is_inline_too_long_error(e):
                        raise
                    logger.debug("Inline direct edit failed: %s", e)
            form = target if isinstance(target, dict) else getattr(target, "form", {}) or {}
            if isinstance(form, dict):
                unit_id = form.get("id") or form.get("uid") or getattr(target, "unit_id", None)
                if unit_id and hasattr(self.inline, "_edit_unit"):
                    try:
                        edited = await self.inline._edit_unit(
                            text=text,
                            reply_markup=reply_markup,
                            unit_id=unit_id,
                            **kwargs,
                        )
                        if edited:
                            return edited
                    except Exception as e:
                        if self._is_inline_too_long_error(e):
                            raise
                        logger.debug("Inline unit edit failed: %s", e)
                caller = form.get("caller") or form.get("message")
                if isinstance(caller, Message):
                    return await self._create_inline_form(
                        message=caller,
                        text=text,
                        reply_markup=reply_markup,
                        **kwargs,
                    )
        except Exception as e:
            if self._is_inline_too_long_error(e):
                raise
            logger.debug("Inline render failed: %s", e)
        return False

    def _info_banner_url(self):
        raw = str(self.config["info_banner_url"] or "").strip()
        if not raw:
            return None
        if raw.lower() in {"0", "false", "none", "off", "no", "disabled"}:
            return None
        if raw.startswith(("http://", "https://")):
            return raw
        logger.debug("Ignoring invalid info banner URL: %s", raw)
        return None

    @staticmethod
    def _info_banner_media_kwargs(url):
        path = urlparse(str(url or "")).path.lower()
        ext = os.path.splitext(path)[1]
        if ext == ".gif":
            return {"gif": url}
        if ext in {".mp4", ".mov", ".webm", ".m4v"}:
            return {"video": url}
        if ext in {"", ".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            return {"photo": url}
        return None

    async def _render_inline_with_info_banner(self, target, text, reply_markup=None, **kwargs):
        banner_url = self._info_banner_url()
        if banner_url:
            banner_kwargs = self._info_banner_media_kwargs(banner_url)
            if banner_kwargs:
                rendered = await self._render_inline(
                    target,
                    text,
                    reply_markup,
                    **banner_kwargs,
                    **kwargs,
                )
                if rendered:
                    return rendered
                logger.debug("Info banner render failed, retrying without banner")
            else:
                logger.debug("Ignoring unsupported info banner media URL: %s", banner_url)
        return await self._render_inline(target, text, reply_markup, **kwargs)

    async def _edit_inline_status(self, target, text, reply_markup=None):
        text = self._apply_emoji_theme(text)
        bot = getattr(self.inline, "bot", None)
        if bot is not None:
            try:
                inline_message_id = getattr(target, "inline_message_id", None)
                chat_id = getattr(target, "chat_id", None)
                message_id = getattr(target, "message_id", None)
                form = getattr(target, "form", {}) or {}
                if not chat_id:
                    chat_id = form.get("chat")
                if not message_id:
                    message_id = form.get("message_id")

                destination = None
                if inline_message_id:
                    destination = {"inline_message_id": inline_message_id}
                elif chat_id and message_id:
                    destination = {"chat_id": chat_id, "message_id": message_id}

                if destination:
                    await bot.edit_message_text(
                        text=text,
                        **destination,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=self.inline.generate_markup(reply_markup),
                    )
                    return True
            except Exception as e:
                logger.debug("Direct inline status edit failed: %s", e)

        try:
            return bool(await target.edit(text=text, reply_markup=reply_markup))
        except Exception as e:
            logger.warning("Inline status edit failed: %s", e)
            return False

    def _disable_gens_chat(self, drop_chat_id=False):
        settings = self._get_ult_settings()
        settings["gens_chat"]["enabled"] = False
        if drop_chat_id:
            settings["gens_chat"]["chat_id"] = None
            settings["gens_chat"]["topic_id"] = None
            settings["gens_chat"]["targets"] = []
        self._set_ult_settings(settings)

    def _get_gens_archive_targets(self):
        gens_chat = self._get_gens_chat_config()
        targets = gens_chat.get("targets")
        if isinstance(targets, list) and targets:
            return [
                target
                for target in targets
                if isinstance(target, dict) and target.get("chat_id")
            ]
        if gens_chat.get("chat_id"):
            return [
                {
                    "chat_id": gens_chat.get("chat_id"),
                    "topic_id": gens_chat.get("topic_id"),
                    "managed": bool(gens_chat.get("managed", False)),
                }
            ]
        return []

    def _sync_primary_gens_archive_target(self, gens_chat):
        targets = [
            target
            for target in gens_chat.get("targets", [])
            if isinstance(target, dict) and target.get("chat_id")
        ]
        if targets:
            gens_chat["chat_id"] = targets[0]["chat_id"]
            gens_chat["topic_id"] = targets[0].get("topic_id")
            gens_chat["managed"] = bool(targets[0].get("managed", False))
        else:
            gens_chat["chat_id"] = None
            gens_chat["topic_id"] = None
            gens_chat["managed"] = False

    def _add_gens_archive_target(self, gens_chat, chat_id, topic_id=None, managed=False):
        targets = gens_chat.get("targets")
        if not isinstance(targets, list):
            targets = []
        key = (str(chat_id), str(topic_id) if topic_id is not None else None)
        for target in targets:
            if not isinstance(target, dict):
                continue
            target_key = (
                str(target.get("chat_id")),
                str(target.get("topic_id")) if target.get("topic_id") is not None else None,
            )
            if target_key == key:
                return False
        targets.append(
            {
                "chat_id": chat_id,
                "topic_id": topic_id,
                "managed": bool(managed),
            }
        )
        gens_chat["targets"] = targets
        self._sync_primary_gens_archive_target(gens_chat)
        return True

    @staticmethod
    def _gens_archive_target_key(target):
        return (
            str(target.get("chat_id")),
            str(target.get("topic_id")) if target.get("topic_id") is not None else None,
        )

    async def _gens_archive_topic_exists(self, target):
        topic_id = target.get("topic_id")
        if topic_id is None:
            return True
        try:
            entity = await self.client.get_entity(target["chat_id"])
            result = await self.client(
                GetForumTopicsByIDRequest(
                    peer=entity,
                    topics=[topic_id],
                )
            )
            topics = getattr(result, "topics", None) or []
            if not topics:
                return False
            return not isinstance(topics[0], ForumTopicDeleted)
        except Exception as e:
            logger.debug("Generation archive topic lookup failed: %s", e)
            try:
                return bool(await self.client.get_messages(target["chat_id"], ids=topic_id))
            except Exception as fallback_error:
                logger.debug("Generation archive topic message check failed: %s", fallback_error)
                return False

    async def _recreate_managed_gens_archive_target(self, gens_chat, old_target):
        content_channel_id = self.db.get("heroku.forums", "channel_id", None)
        if not content_channel_id:
            raise RuntimeError("Generation archive forum channel is unavailable")

        title = gens_chat.get("title") or "ComfyUI Gens"
        topic = await utils.asset_forum_topic(
            self.client,
            self.db,
            content_channel_id,
            title,
            description=self.strings("ult_chat_about"),
            icon_emoji_id=_ULT_GENS_TOPIC_EMOJI_ID,
        )
        topic_id = getattr(topic, "id", None)
        if not topic_id:
            raise RuntimeError("No topic returned")

        new_target = {
            "chat_id": content_channel_id,
            "topic_id": topic_id,
            "managed": True,
        }
        targets = gens_chat.get("targets")
        if not isinstance(targets, list):
            targets = []
        old_key = self._gens_archive_target_key(old_target)
        replaced = False
        cleaned_targets = []
        for target in targets:
            if not isinstance(target, dict) or not target.get("chat_id"):
                continue
            if self._gens_archive_target_key(target) == old_key:
                if not replaced:
                    cleaned_targets.append(new_target)
                    replaced = True
                continue
            cleaned_targets.append(target)
        if not replaced:
            cleaned_targets.insert(0, new_target)

        gens_chat["targets"] = cleaned_targets
        gens_chat["title"] = getattr(topic, "title", None) or title
        gens_chat["enabled"] = True
        self._sync_primary_gens_archive_target(gens_chat)
        return new_target

    async def _ensure_gens_archive_target_for_save(self, gens_chat, target):
        if not target.get("topic_id"):
            return target, False
        if await self._gens_archive_topic_exists(target):
            return target, False
        if not target.get("managed"):
            raise RuntimeError("Generation archive topic is unavailable")
        logger.warning("Generation archive topic is missing, recreating")
        return await self._recreate_managed_gens_archive_target(gens_chat, target), True

    def _archive_message_matches_target(self, message, target):
        expected_topic_id = target.get("topic_id")
        if not expected_topic_id or not message:
            return True
        actual_topic_id = self._safe_topic(message)
        if actual_topic_id is None:
            reply_to = getattr(message, "reply_to", None)
            actual_topic_id = (
                getattr(reply_to, "reply_to_top_id", None)
                or getattr(reply_to, "reply_to_msg_id", None)
                or getattr(message, "reply_to_msg_id", None)
            )
        return str(actual_topic_id) == str(expected_topic_id)

    async def _create_gens_archive_target(self, gens_chat):
        title = gens_chat.get("title") or "ComfyUI Gens"
        content_channel_id = self.db.get("heroku.forums", "channel_id", None)
        if content_channel_id:
            try:
                topic = await utils.asset_forum_topic(
                    self.client,
                    self.db,
                    content_channel_id,
                    title,
                    description=self.strings("ult_chat_about"),
                    icon_emoji_id=_ULT_GENS_TOPIC_EMOJI_ID,
                )
                topic_id = getattr(topic, "id", None)
                if not topic_id:
                    raise RuntimeError("No topic returned")
                gens_chat["title"] = getattr(topic, "title", None) or title
                gens_chat["enabled"] = True
                return self._add_gens_archive_target(
                    gens_chat,
                    content_channel_id,
                    topic_id,
                    managed=True,
                )
            except Exception as e:
                logger.debug("Failed to create generation archive topic: %s", e)

        peer, _ = await utils.asset_channel(
            self.client,
            title,
            self.strings("ult_chat_about"),
            silent=True,
            archive=True,
            invite_bot=False,
            forum=False,
            _folder="comfy",
        )
        chat_id = getattr(peer, "id", None)
        if not chat_id:
            raise RuntimeError("No archive chat returned")
        gens_chat["title"] = getattr(peer, "title", None) or title
        gens_chat["enabled"] = True
        return self._add_gens_archive_target(
            gens_chat,
            chat_id,
            None,
            managed=True,
        )

    async def _ensure_gens_archive_autocreated(self):
        settings = self._get_ult_settings()
        gens_chat = settings["gens_chat"]
        if not gens_chat.get("enabled") or self._get_gens_archive_targets():
            return False
        try:
            await self._create_gens_archive_target(gens_chat)
            self._set_ult_settings(settings)
            return True
        except Exception as e:
            logger.exception(e)
            return False

    def _normalize_archive_chat_id(self, chat_id):
        chat_id = int(chat_id)
        if str(chat_id).startswith("-100"):
            return int(str(chat_id)[4:])
        return chat_id

    def _parse_archive_target(self, query):
        query = str(query or "").strip()
        if not query:
            return None, None

        link_match = re.search(r"t\.me/c/(\d+)(?:/(\d+))?(?:/(\d+))?", query)
        if link_match:
            chat_id = self._normalize_archive_chat_id(link_match.group(1))
            topic_id = int(link_match.group(2)) if link_match.group(2) and link_match.group(3) else None
            return chat_id, topic_id

        normalized = query.replace(":", " ")
        numbers = re.findall(r"-?\d+", normalized)
        if not numbers:
            return None, None

        chat_id = self._normalize_archive_chat_id(numbers[0])
        topic_id = int(numbers[1]) if len(numbers) > 1 else None
        return chat_id, topic_id

    async def _ult_render_main(self, target):
        settings = self._get_ult_settings()
        chat_id = self._get_target_chat_id(target)
        trigger_settings = self._get_trigger_settings_for_chat(chat_id) if chat_id is not None else self._default_trigger_settings()
        ai_status = (
            self.strings("ult_status_on")
            if settings["ai_enhance"]["enabled"]
            else self.strings("ult_status_off")
        )
        gens_status = (
            self.strings("ult_status_on")
            if settings["gens_chat"]["enabled"]
            else self.strings("ult_status_off")
        )
        trigger_status = (
            self.strings("ult_status_on")
            if trigger_settings["enabled"]
            else self.strings("ult_status_off")
        )
        censorship_enabled = bool(settings["telegram_censorship"]["enabled"])
        censorship_status = (
            self.strings("ult_status_on")
            if censorship_enabled
            else self.strings("ult_status_off")
        )
        theme = settings["ui"]["theme"]

        text = "\n".join(
            [
                self.strings("ult_title"),
                "",
                f"{self.strings('ult_ai_title')}: {ai_status}",
                f"{self.strings('ult_gens_title')}: {gens_status}",
                f"{self.strings('ult_trigger_title')}: {trigger_status}",
                self.strings("ult_theme_status").format(utils.escape_html(theme)),
                self.strings("ult_censorship_status").format(censorship_status),
            ]
        )

        markup = [
            [
                {
                    "text": self.strings("ult_btn_ai"),
                    "callback": self._ult_open_ai_enhance,
                    "style": "primary",
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_gens"),
                    "callback": self._ult_open_gens_chat,
                    "style": "primary",
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_trigger"),
                    "callback": self._ult_open_trigger_generation,
                    "args": (chat_id,),
                    "style": "primary",
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_time"),
                    "callback": self._ult_open_generation_time,
                    "style": "primary",
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_theme"),
                    "callback": self._ult_open_emoji_theme,
                    "style": "primary",
                }
            ],
            [
                {
                    "text": (
                        self.strings("ult_btn_censorship_on")
                        if censorship_enabled
                        else self.strings("ult_btn_censorship_off")
                    ),
                    "callback": self._ult_toggle_telegram_censorship,
                    "style": self._state_toggle_style(censorship_enabled),
                    "emoji_id": self._state_toggle_emoji(censorship_enabled),
                }
            ],
            [{
                "text": self.strings("btn_close"),
                "callback": self._safe_close_form,
                "style": "danger",
            }],
        ]

        await self._render_inline(target, text, markup)

    async def _ult_open_ai_enhance(self, call: InlineCall):
        await self._ult_render_ai_enhance(call)

    async def _ult_open_gens_chat(self, call: InlineCall):
        await self._ult_render_gens_chat(call)

    async def _ult_open_trigger_generation(self, call: InlineCall, chat_id):
        if chat_id is None:
            chat_id = self._get_target_chat_id(call)
        await self._ult_render_trigger_generation(call, chat_id)

    async def _ult_open_generation_time(self, call: InlineCall):
        await self._ult_render_generation_time(call)

    async def _ult_open_emoji_theme(self, call: InlineCall):
        await self._ult_render_emoji_theme(call)

    async def _ult_render_emoji_theme(self, target):
        settings = self._get_ult_settings()
        current = settings["ui"]["theme"]
        text = "\n".join(
            [
                self.strings("ult_theme_title"),
                "",
                self.strings("ult_theme_status").format(utils.escape_html(current)),
            ]
        )
        markup = [
            [
                {
                    "text": self.strings("ult_btn_theme_default"),
                    "callback": self._ult_set_emoji_theme,
                    "args": (_EMOJI_THEME_DEFAULT,),
                    "style": "success" if current == _EMOJI_THEME_DEFAULT else "primary",
                },
                {
                    "text": self.strings("ult_btn_theme_colored"),
                    "callback": self._ult_set_emoji_theme,
                    "args": (_EMOJI_THEME_COLORED,),
                    "style": "success" if current == _EMOJI_THEME_COLORED else "primary",
                },
            ],
            [
                {
                    "text": self.strings("ult_btn_theme_cute"),
                    "callback": self._ult_set_emoji_theme,
                    "args": (_EMOJI_THEME_CUTE,),
                    "style": "success" if current == _EMOJI_THEME_CUTE else "primary",
                },
                {
                    "text": self.strings("ult_btn_theme_black"),
                    "callback": self._ult_set_emoji_theme,
                    "args": (_EMOJI_THEME_BLACK,),
                    "style": "success" if current == _EMOJI_THEME_BLACK else "primary",
                },
            ],
            [
                {
                    "text": self.strings("ult_btn_theme_trollface"),
                    "callback": self._ult_set_emoji_theme,
                    "args": (_EMOJI_THEME_TROLLFACE,),
                    "style": "success" if current == _EMOJI_THEME_TROLLFACE else "primary",
                },
            ],
            [{"text": self.strings("btn_back"), "callback": self._ult_back_main, "style": "primary"}],
        ]
        await self._render_inline(target, text, markup)

    async def _ult_set_emoji_theme(self, call: InlineCall, theme: str):
        theme = str(theme or _EMOJI_THEME_DEFAULT).strip().lower()
        if theme not in {
            _EMOJI_THEME_DEFAULT,
            _EMOJI_THEME_COLORED,
            _EMOJI_THEME_CUTE,
            _EMOJI_THEME_BLACK,
            _EMOJI_THEME_TROLLFACE,
        }:
            theme = _EMOJI_THEME_DEFAULT
        settings = self._get_ult_settings()
        settings["ui"]["theme"] = theme
        self._set_ult_settings(settings)
        try:
            await call.answer(self.strings("ult_toggle_saved"))
        except Exception:
            pass
        await self._ult_render_emoji_theme(call)

    async def _ult_toggle_telegram_censorship(self, call: InlineCall):
        settings = self._get_ult_settings()
        settings["telegram_censorship"]["enabled"] = not settings["telegram_censorship"]["enabled"]
        self._set_ult_settings(settings)
        try:
            await call.answer(self.strings("ult_toggle_saved"))
        except Exception:
            pass
        await self._ult_render_main(call)

    async def _ult_render_generation_time(self, target):
        time_settings = self._get_generation_time_config()
        progress_enabled = bool(time_settings.get("progress", True))
        result_enabled = bool(time_settings.get("result", True))
        progress_status = (
            self.strings("ult_status_on")
            if progress_enabled
            else self.strings("ult_status_off")
        )
        result_status = (
            self.strings("ult_status_on")
            if result_enabled
            else self.strings("ult_status_off")
        )

        text = "\n".join(
            [
                self.strings("ult_time_title"),
                "",
                self.strings("ult_time_progress").format(progress_status),
                self.strings("ult_time_result").format(result_status),
            ]
        )

        markup = [
            [
                {
                    "text": f"{self._state_toggle_text(progress_enabled)} {self.strings('ult_btn_time_progress')}",
                    "callback": self._ult_toggle_time_progress,
                    "style": self._state_toggle_style(progress_enabled),
                    "emoji_id": self._state_toggle_emoji(progress_enabled),
                },
                {
                    "text": f"{self._state_toggle_text(result_enabled)} {self.strings('ult_btn_time_result')}",
                    "callback": self._ult_toggle_time_result,
                    "style": self._state_toggle_style(result_enabled),
                    "emoji_id": self._state_toggle_emoji(result_enabled),
                },
            ],
            [
                {
                    "text": self.strings("btn_back"),
                    "callback": self._ult_back_main,
                    "style": "primary",
                }
            ],
        ]

        await self._render_inline(target, text, markup)

    async def _ult_render_ai_enhance(self, target):
        settings = self._get_ult_settings()
        ai_enabled = bool(settings["ai_enhance"]["enabled"])
        confirm_enabled = bool(settings["prompt_confirm"]["enabled"])
        provider = self._get_prompt_provider()
        provider_name = self._format_provider_name(provider)
        api_key_status = (
            self.strings("provider_api_key_set")
            if self._get_provider_api_key(provider)
            else self.strings("provider_api_key_missing")
        )
        model = self._get_provider_model(provider) if self._provider_has_model_input(provider) else self.strings("not_set")

        text = "\n".join(
            [
                self.strings("ult_ai_title"),
                "",
                self.strings("ult_ai_auto").format(
                    self.strings("ult_status_on") if ai_enabled else self.strings("ult_status_off")
                ),
                self.strings("ult_ai_prompt_confirm").format(
                    self.strings("ult_status_on") if confirm_enabled else self.strings("ult_status_off")
                ),
                self.strings("ult_ai_provider").format(provider_name),
                self.strings("ult_ai_model").format(self._preview_negative(model, 120)),
                self.strings("ult_ai_key").format(api_key_status),
                "",
                self.strings("ult_ai_desc"),
            ]
        )

        markup = [
            [
                {
                    "text": f"{self._state_toggle_text(ai_enabled)} {self.strings('ult_btn_ai_auto')}",
                    "callback": self._ult_toggle_ai_enhance,
                    "style": self._state_toggle_style(ai_enabled),
                    "emoji_id": self._state_toggle_emoji(ai_enabled),
                }
            ],
            [
                {
                    "text": f"{self._state_toggle_text(confirm_enabled)} {self.strings('ult_btn_prompt_confirm')}",
                    "callback": self._ult_toggle_prompt_confirm,
                    "style": self._state_toggle_style(confirm_enabled),
                    "emoji_id": self._state_toggle_emoji(confirm_enabled),
                }
            ],
            [{"text": self.strings("provider_btn_menu"), "callback": self._argset_provider_menu}],
            [{"text": self.strings("enhance_prompt_btn_menu"), "callback": self._ult_open_enhance_prompts, "style": "primary"}],
            [{"text": self.strings("btn_back"), "callback": self._ult_back_main, "style": "primary"}],
        ]
        await self._render_inline(target, text, markup)

    async def _ult_render_gens_chat(self, target):
        settings = self._get_ult_settings()
        gens_chat = settings["gens_chat"]
        enabled = gens_chat["enabled"]
        status = (
            self.strings("ult_status_on")
            if enabled
            else self.strings("ult_status_off")
        )
        toggle_text = self._state_toggle_text(enabled)
        toggle_style = self._state_toggle_style(enabled)

        lines = [
            self.strings("ult_gens_title"),
            status,
            "",
            self.strings("ult_gens_desc"),
            "",
        ]

        targets = self._get_gens_archive_targets()
        if targets:
            target_lines = []
            for archive_target in targets:
                if archive_target.get("topic_id"):
                    target_lines.append(
                        self.strings("ult_chat_target_topic").format(
                            archive_target["chat_id"],
                            archive_target["topic_id"],
                        )
                    )
                else:
                    target_lines.append(
                        self.strings("ult_chat_target_chat").format(archive_target["chat_id"])
                    )
            lines.append(self.strings("ult_chat_targets").format("\n".join(target_lines)))
        else:
            lines.append(self.strings("ult_chat_missing"))

        text = "\n".join(lines)

        create_text = (
            self.strings("ult_btn_recreate_chat")
            if targets
            else self.strings("ult_btn_create_chat")
        )

        markup = [
            [
                {
                    "text": toggle_text,
                    "callback": self._ult_toggle_gens_chat,
                    "style": toggle_style,
                    "emoji_id": self._state_toggle_emoji(enabled),
                }
            ],
            [
                {
                    "text": create_text,
                    "callback": self._ult_create_gens_chat,
                    "style": "primary",
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_bind_chat"),
                    "input": self.strings("ult_chat_bind_input"),
                    "handler": self._ult_bind_gens_chat,
                }
            ],
        ]

        if targets:
            markup.append(
                [
                    {
                        "text": self.strings("ult_btn_remove_chat"),
                        "callback": self._ult_render_gens_targets,
                        "style": "danger",
                    }
                ]
            )
            markup.append(
                [
                    {
                        "text": self.strings("ult_btn_clear_chats"),
                        "callback": self._ult_clear_gens_targets,
                        "style": "danger",
                    }
                ]
            )

        markup.extend(
            [
            [
                {
                    "text": self.strings("btn_back"),
                    "callback": self._ult_back_main,
                    "style": "primary",
                }
            ],
            ]
        )

        await self._render_inline(target, text, markup)

    async def _ult_render_gens_targets(self, target):
        targets = self._get_gens_archive_targets()
        if not targets:
            text = "\n".join(
                [
                    self.strings("ult_chat_targets_title"),
                    "",
                    self.strings("ult_chat_targets_empty"),
                ]
            )
            markup = [[{"text": self.strings("btn_back"), "callback": self._ult_open_gens_chat, "style": "primary"}]]
            return await self._render_inline(target, text, markup)

        lines = [self.strings("ult_chat_targets_title"), ""]
        markup = []
        for index, archive_target in enumerate(targets):
            if archive_target.get("topic_id"):
                label = self.strings("ult_chat_target_topic").format(
                    archive_target["chat_id"],
                    archive_target["topic_id"],
                )
            else:
                label = self.strings("ult_chat_target_chat").format(archive_target["chat_id"])
            lines.append(f"{index + 1}. {label}")
            markup.append(
                [
                    {
                        "text": f"{index + 1}. {archive_target['chat_id']}",
                        "callback": self._ult_remove_gens_target,
                        "args": (index,),
                        "style": "danger",
                    }
                ]
            )

        markup.append([{"text": self.strings("btn_back"), "callback": self._ult_open_gens_chat, "style": "primary"}])
        await self._render_inline(target, "\n".join(lines), markup)

    def _format_duration(self, seconds):
        seconds = max(0, int(seconds))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts)

    async def _ult_render_trigger_generation(self, target, chat_id):
        chat_id = chat_id if chat_id is not None else self._get_target_chat_id(target)
        settings = self._get_trigger_settings_for_chat(chat_id)
        enabled = settings["enabled"]
        auto_delete = settings["auto_delete"]
        status = (
            self.strings("ult_status_on")
            if enabled
            else self.strings("ult_status_off")
        )
        auto_delete_status = (
            self.strings("ult_status_on")
            if auto_delete
            else self.strings("ult_status_off")
        )
        russian_guard = settings.get("reject_russian_prompt", False)
        russian_guard_status = (
            self.strings("ult_status_on")
            if russian_guard
            else self.strings("ult_status_off")
        )
        toggle_text = self._state_toggle_text(enabled)
        toggle_style = self._state_toggle_style(enabled)
        auto_delete_toggle = self._state_toggle_text(auto_delete)
        auto_delete_style = self._state_toggle_style(auto_delete)
        active = self._trigger_queue_counts.get(str(chat_id), 0)

        text = "\n".join(
            [
                self.strings("ult_trigger_title"),
                status,
                "",
                self.strings("ult_trigger_desc"),
                "",
                self.strings("ult_trigger_chat").format(utils.escape_html(str(chat_id))),
                self.strings("ult_trigger_word").format(utils.escape_html(settings["trigger"])),
                self.strings("ult_trigger_autodelete").format(auto_delete_status),
                self.strings("ult_trigger_delay").format(self._format_duration(settings["auto_delete_delay"])),
                self.strings("ult_trigger_queue").format(settings["max_queue"]),
                self.strings("ult_trigger_steps_limit").format(settings["max_steps"]),
                self.strings("ult_trigger_active").format(active),
                self.strings("ult_trigger_russian_guard").format(russian_guard_status),
                self.strings("ult_trigger_blacklist").format(len(settings.get("blacklist", []))),
            ]
        )

        markup = [
            [
                {
                    "text": toggle_text,
                    "callback": self._ult_toggle_trigger_generation,
                    "args": (chat_id,),
                    "style": toggle_style,
                    "emoji_id": self._state_toggle_emoji(enabled),
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_trigger_word"),
                    "input": self.strings("ult_trigger_word_input"),
                    "handler": self._ult_trigger_word_input,
                    "args": (chat_id,),
                }
            ],
            [
                {
                    "text": auto_delete_toggle,
                    "callback": self._ult_toggle_trigger_autodelete,
                    "args": (chat_id,),
                    "style": auto_delete_style,
                    "emoji_id": self._state_toggle_emoji(auto_delete),
                },
                {
                    "text": self.strings("ult_btn_trigger_delay"),
                    "input": self.strings("ult_trigger_delay_input"),
                    "handler": self._ult_trigger_delay_input,
                    "args": (chat_id,),
                },
            ],
            [
                {
                    "text": self.strings("ult_btn_trigger_queue"),
                    "input": self.strings("ult_trigger_queue_input"),
                    "handler": self._ult_trigger_queue_input,
                    "args": (chat_id,),
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_trigger_steps"),
                    "input": self.strings("ult_trigger_steps_input"),
                    "handler": self._ult_trigger_steps_input,
                    "args": (chat_id,),
                }
            ],
            [
                {
                    "text": f"{self._state_toggle_text(russian_guard)} {self.strings('ult_trigger_reject_russian')}",
                    "callback": self._ult_toggle_trigger_reject_russian,
                    "args": (chat_id,),
                    "style": self._state_toggle_style(russian_guard),
                    "emoji_id": self._state_toggle_emoji(russian_guard),
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_trigger_blacklist"),
                    "callback": self._ult_render_trigger_blacklist,
                    "args": (chat_id,),
                    "style": "danger",
                }
            ],
            [
                {
                    "text": self.strings("btn_back"),
                    "callback": self._ult_back_main,
                    "style": "primary",
                }
            ],
        ]

        await self._render_inline(target, text, markup)

    async def _format_trigger_blacklist_lines(self, user_ids):
        lines = []
        for index, user_id in enumerate(user_ids, 1):
            label = str(user_id)
            try:
                entity = await self.client.get_entity(int(user_id))
                username = getattr(entity, "username", None)
                if username:
                    label = f"@{username}"
                else:
                    name = " ".join(
                        item
                        for item in (
                            getattr(entity, "first_name", None),
                            getattr(entity, "last_name", None),
                        )
                        if item
                    ).strip()
                    label = name or str(user_id)
            except Exception as e:
                logger.debug("Failed to resolve blacklist user %s: %s", user_id, e)
            lines.append(
                f'{index}. <a href="tg://user?id={int(user_id)}">{utils.escape_html(label)}</a> '
                f"(<code>{int(user_id)}</code>)"
            )
        return lines

    async def _ult_render_trigger_blacklist(self, target, chat_id):
        chat_id = chat_id if chat_id is not None else self._get_target_chat_id(target)
        settings = self._get_trigger_settings_for_chat(chat_id)
        user_ids = settings.get("blacklist", [])
        lines = [self.strings("ult_trigger_blacklist_title"), ""]
        if user_ids:
            lines.extend(await self._format_trigger_blacklist_lines(user_ids))
        else:
            lines.append(self.strings("ult_trigger_blacklist_empty"))
        markup = [[{"text": self.strings("btn_back"), "callback": self._ult_open_trigger_generation, "args": (chat_id,), "style": "primary"}]]
        await self._render_inline(target, "\n".join(lines), markup)

    async def _ult_back_main(self, call: InlineCall):
        await self._ult_render_main(call)

    async def _ult_toggle_ai_enhance(self, call: InlineCall):
        settings = self._get_ult_settings()
        settings["ai_enhance"]["enabled"] = not settings["ai_enhance"]["enabled"]
        self._set_ult_settings(settings)
        try:
            await call.answer(self.strings("ult_toggle_saved"))
        except Exception:
            pass
        await self._ult_render_ai_enhance(call)

    async def _ult_toggle_prompt_confirm(self, call: InlineCall):
        settings = self._get_ult_settings()
        settings["prompt_confirm"]["enabled"] = not settings["prompt_confirm"]["enabled"]
        self._set_ult_settings(settings)
        try:
            await call.answer(self.strings("ult_toggle_saved"))
        except Exception:
            pass
        await self._ult_render_ai_enhance(call)

    async def _ult_toggle_gens_chat(self, call: InlineCall):
        settings = self._get_ult_settings()
        gens_chat = settings["gens_chat"]
        if not self._get_gens_archive_targets() and not gens_chat.get("enabled"):
            try:
                await call.answer(
                    self._plain_text(self.strings("ult_chat_need_create")),
                    show_alert=True,
                )
            except Exception:
                pass
            await self._ult_render_gens_chat(call)
            return

        gens_chat["enabled"] = not gens_chat["enabled"]
        self._set_ult_settings(settings)
        try:
            await call.answer(self.strings("ult_toggle_saved"))
        except Exception:
            pass
        await self._ult_render_gens_chat(call)

    async def _ult_toggle_time_progress(self, call: InlineCall):
        settings = self._get_ult_settings()
        settings["generation_time"]["progress"] = not settings["generation_time"].get("progress", True)
        self._set_ult_settings(settings)
        try:
            await call.answer(self.strings("ult_toggle_saved"))
        except Exception:
            pass
        await self._ult_render_generation_time(call)

    async def _ult_toggle_time_result(self, call: InlineCall):
        settings = self._get_ult_settings()
        settings["generation_time"]["result"] = not settings["generation_time"].get("result", True)
        self._set_ult_settings(settings)
        try:
            await call.answer(self.strings("ult_toggle_saved"))
        except Exception:
            pass
        await self._ult_render_generation_time(call)

    async def _ult_toggle_trigger_generation(self, call: InlineCall, chat_id):
        settings = self._get_trigger_settings_for_chat(chat_id)
        settings["enabled"] = not settings["enabled"]
        self._set_trigger_settings_for_chat(chat_id, settings)
        try:
            await call.answer(self.strings("ult_trigger_saved"))
        except Exception:
            pass
        await self._ult_render_trigger_generation(call, chat_id)

    async def _ult_toggle_trigger_autodelete(self, call: InlineCall, chat_id):
        settings = self._get_trigger_settings_for_chat(chat_id)
        settings["auto_delete"] = not settings["auto_delete"]
        self._set_trigger_settings_for_chat(chat_id, settings)
        try:
            await call.answer(self.strings("ult_trigger_saved"))
        except Exception:
            pass
        await self._ult_render_trigger_generation(call, chat_id)

    async def _ult_trigger_word_input(self, call: InlineCall, query: str, chat_id):
        settings = self._get_trigger_settings_for_chat(chat_id)
        trigger = str(query or "").strip()
        if trigger:
            settings["trigger"] = trigger
            self._set_trigger_settings_for_chat(chat_id, settings)
        try:
            await call.answer(self.strings("ult_trigger_saved"))
        except Exception:
            pass
        await self._ult_render_trigger_generation(call, chat_id)

    async def _ult_trigger_delay_input(self, call: InlineCall, query: str, chat_id):
        settings = self._get_trigger_settings_for_chat(chat_id)
        settings["auto_delete_delay"] = self._coerce_int(query, settings["auto_delete_delay"], 10, 86400)
        self._set_trigger_settings_for_chat(chat_id, settings)
        try:
            await call.answer(self.strings("ult_trigger_saved"))
        except Exception:
            pass
        await self._ult_render_trigger_generation(call, chat_id)

    async def _ult_trigger_queue_input(self, call: InlineCall, query: str, chat_id):
        settings = self._get_trigger_settings_for_chat(chat_id)
        settings["max_queue"] = self._coerce_int(query, settings["max_queue"], 1, 50)
        self._set_trigger_settings_for_chat(chat_id, settings)
        try:
            await call.answer(self.strings("ult_trigger_saved"))
        except Exception:
            pass
        await self._ult_render_trigger_generation(call, chat_id)

    async def _ult_trigger_steps_input(self, call: InlineCall, query: str, chat_id):
        settings = self._get_trigger_settings_for_chat(chat_id)
        settings["max_steps"] = self._coerce_int(query, settings["max_steps"], 1, 100)
        settings["max_steps_user_set"] = True
        self._set_trigger_settings_for_chat(chat_id, settings)
        try:
            await call.answer(self.strings("ult_trigger_saved"))
        except Exception:
            pass
        await self._ult_render_trigger_generation(call, chat_id)

    async def _ult_toggle_trigger_reject_russian(self, call: InlineCall, chat_id):
        settings = self._get_trigger_settings_for_chat(chat_id)
        settings["reject_russian_prompt"] = not settings.get("reject_russian_prompt", False)
        self._set_trigger_settings_for_chat(chat_id, settings)
        try:
            await call.answer(self.strings("ult_trigger_saved"))
        except Exception:
            pass
        await self._ult_render_trigger_generation(call, chat_id)

    async def _resolve_trigger_blacklist_user(self, message, query):
        query = str(query or "").strip()
        if query:
            try:
                entity = await self.client.get_entity(
                    int(query) if query.lstrip("-").isdigit() else query
                )
                user_id = getattr(entity, "id", None)
                if user_id:
                    return int(user_id)
            except Exception as e:
                logger.debug("Failed to resolve blacklist user from args %s: %s", query, e)
        try:
            reply = await message.get_reply_message()
        except Exception:
            reply = None
        if reply:
            sender_id = getattr(reply, "sender_id", None)
            if sender_id:
                return int(sender_id)
            try:
                sender = await reply.get_sender()
                sender_id = getattr(sender, "id", None)
                if sender_id:
                    return int(sender_id)
            except Exception as e:
                logger.debug("Failed to resolve blacklist user from reply: %s", e)
        return None

    def _toggle_trigger_blacklist_user(self, chat_id, user_id):
        settings = self._get_trigger_settings_for_chat(chat_id)
        blacklist = [
            int(item)
            for item in settings.get("blacklist", [])
            if str(item).lstrip("-").isdigit()
        ]
        user_id = int(user_id)
        if user_id in blacklist:
            blacklist = [item for item in blacklist if item != user_id]
            added = False
        else:
            blacklist.append(user_id)
            added = True
        settings["blacklist"] = blacklist
        self._set_trigger_settings_for_chat(chat_id, settings)
        return added

    async def _ult_toggle_trigger_blacklist_user(self, message, query):
        chat_id = utils.get_chat_id(message)
        user_id = await self._resolve_trigger_blacklist_user(message, query)
        if not user_id:
            return await self._safe_answer(message, self.strings("ult_trigger_blacklist_no_user"))
        added = self._toggle_trigger_blacklist_user(chat_id, user_id)
        await self._safe_answer(
            message,
            self.strings(
                "ult_trigger_blacklist_added"
                if added
                else "ult_trigger_blacklist_removed"
            ),
        )

    async def _ult_bind_gens_chat(self, call: InlineCall, query: str):
        chat_id, topic_id = self._parse_archive_target(query)
        if not chat_id:
            try:
                await call.answer(
                    self._plain_text(self.strings("ult_chat_bind_bad")),
                    show_alert=True,
                )
            except Exception:
                pass
            await self._ult_render_gens_chat(call)
            return

        try:
            await self.client.get_entity(chat_id)
            settings = self._get_ult_settings()
            gens_chat = settings["gens_chat"]
            added = self._add_gens_archive_target(gens_chat, chat_id, topic_id, managed=False)
            gens_chat["enabled"] = True
            self._set_ult_settings(settings)
            try:
                await call.answer(
                    self._plain_text(
                        self.strings("ult_chat_bound")
                        if added
                        else self.strings("ult_chat_already_bound")
                    ),
                    show_alert=True,
                )
            except Exception:
                pass
        except Exception as e:
            logger.exception(e)
            try:
                await call.answer(
                    self._plain_text(self.strings("ult_chat_bind_failed")).format(str(e)),
                    show_alert=True,
                )
            except Exception:
                pass
        await self._ult_render_gens_chat(call)

    async def _ult_remove_gens_target(self, call: InlineCall, index: int):
        settings = self._get_ult_settings()
        gens_chat = settings["gens_chat"]
        targets = [
            target
            for target in gens_chat.get("targets", [])
            if isinstance(target, dict) and target.get("chat_id")
        ]
        if 0 <= index < len(targets):
            targets.pop(index)
            gens_chat["targets"] = targets
            if not targets:
                gens_chat["enabled"] = False
            self._sync_primary_gens_archive_target(gens_chat)
            self._set_ult_settings(settings)
            try:
                await call.answer(self._plain_text(self.strings("ult_chat_target_removed")), show_alert=True)
            except Exception:
                pass
        await self._ult_render_gens_targets(call)

    async def _ult_clear_gens_targets(self, call: InlineCall):
        settings = self._get_ult_settings()
        gens_chat = settings["gens_chat"]
        gens_chat["targets"] = []
        gens_chat["enabled"] = False
        self._sync_primary_gens_archive_target(gens_chat)
        self._set_ult_settings(settings)
        try:
            await call.answer(self._plain_text(self.strings("ult_chat_targets_cleared")), show_alert=True)
        except Exception:
            pass
        await self._ult_render_gens_chat(call)

    async def _ult_create_gens_chat(self, call: InlineCall):
        settings = self._get_ult_settings()
        gens_chat = settings["gens_chat"]
        had_old_chat = bool(self._get_gens_archive_targets())

        try:
            added = await self._create_gens_archive_target(gens_chat)
            self._set_ult_settings(settings)
            try:
                await call.answer(
                    self._plain_text(
                        self.strings("ult_chat_already_bound")
                        if not added
                        else (
                            self.strings("ult_chat_recreated")
                            if had_old_chat
                            else self.strings("ult_chat_created")
                        )
                    ),
                    show_alert=True,
                )
            except Exception:
                pass
            await self._ult_render_gens_chat(call)
        except Exception as e:
            logger.exception(e)
            try:
                await call.answer(
                    self._plain_text(self.strings("ult_chat_create_failed")).format(
                        str(e)
                    ),
                    show_alert=True,
                )
            except Exception:
                pass
            await self._ult_render_gens_chat(call)

    def _base_url(self):
        url = str(self.config["comfyui_url"] or "").strip().rstrip("/")
        if not url:
            return None
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError:
            logger.debug("ComfyUI URL format invalid: %s", url)
            return None
        if parsed.scheme in ("http", "https") and hostname:
            return url
        logger.debug("ComfyUI URL format invalid: %s", url)
        return None

    @staticmethod
    def _normalize_probe_url(url):
        url = str(url or "").strip().rstrip("/")
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError as e:
            raise ValueError(url) from e
        if parsed.scheme in ("http", "https") and hostname:
            return url
        raise ValueError(url)

    @staticmethod
    def _ct_ws_url(base_url, client_id):
        return (
            base_url.replace("http://", "ws://", 1)
            .replace("https://", "wss://", 1)
            + f"/ws?clientId={client_id}"
        )

    @staticmethod
    def _ct_preview(value, limit=700):
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            text = str(value)
        text = " ".join(text.split())
        return text[:limit] + ("..." if len(text) > limit else "")

    @staticmethod
    def _ct_input_default(spec, fallback):
        if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict):
            return spec[1].get("default", fallback)
        return fallback

    @staticmethod
    def _ct_icon(ok):
        if ok:
            return '<emoji document_id=5206607081334906820>✅</emoji>'
        return '<emoji document_id=5121063440311386962>👎</emoji>'

    def _ct_line(self, ok, label, detail=None):
        line = "{} <code>{}</code>".format(
            self._ct_icon(ok),
            utils.escape_html(str(label)),
        )
        if detail:
            line += f": {detail}"
        return line

    def _ct_error_detail(self, error, limit=220):
        return "<code>{}</code>".format(
            utils.escape_html(self._ct_preview(error, limit))
        )

    def _ct_build_empty_image_workflow(self, object_info):
        empty_inputs = {
            "width": 128,
            "height": 128,
            "batch_size": 1,
            "color": 0,
        }
        save_inputs = {
            "images": ["1", 0],
            "filename_prefix": f"ctprobe_{int(time.time())}",
        }

        if isinstance(object_info, dict):
            empty_req = (
                object_info
                .get("EmptyImage", {})
                .get("input", {})
                .get("required", {})
            )
            save_req = (
                object_info
                .get("SaveImage", {})
                .get("input", {})
                .get("required", {})
            )
            if isinstance(empty_req, dict):
                for key, fallback in tuple(empty_inputs.items()):
                    if key in empty_req:
                        empty_inputs[key] = self._ct_input_default(empty_req[key], fallback)
                for key in empty_req:
                    empty_inputs.setdefault(key, self._ct_input_default(empty_req[key], None))
            if isinstance(save_req, dict):
                for key in save_req:
                    if key == "images":
                        save_inputs[key] = ["1", 0]
                    elif key == "filename_prefix":
                        save_inputs[key] = f"ctprobe_{int(time.time())}"
                    else:
                        save_inputs.setdefault(key, self._ct_input_default(save_req[key], None))

        return (
            {
                "1": {
                    "class_type": "EmptyImage",
                    "inputs": empty_inputs,
                    "_meta": {"title": "Probe Empty Image"},
                },
                "2": {
                    "class_type": "SaveImage",
                    "inputs": save_inputs,
                    "_meta": {"title": "Probe Save Image"},
                },
            },
            "2",
        )

    async def _ct_get_text(self, url, timeout=15):
        async with self._session_get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            text = await resp.text()
            return resp.status, resp.headers.get("Content-Type", ""), text

    async def _ct_get_json(self, url, timeout=15):
        async with self._session_get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise ComfyUIHTTPError(resp.status, text)
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                content_type = resp.headers.get("Content-Type", "")
                raise ValueError(f"non-JSON response ({content_type}): {text[:300]}") from e

    async def _ct_probe_http(self, base_url):
        lines = []
        object_info = None
        ok_all = True

        for path, label in (
            ("/system_stats", "system_stats"),
            ("/features", "features"),
            ("/object_info/EmptyImage", "object_info EmptyImage"),
            ("/object_info/SaveImage", "object_info SaveImage"),
            ("/queue", "queue"),
        ):
            try:
                status, content_type, text = await self._ct_get_text(base_url + path)
                ok = status == 200
                ok_all = ok_all and ok
                detail = None
                if not ok:
                    detail = "HTTP <code>{}</code> <code>{}</code>".format(
                        status,
                        utils.escape_html(content_type.split(";")[0] or "-"),
                    )
                lines.append(self._ct_line(ok, label, detail))
                if path.startswith("/object_info/") and status == 200:
                    try:
                        data = json.loads(text)
                        object_info = object_info or {}
                        object_info.update(data)
                    except json.JSONDecodeError:
                        ok_all = False
                        lines.append(
                            self._ct_line(
                                False,
                                label,
                                self._ct_error_detail(f"non-JSON: {text}", 160),
                            )
                        )
            except Exception as e:
                ok_all = False
                lines.append(self._ct_line(False, label, self._ct_error_detail(e)))

        return ok_all, lines, object_info

    async def _ct_probe_ws(self, base_url):
        client_id = str(uuid.uuid4())
        try:
            async with self._session_ws_connect(
                self._ct_ws_url(base_url, client_id),
                timeout=10,
            ) as ws:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=3)
                except asyncio.TimeoutError:
                    return True, "connected, no initial message"
                if msg.type == aiohttp.WSMsgType.TEXT:
                    return True, f"connected, first event: {self._ct_preview(msg.data, 220)}"
                return True, f"connected, first frame type: {msg.type.name}"
        except Exception as e:
            return False, str(e)

    async def _ct_queue_prompt(self, base_url, workflow, client_id):
        async with self._session_post(
            f"{base_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["queue_prompt"]),
        ) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise ComfyUIHTTPError(resp.status, text)
            data = json.loads(text)
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise ValueError(f"No prompt_id: {self._ct_preview(data)}")
            return str(prompt_id)

    async def _ct_history_once(self, base_url, prompt_id):
        data = await self._ct_get_json(f"{base_url}/history/{prompt_id}")
        return data.get(prompt_id) if isinstance(data, dict) else None

    async def _ct_wait_result(self, base_url, prompt_id, output_node, ws, timeout):
        start = time.time()
        events = []
        last_history_check = 0.0
        last_history_error = None
        execution_done = False

        while time.time() - start < timeout:
            if ws and not ws.closed:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=1)
                except asyncio.TimeoutError:
                    msg = None
                if msg and msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        data = {}
                    event_type = data.get("type", "unknown")
                    if event_type not in events:
                        events.append(event_type)
                    payload = data.get("data", {})
                    if isinstance(payload, dict) and payload.get("prompt_id") == prompt_id:
                        if event_type == "execution_error":
                            raise ValueError(self._ct_preview(payload, 1200))
                        if event_type in ("execution_success", "execution_complete"):
                            execution_done = True
                        if event_type == "executing" and payload.get("node") is None:
                            execution_done = True
                elif msg and msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    ws = None
            else:
                await asyncio.sleep(1)

            now = time.time()
            if execution_done or now - last_history_check >= 2:
                last_history_check = now
                try:
                    history = await self._ct_history_once(base_url, prompt_id)
                    last_history_error = None
                    if history and self._extract_image_info(history, output_node):
                        return history, events
                    if execution_done and history:
                        raise ValueError(f"No image in history: {self._ct_preview(history, 1200)}")
                except ValueError:
                    raise
                except Exception as e:
                    last_history_error = e
                    logger.debug("ComfyUI tunnel probe history failed: %s", e)

        if last_history_error:
            raise asyncio.TimeoutError(
                f"timeout waiting for prompt_id={prompt_id}; last history error: {last_history_error}"
            )
        raise asyncio.TimeoutError(f"timeout waiting for prompt_id={prompt_id}")

    async def _ct_retrieve_image(self, base_url, image_info):
        params = {
            "filename": image_info.get("filename", ""),
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        }
        async with self._session_get(
            f"{base_url}/view",
            params=params,
            timeout=self._retrieve_media_timeout(),
        ) as resp:
            data = await resp.read()
            if resp.status != 200:
                raise ComfyUIHTTPError(resp.status, repr(data[:500]))
            return data

    async def _ct_probe_generation(self, base_url, object_info):
        workflow, output_node = self._ct_build_empty_image_workflow(object_info)
        client_id = str(uuid.uuid4())
        ws = None
        ws_ok = False
        ws_note = ""

        try:
            ws = await self._session_ws_connect(
                self._ct_ws_url(base_url, client_id),
                timeout=10,
            )
            ws_ok = True
        except Exception as e:
            ws_note = str(e)

        try:
            prompt_id = await self._ct_queue_prompt(base_url, workflow, client_id)
            history, events = await self._ct_wait_result(
                base_url,
                prompt_id,
                output_node,
                ws,
                _CT_PROBE_TIMEOUT,
            )
            image_info = self._extract_image_info(history, output_node)
            if not image_info:
                raise ValueError(f"No image in history: {self._ct_preview(history, 1200)}")
            image_bytes = await self._ct_retrieve_image(base_url, image_info)
            return {
                "prompt_id": prompt_id,
                "ws_ok": ws_ok,
                "ws_note": ws_note,
                "events": events,
                "image_info": image_info,
                "image_bytes": image_bytes,
            }
        finally:
            if ws and not ws.closed:
                await ws.close()

    def _ct_format_report(self, base_url, lines, ok):
        details = "\n".join(lines) if lines else self.strings("ct_no_checks")
        return "\n".join([
            self.strings("ct_title"),
            self.strings("ct_status").format(self.strings("ct_ok" if ok else "ct_fail")),
            "",
            f"<blockquote expandable>{details}</blockquote>",
        ])

    async def _ct_run_probe(self, message, base_url):
        status = await self._safe_answer(
            message,
            self.strings("ct_checking"),
        )
        lines = []
        image_bytes = None
        ok_all = True

        try:
            http_ok, http_lines, object_info = await self._ct_probe_http(base_url)
            ok_all = ok_all and http_ok
            lines.extend(http_lines)

            ws_ok, ws_note = await self._ct_probe_ws(base_url)
            ok_all = ok_all and ws_ok
            lines.append(
                self._ct_line(
                    ws_ok,
                    "websocket",
                    None if ws_ok else self._ct_error_detail(ws_note),
                )
            )

            try:
                result = await self._ct_probe_generation(base_url, object_info)
                image_bytes = result["image_bytes"]
                lines.append(
                    self._ct_line(
                        result["ws_ok"],
                        "generation",
                        None if result["ws_ok"] else self._ct_error_detail(result["ws_note"] or "websocket unavailable"),
                    )
                )
                lines.append(self._ct_line(True, "history/view"))
                ok_all = ok_all and result["ws_ok"]
            except Exception as e:
                ok_all = False
                logger.exception(e)
                lines.append(
                    self._ct_line(
                        False,
                        "minimal generation",
                        self._ct_error_detail(e),
                    )
                )

            report = self._ct_format_report(base_url, lines, ok_all)

            if image_bytes:
                file_obj = io.BytesIO(image_bytes)
                file_obj.name = "comfy_tunnel_probe.png"
                try:
                    sent = await self.client.send_file(
                        utils.get_chat_id(message),
                        file_obj,
                        caption=report,
                        reply_to=getattr(message, "reply_to_msg_id", None) or message.id,
                    )
                    if status and status.id != getattr(sent, "id", None):
                        try:
                            await status.delete()
                        except Exception as e:
                            logger.debug("Failed to delete probe status message: %s", e)
                    return sent
                except Exception as e:
                    logger.exception(e)
                    report = "\n\n".join([
                        report,
                        self.strings("ct_upload_failed").format(utils.escape_html(str(e))),
                    ])
                finally:
                    file_obj.close()

            return await self._safe_answer(status or message, report)
        except Exception as e:
            logger.exception(e)
            lines.append(
                self._ct_line(False, "probe", self._ct_error_detail(e))
            )
            return await self._safe_answer(
                status or message,
                self._ct_format_report(base_url, lines, False),
            )

    def _ws_update_interval(self):
        try:
            value = int(self.config["ws_update_interval"])
        except Exception:
            return 2
        if value == 0:
            return 0
        return max(1, min(5, value))

    @staticmethod
    def _parse_object_info_list(info, class_type, field):
        if not info:
            return []
        raw = (
            info
            .get(class_type, {})
            .get("input", {})
            .get("required", {})
            .get(field, [])
        )
        if isinstance(raw, list) and raw and isinstance(raw[0], list):
            return [x for x in raw[0] if isinstance(x, str)]
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, str)]
        return []

    _EMOJI_TO_TG_RE = re.compile(
        r'<emoji document_id=(\d+)>(.+?)</emoji>'
    )

    @staticmethod
    def _emoji_theme_char_key(char: str) -> str:
        return str(char or "").replace("\ufe0f", "")

    def _emoji_theme_name(self) -> str:
        settings = self._get_ult_settings()
        theme = str(settings.get("ui", {}).get("theme") or _EMOJI_THEME_DEFAULT).strip().lower()
        if theme not in _EMOJI_THEME_REPLACEMENTS:
            return _EMOJI_THEME_DEFAULT
        return theme

    def _apply_emoji_theme(self, text: str) -> str:
        theme = self._emoji_theme_name()
        replacements = _EMOJI_THEME_REPLACEMENTS.get(theme)
        id_fallbacks = _EMOJI_THEME_ID_FALLBACKS.get(theme, {})
        error_id_fallbacks = _EMOJI_THEME_ERROR_ID_FALLBACKS.get(theme, {})
        if not replacements and not id_fallbacks and not error_id_fallbacks:
            return text

        def replace(match):
            tag = match.group("tag")
            old_id = match.group("id")
            old_char = match.group("char")
            char_key = self._emoji_theme_char_key(old_char)
            new_emoji = replacements.get((old_id, char_key))
            if not new_emoji and old_id == "5121063440311386962":
                new_emoji = error_id_fallbacks.get(char_key) or error_id_fallbacks.get("*")
            if not new_emoji:
                new_emoji = id_fallbacks.get(old_id)
            if not new_emoji:
                return match.group(0)
            new_id, new_char = new_emoji
            if tag == "emoji":
                return f"<emoji document_id={new_id}>{new_char}</emoji>"
            return f'<tg-emoji emoji-id="{new_id}">{new_char}</tg-emoji>'

        return _EMOJI_THEME_TAG_RE.sub(replace, str(text or ""))

    def _to_inline_emoji(self, text: str) -> str:
        text = self._apply_emoji_theme(text)
        return self._EMOJI_TO_TG_RE.sub(
            r'<tg-emoji emoji-id="\1">\2</tg-emoji>', text
        )

    @staticmethod
    def _strip_leading_custom_emoji(text: str) -> str:
        return re.sub(
            r'^\s*<(?:tg-emoji\s+emoji-id="[^"]+"|emoji\s+document_id=\d+)>.*?</(?:tg-emoji|emoji)>\s*',
            "",
            str(text or ""),
            count=1,
            flags=re.DOTALL,
        )

    def _format_generation_preflight_inline(self, text: str) -> str:
        body = self._strip_leading_custom_emoji(self._to_inline_emoji(text))
        return f"{_PREFLIGHT_EYES_INLINE} {body}"

    async def _measure_userbot_ping_ms(self):
        start = time.perf_counter()
        await self.client.get_me()
        return max(0, int((time.perf_counter() - start) * 1000))

    def _format_ci_ping_quote(self, ping_ms):
        try:
            ping_ms = int(ping_ms)
        except (TypeError, ValueError):
            return ""
        return f"<blockquote>{self.strings('info_userbot_ping').format(ping_ms)}</blockquote>"

    def _format_ci_loading_text(self, ping_ms=None):
        text = self._format_generation_preflight_inline(self.strings("ci_loading"))
        ping_quote = self._format_ci_ping_quote(ping_ms)
        if ping_quote:
            text = f"{text}\n{ping_quote}"
        return text

    async def _ci_ping_loop(self, target, ping_state, stop_event):
        while not stop_event.is_set() and not self._unloading:
            try:
                ping_ms = await self._measure_userbot_ping_ms()
                ping_state["value"] = ping_ms
                text = self._format_ci_loading_text(ping_ms)
                if isinstance(target, Message):
                    await utils.answer(target, self._apply_emoji_theme(text))
                elif hasattr(target, "edit") and callable(target.edit):
                    await target.edit(text=self._apply_emoji_theme(text))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("Failed to update ci ping: %s", e)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    @staticmethod
    def _plain_text(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text)

    async def _safe_close_form(self, call: InlineCall):
        try:
            await call.delete()
        except Exception as e:
            logger.debug("Failed to close inline form: %s", e)

    def _classify_error(self, error):
        error_text = str(error).lower()

        if isinstance(error, asyncio.TimeoutError):
            return "timeout", {}

        if isinstance(error, asyncio.CancelledError):
            return "cancelled", {}

        if isinstance(error, UserFacingError):
            return error.key, error.kwargs

        if isinstance(error, (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, ConnectionRefusedError, OSError)):
            return "connection", {}

        if isinstance(error, aiohttp.ClientError):
            return "connection", {}

        if isinstance(error, ValueError):
            raw = str(error)

            if isinstance(error, ComfyUIExecutionError):
                try:
                    error_json = json.loads(raw)
                    return self._classify_comfyui_json_error(error_json)
                except json.JSONDecodeError:
                    pass
                return "execution", {"message": raw}

            if isinstance(error, ComfyUIHTTPError):
                if error.temporary:
                    return "server_unavailable", {}
                try:
                    error_json = json.loads(error.body)
                    return self._classify_comfyui_json_error(error_json)
                except json.JSONDecodeError:
                    pass

            if any(code in raw for code in ("HTTP 502", "HTTP 503", "HTTP 504")):
                return "server_unavailable", {}

            for prefix in ("HTTP 400: ", "HTTP 500: ", "HTTP 422: ", "HTTP 403: ", "HTTP 404: "):
                if raw.startswith(prefix):
                    json_part = raw[len(prefix):]
                    try:
                        error_json = json.loads(json_part)
                        return self._classify_comfyui_json_error(error_json)
                    except json.JSONDecodeError:
                        pass

            if "vae" in error_text and "source" in error_text:
                return "vae_not_found", {}
            if "no prompt_id" in error_text:
                return "prompt_queue", {}
            if self._plain_text(self.strings("unavailable")).lower() in error_text:
                return "unavailable", {}
            if "'nonetype' object has no attribute" in error_text:
                return "none_input", {}
            if "execution error" in error_text:
                return "execution", {}
            if "upload failed" in error_text:
                return "upload_failed", {}
            if "failed to retrieve" in error_text:
                return "retrieve_failed", {}
            if "failed to process image" in error_text:
                return "image_invalid", {}
            if "img2img unsupported" in error_text:
                return "img2img_unsupported", {}
            if "telegram send failed" in error_text:
                return "send_failed", {}
            if self._plain_text(self.strings("no_images")).lower() in error_text:
                return "no_images", {}
            if self._plain_text(self.strings("unexpected_comfy_response")).lower() in error_text:
                return "server_unavailable", {}

            return "generic", {}

        return "generic", {}

    def _classify_comfyui_json_error(self, error_json):
        if not isinstance(error_json, dict):
            return "execution", {}
        error_info = error_json.get("error", {})
        if not isinstance(error_info, dict):
            return "execution", {}
        error_type = error_info.get("type", "")
        error_message = error_info.get("message", "")
        extra_info = error_info.get("extra_info", {})
        if not isinstance(extra_info, dict):
            extra_info = {}

        if error_type == "missing_node_type":
            node_title = extra_info.get("node_title", "")
            node_type = extra_info.get("node_type", node_title)
            return "node_missing", {"node": node_title or node_type or "Unknown"}

        error_msg_lower = error_message.lower()

        if "out of memory" in error_msg_lower or "cuda" in error_msg_lower or "vram" in error_msg_lower:
            return "vram", {}

        if ("checkpoint" in error_msg_lower or "model" in error_msg_lower) and "not found" in error_msg_lower:
            model_name = extra_info.get("model_name", "")
            return "model_not_found", {"model": model_name}

        if error_type == "prompt_outputs_failed_validation":
            classified = self._classify_comfyui_validation_error(error_json)
            if classified:
                return classified
            return "workflow_invalid", {}

        details = {
            "message": error_message,
            "type": error_type,
            "node": extra_info.get("node_title") or extra_info.get("node_type") or extra_info.get("node_id"),
            "node_id": extra_info.get("node_id"),
            "node_type": extra_info.get("node_type"),
        }
        return "execution", {k: v for k, v in details.items() if v}

    @staticmethod
    def _extract_comfyui_allowed_values(input_config):
        if isinstance(input_config, list) and input_config and isinstance(input_config[0], list):
            return [str(item) for item in input_config[0] if item is not None]
        return []

    @classmethod
    def _classify_comfyui_validation_error(cls, error_json):
        node_errors = error_json.get("node_errors", {})
        if not isinstance(node_errors, dict):
            return None
        model_fields = {
            "ckpt_name",
            "unet_name",
            "diffusion_model",
            "diffusion_model_name",
            "model",
            "model_name",
        }
        for node_error in node_errors.values():
            if not isinstance(node_error, dict):
                continue
            errors = node_error.get("errors", [])
            if not isinstance(errors, list):
                continue
            for item in errors:
                if not isinstance(item, dict) or item.get("type") != "value_not_in_list":
                    continue
                extra = item.get("extra_info", {})
                if not isinstance(extra, dict):
                    extra = {}
                input_name = str(extra.get("input_name") or "").strip()
                input_name_l = input_name.lower()
                is_model_field = (
                    input_name_l in model_fields
                    or "model" in input_name_l
                    or "ckpt" in input_name_l
                    or "checkpoint" in input_name_l
                )
                if not is_model_field:
                    continue
                received = extra.get("received_value")
                if received is None:
                    details = str(item.get("details") or "")
                    match = re.search(r":\s*'([^']+)'", details)
                    received = match.group(1) if match else "unknown"
                available = cls._extract_comfyui_allowed_values(extra.get("input_config"))
                return (
                    "model_value_not_in_list",
                    {
                        "model": str(received),
                        "available": available,
                    },
                )
        lines = []
        for node_id, node_error in node_errors.items():
            if not isinstance(node_error, dict):
                continue
            class_type = (
                node_error.get("class_type")
                or node_error.get("node_type")
                or node_error.get("type")
                or "Unknown"
            )
            title = node_error.get("node_title") or node_error.get("title")
            node_label = f"{node_id}: {title or class_type}"
            errors = node_error.get("errors", [])
            if not isinstance(errors, list):
                errors = []
            if not errors:
                lines.append(f"<b>{utils.escape_html(str(node_label))}</b>: validation failed")
                continue
            for item in errors[:3]:
                if not isinstance(item, dict):
                    continue
                extra = item.get("extra_info", {})
                if not isinstance(extra, dict):
                    extra = {}
                bits = []
                input_name = extra.get("input_name")
                if input_name:
                    bits.append(f"input <code>{utils.escape_html(str(input_name))}</code>")
                err_type = item.get("type")
                if err_type:
                    bits.append(f"type <code>{utils.escape_html(str(err_type))}</code>")
                message = item.get("message") or item.get("details") or "validation failed"
                received = extra.get("received_value")
                line = f"<b>{utils.escape_html(str(node_label))}</b>: {utils.escape_html(str(message))}"
                if bits:
                    line += " (" + ", ".join(bits) + ")"
                if received is not None:
                    line += f"; value <code>{utils.escape_html(str(received))}</code>"
                lines.append(line)
                if len(lines) >= 6:
                    break
            if len(lines) >= 6:
                break
        if lines:
            return "workflow_invalid_details", {"details": "\n".join(lines)}
        return None

    def _get_error_message(self, error_type, details, is_inline=False):
        error_map = {
            "timeout": "timeout",
            "unavailable": "easter_dream_unavailable",
            "connection": "err_connection",
            "server_unavailable": "err_server_unavailable",
            "node_missing": "err_node_missing",
            "model_not_found": "err_model_not_found",
            "model_value_not_in_list": "err_model_value_not_in_list",
            "vram": "err_vram",
            "image_invalid": "err_image_invalid",
            "img2img_unsupported": "err_img2img_unsupported",
            "upload_failed": "err_upload_failed",
            "retrieve_failed": "err_retrieve_failed",
            "send_failed": "err_send_failed",
            "workflow_invalid": "err_workflow_invalid",
            "workflow_invalid_details": "err_workflow_invalid_details",
            "vae_not_found": "err_vae_not_found",
            "prompt_queue": "err_prompt_queue",
            "execution": "err_execution",
            "none_input": "err_none_input",
            "input_too_large": "img_too_large",
            "ctools_workflow_no_input": "ctools_workflow_no_input",
            "ctools_workflow_no_output": "ctools_workflow_no_output",
            "no_images": "no_images",
            "output_too_large": "output_too_large",
            "civitai_error": "civitai_error",
            "civitai_no_prompt": "civitai_no_prompt",
            "archive_access_lost": "ult_chat_access_lost",
            "generic": "err_generic",
        }

        string_key = error_map.get(error_type, "err_generic")
        text = self.strings(string_key)

        if error_type == "node_missing" and details.get("node"):
            text = text.format(utils.escape_html(details["node"]))
        elif error_type == "model_value_not_in_list":
            available = details.get("available") or []
            available_text = "\n".join(
                f"- <code>{utils.escape_html(self._format_model_name(model, max_length=None))}</code>"
                for model in available
            )
            if not available_text:
                available_text = self.strings("not_set")
            text = text.format(
                utils.escape_html(self._format_model_name(details.get("model") or "unknown", max_length=None)),
                available_text,
            )
        elif error_type == "model_not_found" and details.get("model"):
            text = text.format(utils.escape_html(self._format_model_name(details["model"], max_length=None)))
        elif error_type == "model_not_found":
            text = text.format("unknown")
        elif error_type == "workflow_invalid_details":
            text = text.format(details.get("details") or self.strings("err_workflow_invalid"))
        elif error_type == "node_missing":
            text = text.format("Unknown")
        elif error_type == "execution" and details.get("message"):
            detail = str(details["message"]).strip()
            node_bits = []
            if details.get("type"):
                node_bits.append(f"type={details['type']}")
            if details.get("node"):
                node_bits.append(f"node={details['node']}")
            if node_bits:
                detail = f"{detail} ({', '.join(map(str, node_bits))})"
            if len(detail) > 700:
                detail = detail[:697] + "..."
            text = f"{text}\n\n<code>{utils.escape_html(detail)}</code>"
        elif error_type == "input_too_large":
            text = text.format(details.get("max_mb", self.config["max_input_mb"]))
        elif error_type == "ctools_workflow_no_input":
            text = text.format(utils.escape_html(details.get("kind") or "media"))
        elif error_type == "output_too_large":
            text = text.format(details.get("max_mb", self.config["max_output_mb"]))

        if is_inline:
            text = self._to_inline_emoji(text)

        return text

    async def _safe_answer(self, message, text):
        text = self._apply_emoji_theme(text)
        try:
            return await utils.answer(message, text)
        except Exception as e:
            if "MessageIdInvalid" in type(e).__name__ or "MessageNotModified" in type(e).__name__:
                try:
                    return await self.client.send_message(
                        message.chat_id, text, reply_to=message.id
                    )
                except Exception:
                    pass
            else:
                logger.debug("Failed to answer message: %s", e)

    @staticmethod
    def _message_sent_as_channel(message):
        from_id = getattr(message, "from_id", None)
        if isinstance(from_id, PeerChannel) or type(from_id).__name__ == "PeerChannel":
            return True
        sender = getattr(message, "sender", None)
        return bool(getattr(sender, "broadcast", False))

    async def _create_generation_preflight(self, message, string_key="preflight_preparing"):
        text = self.strings(string_key)
        inline_text = self._format_generation_preflight_inline(text)
        if self._message_sent_as_channel(message):
            return await self._safe_answer(message, text)
        try:
            if not self._self_has_premium:
                form = await self.inline.form(message=message, text=inline_text)
            else:
                # Keep the premium dummy step, but make the dummy itself useful if edit stalls.
                form = await self.inline.form(message=message, text=inline_text)
                try:
                    await form.edit(text=inline_text)
                except Exception as e:
                    logger.debug("Premium preflight dummy edit failed: %s", e)
            if form:
                return form
        except Exception as e:
            logger.debug("Failed to create inline generation preflight: %s", e)
        return await self._safe_answer(message, text)

    async def _update_generation_preflight(self, target, string_key=None, text=None):
        if not target:
            return None
        text = text if text is not None else self.strings(string_key)
        try:
            if isinstance(target, Message):
                return await self._safe_answer(target, text) or target
            await target.edit(text=self._format_generation_preflight_inline(text))
            return target
        except Exception as e:
            logger.debug("Failed to update generation preflight: %s", e)
            return target

    def _split_html_text(self, text, limit=3900):
        try:
            parsed_text, entities = self.client.parse_mode.parse(text)
            return list(utils.smart_split(parsed_text, entities, limit))
        except Exception as e:
            logger.debug("HTML smart split failed: %s", e)
            return [text[i : i + limit] for i in range(0, len(text), limit)]

    @staticmethod
    def _safe_topic(message):
        try:
            return utils.get_topic(message)
        except AttributeError:
            return None

    async def _smart_answer(self, message, text):
        text = self._apply_emoji_theme(text)
        if len(text) < 3900:
            return await utils.answer(message, text)
        chunks = self._split_html_text(text)
        if not chunks:
            return await utils.answer(message, text)
        first = await utils.answer(message, chunks[0])
        chat_id = utils.get_chat_id(first if isinstance(first, Message) else message)
        reply_to = self._safe_topic(message) or getattr(message, "reply_to_msg_id", None)
        for chunk in chunks[1:]:
            await self.client.send_message(chat_id, chunk, reply_to=reply_to)
        return first

    async def _handle_gen_error(self, target, error):
        error_type, details = self._classify_error(error)
        log_error = self._plain_text(str(error))
        if error_type in ("server_unavailable", "unavailable", "connection", "timeout"):
            logger.warning("Generation temporary error: %s: %s", type(error).__name__, log_error)
        else:
            logger.error("Generation error: %s: %s", type(error).__name__, log_error)
        if isinstance(error, (MemoryError, OSError)):
            logger.critical("CRITICAL SYSTEM ERROR: %s: %s", type(error).__name__, log_error)
        if error_type not in ("server_unavailable", "unavailable", "connection", "timeout", "execution") and not isinstance(error, (asyncio.TimeoutError, asyncio.CancelledError)):
            logger.exception(error)

        is_inline = isinstance(target, InlineCall)
        text = self._get_error_message(error_type, details, is_inline=is_inline)

        try:
            if isinstance(target, InlineCall):
                await target.edit(text=text)
            elif self._self_has_premium:
                rendered = await self._render_inline(target, self._to_inline_emoji(text))
                if not rendered:
                    await self._safe_answer(target, text)
            else:
                await self._safe_answer(target, text)
        except Exception as e:
            logger.debug("Failed to send error message: %s", e)

    def _trace_input(self, workflow, node_id, input_name):
        node = workflow.get(node_id)
        if not node:
            return None
        val = node.get("inputs", {}).get(input_name)
        if isinstance(val, list) and len(val) == 2:
            return str(val[0])
        return None


    def _find_prompt_nodes(self, workflow):
        positive_nid = None
        negative_nid = None

        text_nodes = {}
        for nid, node in workflow.items():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type", "")
            ct_lower = ct.lower()
            title = node.get("_meta", {}).get("title", "").lower()
            inputs = node.get("inputs", {})
            is_text_node = (
                ct_lower in ("cliptextencode", "impactwildcardprocessor", "wildcardencode")
                or "textencode" in ct_lower
                or ct_lower in ("primitivestringmultiline", "ttn text", "cr text")
                or ("text" in ct_lower and any(key in inputs for key in ("text", "value", "string", "prompt")))
                or ("wildcard" in ct_lower and any(key in inputs for key in ("wildcard_text", "text", "prompt")))
                or ("prompt" in ct_lower and any(key in inputs for key in ("prompt", "text", "positive", "negative")))
                or (("positive" in title or "negative" in title) and any(isinstance(inputs.get(key), str) for key in ("wildcard_text", "text", "prompt", "text_g", "text_l", "positive", "negative", "value", "string")))
            )
            if is_text_node:
                dual_fields = [field for field in ("text_g", "text_l") if field in inputs]
                flux_fields = [field for field in ("clip_l", "t5xxl") if field in inputs]
                field = (
                    "wildcard_text" if "wildcard_text" in inputs
                    else "text" if "text" in inputs
                    else "prompt" if "prompt" in inputs
                    else dual_fields if dual_fields
                    else flux_fields if flux_fields
                    else "clip_l" if "clip_l" in inputs
                    else "t5xxl" if "t5xxl" in inputs
                    else "positive" if "positive" in inputs
                    else "negative" if "negative" in inputs
                    else "value" if "value" in inputs
                    else "string" if "string" in inputs
                    else None
                )
                if field:
                    text_nodes[nid] = {"field": field, "title": title, "ct": ct, "inputs": inputs}

        def find_text_source(start_nid):
            traced = str(start_nid)
            seen = set()
            for _ in range(12):
                if not traced or traced in seen:
                    break
                seen.add(traced)
                if traced in text_nodes:
                    return traced
                node = workflow.get(traced)
                if not isinstance(node, dict):
                    break
                next_id = None
                for value in node.get("inputs", {}).values():
                    if self._is_workflow_link(value):
                        next_id = str(value[0])
                        break
                if not next_id:
                    break
                traced = next_id
            return None

        for nid, node in workflow.items():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type", "")
            if ct != "SetNode":
                continue
            inputs = node.get("inputs", {})
            title = node.get("_meta", {}).get("title", "").lower()
            if "CONDITIONING" not in inputs or not self._is_workflow_link(inputs["CONDITIONING"]):
                continue
            text_source = find_text_source(inputs["CONDITIONING"][0])
            if not text_source:
                continue
            if "positive" in title and not positive_nid:
                positive_nid = text_source
            if "negative" in title and not negative_nid:
                negative_nid = text_source

        for nid, info in text_nodes.items():
            if "positive" in info["title"] and not positive_nid:
                positive_nid = nid
            if "negative" in info["title"] and not negative_nid:
                negative_nid = nid

        if positive_nid and negative_nid:
            return positive_nid, text_nodes[positive_nid]["field"], negative_nid, text_nodes[negative_nid]["field"]

        conditioning_consumers = {"CLIPTextEncode", "ImpactWildcardProcessor", "WildcardEncode"} | {
            info["ct"] for info in text_nodes.values()
        }
        negative_feeders = set()
        positive_feeders = set()

        for nid, node in workflow.items():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type", "")
            inputs = node.get("inputs", {})
            if ct == "ConditioningZeroOut":
                src = self._trace_input(workflow, nid, "conditioning")
                if src:
                    traced = src
                    for _ in range(10):
                        if not traced or traced not in workflow:
                            break
                        if workflow[traced].get("class_type", "") in conditioning_consumers:
                            negative_feeders.add(traced)
                            break
                        found_next = False
                        for iv in workflow[traced].get("inputs", {}).values():
                            if isinstance(iv, list) and len(iv) == 2:
                                traced = str(iv[0])
                                found_next = True
                                break
                        if not found_next:
                            break

            if ct in ("CFGGuider", "KSampler", "KSamplerAdvanced", "SamplerCustom") or "positive" in inputs or "negative" in inputs:
                role_by_input = {
                    "positive": "positive",
                    "negative": "negative",
                    "cond1": "positive",
                    "cond2": "negative",
                    "conditioning": "positive",
                }
                for input_key, role in role_by_input.items():
                    src = self._trace_input(workflow, nid, input_key)
                    if src:
                        traced = src
                        for _ in range(10):
                            if not traced or traced not in workflow:
                                break
                            if workflow[traced].get("class_type", "") in conditioning_consumers:
                                if role == "positive":
                                    positive_feeders.add(traced)
                                else:
                                    negative_feeders.add(traced)
                                break
                            found_next = False
                            for iv in workflow[traced].get("inputs", {}).values():
                                if isinstance(iv, list) and len(iv) == 2:
                                    traced = str(iv[0])
                                    found_next = True
                                    break
                            if not found_next:
                                break

        def ordered_node_ids(node_ids):
            def sort_key(item):
                text = str(item)
                parts = text.split(":")
                if all(part.isdigit() for part in parts):
                    return (0, tuple(int(part) for part in parts))
                return (1, text)

            return sorted(node_ids, key=sort_key)

        for nid in ordered_node_ids(positive_feeders):
            if nid in text_nodes and not positive_nid:
                positive_nid = nid
        for nid in ordered_node_ids(negative_feeders):
            if nid in text_nodes and nid != positive_nid and not negative_nid:
                negative_nid = nid

        if not positive_nid and not negative_nid and len(text_nodes) == 1:
            positive_nid = next(iter(text_nodes))

        if not positive_nid and not negative_nid and text_nodes:
            remaining = [nid for nid in text_nodes if nid not in negative_feeders]
            if not remaining:
                remaining = list(text_nodes.keys())
            best = None
            for nid in remaining:
                fields = text_nodes[nid]["field"]
                if isinstance(fields, str):
                    fields = [fields]
                txt = next((text_nodes[nid]["inputs"].get(field, "") for field in fields if field in text_nodes[nid]["inputs"]), "")
                if isinstance(txt, str) and txt.strip():
                    best = nid
                    break
            if best:
                positive_nid = best

        if not negative_nid and text_nodes:
            for nid in text_nodes:
                if nid != positive_nid:
                    fields = text_nodes[nid]["field"]
                    if isinstance(fields, str):
                        fields = [fields]
                    txt = next((text_nodes[nid]["inputs"].get(field, "") for field in fields if field in text_nodes[nid]["inputs"]), "")
                    if isinstance(txt, str) and not txt.strip():
                        negative_nid = nid
                        break

        pos_field = text_nodes[positive_nid]["field"] if positive_nid and positive_nid in text_nodes else None
        neg_field = text_nodes[negative_nid]["field"] if negative_nid and negative_nid in text_nodes else None
        if positive_nid and pos_field:
            if isinstance(pos_field, list):
                resolved_fields = []
                resolved_node_id = None
                for field in pos_field:
                    resolved = self._resolve_workflow_input_mapping(
                        workflow,
                        positive_nid,
                        field,
                        ("wildcard_text", "text", "prompt", "clip_l", "t5xxl", "value", "string"),
                    )
                    if resolved_node_id is None:
                        resolved_node_id = resolved["node_id"]
                    if resolved["node_id"] != resolved_node_id:
                        resolved_fields = [resolved["field"]]
                        resolved_node_id = resolved["node_id"]
                        break
                    resolved_fields.append(resolved["field"])
                positive_nid = resolved_node_id
                pos_field = resolved_fields
            else:
                resolved = self._resolve_workflow_input_mapping(
                    workflow,
                    positive_nid,
                    pos_field,
                    ("wildcard_text", "text", "prompt", "clip_l", "t5xxl", "value", "string"),
                )
                positive_nid = resolved["node_id"]
                pos_field = resolved["field"]
        if negative_nid and neg_field:
            if isinstance(neg_field, list):
                resolved_fields = []
                resolved_node_id = None
                for field in neg_field:
                    resolved = self._resolve_workflow_input_mapping(
                        workflow,
                        negative_nid,
                        field,
                        ("wildcard_text", "text", "prompt", "clip_l", "t5xxl", "value", "string"),
                    )
                    if resolved_node_id is None:
                        resolved_node_id = resolved["node_id"]
                    if resolved["node_id"] != resolved_node_id:
                        resolved_fields = [resolved["field"]]
                        resolved_node_id = resolved["node_id"]
                        break
                    resolved_fields.append(resolved["field"])
                negative_nid = resolved_node_id
                neg_field = resolved_fields
            else:
                resolved = self._resolve_workflow_input_mapping(
                    workflow,
                    negative_nid,
                    neg_field,
                    ("wildcard_text", "text", "prompt", "clip_l", "t5xxl", "value", "string"),
                )
                negative_nid = resolved["node_id"]
                neg_field = resolved["field"]
        return positive_nid, pos_field, negative_nid, neg_field

    @staticmethod
    def _is_workflow_link(value):
        return isinstance(value, list) and len(value) == 2 and isinstance(value[0], (str, int))

    @classmethod
    def _extract_comfy_types(cls, value):
        if isinstance(value, str):
            return {value.upper()}
        if isinstance(value, (list, tuple)):
            result = set()
            for item in value:
                result.update(cls._extract_comfy_types(item))
            return result
        return set()

    @classmethod
    def _extract_required_input_types(cls, input_spec):
        if isinstance(input_spec, str):
            return {input_spec.upper()}
        if isinstance(input_spec, (list, tuple)) and input_spec:
            return cls._extract_comfy_types(input_spec[0])
        return set()

    def _get_node_output_types(self, workflow, object_info, node_id, output_index=0):
        node = workflow.get(str(node_id))
        if not isinstance(node, dict):
            return set()
        class_type = node.get("class_type", "")
        node_info = object_info.get(class_type, {}) if isinstance(object_info, dict) else {}
        outputs = node_info.get("output", [])
        if isinstance(outputs, (list, tuple)) and len(outputs) > output_index:
            output_types = self._extract_comfy_types(outputs[output_index])
            if output_types:
                return output_types
        if class_type == "CheckpointLoaderSimple":
            return ({"MODEL"}, {"CLIP"}, {"VAE"})[output_index] if output_index in (0, 1, 2) else set()
        if class_type == "UNETLoader":
            return {"MODEL"}
        if class_type == "CLIPLoader":
            return {"CLIP"}
        if class_type == "VAELoader":
            return {"VAE"}
        if class_type == "PathchSageAttentionKJ":
            return {"MODEL"}
        if "Lora Loader" in class_type or "LoraLoader" in class_type:
            return ({"MODEL"}, {"CLIP"})[output_index] if output_index in (0, 1) else set()
        return set()

    def _get_global_input_types(self, workflow, object_info):
        global_types = set()
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type", ""))
            if class_type.lower() != "anything everywhere":
                continue
            for value in node.get("inputs", {}).values():
                if not self._is_workflow_link(value):
                    continue
                try:
                    output_index = int(value[1])
                except (TypeError, ValueError):
                    output_index = 0
                global_types.update(
                    self._get_node_output_types(workflow, object_info, value[0], output_index)
                )
        return global_types

    def _get_global_input_links(self, workflow, object_info):
        global_links = {}
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type", ""))
            if class_type.lower() != "anything everywhere":
                continue
            for value in node.get("inputs", {}).values():
                if not self._is_workflow_link(value):
                    continue
                try:
                    output_index = int(value[1])
                except (TypeError, ValueError):
                    output_index = 0
                link = [str(value[0]), output_index]
                for output_type in self._get_node_output_types(
                    workflow,
                    object_info,
                    value[0],
                    output_index,
                ):
                    global_links.setdefault(output_type, link)
        return global_links

    def _global_input_covers_required(self, input_name, input_spec, global_types):
        if not global_types:
            return False
        known_names = {
            "clip": {"CLIP"},
            "vae": {"VAE"},
            "model": {"MODEL"},
        }
        input_types = self._extract_required_input_types(input_spec)
        fallback_types = known_names.get(str(input_name).lower(), set())
        return bool((input_types | fallback_types) & global_types)

    def _global_link_for_required(self, input_name, input_spec, global_links):
        if not global_links:
            return None
        known_names = {
            "clip": {"CLIP"},
            "vae": {"VAE"},
            "model": {"MODEL"},
        }
        input_types = self._extract_required_input_types(input_spec)
        input_types.update(known_names.get(str(input_name).lower(), set()))
        for input_type in input_types:
            link = global_links.get(input_type)
            if link:
                return list(link)
        return None

    @staticmethod
    def _is_ignored_missing_required_input(class_type, input_name):
        return (
            str(class_type) == "ToDetailerPipe"
            and str(input_name) == "bbox_detector"
        )

    async def _materialize_global_inputs(self, workflow):
        object_info = await self._get_all_object_info()
        if not isinstance(object_info, dict):
            return workflow
        global_links = self._get_global_input_links(workflow, object_info)
        if not global_links:
            return workflow
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type")
            if str(class_type).lower() == "anything everywhere":
                continue
            node_info = object_info.get(class_type, {})
            required_inputs = (
                node_info
                .get("input", {})
                .get("required", {})
            )
            if not isinstance(required_inputs, dict):
                continue
            inputs = node.setdefault("inputs", {})
            for input_name, input_spec in required_inputs.items():
                if input_name in inputs:
                    continue
                link = self._global_link_for_required(
                    input_name,
                    input_spec,
                    global_links,
                )
                if link:
                    inputs[input_name] = link
        return workflow

    def _resolve_workflow_input_mapping(self, workflow, node_id, field, preferred_fields=None):
        node_id = str(node_id)
        field = str(field)
        preferred_fields = tuple(preferred_fields or ())
        seen = set()

        for _ in range(8):
            key = (node_id, field)
            if key in seen:
                break
            seen.add(key)

            node = workflow.get(node_id)
            if not isinstance(node, dict):
                break
            inputs = node.get("inputs", {})
            if field not in inputs or not self._is_workflow_link(inputs[field]):
                break

            source_node_id = str(inputs[field][0])
            source_node = workflow.get(source_node_id)
            if not isinstance(source_node, dict):
                break
            source_inputs = source_node.get("inputs", {})
            candidates = preferred_fields + (field, "value")
            next_field = next((candidate for candidate in candidates if candidate in source_inputs), None)
            if not next_field:
                break

            node_id = source_node_id
            field = next_field

        return {"node_id": node_id, "field": field}

    @staticmethod
    def _set_get_node_name(node):
        meta = node.get("_meta", {}) if isinstance(node, dict) else {}
        widgets = meta.get("ui_widgets", [])
        if isinstance(widgets, list) and widgets and widgets[0] is not None:
            return str(widgets[0]).strip().lower()
        title = str(meta.get("title", "")).strip().lower()
        if title.startswith("set_") or title.startswith("get_"):
            return title[4:].strip()
        return title

    @staticmethod
    def _is_sampler_like_node(class_type, inputs):
        lowered = str(class_type).lower()
        sampler_fields = {"steps", "cfg", "denoise", "sampler_name", "scheduler", "seed", "noise_seed"}
        return "sampler" in lowered and any(field in inputs for field in sampler_fields)

    @staticmethod
    def _is_scheduler_like_node(class_type, inputs):
        lowered = str(class_type).lower()
        scheduler_fields = {"steps", "scheduler", "denoise"}
        return "scheduler" in lowered and any(field in inputs for field in scheduler_fields)

    @staticmethod
    def _is_model_loader_like_node(class_type, inputs):
        lowered = str(class_type).lower()
        if any(token in lowered for token in ("sam", "upscale", "vae", "clip", "lora")):
            return False
        if "frameinterpolation" in lowered or ("frame" in lowered and "interpolation" in lowered):
            return False
        if "backgroundremoval" in lowered or ("background" in lowered and "removal" in lowered):
            return False
        model_fields = {"ckpt_name", "unet_name", "diffusion_model_name", "model_name", "patch_name", "model_patch", "model_patch_name"}
        return (
            any(field in inputs for field in model_fields)
            and any(token in lowered for token in ("checkpoint", "ckpt", "unet", "diffusion", "model", "patch"))
        )

    @staticmethod
    def _is_api_image_node(class_type, inputs):
        lowered = str(class_type).lower()
        return (
            any(token in lowered for token in ("gemini", "nano", "openai", "gpt", "image2"))
            and "prompt" in inputs
            and any(field in inputs for field in ("model", "seed", "resolution", "aspect_ratio"))
        )

    @staticmethod
    def _is_size_like_node(class_type, title, inputs):
        lowered = f"{class_type} {title}".lower()
        return (
            "width" in inputs
            and "height" in inputs
            and any(token in lowered for token in ("latent", "size", "resolution", "aspect", "empty", "image"))
        )

    @staticmethod
    def _is_output_like_node(class_type, title, inputs):
        lowered = f"{class_type} {title}".lower()
        if not any(field in inputs for field in ("images", "image", "pixels", "video", "videos")):
            return False
        if "preview" in lowered:
            return False
        return any(token in lowered for token in ("save", "preview", "output", "viewer", "display"))

    @staticmethod
    def _is_video_output_node(class_type, title, inputs):
        lowered = f"{class_type} {title}".lower()
        if "vhs_videocombine" in lowered:
            return True
        if any(token in lowered for token in ("savevideo", "save video", "video combine", "videocombine")):
            return True
        if any(field in inputs for field in ("video", "videos", "frames")) and any(
            token in lowered
            for token in ("save", "output", "combine", "video")
        ):
            return True
        return False

    @staticmethod
    def _is_preview_output_node(class_type, title):
        lowered = f"{class_type} {title}".lower()
        return "preview" in lowered or "viewer" in lowered or "display" in lowered

    @staticmethod
    def _is_save_output_node(class_type, title):
        lowered = f"{class_type} {title}".lower()
        if "preview" in lowered:
            return False
        return any(token in lowered for token in ("saveimage", "save image", "image saver", "savevideo", "save video", "save", "output"))

    @staticmethod
    def _is_media_loader_node(class_type, title):
        lowered = f"{class_type} {title}".lower()
        return any(token in lowered for token in ("loadimage", "load image", "loadvideo", "load video", "image loader", "video loader"))

    @classmethod
    def _media_output_rank(cls, workflow, node_id, media_kind="image"):
        node = workflow.get(str(node_id), {}) if isinstance(workflow, dict) else {}
        class_type = str(node.get("class_type", ""))
        title = str(node.get("_meta", {}).get("title", ""))
        lowered = f"{class_type} {title}".lower()
        rank = 0
        if cls._is_preview_output_node(class_type, title):
            rank -= 200
        if cls._is_save_output_node(class_type, title):
            rank += 100
        if "final" in lowered:
            rank += 40
        if "output" in lowered:
            rank += 20
        if "input" in lowered or "original" in lowered:
            rank -= 40
        if media_kind == "video" and "video" in lowered:
            rank += 20

        seen = set()
        transform_count = 0
        loader_count = 0

        def walk(nid, depth=0):
            nonlocal transform_count, loader_count
            if depth > 16:
                return
            nid = str(nid)
            if nid in seen:
                return
            seen.add(nid)
            current = workflow.get(nid, {}) if isinstance(workflow, dict) else {}
            if not isinstance(current, dict):
                return
            ct = str(current.get("class_type", ""))
            tt = str(current.get("_meta", {}).get("title", ""))
            if cls._is_media_loader_node(ct, tt):
                loader_count += 1
            elif nid != str(node_id) and not cls._is_preview_output_node(ct, tt):
                transform_count += 1
            for value in current.get("inputs", {}).values():
                if isinstance(value, list) and len(value) == 2:
                    walk(value[0], depth + 1)

        walk(node_id)
        rank += min(transform_count, 6) * 10
        if loader_count and transform_count == 0:
            rank -= 120
        return rank

    @staticmethod
    def _video_output_rank(class_type, title):
        lowered = f"{class_type} {title}".lower()
        rank = 0
        if "final" in lowered:
            rank += 50
        if "audio" in lowered:
            rank += 10
        if any(token in lowered for token in ("save", "output")):
            rank += 10
        if any(token in lowered for token in ("preview", "lq", "low quality")):
            rank -= 20
        return rank

    @staticmethod
    def _is_input_image_node(class_type, title, inputs):
        lowered = f"{class_type} {title}".lower()
        if not any(field in inputs for field in ("image", "file", "path")):
            return False
        if any(token in lowered for token in ("save", "preview", "output", "combine")):
            return False
        return any(token in lowered for token in ("loadimage", "load image", "image loader", "imageloader", "k3nkimage"))

    @staticmethod
    def _is_image_only_mapping(mapping):
        if not isinstance(mapping, dict):
            return False
        output = (
            mapping.get("output")
            or mapping.get("output_regular")
            or mapping.get("output_upscaled")
            or mapping.get("output_video")
        )
        return (
            bool(output)
            and bool(mapping.get("input_image") or mapping.get("input_video") or mapping.get("latent_switch"))
            and not bool(mapping.get("positive"))
            and not bool(mapping.get("model"))
            and not any(mapping.get(key) for key in ("seed", "steps", "cfg", "denoise"))
        )

    def _is_image_only_workflow_data(self, wf_data):
        if not isinstance(wf_data, dict):
            return False
        mapping = wf_data.get("mapping") or self._parse_workflow(wf_data.get("workflow", {}))
        return self._is_image_only_mapping(mapping)

    def _workflow_requires_input_image(self, wf_data):
        return self._workflow_required_input_kind(wf_data) == "image"

    def _workflow_required_input_kind(self, wf_data):
        if not isinstance(wf_data, dict):
            return None
        mapping = wf_data.get("mapping") or self._parse_workflow(wf_data.get("workflow", {}))
        if not isinstance(mapping, dict):
            return None
        if mapping.get("latent_switch"):
            return None
        input_kind = mapping.get("input_kind")
        if input_kind == "video" and mapping.get("input_video"):
            return "video"
        if input_kind in ("image", "image_pair") and bool(mapping.get("input_image") or mapping.get("input_images")):
            return "image"
        return None

    def _parse_workflow(self, workflow):
        workflow = self._normalize_workflow_format(workflow)
        mapping = {
            "positive": None, "negative": None, "model": None, "seed": None,
            "width": None, "height": None, "output_upscaled": None,
            "output_regular": None, "output_video": None, "output_preview": None,
            "steps": None, "cfg": None, "denoise": None,
            "latent_switch": None, "vae_output_node": None, "sam_model": None,
            "vae": None, "input_image": None, "input_video": None, "scale_by": None,
            "sampler_name": None, "scheduler": None, "upscale_model_loader": None,
            "ultimate_upscale_node_id": None, "hires_fix_node_id": None,
            "output": None, "flux_guidance": None, "megapixels": None,
            "resolution": None, "frames": None, "fps": None,
            "output_kind": "image", "input_kind": "none",
            "megapixels_nodes": [], "model_nodes": [], "input_images": [],
        }
        if not isinstance(workflow, dict):
            return mapping

        pos_nid, pos_field, neg_nid, neg_field = self._find_prompt_nodes(workflow)
        if pos_nid and pos_field:
            mapping["positive"] = {"node_id": pos_nid, "field": pos_field}
        if neg_nid and neg_field:
            mapping["negative"] = {"node_id": neg_nid, "field": neg_field}

        for nid, node in workflow.items():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type", "")
            inputs = node.get("inputs", {})
            title = node.get("_meta", {}).get("title", "").lower()

            if ct == "CheckpointLoaderSimple" and "ckpt_name" in inputs:
                mapping.setdefault("model_nodes", [])
                mapping["model_nodes"].append({"node_id": nid, "field": "ckpt_name"})
                if not mapping["model"]:
                    mapping["model"] = {"node_id": nid, "field": "ckpt_name"}
                    mapping["vae_output_node"] = {"node_id": nid, "output_index": 2}
            if ct == "UNETLoader" and "unet_name" in inputs:
                mapping.setdefault("model_nodes", [])
                mapping["model_nodes"].append({"node_id": nid, "field": "unet_name"})
                if not mapping["model"]:
                    mapping["model"] = {"node_id": nid, "field": "unet_name"}
            if "diffusion_model" in inputs:
                resolved = self._resolve_workflow_input_mapping(workflow, nid, "diffusion_model", ("diffusion_model", "unet_name", "ckpt_name", "model_name", "value"))
                mapping.setdefault("model_nodes", [])
                if resolved not in mapping["model_nodes"]:
                    mapping["model_nodes"].append(resolved)
                if not mapping["model"]:
                    mapping["model"] = resolved
            if self._is_model_loader_like_node(ct, inputs):
                for model_field in ("ckpt_name", "unet_name", "diffusion_model_name", "model_name", "patch_name", "model_patch", "model_patch_name"):
                    if model_field not in inputs:
                        continue
                    resolved = self._resolve_workflow_input_mapping(
                        workflow,
                        nid,
                        model_field,
                        ("ckpt_name", "unet_name", "diffusion_model_name", "model_name", "patch_name", "model_patch", "model_patch_name", "value"),
                    )
                    mapping.setdefault("model_nodes", [])
                    if resolved not in mapping["model_nodes"]:
                        mapping["model_nodes"].append(resolved)
                    if not mapping["model"]:
                        mapping["model"] = resolved
                    break
            if self._is_api_image_node(ct, inputs):
                if not mapping["positive"]:
                    mapping["positive"] = self._resolve_workflow_input_mapping(
                        workflow,
                        nid,
                        "prompt",
                        ("prompt", "text", "value"),
                    )
                if "model" in inputs and not mapping["model"]:
                    mapping["model"] = {"node_id": nid, "field": "model"}
                    mapping.setdefault("model_nodes", [])
                    if mapping["model"] not in mapping["model_nodes"]:
                        mapping["model_nodes"].append(mapping["model"])
                if "seed" in inputs and not mapping["seed"]:
                    mapping["seed"] = self._resolve_workflow_input_mapping(
                        workflow,
                        nid,
                        "seed",
                        ("seed", "noise_seed", "value"),
                    )
                if "resolution" in inputs and not mapping["resolution"]:
                    mapping["resolution"] = {"node_id": nid, "field": "resolution"}
            if ct == "SAMLoader" and "model_name" in inputs and not mapping["sam_model"]:
                mapping["sam_model"] = {"node_id": nid, "field": "model_name"}
            if ct == "VAELoader" and "vae_name" in inputs and not mapping["vae"]:
                mapping["vae"] = {"node_id": nid, "field": "vae_name"}

            if ct == "UpscaleModelLoader" and "model_name" in inputs and not mapping["upscale_model_loader"]:
                mapping["upscale_model_loader"] = {"node_id": nid, "field": "model_name"}

            if ct == "UltimateSDUpscale" and not mapping["ultimate_upscale_node_id"]:
                mapping["ultimate_upscale_node_id"] = {"node_id": nid}

            if ct == "easy hiresFix" and not mapping["hires_fix_node_id"]:
                mapping["hires_fix_node_id"] = {"node_id": nid, "output_index": 1}

            if ct == "SaveImage":
                current_regular = mapping.get("output_regular", {}).get("node_id") if mapping.get("output_regular") else None
                better_regular = (
                    not current_regular
                    or self._media_output_rank(workflow, nid, "image")
                    > self._media_output_rank(workflow, current_regular, "image")
                )
                if "upscale" in title and not mapping["output_upscaled"]:
                    mapping["output_upscaled"] = {"node_id": nid}
                elif better_regular:
                    mapping["output_regular"] = {"node_id": nid}
                elif not mapping["output_upscaled"]:
                    mapping["output_upscaled"] = {"node_id": nid}
            if ct == "PreviewImage":
                current_preview = mapping.get("output_preview", {}).get("node_id") if mapping.get("output_preview") else None
                if (
                    not current_preview
                    or self._media_output_rank(workflow, nid, "image")
                    > self._media_output_rank(workflow, current_preview, "image")
                ):
                    mapping["output_preview"] = {"node_id": nid}
            if self._is_video_output_node(ct, title, inputs):
                current_video = mapping.get("output_video")
                if (
                    not current_video
                    or self._media_output_rank(workflow, nid, "video")
                    > self._media_output_rank(workflow, current_video.get("node_id"), "video")
                ):
                    mapping["output_video"] = {"node_id": nid}
            if self._is_output_like_node(ct, title, inputs):
                if ("video" in ct.lower() or "video" in title):
                    current_video = mapping.get("output_video")
                    if (
                        not current_video
                        or self._media_output_rank(workflow, nid, "video")
                        > self._media_output_rank(workflow, current_video.get("node_id"), "video")
                    ):
                        mapping["output_video"] = {"node_id": nid}
                elif "upscale" in title and not mapping["output_upscaled"]:
                    mapping["output_upscaled"] = {"node_id": nid}
                elif (
                    not mapping["output_regular"]
                    or self._media_output_rank(workflow, nid, "image")
                    > self._media_output_rank(workflow, mapping["output_regular"].get("node_id"), "image")
                ):
                    mapping["output_regular"] = {"node_id": nid}
                elif not mapping["output_upscaled"]:
                    mapping["output_upscaled"] = {"node_id": nid}

            if "seed (rgthree)" in ct.lower() and "seed" in inputs and not mapping["seed"]:
                mapping["seed"] = self._resolve_workflow_input_mapping(workflow, nid, "seed", ("seed", "noise_seed", "value"))
            if ct == "RandomNoise" and "noise_seed" in inputs and not mapping["seed"]:
                mapping["seed"] = self._resolve_workflow_input_mapping(workflow, nid, "noise_seed", ("seed", "noise_seed", "value"))
            if "seed" in inputs and not mapping["seed"] and ("seed" in title or "seed" in ct.lower()):
                mapping["seed"] = self._resolve_workflow_input_mapping(workflow, nid, "seed", ("seed", "noise_seed", "value"))
            if "value" in inputs and not mapping["seed"] and "seed" in title:
                mapping["seed"] = self._resolve_workflow_input_mapping(workflow, nid, "value", ("seed", "noise_seed", "value"))

            if ct == "easy int" and "width" in title and "value" in inputs and not mapping["width"]:
                mapping["width"] = {"node_id": nid, "field": "value"}
            if ct == "easy int" and "height" in title and "value" in inputs and not mapping["height"]:
                mapping["height"] = {"node_id": nid, "field": "value"}
            if ct == "CR Aspect Ratio" and "width" in inputs and not mapping["width"]:
                mapping["width"] = {"node_id": nid, "field": "width"}
            if ct == "CR Aspect Ratio" and "height" in inputs and not mapping["height"]:
                mapping["height"] = {"node_id": nid, "field": "height"}
            if ct == "CR Aspect Ratio Social Media" and "width" in inputs and not mapping["width"]:
                mapping["width"] = {"node_id": nid, "field": "width"}
            if ct == "CR Aspect Ratio Social Media" and "height" in inputs and not mapping["height"]:
                mapping["height"] = {"node_id": nid, "field": "height"}
            if ct == "SetNode":
                set_name = self._set_get_node_name(node)
                if set_name == "width" and "INT" in inputs and not mapping["width"]:
                    mapping["width"] = {"node_id": nid, "field": "INT"}
                if set_name == "height" and "INT" in inputs and not mapping["height"]:
                    mapping["height"] = {"node_id": nid, "field": "INT"}

            width_field = next(
                (
                    field
                    for field in ("resize_type.width", "target_width", "width")
                    if field in inputs and not self._is_workflow_link(inputs.get(field))
                ),
                None,
            )
            height_field = next(
                (
                    field
                    for field in ("resize_type.height", "target_height", "height")
                    if field in inputs and not self._is_workflow_link(inputs.get(field))
                ),
                None,
            )
            if width_field and height_field and (
                "resize" in ct.lower()
                or "resize" in title
                or "scale" in ct.lower()
                or "dimension" in title
            ):
                if not mapping["width"]:
                    mapping["width"] = {"node_id": nid, "field": width_field}
                if not mapping["height"]:
                    mapping["height"] = {"node_id": nid, "field": height_field}

            if ct == "EmptyLatentImage" and not mapping["width"]:
                mapping["width"] = {"node_id": nid, "field": "width"}
            if ct == "EmptyLatentImage" and not mapping["height"]:
                mapping["height"] = {"node_id": nid, "field": "height"}
            if ct == "EmptySD3LatentImage" and not mapping["width"]:
                mapping["width"] = {"node_id": nid, "field": "width"}
            if ct == "EmptySD3LatentImage" and not mapping["height"]:
                mapping["height"] = {"node_id": nid, "field": "height"}
            if ct == "EmptyFlux2LatentImage" and not mapping["width"]:
                mapping["width"] = {"node_id": nid, "field": "width"}
            if ct == "EmptyFlux2LatentImage" and not mapping["height"]:
                mapping["height"] = {"node_id": nid, "field": "height"}
            if self._is_size_like_node(ct, title, inputs):
                if not mapping["width"]:
                    mapping["width"] = self._resolve_workflow_input_mapping(workflow, nid, "width", ("width", "value"))
                if not mapping["height"]:
                    mapping["height"] = self._resolve_workflow_input_mapping(workflow, nid, "height", ("height", "value"))
            if ct == "SDXLEmptyLatentSizePicker+":
                if "width_override" in inputs and not mapping["width"]:
                    mapping["width"] = {"node_id": nid, "field": "width_override"}
                if "height_override" in inputs and not mapping["height"]:
                    mapping["height"] = {"node_id": nid, "field": "height_override"}
                if "resolution" in inputs:
                    match = re.search(r"(\d+)\s*x\s*(\d+)", str(inputs.get("resolution")))
                    if match:
                        if not mapping["width"]:
                            mapping["width"] = {"node_id": nid, "field": "resolution_width"}
                        if not mapping["height"]:
                            mapping["height"] = {"node_id": nid, "field": "resolution_height"}
            if "resolution" in inputs and not mapping["resolution"] and (
                "resolution" in ct.lower() or "resolution" in title
            ):
                mapping["resolution"] = {"node_id": nid, "field": "resolution"}

            if ct == "ImpactSwitch" and "latent" in title and not mapping["latent_switch"]:
                mapping["latent_switch"] = {"node_id": nid, "field": "select"}
            if self._is_input_image_node(ct, title, inputs) and not mapping["input_image"]:
                image_field = next((field for field in ("image", "file", "path") if field in inputs), None)
                if image_field:
                    mapping["input_image"] = {"node_id": nid, "field": image_field}
            if self._is_input_image_node(ct, title, inputs):
                image_field = next((field for field in ("image", "file", "path") if field in inputs), None)
                item = {"node_id": nid, "field": image_field} if image_field else None
                if item and item not in mapping["input_images"]:
                    mapping["input_images"].append(item)
            if not mapping["input_image"] and ("wan" in ct.lower() or "image to video" in title):
                image_field = next(
                    (
                        field
                        for field in ("start_image", "image", "images", "first_frame")
                        if field in inputs
                    ),
                    None,
                )
                if image_field:
                    mapping["input_image"] = {
                        "node_id": nid,
                        "field": image_field,
                        "expects_link": True,
                    }
                    if mapping["input_image"] not in mapping["input_images"]:
                        mapping["input_images"].append(mapping["input_image"])
            if (
                ("loadvideo" in ct.lower() or "load video" in title)
                and not mapping["input_video"]
            ):
                for video_field in ("video", "file", "video_path", "path"):
                    if video_field in inputs:
                        mapping["input_video"] = {"node_id": nid, "field": video_field}
                        break
            if ct == "ImageScaleBy" and "scale_by" in inputs and not mapping["scale_by"]:
                mapping["scale_by"] = {"node_id": nid, "field": "scale_by"}
            if "frame" in title or "frames" in ct.lower() or "video" in ct.lower() or "wan" in ct.lower():
                for frame_field in ("frames", "frame_count", "num_frames", "length", "video_length"):
                    if frame_field in inputs and not mapping["frames"]:
                        mapping["frames"] = self._resolve_workflow_input_mapping(
                            workflow,
                            nid,
                            frame_field,
                            ("frames", "frame_count", "num_frames", "length", "video_length", "value"),
                        )
                        break
                for fps_field in ("fps", "frame_rate", "framerate"):
                    if fps_field in inputs and not mapping["fps"]:
                        mapping["fps"] = self._resolve_workflow_input_mapping(
                            workflow,
                            nid,
                            fps_field,
                            ("fps", "frame_rate", "framerate", "value"),
                        )
                        break
            megapixels_field = next(
                (field for field in ("megapixels", "resize_type.megapixels") if field in inputs),
                None,
            )
            if megapixels_field and not mapping["megapixels"] and (
                "scale" in ct.lower()
                or "size" in ct.lower()
                or "pixel" in ct.lower()
                or "resolution" in title
                or "resize" in ct.lower()
                or "resize" in title
            ):
                mapping["megapixels"] = self._resolve_workflow_input_mapping(
                    workflow,
                    nid,
                    megapixels_field,
                    ("megapixels", "resize_type.megapixels", "value"),
                )
            if megapixels_field and (
                "scale" in ct.lower()
                or "size" in ct.lower()
                or "pixel" in ct.lower()
                or "resolution" in title
                or "resize" in ct.lower()
                or "resize" in title
            ):
                resolved = self._resolve_workflow_input_mapping(
                    workflow,
                    nid,
                    megapixels_field,
                    ("megapixels", "resize_type.megapixels", "value"),
                )
                if resolved not in mapping["megapixels_nodes"]:
                    mapping["megapixels_nodes"].append(resolved)

            if ct == "KSampler" or ct == "KSamplerAdvanced":
                if "steps" in inputs and not mapping["steps"]:
                    mapping["steps"] = self._resolve_workflow_input_mapping(workflow, nid, "steps", ("steps", "value"))
                if "cfg" in inputs and not mapping["cfg"]:
                    mapping["cfg"] = self._resolve_workflow_input_mapping(workflow, nid, "cfg", ("cfg", "value"))
                if "sampler_name" in inputs and not mapping["sampler_name"]:
                    mapping["sampler_name"] = self._resolve_workflow_input_mapping(workflow, nid, "sampler_name", ("sampler_name", "value"))
                if "scheduler" in inputs and not mapping["scheduler"]:
                    mapping["scheduler"] = self._resolve_workflow_input_mapping(workflow, nid, "scheduler", ("scheduler", "value"))
                if "denoise" in inputs and not mapping["denoise"]:
                    mapping["denoise"] = self._resolve_workflow_input_mapping(workflow, nid, "denoise", ("denoise", "value"))
                if "seed" in inputs and not mapping["seed"]:
                    mapping["seed"] = self._resolve_workflow_input_mapping(workflow, nid, "seed", ("seed", "noise_seed", "value"))
                if "noise_seed" in inputs and not mapping["seed"]:
                    mapping["seed"] = self._resolve_workflow_input_mapping(workflow, nid, "noise_seed", ("seed", "noise_seed", "value"))
            elif ct == "BasicScheduler":
                if "steps" in inputs and not mapping["steps"]:
                    mapping["steps"] = self._resolve_workflow_input_mapping(workflow, nid, "steps", ("steps", "value"))
                if "scheduler" in inputs and not mapping["scheduler"]:
                    mapping["scheduler"] = self._resolve_workflow_input_mapping(workflow, nid, "scheduler", ("scheduler", "value"))
                if "denoise" in inputs and not mapping["denoise"]:
                    mapping["denoise"] = self._resolve_workflow_input_mapping(workflow, nid, "denoise", ("denoise", "value"))
            elif self._is_scheduler_like_node(ct, inputs):
                if "steps" in inputs and not mapping["steps"]:
                    mapping["steps"] = self._resolve_workflow_input_mapping(workflow, nid, "steps", ("steps", "value"))
                if "scheduler" in inputs and not mapping["scheduler"]:
                    mapping["scheduler"] = self._resolve_workflow_input_mapping(workflow, nid, "scheduler", ("scheduler", "value"))
                if "denoise" in inputs and not mapping["denoise"]:
                    mapping["denoise"] = self._resolve_workflow_input_mapping(workflow, nid, "denoise", ("denoise", "value"))
            elif ct == "KSamplerSelect":
                if "sampler_name" in inputs and not mapping["sampler_name"]:
                    mapping["sampler_name"] = self._resolve_workflow_input_mapping(workflow, nid, "sampler_name", ("sampler_name", "value"))
            elif ct == "CFGGuider":
                if "cfg" in inputs and not mapping["cfg"]:
                    mapping["cfg"] = self._resolve_workflow_input_mapping(workflow, nid, "cfg", ("cfg", "value"))
            elif ct == "DualCFGGuider":
                if "cfg_conds" in inputs and not mapping["cfg"]:
                    mapping["cfg"] = self._resolve_workflow_input_mapping(workflow, nid, "cfg_conds", ("cfg_conds", "cfg", "value"))
                elif "cfg" in inputs and not mapping["cfg"]:
                    mapping["cfg"] = self._resolve_workflow_input_mapping(workflow, nid, "cfg", ("cfg", "value"))
            elif ct == "FluxGuidance":
                if "guidance" in inputs and not mapping["flux_guidance"]:
                    mapping["flux_guidance"] = self._resolve_workflow_input_mapping(workflow, nid, "guidance", ("guidance", "value"))
            elif ct == "CLIPTextEncodeFlux":
                if "guidance" in inputs and not mapping["flux_guidance"]:
                    mapping["flux_guidance"] = self._resolve_workflow_input_mapping(workflow, nid, "guidance", ("guidance", "value"))
            elif ct == "easy int" and "steps" in title and "value" in inputs and not mapping["steps"]:
                mapping["steps"] = self._resolve_workflow_input_mapping(workflow, nid, "value", ("steps", "value"))
            elif ct == "PrimitiveFloat" and "cfg" in title and "value" in inputs and not mapping["cfg"]:
                mapping["cfg"] = self._resolve_workflow_input_mapping(workflow, nid, "value", ("cfg", "value"))
            elif ct == "PrimitiveFloat" and "denoise" in title and "value" in inputs and not mapping["denoise"]:
                mapping["denoise"] = self._resolve_workflow_input_mapping(workflow, nid, "value", ("denoise", "value"))
            elif "denoise" in inputs and not mapping["denoise"]:
                mapping["denoise"] = self._resolve_workflow_input_mapping(workflow, nid, "denoise", ("denoise", "value"))

            if self._is_sampler_like_node(ct, inputs):
                if "steps" in inputs and not mapping["steps"]:
                    mapping["steps"] = self._resolve_workflow_input_mapping(workflow, nid, "steps", ("steps", "value"))
                if "cfg" in inputs and not mapping["cfg"]:
                    mapping["cfg"] = self._resolve_workflow_input_mapping(workflow, nid, "cfg", ("cfg", "value"))
                if "sampler_name" in inputs and not mapping["sampler_name"]:
                    mapping["sampler_name"] = self._resolve_workflow_input_mapping(workflow, nid, "sampler_name", ("sampler_name", "value"))
                if "scheduler" in inputs and not mapping["scheduler"]:
                    mapping["scheduler"] = self._resolve_workflow_input_mapping(workflow, nid, "scheduler", ("scheduler", "value"))
                if "denoise" in inputs and not mapping["denoise"]:
                    mapping["denoise"] = self._resolve_workflow_input_mapping(workflow, nid, "denoise", ("denoise", "value"))
                if "seed" in inputs and not mapping["seed"]:
                    mapping["seed"] = self._resolve_workflow_input_mapping(workflow, nid, "seed", ("seed", "noise_seed", "value"))
                if "noise_seed" in inputs and not mapping["seed"]:
                    mapping["seed"] = self._resolve_workflow_input_mapping(workflow, nid, "noise_seed", ("seed", "noise_seed", "value"))

        if not mapping.get("output") and mapping.get("output_regular"):
            mapping["output"] = mapping["output_regular"]
        elif not mapping.get("output") and mapping.get("output_upscaled"):
            mapping["output"] = mapping["output_upscaled"]
        elif not mapping.get("output") and mapping.get("output_video"):
            mapping["output"] = mapping["output_video"]

        if mapping.get("output_video"):
            if mapping.get("output_regular") or mapping.get("output_upscaled"):
                mapping["output_kind"] = "mixed"
            else:
                mapping["output_kind"] = "video"
        image_input_nodes = {
            str(nid)
            for nid, node in workflow.items()
            if isinstance(node, dict)
            and self._is_input_image_node(
                node.get("class_type", ""),
                node.get("_meta", {}).get("title", ""),
                node.get("inputs", {}),
            )
        }

        if mapping.get("input_video"):
            mapping["input_kind"] = "video"
        elif len(image_input_nodes) > 1:
            mapping["input_kind"] = "image_pair"
        elif mapping.get("input_image") or mapping.get("latent_switch"):
            mapping["input_kind"] = "image"

        return mapping

    def _guess_node_pack(self, class_type: str):
        lowered = class_type.lower()
        exact = {
            "mathexpression|pysssss": "ComfyUI-Custom-Scripts",
            "playsound|pysssss": "ComfyUI-Custom-Scripts",
            "showtext|pysssss": "ComfyUI-Custom-Scripts",
            "ultimatesdupscale": "ComfyUI_UltimateSDUpscale",
            "facedetailer": "ComfyUI-Impact-Pack",
            "detailerforeach": "ComfyUI-Impact-Pack",
            "impactsimpledetectorsegs": "ComfyUI-Impact-Pack",
            "samloader": "ComfyUI-Impact-Pack",
            "ultralyticsdetectorprovider": "ComfyUI-Impact-Pack",
            "anything everywhere": "rgthree-comfy",
            "any switch (rgthree)": "rgthree-comfy",
            "seed (rgthree)": "rgthree-comfy",
            "power lora loader (rgthree)": "rgthree-comfy",
            "imagecasharpening+": "ComfyUI-Image-Filters",
            "imagedesaturate+": "ComfyUI-Image-Filters",
            "colormatch": "ComfyUI-Image-Filters",
            "depthanythingv2preprocessor": "comfyui_controlnet_aux",
            "cr vignette filter": "ComfyUI_Comfyroll_CustomNodes",
            "cr aspect ratio social media": "ComfyUI_Comfyroll_CustomNodes",
            "vhs_videocombine": "ComfyUI-VideoHelperSuite",
            "wanvideomodelloader": "ComfyUI-WanVideoWrapper",
            "wanvideosampler": "ComfyUI-WanVideoWrapper",
            "wanvideoscheduler": "ComfyUI-WanVideoWrapper",
            "wanvideovaeloader": "ComfyUI-WanVideoWrapper",
            "wanimagetovideo": "ComfyUI-WanVideoWrapper",
        }
        if lowered in exact:
            return exact[lowered]
        guesses = (
            ("pysssss", "ComfyUI-Custom-Scripts"),
            ("ultimate", "ComfyUI_UltimateSDUpscale"),
            ("impact", "ComfyUI-Impact-Pack"),
            ("rgthree", "rgthree-comfy"),
            ("easy", "ComfyUI-Easy-Use"),
            ("easyuse", "ComfyUI-Easy-Use"),
            ("kj", "ComfyUI-KJNodes"),
            ("cr_", "ComfyUI_Comfyroll_CustomNodes"),
            ("was", "WAS Node Suite"),
            ("cr ", "ComfyUI_Comfyroll_CustomNodes"),
            ("comfyroll", "ComfyUI_Comfyroll_CustomNodes"),
            ("controlnetaux", "comfyui_controlnet_aux"),
            ("preprocessor", "comfyui_controlnet_aux"),
            ("qwen", "ComfyUI-AILab"),
            ("ailab", "ComfyUI-AILab"),
            ("efficiency", "efficiency-nodes-comfyui"),
            ("inspire", "ComfyUI-Inspire-Pack"),
            ("vhs_", "ComfyUI-VideoHelperSuite"),
            ("videohelper", "ComfyUI-VideoHelperSuite"),
            ("wanvideo", "ComfyUI-WanVideoWrapper"),
            ("wan", "ComfyUI-WanVideoWrapper"),
            ("mmaudio", "ComfyUI-MMAudio"),
            ("rife", "ComfyUI-Frame-Interpolation"),
            ("florence2", "ComfyUI-Florence2"),
        )
        for marker, pack in guesses:
            if marker in lowered:
                return pack
        return None

    _UI_WIDGET_INPUTS = {
        "CheckpointLoaderSimple": ("ckpt_name",),
        "UNETLoader": ("unet_name", "weight_dtype"),
        "UnetLoaderGGUF": ("unet_name",),
        "LoraLoaderModelOnly": ("lora_name", "strength_model"),
        "DualCLIPLoader": ("clip_name1", "clip_name2", "type"),
        "CLIPLoader": ("clip_name", "type", "device"),
        "VAELoader": ("vae_name",),
        "CLIPTextEncode": ("text",),
        "CLIPTextEncodeFlux": ("clip_l", "t5xxl", "guidance"),
        "PrimitiveStringMultiline": ("value",),
        "ttN text": ("text",),
        "CR Text": ("text",),
        "Text Find and Replace": ("text", "find", "replace"),
        "easy promptReplace": ("text", "replace", "replace_with"),
        "Prompts Everywhere": ("text",),
        "CLIPSetLastLayer": ("stop_at_clip_layer",),
        "KSamplerSelect": ("sampler_name",),
        "BasicScheduler": ("scheduler", "steps", "denoise"),
        "RandomNoise": ("noise_seed", None),
        "KSampler": ("seed", None, "steps", "cfg", "sampler_name", "scheduler", "denoise"),
        "KSamplerAdvanced": ("add_noise", "noise_seed", None, "steps", "cfg", "sampler_name", "scheduler", "start_at_step", "end_at_step", "return_with_leftover_noise"),
        "SaveImage": ("filename_prefix",),
        "LoadImage": ("image", "upload"),
        "EmptyLatentImage": ("width", "height", "batch_size"),
        "EmptySD3LatentImage": ("width", "height", "batch_size"),
        "EmptyFlux2LatentImage": ("width", "height", "batch_size"),
        "SDXL Resolutions (JPS)": ("resolution",),
        "SDXLEmptyLatentSizePicker+": ("resolution", "batch_size", "width_override", "height_override"),
        "CR Aspect Ratio Social Media": ("width", "height", "aspect_ratio", "swap_dimensions", "upscale_factor", "prescale_factor", "batch_size"),
        "ImageScaleBy": ("upscale_method", "scale_by"),
        "LatentUpscaleBy": ("upscale_method", "scale_by"),
        "ImageResizeKJv2": ("width", "height", "upscale_method", "keep_proportion", "pad_color", "crop_position", "divisible_by", "device"),
        "ImageResize+": ("width", "height", "interpolation", "method"),
        "ImageScale": ("upscale_method", "width", "height", "crop"),
        "SetImageSize": ("width", "height"),
        "HintImageEnchance": ("image_gen_width", "image_gen_height", "resize_mode"),
        "UpscaleModelLoader": ("model_name",),
        "ControlNetLoader": ("control_net_name",),
        "ControlNetApplyAdvanced": ("strength", "start_percent", "end_percent"),
        "SAMLoader": ("model_name", "device_mode"),
        "UltralyticsDetectorProvider": ("model_name",),
        "easy positive": ("positive",),
        "easy negative": ("negative",),
        "easy mathInt": ("a", "b", "operation"),
        "easy mathFloat": ("a", "b", "operation"),
        "MathExpression|pysssss": ("expression",),
        "ComfyMathExpression": ("expression",),
        "PrimitiveBoolean": ("value",),
        "PrimitiveFloat": ("value",),
        "PrimitiveInt": ("value",),
        "Int": ("value",),
        "Float": ("value",),
        "ttN int": ("value",),
        "mxSlider": ("value", "min", "max", "step"),
        "mxSlider2D": ("x", "y", "min", "max", "step"),
        "Seed (rgthree)": ("seed",),
        "VHS_VideoCombine": ("frame_rate", "loop_count", "filename_prefix", "format", "pingpong", "save_output"),
        "VHS_LoadVideo": ("video", "force_rate", "force_size", "custom_width", "custom_height", "frame_load_cap", "skip_first_frames", "select_every_nth"),
        "VHS_LoadVideoFFmpeg": ("video", "force_rate", "force_size", "custom_width", "custom_height", "frame_load_cap", "skip_first_frames", "select_every_nth"),
        "VHS_LoadAudio": ("audio",),
        "WanImageToVideo": ("width", "height", "length", "batch_size"),
        "WanFirstLastFrameToVideo": ("width", "height", "length", "batch_size"),
        "WanResolutions": ("width", "height", "resolution"),
        "WanMoeKSampler": ("seed", "steps", "cfg", "shift", "denoise", "sampler_name", "scheduler"),
        "WanVideoSampler": ("seed", "steps", "cfg", "shift", "denoise", "scheduler"),
        "WanVideoScheduler": ("steps", "cfg", "shift", "scheduler", "denoise"),
        "WanVideoModelLoader": ("model_name", "base_precision", "quantization"),
        "WanVideoVAELoader": ("vae_name",),
        "WanVideoTextEncodeCached": ("text", "negative", "force_offload"),
        "WanVideoEncode": ("width", "height", "num_frames"),
        "WanVideoImageToVideoEncode": ("width", "height", "num_frames"),
        "WanVideoEncodeLatentBatch": ("width", "height", "num_frames"),
        "ImageDesaturate+": ("factor", "method"),
        "PlaySound|pysssss": ("mode", "volume", "file"),
        "ColorMatch": ("method",),
        "ImageCASharpening+": ("amount",),
        "CR Vignette Filter": ("vignette_shape", "feather_amount", "x_offset", "y_offset", "zoom", "reverse"),
        "ImageCompositeMasked": ("x", "y", "resize_source"),
        "ImpactSimpleDetectorSEGS": (
            "bbox_threshold", "bbox_dilation", "crop_factor",
            "drop_size", "sub_threshold", "sub_dilation",
            "sub_bbox_expansion", "sam_mask_hint_threshold",
        ),
        "DetailerForEach": (
            "guide_size", "guide_size_for", "max_size", "seed", None,
            "steps", "cfg", "sampler_name", "scheduler", "denoise",
            "feather", "noise_mask", "force_inpaint", "wildcard",
            "cycle", "inpaint_model", "noise_mask_feather", None, None,
        ),
        "UltimateSDUpscale": (
            "upscale_by", "seed", None, "steps", "cfg",
            "sampler_name", "scheduler", "denoise", "mode_type",
            "tile_width", "tile_height", "mask_blur", "tile_padding",
            "seam_fix_mode", "seam_fix_denoise", "seam_fix_width",
            "seam_fix_mask_blur", "seam_fix_padding", "force_uniform_tiles",
            "tiled_decode", "batch_size",
        ),
        "PatchModelAddDownscale": ("block_number", "downscale_factor", "start_percent", "end_percent", "downscale_after_skip", "downscale_method", "upscale_method"),
        "SelfAttentionGuidance": ("scale", "blur_sigma"),
        "FaceDetailer": (
            "guide_size", "guide_size_for", "max_size", "seed", None,
            "steps", "cfg", "sampler_name", "scheduler", "denoise",
            "feather", "noise_mask", "force_inpaint", "bbox_threshold",
            "bbox_dilation", "bbox_crop_factor", "sam_detection_hint",
            "sam_dilation", "sam_threshold", "sam_bbox_expansion",
            "sam_mask_hint_threshold", "sam_mask_hint_use_negative",
            "drop_size", "wildcard", "cycle", "inpaint_model",
            "noise_mask_feather", None, None,
        ),
    }

    @staticmethod
    def _is_ui_workflow(workflow):
        return (
            isinstance(workflow, dict)
            and isinstance(workflow.get("nodes"), list)
            and isinstance(workflow.get("links"), list)
        )

    @staticmethod
    def _is_api_workflow(workflow):
        return (
            isinstance(workflow, dict)
            and bool(workflow)
            and all(isinstance(node_id, (str, int)) for node_id in workflow)
            and any(
                isinstance(node, dict)
                and isinstance(node.get("inputs", {}), dict)
                and isinstance(node.get("class_type"), str)
                and node.get("class_type")
                for node in workflow.values()
            )
        )

    @staticmethod
    def _is_uuid_class_type(class_type):
        return bool(re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            str(class_type or "").strip(),
        ))

    def _is_ui_virtual_proxy_node(self, node):
        if not isinstance(node, dict):
            return False
        class_type = node.get("type")
        properties = node.get("properties", {})
        outputs = node.get("outputs", [])
        return (
            self._is_uuid_class_type(class_type)
            and isinstance(properties, dict)
            and "proxyWidgets" in properties
            and not outputs
        )

    def _sanitize_api_workflow(self, workflow, object_info=None):
        if not isinstance(workflow, dict):
            return workflow
        sanitized = {}
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            sanitized[str(node_id)] = node
        return sanitized

    def _cached_all_object_info(self):
        base = self._base_url()
        if not base:
            return None
        return self._comfy_cache.get(f"object_info:{base}:all")

    def _extract_workflow_payload(self, workflow):
        seen = set()
        current = workflow
        for _ in range(8):
            marker = id(current)
            if marker in seen:
                break
            seen.add(marker)

            if isinstance(current, str):
                stripped = current.strip()
                if not stripped:
                    break
                try:
                    current = json.loads(stripped)
                    continue
                except Exception:
                    break

            if self._is_ui_workflow(current) or self._is_api_workflow(current):
                return current

            if not isinstance(current, dict):
                break

            extra_pnginfo = current.get("extra_pnginfo")
            if isinstance(extra_pnginfo, dict):
                for key in ("workflow", "prompt"):
                    nested = extra_pnginfo.get(key)
                    if nested:
                        current = nested
                        break
                else:
                    nested = None
                if nested:
                    continue

            for key in ("prompt", "workflow", "workflow_api", "api_workflow"):
                nested = current.get(key)
                if nested:
                    current = nested
                    break
            else:
                break

        return current

    @staticmethod
    def _ui_node_title(node, class_type):
        return (
            str(node.get("title") or "").strip()
            or str(node.get("properties", {}).get("Node name for S&R") or "").strip()
            or str(class_type or "").strip()
        )

    def _ui_widget_fields_from_object_info(self, class_type, node_inputs, object_info):
        if not isinstance(object_info, dict):
            return []
        node_info = object_info.get(class_type, {})
        fields = []
        for section in ("required", "optional"):
            items = node_info.get("input", {}).get(section, {})
            if not isinstance(items, dict):
                continue
            for name in items:
                if name not in node_inputs:
                    fields.append(name)
        return fields

    def _ui_widget_fields(self, node, object_info=None):
        class_type = str(node.get("type") or "")
        if class_type in self._UI_WIDGET_INPUTS:
            return self._UI_WIDGET_INPUTS[class_type]
        node_inputs = {
            item.get("name")
            for item in node.get("inputs", [])
            if isinstance(item, dict) and item.get("name")
        }
        return tuple(self._ui_widget_fields_from_object_info(class_type, node_inputs, object_info))

    @staticmethod
    def _ui_primitive_value(node):
        widgets = node.get("widgets_values")
        if isinstance(widgets, list) and widgets:
            return widgets[0]
        return None

    @staticmethod
    def _ui_set_get_name(node):
        widgets = node.get("widgets_values")
        if isinstance(widgets, list) and widgets and widgets[0] is not None:
            return str(widgets[0]).strip().lower()
        title = str(node.get("title") or "").strip().lower()
        if title.startswith("set_") or title.startswith("get_"):
            return title[4:].strip()
        return title

    @staticmethod
    def _ui_power_lora_inputs(node):
        widgets = node.get("widgets_values")
        if not isinstance(widgets, list):
            return {}
        result = {}
        index = 1
        for value in widgets:
            if not isinstance(value, dict) or "lora" not in value:
                continue
            result[f"lora_{index}"] = {
                "on": bool(value.get("on", True)),
                "lora": value.get("lora"),
                "strength": value.get("strength", 1),
            }
            if "strengthTwo" in value:
                result[f"lora_{index}"]["strengthTwo"] = value.get("strengthTwo")
            index += 1
        return result

    def _convert_ui_workflow_to_api(self, workflow, object_info=None):
        nodes = workflow.get("nodes", [])
        links = {}
        nodes_by_id = {}
        primitive_values = {}

        for node in nodes:
            if not isinstance(node, dict) or node.get("id") is None:
                continue
            node_id = str(node.get("id"))
            nodes_by_id[node_id] = node
            if node.get("type") == "PrimitiveNode":
                primitive_values[node_id] = self._ui_primitive_value(node)

        for link in workflow.get("links", []):
            try:
                if isinstance(link, list) and len(link) >= 5:
                    links[link[0]] = [str(link[1]), int(link[2])]
                elif isinstance(link, dict):
                    link_id = link.get("id", link.get("link_id"))
                    source_id = link.get("origin_id", link.get("source_id", link.get("from_node_id")))
                    source_slot = link.get("origin_slot", link.get("source_slot", link.get("from_slot", 0)))
                    if link_id is not None and source_id is not None:
                        links[link_id] = [str(source_id), int(source_slot or 0)]
            except (TypeError, ValueError):
                continue

        def input_source_value(node):
            for item in node.get("inputs", []):
                if not isinstance(item, dict):
                    continue
                link_id = item.get("link")
                if link_id is None and isinstance(item.get("links"), list) and item["links"]:
                    link_id = item["links"][0]
                if link_id is None or link_id not in links:
                    continue
                source_id, source_output = links[link_id]
                if source_id in primitive_values:
                    return primitive_values[source_id]
                return [source_id, source_output]
            return None

        set_sources = {}
        aliases = {}
        for node in nodes:
            if not isinstance(node, dict) or node.get("id") is None:
                continue
            node_id = str(node.get("id"))
            class_type = node.get("type")
            if class_type == "SetNode":
                source_value = input_source_value(node)
                if source_value is None:
                    continue
                name = self._ui_set_get_name(node)
                if name:
                    set_sources[name] = source_value
                    aliases[node_id] = source_value
            elif class_type == "Reroute":
                source_value = input_source_value(node)
                if source_value is not None:
                    aliases[node_id] = source_value

        for node in nodes:
            if not isinstance(node, dict) or node.get("id") is None:
                continue
            if node.get("type") != "GetNode":
                continue
            source_value = set_sources.get(self._ui_set_get_name(node))
            if source_value is not None:
                aliases[str(node.get("id"))] = source_value

        def resolve_source_value(source_id, source_output):
            source_id = str(source_id)
            source_output = int(source_output)
            seen = set()
            while source_id in aliases and source_id not in seen:
                seen.add(source_id)
                alias = aliases[source_id]
                if not self._is_workflow_link(alias):
                    return alias
                source_id = str(alias[0])
                try:
                    source_output = int(alias[1])
                except (TypeError, ValueError):
                    source_output = 0
            if source_id in primitive_values:
                return primitive_values[source_id]
            return [source_id, source_output]

        converted = {}
        for node in nodes:
            if not isinstance(node, dict) or node.get("id") is None:
                continue
            if self._is_ui_virtual_proxy_node(node):
                continue
            node_id = str(node.get("id"))
            class_type = node.get("type")
            if not class_type or class_type in {"Note", "PrimitiveNode", "Reroute", "SetNode", "GetNode"}:
                continue

            inputs = {}
            for item in node.get("inputs", []):
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                link_id = item.get("link")
                if link_id is None and isinstance(item.get("links"), list) and item["links"]:
                    link_id = item["links"][0]
                if link_id is None or link_id not in links:
                    continue
                source_id, source_output = links[link_id]
                inputs[item["name"]] = resolve_source_value(source_id, source_output)

            widgets = node.get("widgets_values")
            if not isinstance(widgets, list):
                widgets = []
            for field, value in zip(self._ui_widget_fields(node, object_info), widgets):
                if field is None or field in inputs:
                    continue
                inputs[field] = value
            if class_type == "Power Lora Loader (rgthree)":
                inputs.update(self._ui_power_lora_inputs(node))

            meta = {"title": self._ui_node_title(node, class_type)}
            if widgets:
                meta["ui_widgets"] = widgets
            properties = node.get("properties")
            if isinstance(properties, dict) and "value" in properties:
                meta["ui_value"] = properties.get("value")

            converted[node_id] = {
                "inputs": inputs,
                "class_type": class_type,
                "_meta": meta,
            }

        return converted

    def _normalize_workflow_format(self, workflow, object_info=None):
        workflow = self._extract_workflow_payload(workflow)
        if object_info is None:
            object_info = self._cached_all_object_info()
        if self._is_ui_workflow(workflow):
            return self._sanitize_api_workflow(
                self._convert_ui_workflow_to_api(workflow, object_info),
                object_info,
            )
        if isinstance(workflow, dict):
            nodes = {
                str(node_id): node
                for node_id, node in workflow.items()
                if isinstance(node, dict)
                and isinstance(node.get("inputs", {}), dict)
                and isinstance(node.get("class_type"), str)
                and node.get("class_type")
            }
            if nodes and len(nodes) != len(workflow):
                return self._sanitize_api_workflow(nodes, object_info)
            if nodes:
                return self._sanitize_api_workflow(nodes, object_info)
        return workflow

    async def _validate_workflow(self, workflow):
        result = {
            "ok": False,
            "critical": [],
            "warnings": [],
            "missing_nodes": [],
            "found": {},
            "mapping": {},
        }

        object_info = await self._get_all_object_info()
        workflow = self._normalize_workflow_format(workflow, object_info)

        if not isinstance(workflow, dict) or not workflow:
            result["critical"].append(self.strings("wf_validation_empty"))
            return result

        invalid_nodes = [
            node_id
            for node_id, node in workflow.items()
            if not isinstance(node, dict) or not isinstance(node.get("inputs", {}), dict)
        ]
        if invalid_nodes:
            result["critical"].append(self.strings("wf_validation_node_invalid"))
            return result

        class_types = sorted(
            {
                node.get("class_type")
                for node in workflow.values()
                if isinstance(node.get("class_type"), str) and node.get("class_type")
            }
        )

        if isinstance(object_info, dict):
            installed_nodes = set(object_info.keys())
            global_input_types = self._get_global_input_types(workflow, object_info)
            result["missing_nodes"] = [
                class_type
                for class_type in class_types
                if class_type not in installed_nodes
                and not self._is_uuid_class_type(class_type)
            ]
            if result["missing_nodes"]:
                result["critical"].extend(result["missing_nodes"])
            for node_id, node in workflow.items():
                class_type = node.get("class_type")
                node_info = object_info.get(class_type, {})
                required_inputs = (
                    node_info
                    .get("input", {})
                    .get("required", {})
                )
                if not isinstance(required_inputs, dict):
                    continue
                inputs = node.get("inputs", {})
                missing_inputs = [
                    name
                    for name, input_spec in required_inputs.items()
                    if name not in inputs
                    and not self._is_ignored_missing_required_input(
                        class_type,
                        name,
                    )
                    and not (
                        str(class_type) == "BatchImagesNode"
                        and name == "images"
                        and any(str(key).startswith("images.") for key in inputs)
                    )
                    and not self._global_input_covers_required(
                        name,
                        input_spec,
                        global_input_types,
                    )
                ]
                if missing_inputs:
                    result["critical"].append(
                        self.strings("wf_validation_missing_inputs").format(
                            node_id,
                            class_type,
                            ", ".join(str(name) for name in missing_inputs[:10]),
                        )
                    )
        else:
            result["warnings"].append(self.strings("wf_validation_object_info_fail"))

        mapping = self._parse_workflow(workflow)
        result["mapping"] = {key: value for key, value in mapping.items() if value}

        checks = {
            "positive": bool(mapping.get("positive")),
            "negative": bool(mapping.get("negative")),
            "model": bool(mapping.get("model")),
            "seed": bool(mapping.get("seed")),
            "steps": bool(mapping.get("steps")),
            "cfg": bool(mapping.get("cfg") or mapping.get("flux_guidance")),
            "output": bool(mapping.get("output") or mapping.get("output_regular") or mapping.get("output_upscaled") or mapping.get("output_video")),
            "size": bool((mapping.get("width") and mapping.get("height")) or mapping.get("megapixels") or mapping.get("resolution")),
            "denoise": bool(mapping.get("denoise")),
            "img2img": bool(mapping.get("input_image") or mapping.get("input_video") or mapping.get("latent_switch")),
            "frames": bool(mapping.get("frames")),
            "fps": bool(mapping.get("fps")),
            "output_kind": mapping.get("output_kind") or "image",
            "input_kind": mapping.get("input_kind") or "none",
        }
        image_only = self._is_image_only_mapping(mapping)
        checks["image_only"] = image_only
        result["found"] = checks

        if (
            not image_only
            and not checks["positive"]
            and not (
                mapping.get("output_kind") in ("video", "mixed")
                and mapping.get("input_kind") in ("image", "image_pair", "video")
            )
        ):
            result["critical"].append(self.strings("wf_validation_no_positive"))
        if not image_only and not checks["model"] and mapping.get("output_kind") not in ("video", "mixed"):
            result["critical"].append(self.strings("wf_validation_no_model"))
        if not checks["output"]:
            result["critical"].append(self.strings("wf_validation_no_output"))

        warning_keys = (
            ()
            if image_only
            else ("negative", "seed", "steps", "cfg", "size", "denoise", "img2img")
        )
        label_map = {
            "negative": "wf_check_negative",
            "model": "wf_check_model",
            "seed": "wf_check_seed",
            "steps": "wf_check_steps",
            "cfg": "wf_check_cfg",
            "size": "wf_check_size",
            "denoise": "wf_check_denoise",
            "img2img": "wf_check_img2img",
        }
        for key in warning_keys:
            if not checks[key]:
                result["warnings"].append(
                    self.strings("wf_validation_missing_optional").format(
                        self.strings(label_map[key])
                    )
                )

        result["ok"] = not result["critical"] and not result["missing_nodes"]
        return result

    @staticmethod
    def _append_expandable_section(lines, title, body):
        if not body:
            return
        lines.append(title)
        lines.append(f"<blockquote expandable>{chr(10).join(body)}</blockquote>")

    def _format_workflow_validation(self, name, validation, saved=False):
        title = (
            self.strings("checkwf_saved_title")
            if saved
            else self.strings("checkwf_title")
        ).format(utils.escape_html(name))
        lines = [title, ""]
        lines.append(
            self.strings("wf_validation_ok")
            if validation.get("ok")
            else self.strings("wf_validation_failed")
        )

        label_map = {
            "positive": "wf_check_positive",
            "negative": "wf_check_negative",
            "model": "wf_check_model",
            "seed": "wf_check_seed",
            "steps": "wf_check_steps",
            "cfg": "wf_check_cfg",
            "output": "wf_check_output",
            "size": "wf_check_size",
            "denoise": "wf_check_denoise",
            "img2img": "wf_check_img2img",
            "frames": "wf_check_frames",
            "fps": "wf_check_fps",
        }
        found = validation.get("found", {})
        if found:
            found_lines = []
            found_lines.append(
                f"{self.strings('wf_icon_found')} {self.strings('wf_check_output_kind').format(utils.escape_html(str(found.get('output_kind') or 'image')))}"
            )
            found_lines.append(
                f"{self.strings('wf_icon_found')} {self.strings('wf_check_input_kind').format(utils.escape_html(str(found.get('input_kind') or 'none')))}"
            )
            for key, label_key in label_map.items():
                if found.get("image_only") and key not in ("output", "size", "img2img"):
                    continue
                if found.get("image_only") and key == "size" and not found.get("size"):
                    continue
                icon = self.strings("wf_icon_found") if found.get(key) else self.strings("wf_icon_missing")
                found_lines.append(f"{icon} {self.strings(label_key)}")
            self._append_expandable_section(
                lines,
                self.strings("wf_validation_found"),
                found_lines,
            )

        critical = [
            item
            for item in validation.get("critical", [])
            if item not in validation.get("missing_nodes", [])
        ]
        critical_lines = []
        if critical:
            for item in critical:
                critical_lines.append(f"{self.strings('wf_icon_error')} {utils.escape_html(item)}")

        missing_nodes = validation.get("missing_nodes", [])
        if missing_nodes:
            critical_lines.append(self.strings("wf_validation_missing_nodes").strip())
            for node in missing_nodes:
                pack = self._guess_node_pack(node)
                if pack:
                    critical_lines.append(
                        self.strings("wf_validation_node_pack").format(
                            f"<code>{utils.escape_html(node)}</code>",
                            utils.escape_html(pack),
                        )
                    )
                else:
                    critical_lines.append(f"<code>{utils.escape_html(node)}</code>")
        self._append_expandable_section(
            lines,
            self.strings("wf_validation_critical"),
            critical_lines,
        )

        warnings = validation.get("warnings", [])
        if warnings:
            warning_lines = []
            for item in warnings:
                warning_lines.append(f"{self.strings('wf_icon_warning')} {utils.escape_html(item)}")
            self._append_expandable_section(
                lines,
                self.strings("wf_validation_warnings"),
                warning_lines,
            )

        return "\n".join(lines)

    @staticmethod
    def _truncate_validation_item(item, limit=180):
        text = str(item)
        if len(text) <= limit:
            return text
        return f"{text[: max(0, limit - 3)]}..."

    def _format_workflow_validation_compact(self, name, validation, max_items=25, max_chars=180):
        title = self.strings("checkwf_title").format(utils.escape_html(name))
        lines = [
            title,
            "",
            self.strings("wf_validation_failed"),
        ]

        critical = [
            item
            for item in validation.get("critical", [])
            if item not in validation.get("missing_nodes", [])
        ]
        critical_lines = [
            f"{self.strings('wf_icon_error')} {utils.escape_html(self._truncate_validation_item(item, max_chars))}"
            for item in critical[:max_items]
        ]
        if len(critical) > max_items:
            critical_lines.append(f"... +{len(critical) - max_items}")

        missing_nodes = validation.get("missing_nodes", [])
        if missing_nodes:
            critical_lines.append(self.strings("wf_validation_missing_nodes").strip())
            for node in missing_nodes[:max_items]:
                pack = self._guess_node_pack(node)
                node = self._truncate_validation_item(node, max_chars)
                if pack:
                    critical_lines.append(
                        self.strings("wf_validation_node_pack").format(
                            f"<code>{utils.escape_html(node)}</code>",
                            utils.escape_html(pack),
                        )
                    )
                else:
                    critical_lines.append(f"<code>{utils.escape_html(node)}</code>")
            if len(missing_nodes) > max_items:
                critical_lines.append(f"... +{len(missing_nodes) - max_items}")

        self._append_expandable_section(
            lines,
            self.strings("wf_validation_critical"),
            critical_lines,
        )

        warnings = validation.get("warnings", [])
        warning_lines = [
            f"{self.strings('wf_icon_warning')} {utils.escape_html(self._truncate_validation_item(item, max_chars))}"
            for item in warnings[:max_items]
        ]
        if len(warnings) > max_items:
            warning_lines.append(f"... +{len(warnings) - max_items}")
        self._append_expandable_section(
            lines,
            self.strings("wf_validation_warnings"),
            warning_lines,
        )

        return "\n".join(lines)

    async def _load_workflow_json_from_reply(self, message):
        reply = await message.get_reply_message()
        if not reply or not reply.document:
            return None, "no_reply"
        file_obj = getattr(reply, "file", None)
        file_size = getattr(file_obj, "size", None)
        if file_size and file_size > 10 * 1024 * 1024:
            return None, "too_large"
        bio = io.BytesIO()
        try:
            await self.client.download_media(reply, bio)
            bio.seek(0)
            return self._normalize_workflow_format(json.load(bio)), None
        except json.JSONDecodeError:
            return None, "bad_json"
        except Exception as e:
            logger.exception(e)
            return None, "bad_json"
        finally:
            bio.close()

    async def _get_workflow_reply_name(self, message, fallback="workflow"):
        args = utils.get_args_raw(message).strip()
        if args:
            return args
        reply = await message.get_reply_message()
        if not reply:
            return fallback
        file_obj = getattr(reply, "file", None)
        file_name = getattr(file_obj, "name", None)
        if not file_name and getattr(reply, "document", None):
            for attr in getattr(reply.document, "attributes", []):
                file_name = getattr(attr, "file_name", None)
                if file_name:
                    break
        if not file_name:
            return fallback
        file_name = file_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
        if file_name.lower().endswith(".json"):
            file_name = file_name[:-5]
        return file_name or fallback

    async def _get_available_loras(self):
        info = await self._get_object_info("LoraLoader", attempts=1, timeout=8)
        return self._parse_object_info_list(info, "LoraLoader", "lora_name")

    async def _fetch_civitai_random_prompt(self):
        params = {
            "limit": 100,
            "sort": "Most Reactions",
            "period": "Month",
            "nsfw": "false",
            "withMeta": "true",
        }
        try:
            async with self._session_get(
                _CIVITAI_IMAGES_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    logger.debug("Civitai images request failed (HTTP %s): %s", resp.status, (await resp.text())[:500])
                    raise UserFacingError("civitai_error", self._plain_text(self.strings("civitai_error")))
                data = await resp.json(content_type=None)
        except UserFacingError:
            raise
        except Exception as e:
            logger.debug("Civitai random prompt request failed: %s", e)
            raise UserFacingError("civitai_error", self._plain_text(self.strings("civitai_error")))

        items = data.get("items", []) if isinstance(data, dict) else []
        prompts = []
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta")
            if not isinstance(meta, dict):
                continue
            positive = meta.get("prompt")
            if not isinstance(positive, str) or not positive.strip():
                continue
            negative = meta.get("negativePrompt")
            if not isinstance(negative, str):
                negative = ""
            elif negative.strip().lower() in {"none", "null"}:
                negative = ""
            prompts.append(
                {
                    "positive": positive.strip(),
                    "negative": negative.strip(),
                }
            )

        if not prompts:
            raise UserFacingError("civitai_no_prompt", self._plain_text(self.strings("civitai_no_prompt")))
        return random.choice(prompts)

    def _canonical_workflow_name(self, name):
        raw = str(name or "").strip()
        lowered = raw.lower()
        if lowered == "":
            return _DEFAULT_WORKFLOW_NAME
        if lowered in ("t2i", "i2i", "anime"):
            return _ANIME_WORKFLOW_NAME
        if lowered in ("anima", "animev2", "anime_v2", "anime-v2", "anime v2"):
            return _ANIME_V2_WORKFLOW_NAME
        if lowered in ("zimageturbo", "z_image_turbo", "z-image-turbo", "z image turbo"):
            return _Z_IMAGE_TURBO_WORKFLOW_NAME
        if lowered in ("sdxlreal1", "sdxl_real1", "sdxl-real1", "sdxl real1"):
            return _SDXL_REAL1_WORKFLOW_NAME
        if lowered in ("sdxlreal2", "sdxl_real2", "sdxl-real2", "sdxl real2"):
            return _SDXL_REAL2_WORKFLOW_NAME
        if lowered in ("ernie", "ernie workflow", "ernie_workflow", "ernie-workflow"):
            return _ERNIE_WORKFLOW_NAME
        if lowered in ("fluxedit", "flux_edit", "flux-edit", "flux edit", "fluxi2i", "flux_i2i", "flux-i2i"):
            return _FLUX_EDIT_WORKFLOW_NAME
        for workflow_name in self._BUILTIN_WORKFLOWS:
            if workflow_name.lower() == lowered:
                return workflow_name
        custom = self.get("workflows", {})
        if isinstance(custom, dict):
            for workflow_name in custom:
                if str(workflow_name).lower() == lowered:
                    return workflow_name
        return raw

    def _builtin_workflow_description(self, name):
        canonical_name = self._canonical_workflow_name(name)
        if canonical_name == _ANIME_WORKFLOW_NAME:
            return self.strings("wf_desc_anime")
        if canonical_name == _ANIME_V2_WORKFLOW_NAME:
            return self.strings("wf_desc_anime_v2")
        if canonical_name == _Z_IMAGE_TURBO_WORKFLOW_NAME:
            return self.strings("wf_desc_zimage_turbo")
        if canonical_name == _SDXL_REAL1_WORKFLOW_NAME:
            return self.strings("wf_desc_sdxl_real1")
        if canonical_name == _SDXL_REAL2_WORKFLOW_NAME:
            return self.strings("wf_desc_sdxl_real2")
        if canonical_name == _ERNIE_WORKFLOW_NAME:
            return self.strings("wf_desc_ernie")
        if canonical_name == _FLUX_EDIT_WORKFLOW_NAME:
            return self.strings("wf_desc_fluxedit")
        return ""

    def _custom_workflow_entry(self, name):
        custom = self.get("workflows", {})
        if not isinstance(custom, dict):
            return {}
        canonical_name = self._canonical_workflow_name(name)
        entry = custom.get(canonical_name) or custom.get(str(name or "").lower())
        return entry if isinstance(entry, dict) else {}

    def _workflow_description(self, name):
        canonical_name = self._canonical_workflow_name(name)
        if canonical_name in self._BUILTIN_WORKFLOWS:
            return self._builtin_workflow_description(canonical_name)
        return str(self._custom_workflow_entry(canonical_name).get("description") or "").strip()

    @staticmethod
    def _prompt_has_embedding(prompt, embedding):
        prompt = str(prompt or "").lower()
        embedding = str(embedding or "").strip().rstrip(",").lower()
        if not embedding:
            return False
        return bool(re.search(rf"(?<![\w:]){re.escape(embedding)}(?![\w:])", prompt))

    def _ensure_positive_settings(self):
        global_positive = self.get("global_positive_prompt")
        if not isinstance(global_positive, str):
            global_positive = _GLOBAL_POSITIVE_DEFAULT
            self.set("global_positive_prompt", global_positive)

        workflow_positives = self.get("workflow_positive_prompts", {})
        if not isinstance(workflow_positives, dict):
            workflow_positives = {}

        changed = False
        normalized = {}
        for name, value in workflow_positives.items():
            canonical = self._canonical_workflow_name(name)
            if isinstance(value, str):
                normalized[canonical] = value
                if canonical != name:
                    changed = True

        for wf_name, default_value in _BUILTIN_WORKFLOW_POSITIVE_DEFAULTS.items():
            if wf_name not in normalized:
                normalized[wf_name] = default_value
                changed = True

        if changed or workflow_positives != normalized:
            self.set("workflow_positive_prompts", normalized)

        return global_positive, normalized

    def _get_global_positive_prompt(self):
        return self._ensure_positive_settings()[0]

    def _set_global_positive_prompt(self, value):
        self.set("global_positive_prompt", str(value or "").strip())
        self._ensure_positive_settings()

    def _get_workflow_positive_prompts(self):
        return self._ensure_positive_settings()[1]

    def _set_workflow_positive_prompt(self, wf_name, value):
        wf_name = self._canonical_workflow_name(wf_name)
        _, workflow_positives = self._ensure_positive_settings()
        workflow_positives[wf_name] = str(value or "").strip()
        self.set("workflow_positive_prompts", workflow_positives)

    def _reset_workflow_positive_prompt(self, wf_name):
        wf_name = self._canonical_workflow_name(wf_name)
        _, workflow_positives = self._ensure_positive_settings()
        if wf_name in _BUILTIN_WORKFLOW_POSITIVE_DEFAULTS:
            workflow_positives[wf_name] = _BUILTIN_WORKFLOW_POSITIVE_DEFAULTS[wf_name]
        else:
            workflow_positives.pop(wf_name, None)
        self.set("workflow_positive_prompts", workflow_positives)

    @staticmethod
    def _clean_positive_value(value):
        return str(value or "").strip()

    def _resolve_positive_prompt(self, wf_name):
        wf_name = self._canonical_workflow_name(wf_name)
        global_positive, workflow_positives = self._ensure_positive_settings()
        if wf_name in workflow_positives:
            value = self._clean_positive_value(workflow_positives.get(wf_name))
            if value:
                if (
                    wf_name in _BUILTIN_WORKFLOW_POSITIVE_DEFAULTS
                    and value == _BUILTIN_WORKFLOW_POSITIVE_DEFAULTS.get(wf_name)
                ):
                    return value, "workflow"
                return value, "custom"
        global_value = self._clean_positive_value(global_positive)
        if global_value:
            return global_value, "global"
        default_value = self._clean_positive_value(_BUILTIN_WORKFLOW_POSITIVE_DEFAULTS.get(wf_name))
        if default_value:
            return default_value, "workflow"
        return "", "empty"

    def _apply_positive_prompt_preset(self, wf_name, positive):
        positive = str(positive or "").strip()
        preset, _ = self._resolve_positive_prompt(wf_name)
        preset = self._clean_positive_value(preset)
        if not positive or not preset:
            return positive
        if self._prompt_has_embedding(positive, preset) or positive.startswith(preset):
            return positive
        return f"{preset} {positive}".strip()

    def _ensure_negative_settings(self):
        global_negative = self.get("global_negative_prompt")
        if not isinstance(global_negative, str):
            global_negative = _GLOBAL_NEGATIVE_DEFAULT
            self.set("global_negative_prompt", global_negative)

        workflow_negatives = self.get("workflow_negative_prompts", {})
        if not isinstance(workflow_negatives, dict):
            workflow_negatives = {}

        changed = False
        normalized = {}
        for name, value in workflow_negatives.items():
            canonical = self._canonical_workflow_name(name)
            if isinstance(value, str):
                normalized[canonical] = value
                if canonical != name:
                    changed = True

        for wf_name, default_value in _BUILTIN_WORKFLOW_NEGATIVE_DEFAULTS.items():
            if wf_name not in normalized:
                normalized[wf_name] = default_value
                changed = True

        if changed or workflow_negatives != normalized:
            self.set("workflow_negative_prompts", normalized)

        return global_negative, normalized

    def _get_global_negative_prompt(self):
        return self._ensure_negative_settings()[0]

    def _set_global_negative_prompt(self, value):
        self.set("global_negative_prompt", str(value or "").strip())
        self._ensure_negative_settings()

    def _get_workflow_negative_prompts(self):
        return self._ensure_negative_settings()[1]

    def _set_workflow_negative_prompt(self, wf_name, value):
        wf_name = self._canonical_workflow_name(wf_name)
        _, workflow_negatives = self._ensure_negative_settings()
        workflow_negatives[wf_name] = str(value or "").strip()
        self.set("workflow_negative_prompts", workflow_negatives)

    def _reset_workflow_negative_prompt(self, wf_name):
        wf_name = self._canonical_workflow_name(wf_name)
        _, workflow_negatives = self._ensure_negative_settings()
        if wf_name in _BUILTIN_WORKFLOW_NEGATIVE_DEFAULTS:
            workflow_negatives[wf_name] = _BUILTIN_WORKFLOW_NEGATIVE_DEFAULTS[wf_name]
        else:
            workflow_negatives.pop(wf_name, None)
        self.set("workflow_negative_prompts", workflow_negatives)

    @staticmethod
    def _clean_negative_value(value):
        return str(value or "").strip()

    def _workflow_json_negative_prompt(self, wf_data):
        if not isinstance(wf_data, dict):
            return ""
        workflow = wf_data.get("workflow")
        mapping = wf_data.get("mapping", {})
        value = self._workflow_mapping_value(workflow, mapping.get("negative"))
        return value if isinstance(value, str) else ""

    def _resolve_negative_prompt(self, wf_name, wf_data=None):
        wf_name = self._canonical_workflow_name(wf_name)
        global_negative, workflow_negatives = self._ensure_negative_settings()
        if wf_name in workflow_negatives:
            value = self._clean_negative_value(workflow_negatives.get(wf_name))
            if value:
                return value, "custom"
        global_value = self._clean_negative_value(global_negative)
        if global_value:
            return global_value, "global"
        workflow_value = self._clean_negative_value(
            self._workflow_json_negative_prompt(wf_data)
        )
        if workflow_value:
            return workflow_value, "workflow"
        return "", "empty"

    def _negative_source_label(self, source):
        return self.strings(f"negative_source_{source}")

    def _preview_negative(self, value, limit=320):
        text = self._plain_text(str(value or "")).replace("\r", " ").strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            return self.strings("negative_not_set")
        if len(text) > limit:
            return text[: limit - 3].rstrip() + "..."
        return text

    def _format_negative_quote(self, value, limit=320):
        if limit is None:
            text = self._plain_text(str(value or "")).replace("\r", " ").strip()
            text = re.sub(r"\s+", " ", text)
            if not text:
                text = self.strings("negative_not_set")
        else:
            text = self._preview_negative(value, limit)
        return f"<blockquote expandable>{utils.escape_html(text)}</blockquote>"

    @staticmethod
    def _negative_source_icon(source):
        return {
            "custom": '<tg-emoji emoji-id="5280863578369311403">🟢</tg-emoji>',
            "global": '<tg-emoji emoji-id="5271842287326863410">🔵</tg-emoji>',
            "workflow": '<tg-emoji emoji-id="5280630189846451420">🟡</tg-emoji>',
            "empty": '<tg-emoji emoji-id="5348451945403137943">⚪️</tg-emoji>',
        }.get(source, '<tg-emoji emoji-id="5348451945403137943">⚪️</tg-emoji>')

    def _get_workflow_data(self, name):
        name = self._canonical_workflow_name(name)
        if name in self._BUILTIN_WORKFLOWS:
            cached_wf = self.get(self._builtin_workflow_cache_key(name))
            if not cached_wf:
                return None
            workflow = json.loads(json.dumps(cached_wf))
            mapping = self._parse_workflow(workflow)
            if name == _SDXL_REAL1_WORKFLOW_NAME:
                mapping.update({
                    "positive": {"node_id": "109", "field": "text"},
                    "negative": {"node_id": "6", "field": "text"},
                    "model": {"node_id": "3", "field": "ckpt_name"},
                    "model_nodes": [{"node_id": "3", "field": "ckpt_name"}, {"node_id": "36", "field": "ckpt_name"}],
                    "seed": {"node_id": "7", "field": "seed"},
                    "steps": {"node_id": "7", "field": "steps"},
                    "cfg": {"node_id": "7", "field": "cfg"},
                    "sampler_name": {"node_id": "7", "field": "sampler_name"},
                    "scheduler": {"node_id": "7", "field": "scheduler"},
                    "denoise": {"node_id": "7", "field": "denoise"},
                    "width": {"node_id": "18", "field": "width_override"},
                    "height": {"node_id": "18", "field": "height_override"},
                    "output": {"node_id": "128"},
                    "output_regular": {"node_id": "128"},
                })
            elif name == _SDXL_REAL2_WORKFLOW_NAME:
                mapping.update({
                    "positive": {"node_id": "109", "field": "text"},
                    "negative": {"node_id": "6", "field": "text"},
                    "model": {"node_id": "3", "field": "ckpt_name"},
                    "model_nodes": [{"node_id": "3", "field": "ckpt_name"}],
                    "seed": {"node_id": "7", "field": "seed"},
                    "steps": {"node_id": "7", "field": "steps"},
                    "cfg": {"node_id": "7", "field": "cfg"},
                    "sampler_name": {"node_id": "7", "field": "sampler_name"},
                    "scheduler": {"node_id": "7", "field": "scheduler"},
                    "denoise": {"node_id": "7", "field": "denoise"},
                    "width": {"node_id": "18", "field": "width_override"},
                    "height": {"node_id": "18", "field": "height_override"},
                    "scale_by": {"node_id": "143", "field": "scale_by"},
                    "output": {"node_id": "128"},
                    "output_regular": {"node_id": "128"},
                })
            elif name == _ERNIE_WORKFLOW_NAME:
                mapping.update({
                    "positive": {"node_id": "111", "field": "text"},
                    "model": {"node_id": "124", "field": "unet_name"},
                    "model_nodes": [{"node_id": "124", "field": "unet_name"}],
                    "seed": {"node_id": "110", "field": "seed"},
                    "steps": {"node_id": "110", "field": "steps"},
                    "cfg": {"node_id": "110", "field": "cfg"},
                    "sampler_name": {"node_id": "110", "field": "sampler_name"},
                    "scheduler": {"node_id": "110", "field": "scheduler"},
                    "denoise": {"node_id": "110", "field": "denoise"},
                    "width": {"node_id": "107", "field": "width"},
                    "height": {"node_id": "107", "field": "height"},
                    "scale_by": {"node_id": "153", "field": "scale_by"},
                    "output": {"node_id": "148"},
                    "output_regular": {"node_id": "148"},
                })
            return {
                "workflow": workflow,
                "mapping": mapping,
            }

        custom = self.get("workflows", {})
        wf_entry = custom.get(name) if isinstance(custom, dict) else None
        if wf_entry and isinstance(wf_entry, dict) and "workflow" in wf_entry:
            workflow = self._normalize_workflow_format(json.loads(json.dumps(wf_entry["workflow"])))
            return {
                "workflow": workflow,
                "mapping": self._parse_workflow(workflow),
                "description": str(wf_entry.get("description") or "").strip(),
            }
        return None

    async def _ensure_builtin_workflow(self, wf_name=_ANIME_WORKFLOW_NAME, force=False):
        wf_name = self._canonical_workflow_name(wf_name)
        cache_key = self._builtin_workflow_cache_key(wf_name)
        if self.get(cache_key) and not force:
            return True
        current_time = time.time()
        last_retry = self._last_builtin_wf_retry.get(wf_name, 0) if isinstance(self._last_builtin_wf_retry, dict) else 0
        if not force and current_time - last_retry < self._builtin_wf_retry_interval:
            return False
        async with self._builtin_wf_lock:
            if self.get(cache_key) and not force:
                return True
            current_time = time.time()
            last_retry = self._last_builtin_wf_retry.get(wf_name, 0) if isinstance(self._last_builtin_wf_retry, dict) else 0
            if not force and current_time - last_retry < self._builtin_wf_retry_interval:
                return False
            self._last_builtin_wf_retry[wf_name] = current_time
            try:
                await self._fetch_builtin_workflow(wf_name, force=force)
                self._builtin_wf_load_failed = False
                return bool(self.get(cache_key))
            except Exception as e:
                self._builtin_wf_load_failed = True
                logger.exception(e)
                return False

    async def _ensure_workflow_data(self, name):
        name = self._canonical_workflow_name(name)
        if name in self._BUILTIN_WORKFLOWS and not self.get(self._builtin_workflow_cache_key(name)):
            await self._ensure_builtin_workflow(name)
        return self._get_workflow_data(name)

    def _get_all_workflow_names(self):
        custom = self.get("workflows", {})
        return list(self._BUILTIN_WORKFLOWS) + list(custom.keys())

    async def _health_check(self, attempts=4, on_retry=None):
        base = self._base_url()
        if not base:
            return False
        retry_statuses = {408, 425, 429, 500, 502, 503, 504}
        delays = (2, 3, 5)
        attempts = max(1, int(attempts or 1))
        for attempt in range(attempts):
            try:
                async with self._session_get(
                    f"{base}/system_stats",
                    timeout=aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["queue_status"]),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.debug("ComfyUI health check failed (HTTP %s)", resp.status)
                    if resp.status not in retry_statuses:
                        return False
            except Exception as e:
                logger.debug("ComfyUI health check failed: %s", e)
            if attempt < attempts - 1:
                if on_retry:
                    try:
                        await on_retry(attempt + 2, attempts)
                    except Exception as e:
                        logger.debug("ComfyUI retry status update failed: %s", e)
                await asyncio.sleep(delays[min(attempt, len(delays) - 1)])
        return False

    async def _get_object_info(self, class_type: str, attempts=2, timeout=15):
        base = self._base_url()
        if not base:
            return None
        cache_key = f"object_info:{base}:{class_type}"
        if cache_key in self._comfy_cache:
            return self._comfy_cache[cache_key]
        retry_statuses = {408, 425, 429, 500, 502, 503, 504}
        attempts = max(1, int(attempts or 1))
        for attempt in range(attempts):
            try:
                async with self._session_get(
                    f"{base}/object_info/{class_type}",
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._comfy_cache[cache_key] = data
                        return data
                    logger.debug("ComfyUI object_info for %s failed (HTTP %s)", class_type, resp.status)
                    if resp.status not in retry_statuses:
                        return None
            except Exception as e:
                logger.debug("ComfyUI object_info for %s failed: %s", class_type, e)
            if attempt < attempts - 1:
                await asyncio.sleep(2)
        return None

    async def _get_all_object_info(self, attempts=2):
        base = self._base_url()
        if not base:
            return None
        cache_key = f"object_info:{base}:all"
        if cache_key in self._comfy_cache:
            return self._comfy_cache[cache_key]
        retry_statuses = {408, 425, 429, 500, 502, 503, 504}
        attempts = max(1, int(attempts or 1))
        for attempt in range(attempts):
            try:
                async with self._session_get(
                    f"{base}/object_info",
                    timeout=aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["object_info_all"]),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._comfy_cache[cache_key] = data
                        return data
                    logger.debug("ComfyUI object_info failed (HTTP %s)", resp.status)
                    if resp.status not in retry_statuses:
                        return None
            except Exception as e:
                logger.debug("ComfyUI object_info failed: %s", e)
            if attempt < attempts - 1:
                await asyncio.sleep(2)
        return None

    async def _free_comfy_memory(self):
        base = self._base_url()
        if not base:
            raise UserFacingError("connection", self._plain_text(self.strings("no_url")))
        async with self._session_post(
            f"{base}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                self._comfy_cache.clear()
                return True
            text = await resp.text()
            logger.error("ComfyUI free memory failed (HTTP %s): %s", resp.status, text[:500])
            raise ValueError(f"HTTP {resp.status}")

    async def _clear_comfy_queue(self):
        base = self._base_url()
        if not base:
            return False
        try:
            async with self._session_post(
                f"{base}/queue",
                json={"clear": True},
                timeout=aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["queue_status"]),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug("ComfyUI queue clear failed: %s", e)
            return False

    async def _force_free_comfy_memory(self):
        self._cancel_flags.clear()
        self._generation_runtime.clear()
        self._active_generations = 0
        await self._interrupt_generation()
        await self._clear_comfy_queue()
        return await self._free_comfy_memory()

    async def _queue_prompt(self, workflow_json, client_id):
        base = self._base_url()
        payload = {"prompt": workflow_json, "client_id": client_id}
        async with self._session_post(
            f"{base}/prompt",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["queue_prompt"]),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            text = await resp.text()
            if resp.status in (502, 503, 504):
                logger.warning("ComfyUI prompt queue temporary failure (HTTP %s): %s", resp.status, text[:1000])
            else:
                logger.error("ComfyUI prompt queue failed (HTTP %s): %s", resp.status, text[:1000])
            raise ComfyUIHTTPError(resp.status, text)

    @staticmethod
    def _queue_item_has_prompt(item, prompt_id):
        target = str(prompt_id)
        if isinstance(item, dict):
            return any(ComfyImageGenMod._queue_item_has_prompt(value, target) for value in item.values())
        if isinstance(item, (list, tuple, set)):
            return any(ComfyImageGenMod._queue_item_has_prompt(value, target) for value in item)
        return str(item) == target

    def _find_prompt_queue_position(self, items, prompt_id):
        for index, item in enumerate(items or [], start=1):
            if self._queue_item_has_prompt(item, prompt_id):
                return index
        return None

    @staticmethod
    def _looks_like_prompt_id(value):
        value = str(value or "")
        return bool(re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            value,
        ))

    @classmethod
    def _extract_queue_prompt_id(cls, item):
        if isinstance(item, dict):
            for key in ("prompt_id", "id"):
                value = item.get(key)
                if cls._looks_like_prompt_id(value):
                    return str(value)
            for value in item.values():
                prompt_id = cls._extract_queue_prompt_id(value)
                if prompt_id:
                    return prompt_id
            return None
        if isinstance(item, (list, tuple)):
            if len(item) > 1 and cls._looks_like_prompt_id(item[1]):
                return str(item[1])
            for value in item:
                prompt_id = cls._extract_queue_prompt_id(value)
                if prompt_id:
                    return prompt_id
            return None
        if cls._looks_like_prompt_id(item):
            return str(item)
        return None

    async def _get_queue_snapshot(self, timeout=None):
        base = self._base_url()
        if not base:
            return {"ok": False, "queue_running": [], "queue_pending": []}
        timeout = _COMFY_TIMEOUTS["queue_status"] if timeout is None else timeout
        try:
            async with self._session_get(
                f"{base}/queue",
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    return {"ok": False, "queue_running": [], "queue_pending": []}
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.debug("ComfyUI queue snapshot failed: %s", e)
            return {"ok": False, "queue_running": [], "queue_pending": []}
        if not isinstance(data, dict):
            return {"ok": False, "queue_running": [], "queue_pending": []}
        running = data.get("queue_running") or []
        pending = data.get("queue_pending") or []
        if not isinstance(running, list):
            running = []
        if not isinstance(pending, list):
            pending = []
        running_prompt_id = self._extract_queue_prompt_id(running[0]) if running else None
        return {
            "ok": True,
            "queue_running": running,
            "queue_pending": pending,
            "running_count": len(running),
            "pending_count": len(pending),
            "running_prompt_id": running_prompt_id,
            "active": bool(running or pending),
        }

    async def _get_prompt_queue_info(self, prompt_id, timeout=None):
        if not prompt_id:
            return {"state": None, "position": None}
        snapshot = await self._get_queue_snapshot(timeout=timeout)
        if not snapshot.get("ok"):
            return {"state": None, "position": None}
        running = snapshot.get("queue_running") or []
        pending = snapshot.get("queue_pending") or []
        for item in running:
            if self._queue_item_has_prompt(item, prompt_id):
                return {
                    "state": "running",
                    "position": None,
                    "running_other": False,
                    "running_count": snapshot.get("running_count", 0),
                    "pending_count": snapshot.get("pending_count", 0),
                    "running_prompt_id": snapshot.get("running_prompt_id"),
                }
        position = self._find_prompt_queue_position(pending, prompt_id)
        if position is not None:
            return {
                "state": "pending",
                "position": position,
                "running_other": bool(running),
                "running_count": snapshot.get("running_count", 0),
                "pending_count": snapshot.get("pending_count", 0),
                "running_prompt_id": snapshot.get("running_prompt_id"),
            }
        return {
            "state": None,
            "position": None,
            "running_other": bool(running),
            "running_count": snapshot.get("running_count", 0),
            "pending_count": snapshot.get("pending_count", 0),
            "running_prompt_id": snapshot.get("running_prompt_id"),
        }

    async def _get_prompt_queue_state(self, prompt_id):
        return (await self._get_prompt_queue_info(prompt_id)).get("state")

    async def _delete_queued_prompt(self, prompt_id):
        base = self._base_url()
        if not base or not prompt_id:
            return False
        try:
            async with self._session_post(
                f"{base}/queue",
                json={"delete": [prompt_id]},
                timeout=aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["queue_delete"]),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug("ComfyUI queue delete failed: %s", e)
            return False

    async def _cancel_runtime_generation(self, client_id: str):
        runtime = self._generation_runtime.get(client_id)
        if not runtime:
            return False
        runtime["phase"] = "cancelled"
        runtime["cancelled"] = True
        prompt_id = runtime.get("prompt_id")
        if not prompt_id:
            return False
        queue_state = await self._get_prompt_queue_state(prompt_id)
        if queue_state == "running":
            await self._interrupt_generation(prompt_id)
            return True
        if queue_state == "pending":
            return await self._delete_queued_prompt(prompt_id)
        return False

    def _set_generation_phase(self, client_id: str, phase: str):
        runtime = self._generation_runtime.get(client_id)
        if runtime is not None:
            runtime["phase"] = phase

    def _cleanup_generation_runtime(self, client_id: str):
        self._cancel_flags.pop(client_id, None)
        self._generation_runtime.pop(client_id, None)

    def _set_cancel_reason(self, client_id: str, reason: str):
        runtime = self._generation_runtime.get(client_id)
        if isinstance(runtime, dict) and not runtime.get("cancel_reason"):
            runtime["cancel_reason"] = str(reason or "unknown")

    def _get_cancel_reason(self, client_id: str):
        runtime = self._generation_runtime.get(client_id)
        if isinstance(runtime, dict):
            return runtime.get("cancel_reason")
        return None

    async def _raise_if_generation_cancelled(self, client_id: str):
        if self._cancel_flags.get(client_id, False):
            self._set_cancel_reason(client_id, "cancel_flag")
            await self._cancel_runtime_generation(client_id)
            raise asyncio.CancelledError()

    def _queue_status_text(self, queue_info, idle=False):
        state = (queue_info or {}).get("state")
        if state == "pending":
            position = (queue_info or {}).get("position")
            if (queue_info or {}).get("running_other"):
                if position is not None:
                    return self.strings("queue_comfy_other_running").format(position)
                return self.strings("queue_comfy_other_running_unknown")
            if position is not None:
                return self.strings("queue_comfy_pending").format(position)
            return self.strings("queue_comfy_pending_unknown")
        if state == "running":
            if (queue_info or {}).get("ws_fallback"):
                return self.strings("queue_comfy_running_ws_fallback")
            return self.strings("queue_comfy_running")
        if idle:
            return self.strings("queue_idle_warning")
        return self.strings("queue_comfy_submitted")

    def _runtime_by_prompt_id(self, prompt_id):
        if not prompt_id:
            return None
        target = str(prompt_id)
        for runtime in list(self._generation_runtime.values()):
            if isinstance(runtime, dict) and str(runtime.get("prompt_id")) == target:
                return runtime
        return None

    def _format_cmon_text(self, snapshot):
        lines = [self.strings("cmon_title")]
        if not snapshot.get("ok"):
            lines.append(f"<blockquote>{self.strings('cmon_unavailable')}</blockquote>")
            return self._to_inline_emoji("\n".join(lines))

        running_prompt_id = snapshot.get("running_prompt_id")
        details = []
        runtime = self._runtime_by_prompt_id(running_prompt_id)
        if running_prompt_id and runtime:
            details.append(self.strings("cmon_active").format(utils.escape_html(running_prompt_id)))
        elif running_prompt_id:
            details.append(self.strings("cmon_active_other").format(utils.escape_html(running_prompt_id)))
        elif snapshot.get("running_count"):
            details.append(self.strings("cmon_active_unknown"))
        else:
            details.append(self.strings("cmon_no_tasks"))

        if runtime:
            current_node_id = runtime.get("current_node_id")
            if current_node_id is not None:
                node_info = self._get_node_status_info(runtime.get("workflow"), current_node_id)
                node_status = (
                    node_info.get("text")
                    if isinstance(node_info, dict) and node_info.get("text")
                    else self.strings("fmt_running_node").format(utils.escape_html(str(current_node_id)))
                )
                details.append(self.strings("cmon_current_node").format(node_status))
            progress_pct = runtime.get("progress_pct")
            if progress_pct is not None:
                details.append(self.strings("cmon_progress").format(int(progress_pct)))

        details.append(self.strings("cmon_last_check").format(time.strftime("%H:%M:%S")))
        lines.append(f"<blockquote expandable>{chr(10).join(details)}</blockquote>")
        return self._to_inline_emoji("\n".join(lines))

    async def _cmon_loop(self, state_id, form):
        idle_since = None
        try:
            while not self._unloading:
                snapshot = await self._get_queue_snapshot(timeout=5)
                now = time.monotonic()
                if snapshot.get("running_count"):
                    idle_since = None
                else:
                    if idle_since is None:
                        idle_since = now
                    elif now - idle_since >= _CMON_IDLE_CLOSE_AFTER:
                        try:
                            await self._edit_cmon_form(
                                form,
                                self._to_inline_emoji(self.strings("cmon_closed_idle")),
                                None,
                            )
                        except Exception:
                            pass
                        try:
                            await asyncio.sleep(2)
                            await form.delete()
                        except Exception:
                            pass
                        return
                markup = [[{
                    "text": self.strings("btn_close"),
                    "callback": self._cmon_close,
                    "args": (state_id,),
                    "style": "danger",
                }]]
                try:
                    await self._edit_cmon_form(form, self._format_cmon_text(snapshot), markup)
                except Exception as e:
                    if self._is_cmon_dead_form_error(e):
                        logger.debug("Stopping cmon loop for dead form: %s", e)
                        return
                    logger.debug("Failed to update cmon form: %s", e)
                await asyncio.sleep(_CMON_POLL_INTERVAL)
        except asyncio.CancelledError:
            raise
        finally:
            entry = self._cmon_tasks.get(state_id)
            if isinstance(entry, dict) and entry.get("task") is asyncio.current_task():
                self._cmon_tasks.pop(state_id, None)

    async def _cmon_close(self, call: InlineCall, state_id: str):
        entry = self._cmon_tasks.pop(state_id, None)
        task = entry.get("task") if isinstance(entry, dict) else entry
        if task:
            task.cancel()
        try:
            await call.delete()
        except Exception as e:
            if not self._is_cmon_dead_form_error(e):
                logger.debug("Failed to close cmon form: %s", e)
        try:
            await call.answer()
        except Exception:
            pass

    async def _close_cmon_entry(self, state_id):
        entry = self._cmon_tasks.pop(state_id, None)
        if not entry:
            return
        task = entry.get("task") if isinstance(entry, dict) else entry
        form = entry.get("form") if isinstance(entry, dict) else None
        if task:
            task.cancel()
        if form:
            try:
                await form.delete()
            except Exception as e:
                if not self._is_cmon_dead_form_error(e):
                    logger.debug("Failed to delete previous cmon form: %s", e)

    def _cmon_state_id(self, message):
        try:
            chat_id = utils.get_chat_id(message)
        except Exception:
            chat_id = getattr(message, "chat_id", None) or "unknown"
        sender_id = getattr(message, "sender_id", None) or self.tg_id or 0
        return f"{chat_id}:{sender_id}"

    @staticmethod
    def _is_cmon_dead_form_error(error):
        text = f"{type(error).__name__}: {error}".lower()
        return any(
            marker in text
            for marker in (
                "msg not found",
                "messageidinvalid",
                "message id invalid",
                "messagedeleteforbidden",
                "message delete forbidden",
                "message to delete not found",
                "inline message id invalid",
                "message not found",
            )
        )

    async def _edit_cmon_form(self, form, text, reply_markup):
        text = self._apply_emoji_theme(text)
        if hasattr(form, "edit") and callable(form.edit):
            await form.edit(text=text, reply_markup=reply_markup)
            return True
        form_data = form if isinstance(form, dict) else getattr(form, "form", {}) or {}
        if isinstance(form_data, dict):
            unit_id = form_data.get("id") or form_data.get("uid") or getattr(form, "unit_id", None)
            if unit_id and hasattr(self.inline, "_edit_unit"):
                await self.inline._edit_unit(
                    text=text,
                    reply_markup=reply_markup,
                    unit_id=unit_id,
                )
                return True
        return False

    async def _create_cmon_form(self, message, text, reply_markup):
        return await self.inline.form(
            message=message,
            text=self._apply_emoji_theme(text),
            reply_markup=reply_markup,
        )

    @staticmethod
    def _extract_ws_progress_pct(dtype, ddata, prompt_id, current_node_id=None):
        if not isinstance(ddata, dict):
            return None

        def _percent(value, max_val):
            try:
                max_val = float(max_val)
                if not max_val:
                    return 0
                return max(0, min(100, int(float(value) / max_val * 100)))
            except (TypeError, ValueError, ZeroDivisionError):
                return None

        if dtype == "progress":
            progress_prompt_id = ddata.get("prompt_id")
            if progress_prompt_id != prompt_id:
                return None
            value = ddata.get("value", 0)
            max_val = ddata.get("max", 1)
            return _percent(value, max_val)

        if dtype == "progress_state":
            if ddata.get("prompt_id") != prompt_id:
                return None
            nodes = ddata.get("nodes", {})
            if not isinstance(nodes, dict):
                return None
            candidates = []
            if current_node_id is not None:
                node_state = nodes.get(str(current_node_id))
                if isinstance(node_state, dict):
                    candidates.append(node_state)
            candidates.extend(
                node_state
                for node_state in nodes.values()
                if isinstance(node_state, dict)
                and str(node_state.get("state", "")).lower() == "running"
            )
            for node_state in candidates:
                pct = _percent(node_state.get("value", 0), node_state.get("max", 1))
                if pct is not None:
                    return pct

        return None

    @staticmethod
    def _normalize_ws_timestamp(value):
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        if timestamp > 100000000000:
            timestamp /= 1000
        return timestamp

    @staticmethod
    def _runtime_duration(runtime, now=None):
        if not isinstance(runtime, dict):
            return None
        start_ts = runtime.get("server_start_ts")
        end_ts = runtime.get("server_end_ts")
        if start_ts is not None and end_ts is not None and end_ts >= start_ts:
            return end_ts - start_ts
        if runtime.get("duration") is not None:
            return runtime.get("duration")
        local_start = runtime.get("local_start")
        if local_start is not None:
            current = runtime.get("local_end")
            if current is None:
                current = time.monotonic() if now is None else now
            if current >= local_start:
                return current - local_start
        return runtime.get("duration")

    @staticmethod
    def _runtime_has_started(runtime):
        if not isinstance(runtime, dict):
            return False
        return bool(
            runtime.get("server_start_ts") is not None
            or runtime.get("local_start") is not None
            or runtime.get("duration") is not None
            or runtime.get("phase") in ("running", "finishing", "finished", "uploading")
        )

    def _mark_runtime_running(self, client_id: str, current_node_id=None):
        runtime = self._generation_runtime.get(client_id)
        if runtime is None:
            return
        runtime["phase"] = "running"
        runtime["executing"] = True
        if current_node_id is not None:
            runtime["current_node_id"] = str(current_node_id)
        if runtime.get("local_start") is None:
            runtime["local_start"] = time.monotonic()

    def _mark_runtime_finished(self, client_id: str, ddata=None, generation_state=None):
        runtime = self._generation_runtime.get(client_id)
        if runtime is None:
            return
        now = time.monotonic()
        runtime["phase"] = "finished"
        runtime["executing"] = False
        runtime["current_node_id"] = None
        if runtime.get("local_start") is None:
            runtime["local_start"] = runtime.get("queued_at") or now
        runtime["local_end"] = now
        if isinstance(ddata, dict):
            timestamp = self._normalize_ws_timestamp(ddata.get("timestamp"))
            if timestamp is not None:
                runtime["server_end_ts"] = timestamp
        duration = self._runtime_duration(runtime)
        if duration is not None:
            runtime["duration"] = duration
            if generation_state is not None:
                generation_state["generation_duration"] = duration

    @staticmethod
    def _iter_history_messages(history):
        status = history.get("status") if isinstance(history, dict) else None
        if not isinstance(status, dict):
            return
        messages = status.get("messages") or []
        for item in messages:
            event_type = ""
            payload = {}
            if isinstance(item, (list, tuple)) and item:
                event_type = str(item[0] or "").lower()
                if len(item) > 1 and isinstance(item[1], dict):
                    payload = item[1]
            elif isinstance(item, dict):
                event_type = str(item.get("type") or item.get("event") or "").lower()
                payload = item
            yield event_type, payload

    def _apply_history_runtime_timestamps(self, client_id, history):
        runtime = self._generation_runtime.get(client_id)
        if runtime is None:
            return
        for event_type, payload in self._iter_history_messages(history):
            timestamp = self._normalize_ws_timestamp(payload.get("timestamp"))
            if timestamp is None:
                continue
            if event_type == "execution_start":
                runtime["server_start_ts"] = timestamp
            elif event_type in ("execution_success", "execution_complete", "execution_interrupted", "execution_error"):
                runtime["server_end_ts"] = timestamp

    def _store_generation_duration(self, generation_state, runtime, now=None):
        if generation_state is None:
            return None
        if not self._runtime_has_started(runtime):
            generation_state.pop("generation_duration", None)
            return None
        duration = self._runtime_duration(runtime, now)
        if duration is not None:
            generation_state["generation_duration"] = duration
        return duration

    @staticmethod
    def _comfy_execution_error_payload(error_payload=None, status=None):
        error_payload = error_payload if isinstance(error_payload, dict) else {}
        status = status if isinstance(status, dict) else {}
        message = (
            error_payload.get("exception_message")
            or error_payload.get("message")
            or status.get("message")
            or status.get("status_str")
            or "Execution error in ComfyUI"
        )
        extra_info = {
            key: error_payload.get(key)
            for key in ("node_id", "node_type", "node_title", "exception_type")
            if error_payload.get(key) is not None
        }
        error_json = {
            "error": {
                "type": error_payload.get("exception_type") or "execution_error",
                "message": str(message),
                "extra_info": extra_info,
            },
            "raw": error_payload,
        }
        for key in ("traceback", "current_inputs", "current_outputs", "executed"):
            if key in error_payload:
                error_json[key] = error_payload[key]
        if status:
            error_json["status"] = status
        return ComfyUIExecutionError(json.dumps(error_json, ensure_ascii=False))

    async def _wait_ws(self, client_id, queue_func, status_form=None, cancel_markup=None, display_positive="", display_model="", display_wf="", expected_output_node=None, timeout=_GENERATION_TIMEOUT, easter_egg=None, workflow=None, status_is_inline=True, generation_state=None):
        base = self._base_url()
        ws_url = base.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws?clientId={client_id}"
        prompt_id = None
        ready_history = None
        last_edit = 0
        last_queue_poll = 0
        last_history_poll = 0
        last_queue_status = None
        start = None
        deadline = None
        last_event_at = time.monotonic()
        idle_warned = False
        ws_update_interval = self._ws_update_interval()

        async def _update_status(status_text=None, is_progress=False, progress_pct=0, queue_info=None):
            if not status_form:
                return
            runtime = self._generation_runtime.get(client_id) or {}
            node_status = self._get_node_status_info(workflow, runtime.get("current_node_id"))
            effective_status = status_text
            if effective_status is None and node_status:
                effective_status = node_status.get("text")
            duration_text = None
            if self._show_generation_time_progress():
                duration = self._store_generation_duration(
                    generation_state,
                    runtime,
                    time.monotonic(),
                )
                duration_text = self._format_generation_time_value(duration)
            eta_text = None
            eta_seconds = self._estimate_generation_eta(
                generation_state,
                runtime,
                queue_info=queue_info,
                progress_pct=progress_pct if is_progress else None,
            )
            if eta_seconds is not None:
                eta_text = self._format_eta_value(eta_seconds)
                if eta_text and generation_state is not None and generation_state.get("generation_eta_initial") is None:
                    generation_state["generation_eta_initial"] = eta_seconds
            progress_text = self._format_status_text(
                display_positive,
                display_model,
                display_wf,
                is_inline=status_is_inline,
                is_progress=is_progress,
                progress_pct=progress_pct,
                easter_egg=easter_egg,
                status_text=effective_status,
                generation_time=duration_text,
                generation_eta=eta_text,
            )
            if status_is_inline:
                await status_form.edit(text=progress_text, reply_markup=cancel_markup)
            else:
                await utils.answer(status_form, self._apply_emoji_theme(progress_text))

        async def _queue_once():
            nonlocal prompt_id
            if prompt_id:
                return
            await self._raise_if_generation_cancelled(client_id)
            try:
                await _update_status(self.strings("fmt_encoding_prompt"))
            except Exception:
                pass
            queue_resp = queue_func() if callable(queue_func) else queue_func
            if asyncio.iscoroutine(queue_resp):
                queue_resp = await queue_resp
            prompt_id = queue_resp.get("prompt_id") if isinstance(queue_resp, dict) else None
            if not prompt_id:
                logger.error("ComfyUI returned no prompt_id: %s", queue_resp)
                raise ValueError("No prompt_id from ComfyUI")
            runtime = self._generation_runtime.get(client_id)
            if runtime is not None:
                runtime["prompt_id"] = prompt_id
                runtime["phase"] = "queued"
                runtime["queued_at"] = time.monotonic()
            if self._cancel_flags.get(client_id, False):
                self._set_cancel_reason(client_id, "cancel_flag_after_queue")
                await self._cancel_runtime_generation(client_id)
                raise asyncio.CancelledError()
            try:
                await _update_status(self.strings("queue_comfy_submitted"))
            except Exception:
                pass

        async def _poll_queue(force=False, idle=False):
            nonlocal last_queue_poll, last_queue_status, last_event_at, idle_warned
            if not prompt_id:
                return None
            now = time.monotonic()
            if not force and now - last_queue_poll < _QUEUE_POLL_INTERVAL:
                return None
            last_queue_poll = now
            queue_info = await self._get_prompt_queue_info(prompt_id, timeout=3)
            state = queue_info.get("state")
            runtime = self._generation_runtime.get(client_id)
            if runtime is not None:
                if state == "running":
                    self._mark_runtime_running(client_id)
                    last_event_at = now
                    idle_warned = False
                elif state == "pending":
                    runtime["phase"] = "queued"
                    runtime["executing"] = False
                elif state is None and runtime.get("phase") in ("queued", "running"):
                    queue_info["state"] = "running"
                    queue_info["ws_fallback"] = True
                    state = "running"
                    self._mark_runtime_running(client_id)
            status_text = self._queue_status_text(queue_info, idle=idle)
            if force or idle or state == "running" or status_text != last_queue_status:
                last_queue_status = status_text
                try:
                    await _update_status(status_text, queue_info=queue_info)
                except Exception:
                    pass
            return queue_info

        async def _poll_history(force=False):
            nonlocal last_history_poll, ready_history
            if ready_history is not None:
                return ready_history
            if not prompt_id:
                return None
            now = time.monotonic()
            if not force and now - last_history_poll < _HISTORY_POLL_INTERVAL:
                return None
            last_history_poll = now
            try:
                history = await self._fetch_history_once(
                    prompt_id,
                    expected_output_node,
                    timeout=3,
                    allow_finished=True,
                )
            except ComfyUIExecutionError:
                raise
            except Exception as e:
                logger.debug("ComfyUI history poll failed: %s", e)
                return None
            if history:
                ready_history = history
                self._apply_history_runtime_timestamps(client_id, history)
                self._mark_runtime_finished(client_id, generation_state=generation_state)
            return ready_history

        try:
            async with self._session_ws_connect(ws_url, timeout=_COMFY_TIMEOUTS["ws_connect"]) as ws:
                await _queue_once()
                start = time.time()
                deadline = start + timeout
                last_event_at = time.monotonic()
                await _poll_queue(force=True)
                while True:
                    now_time = time.time()
                    remaining = deadline - now_time
                    if remaining <= 0:
                        if await _poll_history(force=True):
                            break
                        if prompt_id:
                            await _poll_queue(force=True, idle=True)
                        raise asyncio.TimeoutError()
                    if self._unloading:
                        self._set_cancel_reason(client_id, "unloading")
                        await self._interrupt_generation(prompt_id)
                        raise asyncio.CancelledError()
                    if self._cancel_flags.get(client_id, False):
                        self._set_cancel_reason(client_id, "cancel_flag_wait_loop")
                        await self._cancel_runtime_generation(client_id)
                        raise asyncio.CancelledError()
                    if await _poll_history():
                        break
                    await _poll_queue()
                    try:
                        msg = await asyncio.wait_for(
                            ws.receive(),
                            timeout=min(1, max(0.1, remaining)),
                        )
                    except asyncio.TimeoutError:
                        if await _poll_history():
                            break
                        await _poll_queue()
                        if (
                            prompt_id
                            and not idle_warned
                            and time.monotonic() - last_event_at >= _GENERATION_IDLE_WARNING
                        ):
                            idle_warned = True
                            await _poll_queue(force=True, idle=True)
                        continue
                    if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    dtype = data.get("type")
                    ddata = data.get("data", {})
                    if ddata.get("prompt_id") == prompt_id:
                        last_event_at = time.monotonic()
                        idle_warned = False
                        runtime = self._generation_runtime.get(client_id)
                        if runtime is not None:
                            match dtype:
                                case "execution_start":
                                    self._mark_runtime_running(client_id)
                                    timestamp = self._normalize_ws_timestamp(ddata.get("timestamp"))
                                    if timestamp is not None:
                                        runtime["server_start_ts"] = timestamp
                                case "executing":
                                    if ddata.get("node") is not None:
                                        self._mark_runtime_running(client_id, ddata.get("node"))
                                    else:
                                        runtime["phase"] = "finishing"
                                        runtime["executing"] = False
                                        runtime["current_node_id"] = None
                                case "progress":
                                    self._mark_runtime_running(client_id, ddata.get("node"))
                                case "progress_state":
                                    self._mark_runtime_running(client_id)
                                    nodes = ddata.get("nodes", {})
                                    if isinstance(nodes, dict):
                                        running_nodes = [
                                            str(node_id)
                                            for node_id, node_state in nodes.items()
                                            if isinstance(node_state, dict)
                                            and str(node_state.get("state", "")).lower() == "running"
                                        ]
                                        if running_nodes:
                                            runtime["current_node_id"] = running_nodes[-1]
                                case "execution_cached":
                                    self._mark_runtime_running(client_id)
                                case "execution_success" | "execution_complete" | "execution_interrupted" | "execution_error":
                                    self._mark_runtime_finished(client_id, ddata, generation_state)
                    runtime = self._generation_runtime.get(client_id) or {}
                    pct = self._extract_ws_progress_pct(dtype, ddata, prompt_id, runtime.get("current_node_id"))
                    if pct is not None and runtime is not None:
                        runtime["progress_pct"] = pct
                    if status_form and ws_update_interval:
                        now = time.time()
                        if now - last_edit >= ws_update_interval:
                            last_edit = now
                            try:
                                runtime = self._generation_runtime.get(client_id) or {}
                                node_status = self._get_node_status_info(workflow, runtime.get("current_node_id"))
                                status_text = None
                                has_progress = pct is not None
                                if node_status:
                                    if not has_progress or node_status.get("known"):
                                        status_text = node_status.get("text")
                                if dtype == "execution_cached" and ddata.get("prompt_id") == prompt_id:
                                    cached_nodes = ddata.get("nodes") or []
                                    if isinstance(cached_nodes, list):
                                        status_text = self.strings("fmt_cached_nodes").format(len(cached_nodes))
                                await _update_status(status_text, has_progress, pct or 0)
                            except Exception:
                                pass
                    if dtype == "executed" and ddata.get("prompt_id") == prompt_id:
                        if expected_output_node and str(ddata.get("node")) != str(expected_output_node):
                            continue
                        self._mark_runtime_finished(client_id, ddata, generation_state)
                        break
                    if dtype == "executing" and ddata.get("prompt_id") == prompt_id and ddata.get("node") is None:
                        self._mark_runtime_finished(client_id, ddata, generation_state)
                        break
                    if dtype in ("execution_success", "execution_complete") and ddata.get("prompt_id") == prompt_id:
                        self._mark_runtime_finished(client_id, ddata, generation_state)
                        break
                    if dtype == "execution_interrupted" and ddata.get("prompt_id") == prompt_id:
                        self._set_cancel_reason(client_id, "execution_interrupted")
                        self._mark_runtime_finished(client_id, ddata, generation_state)
                        raise asyncio.CancelledError()
                    if dtype == "execution_error" and ddata.get("prompt_id") == prompt_id:
                        raise self._comfy_execution_error_payload(ddata)
                if ready_history is None:
                    remaining = (deadline - time.time()) if deadline else timeout
                    ready_history = await self._fetch_history(
                        prompt_id,
                        expected_output_node,
                        max(1, remaining),
                        allow_finished=True,
                        client_id=client_id,
                    )
                    self._apply_history_runtime_timestamps(client_id, ready_history)
                    self._mark_runtime_finished(client_id, generation_state=generation_state)
        except (aiohttp.ClientError, OSError):
            if prompt_id is None:
                await _queue_once()
            remaining = (deadline - time.time()) if deadline else timeout
            history = await self._fetch_history(
                prompt_id,
                expected_output_node,
                max(1, remaining),
                allow_finished=True,
                client_id=client_id,
            )
            self._apply_history_runtime_timestamps(client_id, history)
            self._mark_runtime_finished(client_id, generation_state=generation_state)
            return prompt_id, history
        finally:
            runtime = self._generation_runtime.get(client_id)
            if runtime is not None:
                self._store_generation_duration(generation_state, runtime, time.monotonic())
            self._cleanup_generation_runtime(client_id)
        if ready_history is not None:
            return prompt_id, ready_history
        raise asyncio.TimeoutError()

    async def _interrupt_generation(self, prompt_id=None):
        base = self._base_url()
        if not base:
            return
        try:
            kwargs = {"timeout": aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["interrupt"])}
            if prompt_id:
                kwargs["json"] = {"prompt_id": prompt_id}
            async with self._session_post(
                f"{base}/interrupt",
                **kwargs,
            ) as resp:
                pass
        except Exception:
            pass

    async def _cancel_generation(self, call: InlineCall, client_id: str):
        self._set_cancel_reason(client_id, "manual_cancel_button")
        self._cancel_flags[client_id] = True
        await self._cancel_runtime_generation(client_id)
        try:
            await call.edit(text=self.strings("cancelled"))
        except Exception:
            pass
        await asyncio.sleep(2)
        try:
            await call.delete()
        except Exception:
            pass

    def _history_has_expected_output(self, history, expected_output_node=None):
        return bool(
            self._extract_media_info(
                history,
                expected_output_node,
                ("videos", "video", "gifs", "audio", "images"),
            )
        )

    @staticmethod
    def _history_is_finished(history):
        if not isinstance(history, dict):
            return False
        status = history.get("status")
        if not isinstance(status, dict):
            return False
        if status.get("completed") is True:
            return True
        status_text = str(status.get("status_str") or status.get("status") or "").lower()
        return status_text in {"success", "completed", "complete"}

    def _history_execution_error(self, history):
        if not isinstance(history, dict):
            return None
        status = history.get("status")
        if not isinstance(status, dict):
            return None

        status_text = str(
            status.get("status_str") or status.get("status") or ""
        ).lower()
        messages = status.get("messages") or []
        error_payload = None

        for item in messages:
            event_type = ""
            payload = {}
            if isinstance(item, (list, tuple)) and item:
                event_type = str(item[0] or "").lower()
                if len(item) > 1 and isinstance(item[1], dict):
                    payload = item[1]
            elif isinstance(item, dict):
                event_type = str(item.get("type") or item.get("event") or "").lower()
                payload = item
            if event_type == "execution_error":
                error_payload = payload
                break

        if not error_payload:
            if "error" not in status_text and "failed" not in status_text:
                return None
            error_payload = {}

        if not error_payload:
            error_payload = {"message": status_text or "Execution error in ComfyUI"}
        return self._comfy_execution_error_payload(error_payload, status)

    async def _fetch_history_once(self, prompt_id, expected_output_node=None, timeout=None, allow_finished=False):
        base = self._base_url()
        if not base or not prompt_id:
            return None
        timeout = _COMFY_TIMEOUTS["history_request"] if timeout is None else timeout
        async with self._session_get(
            f"{base}/history/{prompt_id}",
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
        if prompt_id not in data:
            return None
        history = data[prompt_id]
        history_error = self._history_execution_error(history)
        if history_error:
            raise history_error
        if self._history_has_expected_output(history, expected_output_node):
            return history
        if allow_finished and self._history_is_finished(history):
            return history
        return None

    async def _fetch_history(self, prompt_id, expected_output_node=None, timeout=180, allow_finished=False, client_id=None):
        base = self._base_url()
        url = f"{base}/history/{prompt_id}"
        delay = 2
        start = time.time()
        last_error = None
        last_error_at = None
        while True:
            if time.time() - start >= timeout:
                if last_error:
                    raise last_error
                raise asyncio.TimeoutError()
            if (
                last_error
                and last_error_at
                and time.time() - last_error_at >= 30
                and isinstance(last_error, ValueError)
                and not isinstance(last_error, ComfyUIHTTPError)
            ):
                raise last_error
            if self._unloading:
                raise asyncio.CancelledError()
            if client_id:
                await self._raise_if_generation_cancelled(client_id)
            try:
                async with self._session_get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["history_request"]),
                ) as resp:
                    raw_text = await resp.text()
                    if resp.status == 200:
                        try:
                            data = json.loads(raw_text)
                        except json.JSONDecodeError:
                            content_type = resp.headers.get("Content-Type", "")
                            preview = re.sub(r"\s+", " ", raw_text[:500]).strip()
                            logger.warning(
                                "ComfyUI history returned non-JSON (content-type=%s): %s",
                                content_type,
                                preview,
                            )
                            last_error = UserFacingError("server_unavailable", self._plain_text(self.strings("unexpected_comfy_response")))
                            last_error_at = last_error_at or time.time()
                            await asyncio.sleep(delay)
                            continue
                        if prompt_id in data:
                            history = data[prompt_id]
                            history_error = self._history_execution_error(history)
                            if history_error:
                                raise history_error
                            if self._history_has_expected_output(history, expected_output_node):
                                return history
                            if allow_finished and self._history_is_finished(history):
                                return history
                        last_error = None
                        last_error_at = None
                    else:
                        if resp.status in (502, 503, 504):
                            logger.warning("ComfyUI history temporary failure (HTTP %s): %s", resp.status, raw_text[:500])
                            last_error = ComfyUIHTTPError(resp.status, raw_text)
                            last_error_at = last_error_at or time.time()
                        else:
                            logger.error("ComfyUI history failed (HTTP %s): %s", resp.status, raw_text[:500])
                            raise ComfyUIHTTPError(resp.status, raw_text)
            except ValueError:
                raise
            except asyncio.TimeoutError as e:
                last_error = e
                last_error_at = last_error_at or time.time()
                logger.debug("ComfyUI history request timed out")
            except (aiohttp.ClientError, OSError) as e:
                last_error = e
                last_error_at = last_error_at or time.time()
                logger.debug("ComfyUI history request failed: %s", e)
            await asyncio.sleep(delay)

    async def _upload_to_comfyui(self, img_bio, filename="input.png", content_type=None):
        base = self._base_url()
        content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = aiohttp.FormData()
        data.add_field(
            "image",
            img_bio,
            filename=filename,
            content_type=content_type,
        )
        async with self._session_post(
            f"{base}/upload/image",
            data=data,
            timeout=aiohttp.ClientTimeout(total=_COMFY_TIMEOUTS["upload_image"]),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                if resp.status in (502, 503, 504):
                    logger.warning("ComfyUI image upload temporary failure (HTTP %s): %s", resp.status, text[:500])
                else:
                    logger.error("ComfyUI image upload failed (HTTP %s): %s", resp.status, text[:500])
                raise ComfyUIHTTPError(resp.status, text)
            result = await resp.json()
            return result.get("name", filename)

    def _max_output_bytes(self):
        max_mb = self._coerce_int(self.config["max_output_mb"], 300, 1, 2000)
        return max_mb, max_mb * 1024 * 1024

    def _retrieve_media_timeout(self):
        max_mb, _ = self._max_output_bytes()
        sock_read = max(_COMFY_TIMEOUTS["retrieve_media"], min(3600, max_mb * 2))
        return aiohttp.ClientTimeout(total=None, sock_read=sock_read)

    @staticmethod
    def _file_size(file_obj):
        if not hasattr(file_obj, "seek") or not hasattr(file_obj, "tell"):
            return None
        pos = file_obj.tell()
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(pos)
        return size

    @staticmethod
    def _read_file_bytes(file_obj):
        file_obj.seek(0)
        data = file_obj.read()
        file_obj.seek(0)
        return data

    async def _retrieve_image(self, image_info):
        return await self._retrieve_comfy_media(image_info, "image")

    async def _retrieve_comfy_media(self, media_info, media_label="media"):
        base = self._base_url()
        filename = media_info.get("filename")
        subfolder = media_info.get("subfolder", "")
        folder_type = media_info.get("type", "output")
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type,
        }
        max_mb, max_bytes = self._max_output_bytes()
        async with self._session_get(
            f"{base}/view",
            params=params,
            timeout=self._retrieve_media_timeout(),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                if resp.status in (502, 503, 504):
                    logger.warning("ComfyUI %s retrieve temporary failure (HTTP %s), filename=%s: %s", media_label, resp.status, filename, text[:500])
                else:
                    logger.error("ComfyUI %s retrieve failed (HTTP %s), filename=%s: %s", media_label, resp.status, filename, text[:500])
                raise ComfyUIHTTPError(resp.status, text or f"Failed to retrieve {media_label}")
            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = None
                if declared_size and declared_size > max_bytes:
                    raise UserFacingError("output_too_large", max_mb=max_mb)

            suffix = "." + self._media_extension(media_info, media_label).lstrip(".")
            out = tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix="comfyimagegen_",
                suffix=suffix,
            )
            total = 0
            try:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise UserFacingError("output_too_large", max_mb=max_mb)
                    out.write(chunk)
                out.seek(0)
                return out
            except Exception:
                out.close()
                raise

    def _extract_image_info(self, history, expected_output_node_id=None):
        return self._extract_media_info(history, expected_output_node_id, ("images",))

    @staticmethod
    def _output_key_aliases(output_key):
        if output_key == "video":
            return ("video", "videos", "animated", "animations", "images")
        if output_key == "videos":
            return ("videos", "video", "animated", "animations", "images")
        if output_key == "gifs":
            return ("gifs", "gif", "animated", "animations", "images")
        if output_key == "animated":
            return ("animated", "animations", "videos", "video", "gifs", "images")
        return (output_key,)

    @staticmethod
    def _normalize_history_media_items(items):
        if isinstance(items, dict):
            return [items]
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []

    def _history_media_items(self, node_output, actual_key):
        if not isinstance(node_output, dict):
            return []
        items = self._normalize_history_media_items(node_output.get(actual_key, []))
        if items:
            return items
        ui = node_output.get("ui")
        if isinstance(ui, dict):
            return self._normalize_history_media_items(ui.get(actual_key, []))
        return []

    def _extract_media_info(self, history, expected_output_node_id=None, output_keys=None):
        output_keys = output_keys or ("videos", "video", "animated", "animations", "gifs", "images", "audio")
        outputs = history.get("outputs", {})
        if expected_output_node_id and expected_output_node_id in outputs:
            for output_key in output_keys:
                for actual_key in self._output_key_aliases(output_key):
                    items = self._history_media_items(outputs[expected_output_node_id], actual_key)
                    if items:
                        info = dict(items[0])
                        info.setdefault("output_key", actual_key)
                        return info

        for node_id, node_output in outputs.items():
            for output_key in output_keys:
                for actual_key in self._output_key_aliases(output_key):
                    items = self._history_media_items(node_output, actual_key)
                    if items:
                        info = dict(items[0])
                        info.setdefault("output_key", actual_key)
                        return info
        return None

    @staticmethod
    def _history_output_summary(history):
        outputs = history.get("outputs", {}) if isinstance(history, dict) else {}
        summary = {}
        for node_id, node_output in outputs.items():
            if not isinstance(node_output, dict):
                continue
            keys = [key for key, value in node_output.items() if value]
            ui = node_output.get("ui")
            if isinstance(ui, dict):
                keys.extend(f"ui.{key}" for key, value in ui.items() if value)
            summary[str(node_id)] = keys[:12]
        return summary

    @staticmethod
    def _media_extension(media_info, media_label="media"):
        filename = str((media_info or {}).get("filename") or "")
        if "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        fmt = str((media_info or {}).get("format") or "").lower()
        if "webp" in fmt:
            return "webp"
        if "gif" in fmt:
            return "gif"
        if "mp4" in fmt or "h264" in fmt or "h265" in fmt:
            return "mp4"
        if "webm" in fmt:
            return "webm"
        if "wav" in fmt:
            return "wav"
        if "audio" in fmt:
            return "wav"
        if media_label == "image":
            return "png"
        return "bin"

    @classmethod
    def _media_kind_from_info(cls, media_info, default="media"):
        ext = cls._media_extension(media_info, default)
        fmt = str((media_info or {}).get("format") or "").lower()
        output_key = str((media_info or {}).get("output_key") or "").lower()
        if (
            ext in {"mp4", "webm", "mkv", "mov", "avi", "m4v", "gif"}
            or any(token in fmt for token in ("video", "h264", "h265", "mp4", "webm", "gif"))
            or output_key in {"videos", "video", "gifs", "gif", "animated", "animations"}
        ):
            return "video"
        if ext in {"wav", "mp3", "ogg", "flac"} or "audio" in fmt or output_key == "audio":
            return "audio"
        if ext in {"png", "jpg", "jpeg", "webp", "bmp"} or output_key in {"images", "image"}:
            return "image"
        return default or "media"

    @classmethod
    def _telegram_photo_supported(cls, media_info):
        ext = cls._media_extension(media_info, "image")
        fmt = str((media_info or {}).get("format") or "").lower()
        if ext not in {"png", "jpg", "jpeg", "webp"}:
            return False
        if any(token in fmt for token in ("exr", "float", "16", "32")):
            return False
        return True

    def _next_node_id(self, workflow):
        max_id = 0
        for k in workflow.keys():
            try:
                max_id = max(max_id, int(k))
            except (ValueError, TypeError):
                pass
        return str(max_id + 1)

    async def _get_models_for_workflow_field(self, field):
        if field == "ckpt_name":
            return self._parse_object_info_list(
                await self._get_object_info("CheckpointLoaderSimple"),
                "CheckpointLoaderSimple",
                "ckpt_name",
            )
        if field in ("unet_name", "diffusion_model", "diffusion_model_name"):
            return self._parse_object_info_list(
                await self._get_object_info("UNETLoader"),
                "UNETLoader",
                "unet_name",
            )
        if field in ("patch_name", "model_patch", "model_patch_name"):
            return (await self._get_available_models_by_field()).get(field, [])
        return []

    @staticmethod
    def _is_model_filename(value):
        value = str(value or "").strip()
        return bool(
            value
            and re.search(
                r"\.(safetensors|ckpt|pt|pth|bin|gguf|onnx)$",
                value,
                re.IGNORECASE,
            )
        )

    async def _get_available_models_by_field(self):
        fields = {
            "ckpt_name": set(await self._get_models_for_workflow_field("ckpt_name")),
            "unet_name": set(await self._get_models_for_workflow_field("unet_name")),
        }
        fields["diffusion_model"] = set(fields["unet_name"])
        fields["diffusion_model_name"] = set(fields["unet_name"])

        object_info = await self._get_all_object_info()
        if isinstance(object_info, dict):
            for class_type, info in object_info.items():
                class_l = str(class_type).lower()
                if "patch" not in class_l:
                    continue
                input_data = info.get("input", {}) if isinstance(info, dict) else {}
                candidates = {}
                for section in ("required", "optional"):
                    values = input_data.get(section, {})
                    if isinstance(values, dict):
                        candidates.update(values)
                for field, raw in candidates.items():
                    field_l = str(field).lower()
                    if (
                        field not in ("patch_name", "model_patch", "model_patch_name", "model_name")
                        and "patch" not in field_l
                        and "model" not in field_l
                    ):
                        continue
                    values = []
                    if isinstance(raw, list) and raw and isinstance(raw[0], list):
                        values = [
                            item
                            for item in raw[0]
                            if isinstance(item, str) and self._is_model_filename(item)
                        ]
                    elif isinstance(raw, list):
                        values = [
                            item
                            for item in raw
                            if isinstance(item, str) and self._is_model_filename(item)
                        ]
                    if values:
                        fields.setdefault(field, set()).update(values)

        return {field: sorted(values) for field, values in fields.items() if values}

    @staticmethod
    def _model_field_group(field):
        if field == "ckpt_name":
            return "checkpoint"
        if field in ("unet_name", "diffusion_model", "diffusion_model_name"):
            return "unet"
        if field in ("patch_name", "model_patch", "model_patch_name") or "patch" in str(field).lower():
            return "patch"
        return field

    @classmethod
    def _model_field_is_compatible(cls, selected_fields, target_field):
        target_group = cls._model_field_group(target_field)
        return any(cls._model_field_group(field) == target_group for field in selected_fields)

    async def _get_selected_model_fields(self, model):
        field_models = await self._get_available_models_by_field()
        if not field_models:
            return None
        return {
            field
            for field, models in field_models.items()
            if model in models
        }

    def _get_workflow_primary_model(self, wf_data):
        mapping = wf_data.get("mapping", {}) if isinstance(wf_data, dict) else {}
        model_map = mapping.get("model")
        if not model_map:
            return None
        workflow = wf_data.get("workflow", {}) if isinstance(wf_data, dict) else {}
        return (
            workflow
            .get(model_map.get("node_id"), {})
            .get("inputs", {})
            .get(model_map.get("field"))
        )

    async def _resolve_workflow_model_for_node(self, workflow, item, model, selected_fields, force_selected_model=False):
        nid = item.get("node_id")
        field = item.get("field")
        original_model = (
            workflow
            .get(nid, {})
            .get("inputs", {})
            .get(field, "")
        )

        if not model:
            return original_model

        if selected_fields is None:
            return model

        if selected_fields and self._model_field_is_compatible(selected_fields, field):
            return model

        if (
            not selected_fields
            and self._is_model_filename(model)
            and (
                self._model_field_group(field) == "patch"
                or (
                    self._model_field_group(field) not in ("checkpoint", "unet")
                    and self._is_model_filename(original_model)
                )
            )
        ):
            return model

        if force_selected_model:
            return model

        return original_model or None

    async def _prepare_workflow(self, wf_data, positive, negative, seed, width, height, model, denoise, parsed_steps, parsed_cfg, sampler_name=None, scheduler=None, input_filename=None, wf_name=None, limited_mode=False, input_video_filename=None):
        workflow = json.loads(json.dumps(wf_data["workflow"]))
        mapping = wf_data["mapping"]

        final_output_node_for_extraction = None

        if self._impact_wildcard_select_text:
            for nid, node in workflow.items():
                if node.get("class_type") == "ImpactWildcardProcessor":
                    if "Select to add Wildcard" in node.get("inputs", {}):
                        workflow[nid]["inputs"]["Select to add Wildcard"] = self._impact_wildcard_select_text
                elif "DetailerPipe" in node.get("class_type", ""):
                    if "Select to add Wildcard" in node.get("inputs", {}):
                        workflow[nid]["inputs"]["Select to add Wildcard"] = self._impact_wildcard_select_text

        pos_map = mapping.get("positive")
        if pos_map and positive is not None:
            nid = pos_map["node_id"]
            fields = pos_map.get("fields") or pos_map.get("field")
            if isinstance(fields, str):
                fields = [fields]
            if not isinstance(fields, list):
                fields = []
            if nid in workflow:
                for field in fields:
                    workflow[nid]["inputs"][field] = positive
                if "wildcard_text" in fields and "populated_text" in workflow[nid]["inputs"]:
                    workflow[nid]["inputs"]["populated_text"] = positive

        neg_map = mapping.get("negative")
        if neg_map and negative is not None:
            nid = neg_map["node_id"]
            fields = neg_map.get("fields") or neg_map.get("field")
            if isinstance(fields, str):
                fields = [fields]
            if not isinstance(fields, list):
                fields = []
            if nid in workflow:
                for field in fields:
                    workflow[nid]["inputs"][field] = negative
                if "wildcard_text" in fields and "populated_text" in workflow[nid]["inputs"]:
                    workflow[nid]["inputs"]["populated_text"] = negative

        model_map = mapping.get("model")
        if model_map and model:
            selected_model_fields = await self._get_selected_model_fields(model)
            model_nodes = mapping.get("model_nodes") or [model_map]
            for item in model_nodes:
                nid = item.get("node_id")
                field = item.get("field")
                if nid in workflow and field in workflow[nid].get("inputs", {}):
                    force_selected_model = (
                        item.get("node_id") == model_map.get("node_id")
                        and item.get("field") == model_map.get("field")
                    )
                    resolved_model = await self._resolve_workflow_model_for_node(
                        workflow,
                        item,
                        model,
                        selected_model_fields,
                        force_selected_model=force_selected_model,
                    )
                    if resolved_model:
                        workflow[nid]["inputs"][field] = resolved_model

        sam_model_map = mapping.get("sam_model")
        if sam_model_map and self._available_sam_models:
            nid = sam_model_map["node_id"]
            field = sam_model_map["field"]
            if nid in workflow and field in workflow[nid]["inputs"]:
                desired = workflow[nid]["inputs"][field]
                desired_prefix = desired.rsplit(".", 1)[0] if "." in desired else desired

                found = None
                if desired in self._available_sam_models:
                    found = desired
                else:
                    for m in self._available_sam_models:
                        if m.startswith(desired_prefix):
                            found = m
                            break

                if found:
                    workflow[nid]["inputs"][field] = found

        seed_map = mapping.get("seed")
        if seed_map and not limited_mode:
            nid = seed_map["node_id"]
            field = seed_map["field"]
            if nid in workflow:
                workflow[nid]["inputs"][field] = seed if seed is not None else random.randint(1, 2**44)

        width_map = mapping.get("width")
        if width_map and width is not None:
            nid = width_map["node_id"]
            field = width_map["field"]
            if nid in workflow and not self._is_workflow_link(workflow[nid].get("inputs", {}).get(field)):
                workflow[nid]["inputs"][field] = width

        height_map = mapping.get("height")
        if height_map and height is not None:
            nid = height_map["node_id"]
            field = height_map["field"]
            if nid in workflow and not self._is_workflow_link(workflow[nid].get("inputs", {}).get(field)):
                workflow[nid]["inputs"][field] = height

        steps_map = mapping.get("steps")
        if steps_map and parsed_steps is not None:
            nid = steps_map["node_id"]
            field = steps_map["field"]
            if nid in workflow:
                workflow[nid]["inputs"][field] = parsed_steps

        cfg_map = mapping.get("cfg")
        if cfg_map and parsed_cfg is not None:
            nid = cfg_map["node_id"]
            field = cfg_map["field"]
            if nid in workflow:
                workflow[nid]["inputs"][field] = parsed_cfg

        sampler_map = mapping.get("sampler_name")
        if sampler_map and sampler_name:
            nid = sampler_map["node_id"]
            field = sampler_map["field"]
            if nid in workflow:
                workflow[nid]["inputs"][field] = sampler_name

        scheduler_map = mapping.get("scheduler")
        if scheduler_map and scheduler:
            nid = scheduler_map["node_id"]
            field = scheduler_map["field"]
            if nid in workflow:
                workflow[nid]["inputs"][field] = scheduler

        flux_guidance_map = mapping.get("flux_guidance")
        if flux_guidance_map and parsed_cfg is not None:
            nid = flux_guidance_map["node_id"]
            field = flux_guidance_map["field"]
            if nid in workflow:
                workflow[nid]["inputs"][field] = parsed_cfg

        megapixels_map = mapping.get("megapixels")
        if megapixels_map and width is not None and height is not None:
            megapixels_nodes = mapping.get("megapixels_nodes") or [megapixels_map]
            megapixels_value = round((width * height) / 1_000_000, 3)
            for item in megapixels_nodes:
                nid = item.get("node_id")
                field = item.get("field")
                if nid in workflow and field in workflow[nid].get("inputs", {}):
                    workflow[nid]["inputs"][field] = megapixels_value

        denoise_map = mapping.get("denoise")
        denoise_to_use = denoise
        if limited_mode:
            denoise_to_use = None
        elif denoise is None:
            if input_filename:
                denoise_to_use = 0.5
            else:
                denoise_to_use = 1.0

        if denoise_map and denoise_to_use is not None:
            nid = denoise_map["node_id"]
            field = denoise_map["field"]
            if nid in workflow:
                workflow[nid]["inputs"][field] = denoise_to_use

        if input_filename:
            input_image_map = mapping.get("input_image")
            input_image_maps = mapping.get("input_images") or []
            if input_image_map and input_image_map not in input_image_maps:
                input_image_maps = [input_image_map, *input_image_maps]
            handled_input_image = False
            for input_image_map in input_image_maps:
                if not input_image_map or input_image_map.get("node_id") not in workflow:
                    continue
                if input_image_map.get("expects_link"):
                    load_image_node_id = self._next_node_id(workflow)
                    workflow[load_image_node_id] = {
                        "inputs": {"image": input_filename},
                        "class_type": "LoadImage",
                        "_meta": {"title": "Load Image (Dynamic)"},
                    }
                    workflow[input_image_map["node_id"]]["inputs"][input_image_map["field"]] = [load_image_node_id, 0]
                else:
                    workflow[input_image_map["node_id"]]["inputs"][input_image_map["field"]] = input_filename
                handled_input_image = True

            if handled_input_image:
                latent_switch_map = mapping.get("latent_switch")
                if latent_switch_map:
                    nid = latent_switch_map["node_id"]
                    if nid in workflow:
                        workflow[nid]["inputs"]["select"] = 2
            else:
                latent_switch_map = mapping.get("latent_switch")
                if not latent_switch_map or latent_switch_map.get("node_id") not in workflow:
                    raise ValueError("img2img unsupported by workflow")

                load_image_node_id = self._next_node_id(workflow)
                workflow[load_image_node_id] = {
                    "inputs": {"image": input_filename},
                    "class_type": "LoadImage",
                    "_meta": {"title": "Load Image (Dynamic)"},
                }

                vae_encode_node_id = self._next_node_id(workflow)

                vae_output_node_info = mapping.get("vae_output_node")
                vae_source_node_id = None
                vae_source_output_index = 2

                if vae_output_node_info:
                    vae_source_node_id = vae_output_node_info["node_id"]
                    vae_source_output_index = vae_output_node_info.get("output_index", 2)
                else:
                    for nid, node in workflow.items():
                        if node.get("class_type") == "CheckpointLoaderSimple":
                            vae_source_node_id = nid
                            break

                if not vae_source_node_id:
                    logger.error("Could not determine VAE source node for i2i workflow")
                    raise ValueError("VAE source not found")

                workflow[vae_encode_node_id] = {
                    "inputs": {
                        "pixels": [load_image_node_id, 0],
                        "vae": [str(vae_source_node_id), vae_source_output_index],
                    },
                    "class_type": "VAEEncode",
                    "_meta": {"title": "VAE Encode (Dynamic)"},
                }

                nid = latent_switch_map["node_id"]
                workflow[nid]["inputs"]["select"] = 2
                workflow[nid]["inputs"]["input2"] = [vae_encode_node_id, 0]

        if input_video_filename:
            input_video_map = mapping.get("input_video")
            if input_video_map and input_video_map.get("node_id") in workflow:
                workflow[input_video_map["node_id"]]["inputs"][input_video_map["field"]] = input_video_filename
            else:
                raise ValueError("video input unsupported by workflow")

        workflow = await self._materialize_global_inputs(workflow)

        if final_output_node_for_extraction is None:
            if mapping.get("output_kind") in ("video", "mixed") and mapping.get("output_video"):
                final_output_node_for_extraction = mapping["output_video"]["node_id"]
            elif mapping.get("output_regular"):
                final_output_node_for_extraction = mapping["output_regular"]["node_id"]
            elif mapping.get("output_upscaled"):
                final_output_node_for_extraction = mapping["output_upscaled"]["node_id"]
            elif mapping.get("output"):
                final_output_node_for_extraction = mapping["output"]["node_id"]

        return workflow, final_output_node_for_extraction

    _REFUSAL_PHRASES = (
        "i cannot", "i can't", "i'm sorry", "i apologize", "i'm unable",
        "i am unable", "i am not able", "against my", "not appropriate",
        "i must decline", "i'm not able", "as an ai", "as a language model",
        "i'm afraid", "content policy", "violates", "inappropriate",
        "i won't", "i will not", "i do not", "i don't", "cannot assist",
        "cannot help", "cannot fulfill", "cannot comply", "cannot generate",
        "cannot create", "not able to", "not going to", "goes against",
        "against policy", "ethical guidelines", "safety guidelines",
        "harmful content", "explicit content", "sexual content",
        "not comfortable", "decline to", "refuse to", "unable to assist",
        "unable to help", "unable to generate", "unable to create",
        "beyond my capabilities", "outside my", "my guidelines",
        "my programming", "my ethical", "responsible ai",
        "я не могу", "к сожалению", "не в состоянии", "извините",
        "не могу помочь", "не могу создать", "не могу сгенерировать",
        "против правил", "нарушает", "неприемлем", "недопустим",
        "отказываюсь", "не имею права", "мне не разрешено",
    )

    _STRONG_REFUSAL_PHRASES = (
        "я не могу обработать",
        "не могу обработать этот запрос",
        "не могу выполнить этот запрос",
        "не могу помочь с этим запросом",
        "противоречит принципам безопасности",
        "принципам безопасности и этики",
        "незаконной и вредной деятельностью",
        "содержит контент, связанный с незаконной",
        "опасной деятельностью",
        "вредной деятельностью",
        "я не могу создать",
        "я не могу сгенерировать",
        "я не могу помочь",
        "я не могу выполнить",
        "не могу обработать",
        "не могу создать",
        "не могу сгенерировать",
        "не могу предоставить",
        "не могу продолжить",
        "не могу способствовать",
        "я не могу",
        "i can't process this request",
        "i cannot process this request",
        "i can't comply with this request",
        "i cannot comply with this request",
        "i can't help with this request",
        "i cannot help with this request",
        "safety and ethics",
        "illegal and harmful activity",
        "harmful illegal activity",
        "disallowed content",
        "i can't create",
        "i cannot create",
        "i can't generate",
        "i cannot generate",
    )

    def _is_refusal_response(self, text):
        lower = str(text or "").lower().strip()
        if any(phrase in lower for phrase in self._STRONG_REFUSAL_PHRASES):
            return True
        matches = sum(1 for phrase in self._REFUSAL_PHRASES if phrase in lower)
        return matches >= 2

    async def _enhance_prompt(self, user_prompt: str, model_name: str, image_path=None):
        provider = self._get_prompt_provider()
        system_prompt = await self._fetch_enhance_prompt(provider)
        if not system_prompt:
            return None, "error"
        self._enhance_system_prompt = system_prompt

        prompt = str(user_prompt or "").strip()

        if provider == "groq":
            result, error = await self._call_groq_enhance(prompt, model_name)
        elif provider == "openrouter":
            result, error = await self._call_openrouter_enhance(prompt, model_name)
        elif provider == "grok":
            result, error = await self._call_grok_enhance(prompt, model_name)
        elif provider == "deepseek":
            if image_path:
                return None, "vision_unsupported"
            result, error = await self._call_deepseek_enhance(prompt, model_name, image_path=image_path)
        else:
            result, error = await self._call_gemini_enhance(prompt, model_name)

        if result:
            if self._is_refusal_response(result):
                return None, "censored"
            return result, None
        return None, error

    async def _call_gemini_enhance(self, cleaned_prompt: str, model_name: str):
        if not GENAI_AVAILABLE:
            return None, "dependency_missing"

        api_key = self._get_provider_api_key("gemini")
        if not api_key:
            return None, "no_key"

        try:
            if not self._genai_client or self._genai_api_key != api_key:
                self._genai_client = genai.Client(api_key=api_key)
                self._genai_api_key = api_key
            config = genai_types.GenerateContentConfig(
                system_instruction=self._enhance_system_prompt,
                temperature=1.0,
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                safety_settings=[
                    genai_types.SafetySetting(category=cat, threshold="BLOCK_NONE")
                    for cat in [
                        "HARM_CATEGORY_HARASSMENT",
                        "HARM_CATEGORY_HATE_SPEECH",
                        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "HARM_CATEGORY_DANGEROUS_CONTENT",
                    ]
                ],
            )
            chat = self._genai_client.aio.chats.create(
                model=self._get_gemini_model(),
                config=config,
            )
            nonce = uuid.uuid4().hex[:12]
            ready_response = await asyncio.wait_for(
                chat.send_message(
                    "Confirm that you understand the image prompt enhancement task and the required output format. "
                    f"Reply exactly with READY:{nonce}"
                ),
                timeout=30,
            )
            ready_text = (ready_response.text or "").strip()
            if ready_text != f"READY:{nonce}":
                if self._is_refusal_response(ready_text):
                    return None, "censored"
                return None, "error"
            response = await asyncio.wait_for(
                chat.send_message(
                    f"user_prompt: {cleaned_prompt}\ntarget_model: {model_name}"
                ),
                timeout=60,
            )
            if response.text:
                result = response.text.strip().strip('"').strip("'").strip("`")
                if result:
                    if self._is_refusal_response(result):
                        return None, "censored"
                    return result, None
            if hasattr(response, "candidates") and response.candidates:
                finish_reason = getattr(response.candidates[0], "finish_reason", None)
                if finish_reason and str(finish_reason) in ("SAFETY", "2", "FinishReason.SAFETY"):
                    return None, "censored"
            return None, "error"
        except asyncio.TimeoutError:
            logger.warning("Gemini prompt enhancement timed out")
            return None, "timeout"
        except Exception as e:
            logger.exception(e)
            err_str = str(e).lower()
            status = getattr(e, "status_code", None) or getattr(e, "code", None)
            try:
                status = int(status)
            except (TypeError, ValueError):
                status = None
            if status == 429 or any(
                marker in err_str
                for marker in ("429", "quota", "rate limit", "resource_exhausted")
            ):
                return None, "rate_limit"
            if status in (401, 403) or any(
                marker in err_str
                for marker in (
                    "401",
                    "403",
                    "api key not valid",
                    "invalid api key",
                    "api_key_invalid",
                    "unauthenticated",
                    "permission denied",
                )
            ):
                return None, "expired"
            return None, "error"

    async def _call_openai_compatible_enhance(
        self, cleaned_prompt: str, model_name: str, api_key: str, base_url: str, models_list: list, provider_name: str, image_path=None,
    ):
        last_error = None
        for model in models_list:
            user_content = self._build_openai_compatible_user_content(
                cleaned_prompt,
                model_name,
                image_path=image_path,
            )
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": self._enhance_system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 1.0,
                "max_tokens": 2048,
            }

            try:
                async with self._session_post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status in (401, 403):
                        return None, "expired"
                    if resp.status == 429:
                        last_error = "rate_limit"
                        continue
                    if resp.status != 200:
                        resp_text = await resp.text()
                        logger.debug("%s API error (model=%s, status=%s): %s", provider_name, model, resp.status, resp_text[:500])
                        try:
                            err_data = json.loads(resp_text)
                            err_msg = err_data.get("error", {}).get("message", resp_text[:200])
                        except json.JSONDecodeError:
                            err_msg = resp_text[:200]
                        if "not found" in resp_text.lower() or "decommissioned" in resp_text.lower() or "not available" in resp_text.lower():
                            last_error = f"model {model} unavailable"
                            continue
                        last_error = err_msg
                        continue
                    data = await resp.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    if "<think>" in content and "</think>" in content:
                        content = content.split("</think>", 1)[1]
                    result = content.strip().strip('"').strip("'").strip("`")
                    if result:
                        if self._is_refusal_response(result):
                            return None, "censored"
                        return result, None
                    return None, "censored"
            except asyncio.TimeoutError:
                last_error = "timeout"
                continue
            except Exception as e:
                logger.exception(e)
                last_error = str(e)
                continue

        if last_error == "rate_limit":
            return None, "rate_limit"
        return None, last_error or "error"

    def _build_openai_compatible_user_content(self, cleaned_prompt, model_name, image_path=None):
        text = f"user_prompt: {cleaned_prompt}\ntarget_model: {model_name}"
        if not image_path:
            return text
        try:
            with open(image_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            logger.debug("Failed to read image for AI enhancement: %s", e)
            return text
        if not raw:
            return text
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        return [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]

    async def _call_groq_enhance(self, cleaned_prompt: str, model_name: str):
        api_key = self._get_provider_api_key("groq")
        if not api_key:
            return None, "no_key"
        return await self._call_openai_compatible_enhance(
            cleaned_prompt, model_name, api_key,
            "https://api.groq.com/openai/v1",
            ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"],
            "Groq",
        )

    async def _call_openrouter_enhance(self, cleaned_prompt: str, model_name: str):
        api_key = self._get_provider_api_key("openrouter")
        if not api_key:
            return None, "no_key"
        return await self._call_openai_compatible_enhance(
            cleaned_prompt, model_name, api_key,
            "https://openrouter.ai/api/v1",
            self._get_provider_model_chain("openrouter"),
            "OpenRouter",
        )

    async def _call_grok_enhance(self, cleaned_prompt: str, model_name: str):
        api_key = self._get_provider_api_key("grok")
        if not api_key:
            return None, "no_key"
        return await self._call_openai_compatible_enhance(
            cleaned_prompt, model_name, api_key,
            "https://api.x.ai/v1",
            self._get_provider_model_chain("grok"),
            "Grok",
        )

    async def _call_deepseek_enhance(self, cleaned_prompt: str, model_name: str, image_path=None):
        api_key = self._get_provider_api_key("deepseek")
        if not api_key:
            return None, "no_key"
        if image_path:
            return None, "vision_unsupported"
        models = self._get_provider_model_chain("deepseek")
        if not models:
            return None, "model is not set"
        return await self._call_openai_compatible_enhance(
            cleaned_prompt, model_name, api_key,
            "https://api.deepseek.com",
            models,
            "DeepSeek",
            image_path=image_path,
        )

    def _format_prompt_for_display(self, prompt_text: str, truncate: bool = True, hidden: bool = False) -> str:
        prompt_text = str(prompt_text or "")
        if not prompt_text:
            prompt_text = self.strings("prompt_empty")
        if truncate and len(prompt_text) > 400:
            prompt_text = f"{prompt_text[:397]}..."
        escaped_prompt = utils.escape_html(prompt_text)
        if hidden:
            escaped_prompt = f"<tg-spoiler>{escaped_prompt}</tg-spoiler>"
        return f"<blockquote expandable>{escaped_prompt}</blockquote>"

    def _format_model_name(self, model_name: str, max_length=30) -> str:
        if not model_name:
            return "default"
        name = re.sub(
            r"\.(safetensors|ckpt|pt|pth|bin|gguf|onnx)$",
            "",
            str(model_name),
            flags=re.IGNORECASE,
        )
        if max_length and len(name) > max_length:
            name = name[:max_length - 3] + "..."
        return name

    def _format_lora_name(self, lora_name: str, max_length=32) -> str:
        if not lora_name:
            return "default"
        name = re.sub(
            r"\.(safetensors|ckpt|pt|pth|bin)$",
            "",
            str(lora_name),
            flags=re.IGNORECASE,
        )
        if max_length and len(name) > max_length:
            name = name[:max_length - 3] + "..."
        return name

    def _format_lora_text_for_display(self, lora_text: str) -> str:
        lines = []
        for line in str(lora_text or "").splitlines():
            if ":" in line:
                name, value = line.split(":", 1)
                lines.append(f"{self._format_lora_name(name.strip(), max_length=None)}:{value}")
            else:
                lines.append(self._format_lora_name(line.strip(), max_length=None))
        return "\n".join(line for line in lines if line)

    def _format_ai_model_name(self, provider: str) -> str:
        model = self._get_provider_model(provider)
        return model or "default"

    def _format_enhance_command_result(self, original_prompt: str, enhanced_prompt: str) -> str:
        provider = self._get_prompt_provider()
        lines = [
            self.strings("enhance_cmd_title"),
            "",
            self.strings("enhance_cmd_provider").format(self._format_provider_name(provider)),
            self.strings("enhance_cmd_model").format(utils.escape_html(self._format_ai_model_name(provider))),
            "",
            self.strings("enhance_cmd_original"),
            self._format_prompt_for_display(original_prompt),
            "",
            self.strings("enhance_cmd_result"),
            self._format_prompt_for_display(enhanced_prompt, truncate=False),
        ]
        return "\n".join(lines)

    async def _get_prompt_from_args_or_reply(self, message: Message):
        args = utils.get_args_raw(message)
        if args:
            return args.strip()
        reply = await message.get_reply_message()
        if not reply:
            return ""
        return (getattr(reply, "raw_text", None) or reply.text or "").strip()

    def _format_loras_for_display(self, selected_loras, is_inline=False):
        if not selected_loras:
            return None
        if is_inline:
            lora_emoji = '<tg-emoji emoji-id="5764779661028495989">\U0001f3a8</tg-emoji>'
        else:
            lora_emoji = '<emoji document_id=5764779661028495989>\U0001f3a8</emoji>'
        items = []
        for lora_name, weight in list(selected_loras.items())[:5]:
            name = self._format_lora_name(lora_name)
            try:
                weight_text = f"{float(weight):.1f}"
            except (TypeError, ValueError):
                weight_text = str(weight)
            items.append(f"{utils.escape_html(name)} [{utils.escape_html(weight_text)}]")
        extra = len(selected_loras) - len(items)
        if extra > 0:
            items.append(utils.escape_html(self.strings("fmt_loras_more").format(extra)))
        return f"{lora_emoji} {self.strings('fmt_loras')} " + ", ".join(items)

    def _format_generation_time_value(self, seconds):
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            return None
        if seconds < 0:
            return None
        if seconds < 60:
            return f"{seconds:.1f}s"
        return self._format_duration(seconds)

    @staticmethod
    def _generation_stats_key(wf_name, model_name=None):
        wf_key = str(wf_name or "default").strip() or "default"
        model_key = str(model_name or "").strip()
        if not model_key:
            return wf_key
        return f"{wf_key}::{model_key}"

    def _duration_average_from_values(self, values):
        if not isinstance(values, list) or not values:
            return None
        clean = []
        for value in values[-_GENERATION_STATS_LIMIT:]:
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value > 0:
                clean.append(value)
        if not clean:
            return None
        return sum(clean) / len(clean)

    def _get_generation_duration_average(self, wf_name, model_name=None):
        stats = self.get("generation_duration_stats", {})
        if not isinstance(stats, dict):
            return None
        avg = self._duration_average_from_values(
            stats.get(self._generation_stats_key(wf_name, model_name))
        )
        if avg is not None:
            return avg
        return self._duration_average_from_values(
            stats.get(self._generation_stats_key(wf_name))
        )

    def _record_generation_duration_stat(self, generation_state):
        if not isinstance(generation_state, dict):
            return
        duration = generation_state.get("generation_duration")
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            return
        if duration <= 0:
            return
        stats = self.get("generation_duration_stats", {})
        if not isinstance(stats, dict):
            stats = {}
        key = self._generation_stats_key(
            generation_state.get("wf_name"),
            generation_state.get("model"),
        )
        values = stats.get(key)
        if not isinstance(values, list):
            values = []
        values.append(round(duration, 3))
        stats[key] = values[-_GENERATION_STATS_LIMIT:]
        self.set("generation_duration_stats", stats)

    def _format_eta_value(self, seconds):
        value = self._format_generation_time_value(seconds)
        return f"~{value}" if value else None

    def _estimate_generation_eta(self, generation_state, runtime=None, queue_info=None, progress_pct=None):
        if not isinstance(generation_state, dict):
            return None
        runtime = runtime if isinstance(runtime, dict) else {}
        queue_info = queue_info if isinstance(queue_info, dict) else {}
        if queue_info.get("state") == "pending":
            return None
        if runtime.get("phase") not in ("running", "finishing", "uploading"):
            return None

        eta_total = runtime.get("eta_total")
        eta_started_at = runtime.get("eta_started_at")
        if eta_total is not None and eta_started_at is not None:
            try:
                remaining = float(eta_total) - (time.monotonic() - float(eta_started_at))
            except (TypeError, ValueError):
                remaining = None
            if remaining is not None and remaining > 1:
                return remaining
            return None

        avg = self._get_generation_duration_average(
            generation_state.get("wf_name"),
            generation_state.get("model"),
        )
        if not avg:
            return None
        runtime["eta_total"] = avg
        runtime["eta_started_at"] = time.monotonic()
        return avg

    def _format_gen_text(self, prompt_display, model, wf_name, header, is_inline=False, selected_loras=None, generation_time=None, generation_eta=None, quote_details=False):
        model_short = utils.escape_html(self._format_model_name(model))
        if is_inline:
            prompt_emoji = '<tg-emoji emoji-id="5879841310902324730">\u270f\ufe0f</tg-emoji>'
            model_emoji = '<tg-emoji emoji-id="5206591666697306436">\U0001f36d</tg-emoji>'
            wf_emoji = '<tg-emoji emoji-id="4904936030232117798">\u2699\ufe0f</tg-emoji>'
            time_emoji = '<tg-emoji emoji-id="5870921681735781843">\u23f1</tg-emoji>'
        else:
            prompt_emoji = '<emoji document_id=5879841310902324730>\u270f\ufe0f</emoji>'
            model_emoji = '<emoji document_id=5206591666697306436>\U0001f36d</emoji>'
            wf_emoji = '<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji>'
            time_emoji = '<emoji document_id=5870921681735781843>\u23f1</emoji>'
        lines = [
            header,
            f"{prompt_emoji} {self.strings('fmt_prompt')} {prompt_display}",
        ]
        detail_lines = [
            f"{model_emoji} {self.strings('fmt_model')} {model_short}",
            f"{wf_emoji} {self.strings('fmt_workflow')} {utils.escape_html(wf_name)}",
        ]
        if generation_time:
            time_line = self.strings("fmt_generation_time").format(utils.escape_html(generation_time))
            if generation_eta:
                time_line = f"{time_line} / {self.strings('fmt_generation_eta').format(utils.escape_html(generation_eta))}"
            detail_lines.append(f"{time_emoji} {time_line}")
        elif generation_eta:
            detail_lines.append(f"{time_emoji} {self.strings('fmt_generation_eta').format(utils.escape_html(generation_eta))}")
        lora_display = self._format_loras_for_display(selected_loras, is_inline)
        if lora_display:
            detail_lines.append(lora_display)
        if quote_details:
            details = "\n".join(detail_lines)
            lines.append(f"<blockquote>{details}</blockquote>")
        else:
            lines.extend(detail_lines)
        return self._apply_emoji_theme("\n".join(lines))

    @staticmethod
    def _ritual_progress(progress_pct):
        if progress_pct >= 90:
            return 666
        if progress_pct >= 33:
            return 66
        return 6

    def _pick_easter_egg(self, positive, width, height):
        positive = str(positive or "")
        lowered = positive.lower()
        if width == 666 and height == 666:
            return "ritual_666"
        if any(term in lowered for term in ("backrooms", "empty mall", "yellow wallpaper")):
            return "backrooms"
        if len(positive) > 1100 and random.random() < 0.05:
            return "long_prompt_rare"
        if len(positive) > 1100:
            return "long_prompt"
        if 0 < len(positive.split()) <= 2 and random.random() < 0.25:
            return "short_prompt"
        if random.random() < 0.05:
            return "noise_form"
        return None

    def _format_easter_header(self, easter_egg, is_progress=False, progress_pct=0):
        if easter_egg == "ritual_666":
            return self.strings("easter_ritual_progress").format(
                self._ritual_progress(progress_pct)
            )
        if easter_egg == "backrooms":
            return self.strings("easter_backrooms").format(progress_pct)
        if easter_egg == "long_prompt":
            header = self.strings("easter_long_prompt")
        elif easter_egg == "long_prompt_rare":
            header = self.strings("easter_long_prompt_rare")
        elif easter_egg == "short_prompt":
            header = self.strings("easter_short_prompt")
        elif easter_egg == "noise_form":
            header = self.strings("easter_noise_form")
        else:
            return None
        if is_progress:
            return f"{header} {progress_pct}%"
        return header

    def _normalize_node_title(self, title, class_type):
        value = str(title or "").strip()
        if value:
            value = re.sub(r"^[^\wА-Яа-яЁё]+", "", value).strip()
            if value:
                return value
        return str(class_type or "").strip()

    def _get_node_status_info(self, workflow, node_id):
        if not workflow or node_id is None:
            return None
        node = workflow.get(str(node_id))
        if not isinstance(node, dict):
            return None
        class_type = str(node.get("class_type", "")).strip()
        title = self._normalize_node_title(node.get("_meta", {}).get("title", ""), class_type)
        title_lower = title.lower()
        class_lower = class_type.lower()
        key = None
        show_progress = False

        if class_type in ("CheckpointLoaderSimple", "UNETLoader", "VAELoader", "CLIPLoader", "UpscaleModelLoader", "SAMLoader", "UltralyticsDetectorProvider"):
            key = "fmt_loading_model"
        elif class_type in ("CLIPTextEncode", "ImpactWildcardProcessor", "WildcardEncode", "ConditioningConcat", "CLIPSetLastLayer"):
            key = "fmt_encoding_prompt"
        elif class_type in ("LoadImage", "VAEEncode", "EmptyLatentImage", "EmptySD3LatentImage", "SDXLEmptyLatentSizePicker+", "CR Aspect Ratio", "ImageScaleBy", "ImpactSwitch"):
            key = "fmt_processing_image"
        elif "sampler" in class_lower or self._is_sampler_like_node(class_type, node.get("inputs", {})):
            key = "fmt_generating"
            show_progress = True
        elif class_type == "VAEDecode":
            key = "fmt_decoding_image"
        elif class_type in ("UltimateSDUpscale", "ImageUpscaleWithModel", "ImageScaleBy"):
            key = "fmt_upscaling_image"
            show_progress = "upscale" in class_lower or "upscale" in title_lower
        elif class_type == "FaceDetailer":
            key = "fmt_detailing_face"
            show_progress = True
        elif class_type == "SaveImage":
            key = "fmt_saving_result"
        elif class_type in ("Power Lora Loader (rgthree)", "CR LoRA Stack", "CR Apply LoRA Stack"):
            key = "fmt_applying_lora"
        elif title:
            return {"text": self.strings("fmt_running_node").format(utils.escape_html(title)), "show_progress": False, "known": False}

        if not key:
            fallback = title or class_type or str(node_id)
            return {"text": self.strings("fmt_running_node").format(utils.escape_html(fallback)), "show_progress": False, "known": False}

        return {"text": self.strings(key), "show_progress": show_progress, "known": True}

    def _format_status_text(self, prompt_display, model, wf_name, is_inline=False, is_progress=False, progress_pct=0, easter_egg=None, status_key=None, status_text=None, generation_time=None, generation_eta=None):
        if is_inline:
            gen_emoji = '<tg-emoji emoji-id="4904936030232117798">\u2699\ufe0f</tg-emoji>'
        else:
            gen_emoji = '<emoji document_id=4904936030232117798>\u2699\ufe0f</emoji>'
        easter_header = self._format_easter_header(easter_egg, is_progress, progress_pct)
        if status_text and is_progress:
            header = f"{gen_emoji} {status_text} {progress_pct}%"
        elif status_text:
            header = f"{gen_emoji} {status_text}"
        elif easter_header:
            header = f"{gen_emoji} {easter_header}"
        elif is_progress:
            header = f"{gen_emoji} {self.strings('fmt_generating_pct').format(progress_pct)}"
        elif status_key:
            header = f"{gen_emoji} {self.strings(status_key)}"
        else:
            header = f"{gen_emoji} {self.strings('fmt_generating')}"
        return self._apply_emoji_theme(self._format_gen_text(
            prompt_display,
            model,
            wf_name,
            header,
            is_inline,
            generation_time=generation_time,
            generation_eta=generation_eta,
            quote_details=True,
        ))

    def _format_success_text(self, prompt_display, model, wf_name, is_inline=False, selected_loras=None, generation_time=None):
        if is_inline:
            ok_emoji = '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji>'
        else:
            ok_emoji = '<emoji document_id=5206607081334906820>\u2705</emoji>'
        header = f"{ok_emoji} {self.strings('fmt_done')}"
        return self._apply_emoji_theme(self._format_gen_text(
            prompt_display,
            model,
            wf_name,
            header,
            is_inline,
            selected_loras,
            generation_time=generation_time,
            quote_details=True,
        ))

    def _normalize_selected_loras(self, selected_loras, available_loras=None):
        if not isinstance(selected_loras, dict):
            return {}
        available = set(available_loras) if available_loras is not None else None
        normalized = {}
        for lora_name, weight in selected_loras.items():
            lora_name = str(lora_name).strip()
            if not lora_name:
                continue
            if available is not None and lora_name not in available:
                continue
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                weight = 0.75
            normalized[lora_name] = round(max(0.1, min(2.0, weight)), 1)
        return normalized

    def _normalize_lora_preset_entries(self, selected_loras, available_loras=None):
        if not isinstance(selected_loras, dict):
            return {}
        available = set(available_loras) if available_loras is not None else None
        normalized = {}
        for lora_name, value in selected_loras.items():
            lora_name = str(lora_name).strip()
            if not lora_name:
                continue
            if available is not None and lora_name not in available:
                continue
            if isinstance(value, dict):
                enabled = bool(value.get("enabled"))
                weight = value.get("weight", 0.75)
            else:
                enabled = True
                weight = value
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                weight = 0.75
            normalized[lora_name] = {
                "enabled": enabled,
                "weight": round(max(0.1, min(2.0, weight)), 1),
            }
        return normalized

    def _get_enabled_lora_presets(self, selected_loras, available_loras=None):
        entries = self._normalize_lora_preset_entries(selected_loras, available_loras)
        return {
            lora_name: entry["weight"]
            for lora_name, entry in entries.items()
            if entry.get("enabled")
        }

    def _normalize_lora_argset_data(self, data):
        if not isinstance(data, dict):
            data = {}
        return {
            "enabled": bool(data.get("enabled", False)),
            "selected": self._normalize_lora_preset_entries(data.get("selected")),
        }

    def _get_global_lora_data(self):
        data = self.get("global_lora_presets", None)
        if data is None:
            saved = self.get("default_args", {})
            if isinstance(saved, dict):
                data = saved.get("lora")
        data = self._normalize_lora_argset_data(data)
        self.set("global_lora_presets", data)
        return self._clone_argset_data(data)

    def _set_global_lora_data(self, data):
        data = self._normalize_lora_argset_data(data)
        self.set("global_lora_presets", data)
        return self._clone_argset_data(data)

    def _ensure_lora_argset_entry(self, saved):
        data = self._get_global_lora_data()
        if isinstance(saved, dict):
            saved["lora"] = self._clone_argset_data(data)
            return saved["lora"]
        return data

    def _workflow_limited_mode(self):
        return bool(self.get("workflow_limited_mode", False))

    def _set_workflow_limited_mode(self, enabled):
        self.set("workflow_limited_mode", bool(enabled))

    @staticmethod
    def _apply_limited_generation_mode(parsed):
        for key in (
            "width",
            "height",
            "steps",
            "cfg",
            "seed",
            "denoise",
            "sampler_name",
            "scheduler",
        ):
            parsed[key] = None
        parsed["use_lora_picker"] = False
        return parsed

    def _get_default_lora_data(self):
        return self._get_global_lora_data()

    def _get_default_lora_presets(self):
        data = self._get_default_lora_data()
        if not self._argset_enabled(data):
            return {}
        return self._get_enabled_lora_presets(data.get("selected"))

    def _format_lora_preset_summary(self, data):
        selected = self._normalize_lora_preset_entries(data.get("selected")) if isinstance(data, dict) else {}
        if not selected:
            return self.strings("lora_presets_empty")
        enabled_count = sum(1 for entry in selected.values() if entry.get("enabled"))
        return self.strings("lora_presets_selected").format(f"{enabled_count}/{len(selected)}")

    def _build_generation_state(
        self,
        *,
        positive,
        original_positive,
        negative,
        width,
        height,
        seed,
        denoise,
        steps,
        cfg,
        wf_name,
        model,
        input_filename,
        input_image_name=None,
        input_image_path=None,
        input_video_filename=None,
        input_video_name=None,
        input_video_path=None,
        chat_id,
        reply_to,
        enhance_prompt,
        use_lora_picker,
        enhanced=False,
        easter_egg=None,
        selected_loras=None,
        lora_entries=None,
        auto_delete_result_delay=None,
        trigger_origin=None,
        health_checked=False,
        plain_status=False,
        reuse_status_message=False,
        sampler_name=None,
        scheduler=None,
        limited_mode=False,
    ):
        return {
            "positive": positive,
            "original_positive": original_positive,
            "negative": negative,
            "width": width,
            "height": height,
            "seed": seed,
            "denoise": denoise,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "wf_name": wf_name,
            "model": model,
            "input_filename": input_filename,
            "input_image_name": input_image_name,
            "input_image_path": input_image_path,
            "input_video_filename": input_video_filename,
            "input_video_name": input_video_name,
            "input_video_path": input_video_path,
            "chat_id": chat_id,
            "reply_to": reply_to,
            "enhance_prompt": enhance_prompt,
            "use_lora_picker": use_lora_picker,
            "enhanced": enhanced,
            "easter_egg": easter_egg,
            "selected_loras": self._normalize_selected_loras(selected_loras),
            "lora_entries": self._normalize_lora_preset_entries(lora_entries if lora_entries is not None else selected_loras),
            "auto_delete_result_delay": auto_delete_result_delay,
            "trigger_origin": trigger_origin,
            "health_checked": health_checked,
            "plain_status": plain_status,
            "reuse_status_message": bool(reuse_status_message),
            "limited_mode": bool(limited_mode),
        }

    def _build_display_bundle(self, state: dict, hidden_prompt: bool = False):
        positive = state["positive"]
        original_positive = state.get("original_positive", positive)
        if state.get("enhanced") and positive != original_positive:
            prompt_display = (
                self._format_prompt_for_display(original_positive, hidden=hidden_prompt)
                + "\n"
                + self.strings("enhanced_label")
                + " "
                + self._format_prompt_for_display(positive, hidden=hidden_prompt)
            )
        else:
            prompt_display = self._format_prompt_for_display(positive, hidden=hidden_prompt)

        return (
            prompt_display,
            state.get("model") or "default",
            state["wf_name"],
        )

    def _store_last_generation(self, state: dict):
        self.set(
            "last_generation",
            {
                "positive": state.get("positive") or "",
                "original_positive": state.get("original_positive") or state.get("positive") or "",
                "negative": state["negative"],
                "width": state["width"],
                "height": state["height"],
                "denoise": state["denoise"],
                "steps": state["steps"],
                "cfg": state["cfg"],
                "sampler_name": state.get("sampler_name"),
                "scheduler": state.get("scheduler"),
                "model": state["model"],
                "wf_name": state["wf_name"],
                "enhance_prompt": state.get("enhance_prompt", False),
                "selected_loras": state.get("selected_loras", {}),
            },
        )

    def _workflow_mapping_value(self, workflow, mapping):
        if not isinstance(workflow, dict) or not isinstance(mapping, dict):
            return None
        node = workflow.get(str(mapping.get("node_id")))
        if not isinstance(node, dict):
            return None
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            return None
        fields = mapping.get("fields") or mapping.get("field")
        if isinstance(fields, str):
            fields = [fields]
        if not isinstance(fields, list):
            return None
        for field in fields:
            if field in inputs:
                return inputs.get(field)
        return None

    def _sync_generation_state_from_workflow(self, state, wf_data, workflow):
        mapping = wf_data.get("mapping", {}) if isinstance(wf_data, dict) else {}
        positive_value = self._workflow_mapping_value(workflow, mapping.get("positive"))
        if isinstance(positive_value, str):
            state["archive_positive"] = positive_value
        negative_value = self._workflow_mapping_value(workflow, mapping.get("negative"))
        if isinstance(negative_value, str):
            state["archive_negative"] = negative_value
        for key in ("width", "height", "steps", "seed", "denoise"):
            value = self._workflow_mapping_value(workflow, mapping.get(key))
            if value is not None:
                state[key] = value
        cfg_value = self._workflow_mapping_value(workflow, mapping.get("cfg"))
        if cfg_value is None:
            cfg_value = self._workflow_mapping_value(workflow, mapping.get("flux_guidance"))
        if cfg_value is not None:
            state["cfg"] = cfg_value
        sampler_name = self._workflow_mapping_value(workflow, mapping.get("sampler_name"))
        if sampler_name is not None:
            state["sampler_name"] = sampler_name
        scheduler = self._workflow_mapping_value(workflow, mapping.get("scheduler"))
        if scheduler is not None:
            state["scheduler"] = scheduler

    def _next_archive_generation_number(self):
        value = self._coerce_int(self.get("archive_generation_counter"), 0, 0)
        value += 1
        self.set("archive_generation_counter", value)
        return value

    def _format_archive_loras_plain(self, selected_loras):
        selected_loras = self._normalize_selected_loras(selected_loras)
        if not selected_loras:
            return "none"
        return "\n".join(
            f"{self._format_lora_name(name, max_length=None)}: {weight}"
            for name, weight in selected_loras.items()
        )

    def _build_archive_prompt_text(self, state: dict, generation_number: int):
        positive = str(state.get("archive_positive") or state.get("positive") or "")
        original_positive = str(state.get("original_positive") or positive)
        negative = str(state.get("archive_negative") or state.get("negative") or "")
        lines = [
            f"Generation: #{generation_number}",
            "",
        ]
        if state.get("enhanced") and positive != original_positive:
            lines.extend([
                "Original prompt:",
                original_positive,
                "",
                "Enhanced prompt:",
                positive,
                "",
            ])
        else:
            lines.extend([
                "Prompt:",
                positive,
                "",
            ])
        size = (
            f"{state.get('width')}x{state.get('height')}"
            if state.get("width") is not None and state.get("height") is not None
            else None
        )
        fields = [
            ("Negative", negative),
            ("Model", self._format_model_name(state.get("model") or "default", max_length=None)),
            ("Workflow", str(state.get("wf_name") or "default")),
            ("Size", size),
            ("Steps", state.get("steps")),
            ("CFG", state.get("cfg")),
            ("Sampler", state.get("sampler_name")),
            ("Scheduler", state.get("scheduler")),
            ("Seed", state.get("seed")),
            ("Denoise", state.get("denoise")),
            ("LoRA", self._format_archive_loras_plain(state.get("selected_loras"))),
        ]
        for label, value in fields:
            if value is None:
                continue
            lines.extend([f"{label}:", str(value), ""])
        return "\n".join(lines).strip()

    async def _send_archive_text_fallback(
        self,
        chat_id,
        prompt_text,
        generation_number,
        reply_to=None,
        allow_unthreaded_fallback=True,
    ):
        text = "\n\n".join([
            self.strings("archive_full_prompt_title").format(generation_number),
            str(prompt_text or ""),
        ])
        try:
            return await self.client.send_message(chat_id, text, reply_to=reply_to)
        except Exception:
            if not allow_unthreaded_fallback:
                raise
            return await self.client.send_message(chat_id, text)

    async def _send_archive_prompt_file(
        self,
        chat_id,
        state,
        generation_number,
        reply_to=None,
        allow_unthreaded_fallback=True,
    ):
        prompt_text = str(state.get("archive_positive") or state.get("positive") or "")
        try:
            prompt_text = self._build_archive_prompt_text(state, generation_number)
            text = prompt_text
            file_obj = io.BytesIO(text.encode("utf-8"))
            file_obj.name = f"comfy_prompt_{generation_number:06d}.txt"
            try:
                return await self.client.send_file(
                    chat_id,
                    file_obj,
                    caption=self.strings("archive_full_prompt_caption"),
                    reply_to=reply_to,
                )
            except Exception:
                if not allow_unthreaded_fallback:
                    raise
                file_obj.seek(0)
                return await self.client.send_file(
                    chat_id,
                    file_obj,
                    caption=self.strings("archive_full_prompt_caption"),
                )
            finally:
                file_obj.close()
        except Exception as e:
            logger.debug("Failed to send archive prompt file: %s", e)
            return await self._send_archive_text_fallback(
                chat_id,
                prompt_text,
                generation_number,
                reply_to,
                allow_unthreaded_fallback=allow_unthreaded_fallback,
            )

    async def _build_workflow_file(self, wf_name):
        wf_name = self._canonical_workflow_name(wf_name)
        if not wf_name or wf_name.lower() == "i2i":
            return wf_name, None, ""
        wf_data = await self._ensure_workflow_data(wf_name)
        if not wf_data:
            return wf_name, None, ""
        json_str = json.dumps(wf_data["workflow"], indent=2, ensure_ascii=False)
        file_obj = io.BytesIO(json_str.encode("utf-8"))
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", wf_name).strip() or "workflow"
        file_obj.name = f"{safe_name}_workflow.json"
        return wf_name, file_obj, self._workflow_description(wf_name)

    def _extract_cshare_generation_number(self, text):
        match = re.search(r"\bGeneration:\s*#(\d+)", str(text or ""), re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    async def _download_cshare_text(self, message):
        if getattr(message, "media", None):
            bio = io.BytesIO()
            try:
                await self.client.download_media(message, bio)
                value = bio.getvalue()
            finally:
                bio.close()
            if value:
                return value.decode("utf-8", errors="ignore").strip()
        return (getattr(message, "raw_text", None) or message.text or "").strip()

    async def _find_cshare_prompt_info(self, archive_message, generation_number):
        chat_id = utils.get_chat_id(archive_message)
        ids = list(range(archive_message.id + 1, archive_message.id + 21))
        try:
            messages = await self.client.get_messages(chat_id, ids=ids)
        except Exception as e:
            logger.debug("Failed to fetch archive prompt messages: %s", e)
            return None, ""
        for item in messages or []:
            if not item:
                continue
            if getattr(item, "reply_to_msg_id", None) != archive_message.id:
                continue
            text = await self._download_cshare_text(item)
            if not text:
                continue
            if self._extract_cshare_generation_number(text) == generation_number:
                return item, text
        return None, ""

    def _parse_archive_prompt_text(self, text):
        result = {"raw": str(text or "")}
        headers = {
            "generation": "generation",
            "original prompt": "original_prompt",
            "enhanced prompt": "enhanced_prompt",
            "prompt": "prompt",
            "negative": "negative",
            "model": "model",
            "workflow": "workflow",
            "size": "size",
            "steps": "steps",
            "cfg": "cfg",
            "sampler": "sampler",
            "scheduler": "scheduler",
            "seed": "seed",
            "denoise": "denoise",
            "lora": "lora",
        }
        current = None
        buffer = []

        def flush():
            nonlocal current, buffer
            if current:
                result[current] = "\n".join(buffer).strip()
            current = None
            buffer = []

        for line in result["raw"].splitlines():
            match = re.match(
                r"^\s*(Generation|Original prompt|Enhanced prompt|Prompt|Negative|Model|Workflow|Size|Steps|CFG|Sampler|Scheduler|Seed|Denoise|LoRA):\s*(.*)\s*$",
                line,
                re.IGNORECASE,
            )
            if match:
                flush()
                key = headers[match.group(1).lower()]
                value = match.group(2)
                if key == "generation":
                    result["generation"] = self._extract_cshare_generation_number(line)
                    current = None
                    buffer = []
                else:
                    current = key
                    buffer = [value] if value else []
                continue
            if current:
                buffer.append(line)
        flush()
        return result

    async def _download_cshare_image(self, message, generation_number):
        if not getattr(message, "media", None):
            return None, None
        bio = io.BytesIO()
        try:
            await self.client.download_media(message, bio)
            value = bio.getvalue()
        finally:
            bio.close()
        if not value:
            return None, None
        filename = None
        try:
            filename = getattr(message.file, "name", None)
        except Exception:
            filename = None
        if not filename:
            filename = f"comfy_generation_{generation_number:06d}.png"
        return value, filename

    def _cshare_quote_html(self, label, value):
        value = str(value or "").strip() or "—"
        return f"{label}:\n<blockquote expandable>{utils.escape_html(value)}</blockquote>"

    def _cshare_short_quote_html(self, label, value, limit=300):
        value = str(value or "").strip() or "—"
        if len(value) > limit:
            value = value[:limit].rstrip() + "..."
        return f"{label}:\n<blockquote expandable>{utils.escape_html(value)}</blockquote>"

    def _cshare_quote_html_raw(self, label, value):
        value = str(value or "").strip() or "-"
        return f"{label}:\n<blockquote expandable>{value}</blockquote>"

    def _cshare_quote_plain(self, label, value):
        value = str(value or "").strip() or "—"
        return f"{label}:\n{value}"

    def _format_builtin_workflow_link_html(self, wf_name):
        canonical = self._canonical_workflow_name(wf_name)
        url = _BUILTIN_WORKFLOW_TELEGRAM_URLS.get(canonical)
        if not url:
            return utils.escape_html(str(wf_name or ""))
        return f'<a href="{url}">{utils.escape_html(canonical)}</a>'

    def _cshare_param_value(self, value):
        value = str(value or "").strip()
        return "" if value.lower() in {"none", "null", "nonexnone"} else value

    def _format_cshare_params(self, data):
        parts = []
        size = self._cshare_param_value(data.get("size"))
        steps = self._cshare_param_value(data.get("steps"))
        cfg = self._cshare_param_value(data.get("cfg"))
        sampler = self._cshare_param_value(data.get("sampler"))
        scheduler = self._cshare_param_value(data.get("scheduler"))
        seed = self._cshare_param_value(data.get("seed"))
        denoise = self._cshare_param_value(data.get("denoise"))
        if size:
            parts.append(size)
        if steps:
            parts.append(f"steps {steps}")
        if cfg:
            parts.append(f"CFG {cfg}")
        if sampler:
            parts.append(f"sampler {sampler}")
        if scheduler:
            parts.append(f"scheduler {scheduler}")
        if seed:
            parts.append(f"seed {seed}")
        if denoise:
            parts.append(f"denoise {denoise}")
        return ", ".join(parts) or "—"

    @staticmethod
    def _generate_cshare_id():
        return f"{random.choice(string.ascii_lowercase)}{random.randint(0, 999):03d}"

    async def _format_cshare_author(self, message, anonymous):
        if anonymous:
            value = self.strings("cshare_author_anon")
            return value, value
        try:
            sender = await message.get_sender()
        except Exception:
            sender = None
        sender_id = getattr(sender, "id", None) or getattr(message, "sender_id", None) or self.tg_id
        username = getattr(sender, "username", None)
        if username:
            label = f"@{username}"
            return f'<a href="https://t.me/{utils.escape_html(username)}">{utils.escape_html(label)}</a>', label
        name = " ".join(
            item
            for item in (
                getattr(sender, "first_name", None),
                getattr(sender, "last_name", None),
            )
            if item
        ).strip() or str(sender_id)
        return f'<a href="tg://user?id={sender_id}">{utils.escape_html(name)}</a>', name

    def _build_cshare_post(self, data, note, author_html, author_plain, workflow_display, workflow_description="", workflow_plain_display=None):
        positive = data.get("enhanced_prompt") or data.get("prompt") or "—"
        negative = data.get("negative") or "—"
        model = self._format_model_name(data.get("model"), max_length=None) if data.get("model") else "—"
        lora = self._format_lora_text_for_display(data.get("lora")).strip()
        params = self._format_cshare_params(data)
        workflow_description = str(workflow_description or "").strip()

        html_lines = []
        plain_lines = []
        if note:
            html_lines.extend([utils.escape_html(note), ""])
            plain_lines.extend([note, ""])
        html_lines.extend([self.strings("cshare_author").format(author_html), ""])
        plain_lines.extend([self._plain_text(self.strings("cshare_author").format(author_plain)), ""])
        fields = [
            ("Positive", positive),
            ("Negative", negative),
            ("Model", model),
        ]
        if lora and lora.lower() != "none":
            fields.append(("LoRA", lora))
        fields.extend(
            [
                ("Workflow", workflow_display),
                ("Params", params),
            ]
        )
        if workflow_description:
            fields.insert(-1, ("Workflow description", workflow_description))
        for label, value in fields:
            if label == "Workflow":
                html_lines.extend([self._cshare_quote_html_raw(label, value), ""])
            else:
                html_lines.extend([self._cshare_quote_html(label, value), ""])
            plain_value = workflow_plain_display if label == "Workflow" and workflow_plain_display is not None else value
            plain_lines.extend([self._cshare_quote_plain(label, plain_value), ""])
        return "\n".join(html_lines).strip(), "\n\n".join(plain_lines).strip()

    def _build_cshare_short_caption(self, data, note, author_html):
        positive = data.get("enhanced_prompt") or data.get("prompt") or "—"
        model = self._format_model_name(data.get("model"), max_length=None) if data.get("model") else "—"
        lines = []
        if note:
            lines.extend([utils.escape_html(note), ""])
        lines.extend(
            [
                self.strings("cshare_author").format(author_html),
                "",
                self._cshare_short_quote_html("Prompt", positive, 300),
                "",
                self._cshare_quote_html("Model", model),
            ]
        )
        return "\n".join(lines).strip()

    def _build_cshare_post_ru(self, data, note, author_html, author_plain, workflow_display, workflow_description="", workflow_plain_display=None, share_id=None):
        positive = data.get("enhanced_prompt") or data.get("prompt") or "—"
        negative = data.get("negative") or "—"
        model = self._format_model_name(data.get("model"), max_length=None) if data.get("model") else "—"
        lora = self._format_lora_text_for_display(data.get("lora")).strip()
        params = self._format_cshare_params(data)
        workflow_description = str(workflow_description or "").strip()

        html_lines = []
        plain_lines = []
        if share_id:
            html_lines.extend([f"Предложка ComfyIdeas #{share_id}", ""])
            plain_lines.extend([f"Предложка ComfyIdeas #{share_id}", ""])
        if note:
            html_lines.extend([utils.escape_html(note), ""])
            plain_lines.extend([note, ""])
        html_lines.extend([f"Автор: {author_html}", ""])
        plain_lines.extend([f"Автор: {author_plain}", ""])
        fields = [
            ("Промпт", positive),
            ("Негатив", negative),
            ("Модель", model),
        ]
        if lora and lora.lower() != "none":
            fields.append(("LoRA", lora))
        fields.extend(
            [
                ("Воркфлоу", workflow_display),
                ("Параметры", params),
            ]
        )
        if workflow_description:
            fields.insert(-1, ("Описание воркфлоу", workflow_description))
        for label, value in fields:
            if label == "Воркфлоу":
                html_lines.extend([self._cshare_quote_html_raw(label, value), ""])
            else:
                html_lines.extend([self._cshare_quote_html(label, value), ""])
            plain_value = workflow_plain_display if label == "Воркфлоу" and workflow_plain_display is not None else value
            plain_lines.extend([self._cshare_quote_plain(label, plain_value), ""])
        return "\n".join(html_lines).strip(), "\n\n".join(plain_lines).strip()

    def _build_cshare_short_caption_ru(self, data, note, author_html, workflow_display, share_id):
        positive = data.get("enhanced_prompt") or data.get("prompt") or "—"
        model = data.get("model") or "—"
        lines = [f"Предложка ComfyIdeas #{share_id}"]
        if note:
            lines.extend(["", utils.escape_html(note)])
        lines.extend(
            [
                "",
                f"Автор: {author_html}",
                "",
                self._cshare_short_quote_html("Промпт", positive, 300),
                "",
                self._cshare_quote_html("Модель", model),
                "",
                self._cshare_quote_html_raw("Воркфлоу", workflow_display),
            ]
        )
        return "\n".join(lines).strip()

    async def _send_cshare_text_file(self, target, text, share_id):
        file_obj = io.BytesIO(str(text or "").encode("utf-8"))
        file_obj.name = f"comfy_share_{share_id}.txt"
        try:
            return await self._cshare_send_file(
                target,
                file_obj,
                caption=f"Текст предложки #{share_id}",
            )
        finally:
            file_obj.close()

    async def _send_cshare_workflow_file(self, target, wf_name, file_obj, description=""):
        if not wf_name or not file_obj:
            return False
        caption = f"Workflow: {self._format_builtin_workflow_link_html(wf_name)}"
        description = str(description or "").strip()
        if description:
            caption += f"\n\nDescription:\n<blockquote expandable>{utils.escape_html(description)}</blockquote>"
        try:
            await self._cshare_send_file(
                target,
                file_obj,
                caption=caption,
            )
            return True
        except Exception as e:
            logger.debug("Failed to send cshare workflow file: %s", e)
            try:
                await self._cshare_send_message(target, f"{self.get_prefix()}mlwf {wf_name}")
                return True
            except Exception as fallback_error:
                logger.debug("Failed to fallback-send mlwf command: %s", fallback_error)
                return False
        finally:
            file_obj.close()

    def _is_chat_write_forbidden(self, error):
        return error.__class__.__name__ in {"ChatWriteForbiddenError", "ChatSendMediaForbiddenError", "ChatSendPlainForbiddenError"}

    def _is_monoforum_reply_error(self, error):
        return "REPLY_TO_MONOFORUM_PEER_INVALID" in str(error)

    def _can_retry_cshare_fallback(self, error):
        return self._is_monoforum_reply_error(error) or self._is_chat_write_forbidden(error)

    def _cshare_peer(self, target):
        return target.get("peer") if isinstance(target, dict) else target

    def _cshare_reply_to(self, target):
        return target.get("reply_to") if isinstance(target, dict) else None

    def _cshare_fallback_target(self, target):
        return target.get("fallback") if isinstance(target, dict) else None

    async def _cshare_try_init_direct(self, target):
        peer = self._cshare_fallback_target(target) or self._cshare_peer(target)
        if not peer:
            return False
        try:
            msg = await self.client.send_message(peer, ".")
        except Exception as e:
            logger.debug("Failed to initialize ComfyIdeas direct monoforum: %s", e)
            return False
        try:
            await msg.delete()
        except Exception as e:
            logger.debug("Failed to delete ComfyIdeas direct init message: %s", e)
        return True

    async def _cshare_send_file(self, target, file_obj, **kwargs):
        reply_to = self._cshare_reply_to(target)
        if reply_to is not None:
            try:
                return await self._cshare_send_file_raw(target, file_obj, reply_to, **kwargs)
            except Exception as e:
                if self._is_monoforum_reply_error(e) and await self._cshare_try_init_direct(target):
                    if hasattr(file_obj, "seek"):
                        file_obj.seek(0)
                    try:
                        return await self._cshare_send_file_raw(target, file_obj, reply_to, **kwargs)
                    except Exception as retry_error:
                        if not self._can_retry_cshare_fallback(retry_error):
                            raise
                fallback = self._cshare_fallback_target(target)
                if not fallback or not self._can_retry_cshare_fallback(e):
                    raise
                kwargs.pop("reply_to", None)
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)
                try:
                    return await self.client.send_file(fallback, file_obj, **kwargs)
                except Exception as fallback_error:
                    if self._is_monoforum_reply_error(fallback_error):
                        raise e
                    raise
        try:
            return await self.client.send_file(self._cshare_peer(target), file_obj, **kwargs)
        except Exception as e:
            fallback = self._cshare_fallback_target(target)
            if not fallback or not self._can_retry_cshare_fallback(e):
                raise
            kwargs.pop("reply_to", None)
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            try:
                return await self.client.send_file(fallback, file_obj, **kwargs)
            except Exception as fallback_error:
                if self._is_monoforum_reply_error(fallback_error):
                    raise e
                raise

    async def _cshare_send_message(self, target, text, **kwargs):
        reply_to = self._cshare_reply_to(target)
        if reply_to is not None:
            try:
                return await self._cshare_send_message_raw(target, text, reply_to, **kwargs)
            except Exception as e:
                if self._is_monoforum_reply_error(e) and await self._cshare_try_init_direct(target):
                    try:
                        return await self._cshare_send_message_raw(target, text, reply_to, **kwargs)
                    except Exception as retry_error:
                        if not self._can_retry_cshare_fallback(retry_error):
                            raise
                fallback = self._cshare_fallback_target(target)
                if not fallback or not self._can_retry_cshare_fallback(e):
                    raise
                kwargs.pop("reply_to", None)
                try:
                    return await self.client.send_message(fallback, text, **kwargs)
                except Exception as fallback_error:
                    if self._is_monoforum_reply_error(fallback_error):
                        raise e
                    raise
        try:
            return await self.client.send_message(self._cshare_peer(target), text, **kwargs)
        except Exception as e:
            fallback = self._cshare_fallback_target(target)
            if not fallback or not self._can_retry_cshare_fallback(e):
                raise
            kwargs.pop("reply_to", None)
            try:
                return await self.client.send_message(fallback, text, **kwargs)
            except Exception as fallback_error:
                if self._is_monoforum_reply_error(fallback_error):
                    raise e
                raise

    async def _cshare_send_file_raw(self, target, file_obj, reply_to, **kwargs):
        if not (InputMediaUploadedDocument and DocumentAttributeFilename):
            raise UserFacingError("cshare_direct_unavailable", self._plain_text(self.strings("cshare_direct_unavailable")))
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        filename = getattr(file_obj, "name", None) or "file.bin"
        uploaded = await self.client.upload_file(file_obj, file_name=filename)
        caption = kwargs.get("caption") or ""
        try:
            text, entities = self.client.parse_mode.parse(caption)
        except Exception:
            text, entities = caption, []
        media = InputMediaUploadedDocument(
            file=uploaded,
            mime_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            attributes=[DocumentAttributeFilename(filename)],
        )
        request = SendMediaRequest(
            peer=await self.client.get_input_entity(self._cshare_peer(target)),
            media=media,
            message=text,
            random_id=random.getrandbits(63),
            reply_to=reply_to,
            entities=entities or [],
        )
        result = await self.client(request)
        try:
            return self.client._get_response_message(request, result, await self.client.get_input_entity(self._cshare_peer(target)))
        except Exception:
            return None

    async def _cshare_send_message_raw(self, target, text, reply_to, **kwargs):
        try:
            parsed_text, entities = self.client.parse_mode.parse(text)
        except Exception:
            parsed_text, entities = text, []
        request = SendMessageRequest(
            peer=await self.client.get_input_entity(self._cshare_peer(target)),
            message=parsed_text,
            random_id=random.getrandbits(63),
            no_webpage=not kwargs.get("link_preview", False),
            reply_to=reply_to,
            entities=entities or [],
        )
        result = await self.client(request)
        try:
            return self.client._get_response_message(request, result, await self.client.get_input_entity(self._cshare_peer(target)))
        except Exception:
            return None

    async def _resolve_cshare_direct_target(self):
        channel = await self.client.get_entity("comfyideas")
        monoforum = None

        for target in (
            "https://t.me/comfyideas?direct",
            "tg://resolve?domain=comfyideas&direct",
        ):
            try:
                entity = await self.client.get_entity(target)
                if getattr(entity, "monoforum", False):
                    monoforum = entity
                    break
            except Exception as e:
                logger.debug("Failed to resolve ComfyIdeas direct target %s: %s", target, e)

        if getattr(channel, "monoforum", False):
            monoforum = channel

        linked_id = getattr(channel, "linked_monoforum_id", None)
        if not linked_id and not monoforum:
            raise UserFacingError("cshare_direct_unavailable", self._plain_text(self.strings("cshare_direct_unavailable")))

        if linked_id and not monoforum:
            for entity_like in (PeerChannel(int(linked_id)),):
                try:
                    entity = await self.client.get_entity(entity_like)
                    if entity:
                        monoforum = entity
                        break
                except Exception as e:
                    logger.debug("Failed to resolve ComfyIdeas monoforum by id %s: %s", linked_id, e)
                try:
                    entity = await self.client.get_input_entity(entity_like)
                    if entity:
                        monoforum = entity
                        break
                except Exception as e:
                    logger.debug("Failed to resolve ComfyIdeas input monoforum by id %s: %s", linked_id, e)

        if linked_id and not monoforum:
            try:
                dialogs = await self.client.get_dialogs(limit=200)
                for dialog in dialogs:
                    entity = getattr(dialog, "entity", None)
                    if getattr(entity, "id", None) == linked_id:
                        monoforum = entity
                        break
                    if getattr(entity, "monoforum", False) and getattr(entity, "linked_monoforum_id", None) == getattr(channel, "id", None):
                        monoforum = entity
                        break
            except Exception as e:
                logger.debug("Failed to scan dialogs for ComfyIdeas monoforum: %s", e)

        if not monoforum:
            raise UserFacingError("cshare_direct_unavailable", self._plain_text(self.strings("cshare_direct_unavailable")))

        if InputReplyToMonoForum:
            try:
                try:
                    self_peer = await self.client.get_input_entity(self.tg_id)
                except Exception:
                    self_peer = await self.client.get_input_entity("me")
                return {
                    "peer": monoforum,
                    "reply_to": InputReplyToMonoForum(monoforum_peer_id=self_peer),
                    "fallback": monoforum,
                }
            except Exception as e:
                logger.debug("Failed to resolve self input peer for ComfyIdeas monoforum: %s", e)

        return {"peer": monoforum}

    def _message_html(self, message):
        text = getattr(message, "raw_text", None) or getattr(message, "text", None) or ""
        entities = getattr(message, "entities", None) or []
        if not entities:
            return utils.escape_html(text)
        try:
            return html.unparse(utils.escape_html(text), entities)
        except Exception as e:
            logger.debug("Failed to unparse message html: %s", e)
            return utils.escape_html(text)

    def _extract_cshare_top_block(self, text):
        text = str(text or "")
        start = text.find("[")
        if start == -1:
            return ""
        end = text.find("]", start + 1)
        if end == -1:
            return ""
        return text[start + 1:end].strip()

    async def _fetch_cshare_top(self):
        try:
            message = await self.client.get_messages(
                _CSHARE_TOP_CHAT,
                ids=_CSHARE_TOP_MESSAGE_ID,
            )
        except Exception as e:
            logger.debug("Failed to fetch ComfyIdeas top: %s", e)
            return ""
        if not message:
            return ""
        return self._extract_cshare_top_block(self._message_html(message))

    async def _answer_cshare_top(self, message):
        top = await self._fetch_cshare_top()
        await self._safe_answer(
            message,
            top or self.strings("cshare_top_unavailable"),
        )

    async def _format_cshare_done_with_top(self):
        top = await self._fetch_cshare_top()
        if not top:
            return self.strings("cshare_done")
        return f"{self.strings('cshare_done')}\n\n{top}"

    def _build_cshare_preview_text(self, post_html, short_caption_html=None):
        body = str(post_html or "").strip()
        if len(body) > 3400 and short_caption_html:
            body = str(short_caption_html or "").strip()
        if len(body) > 3400:
            body = body[:3397].rstrip() + "..."
        return "\n\n".join([
            self.strings("cshare_preview_title"),
            body,
        ]).strip()

    async def _prepare_cshare_preview_state(self, message, reply, generation_number, prompt_text, raw_args):
        data = self._parse_archive_prompt_text(prompt_text)
        if data.get("generation") != generation_number:
            return None, self.strings("cshare_no_prompt_info")
        if not getattr(reply, "media", None):
            return None, self.strings("cshare_no_image")

        anonymous = bool(re.search(r"(^|\s)-anon(\s|$)", raw_args, re.IGNORECASE))
        note = re.sub(r"(^|\s)-anon(\s|$)", " ", raw_args, flags=re.IGNORECASE).strip()
        author_html, author_plain = await self._format_cshare_author(message, anonymous)

        workflow_display = self.strings("cshare_unknown_workflow")
        workflow_name = None
        workflow_description = ""
        workflow_plain_display = self.strings("cshare_unknown_workflow")
        should_send_workflow = False
        raw_workflow = str(data.get("workflow") or "").strip()
        if raw_workflow:
            try:
                canonical_workflow = self._canonical_workflow_name(raw_workflow)
                if canonical_workflow in self._BUILTIN_WORKFLOWS:
                    workflow_name = canonical_workflow
                    workflow_display = self._format_builtin_workflow_link_html(workflow_name)
                    workflow_plain_display = workflow_name
                else:
                    workflow_name, workflow_file, workflow_description = await self._build_workflow_file(canonical_workflow)
                    try:
                        if workflow_file:
                            should_send_workflow = True
                            workflow_display = utils.escape_html(workflow_name)
                            workflow_plain_display = workflow_name
                    finally:
                        if workflow_file:
                            workflow_file.close()
            except Exception as e:
                logger.debug("Failed to prepare cshare workflow: %s", e)

        post_html, post_plain = self._build_cshare_post(
            data,
            note,
            author_html,
            author_plain,
            workflow_display,
            "",
            workflow_plain_display,
        )
        short_caption_html = self._build_cshare_short_caption(data, note, author_html)
        share_id = self._generate_cshare_id()

        return {
            "share_id": share_id,
            "archive_chat_id": utils.get_chat_id(reply),
            "archive_message_id": reply.id,
            "generation_number": generation_number,
            "data": data,
            "note": note,
            "author_html": author_html,
            "author_plain": author_plain,
            "workflow_name": workflow_name,
            "workflow_description": workflow_description,
            "workflow_display": workflow_display,
            "workflow_plain_display": workflow_plain_display,
            "should_send_workflow": should_send_workflow,
            "post_html": post_html,
            "post_plain": post_plain,
            "short_caption_html": short_caption_html,
        }, None

    async def _render_cshare_preview(self, message, state):
        state_id = str(uuid.uuid4())
        self._cshare_preview_states[state_id] = state
        markup = [
            [{
                "text": self.strings("cshare_preview_send_btn"),
                "callback": self._cshare_preview_send,
                "args": (state_id,),
                "style": "success",
            }],
            [{
                "text": self.strings("btn_cancel"),
                "callback": self._cshare_preview_cancel,
                "args": (state_id,),
                "style": "danger",
            }],
        ]
        text = self._build_cshare_preview_text(
            state.get("post_html"),
            state.get("short_caption_html"),
        )
        return await self._render_inline(message, self._to_inline_emoji(text), markup)

    async def _send_cshare_submission(self, state):
        archive_message = await self.client.get_messages(
            state["archive_chat_id"],
            ids=state["archive_message_id"],
        )
        if not archive_message:
            raise UserFacingError("cshare_no_archive", self._plain_text(self.strings("cshare_no_archive")))

        image_bytes, image_name = await self._download_cshare_image(
            archive_message,
            state["generation_number"],
        )
        if not image_bytes:
            raise UserFacingError("cshare_no_image", self._plain_text(self.strings("cshare_no_image")))

        target = await self._resolve_cshare_direct_target()
        data = state["data"]
        note = state.get("note", "")
        author_html = state.get("author_html", "")
        author_plain = state.get("author_plain", "")
        workflow_display = state.get("workflow_display") or self.strings("cshare_unknown_workflow")
        workflow_plain_display = state.get("workflow_plain_display") or self.strings("cshare_unknown_workflow")
        workflow_name = state.get("workflow_name")
        workflow_description = state.get("workflow_description", "")
        should_send_workflow = bool(state.get("should_send_workflow"))
        share_id = state.get("share_id") or self._generate_cshare_id()
        post_html, post_plain = self._build_cshare_post_ru(
            data,
            note,
            author_html,
            author_plain,
            workflow_display,
            "",
            workflow_plain_display,
            share_id,
        )
        short_caption_html = None
        workflow_file = None

        try:
            image_file = io.BytesIO(image_bytes)
            image_file.name = image_name
            sent_message = None
            caption_mode = len(post_html) <= 1024
            try:
                if caption_mode:
                    sent_message = await self._cshare_send_file(
                        target,
                        image_file,
                        caption=post_html,
                        force_document=True,
                    )
                else:
                    sent_message = await self._cshare_send_file(
                        target,
                        image_file,
                        caption=f"Предложка ComfyIdeas #{share_id}",
                        force_document=True,
                    )
                    short_caption_html = self._build_cshare_short_caption_ru(
                        data,
                        note,
                        author_html,
                        workflow_display,
                        share_id,
                    )
            finally:
                image_file.close()

            workflow_sent = True
            if should_send_workflow and workflow_name:
                workflow_name, workflow_file, workflow_description = await self._build_workflow_file(workflow_name)
                workflow_sent = await self._send_cshare_workflow_file(target, workflow_name, workflow_file, workflow_description)
                workflow_file = None

            if not workflow_sent and workflow_display != self.strings("cshare_unknown_workflow"):
                workflow_display = self.strings("cshare_unknown_workflow")
                workflow_plain_display = workflow_display
                post_html, post_plain = self._build_cshare_post_ru(
                    data,
                    note,
                    author_html,
                    author_plain,
                    workflow_display,
                    "",
                    workflow_plain_display,
                    share_id,
                )
                if not caption_mode:
                    short_caption_html = self._build_cshare_short_caption_ru(
                        data,
                        note,
                        author_html,
                        workflow_display,
                        share_id,
                    )
                if caption_mode and sent_message:
                    try:
                        await sent_message.edit(post_html)
                    except Exception as e:
                        logger.debug("Failed to update cshare caption: %s", e)
            if not caption_mode:
                if short_caption_html and sent_message:
                    try:
                        await sent_message.edit(short_caption_html)
                    except Exception as e:
                        logger.debug("Failed to update cshare short caption: %s", e)
                await self._send_cshare_text_file(target, post_plain, share_id)
        finally:
            if workflow_file:
                workflow_file.close()

    async def _cshare_preview_send(self, call: InlineCall, state_id: str):
        state = self._cshare_preview_states.pop(state_id, None)
        if not state:
            return await call.edit(text=self._to_inline_emoji(self.strings("cshare_preview_expired")))
        try:
            await self._send_cshare_submission(state)
        except Exception as e:
            direct_error = isinstance(e, UserFacingError) and e.key == "cshare_direct_unavailable"
            error_text = self.strings("cshare_direct_unavailable") if direct_error else self.strings("cshare_target_error").format(utils.escape_html(str(e)))
            if isinstance(e, UserFacingError) and e.key in ("cshare_no_archive", "cshare_no_image"):
                error_text = self.strings(e.key)
            elif direct_error or self._is_monoforum_reply_error(e) or self._is_chat_write_forbidden(e):
                error_text = self.strings("cshare_direct_unavailable")
            else:
                logger.exception(e)
            return await call.edit(text=self._to_inline_emoji(error_text))
        await call.edit(text=self._to_inline_emoji(await self._format_cshare_done_with_top()))

    async def _cshare_preview_cancel(self, call: InlineCall, state_id: str):
        self._cshare_preview_states.pop(state_id, None)
        await call.edit(text=self._to_inline_emoji(self.strings("cshare_preview_cancelled")))

    async def _send_generation_duplicate(self, media_source, caption, state=None, media_filename=None, media_kind="image"):
        settings = self._get_ult_settings()
        gens_chat = settings["gens_chat"]
        targets = [
            target
            for target in gens_chat.get("targets", [])
            if isinstance(target, dict) and target.get("chat_id")
        ]
        if not targets and gens_chat.get("chat_id"):
            targets = [
                {
                    "chat_id": gens_chat.get("chat_id"),
                    "topic_id": gens_chat.get("topic_id"),
                    "managed": bool(gens_chat.get("managed", False)),
                }
            ]
        if not gens_chat.get("enabled") or not targets:
            return

        changed_targets = False
        checked_targets = []
        try:
            for target in targets:
                checked_target, changed = await self._ensure_gens_archive_target_for_save(gens_chat, target)
                checked_targets.append(checked_target)
                changed_targets = changed_targets or changed
        except Exception as e:
            logger.warning("Failed to recreate generation archive target: %s", e)
            self._disable_gens_chat(drop_chat_id=True)
            raise UserFacingError(
                "archive_access_lost",
                self._plain_text(self.strings("ult_chat_access_lost")),
            ) from e

        if changed_targets:
            self._set_ult_settings(settings)
            targets = self._get_gens_archive_targets()
        else:
            targets = checked_targets

        if not targets:
            self._disable_gens_chat(drop_chat_id=True)
            raise UserFacingError(
                "archive_access_lost",
                self._plain_text(self.strings("ult_chat_access_lost")),
            )

        generation_number = self._next_archive_generation_number() if state else None
        sent_any = False
        failed_access = 0
        for target in targets:
            try:
                archive_caption = (
                    f"{caption}\nGeneration: #{generation_number}"
                    if generation_number is not None
                    else caption
                )
                if media_kind == "image" and isinstance(media_source, (bytes, bytearray)):
                    sent_message = await self._send_result(
                        target["chat_id"],
                        media_source,
                        archive_caption,
                        reply_to=target.get("topic_id"),
                        force_document=True,
                    )
                else:
                    source_to_send = media_source
                    close_after = False
                    if hasattr(source_to_send, "seek"):
                        source_to_send.seek(0)
                    elif isinstance(source_to_send, (bytes, bytearray)):
                        source_to_send = io.BytesIO(source_to_send)
                        source_to_send.name = media_filename or "comfyui_result.bin"
                        close_after = True
                    try:
                        sent_message = await self._send_file_result(
                            target["chat_id"],
                            source_to_send,
                            archive_caption,
                            reply_to=target.get("topic_id"),
                            force_document=True,
                        )
                    finally:
                        if close_after:
                            source_to_send.close()
                if not self._archive_message_matches_target(sent_message, target):
                    raise RuntimeError("Generation archive topic mismatch")
                if generation_number is not None:
                    reply_to = getattr(sent_message, "id", None)
                    await self._send_archive_prompt_file(
                        target["chat_id"],
                        state,
                        generation_number,
                        reply_to=reply_to,
                        allow_unthreaded_fallback=not bool(target.get("topic_id")),
                    )
                sent_any = True
            except (ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError):
                failed_access += 1
                logger.warning(self._plain_text(self.strings("ult_chat_access_lost")))
            except Exception as e:
                err_text = f"{type(e).__name__}: {e}".lower()
                if any(
                    marker in err_text
                    for marker in (
                        "channelprivate",
                        "chatadminrequired",
                        "usernotparticipant",
                        "peeridinvalid",
                        "channelinvalid",
                        "chatwriteforbidden",
                        "msgidinvalid",
                        "replytomsgidinvalid",
                        "topicdeleted",
                        "forumtopicdeleted",
                        "topic mismatch",
                    )
                ):
                    failed_access += 1
                    logger.warning(self._plain_text(self.strings("ult_chat_access_lost")))
                    continue
                logger.exception(e)
        if not sent_any and failed_access == len(targets):
            self._disable_gens_chat(drop_chat_id=True)
            raise UserFacingError(
                "archive_access_lost",
                self._plain_text(self.strings("ult_chat_access_lost")),
            )

    def _get_enhance_error_text(self, error):
        provider = self._get_prompt_provider()
        provider_name = self._format_provider_name(provider)
        key_config_map = {
            "gemini": self.strings("ult_ai_key_path"),
            "groq": self.strings("ult_ai_key_path"),
            "openrouter": self.strings("ult_ai_key_path"),
            "grok": self.strings("ult_ai_key_path"),
            "deepseek": self.strings("ult_ai_key_path"),
        }

        if error == "no_key":
            return self.strings("enhance_no_key").format(
                provider_name,
                utils.escape_html(key_config_map.get(provider, "")),
            )
        if error == "dependency_missing":
            return self.strings("enhance_dependency_missing")
        if error == "expired":
            return self.strings("enhance_key_expired").format(provider_name)
        if error == "rate_limit":
            return self.strings("enhance_rate_limit").format(provider_name)
        if error == "censored":
            return self.strings("enhance_censored").format(provider_name)
        if error == "timeout":
            return self.strings("enhance_timeout").format(provider_name)
        if error == "error":
            return self.strings("enhance_service_error").format(provider_name)
        if error == "vision_unsupported":
            return self.strings("enhance_vision_unsupported").format(provider_name)
        return self.strings("enhance_error").format(
            provider_name, utils.escape_html(str(error))
        )

    async def _run_direct_generation(self, target, state: dict, selected_loras=None):
        if selected_loras is None:
            selected_loras = state.get("selected_loras")
        selected_loras = self._normalize_selected_loras(selected_loras)
        state["selected_loras"] = dict(selected_loras)
        display_positive, display_model, display_wf = self._build_display_bundle(state)
        easter_egg = state.get("easter_egg")

        client_id = str(uuid.uuid4())
        self._generation_runtime[client_id] = {
            "prompt_id": None,
            "phase": "waiting_local",
            "executing": False,
            "cancelled": False,
            "current_node_id": None,
        }
        cancel_markup = [[{
            "text": self.strings("cancel_btn"),
            "callback": self._cancel_generation,
            "args": (client_id,),
            "style": "danger",
            "emoji_id": "5121063440311386962",
        }]]

        if isinstance(target, Message):
            initial_status_text = self._format_status_text(
                display_positive, display_model, display_wf, is_inline=False, easter_egg=easter_egg, status_key="fmt_loading_model",
            )
            if state.get("reuse_status_message"):
                status_is_inline = False
                status_form = await self._safe_answer(target, initial_status_text) or target
            else:
                status_is_inline = not state.get("plain_status")
            if status_is_inline:
                try:
                    status_form = await self._create_inline_form(
                        message=target,
                        text=self._format_status_text(
                            display_positive, display_model, display_wf, is_inline=True, easter_egg=easter_egg, status_key="fmt_loading_model",
                        ),
                        reply_markup=cancel_markup,
                    )
                except Exception as e:
                    logger.debug("Failed to create inline generation form: %s", e)
                    status_is_inline = False
                else:
                    status_form = status_form
            if not status_is_inline and not state.get("reuse_status_message"):
                status_is_inline = False
                status_form = await self._safe_answer(
                    target,
                    initial_status_text,
                )
                if not status_form:
                    self._cleanup_generation_runtime(client_id)
                    self._cleanup_input_file(state)
                    return
        else:
            status_is_inline = True
            try:
                await target.edit(
                    text=self._format_status_text(
                        display_positive, display_model, display_wf, is_inline=True, easter_egg=easter_egg, status_key="fmt_loading_model",
                    ),
                    reply_markup=cancel_markup,
                )
                status_form = target
            except Exception as e:
                logger.debug("Failed to edit inline generation status: %s", e)
                try:
                    await target.answer(
                        self._plain_text(self.strings("ult_state_expired")),
                        show_alert=True,
                    )
                except Exception as answer_error:
                    logger.debug("Failed to answer expired inline generation action: %s", answer_error)
                self._cleanup_generation_runtime(client_id)
                self._cleanup_input_file(state)
                return

        if self._semaphore.locked():
            try:
                queue_text = self._format_status_text(
                    display_positive,
                    display_model,
                    display_wf,
                    is_inline=status_is_inline,
                    easter_egg=easter_egg,
                    status_text=self.strings("queue_local_waiting"),
                )
                if status_is_inline:
                    await status_form.edit(text=queue_text, reply_markup=cancel_markup)
                else:
                    await utils.answer(status_form, self._apply_emoji_theme(queue_text))
            except Exception:
                pass

        async with self._semaphore:
            self._set_generation_phase(client_id, "preparing")
            if self._unloading:
                try:
                    await status_form.delete()
                except Exception:
                    pass
                self._cleanup_generation_runtime(client_id)
                self._cleanup_input_file(state)
                return
            self._active_generations += 1
            try:
                try:
                    preparing_text = self._format_status_text(
                        display_positive,
                        display_model,
                        display_wf,
                        is_inline=status_is_inline,
                        easter_egg=easter_egg,
                        status_key="fmt_loading_model",
                    )
                    if status_is_inline:
                        await status_form.edit(text=preparing_text, reply_markup=cancel_markup)
                    else:
                        await utils.answer(status_form, self._apply_emoji_theme(preparing_text))
                except Exception:
                    pass

                await self._raise_if_generation_cancelled(client_id)

                async def _update_connection_retry(next_attempt, total_attempts):
                    retry_text = self._format_status_text(
                        display_positive,
                        display_model,
                        display_wf,
                        is_inline=status_is_inline,
                        easter_egg=easter_egg,
                        status_text=self.strings("connecting_retry").format(next_attempt, total_attempts),
                    )
                    if status_is_inline:
                        await status_form.edit(text=retry_text, reply_markup=cancel_markup)
                    else:
                        await utils.answer(status_form, self._apply_emoji_theme(retry_text))

                if not state.get("health_checked"):
                    health = await self._health_check(on_retry=_update_connection_retry)
                    if not health:
                        raise UserFacingError("unavailable", self._plain_text(self.strings("unavailable")))

                await self._raise_if_generation_cancelled(client_id)
                wf_data = await self._ensure_workflow_data(state["wf_name"])
                if not wf_data:
                    available = ", ".join(self._get_all_workflow_names())
                    raise ValueError(
                        self.strings("wf_not_found").format(
                            utils.escape_html(state["wf_name"]),
                            utils.escape_html(available),
                        )
                    )

                await self._raise_if_generation_cancelled(client_id)
                input_filename = await self._upload_state_input_image(state)
                input_video_filename = await self._upload_state_input_video(state)

                await self._raise_if_generation_cancelled(client_id)
                prepared_workflow, final_output_node = await self._prepare_workflow(
                    wf_data,
                    state["positive"],
                    state["negative"],
                    state["seed"],
                    state["width"],
                    state["height"],
                    state["model"],
                    state["denoise"],
                    state["steps"],
                    state["cfg"],
                    state.get("sampler_name"),
                    state.get("scheduler"),
                    input_filename,
                    state["wf_name"],
                    state.get("limited_mode", False),
                    input_video_filename=input_video_filename,
                )

                if selected_loras:
                    prepared_workflow = self._inject_loras(
                        prepared_workflow,
                        wf_data,
                        selected_loras,
                    )

                self._sync_generation_state_from_workflow(state, wf_data, prepared_workflow)
                runtime = self._generation_runtime.get(client_id)
                if runtime is not None:
                    runtime["workflow"] = prepared_workflow

                async def _do_queue():
                    await self._raise_if_generation_cancelled(client_id)
                    self._set_generation_phase(client_id, "queueing")
                    return await self._retry(self._queue_prompt, prepared_workflow, client_id)

                _, history = await self._wait_ws(
                    client_id,
                    _do_queue,
                    status_form=status_form,
                    cancel_markup=cancel_markup,
                    display_positive=display_positive,
                    display_model=display_model,
                    display_wf=display_wf,
                    expected_output_node=final_output_node,
                    easter_egg=easter_egg,
                    workflow=prepared_workflow,
                    status_is_inline=status_is_inline,
                    generation_state=state,
                )

                try:
                    if status_is_inline:
                        await status_form.edit(text=self.strings("inline_uploading"))
                    else:
                        await utils.answer(status_form, self._apply_emoji_theme(self.strings("uploading")))
                except Exception:
                    pass
                self._set_generation_phase(client_id, "uploading")

                output_kind = (wf_data.get("mapping") or {}).get("output_kind") or "image"
                media_kind = "video" if output_kind in ("video", "mixed") else "image"
                media_info = (
                    self._extract_media_info(history, final_output_node, ("videos", "video", "animated", "animations", "gifs", "audio", "images"))
                    if media_kind == "video"
                    else self._extract_image_info(history, final_output_node)
                )
                if not media_info:
                    logger.warning(
                        "No media found in ComfyUI history for node %s; output_kind=%s; outputs=%s",
                        final_output_node,
                        output_kind,
                        self._history_output_summary(history),
                    )
                    raise UserFacingError("no_images", self._plain_text(self.strings("no_images")))
                media_kind = self._media_kind_from_info(media_info, media_kind)

                media_bio = await self._retry(self._retrieve_comfy_media, media_info, media_kind)
                media_bytes = None
                try:
                    media_size = self._file_size(media_bio) or 0
                    send_as_file = (
                        media_kind != "image"
                        or not self._telegram_photo_supported(media_info)
                        or self.config["output_format"] == "document_png"
                        or media_size > 50 * 1024 * 1024
                    )
                    if not send_as_file:
                        media_bytes = await utils.run_sync(self._read_file_bytes, media_bio)
                    generation_time = None
                    if self._show_generation_time_result():
                        generation_time = self._format_generation_time_value(
                            state.get("generation_duration")
                        )
                    generation_caption_hidden = (
                        self._telegram_censorship_enabled()
                        and media_kind == "image"
                        and self.config["output_format"] != "document_png"
                    )
                    result_display_positive = (
                        self._build_display_bundle(state, hidden_prompt=True)[0]
                        if generation_caption_hidden
                        else display_positive
                    )
                    caption = self._format_success_text(
                        display_positive,
                        display_model,
                        display_wf,
                        selected_loras=state.get("selected_loras"),
                        generation_time=generation_time,
                    )
                    result_caption = self._format_success_text(
                        result_display_positive,
                        display_model,
                        display_wf,
                        selected_loras=state.get("selected_loras"),
                        generation_time=generation_time,
                    )
                    auto_delete_delay = state.get("auto_delete_result_delay")
                    if auto_delete_delay:
                        result_caption = "\n".join(
                            [
                                result_caption,
                                self.strings("trigger_autodelete_caption").format(
                                    self._format_duration(auto_delete_delay)
                                ),
                            ]
                        )

                    if media_kind == "image":
                        if send_as_file:
                            sent_message = await self._send_file_result(
                                state["chat_id"],
                                media_bio,
                                result_caption,
                                reply_to=state["reply_to"],
                                force_document=True,
                            )
                        else:
                            sent_message = await self._send_result(
                                state["chat_id"],
                                media_bytes,
                                result_caption,
                                reply_to=state["reply_to"],
                                spoiler=generation_caption_hidden,
                            )
                    else:
                        sent_message = await self._send_file_result(
                            state["chat_id"],
                            media_bio,
                            result_caption,
                            reply_to=state["reply_to"],
                            force_document=True,
                        )
                    self._increment_total_generation_count()
                    if auto_delete_delay and sent_message:
                        self._track_auto_delete(sent_message, auto_delete_delay)
                    self._record_generation_duration_stat(state)
                    await self._send_generation_duplicate(
                        media_bytes if media_bytes is not None else media_bio,
                        caption,
                        state,
                        media_filename=getattr(media_bio, "name", None),
                        media_kind=media_kind,
                    )
                finally:
                    media_bio.close()
                    del media_bytes

                self._store_last_generation(state)

                try:
                    await status_form.delete()
                except Exception:
                    pass
            except asyncio.CancelledError:
                cancel_reason = self._get_cancel_reason(client_id) or "unknown"
                logger.warning("Generation cancelled: client_id=%s reason=%s", client_id, cancel_reason)
                try:
                    cancelled_text = f"{self.strings('cancelled')} <code>{utils.escape_html(cancel_reason)}</code>"
                    cancelled_text = self._to_inline_emoji(cancelled_text)
                    if status_is_inline:
                        await status_form.edit(text=cancelled_text, reply_markup=None)
                    else:
                        await utils.answer(status_form, self._apply_emoji_theme(cancelled_text))
                except Exception:
                    pass
            except Exception as e:
                if not await self._handle_trigger_generation_error(state, e, status_form):
                    await self._handle_gen_error(status_form, e)
            finally:
                self._active_generations = max(0, self._active_generations - 1)
                self._cleanup_input_file(state)

    async def _launch_generation_flow(self, target, state: dict):
        if state.get("use_lora_picker"):
            state_id = str(uuid.uuid4())
            lora_state = dict(state)
            lora_state["selected"] = self._normalize_lora_preset_entries(state.get("lora_entries"))
            lora_state["page"] = 0
            self._lora_states[state_id] = lora_state
            status_target = target
            if isinstance(target, Message):
                if state.get("reuse_status_message"):
                    status_target = await self._update_generation_preflight(target, "lora_loading") or target
                else:
                    status_target = await self._safe_answer(target, self.strings("lora_loading")) or target
            else:
                await self._update_generation_preflight(target, "lora_loading")
            await self._render_lora_list(status_target, state_id)
            return

        await self._run_direct_generation(target, state)

    def _build_enhance_chat_request(self, current_prompt, edit_text):
        return (
            "Current prompt:\n"
            f"{str(current_prompt or '').strip()}\n\n"
            "Requested edits:\n"
            f"{str(edit_text or '').strip()}\n\n"
            "Return only the updated final prompt. Keep important existing details unless the requested edits change them."
        )

    async def _start_enhance_chat(
        self,
        target,
        *,
        mode,
        prompt,
        original_prompt=None,
        generation_state=None,
        model=None,
        image_path=None,
    ):
        state_id = str(uuid.uuid4())
        self._enhance_chat_states[state_id] = {
            "mode": mode,
            "prompt": str(prompt or "").strip(),
            "original_prompt": str(original_prompt or prompt or "").strip(),
            "generation_state": generation_state,
            "model": model or (generation_state or {}).get("model") or self.config["model_name"] or "unknown",
            "image_path": image_path or (generation_state or {}).get("input_image_path"),
            "edits": [],
        }
        await self._render_enhance_chat(target, state_id)

    async def _render_enhance_chat(self, target, state_id: str):
        state = self._enhance_chat_states.get(state_id)
        if not state:
            text = self._to_inline_emoji(self.strings("ult_state_expired"))
            if isinstance(target, InlineCall):
                return await target.edit(text=text)
            return await self._safe_answer(target, text)

        edit_count = min(len(state.get("edits") or []), 100)
        title = f"{_PREFLIGHT_EYES_INLINE} {self.strings('enhance_chat_title').format(edit_count)}"
        text = "\n\n".join([
            title,
            self._format_prompt_for_display(state.get("prompt"), truncate=False),
        ])
        markup = [
            [{
                "text": self.strings("enhance_chat_edit_btn"),
                "input": self.strings("enhance_chat_input"),
                "handler": self._enhance_chat_edit_input,
                "args": (state_id,),
            }],
        ]
        if state.get("mode") == "generate":
            markup.append([
                {
                    "text": self.strings("ult_btn_generate"),
                    "callback": self._enhance_chat_generate,
                    "args": (state_id,),
                    "style": "success",
                    "emoji_id": "5206607081334906820",
                },
                {
                    "text": self.strings("ult_btn_cancel"),
                    "callback": self._enhance_chat_cancel,
                    "args": (state_id,),
                    "style": "danger",
                    "emoji_id": "5121063440311386962",
                },
            ])
        else:
            markup.append([{
                "text": self.strings("btn_close"),
                "callback": self._enhance_chat_cancel,
                "args": (state_id,),
                "style": "danger",
            }])
        await self._render_inline(target, self._to_inline_emoji(text), markup)

    async def _enhance_chat_edit_input(self, call: InlineCall, query: str, state_id: str):
        state = self._enhance_chat_states.get(state_id)
        if not state:
            return await call.edit(text=self._to_inline_emoji(self.strings("ult_state_expired")))
        edit_text = str(query or "").strip()
        if not edit_text:
            try:
                await call.answer(self._plain_text(self.strings("enhance_chat_empty")), show_alert=True)
            except Exception:
                pass
            return
        edits = list(state.get("edits") or [])
        if len(edits) >= 100:
            try:
                await call.answer(self._plain_text(self.strings("enhance_chat_limit")), show_alert=True)
            except Exception:
                pass
            return await self._render_enhance_chat(call, state_id)

        try:
            await call.edit(text=self._to_inline_emoji(self.strings("status_enhancing")))
        except Exception:
            pass
        enhanced, error = await self._enhance_prompt(
            self._build_enhance_chat_request(state.get("prompt"), edit_text),
            state.get("model") or "unknown",
            image_path=state.get("image_path"),
        )
        if error:
            try:
                await call.answer(self._plain_text(self._get_enhance_error_text(error)), show_alert=True)
            except Exception:
                pass
            return await self._render_enhance_chat(call, state_id)

        state["prompt"] = str(enhanced or "").strip()
        edits.append(edit_text)
        state["edits"] = edits[:100]
        generation_state = state.get("generation_state")
        if isinstance(generation_state, dict):
            generation_state["positive"] = state["prompt"]
            generation_state["enhanced"] = state["prompt"] != generation_state.get("original_positive")
        self._enhance_chat_states[state_id] = state
        await self._render_enhance_chat(call, state_id)

    async def _enhance_chat_generate(self, call: InlineCall, state_id: str):
        state = self._enhance_chat_states.pop(state_id, None)
        if not state:
            return await call.edit(text=self._to_inline_emoji(self.strings("ult_state_expired")))
        generation_state = state.get("generation_state")
        if not isinstance(generation_state, dict):
            return await self._enhance_chat_cancel(call, state_id)
        generation_state["positive"] = state.get("prompt") or generation_state.get("positive")
        generation_state["enhanced"] = generation_state["positive"] != generation_state.get("original_positive")
        generation_state["enhance_prompt"] = True
        await self._launch_generation_flow(call, generation_state)

    async def _enhance_chat_cancel(self, call: InlineCall, state_id: str):
        state = self._enhance_chat_states.pop(state_id, None)
        generation_state = state.get("generation_state") if isinstance(state, dict) else None
        if isinstance(generation_state, dict):
            self._cleanup_input_file(generation_state)
        try:
            await call.delete()
        except Exception:
            pass

    async def _render_enhance_confirm(self, target, state_id: str):
        state = self._enhance_confirm_states.get(state_id)
        if not state:
            if isinstance(target, InlineCall):
                await target.edit(text=self.strings("ult_state_expired"))
            else:
                await utils.answer(target, self._apply_emoji_theme(self.strings("ult_state_expired")))
            return

        lines = [
            self.strings("ult_confirm_title"),
            self.strings("ult_confirm_model").format(
                utils.escape_html(self._format_model_name(state["model"]))
            ),
            self.strings("ult_confirm_workflow").format(
                utils.escape_html(state["wf_name"])
            ),
            "",
            f"{self.strings('ult_confirm_source')}:",
            self._format_prompt_for_display(state["original_positive"], truncate=False),
            "",
        ]

        if state.get("censored"):
            lines.append(self.strings("ult_confirm_censored"))
        else:
            lines.extend(
                [
                    f"{self.strings('ult_confirm_result')}:",
                    self._format_prompt_for_display(state["enhanced_positive"], truncate=False),
                ]
            )

        markup = [
            [
                {
                    "text": self.strings("enhance_chat_edit_btn"),
                    "callback": self._enhance_confirm_open_chat,
                    "args": (state_id,),
                    "style": "primary",
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_regenerate"),
                    "callback": self._enhance_confirm_regenerate,
                    "args": (state_id,),
                    "style": "primary",
                    "emoji_id": "5258053877669657143",
                }
            ],
            [
                {
                    "text": self.strings("ult_btn_generate"),
                    "callback": self._enhance_confirm_generate,
                    "args": (state_id,),
                    "style": "success",
                    "emoji_id": "5206607081334906820",
                },
                {
                    "text": self.strings("ult_btn_cancel"),
                    "callback": self._enhance_confirm_cancel,
                    "args": (state_id,),
                    "style": "danger",
                    "emoji_id": "5121063440311386962",
                },
            ],
        ]

        text = "\n".join(lines)

        await self._render_inline(target, text, markup)

    async def _enhance_confirm_open_chat(self, call: InlineCall, state_id: str):
        state = self._enhance_confirm_states.pop(state_id, None)
        if not state:
            return await call.edit(text=self._to_inline_emoji(self.strings("ult_state_expired")))
        prompt = state.get("enhanced_positive") or state.get("positive") or state.get("original_positive")
        state["positive"] = prompt
        state["enhanced_positive"] = prompt
        state["censored"] = False
        await self._start_enhance_chat(
            call,
            mode="generate",
            prompt=prompt,
            original_prompt=state.get("original_positive"),
            generation_state=state,
            model=state.get("model") or "unknown",
            image_path=state.get("input_image_path"),
        )

    async def _enhance_confirm_regenerate(self, call: InlineCall, state_id: str):
        state = self._enhance_confirm_states.get(state_id)
        if not state:
            return await call.edit(text=self.strings("ult_state_expired"))

        try:
            await call.edit(text=self._to_inline_emoji(self.strings("status_enhancing")))
        except Exception:
            pass

        enhanced, error = await self._enhance_prompt(
            state["original_positive"],
            state["model"] or "unknown",
            image_path=state.get("input_image_path"),
        )

        if error and error != "censored":
            state = self._enhance_confirm_states.pop(state_id, None)
            if state:
                self._cleanup_input_file(state)
            return await call.edit(text=self._to_inline_emoji(self._get_enhance_error_text(error)))

        if error == "censored":
            state["censored"] = True
            state["positive"] = state["original_positive"]
            state["enhanced_positive"] = None
            state["enhanced"] = False
        else:
            state["censored"] = False
            state["positive"] = enhanced
            state["enhanced_positive"] = enhanced
            state["enhanced"] = enhanced != state["original_positive"]

        self._enhance_confirm_states[state_id] = state
        await self._render_enhance_confirm(call, state_id)

    async def _enhance_confirm_generate(self, call: InlineCall, state_id: str):
        state = self._enhance_confirm_states.pop(state_id, None)
        if not state:
            return await call.edit(text=self.strings("ult_state_expired"))

        generation_state = self._build_generation_state(
            positive=state["positive"],
            original_positive=state["original_positive"],
            negative=state["negative"],
            width=state["width"],
            height=state["height"],
            seed=state["seed"],
            denoise=state["denoise"],
            steps=state["steps"],
            cfg=state["cfg"],
            wf_name=state["wf_name"],
            model=state["model"],
            input_filename=state["input_filename"],
            input_image_name=state.get("input_image_name"),
            input_image_path=state.get("input_image_path"),
            input_video_name=state.get("input_video_name"),
            input_video_path=state.get("input_video_path"),
            chat_id=state["chat_id"],
            reply_to=state["reply_to"],
            enhance_prompt=state["enhance_prompt"],
            use_lora_picker=state["use_lora_picker"],
            enhanced=state.get("enhanced", False),
            easter_egg=state.get("easter_egg"),
            selected_loras=state.get("selected_loras"),
            auto_delete_result_delay=state.get("auto_delete_result_delay"),
            trigger_origin=state.get("trigger_origin"),
            sampler_name=state.get("sampler_name"),
            scheduler=state.get("scheduler"),
            limited_mode=state.get("limited_mode", False),
        )
        await self._launch_generation_flow(call, generation_state)

    async def _enhance_confirm_cancel(self, call: InlineCall, state_id: str):
        state = self._enhance_confirm_states.pop(state_id, None)
        if state:
            self._cleanup_input_file(state)
        try:
            await call.delete()
        except Exception:
            pass

    def _prepare_output_image(self, image_bytes, as_document):
        img_buf = io.BytesIO(image_bytes)
        img = None
        out = io.BytesIO()
        try:
            img = Image.open(img_buf)
            if as_document:
                if img.mode not in ("RGBA", "RGB"):
                    img = img.convert("RGBA")
                img.save(out, format="PNG")
                out.seek(0)
                out.name = "comfyui_result.png"
            else:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(out, format="JPEG", quality=95)
                out.seek(0)
                out.name = "comfyui_result.jpg"
            return out
        except Exception:
            out.close()
            raise
        finally:
            if img:
                img.close()
            img_buf.close()

    async def _send_spoiler_photo_result(self, chat_id, image_bytes, caption, reply_to=None):
        if not InputMediaUploadedPhoto:
            raise RuntimeError("InputMediaUploadedPhoto is unavailable")
        caption = self._apply_emoji_theme(caption)

        try:
            out = await utils.run_sync(self._prepare_output_image, image_bytes, False)
        except Exception as e:
            logger.error("Failed to process image: %s: %s", type(e).__name__, e)
            logger.exception(e)
            raise ValueError("Failed to process image") from e

        try:
            out.seek(0)
            uploaded = await self.client.upload_file(out, file_name=getattr(out, "name", "comfyui_result.jpg"))
            try:
                text, entities = self.client.parse_mode.parse(caption or "")
            except Exception:
                text, entities = caption or "", []
            request_reply_to = reply_to
            if (
                reply_to is not None
                and InputReplyToMessage
                and isinstance(reply_to, int)
            ):
                request_reply_to = InputReplyToMessage(reply_to_msg_id=reply_to)
            request = SendMediaRequest(
                peer=await self.client.get_input_entity(chat_id),
                media=InputMediaUploadedPhoto(file=uploaded, spoiler=True),
                message=text,
                random_id=random.getrandbits(63),
                reply_to=request_reply_to,
                entities=entities or [],
            )
            result = await self.client(request)
            try:
                return self.client._get_response_message(
                    request,
                    result,
                    await self.client.get_input_entity(chat_id),
                )
            except Exception:
                return None
        except Exception as e:
            logger.error("Failed to send spoiler photo: %s: %s", type(e).__name__, e)
            logger.exception(e)
            raise ValueError("Telegram send failed") from e
        finally:
            out.close()
            del out

    async def _send_result(self, chat_id, image_bytes, caption, reply_to=None, force_document=False, spoiler=False):
        caption = self._apply_emoji_theme(caption)
        output_format = self.config["output_format"]
        as_document = force_document or output_format == "document_png"

        if spoiler and not as_document:
            return await self._send_spoiler_photo_result(chat_id, image_bytes, caption, reply_to=reply_to)

        try:
            out = await utils.run_sync(self._prepare_output_image, image_bytes, as_document)
        except Exception as e:
            logger.error("Failed to process image: %s: %s", type(e).__name__, e)
            logger.exception(e)
            raise ValueError("Failed to process image") from e

        try:
            send_kwargs = {
                "caption": caption,
                "reply_to": reply_to,
                "force_document": as_document,
            }
            sent_message = await self.client.send_file(chat_id, out, **send_kwargs)
        except Exception as e:
            logger.error("Failed to send image: %s: %s", type(e).__name__, e)
            logger.exception(e)
            raise ValueError("Telegram send failed") from e
        finally:
            out.close()
            del out
        return sent_message

    async def _send_file_result(self, chat_id, file_obj, caption, reply_to=None, force_document=True):
        caption = self._apply_emoji_theme(caption)
        try:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            send_kwargs = {
                "caption": caption,
                "reply_to": reply_to,
                "force_document": force_document,
            }
            return await self.client.send_file(chat_id, file_obj, **send_kwargs)
        except Exception as e:
            logger.error("Failed to send media: %s: %s", type(e).__name__, e)
            logger.exception(e)
            raise ValueError("Telegram send failed") from e

    async def _schedule_delete_message(self, message_to_delete: Message, delay: int):
        try:
            await asyncio.sleep(max(0, int(delay)))
            await message_to_delete.delete()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("Failed to auto-delete message: %s", e)

    async def _retry(self, coro_func, *args, attempts=3, delay=2):
        last_err = None
        for i in range(attempts):
            try:
                return await coro_func(*args)
            except ComfyUIHTTPError as e:
                if e.temporary:
                    last_err = e
                    logger.warning("Temporary ComfyUI HTTP error (attempt %d/%d): %s", i + 1, attempts, e)
                    if i < attempts - 1:
                        await asyncio.sleep(delay * (2 ** i))
                    continue
                raise
            except ValueError as e:
                err_str = str(e)
                if any(code in err_str for code in ("HTTP 502", "HTTP 503", "HTTP 504")):
                    last_err = e
                    logger.warning("Temporary server error (attempt %d/%d): %s", i + 1, attempts, e)
                    if i < attempts - 1:
                        await asyncio.sleep(delay * (2 ** i))
                    continue
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                logger.exception(e)
                if i < attempts - 1:
                    await asyncio.sleep(delay * (i + 1))
            except Exception:
                raise
        raise last_err

    _ARGSET_VALIDATORS = {
        "steps": {"min": 1, "max": 100, "type": int},
        "cfg": {"min": 1.0, "max": 30.0, "type": float},
        "denoise": {"min": 0.0, "max": 1.0, "type": float},
        "width": {"min": 64, "max": 4096, "type": int},
        "height": {"min": 64, "max": 4096, "type": int},
    }

    _ARGSET_FALLBACKS = {
        "steps": 30,
        "cfg": 7.0,
        "denoise": 0.5,
        "width": 1024,
        "height": 1024,
    }

    _ARGSET_CHOICE_PARAMS = ("sampler_name", "scheduler")
    _SAMPLER_CHOICES = (
        "euler",
        "euler_cfg_pp",
        "euler_ancestral",
        "heun",
        "heunpp2",
        "dpm_2",
        "dpm_2_ancestral",
        "dpm_fast",
        "dpm_adaptive",
        "dpmpp_2s_ancestral",
        "dpmpp_2s_ancestral_cfg_pp",
        "dpmpp_sde",
        "dpmpp_sde_gpu",
        "ddpm",
        "lcm",
        "ipndm",
        "ipndm_v",
        "deis",
        "er_sde",
        "seeds_2",
        "seeds_3",
        "dpmpp_2m",
        "dpmpp_2m_cfg_pp",
        "dpmpp_2m_sde",
        "dpmpp_2m_sde_gpu",
    )
    _SCHEDULER_CHOICES = (
        "simple",
        "sgm_uniform",
        "karras",
        "exponential",
        "ddim_uniform",
        "beta",
        "normal",
        "linear_quadratic",
        "kl_optimal",
    )

    @staticmethod
    def _argset_enabled(data):
        value = data.get("enabled", False) if isinstance(data, dict) else data
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "enabled", "вкл", "включено", "да"}:
                return True
            if normalized in {"", "0", "false", "no", "off", "disabled", "выкл", "выключено", "нет"}:
                return False
        return bool(value)

    def _ensure_argset_entry(self, saved, param):
        data = saved.get(param, {})
        enabled = self._argset_enabled(data)
        if not isinstance(data, dict):
            data = {}
        data["enabled"] = enabled
        if param in self._ARGSET_FALLBACKS and "value" not in data:
            data["value"] = self._ARGSET_FALLBACKS[param]
        saved[param] = data
        return data

    @staticmethod
    def _normalize_argset_choice_value(value):
        value = str(value or "").strip()
        if not value:
            return None
        return value[:80]

    def _argset_choice_values(self, param):
        if param == "sampler_name":
            return self._SAMPLER_CHOICES
        if param == "scheduler":
            return self._SCHEDULER_CHOICES
        return ()

    def _ensure_choice_argset_entry(self, saved, param):
        data = saved.get(param, {})
        enabled = self._argset_enabled(data)
        if not isinstance(data, dict):
            data = {}
        data["enabled"] = enabled
        data["value"] = self._normalize_argset_choice_value(data.get("value"))
        data["custom"] = self._normalize_argset_choice_value(data.get("custom"))
        saved[param] = data
        return data

    def _argset_choice_value(self, data):
        if isinstance(data, dict):
            return self._normalize_argset_choice_value(data.get("value"))
        return None

    def _argset_value(self, data, param):
        if isinstance(data, dict):
            return data.get("value", self._ARGSET_FALLBACKS[param])
        return self._ARGSET_FALLBACKS[param]

    @staticmethod
    def _build_button_rows(buttons, columns=2):
        rows = []
        row = []
        for button in buttons:
            row.append(button)
            if len(row) == columns:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return rows

    def _load_defaults_from_workflow(self, wf_name):
        wf_data = self._get_workflow_data(wf_name)
        if not wf_data:
            return dict(self._ARGSET_FALLBACKS)

        workflow = wf_data["workflow"]
        mapping = wf_data.get("mapping", {})
        if not mapping:
            mapping = self._parse_workflow(workflow)

        result = {}
        for param, fallback in self._ARGSET_FALLBACKS.items():
            m = mapping.get(param)
            if m and m.get("node_id") and m.get("field"):
                node = workflow.get(m["node_id"], {})
                val = node.get("inputs", {}).get(m["field"])
                if val is not None:
                    try:
                        result[param] = self._ARGSET_VALIDATORS[param]["type"](val)
                        continue
                    except (ValueError, TypeError):
                        pass
            result[param] = fallback
        for param in self._ARGSET_CHOICE_PARAMS:
            result[param] = self._normalize_argset_choice_value(
                self._workflow_mapping_value(workflow, mapping.get(param))
            )
        return result

    @staticmethod
    def _clone_argset_data(data):
        if not isinstance(data, dict):
            return {}
        try:
            return json.loads(json.dumps(data))
        except Exception:
            return dict(data)

    def _build_default_args_for_workflow(self, wf_name=None):
        wf_name = self._canonical_workflow_name(
            wf_name or self.get("default_workflow", _DEFAULT_WORKFLOW_NAME)
        )
        values = self._load_defaults_from_workflow(wf_name)
        defaults = {}
        for param in ("width", "height", "steps", "cfg", "denoise"):
            defaults[param] = {"enabled": False, "value": values.get(param, self._ARGSET_FALLBACKS[param])}
        for param in self._ARGSET_CHOICE_PARAMS:
            defaults[param] = {"enabled": False, "value": None, "custom": None}
        defaults["lora"] = self._get_global_lora_data()
        return defaults

    def _normalize_default_args(self, saved):
        if not isinstance(saved, dict):
            saved = {}
        legacy_ai = saved.pop("ai", None)
        if self._argset_enabled(legacy_ai):
            settings = self._get_ult_settings()
            settings["ai_enhance"]["enabled"] = True
            self._set_ult_settings(settings)
        saved.pop("anime_upscale", None)
        for param in ("width", "height", "steps", "cfg", "denoise"):
            self._ensure_argset_entry(saved, param)
        for param in self._ARGSET_CHOICE_PARAMS:
            self._ensure_choice_argset_entry(saved, param)
        self._ensure_lora_argset_entry(saved)
        return saved

    def _ensure_default_args(self):
        saved = self.get("default_args", {})
        if isinstance(saved, dict) and saved:
            saved = self._normalize_default_args(saved)
            self.set("default_args", saved)
            if not self.get("argset_active_model_key"):
                self.set("argset_active_model_key", self._argset_profile_key())
            return
        defaults = self._build_default_args_for_workflow()
        self.set("default_args", defaults)
        if not self.get("argset_active_model_key"):
            self.set("argset_active_model_key", self._argset_profile_key())

    def _argset_profile_key(self, wf_name=None, model_name=None):
        wf_name = self._canonical_workflow_name(
            wf_name or self.get("default_workflow", _DEFAULT_WORKFLOW_NAME)
        )
        model_name = str(
            model_name if model_name is not None else self.config["model_name"]
        ).strip() or "default"
        return f"{wf_name}\n{model_name}"

    def _sync_argset_for_current_model(self, force=False):
        profile_key = self._argset_profile_key()
        active_key = self.get("argset_active_model_key")
        if not force and not active_key:
            saved = self.get("default_args", {})
            if isinstance(saved, dict) and saved:
                saved = self._normalize_default_args(saved)
                self.set("default_args", saved)
                self.set("argset_active_model_key", profile_key)
                return
        if not force and active_key == profile_key:
            saved = self.get("default_args", {})
            if isinstance(saved, dict) and saved:
                self._ensure_default_args()
                return

        profiles = self.get("model_arg_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        profile = profiles.get(profile_key)
        if isinstance(profile, dict):
            saved = self._normalize_default_args(self._clone_argset_data(profile))
        else:
            wf_name = self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))
            saved = self._build_default_args_for_workflow(wf_name)

        self.set("default_args", saved)
        self.set("argset_active_model_key", profile_key)

    def _save_argset_profile_for_current_model(self):
        self._ensure_default_args()
        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        saved = self._normalize_default_args(saved)
        profiles = self.get("model_arg_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        profile_key = self._argset_profile_key()
        profile = self._clone_argset_data(saved)
        profile.pop("lora", None)
        profiles[profile_key] = profile
        self.set("model_arg_profiles", profiles)
        self.set("argset_active_model_key", profile_key)

    def _update_default_arg_values(self):
        self._sync_argset_for_current_model(force=True)

    def _validate_argset_value(self, param, value_str):
        v = self._ARGSET_VALIDATORS.get(param)
        if not v:
            return False, None
        try:
            val = v["type"](value_str)
        except (ValueError, TypeError):
            return False, None
        if val < v["min"] or val > v["max"]:
            return False, None
        if v.get("step") and val % v["step"] != 0:
            return False, None
        return True, val

    def _argset_current_workflow_choice(self, param):
        wf_name = self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))
        values = self._load_defaults_from_workflow(wf_name)
        return self._normalize_argset_choice_value(values.get(param))

    def _argset_effective_choice(self, data, workflow_value):
        if self._argset_enabled(data):
            return self._argset_choice_value(data) or workflow_value
        return workflow_value

    def _format_argset_choice_value(self, value):
        return utils.escape_html(value or self.strings("not_set"))

    def _argset_footer_row(self, back_callback=None, args=()):
        row = []
        if back_callback:
            button = {"text": self.strings("btn_back"), "callback": back_callback}
            if args:
                button["args"] = args
            row.append(button)
        row.append({"text": self.strings("btn_close"), "callback": self._safe_close_form, "style": "danger"})
        return row

    async def _argset_render_main(self, target):
        self._sync_argset_for_current_model()
        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        if self._workflow_limited_mode():
            lines = [
                self.strings("argset_title"),
                "",
                self.strings("argset_limited_mode"),
            ]
            markup = [
                [{"text": self.strings("btn_close"), "callback": self._safe_close_form, "style": "danger"}],
            ]
            return await self._render_inline(target, "\n".join(lines), markup)

        lines = [self.strings("argset_title"), ""]

        lines.append(self.strings("argset_params"))
        for param in ("width", "height", "steps", "cfg", "denoise"):
            data = saved.get(param, {})
            icon = self.strings("argset_on") if self._argset_enabled(data) else self.strings("argset_off")
            lines.append(f"  {icon} {param.upper() if param == 'cfg' else param.capitalize()}: {self._argset_value(data, param)}")
        for param in self._ARGSET_CHOICE_PARAMS:
            data = self._ensure_choice_argset_entry(saved, param)
            workflow_value = self._argset_current_workflow_choice(param)
            effective_value = self._argset_effective_choice(data, workflow_value)
            icon = self.strings("argset_on") if self._argset_enabled(data) else self.strings("argset_off")
            lines.append(
                f"  {icon} {self.strings(f'label_{param}')}: {self._format_argset_choice_value(effective_value)}"
            )

        lines.append("")
        lines.append(self.strings("argset_enhancements"))
        lora_data = self._ensure_lora_argset_entry(saved)
        lora_icon = self.strings("argset_on") if self._argset_enabled(lora_data) else self.strings("argset_off")
        lines.append(f"  {lora_icon} {self.strings('label_lora_presets')}: {self._format_lora_preset_summary(lora_data)}")

        text = "\n".join(lines)
        markup = [
            [
                {"text": self.strings("btn_params"), "callback": self._argset_cat_params},
            ],
            [
                {"text": self.strings("label_sampler_name"), "callback": self._argset_choice_menu, "args": ("sampler_name",), "style": "primary"},
                {"text": self.strings("label_scheduler"), "callback": self._argset_choice_menu, "args": ("scheduler",), "style": "primary"},
            ],
            [{"text": self.strings("argset_pin_model"), "callback": self._argset_pin_model, "style": "success"}],
            [{"text": self.strings("btn_enhancements"), "callback": self._argset_cat_enhancements}],
            [{"text": self._plain_text(self.strings("positive_menu_title")), "callback": self._argset_positive_menu}],
            [{"text": self._plain_text(self.strings("negative_menu_title")), "callback": self._argset_negative_menu}],
            [
                {"text": self.strings("btn_reset_all"), "callback": self._argset_reset, "style": "danger"},
                {"text": self.strings("btn_close"), "callback": self._safe_close_form, "style": "danger"},
            ],
        ]

        await self._render_inline(target, text, markup)

    async def _argset_cat_params(self, call: InlineCall):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)

        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        lines = [self.strings("argset_params"), ""]

        buttons = []
        for param in ("width", "height", "steps", "cfg", "denoise"):
            data = saved.get(param, {})
            enabled = self._argset_enabled(data)
            icon = self.strings("argset_on") if enabled else self.strings("argset_off")
            label = param.upper() if param == "cfg" else param.capitalize()
            lines.append(f"{icon} {label}: {self._argset_value(data, param)}")
            toggle_text = f"{self._state_toggle_text(enabled)} {label}"
            buttons.extend(
                [
                    {
                        "text": toggle_text,
                        "callback": self._argset_toggle,
                        "args": (param, "params"),
                        "style": self._state_toggle_style(enabled),
                        "emoji_id": self._state_toggle_emoji(enabled),
                    },
                    {
                        "text": "\u270f\ufe0f " + label,
                        "input": self.strings(f"argset_input_{param}"),
                        "handler": self._argset_input_handler,
                        "args": (param, "params"),
                    },
                ]
            )

        markup = self._build_button_rows(buttons)
        markup.append(self._argset_footer_row(self._argset_back))
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_cat_enhancements(self, call: InlineCall):
        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        if self._workflow_limited_mode():
            lines = [
                self.strings("argset_enhancements"),
                "",
                self.strings("argset_limited_mode"),
            ]
            markup = [
                self._argset_footer_row(self._argset_back),
            ]
            return await self._render_inline(call, "\n".join(lines), markup)

        lines = [self.strings("argset_enhancements"), ""]

        buttons = []
        lora_data = self._ensure_lora_argset_entry(saved)
        lora_enabled = self._argset_enabled(lora_data)
        lora_label = self.strings("label_lora_presets")
        lora_icon = self.strings("argset_on") if lora_enabled else self.strings("argset_off")
        lines.append(f"{lora_icon} {lora_label}: {self._format_lora_preset_summary(lora_data)}")
        toggle_text = f"{self._state_toggle_text(lora_enabled)} {lora_label}"
        buttons.extend(
            [
                {
                    "text": toggle_text,
                    "callback": self._argset_toggle,
                    "args": ("lora", "enhancements"),
                    "style": self._state_toggle_style(lora_enabled),
                    "emoji_id": self._state_toggle_emoji(lora_enabled),
                },
                {"text": "\U0001f3a8 " + lora_label, "callback": self._argset_lora_menu},
            ]
        )

        markup = self._build_button_rows(buttons)
        markup.append(self._argset_footer_row(self._argset_back))
        await self._render_inline(call, "\n".join(lines), markup)

    def _workflow_positive_source(self, wf_name):
        _, source = self._resolve_positive_prompt(wf_name)
        return source

    async def _argset_positive_menu(self, call: InlineCall):
        global_positive = self._get_global_positive_prompt()
        wf_names = self._get_all_workflow_names()
        lines = [
            self.strings("positive_menu_title"),
            "",
            self.strings("positive_global") + ":",
            self._format_negative_quote(global_positive, limit=None),
            "",
            self.strings("positive_workflows") + ":",
        ]
        for wf_name in wf_names:
            positive, source = self._resolve_positive_prompt(wf_name)
            positive_display = (
                self._format_negative_quote(self._negative_source_label(source), limit=None)
                if source == "global"
                else self._format_negative_quote(positive, limit=None)
            )
            lines.append(
                f"{self._negative_source_icon(source)} {utils.escape_html(wf_name)}:\n{positive_display}"
            )

        buttons = [{"text": self.strings("positive_btn_global"), "callback": self._argset_positive_global}]
        for wf_name in wf_names:
            source = self._workflow_positive_source(wf_name)
            icon = "\u2705 " if source == "custom" else "\u2b1c "
            label = wf_name
            if len(label) > 24:
                label = label[:21] + "..."
            buttons.append(
                {
                    "text": icon + label,
                    "callback": self._argset_positive_workflow,
                    "args": (wf_name,),
                    "style": "success" if source == "custom" else "primary",
                }
            )

        markup = self._build_button_rows(buttons, columns=2)
        markup.append(self._argset_footer_row(self._argset_back))
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_positive_global(self, call: InlineCall):
        global_positive = self._get_global_positive_prompt()
        lines = [
            self.strings("positive_btn_global"),
            "",
            self.strings("positive_current"),
            self._format_negative_quote(global_positive, limit=None),
        ]
        markup = [
            [
                {
                    "text": self.strings("positive_btn_set"),
                    "input": self.strings("positive_input_global"),
                    "handler": self._argset_positive_global_input,
                }
            ],
            [
                {
                    "text": self.strings("positive_btn_reset"),
                    "callback": self._argset_positive_global_reset,
                    "style": "success",
                },
                {
                    "text": self.strings("positive_btn_clear"),
                    "callback": self._argset_positive_global_clear,
                    "style": "danger",
                },
            ],
            self._argset_footer_row(self._argset_positive_menu),
        ]
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_positive_global_input(self, call: InlineCall, query: str):
        self._set_global_positive_prompt(query)
        try:
            await call.answer(self.strings("positive_saved"))
        except Exception:
            pass
        await self._argset_positive_global(call)

    async def _argset_positive_global_reset(self, call: InlineCall):
        self._set_global_positive_prompt(_GLOBAL_POSITIVE_DEFAULT)
        try:
            await call.answer(self.strings("positive_reset"))
        except Exception:
            pass
        await self._argset_positive_global(call)

    async def _argset_positive_global_clear(self, call: InlineCall):
        self._set_global_positive_prompt("")
        try:
            await call.answer(self.strings("positive_cleared"))
        except Exception:
            pass
        await self._argset_positive_global(call)

    async def _argset_positive_workflow(self, call: InlineCall, wf_name: str):
        wf_name = self._canonical_workflow_name(wf_name)
        current, _ = self._resolve_positive_prompt(wf_name)
        workflow_positives = self._get_workflow_positive_prompts()
        custom = workflow_positives.get(wf_name, "")
        global_positive = self._get_global_positive_prompt()

        lines = [
            f"{self.strings('positive_menu_title')}: {utils.escape_html(wf_name)}",
            "",
            self.strings("positive_current"),
            self._format_negative_quote(current, limit=None),
            "",
            self.strings("positive_custom"),
            self._format_negative_quote(custom, limit=None),
            "",
            self.strings("positive_global_label"),
            self._format_negative_quote(global_positive, limit=None),
        ]
        markup = [
            [
                {
                    "text": self.strings("positive_btn_set"),
                    "input": self.strings("positive_input_workflow").format(wf_name),
                    "handler": self._argset_positive_workflow_input,
                    "args": (wf_name,),
                }
            ],
            [
                {
                    "text": self.strings("positive_btn_reset"),
                    "callback": self._argset_positive_workflow_reset,
                    "args": (wf_name,),
                    "style": "success",
                }
            ],
            self._argset_footer_row(self._argset_positive_menu),
        ]
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_positive_workflow_input(self, call: InlineCall, query: str, wf_name: str):
        self._set_workflow_positive_prompt(wf_name, query)
        try:
            await call.answer(self.strings("positive_saved"))
        except Exception:
            pass
        await self._argset_positive_workflow(call, wf_name)

    async def _argset_positive_workflow_reset(self, call: InlineCall, wf_name: str):
        self._reset_workflow_positive_prompt(wf_name)
        try:
            await call.answer(self.strings("positive_reset"))
        except Exception:
            pass
        await self._argset_positive_workflow(call, wf_name)

    def _workflow_negative_source(self, wf_name):
        wf_name = self._canonical_workflow_name(wf_name)
        wf_data = self._get_workflow_data(wf_name)
        _, source = self._resolve_negative_prompt(wf_name, wf_data)
        return source

    async def _argset_negative_menu(self, call: InlineCall):
        global_negative = self._get_global_negative_prompt()
        wf_names = self._get_all_workflow_names()
        lines = [
            self.strings("negative_menu_title"),
            "",
            self.strings("negative_global") + ":",
            self._format_negative_quote(global_negative, limit=None),
            "",
            self.strings("negative_workflows") + ":",
        ]
        for wf_name in wf_names:
            wf_data = self._get_workflow_data(wf_name)
            negative, source = self._resolve_negative_prompt(wf_name, wf_data)
            negative_display = (
                self._format_negative_quote(self._negative_source_label(source), limit=None)
                if source == "global"
                else self._format_negative_quote(negative, limit=None)
            )
            lines.append(
                f"{self._negative_source_icon(source)} {utils.escape_html(wf_name)}:\n{negative_display}"
            )

        buttons = [{"text": self.strings("negative_btn_global"), "callback": self._argset_negative_global}]
        for wf_name in wf_names:
            source = self._workflow_negative_source(wf_name)
            icon = "\u2705 " if source == "custom" else "\u2b1c "
            label = wf_name
            if len(label) > 24:
                label = label[:21] + "..."
            buttons.append(
                {
                    "text": icon + label,
                    "callback": self._argset_negative_workflow,
                    "args": (wf_name,),
                    "style": "success" if source == "custom" else "primary",
                }
            )

        markup = self._build_button_rows(buttons, columns=2)
        markup.append(self._argset_footer_row(self._argset_back))
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_negative_global(self, call: InlineCall):
        global_negative = self._get_global_negative_prompt()
        lines = [
            self.strings("negative_btn_global"),
            "",
            self.strings("negative_current"),
            self._format_negative_quote(global_negative, limit=None),
        ]
        markup = [
            [
                {
                    "text": self.strings("negative_btn_set"),
                    "input": self.strings("negative_input_global"),
                    "handler": self._argset_negative_global_input,
                }
            ],
            [
                {
                    "text": self.strings("negative_btn_reset"),
                    "callback": self._argset_negative_global_reset,
                    "style": "success",
                },
                {
                    "text": self.strings("negative_btn_clear"),
                    "callback": self._argset_negative_global_clear,
                    "style": "danger",
                },
            ],
            self._argset_footer_row(self._argset_negative_menu),
        ]
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_negative_global_input(self, call: InlineCall, query: str):
        self._set_global_negative_prompt(query)
        try:
            await call.answer(self.strings("negative_saved"))
        except Exception:
            pass
        await self._argset_negative_global(call)

    async def _argset_negative_global_reset(self, call: InlineCall):
        self._set_global_negative_prompt(_GLOBAL_NEGATIVE_DEFAULT)
        try:
            await call.answer(self.strings("negative_reset"))
        except Exception:
            pass
        await self._argset_negative_global(call)

    async def _argset_negative_global_clear(self, call: InlineCall):
        self._set_global_negative_prompt("")
        try:
            await call.answer(self.strings("negative_cleared"))
        except Exception:
            pass
        await self._argset_negative_global(call)

    async def _argset_negative_workflow(self, call: InlineCall, wf_name: str):
        wf_name = self._canonical_workflow_name(wf_name)
        wf_data = self._get_workflow_data(wf_name)
        current, _ = self._resolve_negative_prompt(wf_name, wf_data)
        workflow_negatives = self._get_workflow_negative_prompts()
        custom = workflow_negatives.get(wf_name, "")
        global_negative = self._get_global_negative_prompt()

        lines = [
            f"{self.strings('negative_menu_title')}: {utils.escape_html(wf_name)}",
            "",
            self.strings("negative_current"),
            self._format_negative_quote(current, limit=None),
            "",
            self.strings("negative_custom"),
            self._format_negative_quote(custom, limit=None),
            "",
            self.strings("negative_global_label"),
            self._format_negative_quote(global_negative, limit=None),
        ]
        markup = [
            [
                {
                    "text": self.strings("negative_btn_set"),
                    "input": self.strings("negative_input_workflow").format(wf_name),
                    "handler": self._argset_negative_workflow_input,
                    "args": (wf_name,),
                }
            ],
            [
                {
                    "text": self.strings("negative_btn_reset"),
                    "callback": self._argset_negative_workflow_reset,
                    "args": (wf_name,),
                    "style": "success",
                }
            ],
            self._argset_footer_row(self._argset_negative_menu),
        ]
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_negative_workflow_input(self, call: InlineCall, query: str, wf_name: str):
        self._set_workflow_negative_prompt(wf_name, query)
        try:
            await call.answer(self.strings("negative_saved"))
        except Exception:
            pass
        await self._argset_negative_workflow(call, wf_name)

    async def _argset_negative_workflow_reset(self, call: InlineCall, wf_name: str):
        self._reset_workflow_negative_prompt(wf_name)
        try:
            await call.answer(self.strings("negative_reset"))
        except Exception:
            pass
        await self._argset_negative_workflow(call, wf_name)

    async def _argset_lora_menu(self, call: InlineCall, state_id: str = None):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)

        lora_data = self._get_default_lora_data()
        if state_id is None or state_id not in self._argset_lora_states:
            state_id = str(uuid.uuid4())
            self._argset_lora_states[state_id] = {
                "page": 0,
                "selected": self._normalize_lora_preset_entries(lora_data.get("selected")),
            }
        await self._render_argset_lora_list(call, state_id)

    async def _render_argset_lora_list(self, call_or_message, state_id):
        state = self._argset_lora_states.get(state_id)
        if not state:
            return
        all_loras = await self._get_available_loras()
        if not all_loras:
            return await self._safe_answer(call_or_message, self.strings("lora_none_available"))
        state["selected"] = self._normalize_lora_preset_entries(state.get("selected"), all_loras)
        page = state["page"]
        per_page = 6
        total_pages = max(1, (len(all_loras) + per_page - 1) // per_page)
        page = min(page, total_pages - 1)
        state["page"] = page
        start = page * per_page
        page_loras = all_loras[start:start + per_page]

        lines = [self.strings("lora_presets_title")]
        if not state["selected"]:
            lines.append(self.strings("lora_presets_empty"))
        lines.append("")
        for lora in page_loras:
            entry = state["selected"].get(lora, {"enabled": False, "weight": 0.75})
            is_on = bool(entry.get("enabled"))
            weight = entry.get("weight", 0.75)
            icon = self.strings("argset_on") if is_on else self.strings("argset_off")
            lines.append(f"{icon} {utils.escape_html(self._format_lora_name(lora, max_length=None))} ({weight:.1f})")
        lines.append(self.strings("lora_page").format(page + 1, total_pages))

        buttons = []
        for lora in page_loras:
            short_name = self._format_lora_name(lora, max_length=None)
            if len(short_name) > 20:
                short_name = short_name[:18] + ".."
            icon = "\u2705 " if state["selected"].get(lora, {}).get("enabled") else "\u2b1c "
            buttons.append(
                {
                    "text": f"{icon}{short_name}",
                    "callback": self._argset_lora_detail,
                    "args": (state_id, lora),
                }
            )

        markup = self._build_button_rows(buttons)
        nav_row = []
        if page > 0:
            nav_row.append({"text": "\u25c0\ufe0f", "callback": self._argset_lora_page, "args": (state_id, -1)})
        if page < total_pages - 1:
            nav_row.append({"text": "\u25b6\ufe0f", "callback": self._argset_lora_page, "args": (state_id, 1)})
        if nav_row:
            markup.append(nav_row)
        markup.append(
            [
                {"text": self.strings("lora_presets_clear"), "callback": self._argset_lora_clear, "args": (state_id,)},
                {"text": self.strings("btn_back"), "callback": self._argset_back},
                {"text": self.strings("btn_close"), "callback": self._safe_close_form, "style": "danger"},
            ]
        )
        await self._render_inline(call_or_message, "\n".join(lines), markup)

    async def _argset_lora_page(self, call: InlineCall, state_id: str, direction: int):
        state = self._argset_lora_states.get(state_id)
        if not state:
            return
        state["page"] += direction
        await self._render_argset_lora_list(call, state_id)

    async def _argset_lora_detail(self, call: InlineCall, state_id: str, lora_name: str):
        state = self._argset_lora_states.get(state_id)
        if not state:
            return
        short_name = self._format_lora_name(lora_name, max_length=30)
        entry = state["selected"].get(lora_name, {"enabled": False, "weight": 0.75})
        is_on = bool(entry.get("enabled"))
        weight = entry.get("weight", 0.75)
        status_text = self.strings("lora_on") if is_on else self.strings("lora_off")

        text = self.strings("lora_detail_title").format(
            utils.escape_html(short_name), weight, status_text
        )

        toggle_text = self._state_toggle_text(is_on)
        toggle_style = self._state_toggle_style(is_on)
        toggle_emoji = self._state_toggle_emoji(is_on)

        markup = [
            [
                {"text": "\u2796 0.1", "callback": self._argset_lora_weight, "args": (state_id, lora_name, -0.1)},
                {"text": "\u2795 0.1", "callback": self._argset_lora_weight, "args": (state_id, lora_name, 0.1)},
            ],
            [
                {
                    "text": self.strings("lora_weight_btn"),
                    "input": self.strings("lora_weight_input"),
                    "handler": self._argset_lora_weight_input,
                    "args": (state_id, lora_name),
                }
            ],
            [{"text": toggle_text, "callback": self._argset_lora_toggle, "args": (state_id, lora_name), "style": toggle_style, "emoji_id": toggle_emoji}],
            self._argset_footer_row(self._argset_lora_back, (state_id,)),
        ]

        await self._render_inline(call, text, markup)

    async def _argset_lora_weight(self, call: InlineCall, state_id: str, lora_name: str, delta: float):
        state = self._argset_lora_states.get(state_id)
        if not state:
            return
        entry = state["selected"].get(lora_name, {"enabled": False, "weight": 0.75})
        current = entry.get("weight", 0.75)
        state["selected"][lora_name] = {
            "enabled": bool(entry.get("enabled")),
            "weight": round(max(0.1, min(2.0, current + delta)), 1),
        }
        self._save_argset_lora_presets(state["selected"])
        await self._argset_lora_detail(call, state_id, lora_name)

    async def _argset_lora_weight_input(self, call: InlineCall, query: str, state_id: str, lora_name: str):
        state = self._argset_lora_states.get(state_id)
        if not state:
            return
        try:
            weight = round(float(query.strip().replace(",", ".")), 1)
        except (TypeError, ValueError):
            try:
                await call.answer(self.strings("toast_invalid_value").format(query), show_alert=True)
            except Exception:
                pass
            return
        if weight < 0.1 or weight > 2.0:
            try:
                await call.answer(self.strings("toast_invalid_value").format(query), show_alert=True)
            except Exception:
                pass
            return
        entry = state["selected"].get(lora_name, {"enabled": False, "weight": 0.75})
        state["selected"][lora_name] = {
            "enabled": bool(entry.get("enabled")),
            "weight": weight,
        }
        self._save_argset_lora_presets(state["selected"])
        try:
            await call.answer(self.strings("lora_weight_saved"))
        except Exception:
            pass
        await self._argset_lora_detail(call, state_id, lora_name)

    async def _argset_lora_toggle(self, call: InlineCall, state_id: str, lora_name: str):
        state = self._argset_lora_states.get(state_id)
        if not state:
            return
        entry = state["selected"].get(lora_name, {"enabled": False, "weight": 0.75})
        state["selected"][lora_name] = {
            "enabled": not bool(entry.get("enabled")),
            "weight": entry.get("weight", 0.75),
        }
        self._save_argset_lora_presets(state["selected"])
        try:
            await call.answer(self.strings("lora_presets_saved"))
        except Exception:
            pass
        await self._argset_lora_detail(call, state_id, lora_name)

    async def _argset_lora_clear(self, call: InlineCall, state_id: str):
        state = self._argset_lora_states.get(state_id)
        if not state:
            return
        state["selected"] = {}
        self._save_argset_lora_presets({})
        try:
            await call.answer(self.strings("lora_presets_saved"))
        except Exception:
            pass
        await self._render_argset_lora_list(call, state_id)

    async def _argset_lora_back(self, call: InlineCall, state_id: str):
        await self._render_argset_lora_list(call, state_id)

    def _save_argset_lora_presets(self, selected_loras):
        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        data = self._get_global_lora_data()
        data["selected"] = self._normalize_lora_preset_entries(selected_loras)
        data = self._set_global_lora_data(data)
        saved["lora"] = self._clone_argset_data(data)
        self.set("default_args", saved)

    async def _argset_choice_menu(self, call: InlineCall, param: str):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)

        if param not in self._ARGSET_CHOICE_PARAMS:
            return await self._argset_render_main(call)
        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        data = self._ensure_choice_argset_entry(saved, param)
        self.set("default_args", saved)

        label = self.strings(f"label_{param}")
        workflow_value = self._argset_current_workflow_choice(param)
        effective_value = self._argset_effective_choice(data, workflow_value)
        choices = list(self._argset_choice_values(param))
        custom_value = self._normalize_argset_choice_value(data.get("custom"))

        for value in (custom_value, workflow_value, effective_value):
            if value and value not in choices:
                choices.append(value)

        lines = [
            label,
            "",
            self.strings("argset_choice_workflow").format(self._format_argset_choice_value(workflow_value)),
            self.strings("argset_choice_used").format(self._format_argset_choice_value(effective_value)),
        ]

        buttons = []
        for value in choices:
            is_active = bool(effective_value and value == effective_value)
            buttons.append(
                {
                    "text": ("\u2705 " if is_active else "") + value,
                    "callback": self._argset_choice_select,
                    "args": (param, value),
                    **({"style": "success"} if is_active else {}),
                }
            )

        markup = self._build_button_rows(buttons, columns=2)
        custom_row = [
            {
                "text": self.strings("argset_choice_custom"),
                "input": self.strings(f"argset_input_{param}"),
                "handler": self._argset_choice_custom_input,
                "args": (param,),
            }
        ]
        if custom_value or (workflow_value and workflow_value not in self._argset_choice_values(param)):
            custom_row.append(
                {
                    "text": self.strings("argset_choice_clear"),
                    "callback": self._argset_choice_clear,
                    "args": (param,),
                    "style": "danger",
                }
            )
        markup.append(custom_row)
        if self._argset_enabled(data):
            markup.append(
                [
                    {
                        "text": self.strings("argset_choice_as_workflow"),
                        "callback": self._argset_choice_as_workflow,
                        "args": (param,),
                        "style": "primary",
                    }
                ]
            )
        markup.append(self._argset_footer_row(self._argset_back))
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_choice_select(self, call: InlineCall, param: str, value: str):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)

        if param not in self._ARGSET_CHOICE_PARAMS:
            return
        value = self._normalize_argset_choice_value(value)
        if not value:
            return
        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        data = self._ensure_choice_argset_entry(saved, param)
        workflow_value = self._argset_current_workflow_choice(param)
        if workflow_value and value == workflow_value:
            data["enabled"] = False
            data["value"] = None
        else:
            data["enabled"] = True
            data["value"] = value
            if value not in self._argset_choice_values(param):
                data["custom"] = value
        self.set("default_args", saved)
        await self._argset_choice_menu(call, param)

    async def _argset_choice_as_workflow(self, call: InlineCall, param: str):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)

        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        data = self._ensure_choice_argset_entry(saved, param)
        data["enabled"] = False
        data["value"] = None
        self.set("default_args", saved)
        await self._argset_choice_menu(call, param)

    async def _argset_choice_custom_input(self, call: InlineCall, query: str, param: str):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)

        value = self._normalize_argset_choice_value(query)
        if not value:
            try:
                await call.answer(self.strings("toast_invalid_value").format(query), show_alert=True)
            except Exception:
                pass
            return
        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        data = self._ensure_choice_argset_entry(saved, param)
        data["enabled"] = True
        data["value"] = value
        data["custom"] = value
        self.set("default_args", saved)
        try:
            await call.answer(self.strings("argset_choice_saved").format(value))
        except Exception:
            pass
        await self._argset_choice_menu(call, param)

    async def _argset_choice_clear(self, call: InlineCall, param: str):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)

        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        data = self._ensure_choice_argset_entry(saved, param)
        custom_value = self._normalize_argset_choice_value(data.get("custom"))
        data["custom"] = None
        if custom_value and data.get("value") == custom_value:
            data["enabled"] = False
            data["value"] = None
        if data.get("value") and data["value"] not in self._argset_choice_values(param):
            data["enabled"] = False
            data["value"] = None
        self.set("default_args", saved)
        await self._argset_choice_menu(call, param)

    def _format_provider_name(self, provider):
        names = {
            "gemini": "Gemini",
            "groq": "Groq",
            "openrouter": "OpenRouter",
            "grok": "Grok",
            "deepseek": "DeepSeek",
        }
        return names.get(provider, provider)

    def _enhance_prompt_source_label(self, provider):
        urls = self._get_enhance_prompt_urls()
        key = "enhance_prompt_source_custom" if provider in urls else "enhance_prompt_source_default"
        return self.strings(key)

    async def _ult_open_enhance_prompts(self, call: InlineCall):
        await self._ult_render_enhance_prompts(call)

    async def _ult_render_enhance_prompts(self, target):
        lines = [self.strings("enhance_prompts_title"), ""]
        buttons = []
        for provider in self._provider_ids():
            lines.append(
                f"{self._format_provider_name(provider)}: {self._enhance_prompt_source_label(provider)}"
            )
            buttons.append(
                {
                    "text": self._format_provider_name(provider),
                    "callback": self._ult_enhance_prompt_provider,
                    "args": (provider,),
                    "style": "primary",
                }
            )
        markup = self._build_button_rows(buttons, columns=2)
        markup.append(self._argset_footer_row(self._ult_open_ai_enhance))
        await self._render_inline(target, "\n".join(lines), markup)

    async def _ult_enhance_prompt_provider(self, call: InlineCall, provider: str):
        provider = str(provider or "").strip().lower()
        if provider not in self._provider_ids():
            return await self._ult_render_enhance_prompts(call)
        url = self._get_enhance_prompt_url(provider)
        lines = [
            f"{self.strings('enhance_prompts_title')}: {self._format_provider_name(provider)}",
            "",
            self.strings("enhance_prompt_source").format(self._enhance_prompt_source_label(provider)),
            self.strings("enhance_prompt_current_url").format(utils.escape_html(self._preview_negative(url, 280))),
        ]
        markup = [
            [
                {
                    "text": self.strings("enhance_prompt_btn_set"),
                    "input": self.strings("enhance_prompt_input_url").format(self._format_provider_name(provider)),
                    "handler": self._ult_enhance_prompt_url_input,
                    "args": (provider,),
                }
            ],
            [
                {
                    "text": self.strings("enhance_prompt_btn_download"),
                    "callback": self._ult_enhance_prompt_download,
                    "args": (provider,),
                    "style": "primary",
                }
            ],
            [
                {
                    "text": self.strings("enhance_prompt_btn_reset"),
                    "callback": self._ult_enhance_prompt_reset,
                    "args": (provider,),
                    "style": "danger",
                }
            ],
            self._argset_footer_row(self._ult_open_enhance_prompts),
        ]
        await self._render_inline(call, "\n".join(lines), markup)

    async def _ult_enhance_prompt_url_input(self, call: InlineCall, query: str, provider: str):
        if not self._set_enhance_prompt_url(provider, query):
            try:
                await call.answer(self.strings("enhance_prompt_invalid_url"), show_alert=True)
            except Exception:
                pass
            return
        try:
            await call.answer(self.strings("enhance_prompt_saved"))
        except Exception:
            pass
        await self._ult_enhance_prompt_provider(call, provider)

    async def _ult_enhance_prompt_reset(self, call: InlineCall, provider: str):
        self._reset_enhance_prompt_url(provider)
        try:
            await call.answer(self.strings("enhance_prompt_reset"))
        except Exception:
            pass
        await self._ult_enhance_prompt_provider(call, provider)

    def _inline_call_message(self, call: InlineCall):
        form = getattr(call, "form", {}) or {}
        if isinstance(form, dict):
            for key in ("caller", "message"):
                value = form.get(key)
                if isinstance(value, Message):
                    return value
        value = getattr(call, "message", None)
        return value if isinstance(value, Message) else None

    async def _send_inline_call_file(self, call: InlineCall, file_obj, caption=""):
        message = self._inline_call_message(call)
        if not message:
            return False
        chat_id = utils.get_chat_id(message)
        try:
            await self.client.send_file(
                chat_id,
                file_obj,
                caption=caption,
                reply_to=getattr(message, "id", None),
            )
        except Exception:
            file_obj.seek(0)
            await self.client.send_file(chat_id, file_obj, caption=caption)
        return True

    async def _ult_enhance_prompt_download(self, call: InlineCall, provider: str):
        provider = str(provider or "").strip().lower()
        if provider not in self._provider_ids():
            return await self._ult_render_enhance_prompts(call)
        text = await self._fetch_enhance_prompt(provider, force=True)
        if not text:
            try:
                await call.answer(self.strings("enhance_prompt_download_failed"), show_alert=True)
            except Exception:
                pass
            return
        file_obj = io.BytesIO(str(text).encode("utf-8"))
        safe_provider = re.sub(r"[^a-z0-9_\\-]+", "_", provider.lower()).strip("_") or "provider"
        file_obj.name = f"comfy_enhance_prompt_{safe_provider}.txt"
        try:
            sent = await self._send_inline_call_file(
                call,
                file_obj,
                caption=self.strings("enhance_prompt_file_caption").format(self._format_provider_name(provider)),
            )
            if not sent:
                await call.answer(self.strings("enhance_prompt_download_failed"), show_alert=True)
        except Exception as e:
            logger.debug("Failed to send enhance prompt file: %s", e)
            try:
                await call.answer(self.strings("enhance_prompt_download_failed"), show_alert=True)
            except Exception:
                pass
        finally:
            file_obj.close()

    async def _argset_provider_menu(self, call: InlineCall):
        current = self._get_prompt_provider()
        lines = [
            self.strings("provider_title"),
            "",
            self.strings("provider_current").format(self._format_provider_name(current)),
            "",
        ]

        buttons = []
        for provider in self._provider_ids():
            is_current = provider == current
            icon = self.strings("argset_on") if is_current else self.strings("argset_off")
            lines.append(f"{icon} {self._format_provider_name(provider)}")
            btn_icon = "\u2705 " if is_current else "\u2b1c "
            buttons.append(
                {
                    "text": btn_icon + self._format_provider_name(provider),
                    "callback": self._argset_provider_detail,
                    "args": (provider,),
                    "style": "success" if is_current else "primary",
                }
            )

        markup = self._build_button_rows(buttons)
        markup.append(self._argset_footer_row(self._ult_open_ai_enhance))
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_provider_detail(self, call: InlineCall, provider: str):
        settings = self._get_ai_settings()
        current = settings["provider"]
        provider_data = settings.get(provider, {})
        selected = provider == current
        status = self.strings("provider_selected") if selected else self.strings("provider_not_selected")
        api_key_status = (
            self.strings("provider_api_key_set")
            if self._get_provider_api_key(provider)
            else self.strings("provider_api_key_missing")
        )

        lines = [
            f"{self.strings('provider_title')}: {self._format_provider_name(provider)}",
            "",
            self.strings("provider_status").format(status),
            self.strings("provider_api_key").format(api_key_status),
        ]

        if self._provider_has_model_input(provider):
            lines.append(self.strings("provider_model").format(utils.escape_html(self._get_provider_model(provider))))

        markup = [
            [
                {
                    "text": self.strings("provider_btn_select"),
                    "callback": self._argset_provider_select,
                    "args": (provider,),
                    "style": "success",
                }
            ],
            [
                {
                    "text": self.strings("provider_btn_api_key"),
                    "input": self.strings("provider_input_api_key").format(self._format_provider_name(provider)),
                    "handler": self._argset_provider_api_key_input,
                    "args": (provider,),
                }
            ],
        ]

        presets = self._provider_model_presets(provider)
        if presets:
            preset_buttons = []
            for model in presets:
                label = model
                if len(label) > 30:
                    label = label[:27] + "..."
                preset_buttons.append(
                    {
                        "text": label,
                        "callback": self._argset_provider_model_preset,
                        "args": (provider, model),
                        "style": "success" if model == self._get_provider_model(provider) else "primary",
                    }
                )
            markup.extend(self._build_button_rows(preset_buttons, columns=2))
        if self._provider_has_model_input(provider):
            markup.append([
                {
                    "text": self.strings("provider_btn_model"),
                    "input": self.strings("provider_input_model"),
                    "handler": self._argset_provider_model_input,
                    "args": (provider,),
                }
            ])

        markup.append(self._argset_footer_row(self._argset_provider_menu))
        await self._render_inline(call, "\n".join(lines), markup)

    async def _argset_provider_select(self, call: InlineCall, provider: str):
        self._set_prompt_provider(provider)
        try:
            await call.answer(self.strings("provider_saved").format(self._format_provider_name(provider)))
        except Exception:
            pass
        await self._argset_provider_detail(call, provider)

    async def _argset_provider_api_key_input(self, call: InlineCall, query: str, provider: str):
        self._set_provider_api_key(provider, query)
        try:
            await call.answer(self.strings("provider_key_saved"))
        except Exception:
            pass
        await self._argset_provider_detail(call, provider)

    async def _argset_provider_model_input(self, call: InlineCall, query: str, provider: str):
        self._set_provider_model(provider, query)
        try:
            await call.answer(self.strings("provider_model_saved"))
        except Exception:
            pass
        await self._argset_provider_detail(call, provider)

    async def _argset_provider_model_preset(self, call: InlineCall, provider: str, model: str):
        self._set_provider_model(provider, model)
        try:
            await call.answer(self.strings("provider_model_saved"))
        except Exception:
            pass
        await self._argset_provider_detail(call, provider)

    async def _argset_toggle(self, call: InlineCall, param: str, category: str):
        if self._workflow_limited_mode() or param == "ai":
            return await self._argset_render_main(call)

        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        data = self._ensure_lora_argset_entry(saved) if param == "lora" else self._ensure_argset_entry(saved, param)
        data["enabled"] = not self._argset_enabled(data)
        if param == "lora":
            data = self._set_global_lora_data(data)
            saved["lora"] = self._clone_argset_data(data)
        self.set("default_args", saved)

        cat_map = {
            "params": self._argset_cat_params,
            "enhancements": self._argset_cat_enhancements,
        }
        renderer = cat_map.get(category, self._argset_back)
        await renderer(call)

    async def _argset_pin_model(self, call: InlineCall):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)
        self._save_argset_profile_for_current_model()
        try:
            await call.answer(
                self.strings("argset_pin_model_ok").format(
                    self._format_model_name(self.config["model_name"])
                ),
                show_alert=True,
            )
        except Exception:
            pass
        await self._argset_render_main(call)

    async def _argset_input_handler(self, call: InlineCall, query: str, param: str, category: str):
        if self._workflow_limited_mode():
            return await self._argset_render_main(call)

        ok, val = self._validate_argset_value(param, query.strip())
        if not ok:
            try:
                await call.answer(self.strings("toast_invalid_value").format(query), show_alert=True)
            except Exception:
                pass
            return

        saved = self.get("default_args", {})
        if not isinstance(saved, dict):
            saved = {}
        data = self._ensure_argset_entry(saved, param)
        data["value"] = val
        self.set("default_args", saved)

        cat_map = {
            "params": self._argset_cat_params,
        }
        renderer = cat_map.get(category, self._argset_back)
        await renderer(call)

    async def _argset_reset(self, call: InlineCall):
        wf_name = self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))
        values = self._load_defaults_from_workflow(wf_name)
        defaults = {}
        for param in ("width", "height", "steps", "cfg", "denoise"):
            defaults[param] = {"enabled": False, "value": values.get(param, self._ARGSET_FALLBACKS[param])}
        for param in self._ARGSET_CHOICE_PARAMS:
            defaults[param] = {"enabled": False, "value": None, "custom": None}
        defaults["lora"] = self._get_global_lora_data()
        self.set("default_args", defaults)
        profile_key = self._argset_profile_key(wf_name)
        profiles = self.get("model_arg_profiles", {})
        if isinstance(profiles, dict) and profile_key in profiles:
            profiles.pop(profile_key, None)
            self.set("model_arg_profiles", profiles)
        self.set("argset_active_model_key", profile_key)

        try:
            await call.answer(self.strings("toast_defaults_reset"), show_alert=True)
        except Exception:
            pass
        await self._argset_render_main(call)

    async def _argset_back(self, call: InlineCall):
        await self._argset_render_main(call)

    def _parse_gen_args(self, args_raw: str) -> dict:
        self._sync_argset_for_current_model()
        defaults = self.get("default_args", {})
        if not isinstance(defaults, dict):
            defaults = {}

        parsed = {
            "positive": None,
            "negative": None,
            "width": None,
            "height": None,
            "steps": None,
            "cfg": None,
            "seed": None,
            "denoise": None,
            "sampler_name": None,
            "scheduler": None,
            "use_lora_picker": False,
            "enhance_prompt": False,
            "chat_ai": False,
            "disable_auto_ai": False,
            "inspire": False,
        }

        if self._ai_enhance_enabled():
            parsed["enhance_prompt"] = True

        def extract_arg(pattern, default=None, type_cast=str):
            nonlocal args_raw
            match = re.search(pattern, args_raw, re.IGNORECASE)
            if match:
                value = match.group(1)
                args_raw = args_raw[:match.start()] + args_raw[match.end():]
                args_raw = args_raw.strip()
                try:
                    return type_cast(value)
                except ValueError:
                    return default
            return default

        raw_width = extract_arg(r'-w\s+(\d+)', type_cast=int)
        if raw_width is not None:
            parsed["width"] = max(64, min(4096, raw_width))
        else:
            data = defaults.get("width", {})
            if self._argset_enabled(data):
                parsed["width"] = self._argset_value(data, "width")

        raw_height = extract_arg(r'-h\s+(\d+)', type_cast=int)
        if raw_height is not None:
            parsed["height"] = max(64, min(4096, raw_height))
        else:
            data = defaults.get("height", {})
            if self._argset_enabled(data):
                parsed["height"] = self._argset_value(data, "height")

        raw_steps = extract_arg(r'-steps\s+(\d+)', type_cast=int)
        if raw_steps is not None:
            parsed["steps"] = max(1, min(100, raw_steps))
        else:
            data = defaults.get("steps", {})
            if self._argset_enabled(data):
                parsed["steps"] = self._argset_value(data, "steps")

        raw_cfg = extract_arg(r'-cfg\s+([0-9\.]+)', type_cast=float)
        if raw_cfg is not None:
            parsed["cfg"] = max(1.0, min(30.0, raw_cfg))
        else:
            data = defaults.get("cfg", {})
            if self._argset_enabled(data):
                parsed["cfg"] = self._argset_value(data, "cfg")

        parsed["seed"] = extract_arg(r'-seed\s+(\d+)', type_cast=int)

        raw_denoise = extract_arg(r'-denoise\s+([0-9\.]+)', type_cast=float)
        if raw_denoise is not None:
            parsed["denoise"] = max(0.0, min(1.0, raw_denoise))
        else:
            data = defaults.get("denoise", {})
            if self._argset_enabled(data):
                parsed["denoise"] = self._argset_value(data, "denoise")

        for param in self._ARGSET_CHOICE_PARAMS:
            data = defaults.get(param, {})
            if self._argset_enabled(data):
                parsed[param] = self._argset_choice_value(data)

        if re.search(r'-lora\b', args_raw, re.IGNORECASE):
            parsed["use_lora_picker"] = True
            args_raw = re.sub(r'-lora\b', '', args_raw, flags=re.IGNORECASE).strip()

        if re.search(r'-cai\b', args_raw, re.IGNORECASE):
            parsed["chat_ai"] = True
            parsed["enhance_prompt"] = True
            args_raw = re.sub(r'-cai\b', '', args_raw, flags=re.IGNORECASE).strip()

        if re.search(r'-noai\b', args_raw, re.IGNORECASE):
            parsed["disable_auto_ai"] = True
            args_raw = re.sub(r'-noai\b', '', args_raw, flags=re.IGNORECASE).strip()
            parsed["enhance_prompt"] = False

        if re.search(r'-ai\b', args_raw, re.IGNORECASE):
            parsed["enhance_prompt"] = True
            args_raw = re.sub(r'-ai\b', '', args_raw, flags=re.IGNORECASE).strip()

        if re.search(r'-i\b', args_raw, re.IGNORECASE):
            parsed["inspire"] = True
            parsed["enhance_prompt"] = False
            args_raw = re.sub(r'-i\b', '', args_raw, count=1, flags=re.IGNORECASE).strip()

        neg_match = re.search(
            r'-neg\s+(?:"([^"]*)"|' + r"'([^']*)'|(.+?)(?=\s+-\w|$))",
            args_raw,
            re.IGNORECASE | re.DOTALL,
        )
        if neg_match:
            neg_value = neg_match.group(1) or neg_match.group(2) or neg_match.group(3) or ""
            parsed["negative"] = neg_value.strip()
            args_raw = args_raw[:neg_match.start()] + args_raw[neg_match.end():]
            args_raw = args_raw.strip()

        parsed["positive"] = args_raw.strip()

        return parsed

    async def _render_lora_list(self, call_or_message, state_id):
        state = self._lora_states[state_id]
        try:
            all_loras = await self._get_available_loras()
        except Exception as e:
            logger.debug("Failed to load LoRA list: %s", e)
            state = self._lora_states.pop(state_id, None)
            if state:
                self._cleanup_input_file(state)
            return await self._safe_answer(call_or_message, self.strings("lora_load_failed"))

        if not all_loras:
            state = self._lora_states.pop(state_id, None)
            if state:
                self._cleanup_input_file(state)
            return await self._safe_answer(call_or_message, self.strings("lora_none_available"))

        state["selected"] = self._normalize_lora_preset_entries(state.get("selected"), all_loras)

        page = state["page"]
        per_page = 6
        total_pages = max(1, (len(all_loras) + per_page - 1) // per_page)
        page = min(page, total_pages - 1)
        state["page"] = page
        start = page * per_page
        page_loras = all_loras[start:start + per_page]

        lines = [self.strings("lora_title")]
        lines.append(f"{self.strings('lora_prompt_label')}: {utils.escape_html(str(state.get('positive') or self.strings('prompt_empty'))[:100])}")
        lines.append("")
        for lora in page_loras:
            entry = state["selected"].get(lora, {"enabled": False, "weight": 0.75})
            is_on = bool(entry.get("enabled"))
            weight = entry.get("weight", 0.75)
            icon = '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji>' if is_on else '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji>'
            lines.append(f"{icon} {utils.escape_html(self._format_lora_name(lora, max_length=None))} ({weight:.1f})")

        lines.append(self.strings("lora_page").format(page + 1, total_pages))
        text = "\n".join(lines)

        markup = []
        row = []
        for lora in page_loras:
            short_name = self._format_lora_name(lora, max_length=None)
            if len(short_name) > 20:
                short_name = short_name[:18] + ".."
            icon = "\u2705 " if state["selected"].get(lora, {}).get("enabled") else "\u2b1c "
            row.append({
                "text": f"{icon}{short_name}",
                "callback": self._lora_detail,
                "args": (state_id, lora),
            })
            if len(row) == 2:
                markup.append(row)
                row = []
        if row:
            markup.append(row)

        nav_row = []
        if page > 0:
            nav_row.append({"text": "\u25c0\ufe0f", "callback": self._lora_page, "args": (state_id, -1)})
        if page < total_pages - 1:
            nav_row.append({"text": "\u25b6\ufe0f", "callback": self._lora_page, "args": (state_id, 1)})
        if nav_row:
            markup.append(nav_row)

        markup.append([
            {"text": self.strings("btn_generate"), "callback": self._lora_generate, "args": (state_id,), "style": "success", "emoji_id": "5206607081334906820"},
            {"text": self.strings("btn_cancel"), "callback": self._lora_cancel, "args": (state_id,), "style": "danger", "emoji_id": "5121063440311386962"},
        ])

        await self._render_inline(call_or_message, text, markup)

    async def _lora_page(self, call: InlineCall, state_id: str, direction: int):
        if state_id not in self._lora_states:
            return
        self._lora_states[state_id]["page"] += direction
        await self._render_lora_list(call, state_id)

    async def _lora_detail(self, call: InlineCall, state_id: str, lora_name: str):
        if state_id not in self._lora_states:
            return
        state = self._lora_states[state_id]
        short_name = self._format_lora_name(lora_name, max_length=30)

        entry = state["selected"].get(lora_name, {"enabled": False, "weight": 0.75})
        is_on = bool(entry.get("enabled"))
        weight = entry.get("weight", 0.75)
        status_text = self.strings("lora_on") if is_on else self.strings("lora_off")

        text = self.strings("lora_detail_title").format(
            utils.escape_html(short_name), weight, status_text
        )

        toggle_text = self._state_toggle_text(is_on)
        toggle_style = self._state_toggle_style(is_on)
        toggle_emoji = self._state_toggle_emoji(is_on)

        markup = [
            [
                {"text": "\u2796 0.1", "callback": self._lora_weight, "args": (state_id, lora_name, -0.1)},
                {"text": "\u2795 0.1", "callback": self._lora_weight, "args": (state_id, lora_name, 0.1)},
            ],
            [
                {
                    "text": self.strings("lora_weight_btn"),
                    "input": self.strings("lora_weight_input"),
                    "handler": self._lora_weight_input,
                    "args": (state_id, lora_name),
                }
            ],
            [{"text": toggle_text, "callback": self._lora_toggle, "args": (state_id, lora_name), "style": toggle_style, "emoji_id": toggle_emoji}],
            [{"text": self.strings("btn_back"), "callback": self._lora_back, "args": (state_id,)}],
        ]

        await self._render_inline(call, text, markup)

    async def _lora_weight(self, call: InlineCall, state_id: str, lora_name: str, delta: float):
        if state_id not in self._lora_states:
            return
        state = self._lora_states[state_id]
        entry = state["selected"].get(lora_name, {"enabled": False, "weight": 0.75})
        current = entry.get("weight", 0.75)
        new_weight = round(max(0.1, min(2.0, current + delta)), 1)
        state["selected"][lora_name] = {
            "enabled": bool(entry.get("enabled")),
            "weight": new_weight,
        }
        await self._lora_detail(call, state_id, lora_name)

    async def _lora_weight_input(self, call: InlineCall, query: str, state_id: str, lora_name: str):
        if state_id not in self._lora_states:
            return
        try:
            weight = round(float(query.strip().replace(",", ".")), 1)
        except (TypeError, ValueError):
            try:
                await call.answer(self.strings("toast_invalid_value").format(query), show_alert=True)
            except Exception:
                pass
            return
        if weight < 0.1 or weight > 2.0:
            try:
                await call.answer(self.strings("toast_invalid_value").format(query), show_alert=True)
            except Exception:
                pass
            return
        state = self._lora_states[state_id]
        entry = state["selected"].get(lora_name, {"enabled": False, "weight": 0.75})
        state["selected"][lora_name] = {
            "enabled": bool(entry.get("enabled")),
            "weight": weight,
        }
        try:
            await call.answer(self.strings("lora_weight_saved"))
        except Exception:
            pass
        await self._lora_detail(call, state_id, lora_name)

    async def _lora_toggle(self, call: InlineCall, state_id: str, lora_name: str):
        if state_id not in self._lora_states:
            return
        state = self._lora_states[state_id]
        entry = state["selected"].get(lora_name, {"enabled": False, "weight": 0.75})
        state["selected"][lora_name] = {
            "enabled": not bool(entry.get("enabled")),
            "weight": entry.get("weight", 0.75),
        }
        await self._lora_detail(call, state_id, lora_name)

    async def _lora_back(self, call: InlineCall, state_id: str):
        if state_id not in self._lora_states:
            return
        await self._render_lora_list(call, state_id)

    async def _lora_generate(self, call: InlineCall, state_id: str):
        if state_id not in self._lora_states:
            return
        state = self._lora_states.pop(state_id)
        selected_entries = self._normalize_lora_preset_entries(state.pop("selected", {}))
        selected_loras = self._get_enabled_lora_presets(selected_entries)
        state.pop("page", None)
        state["selected_loras"] = dict(selected_loras)
        await self._run_direct_generation(call, state, selected_loras=selected_loras)

    async def _lora_cancel(self, call: InlineCall, state_id: str):
        state = self._lora_states.pop(state_id, None)
        if state:
            self._cleanup_input_file(state)
        try:
            await call.delete()
        except Exception:
            pass

    def _inject_loras(self, workflow: dict, wf_data: dict, selected_loras: dict) -> dict:
        power_lora_node_id = None
        for nid, node in workflow.items():
            if node.get("class_type") == "Power Lora Loader (rgthree)":
                power_lora_node_id = nid
                break

        if power_lora_node_id:
            node_inputs = workflow[power_lora_node_id]["inputs"]

            existing_lora_keys = [k for k in node_inputs if k.startswith("lora_")]
            for k in existing_lora_keys:
                if isinstance(node_inputs[k], dict):
                    node_inputs[k]["on"] = False

            existing_lora_indexes = []
            for key in existing_lora_keys:
                match = re.fullmatch(r"lora_(\d+)", key)
                if match:
                    existing_lora_indexes.append(int(match.group(1)))
            next_lora_index = max(existing_lora_indexes, default=0) + 1

            for lora_name, weight in selected_loras.items():
                found = False
                for k in existing_lora_keys:
                    if isinstance(node_inputs[k], dict) and node_inputs[k].get("lora") == lora_name:
                        node_inputs[k]["on"] = True
                        node_inputs[k]["strength"] = weight
                        found = True
                        break
                if not found:
                    while f"lora_{next_lora_index}" in node_inputs:
                        next_lora_index += 1
                    key = f"lora_{next_lora_index}"
                    node_inputs[key] = {
                        "on": True,
                        "lora": lora_name,
                        "strength": weight,
                    }
                    next_lora_index += 1

            return workflow

        cr_lora_stack_node_id = None
        for nid, node in workflow.items():
            if node.get("class_type") == "CR LoRA Stack":
                cr_lora_stack_node_id = nid
                break

        if not cr_lora_stack_node_id:
            return workflow

        node_inputs = workflow[cr_lora_stack_node_id]["inputs"]
        lora_indexes = []
        for key in node_inputs:
            match = re.fullmatch(r"lora_name_(\d+)", key)
            if match:
                lora_indexes.append(int(match.group(1)))
        lora_indexes = sorted(lora_indexes)

        for index in lora_indexes:
            if f"switch_{index}" in node_inputs:
                node_inputs[f"switch_{index}"] = "Off"

        for index, item in zip(lora_indexes, selected_loras.items()):
            lora_name, weight = item
            node_inputs[f"switch_{index}"] = "On"
            node_inputs[f"lora_name_{index}"] = lora_name
            node_inputs[f"model_weight_{index}"] = weight
            node_inputs[f"clip_weight_{index}"] = weight

        return workflow

    def _extract_trigger_prompt(self, text, trigger):
        raw = (text or "").strip()
        trigger = (trigger or "").strip()
        if not raw or not trigger:
            return None
        raw_lower = raw.lower()
        trigger_lower = trigger.lower()
        if raw_lower == trigger_lower:
            return ""
        if raw_lower.startswith(trigger_lower) and len(raw) > len(trigger) and raw[len(trigger)].isspace():
            return raw[len(trigger):].strip()
        return None

    def _trigger_queue_key(self, chat_id):
        return str(chat_id)

    def _trigger_cooldown_key(self, chat_id, sender_id):
        return f"{chat_id}:{sender_id or 0}"

    async def _send_trigger_reply(self, message, text):
        try:
            return await self.client.send_message(
                utils.get_chat_id(message),
                text,
                reply_to=message.id,
            )
        except Exception as e:
            logger.debug("Failed to send trigger reply: %s", e)

    async def _notify_trigger_queue_full(self, message):
        chat_id = utils.get_chat_id(message)
        cooldown_key = self._trigger_cooldown_key(chat_id, getattr(message, "sender_id", None))
        if cooldown_key in self._trigger_queue_cooldowns:
            return
        self._trigger_queue_cooldowns[cooldown_key] = True
        await self._send_trigger_reply(message, self.strings("trigger_queue_full"))

    async def _notify_trigger_too_often(self, message):
        chat_id = utils.get_chat_id(message)
        cooldown_key = self._trigger_cooldown_key(chat_id, getattr(message, "sender_id", None))
        if cooldown_key in self._trigger_rate_limit_cooldowns:
            return
        self._trigger_rate_limit_cooldowns[cooldown_key] = True
        await self._send_trigger_reply(message, self.strings("trigger_too_often"))

    async def _notify_trigger_unavailable(self, message, text):
        chat_id = utils.get_chat_id(message)
        await self._notify_trigger_unavailable_by_origin(
            chat_id,
            getattr(message, "sender_id", None),
            message.id,
            text,
        )

    async def _notify_trigger_unavailable_by_origin(self, chat_id, sender_id, reply_to, text):
        if chat_id is None:
            return
        cooldown_key = self._trigger_cooldown_key(chat_id, sender_id)
        if cooldown_key in self._trigger_unavailable_cooldowns:
            return
        self._trigger_unavailable_cooldowns[cooldown_key] = True
        try:
            await self.client.send_message(chat_id, text, reply_to=reply_to)
        except Exception as e:
            logger.debug("Failed to send trigger unavailable reply: %s", e)

    def _reply_media_is_source_post(self, message, reply):
        if not reply:
            return False
        if getattr(reply, "post", False):
            return True
        reply_id = getattr(reply, "id", None)
        reply_to = getattr(message, "reply_to", None)
        reply_to_top_id = getattr(reply_to, "reply_to_top_id", None)
        if (
            reply_id is not None
            and reply_to_top_id is not None
            and str(reply_id) == str(reply_to_top_id)
            and getattr(reply, "media", None)
        ):
            return True
        reply_to_msg_id = (
            getattr(reply_to, "reply_to_msg_id", None)
            or getattr(message, "reply_to_msg_id", None)
        )
        fwd_from = getattr(reply, "fwd_from", None)
        from_id = getattr(reply, "from_id", None)
        sender = getattr(reply, "sender", None)
        looks_like_channel_post = bool(
            fwd_from
            or isinstance(from_id, PeerChannel)
            or type(from_id).__name__ == "PeerChannel"
            or getattr(sender, "broadcast", False)
        )
        if (
            reply_id is not None
            and reply_to_msg_id is not None
            and str(reply_id) == str(reply_to_msg_id)
            and looks_like_channel_post
            and getattr(reply, "media", None)
        ):
            return True
        try:
            message_chat_id = utils.get_chat_id(message)
            reply_chat_id = utils.get_chat_id(reply)
        except Exception:
            return False
        return bool(
            message_chat_id is not None
            and reply_chat_id is not None
            and int(message_chat_id) != int(reply_chat_id)
            and getattr(reply, "media", None)
        )

    def _reply_media_kind_for_message(self, message, reply, context="generation"):
        if self._reply_media_is_source_post(message, reply):
            logger.debug(
                "Ignoring %s reply media from source post: message_id=%s reply_id=%s",
                context,
                getattr(message, "id", None),
                getattr(reply, "id", None),
            )
            return None
        return self._reply_media_kind(reply)

    def _trigger_reply_media_is_source_post(self, message, reply):
        return self._reply_media_is_source_post(message, reply)

    def _trigger_reply_media_kind(self, message, reply):
        return self._reply_media_kind_for_message(message, reply, context="trigger")

    async def _make_trigger_inline_anchor(self, message):
        try:
            return await self.client.send_message(
                utils.get_chat_id(message),
                self.strings("connecting"),
                reply_to=message.id,
            )
        except Exception as e:
            logger.debug("Failed to create trigger inline anchor: %s", e)
            return message

    def _is_trigger_cooldown_error(self, error):
        error_type, _ = self._classify_error(error)
        return error_type in ("server_unavailable", "unavailable", "connection", "timeout")

    def _contains_cyrillic(self, text):
        return bool(re.search(r"[\u0400-\u04FF]", str(text or "")))

    def _apply_trigger_steps_limit(self, parsed_steps, max_steps, wf_name):
        max_steps = self._coerce_int(max_steps, 40, 1, 100)
        if parsed_steps is not None:
            return min(parsed_steps, max_steps)
        workflow_steps = self._load_defaults_from_workflow(wf_name).get("steps")
        try:
            workflow_steps = int(workflow_steps)
        except (TypeError, ValueError):
            return parsed_steps
        if workflow_steps > max_steps:
            return max_steps
        return parsed_steps

    async def _handle_trigger_generation_error(self, state, error, status_form):
        origin = state.get("trigger_origin") if isinstance(state, dict) else None
        if not origin or not self._is_trigger_cooldown_error(error):
            return False
        error_type, details = self._classify_error(error)
        text = self._get_error_message(error_type, details, is_inline=False)
        await self._notify_trigger_unavailable_by_origin(
            origin.get("chat_id"),
            origin.get("sender_id"),
            origin.get("message_id"),
            text,
        )
        try:
            await status_form.delete()
        except Exception:
            pass
        return True

    async def _run_trigger_generation(self, message, raw_args, settings):
        if not raw_args:
            await self._send_trigger_reply(message, self.strings("no_prompt"))
            return

        limited_mode = self._workflow_limited_mode()
        repeat_requested = bool(raw_args and re.search(r'-r\b|-repeat\b', raw_args, re.IGNORECASE))
        repeat_selected_loras = {}
        if repeat_requested:
            last = self.get("last_generation")
            if not last:
                await self._send_trigger_reply(message, self.strings("repeat_no_last"))
                return
            # Model, workflow, and seed are intentionally not reused during repeat generation.
            if not limited_mode:
                repeat_selected_loras = self._normalize_selected_loras(last.get("selected_loras"))
            parts = [last.get("positive", "")]
            if last.get("negative") is not None:
                parts.append(f'-neg "{last["negative"]}"')
            if not limited_mode:
                if last.get("width"):
                    parts.append(f'-w {last["width"]}')
                if last.get("height"):
                    parts.append(f'-h {last["height"]}')
                if last.get("steps"):
                    parts.append(f'-steps {last["steps"]}')
                if last.get("cfg"):
                    parts.append(f'-cfg {last["cfg"]}')
                if last.get("denoise") is not None:
                    parts.append(f'-denoise {last["denoise"]}')
            raw_args = " ".join(parts)

        base = self._base_url()
        if not base:
            await self._notify_trigger_unavailable(message, self.strings("no_url"))
            return

        health_status = None

        async def _update_trigger_connection_retry(next_attempt, total_attempts):
            nonlocal health_status
            text = self.strings("connecting_retry").format(next_attempt, total_attempts)
            if health_status:
                await self._safe_answer(health_status, text)
            else:
                health_status = await self._send_trigger_reply(message, text)

        async def _answer_trigger_preflight(text):
            if health_status:
                await self._safe_answer(health_status, text)
                return health_status
            return await self._send_trigger_reply(message, text)

        health = await self._health_check(on_retry=_update_trigger_connection_retry)
        if not health:
            if health_status:
                await self._safe_answer(health_status, self.strings("unavailable"))
            else:
                await self._notify_trigger_unavailable(message, self.strings("unavailable"))
            return

        parsed = self._parse_gen_args(raw_args)
        parsed["use_lora_picker"] = False
        if parsed.get("chat_ai"):
            parsed["chat_ai"] = False
            parsed["enhance_prompt"] = False
        if limited_mode:
            parsed = self._apply_limited_generation_mode(parsed)
        positive = parsed["positive"]

        if (
            settings.get("reject_russian_prompt")
            and self._contains_cyrillic(positive)
            and not parsed.get("enhance_prompt")
        ):
            await _answer_trigger_preflight(self.strings("trigger_russian_requires_ai"))
            return

        if parsed.get("inspire"):
            parsed["enhance_prompt"] = False
            status = await _answer_trigger_preflight(self.strings("status_civitai_inspire"))
            try:
                inspired_prompt = await self._fetch_civitai_random_prompt()
            except ValueError as e:
                await self._safe_answer(status or message, str(e))
                return
            except Exception as e:
                logger.exception(e)
                await self._safe_answer(status or message, self.strings("civitai_error"))
                return
            try:
                if status and status is not health_status:
                    await status.delete()
            except Exception:
                pass
            positive = inspired_prompt["positive"]
            if parsed["negative"] is None and inspired_prompt.get("negative"):
                parsed["negative"] = inspired_prompt["negative"]

        if not positive:
            await _answer_trigger_preflight(self.strings("no_prompt"))
            return
        if positive.strip().lower() == "ничего":
            await _answer_trigger_preflight(self.strings("easter_nothing"))
            return

        width = parsed["width"]
        height = parsed["height"]
        seed = parsed["seed"]
        denoise = parsed["denoise"]
        parsed_steps = parsed["steps"]
        parsed_cfg = parsed["cfg"]

        reply = await message.get_reply_message()
        reply_kind = self._trigger_reply_media_kind(message, reply)
        has_photo = reply_kind == "image"
        has_video = reply_kind == "video"
        input_filename = None
        input_image_path = None
        input_image_name = None
        input_video_path = None
        input_video_name = None

        wf_name = self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))
        wf_data = await self._ensure_workflow_data(wf_name)
        if not wf_data:
            available = ", ".join(self._get_all_workflow_names())
            await _answer_trigger_preflight(
                self.strings("wf_not_found").format(
                    utils.escape_html(wf_name),
                    utils.escape_html(available),
                ),
            )
            return
        negative = (
            parsed["negative"]
            if parsed["negative"] is not None
            else self._resolve_negative_prompt(wf_name, wf_data)[0]
        )
        required_input_kind = self._workflow_required_input_kind(wf_data)
        if required_input_kind == "image" and not has_photo:
            await _answer_trigger_preflight(self.strings("no_reply_photo"))
            return
        if required_input_kind == "video" and not has_video:
            await _answer_trigger_preflight(self.strings("ctools_no_reply_video"))
            return
        parsed_steps = self._apply_trigger_steps_limit(
            parsed_steps,
            settings.get("max_steps", 40),
            wf_name,
        )

        model = (
            None
            if limited_mode
            else (self.config["model_name"] or self._get_workflow_primary_model(wf_data))
        )

        if has_photo:
            try:
                input_image_path, input_image_name = await self._download_input_image_to_temp(reply)
            except UserFacingError as e:
                if e.key == "input_too_large":
                    await _answer_trigger_preflight(
                        self.strings("img_too_large").format(e.kwargs.get("max_mb", self.config["max_input_mb"])),
                    )
                    return
                raise
            except Exception as e:
                logger.error("Failed to prepare image for ComfyUI: %s: %s", type(e).__name__, e)
                logger.exception(e)
                await _answer_trigger_preflight(self.strings("err_upload_failed"))
                return
        if has_video:
            try:
                input_video_path, input_video_name = await self._download_input_media_to_temp(
                    reply,
                    prefix="input_video",
                    default_suffix=".mp4",
                )
            except UserFacingError as e:
                if e.key == "input_too_large":
                    await _answer_trigger_preflight(
                        self.strings("img_too_large").format(e.kwargs.get("max_mb", self.config["max_input_mb"])),
                    )
                    return
                raise
            except Exception as e:
                logger.error("Failed to prepare video for ComfyUI: %s: %s", type(e).__name__, e)
                logger.exception(e)
                await _answer_trigger_preflight(self.strings("err_upload_failed"))
                return

        original_positive = positive
        enhance_error = None
        censored_enhance = False

        if parsed.get("enhance_prompt"):
            enhance_status = await _answer_trigger_preflight(self.strings("status_enhancing"))
            enhanced, error = await self._enhance_prompt(
                positive,
                model or "unknown",
                image_path=input_image_path if has_photo else None,
            )
            try:
                if enhance_status and enhance_status is not health_status:
                    await enhance_status.delete()
            except Exception:
                pass
            if error:
                enhance_error = error
            else:
                positive = enhanced

        if enhance_error:
            self._cleanup_input_file({"input_image_path": input_image_path, "input_video_path": input_video_path})
            await _answer_trigger_preflight(self._get_enhance_error_text(enhance_error))
            return

        positive = self._apply_positive_prompt_preset(wf_name, positive)
        easter_egg = self._pick_easter_egg(positive, width, height)

        if has_photo and not input_image_path:
            try:
                input_image_path, input_image_name = await self._download_input_image_to_temp(reply)
            except UserFacingError as e:
                if e.key == "input_too_large":
                    await _answer_trigger_preflight(
                        self.strings("img_too_large").format(e.kwargs.get("max_mb", self.config["max_input_mb"])),
                    )
                    return
                raise
            except Exception as e:
                logger.error("Failed to prepare image for ComfyUI: %s: %s", type(e).__name__, e)
                logger.exception(e)
                await _answer_trigger_preflight(self.strings("err_upload_failed"))
                return

        generation_state = self._build_generation_state(
            positive=positive,
            original_positive=original_positive,
            negative=negative,
            width=width,
            height=height,
            seed=seed,
            denoise=denoise,
            steps=parsed_steps,
            cfg=parsed_cfg,
            wf_name=wf_name,
            model=model,
            input_filename=input_filename,
            input_image_name=input_image_name,
            input_image_path=input_image_path,
            input_video_name=input_video_name,
            input_video_path=input_video_path,
            chat_id=utils.get_chat_id(message),
            reply_to=message.id,
            enhance_prompt=parsed.get("enhance_prompt", False),
            use_lora_picker=False,
            enhanced=parsed.get("enhance_prompt") and not censored_enhance and positive != original_positive,
            easter_egg=easter_egg,
            selected_loras={} if limited_mode else (repeat_selected_loras if repeat_requested else self._get_default_lora_presets()),
            auto_delete_result_delay=settings["auto_delete_delay"] if settings.get("auto_delete") else None,
            trigger_origin={
                "chat_id": utils.get_chat_id(message),
                "sender_id": getattr(message, "sender_id", None),
                "message_id": message.id,
            },
            health_checked=True,
            sampler_name=parsed.get("sampler_name"),
            scheduler=parsed.get("scheduler"),
            limited_mode=limited_mode,
        )

        if health_status:
            try:
                await health_status.delete()
            except Exception:
                pass

        await self._launch_generation_flow(
            await self._make_trigger_inline_anchor(message),
            generation_state,
        )

    @loader.watcher()
    async def watcher(self, message: Message):
        try:
            text = (getattr(message, "raw_text", None) or message.text or "").strip()
            if not text:
                return
            chat_id = utils.get_chat_id(message)
            settings = self._get_trigger_settings_for_chat(chat_id, create=False)
            if not settings["enabled"]:
                return
            sender_id = getattr(message, "sender_id", None)
            try:
                if sender_id and int(sender_id) in settings.get("blacklist", []):
                    return
            except (TypeError, ValueError):
                pass
            trigger_prompt = self._extract_trigger_prompt(text, settings["trigger"])
            if trigger_prompt is None:
                return

            cooldown_key = self._trigger_cooldown_key(chat_id, sender_id)
            queue_key = self._trigger_queue_key(chat_id)
            too_often = False
            queue_full = False
            async with self._trigger_queue_lock:
                if cooldown_key in self._trigger_generation_cooldowns:
                    too_often = True
                else:
                    active = self._trigger_queue_counts.get(queue_key, 0)
                    if active >= settings["max_queue"]:
                        queue_full = True
                    else:
                        self._trigger_generation_cooldowns[cooldown_key] = True
                        self._trigger_queue_counts[queue_key] = active + 1
            if too_often:
                await self._notify_trigger_too_often(message)
                return
            if queue_full:
                await self._notify_trigger_queue_full(message)
                return
            try:
                await self._run_trigger_generation(message, trigger_prompt, settings)
            finally:
                async with self._trigger_queue_lock:
                    remaining = self._trigger_queue_counts.get(queue_key, 1) - 1
                    if remaining > 0:
                        self._trigger_queue_counts[queue_key] = remaining
                    else:
                        self._trigger_queue_counts.pop(queue_key, None)
        except Exception as e:
            logger.exception(e)

    @loader.command(
        ru_doc=" [промпт] - Улучшить промпт без генерации",
        aliases=["eprompt", "aiprompt"],
    )
    async def enhance(self, message: Message):
        """ [prompt] - Enhance prompt without generation"""
        raw_args = utils.get_args_raw(message)
        raw_args = re.sub(r'-cai\b', '', raw_args, flags=re.IGNORECASE).strip()
        if raw_args:
            prompt = raw_args
        else:
            reply = await message.get_reply_message()
            prompt = (getattr(reply, "raw_text", None) or reply.text or "").strip() if reply else ""
        if not prompt:
            return await self._safe_answer(message, self.strings("no_prompt"))

        status = await self._safe_answer(message, self.strings("status_enhancing"))
        enhanced, error = await self._enhance_prompt(prompt, self.config["model_name"] or "unknown")
        if error:
            return await self._safe_answer(status or message, self._get_enhance_error_text(error))

        return await self._start_enhance_chat(
            status or message,
            mode="enhance",
            prompt=enhanced,
            original_prompt=prompt,
            model=self.config["model_name"] or "unknown",
        )

    def _parse_upscale_scale(self, raw_args):
        raw_args = str(raw_args or "").strip().replace(",", ".")
        if not raw_args:
            return 2.0
        raw_args = raw_args.rstrip("xX").strip()
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw_args):
            return None
        try:
            value = float(raw_args)
        except ValueError:
            return None
        if value < 0.1 or value > 8:
            return None
        return value

    @staticmethod
    def _format_scale_value(value):
        return f"{float(value):.2f}".rstrip("0").rstrip(".")

    def _reply_media_kind(self, reply):
        if not reply or not getattr(reply, "media", None):
            return None
        if getattr(reply, "video", None) or getattr(reply, "gif", None):
            return "video"
        if getattr(reply, "photo", None):
            return "image"
        mime = str(getattr(getattr(reply, "file", None), "mime_type", "") or "").lower()
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("image/"):
            return "image"
        file_name = str(getattr(getattr(reply, "file", None), "name", "") or "")
        ext = os.path.splitext(file_name)[1].lower()
        if ext in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
            return "video"
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
            return "image"
        return None

    def _ctool_output_node(self, mapping, output_kind):
        output = mapping.get("output_video") if output_kind == "video" else (mapping.get("output_regular") or mapping.get("output_upscaled"))
        return output.get("node_id") if isinstance(output, dict) else None

    def _set_ctool_input(self, workflow, mapping, input_filename, input_kind):
        if input_kind == "video":
            input_map = mapping.get("input_video")
            if input_map and input_map.get("node_id") in workflow:
                workflow[input_map["node_id"]]["inputs"][input_map["field"]] = input_filename
                return
            raise UserFacingError("ctools_workflow_no_input", kind=input_kind)

        input_maps = list(mapping.get("input_images") or [])
        input_image = mapping.get("input_image")
        if input_image and input_image not in input_maps:
            input_maps.insert(0, input_image)
        for input_map in input_maps:
            if input_map and input_map.get("node_id") in workflow:
                workflow[input_map["node_id"]]["inputs"][input_map["field"]] = input_filename
                return
        raise UserFacingError("ctools_workflow_no_input", kind=input_kind)

    def _set_ctool_scale(self, workflow, mapping, scale):
        if scale is None:
            return
        scale_map = mapping.get("scale_by")
        if scale_map and scale_map.get("node_id") in workflow:
            workflow[scale_map["node_id"]]["inputs"][scale_map["field"]] = float(scale)
            return
        for node in workflow.values():
            if isinstance(node, dict) and "scale_by" in node.get("inputs", {}):
                node["inputs"]["scale_by"] = float(scale)
                return

    async def _prepare_ctool_workflow(self, tool_id, input_filename, scale=None):
        tool = self._ctool_definitions()[tool_id]
        workflow = await self._fetch_ctool_workflow(tool_id)
        workflow = self._normalize_workflow_format(json.loads(json.dumps(workflow)))
        mapping = self._parse_workflow(workflow)
        self._set_ctool_input(workflow, mapping, input_filename, tool["input_kind"])
        if tool_id == _CTOOL_UPSCALE:
            self._set_ctool_scale(workflow, mapping, scale)
        workflow = await self._materialize_global_inputs(workflow)
        output_node = self._ctool_output_node(mapping, tool["output_kind"])
        if not output_node:
            raise UserFacingError("ctools_workflow_no_output")
        return workflow, output_node, tool["output_kind"]

    async def _ctool_set_status(self, target, text):
        if isinstance(target, InlineCall):
            await self._render_inline(target, self._to_inline_emoji(text))
            return target
        return await self._safe_answer(target, text)

    async def _run_ctool(self, target, reply, tool_id, scale=None, chat_id=None, reply_to=None):
        base = self._base_url()
        if not base:
            return await self._ctool_set_status(target, self.strings("no_url"))
        tool = self._ctool_definitions().get(tool_id)
        if not tool:
            return await self._ctool_set_status(target, self.strings("ctools_bad_mode"))
        if self._reply_media_kind(reply) != tool["input_kind"]:
            key = "ctools_no_reply_video" if tool["input_kind"] == "video" else "ctools_no_reply_image"
            return await self._ctool_set_status(target, self.strings(key))

        chat_id = chat_id or utils.get_chat_id(target)
        reply_to = reply_to or getattr(target, "reply_to_msg_id", None)
        label = tool["label"]
        if tool_id == _CTOOL_UPSCALE and scale is not None:
            label = f"{label} x{self._format_scale_value(scale)}"
        status = await self._ctool_set_status(target, self.strings(tool.get("processing_key") or "ctools_processing_upscale"))
        input_path = None
        client_id = str(uuid.uuid4())
        try:
            default_suffix = ".mp4" if tool["input_kind"] == "video" else ".png"
            input_path, input_name = await self._download_input_media_to_temp(reply, prefix=f"ctool_{tool_id}", default_suffix=default_suffix)
            input_filename = await self._upload_input_path_to_comfyui(input_path, input_name, content_type=mimetypes.guess_type(input_name)[0])
            workflow, output_node, output_kind = await self._prepare_ctool_workflow(tool_id, input_filename, scale)

            async def _do_queue():
                return await self._retry(self._queue_prompt, workflow, client_id)

            _, history = await self._wait_ws(client_id, _do_queue, expected_output_node=output_node, timeout=_CUPSCALE_TIMEOUT, workflow=workflow)
            output_keys = ("videos", "video", "animated", "animations", "gifs", "images") if output_kind == "video" else ("images",)
            media_info = self._extract_media_info(history, output_node, output_keys)
            if not media_info:
                logger.warning(
                    "No ctool media found in ComfyUI history for tool=%s node=%s; output_kind=%s; outputs=%s",
                    tool_id,
                    output_node,
                    output_kind,
                    self._history_output_summary(history),
                )
                raise UserFacingError("retrieve_failed", self._plain_text(self.strings("err_retrieve_failed")))
            media_kind = self._media_kind_from_info(media_info, output_kind)
            media_bio = await self._retry(self._retrieve_comfy_media, media_info, media_kind)
            try:
                await self._ctool_set_status(status or target, self.strings("ctools_uploading"))
                caption = self.strings(tool["done_key"]) if tool.get("done_key") else self.strings("ctools_done").format(label)
                await self._send_file_result(chat_id, media_bio, caption, reply_to=reply_to, force_document=True)
            finally:
                media_bio.close()
            try:
                if status:
                    await status.delete()
            except Exception:
                pass
        except Exception as e:
            logger.exception(e)
            target_for_error = status or target
            text = self._get_error_message(*self._classify_error(e), is_inline=isinstance(target_for_error, InlineCall))
            if isinstance(target_for_error, InlineCall):
                await self._render_inline(target_for_error, text)
            else:
                await self._safe_answer(target_for_error, text)
        finally:
            self._cleanup_input_file(input_path)

    def _parse_ctools_args(self, raw_args):
        parts = str(raw_args or "").split()
        if not parts:
            return None, None, False
        tool_id = self._canonical_ctool_id(parts[0])
        if not tool_id:
            return None, None, True
        scale = None
        if tool_id == _CTOOL_UPSCALE:
            scale = self._parse_upscale_scale(" ".join(parts[1:]))
            if scale is None:
                return tool_id, None, True
        return tool_id, scale, False

    async def _render_ctools_menu(self, message, reply):
        state_id = str(uuid.uuid4())
        self._ctools_states[state_id] = {
            "chat_id": utils.get_chat_id(message),
            "reply_id": getattr(reply, "id", None),
            "reply_to": getattr(message, "reply_to_msg_id", None),
        }
        lines = [
            self.strings("ctools_title"),
            "",
            self.strings("ctools_desc_upscale"),
            self.strings("ctools_desc_rmbg"),
            self.strings("ctools_desc_fps"),
        ]
        markup = [
            [{"text": self.strings("ctools_btn_upscale"), "callback": self._ctools_menu_run, "args": (state_id, _CTOOL_UPSCALE)}],
            [{"text": self.strings("ctools_btn_rmbg"), "callback": self._ctools_menu_run, "args": (state_id, _CTOOL_RMBG)}],
            [{"text": self.strings("ctools_btn_fps"), "callback": self._ctools_menu_run, "args": (state_id, _CTOOL_FPS)}],
            [{"text": self.strings("btn_close"), "callback": self._safe_close_form, "style": "danger"}],
        ]
        await self._render_inline(message, self._to_inline_emoji("\n".join(lines)), markup)

    async def _ctools_menu_run(self, call: InlineCall, state_id: str, tool_id: str):
        state = self._ctools_states.pop(state_id, None)
        if not state:
            return await self._render_inline(call, self._to_inline_emoji(self.strings("ctools_state_expired")))
        reply = await self.client.get_messages(state["chat_id"], ids=state["reply_id"])
        scale = 2.0 if tool_id == _CTOOL_UPSCALE else None
        await self._run_ctool(call, reply, tool_id, scale=scale, chat_id=state["chat_id"], reply_to=state.get("reply_to"))

    @loader.command(
        ru_doc=" [-upscale (0.1-8x)|-rmbg|-fps] - апскейл изображения, убрать фон, повысить FPS видео",
    )
    async def ctools(self, message: Message):
        """ [-upscale (0.1-8x)|-rmbg|-fps] - upscale image, remove background, boost video FPS"""
        reply = await message.get_reply_message()
        raw_args = utils.get_args_raw(message).strip()
        if not raw_args:
            if not reply or not getattr(reply, "media", None):
                return await self._safe_answer(message, "\n".join([self.strings("ctools_title"), self.strings("ctools_usage")]))
            return await self._render_ctools_menu(message, reply)
        tool_id, scale, bad = self._parse_ctools_args(raw_args)
        if bad or not tool_id:
            if tool_id == _CTOOL_UPSCALE:
                return await self._safe_answer(message, self.strings("ctools_bad_scale"))
            return await self._safe_answer(message, self.strings("ctools_bad_mode"))
        if not reply or not getattr(reply, "media", None):
            tool = self._ctool_definitions().get(tool_id, {})
            key = "ctools_no_reply_video" if tool.get("input_kind") == "video" else "ctools_no_reply_image"
            return await self._safe_answer(message, self.strings(key))
        await self._run_ctool(message, reply, tool_id, scale=scale, chat_id=utils.get_chat_id(message), reply_to=getattr(message, "reply_to_msg_id", None))

    @loader.command(
        ru_doc=" [Реплай на генерацию из архива] [текст] - Поделиться своей генерацией в @ComfyIdeas. -anon, -top",
    )
    async def cshare(self, message: Message):
        """ [reply to archive generation] [text] - share your generation to @ComfyIdeas. -anon, -top"""
        raw_args = utils.get_args_raw(message)
        if re.search(r"(^|\s)-top(\s|$)", raw_args, re.IGNORECASE):
            return await self._answer_cshare_top(message)

        reply = await message.get_reply_message()
        if not reply:
            return await self._safe_answer(message, self.strings("cshare_no_reply"))

        generation_number = self._extract_cshare_generation_number(
            getattr(reply, "raw_text", None) or reply.text or ""
        )
        if generation_number is None:
            return await self._safe_answer(message, self.strings("cshare_no_archive"))

        prompt_message, prompt_text = await self._find_cshare_prompt_info(reply, generation_number)
        if not prompt_message or not prompt_text:
            return await self._safe_answer(message, self.strings("cshare_no_prompt_info"))

        data = self._parse_archive_prompt_text(prompt_text)
        if data.get("generation") != generation_number:
            return await self._safe_answer(message, self.strings("cshare_no_prompt_info"))

        state, error_text = await self._prepare_cshare_preview_state(
            message,
            reply,
            generation_number,
            prompt_text,
            raw_args,
        )
        if error_text:
            return await self._safe_answer(message, error_text)
        await self._render_cshare_preview(message, state)

    @loader.command(
        ru_doc=" [промпт] - Генерация изображения. -r, -neg, -w, -h, -steps, -cfg, -seed, -denoise, -lora, -ai, -noai, -i",
        aliases=["img"],
    )
    async def comfy(self, message: Message):
        """ [prompt] - Generate image. -r, -neg, -w, -h, -steps, -cfg, -seed, -denoise, -lora, -ai, -noai, -i"""
        raw_args = utils.get_args_raw(message)
        limited_mode = self._workflow_limited_mode()
        repeat_requested = bool(raw_args and re.search(r'-r\b|-repeat\b', raw_args, re.IGNORECASE))
        repeat_selected_loras = {}

        if repeat_requested:
            last = self.get("last_generation")
            if not last:
                return await self._safe_answer(message, self.strings("repeat_no_last"))
            # Model, workflow, and seed are intentionally not reused during repeat generation.
            if not limited_mode:
                repeat_selected_loras = self._normalize_selected_loras(last.get("selected_loras"))
            parts = [last.get("positive", "")]
            if last.get("negative") is not None:
                parts.append(f'-neg "{last["negative"]}"')
            if not limited_mode:
                if last.get("width"):
                    parts.append(f'-w {last["width"]}')
                if last.get("height"):
                    parts.append(f'-h {last["height"]}')
                if last.get("steps"):
                    parts.append(f'-steps {last["steps"]}')
                if last.get("cfg"):
                    parts.append(f'-cfg {last["cfg"]}')
                if last.get("denoise") is not None:
                    parts.append(f'-denoise {last["denoise"]}')
            raw_args = " ".join(parts)

        base = self._base_url()
        if not base:
            return await self._safe_answer(message, self.strings("no_url"))

        preflight_target = None

        async def _ensure_preflight(string_key="preflight_preparing"):
            nonlocal preflight_target
            if preflight_target is None:
                preflight_target = await self._create_generation_preflight(message, string_key)
            else:
                preflight_target = await self._update_generation_preflight(preflight_target, string_key) or preflight_target
            return preflight_target

        async def _finish_preflight(text):
            if preflight_target is not None:
                return await self._update_generation_preflight(preflight_target, text=text)
            return await self._safe_answer(message, text)

        preloaded_reply = None
        preloaded_reply_kind = None
        preloaded_wf_name = None
        preloaded_wf_data = None
        image_only_workflow = False

        if not raw_args:
            preloaded_reply = await message.get_reply_message()
            preloaded_reply_kind = self._reply_media_kind_for_message(
                message,
                preloaded_reply,
                context="generation",
            )
            if not preloaded_reply_kind:
                return await self._safe_answer(message, self.strings("no_prompt"))
            await _ensure_preflight("preflight_workflow")
            preloaded_wf_name = self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))
            preloaded_wf_data = await self._ensure_workflow_data(preloaded_wf_name)
            image_only_workflow = self._is_image_only_workflow_data(preloaded_wf_data)
            if not image_only_workflow:
                return await _finish_preflight(self.strings("no_prompt"))

        parsed = self._parse_gen_args(raw_args)
        default_lora_data = self._get_default_lora_data()
        default_selected_loras = self._get_enabled_lora_presets(default_lora_data.get("selected"))
        picker_lora_entries = default_lora_data.get("selected")
        if self._argset_enabled(default_lora_data):
            parsed["use_lora_picker"] = True
        if repeat_requested:
            picker_lora_entries = repeat_selected_loras
        if limited_mode:
            parsed = self._apply_limited_generation_mode(parsed)
            default_selected_loras = {}
            picker_lora_entries = {}
            repeat_selected_loras = {}
        positive = parsed["positive"]

        if parsed.get("inspire"):
            parsed["enhance_prompt"] = False
            await _ensure_preflight("status_civitai_inspire")
            try:
                inspired_prompt = await self._fetch_civitai_random_prompt()
            except ValueError as e:
                return await _finish_preflight(str(e))
            except Exception as e:
                logger.exception(e)
                return await _finish_preflight(self.strings("civitai_error"))
            positive = inspired_prompt["positive"]
            if parsed["negative"] is None and inspired_prompt.get("negative"):
                parsed["negative"] = inspired_prompt["negative"]

        if not positive and not image_only_workflow:
            return await _finish_preflight(self.strings("no_prompt"))
        if positive and positive.strip().lower() == "ничего":
            return await _finish_preflight(self.strings("easter_nothing"))

        await _ensure_preflight("preflight_preparing")

        width = parsed["width"]
        height = parsed["height"]
        seed = parsed["seed"]
        denoise = parsed["denoise"]

        parsed_steps = parsed["steps"]
        parsed_cfg = parsed["cfg"]

        reply = preloaded_reply or await message.get_reply_message()
        reply_kind = preloaded_reply_kind or self._reply_media_kind_for_message(
            message,
            reply,
            context="generation",
        )
        has_photo = reply_kind == "image"
        has_video = reply_kind == "video"
        input_filename = None
        input_image_path = None
        input_image_name = None
        input_video_path = None
        input_video_name = None

        wf_name = preloaded_wf_name or self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))

        if preloaded_wf_data is None:
            await _ensure_preflight("preflight_workflow")
        wf_data = preloaded_wf_data or await self._ensure_workflow_data(wf_name)
        if not wf_data:
            available = ", ".join(self._get_all_workflow_names())
            return await _finish_preflight(
                self.strings("wf_not_found").format(
                    utils.escape_html(wf_name),
                    utils.escape_html(available),
                ),
            )
        negative = (
            parsed["negative"]
            if parsed["negative"] is not None
            else self._resolve_negative_prompt(wf_name, wf_data)[0]
        )
        image_only_workflow = image_only_workflow or self._is_image_only_workflow_data(wf_data)
        mapping = wf_data.get("mapping") or self._parse_workflow(wf_data.get("workflow", {}))
        required_input_kind = self._workflow_required_input_kind(wf_data)
        if required_input_kind == "image" and not has_photo:
            return await _finish_preflight(self.strings("no_reply_photo"))
        if required_input_kind == "video" and not has_video:
            return await _finish_preflight(self.strings("ctools_no_reply_video"))
        promptless_media_workflow = image_only_workflow and not positive
        if promptless_media_workflow:
            parsed["enhance_prompt"] = False
            parsed["chat_ai"] = False
            parsed["use_lora_picker"] = False

        await _ensure_preflight("preflight_model")
        model = (
            None
            if limited_mode or promptless_media_workflow
            else (self.config["model_name"] or self._get_workflow_primary_model(wf_data))
        )

        if has_photo:
            await _ensure_preflight("preflight_image")
            try:
                input_image_path, input_image_name = await self._download_input_image_to_temp(reply)
            except UserFacingError as e:
                if e.key == "input_too_large":
                    return await _finish_preflight(
                        self.strings("img_too_large").format(e.kwargs.get("max_mb", self.config["max_input_mb"])),
                    )
                raise
            except Exception as e:
                logger.error("Failed to prepare image for ComfyUI: %s: %s", type(e).__name__, e)
                logger.exception(e)
                return await _finish_preflight(self.strings("err_upload_failed"))
        if has_video:
            await _ensure_preflight("preflight_image")
            try:
                input_video_path, input_video_name = await self._download_input_media_to_temp(
                    reply,
                    prefix="input_video",
                    default_suffix=".mp4",
                )
            except UserFacingError as e:
                if e.key == "input_too_large":
                    return await _finish_preflight(
                        self.strings("img_too_large").format(e.kwargs.get("max_mb", self.config["max_input_mb"])),
                    )
                raise
            except Exception as e:
                logger.error("Failed to prepare video for ComfyUI: %s: %s", type(e).__name__, e)
                logger.exception(e)
                return await _finish_preflight(self.strings("err_upload_failed"))

        original_positive = positive
        enhance_error = None
        censored_enhance = False
        if parsed.get("enhance_prompt"):
            await _ensure_preflight("status_enhancing")
            enhanced, error = await self._enhance_prompt(
                positive,
                model or "unknown",
                image_path=input_image_path if has_photo else None,
            )
            if error == "censored" and self._prompt_confirm_enabled():
                censored_enhance = True
                positive = original_positive
            elif error:
                enhance_error = error
            else:
                positive = enhanced

        if enhance_error:
            self._cleanup_input_file({"input_image_path": input_image_path, "input_video_path": input_video_path})
            return await _finish_preflight(
                self._get_enhance_error_text(enhance_error),
            )

        positive = self._apply_positive_prompt_preset(wf_name, positive)
        easter_egg = self._pick_easter_egg(positive, width, height)

        if has_photo and not input_image_path:
            await _ensure_preflight("preflight_image")
            try:
                input_image_path, input_image_name = await self._download_input_image_to_temp(reply)
            except UserFacingError as e:
                if e.key == "input_too_large":
                    return await _finish_preflight(
                        self.strings("img_too_large").format(e.kwargs.get("max_mb", self.config["max_input_mb"])),
                    )
                raise
            except Exception as e:
                logger.error("Failed to prepare image for ComfyUI: %s: %s", type(e).__name__, e)
                logger.exception(e)
                return await _finish_preflight(self.strings("err_upload_failed"))

        generation_state = self._build_generation_state(
            positive=positive,
            original_positive=original_positive,
            negative=negative,
            width=width,
            height=height,
            seed=seed,
            denoise=denoise,
            steps=parsed_steps,
            cfg=parsed_cfg,
            wf_name=wf_name,
            model=model,
            input_filename=input_filename,
            input_image_name=input_image_name,
            input_image_path=input_image_path,
            input_video_name=input_video_name,
            input_video_path=input_video_path,
            chat_id=message.chat_id,
            reply_to=message.reply_to_msg_id or message.id,
            enhance_prompt=parsed.get("enhance_prompt", False),
            use_lora_picker=parsed.get("use_lora_picker"),
            enhanced=parsed.get("enhance_prompt") and not censored_enhance and positive != original_positive,
            easter_egg=easter_egg,
            selected_loras={} if promptless_media_workflow else (repeat_selected_loras or default_selected_loras),
            lora_entries={} if promptless_media_workflow else picker_lora_entries,
            reuse_status_message=isinstance(preflight_target, Message),
            sampler_name=parsed.get("sampler_name"),
            scheduler=parsed.get("scheduler"),
            limited_mode=limited_mode,
        )

        if parsed.get("chat_ai"):
            await self._start_enhance_chat(
                preflight_target or message,
                mode="generate",
                prompt=positive,
                original_prompt=original_positive,
                generation_state=generation_state,
                model=model or "unknown",
                image_path=input_image_path if has_photo else None,
            )
            return

        if parsed.get("enhance_prompt") and self._prompt_confirm_enabled():
            state_id = str(uuid.uuid4())
            self._enhance_confirm_states[state_id] = {
                **generation_state,
                "enhanced_positive": None if censored_enhance else positive,
                "censored": censored_enhance,
            }
            await self._render_enhance_confirm(preflight_target or message, state_id)
            return

        await _ensure_preflight("preflight_launch")
        await self._launch_generation_flow(preflight_target or message, generation_state)

    @loader.command(
        ru_doc=" - Дополнительные настройки/функции. -bl [reply/@user/id] (блэклист для триггеров)",
    )
    async def ultcomfy(self, message: Message):
        """ - Open additional settings/functions. -bl [reply/@user/id] (trigger blacklist)"""
        self._ensure_ult_settings()
        raw_args = utils.get_args_raw(message)
        if re.search(r"(^|\s)-bl(\s|$)", raw_args, re.IGNORECASE):
            query = re.sub(r"(^|\s)-bl(\s|$)", " ", raw_args, flags=re.IGNORECASE).strip()
            return await self._ult_toggle_trigger_blacklist_user(message, query)
        await self._ult_render_main(message)

    @loader.command(
        ru_doc=" - справка ComfyUI",
    )
    async def chelp(self, message: Message):
        """ - ComfyUI help"""
        text = self._to_inline_emoji(self.strings("help_text"))
        rendered = await self._render_inline_with_info_banner(
            message,
            text,
            [[{"text": self.strings("btn_close"), "callback": self._safe_close_form, "style": "danger"}]],
        )
        if not rendered:
            await self._smart_answer(message, self.strings("help_text"))

    @loader.command(ru_doc=" - Статус подключения к ComfyUI")
    async def ci(self, message: Message):
        """ - ComfyUI connection status"""
        status = await self._safe_answer(
            message,
            self._format_ci_loading_text(),
        )
        ping_state = {}
        ping_stop = asyncio.Event()
        ping_task = asyncio.create_task(self._ci_ping_loop(status or message, ping_state, ping_stop))
        try:
            await self._render_comfyinfo(
                status or message,
                userbot_ping_state=ping_state,
                ping_stop_event=ping_stop,
                ping_task=ping_task,
            )
        finally:
            ping_stop.set()
            if not ping_task.done():
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    @loader.command(ru_doc=" - мониторинг задач ComfyUI")
    async def cmon(self, message: Message):
        """ - ComfyUI task monitor"""
        if not self._base_url():
            return await self._safe_answer(message, self.strings("no_url"))
        state_id = self._cmon_state_id(message)
        status = await self._safe_answer(message, self.strings("cmon_starting"))
        await self._close_cmon_entry(state_id)
        snapshot = await self._get_queue_snapshot(timeout=5)
        markup = [[{
            "text": self.strings("btn_close"),
            "callback": self._cmon_close,
            "args": (state_id,),
            "style": "danger",
        }]]
        try:
            form = await self._create_cmon_form(
                status or message,
                self._format_cmon_text(snapshot),
                markup,
            )
        except Exception as e:
            logger.debug("Failed to create cmon inline form: %s", e)
            form = None
        if not form:
            return await self._safe_answer(status or message, self._plain_text(self._format_cmon_text(snapshot)))
        task = asyncio.create_task(self._cmon_loop(state_id, form))
        self._cmon_tasks[state_id] = {"task": task, "form": form}

    @loader.command(
        ru_doc=" [URL] - API проверка текущего туннеля ComfyUI",
    )
    async def ct(self, message: Message):
        """ [URL] - ComfyUI tunnel API probe"""
        raw_url = utils.get_args_raw(message).strip()
        if raw_url:
            try:
                base_url = self._normalize_probe_url(raw_url)
            except ValueError:
                return await self._safe_answer(
                    message,
                    self.strings("ct_bad_url"),
                )
        else:
            base_url = self._base_url()
            if not base_url:
                return await self._safe_answer(message, self.strings("no_url"))

        await self._ct_run_probe(message, base_url)

    async def _render_comfyinfo(self, target, userbot_ping_state=None, ping_stop_event=None, ping_task=None):
        base = self._base_url()
        if not base:
            if isinstance(target, Message):
                return await utils.answer(target, self._apply_emoji_theme(self.strings("no_url")))
            return await self._render_inline(target, self._to_inline_emoji(self.strings("no_url")))

        lines = [self.strings("info_title")]
        model_workflow_lines = [
            self.strings("info_model").format(
                utils.escape_html(
                    self._format_model_name(self.config["model_name"], max_length=None)
                    if self.config["model_name"]
                    else self.strings("not_set")
                ),
            ),
            self.strings("info_wf").format(
                utils.escape_html(self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))),
            ),
        ]
        details = []

        health = await self._health_check()
        if health and isinstance(health, dict):
            lines.append(self.strings("info_ok"))
            system = health.get("system", {})
            if isinstance(system, dict):
                version = self._first_present(system, (
                    "comfyui_version",
                    "comfyui",
                    "version",
                    "git_version",
                ))
                python_version = self._first_present(system, ("python_version", "python"))
                pytorch_version = self._first_present(system, ("pytorch_version", "torch_version", "torch"))
                frontend_version = self._first_present(system, (
                    "comfyui_frontend_package_version",
                    "frontend_version",
                    "frontend",
                ))
                if version:
                    details.append(self.strings("info_version").format(utils.escape_html(str(version))))
                if python_version:
                    details.append(self.strings("info_python").format(utils.escape_html(str(python_version))))
                if pytorch_version:
                    details.append(self.strings("info_pytorch").format(utils.escape_html(str(pytorch_version))))
                if frontend_version:
                    details.append(self.strings("info_frontend").format(utils.escape_html(str(frontend_version))))
                ram_total = self._coerce_int(system.get("ram_total"), 0, 0)
                ram_free = self._coerce_int(system.get("ram_free"), 0, 0)
                if ram_total > 0:
                    ram_used = max(0, ram_total - ram_free)
                    details.append(self.strings("info_ram").format(
                        self._format_memory_gb(ram_used),
                        self._format_memory_gb(ram_total),
                    ))
            devices = health.get("devices", [])
            if devices:
                for idx, dev in enumerate(devices, 1):
                    if not isinstance(dev, dict):
                        continue
                    device_name = self._format_comfy_device_name(dev)
                    if len(devices) > 1:
                        device_name = f"{idx}. {device_name}"
                    details.append(self.strings(self._device_info_key(dev, device_name)).format(
                        utils.escape_html(device_name)
                    ))
                    if self._device_is_cpu(dev, device_name):
                        continue
                    vram_total = self._coerce_int(dev.get("vram_total"), 0, 0)
                    vram_free = self._coerce_int(dev.get("vram_free"), 0, 0)
                    if vram_total > 0:
                        vram_used = max(0, vram_total - vram_free)
                        details.append(self.strings("info_vram").format(
                            self._format_memory_gb(vram_used),
                            self._format_memory_gb(vram_total),
                        ))
            else:
                details.append(self.strings("info_device").format(
                    self.strings("info_no_device")
                ))
        else:
            lines.append(self.strings("info_fail"))

        if details:
            lines.append(f"<blockquote expandable>{chr(10).join(reversed(details))}</blockquote>")
        lines.append(f"<blockquote expandable>{chr(10).join(model_workflow_lines)}</blockquote>")
        total_generations = self.strings("info_total_generations").format(
            self._get_total_generation_count()
        )
        bottom_lines = [total_generations]
        if ping_stop_event:
            ping_stop_event.set()
        if ping_task and not ping_task.done():
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass
        userbot_ping_ms = None
        if isinstance(userbot_ping_state, dict):
            userbot_ping_ms = userbot_ping_state.get("value")
        if userbot_ping_ms is None:
            try:
                userbot_ping_ms = await self._measure_userbot_ping_ms()
            except Exception as e:
                logger.debug("Failed to measure ci final ping: %s", e)
        ping_quote = self._format_ci_ping_quote(userbot_ping_ms)
        if ping_quote:
            bottom_lines.append(self.strings("info_userbot_ping").format(int(userbot_ping_ms)))
        lines.append(f"<blockquote expandable>{chr(10).join(bottom_lines)}</blockquote>")

        text = self._to_inline_emoji("\n".join(lines))
        markup = [
            [
                {"text": self.strings("free_btn"), "callback": self._free_memory_callback, "style": "danger"},
                {"text": self.strings("force_free_btn"), "callback": self._force_free_memory_callback, "style": "danger"},
            ],
            [{"text": self.strings("refresh_btn"), "callback": self._refresh_comfyinfo_callback, "style": "primary"}],
            [{"text": self.strings("btn_close"), "callback": self._safe_close_form, "style": "danger"}],
        ]

        await self._render_inline_with_info_banner(target, text, markup)

    async def _refresh_comfyinfo_callback(self, call: InlineCall):
        self._comfy_cache.clear()
        await self._render_comfyinfo(call)

    async def _free_memory_callback(self, call: InlineCall):
        if self._active_generations > 0:
            try:
                await call.answer(self._plain_text(self.strings("free_busy")), show_alert=True)
            except Exception:
                pass
            return

        try:
            await self._free_comfy_memory()
            try:
                await call.answer(self._plain_text(self.strings("free_ok")), show_alert=True)
            except Exception:
                pass
        except Exception as e:
            logger.exception(e)
            try:
                await call.answer(self._plain_text(self.strings("free_fail")), show_alert=True)
            except Exception:
                pass
        await self._render_comfyinfo(call)

    async def _force_free_memory_callback(self, call: InlineCall):
        try:
            await self._force_free_comfy_memory()
            try:
                await call.answer(self._plain_text(self.strings("force_free_ok")), show_alert=True)
            except Exception:
                pass
        except Exception as e:
            logger.exception(e)
            try:
                await call.answer(self._plain_text(self.strings("free_fail")), show_alert=True)
            except Exception:
                pass
        await self._render_comfyinfo(call)

    async def _get_available_checkpoints(self):
        models = []
        for values in (await self._get_available_models_by_field()).values():
            models.extend(values)
        return list(dict.fromkeys(models))

    async def _render_model_list(self, call_or_message, state_id):
        state = self._models_page_cache.get(state_id)
        if not state:
            return
        models = state["models"]
        page = state["page"]
        per_page = 6
        total_pages = max(1, (len(models) + per_page - 1) // per_page)
        page = min(page, total_pages - 1)
        state["page"] = page
        start = page * per_page
        page_models = models[start:start + per_page]
        current_model = self.config["model_name"]

        lines = [self.strings("models_title")]
        for m in page_models:
            icon = '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji>' if m == current_model else '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji>'
            lines.append(f"<blockquote>{icon} {utils.escape_html(self._format_model_name(m, max_length=None))}</blockquote>")
        lines.append(self.strings("models_page").format(page + 1, total_pages))
        text = "\n".join(lines)

        buttons = []
        for m in page_models:
            short_name = self._format_model_name(m, max_length=None)
            if len(short_name) > 25:
                short_name = short_name[:23] + ".."
            icon = "\u2705 " if m == current_model else "\u2b1c "
            buttons.append({
                "text": f"{icon}{short_name}",
                "callback": self._model_select,
                "args": (state_id, m),
            })

        markup = self._build_button_rows(buttons)
        nav_row = []
        if page > 0:
            nav_row.append({"text": "\u25c0\ufe0f", "callback": self._model_page, "args": (state_id, -1)})
        if page < total_pages - 1:
            nav_row.append({"text": "\u25b6\ufe0f", "callback": self._model_page, "args": (state_id, 1)})
        if nav_row:
            markup.append(nav_row)

        markup.append([{
            "text": self.strings("models_manual_btn"),
            "input": self.strings("models_manual_input"),
            "handler": self._model_manual_input,
            "args": (state_id,),
        }])
        markup.append([{"text": "\u274c", "callback": self._safe_close_form, "style": "danger", "emoji_id": "5121063440311386962"}])

        await self._render_inline(call_or_message, text, markup)

    async def _model_page(self, call: InlineCall, state_id: str, direction: int):
        state = self._models_page_cache.get(state_id)
        if not state:
            return
        state["page"] += direction
        await self._render_model_list(call, state_id)

    async def _model_select(self, call: InlineCall, state_id: str, model_name: str):
        self.config["model_name"] = model_name
        self._sync_argset_for_current_model()
        try:
            await call.answer(self.strings("toast_model_set").format(self._format_model_name(model_name, max_length=None)))
        except Exception:
            pass
        state = self._models_page_cache.get(state_id)
        if state:
            await self._render_model_list(call, state_id)

    async def _model_manual_input(self, call: InlineCall, query: str, state_id: str):
        model_name = str(query or "").strip()
        if not model_name:
            return
        self.config["model_name"] = model_name
        self._sync_argset_for_current_model()
        try:
            await call.answer(self.strings("toast_model_set").format(self._format_model_name(model_name, max_length=None)))
        except Exception:
            pass
        state = self._models_page_cache.get(state_id)
        if state:
            if model_name not in state["models"]:
                state["models"].append(model_name)
                state["models"] = sorted(dict.fromkeys(state["models"]))
            await self._render_model_list(call, state_id)

    @loader.command(
        ru_doc=" - Выбрать модель ComfyUI",
        aliases=["smodel", "setm"],
    )
    async def setmodel(self, message: Message):
        """ - Select ComfyUI model"""
        args = utils.get_args_raw(message).strip()
        if args:
            self.config["model_name"] = args
            self._sync_argset_for_current_model()
            return await utils.answer(
                message,
                self.strings("models_set").format(utils.escape_html(self._format_model_name(args, max_length=None))),
            )

        base = self._base_url()
        if not base:
            return await utils.answer(message, self._apply_emoji_theme(self.strings("no_url")))

        status = await self._safe_answer(
            message,
            self._format_generation_preflight_inline(self.strings("models_loading")),
        )
        models = await self._get_available_checkpoints()
        if not models:
            return await self._safe_answer(status or message, self.strings("models_empty"))

        state_id = str(uuid.uuid4())
        self._models_page_cache[state_id] = {
            "models": sorted(models),
            "page": 0,
        }
        await self._render_model_list(status or message, state_id)

    async def _render_wf_main(self, call_or_message, state_id):
        current_wf = self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))
        current_icon = (
            '<tg-emoji emoji-id="5271842287326863410">🔵</tg-emoji>'
            if self._workflow_limited_mode()
            else '<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji>'
        )
        text = "\n".join([
            self.strings("wf_title"),
            self.strings("wf_current").format(f"{current_icon} {utils.escape_html(current_wf)}"),
        ])
        markup = [
            [
                {"text": self.strings("wf_builtin_btn"), "callback": self._wf_show_builtin, "args": (state_id,)},
                {"text": self.strings("wf_custom_btn"), "callback": self._wf_show_custom, "args": (state_id,)},
            ],
            [{"text": "\u274c", "callback": self._safe_close_form}],
        ]
        await self._render_inline(call_or_message, text, markup)

    async def _wf_show_builtin(self, call: InlineCall, state_id: str):
        state = self._wf_page_cache.get(state_id)
        if not state:
            return
        state["workflows"] = sorted(self._BUILTIN_WORKFLOWS)
        state["wf_type"] = "builtin"
        state["page"] = 0
        await self._render_wf_list(call, state_id)

    async def _wf_show_custom(self, call: InlineCall, state_id: str):
        state = self._wf_page_cache.get(state_id)
        if not state:
            return
        custom = self.get("workflows", {})
        if not custom:
            try:
                await call.answer(self.strings("toast_no_custom_wf"), show_alert=True)
            except Exception:
                pass
            return
        state["workflows"] = sorted(custom.keys())
        state["wf_type"] = "custom"
        state["page"] = 0
        await self._render_wf_list(call, state_id)

    async def _render_wf_list(self, call_or_message, state_id):
        state = self._wf_page_cache.get(state_id)
        if not state:
            return
        workflows = state["workflows"]
        page = state["page"]
        per_page = 6
        total_pages = max(1, (len(workflows) + per_page - 1) // per_page)
        page = min(page, total_pages - 1)
        state["page"] = page
        start = page * per_page
        page_wfs = workflows[start:start + per_page]
        current_wf = self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))

        title_key = "wf_list_title_builtin" if state["wf_type"] == "builtin" else "wf_list_title_custom"
        limited_mode = self._workflow_limited_mode()
        lines = [
            self.strings(title_key),
            f"<blockquote>{self.strings('wf_limited_hint')}</blockquote>",
        ]
        for w in page_wfs:
            if w == current_wf and limited_mode:
                icon = '<tg-emoji emoji-id="5271842287326863410">🔵</tg-emoji>'
            elif w == current_wf:
                icon = '<tg-emoji emoji-id="5206607081334906820">\u2705</tg-emoji>'
            else:
                icon = '<tg-emoji emoji-id="5985346521103604145">\u2b1c</tg-emoji>'
            lines.append(f"{icon} {utils.escape_html(w)}")
            description = self._workflow_description(w)
            if description:
                lines.append(f"<blockquote>{utils.escape_html(description)}</blockquote>")
        lines.append(self.strings("wf_page").format(page + 1, total_pages))
        text = "\n".join(lines)

        buttons = []
        for w in page_wfs:
            display = w
            if len(display) > 25:
                display = display[:23] + ".."
            is_current = w == current_wf
            if is_current and limited_mode:
                icon = "🔵 "
                style = "primary"
            elif is_current:
                icon = "\u2705 "
                style = "success"
            else:
                icon = "\u2b1c "
                style = None
            button = {
                "text": f"{icon}{display}",
                "callback": self._wf_select,
                "args": (state_id, w),
            }
            if style:
                button["style"] = style
            buttons.append(button)

        markup = self._build_button_rows(buttons)
        nav_row = []
        if page > 0:
            nav_row.append({"text": "\u25c0\ufe0f", "callback": self._wf_page, "args": (state_id, -1)})
        if page < total_pages - 1:
            nav_row.append({"text": "\u25b6\ufe0f", "callback": self._wf_page, "args": (state_id, 1)})
        if nav_row:
            markup.append(nav_row)

        markup.append([
            {"text": self.strings("btn_back"), "callback": self._wf_back_to_main, "args": (state_id,)},
            {"text": "\u274c", "callback": self._safe_close_form},
        ])

        await self._render_inline(call_or_message, text, markup)

    async def _wf_page(self, call: InlineCall, state_id: str, direction: int):
        state = self._wf_page_cache.get(state_id)
        if not state:
            return
        state["page"] += direction
        await self._render_wf_list(call, state_id)

    async def _wf_select(self, call: InlineCall, state_id: str, wf_name: str):
        current_wf = self._canonical_workflow_name(self.get("default_workflow", _DEFAULT_WORKFLOW_NAME))
        if wf_name == current_wf:
            limited_mode = not self._workflow_limited_mode()
            self._set_workflow_limited_mode(limited_mode)
            toast_key = "toast_wf_limited_on" if limited_mode else "toast_wf_limited_off"
        else:
            self.set("default_workflow", wf_name)
            self._set_workflow_limited_mode(False)
            self._update_default_arg_values()
            limited_mode = False
            toast_key = "toast_wf_set"
        try:
            await call.answer(self.strings(toast_key).format(wf_name))
        except Exception:
            pass
        state = self._wf_page_cache.get(state_id)
        if state:
            await self._render_wf_list(call, state_id)

    async def _wf_back_to_main(self, call: InlineCall, state_id: str):
        await self._render_wf_main(call, state_id)

    @loader.command(
        ru_doc=" [имя] (-lm ограниченный режим) - Выбрать воркфлоу по умолчанию",
        aliases=["setworkflow"],
    )
    async def setwf(self, message: Message):
        """ [name] (-lm limited mode) - Select default workflow"""
        args = utils.get_args_raw(message)
        if args:
            limited_mode = bool(re.search(r"(^|\s)-lm(\s|$)", args, re.IGNORECASE))
            raw_name = re.sub(r"(^|\s)-lm(\s|$)", " ", args, flags=re.IGNORECASE).strip()
            if raw_name:
                if raw_name.lower() == "i2i":
                    return await utils.answer(message, self._apply_emoji_theme(self.strings("err_reserved_wf")))
                wf_name = self._canonical_workflow_name(raw_name)
                if wf_name in self._get_all_workflow_names():
                    self.set("default_workflow", wf_name)
                    self._set_workflow_limited_mode(limited_mode)
                    self._update_default_arg_values()
                    return await utils.answer(
                        message,
                        self.strings("wf_limited_set" if limited_mode else "setwf_ok").format(utils.escape_html(wf_name)),
                    )

        state_id = str(uuid.uuid4())
        self._wf_page_cache[state_id] = {
            "workflows": [],
            "wf_type": "builtin",
            "page": 0,
        }
        await self._render_wf_main(message, state_id)

    @loader.command(
        ru_doc=" [имя] - Выгрузить воркфлоу в JSON",
    )
    async def mlwf(self, message: Message):
        """ [name] - Export workflow as JSON"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, self._apply_emoji_theme(self.strings("mlwf_no_name")))

        raw_name = args.strip()

        if raw_name.lower() == "i2i":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("err_reserved_wf")))

        wf_name = self._canonical_workflow_name(raw_name)
        wf_name, file_obj, description = await self._build_workflow_file(wf_name)
        if not file_obj:
            return await utils.answer(
                message,
                self.strings("mlwf_not_found").format(utils.escape_html(wf_name)),
            )

        caption = self.strings("mlwf_success").format(utils.escape_html(wf_name))
        if description:
            caption += f"\n\n<blockquote expandable>{utils.escape_html(description)}</blockquote>"

        try:
            await self.client.send_file(
                utils.get_chat_id(message),
                file_obj,
                caption=caption,
                reply_to=message.id,
            )
        finally:
            file_obj.close()
        try:
            await message.delete()
        except Exception:
            pass

    def _save_custom_workflow(self, name, workflow_json, description):
        workflow = self._normalize_workflow_format(workflow_json)
        mapping = self._parse_workflow(workflow)
        if not mapping.get("positive"):
            logger.warning(self._plain_text(self.strings("no_mapping_pos")))
        custom = self.get("workflows", {})
        custom[name] = {
            "workflow": workflow,
            "mapping": {k: v for k, v in mapping.items() if v},
            "description": description,
        }
        self.set("workflows", custom)
        return mapping

    async def _render_addwf_failed(self, target, name, validation, state_id):
        markup = [
            [{"text": self.strings("add_wf_force_btn"), "callback": self._addwf_force_add, "args": (state_id,), "style": "danger"}],
            [{"text": self.strings("btn_cancel"), "callback": self._safe_close_form, "style": "danger"}],
        ]
        full_text = self._to_inline_emoji(self._format_workflow_validation(name, validation))
        form_text = full_text
        if len(form_text) >= 3900:
            form_text = self._to_inline_emoji(
                self._format_workflow_validation_compact(name, validation)
            )
        if len(form_text) >= 3900:
            form_text = self._to_inline_emoji(
                self._format_workflow_validation_compact(
                    name,
                    validation,
                    max_items=5,
                    max_chars=120,
                )
            )

        rendered = await self._render_inline(target, form_text, markup)
        if rendered:
            return rendered

        await self._smart_answer(target, full_text)
        if form_text == full_text:
            form_text = self._to_inline_emoji(
                self._format_workflow_validation_compact(
                    name,
                    validation,
                    max_items=5,
                    max_chars=120,
                )
            )
        return await self._render_inline(target, form_text, markup)

    async def _addwf_force_add(self, call: InlineCall, state_id: str):
        state = self._addwf_force_states.get(state_id)
        if not state:
            try:
                await call.answer(self._plain_text(self.strings("add_wf_force_expired")), show_alert=True)
            except Exception:
                pass
            return

        name = state["name"]
        custom = self.get("workflows", {})
        if name in custom:
            try:
                await call.answer(self._plain_text(self.strings("add_wf_exists").format(name)), show_alert=True)
            except Exception:
                pass
            return

        self._save_custom_workflow(name, state["workflow"], state.get("description", ""))
        self._addwf_force_states.pop(state_id, None)
        text = "\n\n".join([
            self._format_workflow_validation(name, state["validation"], saved=True),
            self.strings("add_wf_forced_note"),
        ])
        text = self._to_inline_emoji(text)
        try:
            await call.answer(self._plain_text(self.strings("add_wf_ok").format(name)))
        except Exception:
            pass
        await self._edit_inline_status(call, text, reply_markup=None)

    @loader.command(
        ru_doc=" [имя] [описание] [реплай на JSON] - Добавить воркфлоу",
        aliases=["addworkflow"],
    )
    async def addwf(self, message: Message):
        """ [name] [description] [reply to JSON] - Add workflow"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, self._apply_emoji_theme(self.strings("add_wf_no_name")))

        parts = args.strip().split(maxsplit=1)
        name = parts[0].strip().lower()
        description = parts[1].strip() if len(parts) > 1 else ""

        if name == "i2i":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("err_reserved_wf")))

        canonical_name = self._canonical_workflow_name(name)
        if canonical_name in self._BUILTIN_WORKFLOWS:
            return await utils.answer(
                message, self.strings("add_wf_exists").format(utils.escape_html(canonical_name))
            )

        custom = self.get("workflows", {})
        if name in custom:
            return await utils.answer(
                message, self.strings("add_wf_exists").format(utils.escape_html(name))
            )

        workflow_json, load_error = await self._load_workflow_json_from_reply(message)
        if load_error == "no_reply":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("add_wf_no_reply")))
        if load_error == "bad_json":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("add_wf_bad_json")))
        if load_error == "too_large":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("wf_file_too_large")))

        status = await utils.answer(
            message,
            self.strings("checkwf_checking").format(utils.escape_html(name)),
        )

        try:
            if not isinstance(workflow_json, dict) or not workflow_json:
                raise ValueError("Empty or invalid workflow")

            validation = await self._validate_workflow(workflow_json)
            if not validation.get("ok"):
                state_id = str(uuid.uuid4())
                self._addwf_force_states[state_id] = {
                    "name": name,
                    "description": description,
                    "workflow": workflow_json,
                    "validation": validation,
                }
                return await self._render_addwf_failed(status, name, validation, state_id)

            self._save_custom_workflow(name, workflow_json, description)

            await self._smart_answer(
                status,
                self._format_workflow_validation(name, validation, saved=True),
            )

        except Exception as e:
            logger.error("Failed to add workflow: %s: %s", type(e).__name__, e)
            logger.exception(e)
            await utils.answer(status, self._apply_emoji_theme(self.strings("err_workflow_invalid")))

    @loader.command(
        ru_doc=" - Проверить JSON воркфлоу без сохранения",
    )
    async def checkwf(self, message: Message):
        """ - Check workflow JSON without saving"""
        workflow_name = await self._get_workflow_reply_name(message)
        workflow_json, load_error = await self._load_workflow_json_from_reply(message)
        if load_error == "no_reply":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("checkwf_no_reply")))
        if load_error == "bad_json":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("checkwf_bad_json")))
        if load_error == "too_large":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("wf_file_too_large")))

        status = await utils.answer(
            message,
            self.strings("checkwf_checking").format(utils.escape_html(workflow_name)),
        )

        try:
            validation = await self._validate_workflow(workflow_json)
            await self._smart_answer(
                status,
                self._format_workflow_validation(workflow_name, validation),
            )
        except Exception as e:
            logger.exception(e)
            await utils.answer(status, self._apply_emoji_theme(self.strings("err_workflow_invalid")))

    @loader.command(
        ru_doc=" [имя|-all] - Удалить пользовательский воркфлоу",
        aliases=["delworkflow"],
    )
    async def delwf(self, message: Message):
        """ [name|-all] - Delete custom workflow"""
        args = utils.get_args_raw(message)
        if not args:
            custom = self.get("workflows", {})
            if not custom:
                return await utils.answer(message, self._apply_emoji_theme(self.strings("del_wf_no_custom")))
            names = sorted(custom.keys())
            wf_list = "\n".join(f"<code>{utils.escape_html(name)}</code>" for name in names)
            return await self._smart_answer(
                message,
                self.strings("del_wf_no_name_with_list").format(
                    wf_list,
                    utils.escape_html(names[0]),
                ),
            )

        name = args.strip().lower()
        custom = self.get("workflows", {})
        if not isinstance(custom, dict):
            custom = {}

        if name == "-all":
            if not custom:
                return await utils.answer(message, self._apply_emoji_theme(self.strings("del_wf_no_custom")))
            count = len(custom)
            self.set("workflows", {})
            return await utils.answer(message, self._apply_emoji_theme(self.strings("del_wf_all_ok").format(count)))

        if name == "i2i":
            return await utils.answer(message, self._apply_emoji_theme(self.strings("err_reserved_wf")))

        canonical_name = self._canonical_workflow_name(name)
        if canonical_name in self._BUILTIN_WORKFLOWS:
            return await utils.answer(
                message, self.strings("del_wf_builtin").format(utils.escape_html(canonical_name))
            )

        if name not in custom:
            return await utils.answer(
                message, self.strings("del_wf_fail").format(utils.escape_html(name))
            )

        del custom[name]
        self.set("workflows", custom)
        await utils.answer(message, self._apply_emoji_theme(self.strings("del_wf_ok").format(utils.escape_html(name))))

    @loader.command(
        ru_doc=" - Настроить дефолтные аргументы генерации",
        aliases=["csetarg"],
    )
    async def setarg(self, message: Message):
        """ - Configure default generation arguments"""
        self._sync_argset_for_current_model()
        await self._argset_render_main(message)
