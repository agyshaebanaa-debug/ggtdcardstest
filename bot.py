import asyncio
import logging
import random
import time
import io
import os
import math
import string
import html
import uuid
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    FSInputFile, BotCommand
)
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

try:
    from PIL import Image, ImageOps, ImageDraw
except ImportError:
    raise ImportError("Установите Pillow для генерации рамок карт: pip install Pillow")

import aiosqlite

BOT_TOKEN = "8887633400:AAEvlERe0CN1twoc01jGxYzSi8f9Kbwck1A"
SUPER_ADMIN_ID = 5341904332
DB_NAME = "cards_database.db"

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

RARITY_COLORS = {
    "Basic": "gray",
    "Uncommon": "green",
    "Rare": "deepskyblue",
    "Epic": "purple",
    "Legendary": "gold",
    "Mythic": "red",
    "Super": "rainbow",
    "Exclusive": "lightpink",
    "Leaderboard": "cyan",
    "Secret": "black" 
}

RARITY_EMOJI = {
    "Basic": "⚪",
    "Uncommon": "🟢",
    "Rare": "🔵",
    "Epic": "🟣",
    "Legendary": "🟡",
    "Mythic": "🔴",
    "Super": "🌈", 
    "Exclusive": "🌸",
    "Leaderboard": "👑",
    "Secret": "⬛"
}

CLASS_EMOJI = {
    "AOE": "🌪",
    "Splash": "🌊",
    "Booster": "✨",
    "Single": "🎯",
    "Fire": "🔥",
    "Healer": "💗"
}

CLASSES = list(CLASS_EMOJI.keys())

RARITY_WEIGHT = {
    "Secret": 10,
    "Leaderboard": 9, 
    "Exclusive": 8, 
    "Super": 7, 
    "Mythic": 6, 
    "Legendary": 5, 
    "Epic": 4, 
    "Rare": 3, 
    "Uncommon": 2, 
    "Basic": 1
}

active_combats = set()
active_trades = {}  
user_trades = {}    
pvp_queue = set()
active_manual_battles = {} 
surrendered_players = set() 

active_craft_sessions = {} 
active_upgrades = {}

SHOP_PACKAGES = [
    ("1_rnd", "1 Случайная карта", 100, 20, 1.0),
    ("3_rnd", "3 Случайные карты", 275, 20, 0.9),
    ("5_rnd", "5 Случайных карт", 450, 20, 0.9),
    ("10_rnd", "10 Случайных карт", 900, 15, 0.8),
    ("25_rnd", "25 Случайных карт", 2300, 10, 0.7),
    ("50_rnd", "50 Случайных карт", 4500, 3, 0.6),
    ("100_rnd", "100 Случайных карт", 9000, 2, 0.5),
    ("rnd_leg", "Случайная Легендарная", 1000, 5, 0.7), 
    ("rnd_myth", "Случайная Мифическая", 12500, 3, 0.4), 
    ("rnd_sup", "Случайная Супер Карта", 80000, 1, 0.2) 
]

QUEST_TEMPLATES = [
    {"id": "q_pve", "desc": "Сыграть {} PvE боёв", "target": (3, 7)},
    {"id": "q_pvp", "desc": "Сыграть {} PvP дуэлей", "target": (2, 5)},
    {"id": "q_open", "desc": "Открыть {} любых карт", "target": (5, 15)},
    {"id": "q_upgrade", "desc": "Улучшить мутацию {} раз", "target": (1, 3)},
    {"id": "q_craft", "desc": "Скрафтить {} карт", "target": (1, 2)}
]

UPDATE_LOGS = [
    "🛠 <b>Update 2: Donat, Modifications & Diamond Update!</b>\n\n"
    "• <b>Донат-Магазин (/donate)</b>: Две категории — F2P (за Робуксы R$) и P2W (за Telegram Stars ⭐️). Возможность покупать Робуксы по курсу 1 R$ = 1000 Шекелей, а также дарить любые геймпассы друзьям по ID или Юзернейму!\n"
    "• <b>Новые геймпассы</b>: Навсегда х2 Шекели, х2 Опыт pass, 5-й слот юнита, х1.5 Удача и VIP-Статус со множеством привилегий (скидки, дешевый крафт за 4 карты вместо 8)!\n"
    "• <b>Новая мутация Diamond 💎</b>: Шанс 5%, дает +30% к характеристикам! Перебалансированы Золотая (+15%) и Радужная (+45%) мутации.\n"
    "• <b>4 Новых модификатора боя</b>: 2 Дебаффа (Горение и Отключение хила) и 2 Баффа (Щит и Вампиризм).\n"
    "• <b>Система Гарантий (PITY) для паков</b>: Теперь суперадмины могут настраивать гарантированный выпадение карт!\n"
    "• <b>Улучшение рангов</b>: Ранги Uranium VI и VII стали чуть легче для прохождения.\n"
    "• <b>Трейды и промокоды исправлены</b>: Трейд больше не вылетает при добавлении, а промокоды теперь выпадают строго из пула созданных администрацией!"
]

BTN_DRAW = "🎴 Выбить карту"
BTN_PVE = "⚔️ Поиск боя (боты)"
BTN_PVP = "⚔️ PvP Дуэль"
BTN_INV = "🎒 Инвентарь"
BTN_PROF = "👤 Профиль"
BTN_EQ = "🛡 Экипировка"
BTN_QUESTS = "📜 Квесты"
BTN_SHOP = "🛒 Магазин"
BTN_BP = "🎟 Батл-пассы"
BTN_TOP = "🏆 Топ игроков"
BTN_IDX = "📖 Индекс"
BTN_SEED_PACKS = "📦 Сид-Паки"
BTN_MODIFIERS = "🧬 Модификаторы"
BTN_CRAFT = "🔨 Крафт"
BTN_SIGN = "✍️ Подписать карту"
BTN_ADM = "⚙️ Админ-панель"

async def get_db_connection():
    db = await aiosqlite.connect(DB_NAME)
    db.row_factory = aiosqlite.Row
    return db

async def execute_db(query, params=()):
    db = await get_db_connection()
    try:
        await db.execute(query, params)
        await db.commit()
    finally:
        await db.close()

async def fetch_one(query, params=()):
    db = await get_db_connection()
    try:
        async with db.execute(query, params) as cursor:
            result = await cursor.fetchone()
            return dict(result) if result else None
    finally:
        await db.close()

async def fetch_all(query, params=()):
    db = await get_db_connection()
    try:
        async with db.execute(query, params) as cursor:
            result = await cursor.fetchall()
            return [dict(row) for row in result]
    finally:
        await db.close()

