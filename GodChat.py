__version__ = (1, 0, 0)
# meta developer: @mofkomodules
# Name: GodChat
# meta banner: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/godchat_banner.png?v=20261012
# meta pic: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/assets/godchat_banner.png?v=20261012
# meta fhsdesc: quotes, moderation, mofko, mutes, admin, prefix, random, purge, banmedia
# meta tags: quotes, moderation, mofko, mutes, admin, prefix, random, purge, banmedia
# meta link: https://raw.githubusercontent.com/mofko/MofkoModules/refs/heads/main/GodChat.py
# scope: heroku_min 2.1.0
# scope:inline
# requires: pygments regex rlottie-python==1.3.8 opencv-python-headless imageio-ffmpeg

import asyncio
import base64
import copy
import gzip
import hashlib
import html as quote_html
import io
import json
import logging
import math
import os
import random
import re
import secrets
import time
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from herokutl import utils as tl_utils
from herokutl.errors.rpcerrorlist import (
    FloodWaitError,
    HideRequesterMissingError,
)
from herokutl.tl import functions, types
from herokutl.tl.types import ChannelParticipantsAdmins, Message

from .. import loader, utils

logger = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"^(\d+)([a-zа-яё]*)$", re.IGNORECASE)
_DURATION_ALIASES = {
    "": ("minutes", 60),
    "s": ("seconds", 1),
    "с": ("seconds", 1),
    "sec": ("seconds", 1),
    "secs": ("seconds", 1),
    "second": ("seconds", 1),
    "seconds": ("seconds", 1),
    "сек": ("seconds", 1),
    "секунда": ("seconds", 1),
    "секунды": ("seconds", 1),
    "секунд": ("seconds", 1),
    "m": ("minutes", 60),
    "м": ("minutes", 60),
    "min": ("minutes", 60),
    "mins": ("minutes", 60),
    "minute": ("minutes", 60),
    "minutes": ("minutes", 60),
    "мин": ("minutes", 60),
    "минута": ("minutes", 60),
    "минуты": ("minutes", 60),
    "минут": ("minutes", 60),
    "h": ("hours", 60 * 60),
    "ч": ("hours", 60 * 60),
    "hour": ("hours", 60 * 60),
    "hours": ("hours", 60 * 60),
    "час": ("hours", 60 * 60),
    "часа": ("hours", 60 * 60),
    "часов": ("hours", 60 * 60),
    "d": ("days", 24 * 60 * 60),
    "д": ("days", 24 * 60 * 60),
    "day": ("days", 24 * 60 * 60),
    "days": ("days", 24 * 60 * 60),
    "день": ("days", 24 * 60 * 60),
    "дня": ("days", 24 * 60 * 60),
    "дней": ("days", 24 * 60 * 60),
    "y": ("years", 365 * 24 * 60 * 60),
    "г": ("years", 365 * 24 * 60 * 60),
    "л": ("years", 365 * 24 * 60 * 60),
    "year": ("years", 365 * 24 * 60 * 60),
    "years": ("years", 365 * 24 * 60 * 60),
    "год": ("years", 365 * 24 * 60 * 60),
    "года": ("years", 365 * 24 * 60 * 60),
    "лет": ("years", 365 * 24 * 60 * 60),
}
_TELEGRAM_MIN_MUTE = 30
_TELEGRAM_MAX_MUTE = 366 * 24 * 60 * 60
_ACTIVITY_PERIODS = {
    1: timedelta(days=30),
    3: timedelta(days=90),
}
_ACTIVITY_CACHE_TTL = 20 * 60
_MEMBER_CACHE_TTL = 10 * 60
_SESSION_TTL = 24 * 60 * 60
_MAX_ACTIVITY_CACHE = 256
_MAX_MEMBER_CACHE = 16
_MAX_SESSIONS = 128
_MEDIA_SIFT_CANDIDATE_LIMIT = 16
_MEDIA_FAMILY_SEED_LIMIT = 8
_MEDIA_DONOR_TITLE = "GodChat Media Archive"
_MEDIA_RECORD_PREFIX = "GCM1:"
_MEDIA_DELETE_PREFIX = "GCMD1:"
_MAX_HISTORY = 200
_PARTICIPANT_PAGE = 200
_PARTICIPANT_ATTEMPTS = 8
_PANIC_SLOW_MODE = 60 * 60
_PANIC_DEFAULTS = {
    "auto": False, "joins": 10, "window": 5,
    "close": True, "slow": True, "requests": True,
}
_BULK_KICK_TTL = 5 * 60
_MAX_BULK_KICK_JOBS = 16
_JOIN_REQUEST_CONFIRM_TTL = 5 * 60
_BROKEN_STATE_NAMESPACE = "MofkoGodChat"
_PERSISTENT_STATE_KEYS = (
    "chat_controls",
    "panic_settings",
    "join_request_jobs",
    "delete_mutes",
    "guest_bot_blocks",
    "guest_bot_member_blocks",
    "sticker_bans",
    "media_bans",
)
_NORMAL_RESULT_TTL = 6
_IMPORTANT_RESULT_TTL = 12
_BANNED_RIGHT_FIELDS = (
    "view_messages",
    "send_messages",
    "send_media",
    "send_stickers",
    "send_gifs",
    "send_games",
    "send_inline",
    "embed_links",
    "send_polls",
    "change_info",
    "invite_users",
    "pin_messages",
    "manage_topics",
    "send_photos",
    "send_videos",
    "send_roundvideos",
    "send_audios",
    "send_voices",
    "send_docs",
    "send_plain",
    "edit_rank",
    "send_reactions",
    "manage_linked_peers",
)
_EMOJI = {
    "ban": '<tg-emoji emoji-id="5278578973595427038">🚫</tg-emoji>',
    "kick": '<tg-emoji emoji-id="5873225338984599714">📤</tg-emoji>',
    "mute": '<tg-emoji emoji-id="5407001145740631266">🤐</tg-emoji>',
    "success": '<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji>',
    "off": '<tg-emoji emoji-id="5985346521103604145">⬜</tg-emoji>',
    "error": '<tg-emoji emoji-id="5121063440311386962">👎</tg-emoji>',
    "warning": '<tg-emoji emoji-id="4904936030232117798">⚠️</tg-emoji>',
    "time": '<tg-emoji emoji-id="5870921681735781843">⏱</tg-emoji>',
    "reason": '<tg-emoji emoji-id="5879841310902324730">✏️</tg-emoji>',
    "prefix": '<tg-emoji emoji-id="5879841310902324730">✏️</tg-emoji>',
}
_RANDOM_EMOJI = {
    "dice": '<tg-emoji emoji-id="5444931419270839381">🏅</tg-emoji>',
    "user": '<tg-emoji emoji-id="5188678912883827293">🤖</tg-emoji>',
    "activity": '<tg-emoji emoji-id="5877485980901971030">📊</tg-emoji>',
    "message": '<tg-emoji emoji-id="5253590213917158323">💬</tg-emoji>',
    "ban": '<tg-emoji emoji-id="5121063440311386962">👎</tg-emoji>',
    "ok": '<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji>',
}


class _GQuoteError(Exception):
    pass


_GQUOTE_PILLOW_WORKER = r'''
import io, json, math, os, re, shutil, subprocess, sys, traceback, unicodedata, hashlib
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
LIMITS_UNAVAILABLE = False
if sys.platform.startswith('linux') and __name__ == '__main__':
    try:
        import resource
        for limit, budget in ((resource.RLIMIT_AS, 512*1024*1024), (resource.RLIMIT_CPU, 140)):
            soft, hard = resource.getrlimit(limit)
            ceiling = budget if hard == resource.RLIM_INFINITY else min(budget, hard)
            resource.setrlimit(limit, (min(soft,ceiling) if soft != resource.RLIM_INFINITY else ceiling, hard))
    except (ImportError, OSError, ValueError):
        LIMITS_UNAVAILABLE = True
import regex
from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageOps, features

class Node:
    def __init__(self, tag='root', attrs=()):
        self.tag, self.a, self.children = tag, dict(attrs), []
    def has(self, name):
        return name in self.a.get('class', '').split()
    def text(self):
        return ''.join(c if isinstance(c, str) else c.text() for c in self.children)

class Tree(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.count = 0
        self.feed(markup)
    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > 24000 or len(self.stack) > 64:
            raise ValueError('markup_limit')
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('img', 'br', 'hr', 'meta', 'input'):
            self.stack.append(node)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, text):
        self.stack[-1].children.append(text)

class Box:
    def __init__(self, w=0, h=0, ops=None):
        self.w, self.h, self.ops = w, h, ops or []
    def add(self, other, x=0, y=0):
        self.ops.extend((kind, px+x, py+y, value) for kind, px, py, value in other.ops)

class Raster:
    def __init__(self,path,size): self.path,self.size=path,size; self.width,self.height=size
    def resize(self,size,resample=Image.Resampling.LANCZOS):
        with Image.open(self.path) as image: return image.convert('RGBA').resize(size,resample)

class Painter:
    BLOCKS = {'div','p','pre','blockquote','details','ul','ol','li','table','h1','h2','h3','h4','h5','h6','hr'}
    def __init__(self, payload):
        self.p = payload
        self.root = Path(payload['root']).resolve()
        self.options = payload['options']
        self.scale = self.options['scale']
        self.width = self.options['width']
        self.dark = self.options['theme'] == 'dark'
        self.bg = self.options.get('background_color') or ('#181b1e' if self.dark else '#dce5e9')
        self.bubble = '#33383d' if self.dark else '#ffffff'
        self.out = '#33383d' if self.dark else '#e1f5d5'
        self.fg = '#f2f4f5' if self.dark else '#19232b'
        self.muted = '#9b9fa3' if self.dark else '#607180'
        self.code = '#272b2f' if self.dark else '#f0f3f5'
        self.warnings, self.fonts, self.images, self.glyphs = [], {}, {}, {}
        self.image_bytes = 0
        self.message_id, self.document_id = None, None
        self.raqm = features.check_feature('raqm')
        self.progress = Path(payload['progress'])
        self.stage = 'layout'
        if LIMITS_UNAVAILABLE: self.warn('worker_resource_limits_unavailable')
    def warn(self, code, error=None):
        item = dict(code=code, message=self.message_id, document=self.document_id,
                    exception=type(error).__name__ if error else None)
        if item not in self.warnings:
            self.warnings.append(item)
    def checkpoint(self, stage):
        self.stage = stage
        self.progress.write_text(json.dumps(dict(stage=stage, message=self.message_id, document=self.document_id)), encoding='utf8')
    def path(self, uri):
        parsed = urlsplit(uri)
        if parsed.scheme != 'file' or parsed.netloc:
            raise ValueError('nonlocal_asset')
        value = unquote(parsed.path)
        if os.name == 'nt' and re.match(r'^/[A-Za-z]:/', value):
            value = value[1:]
        path = Path(value).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('asset_outside_cache')
        return path
    def font(self, style):
        size = max(8, min(48, style.get('size', 16)))
        family = style.get('family') or ('mono' if style.get('mono') else ('bolditalic' if style.get('bold') and style.get('italic') else 'bold' if style.get('bold') else 'italic' if style.get('italic') else 'regular'))
        key = family, size, self.scale, bool(style.get('bold')) if family in ('cjk','hangul') else False
        if key not in self.fonts:
            path = self.p['fonts'].get(family) or self.p['fonts'].get('regular')
            if not path:
                raise ValueError('text_font_missing')
            self.fonts[key] = ImageFont.truetype(path, round(size*self.scale))
            if family in ('cjk','hangul'):
                try: self.fonts[key].set_variation_by_axes([700 if style.get('bold') else 400])
                except (OSError,ValueError): pass
        return self.fonts[key]
    @staticmethod
    def rtl(text):
        for c in text:
            kind = unicodedata.bidirectional(c)
            if kind in ('R', 'AL'): return True
            if kind == 'L': return False
        return False
    def measure(self, text, style):
        return self.font(style).getlength(text, **({'direction':'rtl'} if self.raqm and self.rtl(text) else {}))/self.scale
    def glyph_style(self,text,style):
        if text.isascii() or text.isspace(): return style
        key=(text,style.get('family'),bool(style.get('bold')),bool(style.get('italic')),bool(style.get('mono')))
        if key not in self.glyphs:
            def missing(st):
                font=self.font(dict(st,size=16))
                unknown=font.getmask('\U0010ffff')
                return any((glyph:=font.getmask(char)).size==unknown.size and bytes(glyph)==bytes(unknown)
                           for char in text if unicodedata.category(char) not in ('Cf','Cc','Zl','Zp')
                           and char not in ('\ufe0e','\ufe0f') and not 0xe0100 <= ord(char) <= 0xe01ef)
            found=None
            if missing(style):
                families=(family for family in self.p['fonts'] if family not in
                          ('regular','bold','italic','bolditalic','mono','emoji','symbols','symbols2','math'))
                found=next((family for family in (*families,'math','symbols','symbols2')
                            if self.p['fonts'].get(family) and not missing(dict(style,family=family))),'missing')
            if len(self.glyphs)<4096: self.glyphs[key]=found
        else: found=self.glyphs[key]
        if found=='missing': self.warn('text_glyph_missing')
        return dict(style,family=found) if found and found!='missing' else style
    def cached_image(self, key, producer):
        if key not in self.images:
            image = producer().convert('RGBA')
            if image.width*image.height > 4_500_000:
                raise ValueError('decoded_image_limit')
            path=Path(self.p['output'])/('asset-'+hashlib.sha256(str(key).encode()).hexdigest()+'.png')
            image.save(path,format='PNG')
            self.image_bytes += path.stat().st_size
            if self.image_bytes > 64*1024*1024:
                raise ValueError('decoded_cache_limit')
            self.images[key] = Raster(path,image.size)
            image.close()
        return self.images[key]
    def asset(self, node, size, color):
        self.document_id = node.a.get('data-document')
        uri = node.a.get('data-tgs') or node.a.get('src')
        if not uri: return None
        key = (uri, round(size*self.scale), color if node.a.get('data-tint') else '')
        def produce():
            path = self.path(uri)
            self.checkpoint('decode_asset')
            if path.suffix == '.json':
                from rlottie_python import LottieAnimation
                data = json.loads(path.read_text(encoding='utf8'))
                if any(a.get('p') or a.get('u') for a in data.get('assets', [])):
                    raise ValueError('tgs_external_asset')
                animation = LottieAnimation.from_data(json.dumps(data))
                total = int(animation.lottie_animation_get_totalframe())
                image = None
                for frame in dict.fromkeys((min(12,max(0,total-1)), 0, max(0,total//2))):
                    image = animation.render_pillow_frame(frame, width=round(size*self.scale), height=round(size*self.scale))
                    if image.getchannel('A').getbbox(): break
                if image is None or not image.getchannel('A').getbbox():
                    raise ValueError('empty_animation_frame')
            elif path.suffix in ('.webm','.mp4'):
                ffmpeg = shutil.which('ffmpeg')
                if not ffmpeg: raise ValueError('ffmpeg_missing')
                output = self.root / 'video-frame.png'
                command = [ffmpeg,'-v','error','-nostdin','-threads','1']
                if path.suffix == '.webm': command += ['-c:v','libvpx-vp9']
                side=min(1600,max(16,round(size*self.scale)))
                command += ['-i',str(path),'-frames:v','1','-vf',f'scale={side}:{side}:force_original_aspect_ratio=decrease','-threads','1','-y',str(output)]
                process = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
                if process.returncode: raise ValueError('video_decode_failed')
                with Image.open(output) as source: image = source.convert('RGBA')
                output.unlink(missing_ok=True)
                if path.suffix == '.webm' and image.getchannel('A').getextrema() == (255,255):
                    self.warn('webm_opaque_frame')
            else:
                with Image.open(path) as source:
                    if source.width*source.height > 24_000_000: raise ValueError('image_pixels_limit')
                    side=min(2048,max(32,round(size*self.scale)))
                    source.thumbnail((side,side))
                    image = source.convert('RGBA')
            if node.a.get('data-tint'):
                solid = Image.new('RGBA', image.size, color)
                solid.putalpha(image.getchannel('A'))
                image = solid
            return image
        try:
            return self.cached_image(key, produce)
        except Exception as error:
            self.warn('asset_decode_fallback', error)
            fallback = node.a.get('data-fallback')
            if fallback:
                try:
                    def load_thumb():
                        with Image.open(self.path(fallback)) as source: return source.convert('RGBA')
                    return self.cached_image(('thumb',fallback),load_thumb)
                except Exception as error: self.warn('thumbnail_failed',error)
            return None
    def emoji(self, text, size):
        path = self.p['fonts'].get('emoji')
        if not path: return None
        def produce():
            font = ImageFont.truetype(path, 109)
            bounds = font.getbbox(text)
            image = Image.new('RGBA',(max(1,bounds[2]-bounds[0]),max(1,bounds[3]-bounds[1])))
            ImageDraw.Draw(image).text((-bounds[0],-bounds[1]),text,font=font,embedded_color=True)
            if not image.getchannel('A').getbbox(): raise ValueError('emoji_glyph_missing')
            return image
        try: return self.cached_image(('unicode',text),produce)
        except Exception as error:
            self.warn('unicode_emoji_fallback',error)
            return None
    def atoms(self, nodes, style):
        result = []
        for node in nodes:
            if isinstance(node,str):
                for part in regex.findall(r'\X',node):
                    if part == '\n': result.append(('newline',None,style)); continue
                    if part == '\t': part = '    '
                    if part == '╰':
                        result.append(('corner',part,style)); continue
                    emoji = None
                    if regex.search(r'\p{Extended_Pictographic}|\p{Regional_Indicator}|\u20e3',part):
                        emoji = self.emoji(part,style.get('size',16))
                    if emoji is not None: result.append(('image',emoji,dict(style, image_size=style.get('size',16)*1.3)))
                    else: result.append(('text',part,self.glyph_style(part,style)))
                continue
            st = dict(style)
            css = node.a.get('style','')
            if node.tag in ('b','strong','th'): st['bold'] = True
            if node.tag in ('i','em'): st['italic'] = True
            if node.tag in ('code','pre'): st['mono'] = True
            if node.tag in ('u','ins'): st['underline'] = True
            if node.tag in ('s','del'): st['strike'] = True
            if node.tag in ('sup','sub'):
                st['shift'] = -4 if node.tag=='sup' else 4
                st['size'] = max(9,st.get('size',16)*.75)
            if node.tag == 'mark': st['background'] = '#665a29' if self.dark else '#fff3a3'
            if node.has('link'): st['color'] = style['accent']
            if node.has('via-inline'): st.update(size=16,bold=False,color=style['accent'])
            if node.has('reply-media'): st['color']=style['accent']
            if node.has('reply-file-icon'):
                result.append(('file-icon',None,dict(st,size=12)))
                continue
            if node.has('reply-forward-icon'):
                result.append(('forward-icon',None,dict(st,size=12)))
                continue
            if node.has('views-icon') or node.has('pin-icon'):
                kind='views-icon' if node.has('views-icon') else 'pin-icon'
                result.append((kind,None,dict(st,size=12,color=st['color'] if kind=='views-icon' else style['accent'])))
                continue
            if node.has('spoiler') and not node.has('revealed'): st['hidden'] = True
            if node.has('name'):
                st['color'] = style['accent']
                colors = re.findall(r'#[0-9a-fA-F]{6}',css)
                if 'linear-gradient' in css and len(colors)>1: st['gradient'] = colors
            if node.has('rank'):
                st.update(size=11,color=style['accent'])
                result.append(('badge',node.text(),st))
                continue
            if node.has('premium'):
                st.update(size=13,color=style['accent'])
                result.append(('text',' ',st))
                result.append(('star',None,st))
                continue
            if node.has('language'): st.update(size=11,color=self.muted)
            if node.tag == 'small': st.update(size=12,color=self.muted)
            color = re.search(r'(?:^|;)\s*color:\s*(#[0-9a-fA-F]{3,8})(?:;|$)',css)
            if color: st['color'] = color[1]
            if 'font-weight: bold' in css: st['bold'] = True
            if 'font-style: italic' in css: st['italic'] = True
            if node.tag == 'br': result.append(('newline',None,st))
            elif node.tag in ('img','video') or 'data-tgs' in node.a:
                size = st.get('size',16)*1.3
                asset = self.asset(node,size,st['color'])
                if asset is not None: result.append(('image',asset,dict(st,image_size=size)))
                else: result.extend(self.atoms([node.a.get('data-alt','◇')],st))
            else:
                result.extend(self.atoms(node.children,st))
        merged = []
        for kind,value,st in result:
            if kind=='text' and merged and merged[-1][0]=='text' and merged[-1][2]==st:
                merged[-1] = ('text',merged[-1][1]+value,st)
            else: merged.append((kind,value,st))
        return merged
    def atom_width(self,kind,value,style):
        if kind=='image': return style['image_size']
        if kind=='corner': return style.get('size',16)*.75
        if kind in ('star','file-icon','forward-icon','views-icon','pin-icon'): return style.get('size',16)
        return self.measure(value,style)+(14 if kind=='badge' else 0)
    def inline(self,nodes,width,style,align='left'):
        atoms = self.atoms(nodes,style)
        tokens = []
        for kind,value,st in atoms:
            if kind=='text':
                tokens.extend(('text',word,st) for word in regex.findall(r'\s+|\S+',value))
            else: tokens.append((kind,value,st))
        lines, line, used = [], [], 0
        def flush():
            nonlocal line,used
            lines.append((line,used)); line=[]; used=0
        for kind,value,st in tokens:
            if kind=='newline': flush(); continue
            extent = self.atom_width(kind,value,st)
            if kind=='badge' and extent>width:
                kind='text'; st=dict(st,background=self.code)
            if extent > width and kind=='text':
                fragments,fragment = [],''
                for cluster in regex.findall(r'\X',value):
                    if fragment and self.measure(fragment+cluster,st)>width:
                        fragments.append(fragment); fragment=''
                    fragment+=cluster
                if fragment: fragments.append(fragment)
            else: fragments=[value]
            for fragment in fragments:
                extent = self.atom_width(kind,fragment,st)
                if line and used+extent>width: flush()
                line.append((kind,fragment,st,extent)); used+=extent
        if line: flush()
        box = Box(width)
        for line,used in lines:
            text = ''.join(v for k,v,st,w in line if k=='text')
            rtl = self.rtl(text)
            if any(unicodedata.bidirectional(c) in ('R','AL') for c in text) and not self.raqm:
                self.warn('raqm_unavailable')
            if rtl and len({str(st) for _,_,st,_ in line})>1:
                self.warn('mixed_rtl_styles_approximate')
            height = max([st['image_size']+4 if k=='image' else st.get('size',16)*1.35 for k,_,st,_ in line]+[style.get('size',16)*1.35])
            metrics=[self.font(st).getmetrics() for k,_,st,_ in line if k in ('text','badge')]
            ascent=max([a/self.scale for a,d in metrics]+[style.get('size',16)*.8])
            descent=max([d/self.scale for a,d in metrics]+[style.get('size',16)*.2])
            height=max(height,ascent+descent)
            baseline=box.h+(height-ascent-descent)/2+ascent
            x = max(0,(width-used)/2) if align=='center' else max(0,width-used) if align=='right' or rtl else 0
            ordered = list(reversed(line)) if rtl else line
            runs=[]
            for k,v,st,w in ordered:
                if not rtl and k=='text' and runs and runs[-1][0]=='text' and runs[-1][2]==st:
                    old=runs[-1]; runs[-1]=(k,old[1]+v,st,old[3]+w)
                else: runs.append((k,v,st,w))
            for kind,value,st,extent in runs:
                y = box.h+(height-(st['image_size'] if kind=='image' else st.get('size',16)))/2+st.get('shift',0)
                if st.get('hidden'):
                    box.ops.append(('rect',x,y,(extent,st.get('size',16)+2,self.muted,3)))
                elif kind=='image':
                    box.ops.append(('image',x,y,(value,extent,extent,False)))
                elif kind=='star':
                    box.ops.append(('star',x,y,(extent,st['color'])))
                elif kind=='corner':
                    box.ops.append(('corner',x,y,(extent,st['color'])))
                elif kind in ('file-icon','forward-icon','views-icon','pin-icon'):
                    box.ops.append((kind,x,y,(extent,st['color'])))
                elif kind=='badge':
                    box.ops.append(('rect',x,y-3,(extent,st['size']+6,self.code,7)))
                    box.ops.append(('text',x+7,y,(value,st)))
                else:
                    box.ops.append(('text',x,baseline+st.get('shift',0),(value,dict(st,text_anchor='ls'))))
                x+=extent
            box.h+=height
        return box
    def flow(self,nodes,width,style):
        box=Box(width); pending=[]; after_block=False
        def flush(before_block=False):
            if pending and after_block and isinstance(pending[0],str) and pending[0].startswith('\n'):
                pending[0]=pending[0][1:]
            if pending and before_block and isinstance(pending[-1],str) and pending[-1].endswith('\n'):
                pending[-1]=pending[-1][:-1]
            if pending:
                item=self.inline(pending,width,style,align=style.get('align','left'))
                box.add(item,0,box.h); box.h+=item.h; pending.clear()
        for node in nodes:
            if isinstance(node,Node) and (node.tag in self.BLOCKS or node.has('media') or node.has('sticker') or node.has('math')):
                flush(before_block=True); item=self.block(node,width,style)
                box.add(item,0,box.h); box.h+=item.h
                after_block=True
            else: pending.append(node)
        flush()
        return box
    def block(self,node,width,style):
        if node.tag in ('style','script','meta'): return Box(width)
        style=dict(style)
        if node.tag.startswith('h') and node.tag[1:].isdigit(): style.update(size={1:26,2:23,3:20}.get(int(node.tag[1:]),18),bold=True)
        if node.has('meta') or node.has('caption') or node.has('via') or node.has('forward') or node.has('day') or node.has('service'):
            style.update(size=12,color=self.muted)
        if node.has('service'): style.update(size=14,color=self.fg)
        if node.has('author'): style.update(bold=True,color=style['accent'])
        if node.has('forward'): style.update(size=14,color=style['accent'])
        if node.has('attachment-title'): style.update(size=16,bold=True)
        if node.has('attachment-subtitle'): style.update(size=14,bold=False,color=self.muted)
        if node.has('language'): style.update(size=11,color=self.muted)
        if node.has('pattern-overlay') or node.has('reply-gift'): return Box(width)
        if node.has('reply'): return self.reply_card(node,width,style)
        if node.has('geo-card'):
            fields={c.a.get('class',''):c for c in node.children if isinstance(c,Node)}
            box=Box(width,99,[('geo-map',0,0,(width,94,style['accent'],self.dark))])
            for name,size,color,bold,gap in (
                ('geo-title',16,style['color'],True,1),
                ('geo-address',13,style['color'],False,2),
                ('geo-coords',12,self.muted,False,3)):
                field=fields.get(name)
                if field and field.text().strip():
                    line=self.inline(field.children,max(1,width-8),dict(style,size=size,color=color,bold=bold))
                    box.add(line,4,box.h+gap); box.h+=line.h+gap
            box.h+=4
            return box
        if node.has('todo-card'):
            fields=[c for c in node.children if isinstance(c,Node)]
            inner=max(1,width-8); box=Box(width)
            for field in fields:
                if field.has('todo-title'):
                    part=self.inline(field.children,inner,dict(style,size=18,bold=True))
                    box.add(part,4,box.h); box.h+=part.h+2
                elif field.has('todo-label'):
                    part=self.inline(field.children,inner,dict(style,size=13,color=self.muted))
                    box.add(part,4,box.h); box.h+=part.h+8
                elif field.has('todo-item'):
                    done=field.a.get('data-done')=='1'
                    body=next((c for c in field.children if isinstance(c,Node) and c.has('todo-text')),None)
                    content=self.inline(body.children if body else field.children,max(1,inner-28),dict(style,size=16))
                    box.ops.append(('todo-mark',8,box.h+max(3,(content.h-14)/2),(14,style['accent'],done)))
                    box.add(content,30,box.h)
                    box.h+=content.h+3
                    by=next((c for c in field.children if isinstance(c,Node) and c.has('todo-by')),None)
                    if by:
                        credit=self.inline(by.children,max(1,inner-28),dict(style,size=12,color=self.muted))
                        box.add(credit,30,box.h); box.h+=credit.h+3
                elif field.has('todo-progress'):
                    box.h+=5
                    part=self.inline(field.children,inner,dict(style,size=13,color=self.muted))
                    box.add(part,4,box.h); box.h+=part.h
            box.h+=3
            return box
        if node.has('giveaway'):
            fields={c.a.get('class',''):c for c in node.children if isinstance(c,Node)}
            inner=max(1,width-24)
            box=Box(width)
            box.ops.append(('rect',0,0,(width,1,self.tint(style.get('bubble_color',self.bubble),'#e7b72e',.55),0)))
            art=min(112,max(76,width*.31))
            ax=(width-art)/2; ay=12
            box.ops.append(('giveaway-art',ax,ay,(art,)))
            box.h=ay+art+5
            for name,size,color,bold,gap in (
                ('giveaway-title',19,style['color'],True,2),
                ('giveaway-prize',16,style['color'],True,3),
                ('giveaway-description',14,style['color'],False,4),
                ('giveaway-channels',13,style['accent'],True,4),
                ('giveaway-countries',12,self.muted,False,4),
                ('giveaway-date',13,self.muted,False,5)):
                field=fields.get(name)
                if field and field.text().strip():
                    line=self.inline(field.children,inner,dict(style,size=size,color=color,bold=bold),align='center')
                    box.add(line,12,box.h+gap); box.h+=line.h+gap
            box.h+=9
            return box
        if node.has('video-card'):
            media=next((c for c in node.children if isinstance(c,Node)),None)
            image=self.asset(media,min(width,800),style['color']) if media else None
            if image is None: return self.inline(['[video unavailable]'],width,style)
            ratio=image.width/max(1,image.height)
            w=min(width,360*ratio); h=w/ratio
            x=(width-w)/2
            box=Box(width,h+6,[('image',x,3,(image,w,h,True if media.has('round') else 'thumb'))])
            label=node.a.get('data-label','')
            if label:
                badge=self.inline([label],max(1,w-16),dict(style,size=11,color='#ffffff'))
                bw=min(w-8,self.inline_width([label],dict(style,size=11))+12)
                box.ops.append(('rect',x+4,7,(bw,badge.h+4,'#25282c',6)))
                box.add(badge,x+10,9)
            return box
        if node.has('reply-author'): style.update(bold=True,color=style['accent'])
        if node.has('author'):
            rank=next((c for c in node.children if isinstance(c,Node) and c.has('rank')),None)
            names=[c for c in node.children if c is not rank]
            if rank:
                rw=min(width-60,max(45,self.inline_width(rank.children,dict(style,size=11))+16))
                title=self.inline(names,max(40,width-rw-10),style)
                badge=self.inline(rank.children,max(20,rw-14),dict(style,size=11),align='center')
                box=Box(width,max(title.h,badge.h+8)+6)
                box.add(title)
                box.ops.append(('rect',width-rw,2,(rw,badge.h+6,self.code,8)))
                box.add(badge,width-rw+7,5)
                return box
            title=self.inline(names,width,style); title.h+=6
            return title
        if node.has('media-spoiler') and not node.has('revealed'):
            box=Box(width,180,[('rect',0,0,(width,180,self.muted,10))])
            box.add(self.inline(['•••'],width,style,align='center'),0,78)
            return box
        if node.has('math'):
            try:
                from matplotlib.mathtext import math_to_image
                from matplotlib import rc_context
                from matplotlib.font_manager import FontProperties
                out=io.BytesIO()
                with rc_context({'savefig.transparent':True,'savefig.facecolor':'none','text.usetex':False}):
                    math_to_image('$'+node.text().strip('$')+'$',out,prop=FontProperties(size=18),dpi=72*self.scale,format='png',color=style['color'])
                out.seek(0)
                with Image.open(out) as source: image=source.convert('RGBA')
                w=min(width,image.width/self.scale); h=image.height*w/image.width
                return Box(width,h+12,[('image',(width-w)/2,6,(image,w,h,False))])
            except Exception as error:
                self.warn('formula_source_fallback',error)
                return self.inline([node.text()],width,dict(style,mono=True))
        if node.tag in ('img','video') or 'data-tgs' in node.a:
            size=200 if node.has('sticker') else 40 if node.has('reply-thumb') else width
            image=self.asset(node,800 if node.has('media') else min(size,800),style['color'])
            if image is None: return self.inline([node.a.get('data-alt','[media unavailable]')],width,style)
            w=min(size,width,image.width/self.scale if not node.has('sticker') else size)
            h=image.height*w/image.width
            if h>650: w*=650/h; h=650
            return Box(width,h+10,[('image',(width-w)/2,5,(image,w,h,node.has('round')))])
        if node.has('grid'):
            items=[c for c in node.children if isinstance(c,Node)]
            box=Box(width); cell=(width-6)/2
            for i in range(0,len(items),2):
                pair=[self.block(c,cell,style) for c in items[i:i+2]]
                height=max(b.h for b in pair)
                for j,b in enumerate(pair): box.add(b,j*(cell+6),box.h)
                box.h+=height+6
            return box
        if node.tag=='table': return self.table(node,width,style)
        if node.tag in ('ul','ol'):
            box=Box(width)
            for i,child in enumerate(c for c in node.children if isinstance(c,Node)):
                prefix=(child.a.get('value',str(i+1))+'.') if node.tag=='ol' else '•'
                content=self.flow(child.children,width-24,style)
                box.add(self.inline([prefix],22,style),0,box.h)
                box.add(content,24,box.h); box.h+=max(content.h,24)+3
            return box
        if node.tag=='hr': return Box(width,12,[('rect',0,6,(width,1,self.muted,0))])
        if node.has('wave'):
            values=[int(re.search(r'height:(\d+)',c.a.get('style','height:3'))[1]) for c in node.children if isinstance(c,Node)]
            return Box(width,32,[('rect',i*4,(32-v)/2,(2,v,style['accent'],1)) for i,v in enumerate(values[:int(width/4)])])
        if node.has('attachment'):
            items=[c for c in node.children if isinstance(c,Node)]
            box=Box(width)
            if items:
                box.ops.append(('rect',0,3,(44,44,style['accent'],22)))
                if items[0].has('document-icon'):
                    box.ops.append(('file-icon',11,12,(24,style.get('bubble_color',self.bubble),style['accent'])))
                else:
                    icon=self.inline(items[0].children,42,dict(style,size=23),align='center')
                    box.add(icon,0,7)
                body=self.flow(items[1:],width-56,style)
                box.add(body,56,4); box.h=max(52,body.h+8)
            return box
        if node.tag=='pre':
            code_style=dict(style,mono=True,size=13)
            language=next((c for c in node.children if isinstance(c,Node) and c.has('language')),None)
            source=[c for c in node.children if c is not language]
            content_width=min(width,max(80,self.inline_width(source,code_style)+16))
            if language and language.text():
                content_width=min(width,max(content_width,self.inline_width(language.children,dict(code_style,size=11))+16))
            body=self.inline(source,max(24,content_width-16),code_style)
            header=self.inline(language.children,max(24,content_width-16),dict(code_style,size=11,color=self.fg)) if language and language.text() else Box(content_width)
            hh=header.h+4 if header.h else 0
            box=Box(width,hh+body.h+10)
            box.ops.append(('rect',0,2,(content_width,hh+body.h+6,'#0e1012' if self.dark else '#f0f2f4',4)))
            if hh:
                box.ops.append(('rect',0,2,(content_width,hh,self.tint(self.bubble,style['accent'],.35),3)))
                box.add(header,8,4)
            box.add(body,8,hh+5)
            box.ops.append(('rect',0,2,(3,hh+body.h+6,style['accent'],1)))
            return box
        if node.has('buttons') or node.has('reactions'):
            rich=node.has('rich-buttons')
            box=Box(width); x=0; y=5 if rich else 0; lineh=0
            for child in node.children:
                if not isinstance(child,Node): continue
                button_color={'primary':'#3567a0','danger':'#a84545','success':'#327a50'}.get(child.a.get('data-button-style')) if node.has('buttons') else None
                if rich:
                    button_color,foreground={'primary':('#334754','#72bdff'),'danger':('#51414b','#ff727e'),'success':('#3a5146','#73e483')}.get(child.a.get('data-button-style'),('#303d46','#ffffff'))
                else: foreground='#ffffff' if button_color else style['color']
                button_style=dict(style,size=13,color=foreground)
                w=min(width,max(55,self.inline_width(child.children,button_style)+24))
                b=self.inline(child.children,w-14,button_style,align='center')
                if x and x+w>width: x=0; y+=lineh+5; lineh=0
                box.ops.append(('rect',x,y,(w,b.h+8,button_color or self.code,8)))
                box.add(b,x+7,y+4); x+=w+5; lineh=max(lineh,b.h+8)
            box.h=y+lineh+(5 if rich else 6 if lineh else 0); return box
        padded=node.tag in ('blockquote','details','pre') or node.has('reply') or node.has('gift') or node.has('notice') or node.has('poll-option')
        pad=10 if padded else 0
        if node.tag=='pre': style.update(mono=True,size=13)
        if node.has('reply'): style.update(size=13)
        colors=re.findall(r'#[0-9a-fA-F]{6}',node.a.get('style',''))
        if node.has('reply') and colors: style['accent']=colors[0]
        children=node.children
        if node.tag=='details' and 'open' not in node.a:
            children=[c for c in children if isinstance(c,Node) and c.tag=='summary']
        if node.has('gift'):
            style['align']='center'
            if colors: style['color']=colors[-1]
        if node.has('meta') or node.has('day') or node.has('service'):
            content=self.inline(children,width-2*pad,style,align='right' if node.has('meta') else 'center')
        else: content=self.flow(children,width-2*pad,style)
        if not content.h: return Box(width)
        margin=5 if padded or node.tag in ('p','h1','h2','h3') else 2
        box=Box(width,content.h+pad*2+margin*2)
        if padded:
            if node.has('gift') and len(colors)>=2:
                box.ops.append(('gradient',0,margin,(width,box.h-2*margin,colors[:2],True)))
            else:
                background=self.tint(style.get('bubble_color',self.bubble),style.get('quote_accent',style['accent']),.14) if node.tag in ('blockquote','details') else self.code
                box.ops.append(('rect',0,margin,(width,box.h-2*margin,background,8)))
            if node.tag in ('blockquote','details') or node.has('reply'):
                box.ops.append(('quote-bar',0,margin,(3,box.h-2*margin,self.quote_colors(node,style))))
            for child in node.children:
                if isinstance(child,Node) and child.has('pattern-overlay'):
                    sources=[c for c in child.children if isinstance(c,Node)]
                    if sources:
                        color=child.a.get('data-pattern-color',style['accent'])
                        asset=self.asset(sources[0],40,color)
                        if asset is not None: box.ops.append(('pattern',0,margin,(width,box.h-2*margin,asset,color)))
        if node.has('media-spoiler') and not node.has('revealed'):
            box.ops.append(('rect',0,0,(width,box.h,self.muted,10)))
            box.add(self.inline(['•••'],width,style,align='center'),0,box.h/2-12)
        else: box.add(content,pad,pad+margin)
        return box
    @staticmethod
    def tint(background,accent,amount):
        base,ink=ImageColor.getrgb(background),ImageColor.getrgb(accent)
        return '#'+''.join(f'{round(a*(1-amount)+b*amount):02x}' for a,b in zip(base,ink))
    def quote_colors(self,node,style):
        colors=re.findall(r'#[0-9a-fA-F]{6}',node.a.get('data-quote-colors',''))[:3]
        colors=colors or style.get('quote_colors') or [style['accent']]
        return colors if len(colors)>1 else [colors[0],self.tint(colors[0],style.get('bubble_color',self.bubble),.45)]
    def reply_preview_nodes(self,nodes):
        result=[]
        for node in nodes:
            if isinstance(node,str):
                result.append(re.sub(r'[\r\n]+',' ',node)); continue
            if node.has('language'): continue
            if node.tag=='br': result.append(' '); continue
            block=node.tag in self.BLOCKS
            clone=Node('code' if node.tag=='pre' else 'span' if block or node.tag in ('b','strong') else node.tag,node.a.items())
            clone.children=self.reply_preview_nodes(node.children)
            if block: result.append(' ')
            result.append(clone)
            if block: result.append(' ')
        return result
    def reply_gift(self,node):
        wrapper=next((c for c in node.children if isinstance(c,Node) and c.has('reply-gift')),None)
        source=next((c for c in wrapper.children if isinstance(c,Node)),None) if wrapper else None
        return self.asset(source,24,self.fg) if source else None
    def reply_card(self,node,width,style):
        style=dict(style,size=13)
        colors=re.findall(r'#[0-9a-fA-F]{6}',node.a.get('style',''))
        if colors: style['accent']=colors[0]
        thumbnail=next((c for c in node.children if isinstance(c,Node) and c.has('reply-thumb')),None)
        content=next((c for c in node.children if isinstance(c,Node) and c.has('reply-content')),None)
        sources=content.children if content else [c for c in node.children if c is not thumbnail and not (isinstance(c,Node) and c.has('pattern-overlay'))]
        image=self.asset(thumbnail,44,style['accent']) if thumbnail else None
        gift=self.reply_gift(node)
        left=66 if image else 12
        inner=max(24,width-left-12-(30 if gift else 0))
        text=Box(inner)
        for child in sources:
            if isinstance(child,Node) and child.has('reply-text'):
                snippet=self.inline(self.reply_preview_nodes(child.children),inner,style)
                if snippet.h>40:
                    snippet.ops=[op for op in snippet.ops if op[2]<36]
                    snippet.h=40
                text.add(snippet,0,text.h); text.h+=snippet.h
            else:
                b=self.block(child,inner,style) if isinstance(child,Node) else self.inline([child],inner,style)
                text.add(b,0,text.h); text.h+=b.h
        height=max(text.h,44 if image else 0)+16
        box=Box(width,height+8)
        background=self.tint(style.get('bubble_color',self.bubble),style['accent'],.14)
        box.ops.append(('rect',0,4,(width,height,background,7)))
        for child in node.children:
            if not isinstance(child,Node) or not child.has('pattern-overlay'): continue
            pattern=next((c for c in child.children if isinstance(c,Node)),None)
            if pattern:
                asset=self.asset(pattern,40,style['accent'])
                if asset is not None:
                    pattern_width=min(200,width*.55)
                    box.ops.append(('reply-pattern',width-pattern_width,4,(pattern_width,height,asset,style['accent'])))
        box.ops.append(('quote-bar',0,4,(3,height,self.quote_colors(node,dict(style,quote_colors=None)))))
        if image: box.ops.append(('image',12,12,(image,44,44,'thumb')))
        box.add(text,left,12)
        if gift: box.ops.append(('image',width-30,8,(gift,24,24,False)))
        return box
    def table(self,node,width,style):
        rows=[c for c in node.children if isinstance(c,Node) and c.tag=='tr']
        occupied={}; grid=[]; columns=1
        for ri,row in enumerate(rows):
            ci=0
            for cell in row.children:
                if not isinstance(cell,Node): continue
                span=max(1,min(100,int(cell.a.get('colspan','1'))))
                rowspan=max(1,min(len(rows)-ri,int(cell.a.get('rowspan','1'))))
                while any(occupied.get((ri,col)) for col in range(ci,ci+span)): ci+=1
                if ci+span>100: raise ValueError('table_columns_limit')
                grid.append((ri,ci,rowspan,span,cell))
                for rr in range(ri,ri+rowspan):
                    for cc in range(ci,ci+span): occupied[(rr,cc)]=True
                ci+=span; columns=max(columns,ci)
        unit=width/columns
        if unit<36: self.warn('table_narrow_columns')
        heights=[24 for _ in rows]; measured=[]
        for ri,ci,rowspan,span,cell in grid:
                w=unit*span
                st=dict(style,size=13,bold=cell.tag=='th')
                align='center' if 'center' in cell.a.get('style','') else 'right' if 'right' in cell.a.get('style','') else 'left'
                content=self.inline(cell.children,max(8,w-12),st,align)
                needed=content.h+12-sum(heights[ri:ri+rowspan])
                if needed>0: heights[ri+rowspan-1]+=needed
                measured.append((ri,ci,rowspan,span,content))
        box=Box(width,sum(heights))
        for ri,ci,rowspan,span,b in measured:
            y=sum(heights[:ri]); h=sum(heights[ri:ri+rowspan])
            box.ops.append(('border',ci*unit,y,(span*unit,h,self.muted,0)))
            box.add(b,ci*unit+6,y+6)
        return box
    def inline_width(self,nodes,style):
        current=maximum=0
        for kind,value,st in self.atoms(nodes,style):
            if kind=='newline': maximum=max(maximum,current); current=0
            else: current+=self.atom_width(kind,value,st)
        return max(maximum,current)
    def natural_width(self,node,style,limit):
        if isinstance(node,str): return self.inline_width([node],style)
        if node.has('reply'): return 0
        if node.has('geo-card'): return min(limit,320)
        if node.has('todo-card'): return min(limit,340)
        if node.has('giveaway'): return min(limit,340)
        style=dict(style)
        if node.has('meta') or node.has('caption') or node.has('via') or node.has('forward') or node.has('day'):
            style.update(size=12,color=self.muted)
        if node.has('author'):
            style.update(bold=True)
            rank=next((c for c in node.children if isinstance(c,Node) and c.has('rank')),None)
            names=[c for c in node.children if c is not rank]
            width=self.inline_width(names,style)
            if rank:
                width=max(60,width)+max(45,self.inline_width(rank.children,dict(style,size=11))+16)+10
            return width
        if node.has('forward'): style.update(size=14)
        if node.has('attachment-title'): style.update(size=16,bold=True)
        if node.has('attachment-subtitle'): style.update(size=14)
        if node.tag in ('table',) or node.has('grid') or node.has('math'):
            return limit
        if node.has('sticker'): return 200
        if node.has('video-card'):
            try: ratio=float(node.a.get('data-width',0))/float(node.a.get('data-height',0))
            except (ValueError,ZeroDivisionError): ratio=0
            if ratio<=0:
                media=next((c for c in node.children if isinstance(c,Node)),None)
                image=self.asset(media,360,style.get('color',self.fg)) if media else None
                ratio=image.width/max(1,image.height) if image else 1
            return min(limit,max(180,min(360,360*ratio)))
        if node.has('media'): return limit
        if node.has('pattern-overlay'): return 0
        if node.tag=='pre': style.update(mono=True,size=13)
        if node.tag in ('h1','h2','h3','h4','h5','h6'):
            style.update(size={1:26,2:23,3:20}.get(int(node.tag[1:]),18),bold=True)
        if node.has('reply'): style.update(size=13)
        widths=[]; pending=[]
        children=node.children
        if node.tag=='details' and 'open' not in node.a:
            children=[child for child in children if isinstance(child,Node) and child.tag=='summary']
        for child in children:
            if isinstance(child,Node) and (child.tag in self.BLOCKS or child.has('media') or child.has('sticker') or child.has('math')):
                if pending: widths.append(self.inline_width(pending,style)); pending=[]
                widths.append(self.natural_width(child,style,limit))
            else: pending.append(child)
        if pending: widths.append(self.inline_width(pending,style))
        width=max(widths+[0])
        if node.tag=='details' and 'open' not in node.a:
            width=min(width,360)
        if node.has('attachment'): width+=56
        if node.tag in ('blockquote','details','pre','ul','ol') or node.has('reply') or node.has('notice'): width+=24
        if node.has('reply') and any(isinstance(c,Node) and c.has('reply-thumb') for c in node.children): width+=54
        if node.has('reply') and any(isinstance(c,Node) and c.has('reply-gift') for c in node.children): width+=30
        if node.has('gift'): width=max(260,width+20)
        return width
    def row_parts(self,row):
        style=dict(size=17,color=self.fg,accent='#79b8e8',bubble_color=self.out if row.has('outgoing') else self.bubble)
        colors=re.findall(r'#[0-9a-fA-F]{6}',row.a.get('style',''))
        if colors: style['accent']=colors[0]
        style['quote_colors']=re.findall(r'#[0-9a-fA-F]{6}',row.a.get('data-quote-colors',''))[:3]
        bubble=next(c for c in row.children if isinstance(c,Node) and c.has('bubble'))
        author=next((c for c in bubble.children if isinstance(c,Node) and c.has('author')),None)
        if author and author.a.get('data-quote-colors'):
            style['quote_colors']=re.findall(r'#[0-9a-fA-F]{6}',author.a['data-quote-colors'])[:3]
        quote_accent=re.findall(r'#[0-9a-fA-F]{6}',author.a.get('data-quote-accent','')) if author else []
        style['quote_accent']=quote_accent[0] if quote_accent else style['accent']
        avatar=next((c for c in row.children if isinstance(c,Node) and (c.has('avatar') or c.has('initials'))),None)
        children=[c for c in bubble.children if not (isinstance(c,Node) and c.has('author') and row.has('grouped'))]
        return style,children,avatar
    def row_width(self,row,limit):
        style,children,avatar=self.row_parts(row)
        width=max([self.natural_width(c,style,limit-28) for c in children]+[104])+28
        return min(limit,max(132,math.ceil(width)))
    def bubble_body(self,children,width,style):
        body=next((c for c in children if isinstance(c,Node) and c.has('body')),None)
        meta=next((c for c in children if isinstance(c,Node) and c.has('meta')),None)
        if body and meta and meta.text() and '\n' not in body.text():
            index=children.index(body)
            trailing=children[index+1:]
            simple=not any(isinstance(c,Node) and c.tag in self.BLOCKS for c in body.children)
            if simple and all(c is meta or (isinstance(c,Node) and not c.children) for c in trailing):
                mw=self.inline_width(meta.children,dict(style,size=12))
                bw=self.inline_width(body.children,style)
                if bw and bw+mw+16<=width:
                    box=self.flow(children[:index],width,style)
                    text=self.inline(body.children,width-mw-16,style)
                    footer=self.inline(meta.children,mw,dict(style,size=12,color=self.muted),align='right')
                    lineheight=max(text.h,footer.h)
                    box.add(text,0,box.h)
                    box.add(footer,width-mw,box.h+lineheight-footer.h)
                    box.h+=lineheight+2
                    return box
        return self.flow(children,width,style)
    def layout(self,markup):
        tree=Tree(markup)
        def find(node):
            if node.a.get('id')=='quote': return node
            for c in node.children:
                if isinstance(c,Node):
                    result=find(c)
                    if result: return result
        quote=find(tree.root)
        if quote is None: raise ValueError('quote_root_missing')
        if self.options.get('compact',True):
            widths=[180]
            for row in quote.children:
                if not isinstance(row,Node) or not row.has('row'): continue
                self.message_id=row.a.get('data-message')
                _,_,avatar=self.row_parts(row)
                margin=48+(52 if avatar else 0)
                widths.append(self.row_width(row,self.width-margin)+margin)
            self.width=min(self.width,math.ceil(max(widths)))
        page=Box(self.width,24); breaks=[]
        for row in quote.children:
            if not isinstance(row,Node): continue
            style=dict(size=16,color=self.fg,accent='#79b8e8')
            if row.has('day'):
                b=self.block(row,self.width-48,style); page.add(b,24,page.h); page.h+=b.h+8; continue
            if not row.has('row'): continue
            self.message_id=row.a.get('data-message')
            self.checkpoint('layout_message')
            style,children,avatar=self.row_parts(row)
            available=self.row_width(row,self.width-48-(52 if avatar else 0))
            body=self.bubble_body(children,available-28,style)
            height=body.h+24
            bx=self.width-24-(52 if avatar else 0)-available if row.has('outgoing') else 24+(52 if avatar else 0)
            page.ops.append(('rect',bx,page.h,(available,height,self.out if row.has('outgoing') else self.bubble,14)))
            if not row.has('grouped'):
                page.ops.append(('tail',bx+available-10 if row.has('outgoing') else bx-8,page.h+height-16,
                                 (18,16,self.out if row.has('outgoing') else self.bubble,row.has('outgoing'))))
            page.add(body,bx+14,page.h+12)
            if avatar and not row.has('grouped'):
                ax=self.width-66 if row.has('outgoing') else 24
                ay=page.h+height-42
                if avatar.has('avatar'):
                    image=self.asset(avatar,42,style['accent'])
                    if image is not None: page.ops.append(('image',ax,ay,(image,42,42,True)))
                else:
                    page.ops.append(('rect',ax,ay,(42,42,style['accent'],21)))
                    initials=self.inline(avatar.children,42,dict(style,color='#ffffff',bold=True),align='center')
                    page.add(initials,ax,ay+8)
            page.h+=height+12; breaks.append(page.h)
        page.h+=12
        return page,breaks
    def gradient(self,size,colors,radial=False):
        w,h=size; a=ImageColor.getrgb(colors[0]); b=ImageColor.getrgb(colors[-1])
        tw,th=(64,64) if radial else (128,1)
        image=Image.new('RGBA',(tw,th)); pixels=[]
        for y in range(th):
            for x in range(tw):
                ratio=min(1,math.hypot((x-32)/42,(y-32)/42)) if radial else x/(tw-1)
                pixels.append(tuple(round(a[i]*(1-ratio)+b[i]*ratio) for i in range(3))+(255,))
        image.putdata(pixels)
        return image.resize((w,h),Image.Resampling.BILINEAR)
    def paint(self,canvas,op,offset):
        kind,x,y,value=op; s=self.scale
        x,y=round(x*s),round((y-offset)*s)
        draw=ImageDraw.Draw(canvas)
        if kind=='tail':
            w,h,color,outgoing=value
            points=[(0,0),(10,0)]+[(10+8*(i/12)**2,5+11*i/12) for i in range(13)]+[(0,16)]
            if not outgoing: points=[(w-px,py) for px,py in points]
            draw.polygon([(x+px*s,y+py*s) for px,py in points],fill=color)
        elif kind=='forward-icon':
            size,color=value
            points=[(0,12),(1,7),(3,4),(6,3),(8,3),(8,0),(14,6),(8,12),(8,8),(5,8),(2,10)]
            draw.polygon([(x+px*size*s/14,y+py*size*s/14) for px,py in points],fill=color)
        elif kind=='views-icon':
            size,color=value
            points=[]
            for i in range(25):
                t=i/24; points.append((x+t*size*s,y+(0.5-0.32*math.sin(math.pi*t))*size*s))
            for i in range(24,-1,-1):
                t=i/24; points.append((x+t*size*s,y+(0.5+0.32*math.sin(math.pi*t))*size*s))
            draw.line(points+[points[0]],fill=color,width=max(1,round(s)))
            draw.ellipse((x+size*.37*s,y+size*.37*s,x+size*.63*s,y+size*.63*s),fill=color)
        elif kind=='pin-icon':
            size,color=value
            points=[(.55,.04),(.96,.45),(.78,.50),(.59,.72),(.56,.89),(.35,.68),(.09,.94),(.04,.89),(.30,.63),(.09,.42),(.26,.39),(.48,.20)]
            draw.polygon([(x+px*size*s,y+py*size*s) for px,py in points],fill=color)
        elif kind=='file-icon':
            size,color=value[:2]
            background=value[2] if len(value)>2 else self.bubble
            points=[(2,0),(8,0),(12,4),(12,14),(2,14)]
            draw.polygon([(x+px*size*s/14,y+py*size*s/14) for px,py in points],fill=color)
            draw.line([(x+8*size*s/14,y),(x+8*size*s/14,y+4*size*s/14),(x+12*size*s/14,y+4*size*s/14)],fill=self.tint(color,background,.5),width=max(1,s))
        elif kind=='star':
            size,color=value; radius=size*s/2; points=[]
            for i in range(10):
                angle=-math.pi/2+i*math.pi/5; r=radius if i%2==0 else radius*.43
                points.append((x+radius+math.cos(angle)*r,y+radius+math.sin(angle)*r))
            draw.polygon(points,fill=color)
        elif kind=='corner':
            size,color=value; size*=s
            points=[(x+size*.16,y+size*.05),(x+size*.16,y+size*.55),
                    (x+size*.20,y+size*.70),(x+size*.34,y+size*.82),
                    (x+size*.53,y+size*.85),(x+size*.96,y+size*.85)]
            draw.line(points,fill=color,width=max(1,round(s*1.2)),joint='curve')
        elif kind=='todo-mark':
            size,color,done=value; size*=s
            if done:
                draw.line(((x+size*.12,y+size*.50),(x+size*.40,y+size*.76),(x+size*.90,y+size*.18)),
                          fill=color,width=max(2,round(2.3*s)),joint='curve')
            else:
                draw.ellipse((x+size*.32,y+size*.32,x+size*.68,y+size*.68),fill=color)
        elif kind=='geo-map':
            width,height,accent,dark=value; width*=s; height*=s
            background='#384950' if dark else '#dce8e7'
            road='#7b898a' if dark else '#ffffff'
            water='#44677e' if dark else '#a9d8e9'
            draw.rounded_rectangle((x,y,x+width,y+height),radius=10*s,fill=background)
            draw.polygon([(x,y+height*.22),(x+width*.25,y),(x+width*.42,y),
                          (x+width*.13,y+height*.59),(x,y+height*.68)],fill=water)
            roads=[((.05,.82),(.95,.27)),((.29,.02),(.69,.98)),((.70,.06),(.95,.89))]
            for (ax,ay),(bx,by) in roads:
                draw.line((x+width*ax,y+height*ay,x+width*bx,y+height*by),
                          fill=road,width=max(2,round(5*s)))
            cx=x+width*.51; cy=y+height*.43; r=13*s
            draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=accent)
            draw.polygon([(cx-r*.70,cy+r*.55),(cx+r*.70,cy+r*.55),(cx,cy+r*1.85)],fill=accent)
            draw.ellipse((cx-r*.35,cy-r*.35,cx+r*.35,cy+r*.35),fill='#ffffff')
        elif kind=='giveaway-art':
            size=value[0]*s
            def poly(points,color):
                draw.polygon([(x+px*size,y+py*size) for px,py in points],fill=color)
            draw.ellipse((x+size*.07,y+size*.08,x+size*.93,y+size*.94),fill='#3b6128')
            draw.rounded_rectangle((x+size*.18,y+size*.39,x+size*.82,y+size*.87),radius=size*.08,fill='#47be28')
            draw.rounded_rectangle((x+size*.13,y+size*.35,x+size*.87,y+size*.47),radius=size*.04,fill='#78de2d')
            draw.rectangle((x+size*.44,y+size*.40,x+size*.56,y+size*.87),fill='#ffe332')
            poly(((.18,.59),(.82,.59),(.82,.67),(.18,.67)),'#ffdd24')
            poly(((.29,.34),(.42,.14),(.50,.38)),'#f9bc0b')
            poly(((.71,.34),(.58,.14),(.50,.38)),'#ffdc21')
            points=[]
            for i in range(10):
                angle=-math.pi/2+i*math.pi/5; radius=.23 if i%2==0 else .105
                points.append((x+(.50+math.cos(angle)*radius)*size,y+(.27+math.sin(angle)*radius)*size))
            draw.polygon(points,fill='#ffe647')
            draw.line(points+[points[0]],fill='#f2a900',width=max(1,round(size*.025)))
            for cx,cy,color in ((.19,.27,'#fb6080'),(.83,.28,'#a873ff'),(.13,.68,'#42d5ff'),(.87,.72,'#ffe647')):
                draw.ellipse((x+(cx-.025)*size,y+(cy-.025)*size,x+(cx+.025)*size,y+(cy+.025)*size),fill=color)
        elif kind=='text':
            text,style=value; font=self.font(style)
            anchor=style.get('text_anchor','lt')
            kwargs={'font':font,'fill':style['color'],'anchor':anchor}
            if self.raqm and self.rtl(text): kwargs['direction']='rtl'
            extent=round(self.measure(text,style)*s); height=round(style.get('size',16)*s)
            top=y-font.getmetrics()[0] if anchor=='ls' else y
            if style.get('background'): draw.rectangle((x,top,x+extent,top+height+2),fill=style['background'])
            if style.get('gradient') and extent>0:
                left,upper,right,lower=font.getbbox(text,anchor=anchor)
                mask=Image.new('L',(max(1,right-left),max(1,lower-upper)))
                ImageDraw.Draw(mask).text((-left,-upper),text,font=font,fill=255,anchor=anchor)
                fill=self.gradient(mask.size,style['gradient']); fill.putalpha(mask); canvas.alpha_composite(fill,(x+left,y+upper))
            else: draw.text((x,y),text,**kwargs)
            underline=y+2*s if anchor=='ls' else y+height+1
            strike=y-height*.35 if anchor=='ls' else y+height*.55
            if style.get('underline'): draw.line((x,underline,x+extent,underline),fill=style['color'],width=s)
            if style.get('strike'): draw.line((x,strike,x+extent,strike),fill=style['color'],width=s)
        elif kind in ('rect','border'):
            w,h,color,radius=value
            if kind=='border': draw.rectangle((x,y,x+round(w*s),y+round(h*s)),outline=color,width=max(1,s))
            else: draw.rounded_rectangle((x,y,x+round(w*s),y+round(h*s)),radius=round(radius*s),fill=color)
        elif kind=='quote-bar':
            w,h,colors=value; w=max(1,round(w*s)); h=max(1,round(h*s))
            start=max(0,-y); end=min(h,canvas.height-y)
            if end<=start: return
            strip=Image.new('RGBA',(w,end-start)); pixels=[]
            palette=[ImageColor.getrgb(c)+(255,) for c in colors]
            for py in range(start,end):
                for px in range(w):
                    color=palette[((py+px)//(6*s))%len(palette)]
                    radius=min(6*s,h/2)
                    cy=radius if py<radius else h-radius if py>=h-radius else py
                    if px<radius and (px-radius)**2+(py-cy)**2>radius**2:
                        color=(0,0,0,0)
                    pixels.append(color)
            strip.putdata(pixels)
            canvas.alpha_composite(strip,(x,y+start))
        elif kind=='image':
            image,w,h,rounded=value
            target=(max(1,round(w*s)),max(1,round(h*s)))
            image=ImageOps.fit(image.resize(image.size),target,Image.Resampling.LANCZOS) if rounded=='thumb' else image.resize(target,Image.Resampling.LANCZOS)
            if rounded:
                mask=Image.new('L',image.size)
                if rounded=='thumb': ImageDraw.Draw(mask).rounded_rectangle((0,0,image.width-1,image.height-1),radius=5*s,fill=255)
                else: ImageDraw.Draw(mask).ellipse((0,0,image.width-1,image.height-1),fill=255)
                from PIL import ImageChops
                image.putalpha(ImageChops.multiply(image.getchannel('A'),mask))
            canvas.alpha_composite(image,(x,y))
        elif kind=='gradient':
            w,h,colors,radial=value
            if w*h*s*s>24_000_000: raise ValueError('gradient_pixels_limit')
            fill=self.gradient((max(1,round(w*s)),max(1,round(h*s))),colors,radial)
            mask=Image.new('L',fill.size)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,fill.width-1,fill.height-1),radius=12*s,fill=255)
            fill.putalpha(mask)
            canvas.alpha_composite(fill,(x,y))
        elif kind=='reply-pattern':
            w,h,asset,color=value
            layer=Image.new('RGBA',(max(1,round(w*s)),max(1,round(h*s))))
            for row,py in enumerate(range(-4,round(h),22)):
                for column,px in enumerate(range(8+(row%2)*17,round(w),35)):
                    size=(10,14,9)[(row+column)%3]*s
                    icon=asset.resize((size,size),Image.Resampling.LANCZOS)
                    tint=Image.new('RGBA',icon.size,color)
                    tint.putalpha(icon.getchannel('A').point(lambda a:round(a*.22)))
                    tint=tint.rotate((-15,12)[(row+column)%2],resample=Image.Resampling.BICUBIC,expand=True)
                    layer.alpha_composite(tint,(px*s,py*s))
            mask=Image.new('L',layer.size)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,layer.width-1,layer.height-1),radius=7*s,fill=255)
            from PIL import ImageChops
            layer.putalpha(ImageChops.multiply(layer.getchannel('A'),mask))
            canvas.alpha_composite(layer,(x,y))
        elif kind=='pattern':
            w,h,asset,color=value
            tile=asset.resize((32*s,32*s),Image.Resampling.LANCZOS)
            tint=Image.new('RGBA',tile.size,color); tint.putalpha(tile.getchannel('A').point(lambda a:round(a*.15)))
            for py in range(max(0,-y)//(64*s)*(64*s),round(h*s)-32*s,64*s):
                if y+py>canvas.height: break
                for px in range(8*s,round(w*s)-32*s,64*s): canvas.alpha_composite(tint,(x+px,y+py+8*s))
    def render(self,markup):
        layout,breaks=self.layout(markup)
        maxheight=min(4000,24_000_000//(self.width*self.scale**2))
        maxpages=24
        if layout.h>maxheight*maxpages: raise ValueError('output_pages_limit')
        paths=[]; offset=0; total=0
        while offset<layout.h:
            if len(paths)>=maxpages: raise ValueError('output_pages_limit')
            end=min(offset+maxheight,math.ceil(layout.h))
            if end<layout.h:
                candidates=[b for b in breaks if offset+maxheight/2<b<=end]
                if candidates: end=math.ceil(max(candidates))
            self.checkpoint('paint_page')
            output_scale=self.scale
            output_size=(self.width*output_scale,round((end-offset)*output_scale))
            aa=2 if output_size[0]*output_size[1]<=2_000_000 else 1
            name=f'page-{len(paths)+1}.png'; path=Path(self.p['output'])/name
            while True:
                canvas=None
                try:
                    canvas=Image.new('RGBA',(output_size[0]*aa,output_size[1]*aa),self.bg if self.options['background'] else (0,0,0,0))
                    wallpaper=self.p.get('wallpaper')
                    if wallpaper:
                        from PIL import ImageOps
                        with Image.open(wallpaper) as source:
                            with ImageOps.fit(source.convert('RGBA'),canvas.size,method=Image.Resampling.LANCZOS) as fitted:
                                canvas.alpha_composite(fitted)
                    self.scale=output_scale*aa
                    for op in layout.ops:
                        if op[2]>end: continue
                        self.paint(canvas,op,offset)
                    if self.options['background']:
                        opaque=canvas.convert('RGB'); canvas.close(); canvas=opaque
                    if aa>1:
                        reduced=canvas.resize(output_size,Image.Resampling.LANCZOS)
                        canvas.close(); canvas=reduced
                    canvas.save(path,format='PNG')
                    break
                except MemoryError:
                    if aa==1: raise
                    if canvas is not None: canvas.close(); canvas=None
                    self.fonts.clear(); self.glyphs.clear()
                    import gc
                    gc.collect()
                    self.warn('antialias_memory_fallback')
                    aa=1
                finally:
                    self.scale=output_scale
                    if canvas is not None: canvas.close()
            total+=path.stat().st_size
            if total>64*1024*1024: raise ValueError('output_bytes_limit')
            paths.append(name); offset=end
        return paths

class Composition:
    @staticmethod
    def column(items,width,gap=0):
        result=Box(width)
        for item in items:
            if item.h<=0: continue
            if result.h: result.h+=gap
            result.add(item,0,result.h); result.h+=item.h
        return result
    @staticmethod
    def aligned(items,gap=0):
        items=[b for b in items if b.h>0]
        baseline=max([getattr(b,'baseline',b.h*.75) for b in items]+[0])
        result=Box(sum(b.w for b in items)+gap*max(0,len(items)-1))
        x=0
        for item in items:
            y=baseline-getattr(item,'baseline',item.h*.75)
            result.add(item,x,y); result.h=max(result.h,y+item.h); x+=item.w+gap
        result.baseline=baseline
        return result

class BalancedPainter(Painter):
    SP=dict(outer=18,inner_x=12,inner_y=8,section=3,avatar=36,avatar_gap=8,
            message=9,group=3,radius=12,quote_x=10,quote_y=5)
    def __init__(self,payload):
        super().__init__(payload)
        self.classic=False
        if self.options.get('sticker'):
            self.SP=dict(self.SP,outer=10,inner_x=10,inner_y=5,section=2,
                         avatar=30,avatar_gap=5,message=4,group=2)

    def inline(self,nodes,width,style,align='left',max_lines=None):
        if self.classic: return super().inline(nodes,width,style,align)
        width=max(1,width)
        groups=[]; word=[]
        def finish():
            if word: groups.append(list(word)); word.clear()
        for kind,value,st in self.atoms(nodes,style):
            if kind=='newline': finish(); groups.append(None)
            elif kind=='text':
                for part in regex.findall(r'[^\S\n]+|\n|[^\s]+',value):
                    if part=='\n': finish(); groups.append(None)
                    elif part.isspace(): finish(); groups.append([('text',part,st)])
                    else: word.append(('text',part,st))
            else: word.append((kind,value,st))
        finish()
        lines=[]; current=[]; used=0
        def line_end():
            nonlocal current,used
            lines.append((current,used)); current=[]; used=0
        def place(atom):
            nonlocal used
            k,v,st=atom; extent=self.atom_width(k,v,st)
            if current and used+extent>width: line_end()
            current.append((k,v,st,extent)); used+=extent
        for group in groups:
            if group is None: line_end(); continue
            extent=sum(self.atom_width(*a) for a in group)
            whitespace=len(group)==1 and group[0][0]=='text' and group[0][1].isspace()
            if current and used+extent>width:
                line_end()
                if whitespace: continue
            if extent<=width:
                for k,v,st in group:
                    w=self.atom_width(k,v,st); current.append((k,v,st,w)); used+=w
            else:
                for k,v,st in group:
                    if k=='text':
                        for cluster in regex.findall(r'\X',v): place((k,cluster,st))
                    else: place((k,v,st))
        if current: line_end()
        if not lines: return Box(width)
        if max_lines and len(lines)>max_lines:
            lines=lines[:max_lines]
            row,used=lines[-1]
            row=list(row)
            ellipsis_width=self.atom_width('text','…',style)
            while row:
                kind,value,atom_style,extent=row[-1]
                if not (kind=='text' and value.isspace()) and used+ellipsis_width<=width:
                    break
                if kind=='text':
                    fragments=regex.findall(r'\X',value)
                    shorter=''.join(fragments[:-1])
                    if shorter:
                        new_extent=self.atom_width(kind,shorter,atom_style)
                        row[-1]=(kind,shorter,atom_style,new_extent)
                        used+=new_extent-extent
                        continue
                row.pop(); used-=extent
            row.append(('text','…',style,ellipsis_width))
            lines[-1]=(row,used+ellipsis_width)
        base=self.font(style).getmetrics()
        asc,desc=base[0]/self.scale,base[1]/self.scale
        body_line=style.get('line_spacing') is not None
        base_asc,base_desc=asc,desc
        for row,_ in lines:
            for k,v,st,w in row:
                if k in ('text','badge'):
                    a,d=self.font(st).getmetrics()
                    if body_line:
                        asc=max(asc,min(a/self.scale,base_asc+2))
                        desc=max(desc,min(d/self.scale,base_desc+2))
                    else:
                        asc=max(asc,a/self.scale); desc=max(desc,d/self.scale)
        line_step=max(style.get('size',16)*style.get('line_spacing',1.22),asc+desc-3)
        if body_line:
            line_step=min(line_step,style.get('size',16)*1.2)
        result=Box(width); result.baseline=asc
        baseline=asc
        for row,used in lines:
            visual=max([st.get('image_size',0) for k,v,st,w in row if k=='image']+[0])
            height=max(asc+desc,visual)
            text=''.join(v for k,v,st,w in row if k=='text')
            rtl=self.rtl(text)
            if rtl: self.warn('mixed_rtl_styles_approximate')
            x=max(0,(width-used)/2) if align=='center' else max(0,width-used) if align=='right' or rtl else 0
            runs=[]
            for k,v,st,w in reversed(row) if rtl else row:
                if not rtl and k=='text' and runs and runs[-1][0]=='text' and runs[-1][2]==st:
                    old=runs[-1]; runs[-1]=(k,old[1]+v,st,old[3]+w)
                else: runs.append((k,v,st,w))
            for k,v,st,w in runs:
                y=baseline+st.get('shift',0)
                if st.get('hidden'):
                    result.ops.append(('rect',x,y-asc,(w,asc+desc,self.muted,3)))
                elif k=='text': result.ops.append(('text',x,y,(v,dict(st,text_anchor='ls'))))
                elif k=='image': result.ops.append(('image',x,y-asc+(height-w)/2,(v,w,w,False)))
                elif k=='badge':
                    result.ops.append(('rect',x,y-st['size'],(w,st['size']+5,self.code,6)))
                    result.ops.append(('text',x+7,y,(v,dict(st,text_anchor='ls'))))
                else: result.ops.append((k,x,y-st.get('size',16),(w,st['color'])))
                x+=w
            result.h=baseline+desc
            baseline+=max(line_step,min(visual,style.get('size',16)*1.2) if body_line else visual)
        return result

    def label(self,nodes,width,style):
        width=max(1,width)
        if self.inline_width(nodes,style)<=width and '\n' not in ''.join(n if isinstance(n,str) else n.text() for n in nodes):
            return self.inline(nodes,width,style)
        atoms=self.atoms(nodes,style); chosen=[]; used=0
        ew=self.measure('…',style)
        for kind,value,st in atoms:
            if kind=='newline': break
            fragments=regex.findall(r'\X',value) if kind=='text' else [value]
            stopped=False
            for fragment in fragments:
                extent=self.atom_width(kind,fragment,st)
                if used+extent+ew>width: stopped=True; break
                chosen.append((kind,fragment,st)); used+=extent
            if stopped: break
        original=self.atoms
        try:
            self.atoms=lambda *_: chosen+[('text','…',style)]
            return self.inline([],width,style)
        finally: self.atoms=original

    def header(self,node,width,style):
        title_style=dict(style,size=13,bold=True,color=style['accent'])
        rank=next((c for c in node.children if isinstance(c,Node) and c.has('rank')),None)
        via=next((c for c in node.children if isinstance(c,Node) and c.has('via-inline')),None)
        names=[c for c in node.children if c is not rank and c is not via]
        names=[c for c in names if not isinstance(c,str) or c.strip()]
        badge=None; reserve=0
        if rank:
            role=rank.a.get('data-role','user')
            color={'owner':'#956ac8','admin':'#49a355'}.get(role,'#999999')
            rs=dict(style,size=9,bold=True,color=color)
            rw=min(max(35,width-48),max(35,self.inline_width(rank.children,rs)+14))
            text=self.label(rank.children,max(1,rw-14),rs)
            badge=Box(rw,text.h+4)
            if role in ('owner','admin'):
                badge.ops.append(('rect',0,0,(rw,text.h+4,self.tint(style.get('bubble_color',self.bubble),color,.15),7)))
            badge.add(text,7,2)
            reserve=rw+8
        available=max(1,width-reserve)
        name_width=min(available,self.inline_width(names,title_style))
        title=self.label(names,max(1,name_width),title_style)
        if via:
            vs=dict(style,size=12,bold=False,color=style['accent'])
            vw=self.inline_width(via.children,vs)
            if title.w+vw+5<=available:
                title=Composition.aligned([title,self.inline(via.children,vw,vs)],5)
            else:
                title=Composition.column([title,self.label(via.children,available,vs)],available,1)
        result=Box(width,max(title.h,badge.h if badge else 0)); result.add(title)
        if badge: result.add(badge,width-badge.w,0)
        return result

    def reply_card(self,node,width,style):
        if self.classic: return super().reply_card(node,width,style)
        style=dict(style,size=13,bold=False)
        colors=re.findall(r'#[0-9a-fA-F]{6}',node.a.get('style',''))
        if colors: style['accent']=colors[0]
        thumb=next((c for c in node.children if isinstance(c,Node) and c.has('reply-thumb')),None)
        content=next((c for c in node.children if isinstance(c,Node) and c.has('reply-content')),node)
        author=next((c for c in content.children if isinstance(c,Node) and c.has('reply-author')),None)
        snippet=next((c for c in content.children if isinstance(c,Node) and c.has('reply-text')),None)
        sticker=node.a.get('data-reply-sticker')=='1'
        if sticker: style['size']=16
        thumb_size=48 if sticker else 36
        image=self.asset(thumb,thumb_size,style['accent']) if thumb else None
        gift=self.reply_gift(node)
        left=self.SP['quote_x']+(thumb_size+6 if image else 0)
        inner=max(1,width-left-8-(24 if gift and not sticker else 0))
        parts=[]
        author_width=max(1,inner-(24 if gift and sticker else 0))
        if author: parts.append(self.label(author.children,author_width,dict(style,color=style['accent'],bold=sticker)))
        if snippet: parts.append(self.label(self.reply_preview_nodes(snippet.children),inner,style))
        compact=[]
        for part in parts:
            trim=max(0,part.h-17)
            line=Box(part.w,part.h-trim); line.add(part,0,-trim/2)
            compact.append(line)
        text=Composition.column(compact,inner,0)
        height=max(text.h,thumb_size if image else 0)+8
        result=Box(width,height,[('rect',0,0,(width,height,self.tint(style.get('bubble_color',self.bubble),style['accent'],.14),6))])
        for child in node.children:
            if not isinstance(child,Node) or not child.has('pattern-overlay'): continue
            source=next((c for c in child.children if isinstance(c,Node)),None)
            if source:
                asset=self.asset(source,30,style['accent'])
                if asset:
                    pw=min(160,width*.70)
                    result.ops.append(('reply-pattern',width-pw,0,(pw,height,asset,style['accent'])))
        result.ops.append(('quote-bar',0,0,(3,height,self.quote_colors(node,dict(style,quote_colors=None)))))
        if image:
            if sticker:
                ratio=min(thumb_size/image.width,thumb_size/image.height)
                iw,ih=image.width*ratio,image.height*ratio
                result.ops.append(('image',10+(thumb_size-iw)/2,(height-ih)/2,(image,iw,ih,False)))
            else: result.ops.append(('image',10,(height-thumb_size)/2,(image,thumb_size,thumb_size,'thumb')))
        result.add(text,left,(height-text.h)/2)
        if gift: result.ops.append(('image',width-26,5,(gift,20,20,False)))
        return result

    def block(self,node,width,style):
        if self.classic: return super().block(node,width,style)
        if node.has('author'): return self.header(node,width,style)
        if node.has('reply'): return self.reply_card(node,width,style)
        if node.has('forward'):
            return self.inline(node.children,width,dict(style,size=14,color=style['accent']))
        if node.has('meta'):
            return self.inline(node.children,width,dict(style,size=11,color=self.muted),align='right')
        if node.has('attachment'):
            icon=next((c for c in node.children if isinstance(c,Node) and c.has('disc')),None)
            content=next((c for c in node.children if isinstance(c,Node) and c is not icon),None)
            if not content: return Box(width)
            parts=[]
            for child in content.children:
                if not isinstance(child,Node): continue
                if child.has('attachment-title'):
                    parts.append(self.label(child.children,max(1,width-54),dict(style,size=15,bold=True)))
                elif child.has('attachment-subtitle'):
                    parts.append(self.label(child.children,max(1,width-54),dict(style,size=13,color=self.muted)))
                else: parts.append(self.block(child,max(1,width-54),style))
            text=Composition.column(parts,max(1,width-54),2)
            height=max(42,text.h)
            result=Box(width,height,[('rect',0,(height-42)/2,(42,42,style['accent'],21))])
            if icon and icon.has('document-icon'):
                result.ops.append(('file-icon',10,(height-24)/2,(24,style.get('bubble_color',self.bubble),style['accent'])))
            elif icon:
                pict=self.inline(icon.children,42,dict(style,size=22),align='center'); result.add(pict,0,(height-pict.h)/2)
            result.add(text,54,(height-text.h)/2)
            return result
        if node.has('buttons'):
            items=[c for c in node.children if isinstance(c,Node)]
            if not items: return Box(width)
            rich=node.has('rich-buttons')
            gap=4; cell=max(1,(width-gap*(len(items)-1))/len(items)); rendered=[]
            for child in items:
                if rich:
                    color,foreground={'primary':('#334754','#72bdff'),'danger':('#51414b','#ff727e'),'success':('#3a5146','#73e483')}.get(child.a.get('data-button-style'),('#303d46','#ffffff'))
                else:
                    color={'primary':'#3567a0','danger':'#a84545','success':'#327a50'}.get(child.a.get('data-button-style'),self.code)
                    foreground='#ffffff' if color!=self.code else self.fg
                label=self.label(child.children,max(1,cell-12),dict(style,size=13,color=foreground))
                rendered.append((label,color))
            height=max(b.h for b,c in rendered)+8
            top=5 if rich else 0
            result=Box(width,height+2*top)
            for i,(label,color) in enumerate(rendered):
                x=i*(cell+gap); result.ops.append(('rect',x,top,(cell,height,color,8 if rich else 6)))
                actual=min(cell-12,self.inline_width(items[i].children,dict(style,size=13)))
                result.add(label,x+max(6,(cell-actual)/2),top+(height-label.h)/2)
            return result
        if node.tag in ('blockquote','details'):
            if node.tag=='details' and 'open' not in node.a:
                summary=next((c for c in node.children if isinstance(c,Node) and c.tag=='summary'),None)
                text=self.inline(summary.children,max(1,width-20),style,max_lines=2) if summary else Box(width)
            else:
                text=self.flow(node.children,max(1,width-20),style)
            if not text.h: return Box(width)
            result=Box(width,text.h+10,[('rect',0,0,(width,text.h+10,self.tint(style.get('bubble_color',self.bubble),style.get('quote_accent',style['accent']),.14),6)),
                                      ('quote-bar',0,0,(3,text.h+10,self.quote_colors(node,style)))])
            result.add(text,10,5); return result
        if node.has('body'):
            return self.flow(node.children,width,dict(style,line_spacing=1.15))
        if node.has('rich') or node.tag=='p':
            return self.flow(node.children,width,style)
        return super().block(node,width,style)

    def natural_width(self,node,style,limit):
        if self.classic: return super().natural_width(node,style,limit)
        if (isinstance(node,Node) and node.tag=='details' and 'open' not in node.a
                and self.options.get('sticker')):
            return min(280,super().natural_width(node,style,limit))
        if isinstance(node,Node) and node.has('media') and node.tag in ('img','video'):
            box=self.block(node,limit,style)
            images=[op[3][1] for op in box.ops if op[0]=='image']
            if images: return min(limit,max(images))
        if isinstance(node,Node) and node.has('author'):
            rank=next((c for c in node.children if isinstance(c,Node) and c.has('rank')),None)
            via=next((c for c in node.children if isinstance(c,Node) and c.has('via-inline')),None)
            names=[c for c in node.children if c is not rank and c is not via]
            w=self.inline_width(names,dict(style,size=13,bold=True))
            if via: w+=5+self.inline_width(via.children,dict(style,size=12))
            if rank: w+=22+self.inline_width(rank.children,dict(style,size=9,bold=True))
            return min(limit,w)
        if isinstance(node,Node) and node.has('attachment'):
            content=next((c for c in node.children if isinstance(c,Node) and not c.has('disc')),None)
            return 54+max([self.inline_width(c.children,dict(style,size=15 if c.has('attachment-title') else 13,bold=c.has('attachment-title'))) for c in content.children if isinstance(c,Node)]+[0]) if content else 54
        return super().natural_width(node,style,limit)

    def bubble_body(self,children,width,style):
        if self.classic: return super().bubble_body(children,width,style)
        parts=[]; previous=None
        for child in children:
            b=self.block(child,width,style) if isinstance(child,Node) else self.inline([child],width,style)
            if not b.h: continue
            gap=self.SP['section'] if parts else 0
            if previous and previous.has('attachment') and isinstance(child,Node) and child.has('body'): gap=6
            elif previous and previous.has('author') and isinstance(child,Node) and child.has('body'): gap=0
            parts.append((b,gap,child)); previous=child if isinstance(child,Node) else None
        if len(parts)>=2:
            body,gap,node=parts[-2]; footer,fgap,meta=parts[-1]
            if isinstance(node,Node) and node.has('reactions') and isinstance(meta,Node) and meta.has('meta'):
                rects=[op for op in body.ops if op[0]=='rect']
                if rects:
                    last_y=max(op[2] for op in rects)
                    last_row=[op for op in rects if op[2]==last_y]
                    right=max(op[1]+op[3][0] for op in last_row)
                    row_height=max(op[3][1] for op in last_row)
                    fs=dict(style,size=11,color=self.muted)
                    mw=self.inline_width(meta.children,fs)
                    if mw and right+8+mw<=width:
                        time=self.inline(meta.children,mw,fs)
                        dy=max(0,last_y+(row_height-time.h)/2)
                        line=Box(width,max(body.h,dy+time.h))
                        line.add(body); line.add(time,width-mw,dy)
                        parts[-2:]=[(line,gap,node)]
            elif isinstance(node,Node) and node.has('body') and isinstance(meta,Node) and meta.has('meta'):
                simple=not any(isinstance(c,Node) and c.tag in self.BLOCKS for c in node.children)
                text_ops=[op for op in body.ops if op[0]=='text']
                fs=dict(style,size=11,color=self.muted)
                mw=self.inline_width(meta.children,fs)
                if simple and text_ops and len(text_ops)==len(body.ops) and len({op[2] for op in text_ops})==1:
                    bw=max(op[1]+self.measure(op[3][0],op[3][1]) for op in text_ops)
                    if bw+mw+12<=width:
                        time=self.inline(meta.children,mw,fs)
                        dy=text_ops[0][2]-time.baseline
                        line=Box(width,max(body.h,dy+time.h))
                        line.add(body); line.add(time,width-mw,dy)
                        parts[-2:]=[(line,gap,node)]
        result=Box(width)
        for b,gap,node in parts:
            result.h+=gap; result.add(b,0,result.h); result.h+=b.h
        return result

    def layout(self,markup):
        if not self.options.get('sticker'):
            return self.compose_page(markup)
        canvas_width=self.options['width']
        best=None
        for cap in dict.fromkeys(min(canvas_width,value) for value in (400,480,560,640,canvas_width)):
            self.width=canvas_width
            self._sticker_bubble_cap=cap
            page,breaks=self.compose_page(markup)
            size=max(page.w,page.h)
            if best is None or size<best[0]:
                best=(size,page,breaks)
            if page.h<=page.w:
                break
        self.width=best[1].w
        return best[1],best[2]

    def compose_page(self,markup):
        tree=Tree(markup)
        def find(n):
            if n.a.get('id')=='quote': return n
            for c in n.children:
                if isinstance(c,Node):
                    found=find(c)
                    if found: return found
        quote=find(tree.root)
        if quote is None: raise ValueError('quote_root_missing')
        nodes=[n for n in quote.children if isinstance(n,Node)]
        outer=self.SP['outer']; gutter=self.SP['avatar']+self.SP['avatar_gap']
        measurements=[]
        for n in nodes:
            if n.has('service-row'):
                style=dict(size=14,color=self.fg,accent=self.muted)
                avail=self.width-2*outer
                width=min(avail,max(112,self.natural_width(n,style,avail-24)+24))
                measurements.append((n,style,n.children,None,width))
                continue
            if not n.has('row'): continue
            style,children,avatar=self.row_parts(n)
            avail=self.width-2*outer-(gutter if avatar else 0)
            bodies=[c for c in children if isinstance(c,Node) and c.has('body')]
            def plain(node):
                return all(not isinstance(c,Node) or (c.tag not in self.BLOCKS and plain(c)) for c in node.children)
            simple=bool(bodies) and all(plain(c) for c in bodies) and all(
                isinstance(c,Node) and any(c.has(k) for k in ('author','body','reply','meta','forward','reactions')) for c in children)
            avail=min(avail,self._sticker_bubble_cap if self.options.get('sticker')
                      else 384 if simple else 480)
            minimum=196 if any(isinstance(c,Node) and c.has('reply') and c.a.get('data-reply-sticker')=='1' for c in children) else 112
            width=min(avail,max(minimum,max([self.natural_width(c,style,avail-24) for c in children]+[0])+24))
            if len(children)>=2 and isinstance(children[-2],Node) and children[-2].has('body') and isinstance(children[-1],Node) and children[-1].has('meta'):
                body,meta=children[-2:]
                if plain(body):
                    atoms=self.atoms(body.children,style)
                    if atoms and all(kind!='newline' for kind,_,_ in atoms):
                        text_width=self.inline_width(body.children,style)
                        time_width=self.inline_width(meta.children,dict(style,size=11,color=self.muted))
                        inline_width=text_width+time_width+12+2*self.SP['inner_x']
                        if inline_width<=avail:
                            width=max(width,inline_width)
            measurements.append((n,style,children,avatar,width))
        if self.options.get('compact',True):
            self.width=min(self.width,math.ceil(max([w+2*outer+(gutter if a else 0) for n,s,c,a,w in measurements]+[160])))
        prepared={id(n):(s,c,a,w) for n,s,c,a,w in measurements}
        page=Box(self.width,outer); breaks=[]
        for i,node in enumerate(nodes):
            if node.has('day'):
                b=super().block(node,self.width-2*outer,dict(size=12,color=self.muted,accent=self.muted))
                page.add(b,outer,page.h); page.h+=b.h+6; continue
            if node.has('service-row'):
                self.message_id=node.a.get('data-message'); self.checkpoint('layout_message')
                style,children,avatar,width=prepared[id(node)]
                b=self.flow(children,width-24,style)
                height=b.h+10; x=(self.width-width)/2
                page.ops.append(('rect',x,page.h,(width,height,self.code,min(18,height/2))))
                page.add(b,x+12,page.h+5)
                page.h+=height+self.SP['message']; breaks.append(page.h)
                continue
            if not node.has('row'): continue
            self.message_id=node.a.get('data-message'); self.checkpoint('layout_message')
            style,children,avatar,width=prepared[id(node)]
            continuation=node.has('grouped')
            next_node=nodes[i+1] if i+1<len(nodes) else None
            continued=bool(next_node and next_node.has('row') and next_node.has('grouped') and next_node.has('outgoing')==node.has('outgoing'))
            content=self.bubble_body(children,width-2*self.SP['inner_x'],style)
            height=max(content.h+2*self.SP['inner_y'],self.SP['avatar'] if avatar and not continued else 0)
            outgoing=node.has('outgoing'); color=style['bubble_color']
            x=self.width-outer-(gutter if avatar else 0)-width if outgoing else outer+(gutter if avatar else 0)
            page.ops.append(('bubble-shape',x,page.h,(width,height,color,outgoing,not continued,continuation,continued)))
            page.add(content,x+self.SP['inner_x'],page.h+self.SP['inner_y'])
            if avatar and not continued:
                ax=self.width-outer-self.SP['avatar'] if outgoing else outer
                ay=page.h+height-self.SP['avatar']; size=self.SP['avatar']
                if avatar.has('avatar'):
                    asset=self.asset(avatar,size,style['accent'])
                    if asset: page.ops.append(('image',ax,ay,(asset,size,size,True)))
                else:
                    page.ops.append(('rect',ax,ay,(size,size,style['accent'],size/2)))
                    label=self.inline(avatar.children,size,dict(style,bold=True,color='#ffffff'),align='center')
                    page.add(label,ax,ay+(size-label.h)/2)
            page.h+=height+(self.SP['group'] if continued else self.SP['message']); breaks.append(page.h)
        page.h+=outer-self.SP['message']
        return page,breaks

    def paint(self,canvas,op,offset):
        if op[0]!='bubble-shape': return super().paint(canvas,op,offset)
        _,x,y,value=op; w,h,color,outgoing,tail,joined_above,joined_below=value
        r=min(self.SP['radius'],w/2,h/2); top=4 if joined_above else r; bottom=4 if joined_below else r
        points=[]
        def arc(cx,cy,rr,a,b):
            for i in range(9):
                angle=math.radians(a+(b-a)*i/8); points.append((cx+rr*math.cos(angle),cy+rr*math.sin(angle)))
        arc(r,r,r,180,270); arc(w-top,top,top,270,360)
        if tail:
            points.append((w,h-r))
            for i in range(1,13):
                t=i/12; points.append((w+7*t*t,h-r*(1-t)**2))
        else: arc(w-bottom,h-bottom,bottom,0,90)
        arc(r,h-r,r,90,180)
        if not outgoing: points=[(w-px,py) for px,py in points]
        s=self.scale
        outline=[(round((x+px)*s),round((y-offset+py)*s)) for px,py in points]
        transparency=self.options.get('bubble_transparency',0)
        if transparency>=100:
            return
        stroke=self.tint(color,'#ffffff' if self.dark else '#19232b',.12 if self.dark else .09)
        width=max(1,round(.5*s))
        if transparency==0:
            draw=ImageDraw.Draw(canvas)
            draw.polygon(outline,fill=color)
            if self.options.get('bubble_outline',True):
                draw.line(outline+[outline[0]],fill=stroke,width=width,joint='curve')
            return
        pad=width+1
        left=max(0,min(px for px,py in outline)-pad)
        top=max(0,min(py for px,py in outline)-pad)
        right=min(canvas.width,max(px for px,py in outline)+pad+1)
        bottom=min(canvas.height,max(py for px,py in outline)+pad+1)
        if right<=left or bottom<=top:
            return
        with Image.new('RGBA',(right-left,bottom-top),(0,0,0,0)) as layer:
            points=[(px-left,py-top) for px,py in outline]
            draw=ImageDraw.Draw(layer)
            draw.polygon(points,fill=color)
            if self.options.get('bubble_outline',True):
                draw.line(points+[points[0]],fill=stroke,width=width,joint='curve')
            layer.putalpha(layer.getchannel('A').point(lambda alpha:round(alpha*(100-transparency)/100)))
            canvas.alpha_composite(layer,(left,top))

def main():
    payload=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    painter=None
    try:
        painter=BalancedPainter(payload)
        paths=painter.render(payload['html'])
        result=dict(pages=paths,warnings=painter.warnings)
    except Exception as error:
        safe_codes={'markup_limit','nonlocal_asset','asset_outside_cache','text_font_missing',
                    'decoded_image_limit','decoded_cache_limit','tgs_external_asset',
                    'empty_animation_frame','ffmpeg_missing','video_decode_failed',
                    'image_pixels_limit','quote_root_missing','output_pages_limit',
                    'output_bytes_limit','table_columns_limit','gradient_pixels_limit'}
        code=str(error) if isinstance(error,ValueError) and str(error) in safe_codes else type(error).__name__
        if isinstance(error,OSError) and error.errno==28: code='storage_full'
        result=dict(error=code,stage=painter.stage if painter else 'worker_start',
                    message=painter.message_id if painter else None,document=painter.document_id if painter else None,
                    trace=[f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(error.__traceback__)])
    Path(payload['response']).write_text(json.dumps(result),encoding='utf8')
if __name__=='__main__': main()
'''


class _GQuoteRenderer:

    DEFAULTS = dict(theme="dark", background=False, background_mode="transparent", background_url="", dates=True, tags=True,
                     avatars=True, reactions=True, spoilers=True, expanded=False,
                     width=720, scale=2, compact=True, gift_colors=True, bubble_outline=True,
                     bubble_transparency=0, link_preview_position='bottom',
                     composition="balanced", send_format="sticker")
    SCRIPT_FONTS = {('tailue' if name == 'NewTaiLue' else name.lower()): name for name in (
        'Adlam AnatolianHieroglyphs Arabic Armenian Avestan Balinese Bamum BassaVah Batak Bengali '
        'Bhaiksuki Brahmi Buginese Buhid CanadianAboriginal Carian CaucasianAlbanian Chakma Cham '
        'Cherokee Chorasmian Coptic Cuneiform Cypriot CyproMinoan Deseret Devanagari Duployan '
        'EgyptianHieroglyphs Elbasan Elymaic Ethiopic Georgian Glagolitic Gothic Grantha Gujarati '
        'GunjalaGondi Gurmukhi HanifiRohingya Hanunoo Hatran Hebrew ImperialAramaic '
        'InscriptionalPahlavi InscriptionalParthian Javanese Kaithi Kannada KayahLi Kharoshthi '
        'Khmer Khojki Khudawadi Lao Lepcha Limbu LinearA LinearB Lisu Lycian Lydian Mahajani '
        'Malayalam Mandaic Manichaean Marchen MasaramGondi Medefaidrin MeeteiMayek '
        'MendeKikakui Miao Modi Mongolian Mro Multani Myanmar NKo Nabataean Nandinagari '
        'NewTaiLue Newa Nushu Ogham OlChiki OldHungarian OldItalic OldNorthArabian OldPermic '
        'OldPersian OldSogdian OldSouthArabian OldTurkic Oriya Osage Osmanya PahawhHmong '
        'Palmyrene PauCinHau PhagsPa Phoenician PsalterPahlavi Rejang Runic Samaritan Saurashtra '
        'Sharada Shavian Siddham SignWriting Sinhala Sogdian SoraSompeng Soyombo Sundanese '
        'SylotiNagri Syriac Tagalog Tagbanwa TaiLe TaiTham TaiViet Takri Tamil Tangsa Telugu '
        'Thaana Thai Tifinagh Tirhuta Ugaritic Vai Vithkuqi Wancho WarangCiti Yi ZanabazarSquare'
    ).split()}
    SERIF_FONTS = {name.lower(): name for name in (
        'Ahom DivesAkuru Dogra Makasar NyiakengPuachueHmong OldUyghur Tangut Tibetan Toto Yezidi'
    ).split()}
    EXTRA_FONTS = {
        'meroitic': ('NotoSansMeroitic', r'[\U00010980-\U000109ff]'),
        'indicsiyaq': ('NotoSansIndicSiyaqNumbers', r'[\U0001ec70-\U0001ecbf]'),
        'mayan': ('NotoSansMayanNumerals', r'[\U0001d2e0-\U0001d2ff]'),
        'tamilsupplement': ('NotoSansTamilSupplement', r'[\U00011fc0-\U00011fff]'),
    }
    MAX_MESSAGES = 30

    @classmethod
    def normalize_options(cls, stored):
        options = dict(cls.DEFAULTS)
        if isinstance(stored, dict):
            if stored.get("theme") in ("dark", "light"):
                options["theme"] = stored["theme"]
            if stored.get('send_format') in ('sticker', 'png', 'photo'):
                options['send_format'] = stored['send_format']
            for key in ("spoilers", "gift_colors", "expanded", "bubble_outline"):
                if type(stored.get(key)) is bool:
                    options[key] = stored[key]
            transparency=stored.get('bubble_transparency')
            if type(transparency) is int and 0<=transparency<=100 and transparency%5==0:
                options['bubble_transparency']=transparency
            if stored.get('link_preview_position') in ('top', 'bottom'):
                options['link_preview_position']=stored['link_preview_position']
            mode=stored.get('background_mode','transparent')
            if mode in ('transparent','dark','light','custom'):
                options['background_mode']=mode
                options['background']=mode!='transparent'
            url=stored.get('background_url','')
            if isinstance(url,str) and len(url)<=2048:
                options['background_url']=url
        return options
    MAX_ASSET = 12 * 1024 * 1024
    MAX_CACHE = 96 * 1024 * 1024
    MAX_PIXELS = 24_000_000
    MAX_PAGES = 24
    PEER_COLORS = ("#ef7777", "#d99c58", "#af8add", "#70b87c", "#6dbcc5", "#76a8e6", "#d883b1")
    CSS = ""

    def __init__(self, module):
        self.module = module
        self.root = tempfile.TemporaryDirectory(prefix="godchat-gquote-")
        self.cache = {}
        self.cache_size = 0
        self.avatar_refresh_after = {}
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.closed = False

    @staticmethod
    def kind(obj):
        return type(obj).__name__

    @staticmethod
    def esc(value):
        return quote_html.escape(str(value or ""), quote=True)

    @staticmethod
    def color(value, default="#79b8e8"):
        return f"#{int(value) & 0xffffff:06x}" if isinstance(value, int) else default

    @staticmethod
    def username(peer):
        return getattr(peer, "username", None) or next((
            item.username for item in (getattr(peer, "usernames", None) or [])
            if getattr(item, "active", False) and getattr(item, "username", None)
        ), None)

    def name(self, peer):
        getter = getattr(self.module, '_custom_name', None)
        custom = getter(peer) if callable(getter) else None
        if custom: return custom
        return (getattr(peer, "title", None) or " ".join(filter(None, (
            getattr(peer, "first_name", None), getattr(peer, "last_name", None))))
            or self.username(peer) or "Deleted account")

    def label(self, ru, en):
        return ru if self.ru else en

    def warn(self, code, obj=None, error=None):
        kind = self.kind(obj) if obj is not None else "None"
        entry = f"{code}:{kind}"
        if entry not in self.state["warnings"]:
            self.state["warnings"].append(entry)
            self.log("warning", code, kind, error)

    def log(self, level, code, kind="None", error=None, state=None):
        frames = ""
        if error and error.__traceback__:
            frames = " > ".join(
                f"{Path(f.filename).name}:{f.lineno}:{f.name}"
                for f in traceback.extract_tb(error.__traceback__)
            )
        cause = error
        causes = []
        for _ in range(5):
            if cause is None:
                break
            causes.append(self.kind(cause) + (":" + str(cause) if isinstance(cause, _GQuoteError) else ""))
            cause = cause.__cause__ or cause.__context__
        state = state or self.state
        getattr(logger, level)(
            "gquote op=%s stage=%s message=%s element=%s code=%s exception=%s trace=%s",
            state["id"], state.get("stage"), state.get("message_id"),
            kind if kind != "None" else state.get("element", kind), code,
            ' <- '.join(causes) or "None", frames,
        )

    async def close(self):
        self.closed = True
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        self.root.cleanup()
        self.cache.clear()

    async def _cache_asset(self, key, producer):
        cached = self.cache.get(key)
        if cached and Path(cached).exists():
            return cached
        data, suffix = await producer()
        if not data:
            raise _GQuoteError("empty_asset")
        if len(data) > self.MAX_ASSET:
            raise _GQuoteError("asset_limit")
        if self.cache_size + len(data) > self.MAX_CACHE:
            raise _GQuoteError("cache_limit")
        path = Path(self.root.name) / (hashlib.sha256(key.encode()).hexdigest() + suffix)
        self.cache_size += len(data)
        try:
            await utils.run_sync(path.write_bytes, data)
        except BaseException:
            self.cache_size -= len(data)
            raise
        self.cache[key] = str(path)
        return str(path)

    @staticmethod
    def _fetch_asset(url):
        with urlopen(Request(url, headers={"User-Agent": "GodChat-gquote"}), timeout=30) as response:
            data = response.read(_GQuoteRenderer.MAX_ASSET + 1)
        if len(data) > _GQuoteRenderer.MAX_ASSET:
            raise _GQuoteError("asset_limit")
        return data

    async def library(self, name):
        urls = {
            "emoji_font": ("https://raw.githubusercontent.com/googlefonts/noto-emoji/v2.051/fonts/NotoColorEmoji.ttf", ".ttf"),
            "font_cjk": ("https://raw.githubusercontent.com/google/fonts/66a36c8c94b1a5d992ee4e7f392fccfe4945767c/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf", ".ttf"),
            "font_hangul": ("https://raw.githubusercontent.com/google/fonts/66a36c8c94b1a5d992ee4e7f392fccfe4945767c/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf", ".ttf"),
        }
        font_base = "https://raw.githubusercontent.com/notofonts/noto-fonts/ffebf8c1ee449e544955a7e813c54f9b73848eac/hinted/ttf/"
        for family, filename in {"regular":"NotoSans/NotoSans-Regular.ttf", "bold":"NotoSans/NotoSans-Bold.ttf",
                                 "italic":"NotoSans/NotoSans-Italic.ttf", "bolditalic":"NotoSans/NotoSans-BoldItalic.ttf",
                                 "mono":"NotoSansMono/NotoSansMono-Regular.ttf"}.items():
            urls["font_" + family] = (font_base + filename, ".ttf")
        urls["font_symbols"] = (font_base + "NotoSansSymbols/NotoSansSymbols-Regular.ttf", ".ttf")
        urls["font_symbols2"] = (font_base + "NotoSansSymbols2/NotoSansSymbols2-Regular.ttf", ".ttf")
        urls["font_math"] = (font_base + "NotoSansMath/NotoSansMath-Regular.ttf", ".ttf")
        for family, script in self.SCRIPT_FONTS.items():
            font = 'NotoSans' + script
            urls['font_'+family] = (font_base+font+'/'+font+'-Regular.ttf', '.ttf')
        for family, script in self.SERIF_FONTS.items():
            font = 'NotoSerif' + script
            urls['font_'+family] = (font_base+font+'/'+font+'-Regular.ttf', '.ttf')
        for family, (font, _) in self.EXTRA_FONTS.items():
            urls['font_'+family] = (font_base+font+'/'+font+'-Regular.ttf', '.ttf')
        url, suffix = urls[name]
        async def get():
            return await utils.run_sync(self._fetch_asset, url), suffix
        return await self._cache_asset("library:" + name, get)

    @staticmethod
    def _image_bytes(data):
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > _GQuoteRenderer.MAX_PIXELS:
                raise _GQuoteError("image_pixels_limit")
            image = ImageOps.exif_transpose(image)
            image.thumbnail((2048, 2048))
            out = io.BytesIO()
            image.convert("RGBA").save(out, format="PNG")
            return out.getvalue(), ".png"

    async def download(self, media, thumb=None):
        identity = getattr(media, "id", None)
        key = f"media:{self.kind(media)}:{identity}:{thumb}"
        async def get():
            size = getattr(media, "size", 0) or 0
            if thumb is None and size > self.MAX_ASSET:
                raise _GQuoteError("media_size_limit")
            class BoundedBuffer(io.BytesIO):
                def write(buffer, data):
                    if buffer.tell() + len(data) > _GQuoteRenderer.MAX_ASSET:
                        raise _GQuoteError("download_limit")
                    return super(BoundedBuffer, buffer).write(data)
            out = BoundedBuffer()
            await asyncio.wait_for(self.module.client.download_media(media, out, thumb=thumb), 40)
            data = out.getvalue()
            mime = getattr(media, "mime_type", "") or ""
            if thumb is None and mime == "application/x-tgsticker":
                with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
                    raw = compressed.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise _GQuoteError("tgs_limit")
                json.loads(raw)
                return raw, ".json"
            if thumb is None and (mime.startswith("video/") or mime == "image/gif"):
                return data, ".webm" if "webm" in mime else ".mp4" if "video" in mime else ".gif"
            return await utils.run_sync(self._image_bytes, data)
        return await self._cache_asset(key, get)

    async def image(self, media, css="media", thumb=None):
        if not media:
            return ""
        try:
            path = await self.download(media, thumb)
            attributes = {self.kind(a): a for a in getattr(media, "attributes", []) or []}
            custom = attributes.get("DocumentAttributeCustomEmoji") or attributes.get("DocumentAttributeSticker")
            extra = f' data-document="{self.esc(getattr(media,"id",None))}" data-alt="{self.esc(getattr(custom,"alt",None) or "◇")}"'
            if getattr(custom, "text_color", False):
                extra += ' data-tint="1"'
            if path.endswith((".json", ".webm", ".mp4")) and getattr(media, "thumbs", None):
                try:
                    fallback = await self.download(media, -1)
                    extra += f' data-fallback="{Path(fallback).as_uri()}"'
                except Exception:
                    pass
            if path.endswith(".json"):
                self.animation_count = getattr(self, "animation_count", 0) + 1
                if self.animation_count > 160:
                    raise _GQuoteError("animation_count_limit")
                return f'<img class="{css}" data-tgs="{Path(path).as_uri()}"{extra}>'
            if path.endswith((".mp4", ".webm")):
                return f'<video class="{css}" src="{Path(path).as_uri()}"{extra}></video>'
            return f'<img class="{css}" src="{Path(path).as_uri()}"{extra}>'
        except Exception as error:
            self.warn("media_unavailable", media, error)
            return self.notice(self.label("Медиа недоступно", "Media unavailable"))

    def notice(self, text):
        return f'<div class="notice">{self.esc(text)}</div>'

    async def emoji(self, identity, alt="⭐"):
        if not identity:
            return self.esc(alt)

        try:
            key = int(identity)
            if key not in self.documents:
                docs = await asyncio.wait_for(self.module.client(
                    functions.messages.GetCustomEmojiDocumentsRequest([key])), 20)
                self.documents.update({d.id: d for d in docs})
            doc = self.documents.get(key)
            if not doc:
                raise _GQuoteError("emoji_missing")
            result = await self.image(doc, "emoji")
            if 'class="notice"' in result:
                return self.esc(alt)
            return result
        except Exception as error:
            self.warn("emoji_unavailable", error=error)
            return self.esc(alt)

    async def pattern(self, document=None, identity=None, color="#ffffff"):
        if not document and identity:
            try:
                docs = await asyncio.wait_for(self.module.client(functions.messages.GetCustomEmojiDocumentsRequest([identity])), 20)
                document = next(iter(docs), None)
            except Exception as error:
                self.warn("pattern_unavailable", error=error)
        if not document:
            return ''
        return f'<div class="pattern-overlay" data-pattern-color="{color}">' + await self.image(document, "pattern-source") + '</div>'

    async def code(self, text, language=""):
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import get_lexer_by_name, TextLexer
        from pygments.util import ClassNotFound
        try:
            lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False) if language else TextLexer(stripnl=False, ensurenl=False)
        except ClassNotFound:
            lexer = TextLexer(stripnl=False, ensurenl=False)
        formatter = HtmlFormatter(nowrap=True, noclasses=True,
                                  style="monokai" if self.options["theme"] == "dark" else "friendly")
        painted = await utils.run_sync(highlight, text, lexer, formatter)
        if painted.endswith('\n') and not text.endswith('\n'):
            painted = painted[:-1]
        return f'<pre><div class="language">{self.esc(language)}</div>{painted}</pre>'

    async def entities(self, text, entities):
        text = text or ""
        raw = text.encode("utf-16-le", "surrogatepass")
        if len(raw) > 262144:
            raise _GQuoteError("text_limit")
        spans = []
        for entity in entities or []:
            start = max(0, int(getattr(entity, "offset", 0)))
            end = min(len(raw) // 2, start + int(getattr(entity, "length", 0)))
            if end > start:
                spans.append((start, end, entity))
        boundaries = sorted({0, len(raw) // 2} | {x for a, b, _ in spans for x in (a, b)})
        result, skip = [], -1
        for a, b in zip(boundaries, boundaries[1:]):
            if a < skip:
                continue
            active = sorted((s for s in spans if s[0] <= a < s[1]), key=lambda s: (s[0], -s[1]))
            special = next((s for s in active if self.kind(s[2]) in ("MessageEntityPre", "MessageEntityCustomEmoji", "MessageEntityFormattedDate")), None)
            if special:
                start, end, entity = special
                value = raw[max(a, start)*2:end*2].decode("utf-16-le", "replace")
                if self.kind(entity) == "MessageEntityPre":
                    value = await self.code(value, getattr(entity, "language", ""))
                elif self.kind(entity) == "MessageEntityCustomEmoji":
                    value = await self.emoji(entity.document_id, value)
                else:
                    value = self.esc(self.formatted_date(entity) or value)
                skip = end
            else:
                value = self.esc(raw[a*2:b*2].decode("utf-16-le", "replace"))
            for _, _, entity in reversed(active):
                kind = self.kind(entity).replace("MessageEntity", "")
                tags = {"Bold": "b", "Italic": "i", "Underline": "u", "Strike": "s", "Code": "code"}
                if kind in tags:
                    value = f'<{tags[kind]}>{value}</{tags[kind]}>'
                elif kind == "Spoiler":
                    value = f'<span class="spoiler {"revealed" if self.options["spoilers"] else ""}">{value}</span>'
                elif kind == "Blockquote":
                    pass
                elif kind in ("Url", "TextUrl", "Mention", "MentionName", "Email", "Phone", "Hashtag", "BotCommand", "Cashtag"):
                    value = f'<span class="link">{value}</span>'
                elif kind.startswith("Diff"):
                    if kind == "DiffReplace" and a == getattr(entity, "offset", -1):
                        value = '<del>' + self.esc(getattr(entity, "old_text", "")) + '</del>' + value
                    value = f'<{ "del" if kind == "DiffDelete" else "ins" }>{value}</{ "del" if kind == "DiffDelete" else "ins" }>'
                elif kind not in ("Pre", "CustomEmoji", "FormattedDate", "BankCard"):
                    self.warn("entity_unsupported", entity)
            quote = next((s for s in active if self.kind(s[2]) == "MessageEntityBlockquote"), None)
            if quote:
                if a == quote[0]:
                    collapsed = getattr(quote[2], "collapsed", False) and not self.options["expanded"]
                    if collapsed:
                        preview = " ".join(raw[quote[0]*2:quote[1]*2].decode("utf-16-le", "replace").split())
                        if len(preview) > 512:
                            preview = preview[:512].rstrip() + "…"
                        value = '<details><summary>' + self.esc(preview or self.label("Цитата", "Quote")) + '</summary>' + value
                    else:
                        value = '<blockquote>' + value
                if (skip if special else b) >= quote[1]:
                    value += '</details>' if getattr(quote[2], "collapsed", False) and not self.options["expanded"] else '</blockquote>'
            result.append(value)
        return "".join(result)

    def local_date(self, date):
        return date.astimezone(getattr(self, "quote_timezone", None))

    def formatted_date(self, item):
        date = getattr(item, "date", None)
        if not hasattr(date, "strftime"):
            return ''
        date = self.local_date(date)
        parts = []
        if getattr(item, "day_of_week", False):
            days = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье") if self.ru else ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            parts.append(days[date.weekday()])
        if getattr(item, "long_date", False) or getattr(item, "short_date", False):
            parts.append(date.strftime('%d.%m.%Y'))
        if getattr(item, "long_time", False) or getattr(item, "short_time", False):
            parts.append(date.strftime('%H:%M:%S' if getattr(item, "long_time", False) else '%H:%M'))
        if getattr(item, "relative", False):
            self.warn("relative_date_absolute", item)
        return ' '.join(parts) or date.strftime('%d.%m.%Y %H:%M')

    async def rich_text(self, item, depth=0):
        if depth > 24:
            raise _GQuoteError("rich_depth_limit")
        if item is None:
            return ""
        if isinstance(item, str):
            return self.esc(item)
        kind = self.kind(item)
        if kind == "TextPlain":
            return self.esc(item.text)
        if kind == "TextEmpty":
            return ""
        if kind == "TextConcat":
            return "".join([await self.rich_text(x, depth + 1) for x in item.texts])
        if kind == "TextCustomEmoji":
            return await self.emoji(getattr(item, "document_id", None), getattr(item, "alt", "⭐"))
        if kind == "TextImage":
            return await self.image(self.documents.get(item.document_id), "emoji")
        if kind == "TextMath":
            return self.formula(getattr(item, "source", ""))
        value = await self.rich_text(getattr(item, "text", ""), depth + 1)
        tags = {"TextBold": "b", "TextItalic": "i", "TextUnderline": "u", "TextStrike": "s", "TextFixed": "code", "TextSubscript": "sub", "TextSuperscript": "sup", "TextMarked": "mark"}
        if kind in tags:
            return f'<{tags[kind]}>{value}</{tags[kind]}>'
        if kind == "TextSpoiler":
            return f'<span class="spoiler {"revealed" if self.options["spoilers"] else ""}">{value}</span>'
        if kind in ("TextUrl", "TextAutoUrl", "TextEmail", "TextAutoEmail", "TextPhone", "TextAutoPhone", "TextMention", "TextMentionName", "TextHashtag", "TextCashtag", "TextBotCommand"):
            return f'<span class="link">{value}</span>'
        if kind == "TextDiff":
            return '<del>' + await self.rich_text(getattr(item, "old_text", ""), depth + 1) + '</del><ins>' + value + '</ins>'
        if kind in ("TextAnchor", "TextBankCard"):
            return value
        if kind == "TextDate":
            return self.esc(self.formatted_date(item)) or value
        self.warn("rich_text_unsupported", item)
        return value or self.notice(kind)

    def plain(self, value, depth=0):
        if depth > 24 or value is None:
            return ""
        if isinstance(value, str):
            return value
        if hasattr(value, "texts"):
            return "".join(self.plain(x, depth + 1) for x in value.texts)
        return self.plain(getattr(value, "text", ""), depth + 1)

    def formula(self, value, block=False):
        return f'<span class="math" data-display="{int(block)}">{self.esc(self.plain(value))}</span>'

    async def blocks(self, blocks, depth=0):
        if depth > 20:
            raise _GQuoteError("block_depth_limit")
        result = []
        for block in blocks or []:
            self.block_count += 1
            if self.block_count > 2000:
                raise _GQuoteError("block_count_limit")
            kind = self.kind(block).replace("PageBlock", "")
            self.state["element"] = self.kind(block)
            text = await self.rich_text(getattr(block, "text", None))
            caption = getattr(block, "caption", None)
            cap = await self.rich_text(getattr(caption, "text", caption)) if caption else ""
            if kind in ("Paragraph", "Footer", "Kicker", "AuthorDate"):
                result.append('<p>' + (text or self.esc(getattr(block, "author", ""))) + '</p>')
            elif kind in ("Title", "Header", "Subtitle", "Subheader") or kind.startswith("Heading"):
                level = kind[-1] if kind[-1:].isdigit() else "2"
                result.append(f'<h{level}>{text}</h{level}>')
            elif kind == "Preformatted":
                result.append(await self.code(self.plain(block.text), getattr(block, "language", "")))
            elif kind == "Divider":
                result.append('<hr>')
            elif kind == "ButtonRow":
                buttons = []
                for button in getattr(block, "buttons", []) or []:
                    label = await self.rich_text(getattr(button, "text", None))
                    if not label:
                        continue
                    style = getattr(button, "style", None)
                    color = next((name for name in ("primary", "danger", "success") if getattr(style, "bg_" + name, False)), "")
                    icon_id = getattr(style, "icon", None)
                    icon = (await self.emoji(icon_id) + " ") if icon_id else ""
                    buttons.append('<span class="button" data-button-style="' + color + '">' + icon + label + '</span>')
                if buttons:
                    result.append('<div class="buttons rich-buttons">' + ''.join(buttons) + '</div>')
            elif kind == "Anchor":
                continue
            elif kind in ("Blockquote", "Pullquote"):
                result.append('<blockquote>' + text + ('<small>' + cap + '</small>' if cap else '') + '</blockquote>')
            elif kind in ("Details", "Thinking", "BlockquoteBlocks"):
                title = await self.rich_text(getattr(block, "title", None))
                inner = await self.blocks(getattr(block, "blocks", []), depth + 1)
                if kind == "Thinking":
                    inner = text
                if kind == "BlockquoteBlocks":
                    result.append('<blockquote>' + inner + '</blockquote>')
                else:
                    result.append(f'<details {"open" if self.options["expanded"] else ""}><summary>{title or self.label("Подробности", "Details")}</summary>{inner}</details>')
            elif kind in ("List", "OrderedList"):
                tag = "ol" if kind == "OrderedList" else "ul"
                items = []
                for item in getattr(block, "items", []):
                    inner = await self.blocks(item.blocks, depth + 1) if hasattr(item, "blocks") else await self.rich_text(getattr(item, "text", item))
                    number = getattr(item, "num", None)
                    attr = f' value="{int(number)}"' if str(number).isdigit() else ""
                    items.append('<li' + attr + '>' + inner + '</li>')
                result.append(f'<{tag}>' + ''.join(items) + f'</{tag}>')
            elif kind == "Table":
                rows = []
                for row in getattr(block, "rows", []):
                    cells = []
                    for cell in row.cells:
                        tag = "th" if getattr(cell, "header", False) else "td"
                        align = "center" if getattr(cell, "align_center", False) else "right" if getattr(cell, "align_right", False) else "left"
                        cells.append(f'<{tag} colspan="{max(1, min(100, getattr(cell, "colspan", 1) or 1))}" rowspan="{max(1, min(100, getattr(cell, "rowspan", 1) or 1))}" style="text-align:{align}">' + await self.rich_text(getattr(cell, "text", None)) + f'</{tag}>')
                    rows.append('<tr>' + ''.join(cells) + '</tr>')
                result.append(text + '<table>' + ''.join(rows) + '</table>')
            elif kind in ("Photo", "Video", "Audio", "Document"):
                identity = next((getattr(block, key) for key in ("photo_id", "video_id", "audio_id", "document_id") if getattr(block, key, None)), None)
                media = self.documents.get(identity) or self.photos.get(identity)
                result.append((await self.document(media) if self.kind(media) == "Document" else await self.image(media)) + '<div class="caption">' + cap + '</div>')
            elif kind in ("Collage", "Slideshow"):
                result.append('<div class="grid">' + await self.blocks(getattr(block, "items", []), depth + 1) + '</div>' + cap)
            elif kind == "Cover":
                result.append(await self.blocks([block.cover], depth + 1))
            elif kind == "Math":
                result.append(self.formula(getattr(block, "source", ""), True))
            elif kind == "Map":
                result.append(self.geo(getattr(block, "geo", None)) + cap)
            elif kind in ("Embed", "EmbedPost"):
                result.append(self.notice(getattr(block, "url", "") or kind) + cap)
                if hasattr(block, "blocks"):
                    result.append(await self.blocks(block.blocks, depth + 1))
                self.warn("external_embed_static", block)
            else:
                self.warn("block_unsupported", block)
                result.append(self.notice(kind) + text + cap)
        return ''.join(result)

    @staticmethod
    def size(value):
        value = float(value or 0)
        for suffix in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or suffix == "TB":
                return f"{value:.1f} {suffix}"
            value /= 1024

    def attachment(self, title, subtitle, icon=None, waveform=""):
        disc = '<div class="disc document-icon"></div>' if icon is None else '<div class="disc">' + self.esc(icon) + '</div>'
        return f'<div class="attachment">{disc}<div><div class="attachment-title">{self.esc(title)}</div>{waveform}<div class="attachment-subtitle">{self.esc(subtitle)}</div></div></div>'

    async def document(self, doc):
        if not doc:
            self.warn("document_missing")
            return self.notice(self.label("Файл недоступен", "File unavailable"))
        attrs = {self.kind(a): a for a in getattr(doc, "attributes", [])}
        filename = getattr(attrs.get("DocumentAttributeFilename"), "file_name", "File")
        audio = attrs.get("DocumentAttributeAudio")
        video = attrs.get("DocumentAttributeVideo")
        mime = getattr(doc, "mime_type", "") or ""
        if "DocumentAttributeSticker" in attrs or "DocumentAttributeCustomEmoji" in attrs:
            return await self.image(doc, "sticker")
        if audio:
            duration = int(getattr(audio, "duration", 0) or 0)
            wave = getattr(audio, "waveform", None)
            waveform = ""
            if wave:
                bits = int.from_bytes(wave, "little")
                values = [(bits >> i) & 31 for i in range(0, len(wave) * 8 - 4, 5)]
                step = max(1, math.ceil(len(values) / 64))
                waveform = '<div class="wave">' + ''.join(f'<i style="height:{max(3, v)}px"></i>' for v in values[::step]) + '</div>'
            title = self.label("Голосовое сообщение", "Voice message") if getattr(audio, "voice", False) else getattr(audio, "title", None) or filename
            performer = getattr(audio, "performer", "") or ""
            return self.attachment(title, f"{performer} {duration//60}:{duration%60:02}", "▶", waveform)
        if video or mime.startswith("video/") or mime == "image/gif":
            animated = "DocumentAttributeAnimated" in attrs or mime == "image/gif"
            thumbs = [t for t in getattr(doc, "thumbs", []) or [] if getattr(t, "w", 0) and getattr(t, "h", 0)]
            thumb = max(thumbs, key=lambda t: t.w*t.h) if thumbs else None
            image = await self.image(doc, "media round" if getattr(video, "round_message", False) else "media", thumb)
            duration = int(getattr(video, "duration", 0) or 0)
            label = "GIF" if animated else f'{duration//60}:{duration%60:02} · {self.size(doc.size)}'
            return f'<div class="video-card" data-width="{getattr(video,"w",0)}" data-height="{getattr(video,"h",0)}" data-gif="{int(animated)}" data-label="{self.esc(label)}">{image}</div>'
        if mime.startswith("image/"):
            return await self.image(doc)
        thumb = await self.image(doc, "media", -1) if getattr(doc, "thumbs", None) else ""
        return thumb + self.attachment(filename, self.size(getattr(doc, "size", 0)))

    def geo(self, media):
        geo = getattr(media, "geo", None)
        if not geo:
            return self.notice(self.label("Геопозиция недоступна", "Location unavailable"))
        title = getattr(media, "title", None) or (
            self.label("Геопозиция в реальном времени", "Live location")
            if self.kind(media) == "MessageMediaGeoLive" else self.label("Геопозиция", "Location")
        )
        address = getattr(media, "address", None) or ""
        try:
            lat, lon = float(geo.lat), float(geo.long)
            coords = f"{lat:.5f}, {lon:.5f}" if math.isfinite(lat) and math.isfinite(lon) else ""
        except (AttributeError, TypeError, ValueError):
            coords = ""
        fields = (("geo-title", title), ("geo-address", address), ("geo-coords", coords))
        return '<div class="geo-card">' + ''.join(
            f'<div class="{kind}">{self.esc(value)}</div>' for kind, value in fields if value
        ) + '</div>'

    async def giveaway(self, media, results=False):
        count = int(getattr(media, "winners_count" if results else "quantity", 0) or 0)
        stars = int(getattr(media, "stars", 0) or 0)
        months = int(getattr(media, "months", 0) or 0)
        if stars:
            prize = self.label(f"{count} победителей · {stars:,} звёзд", f"{count} winners · {stars:,} Stars").replace(",", " ")
        elif months:
            prize = self.label(f"{count} победителей · Premium на {months} мес.", f"{count} winners · {months} months Premium")
        else:
            prize = self.label(f"{count} победителей", f"{count} winners")
        description = str(getattr(media, "prize_description", None) or "").strip()
        if len(description) > 180:
            description = description[:179].rstrip() + "…"
        channel_ids = [getattr(media, "channel_id", None)] if results else (getattr(media, "channels", None) or [])
        channel_names = []
        for channel_id in channel_ids[:3]:
            if not channel_id:
                continue
            identity = types.PeerChannel(channel_id)
            try:
                peer = await asyncio.wait_for(self.peer(identity), 3)
                channel_names.append(self.name(peer))
            except Exception as error:
                self.warn("giveaway_channel_unavailable", media, error)
        if len(channel_ids) > 3:
            channel_names.append(self.label(f"и ещё {len(channel_ids)-3}", f"and {len(channel_ids)-3} more"))
        participants = self.label("Участники: ", "Participants: ") + ", ".join(channel_names) if channel_names else ""
        if getattr(media, "only_new_subscribers", False):
            restriction = self.label("Только новые подписчики", "New subscribers only")
            participants = participants + " · " + restriction if participants else restriction
        countries = []
        country_names = {
            "RU": ("Россия", "Russia"), "BY": ("Беларусь", "Belarus"),
            "UZ": ("Узбекистан", "Uzbekistan"), "KZ": ("Казахстан", "Kazakhstan"),
            "AE": ("ОАЭ", "UAE"), "UA": ("Украина", "Ukraine"),
            "US": ("США", "USA"), "GB": ("Великобритания", "UK"),
        }
        country_codes = getattr(media, "countries_iso2", None) or []
        for code in country_codes[:5]:
            code = str(code).upper()
            if len(code) == 2 and code.isalpha() and code.isascii():
                flag = "".join(chr(0x1F1E6 + ord(char) - ord("A")) for char in code)
                name = country_names.get(code, (code, code))[0 if self.ru else 1]
                countries.append(f"{flag} {name}")
        if len(country_codes) > 5:
            countries.append(f"+{len(country_codes)-5}")
        until = getattr(media, "until_date", None)
        date = ""
        if hasattr(until, "strftime"):
            date = self.label("Итоги: ", "Results: ") + self.local_date(until).strftime("%d.%m.%Y %H:%M")
        fields = (
            ("giveaway-title", self.label("Результаты розыгрыша", "Giveaway results") if results else self.label("Розыгрыш призов", "Prize giveaway")),
            ("giveaway-prize", prize),
            ("giveaway-description", description),
            ("giveaway-channels", participants),
            ("giveaway-countries", " · ".join(countries)),
            ("giveaway-date", date),
        )
        return '<div class="giveaway">' + ''.join(
            f'<div class="{kind}">{self.esc(value)}</div>' for kind, value in fields if value
        ) + '</div>'

    async def media(self, media):
        kind = self.kind(media)
        self.state["element"] = kind
        if media is None or kind == "MessageMediaEmpty":
            return ""
        if kind == "MessageMediaPhoto":
            value = await self.image(getattr(media, "photo", None))
        elif kind == "MessageMediaDocument":
            value = await self.document(getattr(media, "document", None))
        elif kind == "MessageMediaWebPage":
            page = media.webpage
            value = '<blockquote><b>' + self.esc(getattr(page, "site_name", "")) + '</b><div>' + self.esc(getattr(page, "title", "")) + '</div>' + self.esc(getattr(page, "description", ""))
            if getattr(page, "photo", None):
                value += await self.image(page.photo)
            value += '</blockquote>'
        elif kind == "MessageMediaPoll":
            poll, results = media.poll, media.results
            question = getattr(poll.question, "text", poll.question)
            value = '<b>' + await self.entities(question, getattr(poll.question, "entities", [])) + '</b>'
            total = getattr(results, "total_voters", 0) or 0
            counts = {r.option: r for r in getattr(results, "results", []) or []}
            for answer in poll.answers:
                item = counts.get(answer.option)
                votes = getattr(item, "voters", 0) or 0
                text = getattr(answer.text, "text", answer.text)
                rendered = await self.entities(text, getattr(answer.text, "entities", []))
                percent = round(votes * 100 / total) if total else 0
                value += '<div class="poll-option">' + ('✓ ' if getattr(item, "chosen", False) else '') + rendered
                if item is not None:
                    value += f' · {percent}%<div class="poll-bar" style="width:{percent}%"></div>'
                value += '</div>'
            value += '<div class="caption">' + self.label(f"Голосов: {total}", f"Votes: {total}") + '</div>'
        elif kind == "MessageMediaContact":
            getter = getattr(self.module, '_custom_name', None)
            custom = getter(SimpleNamespace(id=getattr(media, 'user_id', None))) if callable(getter) else None
            value = self.attachment(custom or f'{media.first_name} {media.last_name}', media.phone_number, "☎")
        elif kind in ("MessageMediaGeo", "MessageMediaGeoLive", "MessageMediaVenue"):
            value = self.geo(media)
        elif kind == "MessageMediaDice":
            value = self.attachment(media.emoticon, str(media.value), media.emoticon)
            self.warn("dice_static_value", media)
        elif kind == "MessageMediaToDo":
            todo = media.todo
            completions = {item.id: item for item in getattr(media, "completions", []) or [] if getattr(item, "completed_by", None)}
            items = getattr(todo, "list", []) or []
            title = getattr(todo, "title", None)
            value = '<div class="todo-card"><div class="todo-title">' + await self.entities(getattr(title, "text", title) or "", getattr(title, "entities", []) or []) + '</div>'
            value += '<div class="todo-label">' + self.label("Список задач", "To-do list") + '</div>'
            for item in items:
                item_title = getattr(item, "title", None)
                done = item.id in completions
                body = await self.entities(getattr(item_title, "text", item_title) or "", getattr(item_title, "entities", []) or [])
                value += f'<div class="todo-item" data-done="{int(done)}"><div class="todo-text">{body}</div>'
                if done:
                    try:
                        peer = await asyncio.wait_for(self.peer(completions[item.id].completed_by), 3)
                        value += '<div class="todo-by">' + self.esc(self.name(peer)) + '</div>'
                    except Exception as error:
                        self.warn("todo_completer_unavailable", media, error)
                value += '</div>'
            done_count = sum(item.id in completions for item in items)
            value += '<div class="todo-progress">' + self.label(f"{done_count} из {len(items)} выполнено", f"{done_count} of {len(items)} completed") + '</div></div>'
        elif kind == "MessageMediaGame":
            value = self.attachment(media.game.title, media.game.description, "🎮")
            if getattr(media.game, "photo", None):
                value += await self.image(media.game.photo)
        elif kind == "MessageMediaInvoice":
            value = self.attachment(media.title, f'{media.description} · {media.total_amount} {media.currency}', "🧾")
            self.warn("invoice_raw_amount", media)
        elif kind == "MessageMediaPaidMedia":
            parts = []
            for item in getattr(media, "extended_media", []):
                parts.append(await self.media(item.media) if getattr(item, "media", None) else self.notice(self.label("Платное медиа: предпросмотр недоступен", "Paid media: preview unavailable")))
            value = ''.join(parts)
        elif kind == "MessageMediaStory":
            story = getattr(media, "story", None)
            if not story or not getattr(story, "media", None):
                result = await asyncio.wait_for(self.module.client(functions.stories.GetStoriesByIDRequest(peer=media.peer, id=[media.id])), 20)
                story = next(iter(getattr(result, "stories", [])), None)
            if story and getattr(story, "media", None):
                value = await self.media(story.media) + await self.entities(getattr(story, "caption", ""), getattr(story, "entities", []))
            else:
                self.warn("story_unavailable", media)
                value = self.notice(self.label("История недоступна", "Story unavailable"))
        elif kind in ("MessageMediaGiveaway", "MessageMediaGiveawayResults"):
            value = await self.giveaway(media, kind == "MessageMediaGiveawayResults")
        elif kind == "MessageMediaVideoStream":
            value = self.attachment(self.label("Прямая трансляция", "Live stream"), '', "▶")
        else:
            self.warn("media_type_unsupported", media)
            value = self.notice(kind)
        if getattr(media, "spoiler", False):
            value = f'<div class="media-spoiler {"revealed" if self.options["spoilers"] else ""}">{value}</div>'
        return value

    async def todo_source(self, message):
        info = getattr(message, "reply_to", None)
        msg_id = getattr(info, "reply_to_msg_id", None)
        if not msg_id:
            return None
        peer = getattr(info, "reply_to_peer_id", None) or message.peer_id
        key = (str(peer), msg_id)
        if key not in self.replies:
            result = await asyncio.wait_for(self.module.client.get_messages(peer, ids=msg_id), 5)
            self.replies[key] = next((item for item in result if item), None) if isinstance(result, (list, tuple)) else result
        return self.replies[key]

    async def action(self, action, actor=None, message=None):
        kind = self.kind(action)
        if kind == "MessageActionTodoCompletions":
            titles = {}
            if message:
                try:
                    source = await self.todo_source(message)
                    todo = getattr(getattr(source, "media", None), "todo", None)
                    titles = {item.id: getattr(item.title, "text", item.title) for item in getattr(todo, "list", []) or []}
                except Exception as error:
                    self.warn("todo_source_unavailable", action, error)
            parts = []
            for ids, ru, en in (
                (getattr(action, "completed", []) or [], "отметил(а) как выполненное", "completed"),
                (getattr(action, "incompleted", []) or [], "снял(а) отметку выполнения", "unchecked"),
            ):
                if ids:
                    names = [f'«{titles.get(item_id) or self.label(f"задача №{item_id}", f"task #{item_id}")}»' for item_id in ids]
                    parts.append(self.label(ru, en) + " " + ", ".join(names))
            if parts:
                return '<div class="service"><b>' + self.esc(actor or self.label("Участник", "Member")) + '</b> ' + self.esc("; ".join(parts)) + '</div>'
        if kind == "MessageActionTodoAppendTasks":
            items = []
            for item in getattr(action, "list", []) or []:
                title = getattr(item, "title", None)
                items.append(getattr(title, "text", title) or self.label("задачу", "a task"))
            return '<div class="service"><b>' + self.esc(actor or self.label("Участник", "Member")) + '</b> ' + self.esc(self.label("добавил(а) задачи: ", "added tasks: ") + ", ".join(map(str, items))) + '</div>'
        if kind == 'MessageActionBoostApply':
            title=self.label('проголосовал(а) за группу','boosted the group')
            boosts=getattr(action,'boosts',1)
            if isinstance(boosts,int) and boosts>1: title+=f' · {boosts}'
            return '<div class="service"><b>'+self.esc(actor or self.label('Участник','Member'))+'</b> '+self.esc(title)+'</div>'
        if kind in ("MessageActionStarGift", "MessageActionStarGiftUnique"):
            gift = action.gift
            attrs = {self.kind(a): a for a in getattr(gift, "attributes", [])}
            backdrop = attrs.get("StarGiftAttributeBackdrop") or getattr(gift, "background", None)
            style = ""
            if backdrop:
                style = f'background:radial-gradient(circle,{self.color(getattr(backdrop,"center_color",None))},{self.color(getattr(backdrop,"edge_color",None))});color:{self.color(getattr(backdrop,"text_color",None),"#ffffff")}'
            model = attrs.get("StarGiftAttributeModel")
            doc = getattr(model, "document", None) or getattr(gift, "sticker", None)
            title = getattr(gift, "title", None) or self.label("Подарок", "Gift")
            number = getattr(gift, "num", None)
            pattern = attrs.get("StarGiftAttributePattern")
            pattern_html = await self.pattern(getattr(pattern, "document", None), color=self.color(getattr(backdrop, "pattern_color", None))) if pattern else ''
            result = f'<div class="gift" style="{style}">' + pattern_html + await self.image(doc, "sticker") + '<h3>' + self.esc(title) + (f' #{number}' if number else '') + '</h3>'
            for key in ("StarGiftAttributeModel", "StarGiftAttributePattern", "StarGiftAttributeBackdrop"):
                if key in attrs:
                    result += '<div>' + self.esc(getattr(attrs[key], "name", "")) + '</div>'
            result += '</div>'
            text = getattr(action, "message", None)
            if text:
                result += await self.entities(text.text, text.entities)
            return result
        labels = {
            "MessageActionPinMessage": ("Закреплённое сообщение", "Pinned message"),
            "MessageActionPhoneCall": ("Звонок", "Call"),
            "MessageActionChatJoinedByLink": ("Вступление по ссылке", "Joined by link"),
            "MessageActionChatJoinedByRequest": ("Заявка на вступление принята", "Join request approved"),
            "MessageActionChatAddUser": ("Добавлены участники", "Members added"),
            "MessageActionChatDeleteUser": ("Участник вышел или удалён", "Member left or removed"),
            "MessageActionGiftPremium": ("Подарок Telegram Premium", "Telegram Premium gift"),
            "MessageActionGiftCode": ("Подарочный код Premium", "Premium gift code"),
            "MessageActionGiftTon": ("Подарок TON", "TON gift"),
            "MessageActionGroupCall": ("Групповой звонок", "Group call"),
            "MessageActionGroupCallScheduled": ("Запланирован звонок", "Scheduled call"),
            "MessageActionTopicEdit": ("Изменён топик", "Topic edited"),
            "MessageActionSetChatTheme": ("Изменена тема чата", "Chat theme changed"),
            "MessageActionSetChatWallPaper": ("Изменён фон чата", "Chat wallpaper changed"),
            "MessageActionHistoryClear": ("История очищена", "History cleared"),
            "MessageActionScreenshotTaken": ("Сделан снимок экрана", "Screenshot taken"),
            "MessageActionContactSignUp": ("Контакт присоединился к Telegram", "Contact joined Telegram"),
            "MessageActionChatCreate": ("Создан чат", "Chat created"),
            "MessageActionChannelCreate": ("Создан канал", "Channel created"),
            "MessageActionGiftStars": ("Подарок Telegram Stars", "Telegram Stars gift"),
            "MessageActionSetMessagesTTL": ("Изменён таймер удаления", "Auto-delete timer changed"),
            "MessageActionChatEditTitle": ("Изменено название чата", "Chat title changed"),
            "MessageActionChatEditPhoto": ("Изменена фотография чата", "Chat photo changed"),
            "MessageActionTopicCreate": ("Создан топик", "Topic created"),
        }
        if kind not in labels:
            self.warn("service_unsupported", action)
        title = self.label(*labels[kind]) if kind in labels else self.label('Служебное сообщение','Service message')
        parts = [getattr(action, name, None) for name in ("title", "duration", "months", "stars", "period")]
        rendered = '<div class="service">' + self.esc(title) + '<br>' + self.esc(' · '.join(str(x) for x in parts if x is not None)) + '</div>'
        if getattr(action, "message", None) and hasattr(action.message, "text"):
            rendered += await self.entities(action.message.text, action.message.entities)
        if getattr(action, "photo", None):
            rendered += await self.image(action.photo)
        return rendered

    async def peer(self, identity):
        key = str(identity)
        if key not in self.peers:
            self.peers[key] = await asyncio.wait_for(self.module.client.get_entity(identity), 20)
        return self.peers[key]

    async def refresh_avatar_peer(self, identity, sender, retry=False):
        key = str(identity)
        now = time.monotonic()
        if not retry and now < self.avatar_refresh_after.get(key, 0):
            return sender
        self.avatar_refresh_after[key] = now + 15
        if len(self.avatar_refresh_after) > 512:
            self.avatar_refresh_after = {
                peer_key: expires for peer_key, expires in self.avatar_refresh_after.items()
                if expires > now
            }
            if len(self.avatar_refresh_after) > 512:
                self.avatar_refresh_after = dict(list(self.avatar_refresh_after.items())[-512:])
        client = self.module.client
        try:
            forced = getattr(client, 'force_get_entity', None)
            if callable(forced):
                fresh = await asyncio.wait_for(forced(identity), 5)
            else:
                fresh = await asyncio.wait_for(client.get_entity(identity, force=True), 5)
        except (TypeError, asyncio.TimeoutError):
            return sender
        except Exception:
            return sender
        if fresh is not None:
            self.peers[key] = fresh
            return fresh
        return sender

    def accent_colors(self, palette, accent, collectible=True):
        colors = None
        if self.kind(palette) == "PeerColorCollectible" and collectible:
            colors = getattr(palette, "dark_colors", None) if self.options["theme"] == "dark" else None
            colors = colors or getattr(palette, "colors", None)
        elif getattr(palette, "color", None) is not None:
            colors = self.palettes.get(palette.color)
        return ','.join(self.color(c, accent) for c in colors[:3]) if colors else accent

    @staticmethod
    def short_quote_name(name):
        import regex
        parts = regex.findall(r'\X', name)
        return ''.join(parts[:15]) + '..' if len(parts) > 15 else name

    async def author(self, message, via=None):
        sender = None
        identity = getattr(message, "from_id", None) or message.peer_id
        try:
            sender = await self.peer(identity)
        except Exception as error:
            self.warn("sender_unavailable", message, error)
        if (self.options["avatars"] and self.kind(sender) == "User"
                and not getattr(sender, "photo", None)):
            sender = await self.refresh_avatar_peer(identity, sender)
        name = getattr(message, 'display_name', None) or self.name(sender)
        shown_name = self.short_quote_name(name)
        palette = getattr(sender, "color", None)
        fallback = self.PEER_COLORS
        accent = fallback[abs(getattr(sender, "id", 0)) % len(fallback)]
        if getattr(palette, "color", None) is not None:
            identity = palette.color
            if identity in self.palettes:
                colors = self.palettes[identity]
                accent = self.color(colors[0]) if colors else accent
            elif 0 <= identity < len(fallback):
                accent = fallback[identity]
            else:
                self.warn("peer_palette_missing", palette)
        avatar = ''
        if self.options["avatars"] and sender:
            for attempt in range(2):
                if not getattr(sender, "photo", None):
                    break
                try:
                    key = f'avatar:{sender.id}:{getattr(sender.photo,"photo_id",0)}'
                    async def get():
                        data = await asyncio.wait_for(self.module.client.download_profile_photo(sender, bytes, download_big=False), 20)
                        if not data:
                            raise _GQuoteError("avatar_empty")
                        return await utils.run_sync(self._image_bytes, data)
                    path = await self._cache_asset(key, get)
                    avatar = f'<img class="avatar" src="{Path(path).as_uri()}">'
                    break
                except Exception as error:
                    if attempt == 0:
                        fresh = await self.refresh_avatar_peer(identity, sender, retry=True)
                        if fresh is not sender and getattr(fresh, "photo", None):
                            sender = fresh
                            continue
                    self.warn("avatar_unavailable", sender, error)
                    break
        if self.options["avatars"] and not avatar:
            avatar = '<div class="initials">' + self.esc(name[:1]) + '</div>'
        status = getattr(sender, "emoji_status", None)
        display_status = getattr(message, 'display_status', None)
        if display_status is None:
            status_html = await self.emoji(getattr(status, "document_id", None)) if status else ('<span class="premium">★</span>' if getattr(sender, "premium", False) else '')
        elif isinstance(display_status, int) and not isinstance(display_status, bool):
            status_html = await self.emoji(display_status)
        elif isinstance(display_status, str):
            status_html = '<span class="emoji-status">' + self.esc(display_status) + '</span>'
        elif isinstance(display_status, dict):
            status_html = await self.image(display_status.get('document'), 'emoji')
        elif display_status is False:
            status_html = ''
        rank = getattr(message, "from_rank", None) or getattr(message, "post_author", None)
        role = "user"
        if self.options["tags"] and sender and getattr(message, "is_group", False):
            try:
                key = (str(message.peer_id), sender.id)
                if key not in self.ranks:
                    permissions = await asyncio.wait_for(self.module.client.get_permissions(message.peer_id, sender), 15)
                    resolved_role = "owner" if permissions.is_creator else "admin" if permissions.is_admin else "user"
                    resolved_rank = getattr(getattr(permissions, "participant", None), "rank", None) or (self.label("Владелец", "Owner") if permissions.is_creator else self.label("Админ", "Admin") if permissions.is_admin else '')
                    self.ranks[key] = (resolved_rank, resolved_role)
                resolved_rank, role = self.ranks[key]
                rank = rank or resolved_rank
            except Exception as error:
                self.warn("rank_unavailable", message, error)
        if getattr(message, 'display_role', None):
            role = message.display_role
        if getattr(message, 'display_rank', None) is not None:
            rank = message.display_rank
        quote_colors = self.accent_colors(palette, accent, self.options.get("gift_colors", True))
        quote_accent = None
        if self.options.get("gift_colors", True):
            quote_accent = getattr(palette, "dark_accent_color", None) if self.options["theme"] == "dark" else None
            if quote_accent is None:
                quote_accent = getattr(palette, "accent_color", None)
        quote_accent = self.color(quote_accent, accent)
        header = '<div class="author" data-quote-colors="' + quote_colors + '" data-quote-accent="' + quote_accent + '"><span class="name">' + self.esc(shown_name) + '</span>'
        header += status_html
        if rank and self.options["tags"]:
            header += ' <span class="rank" data-role="' + role + '">' + self.esc(rank) + '</span>'
        if via:
            header += ' <span class="via-inline">' + self.esc(via) + '</span>'
        header += '</div>'
        return avatar, header, accent

    async def reply(self, message):
        info = getattr(message, "reply_to", None)
        if not info:
            return ''
        if getattr(info, "forum_topic", False) and not getattr(info, "quote_text", None) and getattr(info, "reply_to_msg_id", None) == getattr(info, "reply_to_top_id", None):
            return ''
        source = None
        try:
            peer = getattr(info, "reply_to_peer_id", None) or message.peer_id
            key = (str(peer), getattr(info, "reply_to_msg_id", None))
            if key[1]:
                if key not in self.replies:
                    result = await asyncio.wait_for(self.module.client.get_messages(peer, ids=key[1]), 20)
                    self.replies[key] = next((x for x in result if x), None) if isinstance(result, (list, tuple)) else result
                source = self.replies[key]
            name = self.label("Ответ", "Reply")
            if source:
                sender = await self.peer(getattr(source, "from_id", None) or source.peer_id)
                name = getattr(source, 'display_name', None) or self.name(sender)
            else:
                sender = None
            reply_author = self.esc(self.short_quote_name(name))
            forwarded = getattr(source, "fwd_from", None)
            if forwarded:
                forwarded_name = getattr(forwarded, "from_name", None) or getattr(forwarded, "post_author", None)
                getter = getattr(self.module, '_custom_name', None)
                if callable(getter) and getattr(forwarded, 'from_id', None):
                    forwarded_name = getter(forwarded.from_id) or forwarded_name
                if not forwarded_name and getattr(forwarded, "from_id", None):
                    try:
                        forwarded_name = self.name(await self.peer(forwarded.from_id))
                    except Exception as error:
                        self.warn("reply_forward_sender_unavailable", forwarded, error)
                if forwarded_name:
                    reply_author += ' <span class="reply-forward"><span class="reply-forward-icon"></span> ' + self.esc(forwarded_name) + '</span>'
            quote = getattr(info, "quote_text", None)
            text = quote if quote is not None else getattr(source, "message", None)
            entities = getattr(info, "quote_entities", []) if quote is not None else getattr(source, "entities", [])
            if text is None:
                text = '' if source else self.label("Сообщение недоступно", "Message unavailable")
            body = await self.entities(text, entities)
            document=getattr(getattr(source,'media',None),'document',None)
            sticker_attr=next((a for a in getattr(document,'attributes',[]) or [] if self.kind(a)=='DocumentAttributeSticker'),None)
            sticker=sticker_attr is not None
            if not text and quote is None and source:
                media = getattr(source, "media", None)
                document = getattr(media, "document", None)
                if document:
                    filename = next((a.file_name for a in getattr(document, "attributes", []) if self.kind(a) == "DocumentAttributeFilename"), None)
                    label = self.label('Стикер','Sticker') if sticker else filename or self.label("Файл", "File")
                    if sticker and getattr(sticker_attr,'alt',None): label+=' '+sticker_attr.alt
                    body = '<span class="reply-media">'+('' if sticker else '<span class="reply-file-icon"></span> ') + self.esc(label) + '</span>'
                elif getattr(media, "photo", None):
                    body = '<span class="reply-media">' + self.label("Фото", "Photo") + '</span>'
                else:
                    body = self.esc(self.label("Сообщение", "Message"))
            palette = getattr(sender, "color", None)
            reply_accent = getattr(palette, "dark_accent_color", None) if self.options["theme"] == "dark" else None
            reply_accent = reply_accent if reply_accent is not None else getattr(palette, "accent_color", None)
            palette_id = getattr(palette, "color", None)
            if reply_accent is None and self.palettes.get(palette_id):
                reply_accent = self.palettes[palette_id][0]
            ordinary_id = palette_id if isinstance(palette_id, int) and 0 <= palette_id < len(self.PEER_COLORS) else abs(getattr(sender, "id", 0)) % len(self.PEER_COLORS)
            reply_color = self.color(reply_accent, self.PEER_COLORS[ordinary_id] if sender else "#79b8e8")
            pattern = await self.pattern(identity=getattr(palette, "background_emoji_id", None), color=reply_color)
            gift_id = getattr(palette, "gift_emoji_id", None)
            gift_image = await self.emoji(gift_id, alt="") if gift_id else ''
            if gift_id and not gift_image:
                self.warn("reply_gift_unavailable", palette)
            gift = '<div class="reply-gift">' + gift_image + '</div>' if gift_image else ''
            thumbnail = ''
            photo = getattr(getattr(source, "media", None), "photo", None)
            if photo:
                thumbnail = await self.image(photo, "reply-thumb")
            if not thumbnail:
                document = getattr(getattr(source, "media", None), "document", None)
                if sticker:
                    thumbnail=await self.image(document,'reply-thumb reply-sticker')
                elif getattr(document, "thumbs", None):
                    thumbnail = await self.image(document, "reply-thumb", -1)
            quote_colors = self.accent_colors(palette, reply_color)
            return '<div class="reply"'+(' data-reply-sticker="1"' if sticker else '')+' style="--accent:' + reply_color + '" data-quote-colors="' + quote_colors + '">' + pattern + gift + thumbnail + '<div class="reply-content"><div class="reply-author">' + reply_author + '</div><div class="reply-text">' + body + '</div></div></div>'
        except Exception as error:
            self.warn("reply_unavailable", info, error)
            return self.notice(self.label("Ответ: сообщение недоступно", "Reply: message unavailable"))

    async def message(self, message, grouped=False):
        self.state["message_id"] = message.id
        self.state["element"] = "Message"
        action=getattr(message,'action',None)
        if action and self.kind(action) not in ('MessageActionStarGift','MessageActionStarGiftUnique'):
            actor=None
            try:
                actor=self.name(await self.peer(getattr(message,'from_id',None) or getattr(message,'sender_id',None)))
            except Exception as error:
                self.warn('service_sender_unavailable',action,error)
            return f'<div class="service-row" data-message="{message.id}">'+await self.action(action,actor,message)+'</div>'
        prefix = ''
        forwarded = getattr(message, "fwd_from", None)
        if forwarded:
            name = getattr(forwarded, "from_name", None) or getattr(forwarded, "post_author", None)
            getter = getattr(self.module, '_custom_name', None)
            if callable(getter) and getattr(forwarded, 'from_id', None):
                name = getter(forwarded.from_id) or name
            if not name and getattr(forwarded, "from_id", None):
                try:
                    name = self.name(await self.peer(forwarded.from_id))
                except Exception as error:
                    self.warn("forward_sender_unavailable", forwarded, error)
            prefix += '<div class="forward">' + self.label("Переслано от ", "Forwarded from ") + self.esc(name or self.label("скрытый автор", "hidden sender")) + '</div>'
        bot = getattr(message, "via_bot_id", None) or getattr(message, "via_business_bot_id", None)
        via = getattr(message, 'display_via', None)
        if bot:
            try:
                bot_peer = await self.peer(bot)
                username = self.username(bot_peer)
                via = self.label("через ", "via ") + ("@" + username if username else self.name(bot_peer))
            except Exception as error:
                self.warn("bot_unavailable", message, error)
        avatar, header, accent = await self.author(message, via=via)
        reply = await self.reply(message)
        rich = getattr(message, "rich_message", None)
        rich_placeholder = self.kind(getattr(message, "media", None)) == "MessageMediaUnsupported"
        rich_suspected = rich_placeholder or bool(not getattr(message, "message", None) and
                                                   getattr(message, "media", None) is None and
                                                   not getattr(message, "action", None))
        if (rich and getattr(rich, "part", False)) or (rich_suspected and not rich):
            failure = None
            for method in ("rich", "message"):
                try:
                    if method == "rich":
                        result = await asyncio.wait_for(
                            self.module.client(functions.messages.GetRichMessageRequest(message.peer_id, message.id)), 20
                        )
                        full = next((m for m in getattr(result, "messages", []) or []
                                     if getattr(m, "id", None) == message.id), None)
                    else:
                        result = await asyncio.wait_for(
                            self.module.client.get_messages(message.peer_id, ids=message.id), 20
                        )
                        full = next((m for m in result if getattr(m, "id", None) == message.id), None) if isinstance(result, (list, tuple)) else result
                    candidate = getattr(full, "rich_message", None)
                    if candidate and getattr(candidate, "blocks", None):
                        rich = candidate
                        if not getattr(rich, "part", False):
                            break
                except Exception as error:
                    failure = error
            if not rich or not getattr(rich, "blocks", None):
                if rich_placeholder:
                    self.warn("rich_message_unavailable", message, failure)
                rich = None
            elif getattr(rich, "part", False):
                self.warn("rich_message_partial", message, failure)
        if rich:
            self.documents.update({d.id: d for d in getattr(rich, "documents", []) or []})
            self.photos.update({p.id: p for p in getattr(rich, "photos", []) or []})
            body = '<div class="rich"' + (' dir="rtl"' if getattr(rich, "rtl", False) else '') + '>' + await self.blocks(rich.blocks) + '</div>'
        elif getattr(message, "action", None):
            body = await self.action(message.action)
        elif rich_placeholder:
            body = self.notice(self.label("Rich-сообщение недоступно", "Rich message unavailable"))
        else:
            text = '<div class="body" dir="auto">' + await self.entities(getattr(message, "message", ""), getattr(message, "entities", [])) + '</div>'
            message_media = getattr(message, "media", None)
            media = await self.media(message_media)
            if (self.kind(message_media) == 'MessageMediaWebPage'
                    and self.options.get('link_preview_position', 'bottom') == 'bottom'):
                body = text + media
            else:
                body = media + text
        reactions = ''
        if self.options["reactions"]:
            for entry in getattr(getattr(message, "reactions", None), "results", []) or []:
                reaction = entry.reaction
                emoji = await self.emoji(reaction.document_id) if hasattr(reaction, "document_id") else self.esc(getattr(reaction, "emoticon", "⭐"))
                reactions += f'<span class="reaction">{emoji} {entry.count}</span>'
        buttons = ''
        for row in getattr(getattr(message, "reply_markup", None), "rows", []) or []:
            buttons += '<div class="buttons">'
            for button in row.buttons:
                style = getattr(button, "style", None)
                color = next((name for name in ("primary", "danger", "success") if getattr(style, "bg_" + name, False)), '')
                icon_id = getattr(style, "icon", None)
                icon = (await self.emoji(icon_id) + ' ') if icon_id else ''
                buttons += '<span class="button" data-button-style="' + color + '">' + icon + self.esc(button.text) + '</span>'
            buttons += '</div>'
        metadata = []
        if getattr(message, "views", None) is not None:
            metadata.append('<span class="views-icon"></span> ' + self.esc(str(message.views)))
        if getattr(message, "pinned", False):
            metadata.append('<span class="pin-icon"></span>')
        if self.options["dates"] and getattr(message, "date", None):
            metadata.append(self.esc(getattr(message, 'display_time', None) or self.local_date(message.date).strftime("%H:%M")))
        classes = 'row' + (' grouped' if grouped else '') + (' noavatar' if not self.options["avatars"] else '')
        return f'<div class="{classes}" data-message="{message.id}" style="--accent:{accent}">{avatar}<div class="bubble">{header}{prefix}{reply}{body}<div class="reactions">{reactions}</div>{buttons}<div class="meta">{" · ".join(metadata)}</div></div></div>'

    async def build(self, state):
        self.state = state
        timezone_getter = getattr(self.module, "_quote_timezone", None)
        self.quote_timezone = timezone_getter() if callable(timezone_getter) else None
        self.options = state["options"]
        self.ru = state["ru"]
        self.documents, self.photos, self.animations = {}, {}, {}
        self.animation_count = 0
        self.peers, self.replies, self.ranks, self.palettes = {}, {}, {}, {}
        self.peers.update(state.get('resolved_peers', {}))
        self.replies.update(state.get('resolved_replies', {}))
        self.block_count = 0
        state["warnings"] = []
        state["stage"] = "collect"
        await self._prime_emoji(state["messages"])
        try:
            response = await asyncio.wait_for(self.module.client(functions.help.GetPeerColorsRequest(hash=0)), 15)
            for item in getattr(response, "colors", []):
                palette = getattr(item, "dark_colors", None) if self.options["theme"] == "dark" else None
                palette = palette or getattr(item, "colors", None)
                self.palettes[item.color_id] = getattr(palette, "colors", [])
        except Exception as error:
            self.warn("palettes_unavailable", error=error)
        rows = []
        previous = None
        messages = [m for m in state["messages"] if m.id in state["selected"]]
        album_ids = {getattr(m, "grouped_id", None) for m in messages if getattr(m, "grouped_id", None)}
        handled = set()
        for message in messages:
            if message.id not in state["selected"]:
                continue
            if message.id in handled:
                continue
            date = getattr(message, "date", None)
            prev_date = getattr(previous, "date", None)
            grouped = bool(previous and getattr(previous, "from_id", None) == getattr(message, "from_id", None) and date and prev_date and (date-prev_date).total_seconds() < 300 and not getattr(message,"reply_to",None))
            if getattr(previous,'action',None) or getattr(message,'action',None): grouped=False
            if grouped and any(getattr(previous, field, None) != getattr(message, field, None) for field in ("via_bot_id", "via_business_bot_id", "out")):
                grouped = False
            album_id = getattr(message, "grouped_id", None)
            album = [m for m in messages if getattr(m, "grouped_id", None) == album_id] if album_id in album_ids else []
            if len(album) > 1 and all(self.kind(getattr(m, "media", None)) == "MessageMediaPhoto" for m in album):
                combined = copy.copy(message)
                combined.media = None
                combined.message = ''
                combined.entities = []
                base = await self.message(combined, grouped)
                photos = '<div class="grid">' + ''.join([await self.media(m.media) for m in album]) + '</div>'
                captions = ''.join([('<div class="body">' + await self.entities(getattr(m,"message",""),getattr(m,"entities",[])) + '</div>') for m in album if getattr(m,"message",None)])
                rows.append(base.replace('<div class="body" dir="auto"></div>', photos + captions, 1))
                handled.update(m.id for m in album)
            else:
                rows.append(await self.message(message, grouped))
            previous = message
        if not rows:
            raise _GQuoteError("no_selected_messages")
        css_class = self.options["theme"] + (' transparent' if not self.options["background"] else '')
        return '<!doctype html><meta charset="utf-8"><style>' + self.CSS + f'</style><div id="quote" class="{css_class}" style="width:{self.options["width"]}px">' + ''.join(rows) + '</div>'

    async def _prime_emoji(self, messages):
        identities = set()
        visited = 0
        def visit(value, depth=0):
            nonlocal visited
            visited += 1
            if depth > 24 or visited > 12000 or value is None or isinstance(value, (str, int, float, bytes)):
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    visit(item, depth + 1)
                return
            if self.kind(value) in ("MessageEntityCustomEmoji", "TextCustomEmoji", "ReactionCustomEmoji"):
                identity = getattr(value, "document_id", None)
                if identity:
                    identities.add(identity)
            if self.kind(value) == "RichMessage":
                self.documents.update({d.id:d for d in getattr(value, "documents", []) or []})
            for name in ("blocks", "items", "rows", "cells", "buttons", "text", "texts", "caption", "rich_message", "entities", "reaction", "results", "reactions", "title"):
                child = getattr(value, name, None)
                if child is not None:
                    visit(child, depth + 1)
        visit(messages)
        missing = sorted(identities - self.documents.keys())
        for offset in range(0, len(missing), 80):
            try:
                docs = await asyncio.wait_for(self.module.client(
                    functions.messages.GetCustomEmojiDocumentsRequest(missing[offset:offset + 80])), 20)
                self.documents.update({d.id:d for d in docs})
            except Exception as error:
                self.warn("emoji_prefetch_failed", error=error)
                break

    async def render(self, state):
        try:
            await asyncio.wait_for(self.lock.acquire(), 120)
        except TimeoutError as error:
            raise _GQuoteError("render_queue_timeout") from error
        try:
            if self.closed:
                raise _GQuoteError("renderer_closed")
            self.state = state
            task = asyncio.current_task()
            self.tasks.add(task)
            try:
                return await asyncio.wait_for(self._render(state), 240)
            finally:
                self.tasks.discard(task)
        finally:
            self.lock.release()

    async def _font_paths(self, markup=""):
        candidates = {
            "regular": ("DejaVuSans.ttf", "arial.ttf"),
            "bold": ("DejaVuSans-Bold.ttf", "arialbd.ttf"),
            "italic": ("DejaVuSans-Oblique.ttf", "ariali.ttf"),
            "bolditalic": ("DejaVuSans-BoldOblique.ttf", "arialbi.ttf"),
            "mono": ("DejaVuSansMono.ttf", "consola.ttf"),
            "symbols": ("DejaVuSans.ttf", "seguisym.ttf"),
        }
        bases = (Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"),
                 Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts")
        paths = {}
        for name, files in candidates.items():
            path = next((base / filename for base in bases for filename in files if (base / filename).is_file()), None)
            if name == "symbols":
                if path:
                    paths[name] = str(path)
                continue
            try:
                paths[name] = await self.library("font_" + name)
            except Exception as error:
                self.warn("font_" + name + "_unavailable", error=error)
                if path:
                    paths[name] = str(path)
        if "regular" not in paths:
            raise _GQuoteError("text_font_missing")
        text = quote_html.unescape(markup)
        script_text = ''.join(set(char for char in text if ord(char) > 127))
        if re.search(r'[\U0001f100-\U0001f1ff]', text):
            try:
                paths["symbols"] = await self.library("font_symbols")
            except Exception as error:
                self.warn("font_symbols_unavailable", error=error)
        if script_text:
            import regex as script_regex
            for family, script in (*self.SCRIPT_FONTS.items(), *self.SERIF_FONTS.items()):
                if not script_regex.search(r'\p{Script=' + script + r'}', script_text):
                    continue
                try:
                    paths[family] = await self.library('font_'+family)
                except Exception as error:
                    self.warn('font_'+family+'_unavailable', error=error)
        for family, (_, pattern) in self.EXTRA_FONTS.items():
            if re.search(pattern, script_text):
                try:
                    paths[family] = await self.library('font_'+family)
                except Exception as error:
                    self.warn('font_'+family+'_unavailable', error=error)
        if re.search(r'[\u2200-\u22ff\u27c0-\u27ef\u2980-\u2aff\U0001d400-\U0001d7ff]', script_text):
            try:
                paths["math"] = await self.library("font_math")
            except Exception as error:
                self.warn("font_math_unavailable", error=error)
        if re.search(r'[\u2100-\u2bff\U0001d100-\U0001d1ff\U0001f000-\U0001f0ff]', script_text):
            try:
                paths["symbols2"] = await self.library("font_symbols2")
            except Exception as error:
                self.warn("font_symbols2_unavailable", error=error)
        if re.search(r'[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\U00020000-\U0003134f]', script_text):
            cjk_candidates = (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                              Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
                              Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msgothic.ttc")
            cjk = next((p for p in cjk_candidates if p.is_file()), None)
            try:
                paths["cjk"] = str(cjk) if cjk else await self.library("font_cjk")
            except Exception as error:
                self.warn("font_cjk_unavailable", error=error)
        if re.search(r'[\u1100-\u11ff\u3130-\u318f\uac00-\ud7ff]', script_text):
            try:
                paths["hangul"] = await self.library("font_hangul")
            except Exception as error:
                self.warn("font_hangul_unavailable", error=error)
        try:
            paths["emoji"] = await self.library("emoji_font")
        except Exception as error:
            self.warn("emoji_font_fallback", error=error)
        return paths

    async def _render(self, state):
        import sys
        import signal
        started = time.monotonic()
        if self.cache_size > 32 * 1024 * 1024:
            for key, cached in tuple(self.cache.items()):
                if key.startswith(("media:", "avatar:")):
                    path = Path(cached)
                    if path.exists():
                        self.cache_size -= path.stat().st_size
                        path.unlink()
                    del self.cache[key]
        markup = await self.build(state)
        if len(markup.encode("utf8")) > 8 * 1024 * 1024:
            raise _GQuoteError("markup_bytes_limit")
        state["stage"] = "fonts"
        fonts = await self._font_paths(markup)
        with tempfile.TemporaryDirectory(prefix="render-", dir=self.root.name) as folder:
            job = Path(folder)
            worker = job / "worker.py"
            request = job / "request.json"
            response = job / "response.json"
            progress = job / "progress.json"
            render_options = dict(state['options'], sticker=state.get('output')=='sticker')
            if not render_options['sticker']:
                render_options['scale'] = 4
            payload = dict(root=self.root.name, output=folder, response=str(response),
                           progress=str(progress), html=markup, fonts=fonts,
                           options=render_options)
            mode=state['options'].get('background_mode','transparent')
            if mode in ('dark','light'):
                payload['options']['background_color']='#181b1e' if mode=='dark' else '#dce5e9'
            elif mode=='custom':
                import base64
                cached=self.module.get('gquote_background_cache',{})
                if not isinstance(cached,dict) or cached.get('url')!=state['options'].get('background_url'):
                    raise _GQuoteError('custom_background_missing')
                wallpaper=job/'wallpaper.webp'
                await utils.run_sync(wallpaper.write_bytes,base64.b64decode(cached['data']))
                payload['wallpaper']=str(wallpaper)
            await utils.run_sync(worker.write_text, _GQUOTE_PILLOW_WORKER, encoding="utf8")
            await utils.run_sync(request.write_text, json.dumps(payload, ensure_ascii=True), encoding="utf8")
            state["stage"] = "pillow_worker"
            environment = dict(os.environ)
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
                environment[key] = "1"
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(worker), str(request),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                env=environment,
                start_new_session=os.name != "nt",
            )
            stderr = bytearray()
            async def drain_errors():
                while chunk := await process.stderr.read(4096):
                    stderr.extend(chunk)
                    if len(stderr) > 8192:
                        del stderr[:-8192]
            reader = asyncio.create_task(drain_errors())
            try:
                try:
                    result = await asyncio.wait_for(process.wait(), 150)
                except TimeoutError as error:
                    raise _GQuoteError("pillow_worker_timeout") from error
                await asyncio.wait_for(asyncio.shield(reader), 5)
                if result:
                    detail = bytes(stderr).decode("utf8", "replace")
                    missing = re.search(r"ModuleNotFoundError: No module named '([\w.]+)'", detail)
                    if missing:
                        raise _GQuoteError("worker_dependency_missing_" + missing[1])
                    if "ENOSPC" in detail or "No space left on device" in detail:
                        raise _GQuoteError("storage_full")
                    if "MemoryError" in detail:
                        raise _GQuoteError("worker_memory_limit")
                    raise _GQuoteError(f"pillow_worker_exit_{result}")
                if not response.is_file() or response.stat().st_size > 256 * 1024:
                    raise _GQuoteError("pillow_worker_response_missing")
                answer = json.loads(await utils.run_sync(response.read_text, encoding="utf8"))
                if answer.get("error"):
                    state["stage"] = answer.get("stage", "pillow_worker")
                    state["message_id"] = answer.get("message")
                    logger.error("gquote op=%s stage=%s document=%s exception=%s trace=%s",
                                 state["id"], state["stage"], answer.get("document"), answer["error"],
                                 " > ".join(answer.get("trace", [])))
                    raise _GQuoteError("pillow_" + answer["error"])
                for warning in answer.get("warnings", []):
                    entry = warning["code"]
                    if entry not in state["warnings"]:
                        state["warnings"].append(entry)
                    logger.warning("gquote op=%s stage=pillow_worker message=%s document=%s code=%s exception=%s trace=%s",
                                   state["id"], warning.get("message"), warning.get("document"), entry, warning.get("exception"),
                                   " > ".join(warning.get("trace", [])))
                pages = []
                names = answer.get("pages", [])
                if not 1 <= len(names) <= self.MAX_PAGES:
                    raise _GQuoteError("output_pages_limit")
                for name in names:
                    if not re.fullmatch(r"page-\d+\.png", name):
                        raise _GQuoteError("invalid_output_path")
                    path = job / name
                    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
                        raise _GQuoteError("output_bytes_limit")
                    pages.append(await utils.run_sync(path.read_bytes))
                    if sum(map(len, pages)) > 64 * 1024 * 1024:
                        raise _GQuoteError("output_bytes_limit")
                self.log("info", f"pillow_ok_pages_{len(pages)}_ms_{int((time.monotonic()-started)*1000)}")
                return pages
            finally:
                if process.returncode is None:
                    try:
                        if os.name == "nt":
                            process.kill()
                        else:
                            os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await process.wait()
                if not reader.done():
                    reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
                if progress.is_file() and progress.stat().st_size < 4096:
                    try:
                        checkpoint = json.loads(await utils.run_sync(progress.read_text, encoding="utf8"))
                        self.log("info", "worker_checkpoint_" + checkpoint.get("stage", "unknown"),
                                 state=dict(state, message_id=checkpoint.get("message"),
                                            element="document:" + str(checkpoint.get("document"))))
                    except Exception:
                        pass

class _HelpCommandName(str):

    def __new__(cls, name, rank):
        value = super().__new__(cls, name)
        value._help_rank = rank
        return value

    def __lt__(self, other):
        return (self._help_rank, str(self)) < (
            getattr(other, "_help_rank", float("inf")), str(other)
        )


@loader.tds
class GodChatMod(loader.Module):

    _HELP_COMMAND_ORDER = (
        "gcfg", "ban", "unban", "gban", "gunban", "mute", "dmute", "unmute", "kick",
        "del", "purge", "req", "panic", "banchat",
        "banmedia", "unbanmedia",
        "id", "member", "rmember", "prefix", "aclear",
        "gq", "fq", "mfq", "guest", "inline",
    )

    @property
    def commands(self):
        commands = super().commands
        names = [name for name in self._HELP_COMMAND_ORDER if name in commands]
        names.extend(name for name in commands if name not in self._HELP_COMMAND_ORDER)
        return {
            _HelpCommandName(name, rank): commands[name]
            for rank, name in enumerate(names)
        }

    @commands.setter
    def commands(self, _):
        pass

    strings = {
        "name": "GodChat",
        "reason": "Reason",
        "duration": "Duration",
        "messages_deleted": "Messages: deleted",
        "messages_delete_failed": "Messages: could not be deleted",
        "status": "Status",
        "groups_only": "This command only works in groups.",
        "reply_or_user": "Reply to a message or specify @username or ID.",
        "self_action": "You cannot apply this action to yourself.",
        "member_rights_failed": "Could not get the member or their permissions.",
        "rank_error": "Enter a tag up to 16 characters long without emoji.",
        "tag": "Tag",
        "tag_type": "Type",
        "tag_regular": "regular",
        "tag_admin": "admin",
        "creator_regular_tag": "The creator cannot receive a regular tag.",
        "tag_changed_demote_failed": "The tag was changed, but admin rights could not be removed.",
        "tag_change_failed": "Could not change the tag. Check tag-management rights and make sure the text has no emoji.",
        "admin_tag_supergroup": "An admin tag without separate permissions is only available in a supergroup.",
        "admin_tag_failed": "Could not set the admin tag. Check the permission to add admins, tag length and emoji.",
        "admin_tag_rights": "Not enough rights to set an admin tag.",
        "aclear_rights": "Administrator and tag-management rights are required.",
        "aclear_list_failed": "Could not get the administrator list.",
        "aclear_result": "Admin rights removed: {removed}. Failed: {failed}. Tags not preserved: {tag_failed}.",
        "role_creator": "Creator",
        "role_admin": "Admin",
        "role_member": "Member",
        "media": "Media or attachment",
        "activity_unchecked": "Activity has not been checked yet.",
        "activity": "Activity for {months} mo.",
        "messages_short": "msgs.",
        "inline_forbidden": "Inline: forbidden",
        "banned": "Banned",
        "kicked": "Kicked",
        "not_in_chat": "Not in chat",
        "unknown": "unknown",
        "common_chats": "Common chats",
        "joined": "Joined",
        "last_message": "Last message",
        "last_message_missing": "Last message was not found.",
        "message": "Message",
        "user_banned": "The user is banned.",
        "user_kicked": "The user was kicked from the chat.",
        "user_unbanned": "The user was unbanned and is not in the chat.",
        "random_member": "Random member",
        "member_card": "Member card",
        "inline_allow": "🧩 Allow inline",
        "inline_forbid": "🧩 Forbid inline",
        "unban_button": "🔓 Unban",
        "kick_button": "🚪 Kick",
        "ban_button": "🚫 Ban",
        "profile_button": "👤 Open profile",
        "last_message_button": "💬 Open last message",
        "copy_id_button": "📋 Copy ID",
        "one_month_button": "📊 1 month",
        "three_months_button": "📊 3 months",
        "previous_button": "⬅️ Previous",
        "next_button": "🎲 Next",
        "close_button": "✖️ Close",
        "tag_button": "✏️ Tag",
        "admin_tag_button": "🛡 Admin tag",
        "tag_input": "Enter a tag",
        "admin_tag_input": "Enter an admin tag",
        "card_expired": "The card has expired. Run the command again.",
        "action_running": "The previous action is still running",
        "first_member": "This is the first selected member",
        "member_select_failed": "Could not select another regular member.",
        "unknown_period": "Unknown period",
        "activity_counting": "Counting activity for {months} mo...",
        "activity_failed": "Could not check activity in this chat.",
        "no_restriction_rights": "Not enough rights to change restrictions.",
        "personal_restrictions_supergroup": "Personal restrictions are only available in a supergroup.",
        "member_rights_refresh_failed": "Could not refresh member permissions.",
        "inline_member_only": "Inline restriction is only available for a member.",
        "inline_chat_forbidden": "Inline is forbidden for the entire chat. Use .inline -all.",
        "inline_change_failed": "Could not change the inline restriction.",
        "inline_forbidden_notice": "Inline is forbidden.",
        "inline_allowed_notice": "Inline is allowed.",
        "member_rights_update_failed": "Could not refresh user permissions.",
        "tag_rights_missing": "Not enough rights to change the tag.",
        "tag_input_error": "The tag must contain up to 16 characters without emoji.",
        "admin_tag_only_supergroup": "An admin tag is only available in a supergroup.",
        "member_kick_rights": "Not enough rights to remove members.",
        "member_admin": "The user is already an administrator.",
        "member_kicked": "Member removed",
        "member_kick_failed": "Could not remove the member. Check permissions.",
        "member_ban_rights": "Not enough rights to ban members.",
        "member_banned": "Member banned",
        "member_ban_failed": "Could not ban the member. Check permissions.",
        "member_unban_rights": "Not enough rights to unban members.",
        "member_unbanned": "Member unbanned",
        "member_unban_failed": "Could not unban the member. Check permissions.",
        "tag_changed": "{tag_type} changed: {rank}",
        "menu_open_failed": "Could not open the menu.",
        "reply_or_one_user": "Reply to a message or specify one user.",
        "member_card_open_failed": "Could not open the member card.",
        "inline": "Inline",
        "forbidden": "forbidden",
        "allowed": "allowed",
        "purge_reply": "Reply to the start of the range.",
        "other_topic": "The message is in another topic.",
        "invalid_range": "Invalid message range.",
        "delete_rights_missing": "No permission to delete messages.",
        "deleted": "Deleted",
        "reply_or_user_and_amount": "Reply to a message or specify a user and amount.",
        "message_delete_failed": "Could not delete the message.",
        "amount_or_all": "Specify an amount or <code>-all</code>.",
        "positive_amount": "The amount must be a positive number.",
        "all_messages": "all messages",
        "messages_delete_permissions_failed": "Could not delete messages. Check account permissions.",
        "deletion": "Deletion",
        "removed_from_basic_group": "removed from a basic group",
        "banned_action": "banned",
        "working": "Working...",
        "creator_ban_forbidden": "The chat creator cannot be demoted or banned.",
        "demoted_ban_failed": "Admin rights were removed, but the ban failed.",
        "demote_ban_failed": "Could not demote the admin and ban them.",
        "ban_title": "Ban",
        "confirmation": "Confirmation",
        "administrator": "Administrator",
        "admin_will_be_demoted": "rights will be removed before the ban",
        "messages": "Messages",
        "will_be_deleted": "will be deleted",
        "demote_and_ban_button": "🚫 Demote and ban",
        "cancel_button": "✖️ Cancel",
        "confirmation_open_failed": "Could not open the confirmation.",
        "ban_failed": "Could not ban the user. Check account permissions.",
        "basic_group_no_bans": "A basic group has no blocked-user list.",
        "unban_failed": "Could not unban the user. Check account permissions.",
        "unban_title": "Unban",
        "unbanned_action": "unbanned",
        "confirmation_expired": "The confirmation has expired.",
        "removing_deleted_accounts": "Removing deleted accounts...",
        "admin_list_refresh_failed": "Could not refresh the administrator list.",
        "kicked_count": "Kicked",
        "member_list_failed": "Could not get the member list.",
        "no_deleted_accounts": "There are no deleted accounts in the chat.",
        "deleted_accounts": "Deleted accounts",
        "will_be_kicked": "Will be kicked",
        "creator_kick_forbidden": "The chat creator cannot be kicked.",
        "demote_admin_first": "Remove the user's administrator rights first.",
        "kick_failed": "Could not kick the user. Check account permissions.",
        "kick_title": "Kick",
        "removed_from_chat": "removed from the chat",
        "duration_seconds": "second|seconds|seconds",
        "duration_minutes": "minute|minutes|minutes",
        "duration_hours": "hour|hours|hours",
        "duration_days": "day|days|days",
        "duration_years": "year|years|years",
        "duration_messages": "message|messages|messages",
        "forever": "forever",
        "invalid_time": "Invalid time.",
        "duration_format": "<code>1s, 2m, 3h, 4d, 5y</code> or <code>1с, 2м, 3ч, 4д, 5л</code>.\n<code>4года</code> and <code>5 лет</code> are also supported.\nA number without a letter means minutes.",
        "chat_fetch_failed": "Could not get the chat.", "chat_only": "This command is only available in a chat.", "supergroup_panic_only": "Panic is only available in a supergroup.", "chat_or_channel_only": "This command is only available in a chat or channel.", "requests_failed": "Could not clear join requests. Check permissions.", "requests_cleared": "Join requests cleared", "requests_none": "There are no join requests.", "requests_rights": "Not enough rights to manage join requests.", "requests_title": "Join requests", "requests_count": "Join requests", "requests_reject_all": "All requests will be declined.", "requests_clear_button": "🗑 Clear all", "requests_cleanup_scheduled": "Cleanup is already scheduled.", "continues_at": "It will continue at", "new_requests": "New requests", "no_arguments": "This command does not accept arguments.", "inline_all_status": "For regular members", "reply_or_all_inline": "Reply to a member or use <code>-all</code>.", "admin_restrict_forbidden": "An administrator cannot be restricted.", "member_not_in_chat": "The member is not in the chat.", "inline_all_already_forbidden": "Inline is already forbidden for the entire chat.", "inline_all_allow_hint": "Use <code>.inline -all</code> to allow it for everyone.", "chat_open_failed": "Could not open the chat. Check permissions.", "banchat_off": "Banchat disabled", "chat_stays_closed_panic": "The chat remains closed because panic is enabled.", "chat_opened": "Chat opened", "close_chat_failed": "Could not close the chat. Check permissions.", "chat_closed": "Chat closed", "repeat_opens_chat": "Run the command again to open the chat.", "banchat_finished": "Banchat duration has ended", "close_time_ended": "The closing time has ended.", "panic_disable_failed": "Could not disable panic. Check permissions.", "panic_off": "Panic disabled", "panic_restored": "Slow mode and join requests were restored.", "chat_closed_by_banchat": "The chat remains closed through banchat.", "panic_enable_failed": "Could not enable panic. Check chat-management and join-request permissions.", "panic_on": "Panic enabled", "panic_enabled_details": "<b>Chat:</b> closed\n<b>Slow mode:</b> 1 hour\n<b>Joining:</b> by requests\nRun the command again to restore the previous settings.", "creator_mute_forbidden": "The chat creator cannot be muted.", "mute_basic_group": "Mute is unavailable in a basic group. Convert it to a supergroup.", "mute_basic_group_short": "Mute is unavailable in a basic group.", "mute_failed": "Could not mute the user. Check account permissions.", "mute_title": "Mute", "muted_action": "muted", "unmute_failed": "Could not unmute the user. Check account permissions.", "unmute_title": "Unmute", "restrictions_removed": "restrictions removed", "seconds_short": "sec.", "try_later": "Try again later.",
    }

    strings_ru = {
        "name": "GodChat",
        "reason": "Причина",
        "duration": "Срок",
        "messages_deleted": "Сообщения: удалены",
        "messages_delete_failed": "Сообщения: не удалось удалить",
        "status": "Статус",
        "groups_only": "Команда работает только в группах.",
        "reply_or_user": "Ответь на сообщение или укажи @username либо ID.",
        "self_action": "Нельзя применить это действие к себе.",
        "member_rights_failed": "Не удалось получить участника или его права.",
        "rank_error": "Укажи префикс длиной до 16 символов без эмодзи.",
        "tag": "Префикс",
        "tag_type": "Тип",
        "tag_regular": "обычный",
        "tag_admin": "админский",
        "creator_regular_tag": "Создателю нельзя выдать обычный префикс.",
        "tag_changed_demote_failed": "Префикс изменён, но снять админку не удалось.",
        "tag_change_failed": "Не удалось изменить префикс. Проверь права управления префиксами и убедись, что в тексте нет эмодзи.",
        "admin_tag_supergroup": "Админ-префикс без отдельных прав доступен только в супергруппе.",
        "admin_tag_failed": "Не удалось выдать админ-префикс. Проверь право добавления администраторов, длину и отсутствие эмодзи.",
        "admin_tag_rights": "Недостаточно прав для установки админ-префикса.",
        "aclear_rights": "Нужны права назначать администраторов и менять префиксы.",
        "aclear_list_failed": "Не удалось получить список администраторов.",
        "aclear_result": "Снята админка: {removed}. Ошибок: {failed}. Не удалось сохранить префикс: {tag_failed}.",
        "role_creator": "Создатель",
        "role_admin": "Админ",
        "role_member": "Участник",
        "media": "Медиа или вложение",
        "activity_unchecked": "Активность ещё не проверялась.",
        "activity": "Активность за {months} мес.",
        "messages_short": "сообщ.",
        "inline_forbidden": "Инлайн: запрещён",
        "banned": "Забанен",
        "kicked": "Кикнут",
        "not_in_chat": "Не состоит в чате",
        "unknown": "неизвестно",
        "common_chats": "Общие чаты",
        "joined": "Дата вступления",
        "last_message": "Последнее сообщение",
        "last_message_missing": "Последнее сообщение не найдено.",
        "message": "Сообщение",
        "user_banned": "Пользователь забанен.",
        "user_kicked": "Пользователь кикнут из чата.",
        "user_unbanned": "Пользователь разбанен и не состоит в чате.",
        "random_member": "Случайный участник",
        "member_card": "Карточка пользователя",
        "inline_allow": "🧩 Разрешить инлайн",
        "inline_forbid": "🧩 Запретить инлайн",
        "unban_button": "🔓 Разбанить",
        "kick_button": "🚪 Кикнуть",
        "ban_button": "🚫 Забанить",
        "profile_button": "👤 Открыть профиль",
        "last_message_button": "💬 Открыть последнее сообщение",
        "copy_id_button": "📋 Скопировать ID",
        "one_month_button": "📊 За 1 месяц",
        "three_months_button": "📊 За 3 месяца",
        "previous_button": "⬅️ Предыдущий",
        "next_button": "🎲 Следующий",
        "close_button": "✖️ Закрыть",
        "tag_button": "✏️ Префикс",
        "admin_tag_button": "🛡 Админ-префикс",
        "tag_input": "Введите префикс",
        "admin_tag_input": "Введите админ-префикс",
        "card_expired": "Карточка устарела. Запусти команду ещё раз.",
        "action_running": "Предыдущее действие ещё выполняется",
        "first_member": "Это первый выбранный участник",
        "member_select_failed": "Не удалось выбрать другого обычного участника.",
        "unknown_period": "Неизвестный период",
        "activity_counting": "Считаю активность за {months} мес...",
        "activity_failed": "Не удалось проверить активность в этом чате.",
        "no_restriction_rights": "Недостаточно прав для изменения ограничений.",
        "personal_restrictions_supergroup": "Личные ограничения доступны только в супергруппе.",
        "member_rights_refresh_failed": "Не удалось обновить права участника.",
        "inline_member_only": "Ограничение инлайна доступно только участнику.",
        "inline_chat_forbidden": "Инлайн запрещён для всего чата. Используй .inline -all.",
        "inline_change_failed": "Не удалось изменить ограничение инлайна.",
        "inline_forbidden_notice": "Инлайн запрещён.",
        "inline_allowed_notice": "Инлайн разрешён.",
        "member_rights_update_failed": "Не удалось обновить права пользователя.",
        "tag_rights_missing": "Недостаточно прав для изменения префикса.",
        "tag_input_error": "Префикс должен содержать до 16 символов без эмодзи.",
        "admin_tag_only_supergroup": "Админ-префикс доступен только в супергруппе.",
        "member_kick_rights": "Недостаточно прав для удаления участников.",
        "member_admin": "Пользователь уже является администратором.",
        "member_kicked": "Участник удалён",
        "member_kick_failed": "Не удалось удалить участника. Проверь права.",
        "member_ban_rights": "Недостаточно прав для блокировки участников.",
        "member_banned": "Участник забанен",
        "member_ban_failed": "Не удалось забанить участника. Проверь права.",
        "member_unban_rights": "Недостаточно прав для разблокировки участников.",
        "member_unbanned": "Участник разбанен",
        "member_unban_failed": "Не удалось разбанить участника. Проверь права.",
        "tag_changed": "{tag_type} изменён: {rank}",
        "menu_open_failed": "Не удалось открыть меню.",
        "reply_or_one_user": "Ответь на сообщение или укажи одного пользователя.",
        "member_card_open_failed": "Не удалось открыть карточку участника.",
        "inline": "Инлайн",
        "forbidden": "запрещён",
        "allowed": "разрешён",
        "purge_reply": "Ответь на начало диапазона.",
        "other_topic": "Сообщение находится в другом топике.",
        "invalid_range": "Неверный диапазон сообщений.",
        "delete_rights_missing": "Нет права удаления сообщений.",
        "deleted": "Удалено",
        "reply_or_user_and_amount": "Ответь на сообщение или укажи пользователя и количество.",
        "message_delete_failed": "Не удалось удалить сообщение.",
        "amount_or_all": "Укажи количество или <code>-all</code>.",
        "positive_amount": "Количество должно быть положительным числом.",
        "all_messages": "все сообщения",
        "messages_delete_permissions_failed": "Не удалось удалить сообщения. Проверь права аккаунта.",
        "deletion": "Удаление",
        "removed_from_basic_group": "удалён из обычной группы",
        "banned_action": "забанен",
        "working": "Выполняю...",
        "creator_ban_forbidden": "Создателя чата нельзя лишить прав и забанить.",
        "demoted_ban_failed": "Права администратора сняты, но забанить не удалось.",
        "demote_ban_failed": "Не удалось снять админку и забанить.",
        "ban_title": "Бан",
        "confirmation": "Подтверждение",
        "administrator": "Администратор",
        "admin_will_be_demoted": "права будут сняты перед баном",
        "messages": "Сообщения",
        "will_be_deleted": "будут удалены",
        "demote_and_ban_button": "🚫 Снять админку и забанить",
        "cancel_button": "✖️ Отмена",
        "confirmation_open_failed": "Не удалось открыть подтверждение.",
        "ban_failed": "Не удалось забанить. Проверь права аккаунта.",
        "basic_group_no_bans": "В обычной группе нет списка заблокированных.",
        "unban_failed": "Не удалось разбанить. Проверь права аккаунта.",
        "unban_title": "Разбан",
        "unbanned_action": "разбанен",
        "confirmation_expired": "Подтверждение устарело.",
        "removing_deleted_accounts": "Удаляю удалённые аккаунты...",
        "admin_list_refresh_failed": "Не удалось обновить список администраторов.",
        "kicked_count": "Кикнуто",
        "member_list_failed": "Не удалось получить список участников.",
        "no_deleted_accounts": "Удалённых аккаунтов в чате нет.",
        "deleted_accounts": "Удалённые аккаунты",
        "will_be_kicked": "Будет кикнуто",
        "creator_kick_forbidden": "Создателя чата нельзя кикнуть.",
        "demote_admin_first": "Сначала сними с пользователя права администратора.",
        "kick_failed": "Не удалось кикнуть. Проверь права аккаунта.",
        "kick_title": "Кик",
        "removed_from_chat": "удалён из чата",
        "duration_seconds": "секунда|секунды|секунд",
        "duration_minutes": "минута|минуты|минут",
        "duration_hours": "час|часа|часов",
        "duration_days": "день|дня|дней",
        "duration_years": "год|года|лет",
        "duration_messages": "сообщение|сообщения|сообщений",
        "forever": "навсегда",
        "invalid_time": "Неверное время.",
        "duration_format": "<code>1s, 2m, 3h, 4d, 5y</code> или <code>1с, 2м, 3ч, 4д, 5л</code>.\nТакже доступны <code>4года</code> и <code>5 лет</code>.\nЧисло без буквы означает минуты.",
        "chat_fetch_failed": "Не удалось получить чат.", "chat_only": "Команда доступна только в чате.", "supergroup_panic_only": "Паника доступна только в супергруппе.", "chat_or_channel_only": "Команда доступна только в чате или канале.", "requests_failed": "Не удалось очистить заявки. Проверь права.", "requests_cleared": "Заявки очищены", "requests_none": "Заявок на вступление нет.", "requests_rights": "Недостаточно прав для заявок.", "requests_title": "Заявки", "requests_count": "Заявок на вступление", "requests_reject_all": "Все заявки будут отклонены.", "requests_clear_button": "🗑 Очистить все", "requests_cleanup_scheduled": "Очистка уже запланирована.", "continues_at": "Продолжу в", "new_requests": "Новых заявок", "no_arguments": "Команда не принимает аргументы.", "inline_all_status": "Для обычных участников", "reply_or_all_inline": "Ответь на участника или используй <code>-all</code>.", "admin_restrict_forbidden": "Нельзя ограничить администратора.", "member_not_in_chat": "Участник не состоит в чате.", "inline_all_already_forbidden": "Инлайн уже запрещён для всего чата.", "inline_all_allow_hint": "Используй <code>.inline -all</code>, чтобы разрешить его всем.", "chat_open_failed": "Не удалось открыть чат. Проверь права.", "banchat_off": "Banchat выключен", "chat_stays_closed_panic": "Чат остаётся закрыт, потому что включена паника.", "chat_opened": "Чат открыт", "close_chat_failed": "Не удалось закрыть чат. Проверь права.", "chat_closed": "Чат закрыт", "repeat_opens_chat": "Повторная команда откроет чат.", "banchat_finished": "Срок banchat завершён", "close_time_ended": "Время закрытия закончилось.", "panic_disable_failed": "Не удалось выключить панику. Проверь права.", "panic_off": "Паника выключена", "panic_restored": "Медленный режим и заявки восстановлены.", "chat_closed_by_banchat": "Чат остаётся закрыт через banchat.", "panic_enable_failed": "Не удалось включить панику. Проверь права управления чатом и заявками.", "panic_on": "Паника включена", "panic_enabled_details": "<b>Чат:</b> закрыт\n<b>Медленный режим:</b> 1 час\n<b>Вступление:</b> по заявкам\nПовторная команда вернёт прежние настройки.", "creator_mute_forbidden": "Создателя чата нельзя замутить.", "mute_basic_group": "Мут недоступен в обычной группе. Преобразуй её в супергруппу.", "mute_basic_group_short": "Мут недоступен в обычной группе.", "mute_failed": "Не удалось замутить. Проверь права аккаунта.", "mute_title": "Мут", "muted_action": "получил мут", "unmute_failed": "Не удалось размутить. Проверь права аккаунта.", "unmute_title": "Размут", "restrictions_removed": "ограничения сняты", "seconds_short": "сек.", "try_later": "Попробуй позже.",
    }

    strings.update({
        "requests_accept_all": "All requests will be accepted.",
        "requests_accept_button": "✅ Accept all",
        "requests_accepted": "Join requests accepted",
        "requests_batch": "Selected: {count}",
        "requests_batch_input": "Enter the number of requests",
        "requests_batch_invalid": "Enter a whole number greater than zero.",
        "requests_accept_batch": "✅ Accept {count}",
        "requests_decline_batch": "🗑 Decline {count}",
        "requests_menu_hint": "Choose how many join requests to process.",
        "dmute_title": "Delete-mute",
        "dmute_action": "new messages will be deleted",
        "dmute_removed": "Delete-mute removed",
        "dmute_none": "Delete-mute is not enabled.",
        "dmute_usage": "Reply to a user or specify @username or ID, then an optional duration.",
        "dmute_delete_rights": "Need rights to delete messages and restrict members in this chat.",
        "dmute_private_self": "Delete-mute cannot be applied to Saved Messages.",
        "member_select_empty": "No suitable members were found.",
        "guest_title": "Guest bots",
        "guest_forbidden": "Guest bots are forbidden.",
        "guest_allowed": "Guest bots are allowed.",
        "guest_delete_rights": "Not enough rights to delete guest-bot messages in this chat.",
        "guest_allow_button": "🤖 Allow guest bots",
        "guest_forbid_button": "🤖 Forbid guest bots",
        "sticker_ban_reply": "Reply to a sticker.",
        "sticker_ban_title": "Sticker bans",
        "sticker_ban_args": "Use optional <code>-p</code> (pack) and <code>-g</code> (global) arguments.",
        "sticker_global_title": "Global sticker bans",
        "sticker_other_scope": "A ban in the other scope (local/global) still applies in this chat.",
        "sticker_pack_missing": "Could not determine this sticker pack.",
        "sticker_ban_rights": "Not enough rights to delete stickers in this chat.",
        "sticker_banned": "Sticker is now forbidden.",
        "sticker_unbanned": "Sticker is allowed again.",
        "sticker_pack_banned": "Sticker pack is now forbidden.",
        "sticker_pack_unbanned": "Sticker pack is allowed again.",
        "sticker_pack_not_banned": "This sticker pack is not banned here.",
        "sticker_not_banned": "This sticker is not banned here.",
        "sticker_still_pack_banned": "This sticker is still blocked by its sticker pack.",
        "markup_hint": "<b>Formatting</b>\n<code>&lt;b&gt;bold&lt;/b&gt;</code>\n<code>&lt;i&gt;italic&lt;/i&gt;</code>\n<code>&lt;u&gt;underline&lt;/u&gt;</code>\n<code>&lt;s&gt;strikethrough&lt;/s&gt;</code>\n<code>&lt;code&gt;inline code&lt;/code&gt;</code>\n<code>&lt;pre&gt;code block&lt;/pre&gt;</code>\n<code>&lt;a href=\"URL\"&gt;link&lt;/a&gt;</code>\n<code>&lt;q&gt;quote&lt;/q&gt;</code>\n<code>&lt;qe&gt;expandable quote&lt;/qe&gt;</code>\n<code>&lt;tg-emoji emoji-id=\"ID\"&gt;🙂&lt;/tg-emoji&gt;</code>",
    })
    strings_ru.update({
        "requests_accept_all": "Все заявки будут приняты.",
        "requests_accept_button": "✅ Принять все",
        "requests_accepted": "Заявки приняты",
        "requests_batch": "Выбрано: {count}",
        "requests_batch_input": "Введите количество заявок",
        "requests_batch_invalid": "Введите целое число больше нуля.",
        "requests_accept_batch": "✅ Принять {count}",
        "requests_decline_batch": "🗑 Отклонить {count}",
        "requests_menu_hint": "Выберите, сколько заявок обработать.",
        "dmute_title": "Делит-мут",
        "dmute_action": "новые сообщения будут удаляться",
        "dmute_removed": "Делит-мут снят",
        "dmute_none": "Делит-мут не включён.",
        "dmute_usage": "Ответь на пользователя или укажи @username либо ID, затем при необходимости срок.",
        "dmute_delete_rights": "Нужны права на удаление сообщений и ограничение участников в этом чате.",
        "dmute_private_self": "Нельзя поставить делит-мут в Избранном.",
        "member_select_empty": "Подходящих участников не найдено.",
        "guest_title": "Гостевые боты",
        "guest_forbidden": "Гостевые боты запрещены.",
        "guest_allowed": "Гостевые боты разрешены.",
        "guest_delete_rights": "Недостаточно прав для удаления сообщений гостевых ботов в этом чате.",
        "guest_allow_button": "🤖 Разрешить гостевых ботов",
        "guest_forbid_button": "🤖 Запретить гостевых ботов",
        "sticker_ban_reply": "Ответь на стикер.",
        "sticker_ban_title": "Запреты стикеров",
        "sticker_ban_args": "Аргументы: <code>-p</code> — весь пак, <code>-g</code> — глобально. Можно вместе.",
        "sticker_global_title": "Глобальный запрет стикеров",
        "sticker_other_scope": "В этом чате остаётся запрет другого уровня (локальный/глобальный).",
        "sticker_pack_missing": "Не удалось определить пак этого стикера.",
        "sticker_ban_rights": "Недостаточно прав для удаления стикеров в этом чате.",
        "sticker_banned": "Стикер теперь запрещён.",
        "sticker_unbanned": "Стикер снова разрешён.",
        "sticker_pack_banned": "Стикерпак теперь запрещён.",
        "sticker_pack_unbanned": "Стикерпак снова разрешён.",
        "sticker_pack_not_banned": "Этот стикерпак здесь не запрещён.",
        "sticker_not_banned": "Этот стикер здесь не запрещён.",
        "sticker_still_pack_banned": "Этот стикер всё ещё запрещён его стикерпаком.",
        "markup_hint": "<b>Форматирование</b>\n<code>&lt;b&gt;жирный&lt;/b&gt;</code>\n<code>&lt;i&gt;курсив&lt;/i&gt;</code>\n<code>&lt;u&gt;подчёркнутый&lt;/u&gt;</code>\n<code>&lt;s&gt;зачёркнутый&lt;/s&gt;</code>\n<code>&lt;code&gt;код&lt;/code&gt;</code>\n<code>&lt;pre&gt;блок кода&lt;/pre&gt;</code>\n<code>&lt;a href=\"URL\"&gt;ссылка&lt;/a&gt;</code>\n<code>&lt;q&gt;цитата&lt;/q&gt;</code>\n<code>&lt;qe&gt;свёрнутая цитата&lt;/qe&gt;</code>\n<code>&lt;tg-emoji emoji-id=\"ID\"&gt;🙂&lt;/tg-emoji&gt;</code>",
    })

    def _s(self, key, **kwargs):
        return self.strings(key).format(**kwargs)

    strings.update({
        "gq_title": "GodChat · Message snapshot", "gq_reply": "Reply to a message. [n]: 1–30 messages, ending at the reply. -u: only that author's messages. Settings: gcfg.",
        "gq_args_bad": "Use [n] (1–30) and optionally -u. Open settings with gcfg.",
        "gq_work": '<tg-emoji emoji-id="5447421246172069841">📄</tg-emoji> Creating a quote', "gq_busy": "A snapshot is already being processed in this menu.",
        "gq_expired": "This menu expired. Run gcfg again.", "gq_failed": "Snapshot failed. Operation: <code>{op}</code>\nStage: <code>{stage}</code>\nCode: <code>{code}</code>\nDetailed diagnostics are in the server log.",
        "gq_preview": "Send preview", "gq_png": "Send PNG", "gq_reset": "Restore defaults", "gq_close": "Close", "gq_cancel": "Cancel",
        "gq_theme": "Theme", "gq_background": "Background", "gq_dates": "Date", "gq_tags": "Tags", "gq_avatars": "Avatars", "gq_reactions": "Reactions", "gq_spoilers": "Reveal spoilers", "gq_expanded": "Expand quotes", "gq_width": "Width", "gq_scale": "Scale",
        "gq_compact": "Compact snapshot", "gq_gift_colors": "Gift colors", "gq_bubble_outline": "Bubble outline", "gq_bubble_transparency": "Bubble transparency", "gq_extra": "Additional",
        "gq_composition": "Layout", "gq_balanced": "New", "gq_classic": "Previous",
        "gq_select": "Messages", "gq_count": "Change count", "gq_count_input": "Number of messages (1–30), ending at the original reply", "gq_count_bad": "Enter a number from 1 to 30.",
        "gq_album": "Whole album", "gq_add": "Add message", "gq_add_input": "Message ID or t.me link from this chat", "gq_add_bad": "Enter an accessible message ID or link from the same chat (up to 30 messages).",
        "gq_ready": "Messages: {count} · Pages: {pages}\nOperation: <code>{op}</code>", "gq_warn": "Some elements have limitations. Diagnostic codes:", "gq_dirty": "Settings changed. Send preview to see the result.",
        "gq_sent": "Snapshot sent.", "gq_cancelled": "Cancelled.", "gq_back": "Back", "gq_no_selection": "Select at least one message.",
        "gq_full": "Too many open snapshot menus. Close an existing one.", "gq_old": "Unavailable message",
    })
    strings_ru.update({
        "gq_title": "GodChat · Снимок сообщений", "gq_reply": "Ответь на сообщение. [n]: 1–30 сообщений, заканчивая реплаем. -u: только сообщения его автора. Настройки: gcfg.",
        "gq_args_bad": "Укажи [n] (1–30) и при необходимости -u. Для настроек используй gcfg.",
        "gq_work": '<tg-emoji emoji-id="5447421246172069841">📄</tg-emoji> Создаю цитату', "gq_busy": "В этом меню уже выполняется обработка снимка.",
        "gq_expired": "Меню устарело. Запусти gcfg ещё раз.", "gq_failed": "Не удалось создать снимок. Операция: <code>{op}</code>\nЭтап: <code>{stage}</code>\nКод: <code>{code}</code>\nПодробная диагностика — в логах сервера.",
        "gq_preview": "Отправить превью", "gq_png": "Отправить PNG", "gq_reset": "Вернуть дефолт", "gq_close": "Закрыть", "gq_cancel": "Отмена",
        "gq_theme": "Тема", "gq_background": "Фон", "gq_dates": "Дата", "gq_tags": "Теги", "gq_avatars": "Аватары", "gq_reactions": "Реакции", "gq_spoilers": "Раскрыть спойлеры", "gq_expanded": "Раскрыть цитаты", "gq_width": "Ширина", "gq_scale": "Масштаб",
        "gq_compact": "Компактный снимок", "gq_gift_colors": "Цвет подарка", "gq_bubble_outline": "Обводка облачка", "gq_bubble_transparency": "Прозрачность облачка", "gq_extra": "Дополнительно",
        "gq_composition": "Компоновка", "gq_balanced": "Новая", "gq_classic": "Прежняя",
        "gq_select": "Сообщения", "gq_count": "Изменить количество", "gq_count_input": "Количество сообщений (1–30), заканчивая исходным реплаем", "gq_count_bad": "Введи число от 1 до 30.",
        "gq_album": "Весь альбом", "gq_add": "Добавить сообщение", "gq_add_input": "ID сообщения или ссылка t.me из этого чата", "gq_add_bad": "Введи ID доступного сообщения или ссылку из этого же чата (до 30 сообщений).",
        "gq_ready": "Сообщений: {count} · Страниц: {pages}\nОперация: <code>{op}</code>", "gq_warn": "Часть элементов имеет ограничения. Коды диагностики:", "gq_dirty": "Настройки изменены. Нажми «Отправить превью», чтобы увидеть результат.",
        "gq_sent": "Снимок отправлен.", "gq_cancelled": "Отменено.", "gq_back": "Назад", "gq_no_selection": "Выбери хотя бы одно сообщение.",
        "gq_full": "Слишком много открытых меню снимков. Закрой одно из предыдущих.", "gq_old": "Сообщение недоступно",
    })
    strings.update({
        "gq_link_preview_position": "Link preview",
        "gq_link_preview_top": "top",
        "gq_link_preview_bottom": "bottom",
        "gq_transparency_short": "Opacity",
    })
    strings_ru.update({
        "gq_link_preview_position": "Превью ссылок",
        "gq_link_preview_top": "сверху",
        "gq_link_preview_bottom": "снизу",
        "gq_transparency_short": "Прозр.",
    })

    def _gq_get(self, token):
        state = self._gquote_sessions.get(token)
        return state if state and time.monotonic() - state["created"] < 1800 else None

    def _gq_migrate_expanded_default(self):
        if self.get('gquote_expanded_default_v1', False):
            return
        saved = self.get('gquote_options', {})
        saved = dict(saved) if isinstance(saved, dict) else {}
        saved['expanded'] = False
        self._save_state('gquote_options', _GQuoteRenderer.normalize_options(saved))
        self._save_state('gquote_expanded_default_v1', True)

    def _gq_trigger_get(self, chat_id):
        saved = self.get('gquote_chat_triggers', {})
        config = saved.get(str(int(chat_id)), {}) if isinstance(saved, dict) else {}
        if not isinstance(config, dict):
            config = {}
        trigger = config.get('trigger', 'цитата')
        if not isinstance(trigger, str) or not 1 <= len(trigger) <= 32:
            trigger = 'цитата'
        return {'enabled': config.get('enabled') is True, 'trigger': trigger}

    def _gq_trigger_save(self, chat_id, config):
        saved = self.get('gquote_chat_triggers', {})
        saved = dict(saved) if isinstance(saved, dict) else {}
        saved[str(int(chat_id))] = dict(config)
        self._save_state('gquote_chat_triggers', saved)

    async def _gq_trigger_input(self, call, value, token):
        state = self._gq_get(token)
        if not state or not state.get('gcfg') or not getattr(state['source'], 'is_group', False):
            return await call.answer(self._s('gq_expired'), show_alert=True)
        if state.get('task'):
            return await call.answer(self._s('gq_busy'), show_alert=True)
        trigger = ' '.join(value.split())
        if not 1 <= len(trigger) <= 32 or any(ord(char) < 32 for char in trigger):
            return await call.answer(self._s('gq_trigger_invalid'), show_alert=True)
        config = self._gq_trigger_get(state['source'].chat_id)
        config['trigger'] = trigger
        self._gq_trigger_save(state['source'].chat_id, config)
        await self._inline_answer(state['status'], self._gq_text(state), self._gq_markup(state))

    @loader.watcher('only_messages')
    async def _gq_trigger_watcher(self, message: Message):
        if not getattr(message, 'is_group', False) or not getattr(message, 'reply_to_msg_id', None):
            return
        config = self._gq_trigger_get(message.chat_id)
        if not config['enabled']:
            return
        sender = getattr(message, 'sender', None)
        if getattr(sender, 'bot', False):
            return
        text = ' '.join((getattr(message, 'raw_text', None) or '').split()).casefold()
        trigger = config['trigger'].casefold()
        if text == trigger:
            count = 1
        elif text.startswith(trigger + ' ') and re.fullmatch(r'[0-9]{1,2}', text[len(trigger)+1:]):
            count = int(text[len(trigger)+1:])
            if not 1 <= count <= _GQuoteRenderer.MAX_MESSAGES:
                return await self._answer_temporary(message, self._s('gq_count_bad'), 12)
        else:
            return
        now = time.monotonic()
        hits = [stamp for stamp in self._gq_trigger_hits.get(message.chat_id, ()) if now - stamp < 5]
        if len(hits) >= 2:
            return
        hits.append(now)
        self._gq_trigger_hits[message.chat_id] = hits
        if len(self._gq_trigger_hits) > 256:
            self._gq_trigger_hits = {
                chat_id: recent for chat_id, recent in self._gq_trigger_hits.items()
                if recent and now - recent[-1] < 5
            }
        await self._gq_start(message, count, trigger=True)

    def _gq_pack_get(self, chat_id):
        saved = self.get('gquote_sticker_packs', {})
        if not isinstance(saved, dict):
            return None
        pack = saved.get(str(int(chat_id)))
        if not isinstance(pack, dict) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', str(pack.get('short_name', ''))):
            return None
        return pack

    def _gq_pack_save(self, chat_id, short_name, enabled=False):
        saved = self.get('gquote_sticker_packs', {})
        saved = dict(saved) if isinstance(saved, dict) else {}
        saved[str(int(chat_id))] = {'short_name':short_name, 'enabled':bool(enabled)}
        self._save_state('gquote_sticker_packs', saved)

    @staticmethod
    def _gq_pack_name(value):
        value = value.strip()
        if value.startswith(('https://', 'http://')):
            parsed = urlsplit(value)
            if parsed.hostname not in ('t.me', 'telegram.me') or parsed.query or parsed.fragment:
                return None
            match = re.fullmatch(r'/addstickers/([A-Za-z][A-Za-z0-9_]{0,63})/?', parsed.path)
            return match.group(1) if match else None
        return value if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value) else None

    async def _gq_pack_fetch(self, short_name):
        result = await self.client(functions.messages.GetStickerSetRequest(
            stickerset=types.InputStickerSetShortName(short_name), hash=0))
        pack = result.set
        if not getattr(pack, 'creator', False) or getattr(pack, 'masks', False) or getattr(pack, 'emojis', False):
            raise ValueError('quote_pack_not_owned_or_regular')
        return result

    strings.update({
        'gq_bg_transparent':'Transparent','gq_bg_dark':'Dark','gq_bg_light':'Light',
        'gq_bg_custom':'Custom background','gq_bg_saved':'Saved background',
        'gq_bg_input':'Raw image URL, image hosting link or direct image URL',
        'gq_bg_bad':'Could not load the background from this link.',
        'gq_bg_upload':'Upload background','gq_bg_replace':'Replace background',
        'gq_bg_loaded':'Background loaded and selected.',
        'gq_send_format':'Send as','gq_format_sticker':'Sticker','gq_format_png':'PNG','gq_format_photo':'Photo',
        'gq_pack_create':'Create chat pack','gq_pack_replace':'Create new chat pack',
        'gq_pack_connect':'Connect my pack','gq_pack_open':'Open pack',
        'gq_pack_auto':'Add new quotes to pack',
        'gq_pack_input':'Sticker pack link or short name',
        'gq_pack_invalid':'Pack not found, is not yours, or is not a regular sticker pack.',
        'gq_pack_failed':'Could not update the quote sticker pack. See logs.',
        'gq_pack_full':'The quote sticker pack is full. Auto-add has been disabled.',
        'gq_pack_send_failed':'Sticker added to the pack, but could not be sent from it. The quote was sent normally.',
        'gq_pack_saved':'Quote pack',
        'gq_trigger_enable':'Quotes by trigger',
        'gq_trigger_name':'Trigger',
        'gq_trigger_input':'Trigger text (1–32 characters); reply with trigger [n], n=1–30',
        'gq_trigger_invalid':'Enter 1–32 characters for the trigger.',
        'gq_trigger_usage':'Reply to the last message: <code>{trigger}</code> or <code>{trigger} 4</code> for four messages',
    })
    strings_ru.update({
        'gq_bg_transparent':'Прозрачный','gq_bg_dark':'Тёмный','gq_bg_light':'Светлый',
        'gq_bg_custom':'Свой фон','gq_bg_saved':'Сохранённый фон',
        'gq_bg_input':'Raw-ссылка, ссылка с хостинга или прямая ссылка на картинку',
        'gq_bg_bad':'Не удалось загрузить фон по этой ссылке.',
        'gq_bg_upload':'Загрузить фон','gq_bg_replace':'Заменить фон',
        'gq_bg_loaded':'Фон загружен и выбран.',
        'gq_send_format':'Формат отправки','gq_format_sticker':'Стикер','gq_format_png':'PNG','gq_format_photo':'Фото',
        'gq_pack_create':'Создать пак чата','gq_pack_replace':'Создать новый пак чата',
        'gq_pack_connect':'Добавить свой пак','gq_pack_open':'Открыть пак',
        'gq_pack_auto':'Добавлять новые цитаты в пак',
        'gq_pack_input':'Ссылка на стикерпак или его короткое имя',
        'gq_pack_invalid':'Пак не найден, не принадлежит вашему аккаунту или не является обычным паком стикеров.',
        'gq_pack_failed':'Не удалось изменить пак цитат. Подробности в логах.',
        'gq_pack_full':'Пак цитат заполнен. Автодобавление выключено.',
        'gq_pack_send_failed':'Стикер добавлен в пак, но отправить его из пака не удалось. Цитата отправлена обычным способом.',
        'gq_pack_saved':'Пак цитат',
        'gq_trigger_enable':'Цитаты по триггеру',
        'gq_trigger_name':'Триггер',
        'gq_trigger_input':'Текст триггера (1–32 символа); ответ: триггер [n], n=1–30',
        'gq_trigger_invalid':'Укажи от 1 до 32 символов для триггера.',
        'gq_trigger_usage':'Ответь на последнее сообщение: <code>{trigger}</code> или <code>{trigger} 4</code> для четырёх сообщений',
    })

    def _gq_markup(self, state, busy=False):
        token = state["id"]
        if busy:
            if state.get('fake') and state.get('config', True):
                return self._mfq_markup(state)
            rows = []
            if state.get("config", True):
                rows.append([{"text": self._s("gq_close"), "callback": self._mfq_callback if state.get('fake') else self._gq_callback, "args": (token, "close"), "style": "danger"}])
            return rows
        if state.get('fake') and state.get('config', True):
            return self._mfq_markup(state)
        if not state.get("config", True):
            return []
        def button(text, action, style=None):
            result = {"text": text, "callback": self._gq_callback, "args": (token, action)}
            if style or action in ("close", "back"):
                result["style"] = style or "danger"
            return result
        options = state["options"]
        if state.get('gq_view')=='extra':
            toggles=[button(('✓ ' if options[key] else '✗ ')+self._s('gq_'+key),key,
                            'success' if options[key] else 'danger') for key in ('spoilers','expanded')]
            return [toggles,
                    [button(self._s('gq_link_preview_position')+': '+self._s('gq_link_preview_'+options.get('link_preview_position','bottom')),
                            'link_preview_position')],
                    [button('−5%','transparency_down'),
                     button(self._s('gq_transparency_short')+' '+str(options['bubble_transparency'])+'%','transparency_info'),
                     button('+5%','transparency_up')],
                    [button(self._s('gq_back'),'extra_back','danger'),button(self._s('gq_close'),'close')]]
        rows = [[button(self._s("gq_theme") + ': ' + options["theme"], "theme")]]
        rows.append([button(self._s('gq_send_format')+': '+self._s('gq_format_'+options.get('send_format','sticker')), 'send_format')])
        rows.append([button(self._s('gq_background')+': '+self._s('gq_bg_'+options.get('background_mode','transparent')), 'background_menu')])
        keys = ("gift_colors", "bubble_outline")
        toggles = [button(('✓ ' if options[k] else '✗ ') + self._s('gq_' + k), k, "success" if options[k] else "danger") for k in keys]
        rows.extend([toggles[i:i+2] for i in range(0, len(toggles), 2)])
        rows.append([button(self._s('gq_extra'),'extra','primary')])
        if state.get('gcfg') and state.get('gq_view')!='extra' and getattr(state['source'], 'is_group', False):
            trigger = self._gq_trigger_get(state['source'].chat_id)
            rows.append([button(('✓ ' if trigger['enabled'] else '✗ ') + self._s('gq_trigger_enable'),
                                'trigger_toggle', 'success' if trigger['enabled'] else 'danger')])
            rows.append([{'text':self._s('gq_trigger_name') + ': ' + trigger['trigger'],
                          'input':self._s('gq_trigger_input'), 'handler':self._gq_trigger_input,
                          'args':(token,), 'style':'primary'}])
            pack = self._gq_pack_get(state['source'].chat_id)
            rows.append([button(self._s('gq_pack_replace' if pack else 'gq_pack_create'), 'pack_create', 'primary')])
            rows.append([{'text':self._s('gq_pack_connect'),'input':self._s('gq_pack_input'),
                          'handler':self._gq_pack_input,'args':(token,),'style':'primary'}])
            if pack:
                rows.append([button(('✓ ' if pack.get('enabled') else '✗ ')+self._s('gq_pack_auto'),
                                    'pack_toggle','success' if pack.get('enabled') else 'danger')])
                rows.append([{'text':self._s('gq_pack_open'),'url':'https://t.me/addstickers/'+pack['short_name']}])
        back = [{"text": self._s("gq_back"), "callback": self._gcfg_open, "args": (token, "main"), "style": "danger"}]
        if state.get("reply"):
            rows.append([button(self._s("gq_png"), "png"), button(self._s("gq_preview"), "preview")])
        rows.append([button(self._s("gq_reset"), "reset")])
        rows.append((back if state.get("gcfg") else []) + [button(self._s("gq_close"), "close")])
        return rows

    def _gq_text(self, state):
        if state.get('fake'):
            return self._mfq_text(state)
        title=self._s("gcfg_quotes")
        if state.get('gq_view')=='extra':
            title+=' · '+self._s('gq_extra')
        text = _RANDOM_EMOJI["message"] + ' <b>GodChat · ' + title + '</b>'
        if state.get('gcfg') and state.get('gq_view')!='extra' and getattr(state['source'], 'is_group', False):
            trigger = self._gq_trigger_get(state['source'].chat_id)
            if trigger['enabled']:
                text += '\n\n' + self._s('gq_trigger_usage', trigger=utils.escape_html(trigger['trigger']))
            pack = self._gq_pack_get(state['source'].chat_id)
            if pack:
                text += '\n\n' + self._s('gq_pack_saved') + ': <code>' + utils.escape_html(pack['short_name']) + '</code>'
        return text

    def _gq_background_text(self,state,uploaded=False):
        mode=state['options'].get('background_mode','transparent')
        text=self._gq_text(state)+'\n\n'+self._s('gq_background')+': <b>'+self._s('gq_bg_'+mode)+'</b>'
        if uploaded: text+='\n'+_EMOJI['success']+' '+self._s('gq_bg_loaded')
        return text

    def _gq_background_markup(self,state):
        token=state['id']; mode=state['options'].get('background_mode','transparent')
        cache=self.get('gquote_background_cache',{})
        saved=isinstance(cache,dict) and bool(cache.get('url'))
        rows=[]
        for pair in (('transparent','dark'),('light',)):
            rows.append([{'text':('✓ ' if mode==value else '')+self._s('gq_bg_'+value),
                'callback':self._gq_callback,'args':(token,'bg:'+value),
                **({'style':'success'} if mode==value else {})} for value in pair])
        rows.append([{'text':self._s('gq_bg_replace' if saved else 'gq_bg_upload'),'input':self._s('gq_bg_input'),
                      'handler':self._gq_background_input,'args':(token,),'style':'primary'}])
        if saved:
            rows.append([{'text':('✓ ' if mode=='custom' else '')+self._s('gq_bg_saved'),'callback':self._gq_callback,
                'args':(token,'bg:custom'),'style':'success' if mode=='custom' else 'primary'}])
        rows.append([{'text':self._s('gq_back'),'callback':self._gcfg_open,'args':(token,'quotes'),'style':'danger'},
                     {'text':self._s('gq_close'),'callback':self._gq_callback,'args':(token,'close'),'style':'danger'}])
        return rows

    @staticmethod
    def _gq_fetch_background(url):
        from urllib.parse import urlsplit, urljoin
        from html.parser import HTMLParser
        from PIL import Image, ImageOps
        def valid(link):
            parsed=urlsplit(link)
            return parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password and len(link)<=2048
        if not valid(url): raise _GQuoteError('background_url_invalid')
        class Images(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True); self.links=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs); target=None; priority=3
                if tag=='meta' and (a.get('property') or a.get('name','')).lower() in ('og:image','og:image:secure_url','twitter:image','twitter:image:src'):
                    target=a.get('content'); priority=1
                elif tag=='link' and a.get('rel','').lower()=='image_src':
                    target=a.get('href'); priority=1
                elif tag=='a' and ('download' in a or re.search(r'(?:raw|download|original)',a.get('href',''),re.I)):
                    target=a.get('href'); priority=0
                elif tag=='img':
                    target=a.get('data-original') or a.get('data-src') or a.get('src')
                    if re.search(r'(?:logo|favicon|avatar|icon)',a.get('class','')+' '+a.get('id',''),re.I): target=None
                if target: self.links.append((priority,target))
        queue=[(url,0)]; seen=set(); data=None; last_error=None
        while queue and len(seen)<6:
            current,depth=queue.pop(0)
            if current in seen or not valid(current): continue
            seen.add(current)
            try:
                with urlopen(Request(current,headers={'User-Agent':'Mozilla/5.0 (compatible; GodChat-gquote)',
                        'Accept':'image/avif,image/webp,image/*,text/html;q=0.8,*/*;q=0.5'}),timeout=30) as response:
                    candidate=response.read(12*1024*1024+1)
                    final=getattr(response,'geturl',lambda:current)()
                    if not isinstance(final,str): final=current
                if len(candidate)>12*1024*1024: raise _GQuoteError('background_bytes_limit')
                if candidate.lstrip().startswith(b'<'):
                    if len(candidate)>2*1024*1024 or depth>=2: raise _GQuoteError('background_page_limit')
                    parser=Images(); parser.feed(candidate.decode('utf8','replace'))
                    links=[(urljoin(final,link),depth+1) for _,link in sorted(parser.links,key=lambda item:item[0])]
                    queue=links[:6]+queue
                    continue
                with Image.open(io.BytesIO(candidate)) as image:
                    if image.format not in ('PNG','JPEG','WEBP','GIF'): raise _GQuoteError('background_image_invalid')
                data=candidate; break
            except Exception as error:
                last_error=error
        if data is None: raise _GQuoteError('background_image_not_found') from last_error
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ('PNG','JPEG','WEBP','GIF') or source.width*source.height>16_000_000:
                raise _GQuoteError('background_image_invalid')
            with ImageOps.exif_transpose(source) as oriented:
                with oriented.convert('RGB') as normalized:
                    normalized.thumbnail((1280,1280),Image.Resampling.LANCZOS)
                    out=io.BytesIO(); normalized.save(out,format='WEBP',quality=95,method=4)
        result=out.getvalue()
        if len(result)>3*1024*1024: raise _GQuoteError('background_cache_limit')
        return result

    async def _gq_background_input(self,call,value,token):
        state=self._gq_get(token)
        if not state: return await call.answer(self._s('gq_expired'),show_alert=True)
        if state.get('task'): return await call.answer(self._s('gq_busy'),show_alert=True)
        url=value.strip()
        if not url or len(url)>2048: return await call.answer(self._s('gq_bg_bad'),show_alert=True)
        lock=getattr(self,'_gq_background_lock',None)
        if lock is None: self._gq_background_lock=lock=asyncio.Lock()
        task=asyncio.current_task(); state['task']=task; self._gquote_tasks.add(task)
        try:
            async with lock:
                cached=self.get('gquote_background_cache',{})
                if not isinstance(cached,dict) or cached.get('url')!=url:
                    import base64
                    data=await utils.run_sync(self._gq_fetch_background,url)
                    self._save_state('gquote_background_cache',{'url':url,'data':base64.b64encode(data).decode('ascii')})
            if state.get('closed'): return
            state['options'].update(background_mode='custom',background=True,background_url=url)
            state['dirty']=True; state['pages']=[]
            self._save_state('gquote_options',state['options'])
            await self._inline_answer(state['status'],self._gq_background_text(state,uploaded=True),self._gq_background_markup(state))
        except asyncio.CancelledError: raise
        except Exception:
            logger.warning('gquote background download failed',exc_info=True)
            await call.answer(self._s('gq_bg_bad'),show_alert=True)
            if not state.get('closed'):
                await self._inline_answer(state['status'],self._gq_background_text(state)+'\n\n'+self._s('gq_bg_bad'),self._gq_background_markup(state))
        finally:
            state['task']=None; self._gquote_tasks.discard(task)

    @staticmethod
    def _gq_sticker_bytes(data):
        from PIL import Image
        pages=data if isinstance(data,list) else [data]
        dimensions=[]
        for page in pages:
            with Image.open(io.BytesIO(page)) as source: dimensions.append(source.size)
        if not dimensions: raise _GQuoteError('no_output_pages')
        width=max(w for w,h in dimensions); height=sum(h for w,h in dimensions)
        ratio=512/max(width,height)
        size=(max(1,round(width*ratio)),max(1,round(height*ratio)))
        with Image.new('RGBA',size,(0,0,0,0)) as resized:
            offset=0
            for page,(w,h) in zip(pages,dimensions):
                top=round(offset*ratio); bottom=round((offset+h)*ratio); offset+=h
                if bottom<=top: continue
                with Image.open(io.BytesIO(page)) as source:
                    with source.convert('RGBA') as image:
                        with image.resize((max(1,round(w*ratio)),bottom-top),Image.Resampling.LANCZOS) as part:
                            resized.alpha_composite(part,((size[0]-part.width)//2,top))
            out=io.BytesIO(); resized.save(out,format='WEBP',lossless=True,method=6)
            if out.tell()>512*1024:
                for quality in (95,90,80,70):
                    out=io.BytesIO(); resized.save(out,format='WEBP',quality=quality,method=6)
                    if out.tell()<=512*1024: break
            if out.tell()>512*1024: raise _GQuoteError('sticker_bytes_limit')
            return out.getvalue(),size

    @staticmethod
    def _gq_pack_seed():
        from PIL import Image, ImageDraw
        image = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((38, 54, 474, 418), radius=78, fill='#303447')
        draw.polygon(((112, 398), (112, 480), (200, 406)), fill='#303447')
        for left in (135, 285):
            draw.ellipse((left, 185, left+75, 260), fill='#ffffff')
            draw.polygon(((left+32, 245), (left+75, 245), (left+18, 325)), fill='#ffffff')
        output = io.BytesIO()
        image.save(output, format='WEBP', lossless=True)
        return output.getvalue()

    async def _gq_pack_upload(self, data, size=(512, 512)):
        source = io.BytesIO(data)
        source.name = 'godchat_quote.webp'
        uploaded = await self.client.upload_file(source)
        result = await self.client(functions.messages.UploadMediaRequest(
            peer='me',
            media=types.InputMediaUploadedDocument(
                file=uploaded, mime_type='image/webp',
                attributes=[types.DocumentAttributeSticker(
                    alt='💬', stickerset=types.InputStickerSetEmpty()),
                    types.DocumentAttributeImageSize(w=size[0], h=size[1])],
            ),
        ))
        document = getattr(result, 'document', None)
        if document is None:
            raise ValueError('quote_sticker_upload_failed')
        return types.InputStickerSetItem(
            document=tl_utils.get_input_document(document), emoji='💬')

    async def _gq_pack_create(self, call, state):
        chat_id = state['source'].chat_id
        task = asyncio.current_task()
        state['task'] = task
        self._gquote_tasks.add(task)
        error = None
        try:
            lock = self._gq_pack_locks.setdefault(str(int(chat_id)), asyncio.Lock())
            async with lock:
                entity = await self.client.get_entity(chat_id)
                title = (str(getattr(entity, 'title', '') or 'Chat') + ' · цитаты')[:64]
                sticker = await self._gq_pack_upload(await utils.run_sync(self._gq_pack_seed))
                short_name = 'godchat_' + str(abs(int(chat_id))) + '_' + secrets.token_hex(4)
                result = await self.client(functions.stickers.CreateStickerSetRequest(
                    user_id='me', title=title, short_name=short_name,
                    stickers=[sticker], software='GodChat',
                ))
                self._gq_pack_save(chat_id, result.set.short_name, False)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Could not create quote sticker pack for chat %s', chat_id)
            error = self._s('gq_pack_failed')
        finally:
            state['task'] = None
            self._gquote_tasks.discard(task)
        if not state.get('closed'):
            await self._inline_answer(state['status'],
                self._gq_text(state) + ('\n\n' + error if error else ''), self._gq_markup(state))

    async def _gq_pack_input(self, call, value, token):
        state = self._gq_get(token)
        if not state:
            return await call.answer(self._s('gq_expired'), show_alert=True)
        if state.get('task'):
            return await call.answer(self._s('gq_busy'), show_alert=True)
        if not state.get('gcfg') or not getattr(state['source'], 'is_group', False):
            return await call.answer(self._s('groups_only'), show_alert=True)
        short_name = self._gq_pack_name(value)
        if not short_name:
            return await call.answer(self._s('gq_pack_invalid'), show_alert=True)
        task = asyncio.current_task()
        state['task'] = task
        self._gquote_tasks.add(task)
        error = None
        try:
            chat_id = state['source'].chat_id
            lock = self._gq_pack_locks.setdefault(str(int(chat_id)), asyncio.Lock())
            async with lock:
                pack = await self._gq_pack_fetch(short_name)
                if len(pack.documents) >= 120:
                    error = self._s('gq_pack_full')
                else:
                    self._gq_pack_save(chat_id, pack.set.short_name, False)
        except asyncio.CancelledError:
            raise
        except ValueError:
            error = self._s('gq_pack_invalid')
        except Exception:
            logger.exception('Could not connect quote sticker pack %s', short_name)
            error = self._s('gq_pack_invalid')
        finally:
            state['task'] = None
            self._gquote_tasks.discard(task)
        if not state.get('closed'):
            await self._inline_answer(state['status'],
                self._gq_text(state) + ('\n\n' + error if error else ''), self._gq_markup(state))

    async def _gq_pack_append(self, state, return_document=False):
        source = state['source']
        if not getattr(source, 'is_group', False):
            return None
        chat_id = source.chat_id
        saved = self._gq_pack_get(chat_id)
        if not saved or not saved.get('enabled'):
            return None
        lock = self._gq_pack_locks.setdefault(str(int(chat_id)), asyncio.Lock())
        async with lock:
            saved = self._gq_pack_get(chat_id)
            if not saved or not saved.get('enabled'):
                return None
            try:
                result = await self._gq_pack_fetch(saved['short_name'])
                if len(result.documents) >= 120:
                    self._gq_pack_save(chat_id, saved['short_name'], False)
                    return self._s('gq_pack_full')
                existing_ids = {item.id for item in result.documents if getattr(item, 'id', None) is not None}
                pack_state = dict(state, options=dict(state['options'], expanded=False,
                                                      background=False, background_mode='transparent'),
                                  output='sticker', warnings=[], pages=[])
                pages = await self._gquote_renderer.render(pack_state)
                data, size = await utils.run_sync(self._gq_sticker_bytes, pages)
                sticker = await self._gq_pack_upload(data, size)
                added = await self.client(functions.stickers.AddStickerToSetRequest(
                    stickerset=types.InputStickerSetShortName(saved['short_name']),
                    sticker=sticker,
                ))
                if return_document:
                    documents = getattr(added, 'documents', None)
                    if documents is None:
                        documents = (await self._gq_pack_fetch(saved['short_name'])).documents
                    new_documents = [item for item in documents
                                     if getattr(item, 'id', None) is not None and item.id not in existing_ids]
                    document = new_documents[0] if len(new_documents) == 1 else None
                    if document is None:
                        document = next((item for item in documents
                                         if getattr(item, 'id', None) == getattr(sticker.document, 'id', None)), None)
                    if document is None:
                        refreshed = await self._gq_pack_fetch(saved['short_name'])
                        new_documents = [item for item in refreshed.documents
                                         if getattr(item, 'id', None) is not None and item.id not in existing_ids]
                        document = new_documents[0] if len(new_documents) == 1 else None
                    if document is None:
                        raise ValueError('new_quote_sticker_missing_from_pack')
                    return document
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.exception('Could not append quote sticker to pack %s', saved['short_name'])
                reason = (type(error).__name__ + ' ' + str(error)).lower()
                if 'sticker' in reason and ('too_much' in reason or 'toomuch' in reason):
                    self._gq_pack_save(chat_id, saved['short_name'], False)
                    return self._s('gq_pack_full')
                return None
        return None

    @staticmethod
    def _gq_sender_key(item):
        sender_id = getattr(item, 'sender_id', None)
        if sender_id is not None:
            return sender_id
        peer = getattr(item, 'from_id', None)
        if isinstance(peer, int):
            return peer
        return tl_utils.get_peer_id(peer) if peer is not None else None

    async def _gq_collect(self, reply, count, exclude_id=None, user_only=False):
        if count == 1:
            return [reply]
        kwargs = dict(limit=None if user_only else count+5, max_id=reply.id)
        topic = utils.get_topic(reply)
        if topic is not None:
            kwargs["reply_to"] = topic
        messages = []
        author = self._gq_sender_key(reply) if user_only else None
        async for item in self.client.iter_messages(reply.peer_id, **kwargs):
            if (not item or item.id >= reply.id or item.id == exclude_id
                    or self.kind_for_quote(item) == "MessageEmpty"):
                continue
            if user_only and (author is None or self._gq_sender_key(item) != author):
                continue
            messages.append(item)
            if user_only and len(messages) >= count-1:
                break
        return sorted(messages,key=lambda m:m.id)[-(count-1):]+[reply]

    @staticmethod
    def kind_for_quote(item):
        return type(item).__name__

    @loader.command(ru_doc="[n] [-u] - цитата из n сообщений до реплая; [-u] - только сообщения автора реплая", en_doc="[n] [-u] - quote n messages up to the replied one; -u selects only that author's messages")
    async def gq(self, message: Message):
        args = utils.get_args_raw(message).split()
        user_only = '-u' in args
        count_args = [arg for arg in args if arg != '-u']
        if (args.count('-u') > 1 or len(count_args) > 1
                or (count_args and not re.fullmatch(r"[0-9]{1,2}", count_args[0]))):
            return await self._answer_temporary(message, self._s("gq_args_bad"), 12)
        count = int(count_args[0]) if count_args else 1
        if not 1 <= count <= _GQuoteRenderer.MAX_MESSAGES:
            return await self._answer_temporary(message, self._s("gq_count_bad"), 12)
        if user_only:
            await self._gq_start(message, count, user_only=True)
        else:
            await self._gq_start(message, count)

    @loader.command(ru_doc=" - создать фейк-цитату", en_doc=' - create a fake quote')
    async def mfq(self, message: Message):
        if utils.get_args_raw(message).strip():
            return await self._answer_temporary(message, self._s('no_arguments'), 12)
        for token, old in tuple(self._gquote_sessions.items()):
            if not self._gq_get(token) and not old.get('task'):
                self._gquote_sessions.pop(token, None)
        if len(self._gquote_sessions) >= 4:
            return await self._answer_temporary(message, self._s('gq_full'), 12)
        source = await self._get_reply_message(message)
        try:
            peer = await asyncio.wait_for(self.client.get_entity(
                (getattr(source, 'from_id', None) or source.peer_id) if source else self._me_id), 20)
        except Exception:
            text = 'Не удалось получить автора сообщения.' if self._s('gq_theme') == 'Тема' else 'Could not resolve the author.'
            return await self._answer_temporary(message, text, 12)
        token = secrets.token_hex(4)
        state = dict(id=token, source=message, reply=source or message,
                     reply_anchor=source.id if source else None, fake=True, config=True,
                     created=time.monotonic(), ru=self._s('gq_theme') == 'Тема',
                     stage='draft', warnings=[], pages=[], dirty=True, messages=[], selected=set(),
                     options=_GQuoteRenderer.normalize_options(self.get('gquote_options', {})),
                     draft=[self._mfq_entry(peer, source)], cursor=0, next_id=2, view='editor')
        state['draft'][0]['id'] = 1
        self._gquote_sessions[token] = state
        try:
            state['status'] = await self._open_inline_status(message, self._mfq_text(state), self._mfq_markup(state))
        except Exception:
            self._gquote_sessions.pop(token, None)
            raise

    @loader.command(ru_doc=" [-r] [-s] [-m] [@|ID] [Текст] - Быстрая фейк-цитата. [-r] - ответ на исходное сообщение; [-s] - сохранить реплай исходного сообщения; [-m] - сохранить медиа.", en_doc='[-r] [-s] [-m] [@|ID] [Text] - Quick fake quote. -r replies to the source message; -s keeps its original reply; -m keeps media.')
    async def fq(self, message: Message):
        args = utils.get_args_raw(message).strip()
        ru = self._s('gq_theme') == 'Тема'
        if not args:
            return await self._answer_temporary(message, 'Укажите текст цитаты.' if ru else 'Enter quote text.', 12)
        try:
            args, keep_media, source_reply_first, keep_source_reply = self._fq_command_flags(args)
        except ValueError as error:
            conflict = str(error) == 'conflicting_flags'
            return await self._answer_temporary(message,
                ('Нельзя использовать -r и -s вместе.' if ru else 'Do not combine -r and -s.') if conflict
                else ('Повторяющийся флаг.' if ru else 'Duplicate flag.'), 12)
        if not args:
            return await self._answer_temporary(message, 'Укажите текст цитаты.' if ru else 'Enter quote text.', 12)
        for token, old in tuple(self._gquote_sessions.items()):
            if not self._gq_get(token) and not old.get('task'): self._gquote_sessions.pop(token, None)
        if len(self._gquote_sessions) >= 4:
            return await self._answer_temporary(message, self._s('gq_full'), 12)
        reply = await self._get_reply_message(message)
        if keep_media and not getattr(reply, 'media', None):
            return await self._answer_temporary(message, 'Для -m нужен реплай на медиа.' if ru else 'Reply to media to use -m.', 12)
        if keep_source_reply and not getattr(getattr(reply, 'reply_to', None), 'reply_to_msg_id', None):
            return await self._answer_temporary(message,
                'Для -s ответьте на сообщение, у которого есть реплай.' if ru
                else 'To use -s, reply to a message that already replies to another message.', 12)
        token = secrets.token_hex(4)
        state = dict(id=token, source=message, reply=reply or message, reply_anchor=reply.id if reply else None,
                     fake=True, config=False, ru=ru, created=time.monotonic(), stage='parse', warnings=[],
                     pages=[], dirty=True, messages=[], selected=set(), options={}, draft=[], cursor=0, view='editor')
        self._gquote_sessions[token] = state
        task = asyncio.current_task(); state['task'] = task; self._gquote_tasks.add(task)
        try:
            state['draft'] = await asyncio.wait_for(self._fq_parse(args, reply, keep_media=keep_media,
                                                                    source_reply_first=source_reply_first,
                                                                    keep_source_reply=keep_source_reply), 60)
            state['options'] = _GQuoteRenderer.normalize_options(self.get('gquote_options', {}))
            state['status'] = await self._open_inline_status(message, self._s('gq_work'), [])
            self._mfq_materialize(state)
            await self._gq_run(state, document=state['options']['send_format']=='png', photo=state['options']['send_format']=='photo')
        except asyncio.CancelledError:
            if state.get('status'):
                try: await state['status'].delete()
                except Exception: pass
            raise
        except Exception as error:
            if state.get('status'):
                await self._gq_failure(state, error)
            else:
                if str(error) == 'source_reply_unavailable':
                    reason = 'Не удалось получить сообщение из исходного реплая.' if ru else 'Could not load the message from the original reply.'
                elif str(error) == 'source_reply_single_message':
                    reason = 'С -s можно заменить только одно сообщение.' if ru else 'With -s, only one message can be replaced.'
                else:
                    reason = 'Проверьте автора и текст.' if ru else 'Check the author and text.'
                await self._answer_temporary(message, reason, 12)
        finally:
            self._gquote_tasks.discard(task)
            self._gquote_sessions.pop(token, None)

    @staticmethod
    def _fq_command_flags(args):
        leading=[]
        args=args.strip()
        while True:
            match=re.match(r'^(-[rms])(?:\s+|$)',args)
            if not match:
                break
            leading.append(match[1]); args=args[match.end():].strip()
        trailing=[]
        while True:
            match=re.search(r'(?:^|\s+)(-[rms])$',args)
            if not match:
                break
            trailing.append(match[1]); args=args[:match.start()].strip()
        if len(leading+trailing)!=len(set(leading+trailing)):
            raise ValueError('duplicate_flag')
        if '-r' in leading+trailing and '-s' in leading+trailing:
            raise ValueError('conflicting_flags')
        if '-r' in trailing:
            args=(args+' -r').strip()
        return args, '-m' in leading or '-m' in trailing, '-r' in leading, '-s' in leading or '-s' in trailing

    async def _fq_parse(self, args, reply, keep_media=False, source_reply_first=False, keep_source_reply=False):
        if len(args) > 65536: raise ValueError('args_limit')
        if keep_source_reply and not getattr(getattr(reply, 'reply_to', None), 'reply_to_msg_id', None):
            raise ValueError('source_reply_required')
        blocks = re.split(r'(?:\s*\|\s*|\s+;\s+)(?=@[A-Za-z0-9_]+\s|-?\d+\s)', args)
        if len(blocks) > _GQuoteRenderer.MAX_MESSAGES: raise ValueError('message_limit')
        if keep_source_reply and len(blocks) != 1:
            raise ValueError('source_reply_single_message')
        cache = {}
        async def resolve(identity):
            key = str(identity)
            if key not in cache:
                cache[key] = await asyncio.wait_for(self.client.get_entity(identity), 20)
            return cache[key]
        async def parse_author(value, fallback=None):
            match = re.match(r'^(@[A-Za-z0-9_]+|-?\d+)\s+([\s\S]+)$', value.strip())
            if match:
                identity, text = match.groups()
                return await resolve(int(identity) if identity.lstrip('-').isdigit() else identity), text
            if fallback:
                return await resolve(getattr(fallback, 'from_id', None) or fallback.peer_id), value.strip()
            raise ValueError('author_required')
        if keep_source_reply:
            info = reply.reply_to
            parent_peer = getattr(info, 'reply_to_peer_id', None) or reply.peer_id
            parent = await asyncio.wait_for(self.client.get_messages(
                parent_peer, ids=info.reply_to_msg_id), 20)
            if isinstance(parent, (list, tuple)):
                parent = next((item for item in parent if item), None)
            if parent is None:
                raise ValueError('source_reply_unavailable')
            peer, value = await parse_author(blocks[0], reply)
            text, entities = self._mfq_parse_text(value)
            entry = self._mfq_entry(peer, reply)
            entry.update(id=1, text=text, entities=entities,
                         media=getattr(reply, 'media', None) if keep_media else None,
                         original_peer=parent_peer, source_reply=parent)
            return [entry]
        entries = []
        for index, block in enumerate(blocks):
            source_reply = bool(re.search(r'\s+-r\s*$', block)) or (source_reply_first and index==0)
            if source_reply:
                if reply is None: raise ValueError('reply_required')
                block = re.sub(r'\s+-r\s*$', '', block)
            parts = re.split(r'\s+-r\s+', block, maxsplit=1)
            peer, value = await parse_author(parts[0], reply if index == 0 else None)
            text, entities = self._mfq_parse_text(value)
            entry = self._mfq_entry(peer)
            entry.update(id=index+1, text=text, entities=entities)
            if keep_media and index==0:
                entry['media']=getattr(reply,'media',None)
            if source_reply:
                entry['original_reply'] = SimpleNamespace(reply_to_msg_id=reply.id, reply_to_peer_id=reply.peer_id)
                entry['original_peer'] = reply.peer_id
                entry['source_reply'] = reply
            if len(parts) == 2:
                reply_peer, reply_value = await parse_author(parts[1])
                reply_text, reply_entities = self._mfq_parse_text(reply_value)
                entry['reply'] = dict(peer=reply_peer, text=reply_text, entities=reply_entities)
            entries.append(entry)
        return entries

    @staticmethod
    def _mfq_entry(peer, source=None):
        buttons = []
        for row in getattr(getattr(source, 'reply_markup', None), 'rows', []) or []:
            copied = [SimpleNamespace(text=str(button.text), style=copy.deepcopy(getattr(button, 'style', None)))
                      for button in getattr(row, 'buttons', []) or [] if getattr(button, 'text', None)]
            if copied: buttons.append(copied)
        return dict(peer=peer, text=getattr(source, 'message', '') or '',
                    entities=copy.deepcopy(getattr(source, 'entities', None) or []),
                    media=getattr(source, 'media', None),
                    buttons=buttons,
                    date=getattr(source, 'date', None) or datetime.now(timezone.utc),
                    name=None, rank=getattr(source, 'from_rank', None) or getattr(source, 'post_author', None), role=None, reply=None,
                    via=getattr(source, 'via_bot_id', None) or getattr(source, 'via_business_bot_id', None), status=None,
                    original_reply=getattr(source, 'reply_to', None),
                    original_peer=getattr(source, 'peer_id', None))

    def _mfq_tr(self, state, ru, en):
        return ru if state['ru'] else en

    def _mfq_text(self, state):
        tr = lambda ru, en: self._mfq_tr(state, ru, en)
        current = state['draft'][state['cursor']]
        esc = utils.escape_html
        name = current['name'] or self._name(current['peer'])
        text = self._mfq_edit_text(current)[:900] or tr('Текст не задан', 'No text yet')
        details = [tr('Автор: ', 'Author: ') + esc(name), esc(text)]
        if current['media']: details.append(tr('📎 Медиа прикреплено', '📎 Media attached'))
        button_count = sum(len(row) for row in current.get('buttons', []))
        if button_count: details.append(tr('🔘 Кнопок: ', '🔘 Buttons: ')+str(button_count))
        if current['reply'] or current['original_reply']: details.append(tr('↩ Ответ добавлен', '↩ Reply added'))
        reply = current['reply']
        if isinstance(reply, dict):
            details.append('↩ '+esc(self._name(reply['peer']))+': '+esc(self._mfq_edit_text(reply)[:240] or tr('Текст ответа не задан', 'No reply text yet')))
        elif isinstance(reply, int):
            target = next((e for e in state['draft'] if e['id'] == reply), None)
            if target: details.append('↩ '+esc(target['name'] or self._name(target['peer']))+': '+esc(self._mfq_edit_text(target)[:240]))
        if current['rank']: details.append(tr('Префикс: ', 'Tag: ')+esc(current['rank']))
        if current.get('via'):
            via = current['via']
            username = _GQuoteRenderer.username(via)
            details.append('via '+esc('@'+username if username else str(via)))
        if current.get('status') is not None:
            status = current['status']
            icon = (f'<tg-emoji emoji-id="{status}">⭐</tg-emoji>' if isinstance(status, int) and not isinstance(status, bool)
                    else tr('Стикер', 'Sticker') if isinstance(status, dict)
                    else esc(status) if status else tr('Без статуса', 'No status'))
            details.append(tr('Эмодзи-статус: ', 'Emoji status: ')+icon)
        details.append(esc(current.get('time_label') or current['date'].astimezone(self._quote_timezone()).strftime('%H:%M')))
        title = tr('Фейк-цитата', 'Fake quote')
        waiting = state.get('await_media')
        hint = ''
        if waiting:
            hint = '\n\n'+tr(f"Отправьте следующим сообщением медиа для сообщения {waiting['number']} в этом чате.",
                             f"Send media in this chat for message {waiting['number']}.")
        if state.get('await_status'):
            hint += '\n\n'+tr('Отправьте следующим сообщением эмодзи или стикер в этом чате.',
                                 'Send an emoji or sticker in this chat.')
        if state.get('await_text'):
            hint += '\n\n'+tr('Отправьте текст следующим сообщением в этом чате. Он будет удалён после сохранения.',
                                 'Send the text as the next message in this chat. It will be deleted after saving.')
        return (_RANDOM_EMOJI['message'] + f' <b>GodChat · {title}</b>\n\n'
                + tr('Сообщение', 'Message') + f" {state['cursor']+1} / {len(state['draft'])}\n"
                + '<blockquote>' + '\n'.join(details) + '</blockquote>\n'
                + tr('Оформление — из .gcfg', 'Appearance — from .gcfg') + hint
                + '\n\n<blockquote expandable>' + self._s('markup_hint') + '</blockquote>')

    def _mfq_markup(self, state):
        tr = lambda ru, en: self._mfq_tr(state, ru, en)
        token = state['id']
        def button(ru, en, action, style=None):
            result = dict(text=tr(ru, en), callback=self._mfq_callback, args=(token, action))
            if style: result['style'] = style
            return result
        def inp(ru, en, field, prompt=None):
            entry_id = state['draft'][state['cursor']]['id']
            queries = state.setdefault('input_queries', {})
            query = queries.setdefault((entry_id, field), secrets.token_hex(5))
            return dict(text=tr(ru, en), input=prompt or tr(ru, en), handler=self._mfq_input,
                        args=(token, field, entry_id), style='primary', _switch_query=query)
        close = button('Закрыть', 'Close', 'close', 'danger')
        back = button('Назад', 'Back', 'editor', 'danger')
        if state.get('view') == 'status':
            return [[inp('По ID эмодзи', 'Emoji ID', 'status_id', tr('ID премиум-эмодзи', 'Custom emoji ID'))],
                    [button('Отменить ожидание', 'Cancel waiting', 'status_cancel', 'danger') if state.get('await_status')
                     else button('Следующим сообщением', 'Send next message', 'status_message', 'primary')],
                    [button('Убрать статус', 'Remove status', 'status_clear', 'danger'),
                     button('Вернуть статус автора', 'Restore author status', 'status_reset')],
                    [button('Назад', 'Back', 'extra', 'danger'), close]]
        if state.get('view') == 'reply':
            rows = [[button('Без ответа', 'No reply', 'reply_clear', 'danger')],
                    [inp('Автор ответа', 'Reply author', 'reply_author', '@username / ID'),
                     inp('Текст ответа', 'Reply text', 'reply_text')],
                    [button('Отменить ввод текста', 'Cancel text input', 'text_message_cancel', 'danger')
                     if state.get('await_text', {}).get('field') == 'reply_text'
                     else button('Текст следующим сообщением', 'Text as next message', 'reply_text_message')]]
            for entry in state['draft']:
                if entry['id'] != state['draft'][state['cursor']]['id']:
                    label = f"{state['draft'].index(entry)+1}. " + (entry['text'][:25] or tr('Медиа', 'Media'))
                    rows.append([button(label, label, 'reply:'+str(entry['id']))])
            return rows + [[back, close]]
        if state.get('view') == 'extra':
            return [[inp('Отображаемое имя', 'Display name', 'name'), inp('Префикс', 'Tag', 'rank')],
                    [inp('via @bot', 'via @bot', 'via', '@bot'),
                     *([button('Убрать via', 'Remove via', 'via_clear', 'danger')]
                       if state['draft'][state['cursor']].get('via') else [])],
                    [button('Эмодзи-статус', 'Emoji status', 'status_menu')],
                     [inp('Время HH:MM', 'Time HH:MM', 'time'),
                      button('Сбросить имя и префикс', 'Reset name and tag', 'reset_author')],
                     [inp('Добавить кнопку', 'Add button', 'button_label', tr('Текст кнопки', 'Button text')),
                      *([button('Убрать кнопки', 'Remove buttons', 'buttons_clear', 'danger')]
                        if state['draft'][state['cursor']].get('buttons') else [])],
                     [button('Дублировать', 'Duplicate', 'duplicate'), button('Убрать медиа', 'Remove media', 'media_clear')],
                     [back, close]]
        send_buttons = [button('Отправить PNG', 'Send PNG', 'png')]
        if state.get('options', {}).get('send_format', 'sticker') != 'sticker':
            send_buttons.insert(0, button('Отправить стикер', 'Send sticker', 'sticker', 'success'))
        return [[inp('Автор', 'Author', 'author', '@username / ID'), inp('Текст', 'Text', 'text')],
                [button('Отменить ввод текста', 'Cancel text input', 'text_message_cancel', 'danger')
                 if state.get('await_text', {}).get('field') == 'text'
                 else button('Текст следующим сообщением', 'Text as next message', 'text_message')],
                [button('Отменить добавление медиа', 'Cancel media upload', 'media_cancel', 'danger')
                 if state.get('await_media') else button('Добавить медиа', 'Add media', 'media_add', 'primary')],
                [button('Реплай', 'Reply', 'reply_menu'), button('Дополнительно', 'More', 'extra')],
                 [button('Добавить', 'Add', 'add'), button('Удалить', 'Delete', 'delete', 'danger')],
                 *([[button('←', '←', 'prev'), button('→', '→', 'next')]] if len(state['draft']) > 1 else []),
                 [button('Превью', 'Preview', 'preview')],
                 send_buttons,
                 [close]]

    def _mfq_materialize(self, state, preview=False):
        state['options'] = _GQuoteRenderer.normalize_options(self.get('gquote_options', {}))
        state['resolved_peers'], state['resolved_replies'] = {}, {}
        messages = []
        def make(entry):
            status = entry.get('status')
            status_key = ('sticker', getattr(status.get('document'), 'id', None)) if isinstance(status, dict) else status
            peer_key = 'mfq:'+str(entry['peer'].id)+':'+repr((entry['name'], entry['rank'], entry['role'], status_key))
            state['resolved_peers'][peer_key] = entry['peer']
            via = entry.get('via')
            if via and not isinstance(via, (int, str)): state['resolved_peers'][str(via.id)] = via
            return SimpleNamespace(id=entry['id'], from_id=peer_key, peer_id=state['reply'].peer_id,
                message=entry['text'], entities=entry['entities'], media=entry['media'], date=entry['date'],
                reply_markup=SimpleNamespace(rows=[SimpleNamespace(buttons=row) for row in entry.get('buttons', [])]) if entry.get('buttons') else None,
                display_name=entry['name'], display_rank=entry['rank'], display_role=entry['role'],
                display_status=entry.get('status'), via_bot_id=via if isinstance(via, int) else getattr(via, 'id', None),
                display_time=entry.get('time_label'),
                display_via=self._mfq_tr(state, 'через ', 'via ')+via if isinstance(via, str) else None,
                reply_to=None, is_group=bool(getattr(state['source'], 'is_group', False)), out=False)
        for entry in state['draft']:
            if not entry['text'].strip() and not entry['media']:
                if not preview: raise _GQuoteError('empty_draft_message')
                entry = dict(entry, text=self._mfq_tr(state, 'Текст не задан', 'No text yet'))
            messages.append(make(entry))
        lookup = {m.id: m for m in messages}
        for entry, msg in zip(state['draft'], messages):
            reply = entry['reply']
            if isinstance(reply, int) and reply in lookup:
                msg.reply_to = SimpleNamespace(reply_to_msg_id=reply)
                state['resolved_replies'][(str(msg.peer_id), reply)] = lookup[reply]
            elif isinstance(reply, dict):
                if not reply['text'].strip() and not preview: raise _GQuoteError('empty_reply_text')
                reply_id = -entry['id']
                reply_entry = dict(id=reply_id, peer=reply['peer'], text=reply['text'] or self._mfq_tr(state, 'Текст ответа не задан', 'No reply text yet'), entities=reply.get('entities', []),
                                   media=reply.get('media'), date=entry['date'], name=None, rank=None, role=None)
                msg.reply_to = SimpleNamespace(reply_to_msg_id=reply_id)
                state['resolved_replies'][(str(msg.peer_id), reply_id)] = make(reply_entry)
            elif entry['original_reply']:
                msg.reply_to = copy.copy(entry['original_reply'])
                if entry['original_peer']:
                    msg.reply_to.reply_to_peer_id = entry['original_peer']
                source_reply = entry.get('source_reply')
                if source_reply:
                    source_peer = getattr(msg.reply_to, 'reply_to_peer_id', None) or msg.peer_id
                    state['resolved_replies'][(str(source_peer), msg.reply_to.reply_to_msg_id)] = source_reply
        state['messages'], state['selected'] = messages, {m.id for m in messages}
        state['pages'], state['dirty'] = [], True

    async def _mfq_render(self, state, action):
        task = asyncio.current_task()
        state['task'] = task
        self._gquote_tasks.add(task)
        try:
            if state.get('closed'): return
            invalid = next((index+1 for index, entry in enumerate(state['draft'])
                            if (not entry['text'].strip() and not entry['media'])
                            or (isinstance(entry['reply'], dict) and not entry['reply']['text'].strip())), None)
            if invalid is not None and action != 'preview':
                text = self._mfq_tr(state, f'Добавьте текст или медиа в сообщение {invalid}; если задан ответ — заполните его текст.',
                                   f'Add text or media to message {invalid}; if it has a reply, fill in its text.')
                return await self._inline_answer(state['status'], self._mfq_text(state)+'\n\n'+text, self._mfq_markup(state))
            self._mfq_materialize(state, preview=action == 'preview')
            await self._gq_run(state, preview=action == 'preview', document=action != 'sticker')
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._gq_failure(state, error)
        finally:
            if state.get('task') is task: state['task'] = None
            self._gquote_tasks.discard(task)

    async def _mfq_refresh(self, state, changed=True):
        if changed: state['dirty'], state['pages'] = True, []
        await self._inline_answer(state['status'], self._mfq_text(state), self._mfq_markup(state))

    async def _mfq_input(self, call, value, token, field, entry_id):
        state = self._gq_get(token)
        if not state: return await call.answer(self._s('gq_expired'), show_alert=True)
        while state.get('task'):
            pending = state['task']
            try:
                await asyncio.wait_for(asyncio.shield(pending), 180)
            except asyncio.TimeoutError:
                return await self._inline_answer(state['status'], self._mfq_text(state)+'\n\n'+self._s('gq_busy'), self._mfq_markup(state))
            except asyncio.CancelledError:
                if state.get('closed'): return
                raise
            if state.get('closed') or not self._gq_get(token): return
        if state.get('closed'): return
        entry = next((e for e in state['draft'] if e['id'] == entry_id), None)
        if entry is None: return await call.answer(self._s('gq_expired'), show_alert=True)
        tr = lambda ru, en: self._mfq_tr(state, ru, en)
        value = value.strip()
        limit = 16384 if field in ('text', 'reply_text') else 64 if field == 'button_label' else 128
        if not value or len(value) > limit:
            return await self._inline_answer(state['status'], self._mfq_text(state)+'\n\n'+tr('Некорректный ввод.', 'Invalid input.'), self._mfq_markup(state))
        if field in ('text', 'reply_text') and len(value.encode('utf-16-le')) // 2 >= 240:
            return await self._inline_answer(
                state['status'],
                self._mfq_text(state)+'\n\n'+tr(
                    'Inline-ввод обрезает длинный текст. Используйте кнопку «Текст следующим сообщением».',
                    'Inline input truncates long text. Use “Text as next message”.'),
                self._mfq_markup(state),
            )
        task = asyncio.current_task(); state['task'] = task; self._gquote_tasks.add(task)
        try:
            if field in ('author', 'reply_author'):
                if not re.fullmatch(r'@[A-Za-z0-9_]+|-?\d+', value): raise ValueError('author')
                peer = await asyncio.wait_for(self.client.get_entity(int(value) if value.lstrip('-').isdigit() else value), 20)
                if state.get('closed'): return
                if field == 'author': entry.update(peer=peer, name=None, rank=None, role=None)
                else:
                    old = entry['reply'] if isinstance(entry['reply'], dict) else {}
                    entry['reply'] = dict(peer=peer, text=old.get('text', ''), entities=old.get('entities', []))
                    entry['original_reply'] = None
            elif field == 'text':
                text, entities = self._mfq_parse_text(value)
                entry.update(text=text, entities=entities)
            elif field == 'via':
                entry['via'] = value
            elif field == 'status_id':
                if not re.fullmatch(r'[1-9]\d{0,18}', value): raise ValueError('emoji_id')
                identity = int(value)
                docs = await asyncio.wait_for(self.client(functions.messages.GetCustomEmojiDocumentsRequest([identity])), 20)
                if not any(getattr(d, 'id', None) == identity for d in docs): raise ValueError('emoji_missing')
                if state.get('closed'): return
                entry['status'] = identity
                state.pop('await_status', None)
            elif field in ('name', 'rank'): entry[field] = value
            elif field == 'reply_text':
                text, entities = self._mfq_parse_text(value)
                old = entry['reply'] if isinstance(entry['reply'], dict) else {}
                entry['reply'] = dict(peer=old.get('peer', entry['peer']), text=text, entities=entities)
                entry['original_reply'] = None
            elif field == 'time':
                if not re.fullmatch(r'[0-9]{1,4}:[0-9]{1,4}', value): raise ValueError('time')
                entry['time_label'] = value
            elif field == 'button_label':
                if sum(len(row) for row in entry.get('buttons', [])) >= 16:
                    raise ValueError('button_limit')
                entry.setdefault('buttons', []).append([SimpleNamespace(text=value, style=None)])
            else: return
        except asyncio.CancelledError: raise
        except Exception:
            return await self._inline_answer(state['status'], self._mfq_text(state)+'\n\n'+tr('Не удалось применить значение. Проверьте ввод.', 'Could not apply value. Check input.'), self._mfq_markup(state))
        finally:
            state['task'] = None; self._gquote_tasks.discard(task)
        await self._mfq_refresh(state)

    def _mfq_parse_text(self, value):
        text, entities = tl_utils.sanitize_parse_mode('html').parse(self._quote_template_markup(value))
        if not text.strip() or len(text.encode('utf-16-le')) // 2 > 4096:
            raise ValueError('text_length')
        return text, entities

    @staticmethod
    def _mfq_edit_text(entry):
        text = tl_utils.sanitize_parse_mode('html').unparse(entry['text'], entry.get('entities', []))
        text = text.replace('<blockquote expandable>', '<qe>').replace('<blockquote>', '<q>')
        stack = []
        def close_quote(match):
            tag = match.group(0)
            if tag in ('<q>', '<qe>'):
                stack.append(tag[1:-1]); return tag
            return '</'+(stack.pop() if stack else 'q')+'>'
        return re.sub(r'<q>|<qe>|</blockquote>', close_quote, text)

    async def _mfq_callback(self, call, token, action):
        state = self._gq_get(token)
        if not state: return await call.answer(self._s('gq_expired'), show_alert=True)
        if action == 'close':
            preview = state.get('preview')
            await self._gq_callback(call, token, 'close')
            if preview:
                try: await preview.delete()
                except Exception: logger.debug('mfq preview cleanup failed', exc_info=True)
            return
        if state.get('task'): return await call.answer(self._s('gq_busy'), show_alert=True)
        await call.answer()
        if action in ('preview', 'png', 'sticker'):
            return await self._mfq_render(state, action)
        entries = state['draft']; index = state['cursor']; entry = entries[index]
        if action in ('text_message', 'reply_text_message'):
            chat = str(state['source'].peer_id)
            for other in self._gquote_sessions.values():
                if str(other['source'].peer_id) == chat:
                    other.pop('await_text', None)
                    other.pop('await_media', None)
                    other.pop('await_status', None)
            state['await_text'] = dict(entry_id=entry['id'], field='reply_text' if action == 'reply_text_message' else 'text',
                                       chat=chat, after_id=state['source'].id, expires=time.monotonic()+300)
        elif action == 'text_message_cancel':
            state.pop('await_text', None)
        elif action == 'media_add':
            chat = str(state['source'].peer_id)
            for other in self._gquote_sessions.values():
                if str(other['source'].peer_id) == chat:
                    other.pop('await_media', None); other.pop('await_status', None); other.pop('await_text', None)
            state['await_media'] = dict(entry_id=entry['id'], number=index+1, chat=chat,
                                       after_id=state['source'].id, expires=time.monotonic()+300)
        elif action == 'media_cancel': state.pop('await_media', None)
        elif action == 'status_message':
            chat = str(state['source'].peer_id)
            for other in self._gquote_sessions.values():
                if str(other['source'].peer_id) == chat:
                    other.pop('await_media', None); other.pop('await_status', None); other.pop('await_text', None)
            state['await_status'] = dict(entry_id=entry['id'], chat=chat, after_id=state['source'].id,
                                        expires=time.monotonic()+300)
        elif action == 'status_cancel': state.pop('await_status', None)
        elif action in ('status_clear', 'status_reset'):
            entry['status'] = False if action == 'status_clear' else None
            state.pop('await_status', None)
        elif action == 'via_clear': entry['via'] = None
        elif action in ('add', 'duplicate'):
            if len(entries) >= _GQuoteRenderer.MAX_MESSAGES:
                return await call.answer(self._s('gq_count_bad'), show_alert=True)
            new = copy.copy(entry) if action == 'duplicate' else self._mfq_entry(entry['peer'])
            new['entities'] = copy.deepcopy(new['entities'])
            new['buttons'] = copy.deepcopy(new.get('buttons', []))
            if isinstance(new.get('reply'), dict): new['reply'] = dict(new['reply'])
            new['id'] = state['next_id']; state['next_id'] += 1
            entries.insert(index+1, new); state['cursor'] += 1; state['view'] = 'editor'
        elif action == 'delete':
            if len(entries) == 1:
                return await call.answer(self._mfq_tr(state, 'Нужно хотя бы одно сообщение.', 'At least one message is required.'), show_alert=True)
            entries.pop(index); state['cursor'] = min(index, len(entries)-1)
            if state.get('await_media', {}).get('entry_id') == entry['id']: state.pop('await_media', None)
            if state.get('await_status', {}).get('entry_id') == entry['id']: state.pop('await_status', None)
            if state.get('await_text', {}).get('entry_id') == entry['id']: state.pop('await_text', None)
            for item in entries:
                if item['reply'] == entry['id']: item['reply'] = None
        elif action in ('prev', 'next'): state['cursor'] = (index + (-1 if action == 'prev' else 1)) % len(entries)
        elif action in ('editor', 'extra', 'reply_menu', 'status_menu'):
            state['view'] = {'reply_menu': 'reply', 'status_menu': 'status'}.get(action, action)
        elif action == 'reply_clear': entry.update(reply=None, original_reply=None)
        elif action.startswith('reply:'):
            identity = int(action.split(':', 1)[1])
            if identity == entry['id'] or not any(e['id'] == identity for e in entries): return
            entry.update(reply=identity, original_reply=None); state['view'] = 'editor'
        elif action == 'media_clear': entry['media'] = None
        elif action == 'buttons_clear': entry['buttons'] = []
        elif action == 'reset_author': entry.update(name=None, rank=None, role=None)
        else: return
        await self._mfq_refresh(state, changed=action not in ('prev', 'next', 'editor', 'extra', 'reply_menu',
                                'media_add', 'media_cancel', 'status_menu', 'status_message', 'status_cancel',
                                'text_message', 'reply_text_message', 'text_message_cancel'))

    @loader.watcher('only_messages', 'out')
    async def _mfq_text_watcher(self, message):
        if not getattr(message, 'out', False) or getattr(message, 'via_bot_id', None): return
        value = getattr(message, 'raw_text', None) or getattr(message, 'message', '') or ''
        if not value: return
        for token, state in tuple(self._gquote_sessions.items()):
            waiting = state.get('await_text')
            if not waiting: continue
            if not self._gq_get(token) or waiting['expires'] < time.monotonic():
                state.pop('await_text', None); continue
            if str(message.peer_id) != waiting['chat'] or message.id <= waiting['after_id']: continue
            if message.id == getattr(state.get('preview'), 'id', None): continue
            entry = next((e for e in state['draft'] if e['id'] == waiting['entry_id']), None)
            if entry is None:
                state.pop('await_text', None); return
            pending = state.get('task')
            if pending:
                try: await asyncio.shield(pending)
                except asyncio.CancelledError:
                    if state.get('closed'): return
                    raise
            if state.get('closed') or not self._gq_get(token) or entry not in state['draft']: return
            try:
                text, entities = self._mfq_parse_text(value)
            except Exception:
                await self._inline_answer(
                    state['status'],
                    self._mfq_text(state)+'\n\n'+self._mfq_tr(
                        state, 'Не удалось разобрать текст. Отправьте исправленный текст.',
                        'Could not parse the text. Send a corrected message.'),
                    self._mfq_markup(state),
                )
                return
            state.pop('await_text', None)
            if waiting['field'] == 'reply_text':
                old = entry['reply'] if isinstance(entry['reply'], dict) else {}
                entry['reply'] = dict(peer=old.get('peer', entry['peer']), text=text, entities=entities)
                entry['original_reply'] = None
            else:
                entry.update(text=text, entities=entities)
            try: await message.delete()
            except Exception: logger.debug('mfq text input cleanup failed', exc_info=True)
            await self._mfq_refresh(state)
            return

    @loader.watcher('only_messages', 'out')
    async def _mfq_status_watcher(self, message):
        if not getattr(message, 'out', False) or getattr(message, 'via_bot_id', None): return
        media = getattr(message, 'media', None)
        document = getattr(media, 'document', None)
        sticker = document and any(self.kind_for_quote(attr) == 'DocumentAttributeSticker'
                                   for attr in getattr(document, 'attributes', []) or [])
        if self.kind_for_quote(media) in ('MessageMediaPhoto', 'MessageMediaDocument') and not sticker: return
        text = getattr(message, 'raw_text', None) or getattr(message, 'message', '') or getattr(media, 'emoticon', '') or ''
        for token, state in tuple(self._gquote_sessions.items()):
            waiting = state.get('await_status')
            if not waiting: continue
            if not self._gq_get(token) or waiting['expires'] < time.monotonic():
                state.pop('await_status', None); continue
            if str(message.peer_id) != waiting['chat'] or message.id <= waiting['after_id']: continue
            if message.id == getattr(state.get('preview'), 'id', None): continue
            if any(getattr(attr, 'file_name', '').startswith(f"gquote_{state['id']}_")
                   for attr in getattr(document, 'attributes', []) or []): continue
            identity = {'document': document} if sticker else next((getattr(e, 'document_id', None) for e in getattr(message, 'entities', []) or []
                             if self.kind_for_quote(e) == 'MessageEntityCustomEmoji'), None)
            if not identity:
                import regex
                identity = next((part for part in regex.findall(r'\X', text)
                                 if regex.search(r'\p{Extended_Pictographic}|\p{Regional_Indicator}|\u20e3', part)), None)
                if not identity and re.fullmatch(r"(?:[:;=8xX][-^']?[)(DPpOo/\\]|[)(][-^']?[:;=8]|<3)", text.strip()):
                    identity = text.strip()
            if not identity: continue
            entry = next((e for e in state['draft'] if e['id'] == waiting['entry_id']), None)
            state.pop('await_status', None)
            if entry is None: return
            pending = state.get('task')
            if pending:
                try: await asyncio.shield(pending)
                except asyncio.CancelledError:
                    if state.get('closed'): return
                    raise
            if state.get('closed') or not self._gq_get(token) or entry not in state['draft']: return
            entry['status'] = identity
            await self._mfq_refresh(state)
            return

    @loader.watcher('only_messages', 'out')
    async def _mfq_media_watcher(self, message):
        if not getattr(message, 'out', False): return
        media = getattr(message, 'media', None)
        if self.kind_for_quote(media) not in ('MessageMediaPhoto', 'MessageMediaDocument'): return
        for token, state in tuple(self._gquote_sessions.items()):
            waiting = state.get('await_media')
            if not waiting: continue
            if not self._gq_get(token) or waiting['expires'] < time.monotonic():
                state.pop('await_media', None)
                continue
            if str(message.peer_id) != waiting['chat'] or message.id <= waiting['after_id']: continue
            if message.id == getattr(state.get('preview'), 'id', None): continue
            document = getattr(media, 'document', None)
            if any(getattr(attr, 'file_name', '').startswith(f"gquote_{state['id']}_")
                   for attr in getattr(document, 'attributes', []) or []): continue
            entry = next((e for e in state['draft'] if e['id'] == waiting['entry_id']), None)
            if entry is None:
                state.pop('await_media', None)
                return
            state.pop('await_media', None)
            pending = state.get('task')
            if pending:
                try: await asyncio.shield(pending)
                except asyncio.CancelledError:
                    if state.get('closed'): return
                    raise
            if state.get('closed') or not self._gq_get(token) or entry not in state['draft']: return
            entry['media'] = media
            if not entry['text'] and getattr(message, 'message', None):
                entry['text'] = message.message
                entry['entities'] = copy.deepcopy(getattr(message, 'entities', None) or [])
            await self._mfq_refresh(state)
            return

    @loader.command(ru_doc=" - настройки GodChat", en_doc=' - GodChat settings')
    async def gcfg(self, message: Message):
        if utils.get_args_raw(message).strip():
            return await self._answer_temporary(message, self._s("no_arguments"), 12)
        await self._gq_start(message, 1, config=True)

    def _gcfg_markup(self, token):
        state = getattr(self, '_gquote_sessions', {}).get(token, {})
        source = state.get('source')
        in_chat = bool(getattr(source, 'is_group', False) or getattr(source, 'is_channel', False))
        is_channel = bool(state.get('gcfg_channel'))

        def section(label, name, emoji_id):
            return {'text': self._s(label), 'callback': self._gcfg_open,
                    'args': (token, name), 'emoji_id': emoji_id}

        quotes = section('gcfg_quotes_short', 'quotes', '5253590213917158323')
        names = section('gcfg_names', 'names', '5188678912883827293')
        timezone = section('timezone_title', 'timezone', '5870921681735781843')
        close = {'text': self._s('gq_close'), 'callback': self._gq_callback,
                 'args': (token, 'close'), 'style': 'danger',
                 'emoji_id': '5121063440311386962'}
        rows = []
        if in_chat:
            chat = section('gcfg_channel_short' if is_channel else 'gcfg_chat_short',
                           'chat', '5879841310902324730')
            rows.append([chat, quotes])
            if is_channel:
                rows.append([names, timezone])
                rows.append([close])
            else:
                rows.append([section('gcfg_panic_short', 'panic', '4904936030232117798'), names])
                rows.append([timezone, close])
        else:
            rows.extend(([quotes, names], [timezone, close]))
        return rows

    def _names_saved(self):
        saved = self.get('name_overrides', {})
        return saved if isinstance(saved, dict) else {}

    def _names_text(self, state):
        tr = lambda a, b: a if state['ru'] else b
        text = _RANDOM_EMOJI['user']+' <b>GodChat · '+self._s('gcfg_names')+'</b>'
        if state.get('names_view') == 'user':
            user = state['names_user']
            username = self._username(user)
            text += '\n\n<blockquote>'+tr('Имя пользователя: ', 'Original name: ')+utils.escape_html(self._original_name(user))
            if username: text += '\n@'+utils.escape_html(username)
            text += '\nID: <code>'+str(user.id)+'</code>\n'+tr('Ваше имя: ', 'Your name: ')
            text += utils.escape_html(self._custom_name(user) or tr('не задано', 'not set'))+'</blockquote>'
        elif state.get('names_view') == 'saved':
            text += '\n\n<blockquote>'+tr('Сохранённые имена: ', 'Saved names: ')+str(len(self._names_saved()))+'</blockquote>'
        else:
            text += '\n\n<blockquote>'+tr('Выберите пользователя по ID или @username и задайте своё имя.',
                                            'Select a user by ID or @username and set a custom name.')+'</blockquote>'
        return text

    def _names_markup(self, state):
        tr = lambda a, b: a if state['ru'] else b
        token = state['id']
        def btn(a, b, action, style=None):
            result = dict(text=tr(a,b), callback=self._names_callback, args=(token,action))
            if style: result['style'] = style
            return result
        def inp(a, b, field, user_id=None):
            query = state.setdefault('names_queries', {}).setdefault((field,user_id), secrets.token_hex(5))
            return dict(text=tr(a,b), input=tr(a,b), handler=self._names_input, args=(token,field,user_id),
                        _switch_query=query, style='primary')
        close = dict(text=self._s('gq_close'), callback=self._gq_callback, args=(token,'close'), style='danger')
        back = btn('Назад','Back','main','danger')
        if state.get('names_view') == 'user':
            user = state['names_user']
            rows = [[inp('Задать имя','Set name','name',user.id)]]
            if self._custom_name(user): rows.append([btn('Удалить подмену','Remove custom name','delete','danger')])
            return rows+[[btn('Сохранённые','Saved names','saved')],[back,close]]
        if state.get('names_view') == 'saved':
            records = sorted(self._names_saved().items(), key=lambda pair: str(pair[1].get('name','')).casefold())
            page = max(0,min(state.get('names_page',0),max(0,(len(records)-1)//6)))
            state['names_page'] = page
            rows = [[btn(record.get('name',identity)[:40], record.get('name',identity)[:40], 'open:'+identity)]
                    for identity, record in records[page*6:page*6+6]]
            if len(records)>6:
                rows.append([btn('←','←','page:-1'),btn(f'{page+1}/{(len(records)+5)//6}',f'{page+1}/{(len(records)+5)//6}','saved'),btn('→','→','page:1')])
            return rows+[[back,close]]
        return [[inp('Выбрать пользователя','Select user','user')], [btn('Сохранённые','Saved names','saved')],
                [dict(text=self._s('gq_back'), callback=self._gcfg_open, args=(token,'main'), style='danger'),close]]

    async def _names_refresh(self, state, error=None):
        text = self._names_text(state)
        if error: text += '\n\n'+utils.escape_html(error)
        await self._inline_answer(state['status'], text, self._names_markup(state))

    def _names_invalidate(self):
        for state in self._gquote_sessions.values():
            state['dirty'] = True
            state['pages'] = []
        getattr(self, '_member_cache', {}).clear()

    async def _names_input(self, call, value, token, field, user_id=None):
        state = self._gq_get(token)
        if not state: return await call.answer(self._s('gq_expired'),show_alert=True)
        if state.get('task'): return await call.answer(self._s('gq_busy'),show_alert=True)
        value = value.strip()
        tr = lambda a, b: a if state['ru'] else b
        task = asyncio.current_task(); state['task'] = task; self._gquote_tasks.add(task)
        try:
            if field == 'user':
                if not re.fullmatch(r'@[A-Za-z0-9_]+|[1-9]\d{0,18}',value): raise ValueError('user')
                user = await asyncio.wait_for(self.client.get_entity(int(value) if value.isdigit() else value),20)
                if self.kind_for_quote(user) not in ('User','UserEmpty'): raise ValueError('not_user')
                if state.get('closed'): return
                state.update(names_user=user,names_view='user')
            elif field == 'name':
                user = state.get('names_user')
                if user is None or user.id != user_id: raise ValueError('stale_input')
                if not value or len(value)>128 or any(ord(c)<32 for c in value): raise ValueError('name')
                saved = copy.deepcopy(self._names_saved())
                if len(saved)>=1000 and str(user.id) not in saved: raise ValueError('limit')
                saved[str(user.id)] = dict(name=value, original=self._original_name(user), username=self._username(user))
                self._save_state('name_overrides',saved)
                self._names_invalidate()
            else: return
            await self._names_refresh(state)
        except asyncio.CancelledError: raise
        except Exception:
            if not state.get('closed'):
                await self._names_refresh(state,tr('Не удалось применить значение. Проверьте пользователя или имя.',
                                                  'Could not apply the value. Check the user or name.'))
        finally:
            state['task'] = None; self._gquote_tasks.discard(task)

    async def _names_callback(self, call, token, action):
        state = self._gq_get(token)
        if not state: return await call.answer(self._s('gq_expired'),show_alert=True)
        if state.get('task'): return await call.answer(self._s('gq_busy'),show_alert=True)
        await call.answer()
        if action == 'main': state['names_view'] = 'main'
        elif action == 'saved': state['names_view'] = 'saved'
        elif action.startswith('page:'):
            state['names_page'] = max(0,state.get('names_page',0)+int(action[5:]))
            state['names_view'] = 'saved'
        elif action.startswith('open:'):
            identity = action[5:]; record = self._names_saved().get(identity)
            if not record: return await self._names_refresh(state)
            state['names_user'] = SimpleNamespace(id=int(identity),first_name=record.get('original',''),
                                                  last_name=None,username=record.get('username'))
            state['names_view'] = 'user'
        elif action == 'delete':
            user = state.get('names_user')
            if user is None: return
            saved = copy.deepcopy(self._names_saved()); saved.pop(str(user.id),None)
            self._save_state('name_overrides',saved); self._names_invalidate()
        else: return
        await self._names_refresh(state)

    def _gcfg_text(self, token=None):
        return f"{_EMOJI['reason']} <b>{self._s('gcfg_title')}</b>"

    async def _gcfg_open(self, call, token, section):
        state = self._gq_get(token)
        if not state:
            return await call.answer(self._s("gq_expired"), show_alert=True)
        if state.get("task"):
            return await call.answer(self._s("gq_busy"), show_alert=True)
        if section != 'panic':
            await call.answer()
        if section == "timezone":
            await call.edit(self._timezone_text(), reply_markup=self._timezone_markup(token))
        elif section == "quotes":
            state['gq_view']='main'
            await call.edit(self._gq_text(state), reply_markup=self._gq_markup(state))
        elif section == 'names':
            state['names_view'] = 'main'
            await self._names_refresh(state)
        elif section == "chat":
            try:
                entity = await asyncio.wait_for(self.client.get_entity(state['source'].peer_id), 20)
                if self.kind_for_quote(entity) not in ('Channel', 'Chat'):
                    return await call.answer(self._s('gcfg_chat_only'), show_alert=True)
                permissions = None
                try:
                    permissions = await asyncio.wait_for(self.client.get_permissions(entity, self._me_id), 20)
                except Exception:
                    logger.warning('gcfg chat permissions unavailable', exc_info=True)
                await call.edit(self._gcfg_chat_text(entity, permissions, state['ru']), reply_markup=[
                    [{'text': self._s('gcfg_refresh'), 'callback': self._gcfg_open, 'args': (token, 'chat')}],
                    [{'text': self._s('gq_back'), 'callback': self._gcfg_open, 'args': (token, 'main'), 'style': 'danger'},
                     {'text': self._s('gq_close'), 'callback': self._gq_callback, 'args': (token, 'close'), 'style': 'danger'}]])
            except Exception:
                logger.exception('gcfg chat inspection failed')
                await call.answer(self._s('chat_fetch_failed'), show_alert=True)
        elif section == "panic":
            await self._panic_menu(call, state)
        else:
            await call.edit(self._gcfg_text(token), reply_markup=self._gcfg_markup(token))

    def _panic_config(self, chat_id):
        saved = self._panic_settings.get(str(chat_id), {})
        result = dict(_PANIC_DEFAULTS)
        if isinstance(saved, dict):
            for key in ("auto", "close", "slow", "requests"):
                if type(saved.get(key)) is bool:
                    result[key] = saved[key]
            for key, minimum, maximum in (("joins", 1, 100), ("window", 1, 3600)):
                value = saved.get(key)
                if type(value) is int and minimum <= value <= maximum:
                    result[key] = value
        return result

    @staticmethod
    def _panic_has_actions(config):
        return any(config[key] for key in ("close", "slow", "requests"))

    def _panic_chat_id(self, state):
        return str(int(state["source"].chat_id))

    async def _panic_menu(self, call, state):
        try:
            entity = await self.client.get_entity(state["source"].peer_id)
        except Exception:
            return await call.answer(self._s("chat_fetch_failed"), show_alert=True)
        if not isinstance(entity, types.Channel) or not getattr(entity, "megagroup", False):
            return await call.answer(self._s("panic_supergroup_menu"), show_alert=True)
        await call.answer()
        chat_id = self._panic_chat_id(state)
        config = self._panic_config(chat_id)
        active = bool(self._chat_controls.get(chat_id, {}).get("panic_active"))
        flag = lambda value: _EMOJI["success"] if value else _EMOJI["off"]
        toggle_id = lambda value: "5206607081334906820" if value else "5121063440311386962"
        text = (
            f"{_EMOJI['warning']} <b>GodChat · {self._s('panic_settings_title')}</b>\n\n"
            f"<blockquote>{self._s('panic_now')}: {flag(active)}\n"
            f"{self._s('panic_auto')}: {flag(config['auto'])}\n"
            f"{self._s('panic_joins')}: {config['joins']} / {config['window']} {self._s('panic_seconds')}\n"
            f"{self._s('panic_close')}: {flag(config['close'])}\n"
            f"{self._s('panic_slow')}: {flag(config['slow'])}\n"
            f"{self._s('panic_requests')}: {flag(config['requests'])}</blockquote>"
        )
        if active:
            text += f"\n\n<i>{self._s('panic_changes_next')}</i>"
        token = state["id"]
        rows = [[{"text": self._s("panic_auto"), "callback": self._panic_menu_toggle,
                 "args": (token, "auto"), "emoji_id": toggle_id(config["auto"]),
                 "style": "success" if config["auto"] else "danger"}]]
        number_buttons = []
        for key, label, value, minimum, maximum in (
            ("joins", "panic_joins", config["joins"], 1, 100),
            ("window", "panic_window", config["window"], 1, 3600),
        ):
            number_buttons.append({"text": f"{self._s(label)}: {value}",
                                   "input": f"{self._s('panic_number_prompt')}: {minimum}–{maximum}",
                                   "handler": self._panic_menu_number, "args": (token, key),
                                   "emoji_id": "5188678912883827293" if key == "joins" else "5870921681735781843"})
        rows.append(number_buttons)
        action_buttons = []
        for key, label in (("close", "panic_close"), ("slow", "panic_slow"), ("requests", "panic_requests")):
            action_buttons.append({"text": self._s("panic_slow_button" if key == "slow" else label),
                                   "callback": self._panic_menu_toggle, "args": (token, key),
                                   "emoji_id": toggle_id(config[key]),
                                   "style": "success" if config[key] else "danger"})
        rows.append(action_buttons[:2])
        rows.append(action_buttons[2:])
        rows.append([{"text": self._s("gq_back"), "callback": self._gcfg_open,
                      "args": (token, "main"), "style": "primary"}])
        await call.edit(text, reply_markup=rows)

    async def _panic_menu_toggle(self, call, token, key):
        state = self._gq_get(token)
        if not state:
            return await call.answer(self._s("gq_expired"), show_alert=True)
        if key not in ("auto", "close", "slow", "requests"):
            return
        chat_id = self._panic_chat_id(state)
        config = self._panic_config(chat_id)
        next_value = not config[key]
        if key == "auto" and next_value and not self._panic_has_actions(config):
            return await call.answer(self._s("panic_choose_action"), show_alert=True)
        if key != "auto" and not next_value and config["auto"] and not any(
            config[action] for action in ("close", "slow", "requests") if action != key
        ):
            return await call.answer(self._s("panic_choose_action"), show_alert=True)
        config[key] = next_value
        self._panic_settings[chat_id] = config
        self._save_state("panic_settings", self._panic_settings)
        if key == "auto":
            self._panic_joins.pop(chat_id, None)
        await self._panic_menu(call, state)

    async def _panic_menu_number(self, call, data, token, key):
        call = self._input_source_form(call)
        state = self._gq_get(token)
        if not state:
            return await call.answer(self._s("gq_expired"), show_alert=True)
        limits = {"joins": (1, 100), "window": (1, 3600)}
        if key not in limits:
            return
        raw = str(data or "").strip()
        if not raw.isascii() or not raw.isdecimal():
            return await call.answer(self._s("panic_number_bad"), show_alert=True)
        value = int(raw)
        minimum, maximum = limits[key]
        if not minimum <= value <= maximum:
            return await call.answer(self._s("panic_number_bad"), show_alert=True)
        chat_id = self._panic_chat_id(state)
        config = self._panic_config(chat_id)
        config[key] = value
        self._panic_settings[chat_id] = config
        self._save_state("panic_settings", self._panic_settings)
        if key in ("joins", "window"):
            self._panic_joins.pop(chat_id, None)
        await self._panic_menu(call, state)

    def _gcfg_chat_text(self, entity, permissions, ru):
        def tr(a, b): return a if ru else b
        def flag(value): return tr('неизвестно','unknown') if value is None else tr('да','yes') if value else tr('нет','no')
        broadcast = bool(getattr(entity, 'broadcast', False))
        title = utils.escape_html(getattr(entity,'title',''))
        kind = tr('Канал','Channel') if broadcast else tr('Супергруппа','Supergroup') if getattr(entity,'megagroup',False) else tr('Группа','Group')
        lines = [f'<b>{kind}</b>: {title}', '<b>ID:</b> <code>'+str(tl_utils.get_peer_id(entity))+'</code>']
        for attr, a, b in (
            ('join_request','Заявки на вступление','Join requests'),
            ('noforwards','Защита от пересылки','Content protection'),
            ('forum','Форум','Forum'), ('slowmode_enabled','Медленный режим','Slow mode'),
            ('join_to_send','Вступление для отправки сообщений','Join to send')):
            if broadcast and attr in ('forum','slowmode_enabled','join_to_send'): continue
            lines.append(f'<b>{tr(a,b)}:</b> {flag(getattr(entity,attr,None))}')
        blocks = ['<blockquote>'+'\n'.join(lines)+'</blockquote>']
        if not broadcast:
            rights = getattr(entity,'default_banned_rights',None)
            lines = []
            for attr,a,b in (('send_plain','Текст','Text'),('send_photos','Фото','Photos'),
                ('send_videos','Видео','Videos'),('send_stickers','Стикеры','Stickers'),
                ('send_gifs','GIF','GIF'),('send_polls','Опросы','Polls'),
                ('invite_users','Приглашения','Invitations'),('pin_messages','Закрепления','Pin messages')):
                value = getattr(rights,attr,None)
                if attr.startswith('send_') and rights is not None:
                    if getattr(rights,'view_messages',False) or getattr(rights,'send_messages',False): value=True
                    if attr in ('send_photos','send_videos') and getattr(rights,'send_media',False): value=True
                lines.append(f'{tr(a,b)}: {flag(None if value is None else not value)}')
            blocks.append('<b>'+tr('Разрешено участникам','Allowed for members')+'</b>\n<blockquote>'+'\n'.join(lines)+'</blockquote>')
        lines=[]
        creator = bool(getattr(permissions,'is_creator',False))
        admin_rights = getattr(getattr(permissions,'participant',None),'admin_rights',None)
        for attr,a,b in (('ban_users','Блокировать участников','Ban members'),('delete_messages','Удалять сообщения','Delete messages'),
            ('invite_users','Приглашать участников','Invite members'),('pin_messages','Закреплять сообщения','Pin messages'),
            ('add_admins','Назначать администраторов','Add admins'),('manage_ranks','Менять префиксы','Manage ranks')):
            value = True if creator else getattr(permissions,attr,getattr(admin_rights,attr,None)) if permissions is not None else None
            lines.append(f'{tr(a,b)}: {flag(value)}')
        blocks.append('<b>'+tr('Ваши права','Your permissions')+'</b>\n<blockquote>'+'\n'.join(lines)+'</blockquote>')
        return _EMOJI['reason']+' <b>GodChat · '+self._s('gcfg_channel' if broadcast else 'gcfg_chat')+'</b>\n\n'+'\n\n'.join(blocks)

    async def _gq_start(self, message, count, config=False, trigger=False, user_only=False):
        reply = await self._get_reply_message(message)
        if not reply and not config:
            return await self._answer_temporary(message, self._s("gq_reply"), 12)
        for token, old in tuple(self._gquote_sessions.items()):
            if not self._gq_get(token) and not old.get("task"):
                self._gquote_sessions.pop(token, None)
        if len(self._gquote_sessions) >= 4:
            if trigger:
                return
            return await self._answer_temporary(message, self._s("gq_full"), 12)
        options = _GQuoteRenderer.normalize_options(self.get("gquote_options", {}))
        token = secrets.token_hex(4)
        state = dict(id=token, source=message, reply=reply, messages=[], selected=set(), options=options,
                     created=time.monotonic(), ru=self._s("gq_theme") == "Тема", stage="history", warnings=[], pages=[], dirty=True, config=config, trigger=trigger)
        self._gquote_sessions[token] = state
        if config:
            state["messages"] = [reply] if reply else []
            state["selected"] = {reply.id} if reply else set()
            state["gcfg"] = True
            state["gcfg_channel"] = bool(getattr(message, 'is_channel', False) and not getattr(message, 'is_group', False))
            try:
                state["status"] = await self._open_inline_status(
                    message, self._gcfg_text(token), self._gcfg_markup(token),
                )
            except Exception:
                self._gquote_sessions.pop(token, None)
                raise
            return
        task = asyncio.current_task()
        state["task"] = task
        self._gquote_tasks.add(task)
        try:
            state["messages"] = await asyncio.wait_for(
                self._gq_collect(reply, count, exclude_id=message.id, user_only=user_only), 40)
            state["selected"] = {m.id for m in state["messages"]}
            state["status"] = await self._open_inline_status(message, self._s("gq_work"), self._gq_markup(state, True))
            await self._gq_run(state, preview=config, document=state['options']['send_format']=='png', photo=state['options']['send_format']=='photo')
        except asyncio.CancelledError:
            await self._gq_cancel_status(state)
            raise
        except Exception as error:
            await self._gq_failure(state, error)
        finally:
            state["task"] = None
            self._gquote_tasks.discard(task)
            if not config:
                self._gquote_sessions.pop(token, None)

    async def _gq_failure(self, state, error):
        if state.get("closed"):
            return
        code = str(error) if isinstance(error, _GQuoteError) else type(error).__name__
        if self._gquote_renderer:
            self._gquote_renderer.log("error", code, error=error, state=state)
        else:
            logger.error("gquote op=%s stage=%s exception=%s", state["id"], state["stage"], type(error).__name__)
        text = self._s("gq_failed", op=state["id"], stage=utils.escape_html(state["stage"]), code=utils.escape_html(code))
        await self._inline_answer(state.get("status") or state["source"], text, self._gq_markup(state))


    async def _gq_cancel_status(self, state):
        if state.get("closed"):
            return
        try:
            await self._inline_answer(state["status"], self._s("gq_cancelled"), self._gq_markup(state))
        except Exception:
            logger.debug("gquote cancellation status unavailable op=%s", state["id"])

    @staticmethod
    def _gq_photo_bytes(data, theme):
        from PIL import Image
        with Image.open(io.BytesIO(data)) as source:
            rgba = source.convert('RGBA')
            rgba.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', rgba.size, '#181b1d' if theme == 'dark' else '#e8edf1')
            canvas.paste(rgba, mask=rgba.getchannel('A'))
            out = io.BytesIO()
            canvas.save(out, format='JPEG', quality=95, subsampling=0)
            return out.getvalue()

    async def _gq_run(self, state, preview=False, document=True, photo=False):
        normalized = _GQuoteRenderer.normalize_options(state["options"])
        if normalized != state["options"]:
            state["options"] = normalized
            state["dirty"] = True
        if not state.get("reply"):
            raise _GQuoteError("reply_required")
        if not state["messages"]:
            state["stage"] = "history"
            state["messages"] = await asyncio.wait_for(self._gq_collect(state["reply"], 1), 40)
            state["selected"] = {m.id for m in state["messages"]}
        if not state["selected"]:
            raise _GQuoteError("no_selected_messages")
        if self._gquote_renderer is None:
            self._gquote_renderer = _GQuoteRenderer(self)
        output='png' if document or preview or photo else 'sticker'
        if state.get('output')!=output:
            state['output']=output; state['dirty']=True
        await self._inline_answer(state["status"], self._s("gq_work"), self._gq_markup(state, True))
        reply_id = state.get('reply_anchor') if state.get('fake') else state["reply"].id
        trigger_pack = (not preview and state.get('trigger') and
                        getattr(state['source'], 'is_group', False) and
                        (self._gq_pack_get(state['source'].chat_id) or {}).get('enabled'))
        pack_error = None
        pack_sent = False
        if trigger_pack:
            state['stage'] = 'pack'
            packed = await self._gq_pack_append(state, return_document=True)
            if packed is not None and not isinstance(packed, str):
                state['stage'] = 'send_sticker'
                try:
                    await asyncio.wait_for(self.client.send_file(state['reply'].peer_id, packed,
                                                                  reply_to=reply_id), 120)
                    pack_sent = True
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self._gquote_renderer.log('warning', 'pack_sticker_send_failed', error=error, state=state)
                    pack_error = self._s('gq_pack_send_failed')
            else:
                pack_error = packed
        if not pack_sent and (state.get("dirty") or not state["pages"]):
            state["stage"] = "queue"
            state["pages"] = await self._gquote_renderer.render(state)
            state["dirty"] = False
        if not pack_sent:
            state["stage"] = "send_preview" if preview else "send_photo" if photo else "send_png" if document else "send_sticker"
        uploads=[] if pack_sent else state['pages'] if preview or document or photo else [state['pages']]
        for index, data in enumerate(uploads):
            if preview and index:
                break
            out = io.BytesIO(data if isinstance(data,bytes) else b'')
            out.name = f'gquote_{state["id"]}_{index+1}.png'
            send_kwargs={}
            sticker_preview = preview and state.get('fake')
            if (not preview and not document and not photo) or sticker_preview:
                sticker,size=await utils.run_sync(self._gq_sticker_bytes,data)
                out=io.BytesIO(sticker); out.name=f'gquote_{state["id"]}_{index+1}.webp'
                send_kwargs=dict(mime_type='image/webp',attributes=[
                    types.DocumentAttributeSticker(alt='💬',stickerset=types.InputStickerSetEmpty()),
                    types.DocumentAttributeImageSize(w=size[0],h=size[1])])
            elif photo:
                out = io.BytesIO(await utils.run_sync(self._gq_photo_bytes, data, state['options']['theme']))
                out.name = f'gquote_{state["id"]}_{index+1}.jpg'
            caption = ''
            if preview and state.get("preview"):
                try:
                    edit_kwargs = {'attributes': send_kwargs['attributes']} if sticker_preview else {}
                    await asyncio.wait_for(self.client.edit_message(state["reply"].peer_id, state["preview"].id, caption, file=out, **edit_kwargs), 90)
                    continue
                except Exception as error:
                    self._gquote_renderer.log("warning", "preview_edit_failed", error=error, state=state)
                    out.seek(0)
            sent = await asyncio.wait_for(self.client.send_file(state["reply"].peer_id, out, caption=caption,
                                               force_document=False if send_kwargs or preview or photo else document,
                                               reply_to=reply_id,**send_kwargs), 120)
            if preview:
                state["preview"] = sent
        if not preview and not trigger_pack:
            pack_error = await self._gq_pack_append(state)
        if state.get("config", True):
            await self._inline_answer(state["status"],
                self._gq_text(state) + ('\n\n' + pack_error if pack_error else ''),
                self._gq_markup(state))
        else:
            try:
                if pack_error:
                    await self._answer_temporary(state['status'], pack_error, _IMPORTANT_RESULT_TTL)
                else:
                    await state["status"].delete()
            except Exception as error:
                self._gquote_renderer.log("warning", "status_delete_failed", error=error, state=state)



    async def _gq_callback(self, call, token, action):
        state = self._gq_get(token)
        if not state:
            return await call.answer(self._s("gq_expired"), show_alert=True)
        if action == "cancel":
            task = state.get("task")
            if task and not task.done():
                task.cancel()
            return await call.answer(self._s("gq_cancelled"))
        if action == "close":
            state["closed"] = True
            self._gquote_sessions.pop(token, None)
            task = state.get("task")
            if task and not task.done():
                task.cancel()
            await call.answer()
            await state["status"].delete()
            return
        if state.get("task"):
            return await call.answer(self._s("gq_busy"), show_alert=True)
        await call.answer()
        if action in ('extra','extra_back'):
            state['gq_view']='extra' if action=='extra' else 'main'
            return await self._inline_answer(state['status'],self._gq_text(state),self._gq_markup(state))
        if action == 'trigger_toggle':
            if not state.get('gcfg') or not getattr(state['source'], 'is_group', False):
                return
            chat_id = state['source'].chat_id
            config = self._gq_trigger_get(chat_id)
            config['enabled'] = not config['enabled']
            self._gq_trigger_save(chat_id, config)
            return await self._inline_answer(state['status'], self._gq_text(state), self._gq_markup(state))
        if action in ('pack_create', 'pack_toggle'):
            if not state.get('gcfg') or not getattr(state['source'], 'is_group', False):
                return
            if action == 'pack_create':
                return await self._gq_pack_create(call, state)
            chat_id = state['source'].chat_id
            error = None
            try:
                lock = self._gq_pack_locks.setdefault(str(int(chat_id)), asyncio.Lock())
                async with lock:
                    pack = self._gq_pack_get(chat_id)
                    if pack:
                        enabled = not pack.get('enabled', False)
                        if enabled:
                            result = await self._gq_pack_fetch(pack['short_name'])
                            if len(result.documents) >= 120:
                                error = self._s('gq_pack_full')
                                enabled = False
                        self._gq_pack_save(chat_id, pack['short_name'], enabled)
            except Exception:
                logger.exception('Could not toggle quote sticker pack for chat %s', chat_id)
                error = self._s('gq_pack_failed')
            return await self._inline_answer(state['status'],
                self._gq_text(state) + ('\n\n' + error if error else ''), self._gq_markup(state))
        if action=='background_menu':
            return await self._inline_answer(state['status'],self._gq_background_text(state),self._gq_background_markup(state))
        if action.startswith('bg:'):
            mode=action[3:]
            if mode not in ('transparent','dark','light','custom'): return
            if mode=='custom':
                cached=self.get('gquote_background_cache',{})
                if not isinstance(cached,dict) or not cached.get('url'):
                    return await call.answer(self._s('gq_bg_bad'),show_alert=True)
                state['options']['background_url']=cached['url']
            state['options'].update(background_mode=mode,background=mode!='transparent')
            state['dirty']=True; state['pages']=[]
            self._save_state('gquote_options',state['options'])
            return await self._inline_answer(state['status'],self._gq_background_text(state),self._gq_background_markup(state))
        if action in ("png", "preview"):
            task = asyncio.current_task()
            state["task"] = task
            self._gquote_tasks.add(task)
            try:
                if action == "preview":
                    state.pop("preview", None)
                await self._gq_run(state, preview=action == "preview", document=True)
            except asyncio.CancelledError:
                await self._gq_cancel_status(state)
                raise
            except Exception as error:
                await self._gq_failure(state, error)
            finally:
                self._gquote_tasks.discard(task)
                state["task"] = None
            return
        options = state["options"]
        if action == "reset":
            state["options"] = dict(_GQuoteRenderer.DEFAULTS)
        elif action == "theme":
            options["theme"] = 'light' if options["theme"] == 'dark' else 'dark'
        elif action == 'send_format':
            formats = ('sticker', 'png', 'photo')
            options['send_format'] = formats[(formats.index(options.get('send_format','sticker'))+1) % len(formats)]
        elif action in ("spoilers", "expanded", "gift_colors", "bubble_outline"):
            options[action] = not options[action]
        elif action in ('transparency_down','transparency_up'):
            delta=-5 if action=='transparency_down' else 5
            options['bubble_transparency']=min(100,max(0,options['bubble_transparency']+delta))
        elif action=='link_preview_position':
            options['link_preview_position']='top' if options.get('link_preview_position','bottom')=='bottom' else 'bottom'
        elif action=='transparency_info':
            return
        elif action != "back":
            return
        if action != "back":
            state["dirty"] = True
            state["pages"] = []
            self._save_state("gquote_options", state["options"])
        await self._inline_answer(state["status"], self._gq_text(state), self._gq_markup(state))

    def __init__(self):
        self._gquote_renderer = None
        self._offer_timezone_on_ready = False
        self._gquote_sessions = {}
        self._gquote_tasks = set()
        self._gq_pack_locks = {}
        self._gq_trigger_hits = {}
        self._sessions = {}
        self._me_id = None
        self._activity_cache = {}
        self._cache_locks = {}
        self._member_cache = {}
        self._chat_controls = {}
        self._chat_control_locks = {}
        self._banchat_tasks = {}
        self._panic_settings = {}
        self._panic_joins = {}
        self._bulk_kick_jobs = {}
        self._amn_jobs = {}
        self._amn_tasks = set()
        self._bulk_kick_tasks = set()
        self._join_request_confirms = {}
        self._join_request_jobs = {}
        self._join_request_tasks = {}
        self._delete_mutes = {}
        self._dmute_pulse_tasks = {}
        self._dmute_delete_tasks = set()
        self._guest_bot_blocks = {}
        self._guest_bot_member_blocks = {}
        self._sticker_bans = {}
        self._media_bans = {}
        self._media_known_scopes = None
        self._media_record_ids = {}
        self._media_donor = None
        self._media_visual_cache = {}
        self._media_rule_indexes = {}
        self._media_hash_cache = {}
        self._media_hash_slots = asyncio.Semaphore(2)
        self._media_video_slot = asyncio.Semaphore(1)
        self._media_check_slot = asyncio.Semaphore(1)
        self._media_check_tasks = set()
        self._media_pending_scans = {}
        self._media_scan_task = None
        self._media_recovery_task = None
        self._media_outage_notified = False
        self._media_archive_lock = asyncio.Lock()
        self._media_checkpoint_changes = 0
        self._temporary_message_tasks = set()
        self._gban_lock = asyncio.Lock()

    def _save_state(self, key, value):
        self.set(key, copy.deepcopy(value))

    @staticmethod
    def _args(message):
        args = utils.get_args(message)
        return args if isinstance(args, list) else [args] if isinstance(args, str) else []

    def _migrate_broken_state_namespace(self):
        if self.get("state_storage_migrated_v2", False):
            return
        for key in _PERSISTENT_STATE_KEYS:
            current = self.get(key, None)
            legacy = self.db.get(_BROKEN_STATE_NAMESPACE, key, None)
            if not current and isinstance(legacy, dict) and legacy:
                self._save_state(key, legacy)
        self.set("state_storage_migrated_v2", True)

    async def on_dlmod(self):
        self._offer_timezone_on_ready = (
            not self.get("timezone_setup_offered", False)
            and self.get("quote_timezone_minutes", None) is None
        )

    strings.update({
        "timezone_title": "Timezone",
        "timezone_current": "Current timezone", "timezone_now": "Current time",
        "timezone_done": "Done", "timezone_limit": "Available range: UTC−12 to UTC+14.",
        "gcfg_title": "GodChat settings", "gcfg_quotes": "Quote settings",
        'gcfg_names': 'Names',
        "gcfg_chat": "Chat settings", "gcfg_channel": "Channel settings", "gcfg_chat_only": "Open gcfg in a chat or channel.",
        "gcfg_refresh": "Refresh", "active_usernames": "Active usernames",
        "gcfg_quote_hint": "Run gcfg as a reply to send PNG or preview.",
        "gcfg_quotes_short": "Quotes", "gcfg_chat_short": "Chat",
        "gcfg_channel_short": "Channel", "gcfg_panic_short": "Panic",
        "gcfg_summary_quotes": "Quote format",
        "gcfg_summary_trigger": "Quote trigger", "gcfg_summary_panic": "Auto panic",
        "gcfg_format_sticker": "sticker", "gcfg_format_png": "PNG",
        "gcfg_format_photo": "photo", "gcfg_on": "on", "gcfg_off": "off",
    })
    strings_ru.update({
        "timezone_title": "Часовой пояс",
        "timezone_current": "Текущий часовой пояс", "timezone_now": "Сейчас",
        "timezone_done": "Готово", "timezone_limit": "Доступный диапазон: UTC−12 — UTC+14.",
        "gcfg_title": "Настройки GodChat", "gcfg_quotes": "Настройки цитат",
        'gcfg_names': 'Имена',
        "gcfg_chat": "Настройки чата", "gcfg_channel": "Настройки канала", "gcfg_chat_only": "Открой gcfg в чате или канале.",
        "gcfg_refresh": "Обновить", "active_usernames": "Активные имена",
        "gcfg_quote_hint": "Для отправки PNG или превью вызови gcfg реплаем.",
        "gcfg_quotes_short": "Цитаты", "gcfg_chat_short": "Чат",
        "gcfg_channel_short": "Канал", "gcfg_panic_short": "Паника",
        "gcfg_summary_quotes": "Формат цитат",
        "gcfg_summary_trigger": "Триггер цитат", "gcfg_summary_panic": "Автопаника",
        "gcfg_format_sticker": "стикер", "gcfg_format_png": "PNG",
        "gcfg_format_photo": "фото", "gcfg_on": "вкл", "gcfg_off": "выкл",
    })

    strings.update({
        "panic_settings_title": "Panic settings", "panic_auto": "Auto activation",
        "panic_joins": "Joins", "panic_window": "Window",
        "panic_close": "Close chat", "panic_slow": "Slow mode (1 hour)",
        "panic_slow_button": "Slow mode",
        "panic_requests": "Join requests", "panic_now": "Active",
        "panic_choose_action": "Select at least one panic action: close chat, slow mode, or join requests.",
        "panic_slow_on_detail": "Slow mode: 1 hour",
        "panic_requests_on_detail": "Join requests: enabled",
        "panic_slow_restored_detail": "Previous slow mode restored",
        "panic_requests_restored_detail": "Previous join-request setting restored",
        "panic_number_bad": "Enter a whole number in the allowed range.",
        "panic_number_prompt": "Enter a number", "panic_supergroup_menu": "Open this menu in a supergroup.",
        "panic_seconds": "sec",
        "panic_changes_next": "Changed actions apply on the next activation.",
    })
    strings_ru.update({
        "panic_settings_title": "Настройки паники", "panic_auto": "Автовключение",
        "panic_joins": "Входов", "panic_window": "Окно",
        "panic_close": "Закрыть чат", "panic_slow": "Медленный режим (1 час)",
        "panic_slow_button": "Медленный режим",
        "panic_requests": "Заявки на вступление", "panic_now": "Включена",
        "panic_choose_action": "Выбери хотя бы одно действие паники: закрыть чат, медленный режим или заявки.",
        "panic_slow_on_detail": "Медленный режим: 1 час",
        "panic_requests_on_detail": "Заявки на вступление: включены",
        "panic_slow_restored_detail": "Прежний медленный режим восстановлен",
        "panic_requests_restored_detail": "Прежняя настройка заявок восстановлена",
        "panic_number_bad": "Введи целое число в допустимом диапазоне.",
        "panic_number_prompt": "Введи число", "panic_supergroup_menu": "Открой меню в супергруппе.",
        "panic_seconds": "сек",
        "panic_changes_next": "Изменения действий применятся при следующем включении.",
    })

    def _timezone_minutes(self):
        value = self.get("quote_timezone_minutes", None)
        if type(value) is int and -720 <= value <= 840:
            return value
        offset = datetime.now().astimezone().utcoffset() or timedelta()
        return max(-720, min(840, int(offset.total_seconds() // 60)))

    def _timezone_invalidate_previews(self):
        for state in getattr(self, "_gquote_sessions", {}).values():
            state["dirty"] = True
            state["pages"] = []

    def _quote_timezone(self):
        return timezone(timedelta(minutes=self._timezone_minutes()))

    def _timezone_text(self):
        minutes = self._timezone_minutes()
        hours, remainder = divmod(abs(minutes), 60)
        label = f"UTC{'+' if minutes >= 0 else '−'}{hours:02d}:{remainder:02d}"
        now = datetime.now(self._quote_timezone()).strftime('%d.%m.%Y %H:%M')
        return (
            f"{_EMOJI['time']} <b>GodChat · {self._s('timezone_title')}</b>\n\n"
            f"<blockquote>{self._s('timezone_current')}: <code>{label}</code>\n"
            f"{self._s('timezone_now')}: <code>{now}</code></blockquote>"
        )

    def _timezone_markup(self, token=None):
        rows = [[
            {"text": "−1", "callback": self._timezone_change, "args": (-60, token)},
            {"text": "+1", "callback": self._timezone_change, "args": (60, token)},
        ]]
        if token:
            rows.append([
                {"text": self._s("gq_back"), "callback": self._timezone_change, "args": (0, token), "style": "danger"},
                {"text": self._s("gq_close"), "callback": self._gq_callback, "args": (token, "close"), "style": "danger"},
            ])
        else:
            rows.append([{"text": self._s("gq_close"), "callback": self._timezone_change, "args": (0, None), "style": "danger"}])
        return rows

    async def _timezone_change(self, call, delta, token=None):
        if token is not None:
            state = self._gq_get(token)
            if not state:
                return await call.answer(self._s("gq_expired"), show_alert=True)
            if state.get("task"):
                return await call.answer(self._s("gq_busy"), show_alert=True)
            if delta == 0:
                return await self._gcfg_open(call, token, "main")
        if delta not in (-60, 0, 60):
            return
        value = self._timezone_minutes() + delta
        if not -720 <= value <= 840:
            await call.answer(self._s("timezone_limit"), show_alert=True)
            return
        self.set("quote_timezone_minutes", value)
        self._timezone_invalidate_previews()
        await call.answer()
        if delta == 0:
            await call.delete()
        else:
            await call.edit(self._timezone_text(), reply_markup=self._timezone_markup(token))

    async def client_ready(self, client, db):
        self._me_id = int((await client.get_me()).id)
        self._gq_migrate_expanded_default()
        self._save_state("gquote_options", _GQuoteRenderer.normalize_options(self.get("gquote_options", {})))
        self._migrate_broken_state_namespace()
        self.set("gbackup_pending", None)
        controls = self.get("chat_controls", {})
        self._chat_controls = controls if isinstance(controls, dict) else {}
        panic_settings = self.get("panic_settings", {})
        self._panic_settings = panic_settings if isinstance(panic_settings, dict) else {}
        repaired = False
        for chat_id, config in self._panic_settings.items():
            if isinstance(config, dict) and config.get("auto") and not self._panic_has_actions(self._panic_config(chat_id)):
                config["auto"] = False
                repaired = True
        if repaired:
            self._save_state("panic_settings", self._panic_settings)
        requests = self.get("join_request_jobs", {})
        self._join_request_jobs = requests if isinstance(requests, dict) else {}
        delete_mutes = self.get("delete_mutes", {})
        self._delete_mutes = (
            delete_mutes if isinstance(delete_mutes, dict) else {}
        )
        guest_bot_blocks = self.get("guest_bot_blocks", {})
        self._guest_bot_blocks = (
            guest_bot_blocks if isinstance(guest_bot_blocks, dict) else {}
        )
        guest_bot_member_blocks = self.get("guest_bot_member_blocks", {})
        self._guest_bot_member_blocks = (
            guest_bot_member_blocks
            if isinstance(guest_bot_member_blocks, dict)
            else {}
        )
        sticker_bans = self.get("sticker_bans", {})
        self._sticker_bans = sticker_bans if isinstance(sticker_bans, dict) else {}
        self._prune_sticker_bans()
        self._media_bans = {}
        known_scopes = self.get('media_active_scopes', None)
        self._media_known_scopes = (
            set(known_scopes)
            if isinstance(known_scopes, list) and all(isinstance(scope, str) for scope in known_scopes)
            else None
        )
        self._media_record_ids = {}
        self._media_rule_indexes.clear()
        pending = self.get('media_pending_scans', {})
        self._media_pending_scans = {
            str(int(chat_id)): {'min': int(span['min']), 'max': int(span['max'])}
            for chat_id, span in (pending.items() if isinstance(pending, dict) else [])
            if (isinstance(span, dict) and str(chat_id).lstrip('-').isdigit()
                and isinstance(span.get('min'), int) and isinstance(span.get('max'), int)
                and 0 < span['min'] <= span['max'])
        }
        if self.get('media_donor', None) and not await self._media_donor_load():
            await self._media_notify_outage()
            self._media_schedule_recovery()
        self._prune_delete_mutes()
        for chat_id, state in self._chat_controls.items():
            if state.get("banchat_active") and state.get("banchat_until"):
                self._schedule_banchat(chat_id, state["banchat_until"])
        for chat_id, state in self._join_request_jobs.items():
            retry_at = float(state.get("retry_at", 0) or 0)
            if retry_at:
                self._schedule_join_request_cleanup(chat_id, retry_at)
        if self._offer_timezone_on_ready:
            self._offer_timezone_on_ready = False
            try:
                await self.inline.bot.send_message(
                    self._me_id, self._timezone_text(),
                    reply_markup=self.inline.generate_markup(self._timezone_markup()),
                )
                self.set("timezone_setup_offered", True)
            except Exception:
                logger.warning("Could not open quote timezone setup", exc_info=True)

    async def on_unload(self):
        for task in (self._media_scan_task, self._media_recovery_task):
            if task:
                task.cancel()
        await asyncio.gather(*(task for task in (self._media_scan_task, self._media_recovery_task)
                               if task), return_exceptions=True)
        dmute_tasks = tuple(self._dmute_pulse_tasks.values()) + tuple(self._dmute_delete_tasks)
        for task in dmute_tasks:
            task.cancel()
        if dmute_tasks:
            await asyncio.gather(*dmute_tasks, return_exceptions=True)
        for task in tuple(self._media_check_tasks):
            task.cancel()
        if self._media_check_tasks:
            await asyncio.gather(*self._media_check_tasks, return_exceptions=True)
        for task in tuple(self._amn_tasks):
            task.cancel()
        if self._amn_tasks:
            await asyncio.gather(*self._amn_tasks, return_exceptions=True)
        self._amn_jobs.clear()
        for task in tuple(self._gquote_tasks):
            task.cancel()
        if self._gquote_tasks:
            await asyncio.gather(*tuple(self._gquote_tasks), return_exceptions=True)
        if self._gquote_renderer:
            await self._gquote_renderer.close()
        self._gquote_sessions.clear()
        remaining_tasks = (
            tuple(self._banchat_tasks.values())
            + tuple(self._bulk_kick_tasks)
            + tuple(self._join_request_tasks.values())
            + tuple(self._temporary_message_tasks)
        )
        for task in remaining_tasks:
            task.cancel()
        if remaining_tasks:
            await asyncio.gather(*remaining_tasks, return_exceptions=True)
        self._banchat_tasks.clear()
        self._panic_joins.clear()
        self._bulk_kick_tasks.clear()
        self._bulk_kick_jobs.clear()
        self._join_request_confirms.clear()
        self._join_request_tasks.clear()
        self._delete_mutes.clear()
        self._dmute_delete_tasks.clear()
        self._guest_bot_blocks.clear()
        self._guest_bot_member_blocks.clear()
        self._sticker_bans.clear()
        self._media_bans.clear()
        self._media_known_scopes = None
        self._media_record_ids.clear()
        self._media_visual_cache.clear()
        self._media_donor = None
        self._media_pending_scans.clear()
        self._media_scan_task = None
        self._media_recovery_task = None
        self._media_rule_indexes.clear()
        self._media_hash_cache.clear()
        self._temporary_message_tasks.clear()
        self._sessions.clear()
        self._activity_cache.clear()
        self._cache_locks.clear()
        self._member_cache.clear()
        self._chat_control_locks.clear()

    @staticmethod
    def _active_usernames(user):
        values = [getattr(user, 'username', None)] + [getattr(item, 'username', None)
            for item in (getattr(user, 'usernames', None) or []) if getattr(item, 'active', False)]
        result = []; seen = set()
        for value in values:
            if value and value.casefold() not in seen:
                seen.add(value.casefold()); result.append(value)
        return result

    @staticmethod
    def _username(user):
        username = getattr(user, "username", None)
        if username:
            return username
        return next(
            (
                item.username
                for item in (getattr(user, "usernames", None) or [])
                if getattr(item, "active", False)
                and getattr(item, "username", None)
            ),
            None,
        )

    def _custom_name(self, user):
        if type(user).__name__ in ('Channel','Chat','ChannelForbidden','ChatForbidden','PeerChannel','PeerChat'):
            return None
        getter = getattr(self, 'get', None)
        saved = getter('name_overrides', {}) if callable(getter) else {}
        identity = user if isinstance(user, int) else getattr(user, 'id', getattr(user, 'user_id', None))
        entry = saved.get(str(identity)) if isinstance(saved, dict) else None
        return entry.get('name') if isinstance(entry, dict) else None

    @staticmethod
    def _original_name(user):
        name = " ".join(
            part
            for part in (
                getattr(user, "first_name", None),
                getattr(user, "last_name", None),
            )
            if part
        ).strip()
        username = _GQuoteRenderer.username(user)
        return getattr(user, 'title', None) or name or (f"@{username}" if username else str(int(user.id)))

    def _name(self, user):
        return self._custom_name(user) or self._original_name(user)

    def _label(self, user):
        return (
            f"<b>{utils.escape_html(self._name(user))}</b> "
            f"(<code>{int(user.id)}</code>)"
        )

    @staticmethod
    def _reason(args):
        value = " ".join(args).strip()
        return value[:500] + ("…" if len(value) > 500 else "")

    def _reason_block(self, reason):
        return (
            f"\n{_EMOJI['reason']} <b>{self._s('reason')}:</b> "
            f"{utils.escape_html(reason)}"
            if reason
            else ""
        )

    def _duration_block(self, duration):
        return (
            f"\n{_EMOJI['time']} <b>{self._s('duration')}:</b> "
            f"<code>{utils.escape_html(duration)}</code>"
        )

    def _result(
        self,
        icon,
        title,
        user,
        status,
        duration,
        reason,
        history_deleted=None,
    ):
        history = (
            f"\n<b>{self._s('messages_deleted')}</b>"
            if history_deleted is True
            else (
                f"\n<b>{self._s('messages_delete_failed')}</b>"
                if history_deleted is False
                else ""
            )
        )
        return (
            f"{icon} <b>GodChat · {title}</b>\n\n"
            f"<blockquote>{self._label(user)}\n"
            f"<b>{self._s('status')}:</b> {status}"
            f"{self._duration_block(duration) if duration is not None else ''}"
            f"{self._reason_block(reason)}"
            f"{history}</blockquote>"
        )

    async def _resolve_target(self, message, target_options=None):
        args = self._args(message)
        reply = await self._get_reply_message(message)
        if reply:
            target = await reply.get_sender()
            return target if isinstance(target, types.User) else None, args
        if not args:
            return None, []
        options = {item.lower() for item in (target_options or set())}
        reference_index = next(
            (
                index
                for index, value in enumerate(args)
                if value.lower() not in options
            ),
            None,
        )
        if reference_index is None:
            return None, args
        reference = args.pop(reference_index)
        if reference.startswith("@"):
            reference = reference[1:]
        elif reference.isdigit():
            reference = int(reference)
        try:
            target = await self.client.get_entity(reference)
        except Exception:
            return None, args
        return target if isinstance(target, types.User) else None, args

    @staticmethod
    async def _get_reply_message(message):
        reply = await message.get_reply_message()
        if isinstance(reply, (list, tuple)):
            return next((item for item in reply if item is not None), None)
        return reply

    async def _delete_temporary_message(self, message, seconds):
        try:
            await asyncio.sleep(seconds)
            await message.delete()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Could not delete temporary result", exc_info=True)

    def _schedule_temporary_delete(self, message, seconds):
        if not message or not hasattr(message, "delete"):
            return
        task = asyncio.create_task(
            self._delete_temporary_message(message, seconds)
        )
        self._temporary_message_tasks.add(task)
        task.add_done_callback(self._temporary_message_tasks.discard)

    async def _answer_temporary(self, message, text, seconds):
        result = await self._inline_answer(message, text)
        self._schedule_temporary_delete(result, seconds)
        return result

    async def _create_inline_form(self, message, text, reply_markup=None):
        return await self.inline.form(
            message=message,
            text=text,
            reply_markup=reply_markup,
        )

    async def _inline_fallback(self, message, text):
        if getattr(message, "form", None) is None and hasattr(
            message,
            "respond",
        ):
            try:
                return await message.respond(text)
            except Exception:
                logger.debug("Could not send inline fallback response", exc_info=True)
        return await utils.answer(message, text)

    async def _inline_answer(self, target, text, reply_markup=None):
        if getattr(target, '_gquote_plain_status', False):
            try:
                await target.edit(text=text)
            except Exception:
                logger.debug('Could not update plain quote status', exc_info=True)
            return target
        try:
            if isinstance(target, Message):
                form = await self._create_inline_form(
                    target,
                    text,
                    reply_markup,
                )
                if form:
                    return form
            elif hasattr(target, "edit") and callable(target.edit):
                edited = await target.edit(
                    text=text,
                    reply_markup=reply_markup,
                )
                if edited is not False:
                    return target
            form = target if isinstance(target, dict) else getattr(
                target,
                "form",
                {},
            ) or {}
            if isinstance(form, dict):
                caller = form.get("caller") or form.get("message")
                if isinstance(caller, Message):
                    form = await self._create_inline_form(
                        caller,
                        text,
                        reply_markup,
                    )
                    if form:
                        return form
        except Exception:
            logger.debug("Could not create inline result", exc_info=True)
        return await self._inline_fallback(target, text)

    async def _open_inline_status(self, message, text, reply_markup=None):
        try:
            status = await asyncio.wait_for(
                self.inline.form(
                    message=message, text=text, reply_markup=reply_markup,
                    silent=True, ttl=1800,
                ),
                30,
            )
            if status:
                return status
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Could not open quote form", exc_info=True)
        status = await self._inline_fallback(message, text)
        if status and hasattr(status, 'edit') and hasattr(status, 'delete'):
            return SimpleNamespace(edit=status.edit, delete=status.delete,
                                   _gquote_plain_status=True)
        return status

    async def _delete_command_message(self, message):
        try:
            await message.delete()
        except Exception:
            logger.debug("Could not delete command message", exc_info=True)

    async def _context(
        self,
        message,
        allow_self=False,
        target_options=None,
        error_ttl=None,
    ):
        if (
            getattr(message, "is_private", False)
            or not getattr(message, "is_group", False)
        ):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('groups_only')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return None
        target, args = await self._resolve_target(message, target_options)
        if not target:
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} <b>{self._s('reply_or_user')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return None
        if int(target.id) == self._me_id and not allow_self:
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('self_action')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return None
        try:
            entity = await self.client.get_entity(message.chat_id)
            permissions = await self.client.get_permissions(entity, target)
        except Exception:
            logger.exception("Could not resolve moderation context")
            result = await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('member_rights_failed')}</b>"
                ),
            )
            if error_ttl is not None:
                self._schedule_temporary_delete(result, error_ttl)
            return None
        return entity, target, permissions, args

    def _save_delete_mutes(self):
        self._save_state("delete_mutes", self._delete_mutes)

    def _remove_delete_mute(self, chat_id, user_id):
        chat_id = str(int(chat_id))
        users = self._delete_mutes.get(chat_id, {})
        removed = users.pop(str(int(user_id)), None) is not None
        if not users:
            self._delete_mutes.pop(chat_id, None)
        if removed:
            self._save_delete_mutes()
        return removed

    def _prune_delete_mutes(self):
        now = time.time()
        changed = False
        for chat_id, users in list(self._delete_mutes.items()):
            if not isinstance(users, dict):
                self._delete_mutes.pop(chat_id, None)
                changed = True
                continue
            for user_id, state in list(users.items()):
                expires = float(
                    state.get("expires", 0) or 0
                ) if isinstance(state, dict) else 0
                if expires and expires <= now:
                    users.pop(user_id, None)
                    changed = True
            if not users:
                self._delete_mutes.pop(chat_id, None)
                changed = True
        if changed:
            self._save_delete_mutes()

    def _save_sticker_bans(self):
        self._save_state("sticker_bans", self._sticker_bans)

    def _prune_sticker_bans(self):
        changed = False
        for chat_id, rules in list(self._sticker_bans.items()):
            if not isinstance(chat_id, str) or not isinstance(rules, dict):
                self._sticker_bans.pop(chat_id, None)
                changed = True
                continue
            for key, value in list(rules.items()):
                if (
                    not isinstance(key, str)
                    or not key.startswith(("sticker:", "pack:"))
                    or not isinstance(value, dict)
                    or value.get("kind") not in {"sticker", "pack"}
                ):
                    rules.pop(key, None)
                    changed = True
            if not rules:
                self._sticker_bans.pop(chat_id, None)
                changed = True
        if changed:
            self._save_sticker_bans()

    @staticmethod
    def _sticker_ban_keys(message):
        document = getattr(message, "document", None) or getattr(getattr(message,"media",None),"document",None)
        document_id = getattr(document, "id", None)
        if document_id is None:
            return None, None
        sticker = next(
            (
                attribute
                for attribute in (getattr(document, "attributes", None) or [])
                if isinstance(attribute, types.DocumentAttributeSticker)
            ),
            None,
        )
        if sticker is None:
            return None, None
        pack = getattr(sticker, "stickerset", None)
        pack_id = getattr(pack, "id", None)
        if pack_id is not None:
            pack_key = f"pack:id:{int(pack_id)}"
        else:
            short_name = str(getattr(pack, "short_name", "") or "").lower()
            pack_key = f"pack:name:{short_name}" if short_name else None
        return f"sticker:{int(document_id)}", pack_key

    def _sticker_rules(self, chat_id, global_scope=False):
        rules = self._sticker_bans.get("global" if global_scope else str(int(chat_id)), {})
        return rules if isinstance(rules, dict) else {}

    async def _sticker_ban_permissions(self, message):
        if getattr(message, "is_private", False):
            return True
        try:
            entity = await self.client.get_entity(message.chat_id)
        except Exception:
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('chat_fetch_failed')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return False
        capabilities = await self._operator_capabilities(entity)
        if capabilities.get("delete_messages"):
            return True
        await self._answer_temporary(
            message,
            f"{_EMOJI['error']} <b>{self._s('sticker_ban_rights')}</b>",
            _IMPORTANT_RESULT_TTL,
        )
        return False

    @staticmethod
    def _quote_template_markup(template):
        return (
            template.replace("<qe>", "<blockquote expandable>")
            .replace("</qe>", "</blockquote>")
            .replace("<q>", "<blockquote>")
            .replace("</q>", "</blockquote>")
        )

    async def _delete_mute_context(self, message):
        args = self._args(message)
        if getattr(message, "is_private", False):
            reply = await self._get_reply_message(message)
            target = await reply.get_sender() if reply else None
            if not isinstance(target, types.User) or int(target.id) == self._me_id:
                try:
                    target = await self.client.get_entity(message.chat_id)
                except Exception:
                    target = None
            if (
                not isinstance(target, types.User)
                or int(target.id) == self._me_id
            ):
                await self._answer_temporary(
                    message,
                    f"{_EMOJI['error']} <b>{self._s('dmute_private_self')}</b>",
                    _IMPORTANT_RESULT_TTL,
                )
                return None
            return target, args
        target, args = await self._resolve_target(message)
        if not target:
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('dmute_usage')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return None
        return target, args

    @loader.watcher("in", "only_messages")
    async def delete_mute_watcher(self, message: Message):
        sender_id = getattr(message, "sender_id", None)
        chat_id = getattr(message, "chat_id", None)
        if sender_id is None or chat_id is None:
            return
        users = self._delete_mutes.get(str(int(chat_id)))
        sender_key = str(int(sender_id))
        if not users or sender_key not in users:
            return
        state = users[sender_key]
        expires = float(state.get("expires", 0) or 0) if isinstance(state, dict) else 0
        if expires and expires <= time.time():
            self._remove_delete_mute(chat_id, sender_id)
            return
        self._schedule_dmute_pulse(message)
        self._queue_dmute_delete(message)

    def _queue_dmute_delete(self, message):
        task = asyncio.create_task(self._delete_dmute_message(message))
        self._dmute_delete_tasks.add(task)
        task.add_done_callback(self._dmute_delete_tasks.discard)

    async def _delete_dmute_message(self, message):
        peer = getattr(message, 'input_chat', None)
        try:
            if peer is not None or not getattr(message, 'is_channel', False):
                await self.client.delete_messages(peer, [message.id])
            else:
                await message.delete()
        except Exception:
            logger.debug('Could not delete delete-muted message', exc_info=True)
            try:
                await message.delete()
            except Exception:
                logger.debug('Could not delete delete-muted message via fallback', exc_info=True)

    def _schedule_dmute_pulse(self, message):
        if not getattr(message, "is_channel", False) or getattr(message, "is_group", None) is False:
            return
        key = (int(message.chat_id), int(message.sender_id))
        if key in self._dmute_pulse_tasks and not self._dmute_pulse_tasks[key].done():
            return
        chat = getattr(message, "input_chat", None) or message.chat_id
        sender = getattr(message, "input_sender", None) or message.sender_id
        task = asyncio.create_task(self._dmute_pulse(chat, sender, message))
        self._dmute_pulse_tasks[key] = task
        task.add_done_callback(
            lambda done, key=key: self._dmute_pulse_tasks.pop(key, None)
            if self._dmute_pulse_tasks.get(key) is done else None
        )

    async def _dmute_pulse(self, chat, sender, message=None):
        if message is not None and getattr(message, "input_sender", None) is None:
            try:
                sender = await asyncio.wait_for(message.get_input_sender(), timeout=5) or sender
            except Exception:
                logger.debug("Could not resolve delete-muted sender", exc_info=True)
        try:
            result = await asyncio.wait_for(self.client(
                functions.channels.GetParticipantRequest(channel=chat, participant=sender)
            ), timeout=5)
            participant = result.participant
            if isinstance(participant, (types.ChannelParticipantCreator, types.ChannelParticipantAdmin)):
                return
            previous = getattr(participant, "banned_rights", None)
            if previous and (getattr(previous, "send_messages", False)
                             or getattr(previous, "send_plain", False)):
                return
        except Exception:
            logger.warning("Could not check delete-muted member permissions", exc_info=True)
            return

        until_date = int(time.time()) + 60
        previous_fields = {
            field: bool(getattr(previous, field, False))
            for field in _BANNED_RIGHT_FIELDS
        }
        pulse_fields = dict(previous_fields)
        pulse_fields.update(send_messages=True, send_plain=True)
        try:
            await asyncio.wait_for(self.client(functions.channels.EditBannedRequest(
                channel=chat, participant=sender,
                banned_rights=types.ChatBannedRights(until_date=until_date, **pulse_fields),
            )), timeout=5)
        except Exception:
            logger.warning("Could not apply eight-second delete-mute pulse", exc_info=True)
            return

        try:
            await asyncio.sleep(8)
        finally:
            try:
                current = await asyncio.wait_for(self.client(
                    functions.channels.GetParticipantRequest(channel=chat, participant=sender)
                ), timeout=5)
                rights = getattr(current.participant, "banned_rights", None)
                if (isinstance(current.participant, types.ChannelParticipantBanned)
                        and self._rights_until_date(getattr(rights, "until_date", None)) == until_date
                        and (getattr(rights, "send_messages", False)
                             or getattr(rights, "send_plain", False))):
                    await asyncio.wait_for(self.client(functions.channels.EditBannedRequest(
                        channel=chat, participant=sender,
                        banned_rights=types.ChatBannedRights(
                            until_date=getattr(previous, "until_date", None),
                            **previous_fields,
                        ),
                    )), timeout=5)
            except Exception:
                logger.warning("Could not remove eight-second delete-mute pulse", exc_info=True)

    @loader.watcher("only_messages")
    async def sticker_ban_watcher(self, message: Message):
        chat_id = getattr(message, "chat_id", None)
        if chat_id is None:
            return
        if self._media_donor is not None and int(chat_id)==tl_utils.get_peer_id(self._media_donor):
            return
        sticker_key, pack_key = self._sticker_ban_keys(message)
        if sticker_key is None:
            return
        local = self._sticker_rules(chat_id)
        global_rules = self._sticker_rules(chat_id, global_scope=True)
        local_match = sticker_key in local or pack_key in local
        global_match = sticker_key in global_rules or pack_key in global_rules
        if not local_match and not global_match:
            return
        try:
            if not local_match and not getattr(message, "is_private", False):
                entity = await self.client.get_entity(chat_id)
                capabilities = await self._operator_capabilities(entity)
                if not capabilities.get("delete_messages"):
                    return
            await message.delete()
        except Exception:
            logger.debug("Could not delete forbidden sticker", exc_info=True)

    @staticmethod
    def _media_ban_key(message):
        media = getattr(message, 'media', None)
        for kind in ('photo', 'document'):
            identity = getattr(getattr(media,kind,None),'id',None)
            if isinstance(identity,int) and identity > 0:
                return f'{kind}:{identity}'
        return None

    async def _media_can_delete(self, message):
        if getattr(message,'is_private',False):
            return True
        entity = await self.client.get_entity(message.chat_id)
        return bool((await self._operator_capabilities(entity)).get('delete_messages'))

    @staticmethod
    def _media_compact_visual(visual):
        if not isinstance(visual,dict) or not visual.get('sift'):
            return None
        return {'duration':visual['duration'],'aspect':visual['aspect'],
                'frames':visual.get('frames',[]),'sift':True}

    async def _media_notify_outage(self, restored=False):
        if restored:
            self._media_outage_notified = False
            return
        if self._media_outage_notified:
            return
        text = self._s('media_archive_offline_notice')
        try:
            await self.client.send_message('me', text)
        except Exception:
            logger.warning('Could not notify owner about media archive status', exc_info=True)
            return
        self._media_outage_notified = True

    def _media_schedule_recovery(self):
        if self._media_recovery_task is None or self._media_recovery_task.done():
            self._media_recovery_task = asyncio.create_task(self._media_recovery_loop())

    async def _media_recovery_loop(self):
        delay = 5
        while self._media_donor is None:
            await asyncio.sleep(delay)
            if await self._media_donor_load():
                await self._media_notify_outage(restored=True)
                self._media_schedule_scan()
                return
            await self._media_notify_outage()
            delay = min(delay * 2, 60)

    def _media_defer_scan(self, message):
        chat_id, message_id = getattr(message, 'chat_id', None), getattr(message, 'id', None)
        if chat_id is None or not isinstance(message_id, int) or message_id <= 0:
            return False
        key = str(int(chat_id))
        current = self._media_pending_scans.get(key)
        if not isinstance(current, dict):
            current = {'min': message_id, 'max': message_id}
        else:
            current = {'min': min(int(current['min']), message_id),
                       'max': max(int(current['max']), message_id)}
        self._media_pending_scans[key] = current
        self._save_state('media_pending_scans', self._media_pending_scans)
        if self._media_donor is not None:
            self._media_schedule_scan()
        return True

    def _media_schedule_scan(self):
        if (self._media_donor is not None and self._media_pending_scans
                and (self._media_scan_task is None or self._media_scan_task.done())):
            self._media_scan_task = asyncio.create_task(self._media_scan_pending())

    async def _media_scan_pending(self):
        while self._media_donor is not None and self._media_pending_scans:
            chat_id, range_ids = next(iter(self._media_pending_scans.items()))
            start, end = int(range_ids['min']), int(range_ids['max'])
            try:
                if (int(chat_id) != tl_utils.get_peer_id(self._media_donor)
                        and (self._media_bans.get(chat_id) or self._media_bans.get('global'))):
                    async for item in self.client.iter_messages(
                        int(chat_id), min_id=max(0, start - 1), max_id=end + 1, reverse=True
                    ):
                        if self._media_ban_key(item) is not None:
                            async with self._media_check_slot:
                                if await self._media_check(item) is False:
                                    raise RuntimeError('media_scan_check_failed')
                current = self._media_pending_scans.get(chat_id)
                if current and int(current['max']) <= end:
                    self._media_pending_scans.pop(chat_id, None)
                elif current and int(current['min']) >= start:
                    current['min'] = end + 1
                self._save_state('media_pending_scans', self._media_pending_scans)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning('Could not rescan media in chat %s', chat_id, exc_info=True)
                current = self._media_pending_scans.pop(chat_id, None)
                if current is not None:
                    self._media_pending_scans[chat_id] = current
                await asyncio.sleep(1 if len(self._media_pending_scans) > 1 else 10)

    @staticmethod
    def _media_archive_entry(row):
        scope, key, sha = row['scope'], row['key'], row['sha256']
        if (not isinstance(scope, str) or not scope or
                not isinstance(key, str) or not re.fullmatch(r'(photo|document):[0-9]+', key) or
                not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha)):
            raise ValueError('invalid media archive record')
        visual = row.get('visual')
        if not isinstance(visual, dict) or not row.get('visual_id'):
            visual = None
        entry = {'sha256': sha, 'size': int(row.get('size', 0)),
                 'media_id': int(row['media_id']),
                 'visual_id': int(row['visual_id']) if visual else None,
                 'visual_v1': visual,
                 'visual_family': row.get('visual_family') or sha}
        return scope, key, entry

    async def _media_checkpoint(self, force=False):
        if not force and self._media_checkpoint_changes < 64:
            return
        if self._media_donor is None:
            return
        rows = []
        for scope, rules in self._media_bans.items():
            for key, entry in rules.items():
                rows.append({'scope': scope, 'key': key,
                             'record_id': self._media_record_ids[scope, key],
                             'entry': entry})
        payload = gzip.compress(json.dumps({'version': 1, 'rows': rows},
                                           separators=(',', ':')).encode())
        document = io.BytesIO(payload)
        document.name = 'godchat-media-index.json.gz'
        sent = await self.client.send_file(self._media_donor, document,
                                           caption='GodChat media index', parse_mode=None)
        self.set('media_donor_checkpoint', {
            'donor_id': self._media_donor.channel_id, 'id': sent.id,
            'sha256': hashlib.sha256(payload).hexdigest(),
        })
        self._media_checkpoint_changes = 0

    async def _media_checkpoint_maybe(self):
        self._media_checkpoint_changes += 1
        try:
            await self._media_checkpoint()
        except Exception:
            logger.warning('Could not checkpoint GodChat media archive', exc_info=True)

    async def _media_donor_load(self):
        saved=self.get('media_donor',None)
        try:
            if isinstance(saved,dict) and saved.get('id') and saved.get('access_hash'):
                peer=types.InputPeerChannel(int(saved['id']),int(saved['access_hash']))
                entity=await self.client.get_entity(peer)
                if not isinstance(entity,types.Channel):
                    raise ValueError('media donor is not a channel')
            elif saved:
                raise ValueError('invalid saved media donor')
            else:
                result=await self.client(functions.channels.CreateChannelRequest(
                    title=_MEDIA_DONOR_TITLE,
                    about='Private GodChat media-ban storage. Do not delete.',
                    broadcast=True,
                ))
                entity=result.chats[0]
                peer=types.InputPeerChannel(entity.id,entity.access_hash)
                self.set('media_donor',{'id':entity.id,'access_hash':entity.access_hash})
            if not await utils.dnd(self.client,peer,archive=True):
                logger.warning('Could not mute and archive GodChat media donor')
            bans={}; records={}; since=0
            checkpoint=self.get('media_donor_checkpoint',{})
            if (isinstance(checkpoint,dict) and checkpoint.get('donor_id')==entity.id
                    and isinstance(checkpoint.get('id'),int)):
                try:
                    item=await self.client.get_messages(peer,ids=checkpoint['id'])
                    if item is None: raise ValueError('checkpoint missing')
                    data=await self.client.download_media(item,bytes)
                    if hashlib.sha256(data).hexdigest()!=checkpoint.get('sha256'):
                        raise ValueError('checkpoint checksum mismatch')
                    snapshot=json.loads(gzip.decompress(data))
                    if snapshot.get('version')!=1 or not isinstance(snapshot.get('rows'),list):
                        raise ValueError('checkpoint format invalid')
                    for row in snapshot['rows']:
                        scope,key,entry=self._media_archive_entry(dict(row['entry'],
                            scope=row['scope'],key=row['key'],visual=row['entry'].get('visual_v1')))
                        records[scope,key]=int(row['record_id'])
                        bans.setdefault(scope,{})[key]=entry
                    since=checkpoint['id']
                except Exception:
                    logger.warning('GodChat media checkpoint invalid; replaying archive',exc_info=True)
                    bans={}; records={}; since=0
            if since:
                changes=[item async for item in self.client.iter_messages(peer,min_id=since)]
                changes.reverse()
                for item in changes:
                    content=getattr(item,'raw_text',None) or ''
                    if content.startswith(_MEDIA_DELETE_PREFIX):
                        try:
                            scope,key=json.loads(content[len(_MEDIA_DELETE_PREFIX):])
                            bans.get(scope,{}).pop(key,None)
                            records.pop((scope,key),None)
                            if not bans.get(scope): bans.pop(scope,None)
                        except (TypeError,ValueError,KeyError):
                            logger.warning('Ignoring invalid GodChat media deletion %s',item.id)
                    elif content.startswith(_MEDIA_RECORD_PREFIX):
                        try:
                            scope,key,entry=self._media_archive_entry(json.loads(content[len(_MEDIA_RECORD_PREFIX):]))
                            bans.setdefault(scope,{})[key]=entry
                            records[scope,key]=item.id
                        except (TypeError,ValueError,KeyError):
                            logger.warning('Ignoring invalid GodChat media record %s',item.id)
            else:
                seen=set()
                async for item in self.client.iter_messages(peer):
                    content=getattr(item,'raw_text',None) or ''
                    if content.startswith(_MEDIA_DELETE_PREFIX):
                        try:
                            scope,key=json.loads(content[len(_MEDIA_DELETE_PREFIX):])
                            seen.add((scope,key))
                        except (TypeError,ValueError,KeyError):
                            logger.warning('Ignoring invalid GodChat media deletion %s',item.id)
                    elif content.startswith(_MEDIA_RECORD_PREFIX):
                        try:
                            scope,key,entry=self._media_archive_entry(json.loads(content[len(_MEDIA_RECORD_PREFIX):]))
                            if (scope,key) in seen: continue
                            seen.add((scope,key))
                            bans.setdefault(scope,{})[key]=entry
                            records[scope,key]=item.id
                        except (TypeError,ValueError,KeyError):
                            logger.warning('Ignoring invalid GodChat media record %s',item.id)
            self._media_bans=bans
            self._media_known_scopes = set(bans)
            self.set('media_active_scopes', sorted(self._media_known_scopes))
            self._media_record_ids=records
            self._media_rule_indexes.clear()
            self._media_visual_cache.clear()
            self._media_donor=peer
            self._media_checkpoint_changes = len(changes) if since else 0
            if not since:
                try:
                    await self._media_checkpoint(force=True)
                except Exception:
                    logger.warning('Could not create GodChat media checkpoint',exc_info=True)
            self._media_schedule_scan()
            if self.get('media_bans',{}):
                self.set('media_bans',{})
            return True
        except Exception:
            self._media_donor=None
            logger.exception('Could not open GodChat media donor; media bans unavailable')
            return False

    async def _media_load_sift(self,entry):
        visual_id=entry.get('visual_id')
        if not visual_id or self._media_donor is None: return None
        if visual_id in self._media_visual_cache:
            return self._media_visual_cache[visual_id]
        try:
            message=await self.client.get_messages(self._media_donor,ids=visual_id)
            if message is None: return None
            data=await self.client.download_media(message,bytes)
            payload=json.loads(gzip.decompress(data))
            if payload.get('sha256')!=entry.get('sha256'): return None
            visual=payload.get('visual')
            if not isinstance(visual,dict) or not visual.get('sift'): return None
            if len(self._media_visual_cache)>=_MEDIA_SIFT_CANDIDATE_LIMIT:
                self._media_visual_cache.pop(next(iter(self._media_visual_cache)))
            self._media_visual_cache[visual_id]=visual['sift']
            return visual['sift']
        except Exception:
            logger.warning('Could not load GodChat visual reference %s',visual_id,exc_info=True)
            return None

    async def _media_donor_add(self,scope,key,fingerprint,message):
        async with self._media_archive_lock:
            if self._media_donor is None:
                raise RuntimeError('media donor unavailable')
            if key in self._media_bans.get(scope,{}):
                return False
            if self._media_known_scopes is not None:
                self._media_known_scopes.add(scope)
                self.set('media_active_scopes', sorted(self._media_known_scopes))
            sha=fingerprint['sha256']
            existing=next((value for rules in self._media_bans.values() for value in rules.values()
                           if isinstance(value,dict) and value.get('sha256')==sha and value.get('media_id')),None)
            media_id=existing['media_id'] if existing else None
            visual=self._media_compact_visual(fingerprint.get('visual_v1'))
            visual_id=existing.get('visual_id') if existing and visual is not None else None
            if media_id is None:
                sent=await self.client.send_file(self._media_donor,message.media,
                                                 caption='GodChat media ban',parse_mode=None)
                media_id=sent.id
            if visual is not None and visual_id is None:
                payload=gzip.compress(json.dumps({'sha256':sha,'visual':fingerprint['visual_v1']},
                                                 separators=(',',':')).encode())
                document=io.BytesIO(payload)
                document.name=f'godchat-{sha[:16]}.json.gz'
                sent=await self.client.send_file(self._media_donor,document,
                                                 caption='GodChat visual reference',parse_mode=None)
                visual_id=sent.id
            row={'scope':scope,'key':key,'sha256':sha,'size':fingerprint.get('size',0),
                 'media_id':media_id,'visual_id':visual_id,'visual':visual,
                 'visual_family':fingerprint.get('visual_family') or sha}
            record=await self.client.send_message(self._media_donor,_MEDIA_RECORD_PREFIX+
                          json.dumps(row,separators=(',',':')),parse_mode=None)
            entry={name:value for name,value in row.items()
                   if name in {'sha256','size','media_id','visual_id','visual_family'}}
            entry['visual_v1']=visual
            self._media_bans.setdefault(scope,{})[key]=entry
            self._media_record_ids[scope,key]=record.id
            self._media_rule_indexes.pop(scope,None)
            await self._media_checkpoint_maybe()
            return True

    async def _media_donor_remove(self,scope,key):
        async with self._media_archive_lock:
            record_id=self._media_record_ids.get((scope,key))
            if record_id is None: return False
            await self.client.send_message(self._media_donor,
                _MEDIA_DELETE_PREFIX+json.dumps([scope,key],separators=(',',':')),parse_mode=None)
            entry=self._media_bans[scope].pop(key)
            self._media_record_ids.pop((scope,key),None)
            if not self._media_bans[scope]: self._media_bans.pop(scope,None)
            if self._media_known_scopes is not None and scope not in self._media_bans:
                self._media_known_scopes.discard(scope)
                self.set('media_active_scopes', sorted(self._media_known_scopes))
            self._media_rule_indexes.pop(scope,None)
            try:
                await self.client.delete_messages(self._media_donor,[record_id])
            except Exception:
                logger.warning('Could not clean old GodChat media record',exc_info=True)
            still_used={value.get('media_id') for rules in self._media_bans.values()
                        for value in rules.values() if isinstance(value,dict)}
            cleanup=[]
            if entry.get('media_id') not in still_used: cleanup.append(entry['media_id'])
            still_used_visual={value.get('visual_id') for rules in self._media_bans.values()
                               for value in rules.values() if isinstance(value,dict)}
            if entry.get('visual_id') and entry['visual_id'] not in still_used_visual:
                cleanup.append(entry['visual_id'])
                self._media_visual_cache.pop(entry['visual_id'],None)
            if cleanup:
                try: await self.client.delete_messages(self._media_donor,cleanup)
                except Exception: logger.warning('Could not clean unused donor media',exc_info=True)
            await self._media_checkpoint_maybe()
            return True

    async def _media_donor_clear(self,scope):
        count=0
        for key in tuple(self._media_bans.get(scope,{})):
            if await self._media_donor_remove(scope,key): count+=1
        return count

    async def _media_fingerprint(self, message, visual=False, exact_hashes=None, visual_durations=None):
        key = self._media_ban_key(message)
        if key is None:
            raise ValueError('unsupported_media')
        window_durations = {
            f'{float(duration):.2f}': float(duration)
            for duration in (visual_durations or [])
        }
        async with self._media_hash_slots:
            if key in self._media_hash_cache and (not visual or 'visual_v1' in self._media_hash_cache[key]
                    and all(duration in self._media_hash_cache[key].get('visual_windows_v1', {})
                            for duration in window_durations)
                    or self._media_hash_cache[key]['sha256'] in (exact_hashes or set())):
                return self._media_hash_cache[key]
            limit = 128 * 1024 * 1024
            document = getattr(getattr(message,'media',None),'document',None)
            if (getattr(document,'size',0) or 0) > limit:
                raise ValueError('media_hash_limit_128MiB')
            with tempfile.TemporaryDirectory(prefix='godchat-media-') as directory:
                file = open(Path(directory)/'media.bin','w+b')
                class Sink:
                    def write(self, data):
                        if file.tell()+len(data)>limit:
                            raise ValueError('media_hash_limit_128MiB')
                        return file.write(data)
                try:
                    await asyncio.wait_for(self.client.download_media(message, Sink()),120)
                    size=file.tell()
                    if not size:
                        raise ValueError('media_hash_empty_download')
                    def digest():
                        file.seek(0); hashed=hashlib.sha256()
                        while chunk := file.read(1024*1024): hashed.update(chunk)
                        return {'sha256':hashed.hexdigest(),'size':size}
                    fingerprint=await utils.run_sync(digest)
                finally:
                    file.close()
                if visual and fingerprint['sha256'] not in (exact_hashes or set()):
                    fingerprint['visual_v1'] = await self._media_video_fingerprint(Path(directory)/'media.bin',message)
                    if window_durations:
                        fingerprint['visual_windows_v1'] = {
                            duration: await self._media_video_fingerprint(
                                Path(directory)/'media.bin', message, sample_duration=value
                            )
                            for duration, value in window_durations.items()
                        }
            if len(self._media_hash_cache)>=8:
                self._media_hash_cache.pop(next(iter(self._media_hash_cache)))
            self._media_hash_cache[key]=fingerprint
            return fingerprint

    @staticmethod
    def _media_video_info(message):
        doc=getattr(getattr(message,'media',None),'document',None)
        video=next((a for a in getattr(doc,'attributes',[]) or [] if type(a).__name__=='DocumentAttributeVideo'),None)
        if video is None: return None
        duration=getattr(video,'duration',0); w=getattr(video,'w',0); h=getattr(video,'h',0)
        if not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 0.2<=duration<=60: return None
        if not isinstance(w,int) or not isinstance(h,int) or w<=0 or h<=0 or w*h>3840*2160: return None
        return {'duration':float(duration),'aspect':w/h}

    @staticmethod
    def _media_video_compatible(left,right):
        return bool(left and isinstance(right,dict) and
            abs(left['duration']-right.get('duration',-100))<=max(.15,left['duration']*.03) and
            abs(left['aspect']-right.get('aspect',-100))<=left['aspect']*.02)

    @staticmethod
    def _media_duration_compatible(left,right):
        return bool(left and isinstance(right,dict) and
            abs(left['duration']-right.get('duration',-100))<=max(.15,left['duration']*.03))

    @staticmethod
    def _media_duration_prefix_compatible(left,right):
        if not left or not isinstance(right,dict): return False
        duration=right.get('duration',0)
        return isinstance(duration,(int,float)) and .2<=duration<left['duration']<=3*duration+.15

    @staticmethod
    def _media_sift_worker():
        return r'''
import base64, json, sys, zlib
import cv2 as cv
import numpy as np
cv.setNumThreads(1)
cv.ocl.setUseOpenCL(False)
def pack(a):
    return base64.b64encode(zlib.compress(a.tobytes(), 3)).decode('ascii')
def unpack(s, shape):
    size = int(np.prod(shape))
    d = zlib.decompressobj()
    raw = d.decompress(base64.b64decode(s), size + 1)
    if len(raw) != size or not d.eof: raise ValueError('invalid array')
    return np.frombuffer(raw, np.uint8).reshape(shape)
def extract(data):
    rgb = np.frombuffer(base64.b64decode(data), np.uint8).reshape(7,256,256,3)
    frames = [cv.cvtColor(f, cv.COLOR_RGB2GRAY) for f in rgb]
    sift = cv.SIFT_create(nfeatures=400)
    keys, desc = sift.detectAndCompute(frames[0], None)
    if desc is None: keys,desc=[],np.empty((0,128),np.uint8)
    else: keys, desc = keys[:400], desc[:400]
    return dict(v=1, frames=[pack(f) for f in frames],
                colors=[pack(cv.resize(f,(64,64),interpolation=cv.INTER_AREA)) for f in rgb],
                points=[list(k.pt) for k in keys], descriptors=pack(desc.astype(np.uint8)))
def compare(a,b):
    if not a or not b or a.get('v') != 1 or b.get('v') != 1: return False
    if len(a['frames']) != 7 or len(b['frames']) != 7: return False
    if len(a.get('colors',[])) != 7 or len(b.get('colors',[])) != 7: return False
    # No geometric search is needed for ordinary re-encoding, including low-detail clips.
    reversed_b=dict(b,frames=b['frames'][::-1],colors=b['colors'][::-1])
    if verify(a,b,np.eye(3)) or verify(a,reversed_b,np.eye(3),allow_motion_gaps=True): return True
    pa,pb = np.float32(a['points']),np.float32(b['points'])
    if not 16 <= len(pa) <= 400 or not 16 <= len(pb) <= 400: return False
    da = unpack(a['descriptors'],(len(pa),128)).astype(np.float32)
    db = unpack(b['descriptors'],(len(pb),128)).astype(np.float32)
    pairs = cv.BFMatcher().knnMatch(da,db,k=2)
    good = [p[0] for p in pairs if len(p)==2 and p[0].distance < .70*p[1].distance]
    if len(good)<16: return False
    # A repeated texture must not supply many votes for the same target point.
    good = sorted(good,key=lambda m:m.distance)
    used=set(); unique=[]
    for m in good:
        if m.trainIdx not in used: unique.append(m); used.add(m.trainIdx)
    if len(unique)<16: return False
    p = np.float32([pa[m.queryIdx] for m in unique])
    q = np.float32([pb[m.trainIdx] for m in unique])
    h, mask = cv.findHomography(p,q,cv.RANSAC,2.5,maxIters=1000,confidence=.995)
    if h is None or mask is None or not np.isfinite(h).all(): return False
    keep=mask.ravel().astype(bool)
    if keep.sum()<16 or keep.mean()<.65: return False
    for points in (p[keep],q[keep]):
        if cv.contourArea(cv.convexHull(points)) < 256*256*.18: return False
    return verify(a,b,h) or verify(a,reversed_b,h,allow_motion_gaps=True)
def verify(a,b,h,allow_motion_gaps=False):
    corners=np.float32([[0,0],[255,0],[255,255],[0,255]]).reshape(-1,1,2)
    mapped=cv.perspectiveTransform(corners,h)
    if not cv.isContourConvex(mapped) or cv.contourArea(mapped,oriented=True)<=0: return False
    area=cv.contourArea(mapped)
    if not .4*65536 <= area <= 2.5*65536: return False
    valid=cv.warpPerspective(np.full((256,256),255,np.uint8),h,(256,256))>254
    valid=cv.erode(valid.astype(np.uint8),np.ones((5,5),np.uint8)).astype(bool)
    if valid.mean()<.60 or valid.sum()/area<.60: return False
    aligned=[]; targets=[]; informative=0
    for fa,fb in zip(a['frames'],b['frames']):
        x=cv.warpPerspective(unpack(fa,(256,256)),h,(256,256))
        y=unpack(fb,(256,256))
        x=cv.GaussianBlur(x,(3,3),0).astype(np.float32)
        y=cv.GaussianBlur(y,(3,3),0).astype(np.float32)
        x_mean,x_std=x[valid].mean(),x[valid].std()
        y_mean,y_std=y[valid].mean(),y[valid].std()
        if x_std<4 or y_std<4: continue
        y=(y-y_mean)*(x_std/y_std)+x_mean
        delta=np.abs(x-y)[valid]
        if delta.mean()>8 or (delta>22).mean()>.08: return False
        informative+=1
        aligned.append(x); targets.append(y)
    if informative<3: return False
    # Same background is insufficient: changed regions must agree as well.
    bad_motion=0; checked_motion=0
    for ax,bx,ay,by in zip(aligned,aligned[1:],targets,targets[1:]):
        dx,dy=bx-ax,by-ay
        moving=valid & ((np.abs(dx)>12)|(np.abs(dy)>12))
        if moving.sum()>=32:
            checked_motion+=1
            error=np.abs(dx-dy)[moving]
            if error.mean()>10 or (error>25).mean()>.10:
                if not allow_motion_gaps: return False
                bad_motion+=1
    if allow_motion_gaps and (bad_motion>2 or bad_motion and checked_motion-bad_motion<3): return False
    return True
try:
    request=json.load(sys.stdin)
    if request['op']=='extract': result=extract(request['data'])
    else:
        result=[]
        for item in request['refs'][:16]:
            if compare(request['sample'],item['sift']): result.append(item['sha256'])
    print(json.dumps(result,separators=(',',':')))
except Exception:
    sys.exit(2)
'''

    async def _media_sift_run(self, request):
        import sys
        process=None
        try:
            process=await asyncio.create_subprocess_exec(sys.executable,'-c',self._media_sift_worker(),
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
            result,_=await asyncio.wait_for(process.communicate(json.dumps(request).encode()),15)
            if process.returncode: raise ValueError('sift_worker_failed_or_opencv_missing')
            return json.loads(result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning('media SIFT check unavailable',exc_info=True)
            return None
        finally:
            if process is not None and process.returncode is None:
                process.kill(); await process.communicate()

    @staticmethod
    def _media_small_frames(data):
        from PIL import Image
        if len(data)!=7*256*256*3: raise ValueError('video_frame_count')
        result=[]
        for i in range(7):
            with Image.frombytes('RGB',(256,256),data[i*196608:(i+1)*196608]) as frame:
                with frame.resize((32,32),Image.Resampling.BOX) as small:
                    result.append(small.tobytes())
        return b''.join(result)

    @staticmethod
    def _media_frame_hashes(data):
        from PIL import Image
        if len(data)!=7*32*32*3: raise ValueError('video_frame_count')
        cosine=[[math.cos(math.pi*(2*x+1)*u/64) for x in range(32)] for u in range(8)]
        result=[]
        for index in range(7):
            raw=data[index*3072:(index+1)*3072]
            with Image.frombytes('RGB',(32,32),raw) as image:
                with image.convert('L') as gray: pixels=list(gray.tobytes())
            mean=sum(pixels)/1024
            if sum((p-mean)**2 for p in pixels)/1024<16: return None
            horizontal=[[sum(pixels[y*32+x]*cosine[u][x] for x in range(32)) for u in range(8)] for y in range(32)]
            values=[sum(horizontal[y][u]*cosine[v][y] for y in range(32)) for v in range(8) for u in range(8)][1:]
            median=sorted(values)[31]
            bits=sum((value>median)<<i for i,value in enumerate(values))
            result.append({'hash':format(bits,'016x'),'rgb':[sum(raw[c::3])/1024 for c in range(3)]})
        return result

    @staticmethod
    def _media_ffmpeg_executable():
        import shutil
        executable=shutil.which('ffmpeg')
        if executable: return executable
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None

    async def _media_video_fingerprint(self, path, message, sample_duration=None):
        info=self._media_video_info(message)
        if info is None: return None
        if sample_duration is not None:
            info=dict(info,duration=sample_duration)
        sample_duration=max(.2,round(info['duration']*10)/10)
        executable=self._media_ffmpeg_executable()
        if not executable:
            logger.warning('media video fingerprint unavailable: ffmpeg_missing')
            return None
        async with self._media_video_slot:
            process=None
            try:
                process=await asyncio.create_subprocess_exec(executable,'-v','error','-nostdin','-threads','1',
                    '-filter_threads','1','-max_alloc','67108864','-protocol_whitelist','file,pipe',
                    '-format_whitelist','mov,matroska,webm,gif,avi','-i',str(path),'-an','-sn','-dn','-vf',f"fps={7/sample_duration},scale=256:256:flags=area",
                    '-frames:v','7','-pix_fmt','rgb24','-f','rawvideo','pipe:1',
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
                data,_=await asyncio.wait_for(process.communicate(),30)
                if process.returncode: raise ValueError('video_decode_failed')
                small=await utils.run_sync(self._media_small_frames,data)
                frames=await utils.run_sync(self._media_frame_hashes,small)
                import base64
                sift=await self._media_sift_run({'op':'extract','data':base64.b64encode(data).decode('ascii')})
                return dict(info,frames=frames,sift=sift) if frames or sift else None
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning('media video fingerprint failed',exc_info=True)
                return None
            finally:
                if process is not None and process.returncode is None:
                    process.kill(); await process.communicate()

    @classmethod
    def _media_visual_match(cls,left,right):
        if not cls._media_video_compatible(left,right): return False
        a,b=left.get('frames',[]),right.get('frames',[])
        if len(a)!=7 or len(b)!=7: return False
        try:
            distances=[(int(x['hash'],16)^int(y['hash'],16)).bit_count() for x,y in zip(a,b)]
            return max(distances)<=4 and sum(distances)<=14
        except (ValueError,KeyError,TypeError): return False

    @classmethod
    def _media_visual_distance(cls,left,right):
        if not cls._media_video_compatible(left,right): return (65,455)
        a,b=left.get('frames',[]),right.get('frames',[])
        if len(a)!=7 or len(b)!=7: return (65,455)
        try:
            return min(
                (max(distances),sum(distances))
                for order in (b,b[::-1])
                for distances in [[
                    (int(x['hash'],16)^int(y['hash'],16)).bit_count()
                    for x,y in zip(a,order)
                ]]
            )
        except (ValueError,KeyError,TypeError): return (65,455)

    def _media_rule_index(self,scope):
        rules=self._media_bans.get(scope,{})
        cache=getattr(self,'_media_rule_indexes',None)
        if cache is None:
            cache=self._media_rule_indexes={}
        indexed=cache.get(scope)
        if indexed and indexed['rules'] is rules and indexed['length']==len(rules):
            return indexed
        hashes={}; visual=[]
        for value in rules.values():
            if not isinstance(value,dict): continue
            sha=value.get('sha256')
            if sha: hashes.setdefault(sha,value)
            fingerprint=value.get('visual_v1')
            if isinstance(fingerprint,dict) and fingerprint.get('sift'):
                visual.append(value)
        indexed={'rules':rules,'length':len(rules),'hashes':hashes,'visual':visual}
        cache[scope]=indexed
        return indexed

    @staticmethod
    def _media_signature(message):
        document = getattr(getattr(message,'media',None),'document',None)
        video = next((a for a in getattr(document,'attributes',[]) or []
            if type(a).__name__ == 'DocumentAttributeVideo'),None)
        if video is None:
            return None
        size = getattr(document,'size',0)
        width,height = getattr(video,'w',0),getattr(video,'h',0)
        duration = getattr(video,'duration',0)
        codec = getattr(video,'video_codec',None)
        thumb = next((getattr(t,'bytes',None) for t in getattr(document,'thumbs',[]) or []
            if type(t).__name__ == 'PhotoStrippedSize' and isinstance(getattr(t,'bytes',None),bytes)),None)
        if not all(isinstance(v,int) and v>0 for v in (size,width,height)) or not codec or not thumb:
            return None
        if not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<=0:
            return None
        data = [1,size,width,height,float(duration),str(codec).lower(),
                getattr(document,'mime_type',None),bool(getattr(video,'nosound',False)),
                bool(getattr(video,'round_message',False)),hashlib.sha256(thumb).hexdigest()]
        return hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()

    @loader.watcher('only_messages')
    async def media_ban_watcher(self, message: Message):
        chat_id=getattr(message,'chat_id',None)
        key = self._media_ban_key(message)
        if chat_id is None or key is None: return
        if self._media_donor is None:
            if not self.get('media_donor', None):
                return
            if (self._media_known_scopes is not None
                    and 'global' not in self._media_known_scopes
                    and str(int(chat_id)) not in self._media_known_scopes):
                return
            self._media_defer_scan(message)
            self._media_schedule_recovery()
            return
        if int(chat_id)==tl_utils.get_peer_id(self._media_donor):
            return
        local = self._media_bans.get(str(int(chat_id)), {})
        global_rules = self._media_bans.get('global', {})
        if not local and not global_rules: return
        if key in local or key in global_rules:
            await self._media_check(message)
            return
        if len(self._media_check_tasks)>=20:
            if not self._media_defer_scan(message):
                async with self._media_check_slot:
                    await self._media_check(message)
            return
        async def run():
            async with self._media_check_slot:
                await self._media_check(message)
        task=asyncio.create_task(run())
        self._media_check_tasks.add(task)
        task.add_done_callback(self._media_check_tasks.discard)

    async def _media_check(self, message):
        key = self._media_ban_key(message)
        chat_id = getattr(message,'chat_id',None)
        if key is None or chat_id is None:
            return
        local_scope = str(int(chat_id))
        indexes=(self._media_rule_index(local_scope),self._media_rule_index('global'))
        if not any(index['rules'] for index in indexes):
            return
        try:
            if not await self._media_can_delete(message):
                return
            fingerprint = None
            verified = set()
            def matched_scopes():
                result=[]
                for scope in (local_scope,'global'):
                    index=self._media_rule_index(scope)
                    hashes=index['hashes']
                    if (key in index['rules'] or
                            fingerprint is not None and fingerprint['sha256'] in hashes or
                            any(sha in hashes for sha in verified)):
                        result.append(scope)
                return result
            matched = bool(matched_scopes())
            if not matched:
                hashes = set().union(*(index['hashes'] for index in indexes))
                if not hashes:
                    return
                info=self._media_video_info(message)
                candidates=[value for index in indexes for value in index['visual'] if
                    (self._media_duration_compatible(info,value.get('visual_v1')) or
                     self._media_duration_prefix_compatible(info,value.get('visual_v1')))]
                visual=bool(candidates)
                windows=[]
                for value in candidates:
                    if not self._media_duration_compatible(info,value['visual_v1']):
                        duration=value['visual_v1']['duration']
                        if f'{duration:.2f}' not in {f'{item:.2f}' for item in windows}:
                            windows.append(duration)
                        if len(windows)>=3: break
                fingerprint = await self._media_fingerprint(
                    message,visual=visual,exact_hashes=hashes,visual_durations=windows
                )
                matched = bool(matched_scopes())
                samples=[fingerprint.get('visual_v1')]
                samples.extend((fingerprint.get('visual_windows_v1') or {}).values())
                for sample in samples:
                    if matched or not isinstance(sample,dict) or not sample.get('sift'): continue
                    compatible=[value for value in candidates
                                if self._media_video_compatible(sample,value['visual_v1'])]
                    compatible.sort(key=lambda v:self._media_visual_distance(sample,v['visual_v1']))
                    refs=[]; seen=set(); families=set()
                    for value in compatible:
                        family=value.get('visual_family') or value.get('sha256')
                        if family in families or not value.get('sha256'): continue
                        sift=await self._media_load_sift(value)
                        if not sift: continue
                        refs.append({'sha256':value['sha256'],'sift':sift})
                        seen.add(value['sha256']); families.add(family)
                        if len(refs)>=_MEDIA_FAMILY_SEED_LIMIT: break
                    for value in compatible:
                        if value.get('sha256') and value['sha256'] not in seen:
                            sift=await self._media_load_sift(value)
                            if sift:
                                refs.append({'sha256':value['sha256'],'sift':sift})
                                seen.add(value['sha256'])
                        if len(refs)>=_MEDIA_SIFT_CANDIDATE_LIMIT: break
                    if refs:
                        async with self._media_video_slot:
                            verified.update(await self._media_sift_run(
                                {'op':'match','sample':sample['sift'],'refs':refs}
                            ) or [])
                        matched=bool(matched_scopes())
            scopes = matched_scopes()
            if matched and scopes and await self._media_can_delete(message):
                await message.delete()
                if fingerprint is not None and self._media_donor is not None:
                    scopes = matched_scopes()
                    for scope in scopes:
                        if key in self._media_bans.get(scope,{}): continue
                        index=self._media_rule_index(scope)
                        source=next((index['hashes'][sha] for sha in
                                     (fingerprint['sha256'],*verified)
                                     if sha in index['hashes']),None)
                        entry={name:value for name,value in fingerprint.items()
                               if name != 'visual_windows_v1'}
                        if isinstance(source,dict):
                            entry['visual_family']=source.get('visual_family') or source.get('sha256')
                        try:
                            await self._media_donor_add(scope,key,entry,message)
                        except Exception:
                            logger.warning('Could not save verified media to donor',exc_info=True)
        except ValueError:
            logger.warning('Media is outside GodChat fingerprint limits chat=%s key=%s',chat_id,key,exc_info=True)
        except Exception:
            logger.warning('Media ban check failed chat=%s key=%s',chat_id,key,exc_info=True)
            return False
        return True

    strings.update({
        'media_archive_offline_notice':'GodChat: the banned-media archive is unavailable. Checks are paused; the module will reconnect and scan messages received meanwhile.',
        'media_ban_args':'Only -g is supported for media; -p is supported for a replied sticker pack.',
        'media_unban_args':'Use -all to clear all bans, -g for global bans, or -p for a replied sticker pack. -all and -p cannot be combined.',
        'media_ban_reply':'Reply to a sticker, photo, video, animation, audio, voice message or file.',
        'media_ban_rights':'Not enough rights to delete media in this chat.',
        'media_ban_failed':'Could not update media bans. See logs.',
        'media_donor_unavailable':'Media archive is unavailable. See logs.',
        'media_ban_title':'Media and sticker bans', 'media_global_title':'Global media and sticker bans',
        'media_banned':'Media banned.', 'media_already_banned':'Media banned.',
        'media_unbanned':'Media is allowed again.', 'media_not_banned':'This media is not banned here.',
        'media_cleared':'Media and sticker bans removed: {count}.',
        'media_other_scope':'Bans in the other scope remain in effect.',
    })
    strings_ru.update({
        'media_archive_offline_notice':'GodChat: архив запрещённых медиа недоступен. Проверки временно не работают; модуль повторит подключение и проверит сообщения, пришедшие за это время.',
        'media_ban_args':'Для медиа допустим только -g; для пака стикера доступен -p.',
        'media_unban_args':'-all снимает все запреты, -g выбирает глобальные, -p — пак стикера из реплая. -all и -p нельзя использовать вместе.',
        'media_ban_reply':'Ответь на стикер, фото, видео, анимацию, аудио, голосовое сообщение или файл.',
        'media_ban_rights':'Недостаточно прав для удаления медиа в этом чате.',
        'media_ban_failed':'Не удалось изменить запреты медиа. Подробности в логах.',
        'media_donor_unavailable':'Архив медиа недоступен. Подробности в логах.',
        'media_ban_title':'Запреты медиа и стикеров', 'media_global_title':'Глобальные запреты медиа и стикеров',
        'media_banned':'Медиа забанено.', 'media_already_banned':'Медиа забанено.',
        'media_unbanned':'Медиа снова разрешено.', 'media_not_banned':'Это медиа здесь не запрещено.',
        'media_cleared':'Снято запретов медиа и стикеров: {count}.',
        'media_other_scope':'Запреты другой области продолжают действовать.',
    })

    @loader.command(ru_doc=' [-p] [-g] - запретить медиа/стикер; [-p] - пак; [-g] - глобально', en_doc=' [-p] [-g] - ban replied media or toggle a sticker ban; -p - sticker pack; -g - globally')
    @loader.owner
    async def banmedia(self, message: Message):
        args = [str(item).lower() for item in self._args(message)]
        reply = await self._get_reply_message(message)
        sticker_key, _ = self._sticker_ban_keys(reply) if reply else (None, None)
        if sticker_key is not None or "-p" in args:
            return await self._toggle_sticker_ban(message, args, reply)
        await self._media_ban_command(message, clear=False)

    @loader.command(ru_doc=' [-p] [-g] [-all] - снять запрет с реплая; [-p] - пак; [-g] - глобально; [-all] - снять все запреты', en_doc=' [-p] [-g] [-all] - unban replied media/sticker; -p - sticker pack; -g - globally; -all - clear all bans')
    @loader.owner
    async def unbanmedia(self, message: Message):
        args = [str(item).lower() for item in self._args(message)]
        if (len(args)!=len(set(args)) or any(arg not in {'-p','-g','-all'} for arg in args)
                or ('-p' in args and '-all' in args)):
            return await self._answer_temporary(
                message,_EMOJI['error']+' '+self._s('media_unban_args'),_IMPORTANT_RESULT_TTL)
        if '-all' in args:
            return await self._media_ban_command(message, clear=True)
        reply = await self._get_reply_message(message)
        sticker_key, _ = self._sticker_ban_keys(reply) if reply else (None, None)
        if "-p" in args:
            return await self._toggle_sticker_ban(message, args, reply, remove_only=True)
        if sticker_key is not None:
            return await self._toggle_sticker_ban(message, args, reply, remove_only=True)
        await self._media_unban_reply(message, reply, global_scope='-g' in args)

    async def _media_unban_reply(self, message, reply, global_scope=False):
        key = self._media_ban_key(reply)
        if key is None:
            return await self._answer_temporary(
                message,_EMOJI['error']+' '+self._s('media_ban_reply'),_IMPORTANT_RESULT_TTL)
        try:
            if self._media_donor is None and self.get('media_donor', None):
                return await self._answer_temporary(message,
                    _EMOJI['error']+' '+self._s('media_donor_unavailable'),_IMPORTANT_RESULT_TTL)
            if not global_scope and not await self._media_can_delete(message):
                return await self._answer_temporary(
                    message,_EMOJI['error']+' '+self._s('media_ban_rights'),_IMPORTANT_RESULT_TTL)
            scope = 'global' if global_scope else str(int(message.chat_id))
            removed = await self._media_donor_remove(scope,key) if self._media_donor is not None else False
            text = self._s('media_unbanned' if removed else 'media_not_banned')
            other_scope = str(int(message.chat_id)) if global_scope else 'global'
            if key in self._media_bans.get(other_scope,{}):
                text += '\n'+self._s('media_other_scope')
        except Exception:
            logger.exception('Could not remove media ban global=%s key=%s',global_scope,key)
            return await self._answer_temporary(
                message,_EMOJI['error']+' '+self._s('media_ban_failed'),_IMPORTANT_RESULT_TTL)
        return await self._inline_answer(message,_EMOJI['success' if removed else 'error']+' <b>'+text+'</b>')

    async def _media_ban_command(self, message, clear):
        args = [arg.lower() for arg in self._args(message)]
        error = None
        allowed = {'-g','-all'} if clear else {'-g'}
        if len(args)!=len(set(args)) or any(arg not in allowed for arg in args) or (clear and '-all' not in args):
            error = 'media_unban_args' if clear else 'media_ban_args'
        if error:
            return await self._answer_temporary(message,_EMOJI['error']+' '+self._s(error),_IMPORTANT_RESULT_TTL)
        global_scope = '-g' in args
        try:
            reply = None if clear else await self._get_reply_message(message)
            key = None if clear else self._media_ban_key(reply)
            signature = None if clear else self._media_signature(reply)
            if not clear and key is None:
                error = 'media_ban_reply'
            elif not global_scope and not await self._media_can_delete(message):
                error = 'media_ban_rights'
            if error:
                return await self._answer_temporary(message,_EMOJI['error']+' '+self._s(error),_IMPORTANT_RESULT_TTL)
            if self._media_donor is None and not clear and not self.get('media_donor', None):
                if not await self._media_donor_load():
                    return await self._answer_temporary(message,
                        _EMOJI['error']+' '+self._s('media_donor_unavailable'),_IMPORTANT_RESULT_TTL)
            if self._media_donor is None and (not clear or self.get('media_donor', None)):
                return await self._answer_temporary(message,
                    _EMOJI['error']+' '+self._s('media_donor_unavailable'),_IMPORTANT_RESULT_TTL)
            scope = 'global' if global_scope else str(int(message.chat_id))
            fingerprint = None if clear else dict(await self._media_fingerprint(reply,visual=self._media_video_info(reply) is not None))
            if signature:
                fingerprint['signature_v1'] = signature
            if clear:
                count = await self._media_donor_clear(scope) if self._media_donor is not None else 0
                updated_stickers = copy.deepcopy(self._sticker_bans)
                sticker_count = len(updated_stickers.pop(scope, {}))
                text = self._s('media_cleared',count=count+sticker_count)
                other_scope = str(int(message.chat_id)) if global_scope else 'global'
                if self._media_bans.get(other_scope) or self._sticker_bans.get(other_scope):
                    text += '\n'+self._s('media_other_scope')
            else:
                rules = self._media_bans.get(scope,{})
                text = self._s('media_already_banned' if key in rules else 'media_banned')
                if key not in rules:
                    await self._media_donor_add(scope,key,fingerprint,reply)
            if clear and sticker_count:
                self._save_state('sticker_bans',updated_stickers)
                self._sticker_bans = updated_stickers
        except Exception:
            logger.exception('Could not update media bans global=%s clear=%s',global_scope,clear)
            return await self._answer_temporary(message,_EMOJI['error']+' '+self._s('media_ban_failed'),_IMPORTANT_RESULT_TTL)
        if not clear:
            return await self._inline_answer(message,_EMOJI['success']+' <b>'+text+'</b>')
        await self._inline_answer(message,_EMOJI['success']+' <b>GodChat · '+
            self._s('media_global_title' if global_scope else 'media_ban_title')+'</b>\n\n<blockquote>'+text+'</blockquote>')

    def _save_guest_bot_blocks(self):
        self._save_state("guest_bot_blocks", self._guest_bot_blocks)

    def _guest_bots_blocked(self, chat_id):
        return bool(self._guest_bot_blocks.get(str(int(chat_id)), False))

    def _save_guest_bot_member_blocks(self):
        self._save_state("guest_bot_member_blocks", self._guest_bot_member_blocks)

    def _guest_bots_blocked_for_member(self, chat_id, user_id):
        users = self._guest_bot_member_blocks.get(str(int(chat_id)), {})
        return bool(
            users.get(str(int(user_id)), False)
            if isinstance(users, dict)
            else False
        )

    @staticmethod
    def _guest_bot_caller_user_id(message):
        peer = getattr(message, "guestchat_via_from", None)
        user_id = getattr(peer, "user_id", None)
        return int(user_id) if user_id is not None else None

    @loader.watcher("in", "only_messages")
    async def guest_bot_watcher(self, message: Message):
        chat_id = getattr(message, "chat_id", None)
        if chat_id is None or not getattr(message, "guestchat_via_from", None):
            return
        caller_id = self._guest_bot_caller_user_id(message)
        if not self._guest_bots_blocked(chat_id) and not (
            caller_id is not None
            and self._guest_bots_blocked_for_member(chat_id, caller_id)
        ):
            return
        try:
            await message.delete()
        except Exception:
            logger.debug("Could not delete guest-bot message", exc_info=True)

    async def _operator_capabilities(self, entity):
        try:
            permissions = await self.client.get_permissions(
                entity,
                self._me_id,
            )
        except Exception:
            logger.exception("Could not get operator permissions")
            return {
                "admin": False,
                "ban_users": False,
                "delete_messages": False,
                "invite_users": False,
                "add_admins": False,
                "manage_ranks": False,
            }
        creator = bool(getattr(permissions, "is_creator", False))
        admin = bool(getattr(permissions, "is_admin", False))
        rights = getattr(
            getattr(permissions, "participant", None),
            "admin_rights",
            None,
        )
        return {
            "admin": admin,
            "ban_users": creator
            or bool(getattr(permissions, "ban_users", False)),
            "delete_messages": creator
            or bool(getattr(permissions, "delete_messages", False)),
            "invite_users": creator
            or bool(getattr(permissions, "invite_users", False)),
            "add_admins": creator
            or bool(getattr(permissions, "add_admins", False)),
            "manage_ranks": creator
            or (
                admin
                and (
                    isinstance(entity, types.Chat)
                    or bool(getattr(rights, "manage_ranks", False))
                )
            ),
        }

    async def _refresh_operator_capabilities(self, state):
        state["capabilities"] = await self._operator_capabilities(
            state["entity"]
        )
        return state["capabilities"]

    @staticmethod
    def _input_source_form(call):
        form = getattr(call, "form", None)
        source_id = (
            form.get("inline_message_id")
            if isinstance(form, dict)
            else None
        )
        if source_id:
            call.inline_message_id = source_id
        return call

    @staticmethod
    def _rank(args):
        rank = " ".join(args).strip()
        if not rank or len(rank) > 16:
            return None
        return rank

    def _rank_error(self):
        return f"{_EMOJI['error']} <b>{self._s('rank_error')}</b>"

    def _rank_result(self, user, rank, admin):
        kind = self._s("tag_admin" if admin else "tag_regular")
        return (
            f"{_EMOJI['prefix']} <b>GodChat · {self._s('tag')}</b>\n\n"
            f"<blockquote>{self._label(user)}\n"
            f"<b>{self._s('tag')}:</b> {utils.escape_html(rank)}\n"
            f"<b>{self._s('tag_type')}:</b> {kind}</blockquote>"
        )

    async def _set_rank(self, entity, target, rank):
        await self.client(
            functions.messages.EditChatParticipantRankRequest(
                peer=entity,
                participant=target,
                rank=rank,
            )
        )

    @loader.command(ru_doc=" - снять админку со всех в чате, сохранив префиксы", en_doc=' - remove all chat administrators while keeping their tags')
    @loader.group_admin_add_admins
    async def aclear(self, message: Message):
        if getattr(message, "is_private", False) or not getattr(message, "is_group", False):
            return await self._answer_temporary(
                message, f"{_EMOJI['error']} <b>{self._s('groups_only')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
        try:
            entity = await self.client.get_entity(message.chat_id)
            capabilities = await self._operator_capabilities(entity)
            if not capabilities.get("add_admins") or not capabilities.get("manage_ranks"):
                return await self._answer_temporary(
                    message, f"{_EMOJI['error']} <b>{self._s('aclear_rights')}</b>",
                    _IMPORTANT_RESULT_TTL,
                )
            admins = []
            iterator = self.client.iter_participants(
                entity,
                filter=ChannelParticipantsAdmins(),
            ) if isinstance(entity, types.Channel) else self.client.iter_participants(entity)
            async for user in iterator:
                if getattr(user, "bot", False):
                    continue
                participant = getattr(user, "participant", None)
                if isinstance(participant, (types.ChannelParticipantCreator, types.ChatParticipantCreator)):
                    continue
                if not isinstance(participant, (types.ChannelParticipantAdmin, types.ChatParticipantAdmin)):
                    continue
                admins.append((user, getattr(participant, "rank", None) or ""))
        except Exception:
            logger.exception("Could not collect chat administrators for aclear")
            return await self._answer_temporary(
                message, f"{_EMOJI['error']} <b>{self._s('aclear_list_failed')}</b>",
                _IMPORTANT_RESULT_TTL,
            )

        admins.sort(key=lambda item: int(item[0].id) == int(self._me_id))
        removed = failed = tag_failed = 0
        for user, rank in admins:
            try:
                if isinstance(entity, types.Channel):
                    await self.client(functions.channels.EditAdminRequest(
                        channel=entity,
                        user_id=user,
                        admin_rights=types.ChatAdminRights(),
                        rank=rank,
                    ))
                else:
                    await self.client.edit_admin(entity, user, is_admin=False)
                removed += 1
                if rank:
                    try:
                        permissions = await self.client.get_permissions(entity, user)
                        if getattr(getattr(permissions, "participant", None), "rank", None) != rank:
                            await self._set_rank(entity, user, rank)
                    except Exception:
                        tag_failed += 1
                        logger.exception("Could not preserve tag after demoting %s", user.id)
            except FloodWaitError as error:
                logger.warning("aclear stopped by flood wait: %s seconds", error.seconds)
                failed += len(admins) - removed - failed
                break
            except Exception:
                failed += 1
                logger.exception("Could not demote chat administrator %s", user.id)

        text = self._s("aclear_result", removed=removed, failed=failed, tag_failed=tag_failed)
        await self._inline_answer(
            message,
            f"{_EMOJI['success' if not failed and not tag_failed else 'warning']} <b>{text}</b>",
        )

    @loader.command(
        ru_doc=" [пользователь] [префикс] [-a] - префикс; -a - админ-префикс"
    , en_doc=' [user] [tag] [-a] - set a tag; -a - admin tag')
    @loader.group_admin
    async def prefix(self, message: Message):
        context = await self._context(message, allow_self=True, target_options={"-a"})
        if not context:
            return
        entity, target, permissions, args = context
        admin_tag = any(arg.lower() == "-a" for arg in args)
        if sum(arg.lower() == "-a" for arg in args) > 1:
            return await self._answer_temporary(message, self._rank_error(), _IMPORTANT_RESULT_TTL)
        args = [arg for arg in args if arg.lower() != "-a"]
        rank = self._rank(args)
        if rank is None:
            await self._answer_temporary(
                message,
                self._rank_error(),
                _IMPORTANT_RESULT_TTL,
            )
            return
        if admin_tag:
            if not await self.allmodules.check_security(message, self._set_admin_prefix):
                return await self._answer_temporary(
                    message,
                    f"{_EMOJI['error']} <b>{self._s('admin_tag_rights')}</b>",
                    _IMPORTANT_RESULT_TTL,
                )
            return await self._set_admin_prefix(message, entity, target, permissions, rank)
        if getattr(permissions, "is_creator", False):
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('creator_regular_tag')}</b>"
                ),
            )
            return
        try:
            await self._set_rank(entity, target, rank)
            if getattr(permissions, "is_admin", False):
                try:
                    await self.client.edit_admin(
                        entity,
                        target,
                        is_admin=False,
                    )
                except Exception:
                    logger.exception(
                        "Could not demote participant after rank change"
                    )
                    await self._inline_answer(
                        message,
                        (
                            f"{_EMOJI['error']} "
                            f"<b>{self._s('tag_changed_demote_failed')}</b>"
                        ),
                    )
                    return
        except Exception:
            logger.exception("Could not set participant rank")
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} <b>{self._s('tag_change_failed')}</b>"
                ),
            )
            return
        await self._answer_temporary(
            message,
            self._rank_result(
                target,
                rank,
                False,
            ),
            _NORMAL_RESULT_TTL,
        )

    @loader.group_admin_add_admins
    async def _set_admin_prefix(self, message, entity, target, permissions, rank):
        if isinstance(entity, types.Chat):
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} <b>{self._s('admin_tag_supergroup')}</b>"
                ),
            )
            return
        try:
            if getattr(permissions, "is_creator", False):
                await self._set_rank(entity, target, rank)
            elif getattr(permissions, "is_admin", False):
                await self.client(
                    functions.channels.EditAdminRequest(
                        channel=entity,
                        user_id=target,
                        admin_rights=permissions.participant.admin_rights,
                        rank=rank,
                    )
                )
            else:
                await self.client(
                    functions.channels.EditAdminRequest(
                        channel=entity,
                        user_id=target,
                        admin_rights=types.ChatAdminRights(other=True),
                        rank=rank,
                    )
                )
        except Exception:
            logger.exception("Could not set administrator rank")
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('admin_tag_failed')}</b>"
                ),
            )
            return
        await self._answer_temporary(
            message,
            self._rank_result(target, rank, True),
            _NORMAL_RESULT_TTL,
        )

    def _prune_random_runtime(self):
        now = time.monotonic()
        self._sessions = {
            token: state
            for token, state in self._sessions.items()
            if state.get("expires", 0) > now
        }
        while len(self._sessions) > _MAX_SESSIONS:
            token = min(
                self._sessions,
                key=lambda item: self._sessions[item].get("expires", 0),
            )
            self._sessions.pop(token, None)
        for key, cache in list(self._activity_cache.items()):
            if cache.get("expires", 0) <= now:
                self._activity_cache.pop(key, None)
                lock = self._cache_locks.get(key)
                if not lock or not lock.locked():
                    self._cache_locks.pop(key, None)
        for key, cache in list(self._member_cache.items()):
            if cache.get("expires", 0) <= now:
                self._member_cache.pop(key, None)
        for key, lock in list(self._cache_locks.items()):
            if key not in self._activity_cache and not lock.locked():
                self._cache_locks.pop(key, None)
        while len(self._activity_cache) > _MAX_ACTIVITY_CACHE:
            key = min(
                self._activity_cache,
                key=lambda item: self._activity_cache[item].get("expires", 0),
            )
            self._activity_cache.pop(key, None)
            self._cache_locks.pop(key, None)
        while len(self._member_cache) > _MAX_MEMBER_CACHE:
            key = min(
                self._member_cache,
                key=lambda item: self._member_cache[item].get("expires", 0),
            )
            self._member_cache.pop(key, None)

    @classmethod
    def _random_profile_url(cls, user):
        username = cls._username(user)
        return f"https://t.me/{username}" if username else None

    @classmethod
    def _random_message_url(cls, entity, chat_id, message_id):
        username = cls._username(entity)
        if username:
            return f"https://t.me/{username}/{message_id}"
        chat_id = str(chat_id)
        if chat_id.startswith("-100"):
            return f"https://t.me/c/{chat_id[4:]}/{message_id}"
        return None

    def _random_display_name(self, user):
        custom = self._custom_name(user)
        if custom: return custom
        username = self._username(user)
        if username:
            return f"@{username}"
        return self._name(user)

    async def _random_admin_ids(self, entity):
        result = set()
        if not isinstance(entity, types.Channel):
            async for user in self.client.iter_participants(entity):
                participant = getattr(user, "participant", None)
                if isinstance(
                    participant,
                    (
                        types.ChatParticipantAdmin,
                        types.ChatParticipantCreator,
                    ),
                ):
                    result.add(int(user.id))
            return result
        async for user in self.client.iter_participants(
            entity,
            filter=ChannelParticipantsAdmins(),
        ):
            result.add(int(user.id))
        return result

    @staticmethod
    def _eligible_random_member(user, excluded_ids):
        return (
            int(user.id) not in excluded_ids
            and not getattr(user, "bot", False)
            and not getattr(user, "deleted", False)
        )

    async def _new_random_member_cache(self, entity, chat_id):
        admin_ids = await self._random_admin_ids(entity)
        if self._me_id:
            admin_ids.add(int(self._me_id))
        cache = {
            "expires": time.monotonic() + _MEMBER_CACHE_TTL,
            "admins": admin_ids,
            "users": {},
            "total": 0,
            "offsets": set(),
            "channel": isinstance(entity, types.Channel),
        }
        if cache["channel"]:
            channel = tl_utils.get_input_channel(entity)
            cache["channel_input"] = channel
            try:
                full = await self.client(
                    functions.channels.GetFullChannelRequest(channel=channel)
                )
                cache["total"] = int(
                    getattr(full.full_chat, "participants_count", 0) or 0
                )
            except Exception:
                logger.debug(
                    "Could not get participant count",
                    exc_info=True,
                )
        else:
            async for user in self.client.iter_participants(entity):
                if self._eligible_random_member(user, admin_ids):
                    cache["users"][int(user.id)] = user
        self._member_cache[str(chat_id)] = cache
        self._prune_random_runtime()
        return cache

    async def _fill_random_member_cache(self, cache):
        if not cache["channel"]:
            return False
        total = max(cache["total"], _PARTICIPANT_PAGE)
        max_offset = max(0, total - _PARTICIPANT_PAGE)
        offset = None
        for _ in range(_PARTICIPANT_ATTEMPTS):
            candidate = random.randint(0, max_offset) if max_offset else 0
            if candidate in cache["offsets"]:
                continue
            offset = candidate
            break
        if offset is None:
            return False
        cache["offsets"].add(offset)
        result = await self.client(
            functions.channels.GetParticipantsRequest(
                channel=cache["channel_input"],
                filter=types.ChannelParticipantsRecent(),
                offset=offset,
                limit=_PARTICIPANT_PAGE,
                hash=0,
            )
        )
        for participant in getattr(result, "participants", None) or []:
            if isinstance(
                participant,
                (
                    types.ChannelParticipantAdmin,
                    types.ChannelParticipantCreator,
                ),
            ):
                cache["admins"].add(int(participant.user_id))
        previous = len(cache["users"])
        for user in result.users:
            if self._eligible_random_member(user, cache["admins"]):
                cache["users"][int(user.id)] = user
        return len(cache["users"]) > previous

    async def _choose_random_member(self, entity, chat_id, excluded_ids):
        self._prune_random_runtime()
        cache_key = str(chat_id)
        cache = self._member_cache.get(cache_key)
        if not cache:
            cache = await self._new_random_member_cache(entity, chat_id)
        else:
            cache["expires"] = time.monotonic() + _MEMBER_CACHE_TTL
        excluded_ids = {int(user_id) for user_id in excluded_ids}
        for _ in range(_PARTICIPANT_ATTEMPTS):
            candidates = [
                user
                for user_id, user in cache["users"].items()
                if user_id not in excluded_ids
            ]
            if candidates:
                return secrets.choice(candidates)
            filled = await self._fill_random_member_cache(cache)
            if not filled and cache["total"] <= _PARTICIPANT_PAGE:
                break
        raise ValueError("No eligible members in cache")

    @staticmethod
    def _random_message_date(message):
        value = getattr(message, "date", None)
        if value and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _random_message_preview(self, message):
        text = (
            getattr(message, "raw_text", None)
            or getattr(message, "text", None)
            or ""
        ).strip()
        text = " ".join(text.split())
        if not text:
            text = self._s("media")
        return text[:180] + ("…" if len(text) > 180 else "")

    async def _build_random_activity_cache(self, entity, user, months):
        cutoff = datetime.now(timezone.utc) - _ACTIVITY_PERIODS[months]
        count = 0
        messages = []
        async for item in self.client.iter_messages(
            entity,
            from_user=user,
        ):
            message_date = self._random_message_date(item)
            if message_date and message_date < cutoff:
                break
            if isinstance(item, types.MessageService):
                continue
            count += 1
            if not messages:
                messages.append(
                    {
                        "id": item.id,
                        "date": message_date,
                        "text": self._random_message_preview(item),
                    }
                )
        return {
            "expires": time.monotonic() + _ACTIVITY_CACHE_TTL,
            "count": count,
            "messages": messages,
        }

    async def _random_activity_cache_for(
        self,
        entity,
        chat_id,
        user,
        months,
    ):
        self._prune_random_runtime()
        cache_key = f"{chat_id}:{int(user.id)}:{months}"
        cached = self._activity_cache.get(cache_key)
        if cached and cached["expires"] > time.monotonic():
            return cached
        lock = self._cache_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._activity_cache.get(cache_key)
            if cached and cached["expires"] > time.monotonic():
                return cached
            cached = await self._build_random_activity_cache(
                entity,
                user,
                months,
            )
            self._activity_cache[cache_key] = cached
            self._prune_random_runtime()
            return cached

    async def _random_activity(self, entity, chat_id, user, months):
        cache = await self._random_activity_cache_for(
            entity,
            chat_id,
            user,
            months,
        )
        return cache["count"], cache["messages"]

    async def _random_latest_message(self, entity, chat_id, user):
        now = time.monotonic()
        for months in _ACTIVITY_PERIODS:
            cached = self._activity_cache.get(
                f"{chat_id}:{int(user.id)}:{months}"
            )
            if (
                cached
                and cached.get("expires", 0) > now
                and cached.get("messages")
            ):
                return list(cached["messages"][:1])

        async def fetch():
            async for item in self.client.iter_messages(
                entity,
                from_user=user,
                limit=5,
            ):
                if isinstance(item, types.MessageService):
                    continue
                return [
                    {
                        "id": item.id,
                        "date": self._random_message_date(item),
                        "text": self._random_message_preview(item),
                    }
                ]
            return []

        try:
            return await asyncio.wait_for(fetch(), timeout=3)
        except asyncio.TimeoutError:
            logger.debug("Latest member message request timed out")
            return []
        except Exception:
            logger.debug(
                "Could not get latest member message",
                exc_info=True,
            )
            return []

    @staticmethod
    def _random_member_snapshot(state):
        return {
            "user": state["user"],
            "display_name": state["display_name"],
            "activity": state["activity"],
            "activity_months": state["activity_months"],
            "last_messages": list(state["last_messages"]),
            "banned": state["banned"],
            "kicked": state["kicked"],
            "notice": state["notice"],
            "notice_error": state.get("notice_error", False),
            "role": state.get("role"),
            "common_chats": state.get("common_chats"),
            "joined_at": state.get("joined_at"),
            "member_status": state.get("member_status", "member"),
            "member_inline_blocked": bool(
                state.get("member_inline_blocked", False)
            ),
        }

    def _sync_random_history(self, state):
        history = state.get("history")
        index = state.get("history_index", 0)
        if history and 0 <= index < len(history):
            history[index] = self._random_member_snapshot(state)

    @staticmethod
    def _restore_random_history(state, index):
        state["history_index"] = index
        state.update(state["history"][index])

    async def _make_random_state(
        self,
        entity,
        chat_id,
        excluded_ids,
        topic_id=None,
    ):
        try:
            user = await self._choose_random_member(
                entity,
                chat_id,
                excluded_ids,
            )
        except ValueError:
            if not excluded_ids:
                raise
            user = await self._choose_random_member(
                entity,
                chat_id,
                set(),
            )
            excluded_ids = set()
        last_messages, member_info, chat_inline_blocked = await asyncio.gather(
            self._random_latest_message(entity, chat_id, user),
            self._fresh_member_info(entity, user, None),
            self._chat_inline_blocked(entity),
        )
        role, _, member_status, member_inline_blocked = member_info
        state = {
            "entity": entity,
            "chat_id": chat_id,
            "topic_id": topic_id,
            "user": user,
            "display_name": self._random_display_name(user),
            "activity": None,
            "activity_months": None,
            "last_messages": last_messages,
            "seen": set(excluded_ids) | {int(user.id)},
            "banned": False,
            "kicked": False,
            "notice": None,
            "notice_error": False,
            "busy": False,
            "expires": time.monotonic() + _SESSION_TTL,
            "random_mode": True,
            "member_status": member_status,
            "role": role,
            "member_inline_blocked": member_inline_blocked,
            "chat_inline_blocked": chat_inline_blocked,
            "capabilities": await self._operator_capabilities(entity),
        }
        state["history"] = [self._random_member_snapshot(state)]
        state["history_index"] = 0
        return state

    def _member_role(self, permissions):
        if getattr(permissions, "is_creator", False):
            return self._s("role_creator")
        if getattr(permissions, "is_admin", False):
            return self._s("role_admin")
        return self._s("role_member")

    async def _fresh_member_info(self, entity, user, fallback):
        try:
            if isinstance(entity, types.Channel):
                result = await asyncio.wait_for(
                    self.client(
                        functions.channels.GetParticipantRequest(
                            channel=entity,
                            participant=user,
                        )
                    ),
                    timeout=5,
                )
                participant = result.participant
            else:
                result = await asyncio.wait_for(
                    self.client(
                        functions.messages.GetFullChatRequest(
                            chat_id=entity.id,
                        )
                    ),
                    timeout=5,
                )
                participants = getattr(
                    getattr(result.full_chat, "participants", None),
                    "participants",
                    [],
                )
                participant = next(
                    (
                        item
                        for item in participants
                        if int(item.user_id) == int(user.id)
                    ),
                    None,
                )
            if isinstance(
                participant,
                (
                    types.ChannelParticipantCreator,
                    types.ChatParticipantCreator,
                ),
            ):
                role = self._s("role_creator")
            elif isinstance(
                participant,
                (
                    types.ChannelParticipantAdmin,
                    types.ChatParticipantAdmin,
                ),
            ):
                role = self._s("role_admin")
            else:
                role = self._s("role_member")
            if isinstance(participant, types.ChannelParticipantBanned):
                member_status = (
                    "banned"
                    if getattr(
                        participant.banned_rights,
                        "view_messages",
                        False,
                    )
                    else "member"
                )
            elif participant is None or isinstance(
                participant,
                types.ChannelParticipantLeft,
            ):
                member_status = "unbanned"
            else:
                member_status = "member"
            joined_at = (
                getattr(participant, "date", None)
                if member_status == "member"
                else None
            )
            return (
                role,
                joined_at,
                member_status,
                bool(
                    getattr(
                        getattr(participant, "banned_rights", None),
                        "send_inline",
                        False,
                    )
                ),
            )
        except Exception:
            logger.debug("Could not get fresh member info", exc_info=True)
            return self._member_role(fallback), None, "member", False

    async def _common_chats_count(self, user):
        try:
            result = await asyncio.wait_for(
                self.client(
                    functions.messages.GetCommonChatsRequest(
                        user_id=user,
                        max_id=0,
                        limit=1,
                    )
                ),
                timeout=5,
            )
        except Exception:
            logger.debug("Could not get common chats count", exc_info=True)
            return None
        return int(
            getattr(
                result,
                "count",
                len(getattr(result, "chats", None) or []),
            )
        )

    async def _make_member_state(
        self,
        entity,
        chat_id,
        user,
        permissions,
        topic_id=None,
    ):
        last_messages, common_chats, member_info, chat_inline_blocked = (
            await asyncio.gather(
                self._random_latest_message(entity, chat_id, user),
                self._common_chats_count(user),
                self._fresh_member_info(entity, user, permissions),
                self._chat_inline_blocked(entity),
            )
        )
        role, joined_at, member_status, member_inline_blocked = member_info
        state = {
            "entity": entity,
            "chat_id": chat_id,
            "topic_id": topic_id,
            "user": user,
            "display_name": self._random_display_name(user),
            "activity": None,
            "activity_months": None,
            "last_messages": last_messages,
            "seen": {int(user.id)},
            "banned": member_status == "banned",
            "kicked": False,
            "notice": None,
            "notice_error": False,
            "busy": False,
            "expires": time.monotonic() + _SESSION_TTL,
            "random_mode": False,
            "role": role,
            "common_chats": common_chats,
            "joined_at": joined_at,
            "member_status": member_status,
            "member_inline_blocked": member_inline_blocked,
            "chat_inline_blocked": chat_inline_blocked,
            "capabilities": await self._operator_capabilities(entity),
        }
        state["history"] = [self._random_member_snapshot(state)]
        state["history_index"] = 0
        return state

    def _random_card(self, state):
        user = state["user"]
        resolver = getattr(self, '_random_display_name', None)
        display_name = resolver(user) if callable(resolver) else state['display_name']
        name = utils.escape_html(display_name)
        profile_url = self._random_profile_url(user)
        identity = (
            f'<a href="{utils.escape_html(profile_url)}"><b>{name}</b></a>'
            if profile_url
            else f"<b>{name}</b>"
        )
        if state["display_name"] != str(int(user.id)):
            identity += f" (<code>{int(user.id)}</code>)"
        usernames = self._active_usernames(user)
        if usernames:
            identity += '\n<blockquote expandable><b>'+self._s('active_usernames')+':</b>\n'+'\n'.join(
                '<a href="https://t.me/'+utils.escape_html(value)+'">@'+utils.escape_html(value)+'</a>' for value in usernames)+'</blockquote>'
        activity_line = f"<i>{self._s('activity_unchecked')}</i>"
        if state["activity"] is not None:
            activity_line = (
                f"{_RANDOM_EMOJI['activity']} <b>{self._s('activity', months=state['activity_months'])}:</b> "
                f"<code>{state['activity']}</code> {self._s('messages_short')}"
            )
        inline_blocked = (
            state.get("member_status", "member") == "member"
            and state.get("role") == self._s("role_member")
            and (
                state.get("member_inline_blocked", False)
                or state.get("chat_inline_blocked", False)
            )
        )
        inline_status = (
            f"<b>{self._s('inline')}:</b> {self._s('forbidden')}\n" if inline_blocked else ""
        )
        member_details = ""
        if not state.get("random_mode"):
            visible_status = {
                "banned": self._s("banned"),
                "kicked": self._s("kicked"),
                "unbanned": self._s("not_in_chat"),
            }.get(
                state.get("member_status", "member"),
                state.get("role") or self._s("role_member"),
            )
            common_chats = state.get("common_chats")
            common_chats = (
                str(common_chats)
                if common_chats is not None
                else self._s("unknown")
            )
            joined_at = state.get("joined_at")
            joined_at = (
                joined_at.strftime("%d.%m.%Y")
                if joined_at
                else self._s("unknown")
            )
            member_details = (
                f"<b>{self._s('status')}:</b> "
                f"{utils.escape_html(visible_status)}\n"
                f"<b>{self._s('common_chats')}:</b> <code>{common_chats}</code>\n"
                f"<b>{self._s('joined')}:</b> <code>{joined_at}</code>\n"
                f"{inline_status}"
            )
        last_block = f"<i>{self._s('last_message_missing')}</i>"
        if state["last_messages"]:
            item = state["last_messages"][0]
            message_url = self._random_message_url(
                state["entity"],
                state["chat_id"],
                item["id"],
            )
            preview = utils.escape_html(item["text"])
            date = item["date"]
            date_text = date.strftime("%d.%m %H:%M") if date else self._s("message")
            if message_url:
                last_block = (
                    f'<blockquote><a href="{utils.escape_html(message_url)}">'
                    f"<b>{date_text}</b> - {preview}</a></blockquote>"
                )
            else:
                last_block = (
                    f"<blockquote><b>{date_text}</b> - "
                    f"{preview}</blockquote>"
                )
        status = ""
        if state.get("notice"):
            notice_icon = (
                _RANDOM_EMOJI["ban"]
                if state.get("notice_error")
                else _RANDOM_EMOJI["ok"]
            )
            status = (
                f"\n\n{notice_icon} "
                f"<b>{utils.escape_html(state['notice'])}</b>"
            )
        elif state.get("member_status") == "banned":
            status = (
                f"\n\n{_RANDOM_EMOJI['ban']} "
                f"<b>{self._s('user_banned')}</b>"
            )
        elif state.get("member_status") == "kicked":
            status = (
                f"\n\n{_RANDOM_EMOJI['ok']} "
                f"<b>{self._s('user_kicked')}</b>"
            )
        elif state.get("member_status") == "unbanned":
            status = (
                f"\n\n{_RANDOM_EMOJI['ok']} "
                f"<b>{self._s('user_unbanned')}</b>"
            )
        return (
            f"{_RANDOM_EMOJI['dice']} "
            f"<b>{self._s('random_member') if state.get('random_mode') else self._s('member_card')}</b>\n\n"
            f"{_RANDOM_EMOJI['user']} {identity}\n"
            f"{inline_status if state.get('random_mode') else ''}"
            f"{member_details}"
            f"{activity_line}\n\n"
            f"{_RANDOM_EMOJI['message']} <b>{self._s('last_message')}:</b>\n"
            f"{last_block}{status}"
        )

    def _prefix_allowed(self, state, admin):
        capabilities = state.get("capabilities", {})
        role = state.get("role") or self._s("role_member")
        if state.get("member_status", "member") != "member":
            return False
        if admin:
            if not isinstance(state["entity"], types.Channel):
                return False
            if role == self._s("role_creator"):
                return (
                    int(state["user"].id) == self._me_id
                    and bool(capabilities.get("manage_ranks"))
                )
            return bool(
                capabilities.get("add_admins")
            )
        if role == self._s("role_creator") or not capabilities.get("manage_ranks"):
            return False
        return role != self._s("role_admin") or bool(capabilities.get("add_admins"))

    def _member_inline_button(self, token, state):
        if (
            not isinstance(state.get("entity"), types.Channel)
            or state.get("member_status", "member") != "member"
            or state.get("role") != self._s("role_member")
            or not state.get("capabilities", {}).get("ban_users")
        ):
            return None
        blocked = bool(
            state.get("member_inline_blocked", False)
            or state.get("chat_inline_blocked", False)
        )
        return {
            "text": (
                self._s("inline_allow")
                if blocked
                else self._s("inline_forbid")
            ),
            "callback": self._random_toggle_inline,
            "args": (token,),
            "style": "danger" if not blocked else "success",
        }

    def _guest_bot_button(self, token, state):
        if not state.get("capabilities", {}).get("delete_messages"):
            return None
        blocked = self._guest_bots_blocked_for_member(
            state["chat_id"],
            state["user"].id,
        )
        return {
            "text": (
                self._s("guest_allow_button")
                if blocked
                else self._s("guest_forbid_button")
            ),
            "callback": self._random_toggle_guest_bots,
            "args": (token,),
            "style": "success" if blocked else "danger",
        }

    def _random_markup(self, token, state):
        member_status = state.get("member_status", "member")
        is_banned = member_status == "banned"
        capabilities = state.get("capabilities", {})
        target_is_admin = state.get("role") in {self._s("role_admin"), self._s("role_creator")}
        moderation_row = []
        if capabilities.get("ban_users") and is_banned:
            moderation_row.append(
                {
                    "text": self._s("unban_button"),
                    "callback": self._random_unban,
                    "args": (token,),
                    "style": "success",
                }
            )
        elif capabilities.get("ban_users") and not target_is_admin:
            if member_status == "member":
                moderation_row.append(
                    {
                        "text": self._s("kick_button"),
                        "callback": self._random_kick,
                        "args": (token,),
                        "style": "danger",
                    }
                )
            moderation_row.insert(
                len(moderation_row),
                {
                    "text": self._s("ban_button"),
                    "callback": self._random_ban,
                    "args": (token,),
                    "style": "danger",
                },
            )
        markup = []
        profile_url = self._random_profile_url(state["user"])
        if profile_url:
            markup.append(
                [{"text": self._s("profile_button"), "url": profile_url}]
            )
        elif state["last_messages"]:
            message_url = self._random_message_url(
                state["entity"],
                state["chat_id"],
                state["last_messages"][0]["id"],
            )
            if message_url:
                markup.append(
                    [
                        {
                            "text": self._s("last_message_button"),
                            "url": message_url,
                        }
                    ]
                )
        if not markup:
            markup.append(
                [
                    {
                        "text": self._s("copy_id_button"),
                        "copy": str(int(state["user"].id)),
                    }
                ]
            )
        rows = []
        if moderation_row:
            rows.append(moderation_row)
        rows.extend(
            [
                [
                    {
                        "text": self._s("one_month_button"),
                        "callback": self._random_check_activity,
                        "args": (token, 1),
                        "style": "primary",
                    },
                    {
                        "text": self._s("three_months_button"),
                        "callback": self._random_check_activity,
                        "args": (token, 3),
                        "style": "primary",
                    },
                ],
                [
                    {
                        "text": self._s("previous_button"),
                        "callback": self._random_previous,
                        "args": (token,),
                    },
                    {
                        "text": self._s("next_button"),
                        "callback": self._random_next,
                        "args": (token,),
                        "style": "primary",
                    },
                ],
                [
                    {
                        "text": self._s("close_button"),
                        "callback": self._random_close,
                        "args": (token,),
                        "style": "danger",
                    }
                ],
            ]
        )
        inline_button = self._member_inline_button(token, state)
        guest_button = self._guest_bot_button(token, state)
        if inline_button or guest_button:
            close_row = rows.pop()
            if inline_button:
                rows.append([inline_button])
            if guest_button:
                rows.append([guest_button])
            rows.append(close_row)
        markup.extend(rows)
        return markup

    def _member_markup(self, token, state):
        member_status = state.get("member_status", "member")
        is_banned = member_status == "banned"
        capabilities = state.get("capabilities", {})
        role = state.get("role") or self._s("role_member")
        target_is_admin = role in {self._s("role_admin"), self._s("role_creator")}
        moderation_row = []
        if capabilities.get("ban_users") and is_banned:
            moderation_row.append(
                {
                    "text": self._s("unban_button"),
                    "callback": self._random_unban,
                    "args": (token,),
                    "style": "success",
                }
            )
        elif capabilities.get("ban_users") and not target_is_admin:
            if member_status == "member":
                moderation_row.append(
                    {
                        "text": self._s("kick_button"),
                        "callback": self._random_kick,
                        "args": (token,),
                        "style": "danger",
                    }
                )
            moderation_row.append(
                {
                    "text": self._s("ban_button"),
                    "callback": self._random_ban,
                    "args": (token,),
                    "style": "danger",
                }
            )
        markup = []
        profile_url = self._random_profile_url(state["user"])
        if profile_url:
            markup.append(
                [{"text": self._s("profile_button"), "url": profile_url}]
            )
        elif state["last_messages"]:
            message_url = self._random_message_url(
                state["entity"],
                state["chat_id"],
                state["last_messages"][0]["id"],
            )
            if message_url:
                markup.append(
                    [
                        {
                            "text": self._s("last_message_button"),
                            "url": message_url,
                        }
                    ]
                )
        if not markup:
            markup.append(
                [
                    {
                        "text": self._s("copy_id_button"),
                        "copy": str(int(state["user"].id)),
                    }
                ]
            )
        rows = []
        if moderation_row:
            rows.append(moderation_row)
        rows.append(
            [
                {
                    "text": self._s("one_month_button"),
                    "callback": self._random_check_activity,
                    "args": (token, 1),
                    "style": "primary",
                },
                {
                    "text": self._s("three_months_button"),
                    "callback": self._random_check_activity,
                    "args": (token, 3),
                    "style": "primary",
                },
            ]
        )
        inline_button = self._member_inline_button(token, state)
        if inline_button:
            rows.append([inline_button])
        guest_button = self._guest_bot_button(token, state)
        if guest_button:
            rows.append([guest_button])
        if member_status == "member":
            rank_row = []
            if self._prefix_allowed(state, False):
                rank_row.append(
                    {
                        "text": self._s("tag_button"),
                        "input": self._s("tag_input"),
                        "handler": self._member_prefix_input,
                        "args": (token, False),
                    }
                )
            if self._prefix_allowed(state, True):
                rank_row.append(
                    {
                        "text": self._s("admin_tag_button"),
                        "input": self._s("admin_tag_input"),
                        "handler": self._member_prefix_input,
                        "args": (token, True),
                        "style": "success",
                    }
                )
            if rank_row:
                rows.append(rank_row)
        rows.append(
            [
                {
                    "text": self._s("close_button"),
                    "callback": self._random_close,
                    "args": (token,),
                    "style": "danger",
                }
            ]
        )
        markup.extend(rows)
        return markup

    def _member_state_markup(self, token, state):
        if state.get("random_mode"):
            return self._random_markup(token, state)
        return self._member_markup(token, state)

    async def _render_random(self, call, token):
        self._prune_random_runtime()
        state = self._sessions.get(token)
        if not state:
            await call.answer(
                self._s("card_expired"),
                show_alert=True,
            )
            return
        await self._refresh_operator_capabilities(state)
        self._sync_random_history(state)
        await call.edit(
            self._random_card(state),
            reply_markup=self._member_state_markup(token, state),
        )

    async def _random_state(self, call, token):
        self._prune_random_runtime()
        state = self._sessions.get(token)
        if not state:
            await call.answer(
                self._s("card_expired"),
                show_alert=True,
            )
        return state

    @asynccontextmanager
    async def _random_action(self, call, state):
        if state.get("busy"):
            await call.answer(self._s("action_running"))
            yield False
            return
        state["busy"] = True
        try:
            yield True
        finally:
            state["busy"] = False

    async def _random_close(self, call, token):
        self._sessions.pop(token, None)
        await call.delete()

    async def _random_previous(self, call, token):
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            index = state.get("history_index", 0)
            if index <= 0:
                await call.answer(self._s("first_member"))
                return
            self._sync_random_history(state)
            self._restore_random_history(state, index - 1)
            await self._render_random(call, token)

    async def _random_next(self, call, token):
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            self._sync_random_history(state)
            index = state.get("history_index", 0)
            history = state.get("history", [])
            if index + 1 < len(history):
                self._restore_random_history(state, index + 1)
                await self._render_random(call, token)
                return
            try:
                try:
                    user = await self._choose_random_member(
                        state["entity"],
                        state["chat_id"],
                        state["seen"],
                    )
                except ValueError:
                    user = await self._choose_random_member(
                        state["entity"],
                        state["chat_id"],
                        set(),
                    )
                    state["seen"] = set()
            except ValueError:
                await call.answer(
                    self._s("member_select_empty"),
                    show_alert=True,
                )
                return
            except Exception:
                logger.exception("Could not select next member")
                await call.answer(
                    self._s("member_select_failed"),
                    show_alert=True,
                )
                return
            last_messages, member_info = await asyncio.gather(
                self._random_latest_message(
                    state["entity"],
                    state["chat_id"],
                    user,
                ),
                self._fresh_member_info(state["entity"], user, None),
            )
            role, _, member_status, member_inline_blocked = member_info
            state.update(
                {
                    "user": user,
                    "display_name": self._random_display_name(user),
                    "activity": None,
                    "activity_months": None,
                    "last_messages": last_messages,
                    "banned": False,
                    "kicked": False,
                    "member_status": member_status,
                    "role": role,
                    "member_inline_blocked": member_inline_blocked,
                    "notice": None,
                    "notice_error": False,
                }
            )
            state["seen"].add(int(user.id))
            state["history"].append(self._random_member_snapshot(state))
            if len(state["history"]) > _MAX_HISTORY:
                state["history"].pop(0)
            state["history_index"] = len(state["history"]) - 1
            state["expires"] = time.monotonic() + _SESSION_TTL
            await self._render_random(call, token)

    async def _random_check_activity(self, call, token, months):
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            if months not in _ACTIVITY_PERIODS:
                await call.answer(self._s("unknown_period"), show_alert=True)
                return
            await call.answer(self._s("activity_counting", months=months))
            try:
                activity, last_messages = await self._random_activity(
                    state["entity"],
                    state["chat_id"],
                    state["user"],
                    months,
                )
            except Exception:
                logger.exception(
                    "Could not check selected member activity"
                )
                state["notice"] = (
                    self._s("activity_failed")
                )
                state["notice_error"] = True
                await self._render_random(call, token)
                return
            state["activity"] = activity
            state["activity_months"] = months
            if last_messages:
                state["last_messages"] = last_messages
            state["notice"] = None
            state["notice_error"] = False
            await self._render_random(call, token)

    async def _random_moderation_allowed(self, state):
        permissions = await self.client.get_permissions(
            state["entity"],
            state["user"],
        )
        if getattr(permissions, "is_creator", False):
            state["role"] = self._s("role_creator")
            return False
        if getattr(permissions, "is_admin", False):
            state["role"] = self._s("role_admin")
            return False
        state["role"] = self._s("role_member")
        return True

    async def _random_toggle_inline(self, call, token):
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            capabilities = await self._refresh_operator_capabilities(state)
            if not capabilities.get("ban_users"):
                await call.answer(
                    self._s("no_restriction_rights"),
                    show_alert=True,
                )
                await self._render_random(call, token)
                return
            if not isinstance(state["entity"], types.Channel):
                await call.answer(
                    self._s("personal_restrictions_supergroup"),
                    show_alert=True,
                )
                await self._render_random(call, token)
                return
            try:
                permissions = await self.client.get_permissions(
                    state["entity"],
                    state["user"],
                )
            except Exception:
                logger.exception("Could not refresh inline permissions")
                await call.answer(
                    self._s("member_rights_refresh_failed"),
                    show_alert=True,
                )
                return
            state["role"] = self._member_role(permissions)
            state["member_status"] = (
                "banned"
                if self._member_fully_banned(permissions)
                else (
                    "unbanned"
                    if getattr(permissions, "has_left", False)
                    else "member"
                )
            )
            state["member_inline_blocked"] = self._member_inline_blocked(
                permissions
            )
            state["chat_inline_blocked"] = await self._chat_inline_blocked(
                state["entity"]
            )
            if (
                state["member_status"] != "member"
                or state["role"] != self._s("role_member")
            ):
                await call.answer(
                    self._s("inline_member_only"),
                    show_alert=True,
                )
                await self._render_random(call, token)
                return
            if state["chat_inline_blocked"]:
                await call.answer(
                    self._s("inline_chat_forbidden"),
                    show_alert=True,
                )
                await self._render_random(call, token)
                return
            blocked = not state["member_inline_blocked"]
            try:
                await self._set_member_inline(
                    state["entity"],
                    state["user"],
                    permissions,
                    blocked,
                )
            except Exception:
                logger.exception("Could not change member inline permission")
                await call.answer(
                    self._s("inline_change_failed"),
                    show_alert=True,
                )
                return
            state["member_inline_blocked"] = blocked
            state["notice"] = (
                self._s("inline_forbidden_notice") if blocked else self._s("inline_allowed_notice")
            )
            state["notice_error"] = False
            state["expires"] = time.monotonic() + _SESSION_TTL
            await call.answer(
                self._s("inline_forbidden_notice") if blocked else self._s("inline_allowed_notice")
            )
            await self._render_random(call, token)

    async def _random_toggle_guest_bots(self, call, token):
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            capabilities = await self._refresh_operator_capabilities(state)
            if not capabilities.get("delete_messages"):
                await call.answer(
                    self._s("guest_delete_rights"),
                    show_alert=True,
                )
                await self._render_random(call, token)
                return
            blocked = not self._guest_bots_blocked_for_member(
                state["chat_id"],
                state["user"].id,
            )
            chat_id = str(int(state["chat_id"]))
            user_id = str(int(state["user"].id))
            users = self._guest_bot_member_blocks.get(chat_id)
            if not isinstance(users, dict):
                users = {}
                self._guest_bot_member_blocks[chat_id] = users
            if blocked:
                users[user_id] = True
            else:
                users.pop(user_id, None)
                if not users:
                    self._guest_bot_member_blocks.pop(chat_id, None)
            self._save_guest_bot_member_blocks()
            state["notice"] = self._s(
                "guest_forbidden" if blocked else "guest_allowed"
            )
            state["notice_error"] = False
            state["expires"] = time.monotonic() + _SESSION_TTL
            await call.answer(state["notice"])
            await self._render_random(call, token)

    async def _member_prefix_input(
        self,
        call,
        data,
        token,
        admin,
    ):
        call = self._input_source_form(call)
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            try:
                permissions = await self.client.get_permissions(
                    state["entity"],
                    state["user"],
                )
            except Exception:
                logger.exception("Could not refresh member permissions")
                state["notice"] = self._s("member_rights_update_failed")
                state["notice_error"] = True
                await self._render_random(call, token)
                return
            state["role"] = self._member_role(permissions)
            state["member_status"] = (
                "banned"
                if self._member_fully_banned(permissions)
                else (
                    "unbanned"
                    if getattr(permissions, "has_left", False)
                    else "member"
                )
            )
            await self._refresh_operator_capabilities(state)
            if not self._prefix_allowed(state, admin):
                state["notice"] = self._s("tag_rights_missing")
                state["notice_error"] = True
                await self._render_random(call, token)
                return
            rank = self._rank([data])
            if rank is None:
                state["notice"] = (
                    self._s("tag_input_error")
                )
                state["notice_error"] = True
                await self._render_random(call, token)
                return
            try:
                if not admin:
                    if getattr(permissions, "is_creator", False):
                        state["notice"] = (
                            self._s("creator_regular_tag")
                        )
                        state["notice_error"] = True
                        await self._render_random(call, token)
                        return
                    await self._set_rank(
                        state["entity"],
                        state["user"],
                        rank,
                    )
                    if getattr(permissions, "is_admin", False):
                        try:
                            await self.client.edit_admin(
                                state["entity"],
                                state["user"],
                                is_admin=False,
                            )
                        except Exception:
                            logger.exception(
                                "Could not demote member after rank change"
                            )
                            state["notice"] = (
                                self._s("tag_changed_demote_failed")
                            )
                            state["notice_error"] = True
                            await self._render_random(call, token)
                            return
                    state["role"] = self._s("role_member")
                else:
                    if isinstance(state["entity"], types.Chat):
                        state["notice"] = (
                            self._s("admin_tag_only_supergroup")
                        )
                        state["notice_error"] = True
                        await self._render_random(call, token)
                        return
                    if getattr(permissions, "is_creator", False):
                        await self._set_rank(
                            state["entity"],
                            state["user"],
                            rank,
                        )
                    elif getattr(permissions, "is_admin", False):
                        await self.client(
                            functions.channels.EditAdminRequest(
                                channel=state["entity"],
                                user_id=state["user"],
                                admin_rights=(
                                    permissions.participant.admin_rights
                                ),
                                rank=rank,
                            )
                        )
                    else:
                        await self.client(
                            functions.channels.EditAdminRequest(
                                channel=state["entity"],
                                user_id=state["user"],
                                admin_rights=types.ChatAdminRights(
                                    other=True
                                ),
                                rank=rank,
                            )
                        )
                    state["role"] = (
                        self._s("role_creator")
                        if getattr(permissions, "is_creator", False)
                        else self._s("role_admin")
                    )
            except Exception:
                logger.exception("Could not set member rank from menu")
                state["notice"] = (
                    self._s("tag_change_failed")
                )
                state["notice_error"] = True
                await self._render_random(call, token)
                return
            state["notice"] = (
                self._s("tag_changed", tag_type=self._s("tag_admin") if admin else self._s("tag"), rank=rank)
            )
            state["notice_error"] = False
            state["expires"] = time.monotonic() + _SESSION_TTL
            await self._render_random(call, token)

    def _drop_random_cached_member(self, chat_id, user_id):
        cache = self._member_cache.get(str(chat_id))
        if cache:
            cache["users"].pop(int(user_id), None)

    @loader.raw_handler(
        types.UpdateChannelParticipant,
        types.UpdateChatParticipant,
        types.UpdateChatParticipantAdd,
        types.UpdateChatParticipantDelete,
        types.UpdateChatParticipantAdmin,
    )
    async def _random_participant_changed(self, update):
        if isinstance(update, types.UpdateChannelParticipant):
            chat_id = int(f"-100{update.channel_id}")
        else:
            chat_id = -abs(int(update.chat_id))
        cache = self._member_cache.get(str(chat_id))
        if not cache:
            return
        user_id = int(update.user_id)
        participant = getattr(update, "new_participant", None)
        if isinstance(update, types.UpdateChatParticipantAdmin):
            if update.is_admin:
                cache["admins"].add(user_id)
                cache["users"].pop(user_id, None)
            else:
                cache["admins"].discard(user_id)
                cache["expires"] = 0
            return
        if isinstance(update, types.UpdateChatParticipantAdd):
            cache["expires"] = 0
            return
        if isinstance(
            participant,
            (
                types.ChannelParticipantAdmin,
                types.ChannelParticipantCreator,
                types.ChatParticipantAdmin,
                types.ChatParticipantCreator,
            ),
        ):
            cache["admins"].add(user_id)
            cache["users"].pop(user_id, None)
        elif participant is None or isinstance(
            participant,
            (
                types.ChannelParticipantBanned,
                types.ChannelParticipantLeft,
            ),
        ):
            cache["admins"].discard(user_id)
            cache["users"].pop(user_id, None)
        else:
            cache["admins"].discard(user_id)
            cache["expires"] = 0

    @loader.raw_handler(types.UpdateChannelParticipant)
    async def _panic_participant_joined(self, update):
        new = getattr(update, "new_participant", None)
        old = getattr(update, "prev_participant", None)
        absent = (types.ChannelParticipantLeft, types.ChannelParticipantBanned)
        if new is None or isinstance(new, absent) or (old is not None and not isinstance(old, absent)):
            return
        if int(update.user_id) == self._me_id:
            return
        chat_id = str(int(f"-100{update.channel_id}"))
        config = self._panic_config(chat_id)
        if not config["auto"] or not self._panic_has_actions(config) or self._chat_controls.get(chat_id, {}).get("panic_active"):
            return
        now = time.monotonic()
        joins = self._panic_joins.setdefault(chat_id, [])
        joins[:] = [stamp for stamp in joins if now - stamp <= config["window"]]
        joins.append(now)
        if len(joins) < config["joins"]:
            return
        joins.clear()
        async with self._chat_control_lock(chat_id):
            current_config = self._panic_config(chat_id)
            if self._chat_controls.get(chat_id, {}).get("panic_active") or not current_config["auto"] or not self._panic_has_actions(current_config):
                return
            try:
                entity = await self.client.get_entity(int(chat_id))
                if not isinstance(entity, types.Channel) or not getattr(entity, "megagroup", False):
                    return
                await self._enable_panic(entity, chat_id)
            except Exception:
                logger.exception("Could not automatically enable panic in %s", chat_id)

    async def _random_kick(self, call, token):
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            try:
                capabilities = await self._refresh_operator_capabilities(state)
                if not capabilities.get("ban_users"):
                    await call.answer(
                        self._s("member_kick_rights"),
                        show_alert=True,
                    )
                    await self._render_random(call, token)
                    return
                if not await self._random_moderation_allowed(state):
                    await call.answer(
                        self._s("member_admin"),
                        show_alert=True,
                    )
                    await self._render_random(call, token)
                    return
                await self.client.kick_participant(
                    state["entity"],
                    state["user"],
                )
                state["member_status"] = "kicked"
                state["banned"] = False
                state["kicked"] = True
                state["notice"] = None
                state["notice_error"] = False
                self._drop_random_cached_member(
                    state["chat_id"],
                    state["user"].id,
                )
                await call.answer(self._s("member_kicked"))
                await self._render_random(call, token)
            except Exception:
                logger.exception("Could not kick selected member")
                await call.answer(
                    self._s("member_kick_failed"),
                    show_alert=True,
                )

    async def _random_ban(self, call, token):
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            try:
                capabilities = await self._refresh_operator_capabilities(state)
                if not capabilities.get("ban_users"):
                    await call.answer(
                        self._s("member_ban_rights"),
                        show_alert=True,
                    )
                    await self._render_random(call, token)
                    return
                if (
                    state.get("member_status", "member") == "member"
                    and not await self._random_moderation_allowed(state)
                ):
                    await call.answer(
                        self._s("member_admin"),
                        show_alert=True,
                    )
                    await self._render_random(call, token)
                    return
                await self.client.edit_permissions(
                    state["entity"],
                    state["user"],
                    view_messages=False,
                )
                state["member_status"] = "banned"
                state["banned"] = True
                state["kicked"] = False
                state["notice"] = None
                state["notice_error"] = False
                self._drop_random_cached_member(
                    state["chat_id"],
                    state["user"].id,
                )
                await call.answer(self._s("member_banned"))
                await self._render_random(call, token)
            except Exception:
                logger.exception("Could not ban selected member")
                await call.answer(
                    self._s("member_ban_failed"),
                    show_alert=True,
                )

    async def _random_unban(self, call, token):
        state = await self._random_state(call, token)
        if not state:
            return
        async with self._random_action(call, state) as ready:
            if not ready:
                return
            try:
                capabilities = await self._refresh_operator_capabilities(state)
                if not capabilities.get("ban_users"):
                    await call.answer(
                        self._s("member_unban_rights"),
                        show_alert=True,
                    )
                    await self._render_random(call, token)
                    return
                await self.client.edit_permissions(
                    state["entity"],
                    state["user"],
                    None,
                )
                state["member_status"] = "unbanned"
                state["banned"] = False
                state["kicked"] = False
                state["notice"] = None
                state["notice_error"] = False
                await call.answer(self._s("member_unbanned"))
                await self._render_random(call, token)
            except Exception:
                logger.exception("Could not unban selected member")
                await call.answer(
                    self._s("member_unban_failed"),
                    show_alert=True,
                )

    @loader.command(ru_doc=" - действия со случайным участником", en_doc=' - actions with a random member')
    @loader.group_admin
    async def rmember(self, message: Message):
        if getattr(message, "is_private", False):
            await self._inline_answer(
                message,
                (
                    f"{_RANDOM_EMOJI['ban']} "
                    f"<b>{self._s('groups_only')}</b>"
                ),
            )
            return
        self._prune_random_runtime()
        try:
            entity = await self.client.get_entity(message.chat_id)
            state = await self._make_random_state(
                entity,
                message.chat_id,
                set(),
                utils.get_topic(message),
            )
        except ValueError:
            await self._inline_answer(
                message,
                (
                    f"{_RANDOM_EMOJI['ban']} "
                    f"<b>{self._s('member_select_empty')}</b>"
                ),
            )
            return
        except Exception:
            logger.exception("Could not create random-member card")
            await self._inline_answer(
                message,
                (
                    f"{_RANDOM_EMOJI['ban']} "
                    f"<b>{self._s('member_select_failed')}</b>"
                ),
            )
            return
        token = secrets.token_urlsafe(12)
        self._sessions[token] = state
        sent = await self.inline.form(
            self._random_card(state),
            message,
            reply_markup=self._random_markup(token, state),
            ttl=_SESSION_TTL,
        )
        if not sent:
            self._sessions.pop(token, None)
            await self._inline_answer(
                message,
                (
                    f"{_RANDOM_EMOJI['ban']} "
                    f"<b>{self._s('menu_open_failed')}</b>"
                ),
            )

    strings.update({
        "id_title": "ID", "id_chat": "Current chat", "id_sender": "Replied message sender",
        "id_plain": "Plain", "id_marked": "With prefix",
        "id_failed": "Could not identify the requested user/chat or replied message sender.",
        "id_target": "Specified user/chat", "id_usage": "Use one <code>@username</code>, or run without arguments in a chat or as a reply.",
    })
    strings_ru.update({
        "id_title": "ID", "id_chat": "Текущий чат", "id_sender": "Отправитель сообщения из реплая",
        "id_plain": "Обычный", "id_marked": "С префиксом",
        "id_failed": "Не удалось определить ID указанного пользователя/чата или отправителя сообщения из реплая.",
        "id_target": "Указанный пользователь/чат", "id_usage": "Укажи один <code>@username</code> или вызови команду без аргументов в чате либо реплаем.",
    })

    @loader.command(ru_doc=" [@username] - ID пользователя/бота/чата", en_doc=' [@username] - user/bot/chat ID; otherwise replied sender or current chat')
    async def id(self, message: Message):
        args = self._args(message)
        if len(args) > 1 or (args and not re.fullmatch(r"@[A-Za-z0-9_]+", args[0])):
            await self._answer_temporary(
                message, f"{_EMOJI['error']} <b>{self._s('id_usage')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        try:
            reply = None if args else await self._get_reply_message(message)
            if not args and reply is None and (getattr(message, "is_reply", False) or getattr(message, "reply_to_msg_id", None)):
                raise ValueError("reply_unavailable")
            if args:
                peer = await self.client.get_entity(args[0])
            elif reply is not None:
                peer = getattr(reply, "from_id", None) or getattr(reply, "sender_id", None)
                if peer is None and getattr(reply, "post", False):
                    peer = getattr(reply, "peer_id", None)
                if peer is None:
                    peer = await reply.get_sender()
            else:
                peer = getattr(message, "peer_id", None) or getattr(message, "chat_id", None)
            if peer is None:
                raise ValueError("peer_unavailable")
            marked = tl_utils.get_peer_id(peer)
            plain, _ = tl_utils.resolve_id(marked)
        except Exception:
            logger.debug("Could not resolve ID command target", exc_info=True)
            await self._answer_temporary(
                message, f"{_EMOJI['error']} <b>{self._s('id_failed')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        text = (
            f"<b>GodChat · {self._s('id_title')}</b>\n"
            f"{self._s('id_target' if args else 'id_sender' if reply is not None else 'id_chat')}\n\n"
            f"{self._s('id_plain')}: <code>{plain}</code>"
        )
        if marked != plain:
            text += f"\n{self._s('id_marked')}: <code>{marked}</code>"
        await self._inline_answer(message, text)

    @loader.command(
        ru_doc=" [пользователь] - карточка пользователя"
    , en_doc=' [user] - member card')
    @loader.group_admin
    async def member(self, message: Message):
        context = await self._context(message, allow_self=True)
        if not context:
            return
        entity, target, permissions, args = context
        if args:
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('reply_or_one_user')}</b>"
                ),
            )
            return
        try:
            state = await self._make_member_state(
                entity,
                message.chat_id,
                target,
                permissions,
                utils.get_topic(message),
            )
        except Exception:
            logger.exception("Could not create member card")
            await self._inline_answer(
                message,
                (
                    f"{_RANDOM_EMOJI['ban']} "
                    f"<b>{self._s('member_card_open_failed')}</b>"
                ),
            )
            return
        token = secrets.token_urlsafe(12)
        self._sessions[token] = state
        sent = await self.inline.form(
            self._random_card(state),
            message,
            reply_markup=self._member_markup(token, state),
            ttl=_SESSION_TTL,
        )
        if not sent:
            self._sessions.pop(token, None)
            await self._inline_answer(
                message,
                (
                    f"{_RANDOM_EMOJI['ban']} "
                    f"<b>{self._s('menu_open_failed')}</b>"
                ),
            )

    async def _delete_participant_history(self, entity, target):
        previous_offset = None
        while True:
            result = await self.client(
                functions.channels.DeleteParticipantHistoryRequest(
                    channel=entity,
                    participant=target,
                )
            )
            offset = int(getattr(result, "offset", 0) or 0)
            if not offset:
                return
            if previous_offset is not None and offset >= previous_offset:
                raise RuntimeError("Participant history offset did not decrease")
            previous_offset = offset

    async def _delete_recent_messages(
        self,
        entity,
        target,
        limit=None,
        exclude_id=None,
        topic_id=None,
    ):
        batch = []
        deleted = 0
        kwargs = {
            "limit": limit + 1 if limit is not None else None,
            "from_user": target,
        }
        if topic_id is not None:
            kwargs["reply_to"] = topic_id
        async for item in self.client.iter_messages(
            entity,
            **kwargs,
        ):
            if item.id == exclude_id:
                continue
            batch.append(item.id)
            if limit is not None and deleted + len(batch) >= limit:
                break
            if len(batch) == 100:
                await self.client.delete_messages(entity, batch)
                deleted += len(batch)
                batch.clear()
        if batch:
            await self.client.delete_messages(entity, batch)
            deleted += len(batch)
        return deleted

    @loader.command(ru_doc=" - удалить сообщения до реплая", en_doc=' - delete messages up to the replied one')
    @loader.group_admin_delete_messages
    async def purge(self, message: Message):
        entity = await self._chat_command_entity(message)
        if not entity:
            return
        reply = await self._get_reply_message(message)
        if not reply:
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('purge_reply')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        topic_id = utils.get_topic(message)
        if utils.get_topic(reply) != topic_id:
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('other_topic')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        if reply.id > message.id:
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('invalid_range')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        capabilities = await self._operator_capabilities(entity)
        if not capabilities.get("delete_messages"):
            await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('delete_rights_missing')}</b>",
            )
            return
        kwargs = {
            "min_id": reply.id - 1,
            "max_id": message.id + 1,
        }
        if topic_id is not None:
            kwargs["reply_to"] = topic_id
        try:
            ids = {
                item.id
                async for item in self.client.iter_messages(entity, **kwargs)
            }
            ids.add(reply.id)
            ids.discard(message.id)
            ordered = sorted(ids)
            for index in range(0, len(ordered), 100):
                await self.client.delete_messages(
                    entity,
                    ordered[index : index + 100],
                )
            await message.delete()
        except Exception:
            logger.exception("Could not purge messages")
            await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('messages_delete_failed')}</b>",
            )
            return

    @loader.command(
        ru_doc=" [пользователь] [n|-all] - удаление сообщений, без аргументов удаляет реплай"
    , en_doc=' [user] [n|-all] - delete messages; without arguments deletes the reply')
    @loader.group_admin_delete_messages
    async def delcmd(self, message: Message):
        args = self._args(message)
        reply = await self._get_reply_message(message)
        if not args:
            if not reply:
                await self._answer_temporary(
                    message,
                    (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('reply_or_user_and_amount')}</b>"
                    ),
                    _IMPORTANT_RESULT_TTL,
                )
                return
            try:
                await self.client.delete_messages(
                    message.chat_id,
                    [reply.id, message.id],
                )
            except Exception:
                logger.exception("Could not delete replied message")
                await self._inline_answer(
                    message,
                    (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('message_delete_failed')}</b>"
                    ),
                )
            return
        context = await self._context(
            message,
            allow_self=True,
            target_options={"-all"},
        )
        if not context:
            return
        entity, target, _, args = context
        topic_id = utils.get_topic(message)
        if len(args) != 1:
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('amount_or_all')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        mode = args[0].lower()
        if mode != "-all" and (
            not mode.isdigit() or int(mode) <= 0
        ):
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('positive_amount')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        try:
            if (
                mode == "-all"
                and topic_id is None
                and not isinstance(entity, types.Chat)
                and int(target.id) != self._me_id
            ):
                await self._delete_participant_history(entity, target)
                deleted = self._s("all_messages")
            else:
                count = None if mode == "-all" else int(mode)
                amount = await self._delete_recent_messages(
                    entity,
                    target,
                    count,
                    message.id,
                    topic_id,
                )
                deleted = (
                    f"{amount} "
                    f"{self._message_count(amount)}"
                )
        except Exception:
            logger.exception("Could not delete participant messages")
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('messages_delete_permissions_failed')}</b>"
                ),
            )
            return
        await self._delete_command_message(message)





    async def _ban_target(
        self,
        entity,
        target,
        duration,
        delete_history=False,
    ):
        if isinstance(entity, types.Chat):
            if delete_history:
                await self.client(
                    functions.messages.DeleteChatUserRequest(
                        chat_id=entity.id,
                        user_id=target,
                        revoke_history=True,
                    )
                )
            else:
                await self.client.kick_participant(entity, target)
            return self._s("removed_from_basic_group"), (
                True if delete_history else None
            )
        await self.client.edit_permissions(
            entity,
            target,
            (
                timedelta(seconds=duration)
                if duration is not None
                else None
            ),
            view_messages=False,
        )
        history_deleted = None
        if delete_history:
            try:
                await self._delete_participant_history(entity, target)
                history_deleted = True
            except Exception:
                logger.exception("Could not delete participant history")
                history_deleted = False
        return self._s("banned_action"), history_deleted

    def _gban_report(self, target, counts, chats, show_chats, undo=False, running=False,
                     stopped=False, reason=""):
        icon = _EMOJI["success" if undo else "ban"]
        title = self._s("gunban_title" if undo else "gban_title")
        if running:
            title = self._s("gunban_work" if undo else "gban_work")
        username = self._username(target)
        profile = (f"https://t.me/{username}"
                   if username and re.fullmatch(r"[A-Za-z0-9_]{1,32}", username)
                   else f"tg://user?id={int(target.id)}")
        name = utils.escape_html(self._name(target))
        label = (f'<a href="{profile}"><b>{name}</b></a> '
                 f'(<code>{int(target.id)}</code>)')
        text = f"{icon} <b>GodChat · {title}</b>\n{label}"
        if reason and not undo:
            text += self._reason_block(reason)
        if not running:
            total = counts["changed"] + (0 if undo else counts["removed"])
            text += (f"\n\n{self._s('gunban_changed' if undo else 'gban_changed')}: "
                     f"<b>{total}</b>")
        if stopped:
            text += "\n" + self._s("gban_flood_stopped")
        if show_chats and chats:
            items = []
            for entity in chats:
                name = utils.escape_html(str(getattr(entity, "title", None) or entity.id)[:100])
                username = self._username(entity)
                if username and re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
                    name = f'<a href="https://t.me/{username}">{name}</a>'
                line = "▫️ " + name
                if len(text) + sum(map(len, items)) + len(line) > 3400:
                    break
                items.append(line)
            hidden = len(chats) - len(items)
            if hidden:
                items.append(self._s("gban_more", count=hidden))
            text += "\n\n<blockquote expandable>" + "\n".join(items) + "</blockquote>"
        return text

    async def _gban_member_state(self, entity, target):
        if isinstance(entity, types.Chat):
            try:
                permissions = await self.client.get_permissions(entity, target)
            except Exception as error:
                if type(error).__name__ == "UserNotParticipantError":
                    return None
                raise
            return permissions
        try:
            result = await self.client(functions.channels.GetParticipantRequest(
                channel=entity, participant=target), flood_sleep_threshold=0)
        except Exception as error:
            if type(error).__name__ == "UserNotParticipantError":
                return None
            raise
        return result.participant

    @staticmethod
    def _gban_member_flags(member):
        if member is None:
            return False, False
        admin = bool(getattr(member, "is_creator", False)
                     or getattr(member, "is_admin", False)
                     or isinstance(member, (types.ChannelParticipantCreator,
                                            types.ChannelParticipantAdmin)))
        participant = getattr(member, "participant", member)
        banned = bool(getattr(getattr(participant, "banned_rights", None),
                              "view_messages", False))
        return admin, banned

    async def _gban_change(self, entity, target, undo):
        for attempt in range(2):
            try:
                if undo:
                    await self.client.edit_permissions(entity, target, None)
                else:
                    await self._ban_target(entity, target, None)
                return
            except FloodWaitError as error:
                if attempt or int(getattr(error, "seconds", 0) or 0) > 30:
                    raise
                await asyncio.sleep(max(1, int(error.seconds)) + 1)

    async def _gban_process(self, entity, target, undo):
        member = await self._gban_member_state(entity, target)
        admin, banned = self._gban_member_flags(member)
        if (admin or (undo and not banned) or (not undo and banned)
                or (isinstance(entity, types.Chat) and member is None)):
            return "skipped"
        await self._gban_change(entity, target, undo)
        return "removed" if isinstance(entity, types.Chat) else "changed"

    async def _gban_run(self, message, undo=False):
        args = self._args(message)
        if args.count("-f") > 1:
            return await self._answer_temporary(
                message, self._s("gban_usage"), _IMPORTANT_RESULT_TTL)
        show_chats = "-f" in args
        try:
            target, remaining = await self._resolve_target(message, {"-f"})
        except Exception:
            target = None
            remaining = []
        if target is None:
            return await self._answer_temporary(
                message, self._s("gban_usage"), _IMPORTANT_RESULT_TTL)
        if int(target.id) == self._me_id:
            return await self._answer_temporary(
                message, self._s("self_action"), _IMPORTANT_RESULT_TTL)
        remaining = [arg for arg in remaining if arg != "-f"]
        if (undo and remaining) or any(arg.startswith("-") for arg in remaining):
            return await self._answer_temporary(
                message, self._s("gban_usage"), _IMPORTANT_RESULT_TTL)
        reason = self._reason(remaining)
        if self._gban_lock.locked():
            return await self._answer_temporary(
                message, self._s("gban_busy"), _IMPORTANT_RESULT_TTL)
        counts = {"changed": 0, "removed": 0, "skipped": 0, "errors": 0}
        chats = []
        async with self._gban_lock:
            status = await utils.answer(
                message, self._gban_report(target, counts, chats, False,
                                           undo=undo, running=True, reason=reason))
            eligible = []
            stopped = False
            try:
                async for dialog in self.client.iter_dialogs():
                    entity = getattr(dialog, "entity", None)
                    if not isinstance(entity, (types.Channel, types.Chat)):
                        continue
                    rights = getattr(entity, "admin_rights", None)
                    if not (getattr(entity, "creator", False)
                            or getattr(rights, "ban_users", False)):
                        counts["skipped"] += 1
                    elif undo and isinstance(entity, types.Chat):
                        counts["skipped"] += 1
                    else:
                        eligible.append(entity)
            except asyncio.CancelledError:
                raise
            except FloodWaitError:
                counts["errors"] += 1
                stopped = True
                logger.warning("GodChat global ban stopped while listing dialogs", exc_info=True)
            except Exception:
                counts["errors"] += 1
                logger.warning("GodChat global ban could not list dialogs", exc_info=True)
            if not stopped:
                for offset in range(0, len(eligible), 5):
                    batch = eligible[offset:offset + 5]
                    results = await asyncio.gather(
                        *(self._gban_process(entity, target, undo)
                          for entity in batch), return_exceptions=True)
                    for entity, result in zip(batch, results):
                        if isinstance(result, asyncio.CancelledError):
                            raise result
                        if isinstance(result, FloodWaitError):
                            counts["errors"] += 1
                            stopped = True
                            logger.warning("GodChat global ban stopped by Telegram flood wait",
                                           exc_info=(type(result), result, result.__traceback__))
                        elif isinstance(result, Exception):
                            counts["errors"] += 1
                            logger.warning("GodChat global ban failed in chat %s",
                                           getattr(entity, "id", None),
                                           exc_info=(type(result), result, result.__traceback__))
                        else:
                            counts[result] += 1
                            if result != "skipped":
                                chats.append(entity)
                    if stopped:
                        break
            await utils.answer(
                status or message, self._gban_report(target, counts, chats, show_chats,
                                                      undo=undo, stopped=stopped,
                                                      reason=reason))

    @loader.command(ru_doc=" [пользователь] [причина] [-f] - забанить во всех доступных чатах; -f: список чатов", en_doc=' [user] [reason] [-f] - ban in all accessible chats; -f: chat list')
    @loader.owner
    async def gban(self, message: Message):
        await self._gban_run(message)

    @loader.command(ru_doc=" [пользователь] [-f] - разбанить во всех доступных чатах; -f: список чатов", en_doc=' [user] [-f] - unban in all accessible chats; -f: chat list')
    @loader.owner
    async def gunban(self, message: Message):
        await self._gban_run(message, undo=True)

    strings.update({
        "gban_usage": "Reply to a user or specify @username/ID. Use -f to show the chat list.",
        "gban_busy": "A global ban or unban is already running.",
        "gban_title": "Global ban", "gunban_title": "Global unban",
        "gban_work": "Banning across chats...", "gunban_work": "Unbanning across chats...",
        "gban_changed": "Banned in chats and channels",
        "gunban_changed": "Unbanned in chats and channels",
        "gban_more": "...and {count} more",
        "gban_flood_stopped": "Stopped because Telegram requested a longer pause.",
    })
    strings_ru.update({
        "gban_usage": "Ответь на пользователя или укажи @username/ID. Флаг -f покажет список чатов.",
        "gban_busy": "Глобальный бан или разбан уже выполняется.",
        "gban_title": "Глобальный бан", "gunban_title": "Глобальный разбан",
        "gban_work": "Баню в чатах...", "gunban_work": "Разбаниваю в чатах...",
        "gban_changed": "Забанено в чатах и каналах",
        "gunban_changed": "Разбанено в чатах и каналах",
        "gban_more": "…и ещё {count}",
        "gban_flood_stopped": "Остановлено: Telegram запросил долгую паузу.",
    })

    async def _admin_ban(
        self,
        call,
        entity,
        target,
        duration,
        duration_label,
        reason,
        delete_history,
    ):
        await call.answer(self._s("working"))
        demoted = False
        try:
            permissions = await self.client.get_permissions(entity, target)
            if getattr(permissions, "is_creator", False):
                await call.edit(
                    (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('creator_ban_forbidden')}</b>"
                    ),
                    reply_markup={
                        "text": self._s("close_button"),
                        "action": "close",
                        "style": "danger",
                    },
                )
                self._schedule_temporary_delete(call, _IMPORTANT_RESULT_TTL)
                return
            if getattr(permissions, "is_admin", False):
                await self.client.edit_admin(entity, target, is_admin=False)
                demoted = True
            action, history_deleted = await self._ban_target(
                entity,
                target,
                duration,
                delete_history,
            )
        except Exception:
            logger.exception("Could not demote and ban administrator")
            text = (
                f"{_EMOJI['error']} "
                f"<b>{self._s('demoted_ban_failed')}</b>"
                if demoted
                else (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('demote_ban_failed')}</b>"
                )
            )
            await call.edit(
                text,
                reply_markup={
                    "text": self._s("close_button"),
                    "action": "close",
                    "style": "danger",
                },
            )
            self._schedule_temporary_delete(call, _IMPORTANT_RESULT_TTL)
            return
        await call.edit(
            self._result(
                _EMOJI["ban"],
                self._s("ban_title"),
                target,
                action,
                duration_label,
                reason,
                history_deleted,
            ),
            reply_markup={
                "text": self._s("close_button"),
                "action": "close",
                "style": "danger",
            },
        )

    @loader.command(
        ru_doc=(
            " [пользователь] [время] [-d] [причина] - бан; "
            "[-d] - удалить все сообщения"
        )
    , en_doc=' [user] [time] [-d] [reason] - ban; [-d] - delete all messages')
    @loader.group_admin_ban_users
    async def ban(self, message: Message):
        context = await self._context(
            message,
            target_options={"-d"},
            error_ttl=_IMPORTANT_RESULT_TTL,
        )
        if not context:
            return
        entity, target, permissions, args = context
        delete_history = any(arg.lower() == "-d" for arg in args)
        args = [arg for arg in args if arg.lower() != "-d"]
        try:
            duration, duration_label, consumed = self._duration(args)
        except ValueError:
            await self._answer_temporary(
                message,
                self._duration_error(),
                _IMPORTANT_RESULT_TTL,
            )
            return
        reason = self._reason(args[consumed:])
        if getattr(permissions, "is_creator", False):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('creator_ban_forbidden')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        if getattr(permissions, "is_admin", False):
            sent = await self.inline.form(
                (
                    f"{_EMOJI['warning']} "
                    f"<b>GodChat · {self._s('confirmation')}</b>\n\n"
                    f"<blockquote>{self._label(target)}\n"
                    f"<b>{self._s('administrator')}:</b> {self._s('admin_will_be_demoted')}"
                    f"{self._duration_block(duration_label)}"
                    f"{self._reason_block(reason)}"
                    + (
                        f"\n<b>{self._s('messages')}:</b> {self._s('will_be_deleted')}"
                        if delete_history
                        else ""
                    )
                    + "</blockquote>"
                ),
                message,
                reply_markup=[
                    [
                        {
                            "text": self._s("demote_and_ban_button"),
                            "callback": self._admin_ban,
                            "args": (
                                entity,
                                target,
                                duration,
                                duration_label,
                                reason,
                                delete_history,
                            ),
                            "style": "danger",
                        }
                    ],
                    [
                        {
                            "text": self._s("cancel_button"),
                            "action": "close",
                        }
                    ],
                ],
                ttl=5 * 60,
            )
            if not sent:
                await self._answer_temporary(
                    message,
                    (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('confirmation_open_failed')}</b>"
                    ),
                    _IMPORTANT_RESULT_TTL,
                )
            return
        try:
            action, history_deleted = await self._ban_target(
                entity,
                target,
                duration,
                delete_history,
            )
        except Exception:
            logger.exception("Could not ban member")
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('ban_failed')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        await self._inline_answer(
            message,
            self._result(
                _EMOJI["ban"],
                self._s("ban_title"),
                target,
                action,
                duration_label,
                reason,
                history_deleted,
            ),
        )

    @loader.command(ru_doc=" [пользователь] [-all] - разбан; [-all] - разбан всех", en_doc=' [user] [-all] - unban; [-all] - unban all')
    @loader.group_admin_ban_users
    async def unban(self, message: Message):
        args = utils.get_args_raw(message).split()
        if '-all' in args:
            if args != ['-all']:
                return await self._answer_temporary(message, self._s('amn_only'), _IMPORTANT_RESULT_TTL)
            if not getattr(message, 'out', False) and getattr(message, 'sender_id', None) != self._me_id:
                return await self._answer_temporary(message, self._s('amn_owner_only'), _IMPORTANT_RESULT_TTL)
            return await self._amn_start(message)
        context = await self._context(message, error_ttl=_IMPORTANT_RESULT_TTL)
        if not context:
            return
        entity, target, _, _ = context
        if isinstance(entity, types.Chat):
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('basic_group_no_bans')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        try:
            await self.client.edit_permissions(entity, target, None)
        except Exception:
            logger.exception("Could not unban member")
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('unban_failed')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        await self._inline_answer(
            message,
            self._result(
                _EMOJI["success"],
                self._s("unban_title"),
                target,
                self._s("unbanned_action"),
                None,
                "",
            ),
        )

    strings.update({
        "amn_title": "Unban all", "amn_only": "Use unban -all without other arguments in a supergroup or channel.", "amn_owner_only": "Bulk unban is available only to the userbot account.",
        "amn_busy": "An unban operation is already pending or running in this chat.",
        "amn_confirm": "Unban {count} blocked peers? They will not be added back.",
        "amn_start": "Unban", "amn_stop": "Stop", "amn_running": "Unbanning: {done}/{total}",
        "amn_result": "{status}\nUnbanned: {done} · Skipped (state changed): {skipped} · Not processed: {remaining}",
        "amn_done": "Completed", "amn_stopped": "Stopped", "amn_empty": "No banned peers found.",
        "amn_failed": "Operation stopped: {code}. See logs (amn op={op}).",
    })
    strings_ru.update({
        "amn_title": "Разбан всех", "amn_only": "Вызови unban -all без других аргументов в супергруппе или канале.", "amn_owner_only": "Массовый разбан доступен только самому аккаунту юзербота.",
        "amn_busy": "В этом чате уже ожидается подтверждение или выполняется разбан.",
        "amn_confirm": "Разбанить заблокированных: {count}? Обратно в чат они не добавятся.",
        "amn_start": "Разбанить", "amn_stop": "Остановить", "amn_running": "Разбан: {done}/{total}",
        "amn_result": "{status}\nРазбанено: {done} · Пропущено (статус изменён): {skipped} · Не обработано: {remaining}",
        "amn_done": "Завершено", "amn_stopped": "Остановлено", "amn_empty": "Заблокированных нет.",
        "amn_failed": "Операция остановлена: {code}. Подробности в логах (amn op={op}).",
    })

    async def _amn_snapshot(self, entity):
        result = {}; offset = 0
        while True:
            page = await self.client(functions.channels.GetParticipantsRequest(
                channel=entity, filter=types.ChannelParticipantsKicked(q=""),
                offset=offset, limit=200, hash=0), flood_sleep_threshold=0)
            participants = page.participants
            if not participants:
                break
            added = 0
            for participant in participants:
                if not getattr(getattr(participant, "banned_rights", None), "view_messages", False):
                    continue
                peer = participant.peer
                key = tl_utils.get_peer_id(peer)
                if key not in result:
                    target = await self.client.get_input_entity(peer)
                    result[key] = (target, getattr(participant, "date", None))
                    added += 1
            offset += len(participants)
            if len(result) > 10000:
                raise ValueError("amn_snapshot_limit_10000")
            if not added:
                raise ValueError("amn_list_changed_retry")
        return list(result.values())

    async def _amn_start(self, message: Message):
        token = secrets.token_urlsafe(12)
        task = asyncio.current_task()
        self._amn_tasks.add(task)
        try:
            if utils.get_args_raw(message).split() != ['-all']:
                raise ValueError("amn_only")
            entity = await self.client.get_entity(message.chat_id)
            if not isinstance(entity, types.Channel):
                raise ValueError("amn_only")
            if not (await self._operator_capabilities(entity)).get("ban_users"):
                raise ValueError("member_kick_rights")
            now = time.monotonic()
            self._amn_jobs = {k:v for k,v in self._amn_jobs.items() if v.get("running") or v["expires"] > now}
            if any(j["entity"].id == entity.id for j in self._amn_jobs.values()):
                raise ValueError("amn_busy")
            if len(self._amn_jobs) >= 20:
                raise ValueError("amn_pending_limit")
            job = dict(entity=entity, expires=now+300, running=True, stop=False)
            self._amn_jobs[token] = job
            job["users"] = await asyncio.wait_for(self._amn_snapshot(entity), 120)
            job["running"] = False
            job["expires"] = time.monotonic()+300
            if not job["users"]:
                self._amn_jobs.pop(token, None)
                return await self._inline_answer(message, _EMOJI['success']+' '+self._s('amn_empty'))
            text = (_EMOJI['warning']+' <b>GodChat · '+self._s('amn_title')+'</b>\n\n<blockquote>'
                    +utils.escape_html(entity.title)+' · <code>'+str(message.chat_id)+'</code>\n'
                    +self._s('amn_confirm', count=len(job['users']))+'</blockquote>')
            sent = await self.inline.form(text, message, force_me=True, reply_markup=[[
                {"text":self._s('amn_start'),"callback":self._amn_confirm,"args":(token,),"style":"danger"},
                {"text":self._s('cancel_button'),"callback":self._amn_stop,"args":(token,),"style":"danger"}]])
            if not sent:
                raise ValueError("confirmation_open_failed")
        except asyncio.CancelledError:
            self._amn_jobs.pop(token, None)
            raise
        except Exception as error:
            self._amn_jobs.pop(token, None)
            code = str(error) if isinstance(error, ValueError) else type(error).__name__
            logger.exception("amn op=%s stage=prepare code=%s", token, code)
            text = self._s(code) if code in ('amn_only','amn_busy','member_kick_rights','confirmation_open_failed') else self._s('amn_failed',code=utils.escape_html(code),op=token)
            await self._answer_temporary(message, _EMOJI['error']+' '+text, _IMPORTANT_RESULT_TTL)
        finally:
            self._amn_tasks.discard(task)

    async def _amn_stop(self, call, token):
        if getattr(getattr(call, "from_user", None), "id", None) != self._me_id:
            return
        job = self._amn_jobs.get(token)
        if not job:
            return await call.answer(self._s('confirmation_expired'), show_alert=True)
        job['stop'] = True
        await call.answer(self._s('amn_stopped'))
        if not job['running']:
            self._amn_jobs.pop(token, None)
            await call.delete()

    async def _amn_confirm(self, call, token):
        if getattr(getattr(call, "from_user", None), "id", None) != self._me_id:
            return
        job = self._amn_jobs.get(token)
        if not job or job['expires'] < time.monotonic():
            return await call.answer(self._s('confirmation_expired'), show_alert=True)
        if job['running']:
            return await call.answer(self._s('amn_busy'), show_alert=True)
        job['running'] = True
        task = asyncio.current_task(); self._amn_tasks.add(task)
        done = skipped = 0; error_text = ''; stage = 'rights'; target = None
        try:
            await call.answer()
            if not (await self._operator_capabilities(job['entity'])).get('ban_users'):
                raise ValueError('ban_rights_lost')
            for target, ban_date in job['users']:
                if job['stop']:
                    break
                if (done+skipped) % 10 == 0:
                    await call.edit(self._s('amn_running',done=done,total=len(job['users'])), reply_markup=[[
                        {'text':self._s('amn_stop'),'callback':self._amn_stop,'args':(token,), 'style':'danger'}]])
                stage = 'recheck'
                current = await self.client(functions.channels.GetParticipantRequest(
                    channel=job['entity'], participant=target), flood_sleep_threshold=0)
                participant = current.participant
                if (not getattr(getattr(participant,'banned_rights',None),'view_messages',False)
                        or getattr(participant,'date',None) != ban_date):
                    skipped += 1
                    continue
                if job['stop']:
                    break
                stage = 'unban'
                await self.client(functions.channels.EditBannedRequest(channel=job['entity'],
                    participant=target, banned_rights=types.ChatBannedRights(until_date=None)), flood_sleep_threshold=0)
                done += 1
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            job['stop'] = True
            raise
        except Exception as error:
            code = type(error).__name__
            if isinstance(error, FloodWaitError):
                code += f' ({error.seconds}s)'
            logger.exception('amn op=%s stage=%s target=%s completed=%s',token,stage,tl_utils.get_peer_id(target) if target else None,done)
            error_text = self._s('amn_failed',code=utils.escape_html(code),op=token)
        finally:
            self._amn_jobs.pop(token, None); self._amn_tasks.discard(task)
            text = self._s('amn_result',status=self._s('amn_stopped' if job['stop'] or error_text else 'amn_done'),
                done=done,skipped=skipped,remaining=len(job['users'])-done-skipped)
            try:
                await call.edit(_EMOJI['success' if not error_text else 'warning']+' <b>'+text+'</b>',reply_markup=None)
                if error_text:
                    report = await self.client.send_message(job['entity'],_EMOJI['error']+' '+error_text)
                    self._schedule_temporary_delete(report,_IMPORTANT_RESULT_TTL)
            except Exception:
                logger.exception('amn op=%s stage=report completed=%s',token,done)

    async def _deleted_chat_members(self, entity):
        admin_ids = await self._random_admin_ids(entity)
        if self._me_id:
            admin_ids.add(int(self._me_id))
        result = []
        async for user in self.client.iter_participants(entity):
            if (
                not isinstance(user, types.User)
                or int(user.id) in admin_ids
                or getattr(user, "bot", False)
                or not getattr(user, "deleted", False)
            ):
                continue
            result.append(user)
        return result

    def _prune_bulk_kick_jobs(self):
        now = time.monotonic()
        self._bulk_kick_jobs = {
            token: job
            for token, job in self._bulk_kick_jobs.items()
            if job.get("expires", 0) > now
        }
        while len(self._bulk_kick_jobs) >= _MAX_BULK_KICK_JOBS:
            self._bulk_kick_jobs.pop(next(iter(self._bulk_kick_jobs)))

    def _schedule_bulk_kick_cleanup(self, call):
        async def cleanup():
            try:
                await asyncio.sleep(_IMPORTANT_RESULT_TTL)
                await call.delete()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.debug("Could not delete bulk kick result", exc_info=True)
            finally:
                current = asyncio.current_task()
                if current:
                    self._bulk_kick_tasks.discard(current)

        task = asyncio.create_task(cleanup())
        self._bulk_kick_tasks.add(task)

    async def _confirm_kick_deleted(self, call, token):
        job = self._bulk_kick_jobs.pop(token, None)
        if not job or job.get("expires", 0) < time.monotonic():
            await call.answer(self._s("confirmation_expired"), show_alert=True)
            return
        capabilities = await self._operator_capabilities(job["entity"])
        if not capabilities.get("ban_users"):
            await call.answer(
                self._s("member_kick_rights"),
                show_alert=True,
            )
            return
        await call.answer(self._s("removing_deleted_accounts"))
        try:
            current_admin_ids = await self._random_admin_ids(job["entity"])
        except Exception:
            logger.exception("Could not refresh admin list for bulk kick")
            await call.edit(
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('admin_list_refresh_failed')}</b>"
                ),
                reply_markup=None,
            )
            self._schedule_bulk_kick_cleanup(call)
            return
        if self._me_id:
            current_admin_ids.add(int(self._me_id))
        kicked = 0
        for user in job["users"]:
            if int(user.id) in current_admin_ids:
                continue
            try:
                await self.client.kick_participant(job["entity"], user)
                kicked += 1
            except Exception:
                logger.debug("Could not kick deleted account", exc_info=True)
        await call.edit(
            f"{_EMOJI['success']} <b>{self._s('kicked_count')}: <code>{kicked}</code></b>",
            reply_markup=None,
        )

    @loader.command(
        ru_doc=" [пользователь] [причина] [-d] - кик; [-d] - кик удалённых аккаунтов"
    , en_doc=' [user] [reason] [-d] - kick; [-d] - kick deleted accounts')
    @loader.group_admin_ban_users
    async def kick(self, message: Message):
        raw_args = [arg.lower() for arg in self._args(message)]
        if raw_args == ["-d"]:
            entity = await self._chat_command_entity(message, error_ttl=_IMPORTANT_RESULT_TTL)
            if not entity:
                return
            capabilities = await self._operator_capabilities(entity)
            if not capabilities.get("ban_users"):
                await self._answer_temporary(
                    message,
                    (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('member_kick_rights')}</b>"
                    ),
                    _IMPORTANT_RESULT_TTL,
                )
                return
            try:
                users = await self._deleted_chat_members(entity)
            except Exception:
                logger.exception("Could not find deleted chat accounts")
                await self._answer_temporary(
                    message,
                    (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('member_list_failed')}</b>"
                    ),
                    _IMPORTANT_RESULT_TTL,
                )
                return
            if not users:
                await self._inline_answer(
                    message,
                    (
                        f"{_EMOJI['success']} "
                        f"<b>{self._s('no_deleted_accounts')}</b>"
                    ),
                )
                return
            self._prune_bulk_kick_jobs()
            token = secrets.token_urlsafe(12)
            self._bulk_kick_jobs[token] = {
                "entity": entity,
                "users": users,
                "expires": time.monotonic() + _BULK_KICK_TTL,
            }
            sent = await self.inline.form(
                (
                    f"{_EMOJI['warning']} "
                    f"<b>GodChat · {self._s('deleted_accounts')}</b>\n\n"
                    f"<blockquote><b>{self._s('will_be_kicked')}:</b> "
                    f"<code>{self._number(len(users))}</code></blockquote>"
                ),
                message,
                reply_markup=[
                    [
                        {
                            "text": self._s("kick_button"),
                            "callback": self._confirm_kick_deleted,
                            "args": (token,),
                            "style": "danger",
                        }
                    ],
                    [{"text": self._s("cancel_button"), "action": "close"}],
                ],
                ttl=_BULK_KICK_TTL,
            )
            if not sent:
                self._bulk_kick_jobs.pop(token, None)
                await self._answer_temporary(
                    message,
                    (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('confirmation_open_failed')}</b>"
                    ),
                    _IMPORTANT_RESULT_TTL,
                )
            return
        context = await self._context(message, error_ttl=_IMPORTANT_RESULT_TTL)
        if not context:
            return
        entity, target, permissions, args = context
        if getattr(permissions, "is_creator", False):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('creator_kick_forbidden')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        if getattr(permissions, "is_admin", False):
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('demote_admin_first')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        reason = self._reason(args)
        try:
            await self.client.kick_participant(entity, target)
        except Exception:
            logger.exception("Could not kick member")
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('kick_failed')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        await self._inline_answer(
            message,
            self._result(
                _EMOJI["kick"],
                self._s("kick_title"),
                target,
                self._s("removed_from_chat"),
                None,
                reason,
            ),
        )

    @staticmethod
    def _number(value):
        return f"{value:,}".replace(",", "\u00a0")

    @staticmethod
    def _plural(value, one, few, many):
        value = abs(value)
        if value % 100 in range(11, 15):
            return many
        if value % 10 == 1:
            return one
        if value % 10 in range(2, 5):
            return few
        return many

    def _message_count(self, amount):
        forms = self._s("duration_messages").split("|")
        return self._plural(amount, *forms)

    def _duration_name(self, amount, unit):
        forms = self._s(f"duration_{unit}").split("|")
        return (
            f"{self._number(amount)} "
            f"{self._plural(amount, *forms)}"
        )

    def _duration_details(self, seconds):
        year = 365 * 24 * 60 * 60
        day = 24 * 60 * 60
        hour = 60 * 60
        years, remainder = divmod(seconds, year)
        if years >= 1000:
            scale = 10 ** max(0, len(str(years)) - 3)
            years = ((years + scale // 2) // scale) * scale
            days = 0
            hours = 0
        else:
            days, remainder = divmod(remainder, day)
            hours = remainder // hour
        return (
            f"{self._duration_name(years, 'years')}, "
            f"{self._duration_name(days, 'days')}, "
            f"{self._duration_name(hours, 'hours')}"
        )

    def _duration(self, args, clamp_minimum=True):
        if not args or not args[0][:1].isdigit():
            return None, self._s("forever"), 0
        match = _DURATION_RE.fullmatch(args[0].lower())
        if not match:
            raise ValueError
        amount = int(match.group(1))
        if amount <= 0:
            raise ValueError
        alias = match.group(2)
        consumed = 1
        if (
            not alias
            and len(args) > 1
            and args[1].lower() in _DURATION_ALIASES
            and args[1]
        ):
            alias = args[1].lower()
            consumed = 2
        if alias not in _DURATION_ALIASES:
            raise ValueError
        unit, multiplier = _DURATION_ALIASES[alias]
        requested = amount * multiplier
        label = self._duration_name(amount, unit)
        if unit in {"seconds", "minutes", "hours"} and requested >= 60 * 60:
            label += f" (≈ {self._duration_details(requested)})"
        if clamp_minimum and requested < _TELEGRAM_MIN_MUTE:
            return _TELEGRAM_MIN_MUTE, label, consumed
        if requested > _TELEGRAM_MAX_MUTE:
            return None, label, consumed
        return requested, label, consumed

    def _duration_error(self):
        return (
            f"{_EMOJI['error']} <b>{self._s('invalid_time')}</b>\n"
            + self._s("duration_format")
        )

    @staticmethod
    def _rights_until_date(value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return int(value.timestamp())
        return int(value or 0)

    @classmethod
    def _dump_chat_rights(cls, rights):
        return {
            "until_date": cls._rights_until_date(
                getattr(rights, "until_date", None)
            ),
            **{
                field: bool(getattr(rights, field, False))
                for field in _BANNED_RIGHT_FIELDS
            },
        }

    @staticmethod
    def _load_chat_rights(data, closed=False):
        values = {
            field: bool(data.get(field, False))
            for field in _BANNED_RIGHT_FIELDS
        }
        if closed:
            values["send_messages"] = True
        return types.ChatBannedRights(
            until_date=0 if closed else int(data.get("until_date", 0)),
            **values,
        )

    @staticmethod
    def _member_inline_blocked(permissions):
        return bool(
            getattr(
                getattr(
                    getattr(permissions, "participant", None),
                    "banned_rights",
                    None,
                ),
                "send_inline",
                False,
            )
        )

    @staticmethod
    def _member_fully_banned(permissions):
        return bool(
            getattr(
                getattr(
                    getattr(permissions, "participant", None),
                    "banned_rights",
                    None,
                ),
                "view_messages",
                False,
            )
        )

    async def _fresh_chat_settings(self, entity):
        if isinstance(entity, types.Channel):
            result = await asyncio.wait_for(
                self.client(
                    functions.channels.GetFullChannelRequest(
                        channel=entity,
                    )
                ),
                timeout=5,
            )
            chat = next(
                (
                    item
                    for item in result.chats
                    if int(item.id) == int(entity.id)
                ),
                entity,
            )
            return {
                "rights": self._dump_chat_rights(
                    getattr(chat, "default_banned_rights", None)
                ),
                "slow": int(
                    getattr(result.full_chat, "slowmode_seconds", 0) or 0
                ),
                "join_request": bool(
                    getattr(chat, "join_request", False)
                ),
            }
        result = await asyncio.wait_for(
            self.client(
                functions.messages.GetFullChatRequest(chat_id=entity.id)
            ),
            timeout=5,
        )
        chat = next(
            (
                item
                for item in result.chats
                if int(item.id) == int(entity.id)
            ),
            entity,
        )
        return {
            "rights": self._dump_chat_rights(
                getattr(chat, "default_banned_rights", None)
            ),
            "slow": 0,
            "join_request": False,
        }

    async def _chat_inline_blocked(self, entity):
        try:
            settings = await self._fresh_chat_settings(entity)
            return bool(settings["rights"].get("send_inline", False))
        except Exception:
            logger.debug("Could not get chat inline settings", exc_info=True)
            return False

    async def _set_member_inline(self, entity, target, permissions, blocked):
        rights = self._dump_chat_rights(
            getattr(
                getattr(permissions, "participant", None),
                "banned_rights",
                None,
            )
        )
        rights["send_inline"] = bool(blocked)
        await self.client(
            functions.channels.EditBannedRequest(
                channel=entity,
                participant=target,
                banned_rights=self._load_chat_rights(rights),
            )
        )

    async def _set_chat_inline(self, entity, chat_id, blocked):
        settings = await self._fresh_chat_settings(entity)
        rights = settings["rights"]
        rights["send_inline"] = bool(blocked)
        await self.client(
            functions.messages.EditChatDefaultBannedRightsRequest(
                peer=entity,
                banned_rights=self._load_chat_rights(rights),
            )
        )
        state = self._chat_controls.get(str(chat_id))
        if state:
            state["base_rights"]["send_inline"] = bool(blocked)
            self._save_chat_controls()

    async def _set_chat_closed(self, entity, rights, closed):
        await self.client(
            functions.messages.EditChatDefaultBannedRightsRequest(
                peer=entity,
                banned_rights=self._load_chat_rights(rights, closed),
            )
        )

    def _save_chat_controls(self):
        self._save_state("chat_controls", self._chat_controls)

    def _chat_control_lock(self, chat_id):
        return self._chat_control_locks.setdefault(
            str(chat_id),
            asyncio.Lock(),
        )

    @staticmethod
    def _new_chat_control(settings):
        return {
            "base_rights": settings["rights"],
            "banchat_active": False,
            "banchat_until": 0,
            "banchat_label": "",
            "banchat_topic_id": None,
            "panic_active": False,
            "panic_slow": 0,
            "panic_join_request": False,
            "panic_close_applied": True,
            "panic_slow_applied": True,
            "panic_requests_applied": True,
        }

    def _schedule_banchat(self, chat_id, deadline):
        chat_id = str(chat_id)
        previous = self._banchat_tasks.get(chat_id)
        if previous:
            previous.cancel()
        self._banchat_tasks[chat_id] = asyncio.create_task(
            self._banchat_timer(chat_id, float(deadline))
        )

    async def _banchat_timer(self, chat_id, deadline):
        try:
            await asyncio.sleep(max(0, deadline - time.time()))
            topic_id = None
            while True:
                async with self._chat_control_lock(chat_id):
                    state = self._chat_controls.get(chat_id)
                    if (
                        not state
                        or not state.get("banchat_active")
                        or float(state.get("banchat_until", 0)) != deadline
                    ):
                        return
                    topic_id = state.get("banchat_topic_id")
                    if state.get("panic_active"):
                        retry = False
                        if not state.get("panic_close_applied", True):
                            try:
                                entity = await self.client.get_entity(int(chat_id))
                                await self._set_chat_closed(entity, state["base_rights"], False)
                            except Exception:
                                logger.exception("Could not restore chat after banchat timeout")
                                deadline = time.time() + 60
                                state["banchat_until"] = deadline
                                self._save_chat_controls()
                                retry = True
                        if not retry:
                            state["banchat_active"] = False
                            state["banchat_until"] = 0
                            state["banchat_label"] = ""
                            state["banchat_topic_id"] = None
                            self._save_chat_controls()
                            detail = self._s("chat_stays_closed_panic") if state.get("panic_close_applied", True) else self._s("chat_opened")
                            text = f"{_EMOJI['warning']} <b>GodChat · {self._s('banchat_finished')}</b>\n\n<blockquote>{detail}</blockquote>"
                            break
                    else:
                        try:
                            entity = await self.client.get_entity(int(chat_id))
                            await self._set_chat_closed(entity, state["base_rights"], False)
                        except Exception:
                            logger.exception("Could not restore chat after banchat timeout")
                            deadline = time.time() + 60
                            state["banchat_until"] = deadline
                            self._save_chat_controls()
                        else:
                            self._chat_controls.pop(chat_id, None)
                            self._save_chat_controls()
                            text = (
                                f"{_EMOJI['success']} "
                                f"<b>GodChat · {self._s('chat_opened')}</b>\n\n"
                                f"<blockquote>{self._s('close_time_ended')}</blockquote>"
                            )
                            break
                await asyncio.sleep(max(0, deadline - time.time()))
            try:
                await self.client.send_message(
                    int(chat_id),
                    text,
                    **(
                        {"reply_to": int(topic_id)}
                        if topic_id is not None
                        else {}
                    ),
                )
            except Exception:
                logger.debug(
                    "Could not send banchat timeout message",
                    exc_info=True,
                )
        except asyncio.CancelledError:
            return
        finally:
            current = asyncio.current_task()
            if self._banchat_tasks.get(chat_id) is current:
                self._banchat_tasks.pop(chat_id, None)

    async def _chat_command_entity(self, message, panic=False, error_ttl=None):
        try:
            entity = await self.client.get_entity(message.chat_id)
        except Exception:
            result = await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('chat_fetch_failed')}</b>",
            )
            if error_ttl is not None:
                self._schedule_temporary_delete(result, error_ttl)
            return None
        if not isinstance(entity, (types.Chat, types.Channel)) or getattr(
            entity,
            "broadcast",
            False,
        ):
            result = await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('chat_only')}</b>",
            )
            if error_ttl is not None:
                self._schedule_temporary_delete(result, error_ttl)
            return None
        if panic and (
            not isinstance(entity, types.Channel)
            or not getattr(entity, "megagroup", False)
        ):
            result = await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('supergroup_panic_only')}</b>"
                ),
            )
            if error_ttl is not None:
                self._schedule_temporary_delete(result, error_ttl)
            return None
        return entity

    async def _join_request_entity(self, message, error_ttl=None):
        try:
            entity = await self.client.get_entity(message.chat_id)
        except Exception:
            result = await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('chat_fetch_failed')}</b>",
            )
            if error_ttl is not None:
                self._schedule_temporary_delete(result, error_ttl)
            return None
        if not isinstance(entity, (types.Chat, types.Channel)):
            result = await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('chat_or_channel_only')}</b>",
            )
            if error_ttl is not None:
                self._schedule_temporary_delete(result, error_ttl)
            return None
        return entity

    async def _pending_join_request_page(self, entity, limit=100):
        result = await self.client(
            functions.messages.GetChatInviteImportersRequest(
                peer=entity,
                offset_date=None,
                offset_user=types.InputUserEmpty(),
                limit=limit,
                requested=True,
            )
        )
        users = {
            int(user.id): user
            for user in (getattr(result, "users", None) or [])
            if isinstance(user, types.User)
        }
        requesters = []
        seen = set()
        for importer in getattr(result, "importers", None) or []:
            user_id = int(getattr(importer, "user_id", 0) or 0)
            user = users.get(user_id)
            if user is not None and user_id not in seen:
                requesters.append(user)
                seen.add(user_id)
        return int(getattr(result, "count", 0) or 0), requesters

    async def _pending_join_request_count(self, entity):
        count, _ = await self._pending_join_request_page(entity, limit=1)
        return count

    async def _dismiss_all_join_requests(self, entity, approved=False):
        await self.client(
            functions.messages.HideAllChatJoinRequestsRequest(
                peer=entity,
                approved=approved,
            )
        )
        remaining = await self._pending_join_request_count(entity)
        while remaining:
            current_count, requesters = await self._pending_join_request_page(
                entity,
            )
            if not current_count:
                return 0
            if not requesters:
                return current_count
            for requester in requesters:
                try:
                    await self.client(
                        functions.messages.HideChatJoinRequestRequest(
                            peer=entity,
                            user_id=requester,
                            approved=approved,
                        )
                    )
                except HideRequesterMissingError:
                    pass
            next_count = await self._pending_join_request_count(entity)
            if next_count >= current_count:
                return next_count
            remaining = next_count
        return 0

    async def _process_join_request_batch(self, entity, amount, approved=False):
        amount = max(0, int(amount))
        processed = 0
        while processed < amount:
            try:
                _, requesters = await self._pending_join_request_page(
                    entity,
                    limit=min(100, amount - processed),
                )
            except FloodWaitError as error:
                error.processed_requests = processed
                raise
            if not requesters:
                break
            for requester in requesters:
                try:
                    await self.client(
                        functions.messages.HideChatJoinRequestRequest(
                            peer=entity,
                            user_id=requester,
                            approved=approved,
                        )
                    )
                    processed += 1
                except HideRequesterMissingError:
                    pass
                except FloodWaitError as error:
                    error.processed_requests = processed
                    raise
                if processed >= amount:
                    break
        try:
            remaining = await self._pending_join_request_count(entity)
        except FloodWaitError as error:
            error.processed_requests = processed
            raise
        return processed, remaining

    def _save_join_request_jobs(self):
        self._save_state("join_request_jobs", self._join_request_jobs)

    def _prune_join_request_confirms(self):
        now = time.monotonic()
        self._join_request_confirms = {
            token: state
            for token, state in self._join_request_confirms.items()
            if state.get("expires", 0) > now
        }

    def _schedule_join_request_cleanup(self, chat_id, retry_at):
        chat_id = str(chat_id)
        previous = self._join_request_tasks.get(chat_id)
        current = asyncio.current_task()
        if previous and previous is not current:
            previous.cancel()
        self._join_request_tasks[chat_id] = asyncio.create_task(
            self._join_request_cleanup_task(chat_id, float(retry_at))
        )

    async def _queue_join_request_retry(
        self,
        chat_id,
        topic_id,
        count,
        seconds,
        approved=False,
        limit=None,
    ):
        retry_at = time.time() + max(1, int(seconds))
        self._join_request_jobs[str(chat_id)] = {
            "chat_id": int(chat_id),
            "topic_id": topic_id,
            "count": int(count),
            "retry_at": retry_at,
            "approved": bool(approved),
            "limit": int(limit) if limit is not None else None,
        }
        self._save_join_request_jobs()
        self._schedule_join_request_cleanup(chat_id, retry_at)
        return retry_at

    async def _join_request_cleanup_task(self, chat_id, retry_at):
        try:
            await asyncio.sleep(max(0, retry_at - time.time()))
            state = self._join_request_jobs.get(str(chat_id))
            if not state or float(state.get("retry_at", 0) or 0) != retry_at:
                return
            failed = False
            async with self._chat_control_lock(chat_id):
                try:
                    entity = await self.client.get_entity(
                        int(state["chat_id"])
                    )
                    capabilities = await self._operator_capabilities(entity)
                    if not capabilities.get("invite_users"):
                        raise PermissionError
                    approved = bool(state.get("approved", False))
                    limit = state.get("limit")
                    if limit is None:
                        remaining = await self._dismiss_all_join_requests(
                            entity,
                            approved=approved,
                        )
                        processed = int(state.get("count", 0)) - remaining
                    else:
                        processed, remaining = await self._process_join_request_batch(
                            entity,
                            limit,
                            approved=approved,
                        )
                except HideRequesterMissingError:
                    self._join_request_jobs.pop(str(chat_id), None)
                    self._save_join_request_jobs()
                    text = (
                        f"{_EMOJI['success']} "
                        f"<b>{self._s('requests_none')}</b>"
                    )
                except FloodWaitError as error:
                    retry_limit = state.get("limit")
                    if retry_limit is not None:
                        retry_limit = max(
                            0,
                            int(retry_limit) - int(
                                getattr(error, "processed_requests", 0) or 0
                            ),
                        )
                    await self._queue_join_request_retry(
                        chat_id,
                        state.get("topic_id"),
                        state.get("count", 0),
                        error.seconds,
                        approved=bool(state.get("approved", False)),
                        limit=retry_limit,
                    )
                    return
                except Exception:
                    logger.exception("Could not clear pending join requests")
                    failed = True
                    self._join_request_jobs.pop(str(chat_id), None)
                    self._save_join_request_jobs()
                    text = (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('requests_failed')}</b>"
                    )
                else:
                    self._join_request_jobs.pop(str(chat_id), None)
                    self._save_join_request_jobs()
                    text = (
                        f"{_EMOJI['success']} "
                        f"<b>{self._s('requests_accepted' if approved else 'requests_cleared')}:</b> "
                        f"<code>{self._number(max(0, processed))}</code>"
                    )
                    if remaining:
                        text += (
                            f"\n<b>{self._s('new_requests')}:</b> "
                            f"<code>{self._number(remaining)}</code>"
                        )
            result = await self.client.send_message(
                int(state["chat_id"]),
                text,
                **(
                    {"reply_to": int(state["topic_id"])}
                    if state.get("topic_id") is not None
                    else {}
                ),
            )
            if failed:
                self._schedule_temporary_delete(result, _IMPORTANT_RESULT_TTL)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Could not resume join request cleanup")
        finally:
            current = asyncio.current_task()
            if self._join_request_tasks.get(str(chat_id)) is current:
                self._join_request_tasks.pop(str(chat_id), None)

    def _join_request_menu_text(self, state):
        return (
            f"{_EMOJI['warning']} <b>GodChat · {self._s('requests_title')}</b>\n\n"
            f"<blockquote><b>{self._s('requests_count')}:</b> "
            f"<code>{self._number(state['count'])}</code>\n"
            f"<b>{self._s('requests_batch', count=self._number(state['batch']))}</b>\n"
            f"{self._s('requests_menu_hint')}</blockquote>"
        )

    def _join_request_menu_markup(self, token, state):
        batch = self._number(state["batch"])
        return [
            [
                {
                    "text": self._s("requests_accept_batch", count=batch),
                    "callback": self._join_request_action,
                    "args": (token, True, False),
                    "style": "success",
                },
                {
                    "text": self._s("requests_decline_batch", count=batch),
                    "callback": self._join_request_action,
                    "args": (token, False, False),
                    "style": "danger",
                },
            ],
            [{
                "text": self._s("requests_batch", count=batch),
                "input": self._s("requests_batch_input"),
                "handler": self._join_request_batch_input,
                "args": (token,),
            }],
            [
                {
                    "text": self._s("requests_accept_button"),
                    "callback": self._join_request_action,
                    "args": (token, True, True),
                    "style": "success",
                },
                {
                    "text": self._s("requests_clear_button"),
                    "callback": self._join_request_action,
                    "args": (token, False, True),
                    "style": "danger",
                },
            ],
            [{"text": self._s("cancel_button"), "action": "close"}],
        ]

    async def _render_join_request_menu(self, call, token, state):
        await call.edit(
            self._join_request_menu_text(state),
            reply_markup=self._join_request_menu_markup(token, state),
        )

    async def _join_request_batch_input(self, call, data, token):
        call = self._input_source_form(call)
        state = self._join_request_confirms.get(token)
        if not state or state.get("expires", 0) < time.monotonic():
            await call.edit(
                f"{_EMOJI['error']} <b>{self._s('confirmation_expired')}</b>",
                reply_markup=None,
            )
            return
        try:
            batch = int(str(data or "").strip())
        except (TypeError, ValueError):
            batch = 0
        if batch < 1:
            await call.answer(
                self._s("requests_batch_invalid"),
                show_alert=True,
            )
            return
        try:
            state["count"] = await self._pending_join_request_count(state["entity"])
        except Exception:
            logger.debug("Could not refresh pending join request count", exc_info=True)
        state["batch"] = batch
        state["expires"] = time.monotonic() + _JOIN_REQUEST_CONFIRM_TTL
        await self._render_join_request_menu(call, token, state)

    async def _join_request_action(self, call, token, approved, all_requests):
        state = self._join_request_confirms.pop(token, None)
        if not state or state.get("expires", 0) < time.monotonic():
            await call.answer(self._s("confirmation_expired"), show_alert=True)
            return
        capabilities = await self._operator_capabilities(state["entity"])
        if not capabilities.get("invite_users"):
            await call.answer(self._s("requests_rights"), show_alert=True)
            return
        try:
            count = await self._pending_join_request_count(state["entity"])
            if not count:
                await call.edit(
                    f"{_EMOJI['success']} <b>{self._s('requests_none')}</b>",
                    reply_markup=None,
                )
                return
            amount = count if all_requests else min(int(state["batch"]), count)
            if all_requests:
                remaining = await self._dismiss_all_join_requests(
                    state["entity"],
                    approved=approved,
                )
                processed = max(0, count - remaining)
            else:
                processed, remaining = await self._process_join_request_batch(
                    state["entity"],
                    amount,
                    approved=approved,
                )
        except HideRequesterMissingError:
            processed = 0
            remaining = 0
        except FloodWaitError as error:
            processed = int(getattr(error, "processed_requests", 0) or 0)
            limit = None if all_requests else max(0, int(state["batch"]) - processed)
            retry_at = await self._queue_join_request_retry(
                state["chat_id"],
                state.get("topic_id"),
                state["count"],
                error.seconds,
                approved=approved,
                limit=limit,
            )
            await call.edit(
                (
                    f"{_EMOJI['warning']} <b>GodChat · {self._s('requests_title')}</b>\n\n"
                    f"<blockquote>FloodWait: <code>{error.seconds}</code> {self._s('seconds_short')}\n"
                    f"{self._s('continues_at')} "
                    f"<code>{datetime.fromtimestamp(retry_at).strftime('%H:%M:%S')}</code>.</blockquote>"
                ),
                reply_markup=None,
            )
            return
        except Exception:
            logger.exception("Could not process join requests")
            await call.edit(
                f"{_EMOJI['error']} <b>{self._s('requests_failed')}</b>",
                reply_markup=None,
            )
            self._schedule_temporary_delete(call, _IMPORTANT_RESULT_TTL)
            return
        text = (
            f"{_EMOJI['success']} "
            f"<b>{self._s('requests_accepted' if approved else 'requests_cleared')}:</b> "
            f"<code>{self._number(processed)}</code>"
        )
        if remaining:
            text += f"\n<b>{self._s('new_requests')}:</b> <code>{self._number(remaining)}</code>"
        await call.edit(text, reply_markup=None)

    @loader.command(ru_doc=" - управление заявками на вступление", en_doc=' - manage join requests')
    @loader.group_admin_invite_users
    async def reqcmd(self, message: Message):
        if self._args(message):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('no_arguments')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        entity = await self._join_request_entity(message, error_ttl=_IMPORTANT_RESULT_TTL)
        if not entity:
            return
        capabilities = await self._operator_capabilities(entity)
        if not capabilities.get("invite_users"):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('requests_rights')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        chat_id = str(int(message.chat_id))
        active = self._join_request_jobs.get(chat_id)
        if active:
            retry_at = int(active.get("retry_at", 0) or 0)
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['warning']} <b>{self._s('requests_cleanup_scheduled')}</b>\n\n"
                    f"<blockquote>{self._s('continues_at')} "
                    f"<code>{datetime.fromtimestamp(retry_at).strftime('%H:%M:%S')}</code>.</blockquote>"
                ),
            )
            return
        try:
            count = await self._pending_join_request_count(entity)
        except FloodWaitError as error:
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['warning']} <b>FloodWait:</b> "
                    f"<code>{error.seconds}</code> {self._s('seconds_short')} {self._s('try_later')}"
                ),
            )
            return
        except Exception:
            logger.exception("Could not get pending join request count")
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('requests_failed')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        self._prune_join_request_confirms()
        token = secrets.token_urlsafe(12)
        self._join_request_confirms[token] = {
            "entity": entity,
            "chat_id": int(message.chat_id),
            "topic_id": utils.get_topic(message),
            "count": count,
            "batch": max(1, min(10, count)),
            "expires": time.monotonic() + _JOIN_REQUEST_CONFIRM_TTL,
        }
        sent = await self.inline.form(
            self._join_request_menu_text(self._join_request_confirms[token]),
            message,
            reply_markup=self._join_request_menu_markup(
                token,
                self._join_request_confirms[token],
            ),
            ttl=_JOIN_REQUEST_CONFIRM_TTL,
        )
        if not sent:
            self._join_request_confirms.pop(token, None)
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('confirmation_open_failed')}</b>",
                _IMPORTANT_RESULT_TTL,
            )

    @loader.command(ru_doc=" [пользователь|-all] - запретить или разрешить инлайн", en_doc=' [user|-all] - forbid or allow inline')
    @loader.group_admin_ban_users
    async def inlinecmd(self, message: Message):
        args = [arg.lower() for arg in self._args(message)]
        if args == ["-all"]:
            entity = await self._chat_command_entity(message)
            if not entity:
                return
            capabilities = await self._operator_capabilities(entity)
            if not capabilities.get("ban_users"):
                await self._inline_answer(
                    message,
                    (
                        f"{_EMOJI['error']} "
                            f"<b>{self._s('no_restriction_rights')}</b>"
                    ),
                )
                return
            chat_id = str(int(message.chat_id))
            async with self._chat_control_lock(chat_id):
                try:
                    blocked = not await self._chat_inline_blocked(entity)
                    await self._set_chat_inline(entity, chat_id, blocked)
                except Exception:
                    logger.exception("Could not change global inline permission")
                    await self._inline_answer(
                        message,
                        (
                            f"{_EMOJI['error']} "
                            f"<b>{self._s('inline_change_failed')}</b>"
                        ),
                    )
                    return
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['success']} <b>GodChat · {self._s('inline')}</b>\n\n"
                    f"<blockquote>{self._s('inline_all_status')}: "
                    f"<b>{self._s('forbidden') if blocked else self._s('allowed')}</b>"
                    "</blockquote>"
                ),
                _NORMAL_RESULT_TTL,
            )
            return
        if args:
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('reply_or_all_inline')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        context = await self._context(message)
        if not context:
            return
        entity, target, permissions, _ = context
        capabilities = await self._operator_capabilities(entity)
        if not capabilities.get("ban_users"):
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('no_restriction_rights')}</b>"
                ),
            )
            return
        if not isinstance(entity, types.Channel):
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('personal_restrictions_supergroup')}</b>"
                ),
            )
            return
        if (
            getattr(permissions, "is_admin", False)
            or getattr(permissions, "is_creator", False)
        ):
            await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('admin_restrict_forbidden')}</b>",
            )
            return
        if self._member_fully_banned(permissions) or getattr(
            permissions,
            "has_left",
            False,
        ):
            await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('member_not_in_chat')}</b>",
            )
            return
        if await self._chat_inline_blocked(entity):
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['warning']} "
                    f"<b>{self._s('inline_all_already_forbidden')}</b>\n\n"
                    f"<blockquote>{self._s('inline_all_allow_hint')}</blockquote>"
                ),
            )
            return
        blocked = not self._member_inline_blocked(permissions)
        try:
            await self._set_member_inline(
                entity,
                target,
                permissions,
                blocked,
            )
        except Exception:
            logger.exception("Could not change member inline permission")
            await self._inline_answer(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('inline_change_failed')}</b>"
                ),
            )
            return
        await self._answer_temporary(
            message,
            (
                f"{_EMOJI['success']} <b>GodChat · {self._s('inline')}</b>\n\n"
                f"<blockquote>{self._label(target)}\n"
                f"<b>{self._s('inline')}:</b> {self._s('forbidden') if blocked else self._s('allowed')}"
                "</blockquote>"
            ),
            _NORMAL_RESULT_TTL,
        )

    @loader.command(ru_doc=" - запретить или разрешить гостевых ботов в чате", en_doc=' - forbid or allow guest bots in the chat')
    async def guestcmd(self, message: Message):
        if self._args(message):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('no_arguments')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        chat_id = str(int(message.chat_id))
        blocked = not self._guest_bots_blocked(chat_id)
        if blocked and not getattr(message, "is_private", False):
            try:
                entity = await self.client.get_entity(message.chat_id)
            except Exception:
                await self._inline_answer(
                    message,
                    f"{_EMOJI['error']} <b>{self._s('chat_fetch_failed')}</b>",
                )
                return
            capabilities = await self._operator_capabilities(entity)
            if not capabilities.get("delete_messages"):
                await self._inline_answer(
                    message,
                    f"{_EMOJI['error']} <b>{self._s('guest_delete_rights')}</b>",
                )
                return
        if blocked:
            self._guest_bot_blocks[chat_id] = True
        else:
            self._guest_bot_blocks.pop(chat_id, None)
        self._save_guest_bot_blocks()
        await self._answer_temporary(
            message,
            (
                f"{_EMOJI['success']} <b>GodChat · {self._s('guest_title')}</b>\n\n"
                f"<blockquote>{self._s('guest_forbidden') if blocked else self._s('guest_allowed')}</blockquote>"
            ),
            _NORMAL_RESULT_TTL,
        )

    @loader.command(ru_doc=" [время] - закрыть/открыть чат", en_doc=' [time] - close/open the chat')
    @loader.group_admin_ban_users
    async def banchat(self, message: Message):
        entity = await self._chat_command_entity(message)
        if not entity:
            return
        args = self._args(message)
        try:
            duration, duration_label, consumed = self._duration(
                args,
                clamp_minimum=False,
            )
        except ValueError:
            await self._answer_temporary(
                message,
                self._duration_error(),
                _IMPORTANT_RESULT_TTL,
            )
            return
        if consumed != len(args):
            await self._answer_temporary(
                message,
                self._duration_error(),
                _IMPORTANT_RESULT_TTL,
            )
            return
        chat_id = str(int(message.chat_id))
        async with self._chat_control_lock(chat_id):
            state = self._chat_controls.get(chat_id)
            if state and state.get("banchat_active"):
                try:
                    if not state.get("panic_active") or not state.get("panic_close_applied", True):
                        await self._set_chat_closed(
                            entity,
                            state["base_rights"],
                            False,
                        )
                except Exception:
                    logger.exception("Could not disable banchat")
                    await self._inline_answer(
                        message,
                        (
                            f"{_EMOJI['error']} "
                            f"<b>{self._s('chat_open_failed')}</b>"
                        ),
                    )
                    return
                task = self._banchat_tasks.pop(chat_id, None)
                if task:
                    task.cancel()
                state["banchat_active"] = False
                state["banchat_until"] = 0
                state["banchat_label"] = ""
                state["banchat_topic_id"] = None
                panic_active = bool(state.get("panic_active"))
                if panic_active:
                    self._save_chat_controls()
                else:
                    self._chat_controls.pop(chat_id, None)
                    self._save_chat_controls()
                text = (
                    f"{_EMOJI['success']} "
                    f"<b>GodChat · {self._s('banchat_off')}</b>\n\n"
                    f"<blockquote>{self._s('chat_stays_closed_panic' if state.get('panic_close_applied', True) else 'chat_opened')}</blockquote>"
                    if panic_active
                    else (
                        f"{_EMOJI['success']} "
                        f"<b>GodChat · {self._s('chat_opened')}</b>"
                    )
                )
                await self._answer_temporary(
                    message,
                    text,
                    _IMPORTANT_RESULT_TTL,
                )
                return
            try:
                if not state:
                    settings = await self._fresh_chat_settings(entity)
                    state = self._new_chat_control(settings)
                await self._set_chat_closed(
                    entity,
                    state["base_rights"],
                    True,
                )
            except Exception:
                logger.exception("Could not enable banchat")
                await self._inline_answer(
                    message,
                    (
                        f"{_EMOJI['error']} "
                        f"<b>{self._s('close_chat_failed')}</b>"
                    ),
                )
                return
            deadline = time.time() + duration if duration is not None else 0
            state["banchat_active"] = True
            state["banchat_until"] = deadline
            state["banchat_label"] = duration_label
            state["banchat_topic_id"] = utils.get_topic(message)
            self._chat_controls[chat_id] = state
            self._save_chat_controls()
            if deadline:
                self._schedule_banchat(chat_id, deadline)
        await self._answer_temporary(
            message,
            (
                f"{_EMOJI['warning']} <b>GodChat · {self._s('chat_closed')}</b>\n\n"
                f"<blockquote>{self._duration_block(duration_label).lstrip()}\n"
                f"{self._s('repeat_opens_chat')}</blockquote>"
            ),
            _IMPORTANT_RESULT_TTL,
        )

    def _panic_result_details(self, state, enabled):
        details = []
        if state.get("panic_close_applied", True):
            details.append(self._s("chat_closed" if enabled else
                                   "chat_closed_by_banchat" if state.get("banchat_active") else "chat_opened"))
        if state.get("panic_slow_applied", True):
            details.append(self._s("panic_slow_on_detail" if enabled else "panic_slow_restored_detail"))
        if state.get("panic_requests_applied", True):
            details.append(self._s("panic_requests_on_detail" if enabled else "panic_requests_restored_detail"))
        return "\n".join(details)

    @loader.command(ru_doc=" - включение паники", en_doc=' - enable panic')
    @loader.group_admin_ban_users
    async def panic(self, message: Message):
        entity = await self._chat_command_entity(message, panic=True)
        if not entity:
            return
        chat_id = str(int(message.chat_id))
        async with self._chat_control_lock(chat_id):
            active = bool(self._chat_controls.get(chat_id, {}).get("panic_active"))
            if not active and not self._panic_has_actions(self._panic_config(chat_id)):
                return await self._inline_answer(message, f"{_EMOJI['error']} <b>{self._s('panic_choose_action')}</b>")
            try:
                if active:
                    old = self._chat_controls[chat_id]
                    details = self._panic_result_details(old, enabled=False)
                    await self._disable_panic(entity, chat_id)
                else:
                    await self._enable_panic(entity, chat_id)
                    details = self._panic_result_details(self._chat_controls[chat_id], enabled=True)
            except Exception:
                logger.exception("Could not %s panic mode", "disable" if active else "enable")
                return await self._inline_answer(message, f"{_EMOJI['error']} <b>{self._s('panic_disable_failed' if active else 'panic_enable_failed')}</b>")
        if active:
            return await self._inline_answer(message, f"{_EMOJI['success']} <b>GodChat · {self._s('panic_off')}</b>\n\n<blockquote>{details}</blockquote>")
        await self._inline_answer(message, f"{_EMOJI['warning']} <b>GodChat · {self._s('panic_on')}</b>\n\n<blockquote>{details}</blockquote>")

    async def _enable_panic(self, entity, chat_id):
        config = self._panic_config(chat_id)
        if not self._panic_has_actions(config):
            raise ValueError("No panic actions selected")
        state = self._chat_controls.get(chat_id)
        settings = await self._fresh_chat_settings(entity)
        if not state:
            state = self._new_chat_control(settings)
        done = []
        try:
            if config["close"] and not state.get("banchat_active"):
                await self._set_chat_closed(entity, state["base_rights"], True)
                done.append("close")
            if config["slow"] and settings["slow"] != _PANIC_SLOW_MODE:
                await self.client(functions.channels.ToggleSlowModeRequest(channel=entity, seconds=_PANIC_SLOW_MODE))
                done.append("slow")
            if config["requests"] and not settings["join_request"]:
                await self.client(functions.channels.ToggleJoinRequestRequest(channel=entity, enabled=True))
                done.append("requests")
        except Exception:
            for action in reversed(done):
                try:
                    if action == "requests":
                        await self.client(functions.channels.ToggleJoinRequestRequest(channel=entity, enabled=settings["join_request"]))
                    elif action == "slow":
                        await self.client(functions.channels.ToggleSlowModeRequest(channel=entity, seconds=settings["slow"]))
                    elif action == "close":
                        await self._set_chat_closed(entity, state["base_rights"], False)
                except Exception:
                    logger.exception("Could not roll back panic action %s", action)
            raise
        state.update(panic_active=True, panic_slow=settings["slow"],
                     panic_join_request=settings["join_request"],
                     panic_close_applied="close" in done,
                     panic_slow_applied="slow" in done,
                     panic_requests_applied="requests" in done)
        self._chat_controls[chat_id] = state
        self._save_chat_controls()

    async def _disable_panic(self, entity, chat_id):
        state = self._chat_controls[chat_id]
        current = await self._fresh_chat_settings(entity)
        if state.get("panic_slow_applied", True) and current["slow"] == _PANIC_SLOW_MODE:
            await self.client(functions.channels.ToggleSlowModeRequest(channel=entity, seconds=int(state.get("panic_slow", 0))))
        if state.get("panic_requests_applied", True) and current["join_request"]:
            await self.client(functions.channels.ToggleJoinRequestRequest(channel=entity, enabled=bool(state.get("panic_join_request", False))))
        if (state.get("panic_close_applied", True) and not state.get("banchat_active")
                and current["rights"].get("send_messages")):
            rights = dict(current["rights"])
            rights["send_messages"] = bool(state["base_rights"].get("send_messages", False))
            await self._set_chat_closed(entity, rights, False)
        state["panic_active"] = False
        state.pop("panic_until", None)
        if state.get("banchat_active"):
            self._save_chat_controls()
        else:
            self._chat_controls.pop(chat_id, None)
            self._save_chat_controls()
        self._panic_joins.pop(chat_id, None)

    @loader.command(
        ru_doc=" [пользователь] [время] - делит-мут; повторная команда снимает"
    , en_doc=' [user] [time] - delete-mute; repeat to remove')
    async def dmute(self, message: Message):
        context = await self._delete_mute_context(message)
        if not context:
            return
        target, args = context
        if int(target.id) == self._me_id:
            await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('self_action')}</b>",
            )
            return
        chat_id = str(int(message.chat_id))
        users = self._delete_mutes.get(chat_id, {})
        if str(int(target.id)) in users:
            self._remove_delete_mute(chat_id, target.id)
            await self._answer_temporary(
                message,
                self._result(
                    _EMOJI["success"], self._s("dmute_title"), target,
                    self._s("dmute_removed"), None, "",
                ),
                _NORMAL_RESULT_TTL,
            )
            return
        try:
            duration, duration_label, consumed = self._duration(
                args,
                clamp_minimum=False,
            )
        except ValueError:
            await self._answer_temporary(
                message,
                self._duration_error(),
                _IMPORTANT_RESULT_TTL,
            )
            return
        if consumed != len(args):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('dmute_usage')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        try:
            entity = await self.client.get_entity(message.chat_id)
        except Exception:
            await self._inline_answer(
                message,
                f"{_EMOJI['error']} <b>{self._s('chat_fetch_failed')}</b>",
            )
            return
        if not getattr(message, "is_private", False):
            capabilities = await self._operator_capabilities(entity)
            if not capabilities.get("delete_messages") or (
                getattr(message, "is_channel", False)
                and not capabilities.get("ban_users")
            ):
                await self._inline_answer(
                    message,
                    f"{_EMOJI['error']} <b>{self._s('dmute_delete_rights')}</b>",
                )
                return
        users = self._delete_mutes.setdefault(chat_id, {})
        users[str(int(target.id))] = {
            "expires": time.time() + duration if duration is not None else 0,
        }
        self._save_delete_mutes()
        await self._answer_temporary(
            message,
            self._result(
                _EMOJI["mute"], self._s("dmute_title"), target,
                self._s("dmute_action"), duration_label, "",
            ),
            _NORMAL_RESULT_TTL,
        )

    async def _toggle_sticker_ban(self, message, args, reply, remove_only=False):
        if len(args) != len(set(args)) or any(arg not in {"-p", "-g"} for arg in args):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('sticker_ban_args')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        sticker_key, pack_key = self._sticker_ban_keys(reply) if reply else (None, None)
        if sticker_key is None:
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('sticker_ban_reply')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        pack_mode = "-p" in args
        global_scope = "-g" in args
        if pack_mode and pack_key is None:
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('sticker_pack_missing')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        if not global_scope and not await self._sticker_ban_permissions(message):
            return
        scope = "global" if global_scope else str(int(message.chat_id))
        rules = self._sticker_bans.get(scope, {}) if remove_only else self._sticker_bans.setdefault(scope, {})
        key = pack_key if pack_mode else sticker_key
        kind = "pack" if pack_mode else "sticker"
        removing = remove_only and key in rules
        if removing:
            rules.pop(key, None)
            if not rules:
                self._sticker_bans.pop(scope, None)
            result_key = "sticker_pack_unbanned" if pack_mode else "sticker_unbanned"
            if not pack_mode and pack_key in rules:
                result_key = "sticker_still_pack_banned"
        elif remove_only:
            result_key = "sticker_pack_not_banned" if pack_mode else "sticker_not_banned"
        elif key in rules:
            result_key = "sticker_pack_banned" if pack_mode else "sticker_banned"
        else:
            rules[key] = {"kind": kind}
            result_key = "sticker_pack_banned" if pack_mode else "sticker_banned"
        if removing or not remove_only:
            self._save_sticker_bans()
        text = self._s(result_key)
        other = self._sticker_rules(message.chat_id, global_scope=not global_scope)
        if (removing or remove_only) and (sticker_key in other or pack_key in other):
            text += "\n" + self._s("sticker_other_scope")
        await self._inline_answer(
            message,
            (
                f"{_EMOJI['success']} <b>GodChat · {self._s('sticker_global_title' if global_scope else 'sticker_ban_title')}</b>\n\n"
                f"<blockquote>{text}</blockquote>"
            ),
        )

    @loader.command(
        ru_doc=" [пользователь] [время] [причина] - мут"
    , en_doc=' [user] [time] [reason] - mute')
    @loader.group_admin_ban_users
    async def mute(self, message: Message):
        context = await self._context(message, error_ttl=_IMPORTANT_RESULT_TTL)
        if not context:
            return
        entity, target, permissions, args = context
        if getattr(permissions, "is_creator", False):
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('creator_mute_forbidden')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        if getattr(permissions, "is_admin", False):
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('demote_admin_first')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        try:
            duration, duration_label, consumed = self._duration(args)
        except ValueError:
            await self._answer_temporary(
                message,
                self._duration_error(),
                _IMPORTANT_RESULT_TTL,
            )
            return
        reason = self._reason(args[consumed:])
        if isinstance(entity, types.Chat):
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} <b>{self._s('mute_basic_group')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        until_date = (
            timedelta(seconds=duration)
            if duration is not None
            else None
        )
        try:
            await self.client.edit_permissions(
                entity,
                target,
                until_date,
                send_messages=False,
            )
        except Exception:
            logger.exception("Could not mute member")
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('mute_failed')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        await self._inline_answer(
            message,
            self._result(
                _EMOJI["mute"],
                self._s("mute_title"),
                target,
                self._s("muted_action"),
                duration_label,
                reason,
            ),
        )

    @loader.command(
        ru_doc=" [пользователь] - снять мут"
    , en_doc=' [user] - unmute')
    async def unmute(self, message: Message):
        if getattr(message, "is_private", False):
            context = await self._delete_mute_context(message)
            if not context:
                return
            target, args = context
            if args:
                await self._answer_temporary(
                    message,
                    f"{_EMOJI['error']} <b>{self._s('no_arguments')}</b>",
                    _IMPORTANT_RESULT_TTL,
                )
                return
            removed = self._remove_delete_mute(message.chat_id, target.id)
            await self._inline_answer(
                message,
                self._result(
                    _EMOJI["success"] if removed else _EMOJI["warning"],
                    self._s("dmute_title"),
                    target,
                    self._s("dmute_removed" if removed else "dmute_none"),
                    None,
                    "",
                ),
            )
            return
        context = await self._context(message, error_ttl=_IMPORTANT_RESULT_TTL)
        if not context:
            return
        entity, target, _, _ = context
        delete_mute_removed = self._remove_delete_mute(
            message.chat_id,
            target.id,
        )
        if isinstance(entity, types.Chat):
            if delete_mute_removed:
                await self._inline_answer(
                    message,
                    self._result(
                        _EMOJI["success"],
                        self._s("dmute_title"),
                        target,
                        self._s("dmute_removed"),
                        None,
                        "",
                    ),
                )
                return
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('mute_basic_group_short')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        capabilities = await self._operator_capabilities(entity)
        if not capabilities.get("ban_users"):
            if delete_mute_removed:
                await self._inline_answer(
                    message,
                    self._result(
                        _EMOJI["success"],
                        self._s("dmute_title"),
                        target,
                        self._s("dmute_removed"),
                        None,
                        "",
                    ),
                )
                return
            await self._answer_temporary(
                message,
                f"{_EMOJI['error']} <b>{self._s('no_restriction_rights')}</b>",
                _IMPORTANT_RESULT_TTL,
            )
            return
        try:
            await self.client.edit_permissions(entity, target, None)
        except Exception:
            logger.exception("Could not unmute member")
            if delete_mute_removed:
                await self._inline_answer(
                    message,
                    self._result(
                        _EMOJI["success"],
                        self._s("dmute_title"),
                        target,
                        self._s("dmute_removed"),
                        None,
                        "",
                    ),
                )
                return
            await self._answer_temporary(
                message,
                (
                    f"{_EMOJI['error']} "
                    f"<b>{self._s('unmute_failed')}</b>"
                ),
                _IMPORTANT_RESULT_TTL,
            )
            return
        await self._inline_answer(
            message,
            self._result(
                _EMOJI["success"],
                self._s("unmute_title"),
                target,
                "; ".join(
                    item
                    for item in (
                        self._s("restrictions_removed"),
                        self._s("dmute_removed")
                        if delete_mute_removed
                        else "",
                    )
                    if item
                ),
                None,
                "",
            ),
        )


GodChatMod.strings["_cls_doc"] = "Moderation tools for chats"
GodChatMod.strings.update({
    f"_cmd_doc_{name}": method.en_doc
    for name, method in loader.get_commands(GodChatMod).items()
})
