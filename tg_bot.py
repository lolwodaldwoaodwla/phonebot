import telebot
import time
import os
import json
import random
import platform
import threading
from io import BytesIO
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

bot = telebot.TeleBot("8809903771:AAHqCrXvOwdIN9BElGPOfRycQaOG7S7vkVA")

BOT_START_TIME = time.time()

IMAGE_FOLDER = "images"
DATA_FILE = "bot_data.json"
_data_lock = threading.Lock()  # защита от race condition с weekly_tester_pay

rarity_chances = {
    "Ширпотреб": 34.59,
    "Необычный": 24.0,
    "Редкий": 20.0,
    "Мистический": 12.0,
    "Хроматический": 5.0,
    "Аркана": 2.5,
    "Платиновый": 1.0,
    "Артефакт": 0.4,
    "Сезонный": 0.01
}

phones = [
    # Ширпотреб
    {"name": "Motorola Defy Plus", "rarity": "Ширпотреб", "price": 1050},
    {"name": "Google Nexus One", "rarity": "Ширпотреб", "price": 600},
    {"name": "Apple iPhone 3G", "rarity": "Ширпотреб", "price": 600},
    {"name": "Apple iPhone 4", "rarity": "Ширпотреб", "price": 680},
    {"name": "Apple iPhone 5c", "rarity": "Ширпотреб", "price": 900},
    {"name": "Apple iPhone 7", "rarity": "Ширпотреб", "price": 1500},
    {"name": "HTC Sensation", "rarity": "Ширпотреб", "price": 600},
    {"name": "LG Optimus 3D P920", "rarity": "Ширпотреб", "price": 980},
    {"name": "Samsung N7000 Galaxy Note", "rarity": "Ширпотреб", "price": 600},
    {"name": "Samsung N7000 Galaxy Note (Белый)", "rarity": "Ширпотреб", "price": 600},
    {"name": "Samsung i9300 Galaxy S III", "rarity": "Ширпотреб", "price": 1050},
    {"name": "Samsung Galaxy S4 GT-I9500", "rarity": "Ширпотреб", "price": 600},
    {"name": "Samsung Galaxy Note 4", "rarity": "Ширпотреб", "price": 1100},
    {"name": "HTC One X", "rarity": "Ширпотреб", "price": 750},
    {"name": "HTC One M7", "rarity": "Ширпотреб", "price": 750},
    # Необычный
    {"name": "Sony Xperia Z5", "rarity": "Необычный", "price": 2250},
    {"name": "Google Pixel XL", "rarity": "Необычный", "price": 2250},
    {"name": "Essential Phone", "rarity": "Необычный", "price": 3000},
    {"name": "Meizu 16th", "rarity": "Необычный", "price": 3000},
    {"name": "Nokia 8", "rarity": "Необычный", "price": 3000},
    {"name": "Huawei Mate 10 Pro", "rarity": "Необычный", "price": 3000},
    # Редкий
    {"name": "Apple iPhone X", "rarity": "Редкий", "price": 7500},
    {"name": "Apple iPhone Xs", "rarity": "Редкий", "price": 7500},
    {"name": "Apple iPhone Xs Max", "rarity": "Редкий", "price": 8250},
    {"name": "Apple iPhone XR", "rarity": "Редкий", "price": 7500},
    {"name": "Apple iPhone 11", "rarity": "Редкий", "price": 8600},
    {"name": "Apple iPhone 11 Pro", "rarity": "Редкий", "price": 12400},
    # Мистический
    {"name": "Huawei Mate X", "rarity": "Мистический", "price": 38200},
    {"name": "Huawei Mate 40 Pro", "rarity": "Мистический", "price": 35200},
    {"name": "Samsung Galaxy S20 Ultra", "rarity": "Мистический", "price": 24800},
    {"name": "Samsung Galaxy S22 Ultra", "rarity": "Мистический", "price": 41200},
    {"name": "Vivo X Fold", "rarity": "Мистический", "price": 28500},
    # Хроматический
    {"name": "Honor 200 Pro", "rarity": "Хроматический", "price": 52500},
    {"name": "Honor Magic V2", "rarity": "Хроматический", "price": 78800},
    {"name": "Xiaomi 13 Ultra", "rarity": "Хроматический", "price": 82500},
    {"name": "Nothing Phone 2", "rarity": "Хроматический", "price": 63800},
    {"name": "Nothing Phone 2a", "rarity": "Хроматический", "price": 46500},
    # Аркана
    {"name": "Vivo X200", "rarity": "Аркана", "price": 131200},
    {"name": "Vivo X200 FE", "rarity": "Аркана", "price": 135000},
    {"name": "Vivo X200 Pro", "rarity": "Аркана", "price": 142500},
    {"name": "Vivo X200 Pro Mini", "rarity": "Аркана", "price": 138800},
    {"name": "Vivo X200s", "rarity": "Аркана", "price": 127500},
    # Платиновый
    {"name": "Apple iPhone 17", "rarity": "Платиновый", "price": 290000},
    {"name": "Apple iPhone 17 Pro", "rarity": "Платиновый", "price": 315000},
    {"name": "Apple iPhone 17 Pro Max", "rarity": "Платиновый", "price": 335000},
    {"name": "Xiaomi 17", "rarity": "Платиновый", "price": 280000},
    # Артефакт
    {"name": "Xiaomi 13 Pro", "rarity": "Артефакт", "price": 500000},
    {"name": "Xiaomi Poco X3", "rarity": "Артефакт", "price": 500000},
    {"name": "Яндекс.Телефон", "rarity": "Артефакт", "price": 500000},
    {"name": "Apple iPhone 17 Air", "rarity": "Артефакт", "price": 500000},
    # Сезонный (пока 0% шанс)
    {"name": "Samsung Galaxy S26 Ultra PhoneGet 1st Anniversary Edition", "rarity": "Сезонный", "price": 3750000},
    {"name": "Vivo X300 Ultra PhoneGet 1st Anniversary Edition", "rarity": "Сезонный", "price": 3750000},
    {"name": "Apple iPhone 17 Pro Max PhoneGet 1st Anniversary Edition", "rarity": "Сезонный", "price": 3750000},
    {"name": "Xiaomi 17 Ultra PhoneGet 1st Anniversary Edition", "rarity": "Сезонный", "price": 3750000},
    {"name": "Huawei Pura 90 Pro Max PhoneGet 1st Anniversary Edition", "rarity": "Сезонный", "price": 3750000}
]

rarity_icons = {
    "Ширпотреб": "📱",
    "Необычный": "📲",
    "Редкий": "⭐",
    "Мистический": "✨",
    "Хроматический": "🔮",
    "Аркана": "🏆",
    "Платиновый": "💠",
    "Артефакт": "💎",
    "Сезонный": "🗓"
}

def load_data():
    with _data_lock:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                print("Ошибка: bot_data.json повреждён, создаём заново...")
                data = {}
        else:
            data = {}
        # Гарантируем наличие настроек бота
        if "_settings" not in data:
            data["_settings"] = {
                "broken_chance_default": 20,  # %
                "broken_chance_ultra": 5,     # %
                "broken_chance_creator": 0    # %
            }
        return data

def save_data(data):
    with _data_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(user_id, username):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "points": 0,
            "tcoins": 0,
            "cards": 0,
            "phones_value": 0,
            "achievements": 0,
            "profile_views": 0,
            "viewed_by": [],
            "status": "Обычный",
            "username": username or "",
            "collection": {},
            "last_card_time": 0,
            "card_cooldown": 10800,
            "rarity_chances": {},
            "last_dropped": []
        }
        save_data(data)
    else:
        changed = False
        if "collection" not in data[uid]:
            data[uid]["collection"] = {}
            changed = True
        if "last_card_time" not in data[uid]:
            data[uid]["last_card_time"] = 0
            changed = True
        if "card_cooldown" not in data[uid]:
            data[uid]["card_cooldown"] = 10800
            changed = True
        if "rarity_chances" not in data[uid]:
            data[uid]["rarity_chances"] = {}
            changed = True
        if "last_dropped" not in data[uid]:
            data[uid]["last_dropped"] = []
            changed = True
        if changed:
            save_data(data)
    return data[uid]

def update_user(user_id, udata):
    data = load_data()
    data[str(user_id)] = udata
    save_data(data)

def find_image(phone_name):
    if not os.path.exists(IMAGE_FOLDER):
        return None
    for f in os.listdir(IMAGE_FOLDER):
        name_no_ext = os.path.splitext(f)[0].lower()
        if name_no_ext == phone_name.lower():
            return os.path.join(IMAGE_FOLDER, f)
    return None

def get_user_chances(user_id):
    udata = get_user_data(user_id, "")
    drop_lvl = udata.get("drop_chance_level", 0)
    if 0 < drop_lvl < len(UPG_DROP_LEVELS):
        return dict(UPG_DROP_LEVELS[drop_lvl])
    return dict(rarity_chances)