async def check_and_update_schema():
    db = await get_db_connection()
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                coins INTEGER DEFAULT 0,
                trophies INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                last_getcard REAL DEFAULT 0,
                equip1 INTEGER DEFAULT 0,
                equip2 INTEGER DEFAULT 0,
                equip3 INTEGER DEFAULT 0,
                equip4 INTEGER DEFAULT 0,
                equip5 INTEGER DEFAULT 0,
                pity_mythic INTEGER DEFAULT 0,
                pity_super INTEGER DEFAULT 0,
                total_coins INTEGER DEFAULT 0,
                mod_enemy_hp INTEGER DEFAULT 0,
                mod_enemy_atk_all INTEGER DEFAULT 0,
                mod_enemy_stats INTEGER DEFAULT 0,
                mod_player_atk_all INTEGER DEFAULT 0,
                mod_manual_atk INTEGER DEFAULT 0,
                mod_player_hp INTEGER DEFAULT 0,
                mod_enemy_burn INTEGER DEFAULT 0,
                mod_no_heals INTEGER DEFAULT 0,
                mod_player_shield INTEGER DEFAULT 0,
                mod_player_vamp INTEGER DEFAULT 0,
                robux INTEGER DEFAULT 0,
                gp_double_coins INTEGER DEFAULT 0,
                gp_double_xp INTEGER DEFAULT 0,
                gp_fifth_slot INTEGER DEFAULT 0,
                gp_luck_boost INTEGER DEFAULT 0,
                gp_vip INTEGER DEFAULT 0
            )
        """)
        
        # Add newer columns if they do not exist
        for col, col_type in [
            ("equip5", "INTEGER DEFAULT 0"),
            ("mod_enemy_burn", "INTEGER DEFAULT 0"),
            ("mod_no_heals", "INTEGER DEFAULT 0"),
            ("mod_player_shield", "INTEGER DEFAULT 0"),
            ("mod_player_vamp", "INTEGER DEFAULT 0"),
            ("robux", "INTEGER DEFAULT 0"),
            ("gp_double_coins", "INTEGER DEFAULT 0"),
            ("gp_double_xp", "INTEGER DEFAULT 0"),
            ("gp_fifth_slot", "INTEGER DEFAULT 0"),
            ("gp_luck_boost", "INTEGER DEFAULT 0"),
            ("gp_vip", "INTEGER DEFAULT 0")
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            except aiosqlite.OperationalError:
                pass
                
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_dynamic_quests (
                user_id INTEGER PRIMARY KEY,
                q1_id TEXT, q1_target INTEGER, q1_prog INTEGER DEFAULT 0,
                q2_id TEXT, q2_target INTEGER, q2_prog INTEGER DEFAULT 0,
                q3_id TEXT, q3_target INTEGER, q3_prog INTEGER DEFAULT 0,
                reset_time REAL DEFAULT 0
            )
        """)
            
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                rarity TEXT,
                class_type TEXT,
                damage INTEGER DEFAULT 0,
                hp INTEGER DEFAULT 0,
                drop_chance REAL DEFAULT 0,
                photo_id TEXT,
                booster_dmg_mult REAL DEFAULT 1.0,
                booster_hp_mult REAL DEFAULT 1.0,
                is_cardball_exclusive INTEGER DEFAULT 0
            )
        """)
        
        try:
            await db.execute("ALTER TABLE cards ADD COLUMN is_cardball_exclusive INTEGER DEFAULT 0")
        except aiosqlite.OperationalError:
            pass
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                card_id INTEGER,
                count INTEGER DEFAULT 1,
                mutation TEXT DEFAULT 'Normal',
                serial_number INTEGER DEFAULT 0,
                signed_by INTEGER DEFAULT 0,
                is_football INTEGER DEFAULT 0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ranks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                min_trophies INTEGER,
                difficulty_mult REAL DEFAULT 1.0,
                reward_mult REAL DEFAULT 1.0
            )
        """)

        # Resetting and defining new balanced ranks
        await db.execute("DELETE FROM ranks")
        default_ranks = [
            ("🟤 Bronze I", 0, 0.8, 1.0), ("🟤 Bronze II", 50, 0.85, 1.05), ("🟤 Bronze III", 100, 0.9, 1.1), ("🟤 Bronze IV", 150, 0.95, 1.15),
            ("⚪ Silver I", 200, 1.0, 1.2), ("⚪ Silver II", 300, 1.05, 1.25), ("⚪ Silver III", 400, 1.1, 1.3), ("⚪ Silver IV", 500, 1.15, 1.35),
            ("🟡 Gold I", 650, 1.2, 1.4), ("🟡 Gold II", 800, 1.3, 1.5), ("🟡 Gold III", 950, 1.4, 1.6), ("🟡 Gold IV", 1100, 1.5, 1.7),
            ("🟢 Platina I", 1300, 1.8, 1.8), ("🟢 Platina II", 1500, 2.5, 1.9), ("🟢 Platina III", 1700, 3.2, 2.0), ("🟢 Platina IV", 1900, 4.0, 2.1),
            ("💎 Diamond I", 2200, 5.0, 2.5), ("💎 Diamond II", 2500, 6.5, 2.8), ("💎 Diamond III", 2800, 8.0, 3.2), ("💎 Diamond IV", 3100, 10.0, 3.6),
            ("🔴 Ruby I", 3500, 13.0, 4.0), ("🔴 Ruby II", 4000, 15.0, 4.5), ("🔴 Ruby III", 4500, 17.0, 5.0), ("🔴 Ruby IV", 5000, 20.0, 5.5),
            ("☢️ Uranium I", 5700, 21.0, 6.0), ("☢️ Uranium II", 6500, 24.0, 6.5), ("☢️ Uranium III", 7400, 27.0, 7.0), ("☢️ Uranium IV", 8400, 30.0, 7.5), ("☢️ Uranium V", 9500, 33.0, 8.0),
            ("🌌 Uranium VI", 10000, 15.0, 9.0), ("🌌 Uranium VII", 15000, 20.0, 10.0)
        ]
        for r in default_ranks:
            await db.execute("INSERT INTO ranks (name, min_trophies, difficulty_mult, reward_mult) VALUES (?, ?, ?, ?)", r)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                id INTEGER PRIMARY KEY,
                min_coins INTEGER DEFAULT 50,
                max_coins INTEGER DEFAULT 200,
                luck_mult REAL DEFAULT 1.0,
                luck_end REAL DEFAULT 0,
                cd_mult REAL DEFAULT 1.0,
                cd_end REAL DEFAULT 0,
                last_restock REAL DEFAULT 0,
                last_lb_reward REAL DEFAULT 0,
                coin_mult REAL DEFAULT 1.0,
                coin_end REAL DEFAULT 0,
                xp_mult REAL DEFAULT 1.0,
                xp_end REAL DEFAULT 0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seed_packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                photo_id TEXT,
                description TEXT,
                price INTEGER DEFAULT 2000,
                is_football INTEGER DEFAULT 0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seed_pack_cards (
                pack_id INTEGER,
                card_id INTEGER,
                drop_chance REAL,
                PRIMARY KEY (pack_id, card_id)
            )
        """)

        # New tables for Seed Pack Pity systems
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seed_pack_pity (
                pack_id INTEGER,
                card_id INTEGER,
                pity_threshold INTEGER DEFAULT 0,
                PRIMARY KEY (pack_id, card_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_pack_opening_stats (
                user_id INTEGER,
                pack_id INTEGER,
                card_id INTEGER,
                open_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, pack_id, card_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_seed_packs (
                user_id INTEGER,
                pack_id INTEGER,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, pack_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                item_type TEXT, 
                name TEXT, 
                price INTEGER, 
                stock INTEGER, 
                is_football INTEGER DEFAULT 0
            )
        """)

        await db.execute("""CREATE TABLE IF NOT EXISTS admin_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS lb_rewards (id INTEGER PRIMARY KEY AUTOINCREMENT, bracket TEXT, reward_type TEXT, amount INTEGER DEFAULT 0, card_id INTEGER DEFAULT 0, mutation TEXT DEFAULT 'Normal', lb_type TEXT DEFAULT 'trophies')""")
        await db.execute("""CREATE TABLE IF NOT EXISTS authorized_signers (user_id INTEGER PRIMARY KEY)""")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS battle_passes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                photo_id TEXT,
                created_at REAL,
                is_football INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bp_levels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bp_id INTEGER,
                level INTEGER,
                xp_required INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bp_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level_id INTEGER,
                reward_type TEXT,
                amount INTEGER DEFAULT 0,
                card_id INTEGER DEFAULT 0,
                mutation TEXT DEFAULT 'Normal'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_bp (
                user_id INTEGER,
                bp_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, bp_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_bp_claims (
                user_id INTEGER,
                bp_id INTEGER,
                level INTEGER,
                PRIMARY KEY (user_id, bp_id, level)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reward_codes (
                code TEXT PRIMARY KEY,
                reward_type TEXT,
                amount INTEGER DEFAULT 0,
                item_id INTEGER DEFAULT 0,
                mutation TEXT DEFAULT 'Normal',
                owner_id INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                is_football INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS craft_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_card_id INTEGER,
                price INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS craft_ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER,
                card_id INTEGER,
                amount INTEGER DEFAULT 1
            )
        """)

        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (SUPER_ADMIN_ID,))
        await db.execute("INSERT OR IGNORE INTO server_settings (id) VALUES (1)")
        await db.commit()
    finally:
        await db.close()

async def log_user_action(user_id: int, action: str):
    try:
        await execute_db("INSERT INTO user_action_logs (user_id, action) VALUES (?, ?)", (user_id, action))
    except Exception as e:
        logging.error(f"Failed to log user action: {e}")

class AddCard(StatesGroup):
    photo = State()
    name = State()
    drop_chance = State()
    rarity = State()
    class_type = State()
    damage = State()
    hp = State()
    booster_dmg = State()
    booster_hp = State()
    is_cardball_exclusive = State()

class EditCard(StatesGroup):
    waiting_new_value = State()

class GiveCard(StatesGroup):
    user_id = State()
    card_id = State()
    mutation = State()
    custom_serial = State()

class TakeCard(StatesGroup):
    user_id = State()
    inv_id = State()
    amount = State()

class AdminBan(StatesGroup):
    user_id = State()

class AdminManage(StatesGroup):
    add_id = State()
    del_id = State()
    reset_battle_id = State()
    give_coins_id = State()
    give_coins_amount = State()
    give_trophies_id = State()
    give_trophies_amount = State()
    view_logs_id = State()
    gp_user_id = State()
    gp_item_id = State()
    
class AdminLBRewards(StatesGroup):
    bracket = State()
    reward_type = State() 
    amount = State()
    card_id = State()
    mutation = State()

class AdminBPCreation(StatesGroup):
    is_football = State()
    title = State()
    photo = State()
    levels_count = State()
    level_xp = State()
    reward_action = State()
    reward_shekels = State()
    reward_card = State()
    reward_mutation = State()

class AdminBPEdit(StatesGroup):
    select_bp = State()
    edit_menu = State()
    edit_title = State()
    edit_photo = State()

class AdminSigner(StatesGroup):
    add_id = State()

class EventLuck(StatesGroup):
    mult = State()
    mins = State()

class EventCD(StatesGroup):
    mult = State()
    mins = State()

class EventCoin(StatesGroup):
    mult = State()
    mins = State()

class EventXP(StatesGroup):
    mult = State()
    mins = State()

class AdminAnnounce(StatesGroup):
    content = State()

class PvPState(StatesGroup):
    waiting_target = State()

class TradeState(StatesGroup):
    waiting_target = State()
    waiting_robux = State()

class CreateSeedPack(StatesGroup):
    is_football = State()
    title = State()
    photo = State()
    description = State()
    price = State()
    card_select = State()
    card_chance = State()
    confirm_save = State()
    pity_card_select = State()
    pity_card_threshold = State()

class EditSeedPack(StatesGroup):
    select_pack = State()
    menu = State()
    edit_title = State()
    edit_photo = State()
    edit_description = State()
    edit_price = State()
    card_edit_chance = State()
    add_card_select = State()
    add_card_chance = State()

class AdminRewardCode(StatesGroup):
    count = State()
    r_type = State()
    amount = State()
    card_id = State()
    mutation = State()
    pack_id = State()
    is_football = State()

class UserUseCode(StatesGroup):
    waiting_code = State()

class AdminCraftCreate(StatesGroup):
    target_card = State()
    price = State()
    add_ingredient_card = State()
    add_ingredient_amount = State()

class AdminCraftEdit(StatesGroup):
    menu = State()
    edit_price = State()
    add_ing_card = State()
    add_ing_amount = State()

class DonateGiftState(StatesGroup):
    waiting_friend = State()
    confirm_gift = State()

class FakeCall:
    def __init__(self, message, data):
        self.message = message
        self.data = data
        self.from_user = message.from_user

def get_display_name(user_data: dict) -> str:
    if user_data.get('username'): 
        return html.escape(f"@{user_data['username']}")
    elif user_data.get('first_name'): 
        return html.escape(user_data['first_name'])
    return f"Player {user_data.get('id', '???')}"

async def get_user_titles_str(user_id: int) -> str:
    titles = []
    user = await fetch_one("SELECT gp_vip FROM users WHERE id = ?", (user_id,))
    if user and user.get("gp_vip") == 1:
        titles.append("💎 VIP")
    if await is_admin(user_id): 
        titles.append("👑 Администратор")
    if await is_signer(user_id): 
        titles.append("✍️ Сигнер")
    if titles: 
        return f" [<i>{', '.join(titles)}</i>]"
    return ""

def make_progress_bar(current, total, length=10):
    if total <= 0: return "🟩" * length
    pct = min(1.0, current / total)
    filled = int(pct * length)
    empty = length - filled
    return "🟩" * filled + "⬜" * empty

async def generate_dynamic_quests(user_id: int):
    now = time.time()
    db = await get_db_connection()
    try:
        user_q = await db.execute("SELECT * FROM user_dynamic_quests WHERE user_id = ?", (user_id,))
        uq = await user_q.fetchone()
        
        if not uq or uq['reset_time'] < now:
            chosen = random.sample(QUEST_TEMPLATES, 3)
            q1_t = random.randint(chosen[0]['target'][0], chosen[0]['target'][1])
            q2_t = random.randint(chosen[1]['target'][0], chosen[1]['target'][1])
            q3_t = random.randint(chosen[2]['target'][0], chosen[2]['target'][1])
            
            next_hour = (int(now) // 3600 + 1) * 3600
            
            if uq:
                await db.execute("""
                    UPDATE user_dynamic_quests SET 
                    q1_id = ?, q1_target = ?, q1_prog = 0,
                    q2_id = ?, q2_target = ?, q2_prog = 0,
                    q3_id = ?, q3_target = ?, q3_prog = 0,
                    reset_time = ? WHERE user_id = ?
                """, (chosen[0]['id'], q1_t, chosen[1]['id'], q2_t, chosen[2]['id'], q3_t, next_hour, user_id))
            else:
                await db.execute("""
                    INSERT INTO user_dynamic_quests (user_id, q1_id, q1_target, q2_id, q2_target, q3_id, q3_target, reset_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, chosen[0]['id'], q1_t, chosen[1]['id'], q2_t, chosen[2]['id'], q3_t, next_hour))
            await db.commit()
    finally:
        await db.close()

async def add_quest_progress_new(user_id: int, quest_type: str, amount: int = 1):
    await generate_dynamic_quests(user_id)
    db = await get_db_connection()
    try:
        user_q = await db.execute("SELECT * FROM user_dynamic_quests WHERE user_id = ?", (user_id,))
        uq = await user_q.fetchone()
        if not uq: return
        
        uq_dict = dict(uq)
        updated = False
        
        for i in range(1, 4):
            if uq_dict[f'q{i}_id'] == quest_type and uq_dict[f'q{i}_prog'] < uq_dict[f'q{i}_target']:
                new_prog = min(uq_dict[f'q{i}_target'], uq_dict[f'q{i}_prog'] + amount)
                await db.execute(f"UPDATE user_dynamic_quests SET q{i}_prog = ? WHERE user_id = ?", (new_prog, user_id))
                uq_dict[f'q{i}_prog'] = new_prog
                updated = True
                
        if updated:
            if uq_dict['q1_prog'] >= uq_dict['q1_target'] and uq_dict['q2_prog'] >= uq_dict['q2_target'] and uq_dict['q3_prog'] >= uq_dict['q3_target']:
                
                # Double Coins or VIP rewards
                vip_user = await fetch_one("SELECT gp_vip FROM users WHERE id = ?", (user_id,))
                craft_mult = 1.5 if (vip_user and vip_user['gp_vip'] == 1) else 1.0
                coins_won = int(1500 * craft_mult)
                
                await db.execute("UPDATE users SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (coins_won, coins_won, user_id))
                next_hour = (int(time.time()) // 3600 + 1) * 3600
                await db.execute("UPDATE user_dynamic_quests SET reset_time = ? WHERE user_id = ?", (next_hour, user_id))
                
                packs = await fetch_all("SELECT id, title FROM seed_packs WHERE is_football = 0")
                pack_reward_text = ""
                if packs:
                    gift_pack = random.choice(packs)
                    await db.execute("""
                        INSERT INTO user_seed_packs (user_id, pack_id, count)
                        VALUES (?, ?, 1)
                        ON CONFLICT(user_id, pack_id) DO UPDATE SET count = count + 1
                    """, (user_id, gift_pack['id']))
                    pack_reward_text = f"\n📦 А также вы получили Сид-Пак: <b>{gift_pack['title']}</b> (1 шт.)!"
                
                try:
                    msg = f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\nВы выполнили все задания этого часа и получили <b>{coins_won} 💰 Шекелей</b>!{pack_reward_text}\nНовые квесты появятся в начале следующего часа!"
                    await bot.send_message(user_id, msg)
                except: 
                    pass
        await db.commit()
    finally:
        await db.close()

async def is_admin(user_id: int) -> bool:
    if user_id == SUPER_ADMIN_ID: return True
    res = await fetch_one("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    return bool(res)

async def is_signer(user_id: int) -> bool:
    if user_id == SUPER_ADMIN_ID: return True
    res = await fetch_one("SELECT 1 FROM authorized_signers WHERE user_id = ?", (user_id,))
    return bool(res)

async def check_ban(user_id: int) -> bool:
    res = await fetch_one("SELECT banned FROM users WHERE id = ?", (user_id,))
    return bool(res and res['banned'] == 1)

async def notify_super_admin(text: str):
    try: 
        await bot.send_message(SUPER_ADMIN_ID, f"⚠️ <b>ADMIN LOG:</b>\n{text}")
    except Exception as e: 
        logging.error(f"Не удалось отправить лог: {e}")

async def log_admin(admin_id: int, action: str):
    await execute_db("INSERT INTO admin_logs (admin_id, action) VALUES (?, ?)", (admin_id, action))
    admin_info = await fetch_one("SELECT username, first_name FROM users WHERE id = ?", (admin_id,))
    name = get_display_name(admin_info) if admin_info else f"ID {admin_id}"
    await notify_super_admin(f"Admin: <b>{name}</b> ({admin_id})\nAction: {action}")

async def broadcast_message(text_ru: str, notif_type: str = None, shop_types: set = None):
    query = "SELECT * FROM users WHERE banned = 0"
    users = await fetch_all(query)
    success = 0
    for u in users:
        try:
            await bot.send_message(u['id'], text_ru)
            success += 1
            await asyncio.sleep(0.05)
        except: 
            pass
    await notify_super_admin(f"📢 <b>Broadcast complete.</b>\nDelivered: {success}")

def get_main_keyboard(is_adm: bool = False, is_sgn: bool = False, is_football: bool = False):
    kb = [
        [KeyboardButton(text=BTN_DRAW), KeyboardButton(text=BTN_PVE), KeyboardButton(text=BTN_PVP)],
        [KeyboardButton(text=BTN_INV), KeyboardButton(text=BTN_PROF), KeyboardButton(text=BTN_EQ)],
        [KeyboardButton(text=BTN_QUESTS), KeyboardButton(text=BTN_SHOP), KeyboardButton(text=BTN_BP)],
        [KeyboardButton(text=BTN_TOP), KeyboardButton(text=BTN_IDX), KeyboardButton(text=BTN_SEED_PACKS)],
        [KeyboardButton(text=BTN_CRAFT), KeyboardButton(text=BTN_MODIFIERS)]
    ]
    
    bottom_row = []
    if is_sgn: bottom_row.append(KeyboardButton(text=BTN_SIGN))
    if is_adm: bottom_row.append(KeyboardButton(text=BTN_ADM))
    if bottom_row: kb.append(bottom_row)
        
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def get_user_rank(trophies: int):
    ranks = await fetch_all("SELECT * FROM ranks ORDER BY min_trophies DESC")
    for idx, r in enumerate(ranks):
        if trophies >= r['min_trophies']: 
            res = dict(r)
            res['rank_idx'] = len(ranks) - idx - 1
            return res
    return {"name": "🟤 Bronze I", "difficulty_mult": 0.8, "reward_mult": 1.0, "rank_idx": 0}

async def get_active_events(user_id: int = 0):
    settings = await fetch_one("SELECT * FROM server_settings WHERE id = 1")
    now = time.time()
    luck = settings['luck_mult'] if settings['luck_end'] > now else 1.0
    cd = settings['cd_mult'] if settings['cd_end'] > now else 1.0
    
    # VIP / Gamepass luck bonus (Staks)
    if user_id > 0:
        usr = await fetch_one("SELECT gp_luck_boost, gp_vip FROM users WHERE id = ?", (user_id,))
        if usr:
            if usr.get("gp_luck_boost") == 1:
                luck *= 1.5
            if usr.get("gp_vip") == 1:
                luck *= 1.3
                
    return luck, cd

async def get_coin_xp_events(user_id: int = 0):
    settings = await fetch_one("SELECT * FROM server_settings WHERE id = 1")
    now = time.time()
    coin_mult = settings['coin_mult'] if settings['coin_end'] > now else 1.0
    xp_mult = settings['xp_mult'] if settings['xp_end'] > now else 1.0
    
    # VIP / Gamepass coin multipliers
    if user_id > 0:
        usr = await fetch_one("SELECT gp_double_coins, gp_double_xp, gp_vip FROM users WHERE id = ?", (user_id,))
        if usr:
            if usr.get("gp_double_coins") == 1:
                coin_mult *= 2.0
            if usr.get("gp_double_xp") == 1:
                xp_mult *= 2.0
            if usr.get("gp_vip") == 1:
                coin_mult *= 1.5
                xp_mult *= 1.5
                
    return coin_mult, xp_mult

def roll_mutation():
    r = random.random()
    if r <= 0.009: return "Rainbow"
    if r <= 0.059: return "Diamond"
    if r <= 0.209: return "Gold"
    return "Normal"

def roll_seed_pack_mutation():
    r = random.random()
    if r <= 0.015: return "Rainbow"
    if r <= 0.065: return "Diamond"
    if r <= 0.250: return "Gold"
    return "Normal"

def get_mutation_multiplier(mutation: str) -> float:
    if mutation == "Rainbow": return 1.45
    if mutation == "Diamond": return 1.30
    if mutation == "Gold": return 1.15
    return 1.0

def needs_serial_number(rarity: str, mutation: str) -> bool:
    if rarity in ['Leaderboard', 'Exclusive', 'Mythic', 'Super', 'Secret']: return True
    if rarity == 'Legendary' and mutation in ['Gold', 'Diamond', 'Rainbow']: return True
    return False

async def give_card_to_user(user_id: int, card_id: int, mutation: str, rarity: str = None, custom_serial: int = None, is_football: int = 0) -> tuple:
    if not rarity:
        card = await fetch_one("SELECT rarity FROM cards WHERE id = ?", (card_id,))
        rarity = card['rarity'] if card else 'Basic'
        
    db = await get_db_connection()
    try:
        if custom_serial is not None and custom_serial > 0:
            cursor = await db.execute(
                "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, ?, 0, ?)",
                (user_id, card_id, mutation, custom_serial, is_football)
            )
            return cursor.lastrowid, custom_serial, True
            
        if needs_serial_number(rarity, mutation):
            res = await db.execute("SELECT MAX(serial_number) as m FROM inventory WHERE card_id = ? AND mutation = ?", (card_id, mutation))
            row = await res.fetchone()
            curr_max = row['m'] if (row and row['m'] is not None) else 0
            new_serial = curr_max + 1
            
            cursor = await db.execute(
                "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, ?, 0, ?)", 
                (user_id, card_id, mutation, new_serial, is_football)
            )
            return cursor.lastrowid, new_serial, True
        else:
            res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0 AND is_football = ?", (user_id, card_id, mutation, is_football))
            inv_item = await res.fetchone()
            if inv_item:
                await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                return inv_item['id'], 0, False
            else:
                cursor = await db.execute(
                    "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, 0, 0, ?)", 
                    (user_id, card_id, mutation, is_football)
                )
                return cursor.lastrowid, 0, True
    finally:
        await db.commit()
        await db.close()

async def create_bordered_image(bot: Bot, photo_id: str, rarity: str) -> str:
    color = RARITY_COLORS.get(rarity, "gray")
    file = await bot.get_file(photo_id)
    file_bytes = await bot.download_file(file.file_path)
    
    img = Image.open(file_bytes).convert("RGBA")
    width, height = img.size
    
    bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if color == "rainbow":
        for y in range(height):
            r = int(255 * (1 + math.sin(y / height * math.pi * 2)) / 2)
            g = int(255 * (1 + math.sin(y / height * math.pi * 2 + 2*math.pi/3)) / 2)
            b = int(255 * (1 + math.sin(y / height * math.pi * 2 + 4*math.pi/3)) / 2)
            for x in range(width):
                bg.putpixel((x, y), (r, g, b, 255))
    else:
        bg = Image.new("RGBA", (width, height), color)

    img_temp = Image.new("RGBA", bg.size)
    img_temp.paste(img, (0, 0), img)
    final_rgba = Image.alpha_composite(bg, img_temp)
    final_img = final_rgba.convert("RGB")
    
    border_color = "purple" if color == "rainbow" else color
    bordered_img = ImageOps.expand(final_img, border=20, fill=border_color)
    
    bio = io.BytesIO()
    bordered_img.save(bio, format='JPEG')
    bio.seek(0)
    
    msg = await bot.send_photo(chat_id=SUPER_ADMIN_ID, photo=types.BufferedInputFile(bio.read(), filename="card.jpg"), caption=f"Generated frame: {rarity}")
    return msg.photo[-1].file_id

def format_card_name(c):
    r_em = RARITY_EMOJI.get(c.get('rarity', 'Basic'), "⚪")
    c_em = CLASS_EMOJI.get(c.get('class_type', 'Single'), "🎯")
    mut_icon = ""
    if c.get('mutation') == 'Rainbow': mut_icon = "🌈 "
    elif c.get('mutation') == 'Diamond': mut_icon = "💎 "
    elif c.get('mutation') == 'Gold': mut_icon = "⭐ "
    
    name = f"{r_em} {c_em} <b>{mut_icon}{html.escape(c['name'])}</b>"
    if c.get('serial_number', 0) > 0:
        name += f" <b>[#{c['serial_number']:04d}]</b>"
    if c.get('signed_by', 0) > 0:
        signer_name = c.get('signer_name') or f"ID:{c['signed_by']}"
        name += f" <i>(✍️ Sign: {signer_name})</i>"
    return name

def format_card_name_plain(c):
    r_em = RARITY_EMOJI.get(c.get('rarity', 'Basic'), "⚪")
    c_em = CLASS_EMOJI.get(c.get('class_type', 'Single'), "🎯")
    mut_icon = ""
    if c.get('mutation') == 'Rainbow': mut_icon = "🌈 "
    elif c.get('mutation') == 'Diamond': mut_icon = "💎 "
    elif c.get('mutation') == 'Gold': mut_icon = "⭐ "
    
    name = f"{r_em} {c_em} {mut_icon}{c['name']}"
    if c.get('serial_number', 0) > 0:
        name += f" [#{c['serial_number']:04d}]"
    if c.get('signed_by', 0) > 0:
        signer_name = c.get('signer_name') or f"ID:{c['signed_by']}"
        name += f" (✍️ Sign: {signer_name})"
    return name

def format_rarity_display(rarity):
    r_em = RARITY_EMOJI.get(rarity, "⚪")
    return f"{r_em} <b>{rarity.upper()}</b> {r_em}"

def get_pagination_keyboard(items, page, prefix, columns=2, items_per_page=8):
    total_pages = max(1, math.ceil(len(items) / items_per_page))
    page = max(0, min(page, total_pages - 1))
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = items[start_idx:end_idx]
    kb = []
    row = []
    for item in page_items:
        row.append(InlineKeyboardButton(text=item['btn_text'], callback_data=f"{prefix}_{item['id']}"))
        if len(row) == columns:
            kb.append(row)
            row = []
    if row: kb.append(row)
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}_page_{page-1}"))
    if total_pages > 1: nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}_page_{page+1}"))
    if nav_row: kb.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def generate_reward_code() -> str:
    return str(uuid.uuid4()).replace('-', '')[:28].upper()

async def clear_fsm_timeout(state: FSMContext, chat_id: int, delay: int = 60):
    await asyncio.sleep(delay)
    curr = await state.get_state()
    if curr in [TradeState.waiting_target.state, PvPState.waiting_target.state]:
        await state.clear()
        try:
            await bot.send_message(chat_id, "⏳ <i>Время ожидания истекло (1 минута). Действие отменено.</i>")
        except: 
            pass

async def get_card_sources(card_id: int) -> str:
    sources = []
    packs = await fetch_all("SELECT p.title FROM seed_pack_cards spc JOIN seed_packs p ON spc.pack_id = p.id WHERE spc.card_id = ?", (card_id,))
    if packs:
        sources.append("📦 Сид-Паки: " + ", ".join([p['title'] for p in packs]))
    
    c = await fetch_one("SELECT drop_chance, rarity FROM cards WHERE id = ?", (card_id,))
    if c:
        if c['drop_chance'] > 0 and c['rarity'] not in ['Leaderboard', 'Secret']:
            sources.append("🎲 Гача (/getcard) / Магазин")
        if c['rarity'] == 'Leaderboard':
            sources.append("🏆 Топ игроков (Лидерборд)")
            
    bps = await fetch_all("SELECT bp.title FROM bp_rewards bpr JOIN bp_levels bpl ON bpr.level_id = bpl.id JOIN battle_passes bp ON bpl.bp_id = bp.id WHERE bpr.card_id = ?", (card_id,))
    if bps:
        sources.append("🎟 Батл-Пасс: " + ", ".join(list(set([b['title'] for b in bps]))))
        
    craft = await fetch_one("SELECT id FROM craft_recipes WHERE target_card_id = ?", (card_id,))
    if craft: sources.append("🔨 Мастерская Крафта")

    if not sources:
        return "Невозможно получить (Эксклюзив или Секрет)"
    return "\n".join(f"  └ {s}" for s in sources)

async def calculate_chance_weights(luck_mult: float = 1.0, exclude_cardball=True):
    query = """
        SELECT * FROM cards 
        WHERE drop_chance > 0 
        AND rarity NOT IN ('Leaderboard', 'Secret')
        AND id NOT IN (SELECT card_id FROM seed_pack_cards)
    """
    if exclude_cardball:
        query += " AND is_cardball_exclusive = 0"
        
    all_cards = await fetch_all(query)
    if not all_cards: return [], 0
    total_weight = 0
    weights_dict = {}
    for c in all_cards:
        weight = c['drop_chance']
        if weight < 15.0: weight *= luck_mult
        weights_dict[c['id']] = weight
        total_weight += weight
    return weights_dict, total_weight

async def restock_shop():
    await execute_db("DELETE FROM shop_items")
    db = await get_db_connection()
    spawned_types = set()
    try:
        spawned_any = False
        for p_id, p_name_ru, p_price, p_max, p_chance in SHOP_PACKAGES:
            if random.random() <= p_chance:
                stock = random.randint(1, p_max)
                await db.execute("INSERT INTO shop_items (item_type, name, price, stock, is_football) VALUES (?, ?, ?, ?, 0)", (p_id, p_name_ru, p_price, stock))
                spawned_any = True
                spawned_types.add(p_id)
                
        await db.execute("UPDATE server_settings SET last_restock = ? WHERE id = 1", (time.time(),))
        await db.commit()
    finally:
        await db.close()
        
    if spawned_any:
        msg_ru = "🛒 <b>МАГАЗИНЫ ОБНОВЛЕНЫ!</b>\nЗавезли свежие наборы карт. Количество ограничено, успей купить!"
        asyncio.create_task(broadcast_message(msg_ru, notif_type="notif_shop", shop_types=spawned_types))

async def shop_auto_restock_task():
    while True:
        try:
            settings = await fetch_one("SELECT last_restock FROM server_settings WHERE id = 1")
            now = time.time()
            if settings and (now - settings['last_restock'] >= 1.5 * 3600):
                await restock_shop()
        except Exception as e:
            logging.error(f"Shop restock error: {e}")
        await asyncio.sleep(60)

async def give_multiple_cards(user_id: int, count: int, is_football: int = 0) -> list:
    luck_mult, _ = await get_active_events(user_id)
    user = await fetch_one("SELECT pity_mythic, pity_super FROM users WHERE id=?", (user_id,))
    pm = user['pity_mythic'] if user else 0
    ps = user['pity_super'] if user else 0

    query = """
        SELECT * FROM cards 
        WHERE drop_chance > 0 
        AND rarity NOT IN ('Leaderboard', 'Secret')
        AND id NOT IN (SELECT card_id FROM seed_pack_cards)
        AND is_cardball_exclusive = 0
    """
        
    all_cards = await fetch_all(query)
    if not all_cards: return []
    
    super_cards = [c for c in all_cards if c['rarity'] == 'Super']
    mythic_cards = [c for c in all_cards if c['rarity'] == 'Mythic']
    weights = [c['drop_chance'] * (luck_mult if c['drop_chance'] < 15.0 else 1.0) for c in all_cards]
    
    results = []
    for _ in range(count):
        card = random.choices(all_cards, weights=weights, k=1)[0]
        is_pity = False
        p_type = None

        if ps + 1 >= 10000 and card['rarity'] != 'Super' and super_cards:
            card = random.choice(super_cards)
            is_pity = True
            p_type = 'Super'
        elif pm + 1 >= 1000 and card['rarity'] not in ['Mythic', 'Super'] and mythic_cards:
            card = random.choice(mythic_cards)
            is_pity = True
            p_type = 'Mythic'

        if card['rarity'] == 'Super': 
            ps = 0; pm += 1
        elif card['rarity'] == 'Mythic': 
            pm = 0; ps += 1
        else: 
            ps += 1; pm += 1

        mut = roll_mutation()
        _, serial, _ = await give_card_to_user(user_id, card['id'], mut, card['rarity'], is_football=0)

        c_copy = dict(card)
        c_copy['mutation'] = mut
        c_copy['serial_number'] = serial
        c_copy['is_pity'] = is_pity
        c_copy['pity_type'] = p_type
        c_copy['signed_by'] = 0
        results.append(c_copy)

    await execute_db("UPDATE users SET pity_mythic=?, pity_super=? WHERE id=?", (pm, ps, user_id))
    return results

async def leaderboard_rewards_task():
    while True:
        try:
            settings = await fetch_one("SELECT last_lb_reward FROM server_settings WHERE id = 1")
            now = time.time()
            if settings and (now - settings['last_lb_reward'] >= 2 * 24 * 3600):
                
                for lb_type in ['trophies', 'coins', 'cards']:
                    if lb_type == 'trophies':
                        top_users = await fetch_all("SELECT id, trophies as score, username, first_name FROM users WHERE id != ? ORDER BY trophies DESC LIMIT 20", (SUPER_ADMIN_ID,))
                    elif lb_type == 'coins':
                        top_users = await fetch_all("SELECT id, total_coins as score, username, first_name FROM users WHERE id != ? ORDER BY total_coins DESC LIMIT 20", (SUPER_ADMIN_ID,))
                    else:
                        top_users = await fetch_all("""
                            SELECT u.id, SUM(i.count) as score, u.username, u.first_name 
                            FROM users u JOIN inventory i ON u.id = i.user_id 
                            WHERE u.id != ? AND i.is_football = 0 GROUP BY u.id ORDER BY score DESC LIMIT 20
                        """, (SUPER_ADMIN_ID,))

                    if top_users:
                        for idx, user in enumerate(top_users):
                            pos = idx + 1
                            if pos == 1: bracket = "1"
                            elif pos == 2: bracket = "2"
                            elif pos == 3: bracket = "3"
                            elif pos <= 9: bracket = "4_9"
                            else: bracket = "10_20"
                            
                            rewards = await fetch_all("SELECT * FROM lb_rewards WHERE bracket = ? AND lb_type = ?", (bracket, lb_type))
                            reward_msgs_ru = []
                            for r in rewards:
                                if r['reward_type'] == 'shekels':
                                    await execute_db("UPDATE users SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (r['amount'], r['amount'], user['id']))
                                    reward_msgs_ru.append(f"💰 {r['amount']} Шекелей")
                                elif r['reward_type'] == 'card':
                                    c_info = await fetch_one("SELECT name, rarity FROM cards WHERE id = ?", (r['card_id'],))
                                    if c_info:
                                        _, serial, _ = await give_card_to_user(user['id'], r['card_id'], r['mutation'], c_info['rarity'])
                                        mut_str = "🌈" if r['mutation'] == 'Rainbow' else ("💎" if r['mutation'] == 'Diamond' else ("⭐" if r['mutation'] == 'Gold' else ""))
                                        s_str = f" [#{serial:04d}]" if serial > 0 else ""
                                        reward_msgs_ru.append(f"🃏 {mut_str} {c_info['name']}{s_str}")
                                        
                            if rewards:
                                lb_name_ru = "Кубки (Сезон)" if lb_type == 'trophies' else ("Шекели (Все время)" if lb_type == 'coins' else "Карты (Все время)")
                                msg_text = f"🏆 <b>ГРАНДИОЗНАЯ НАГРАДА ЗА ТОП ИГРОКОВ ({lb_name_ru})!</b> 🏆\n\nПоздравляем! Вы заняли <b>{pos} место</b> в мире!\n\n🎁 <b>Награда:</b>\n" + "\n".join([f"🔸 {m}" for m in reward_msgs_ru])
                                try: 
                                    await bot.send_message(user['id'], msg_text)
                                except: 
                                    pass
                
                await execute_db("UPDATE server_settings SET last_lb_reward = ? WHERE id = 1", (now,))
        except Exception as e:
            logging.error(f"LB Rewards error: {e}")
        await asyncio.sleep(600)

async def auto_backup_db():
    try:
        file = FSInputFile(DB_NAME)
        await bot.send_document(SUPER_ADMIN_ID, file, caption="📦 Автоматический бэкап БД при запуске/обновлении.")
        logging.info("Auto DB backup sent to Super Admin.")
    except Exception as e:
        logging.error(f"Auto DB Backup error: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if await check_ban(message.from_user.id): return
    await execute_db(
        "INSERT OR IGNORE INTO users (id, username, first_name) VALUES (?, ?, ?)", 
        (message.from_user.id, message.from_user.username, message.from_user.first_name)
    )
    await execute_db(
        "UPDATE users SET username = ?, first_name = ? WHERE id = ?", 
        (message.from_user.username, message.from_user.first_name, message.from_user.id)
    )
    
    await log_user_action(message.from_user.id, "Открыл главное меню (/start)")

    adm = await is_admin(message.from_user.id)
    sgn = await is_signer(message.from_user.id)
    
    text = (
        "👋 <b>Добро пожаловать в Card Battle Bot!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Собери свою колоду уникальных юнитов, участвуй в ивентах и поднимай кубки на арене!\n\n"
        "📖 <b>ОГРОМНОЕ РУКОВОДСТВО ПО ИГРЕ:</b> /help\n"
        "📞 Тех.поддержка: @ggtdcards_support\n"
        "📰 Новости: @ggtdcardsnews\n"
        "📧 Почта: ggtdcards@gmail.com\n\n"
        "👇 <i>Используй красивое меню снизу для навигации:</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard(adm, sgn))

@dp.message(Command("updatelog"))
async def cmd_updatelog(message: types.Message):
    if await check_ban(message.from_user.id): return
    text = f"📰 <b>ИСТОРИЯ ОБНОВЛЕНИЙ (Стр. 1/{len(UPDATE_LOGS)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n{UPDATE_LOGS[0]}"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if len(UPDATE_LOGS) > 1:
        kb.inline_keyboard.append([InlineKeyboardButton(text="➡️", callback_data="updatelog_1")])
    await message.answer(text, reply_markup=kb if kb.inline_keyboard else None)

@dp.callback_query(F.data.startswith("updatelog_"))
async def cb_updatelog(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[1])
    text = f"📰 <b>ИСТОРИЯ ОБНОВЛЕНИЙ (Стр. {page+1}/{len(UPDATE_LOGS)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n{UPDATE_LOGS[page]}"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"updatelog_{page-1}"))
    if page < len(UPDATE_LOGS) - 1: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"updatelog_{page+1}"))
    if nav: kb.inline_keyboard.append(nav)
    try: await callback.message.edit_text(text, reply_markup=kb if kb.inline_keyboard else None)
    except: pass
    await callback.answer()

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    if await check_ban(message.from_user.id): return
    guide = (
        "📖 <b>ОГРОМНОЕ РУКОВОДСТВО ПО CARD BATTLE BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Добро пожаловать в карточную арену! Ниже описаны все основные механики нашего бота:\n\n"
        "⚔️ <b>ОСНОВНОЙ РЕЖИМ БОЯ (PvE и PvP)</b>\n"
        "• Вы можете собрать боевую колоду из 4-х карт (или 5, если куплен соответствующий геймпас!).\n"
        "• Бой проходит в автоматическом или полуавтоматическом режиме (если включен ручной выбор в Настройках).\n"
        "• В боях против ИИ (ботов) вы получаете <b>Шекели 💰</b>, кубки и опыт БП. Награды зависят от выбранной сложности.\n"
        "• <b>PvP Дуэли</b> позволяют сразиться с друзьями дружеской дуэлью (без изменения рейтинга и наград) или через автоподбор.\n\n"
        "💎 <b>РЕДКОСТИ И МУТАЦИИ КАРТ</b>\n"
        "Каждая карта имеет свою редкость и может выпасть с особой мутацией:\n"
        "⚪ Basic | 🟢 Uncommon | 🔵 Rare | 🟣 Epic | 🟡 Legendary | 🔴 Mythic | 🌈 Super | 🌸 Exclusive | 👑 Leaderboard\n"
        "• ⭐ <b>Золотая мутация</b> (+15% к характеристикам)\n"
        "• 💎 <b>Алмазная мутация</b> (+30% к характеристикам)\n"
        "• 🌈 <b>Радужная мутация</b> (+45% к характеристикам)\n\n"
        "⚡ <b>СИСТЕМА ГАРАНТИЙ (PITY)</b>\n"
        "• При открытии карт из обычной гачи вы застрахованы от неудач:\n"
        "└ Гарантированный <b>Мифик 🔴</b>: каждые 1000 открытий.\n"
        "└ Гарантированный <b>Супер 🌈</b>: каждые 10000 открытий.\n\n"
        "🔨 <b>МАСТЕРСКАЯ КРАФТА И СЛИЯНИЕ</b>\n"
        "• В меню Крафта вы можете создавать новые мощные карты по рецептам, вкладывая обычные копии.\n"
        "• Вы также можете слить 8 одинаковых обычных карт (или 4, если куплен VIP!), чтобы гарантированно повысить их мутацию на уровень выше!\n\n"
        "🎟 <b>БАТЛ-ПАСС (СЕЗОНЫ)</b>\n"
        "• Получайте опыт БП за бои. Повышайте уровень и забирайте эксклюзивные награды, шекели и Сид-Паки!\n\n"
        "🤝 <b>СИСТЕМА ОБМЕНА (ТРЕЙДЫ)</b>\n"
        "• Используйте команду <code>/trade [ID/username]</code>, чтобы начать безопасный обмен картами и Робуксами с другим игроком в реальном времени!\n\n"
        "📞 <b>КОНТАКТЫ И СВЯЗЬ:</b>\n"
        "• 📰 Новости и обновления: @ggtdcardsnews\n"
        "• 💬 Наш чат поддержки: @ggtdcards_support\n"
        "• 📧 Email для предложений: ggtdcards@gmail.com\n"
    )
    await message.answer(guide)

@dp.message(F.text == BTN_MODIFIERS)
async def cmd_modifiers_btn(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id=?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    def s(val): return "✅ Вкл" if val else "❌ Выкл"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 Враги: 1.5x ХП ({s(user.get('mod_enemy_hp'))})", callback_data="set_mod_enemy_hp")],
        [InlineKeyboardButton(text=f"🔴 Враги: ИИ бьет 2 раза ({s(user.get('mod_enemy_atk_all'))})", callback_data="set_mod_enemy_atk_all")],
        [InlineKeyboardButton(text=f"🔴 Враги: 1.2x Статы ИИ ({s(user.get('mod_enemy_stats'))})", callback_data="set_mod_enemy_stats")],
        [InlineKeyboardButton(text=f"🔴 Враги: Начать с Горением ({s(user.get('mod_enemy_burn'))})", callback_data="set_mod_enemy_burn")],
        [InlineKeyboardButton(text=f"🔴 Враги: Отключить лечение ({s(user.get('mod_no_heals'))})", callback_data="set_mod_no_heals")],
        [InlineKeyboardButton(text=f"🟢 Игрок: Бьет 2 раза ({s(user.get('mod_player_atk_all'))})", callback_data="set_mod_player_atk_all")],
        [InlineKeyboardButton(text=f"🟢 Игрок: Ручной выбор атаки ({s(user.get('mod_manual_atk'))})", callback_data="set_mod_manual_atk")],
        [InlineKeyboardButton(text=f"🟢 Игрок: 1.3x ХП ({s(user.get('mod_player_hp'))})", callback_data="set_mod_player_hp")],
        [InlineKeyboardButton(text=f"🟢 Игрок: Стартовый Щит 30% ({s(user.get('mod_player_shield'))})", callback_data="set_mod_player_shield")],
        [InlineKeyboardButton(text=f"🟢 Игрок: Вампиризм 25% ({s(user.get('mod_player_vamp'))})", callback_data="set_mod_player_vamp")]
    ])
    text = (
        "🧬 <b>МОДИФИКАТОРЫ БОЯ (PvE)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВключите модификаторы для усложнения или упрощения боев с ботами.\n\n"
        "🔴 <b>Дебаффы</b> повышают награды (монеты, опыт, кубки).\n🟢 <b>Баффы</b> снижают награды (монеты, опыт), кубки не режутся."
    )
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("set_mod_"))
async def cb_mod_toggle(callback: types.CallbackQuery):
    mod = callback.data.replace("set_mod_", "")
    uid = callback.from_user.id
    user = await fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    new_val = 1 if not user.get(f"mod_{mod}") else 0
    await execute_db(f"UPDATE users SET mod_{mod} = ? WHERE id = ?", (new_val, uid))
    
    # Reload modifiers layout
    user = await fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    def s(val): return "✅ Вкл" if val else "❌ Выкл"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 Враги: 1.5x ХП ({s(user.get('mod_enemy_hp'))})", callback_data="set_mod_enemy_hp")],
        [InlineKeyboardButton(text=f"🔴 Враги: ИИ бьет 2 раза ({s(user.get('mod_enemy_atk_all'))})", callback_data="set_mod_enemy_atk_all")],
        [InlineKeyboardButton(text=f"🔴 Враги: 1.2x Статы ИИ ({s(user.get('mod_enemy_stats'))})", callback_data="set_mod_enemy_stats")],
        [InlineKeyboardButton(text=f"🔴 Враги: Начать с Горением ({s(user.get('mod_enemy_burn'))})", callback_data="set_mod_enemy_burn")],
        [InlineKeyboardButton(text=f"🔴 Враги: Отключить лечение ({s(user.get('mod_no_heals'))})", callback_data="set_mod_no_heals")],
        [InlineKeyboardButton(text=f"🟢 Игрок: Бьет 2 раза ({s(user.get('mod_player_atk_all'))})", callback_data="set_mod_player_atk_all")],
        [InlineKeyboardButton(text=f"🟢 Игрок: Ручной выбор атаки ({s(user.get('mod_manual_atk'))})", callback_data="set_mod_manual_atk")],
        [InlineKeyboardButton(text=f"🟢 Игрок: 1.3x ХП ({s(user.get('mod_player_hp'))})", callback_data="set_mod_player_hp")],
        [InlineKeyboardButton(text=f"🟢 Игрок: Стартовый Щит 30% ({s(user.get('mod_player_shield'))})", callback_data="set_mod_player_shield")],
        [InlineKeyboardButton(text=f"🟢 Игрок: Вампиризм 25% ({s(user.get('mod_player_vamp'))})", callback_data="set_mod_player_vamp")]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except:
        pass
    await callback.answer()

