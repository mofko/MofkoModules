# Name: AllInOne
# Description: Интерактивный модуль для чатов. 
# Author: @mofkomodules

__version__ = (1, 0, 0)

from .. import loader, utils
import random

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