def get_random_phone(user_id=None):
    if user_id:
        chances = get_user_chances(user_id)
    else:
        chances = rarity_chances

    # Получаем последние 3 телефона для анти-повтора
    recent = []
    if user_id:
        udata = get_user_data(user_id, "")
        recent = udata.get("last_dropped", [])

    # До 10 попыток найти телефон, который не был в последних 3
    for _ in range(10):
        rarity_list = list(chances.keys())
        weights = list(chances.values())
        rolled_rarity = random.choices(rarity_list, weights=weights, k=1)[0]
        rarity_phones = [p for p in phones if p["rarity"] == rolled_rarity and p["name"] not in recent]
        if rarity_phones:
            phone = random.choice(rarity_phones)
            # Сохраняем в последние выпавшие
            recent.append(phone["name"])
            recent = recent[-3:]  # храним только последние 3
            udata["last_dropped"] = recent
            update_user(user_id, udata)
            return phone
        # Если все телефоны этой редкости в recent — берём любые
        rarity_phones = [p for p in phones if p["rarity"] == rolled_rarity]
        if rarity_phones:
            phone = random.choice(rarity_phones)
            recent.append(phone["name"])
            recent = recent[-3:]
            udata["last_dropped"] = recent
            update_user(user_id, udata)
            return phone

    # Фоллбэк
    fallback = [p for p in phones if p["rarity"] == "Ширпотреб" and p["name"] not in recent]
    if not fallback:
        fallback = [p for p in phones if p["rarity"] == "Ширпотреб"]
    return random.choice(fallback)

BROKEN_REASONS = [
    "Ваш телефон был забракован на заводе, из-за чего приехал нерабочим.",
    "Служба доставки не уследила за качеством транспортировки, из-за чего ваш телефон был сломан.",
    "По дороге курьер уронил коробку, и телефон повредился.",
]

ALL_DAMAGES = [
    "разбитый экран", "сгоревший чип", "вздутый аккумулятор",
    "отвал памяти", "сломанная материнская плата"
]

# Причины → возможные поломки (логика: от чего повредился — те и поломки)
REASON_DAMAGES = {
    0: [0, 2],         # завод: разбитый экран + вздутый аккумулятор
    1: [0, 1, 3],      # доставка: разбитый экран + сгоревший чип + отвал памяти
    2: [0, 4],         # курьер: разбитый экран + сломанная материнская плата
}


def generate_broken_info():
    """Генерирует причину поломки и список поломок."""
    reason_idx = random.randint(0, len(BROKEN_REASONS) - 1)
    reason = BROKEN_REASONS[reason_idx]
    # Берём 1-2 поломки из подходящих для этой причины
    possible = REASON_DAMAGES.get(reason_idx, [0, 1])
    count = random.randint(1, 2)
    chosen = random.sample(possible, min(count, len(possible)))
    damages = [ALL_DAMAGES[i] for i in chosen]
    return reason, damages


def get_card_text(user_name, phone, broken=False, reason="", damages=None):
    icon = rarity_icons.get(phone['rarity'], "📱")
    price_display = 0 if broken else phone['price']
    text = (
        f"{user_name}, вам выпал телефон!\n\n"
        f"{icon} {phone['name']}\n"
        f"Редкость: {phone['rarity']} | Цена: {price_display} ПОчек"
    )
    if broken:
        text += f"\n\n{reason}\n\nПоломки: {', '.join(damages)}"
    return text

def add_phone_to_collection(user_id, phone, broken=False, damages=None):
    udata = get_user_data(user_id, "")
    # Сломанные — в broken_collection, рабочие — в collection
    if broken:
        bc = udata.get("broken_collection", {})
        key = phone["name"]
        if key in bc:
            bc[key]["count"] += 1
        else:
            bc[key] = {
                "rarity": phone["rarity"],
                "price": 0,
                "count": 1,
                "damages": damages or [],
            }
        udata["broken_collection"] = bc
    else:
        collection = udata.get("collection", {})
        if phone["name"] in collection:
            collection[phone["name"]]["count"] += 1
        else:
            collection[phone["name"]] = {
                "rarity": phone["rarity"],
                "price": phone["price"],
                "count": 1
            }
        udata["collection"] = collection
        udata["phones_value"] = udata.get("phones_value", 0) + phone["price"]
    udata["cards"] = udata.get("cards", 0) + 1
    update_user(user_id, udata)

_card_actions = {}  # user_id -> {name, price, rarity, sell_price, message_id, chat_id, has_photo, original_text}
_card_lock = {}    # user_id -> True  защита от двойного срабатывания пкарточки
_inv_action = {}    # user_id -> {phone_name, rarity, price, sell_price, msg_id, has_photo}
_inv_main_msg = {}  # user_id -> {msg_id, has_photo}
_upg_shop_msg = {}  # user_id -> {msg_id, has_photo}
_pay_pending = {}   # user_id -> {target_id, amount, target_display, msg_id, chat_id, comment}
_paycoin_pending = {}  # user_id -> {target_id, amount, target_display, sender_name, msg_id, chat_id}

def send_card(message, phone):
    # Шанс сломанного телефона из настроек
    data = load_data()
    settings = data.get("_settings", {})
    status = get_user_data(message.from_user.id, "").get("status", "Обычный")

    if "Создатель" in status:
        chance = settings.get("broken_chance_creator", 0) / 100
    elif "Ultra" in status:
        chance = settings.get("broken_chance_ultra", 5) / 100
    else:
        chance = settings.get("broken_chance_default", 20) / 100

    broken = random.random() < chance
    reason = ""
    damages = []
    if broken:
        reason, damages = generate_broken_info()

    add_phone_to_collection(message.from_user.id, phone, broken=broken, damages=damages)
    text = get_card_text(message.from_user.first_name, phone, broken=broken, reason=reason, damages=damages)

    if not broken:
        sell_price = int(phone["price"] * 0.75)
    else:
        sell_price = 0

    uid = message.from_user.id
    _card_actions[uid] = {
        "name": phone["name"],
        "price": 0 if broken else phone["price"],
        "rarity": phone["rarity"],
        "sell_price": sell_price,
        "broken": broken,
    }

    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(telebot.types.InlineKeyboardButton(text="🛒 Действие", callback_data="ca_menu"))

    img = find_image(phone["name"])
    if img:
        with open(img, "rb") as photo:
            msg = bot.send_photo(message.chat.id, photo, caption=text, reply_markup=markup)
        _card_actions[uid]["has_photo"] = True
    else:
        msg = bot.send_message(message.chat.id, text, reply_markup=markup)
        _card_actions[uid]["has_photo"] = False

    _card_actions[uid]["message_id"] = msg.message_id
    _card_actions[uid]["chat_id"] = msg.chat.id
    _card_actions[uid]["original_text"] = text

def check_cooldown(user_id):
    udata = get_user_data(user_id, "")
    last = udata.get("last_card_time", 0)
    cooldown = udata.get("card_cooldown", 10800)
    now = int(time.time())
    remaining = cooldown - (now - last)
    if remaining > 0:
        return remaining
    return 0

def format_cooldown(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h} ч {m} мин {s} сек"

def _try_lock_card(uid):
    if _card_lock.get(uid):
        return False
    _card_lock[uid] = True
    return True


def _unlock_card(uid):
    _card_lock.pop(uid, None)


def _do_pcard(message):
    uid = message.from_user.id
    remaining = check_cooldown(uid)
    if remaining > 0:
        name = message.from_user.first_name or "игрок"
        bot.send_message(message.chat.id, f"{name}, вы сможете выбить карту еще раз через {format_cooldown(remaining)}.")
        return
    phone = get_random_phone(uid)
    send_card(message, phone)
    udata = get_user_data(uid, "")
    udata["last_card_time"] = int(time.time())
    update_user(uid, udata)


@bot.message_handler(commands=["pcard"])
def cmd_pcard(message):
    uid = message.from_user.id
    if not _try_lock_card(uid):
        return
    try:
        _do_pcard(message)
    finally:
        _unlock_card(uid)

@bot.message_handler(func=lambda m: m.text and m.text.lower() == "пкарточка")
def text_pcard(message):
    uid = message.from_user.id
    if not _try_lock_card(uid):
        return
    try:
        _do_pcard(message)
    finally:
        _unlock_card(uid)

def parse_pay_amount(text):
    """Парсит сумму с поддержкой 'к' (тысяча) и 'кк' (миллион)."""
    text = text.lower().strip().replace(" ", "")
    if text.endswith("кк"):
        num = text[:-2]
        try:
            return int(float(num) * 1_000_000)
        except ValueError:
            return None
    elif text.endswith("к"):
        num = text[:-1]
        try:
            return int(float(num) * 1_000)
        except ValueError:
            return None
    else:
        try:
            return int(text)
        except ValueError:
            return None