@dp.message(Command("profile"), F.chat.type == "private")
@dp.message(F.text == BTN_PROF)
async def cmd_profile(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    rank = await get_user_rank(user['trophies'])
    total_cards = await fetch_one("SELECT SUM(count) as s FROM inventory WHERE user_id = ? AND is_football = 0", (user['id'],))
    name = get_display_name(user)
    title_str = await get_user_titles_str(user['id'])
    
    active_bp = await fetch_one("""
        SELECT bp.title, ubp.level, ubp.xp 
        FROM user_bp ubp JOIN battle_passes bp ON ubp.bp_id = bp.id 
        WHERE ubp.user_id = ? AND ubp.is_active = 1 AND bp.is_football = 0
    """, (user['id'],))
    
    bp_text = "<i>Нет активного Батл-пасса</i>"
    if active_bp:
        bp_text = f"<b>{active_bp['title']}</b> (Ур. {active_bp['level']} | {active_bp['xp']} XP)"

    text = (
        f"👤 Профиль игрока <b>{name}</b>{title_str}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎖 <b>Ранг:</b> {rank['name']}\n🏆 <b>Кубки:</b> {user['trophies']}\n"
        f"💰 <b>Шекели:</b> {user['coins']}\n💸 <b>Робуксы:</b> {user['robux']} R$\n"
        f"🃏 <b>Всего карт:</b> {total_cards['s'] or 0}\n🎟 <b>Активный БП:</b> {bp_text}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔮 <b>Гарант на Мифик:</b> {make_progress_bar(user['pity_mythic'], 1000, 8)} ({user['pity_mythic']}/1000)\n"
        f"🌠 <b>Гарант на Супер:</b> {make_progress_bar(user['pity_super'], 10000, 8)} ({user['pity_super']}/10000)\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
        
    text += "⚔️ <b>Экипировка:</b>\n"
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user.get("gp_fifth_slot") == 1 or user.get("gp_vip") == 1:
        slots.append('equip5')
        
    for i, slot in enumerate(slots):
        inv_id = user[slot]
        role_label = f"{i+1}️⃣ "
        if inv_id != 0:
            row = await fetch_one("""
                SELECT c.id, c.name, c.rarity, c.class_type, c.damage, c.hp, c.booster_dmg_mult, c.booster_hp_mult,
                       i.mutation, i.serial_number, i.signed_by
                FROM inventory i JOIN cards c ON i.card_id = c.id
                WHERE i.id = ? AND i.user_id = ? AND i.count > 0
            """, (inv_id, user['id']))
            
            if row:
                mult = get_mutation_multiplier(row['mutation'])
                mut_str = ""
                if row['mutation'] == "Rainbow": mut_str = " 🌈"
                elif row['mutation'] == "Diamond": mut_str = " 💎"
                elif row['mutation'] == "Gold": mut_str = " ⭐"
                
                c_dict = dict(row)
                if row['signed_by'] > 0:
                    signer = await fetch_one("SELECT username, first_name FROM users WHERE id = ?", (row['signed_by'],))
                    if signer: c_dict['signer_name'] = get_display_name(signer)
                
                n = format_card_name(c_dict)
                if row['class_type'] == 'Booster': 
                    text += f" {role_label}{n}{mut_str}\n      └ <i>Бафф: DMG x{round(row['booster_dmg_mult']*mult, 2)} | HP x{round(row['booster_hp_mult']*mult, 2)}</i>\n"
                elif row['class_type'] == 'Healer':
                    text += f" {role_label}{n}{mut_str}\n      └ <i>Статы: 💗 Лечение: {int(row['damage']*mult)} | ❤️ Здоровье: {int(row['hp']*mult)}</i>\n"
                else: 
                    text += f" {role_label}{n}{mut_str}\n      └ <i>Статы: ⚔️ Урон: {int(row['damage']*mult)} | ❤️ Здоровье: {int(row['hp']*mult)}</i>\n"
            else:
                await execute_db(f"UPDATE users SET {slot} = 0 WHERE id = ?", (user['id'],))
                text += f" {role_label}[Слот Пуст]\n"
        else:
            text += f" {role_label}[Слот Пуст]\n"
            
    await message.answer(text)

@dp.message(Command("quests"))
@dp.message(F.text == BTN_QUESTS)
async def cmd_quests(message: types.Message):
    if await check_ban(message.from_user.id): return
    user_id = message.from_user.id
    
    await generate_dynamic_quests(user_id)
    user = await fetch_one("SELECT * FROM user_dynamic_quests WHERE user_id = ?", (user_id,))
    
    if not user: return await message.answer("Ошибка системы квестов.")
    
    now = time.time()
    if user['reset_time'] < now:
        await generate_dynamic_quests(user_id)
        user = await fetch_one("SELECT * FROM user_dynamic_quests WHERE user_id = ?", (user_id,))
        
    left = int(user['reset_time'] - now)
    m, s = divmod(left, 60)
    
    text = (
        "📜 <b>ЕЖЕЧАСНЫЕ КВЕСТЫ</b>\n"
        "<i>Выполни все задания за час, чтобы получить ценный Сид-Пак и Шекели!</i>\n"
        f"⏳ <b>До обновления:</b> {m} мин. {s} сек.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    q_data = {t['id']: t['desc'] for t in QUEST_TEMPLATES}
    for i in range(1, 4):
        q_id = user[f'q{i}_id']
        q_target = user[f'q{i}_target']
        q_prog = user[f'q{i}_prog']
        
        desc = q_data.get(q_id, "Задание").format(q_target)
        status = "✅" if q_prog >= q_target else "❌"
        text += f"{i}️⃣ <b>{desc}:</b>\n{make_progress_bar(q_prog, q_target, 8)} {q_prog}/{q_target} {status}\n\n"
        
    await message.answer(text)

@dp.message(Command("top"))
@dp.message(F.text == BTN_TOP)
async def cmd_top(message: types.Message):
    if await check_ban(message.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Кубки (Сезон)", callback_data="top_trophies")],
        [InlineKeyboardButton(text="💰 Монеты (Все время)", callback_data="top_coins")],
        [InlineKeyboardButton(text="🃏 Карты (Все время)", callback_data="top_cards")]
    ])
    await message.answer("🏆 <b>МИРОВЫЕ РЕЙТИНГИ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите категорию лидерборда:", reply_markup=kb)

@dp.callback_query(F.data.startswith("top_"))
async def cb_top_view(callback: types.CallbackQuery):
    lb_type = callback.data.split("_")[1]
    
    if lb_type == 'trophies':
        top_users = await fetch_all("SELECT username, first_name, id, trophies as score FROM users WHERE id != ? ORDER BY trophies DESC LIMIT 20", (SUPER_ADMIN_ID,))
        title_ru = "🏆 <b>МИРОВОЙ РЕЙТИНГ: КУБКИ (Топ-20)</b>"
        unit = "🏆"
    elif lb_type == 'coins':
        top_users = await fetch_all("SELECT username, first_name, id, total_coins as score FROM users WHERE id != ? ORDER BY total_coins DESC LIMIT 20", (SUPER_ADMIN_ID,))
        title_ru = "💰 <b>МИРОВОЙ РЕЙТИНГ: ШЕКЕЛИ (Топ-20)</b>"
        unit = "💰"
    else:
        top_users = await fetch_all("SELECT u.id, u.username, u.first_name, SUM(i.count) as score FROM users u JOIN inventory i ON u.id = i.user_id WHERE u.id != ? AND i.is_football = 0 GROUP BY u.id ORDER BY score DESC LIMIT 20", (SUPER_ADMIN_ID,))
        title_ru = "🃏 <b>МИРОВОЙ РЕЙТИНГ: КАРТЫ (Топ-20)</b>"
        unit = "🃏"

    text = f"{title_ru}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, u in enumerate(top_users, 1):
        name = get_display_name(u)
        title_str = await get_user_titles_str(u['id'])
        
        score_val = u['score'] if u['score'] is not None else 0
        med = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
        
        if lb_type == 'trophies':
            rank = await get_user_rank(score_val)
            text += f"{med} <b>{i}. {name}</b>{title_str} — {score_val} {unit} <i>({rank['name']})</i>\n"
        else:
            text += f"{med} <b>{i}. {name}</b>{title_str} — {score_val} {unit}\n"
        
    text += "\n🎁 <b>Награды (выдаются каждые 2 дня):</b>\n"
    brackets = ["1", "2", "3", "4_9", "10_20"]
    b_names = {"1": "🥇 1 место", "2": "🥈 2 место", "3": "🥉 3 место", "4_9": "🏅 4-9 места", "10_20": "🎖 10-20 места"}
    
    has_rewards = False
    for b in brackets:
        b_rewards = await fetch_all("SELECT * FROM lb_rewards WHERE bracket = ? AND lb_type = ?", (b, lb_type))
        if b_rewards:
            has_rewards = True
            r_strs = []
            for r in b_rewards:
                if r['reward_type'] == 'shekels':
                    r_strs.append(f"{r['amount']} 💰")
                elif r['reward_type'] == 'card':
                    c = await fetch_one("SELECT name FROM cards WHERE id = ?", (r['card_id'],))
                    mut = "🌈" if r['mutation'] == 'Rainbow' else ("💎" if r['mutation'] == 'Diamond' else ("⭐" if r['mutation'] == 'Gold' else ""))
                    r_strs.append(f"{mut} {c['name'] if c else 'Unknown'}")
            text += f"└ {b_names[b]}: {', '.join(r_strs)}\n"
            
    if not has_rewards: text += "<i>Награды пока не настроены.</i>"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К выбору", callback_data="top_menu")]])
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data == "top_menu")
async def cb_top_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Кубки (Сезон)", callback_data="top_trophies")],
        [InlineKeyboardButton(text="💰 Монеты (Все время)", callback_data="top_coins")],
        [InlineKeyboardButton(text="🃏 Карты (Все время)", callback_data="top_cards")]
    ])
    try: await callback.message.edit_text("🏆 <b>МИРОВЫЕ РЕЙТИНГИ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите категорию лидерборда:", reply_markup=kb)
    except: pass
    await callback.answer()

