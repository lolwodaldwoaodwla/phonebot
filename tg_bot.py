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

_db_lock = threading.Lock()

bot = telebot.TeleBot(os.environ.get("BOT_TOKEN", "8809903771:AAHqCrXvOwdIN9BElGPOfRycQaOG7S7vkVA"))

BOT_START_TIME = time.time()

IMAGE_FOLDER = "images"
DATA_FILE = "bot_data.json"

TURSO_URL = os.environ.get("TURSO_DB_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_DB_TOKEN", "")
_USE_TURSO = bool(TURSO_URL and TURSO_TOKEN)

_conn = None


class _TursoDB:
    """Обёртка над Turso HTTP API — совместима с sqlite3 интерфейсом."""
    def __init__(self, url, token):
        self._url = url.rstrip("/")
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _convert_args(self, params):
        """Конвертирует параметры sqlite3 ? в формат Turso args."""
        if not params:
            return []
        args = []
        for p in params:
            if p is None:
                args.append({"type": "null"})
            elif isinstance(p, int):
                args.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float):
                args.append({"type": "float", "value": str(p)})
            else:
                args.append({"type": "text", "value": str(p)})
        return args

    def _request(self, sql, params=()):
        """Отправляет запрос к Turso HTTP API."""
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": self._convert_args(params)
                    }
                }
            ]
        }
        resp = requests.post(
            f"{self._url}/v2/pipeline",
            headers=self._headers,
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        result = data["results"][0].get("response", {}).get("result", {})
        return result

    def execute(self, sql, params=()):
        """Выполняет SQL и возвращает объект-курсор."""
        result = self._request(sql, params)
        cols = [c["name"] for c in result.get("cols", [])]
        rows = []
        for r in result.get("rows", []):
            row = {}
            for i, col in enumerate(cols):
                val = r[col] if col in r else None
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
                row[col] = val
            rows.append(row)
        return _FakeCursor(cols, rows)

    def executescript(self, sql):
        """Выполняет несколько SQL statements (для локальной совместимости)."""
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                self._request(statement)

    def commit(self):
        pass


class _FakeCursor:
    """Фейковый курсор для совместимости с sqlite3."""
    def __init__(self, columns, rows):
        self._columns = columns
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def _get_db():
    global _conn
    if _conn is None:
        if _USE_TURSO:
            _conn = _TursoDB(TURSO_URL, TURSO_TOKEN)
        else:
            import sqlite3
            db_path = os.environ.get("BOT_DB_PATH", "bot_data.db")
            _conn = sqlite3.connect(db_path, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def _db_execute(db, sql, params=()):
    """Выполняет SQL запрос и возвращает список dict-строк."""
    cursor = db.execute(sql, params)
    if _USE_TURSO:
        return cursor.fetchall()
    else:
        return [dict(r) for r in cursor.fetchall()]


def _db_execute_one(db, sql, params=()):
    """Выполняет SQL запрос и возвращает одну dict-строку или None."""
    cursor = db.execute(sql, params)
    if _USE_TURSO:
        return cursor.fetchone()
    else:
        row = cursor.fetchone()
        return dict(row) if row else None

def _init_db():
    db = _get_db()
    if _USE_TURSO:
        db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, points INTEGER DEFAULT 0, tcoins INTEGER DEFAULT 0, cards INTEGER DEFAULT 0, phones_value INTEGER DEFAULT 0, achievements INTEGER DEFAULT 0, profile_views INTEGER DEFAULT 0, status TEXT DEFAULT 'Обычный', username TEXT DEFAULT '', last_card_time INTEGER DEFAULT 0, card_cooldown INTEGER DEFAULT 10800, rarity_chances TEXT DEFAULT '{}', last_dropped TEXT DEFAULT '[]')")
        db.execute("CREATE TABLE IF NOT EXISTS collection (user_id INTEGER, phone_name TEXT, rarity TEXT, price INTEGER, count INTEGER DEFAULT 1, PRIMARY KEY (user_id, phone_name))")
        db.execute("CREATE TABLE IF NOT EXISTS viewed_by (target_id INTEGER, viewer_id INTEGER, PRIMARY KEY (target_id, viewer_id))")
    else:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0,
            tcoins INTEGER DEFAULT 0,
            cards INTEGER DEFAULT 0,
            phones_value INTEGER DEFAULT 0,
            achievements INTEGER DEFAULT 0,
            profile_views INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Обычный',
            username TEXT DEFAULT '',
            last_card_time INTEGER DEFAULT 0,
            card_cooldown INTEGER DEFAULT 10800,
            rarity_chances TEXT DEFAULT '{}',
            last_dropped TEXT DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS collection (
            user_id INTEGER,
            phone_name TEXT,
            rarity TEXT,
            price INTEGER,
            count INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, phone_name)
        );
        CREATE TABLE IF NOT EXISTS viewed_by (
            target_id INTEGER,
            viewer_id INTEGER,
            PRIMARY KEY (target_id, viewer_id)
        );
    """)
    db.commit()

def _migrate_from_json():
    """Если есть bot_data.json — переносим данные в SQLite."""
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            return
        db = _get_db()
        for uid_str, udata in data.items():
            uid = int(uid_str)
            collection = udata.get("collection", {})
            viewed_by = udata.get("viewed_by", [])
            last_dropped = udata.get("last_dropped", [])
            rarity_chances = udata.get("rarity_chances", {})
            db.execute("""INSERT OR REPLACE INTO users
                (user_id, points, tcoins, cards, phones_value, achievements,
                 profile_views, status, username, last_card_time, card_cooldown,
                 rarity_chances, last_dropped)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid,
                 udata.get("points", 0),
                 udata.get("tcoins", 0),
                 udata.get("cards", 0),
                 udata.get("phones_value", 0),
                 udata.get("achievements", 0),
                 udata.get("profile_views", 0),
                 udata.get("status", "Обычный"),
                 udata.get("username", ""),
                 udata.get("last_card_time", 0),
                 udata.get("card_cooldown", 10800),
                 json.dumps(rarity_chances, ensure_ascii=False),
                 json.dumps(last_dropped, ensure_ascii=False)))
            for phone_name, info in collection.items():
                db.execute("""INSERT OR REPLACE INTO collection
                    (user_id, phone_name, rarity, price, count)
                    VALUES (?,?,?,?,?)""",
                    (uid, phone_name, info["rarity"], info["price"], info["count"]))
            for viewer_id in viewed_by:
                db.execute("INSERT OR IGNORE INTO viewed_by (target_id, viewer_id) VALUES (?,?)",
                           (uid, int(viewer_id)))
        db.commit()
        # Переименовываем JSON файл чтобы не мигрировать снова
        os.rename(DATA_FILE, DATA_FILE + ".migrated")
        print(f"Миграция из JSON в SQLite завершена ({len(data)} пользователей)")
    except Exception as e:
        print(f"Ошибка миграции из JSON: {e}")