@bot.message_handler(commands=["pay"])
def cmd_pay(message):
    help_text = (
        "Использование:\n"
        "1. Ответом на сообщение: `/pay <сумма> [комментарий]`\n"
        "2. По юзернейму: `/pay @username <сумма> [комментарий]`\n"
        "3. По ID: `/pay <user_id> <сумма> [комментарий]`\n\n"
        "💡 Подсказка: Сумму можно писать с буквами 'к' (тысяча) и 'кк' (миллион)."
    )
    args = message.text.split()
    if len(args) < 2 and not message.reply_to_message:
        bot.reply_to(message, help_text, parse_mode="Markdown")
        return
    if not message.reply_to_message and len(args) < 3:
        bot.reply_to(message, help_text, parse_mode="Markdown")
        return

    target_id = None
    amount_str = None
    comment = ""
    target_display = ""

    # Способ 1: ответом на сообщение
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_user = message.reply_to_message.from_user
        target_display = target_user.first_name or target_user.username or f"ID: {target_id}"
        rest = " ".join(args[1:])
        parts = rest.split(maxsplit=1)
        if not parts:
            bot.reply_to(message, help_text, parse_mode="Markdown")
            return
        amount_str = parts[0]
        if len(parts) > 1:
            comment = parts[1]
    else:
        if args[1].startswith("@"):
            username_target = args[1][1:].lower()
            data = load_data()
            found = False
            for uid_str, udata in data.items():
                if udata.get("username", "").lower() == username_target:
                    target_id = int(uid_str)
                    found = True
                    break
            if not found:
                bot.reply_to(message, "❌ Пользователь не найден. Убедитесь, что он использовал бота.", parse_mode="Markdown")
                return
            target_display = f"@{username_target}"
            rest_parts = args[2:]
            if not rest_parts:
                bot.reply_to(message, help_text, parse_mode="Markdown")
                return
            amount_str = rest_parts[0]
            if len(rest_parts) > 1:
                comment = " ".join(rest_parts[1:])
        else:
            try:
                target_id = int(args[1])
            except ValueError:
                bot.reply_to(message, help_text, parse_mode="Markdown")
                return
            target_display = f"ID: {target_id}"
            if len(args) < 3:
                bot.reply_to(message, help_text, parse_mode="Markdown")
                return
            rest_parts = args[2:]
            amount_str = rest_parts[0]
            if len(rest_parts) > 1:
                comment = " ".join(rest_parts[1:])

    amount = parse_pay_amount(amount_str)
    if amount is None or amount <= 0:
        bot.reply_to(message, "❌ Некорректная сумма.", parse_mode="Markdown")
        return

    if target_id == message.from_user.id:
        bot.reply_to(message, "❌ Нельзя перевести самому себе.", parse_mode="Markdown")
        return

    sender_data = get_user_data(message.from_user.id, "")
    sender_points = sender_data.get("points", 0)
    if sender_points < amount:
        name = message.from_user.first_name or "Игрок"
        bot.reply_to(message, f"❌ {name}, у вас недостаточно ПОчек. Ваш баланс: {sender_points} ПОчек.", parse_mode="Markdown")
        return

    # Показываем подтверждение
    sender_name = message.from_user.first_name or "Игрок"
    text = f"{sender_name}, Вы уверены, что хотите передать {amount} ПОчек пользователю {target_display}?"
    if comment:
        text += f"\n\n📝 С комментарием: \"{comment}\""
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="pay_ok"),
        telebot.types.InlineKeyboardButton(text="❌ Отмена", callback_data="pay_no"),
    )
    msg = bot.reply_to(message, text, parse_mode="Markdown", reply_markup=markup)

    _pay_pending[message.from_user.id] = {
        "target_id": target_id,
        "amount": amount,
        "target_display": target_display,
        "sender_name": sender_name,
        "msg_id": msg.message_id,
        "chat_id": msg.chat.id,
        "comment": comment,
    }

@bot.callback_query_handler(func=lambda call: call.data == "pay_ok")
def pay_ok(call):
    uid = call.from_user.id
    pay = _pay_pending.get(uid)
    if not pay:
        bot.answer_callback_query(call.id, "Транзакция не найдена", show_alert=True)
        return

    # Списываем и начисляем
    sender_data = get_user_data(uid, "")
    sender_data["points"] = sender_data.get("points", 0) - pay["amount"]
    update_user(uid, sender_data)

    target_data = get_user_data(pay["target_id"], "")
    target_data["points"] = target_data.get("points", 0) + pay["amount"]
    update_user(pay["target_id"], target_data)

    # Редактируем сообщение отправителя
    text = f"{pay['sender_name']}, Вы успешно перевели {pay['amount']} ПОчек пользователю {pay['target_display']}."
    if pay.get("comment"):
        text += f"\n\n📝 С комментарием: \"{pay['comment']}\""
    try:
        bot.edit_message_text(
            chat_id=pay["chat_id"], message_id=pay["msg_id"],
            text=text
        )
    except:
        pass

    # Уведомляем получателя
    try:
        notif = f"🎁 Вам пришел перевод: {pay['amount']} ПОчек от пользователя {pay['sender_name']}!"
        if pay.get("comment"):
            notif += f"\n\n📝 С комментарием: \"{pay['comment']}\""
        bot.send_message(
            pay["target_id"],
            notif
        )
    except:
        pass

    _pay_pending.pop(uid, None)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "pay_no")
def pay_no(call):
    uid = call.from_user.id
    pay = _pay_pending.get(uid)
    if not pay:
        bot.answer_callback_query(call.id)
        return
    try:
        bot.delete_message(pay["chat_id"], pay["msg_id"])
    except:
        pass
    _pay_pending.pop(uid, None)
    bot.answer_callback_query(call.id)


@bot.message_handler(commands=["paycoin"])
def cmd_paycoin(message):
    help_text = (
        "Использование:\n"
        "1. Ответом на сообщение: `/paycoin <сумма> [комментарий]`\n"
        "2. По юзернейму: `/paycoin @username <сумма> [комментарий]`\n"
        "3. По ID: `/paycoin <user_id> <сумма> [комментарий]`\n\n"
        "💡 Подсказка: Сумму можно писать с буквами 'к' (тысяча) и 'кк' (миллион)."
    )
    args = message.text.split()
    if len(args) < 2 and not message.reply_to_message:
        bot.reply_to(message, help_text, parse_mode="Markdown")
        return
    if not message.reply_to_message and len(args) < 3:
        bot.reply_to(message, help_text, parse_mode="Markdown")
        return

    target_id = None
    amount_str = None
    comment = ""
    target_display = ""

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_user = message.reply_to_message.from_user
        target_display = target_user.first_name or target_user.username or f"ID: {target_id}"
        rest = " ".join(args[1:])
        parts = rest.split(maxsplit=1)
        if not parts:
            bot.reply_to(message, help_text, parse_mode="Markdown")
            return
        amount_str = parts[0]
        if len(parts) > 1:
            comment = parts[1]
    else:
        if args[1].startswith("@"):
            username_target = args[1][1:].lower()
            data = load_data()
            found = False
            for uid_str, udata in data.items():
                if udata.get("username", "").lower() == username_target:
                    target_id = int(uid_str)
                    found = True
                    break
            if not found:
                bot.reply_to(message, "❌ Пользователь не найден. Убедитесь, что он использовал бота.", parse_mode="Markdown")
                return
            target_display = f"@{username_target}"
            if len(args) < 3:
                bot.reply_to(message, help_text, parse_mode="Markdown")
                return
            amount_str = args[2]
            if len(args) > 3:
                comment = " ".join(args[3:])
        else:
            try:
                target_id = int(args[1])
            except ValueError:
                bot.reply_to(message, help_text, parse_mode="Markdown")
                return
            target_display = f"ID: {target_id}"
            if len(args) < 3:
                bot.reply_to(message, help_text, parse_mode="Markdown")
                return
            amount_str = args[2]
            if len(args) > 3:
                comment = " ".join(args[3:])

    amount = parse_pay_amount(amount_str)
    if amount is None or amount <= 0:
        bot.reply_to(message, "❌ Некорректная сумма.", parse_mode="Markdown")
        return

    if target_id == message.from_user.id:
        bot.reply_to(message, "❌ Нельзя перевести самому себе.", parse_mode="Markdown")
        return

    sender_data = get_user_data(message.from_user.id, "")
    sender_coins = sender_data.get("tcoins", 0)
    if sender_coins < amount:
        name = message.from_user.first_name or "Игрок"
        bot.reply_to(message, f"❌ {name}, у вас недостаточно P-Coins. Ваш баланс: {sender_coins} P-Coins.", parse_mode="Markdown")
        return

    sender_name = message.from_user.first_name or "Игрок"
    text = (
        f"⚠️ ПОДТВЕРЖДЕНИЕ ПЕРЕВОДА ЦЕННОЙ ВАЛЮТЫ ⚠️\n\n"
        f"{sender_name}, вы собираетесь перевести {amount} P-Coins пользователю {target_display}.\n\n"
        f"❗️ Внимание: P-Coins являются донатной валютой. Убедитесь, что вы доверяете получателю. Это действие необратимо."
    )
    if comment:
        text += f"\n\n📝 С комментарием: \"{comment}\""
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="paycoin_ok"),
        telebot.types.InlineKeyboardButton(text="❌ Отмена", callback_data="paycoin_no"),
    )
    msg = bot.reply_to(message, text, parse_mode="Markdown", reply_markup=markup)

    _paycoin_pending[message.from_user.id] = {
        "target_id": target_id,
        "amount": amount,
        "target_display": target_display,
        "sender_name": sender_name,
        "msg_id": msg.message_id,
        "chat_id": msg.chat.id,
        "comment": comment,
    }


@bot.callback_query_handler(func=lambda call: call.data == "paycoin_ok")
def paycoin_ok(call):
    uid = call.from_user.id
    pay = _paycoin_pending.get(uid)
    if not pay:
        bot.answer_callback_query(call.id, "Транзакция не найдена", show_alert=True)
        return

    sender_data = get_user_data(uid, "")
    sender_data["tcoins"] = sender_data.get("tcoins", 0) - pay["amount"]
    update_user(uid, sender_data)

    target_data = get_user_data(pay["target_id"], "")
    target_data["tcoins"] = target_data.get("tcoins", 0) + pay["amount"]
    update_user(pay["target_id"], target_data)

    text = f"{pay['sender_name']}, вы успешно перевели {pay['amount']} P-Coins пользователю {pay['target_display']}."
    if pay.get("comment"):
        text += f"\n\n📝 С комментарием: \"{pay['comment']}\""
    try:
        bot.edit_message_text(
            chat_id=pay["chat_id"], message_id=pay["msg_id"],
            text=text
        )
    except:
        pass

    try:
        notif = f"🎁 Вам пришел перевод: {pay['amount']} P-Coins от пользователя {pay['sender_name']}!"
        if pay.get("comment"):
            notif += f"\n\n📝 С комментарием: \"{pay['comment']}\""
        bot.send_message(
            pay["target_id"],
            notif
        )
    except:
        pass

    _paycoin_pending.pop(uid, None)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "paycoin_no")