@dp.message(Command("shop"))
@dp.message(F.text == BTN_SHOP)
async def cmd_shop(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT coins, gp_vip FROM users WHERE id = ?", (message.from_user.id,))
    items = await fetch_all("SELECT * FROM shop_items WHERE stock > 0 AND is_football = 0")
    
    if not items:
        return await message.answer("🛒 <b>Магазин пока пуст.</b>\nЗавоз осуществляется каждые полтора часа. Жди уведомления!")
        
    is_vip = user and user.get("gp_vip") == 1
    
    text = f"🛒 <b>ГЛОБАЛЬНЫЙ МАГАЗИН</b>\n💰 Твой баланс: <b>{user['coins']} Шекелей</b>\n<i>(Товары общие для всех. Кто успел, тот и купил!)</i>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if is_vip:
        text += "💎 <b>У вас активен VIP статус! Скидка 10% на все товары.</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
    kb = []
    for i, item in enumerate(items, 1):
        price = item['price']
        if is_vip:
            price = int(price * 0.9)
            
        text += f"📦 <b>{item['name']}</b>\n      └ 💵 Цена: <b>{price} 💰</b> | Остаток: <b>{item['stock']} шт.</b>\n\n"
        kb.append([InlineKeyboardButton(text=f"Купить: {item['name']} ({price} 💰)", callback_data=f"buy_shop_{item['id']}")])
        
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("buy_shop_"))
async def callback_buy_shop(callback: types.CallbackQuery):
    shop_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    user = await fetch_one("SELECT coins, gp_vip, pity_mythic, pity_super FROM users WHERE id = ?", (user_id,))
    item = await fetch_one("SELECT * FROM shop_items WHERE id = ?", (shop_id,))
    
    if not item or item['stock'] <= 0: return await callback.answer("❌ Этот товар закончился!", show_alert=True)
    
    is_vip = user and user.get("gp_vip") == 1
    price = item['price']
    if is_vip:
        price = int(price * 0.9)
        
    if user['coins'] < price: return await callback.answer("❌ Недостаточно средств!", show_alert=True)
    
    await execute_db("UPDATE users SET coins = coins - ? WHERE id = ?", (price, user_id))
    await execute_db("UPDATE shop_items SET stock = stock - 1 WHERE id = ?", (shop_id,))
    
    await add_quest_progress_new(user_id, 'q_shop_buy', 1)
    
    i_type = item['item_type']
    if i_type.endswith("_rnd"):
        count = int(i_type.split("_")[0])
        won = await give_multiple_cards(user_id, count, is_football=0)
        
        await add_quest_progress_new(user_id, 'q_open', count)
            
        pity_pulls = [c for c in won if c.get('is_pity')]
        
        if count == 1: 
            mut_str = ""
            if won[0]['mutation'] == 'Rainbow': mut_str = "🌈 "
            elif won[0]['mutation'] == 'Diamond': mut_str = "💎 "
            elif won[0]['mutation'] == 'Gold': mut_str = "⭐ "
            
            msg = f"✨ <b>Грандиозная покупка!</b>\nВы выбили: {mut_str}{format_card_name(won[0])}"
            if won[0].get('is_pity'):
                msg = f"🌟 <b>СИСТЕМА PITY! Гарантированный {won[0]['pity_type']}!</b> 🌟\n\n" + msg
        else: 
            msg = f"🛍 <b>Успешно! Вы открыли пак из {count} карт!</b>\nПосмотрите новинки в 🎒 Инвентаре."
            if pity_pulls:
                p_names = ", ".join([f"{c['name']} (Pity {c['pity_type']})" for c in pity_pulls])
                msg += f"\n\n🌟 <b>Сработал PITY! Гарантированные редчайшие карты:</b>\n{p_names}!"
                
        await callback.message.answer(msg)
        
    elif i_type.startswith("rnd_"):
        rarity_map = {"rnd_leg": "Legendary", "rnd_myth": "Mythic", "rnd_sup": "Super"}
        target_rarity = rarity_map[i_type]
        
        query = "SELECT * FROM cards WHERE rarity = ? AND id NOT IN (SELECT card_id FROM seed_pack_cards) AND is_cardball_exclusive = 0"
        all_cards = await fetch_all(query, (target_rarity,))
        
        if not all_cards:
            await execute_db("UPDATE users SET coins = coins + ? WHERE id = ?", (price, user_id))
            return await callback.message.answer("❌ Ошибка БД.")
            
        won_card = random.choice(all_cards)
        mut = roll_mutation()
        _, serial, _ = await give_card_to_user(user_id, won_card['id'], mut, won_card['rarity'], is_football=0)
        won_card['serial_number'] = serial
        won_card['signed_by'] = 0
        
        await add_quest_progress_new(user_id, 'q_open', 1)
            
        pm = user['pity_mythic']; ps = user['pity_super']
        if target_rarity == 'Super': ps = 0; pm += 1
        elif target_rarity == 'Mythic': pm = 0; ps += 1
        else: ps += 1; pm += 1
        await execute_db("UPDATE users SET pity_mythic=?, pity_super=? WHERE id=?", (pm, ps, user_id))
        
        mut_str = "🌈 Радужная" if mut == 'Rainbow' else ("💎 Алмазная" if mut == 'Diamond' else ("⭐ Золотая" if mut == 'Gold' else "Обычная"))
        await callback.message.answer(f"✨ <b>Успешная покупка ГАРАНТА!</b>\nВы выбили: {format_card_name(won_card)}\nМутация: <b>{mut_str}</b>")

    await log_user_action(user_id, f"Купил в магазине: {i_type} ({price})")

    items = await fetch_all("SELECT * FROM shop_items WHERE stock > 0 AND is_football = 0")
    if not items:
        await callback.message.edit_text("🛒 <b>Магазин полностью распродан!</b>\nЖдите следующего завода.")
    else:
        new_val = user['coins'] - price
        text = f"🛒 <b>ГЛОБАЛЬНЫЙ МАГАЗИН</b>\n💰 Твой баланс: <b>{new_val} Шекелей</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if is_vip:
            text += "💎 <b>У вас активен VIP статус! Скидка 10% на все товары.</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
        kb = []
        for i, itm in enumerate(items, 1):
            cur_price = itm['price']
            if is_vip:
                cur_price = int(cur_price * 0.9)
            text += f"📦 <b>{itm['name']}</b>\n      └ 💵 Цена: <b>{cur_price} 💰</b> | Остаток: <b>{itm['stock']} шт.</b>\n\n"
            kb.append([InlineKeyboardButton(text=f"Купить: {itm['name']} ({cur_price} 💰)", callback_data=f"buy_shop_{itm['id']}")])
        try: await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except: pass
    
    await callback.answer()

