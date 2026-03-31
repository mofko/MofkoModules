__version__ = (2, 1, 0)
# meta developer: @mofkomodules
# meta fhsdesk: stars price parser звёзды цены парсер боты telegram

import re
import logging
import asyncio
import aiohttp
import time
from datetime import datetime

from .. import loader, utils
from telethon.tl.types import (
    Message,
    ReplyInlineMarkup,
    ReplyKeyboardMarkup,
    KeyboardButtonCallback,
    KeyboardButtonUrl,
    KeyboardButtonWebView,
    InputNotifyPeer,
    InputPeerNotifySettings,
    InputFolderPeer,
)
from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.tl.functions.folders import EditPeerFoldersRequest
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

BUTTON_KEYWORDS = ["звёзд", "звезд", "star", "⭐", "купить", "buy"]
BUY_BUTTON_KEYWORDS = [
    "купить звёзды", "купить звезды", "buy stars",
    "купить ⭐", "buy ⭐",
]
SELF_BUTTON_KEYWORDS = [
    "купить себе", "себе", "мне", "для себя",
    "for me", "myself", "buy for me",
]
QUANTITY_KEYWORDS = [
    "введите количество", "введите кол-во", "введи количество", "введи кол-во",
    "сколько звёзд", "сколько звезд", "сколько stars", "сколько ⭐",
    "количество звёзд", "количество звезд", "количество stars",
    "напишите количество", "напиши количество",
    "укажите количество", "укажи количество",
    "enter amount", "how many stars", "how many ⭐",
    "желаемое количество",
    "количество звёзд для", "количество звезд для",
    "кол-во звёзд", "кол-во звезд",
]

CURRENCY_MAP = {
    "₽": "RUB",
    "руб": "RUB",
    "rub": "RUB",
    "р": "RUB",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "₴": "UAH",
    "uah": "UAH",
    "₸": "KZT",
    "kzt": "KZT",
    "сум": "UZS",
    "uzs": "UZS",
    "£": "GBP",
    "gbp": "GBP",
    "¥": "CNY",
    "cny": "CNY",
    "try": "TRY",
    "₺": "TRY",
    "лир": "TRY",
}

_CUR = r"([₽$€₴₸£¥₺]|руб\w*|rub|usd|eur|uah|kzt|uzs|gbp|cny|try|лир\w*|сум\w*|р\.?)"
_NUM = r"(\d+[\.,]?\d*)"

PRICE_PATTERNS = [
    re.compile(
        r"100\s*(?:⭐|звёзд\w*|звезд\w*|stars?)\s*[—–=\-:～~»›]\s*" + _NUM + r"\s*" + _CUR,
        re.IGNORECASE,
    ),
    re.compile(
        _NUM + r"\s*" + _CUR + r"\s*[—–=\-:～~»›]\s*100\s*(?:⭐|звёзд\w*|звезд\w*|stars?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"100\s*(?:⭐|звёзд\w*|звезд\w*|stars?)\s*\D{0,15}?" + _NUM + r"\s*" + _CUR,
        re.IGNORECASE,
    ),
    re.compile(
        _NUM + r"\s*" + _CUR + r"\s*\D{0,15}?100\s*(?:⭐|звёзд\w*|звезд\w*|stars?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:итого|стоимость|к оплате|total|price|cost)\s*[:：]?\s*" + _NUM + r"\s*" + _CUR,
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:итогов\w+\s+стоимость|сумма\s+к\s+оплате|стоимость\s+заказа|order\s+total)\s*[:：]?\s*" + _NUM + r"\s*" + _CUR + r"\.?",
        re.IGNORECASE,
    ),
]

REVERSED_PRICE_PATTERN = re.compile(
    _CUR + r"\s*" + _NUM + r"\s*(?:\D{0,10})?100\s*(?:⭐|звёзд\w*|звезд\w*|stars?)",
    re.IGNORECASE,
)

FALLBACK_PRICE_PATTERN = re.compile(
    _NUM + r"\s*" + _CUR,
    re.IGNORECASE,
)