def paycoin_no(call):
    uid = call.from_user.id
    pay = _paycoin_pending.get(uid)
    if not pay:
        bot.answer_callback_query(call.id)
        return
    try:
        bot.delete_message(pay["chat_id"], pay["msg_id"])
    except:
        pass
    _paycoin_pending.pop(uid, None)
    bot.answer_callback_query(call.id)


def get_avatar(user_id):
    try:
        photos = bot.get_user_profile_photos(user_id)
        if photos.total_count == 0:
            return None
        photo = photos.photos[0][-1]
        file_info = bot.get_file(photo.file_id)
        url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        response = requests.get(url, timeout=5)
        return Image.open(BytesIO(response.content)).convert("RGBA")
    except:
        return None

def _draw_rainbow_ring(draw, cx, cy, outer_r, ring_w, alpha=255):
    """Рисует плавное радужное кольцо через arc() — без квадратных артефактов."""
    colors = [
        (255, 50, 50), (255, 140, 0), (255, 230, 0),
        (50, 205, 50), (0, 160, 255), (100, 50, 200), (180, 50, 255)
    ]
    n = len(colors)
    seg = 10  # сегментов на цвет
    total = n * seg
    bbox = [(cx - outer_r, cy - outer_r), (cx + outer_r, cy + outer_r)]
    for i in range(total):
        a1 = i * (360.0 / total)
        a2 = (i + 1) * (360.0 / total) + 0.5
        c = colors[(i // seg) % n]
        draw.arc(bbox, a1, a2, fill=c + (alpha,), width=ring_w)


def make_circle_avatar(img, size, rainbow=False):
    img = img.resize((size, size), Image.LANCZOS)
    ring_w = 6
    inner = size - ring_w * 2
    cx, cy = size // 2, size // 2

    # Маска для аватарки (круг внутри кольца)
    mask = Image.new("L", (size, size), 0)
    draw_m = ImageDraw.Draw(mask)
    r_inner = inner // 2
    draw_m.ellipse([(cx - r_inner, cy - r_inner), (cx + r_inner, cy + r_inner)], fill=255)
    avatar_rgba = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    avatar_rgba.paste(img, (0, 0), mask)

    # Слой для кольца
    ring_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring_layer)

    if rainbow:
        _draw_rainbow_ring(rd, cx, cy, size // 2 - 1, ring_w)
    else:
        rd.ellipse([(1, 1), (size - 2, size - 2)], outline=(255, 255, 255, 255), width=ring_w)

    # Композитим: кольцо под аватаркой
    output = Image.alpha_composite(ring_layer, avatar_rgba)
    return output

def get_font(size, bold=False):
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuibd.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except:
                pass
    return ImageFont.load_default()

def create_inventory_header(user_name):
    w, h = 500, 180
    card = Image.new("RGBA", (w, h), (15, 15, 25, 255))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=16, fill=(15, 15, 25, 255), outline=(60, 60, 80, 200), width=2)
    font_title = get_font(28, bold=True)
    font_sub = get_font(16)
    title = "МОИ ТЕЛЕФОНЫ"
    tb = draw.textbbox((0, 0), title, font=font_title)
    tw = tb[2] - tb[0]
    draw.text(((w - tw) // 2, 40), title, fill=(200, 200, 255, 255), font=font_title)
    sub = f"Коллекция {user_name}"
    sb = draw.textbbox((0, 0), sub, font=font_sub)
    sw = sb[2] - sb[0]
    draw.text(((w - sw) // 2, 90), sub, fill=(140, 140, 180, 255), font=font_sub)
    return card

def send_inv_photo(chat_id, user_name, caption, markup):
    img = create_inventory_header(user_name)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    bot.send_photo(chat_id, buf, caption=caption, parse_mode="Markdown", reply_markup=markup)

def edit_inv_message(chat_id, message_id, caption, markup):
    bot.edit_message_caption(
        chat_id=chat_id,
        message_id=message_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=markup
    )

def get_user_rank_by_points(user_id):
    """Возвращает место в топе по количеству ПОчек (1 = первое место)."""
    data = load_data()
    scores = []
    for uid_str, uinfo in data.items():
        try:
            scores.append((int(uid_str), uinfo.get("points", 0)))
        except ValueError:
            continue
    scores.sort(key=lambda x: x[1], reverse=True)
    for i, (uid, _) in enumerate(scores):
        if uid == user_id:
            return i + 1
    return len(scores) + 1


def create_profile_card(udata, avatar_img, target_user):
    w, h = 500, 200
    # Фон: аватарка блюренная + тёмный оверлей
    if avatar_img:
        bg = avatar_img.resize((w, h), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(18))
        dark = Image.new("RGBA", (w, h), (0, 0, 0, 150))
        bg = Image.alpha_composite(bg, dark)
        card = bg
    else:
        card = Image.new("RGBA", (w, h), (20, 20, 35, 255))

    # Компактная плашка — только правая часть (текст), аватарка на чистом фоне
    avatar_size = 100
    ax = 28
    panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    px1 = ax + avatar_size + 12
    py1 = 15
    px2 = w - 15
    py2 = h - 15
    pd.rounded_rectangle(
        [(px1, py1), (px2, py2)],
        radius=12, fill=(20, 20, 40, 130)
    )
    pd.rounded_rectangle(
        [(px1, py1), (px2, py2)],
        radius=12, outline=(255, 255, 255, 40), width=1
    )
    card = Image.alpha_composite(card, panel)

    # Аватарка (на чистом фоне слева)
    ay = (h - avatar_size) // 2

    if avatar_img:
        avatar = make_circle_avatar(avatar_img, avatar_size, rainbow=True)
        card.paste(avatar, (ax, ay), avatar)
    else:
        no_av = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
        na_d = ImageDraw.Draw(no_av)
        cx = avatar_size // 2
        cy = avatar_size // 2
        _draw_rainbow_ring(na_d, cx, cy, avatar_size // 2 - 1, 5)
        r_inner = avatar_size // 2 - 6
        na_d.ellipse([(cx - r_inner, cy - r_inner), (cx + r_inner, cy + r_inner)], fill=(40, 40, 60, 255))
        head_r = 15
        head_y = cy - 16
        na_d.ellipse([(cx - head_r, head_y), (cx + head_r, head_y + head_r * 2)], fill=(80, 80, 110, 255))
        body_top = head_y + head_r * 2 + 4
        na_d.ellipse([(cx - 24, body_top), (cx + 24, body_top + 34)], fill=(80, 80, 110, 255))
        card.paste(no_av, (ax, ay), no_av)

    # Текст внутри плашки
    draw = ImageDraw.Draw(card)
    username = target_user.first_name or target_user.username or "Unknown"

    font_name = get_font(18, bold=True)
    font_stat = get_font(14)
    font_rank = get_font(15, bold=True)

    text_x = px1 + 16
    text_y = 30

    draw.text((text_x, text_y), username, fill=(255, 255, 255, 255), font=font_name)

    rank = get_user_rank_by_points(target_user.id)
    draw.text((text_x, text_y + 32), f"Место в топе: {rank}", fill=(180, 130, 255, 255), font=font_rank)

    pts = udata.get("points", 0)
    pts_str = f"{pts:,}".replace(",", " ")
    draw.text((text_x, text_y + 60), f"ПОчек: {pts_str}", fill=(180, 130, 255, 255), font=font_stat)

    cards_count = udata.get("cards", 0)
    draw.text((text_x, text_y + 85), f"Карточек: {cards_count}", fill=(180, 130, 255, 255), font=font_stat)

    return card

@bot.message_handler(commands=["paccount"])
def cmd_paccount(message):
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    else:
        target = message.from_user

    udata = get_user_data(target.id, target.username)

    if message.from_user.id != target.id:
        viewer_id = str(message.from_user.id)
        viewed_by = udata.get("viewed_by", [])
        if viewer_id not in viewed_by:
            viewed_by.append(viewer_id)
            udata["viewed_by"] = viewed_by
            udata["profile_views"] = len(viewed_by)
            data = load_data()
            data[str(target.id)] = udata
            save_data(data)

    avatar = get_avatar(target.id)
    card_img = create_profile_card(udata, avatar, target)

    buf = BytesIO()
    card_img.save(buf, format="PNG")
    buf.seek(0)

    name = target.first_name or target.username or "игрок"

    caption = (
        f"👤 Профиль: {name}\n"
        f"📈 Статус: {udata.get('status', 'Обычный')}\n"
        f"💰 ПОчки: {udata.get('points', 0)}\n"
        f"💠 P-Coins: {udata.get('tcoins', 0)}\n"
        f"📱 Общая стоимость телефонов: {udata.get('phones_value', 0)}\n"
        f"🃏 Телефонов в коллекции: {udata.get('cards', 0)}\n"
        f"🏆 Выполнено достижений: {udata.get('achievements', 0)}\n"
        f"👁 Ваш профиль просмотрело {udata.get('profile_views', 0)} игроков."
    )

    bot.send_photo(
        message.chat.id, buf,
        caption=caption
    )

@bot.message_handler(func=lambda m: m.text and m.text.lower() == "пакк")
def text_paccount(message):
    cmd_paccount(message)

def get_rarities_from_collection(user_id):
    udata = get_user_data(user_id, "")
    collection = udata.get("collection", {})
    rarities = {}
    for phone_name, info in collection.items():
        rarity = info["rarity"]
        if rarity not in rarities:
            rarities[rarity] = 0
        rarities[rarity] += info["count"]
    return rarities

def get_phones_by_rarity(user_id, rarity):
    udata = get_user_data(user_id, "")
    collection = udata.get("collection", {})
    result = []
    for phone_name, info in collection.items():
        if info["rarity"] == rarity:
            result.append({"name": phone_name, "count": info["count"], "rarity": info["rarity"], "price": info["price"]})
    return result


def get_broken_phones(user_id):
    udata = get_user_data(user_id, "")
    bc = udata.get("broken_collection", {})
    result = []
    for phone_name, info in bc.items():
        result.append({
            "name": phone_name,
            "count": info["count"],
            "rarity": info["rarity"],
            "damages": info.get("damages", [])
        })
    return result


def get_broken_rarities(user_id):
    udata = get_user_data(user_id, "")
    bc = udata.get("broken_collection", {})
    rarities = {}
    for phone_name, info in bc.items():
        rarity = info["rarity"]
        if rarity not in rarities:
            rarities[rarity] = 0
        rarities[rarity] += info["count"]
    return rarities


def get_broken_phones_by_rarity(user_id, rarity):
    udata = get_user_data(user_id, "")
    bc = udata.get("broken_collection", {})
    result = []
    for phone_name, info in bc.items():
        if info["rarity"] == rarity:
            result.append({"name": phone_name, "count": info["count"], "rarity": info["rarity"], "damages": info.get("damages", [])})
    return result


def inv_broken_rarities_markup(user_id):
    rarities = get_broken_rarities(user_id)
    markup = telebot.types.InlineKeyboardMarkup()
    for rarity, count in rarities.items():
        icon = rarity_icons.get(rarity, "📱")
        markup.add(telebot.types.InlineKeyboardButton(text=f"{icon} {rarity} ({count})", callback_data=f"inv_bcat_{rarity}"))
    markup.add(telebot.types.InlineKeyboardButton(text="📁 Назад", callback_data="inv_back_main"))
    return markup


def inv_broken_phones_markup(user_id, rarity):
    phones_list = get_broken_phones_by_rarity(user_id, rarity)
    markup = telebot.types.InlineKeyboardMarkup()
    for p in phones_list:
        markup.add(telebot.types.InlineKeyboardButton(
            text=f"{p['name']} (x{p['count']})",
            callback_data=f"inv_bphone_{p['name']}"
        ))
    markup.add(telebot.types.InlineKeyboardButton(text="📁 К категориям", callback_data="inv_broken"))
    return markup

def inv_main_markup():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton(text="✅ Рабочие телефоны", callback_data="inv_working"))
    markup.add(telebot.types.InlineKeyboardButton(text="❌ Нерабочие телефоны", callback_data="inv_broken"))
    return markup

def inv_rarities_markup(user_id):
    rarities = get_rarities_from_collection(user_id)
    markup = telebot.types.InlineKeyboardMarkup()
    for rarity, count in rarities.items():
        icon = rarity_icons.get(rarity, "📱")
        markup.add(telebot.types.InlineKeyboardButton(text=f"{icon} {rarity} ({count})", callback_data=f"inv_cat_{rarity}"))
    markup.add(telebot.types.InlineKeyboardButton(text="📁 Назад", callback_data="inv_back_main"))
    return markup

def inv_phones_markup(user_id, rarity):
    phones_list = get_phones_by_rarity(user_id, rarity)
    markup = telebot.types.InlineKeyboardMarkup()
    for p in phones_list:
        markup.add(telebot.types.InlineKeyboardButton(text=f"{p['name']} (x{p['count']})", callback_data=f"inv_phone_{p['name']}"))
    markup.add(telebot.types.InlineKeyboardButton(text="📁 К категориям", callback_data="inv_working"))
    return markup

def find_inv_header():
    if not os.path.exists(IMAGE_FOLDER):
        return None
    for f in os.listdir(IMAGE_FOLDER):
        name_low = f.lower()
        if name_low.startswith("inv_header") and name_low.endswith((".png", ".jpg", ".jpeg", ".webp")):
            return os.path.join(IMAGE_FOLDER, f)
    return None

def _inv_send_photo_msg(chat_id, caption, markup):
    """Отправляет сообщение инвентаря с фото-хедером если есть, иначе текст."""
    inv_header = find_inv_header()
    if inv_header:
        with open(inv_header, "rb") as photo:
            bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup)
        return True
    else:
        bot.send_message(chat_id=chat_id, text=caption, reply_markup=markup)
        return False

def _inv_edit_or_resend(call, text, markup):
    """Редактирует сообщение инвентаря. Если это фото — редактирует caption, не удаляя фото."""
    uid = call.from_user.id
    info = _inv_main_msg.get(uid, {})
    has_photo = info.get("has_photo", False)
    try:
        if has_photo:
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=text, reply_markup=markup
            )
        else:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text, reply_markup=markup
            )
    except Exception as e:
        # Если редактирование не удалось — удаляем старое и отправляем новое
        print(f"inv_edit_or_resend ошибка: {e}")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        has_photo = _inv_send_photo_msg(call.message.chat.id, text, markup)
        _inv_main_msg[uid] = {"has_photo": has_photo}

@bot.message_handler(commands=["myphones"])
def cmd_myphones(message):
    uid = message.from_user.id
    name = message.from_user.first_name or "игрок"
    caption = f"{name}, выберите категорию ваших телефонов:"
    inv_header = find_inv_header()
    if inv_header:
        with open(inv_header, "rb") as photo:
            msg = bot.send_photo(message.chat.id, photo, caption=caption, reply_markup=inv_main_markup())
        _inv_main_msg[uid] = {"has_photo": True}
    else:
        text = f"{caption}"
        bot.send_message(message.chat.id, text, reply_markup=inv_main_markup())
        _inv_main_msg[uid] = {"has_photo": False}

@bot.message_handler(func=lambda m: m.text and m.text.lower() == "пмои телефоны")
def text_myphones(message):
    cmd_myphones(message)

@bot.callback_query_handler(func=lambda call: call.data == "inv_working")
def inv_working(call):
    name = call.from_user.first_name or "игрок"
    text = f"{name}, выберите категорию ваших карточек:"
    _inv_edit_or_resend(call, text, inv_rarities_markup(call.from_user.id))

@bot.callback_query_handler(func=lambda call: call.data == "inv_broken")
def inv_broken(call):
    uid = call.from_user.id
    rarities = get_broken_rarities(uid)
    name = call.from_user.first_name or "игрок"
    if not rarities:
        _inv_edit_or_resend(call, f"{name}, у вас нет нерабочих телефонов.", inv_main_markup())
        return
    text = f"{name}, выберите категорию ваших нерабочих телефонов:"
    _inv_edit_or_resend(call, text, inv_broken_rarities_markup(uid))


@bot.callback_query_handler(func=lambda call: call.data.startswith("inv_bcat_"))
def inv_broken_category(call):
    rarity = call.data[9:]
    phones_list = get_broken_phones_by_rarity(call.from_user.id, rarity)
    total = sum(p["count"] for p in phones_list)
    name = call.from_user.first_name or "игрок"
    text = f"{name}, ваши нерабочие {rarity.lower()} телефоны ({total} шт.):"
    _inv_edit_or_resend(call, text, inv_broken_phones_markup(call.from_user.id, rarity))


@bot.callback_query_handler(func=lambda call: call.data.startswith("inv_bphone_"))
def inv_bphone(call):
    phone_name = call.data[11:]
    uid = call.from_user.id
    udata = get_user_data(uid, "")
    bc = udata.get("broken_collection", {})
    info = bc.get(phone_name, {})
    count = info.get("count", 0)
    rarity = info.get("rarity", "Ширпотреб")
    damages = info.get("damages", [])
    icon = rarity_icons.get(rarity, "📱")

    text = (
        f"{icon} {phone_name}\n"
        f"Редкость: {rarity}\n"
        f"⭐ Количество: {count} шт.\n"
        f"💰 Цена: 0 ПОчек (нерабочий)\n"
        f"Поломки: {', '.join(damages)}"
    )
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(telebot.types.InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data=f"inv_bbackphone_{rarity}"))

    _inv_main_msg[uid] = {"has_photo": False}
    img_path = find_image(phone_name)
    if img_path:
        with open(img_path, "rb") as photo:
            msg = bot.send_photo(call.message.chat.id, photo, caption=text, reply_markup=markup)
        _inv_main_msg[uid] = {"msg_id": msg.message_id, "has_photo": True}
    else:
        msg = bot.send_message(call.message.chat.id, text, reply_markup=markup)
        _inv_main_msg[uid] = {"msg_id": msg.message_id, "has_photo": False}
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("inv_bbackphone_"))
def inv_bback_from_broken_phone(call):
    rarity = call.data[15:]
    phones_list = get_broken_phones_by_rarity(call.from_user.id, rarity)
    total = sum(p["count"] for p in phones_list)
    name = call.from_user.first_name or "игрок"
    text = f"{name}, ваши нерабочие {rarity.lower()} телефоны ({total} шт.):"
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    # Находим главное сообщение инвентаря и редактируем
    uid = call.from_user.id
    info = _inv_main_msg.get(uid, {})
    msg_id = info.get("msg_id")
    chat_id = call.message.chat.id
    if msg_id:
        has_photo = info.get("has_photo", False)
        try:
            if has_photo:
                bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=text, reply_markup=inv_broken_phones_markup(uid, rarity))
            else:
                bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=inv_broken_phones_markup(uid, rarity))
        except Exception:
            msg_id = None
    if not msg_id:
        _inv_send_photo_msg(chat_id, text, inv_broken_phones_markup(uid, rarity))