# Инициализация при запуске
_init_db()
_migrate_from_json()

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
    """Совместимость: возвращает dict всех пользователей (для топов и поиска по юзернейму)."""
    with _db_lock:
        db = _get_db()
        rows = _db_execute(db, "SELECT user_id, points, tcoins, cards, phones_value, achievements, profile_views, status, username, last_card_time, card_cooldown, rarity_chances, last_dropped FROM users")
        col_rows = _db_execute(db, "SELECT user_id, phone_name, rarity, price, count FROM collection")
        view_rows = _db_execute(db, "SELECT target_id, viewer_id FROM viewed_by")

    data = {}
    for r in rows:
        uid = str(r["user_id"])
        data[uid] = {
            "points": r["points"],
            "tcoins": r["tcoins"],
            "cards": r["cards"],
            "phones_value": r["phones_value"],
            "achievements": r["achievements"],
            "profile_views": r["profile_views"],
            "status": r["status"],
            "username": r["username"],
            "last_card_time": r["last_card_time"],
            "card_cooldown": r["card_cooldown"],
            "rarity_chances": json.loads(r["rarity_chances"]) if r["rarity_chances"] else {},
            "last_dropped": json.loads(r["last_dropped"]) if r["last_dropped"] else [],
            "viewed_by": [],
            "collection": {},
        }
    for r in col_rows:
        uid = str(r["user_id"])
        if uid in data:
            data[uid]["collection"][r["phone_name"]] = {
                "rarity": r["rarity"],
                "price": r["price"],
                "count": r["count"],
            }
    for r in view_rows:
        uid = str(r["target_id"])
        if uid in data:
            data[uid]["viewed_by"].append(str(r["viewer_id"]))
    return data

