# Name: AllInOne
# Description: Интерактивный модуль для чатов. 
# Author: @mofkomodules

__version__ = (1, 0, 0)

from .. import loader, utils
import random
from telethon.tl.types import InputPeerChannel

@loader.tds
class AllInOne(loader.Module):
    """Интерактивный модуль для чатов."""
    strings = {
    "name": "AllInOne",
    "Not_chat": "✖️ This is not a chat!",
}

strings_ru = {
    "Not_chat": "✖️ Это не чат!"
    }

@loader.command()
async def ship(self, message):
        """Рандомный шип чата!"""
        
        chat = message.peer_id
        channel = await self.client.get_entity(chat)
        participants = await self.client.get_participants(channel)
        random_user = random.choice(participants)
        random_user2 = random.choice(participants)
        user = random_user.id
        user_name = random_user.first_name
        user2 = random_user2.id
        user_name2 = random_user2.first_name
        Alina_a = f'<a href = "tg://user?id={user}">{user_name}</a>'
        Alina_b = f'<a href = "tg://user?id={user2}">{user_name2}</a>'
        if message.is_private:
            await utils.answer(message, self.strings["Not_chat"])
        else:
            await utils.answer(message, f'🎀 Рандомный шип: {Alina_a} + {Alina_b}\n Любите друг друга ❤️')