@bot.callback_query_handler(func=lambda call: call.data == "inv_back_main")
def inv_back_main(call):
    name = call.from_user.first_name or "игрок"
    text = f"{name}, выберите категорию ваших телефонов:"
    _inv_edit_or_resend(call, text, inv_main_markup())

@bot.callback_query_handler(func=lambda call: call.data.startswith("inv_cat_"))
def inv_category(call):
    rarity = call.data[8:]
    phones_list = get_phones_by_rarity(call.from_user.id, rarity)
    total = sum(p["count"] for p in phones_list)
    name = call.from_user.first_name or "игрок"
    text = f"{name}, ваши {rarity.lower()} телефоны ({total} шт.):"
    _inv_edit_or_resend(call, text, inv_phones_markup(call.from_user.id, rarity))

@bot.callback_query_handler(func=lambda call: call.data.startswith("inv_phone_"))
def inv_phone(call):
    phone_name = call.data[10:]
    udata = get_user_data(call.from_user.id, "")
    collection = udata.get("collection", {})
    phone_info = collection.get(phone_name, {})
    price = phone_info.get("price", 0)
    sell_price = int(price * 0.75)
    rarity = phone_info.get("rarity", "Ширпотреб")

    count = phone_info.get("count", 0)
    text = (
        f"Модель: {phone_name}\n"
        f"Редкость: {rarity}\n"
        f"⭐ Количество: {count} шт.\n"
        f"Исходная цена: {price} ПОчек\n"
        f"Цена продажи: {sell_price} ПОчек"
    )

    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data=f"inv_backphone_{rarity}"),
        telebot.types.InlineKeyboardButton(text="💸 Продать телефон", callback_data="inv_sell"),
    )

    uid = call.from_user.id
    _inv_main_msg[uid] = {"has_photo": False}  # покинули фото-сообщение инвентаря
    img_path = find_image(phone_name)
    if img_path:
        with open(img_path, "rb") as photo:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            msg = bot.send_photo(call.message.chat.id, photo, caption=text, reply_markup=markup)
        _inv_action[uid] = {"msg_id": msg.message_id, "has_photo": True}
    else:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=markup
        )
        _inv_action[uid] = {"msg_id": call.message.message_id, "has_photo": False}
    _inv_action[uid].update({"phone_name": phone_name, "rarity": rarity, "price": price, "sell_price": sell_price})