def save_data(data):
    """Совместимость: сохраняет полный dict в SQLite."""
    with _db_lock:
        db = _get_db()
        for uid_str, udata in data.items():
            uid = int(uid_str)
            db.execute("""INSERT OR REPLACE INTO users
                (user_id, points, tcoins, cards, phones_value, achievements,
                 profile_views, status, username, last_card_time, card_cooldown,
                 rarity_chances, last_dropped)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid,
                 udata.get("points", 0),
                 udata.get("tcoins", 0),
                 udata.get("cards", 0),
                 udata.get("phones_value", 0),
                 udata.get("achievements", 0),
                 udata.get("profile_views", 0),
                 udata.get("status", "Обычный"),
                 udata.get("username", ""),
                 udata.get("last_card_time", 0),
                 udata.get("card_cooldown", 10800),
                 json.dumps(udata.get("rarity_chances", {}), ensure_ascii=False),
                 json.dumps(udata.get("last_dropped", []), ensure_ascii=False)))
            # Сохраняем коллекцию
            collection = udata.get("collection", {})
            for phone_name, info in collection.items():
                db.execute("""INSERT OR REPLACE INTO collection
                    (user_id, phone_name, rarity, price, count)
                    VALUES (?,?,?,?,?)""",
                    (uid, phone_name, info["rarity"], info["price"], info["count"]))
            # Сохраняем viewed_by
            for viewer_id in udata.get("viewed_by", []):
                db.execute("INSERT OR IGNORE INTO viewed_by (target_id, viewer_id) VALUES (?,?)",
                           (uid, int(viewer_id)))
        db.commit()

def get_user_data(user_id, username):
    with _db_lock:
        db = _get_db()
        row = _db_execute_one(db, "SELECT * FROM users WHERE user_id = ?", (user_id,))
        col_rows = _db_execute(db, "SELECT phone_name, rarity, price, count FROM collection WHERE user_id = ?", (user_id,))
        view_rows = _db_execute(db, "SELECT viewer_id FROM viewed_by WHERE target_id = ?", (user_id,))

    collection = {}
    for r in col_rows:
        collection[r["phone_name"]] = {
            "rarity": r["rarity"],
            "price": r["price"],
            "count": r["count"],
        }
    viewed_by = [str(r["viewer_id"]) for r in view_rows]

    if row:
        return {
            "points": row["points"],
            "tcoins": row["tcoins"],
            "cards": row["cards"],
            "phones_value": row["phones_value"],
            "achievements": row["achievements"],
            "profile_views": row["profile_views"],
            "status": row["status"],
            "username": row["username"],
            "last_card_time": row["last_card_time"],
            "card_cooldown": row["card_cooldown"],
            "rarity_chances": json.loads(row["rarity_chances"]) if row["rarity_chances"] else {},
            "last_dropped": json.loads(row["last_dropped"]) if row["last_dropped"] else [],
            "viewed_by": viewed_by,
            "collection": collection,
        }

    # Новый пользователь
    with _db_lock:
        db = _get_db()
        db.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username or ""))
        db.commit()

    return {
        "points": 0, "tcoins": 0, "cards": 0, "phones_value": 0,
        "achievements": 0, "profile_views": 0, "status": "Обычный",
        "username": username or "", "collection": {},
        "last_card_time": 0, "card_cooldown": 10800,
        "rarity_chances": {}, "last_dropped": [], "viewed_by": [],
    }

def update_user(user_id, udata):
    with _db_lock:
        db = _get_db()
        db.execute("""INSERT OR REPLACE INTO users
            (user_id, points, tcoins, cards, phones_value, achievements,
             profile_views, status, username, last_card_time, card_cooldown,
             rarity_chances, last_dropped)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id,
             udata.get("points", 0),
             udata.get("tcoins", 0),
             udata.get("cards", 0),
             udata.get("phones_value", 0),
             udata.get("achievements", 0),
             udata.get("profile_views", 0),
             udata.get("status", "Обычный"),
             udata.get("username", ""),
             udata.get("last_card_time", 0),
             udata.get("card_cooldown", 10800),
             json.dumps(udata.get("rarity_chances", {}), ensure_ascii=False),
             json.dumps(udata.get("last_dropped", []), ensure_ascii=False)))
        # Обновляем коллекцию
        collection = udata.get("collection", {})
        db.execute("DELETE FROM collection WHERE user_id = ?", (user_id,))
        for phone_name, info in collection.items():
            db.execute("INSERT INTO collection (user_id, phone_name, rarity, price, count) VALUES (?,?,?,?,?)",
                       (user_id, phone_name, info["rarity"], info["price"], info["count"]))
        # Обновляем viewed_by
        db.execute("DELETE FROM viewed_by WHERE target_id = ?", (user_id,))
        for viewer_id in udata.get("viewed_by", []):
            db.execute("INSERT INTO viewed_by (target_id, viewer_id) VALUES (?,?)",
                       (user_id, int(viewer_id)))
        db.commit()

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
    custom = udata.get("rarity_chances", {})
    chances = {}
    if custom:
        for rarity, default_chance in rarity_chances.items():
            chances[rarity] = custom.get(rarity, 0)
    else:
        chances = dict(rarity_chances)
    return chances

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