@dp.message(Command("getcard"))
@dp.message(F.text == BTN_DRAW)
async def cmd_getcard(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    if user['id'] in user_trades: return await message.answer("❌ Завершите обмен перед выбиванием!")
    
    luck_mult, cd_mult = await get_active_events(user['id'])
    
    base_cooldown = 3 * 60
    last_col = 'last_getcard'
        
    actual_cooldown = int(base_cooldown / cd_mult)
    now = time.time()
    passed = now - user[last_col]
    
    if passed < actual_cooldown:
        left = int(actual_cooldown - passed)
        mins, secs = divmod(left, 60)
        return await message.answer(f"⏳ <b>Колода перемешивается!</b>\nОжидай: <b>{mins} мин. {secs} сек.</b>")
        
    won_list = await give_multiple_cards(user['id'], 1, is_football=0)
    if not won_list: return await message.answer("😔 В базе нет карт для этой гачи.")
    won_card = won_list[0]
        
    await execute_db(f"UPDATE users SET {last_col} = ? WHERE id = ?", (now, user['id']))
    await add_quest_progress_new(user['id'], 'q_open', 1)
    await log_user_action(user['id'], f"Выбил карту: {won_card['name']} (ID:{won_card['id']}, Мутация: {won_card['mutation']})")
    
    n_fmt = format_card_name(won_card)
    rarity_text = format_rarity_display(won_card['rarity'])
    
    mutation = won_card['mutation']
    mult = get_mutation_multiplier(mutation)
    mut_str = ""
    if mutation == "Gold": mut_str = "⭐ <b>ЗОЛОТАЯ МУТАЦИЯ! (+15% Статов)</b>\n"
    elif mutation == "Diamond": mut_str = "💎 <b>АЛМАЗНАЯ МУТАЦИЯ! (+30% Статов)</b>\n"
    elif mutation == "Rainbow": mut_str = "🌈 <b>РАДУЖНАЯ МУТАЦИЯ! (+45% Статов)</b>\n"
    
    msg = ""
    if won_card['is_pity']:
        msg += f"🌟 <b>СИСТЕМА PITY! ГАРАНТИРОВАННЫЙ {won_card['pity_type']}!</b> 🌟\n\n"
        
    msg += f"🎉 <b>ВЫ ВЫБИЛИ КАРТУ!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n{mut_str}🃏 {n_fmt}\n💎 <b>Редкость:</b> {rarity_text}\n"
    
    if won_card['class_type'] == 'Booster': 
        msg += f"✨ <b>БУСТЕР</b>\n   └ Бафф DMG: <b>x{round(won_card['booster_dmg_mult']*mult, 2)}</b> | HP: <b>x{round(won_card['booster_hp_mult']*mult, 2)}</b>\n"
    elif won_card['class_type'] == 'Healer':
        msg += f"💗 <b>Лечение:</b> {int(won_card['damage']*mult)} | ❤️ <b>Здоровье:</b> {int(won_card['hp']*mult)}\n"
    else: 
        msg += f"⚔️ <b>Урон:</b> {int(won_card['damage']*mult)} | ❤️ <b>Здоровье:</b> {int(won_card['hp']*mult)}\n"
        
    if luck_mult > 1.0 and won_card['drop_chance'] < 15.0:
        msg += f"\n🍀 <i>Сработал ивент удачи!</i>"
        
    await message.answer_photo(photo=won_card['photo_id'], caption=msg)

async def get_index_text(user_id: int, page: int = 0, items_per_page: int = 8):
    query = "SELECT * FROM cards WHERE rarity != 'Secret' AND is_cardball_exclusive = 0"
    all_cards = await fetch_all(query)
    user_inv = await fetch_all("SELECT DISTINCT card_id FROM inventory WHERE user_id = ?", (user_id,))
    user_card_ids = [item['card_id'] for item in user_inv]
    recipes = await fetch_all("SELECT target_card_id FROM craft_recipes")
    crafted_ids = [r['target_card_id'] for r in recipes]
    
    if not all_cards: return "Индекс пуст.", None
    
    luck_mult, _ = await get_active_events(user_id)
    weights_dict, total_w = await calculate_chance_weights(luck_mult, exclude_cardball=True)
    
    pack_cards = await fetch_all("""
        SELECT spc.card_id, spc.drop_chance as pack_chance, sp.title
        FROM seed_pack_cards spc JOIN seed_packs sp ON spc.pack_id = sp.id
    """)
    pack_info = {pc['card_id']: pc for pc in pack_cards}
    pack_totals = {}
    for pc in pack_cards:
        w = pc['pack_chance']
        if w < 15.0: w *= luck_mult
        pack_totals[pc['title']] = pack_totals.get(pc['title'], 0) + w
    
    def index_sort_key(c):
        if c['rarity'] == 'Leaderboard': return (999, c['id'])
        rw = RARITY_WEIGHT.get(c['rarity'], 0)
        return (rw, c['id'])
        
    all_cards.sort(key=index_sort_key, reverse=True)
    total_pages = max(1, math.ceil(len(all_cards) / items_per_page))
    page = max(0, min(page, total_pages - 1))
    
    text = f"📖 <b>ОСНОВНОЙ ИНДЕКС КАРТ (Стр. {page+1}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if luck_mult > 1.0: text += f"🍀 <b>ИВЕНТ УДАЧИ АКТИВЕН (x{luck_mult})! Шансы пересчитаны!</b>\n\n"
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = all_cards[start_idx:end_idx]
    
    for i, c in enumerate(page_items, start_idx + 1):
        inv_stats = await fetch_all("SELECT mutation, SUM(count) as c FROM inventory WHERE card_id = ? AND user_id != ? GROUP BY mutation", (c['id'], SUPER_ADMIN_ID))
        total_exists = sum(item['c'] for item in inv_stats if item['c'])
        
        mut_texts = []
        for st in inv_stats:
            if st['mutation'] == 'Gold' and st['c'] > 0: mut_texts.append(f"⭐ Золотых: {st['c']}")
            if st['mutation'] == 'Diamond' and st['c'] > 0: mut_texts.append(f"💎 Алмазных: {st['c']}")
            if st['mutation'] == 'Rainbow' and st['c'] > 0: mut_texts.append(f"🌈 Радужных: {st['c']}")
            
        mut_str = f"\n      └ <i>Из них: {', '.join(mut_texts)}</i>" if mut_texts else ""
        
        n_fmt = format_card_name(c).replace(" <b>[#-001]</b>", "")
        if c['id'] in crafted_ids: n_fmt += " [🛠 Крафт]"
        r_fmt = format_rarity_display(c['rarity'])
        
        if c['id'] in pack_info:
            p_info = pack_info[c['id']]
            p_title = p_info['title']
            p_weight = p_info['pack_chance']
            if p_weight < 15.0: p_weight *= luck_mult
            p_total = pack_totals.get(p_title, 1)
            real_chance = (p_weight / p_total) * 100 if p_total > 0 else 0
            chance_str = f"Шанс: {real_chance:.4f}% <b>(Пак «{p_title}»)</b>"
        elif c['rarity'] == 'Leaderboard':
            chance_str = "Только за Топ!"
        else:
            real_chance = (weights_dict.get(c['id'], 0) / total_w) * 100 if total_w > 0 else 0
            chance_str = f"Шанс из Гачи: {real_chance:.4f}%"
        
        if c['id'] in user_card_ids:
            text += f"{i}. {n_fmt}\n      └ 💎 {r_fmt} ({chance_str})\n"
            if c['class_type'] == 'Booster': 
                text += f"      └ ✨ Бафф: DMG x{c['booster_dmg_mult']} // HP x{c['booster_hp_mult']}\n"
            elif c['class_type'] == 'Healer': 
                text += f"      └ 💗 Лечение: {c['damage']} // ❤️ Здоровье: {c['hp']}\n"
            else: 
                text += f"      └ ⚔️ Урон: {c['damage']} // ❤️ Здоровье: {c['hp']}\n"
            text += f"      └ 🌍 Существует: {total_exists} шт.{mut_str}\n\n"
        else:
            text += f"{i}. <b>???</b> (Не открыто)\n      └ 💎 {r_fmt} ({chance_str})\n      └ 🌍 Существует: {total_exists} шт.{mut_str}\n\n"
            
    kb = []
    nav_row = []
    cb_prefix = "idx_"
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{cb_prefix}page_{page-1}"))
    if total_pages > 1: nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{cb_prefix}page_{page+1}"))
    if nav_row: kb.append(nav_row)
    
    return text, InlineKeyboardMarkup(inline_keyboard=kb) if kb else None

@dp.message(Command("index"))
@dp.message(F.text == BTN_IDX)
async def cmd_index(message: types.Message):
    if await check_ban(message.from_user.id): return
    text, kb = await get_index_text(message.from_user.id, 0)
    await message.answer(text, reply_markup=kb)
    
@dp.callback_query(F.data.startswith("idx_page_"))
async def callback_index_page(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    text, kb = await get_index_text(callback.from_user.id, page)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

async def get_inventory_text_and_kb(user_id: int, page: int = 0, items_per_page: int = 30):
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by, u.username, u.first_name
        FROM inventory i JOIN cards c ON i.card_id = c.id LEFT JOIN users u ON i.signed_by = u.id
        WHERE i.user_id = ? AND i.count > 0 AND i.is_football = 0
    """, (user_id,))
    
    toggle_row = [
        InlineKeyboardButton(text=f"🎒 Карты (Выбрано)", callback_data="ignore"),
        InlineKeyboardButton(text=f"📦 Сид-Паки", callback_data="inv_packs_menu")
    ]
    
    if not inv: 
        return f"🎒 Ваш инвентарь пуст. Используйте /getcard", InlineKeyboardMarkup(inline_keyboard=[toggle_row])
        
    mutation_weight = {"Rainbow": 4, "Diamond": 3, "Gold": 2, "Normal": 1}
    for item in inv:
        if item['signed_by'] != 0:
            item['signer_name'] = get_display_name({'username': item['username'], 'first_name': item['first_name']})
    inv.sort(key=lambda x: (x['signed_by'] > 0, RARITY_WEIGHT.get(x['rarity'], 0), mutation_weight.get(x['mutation'], 0), x['card_id']), reverse=True)
    
    total_pages = max(1, math.ceil(len(inv) / items_per_page))
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = inv[start_idx:end_idx]
    
    text = f"🎒 <b>ИНВЕНТАРЬ КАРТ (Стр. {page+1}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for item in page_items:
        n_fmt = format_card_name(item).replace(" <b>[#-001]</b>", "")
        mut_emoji = ""
        if item['mutation'] == "Gold": mut_emoji = "⭐ "
        elif item['mutation'] == "Diamond": mut_emoji = "💎 "
        elif item['mutation'] == "Rainbow": mut_emoji = "🌈 "
        text += f"• {mut_emoji}{n_fmt} — <b>{item['count']} шт.</b>\n"
        
    kb = [toggle_row]
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"inv_page_{page-1}"))
    if total_pages > 1: nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"inv_page_{page+1}"))
    if nav_row: kb.append(nav_row)
    
    return text, InlineKeyboardMarkup(inline_keyboard=kb) if kb else None

@dp.message(Command("inventory"))
@dp.message(F.text == BTN_INV)
async def cmd_inventory(message: types.Message):
    if await check_ban(message.from_user.id): return
    text, kb = await get_inventory_text_and_kb(message.from_user.id, 0)
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("inv_page_"))
async def callback_inventory_page(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    page = int(parts[2])
    text, kb = await get_inventory_text_and_kb(callback.from_user.id, page)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.message(F.text == BTN_SIGN)
async def cmd_sign_card(message: types.Message):
    if await check_ban(message.from_user.id): return
    if not await is_signer(message.from_user.id): return
    if message.from_user.id in user_trades: return await message.answer("❌ Завершите обмен перед подписыванием карт!")
    
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0 AND i.signed_by = 0 AND i.is_football = 0
    """, (message.from_user.id,))
    
    if not inv: return await message.answer("❌ Нет карт для подписи.")
    
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = []
    for c in inv:
        mut_emoji = ""
        if c['mutation'] == 'Gold': mut_emoji = "⭐ "
        elif c['mutation'] == 'Diamond': mut_emoji = "💎 "
        elif c['mutation'] == 'Rainbow': mut_emoji = "🌈 "
        items.append({"id": c['inv_id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {mut_emoji}{c['name']} x{c['count']}"})
        
    kb = get_pagination_keyboard(items, 0, "sgn_c", columns=1, items_per_page=8)
    await message.answer("✍️ <b>ВЫБОР КАРТЫ ДЛЯ ПОДПИСИ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите карту:", reply_markup=kb)

@dp.callback_query(F.data.startswith("sgn_c_page_"))
async def cb_sign_card_paginate(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[3])
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0 AND i.signed_by = 0 AND i.is_football = 0
    """, (callback.from_user.id,))
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = []
    for c in inv:
        mut_emoji = ""
        if c['mutation'] == 'Gold': mut_emoji = "⭐ "
        elif c['mutation'] == 'Diamond': mut_emoji = "💎 "
        elif c['mutation'] == 'Rainbow': mut_emoji = "🌈 "
        items.append({"id": c['inv_id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {mut_emoji}{c['name']} x{c['count']}"})
        
    kb = get_pagination_keyboard(items, page, "sgn_c", columns=1, items_per_page=8)
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("sgn_c_"))
async def cb_sign_card_select(callback: types.CallbackQuery):
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if not await is_signer(user_id): return await callback.answer("Нет прав!", show_alert=True)
    
    db = await get_db_connection()
    try:
        cur = await db.execute("SELECT card_id, count, mutation, serial_number, signed_by FROM inventory WHERE id = ? AND user_id = ?", (inv_id, user_id))
        row = await cur.fetchone()
        if not row or row['count'] < 1: return await callback.answer("Not found!", show_alert=True)
        if row['signed_by'] != 0: return await callback.answer("Already signed!", show_alert=True)
        
        await db.execute("BEGIN")
        if row['count'] == 1:
            await db.execute("DELETE FROM inventory WHERE id = ?", (inv_id,))
            await db.execute("UPDATE users SET equip1 = 0 WHERE equip1 = ?", (inv_id,))
            await db.execute("UPDATE users SET equip2 = 0 WHERE equip2 = ?", (inv_id,))
            await db.execute("UPDATE users SET equip3 = 0 WHERE equip3 = ?", (inv_id,))
            await db.execute("UPDATE users SET equip4 = 0 WHERE equip4 = ?", (inv_id,))
            await db.execute("UPDATE users SET equip5 = 0 WHERE equip5 = ?", (inv_id,))
        else:
            await db.execute("UPDATE inventory SET count = count - 1 WHERE id = ?", (inv_id,))
            
        cur2 = await db.execute("""
            SELECT id FROM inventory 
            WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = ? AND signed_by = ? AND is_football = 0
        """, (user_id, row['card_id'], row['mutation'], row['serial_number'], user_id))
        dest = await cur2.fetchone()
        
        if dest:
            await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (dest['id'],))
        else:
            await db.execute("""
                INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football)
                VALUES (?, ?, 1, ?, ?, ?, 0)
            """, (user_id, row['card_id'], row['mutation'], row['serial_number'], user_id))
            
        await db.commit()
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Sign error: {e}")
        return await callback.answer("Ошибка.", show_alert=True)
    finally:
        await db.close()
        
    await callback.message.delete()
    await callback.message.answer("✍️✅ <b>Успешно подписано!</b>")
    await callback.answer()

def get_equip_main_keyboard(user_info, cards_info):
    kb = []
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user_info.get("gp_fifth_slot") == 1 or user_info.get("gp_vip") == 1:
        slots.append('equip5')
        
    for i, slot in enumerate(slots, 1):
        inv_id = user_info[slot]
        text = f"Слот {i}: [Пусто]" if inv_id == 0 else f"Слот {i}: {cards_info.get(inv_id, f'ID: {inv_id}')}"
        kb.append([InlineKeyboardButton(text=text, callback_data=f"eq_select_{i}")])
    kb.append([InlineKeyboardButton(text="❌ Очистить колоду", callback_data="eq_clear")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("equip"))
@dp.message(F.text == BTN_EQ)
async def cmd_equip(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    if message.from_user.id in user_trades: return await message.answer("❌ Завершите обмен перед экипировкой!")
    
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user.get("gp_fifth_slot") == 1 or user.get("gp_vip") == 1:
        slots.append('equip5')
        
    inv_ids = [c for c in [user[s] for s in slots] if c != 0]
    
    cards_info = {}
    if inv_ids:
        inv_list = ",".join(map(str, inv_ids))
        res = await fetch_all(f"""
            SELECT i.id, c.name, i.mutation, i.serial_number 
            FROM inventory i JOIN cards c ON i.card_id = c.id 
            WHERE i.id IN ({inv_list}) AND i.count > 0
        """)
        for r in res:
            mut_str = ""
            if r['mutation'] == 'Gold': mut_str = "⭐"
            elif r['mutation'] == 'Diamond': mut_str = "💎"
            elif r['mutation'] == 'Rainbow': mut_str = "🌈"
            ser_str = f" [#{r['serial_number']:04d}]" if r['serial_number'] > 0 else ""
            cards_info[r['id']] = f"{mut_str}{r['name']}{ser_str}".strip()
            
    await message.answer("🛡 <b>БОЕВАЯ КОЛОДА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите слот:", reply_markup=get_equip_main_keyboard(user, cards_info))

@dp.callback_query(F.data == "eq_clear")
async def cb_eq_clear(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await execute_db("UPDATE users SET equip1 = 0, equip2 = 0, equip3 = 0, equip4 = 0, equip5 = 0 WHERE id = ?", (user_id,))
    await callback.message.edit_text("✅ Боевая колода успешно очищена!")
    await callback.answer()

@dp.callback_query(F.data.startswith("eq_select_"))
async def equip_slot_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    slot_num = int(parts[2])
    
    inv = await fetch_all("""
        SELECT DISTINCT c.id, c.name, c.rarity, c.class_type
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0 AND i.is_football = 0
    """, (callback.from_user.id,))
    
    if not inv: return await callback.answer("Нет карт!", show_alert=True)
    
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {c['name']}"} for c in inv]
    
    await state.update_data(equip_slot=slot_num, equip_items_cards=items)
    kb = get_pagination_keyboard(items, 0, "eq_c", columns=1, items_per_page=8)
    
    lbl = f"Слота {slot_num}"
    await callback.message.edit_text(f"👇 Выберите карту для <b>{lbl}</b>:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("eq_c_page_"))
async def equip_card_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('equip_items_cards', []), page, "eq_c", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("eq_c_"))
async def equip_card_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return 
    card_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    slot_num = data.get('equip_slot', 1)
    
    invs = await fetch_all("""
        SELECT i.id as inv_id, c.name, c.rarity, c.class_type, i.mutation, i.serial_number, i.signed_by, u.username, u.first_name, i.count
        FROM inventory i 
        JOIN cards c ON i.card_id = c.id 
        LEFT JOIN users u ON i.signed_by = u.id
        WHERE i.user_id = ? AND i.card_id = ? AND i.count > 0 AND i.is_football = 0
    """, (callback.from_user.id, card_id))
    
    if not invs: return await callback.answer("Карта пропала!", show_alert=True)
    
    items = []
    for i in invs:
        c_dict = dict(i)
        if i['signed_by'] > 0:
            c_dict['signer_name'] = get_display_name({'username': i['username'], 'first_name': i['first_name']})
        
        name_str = format_card_name_plain(c_dict)
        mut = ""
        if i['mutation'] == 'Gold': mut = "⭐ "
        elif i['mutation'] == 'Diamond': mut = "💎 "
        elif i['mutation'] == 'Rainbow': mut = "🌈 "
        items.append({"id": i['inv_id'], "btn_text": f"{mut}{name_str} (x{i['count']})"})
        
    await state.update_data(equip_items_vars=items)
    kb = get_pagination_keyboard(items, 0, "eq_v", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"eq_select_{slot_num}")])
    
    lbl = f"Слота {slot_num}"
    await callback.message.edit_text(f"👇 Выберите конкретную копию для <b>{lbl}</b>:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("eq_v_page_"))
async def equip_var_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('equip_items_vars', []), page, "eq_v", columns=1, items_per_page=6)
    slot_num = data.get('equip_slot', 1)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"eq_select_{slot_num}")])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("eq_v_"))
async def equip_var_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    slot_num = data.get('equip_slot', 1)
    
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (callback.from_user.id,))
    
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user.get("gp_fifth_slot") == 1 or user.get("gp_vip") == 1:
        slots.append('equip5')
        
    current_eq = [user[s] for s in slots]
    
    if inv_id in current_eq:
        return await callback.answer("❌ Эта копия уже экипирована!", show_alert=True)
        
    card_info = await fetch_one("SELECT card_id FROM inventory WHERE id = ?", (inv_id,))
    if not card_info: return await callback.answer("Error")
    
    if user[slots[slot_num-1]] in current_eq:
        current_eq.remove(user[slots[slot_num-1]])
    
    if any(i != 0 for i in current_eq):
        inv_list = ",".join(map(str, [i for i in current_eq if i != 0]))
        other_cards = await fetch_all(f"SELECT card_id FROM inventory WHERE id IN ({inv_list})")
        if any(c['card_id'] == card_info['card_id'] for c in other_cards):
            return await callback.answer("❌ Нельзя надеть две одинаковые карты!", show_alert=True)

    await execute_db(f"UPDATE users SET {slots[slot_num-1]} = ? WHERE id = ?", (inv_id, callback.from_user.id))
    lbl = f"Слот {slot_num}"
    await callback.message.edit_text(f"✅ Установлено в позицию: {lbl}!")
    await state.clear()
    await callback.answer()

@dp.message(F.text == BTN_BP)
async def cmd_battle_passes(message: types.Message):
    if await check_ban(message.from_user.id): return
    passes = await fetch_all("SELECT * FROM battle_passes WHERE is_football = 0 ORDER BY id DESC")
    
    if not passes:
        return await message.answer("🎟 <b>Батл-пассы</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nНет доступных сезонов.")
        
    kb = []
    for bp in passes:
        kb.append([InlineKeyboardButton(text=f"🎫 {bp['title']}", callback_data=f"bp_view_{bp['id']}")])
        
    await message.answer("🎟 <b>БАТЛ-ПАССЫ</b>\nВыберите сезон:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("bp_view_"))
async def callback_bp_view(callback: types.CallbackQuery):
    bp_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    bp = await fetch_one("SELECT * FROM battle_passes WHERE id = ?", (bp_id,))
    if not bp: return await callback.answer("Not found!", show_alert=True)
    
    user_bp = await fetch_one("SELECT * FROM user_bp WHERE user_id = ? AND bp_id = ?", (user_id, bp_id))
    if not user_bp:
        await execute_db("INSERT INTO user_bp (user_id, bp_id, xp, level, is_active) VALUES (?, ?, 0, 0, 0)", (user_id, bp_id))
        user_bp = await fetch_one("SELECT * FROM user_bp WHERE user_id = ? AND bp_id = ?", (user_id, bp_id))
        
    is_active = bool(user_bp['is_active'])
    status_str = "🟢 <b>АКТИВЕН</b>" if is_active else "🔴 <b>НЕАКТИВЕН</b>"
    
    curr_lvl = user_bp['level']
    curr_xp = user_bp['xp']
    
    next_lvl_data = await fetch_one("SELECT xp_required FROM bp_levels WHERE bp_id = ? AND level = ?", (bp_id, curr_lvl + 1))
    req_xp = next_lvl_data['xp_required'] if next_lvl_data else 0
    
    if next_lvl_data: progress_str = f"{make_progress_bar(curr_xp, req_xp, 12)} ({curr_xp}/{req_xp})"
    else: progress_str = "🏆 <b>ПОЛНОСТЬЮ ПРОЙДЕН!</b>"

    text = (
        f"🏆 <b>СЕЗОН: {bp['title']}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 Статус: {status_str}\n🎖 Уровень: <b>{curr_lvl}</b>\n✨ Опыт: {progress_str}\n"
    )
    
    kb = []
    if not is_active:
        kb.append([InlineKeyboardButton(text="✅ Сделать активным", callback_data=f"bp_set_act_{bp_id}")])
    kb.append([InlineKeyboardButton(text="▶️ Уровни и награды", callback_data=f"bp_lvl_{bp_id}_1")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"bp_list_0")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    
    if bp['photo_id']:
        try:
            await callback.message.answer_photo(photo=bp['photo_id'], caption=text, reply_markup=markup)
            await callback.message.delete()
        except:
            await callback.message.edit_text(text, reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()

@dp.callback_query(F.data.startswith("bp_list_"))
async def callback_bp_list(callback: types.CallbackQuery):
    passes = await fetch_all("SELECT * FROM battle_passes WHERE is_football = 0 ORDER BY id DESC")
    kb = []
    for bp in passes:
        kb.append([InlineKeyboardButton(text=f"🎫 {bp['title']}", callback_data=f"bp_view_{bp['id']}")])
    try: await callback.message.edit_text("🎟 <b>БАТЛ-ПАССЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer("🎟 <b>БАТЛ-ПАССЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.startswith("bp_set_act_"))
async def callback_bp_set_active(callback: types.CallbackQuery):
    bp_id = int(callback.data.split("_")[3])
    user_id = callback.from_user.id
    
    await execute_db("""
        UPDATE user_bp SET is_active = 0 
        WHERE user_id = ? AND bp_id IN (SELECT id FROM battle_passes WHERE is_football = 0)
    """, (user_id,))
    
    await execute_db("UPDATE user_bp SET is_active = 1 WHERE user_id = ? AND bp_id = ?", (user_id, bp_id))
    await callback.answer()
    await callback_bp_view(callback)

@dp.callback_query(F.data.startswith("bp_lvl_"))
async def callback_bp_level(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    bp_id = int(parts[2])
    req_level = int(parts[3])
    user_id = callback.from_user.id
    
    bp = await fetch_one("SELECT * FROM battle_passes WHERE id = ?", (bp_id,))
    user_bp = await fetch_one("SELECT level FROM user_bp WHERE user_id = ? AND bp_id = ?", (user_id, bp_id))
    user_curr_lvl = user_bp['level'] if user_bp else 0
    
    lvl_data = await fetch_one("SELECT id, xp_required FROM bp_levels WHERE bp_id = ? AND level = ?", (bp_id, req_level))
    if not lvl_data: return await callback.answer("Level not found", show_alert=True)
        
    rewards = await fetch_all("SELECT * FROM bp_rewards WHERE level_id = ?", (lvl_data['id'],))
    val_name = "Шекелей"
    val_sym = "💰"
    
    text = (
        f"🏆 <b>{bp['title']} | Уровень {req_level}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Требуется XP: {lvl_data['xp_required']}</i>\n\n🎁 <b>Награды:</b>\n"
    )
    
    if not rewards:
        text += "└ <i>Наград нет.</i>\n"
    else:
        for r in rewards:
            if r['reward_type'] == 'shekels':
                text += f"└ {val_sym} <b>{r['amount']} {val_name}</b>\n"
            elif r['reward_type'] == 'card':
                c = await fetch_one("SELECT name FROM cards WHERE id = ?", (r['card_id'],))
                n = c['name'] if c else "Unknown"
                mut = "🌈" if r['mutation'] == 'Rainbow' else ("💎" if r['mutation'] == 'Diamond' else ("⭐" if r['mutation'] == 'Gold' else ""))
                text += f"└ 🃏 <b>{mut} {n}</b>\n"
                
    text += "\n📊 <b>Статус:</b> "
    is_reached = user_curr_lvl >= req_level
    claim_check = await fetch_one("SELECT * FROM user_bp_claims WHERE user_id = ? AND bp_id = ? AND level = ?", (user_id, bp_id, req_level))
    is_claimed = bool(claim_check)
    
    if is_claimed: text += "✅ <i>Уже получено</i>"
    elif is_reached: text += "🎁 <b>ДОСТУПНО!</b>"
    else: text += "🔒 <i>Не достигнут</i>"
    
    kb = []
    if is_reached and not is_claimed and rewards:
        kb.append([InlineKeyboardButton(text="🎁 ЗАБРАТЬ", callback_data=f"bp_claim_{bp_id}_{req_level}")])
        
    nav_row = []
    max_lvl = await fetch_one("SELECT MAX(level) as m FROM bp_levels WHERE bp_id = ?", (bp_id,))
    max_l = max_lvl['m'] if max_lvl and max_lvl['m'] else 1
    
    if req_level > 1: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"bp_lvl_{bp_id}_{req_level-1}"))
    if req_level < max_l: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"bp_lvl_{bp_id}_{req_level+1}"))
    if nav_row: kb.append(nav_row)
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"bp_view_{bp_id}")])
    
    try: await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.startswith("bp_claim_"))
async def callback_bp_claim_fixed(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    bp_id = int(parts[2])
    req_level = int(parts[3])
    user_id = callback.from_user.id
    
    user_bp = await fetch_one("SELECT level FROM user_bp WHERE user_id = ? AND bp_id = ?", (user_id, bp_id))
    if not user_bp or user_bp['level'] < req_level: return await callback.answer("Locked", show_alert=True)
        
    claim_check = await fetch_one("SELECT * FROM user_bp_claims WHERE user_id = ? AND bp_id = ? AND level = ?", (user_id, bp_id, req_level))
    if claim_check: return await callback.answer("Already claimed", show_alert=True)
        
    lvl_data = await fetch_one("SELECT id FROM bp_levels WHERE bp_id = ? AND level = ?", (bp_id, req_level))
    rewards = await fetch_all("SELECT * FROM bp_rewards WHERE level_id = ?", (lvl_data['id'],))
    
    db = await get_db_connection()
    try:
        await db.execute("BEGIN")
        for r in rewards:
            if r['reward_type'] == 'shekels':
                await db.execute("UPDATE users SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (r['amount'], r['amount'], user_id))
            elif r['reward_type'] == 'card':
                res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0 AND is_football = 0", (user_id, r['card_id'], r['mutation']))
                inv_item = await res.fetchone()
                if inv_item:
                    await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                else:
                    await db.execute("INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, 0, 0, 0)", (user_id, r['card_id'], r['mutation']))
        
        await db.execute("INSERT INTO user_bp_claims (user_id, bp_id, level) VALUES (?, ?, ?)", (user_id, bp_id, req_level))
        await db.commit()
    finally:
        await db.close()
        
    await callback.answer("🎉 Reward claimed!", show_alert=True)
    await callback_bp_level(callback)

async def get_team_data(user_id: int, is_football: int = 0):
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    team = []
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user and (user.get("gp_fifth_slot") == 1 or user.get("gp_vip") == 1):
        slots.append('equip5')
        
    for slot in slots:
        inv_id = user[slot]
        if inv_id != 0:
            row = await fetch_one("""
                SELECT c.id, c.name, c.rarity, c.class_type, c.damage, c.hp, c.booster_dmg_mult, c.booster_hp_mult,
                       i.mutation, i.serial_number, i.signed_by
                FROM inventory i JOIN cards c ON i.card_id = c.id
                WHERE i.id = ? AND i.user_id = ? AND i.count > 0
            """, (inv_id, user_id))
            
            if row:
                card = dict(row)
                mult = get_mutation_multiplier(card['mutation'])
                card['damage'] = int(card['damage'] * mult)
                card['hp'] = int(card['hp'] * mult)
                if card['class_type'] == 'Booster':
                    card['booster_dmg_mult'] = round(card['booster_dmg_mult'] * mult, 2)
                    card['booster_hp_mult'] = round(card['booster_hp_mult'] * mult, 2)
                    
                if card['signed_by'] > 0:
                    signer_info = await fetch_one("SELECT username, first_name FROM users WHERE id = ?", (card['signed_by'],))
                    card['signer_name'] = get_display_name(signer_info) if signer_info else f"ID:{card['signed_by']}"

                card['max_hp'] = card['hp']
                card['burn'] = 0     
                card['dmg_buff'] = 0 
                card['heal_power_mult'] = 1.0
                card['shield'] = 0
                team.append(card)
            else:
                await execute_db(f"UPDATE users SET {slot} = 0 WHERE id = ?", (user_id,))
    return team

async def get_bot_team(user_id: int, difficulty_mult: float, rank_name: str, diff_type: str = "med"):
    all_cards = await fetch_all("SELECT id, name, rarity, class_type, damage, hp, booster_dmg_mult, booster_hp_mult FROM cards WHERE rarity != 'Secret' AND is_cardball_exclusive = 0")
    if len(all_cards) < 4: return []
    
    by_rarity = {}
    for c in all_cards:
        by_rarity.setdefault(c['rarity'], []).append(c)
        
    parts = rank_name.split()
    base_rank = parts[1] if len(parts) > 1 else "Bronze"
    
    ranks_order = ["Bronze", "Silver", "Gold", "Platina", "Diamond", "Ruby", "Uranium"]
    rank_idx = ranks_order.index(base_rank) if base_rank in ranks_order else 0

    if diff_type == "easy": effective_idx = max(0, rank_idx - 1)
    elif diff_type == "med": effective_idx = rank_idx
    elif diff_type == "hard": effective_idx = min(len(ranks_order)-1, rank_idx + 1)
    elif diff_type == "nightmare": effective_idx = min(len(ranks_order)-1, rank_idx + 2)
    else: effective_idx = rank_idx

    effective_rank = ranks_order[effective_idx]
    team_selection = []
    used_ids = set()
    
    # Bots strictly use 4 cards!
    for _ in range(4):
        r = random.random()
        pool = []
        if effective_rank == "Bronze": pool = by_rarity.get('Basic', []) + by_rarity.get('Uncommon', [])
        elif effective_rank == "Silver": pool = by_rarity.get('Uncommon', []) + by_rarity.get('Rare', []) + (by_rarity.get('Epic', []) if r < 0.1 else [])
        elif effective_rank == "Gold": pool = by_rarity.get('Rare', []) + by_rarity.get('Epic', []) + (by_rarity.get('Legendary', []) if r < 0.1 else [])
        elif effective_rank == "Platina": pool = by_rarity.get('Epic', []) + by_rarity.get('Legendary', []) + (by_rarity.get('Mythic', []) if r < 0.1 else [])
        elif effective_rank == "Diamond": pool = by_rarity.get('Legendary', []) + by_rarity.get('Mythic', []) + (by_rarity.get('Super', []) if r < 0.1 else [])
        elif effective_rank == "Ruby": pool = by_rarity.get('Mythic', []) + by_rarity.get('Super', []) + by_rarity.get('Exclusive', []) + (by_rarity.get('Leaderboard', []) if r < 0.1 else [])
        elif effective_rank == "Uranium":
            if diff_type == "nightmare": pool = by_rarity.get('Super', []) + by_rarity.get('Exclusive', []) + by_rarity.get('Leaderboard', [])
            else: pool = by_rarity.get('Super', []) + by_rarity.get('Exclusive', []) + by_rarity.get('Mythic', []) + by_rarity.get('Leaderboard', [])
        
        filtered_pool = [c for c in pool if c['id'] not in used_ids]
        if not filtered_pool:
            filtered_pool = [c for c in all_cards if c['id'] not in used_ids and c['rarity'] != 'Leaderboard']
            if not filtered_pool: filtered_pool = all_cards 
            
        weighted_pool = []
        for c in filtered_pool:
            weight = 1 if c['class_type'] == 'Healer' else 4
            weighted_pool.extend([c] * weight)
            
        chosen = random.choice(weighted_pool)
        used_ids.add(chosen['id'])
        team_selection.append(chosen)
        
    team_copies = []
    for c in team_selection:
        c_copy = dict(c)
        c_copy['max_hp'] = c_copy['hp']
        mut_chance = random.random()
        if difficulty_mult >= 1.0 or diff_type == "nightmare": 
            rainbow_prob = min(0.009, 0.005 * difficulty_mult) 
            diamond_prob = min(0.05, 0.03 * difficulty_mult)
            gold_prob = min(0.15, 0.08 * difficulty_mult)     
            if mut_chance < rainbow_prob: 
                c_copy['mutation'] = "Rainbow"
                c_copy['damage'] = int(c_copy['damage'] * 1.45)
                c_copy['hp'] = int(c_copy['hp'] * 1.45)
            elif mut_chance < rainbow_prob + diamond_prob:
                c_copy['mutation'] = "Diamond"
                c_copy['damage'] = int(c_copy['damage'] * 1.30)
                c_copy['hp'] = int(c_copy['hp'] * 1.30)
            elif mut_chance < rainbow_prob + diamond_prob + gold_prob: 
                c_copy['mutation'] = "Gold"
                c_copy['damage'] = int(c_copy['damage'] * 1.15)
                c_copy['hp'] = int(c_copy['hp'] * 1.15)
            else: c_copy['mutation'] = "Normal"
        else: c_copy['mutation'] = "Normal"
            
        c_copy['max_hp'] = c_copy['hp']
        c_copy['burn'] = 0
        c_copy['dmg_buff'] = 0
        c_copy['serial_number'] = 0
        c_copy['signed_by'] = 0
        c_copy['heal_power_mult'] = 1.0  
        c_copy['shield'] = 0
        team_copies.append(c_copy)
        
    return team_copies

def format_combat_team_vertical(team):
    if not team: return "<i>Все мертвы</i>"
    res = []
    for c in team:
        if c['hp'] <= 0:
            res.append(f"💀 <s>{html.escape(c['name'])}</s>")
            continue
        status = ""
        if c.get('mutation') == 'Rainbow': status += "🌈"
        elif c.get('mutation') == 'Diamond': status += "💎"
        elif c.get('mutation') == 'Gold': status += "⭐"
        if c.get('burn', 0) > 0: status += "🔥"
        if c.get('dmg_buff', 0) > 0: status += "✨"
        if c.get('shield', 0) > 0: status += f"🛡️({c['shield']})"
        if c['class_type'] == 'Booster': status += "🔋"
        if c['class_type'] == 'Healer': status += "💗"
        
        s_str = f" [#{c['serial_number']:04d}]" if c.get('serial_number', 0) > 0 else ""
        sgn_str = ""
        if c.get('signed_by', 0) > 0:
            s_name = c.get('signer_name') or f"ID:{c['signed_by']}"
            sgn_str = f" ✍️ Sign: {s_name}"
            
        if c['class_type'] == 'Healer':
            heal_val = int((c['damage'] + c.get('dmg_buff', 0)) * c.get('heal_power_mult', 1.0))
            res.append(f"• {html.escape(c['name'])}{s_str}{sgn_str}{status} (💗{heal_val} | ❤️{c['hp']}/{c['max_hp']})")
        else:
            dmg = c['damage'] + c.get('dmg_buff', 0)
            res.append(f"• {html.escape(c['name'])}{s_str}{sgn_str}{status} (⚔️{dmg} | ❤️{c['hp']}/{c['max_hp']})")
    return "\n".join(res)

def build_battle_header(p1_name, t1, p2_name, t2):
    return (
        f"⚔️ <b>АРЕНА: БИТВА</b> ⚔️\n━━━━━━━━━━━━━━━━━━━━━━━━\n🔵 <b>Команда {p1_name}:</b>\n{format_combat_team_vertical(t1)}\n\n🔴 <b>Команда {p2_name}:</b>\n{format_combat_team_vertical(t2)}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

def add_dual_log(log1, log2, text_ru):
    if log1 is not None: log1.append(text_ru)
    if log2 is not None: log2.append(text_ru)

def apply_boosters(team, team_name, log1, log2):
    boosters = [c for c in team if c['class_type'] == 'Booster']
    if not boosters: return
    for b in boosters:
        d_mult = b['booster_dmg_mult']
        h_mult = b['booster_hp_mult']
        add_dual_log(log1, log2, f"✨ <b>{team_name}:</b> Бустер <b>{html.escape(b['name'])}</b> усиливает команду! (Урон x{d_mult}, ХП x{h_mult})")
        for c in team:
            bonus_hp = int(c['hp'] * h_mult) - c['hp']
            if bonus_hp > 0:
                c['hp'] += bonus_hp
                c['max_hp'] += bonus_hp
            if c['class_type'] != 'Booster':
                c['dmg_buff'] += int(c['damage'] * d_mult) - c['damage']

async def process_burns(team, team_name, log1, log2):
    for c in team:
        if c['hp'] > 0 and c.get('burn', 0) > 0:
            c['hp'] -= c['burn']
            ru_str = f"🔥 {team_name}: <b>{html.escape(c['name'])}</b> получает {c['burn']} урона от горения!"
            if c['hp'] <= 0:
                c['hp'] = 0
                ru_str += " ☠️ <i>Сгорел дотла!</i>"
            add_dual_log(log1, log2, ru_str)
            c['burn'] = 0

async def execute_turn(atk_team, def_team, atk_name, def_name, log1, log2, force_attacker=None, force_target=None, mods=None, is_player_atk=True):
    await process_burns(atk_team, atk_name, log1, log2)
    atk_alive = [c for c in atk_team if c['hp'] > 0]
    def_alive = [c for c in def_team if c['hp'] > 0]
    heals = 0
    if not atk_alive or not def_alive: return False, heals
    
    if force_attacker and force_attacker['hp'] > 0 and force_attacker in atk_alive:
        atk = force_attacker
    else:
        atk = random.choice(atk_alive)
        
    base_dmg = atk['damage'] + atk.get('dmg_buff', 0)
    c_type = atk['class_type']
    
    dead_ru = " ☠️ <i>Мертв!</i>"
    
    if c_type == "Booster":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
        
        dmg = max(10, int(target['max_hp'] * 0.1))
        
        # Shield mechanism
        if target.get('shield', 0) > 0:
            if target['shield'] >= dmg:
                target['shield'] -= dmg
                dmg = 0
            else:
                dmg -= target['shield']
                target['shield'] = 0
                
        target['hp'] -= dmg
        ru_str = f"🔋 {atk_name}: <b>{html.escape(atk['name'])}</b> пускает заряд в <b>{html.escape(target['name'])}</b> на {dmg}!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
        # Vampirism
        if mods and mods.get('gp_vamp') == 1 and is_player_atk and dmg > 0:
            v_heal = int(dmg * 0.25)
            atk['hp'] = min(atk['max_hp'], atk['hp'] + v_heal)
            add_dual_log(log1, log2, f"🩸 <b>{atk['name']}</b> восполняет {v_heal} ХП от вампиризма!")
        
    elif c_type == "Healer":
        # Check if healing is blocked by modifier
        if mods and mods.get('mod_no_heals') == 1 and is_player_atk:
            add_dual_log(log1, log2, f"❌ <b>Дебафф:</b> {atk_name} Heals are fully disabled!")
            return True, 0
            
        other_allies = [c for c in atk_alive if c is not atk]
        
        if force_target and force_target['hp'] > 0 and force_target in atk_alive:
            target = force_target
            do_heal = True
        elif other_allies:
            target = random.choice(other_allies)
            do_heal = True
        else:
            do_heal = False
            
        if do_heal:
            curr_mult = atk.get('heal_power_mult', 1.0)
            heal_amount = int(base_dmg * curr_mult)
            
            target['hp'] += heal_amount
            if target['hp'] > target['max_hp']: 
                target['hp'] = target['max_hp']
                
            ru_str = f"💗 {atk_name}: <b>{html.escape(atk['name'])}</b> исцеляет союзника <b>{html.escape(target['name'])}</b> на {heal_amount} HP!"
            add_dual_log(log1, log2, ru_str)
            heals += 1
            
            atk['heal_power_mult'] = max(0.0, curr_mult - 0.03)
        else:
            if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
            else: target = random.choice(def_alive)
            
            dmg = max(5, int(base_dmg * 0.2))
            
            # Shield
            if target.get('shield', 0) > 0:
                if target['shield'] >= dmg:
                    target['shield'] -= dmg
                    dmg = 0
                else:
                    dmg -= target['shield']
                    target['shield'] = 0
                    
            target['hp'] -= dmg
            ru_str = f"🎯 {atk_name}: Одинокий Хилер <b>{html.escape(atk['name'])}</b> бьет <b>{html.escape(target['name'])}</b> на {dmg}!"
            if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
            add_dual_log(log1, log2, ru_str)
            
            # Vampirism
            if mods and mods.get('gp_vamp') == 1 and is_player_atk and dmg > 0:
                v_heal = int(dmg * 0.25)
                atk['hp'] = min(atk['max_hp'], atk['hp'] + v_heal)
                add_dual_log(log1, log2, f"🩸 <b>{atk['name']}</b> восполняет {v_heal} ХП от вампиризма!")
        
    elif c_type == "AOE":
        ru_str = f"🌪 {atk_name}: <b>{html.escape(atk['name'])}</b> бьет по всем на {base_dmg}!"
        total_dmg_dealt = 0
        for d in def_alive:
            cur_dmg = base_dmg
            if d.get('shield', 0) > 0:
                if d['shield'] >= cur_dmg:
                    d['shield'] -= cur_dmg
                    cur_dmg = 0
                else:
                    cur_dmg -= d['shield']
                    d['shield'] = 0
                    
            d['hp'] -= cur_dmg
            total_dmg_dealt += cur_dmg
            if d['hp'] <= 0:
                d['hp'] = 0
                ru_str += f" ☠️ <i>{html.escape(d['name'])} мертв!</i>"
        add_dual_log(log1, log2, ru_str)
        
        # Vampirism
        if mods and mods.get('gp_vamp') == 1 and is_player_atk and total_dmg_dealt > 0:
            v_heal = int(total_dmg_dealt * 0.25)
            atk['hp'] = min(atk['max_hp'], atk['hp'] + v_heal)
            add_dual_log(log1, log2, f"🩸 <b>{atk['name']}</b> восполняет {v_heal} ХП от вампиризма!")
        
    elif c_type == "Splash":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: main_t = force_target
        else: main_t = random.choice(def_alive)
            
        splash_dmg = int(base_dmg * 0.5)
        ru_str = f"🌊 {atk_name}: <b>{html.escape(atk['name'])}</b> наносит {base_dmg} по <b>{html.escape(main_t['name'])}</b> и {splash_dmg} остальным!"
        total_dmg_dealt = 0
        for d in def_alive:
            dmg = base_dmg if d == main_t else splash_dmg
            
            if d.get('shield', 0) > 0:
                if d['shield'] >= dmg:
                    d['shield'] -= dmg
                    dmg = 0
                else:
                    dmg -= d['shield']
                    d['shield'] = 0
                    
            d['hp'] -= dmg
            total_dmg_dealt += dmg
            if d['hp'] <= 0:
                d['hp'] = 0
                ru_str += f" ☠️ <i>{html.escape(d['name'])} мертв!</i>"
        add_dual_log(log1, log2, ru_str)
        
        # Vampirism
        if mods and mods.get('gp_vamp') == 1 and is_player_atk and total_dmg_dealt > 0:
            v_heal = int(total_dmg_dealt * 0.25)
            atk['hp'] = min(atk['max_hp'], atk['hp'] + v_heal)
            add_dual_log(log1, log2, f"🩸 <b>{atk['name']}</b> восполняет {v_heal} ХП от вампиризма!")
        
    elif c_type == "Fire":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
            
        dmg = base_dmg
        if target.get('shield', 0) > 0:
            if target['shield'] >= dmg:
                target['shield'] -= dmg
                dmg = 0
            else:
                dmg -= target['shield']
                target['shield'] = 0
                
        target['hp'] -= dmg
        target['burn'] = target.get('burn', 0) + base_dmg
        ru_str = f"🔥 {atk_name}: <b>{html.escape(atk['name'])}</b> бьет <b>{html.escape(target['name'])}</b> на {dmg} и поджигает!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
        # Vampirism
        if mods and mods.get('gp_vamp') == 1 and is_player_atk and dmg > 0:
            v_heal = int(dmg * 0.25)
            atk['hp'] = min(atk['max_hp'], atk['hp'] + v_heal)
            add_dual_log(log1, log2, f"🩸 <b>{atk['name']}</b> восполняет {v_heal} ХП от вампиризма!")
        
    else:
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
            
        dmg = base_dmg
        if target.get('shield', 0) > 0:
            if target['shield'] >= dmg:
                target['shield'] -= dmg
                dmg = 0
            else:
                dmg -= target['shield']
                target['shield'] = 0
                
        target['hp'] -= dmg
        ru_str = f"🎯 {atk_name}: <b>{html.escape(atk['name'])}</b> наносит {dmg} по <b>{html.escape(target['name'])}</b>!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
        # Vampirism
        if mods and mods.get('gp_vamp') == 1 and is_player_atk and dmg > 0:
            v_heal = int(dmg * 0.25)
            atk['hp'] = min(atk['max_hp'], atk['hp'] + v_heal)
            add_dual_log(log1, log2, f"🩸 <b>{atk['name']}</b> восполняет {v_heal} ХП от вампиризма!")
        
    return True, heals

async def get_dynamic_trophies(rank_name: str, rank_idx: int, diff_scale: float = 1.0) -> int:
    if "Uranium VI" in rank_name or "Uranium VII" in rank_name:
        return random.randint(1, 2)
    base = max(5, 18 - int((rank_idx / 25) * 12)) 
    won = random.randint(base, base+3)
    return int(won * diff_scale)

async def add_bp_xp(user_id: int, xp_to_add: int, is_football: int = 0) -> tuple:
    db = await get_db_connection()
    try:
        user_bp = await db.execute("""
            SELECT ubp.bp_id, ubp.level, ubp.xp 
            FROM user_bp ubp JOIN battle_passes bp ON ubp.bp_id = bp.id
            WHERE ubp.user_id = ? AND ubp.is_active = 1 AND bp.is_football = ?
        """, (user_id, is_football))
        ubp = await user_bp.fetchone()
        if not ubp: return False, None, 0
        
        bp_id = ubp['bp_id']
        curr_lvl = ubp['level']
        curr_xp = ubp['xp'] + xp_to_add
        level_up = False
        
        while True:
            next_lvl = await db.execute("SELECT xp_required FROM bp_levels WHERE bp_id = ? AND level = ?", (bp_id, curr_lvl + 1))
            nl = await next_lvl.fetchone()
            if not nl: break 
            
            if curr_xp >= nl['xp_required']:
                curr_lvl += 1
                curr_xp -= nl['xp_required']
                level_up = True
            else:
                break
                
        await db.execute("UPDATE user_bp SET level = ?, xp = ? WHERE user_id = ? AND bp_id = ?", (curr_lvl, curr_xp, user_id, bp_id))
        bp_info = await db.execute("SELECT title FROM battle_passes WHERE id = ?", (bp_id,))
        bp = await bp_info.fetchone()
        
        await db.commit()
        return level_up, bp['title'] if bp else "BP", curr_lvl
    finally:
        await db.close()

async def player_manual_turn(chat_id, p1_id, t1, t2):
    t1_alive = [c for c in t1 if c['hp'] > 0]
    t2_alive = [c for c in t2 if c['hp'] > 0]
    if not t1_alive or not t2_alive: return None, None

    ev = asyncio.Event()
    active_manual_battles[chat_id] = {'p1_id': p1_id, 't1': t1, 't2': t2, 'event': ev, 'attacker_idx': None, 'target_idx': None, 'step': 'atk'}

    kb_btns = []
    for i, c in enumerate(t1):
        if c['hp'] > 0:
            is_heal = (c['class_type'] == 'Healer')
            stat_val = int((c['damage'] + c.get('dmg_buff', 0)) * c.get('heal_power_mult', 1.0)) if is_heal else (c['damage'] + c.get('dmg_buff', 0))
            icon = "💗" if is_heal else "⚔️"
            kb_btns.append([InlineKeyboardButton(text=f"{icon} {c['name']} ({icon}{stat_val} | ❤️{c['hp']})", callback_data=f"manatk_{i}")])
            
    kb = InlineKeyboardMarkup(inline_keyboard=kb_btns)
    
    try:
        msg = await bot.send_message(chat_id, "⏳ <b>Ваш ход!</b> Выберите карту для действия (12 сек):", reply_markup=kb)
    except:
        return None, None

    try:
        await asyncio.wait_for(ev.wait(), timeout=12.0)
        a_idx = active_manual_battles[chat_id]['attacker_idx']
        t_idx = active_manual_battles[chat_id]['target_idx']
        atk = t1[a_idx] if a_idx is not None else None
        
        if atk and atk['class_type'] == 'Healer':
            tgt = t1[t_idx] if t_idx is not None else None
        else:
            tgt = t2[t_idx] if t_idx is not None else None
    except asyncio.TimeoutError:
        atk = None
        tgt = None
    finally:
        active_manual_battles.pop(chat_id, None)
        try: await msg.delete()
        except: pass

    return atk, tgt

@dp.callback_query(F.data.startswith("manatk_"))
async def cb_man_atk(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_manual_battles or active_manual_battles[chat_id]['p1_id'] != callback.from_user.id:
        return await callback.answer("Не ваш ход!", show_alert=True)

    idx = int(callback.data.split("_")[1])
    active_manual_battles[chat_id]['attacker_idx'] = idx
    active_manual_battles[chat_id]['step'] = 'tgt'

    t1 = active_manual_battles[chat_id]['t1']
    t2 = active_manual_battles[chat_id]['t2']
    atk = t1[idx]

    is_heal = (atk['class_type'] == 'Healer')
    target_team = t1 if is_heal else t2

    kb_btns = []
    for i, c in enumerate(target_team):
        if c['hp'] > 0:
            dmg_val = (c['damage'] + c.get('dmg_buff', 0))
            kb_btns.append([InlineKeyboardButton(text=f"{'💗' if is_heal else '🎯'} {c['name']} (⚔️{dmg_val} | ❤️{c['hp']})", callback_data=f"mantgt_{i}")])
            
    kb = InlineKeyboardMarkup(inline_keyboard=kb_btns)
    try: await callback.message.edit_text(f"Выбран: <b>{atk['name']}</b>\nВыберите цель:", reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("mantgt_"))
async def cb_man_tgt(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in active_manual_battles or active_manual_battles[chat_id]['p1_id'] != callback.from_user.id:
        return await callback.answer("Не ваш ход!", show_alert=True)

    idx = int(callback.data.split("_")[1])
    active_manual_battles[chat_id]['target_idx'] = idx
    active_manual_battles[chat_id]['event'].set()
    await callback.answer()

async def do_player_turn_wrapper(chat_id, p1_id, p1_name, p2_name, t1, t2, log, mods, is_pvp):
    if mods and mods.get('mod_manual_atk') and not is_pvp:
        atk, tgt = await player_manual_turn(chat_id, p1_id, t1, t2)
        did_turn, heals = await execute_turn(t1, t2, p1_name, p2_name, log, None, force_attacker=atk, force_target=tgt, mods=mods, is_player_atk=True)
    else:
        did_turn, heals = await execute_turn(t1, t2, p1_name, p2_name, log, None, mods=mods, is_player_atk=True)
    return did_turn, heals

@dp.callback_query(F.data.startswith("surrender_battle_"))
async def cb_surrender_battle_fixed(callback: types.CallbackQuery):
    battle_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    surrendered_players.add((user_id, battle_id))
    chat_id = callback.message.chat.id
    if chat_id in active_manual_battles and active_manual_battles[chat_id]['p1_id'] == user_id:
        active_manual_battles[chat_id]['event'].set()
    await callback.answer("🏳️ Вы сдались!", show_alert=True)

def get_battle_kb(battle_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f"surrender_battle_{battle_id}")]
    ])

async def battle_delay(battle_id, p1_id, p2_id, delay=3.0):
    steps = int(delay * 10)
    for _ in range(steps):
        await asyncio.sleep(0.1)
        if (p1_id, battle_id) in surrendered_players or (p2_id, battle_id) in surrendered_players:
            break

async def safe_edit_text(msg, text, reply_markup=None):
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass 
        else:
            raise e

async def run_battle_loop(bot: Bot, chat_id: int, p1_id: int, p1_name: str, p2_id: int, p2_name: str, t1: list, t2: list, diff_trophies_scale: float = 1.0, diff_bp_mult: float = 1.0, is_pvp: bool = False, pvp_no_rewards: bool = False, mods=None, diff_type: str = "med"):
    battle_id = f"bt_{p1_id}_{int(time.time())}"
    surrendered_players.discard((p1_id, battle_id))
    if p2_id:
        surrendered_players.discard((p2_id, battle_id))
        
    try:
        msg = await bot.send_message(chat_id, f"⚔️ Бой <b>{p1_name}</b> VS <b>{p2_name}</b> начнется через 3 сек!")
        await asyncio.sleep(1)
        await safe_edit_text(msg, "⚔️ Бой начнется через 2 сек!")
        await asyncio.sleep(1)
        await safe_edit_text(msg, "⚔️ Бой начнется через 1 сек!")
        
        battle_start_time = time.time()
        log = []
        apply_boosters(t1, p1_name, log, None)
        apply_boosters(t2, p2_name, log, None)
        
        # New Buff Modifier: Shield 30%
        if mods and mods.get('mod_player_shield') == 1:
            for c in t1:
                c['shield'] = int(c['max_hp'] * 0.3)
            log.append("🛡️ <b>Модификатор:</b> Ваши юниты получили щит в размере 30% от макс. ХП!")
            
        # New Debuff Modifier: Burn 20 start
        if mods and mods.get('mod_enemy_burn') == 1:
            for c in t1:
                c['burn'] = 20
            log.append("🔥 <b>Модификатор:</b> Ваши юниты начинают бой с 20 ед. горения!")

        if log:
            await safe_edit_text(msg, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log), reply_markup=get_battle_kb(battle_id))
            await battle_delay(battle_id, p1_id, p2_id)

        turn = 1
        winner = None
        winner_id = None
        loser_id = None
        p1_total_heals = 0
        p2_total_heals = 0
        timeout_flag = False
        
        while True:
            if time.time() - battle_start_time > 180:
                timeout_flag = True
                break
                
            if (p1_id, battle_id) in surrendered_players:
                winner = p2_name; winner_id = p2_id; loser_id = p1_id
                surrendered_players.discard((p1_id, battle_id))
                log.append(f"🏳️ <b>{p1_name} сдался!</b>")
                break

            t1_alive = [c for c in t1 if c['hp'] > 0]
            t2_alive = [c for c in t2 if c['hp'] > 0]
            
            if not t1_alive and not t2_alive:
                winner = "Ничья"
                break
            elif not t1_alive:
                winner = p2_name
                winner_id = p2_id
                loser_id = p1_id
                break
            elif not t2_alive:
                winner = p1_name
                winner_id = p1_id
                loser_id = p2_id
                break
                
            if turn > 40:
                winner = "Ничья по раундам"
                break

            did_turn, heals = await do_player_turn_wrapper(chat_id, p1_id, p1_name, p2_name, t1, t2, log, mods, is_pvp)
            p1_total_heals += heals
            if did_turn:
                if len(log) > 6: log = log[-6:]
                try: 
                    await safe_edit_text(msg, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log), reply_markup=get_battle_kb(battle_id))
                except Exception as e:
                    if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag = True; break
                await battle_delay(battle_id, p1_id, p2_id)
                
                t2_alive = [c for c in t2 if c['hp'] > 0]
                if t2_alive and mods and mods.get('mod_player_atk_all') and not is_pvp:
                    did_turn_extra, heals_extra = await do_player_turn_wrapper(chat_id, p1_id, p1_name, p2_name, t1, t2, log, mods, is_pvp)
                    p1_total_heals += heals_extra
                    if did_turn_extra:
                        if len(log) > 6: log = log[-6:]
                        try: await safe_edit_text(msg, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log), reply_markup=get_battle_kb(battle_id))
                        except: pass
                        await battle_delay(battle_id, p1_id, p2_id)

            t2_alive = [c for c in t2 if c['hp'] > 0]
            if t2_alive:
                if time.time() - battle_start_time > 180:
                    timeout_flag = True
                    break

                did_turn_e, heals_e = await execute_turn(t2, t1, p2_name, p1_name, log, None, mods=mods, is_player_atk=False)
                p2_total_heals += heals_e
                if did_turn_e:
                    if len(log) > 6: log = log[-6:]
                    try: 
                        await safe_edit_text(msg, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log), reply_markup=get_battle_kb(battle_id))
                    except Exception as e:
                        if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag = True; break
                    await battle_delay(battle_id, p1_id, p2_id)
                    
                t1_alive_check = [c for c in t1 if c['hp'] > 0]
                if t1_alive_check and mods and mods.get('mod_enemy_atk_all') and not is_pvp:
                    did_turn_e_extra, heals_e_extra = await execute_turn(t2, t1, p2_name, p1_name, log, None, mods=mods, is_player_atk=False)
                    p2_total_heals += heals_e_extra
                    if did_turn_e_extra:
                        if len(log) > 6: log = log[-6:]
                        try: await safe_edit_text(msg, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log), reply_markup=get_battle_kb(battle_id))
                        except: pass
                        await battle_delay(battle_id, p1_id, p2_id)
            turn += 1

        if timeout_flag:
            try: await msg.edit_text("⏳ <b>Бой автоматически прерван (ошибка или тайм-аут)!</b>")
            except: pass
            return

        try:
            if is_pvp:
                await add_quest_progress_new(p1_id, 'q_pvp', 1)
                if p2_id != 0: 
                    await add_quest_progress_new(p2_id, 'q_pvp', 1)
            else:
                await add_quest_progress_new(p1_id, 'q_pve', 1)

            code_text = ""
            winner_user_id = None
            if winner == p1_name: winner_user_id = p1_id
            elif is_pvp and winner == p2_name: winner_user_id = p2_id

            # Promo Code drops from the pool of active, admin-generated promo codes!
            if winner_user_id is not None and "Ничья" not in winner:
                if random.random() <= 0.05: 
                    # Get any active admin promo code from the db
                    pool_code = await fetch_one("SELECT code FROM reward_codes WHERE owner_id = 0 AND is_active = 1 LIMIT 1")
                    if pool_code:
                        await execute_db("UPDATE reward_codes SET owner_id = ? WHERE code = ?", (winner_user_id, pool_code['code']))
                        code_text = (
                            f"🎁 <b>ВЫПАЛ КОД-НАГРАДА ОТ АДМИНИСТРАЦИИ! (Шанс 5%)</b>\n"
                            f"Нажми, чтобы скопировать: <code>{pool_code['code']}</code>\n"
                            f"Активируй через /codereward\n\n"
                        )

            final_text = code_text + f"🏁 <b>ИТОГИ БОЯ: {p1_name} VS {p2_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n👑 <b>Победитель: {winner}</b>\n\n"
            bp_messages = []
            
            if pvp_no_rewards:
                final_text += "🤝 <b>Дружеская дуэль завершена!</b> Награды и кубки не начислялись."
            elif is_pvp:
                if "Ничья" not in winner and winner_id and loser_id:
                    await execute_db("UPDATE users SET trophies = trophies + 15 WHERE id = ?", (winner_id,))
                    await execute_db("UPDATE users SET trophies = MAX(0, trophies - 10) WHERE id = ?", (loser_id,))
                    final_text += f"🏆 Победитель забирает <b>+15 Кубков</b>\n💀 Проигравший теряет <b>-10 Кубков</b>"
            else:
                mod_reward_mult = 1.0; mod_trophy_mult = 1.0
                if mods:
                    if mods.get('mod_enemy_hp'): mod_reward_mult += 0.3; mod_trophy_mult += 0.3
                    if mods.get('mod_enemy_atk_all'): mod_reward_mult += 0.35; mod_trophy_mult += 0.35
                    if mods.get('mod_enemy_stats'): mod_reward_mult += 0.2; mod_trophy_mult += 0.2
                    if mods.get('mod_enemy_burn'): mod_reward_mult += 0.25; mod_trophy_mult += 0.25
                    if mods.get('mod_no_heals'): mod_reward_mult += 0.30; mod_trophy_mult += 0.30
                    if mods.get('mod_player_atk_all'): mod_reward_mult -= 0.4
                    if mods.get('mod_manual_atk'): mod_reward_mult -= 0.5
                    if mods.get('mod_player_hp'): mod_reward_mult -= 0.3
                    if mods.get('mod_player_shield'): mod_reward_mult -= 0.2
                    if mods.get('mod_player_vamp'): mod_reward_mult -= 0.25
                    
                mod_reward_mult = max(0.1, mod_reward_mult)
                coin_mult, xp_mult_event = await get_coin_xp_events(p1_id)
                
                if winner == p1_name:
                    user_data = await fetch_one("SELECT trophies FROM users WHERE id = ?", (p1_id,))
                    user_trophies = user_data['trophies'] if user_data else 0
                    rank = await get_user_rank(user_trophies)
                    
                    coins_base = random.randint(25, 90) * rank['reward_mult'] * diff_trophies_scale * 0.85 * coin_mult
                    coins_won = int(coins_base * mod_reward_mult)
                    won_t_base = await get_dynamic_trophies(rank['name'], rank['rank_idx'], diff_trophies_scale)
                    won_t = int(won_t_base * mod_trophy_mult)
                    
                    await execute_db("UPDATE users SET coins = coins + ?, total_coins = total_coins + ?, trophies = trophies + ? WHERE id = ?", (coins_won, coins_won, won_t, p1_id))
                    
                    # R$ Game reward checks (STRICT, NO LUCK MULTIPLIERS PER USER'S REQUEST)
                    robux_won = 0
                    r_chance = random.random()
                    if diff_type == "easy" and r_chance <= 0.05:
                        robux_won = 1
                    elif diff_type == "med" and r_chance <= 0.10:
                        robux_won = 1
                    elif diff_type == "hard" and r_chance <= 0.20:
                        robux_won = 2
                    elif diff_type == "nightmare" and r_chance <= 0.20:
                        robux_won = 3
                        
                    if robux_won > 0:
                        await execute_db("UPDATE users SET robux = robux + ? WHERE id = ?", (robux_won, p1_id))
                    
                    final_text += f"🎉 <b>Награды:</b>\n💰 {coins_won} Шекелей"
                    if coin_mult > 1.0: final_text += f" (Ивент x{coin_mult})"
                    if mod_reward_mult != 1.0: final_text += f" [Моды x{mod_reward_mult:.2f}]"
                    if robux_won > 0: final_text += f"\n💸 <b>+{robux_won} R$ (Робуксов) за победу!</b>"
                    final_text += f"\n🏆 {won_t} Кубков\n"
                    
                    bp_xp = int((20 * diff_bp_mult * xp_mult_event) * mod_reward_mult)
                    lvl_up, bp_title, new_lvl = await add_bp_xp(p1_id, bp_xp)
                    final_text += f"🎫 +{bp_xp} BP XP"
                    if lvl_up: bp_messages.append(f"🎉 <b>НОВЫЙ УРОВЕНЬ БП!</b> {new_lvl} уровень в сезоне «{bp_title}»!")
                    
                elif winner == p2_name:
                    user_data = await fetch_one("SELECT trophies FROM users WHERE id = ?", (p1_id,))
                    user_trophies = user_data['trophies'] if user_data else 0
                    rank = await get_user_rank(user_trophies)
                    
                    if "Uranium VI" in rank['name'] or "Uranium VII" in rank['name']:
                        lost_t = random.randint(30, 50)
                    else:
                        lost_t = 2
                    
                    await execute_db("UPDATE users SET trophies = MAX(0, trophies - ?) WHERE id = ?", (lost_t, p1_id))
                    final_text += f"💀 Вы проиграли и потеряли <b>{lost_t} 🏆</b>.\n"
                    bp_xp = int((5 * diff_bp_mult * xp_mult_event) * mod_reward_mult)
                    lvl_up, bp_title, new_lvl = await add_bp_xp(p1_id, bp_xp)
                    final_text += f"🎫 +{bp_xp} BP XP"
                    if lvl_up: bp_messages.append(f"🎉 <b>НОВЫЙ УРОВЕНЬ БП!</b> {new_lvl} уровень в сезоне «{bp_title}»!")
                    
            try: await msg.edit_text(final_text, reply_markup=None)
            except Exception: pass
            
            for b_msg in bp_messages:
                try: await bot.send_message(p1_id, b_msg)
                except: pass

        except Exception as e:
            logging.error(f"Reward error: {e}")
            try: await msg.edit_text("Ошибка при выдаче наград.", reply_markup=None)
            except: pass

    except Exception as e:
        logging.error(f"Critical battle loop error: {e}")
        try: await bot.send_message(chat_id, "⚠️ Критическая ошибка. Бой прерван.")
        except: pass
    finally:
        active_combats.discard(p1_id)
        if is_pvp and p2_id != 0: active_combats.discard(p2_id)
        if chat_id in active_manual_battles: active_manual_battles.pop(chat_id, None)

@dp.message(F.text == BTN_PVE)
async def cmd_pve_select(message: types.Message):
    if await check_ban(message.from_user.id): return
    if message.from_user.id in active_combats: return await message.answer("❌ Вы уже в бою!")
    if message.from_user.id in user_trades: return await message.answer("❌ Завершите обмен!")
        
    team1 = await get_team_data(message.from_user.id)
    if not team1: return await message.answer("❌ Боевая колода пуста!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Лёгкий (-50% Кубки, -20% XP)", callback_data="pve_diff_easy")],
        [InlineKeyboardButton(text="🟡 Средний (Стандарт)", callback_data="pve_diff_med")],
        [InlineKeyboardButton(text="🔴 Сложный (+40% Кубки, +20% XP)", callback_data="pve_diff_hard")],
        [InlineKeyboardButton(text="☠️ Кошмар (+80% Кубки, +50% XP)", callback_data="pve_diff_nightmare")]
    ])
    await message.answer("⚔️ <b>ВЫБОР СЛОЖНОСТИ ИИ:</b>\n━━━━━━━━━━━━━━━━━━━━━━━━", reply_markup=kb)

@dp.callback_query(F.data.startswith("pve_diff_"))
async def cmd_pve_battle(callback: types.CallbackQuery):
    if callback.from_user.id in active_combats or callback.from_user.id in user_trades:
        return await callback.answer("❌ Заняты!", show_alert=True)
        
    diff_type = callback.data.split("_")[2]
    power_mult, trophies_scale, bp_xp_mult = 1.0, 1.0, 1.0
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (callback.from_user.id,))
    
    diff_name = "Средний"
    if diff_type == "easy": power_mult, trophies_scale, bp_xp_mult, diff_name = 0.7, 0.5, 0.8, "Лёгкий 🟢"
    elif diff_type == "med": power_mult, trophies_scale, bp_xp_mult, diff_name