@bot.callback_query_handler(func=lambda call: call.data.startswith("inv_backphone_"))
def inv_back_from_phone(call):
    uid = call.from_user.id
    rarity = call.data[14:]
    phones_list = get_phones_by_rarity(uid, rarity)
    total = sum(p["count"] for p in phones_list)
    name = call.from_user.first_name or "игрок"
    text = f"{name}, ваши {rarity.lower()} телефоны ({total} шт.):"
    bot.delete_message(call.message.chat.id, call.message.message_id)
    has_photo = _inv_send_photo_msg(call.message.chat.id, text, inv_phones_markup(uid, rarity))
    _inv_main_msg[uid] = {"has_photo": has_photo}

# ========== ПРОДАЖА ИЗ ИНВЕНТАРЯ ==========

@bot.callback_query_handler(func=lambda call: call.data == "inv_sell")
def inv_sell(call):
    uid = call.from_user.id
    act = _inv_action.get(uid)
    if not act:
        bot.answer_callback_query(call.id, "Телефон не найден", show_alert=True)
        return
    name = call.from_user.first_name or "игрок"
    text = (
        f"{name}, вы уверены, что хотите продать {act['phone_name']} "
        f"за {act['sell_price']} ПОчек?"
    )
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="inv_sell_ok"),
        telebot.types.InlineKeyboardButton(text="❌ Отмена", callback_data="inv_sell_no"),
    )
    msg_id = act["msg_id"]
    has_photo = act["has_photo"]
    try:
        if has_photo:
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=msg_id, caption=text, reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=msg_id, text=text, reply_markup=markup)
    except Exception as e:
        print(f"Ошибка inv_sell: {e}")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "inv_sell_ok")
def inv_sell_ok(call):
    uid = call.from_user.id
    act = _inv_action.get(uid)
    if not act:
        bot.answer_callback_query(call.id, "Телефон не найден", show_alert=True)
        return
    phone_name = act["phone_name"]
    sell_price = act["sell_price"]
    price = act["price"]
    rarity = act["rarity"]

    # Убираем 1 телефон из коллекции
    udata = get_user_data(uid, "")
    collection = udata.get("collection", {})
    if phone_name in collection:
        collection[phone_name]["count"] -= 1
        if collection[phone_name]["count"] <= 0:
            del collection[phone_name]
        udata["collection"] = collection
        udata["phones_value"] = max(0, udata.get("phones_value", 0) - price)
        udata["cards"] = max(0, udata.get("cards", 0) - 1)
        udata["points"] = udata.get("points", 0) + sell_price
        update_user(uid, udata)

    text = f"Вы успешно продали {phone_name} за {sell_price} ПОчек!"
    phones_list = get_phones_by_rarity(uid, rarity)
    total = sum(p["count"] for p in phones_list)
    name = call.from_user.first_name or "игрок"
    back_text = f"{name}, ваши {rarity.lower()} телефоны ({total} шт.):"
    back_markup = inv_phones_markup(uid, rarity)

    msg_id = act["msg_id"]
    try:
        bot.delete_message(call.message.chat.id, msg_id)
    except:
        pass
    bot.send_message(chat_id=call.message.chat.id, text=text)
    has_photo = _inv_send_photo_msg(call.message.chat.id, back_text, back_markup)
    _inv_main_msg[uid] = {"has_photo": has_photo}
    _inv_action.pop(uid, None)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "inv_sell_no")
def inv_sell_no(call):
    uid = call.from_user.id
    act = _inv_action.get(uid)
    if not act:
        bot.answer_callback_query(call.id, "Телефон не найден", show_alert=True)
        return
    phone_name = act["phone_name"]
    rarity = act["rarity"]
    price = act["price"]
    sell_price = act["sell_price"]

    # Возвращаемся к просмотру телефона
    udata = get_user_data(uid, "")
    collection = udata.get("collection", {})
    phone_info = collection.get(phone_name, {})
    count = phone_info.get("count", 0)

    text = (
        f"МОИ ТЕЛЕФОНЫ\n\n"
        f"Модель: {phone_name}\n"
        f"Редкость: {rarity}\n"
        f"⭐ Количество: {count} шт.\n"
        f"Исходная цена: {price} ПОчек\n"
        f"Цена продажи: {sell_price} ПОчек"
    )
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data=f"inv_backphone_{rarity}"),
        telebot.types.InlineKeyboardButton(text="💸 Продать телефон", callback_data="inv_sell"),
    )
    msg_id = act["msg_id"]
    has_photo = act["has_photo"]
    try:
        if has_photo:
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=msg_id, caption=text, reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=msg_id, text=text, reply_markup=markup)
    except Exception as e:
        print(f"Ошибка inv_sell_no: {e}")
    bot.answer_callback_query(call.id)

# ========== КНОПКИ ДЕЙСТВИЙ ПРИ ДРОПЕ ==========

def _edit_card_msg(call, text, markup=None):
    """Редактирует сообщение с картой (учитывая фото или текст)."""
    uid = call.from_user.id
    act = _card_actions.get(uid, {})
    chat_id = act.get("chat_id", call.message.chat.id)
    msg_id = act.get("message_id", call.message.message_id)
    has_photo = act.get("has_photo", False)
    try:
        if has_photo:
            bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=text, reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=markup)
    except Exception as e:
        print(f"Ошибка редактирования: {e}")

def _card_action_markup():
    m = telebot.types.InlineKeyboardMarkup(row_width=1)
    m.add(
        telebot.types.InlineKeyboardButton(text="💸 Продать", callback_data="ca_sell"),
        telebot.types.InlineKeyboardButton(text="🔧 В апгрейд", callback_data="ca_upgrade"),
        telebot.types.InlineKeyboardButton(text="📦 На Авито", callback_data="ca_avito"),
        telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data="ca_back"),
    )
    return m

def _sell_confirm_markup():
    m = telebot.types.InlineKeyboardMarkup(row_width=1)
    m.add(
        telebot.types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="ca_sellok"),
        telebot.types.InlineKeyboardButton(text="❌ Отмена", callback_data="ca_sellno"),
    )
    return m

@bot.callback_query_handler(func=lambda call: call.data == "ca_sell")
def ca_sell(call):
    uid = call.from_user.id
    act = _card_actions.get(uid)
    if not act:
        bot.answer_callback_query(call.id, "Карта больше не доступна", show_alert=True)
        return
    name = call.from_user.first_name or "игрок"
    text = (
        f"{name}, вы уверены, что хотите продать {act['name']} "
        f"за {act['sell_price']} ПОчек?"
    )
    _edit_card_msg(call, text, _sell_confirm_markup())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "ca_sellok")