def get_card_text(user_name, phone):
    icon = rarity_icons.get(phone['rarity'], "📱")
    return (
        f"**{user_name}** вам выпал телефон!\n"
        f"{icon} **{phone['name']}**\n"
        f"Редкость: {phone['rarity']} | 💰 Цена: {phone['price']} ПОчек"
    )

def add_phone_to_collection(user_id, phone):
    udata = get_user_data(user_id, "")
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
_inv_action = {}    # user_id -> {phone_name, rarity, price, sell_price, msg_id, has_photo}
_inv_main_msg = {}  # user_id -> {msg_id, has_photo}
_pay_pending = {}   # user_id -> {target_id, amount, target_display, msg_id, chat_id, comment}
_paycoin_pending = {}  # user_id -> {target_id, amount, target_display, sender_name, msg_id, chat_id}

def send_card(message, phone):
    add_phone_to_collection(message.from_user.id, phone)
    text = get_card_text(message.from_user.first_name, phone)
    sell_price = int(phone["price"] * 0.75)

    uid = message.from_user.id
    _card_actions[uid] = {
        "name": phone["name"],
        "price": phone["price"],
        "rarity": phone["rarity"],
        "sell_price": sell_price,
    }

    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(telebot.types.InlineKeyboardButton(text="🛒 Действие", callback_data="ca_menu"))

    img = find_image(phone["name"])
    if img:
        with open(img, "rb") as photo:
            msg = bot.send_photo(message.chat.id, photo, caption=text, parse_mode="Markdown", reply_markup=markup)
        _card_actions[uid]["has_photo"] = True
    else:
        msg = bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
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

