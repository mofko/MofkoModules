# ---------------------------------------------------------------------------------
#                    .-._   _ _ _ _ _ _ _ _
#         .-''-.__.-'00  '-' ' ' ' ' ' ' ' '-.
#         '.___ '    .   .--_'-' '-' '-' _'-' '._
#          V: V 'vv-'   '_   '.       .'  _..' '.'.
#            '=.____.=_.--'   :_.__.__:_   '.   : :
#                    (((____.-'        '-.  /   : :
#                                      (((-'\ .' /
#                                    _____..'  .'
#                                   '-._____.-'
# ---------------------------------------------------------------------------------
# meta developer: @mofkomodules 
# name: Бредик

__version__ = (1, 0, 0)

from herokutl.types import Message
from .. import loader, utils
import random
import logging
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

@loader.tds
class BredMod(loader.Module):
    """Отправь рандомный бред от упоротой нейросети."""
    
    strings = {"name": "Бредик"}

    def __init__(self):
        self._messages_cache: Optional[List[Message]] = None
        self._cache_time: float = 0
        self.source_channel = "https://t.me/neuralmachine"
        self.cache_ttl = 3600
        self.messages_limit = 600

    async def client_ready(self, client, db):
        self.client = client
        self._db = db

    async def _get_messages(self) -> List[Message]:
        current_time = time.time()
        
        if (self._messages_cache and 
            current_time - self._cache_time < self.cache_ttl):
            return self._messages_cache
        
        try:
            messages = await self.client.get_messages(
                self.source_channel,
                limit=self.messages_limit
            )
            
            filtered_messages = [msg for msg in messages if not msg.media]
            
            self._messages_cache = filtered_messages
            self._cache_time = current_time
            
            return filtered_messages
            
        except Exception as e:
            logger.error(f"Error loading messages: {e}")
            return self._messages_cache or []

    @loader.command(
        ru_doc="отправить бред",
        alias="бред"
    ) 
    async def bred(self, message: Message):
        try:
            await message.delete()
            
            messages = await self._get_messages()
            
            if not messages:
                return

            selected_message = random.choice(messages)
            
            await self.client.send_message(
                message.peer_id,
                message=selected_message.text,
                reply_to=getattr(message, "reply_to_msg_id", None)
            )
                
        except Exception as e:
            logger.error(f"Error sending bred: {e}") 