def ca_sellok(call):
    uid = call.from_user.id
    act = _card_actions.get(uid)
    if not act:
        bot.answer_callback_query(call.id, "Карта больше не доступна", show_alert=True)
        return
    # Удаляем телефон из коллекции
    udata = get_user_data(uid, "")
    collection = udata.get("collection", {})
    phone_name = act["name"]
    sell_price = act["sell_price"]
    price = act["price"]

    if phone_name in collection:
        collection[phone_name]["count"] -= 1
        if collection[phone_name]["count"] <= 0:
            del collection[phone_name]
        udata["collection"] = collection
        udata["phones_value"] = max(0, udata.get("phones_value", 0) - price)
        udata["cards"] = max(0, udata.get("cards", 0) - 1)
        udata["points"] = udata.get("points", 0) + sell_price
        update_user(uid, udata)

    text = f"Вы успешно продали {phone_name} за {sell_price} ПОчек!"
    _edit_card_msg(call, text)
    _card_actions.pop(uid, None)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "ca_sellno")
def ca_sellno(call):
    uid = call.from_user.id
    act = _card_actions.get(uid)
    if not act:
        bot.answer_callback_query(call.id, "Карта больше не доступна", show_alert=True)
        return
    _edit_card_msg(call, act["original_text"], _card_action_markup())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "ca_upgrade")
def ca_upgrade(call):
    bot.answer_callback_query(call.id, "🔧 Апгрейд скоро будет доступен!", show_alert=False)

@bot.callback_query_handler(func=lambda call: call.data == "ca_avito")
def ca_avito(call):
    bot.answer_callback_query(call.id, "📦 Выставка на Авито скоро будет доступна!", show_alert=False)

@bot.callback_query_handler(func=lambda call: call.data == "ca_menu")
def ca_menu(call):
    uid = call.from_user.id
    act = _card_actions.get(uid)
    if not act:
        bot.answer_callback_query(call.id, "Карта больше не доступна", show_alert=True)
        return
    _edit_card_msg(call, act["original_text"], _card_action_markup())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "ca_back")
def ca_back(call):
    uid = call.from_user.id
    act = _card_actions.get(uid)
    if not act:
        bot.answer_callback_query(call.id, "Карта больше не доступна", show_alert=True)
        return
    # Назад к одной кнопке "Действие"
    m = telebot.types.InlineKeyboardMarkup(row_width=1)
    m.add(telebot.types.InlineKeyboardButton(text="🛒 Действие", callback_data="ca_menu"))
    _edit_card_msg(call, act["original_text"], m)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "пинг")
def cmd_ping(message):
    start = time.time()
    msg = bot.reply_to(message, "Понг!", parse_mode="Markdown")
    ms = int((time.time() - start) * 1000)
    bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, text=f"Понг!\n{ms}ms", parse_mode="Markdown")

def _get_tinfo_text():
    now = time.time()
    uptime = now - BOT_START_TIME
    d = int(uptime // 86400)
    h = int((uptime % 86400) // 3600)
    m = int((uptime % 3600) // 60)
    s = int(uptime % 60)

    t1 = time.time()
    bot.get_me()
    tg_ms = int((time.time() - t1) * 1000)

    if HAS_PSUTIL:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        cpu_name = platform.processor() or "Unknown"
        if len(cpu_name) > 35:
            cpu_name = cpu_name[:32] + "..."
        ram = psutil.virtual_memory()
        ram_pct = ram.percent
        ram_total = ram.total / (1024**3)
        ram_name = f"{ram_total:.1f} GB"
        # Попытка получить имя ОЗУ через WMI (Windows)
        if platform.system() == "Windows":
            try:
                import subprocess
                result = subprocess.run(
                    ["wmic", "memorychip", "get", "Manufacturer,Speed,PartNumber", "/format:csv"],
                    capture_output=True, text=True, timeout=3, creationflags=0x08000000
                )
                lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                if len(lines) >= 2:
                    parts = lines[1].split(",")
                    if len(parts) >= 4:
                        ram_name = f"{parts[2]} {parts[3].strip()} {parts[1]}MHz"
            except:
                pass
    else:
        cpu_pct = "N/A"
        cpu_name = "psutil не установлен"
        ram_pct = "N/A"
        ram_name = "psutil не установлен"

    text = (
        f"📊Техническая информация:\n\n"
        f"🕘Время работы: {d}д {h}:{m:02d}:{s:02d}\n"
        f"📶Пинг: {tg_ms}ms\n"
        f"🌐Пинг Telegram'а: {tg_ms}ms\n\n"
        f"🖥Нагрузка ЦП: {cpu_pct}% ({cpu_name})\n"
        f"💾Загрузка ОЗУ: {ram_pct}% ({ram_name})"
    )
    return text

def _tinfo_markup():
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(telebot.types.InlineKeyboardButton(text="🔄 Обновить", callback_data="tinfo_refresh"))
    return markup

@bot.message_handler(commands=["tinfo"])
def cmd_tinfo(message):
    text = _get_tinfo_text()
    bot.reply_to(message, text, parse_mode="Markdown", reply_markup=_tinfo_markup())

@bot.callback_query_handler(func=lambda call: call.data == "tinfo_refresh")
def tinfo_refresh(call):
    text = _get_tinfo_text()
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=text, parse_mode="Markdown", reply_markup=_tinfo_markup()
        )
    except:
        pass
    bot.answer_callback_query(call.id)

def weekly_tester_pay():
    """Каждую неделю проверяет юзеров со статусом 'Тестер' и начисляет 1 500 000 ПОчек."""
    WEEK = 7 * 24 * 60 * 60  # секунды в неделе
    while True:
        time.sleep(WEEK)
        try:
            data = load_data()
            paid = 0
            for uid_str, udata in data.items():
                status = udata.get("status", "").lower()
                if "тестер" in status:
                    uid = int(uid_str)
                    udata["points"] = udata.get("points", 0) + 1500000
                    data[uid_str] = udata
                    paid += 1
                    try:
                        bot.send_message(
                            uid,
                            "💰 Выплата тестерам 1 500 000 ПОчек!"
                        )
                    except:
                        pass
            if paid > 0:
                save_data(data)
                print(f"Еженедельная выплата: {paid} тестеров получили 1 500 000 ПОчек")
        except Exception as e:
            print(f"Ошибка еженедельной выплаты: {e}")


# ========== УРОВНИ ШАНСОВ ВЫПАДЕНИЯ ==========

RARITY_ORDER = ["Ширпотреб", "Необычный", "Редкий", "Мистический", "Хроматический", "Аркана", "Платиновый", "Артефакт", "Сезонный"]
RARITY_ICONS_LIST = ["📱", "📲", "⭐", "✨", "🔮", "🏆", "💠", "💎", "🗓"]

UPG_DROP_PRICES = [0, 10000, 25000, 50000, 100000, 250000, 500000]

UPG_DROP_LEVELS = [
    {"Ширпотреб": 34.59, "Необычный": 24.0, "Редкий": 20.0, "Мистический": 12.0, "Хроматический": 5.0, "Аркана": 2.5, "Платиновый": 1.0, "Артефакт": 0.4, "Сезонный": 0.0},
    {"Ширпотреб": 33.39, "Необычный": 22.0, "Редкий": 20.0, "Мистический": 13.5, "Хроматический": 5.5, "Аркана": 3.0, "Платиновый": 1.2, "Артефакт": 0.6, "Сезонный": 0.0},
    {"Ширпотреб": 32.19, "Необычный": 21.0, "Редкий": 19.0, "Мистический": 14.5, "Хроматический": 6.5, "Аркана": 3.5, "Платиновый": 1.5, "Артефакт": 0.8, "Сезонный": 0.0},
    {"Ширпотреб": 31.09, "Необычный": 20.0, "Редкий": 18.0, "Мистический": 15.5, "Хроматический": 7.5, "Аркана": 4.0, "Платиновый": 1.8, "Артефакт": 0.9, "Сезонный": 0.0},
    {"Ширпотреб": 29.79, "Необычный": 19.0, "Редкий": 18.0, "Мистический": 16.0, "Хроматический": 8.5, "Аркана": 4.5, "Платиновый": 2.0, "Артефакт": 1.2, "Сезонный": 0.0},
    {"Ширпотреб": 28.49, "Необычный": 18.0, "Редкий": 18.0, "Мистический": 16.5, "Хроматический": 9.5, "Аркана": 5.0, "Платиновый": 2.5, "Артефакт": 1.5, "Сезонный": 0.0},
    {"Ширпотреб": 25.48, "Необычный": 17.0, "Редкий": 18.0, "Мистический": 17.0, "Хроматический": 10.0, "Аркана": 6.0, "Платиновый": 3.0, "Артефакт": 2.5, "Сезонный": 0.0},
]

# ========== МАГАЗИН УЛУЧШЕНИЙ ==========

UPG_SHOP_IMG = os.path.join(IMAGE_FOLDER, "upgrade_shop.png")
UPG_CD_LEVELS = [180, 170, 160, 150, 140, 130, 120]
UPG_CD_PRICES = [0, 10000, 25000, 50000, 100000, 250000, 500000]


def _format_chances_text(level_chances, header=""):
    lines = []
    if header:
        lines.append(header)
    for rarity, icon in zip(RARITY_ORDER, RARITY_ICONS_LIST):
        val = level_chances.get(rarity, 0)
        lines.append(f"{icon} {rarity}: {val}%")
    return "\n".join(lines)


def _upg_send_shop(chat_id, text, markup):
    if os.path.exists(UPG_SHOP_IMG):
        with open(UPG_SHOP_IMG, "rb") as photo:
            return bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
    else:
        return bot.send_message(chat_id, text, reply_markup=markup)


def _upg_edit_shop(call, text, markup, has_photo):
    try:
        if has_photo:
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup)
    except:
        pass


def _get_cd_level_index(udata):
    cd_sec = udata.get("card_cooldown", 10800)
    cd_min = cd_sec // 60
    for i, lvl_min in enumerate(UPG_CD_LEVELS):
        if cd_min >= lvl_min:
            return i
    return len(UPG_CD_LEVELS) - 1


def _upg_has_photo(uid):
    return _upg_shop_msg.get(uid, {}).get("has_photo", False)


def _upg_main_text(name):
    return f"{name}, добро пожаловать в магазин улучшений!\n\nВыберите, что хотите прокачать:"


def _upg_main_markup():
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="Перезарядка 🕒", callback_data="upg_cooldown"),
        telebot.types.InlineKeyboardButton(text="Шансы выпадения 🎲", callback_data="upg_drops"),
        telebot.types.InlineKeyboardButton(text="Шансы апгрейда 🚀", callback_data="upg_upgrade"),
        telebot.types.InlineKeyboardButton(text="Майнинг ферма 🔨", callback_data="upg_mining"),
        telebot.types.InlineKeyboardButton(text="Лимит покупок 🛒", callback_data="upg_buylimit"),
    )
    return markup