@bot.message_handler(commands=["pcard"])
def cmd_pcard(message):
    remaining = check_cooldown(message.from_user.id)
    if remaining > 0:
        name = message.from_user.first_name or "игрок"
        bot.send_message(message.chat.id, f"**{name}**, вы сможете выбить карту еще раз через {format_cooldown(remaining)}.", parse_mode="Markdown")
        return
    phone = get_random_phone(message.from_user.id)
    send_card(message, phone)
    udata = get_user_data(message.from_user.id, "")
    udata["last_card_time"] = int(time.time())
    update_user(message.from_user.id, udata)

@bot.message_handler(func=lambda m: m.text and m.text.lower() == "пкарточка")
def text_pcard(message):
    remaining = check_cooldown(message.from_user.id)
    if remaining > 0:
        name = message.from_user.first_name or "игрок"
        bot.send_message(message.chat.id, f"**{name}**, вы сможете выбить карту еще раз через {format_cooldown(remaining)}.", parse_mode="Markdown")
        return
    phone = get_random_phone(message.from_user.id)
    send_card(message, phone)
    udata = get_user_data(message.from_user.id, "")
    udata["last_card_time"] = int(time.time())
    update_user(message.from_user.id, udata)

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
        bot.reply_to(message, f"❌ **{name}**, у вас недостаточно ПОчек. Ваш баланс: {sender_points} ПОчек.", parse_mode="Markdown")
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
            bot.send_photo(chat_id, photo, caption=caption, parse_mode="Markdown", reply_markup=markup)
        return True
    else:
        bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown", reply_markup=markup)
        return False

def _inv_edit_or_resend(call, text, markup):
    """Редактирует сообщение инвентаря. Если это фото — редактирует caption, не удаляя фото."""
    uid = call.from_user.id
    info = _inv_main_msg.get(uid, {})
    has_photo = info.get("has_photo", False)
    if has_photo:
        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=text, parse_mode="Markdown", reply_markup=markup
        )
    else:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text, parse_mode="Markdown", reply_markup=markup
        )

@bot.message_handler(commands=["myphones"])
def cmd_myphones(message):
    uid = message.from_user.id
    name = message.from_user.first_name or "игрок"
    caption = f"{name}, выберите категорию ваших телефонов:"
    inv_header = find_inv_header()
    if inv_header:
        with open(inv_header, "rb") as photo:
            msg = bot.send_photo(message.chat.id, photo, caption=caption, parse_mode="Markdown", reply_markup=inv_main_markup())
        _inv_main_msg[uid] = {"has_photo": True}
    else:
        text = f"{caption}"
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=inv_main_markup())
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
    bot.answer_callback_query(call.id, "Нерабочие телефоны пока недоступны", show_alert=False)

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
            msg = bot.send_photo(call.message.chat.id, photo, caption=text, parse_mode="Markdown", reply_markup=markup)
        _inv_action[uid] = {"msg_id": msg.message_id, "has_photo": True}
    else:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode="Markdown",
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
        f"**{name}**, вы уверены, что хотите продать **{act['phone_name']}** "
        f"за **{act['sell_price']}** ПОчек?"
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
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=msg_id, caption=text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=msg_id, text=text, parse_mode="Markdown", reply_markup=markup)
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

    text = f"Вы успешно продали **{phone_name}** за **{sell_price}** ПОчек!"
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
    bot.send_message(chat_id=call.message.chat.id, text=text, parse_mode="Markdown")
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
        f"📱 **МОИ ТЕЛЕФОНЫ**\n\n"
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
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=msg_id, caption=text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=msg_id, text=text, parse_mode="Markdown", reply_markup=markup)
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
            bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode="Markdown", reply_markup=markup)
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
        f"**{name}**, вы уверены, что хотите продать **{act['name']}** "
        f"за **{act['sell_price']}** ПОчек?"
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

    text = f"Вы успешно продали **{phone_name}** за **{sell_price}** ПОчек!"
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

print("Бот запущен!")
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка: {e}")
        time.sleep(5)