UNIT_PRICE_PATTERN = re.compile(
    r"(\d+)\s*(?:⭐|звёзд\w*|звезд\w*|stars?)\s*\(?\s*" + _NUM + r"\s*" + _CUR + r"\s*\)?",
    re.IGNORECASE,
)

MAX_PRICE_PER_100 = {
    "RUB": 170,
    "USD": 2,
    "EUR": 1.70,
    "UAH": 75,
    "KZT": 850,
    "UZS": 22000,
    "GBP": 1.50,
    "CNY": 13,
    "TRY": 60,
}

MIN_PRICE_PER_100 = {
    "RUB": 30,
    "USD": 0.30,
    "EUR": 0.25,
    "UAH": 10,
    "KZT": 100,
    "UZS": 3000,
    "GBP": 0.20,
    "CNY": 2,
    "TRY": 8,
}


def _is_price_valid(amount, currency_code):
    max_price = MAX_PRICE_PER_100.get(currency_code)
    if max_price is not None and amount > max_price:
        return False
    min_price = MIN_PRICE_PER_100.get(currency_code)
    if min_price is not None and amount < min_price:
        return False
    return True


@loader.tds
class StarsPriceParserMod(loader.Module):
    """Stars price parser from bots. Parsing may take some time — prices are sorted from lowest to highest"""

    strings = {
        "name": "StarsPriceParser",
        "processing": "⌛ <b>Parsing star prices from bots...</b>\n{}",
        "result_header": "⭐ <b>Prices for 100 stars</b>\n<i>Sorted from lowest to highest</i>\n\n",
        "result_row": "{}. {} — <b>{}</b> ✅\n",
        "result_row_converted": "{}. {} — <b>{}₽</b> (~{}) ✅\n",
        "result_row_error": "{}. {} — ❌ {}\n",
        "result_footer": "\n🕐 Updated: {}",
        "no_bots": "❌ No bots configured",
        "bot_timeout": "Bot not responding",
        "no_button": "Button not found",
        "no_price": "Failed to parse price",
        "rates_error": "Exchange rates unavailable",
        "cfg_bots": "List of bot usernames to parse prices from",
        "loading": "⏳ Loading...",
    }

    strings_ru = {
        "_cls_doc": "Парсер цен на звёзды из ботов. Парсинг может занять некоторое время — цены отсортированы от наименьшей к большей",
        "processing": "⌛ <b>Парсинг цен на звёзды...</b>\n{}",
        "result_header": "⭐ <b>Цены на 100 звёзд</b>\n<i>Отсортировано от меньшей к большей цене</i>\n\n",
        "result_row": "{}. {} — <b>{}</b> ✅\n",
        "result_row_converted": "{}. {} — <b>{}₽</b> (~{}) ✅\n",
        "result_row_error": "{}. {} — ❌ {}\n",
        "result_footer": "\n🕐 Обновлено: {}",
        "no_bots": "❌ Боты не настроены",
        "bot_timeout": "Бот не отвечает",
        "no_button": "Кнопка не найдена",
        "no_price": "Не удалось распарсить цену",
        "rates_error": "Курсы валют недоступны",
        "cfg_bots": "Список юзернеймов ботов для парсинга цен",
        "loading": "⏳ Загрузка...",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "bots",
                [
                    "@PupoStars_bot",
                    "@missedstarsbot",
                    "@dcstarsbot",
                    "@FantasyBuyStarsBot",
                    "@agentdurovastars_bot",
                ],
                lambda: self.strings("cfg_bots"),
                validator=loader.validators.Series(),
            ),
        )
        self._rates = None

    async def client_ready(self, client, db):
        if not self.get("bots_prepared", False):
            task = asyncio.create_task(self._prepare_bots())
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    async def _prepare_bots(self):
        for bot in self.config["bots"]:
            try:
                peer = await self.client.get_input_entity(bot)
                await self.client(UpdateNotifySettingsRequest(
                    peer=InputNotifyPeer(peer=peer),
                    settings=InputPeerNotifySettings(
                        mute_until=2147483647,
                        silent=True,
                    ),
                ))
                await self.client(EditPeerFoldersRequest(
                    folder_peers=[InputFolderPeer(peer=peer, folder_id=1)],
                ))
            except Exception as e:
                logger.exception(e)
        self.set("bots_prepared", True)

    async def _fetch_rates(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://open.er-api.com/v6/latest/RUB",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    if data.get("result") == "success":
                        return data.get("rates", {})
        except Exception as e:
            logger.exception(e)
        return None

    def _convert_to_rub(self, amount, currency_code, rates):
        if currency_code == "RUB" or not rates:
            return amount
        rate = rates.get(currency_code)
        if not rate or rate == 0:
            return None
        return round(amount / rate, 1)

    def _resolve_currency(self, raw):
        raw_clean = re.sub(r"[.\s]", "", raw).lower()
        for key, code in CURRENCY_MAP.items():
            if raw_clean.startswith(key):
                return code
        return None

    def _extract_price(self, text):
        if not text:
            return None
        for pattern in PRICE_PATTERNS:
            match = pattern.search(text)
            if match:
                amount_str = match.group(1).replace(",", ".")
                currency_raw = match.group(2)
                try:
                    amount = float(amount_str)
                except ValueError:
                    continue
                currency = self._resolve_currency(currency_raw)
                if currency and _is_price_valid(amount, currency):
                    return amount, currency, currency_raw
        match = REVERSED_PRICE_PATTERN.search(text)
        if match:
            currency_raw = match.group(1)
            amount_str = match.group(2).replace(",", ".")
            try:
                amount = float(amount_str)
                currency = self._resolve_currency(currency_raw)
                if currency and _is_price_valid(amount, currency):
                    return amount, currency, currency_raw
            except ValueError:
                pass
        return None

    def _extract_unit_price(self, text):
        if not text:
            return None
        matches = UNIT_PRICE_PATTERN.findall(text)
        for stars_str, amount_str, currency_raw in matches:
            try:
                stars = int(stars_str)
                amount = float(amount_str.replace(",", "."))
            except ValueError:
                continue
            if stars <= 0 or amount <= 0:
                continue
            currency = self._resolve_currency(currency_raw)
            if currency:
                price_per_100 = round(amount / stars * 100, 2)
                if _is_price_valid(price_per_100, currency):
                    return price_per_100, currency, currency_raw
        return None

    def _extract_price_fallback(self, text):
        if not text:
            return None
        matches = FALLBACK_PRICE_PATTERN.findall(text)
        for amount_str, currency_raw in matches:
            amount_str = amount_str.replace(",", ".")
            try:
                amount = float(amount_str)
            except ValueError:
                continue
            currency = self._resolve_currency(currency_raw)
            if currency and amount > 0 and _is_price_valid(amount, currency):
                return amount, currency, currency_raw
        return None

    def _get_buttons(self, message):
        if not message.reply_markup:
            return [], False
        markup = message.reply_markup
        is_inline = isinstance(markup, ReplyInlineMarkup)
        rows = getattr(markup, "rows", None)
        if not rows:
            return [], False
        return rows, is_inline

    def _find_button_by_keywords(self, message, keywords):
        rows, is_inline = self._get_buttons(message)
        if not rows:
            return None
        for i, row in enumerate(rows):
            for j, button in enumerate(row.buttons):
                if isinstance(button, (KeyboardButtonUrl, KeyboardButtonWebView)):
                    continue
                btn_text = getattr(button, "text", "") or ""
                btn_lower = btn_text.lower()
                for keyword in keywords:
                    if keyword.lower() in btn_lower:
                        return {
                            "row": i,
                            "col": j,
                            "text": btn_text,
                            "inline": is_inline,
                        }
        return None

    def _find_button_in_messages(self, messages, keywords):
        for msg in reversed(messages):
            btn = self._find_button_by_keywords(msg, keywords)
            if btn:
                return msg, btn
        return None, None

    def _find_first_clickable_button(self, messages):
        for msg in reversed(messages):
            rows, is_inline = self._get_buttons(msg)
            if not rows:
                continue
            for i, row in enumerate(rows):
                for j, button in enumerate(row.buttons):
                    if isinstance(button, (KeyboardButtonUrl, KeyboardButtonWebView)):
                        continue
                    btn_text = getattr(button, "text", "") or ""
                    if btn_text:
                        return msg, {
                            "row": i,
                            "col": j,
                            "text": btn_text,
                            "inline": is_inline,
                        }
        return None, None

    def _is_quantity_prompt(self, text):
        if not text:
            return False
        text_lower = text.lower()
        for keyword in QUANTITY_KEYWORDS:
            if keyword in text_lower:
                return True
        return False

    def _check_quantity_in_messages(self, messages):
        for msg in reversed(messages):
            text = msg.text or ""
            if self._is_quantity_prompt(text):
                return True
        return False

    async def _click_button(self, conv, message, btn_info):
        if btn_info["inline"]:
            try:
                await message.click(btn_info["row"], btn_info["col"])
            except Exception:
                rows = message.reply_markup.rows
                button = rows[btn_info["row"]].buttons[btn_info["col"]]
                if isinstance(button, KeyboardButtonCallback) and button.data:
                    await message.click(data=button.data)
                else:
                    raise
        else:
            await conv.send_message(btn_info["text"])

    def _get_all_text(self, message):
        parts = []
        if message.text:
            parts.append(message.text)
        rows, _ = self._get_buttons(message)
        for row in rows:
            for button in row.buttons:
                btn_text = getattr(button, "text", "")
                if btn_text:
                    parts.append(btn_text)
        return "\n".join(parts)

    def _get_all_text_from_messages(self, messages):
        parts = []
        for msg in messages:
            parts.append(self._get_all_text(msg))
        return "\n".join(parts)

    async def _collect_responses(self, conv):
        responses = []
        try:
            first = await conv.get_response()
            responses.append(first)
        except asyncio.TimeoutError:
            return responses
        for _ in range(5):
            try:
                extra = await asyncio.wait_for(conv.get_response(), timeout=2)
                responses.append(extra)
            except asyncio.TimeoutError:
                break
            except Exception:
                break
        return responses

    async def _wait_for_reply(self, conv, username):
        responses = []
        try:
            first = await conv.get_response()
            responses.append(first)
        except asyncio.TimeoutError:
            try:
                edit = await asyncio.wait_for(conv.get_edit(), timeout=3)
                if edit:
                    return [edit]
            except Exception:
                pass
            try:
                msgs = await self.client.get_messages(username, limit=3)
                if msgs:
                    return list(reversed(msgs))
            except Exception:
                pass
            return []
        for _ in range(5):
            try:
                extra = await asyncio.wait_for(conv.get_response(), timeout=1.5)
                responses.append(extra)
            except (asyncio.TimeoutError, Exception):
                break
        return responses

    def _build_result(self, username, price_data, rates):
        result = {
            "bot": f"@{username}",
            "price_rub": None,
            "original": None,
            "error": None,
        }
        if not price_data:
            result["error"] = self.strings("no_price")
            return result

        amount, currency, currency_raw = price_data
        price_rub = self._convert_to_rub(amount, currency, rates)

        if price_rub is None:
            result["price_rub"] = amount
            result["original"] = f"{amount}{currency_raw}"
            result["error"] = self.strings("rates_error")
            return result

        result["price_rub"] = price_rub
        if currency != "RUB":
            result["original"] = f"{amount}{currency_raw}"
        return result

    async def _parse_bot(self, bot_username, rates):
        username = bot_username.lstrip("@")
        error_result = {
            "bot": f"@{username}",
            "price_rub": None,
            "original": None,
            "error": None,
        }

        try:
            async with self.client.conversation(username, timeout=8) as conv:
                await conv.send_message("/start")
                all_messages = await self._collect_responses(conv)

                if not all_messages:
                    error_result["error"] = self.strings("bot_timeout")
                    return error_result

                clicked_buttons = set()

                for _ in range(4):
                    combined_text = self._get_all_text_from_messages(all_messages)

                    price_data = self._extract_price(combined_text)
                    if price_data:
                        return self._build_result(username, price_data, rates)

                    if self._check_quantity_in_messages(all_messages):
                        await conv.send_message("100")
                        await asyncio.sleep(0.5)
                        new_msgs = await self._wait_for_reply(conv, username)
                        if new_msgs:
                            all_messages.extend(new_msgs)
                        else:
                            error_result["error"] = self.strings("bot_timeout")
                            return error_result
                        continue

                    msg_with_buy, buy_btn = self._find_button_in_messages(
                        all_messages, BUY_BUTTON_KEYWORDS
                    )
                    if buy_btn and buy_btn["text"] not in clicked_buttons:
                        clicked_buttons.add(buy_btn["text"])
                        await self._click_button(conv, msg_with_buy, buy_btn)
                        await asyncio.sleep(0.5)
                        new_msgs = await self._wait_for_reply(conv, username)
                        if new_msgs:
                            all_messages.extend(new_msgs)
                        else:
                            error_result["error"] = self.strings("bot_timeout")
                            return error_result
                        continue

                    msg_with_self, self_btn = self._find_button_in_messages(
                        all_messages, SELF_BUTTON_KEYWORDS
                    )
                    if self_btn and self_btn["text"] not in clicked_buttons:
                        clicked_buttons.add(self_btn["text"])
                        await self._click_button(conv, msg_with_self, self_btn)
                        await asyncio.sleep(0.5)
                        new_msgs = await self._wait_for_reply(conv, username)
                        if new_msgs:
                            all_messages.extend(new_msgs)
                        else:
                            error_result["error"] = self.strings("bot_timeout")
                            return error_result
                        continue

                    msg_with_star, star_btn = self._find_button_in_messages(
                        all_messages, BUTTON_KEYWORDS
                    )
                    if star_btn and star_btn["text"] not in clicked_buttons:
                        clicked_buttons.add(star_btn["text"])
                        await self._click_button(conv, msg_with_star, star_btn)
                        await asyncio.sleep(0.5)
                        new_msgs = await self._wait_for_reply(conv, username)
                        if new_msgs:
                            all_messages.extend(new_msgs)
                        else:
                            error_result["error"] = self.strings("bot_timeout")
                            return error_result
                        continue

                    price_data = self._extract_unit_price(combined_text)
                    if price_data:
                        return self._build_result(username, price_data, rates)

                    price_data = self._extract_price_fallback(combined_text)
                    if price_data:
                        return self._build_result(username, price_data, rates)

                    error_result["error"] = self.strings("no_price")
                    return error_result

                combined_text = self._get_all_text_from_messages(all_messages)
                price_data = (
                    self._extract_price(combined_text)
                    or self._extract_unit_price(combined_text)
                    or self._extract_price_fallback(combined_text)
                )
                if price_data:
                    return self._build_result(username, price_data, rates)

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.exception(e)
            error_result["error"] = str(e)[:50]
            return error_result

        try:
            async with self.client.conversation(username, timeout=10) as conv:
                await conv.send_message("/start")
                retry_messages = await self._collect_responses(conv)

                if not retry_messages:
                    error_result["error"] = self.strings("bot_timeout")
                    return error_result

                msg_with_btn, first_btn = self._find_first_clickable_button(
                    retry_messages
                )
                if not first_btn:
                    error_result["error"] = self.strings("no_button")
                    return error_result

                await self._click_button(conv, msg_with_btn, first_btn)
                await asyncio.sleep(0.5)
                new_msgs = await self._wait_for_reply(conv, username)
                if new_msgs:
                    retry_messages.extend(new_msgs)

                for _ in range(3):
                    combined_text = self._get_all_text_from_messages(retry_messages)

                    price_data = self._extract_price(combined_text)
                    if price_data:
                        return self._build_result(username, price_data, rates)

                    if self._check_quantity_in_messages(retry_messages):
                        await conv.send_message("100")
                        await asyncio.sleep(0.5)
                        extra = await self._wait_for_reply(conv, username)
                        if extra:
                            retry_messages.extend(extra)
                        continue

                    price_data = (
                        self._extract_unit_price(combined_text)
                        or self._extract_price_fallback(combined_text)
                    )
                    if price_data:
                        return self._build_result(username, price_data, rates)
                    break

        except asyncio.TimeoutError:
            error_result["error"] = self.strings("bot_timeout")
            return error_result
        except Exception as e:
            logger.exception(e)
            error_result["error"] = str(e)[:50]
            return error_result

        error_result["error"] = self.strings("no_price")
        return error_result

    async def _delayed_parse(self, bot, rates, delay):
        if delay > 0:
            await asyncio.sleep(delay)
        return await self._parse_bot(bot, rates)

    async def _parse_all(self, force_refresh=False):
        bots = self.config["bots"]
        if not bots:
            return []

        cached = self.get("cached_results")
        cache_time = self.get("cache_time", 0)
        current_time = time.time()

        if not force_refresh and cached and (current_time - cache_time) < 86400:
            return cached

        self._rates = await self._fetch_rates()

        tasks = []
        for i, bot in enumerate(bots):
            tasks.append(
                asyncio.create_task(self._delayed_parse(bot, self._rates, i * 5))
            )

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results = [
            r if not isinstance(r, Exception) else {
                "bot": f"@{bots[i].lstrip('@')}",
                "price_rub": None,
                "original": None,
                "error": str(r)[:50],
            }
            for i, r in enumerate(raw_results)
        ]

        results.sort(
            key=lambda x: (x["price_rub"] is None, x["price_rub"] or float("inf"))
        )

        has_valid = any(r["price_rub"] is not None for r in results)
        if has_valid:
            self.set("cached_results", results)
            self.set("cache_time", current_time)

        return results

    def _format_results(self, results):
        if not results:
            return self.strings("no_bots")

        text = self.strings("result_header")

        for i, r in enumerate(results, 1):
            bot = utils.escape_html(r["bot"])
            if r["error"] and r["price_rub"] is None:
                text += self.strings("result_row_error").format(i, bot, r["error"])
            elif r["original"]:
                text += self.strings("result_row_converted").format(
                    i, bot, r["price_rub"], utils.escape_html(r["original"])
                )
            else:
                text += self.strings("result_row").format(
                    i, bot, f"{r['price_rub']}₽"
                )

        text += self.strings("result_footer").format(
            datetime.now().strftime("%d.%m.%Y %H:%M")
        )
        return text

    @loader.command(ru_doc=" - Показать цены на 100 звёзд в ботах")
    async def starsprice(self, message: Message):
        """ - Show prices for 100 stars in bots"""
        bots = self.config["bots"]
        if not bots:
            return await utils.answer(message, self.strings("no_bots"))

        form = await self.inline.form(
            text=self.strings("processing").format(""),
            message=message,
            reply_markup=[
                [{"text": self.strings("loading"), "action": "close"}],
            ],
        )

        results = await self._parse_all()
        text = self._format_results(results)

        await form.edit(
            text=text,
            reply_markup=[
                [{"text": "🔄 Обновить", "callback": self._refresh_cb, "style": "success"}],
                [{"text": "❌ Закрыть", "action": "close", "style": "danger"}],
            ],
        )

    async def _refresh_cb(self, call: InlineCall):
        try:
            await call.answer("🔄")
        except Exception:
            pass

        markup = [
            [{"text": "🔄 Обновить", "callback": self._refresh_cb, "style": "success"}],
            [{"text": "❌ Закрыть", "action": "close", "style": "danger"}],
        ]

        try:
            await call.edit(
                text=self.strings("processing").format(""),
                reply_markup=[[{"text": "⏳ Загрузка...", "action": "close"}]],
            )

            results = await self._parse_all(force_refresh=True)
            text = self._format_results(results)

            await call.edit(text=text, reply_markup=markup)
        except Exception as e:
            logger.exception(e)
            await call.edit(
                text=f"❌ <b>Ошибка:</b> {utils.escape_html(str(e)[:100])}",
                reply_markup=markup,
            )

    async def on_unload(self):
        pass