@bot.message_handler(commands=["pupgradeshop"])
def cmd_pupgradeshop(message):
    uid = message.from_user.id
    name = message.from_user.first_name or "игрок"
    text = _upg_main_text(name)
    markup = _upg_main_markup()
    msg = _upg_send_shop(message.chat.id, text, markup)
    _upg_shop_msg[uid] = {"msg_id": msg.message_id, "has_photo": os.path.exists(UPG_SHOP_IMG)}

@bot.message_handler(func=lambda m: m.text and m.text.lower() == "пмагазин улучшений")
def text_pupgradeshop(message):
    cmd_pupgradeshop(message)


# ===== ПЕРЕЗАРЯДКА =====

@bot.callback_query_handler(func=lambda call: call.data == "upg_cooldown")
def upg_cooldown(call):
    uid = call.from_user.id
    udata = get_user_data(uid, "")
    name = call.from_user.first_name or "игрок"
    status = udata.get("status", "Обычный")
    if "Тестер" in status or "Создатель" in status:
        role = "тестер" if "Тестер" in status else "создатель"
        text = f"⏱ Перезарядка 'ПКарточка'\n\n{name}, ты {role} и не можешь прокачать так как и так пониженный кд!"
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data="upg_back"))
        _upg_edit_shop(call, text, markup, _upg_has_photo(uid))
        bot.answer_callback_query(call.id)
        return
    lvl_idx = _get_cd_level_index(udata)
    cd_min = UPG_CD_LEVELS[lvl_idx]
    h = cd_min // 60
    m = cd_min % 60
    if lvl_idx >= 6:
        text = f"⏱ Перезарядка 'ПКарточка'\n\nТекущий уровень: {lvl_idx}\nПерезарядка: {h} ч {m} мин\n\nУ вас максимальный уровень!"
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data="upg_back"))
    else:
        next_min = UPG_CD_LEVELS[lvl_idx + 1]
        next_h = next_min // 60
        next_m = next_min % 60
        cost = UPG_CD_PRICES[lvl_idx + 1]
        text = f"⏱ Перезарядка 'ПКарточка'\n\nТекущий уровень: {lvl_idx}\nПерезарядка: {h} ч {m} мин\n\nСледующий уровень ({lvl_idx + 1}): {next_h} ч {next_m} мин\nСтоимость: {cost:,} ПОчек"
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            telebot.types.InlineKeyboardButton(text=f"📈 Улучшить за {cost:,} ПОчек", callback_data="upg_cooldown_buy"),
            telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data="upg_back"),
        )
    _upg_edit_shop(call, text, markup, _upg_has_photo(uid))
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "upg_cooldown_buy")
def upg_cooldown_buy(call):
    uid = call.from_user.id
    udata = get_user_data(uid, "")
    name = call.from_user.first_name or "игрок"
    lvl_idx = _get_cd_level_index(udata)
    if lvl_idx >= 6:
        bot.answer_callback_query(call.id, "Максимальный уровень!", show_alert=True)
        return
    cost = UPG_CD_PRICES[lvl_idx + 1]
    text = f"{name}, вы уверены, что хотите улучшить Перезарядку за {cost:,} ПОчек?"
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="upg_cooldown_ok"),
        telebot.types.InlineKeyboardButton(text="❌ Отмена", callback_data="upg_cooldown"),
    )
    _upg_edit_shop(call, text, markup, _upg_has_photo(uid))
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "upg_cooldown_ok")
def upg_cooldown_ok(call):
    uid = call.from_user.id
    udata = get_user_data(uid, "")
    name = call.from_user.first_name or "игрок"
    lvl_idx = _get_cd_level_index(udata)
    if lvl_idx >= 6:
        bot.answer_callback_query(call.id, "Максимальный уровень!", show_alert=True)
        return
    next_idx = lvl_idx + 1
    cost = UPG_CD_PRICES[next_idx]
    if udata.get("points", 0) < cost:
        bot.answer_callback_query(call.id, "Недостаточно ПОчек!", show_alert=True)
        return
    udata["points"] = udata.get("points", 0) - cost
    udata["card_cooldown"] = UPG_CD_LEVELS[next_idx] * 60
    update_user(uid, udata)
    text = f"✅ {name}, вы успешно улучшили Перезарядку до уровня {next_idx}!"
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(telebot.types.InlineKeyboardButton(text="⬅️ В магазин", callback_data="upg_back"))
    _upg_edit_shop(call, text, markup, _upg_has_photo(uid))
    bot.answer_callback_query(call.id)


# ===== ШАНСЫ ВЫПАДЕНИЯ =====

@bot.callback_query_handler(func=lambda call: call.data == "upg_drops")
def upg_drops(call):
    uid = call.from_user.id
    udata = get_user_data(uid, "")
    name = call.from_user.first_name or "игрок"
    lvl = udata.get("drop_chance_level", 0)
    if lvl >= 6:
        text = f"🎲 Шансы выпадения телефонов\n\nТекущий уровень: {lvl}\n\n{_format_chances_text(UPG_DROP_LEVELS[lvl])}\n\nУ вас максимальный уровень!"
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data="upg_back"))
    else:
        cost = UPG_DROP_PRICES[lvl + 1]
        text = f"🎲 Шансы выпадения телефонов\n\nТекущий уровень: {lvl}\n{_format_chances_text(UPG_DROP_LEVELS[lvl])}\n\nСледующий уровень: {lvl + 1}\n{_format_chances_text(UPG_DROP_LEVELS[lvl + 1])}\n\nСтоимость: {cost:,} ПОчек"
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            telebot.types.InlineKeyboardButton(text=f"📈 Улучшить за {cost:,} ПОчек", callback_data="upg_drops_buy"),
            telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data="upg_back"),
        )
    _upg_edit_shop(call, text, markup, _upg_has_photo(uid))
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "upg_drops_buy")
def upg_drops_buy(call):
    uid = call.from_user.id
    udata = get_user_data(uid, "")
    name = call.from_user.first_name or "игрок"
    lvl = udata.get("drop_chance_level", 0)
    if lvl >= 6:
        bot.answer_callback_query(call.id, "Максимальный уровень!", show_alert=True)
        return
    cost = UPG_DROP_PRICES[lvl + 1]
    text = f"{name}, вы уверены, что хотите улучшить Шансы выпадения за {cost:,} ПОчек?"
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="upg_drops_ok"),
        telebot.types.InlineKeyboardButton(text="❌ Отмена", callback_data="upg_drops"),
    )
    _upg_edit_shop(call, text, markup, _upg_has_photo(uid))
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "upg_drops_ok")
def upg_drops_ok(call):
    uid = call.from_user.id
    udata = get_user_data(uid, "")
    name = call.from_user.first_name or "игрок"
    lvl = udata.get("drop_chance_level", 0)
    if lvl >= 6:
        bot.answer_callback_query(call.id, "Максимальный уровень!", show_alert=True)
        return
    next_lvl = lvl + 1
    cost = UPG_DROP_PRICES[next_lvl]
    if udata.get("points", 0) < cost:
        bot.answer_callback_query(call.id, "Недостаточно ПОчек!", show_alert=True)
        return
    udata["points"] = udata.get("points", 0) - cost
    udata["drop_chance_level"] = next_lvl
    update_user(uid, udata)
    text = f"✅ {name}, вы успешно улучшили Шансы выпадения до уровня {next_lvl}!"
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(telebot.types.InlineKeyboardButton(text="⬅️ В магазин", callback_data="upg_back"))
    _upg_edit_shop(call, text, markup, _upg_has_photo(uid))
    bot.answer_callback_query(call.id)


# ===== ЗАГЛУШКИ =====

@bot.callback_query_handler(func=lambda call: call.data == "upg_upgrade")
def upg_upgrade(call):
    bot.answer_callback_query(call.id, "Еще не добавлено!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "upg_mining")
def upg_mining(call):
    bot.answer_callback_query(call.id, "Еще не добавлено!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "upg_buylimit")
def upg_buylimit(call):
    bot.answer_callback_query(call.id, "Еще не добавлено!", show_alert=True)


# ===== НАЗАД В МАГАЗИН =====

@bot.callback_query_handler(func=lambda call: call.data == "upg_back")
def upg_back(call):
    uid = call.from_user.id
    name = call.from_user.first_name or "игрок"
    text = _upg_main_text(name)
    markup = _upg_main_markup()
    _upg_edit_shop(call, text, markup, _upg_has_photo(uid))
    bot.answer_callback_query(call.id)


print("Бот запущен!")

t = threading.Thread(target=weekly_tester_pay, daemon=True)
t.start()

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка: {e}")
        time.sleep(5)
