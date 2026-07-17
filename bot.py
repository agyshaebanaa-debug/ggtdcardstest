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
    """
    Рассылает сообщения по всем пользователям, которые не забанены.
    """
    query = "SELECT * FROM users WHERE banned = 0"
    users = await fetch_all(query)
    success = 0
    for u in users:
        try:
            await bot.send_message(u['id'], text_ru)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await notify_super_admin(f"📢 <b>Рассылка завершена.</b>\nДоставлено: {success}")

def get_main_keyboard(is_adm: bool = False, is_sgn: bool = False):
    """
    Генерирует главное клавиатурное меню.
    Кнопка настроек и фильтры удалены, добавлена прямая кнопка модификаторов.
    """
    kb = [
        [KeyboardButton(text=BTN_DRAW), KeyboardButton(text=BTN_PVE), KeyboardButton(text=BTN_PVP)],
        [KeyboardButton(text=BTN_INV), KeyboardButton(text=BTN_PROF), KeyboardButton(text=BTN_EQ)],
        [KeyboardButton(text=BTN_QUESTS), KeyboardButton(text=BTN_SHOP), KeyboardButton(text=BTN_BP)],
        [KeyboardButton(text=BTN_TOP), KeyboardButton(text=BTN_IDX), KeyboardButton(text=BTN_SEED_PACKS)],
        [KeyboardButton(text=BTN_MODIFIERS), KeyboardButton(text=BTN_CRAFT)]
    ]
    
    bottom_row = []
    if is_sgn: 
        bottom_row.append(KeyboardButton(text=BTN_SIGN))
    if is_adm: 
        bottom_row.append(KeyboardButton(text=BTN_ADM))
    if bottom_row: 
        kb.append(bottom_row)
        
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def get_user_rank(trophies: int):
    """
    Возвращает текущий ранг игрока по кубкам.
    """
    ranks = await fetch_all("SELECT * FROM ranks ORDER BY min_trophies DESC")
    for idx, r in enumerate(ranks):
        if trophies >= r['min_trophies']: 
            res = dict(r)
            res['rank_idx'] = len(ranks) - idx - 1
            return res
    return {"name": "🟤 Bronze I", "difficulty_mult": 0.8, "reward_mult": 1.0, "rank_idx": 0}

async def get_active_events():
    """
    Возвращает активные глобальные события (Удача, Перезарядка).
    """
    settings = await fetch_one("SELECT * FROM server_settings WHERE id = 1")
    now = time.time()
    luck = settings['luck_mult'] if settings['luck_end'] > now else 1.0
    cd = settings['cd_mult'] if settings['cd_end'] > now else 1.0
    return luck, cd

async def get_coin_xp_events():
    """
    Возвращает активные глобальные события (Шекели, Опыт).
    """
    settings = await fetch_one("SELECT * FROM server_settings WHERE id = 1")
    now = time.time()
    coin_mult = settings['coin_mult'] if settings['coin_end'] > now else 1.0
    xp_mult = settings['xp_mult'] if settings['xp_end'] > now else 1.0
    return coin_mult, xp_mult


def roll_mutation():
    """
    Рассчитывает выпадение мутации по новым шансам:
    Gold: 15% (r <= 20.9)
    Diamond: 5% (r <= 5.9)
    Rainbow: 0.9% (r <= 0.9)
    """
    r = random.random() * 100
    if r <= 0.9: 
        return "Rainbow"
    if r <= 5.9: 
        return "Diamond"
    if r <= 20.9: 
        return "Gold"
    return "Normal"

def roll_seed_pack_mutation():
    """
    Мутации при открытии Сид-Паков (слегка повышенный шанс).
    """
    r = random.random() * 100
    if r <= 1.5: 
        return "Rainbow"
    if r <= 8.5: 
        return "Diamond"
    if r <= 28.5: 
        return "Gold"
    return "Normal"

def get_mutation_multiplier(mutation: str) -> float:
    """
    Возвращает множитель характеристик для мутации.
    Gold: +15%
    Diamond: +30%
    Rainbow: +45%
    """
    if mutation == "Rainbow": 
        return 1.45
    if mutation == "Diamond": 
        return 1.30
    if mutation == "Gold": 
        return 1.15
    return 1.0

def needs_serial_number(rarity: str, mutation: str) -> bool:
    """
    Проверяет, нужен ли карте серийный номер.
    """
    if rarity in ['Leaderboard', 'Exclusive', 'Mythic', 'Super', 'Secret']: 
        return True
    if rarity == 'Legendary' and mutation in ['Gold', 'Diamond', 'Rainbow']: 
        return True
    return False

async def give_card_to_user(user_id: int, card_id: int, mutation: str, rarity: str = None, custom_serial: int = None, is_football: int = 0) -> tuple:
    """
    Добавляет карту в инвентарь игрока.
    """
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
            await db.commit()
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
            await db.commit()
            return cursor.lastrowid, new_serial, True
        else:
            res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0 AND is_football = ?", (user_id, card_id, mutation, is_football))
            inv_item = await res.fetchone()
            if inv_item:
                await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                await db.commit()
                return inv_item['id'], 0, False
            else:
                cursor = await db.execute(
                    "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, 0, 0, ?)", 
                    (user_id, card_id, mutation, is_football)
                )
                await db.commit()
                return cursor.lastrowid, 0, True
    finally:
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
    name = f"{r_em} {c_em} <b>{html.escape(c['name'])}</b>"
    if c.get('serial_number', 0) > 0:
        name += f" <b>[#{c['serial_number']:04d}]</b>"
    if c.get('signed_by', 0) > 0:
        signer_name = c.get('signer_name') or f"ID:{c['signed_by']}"
        name += f" <i>(✍️ Sign: {signer_name})</i>"
    return name

def format_card_name_plain(c):
    r_em = RARITY_EMOJI.get(c.get('rarity', 'Basic'), "⚪")
    c_em = CLASS_EMOJI.get(c.get('class_type', 'Single'), "🎯")
    name = f"{r_em} {c_em} {c['name']}"
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
    return str(uuid.uuid4()).replace('-', '')[:28]

async def clear_fsm_timeout(state: FSMContext, chat_id: int, delay: int = 60):
    await asyncio.sleep(delay)
    curr = await state.get_state()
    if curr in [TradeState.waiting_target.state, PvPState.waiting_target.state]:
        await state.clear()
        try:
            await bot.send_message(chat_id, "⏳ <i>Время ожидания истекло. Действие отменено.</i>")
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
            sources.append("🎲 Обычная Гача (/getcard)")
        if c['rarity'] == 'Leaderboard':
            sources.append("🏆 Топ игроков (Лидерборд)")
            
    bps = await fetch_all("SELECT bp.title FROM bp_rewards bpr JOIN bp_levels bpl ON bpr.level_id = bpl.id JOIN battle_passes bp ON bpl.bp_id = bp.id WHERE bpr.card_id = ?", (card_id,))
    if bps:
        sources.append("🎟 Батл-Пасс: " + ", ".join(list(set([b['title'] for b in bps]))))
        
    craft = await fetch_one("SELECT id FROM craft_recipes WHERE target_card_id = ?", (card_id,))
    if craft: 
        sources.append("🔨 Мастерская Крафта")

    if not sources:
        return "Невозможно получить (Эксклюзив или Секрет)"
    return "\n".join(f"  └ {s}" for s in sources)


async def calculate_chance_weights(luck_mult: float = 1.0):
    """
    Рассчитывает шансы выпадения карт с учетом ивентов.
    """
    all_cards = await fetch_all("SELECT * FROM cards WHERE drop_chance > 0 AND rarity NOT IN ('Leaderboard', 'Secret') AND is_cardball_exclusive = 0")
    if not all_cards: 
        return [], 0
    total_weight = 0
    weights_dict = {}
    for c in all_cards:
        weight = c['drop_chance']
        if weight < 15.0: 
            weight *= luck_mult
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
        msg_ru = "🛒 <b>МАГАЗИН ОБНОВЛЕН!</b>\nПоступили новые наборы. Успейте приобрести!"
        asyncio.create_task(broadcast_message(msg_ru))

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

async def give_multiple_cards(user_id: int, count: int) -> list:
    """
    Выдает несколько карт из Гачи, учитывая гаранты PITY (Мифик / Супер).
    """
    luck_mult, _ = await get_active_events()
    
    # Check luck boost gamepass (+x1.5 luck)
    user = await fetch_one("SELECT gp_luck_boost, gp_vip, pity_mythic, pity_super FROM users WHERE id=?", (user_id,))
    total_luck = luck_mult
    if user:
        if user['gp_luck_boost'] == 1:
            total_luck *= 1.5
        if user['gp_vip'] == 1:
            total_luck *= 1.3
            
    pm = user['pity_mythic'] if user else 0
    ps = user['pity_super'] if user else 0

    all_cards = await fetch_all("SELECT * FROM cards WHERE drop_chance > 0 AND rarity NOT IN ('Leaderboard', 'Secret') AND is_cardball_exclusive = 0")
    if not all_cards: return []
    
    super_cards = [c for c in all_cards if c['rarity'] == 'Super']
    mythic_cards = [c for c in all_cards if c['rarity'] == 'Mythic']
    weights = [c['drop_chance'] * (total_luck if c['drop_chance'] < 15.0 else 1.0) for c in all_cards]
    
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
            ps = 0
            pm += 1
        elif card['rarity'] == 'Mythic': 
            pm = 0
            ps += 1
        else: 
            ps += 1
            pm += 1

        mut = roll_mutation()
        _, serial, _ = await give_card_to_user(user_id, card['id'], mut, card['rarity'])

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
                        top_users = await fetch_all("SELECT id, trophies as score FROM users WHERE id != ? ORDER BY trophies DESC LIMIT 20", (SUPER_ADMIN_ID,))
                    elif lb_type == 'coins':
                        top_users = await fetch_all("SELECT id, total_coins as score FROM users WHERE id != ? ORDER BY total_coins DESC LIMIT 20", (SUPER_ADMIN_ID,))
                    else:
                        top_users = await fetch_all("SELECT u.id, SUM(i.count) as score FROM users u JOIN inventory i ON u.id = i.user_id WHERE u.id != ? GROUP BY u.id ORDER BY score DESC LIMIT 20", (SUPER_ADMIN_ID,))

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
                                        mut_str = "💎" if r['mutation'] == 'Diamond' else ("🌈" if r['mutation'] == 'Rainbow' else ("⭐" if r['mutation'] == 'Gold' else ""))
                                        s_str = f" [#{serial:04d}]" if serial > 0 else ""
                                        reward_msgs_ru.append(f"🃏 {mut_str} {c_info['name']}{s_str}")
                                        
                            if rewards:
                                lb_name_ru = "Кубки (Сезон)" if lb_type == 'trophies' else ("Шекели" if lb_type == 'coins' else "Карты")
                                msg_text = f"🏆 <b>НАГРАДА ЗА ТОП ({lb_name_ru})!</b>\nВы заняли <b>{pos} место</b>!\n\n🎁 <b>Награда:</b>\n" + "\n".join([f"🔸 {m}" for m in reward_msgs_ru])
                                try: 
                                    await bot.send_message(user['id'], msg_text)
                                except: 
                                    pass
                
                await execute_db("UPDATE server_settings SET last_lb_reward = ? WHERE id = 1", (now,))
        except Exception as e:
            logging.error(f"LB Rewards error: {e}")
        await asyncio.sleep(600)

async def auto_backup_db():
    while True:
        await asyncio.sleep(4 * 3600) 
        try:
            file = FSInputFile(DB_NAME)
            await bot.send_document(SUPER_ADMIN_ID, file, caption="📦 Автоматический бэкап БД.")
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
    
    await log_user_action(message.from_user.id, "Открыл главное меню")
    adm = await is_admin(message.from_user.id)
    sgn = await is_signer(message.from_user.id)
    
    text = (
        "👋 <b>Добро пожаловать в Card Battle Bot!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Собери свою уникальную боевую колоду юнитов, участвуй в турнирах, настраивай крутые модификаторы боя и открывай Сид-Паки!\n\n"
        "📖 <b>ОГРОМНОЕ РУКОВОДСТВО ПО ИГРЕ:</b> /help\n"
        "📞 Тех.поддержка: @ggtdcards_support\n"
        "📧 Почта: ggtdcards@gmail.com\n\n"
        "🛍 Наш Донат-Магазин: /donate\n\n"
        "👇 <i>Используй кнопки снизу для навигации:</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard(adm, sgn))

@dp.message(Command("updatelog"))
async def cmd_updatelog(message: types.Message):
    if await check_ban(message.from_user.id): return
    text = f"📰 <b>ИСТОРИЯ ОБНОВЛЕНИЙ (Стр. 1/{len(UPDATE_LOGS)})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n{UPDATE_LOGS[0]}"
    await message.answer(text)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    if await check_ban(message.from_user.id): return
    guide = (
        "📖 <b>РУКОВОДСТВО ПО CARD BATTLE BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚔️ <b>ОСНОВНОЙ РЕЖИМ БОЯ (PvE и PvP)</b>\n"
        "• Собери боевую колоду из 4-х карт (VIP-игрокам доступен 5-й слот!).\n"
        "• В боях с ботами ты получаешь <b>Шекели 💰</b>, кубки и опыт БП.\n"
        "• Нажмите 🧬 <b>Модификаторы</b> прямо из главного меню, чтобы настроить баффы и дебаффы боя!\n\n"
        "💎 <b>РЕДКОСТИ И МУТАЦИИ КАРТ</b>\n"
        "• ⭐ <b>Золотая мутация</b> (+15% к характеристикам, шанс 15%)\n"
        "• 💎 <b>Алмазная мутация</b> (+30% к характеристикам, шанс 5%)\n"
        "• 🌈 <b>Радужная мутация</b> (+45% к характеристикам, шанс 0.9%)\n\n"
        "⚡ <b>СИСТЕМА ГАРАНТИЙ (PITY)</b>\n"
        "• Обычная гача: Мифик (каждые 1000 попыток), Супер (каждые 10000 попыток).\n"
        "• Создатели паков теперь могут настраивать Pity на конкретные карты из Сид-Паков!\n\n"
        "🔨 <b>МАСТЕРСКАЯ КРАФТА</b>\n"
        "• Сливай 8 одинаковых обычных карт (или всего 4 карты, если ты VIP), чтобы гарантированно повысить их мутацию на уровень выше!\n"
    )
    await message.answer(guide)

@dp.message(Command("profile"))
@dp.message(F.text == BTN_PROF)
async def cmd_profile(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    rank = await get_user_rank(user['trophies'])
    total_cards = await fetch_one("SELECT SUM(count) as s FROM inventory WHERE user_id = ?", (user['id'],))
    name = get_display_name(user)
    title_str = await get_user_titles_str(user['id'])
    
    active_bp = await fetch_one("""
        SELECT bp.title, ubp.level, ubp.xp 
        FROM user_bp ubp JOIN battle_passes bp ON ubp.bp_id = bp.id 
        WHERE ubp.user_id = ? AND ubp.is_active = 1
    """, (user['id'],))
    
    bp_text = "<i>Нет активного БП</i>"
    if active_bp:
        bp_text = f"<b>{active_bp['title']}</b> (Ур. {active_bp['level']} | {active_bp['xp']} XP)"

    text = (
        f"👤 Профиль игрока <b>{name}</b>{title_str}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎖 <b>Ранг:</b> {rank['name']}\n🏆 <b>Кубки:</b> {user['trophies']}\n"
        f"💰 <b>Шекели:</b> {user['coins']}\n💵 <b>Робуксы:</b> {user['robux']} R$\n"
        f"🃏 <b>Всего карт:</b> {total_cards['s'] or 0}\n🎟 <b>Активный БП:</b> {bp_text}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔮 <b>Гарант на Мифик:</b> {make_progress_bar(user['pity_mythic'], 1000, 8)} ({user['pity_mythic']}/1000)\n"
        f"🌠 <b>Гарант на Супер:</b> {make_progress_bar(user['pity_super'], 10000, 8)} ({user['pity_super']}/10000)\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    text += "⚔️ <b>Боевая колода:</b>\n"
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user['gp_fifth_slot'] == 1 or user['gp_vip'] == 1:
        slots.append('equip5')
        
    for i, slot in enumerate(slots, 1):
        inv_id = user[slot]
        if inv_id != 0:
            row = await fetch_one("""
                SELECT c.id, c.name, c.rarity, c.class_type, c.damage, c.hp, c.booster_dmg_mult, c.booster_hp_mult,
                       i.mutation, i.serial_number, i.signed_by
                FROM inventory i JOIN cards c ON i.card_id = c.id
                WHERE i.id = ? AND i.user_id = ? AND i.count > 0
            """, (inv_id, user['id']))
            
            if row:
                mult = get_mutation_multiplier(row['mutation'])
                mut_str = " 💎" if row['mutation'] == 'Diamond' else (" 🌈" if row['mutation'] == "Rainbow" else (" ⭐" if row['mutation'] == 'Gold' else ""))
                c_dict = dict(row)
                if row['signed_by'] > 0:
                    signer = await fetch_one("SELECT username, first_name FROM users WHERE id = ?", (row['signed_by'],))
                    if signer: c_dict['signer_name'] = get_display_name(signer)
                
                n = format_card_name(c_dict)
                if row['class_type'] == 'Booster': 
                    text += f" {i}️⃣ {n}{mut_str}\n      └ <i>Бафф: DMG x{round(row['booster_dmg_mult']*mult, 2)} | HP x{round(row['booster_hp_mult']*mult, 2)}</i>\n"
                elif row['class_type'] == 'Healer':
                    text += f" {i}️⃣ {n}{mut_str}\n      └ <i>Статы: 💗 Лечение: {int(row['damage']*mult)} | ❤️ Здоровье: {int(row['hp']*mult)}</i>\n"
                else: 
                    text += f" {i}️⃣ {n}{mut_str}\n      └ <i>Статы: ⚔️ Урон: {int(row['damage']*mult)} | ❤️ Здоровье: {int(row['hp']*mult)}</i>\n"
            else:
                await execute_db(f"UPDATE users SET {slot} = 0 WHERE id = ?", (user['id'],))
                text += f" {i}️⃣ [Слот Пуст]\n"
        else:
            text += f" {i}️⃣ [Слот Пуст]\n"
            
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
        "<i>Выполни все 3 задания за час, чтобы получить 1500 💰 Шекелей и 1 Сид-Пак!</i>\n"
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
        top_users = await fetch_all("SELECT u.id, u.username, u.first_name, SUM(i.count) as score FROM users u JOIN inventory i ON u.id = i.user_id WHERE u.id != ? GROUP BY u.id ORDER BY score DESC LIMIT 20", (SUPER_ADMIN_ID,))
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
                    mut = "💎" if r['mutation'] == 'Diamond' else ("🌈" if r['mutation'] == 'Rainbow' else ("⭐" if r['mutation'] == 'Gold' else ""))
                    r_strs.append(f"{mut} {c['name'] if c else 'Unknown'}")
            text += f"└ {b_names[b]}: {', '.join(r_strs)}\n"
            
    if not has_rewards: 
        text += "<i>Награды пока не настроены.</i>"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К выбору", callback_data="top_menu")]])
    try: 
        await callback.message.edit_text(text, reply_markup=kb)
    except: 
        pass
    await callback.answer()

@dp.callback_query(F.data == "top_menu")
async def cb_top_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Кубки (Сезон)", callback_data="top_trophies")],
        [InlineKeyboardButton(text="💰 Монеты (Все время)", callback_data="top_coins")],
        [InlineKeyboardButton(text="🃏 Карты (Все время)", callback_data="top_cards")]
    ])
    try: 
        await callback.message.edit_text("🏆 <b>МИРОВЫЕ РЕЙТИНГИ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите категорию лидерборда:", reply_markup=kb)
    except: 
        pass
    await callback.answer()

@dp.message(Command("shop"))
@dp.message(F.text == BTN_SHOP)
async def cmd_shop(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT coins, gp_vip FROM users WHERE id = ?", (message.from_user.id,))
    items = await fetch_all("SELECT * FROM shop_items WHERE stock > 0")
    
    if not items:
        return await message.answer("🛒 <b>Магазин пока пуст.</b>\nЗавоз осуществляется каждые полтора часа. Жди уведомления!")
        
    discount = 0.9 if (user and user['gp_vip'] == 1) else 1.0
    text = f"🛒 <b>ГЛОБАЛЬНЫЙ МАГАЗИН</b>\n💰 Твой баланс: <b>{user['coins']} Шекелей</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    kb = []
    for i, item in enumerate(items, 1):
        price = int(item['price'] * discount)
        text += f"📦 <b>{item['name']}</b>\n      └ 💵 Цена: <b>{price} 💰</b> | Остаток: <b>{item['stock']} шт.</b>\n\n"
        kb.append([InlineKeyboardButton(text=f"Купить: {item['name']} ({price} 💰)", callback_data=f"buy_shop_{item['id']}")])
        
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("buy_shop_"))
async def callback_buy_shop(callback: types.CallbackQuery):
    shop_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    user = await fetch_one("SELECT coins, gp_vip, pity_mythic, pity_super FROM users WHERE id = ?", (user_id,))
    item = await fetch_one("SELECT * FROM shop_items WHERE id = ?", (shop_id,))
    
    if not item or item['stock'] <= 0: 
        return await callback.answer("❌ Этот товар закончился!", show_alert=True)
    
    discount = 0.9 if (user and user['gp_vip'] == 1) else 1.0
    price = int(item['price'] * discount)
    
    if user['coins'] < price: 
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)
    
    await execute_db("UPDATE users SET coins = coins - ? WHERE id = ?", (price, user_id))
    await execute_db("UPDATE shop_items SET stock = stock - 1 WHERE id = ?", (shop_id,))
    
    await add_quest_progress_new(user_id, 'q_shop_buy', 1)
    
    i_type = item['item_type']
    if i_type.endswith("_rnd"):
        count = int(i_type.split("_")[0])
        won = await give_multiple_cards(user_id, count)
        
        await add_quest_progress_new(user_id, 'q_open', count)
        pity_pulls = [c for c in won if c.get('is_pity')]
        
        if count == 1: 
            mut_str = "💎 " if won[0]['mutation'] == 'Diamond' else ("🌈 " if won[0]['mutation'] == 'Rainbow' else ("⭐ " if won[0]['mutation'] == 'Gold' else ""))
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
        
        query = "SELECT * FROM cards WHERE rarity = ? AND is_cardball_exclusive = 0"
        all_cards = await fetch_all(query, (target_rarity,))
        if not all_cards:
            await execute_db("UPDATE users SET coins = coins + ? WHERE id = ?", (price, user_id))
            return await callback.message.answer("❌ Ошибка БД.")
            
        won_card = random.choice(all_cards)
        mut = roll_mutation()
        _, serial, _ = await give_card_to_user(user_id, won_card['id'], mut, won_card['rarity'])
        won_card['serial_number'] = serial
        won_card['signed_by'] = 0
        
        await add_quest_progress_new(user_id, 'q_open', 1)
            
        pm = user['pity_mythic']
        ps = user['pity_super']
        if target_rarity == 'Super': 
            ps = 0
            pm += 1
        elif target_rarity == 'Mythic': 
            pm = 0
            ps += 1
        else: 
            ps += 1
            pm += 1
        await execute_db("UPDATE users SET pity_mythic=?, pity_super=? WHERE id=?", (pm, ps, user_id))
        
        mut_str = "💎 Алмазная" if mut == 'Diamond' else ("🌈 Радужная" if mut == 'Rainbow' else ("⭐ Золотая" if mut == 'Gold' else "Обычная"))
        await callback.message.answer(f"✨ <b>Успешная покупка ГАРАНТА!</b>\nВы выбили: {format_card_name(won_card)}\nМутация: <b>{mut_str}</b>")

    await log_user_action(user_id, f"Купил в магазине: {i_type} ({price} шекелей)")

    items = await fetch_all("SELECT * FROM shop_items WHERE stock > 0")
    if not items:
        await callback.message.edit_text("🛒 <b>Магазин полностью распродан!</b>\nЖдите следующего завоза.")
    else:
        new_val = user['coins'] - price
        text = f"🛒 <b>ГЛОБАЛЬНЫЙ МАГАЗИН</b>\n💰 Твой баланс: <b>{new_val} Шекелей</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        kb = []
        for i, itm in enumerate(items, 1):
            cur_price = int(itm['price'] * discount)
            text += f"📦 <b>{itm['name']}</b>\n      └ 💵 Цена: <b>{cur_price} 💰</b> | Остаток: <b>{itm['stock']} шт.</b>\n\n"
            kb.append([InlineKeyboardButton(text=f"Купить: {itm['name']} ({cur_price} 💰)", callback_data=f"buy_shop_{itm['id']}")])
        try: 
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except: 
            pass
    
    await callback.answer()


@dp.message(Command("getcard"))
@dp.message(F.text == BTN_DRAW)
async def cmd_getcard(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    if user['id'] in user_trades: 
        return await message.answer("❌ Завершите обмен перед выбиванием!")
    
    luck_mult, cd_mult = await get_active_events()
    
    # VIP cooldown reductions
    actual_cooldown = int(3 * 60 / cd_mult)
    if user.get('gp_vip') == 1:
        actual_cooldown = int(actual_cooldown * 0.7) 
        
    now = time.time()
    passed = now - user['last_getcard']
    
    if passed < actual_cooldown:
        left = int(actual_cooldown - passed)
        mins, secs = divmod(left, 60)
        return await message.answer(f"⏳ <b>Колода перемешивается!</b>\nОжидай: <b>{mins} мин. {secs} сек.</b>")
        
    won_list = await give_multiple_cards(user['id'], 1)
    if not won_list: 
        return await message.answer("😔 В базе нет карт для этой гачи.")
    won_card = won_list[0]
        
    await execute_db("UPDATE users SET last_getcard = ? WHERE id = ?", (now, user['id']))
    await add_quest_progress_new(user['id'], 'q_open', 1)
    await log_user_action(user['id'], f"Выбил карту: {won_card['name']} (ID:{won_card['id']}, Мутация: {won_card['mutation']})")
    
    n_fmt = format_card_name(won_card)
    rarity_text = format_rarity_display(won_card['rarity'])
    
    mutation = won_card['mutation']
    mult = get_mutation_multiplier(mutation)
    mut_str = ""
    if mutation == "Gold": 
        mut_str = "⭐ <b>ЗОЛОТАЯ МУТАЦИЯ! (+15% Статов)</b>\n"
    elif mutation == "Diamond": 
        mut_str = "💎 <b>АЛМАЗНАЯ МУТАЦИЯ! (+30% Статов)</b>\n"
    elif mutation == "Rainbow": 
        mut_str = "🌈 <b>РАДУЖНАЯ МУТАЦИЯ! (+45% Статов)</b>\n"
    
    msg = ""
    if won_card.get('is_pity'):
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
    
    luck_mult, _ = await get_active_events()
    weights_dict, total_w = await calculate_chance_weights(luck_mult)
    
    pack_cards = await fetch_all("""
        SELECT spc.card_id, spc.drop_chance as pack_chance, sp.title
        FROM seed_pack_cards spc JOIN seed_packs sp ON spc.pack_id = sp.id
    """)
    pack_info = {pc['card_id']: pc for pc in pack_cards}
    pack_totals = {}
    for pc in pack_cards:
        w = pc['pack_chance']
        if w < 15.0: 
            w *= luck_mult
        pack_totals[pc['title']] = pack_totals.get(pc['title'], 0) + w
    
    def index_sort_key(c):
        if c['rarity'] == 'Leaderboard': 
            return (999, c['id'])
        rw = RARITY_WEIGHT.get(c['rarity'], 0)
        return (rw, c['id'])
        
    all_cards.sort(key=index_sort_key, reverse=True)
    total_pages = max(1, math.ceil(len(all_cards) / items_per_page))
    page = max(0, min(page, total_pages - 1))
    
    text = f"📖 <b>ОСНОВНОЙ ИНДЕКС КАРТ (Стр. {page+1}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if luck_mult > 1.0: 
        text += f"🍀 <b>ИВЕНТ УДАЧИ АКТИВЕН (x{luck_mult})! Шансы пересчитаны!</b>\n\n"
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = all_cards[start_idx:end_idx]
    
    for i, c in enumerate(page_items, start_idx + 1):
        inv_stats = await fetch_all("SELECT mutation, SUM(count) as c FROM inventory WHERE card_id = ? AND user_id != ? GROUP BY mutation", (c['id'], SUPER_ADMIN_ID))
        total_exists = sum(item['c'] for item in inv_stats if item['c'])
        
        mut_texts = []
        for st in inv_stats:
            if st['mutation'] == 'Gold' and st['c'] > 0: 
                mut_texts.append(f"⭐ Золотых: {st['c']}")
            if st['mutation'] == 'Diamond' and st['c'] > 0: 
                mut_texts.append(f"💎 Алмазных: {st['c']}")
            if st['mutation'] == 'Rainbow' and st['c'] > 0: 
                mut_texts.append(f"🌈 Радужных: {st['c']}")
            
        mut_str = f"\n      └ <i>Из них: {', '.join(mut_texts)}</i>" if mut_texts else ""
        
        n_fmt = format_card_name(c)
        if c['id'] in crafted_ids: 
            n_fmt += " [🛠 Крафт]"
        r_fmt = format_rarity_display(c['rarity'])
        
        if c['id'] in pack_info:
            p_info = pack_info[c['id']]
            p_title = p_info['title']
            p_weight = p_info['pack_chance']
            if p_weight < 15.0: 
                p_weight *= luck_mult
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
    if page > 0: 
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"idx_page_{page-1}"))
    if total_pages > 1: 
        nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: 
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"idx_page_{page+1}"))
    if nav_row: 
        kb.append(nav_row)
    
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
        WHERE i.user_id = ? AND i.count > 0
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
        n_fmt = format_card_name(item)
        mut_emoji = ""
        if item['mutation'] == "Gold": 
            mut_emoji = "⭐ "
        elif item['mutation'] == "Diamond": 
            mut_emoji = "💎 "
        elif item['mutation'] == "Rainbow": 
            mut_emoji = "🌈 "
        text += f"• {mut_emoji}{n_fmt} — <b>{item['count']} шт.</b>\n"
        
    kb = [toggle_row]
    nav_row = []
    if page > 0: 
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"inv_page_{page-1}"))
    if total_pages > 1: 
        nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: 
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"inv_page_{page+1}"))
    if nav_row: 
        kb.append(nav_row)
    
    return text, InlineKeyboardMarkup(inline_keyboard=kb) if kb else None

@dp.message(Command("inventory"))
@dp.message(F.text == BTN_INV)
async def cmd_inventory(message: types.Message):
    if await check_ban(message.from_user.id): return
    text, kb = await get_inventory_text_and_kb(message.from_user.id, 0)
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("inv_page_"))
async def callback_inventory_page(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    text, kb = await get_inventory_text_and_kb(callback.from_user.id, page)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.message(F.text == BTN_SIGN)
async def cmd_sign_card(message: types.Message):
    if await check_ban(message.from_user.id): return
    if not await is_signer(message.from_user.id): return
    if message.from_user.id in user_trades: 
        return await message.answer("❌ Завершите обмен перед подписыванием карт!")
    
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0 AND i.signed_by = 0
    """, (message.from_user.id,))
    
    if not inv: return await message.answer("❌ Нет карт для подписи.")
    
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = []
    for c in inv:
        mut_emoji = "⭐ " if c['mutation'] == 'Gold' else ("💎 " if c['mutation'] == 'Diamond' else ("🌈 " if c['mutation'] == 'Rainbow' else ""))
        items.append({"id": c['inv_id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {mut_emoji}{c['name']} x{c['count']}"})
        
    kb = get_pagination_keyboard(items, 0, "sgn_c", columns=1, items_per_page=8)
    await message.answer("✍️ <b>ВЫБОР КАРТЫ ДЛЯ ПОДПИСИ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите карту:", reply_markup=kb)

@dp.callback_query(F.data.startswith("sgn_c_page_"))
async def cb_sign_card_paginate(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[3])
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0 AND i.signed_by = 0
    """, (callback.from_user.id,))
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = []
    for c in inv:
        mut_emoji = "⭐ " if c['mutation'] == 'Gold' else ("💎 " if c['mutation'] == 'Diamond' else ("🌈 " if c['mutation'] == 'Rainbow' else ""))
        items.append({"id": c['inv_id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {mut_emoji}{c['name']} x{c['count']}"})
        
    kb = get_pagination_keyboard(items, page, "sgn_c", columns=1, items_per_page=8)
    try: 
        await callback.message.edit_reply_markup(reply_markup=kb)
    except: 
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("sgn_c_"))
async def cb_sign_card_select(callback: types.CallbackQuery):
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if not await is_signer(user_id): 
        return await callback.answer("Нет прав!", show_alert=True)
    
    db = await get_db_connection()
    try:
        cur = await db.execute("SELECT card_id, count, mutation, serial_number, signed_by FROM inventory WHERE id = ? AND user_id = ?", (inv_id, user_id))
        row = await cur.fetchone()
        if not row or row['count'] < 1: 
            return await callback.answer("Не найдено!", show_alert=True)
        if row['signed_by'] != 0: 
            return await callback.answer("Уже подписано!", show_alert=True)
        
        await db.execute("BEGIN TRANSACTION")
        if row['count'] == 1:
            await db.execute("DELETE FROM inventory WHERE id = ?", (inv_id,))
            for s in ['equip1', 'equip2', 'equip3', 'equip4', 'equip5']:
                await db.execute(f"UPDATE users SET {s} = 0 WHERE {s} = ?", (inv_id,))
        else:
            await db.execute("UPDATE inventory SET count = count - 1 WHERE id = ?", (inv_id,))
            
        cur2 = await db.execute("""
            SELECT id FROM inventory 
            WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = ? AND signed_by = ?
        """, (user_id, row['card_id'], row['mutation'], row['serial_number'], user_id))
        dest = await cur2.fetchone()
        
        if dest:
            await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (dest['id'],))
        else:
            await db.execute("""
                INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by)
                VALUES (?, ?, 1, ?, ?, ?)
            """, (user_id, row['card_id'], row['mutation'], row['serial_number'], user_id))
            
        await db.commit()
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Sign error: {e}")
        return await callback.answer("Ошибка подписи.", show_alert=True)
    finally:
        await db.close()
        
    await callback.message.delete()
    await callback.message.answer("✍️✅ <b>Успешно подписано вашим именем!</b>")
    await callback.answer()


def get_equip_main_keyboard(user_info, cards_info):
    kb = []
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user_info.get('gp_fifth_slot', 0) == 1 or user_info.get('gp_vip', 0) == 1:
        slots.append('equip5')
        
    for i, slot in enumerate(slots, 1):
        inv_id = user_info[slot]
        text = f"Слот {i}: [Пусто]" if inv_id == 0 else f"Слот {i}: {cards_info.get(inv_id, f'ID: {inv_id}')}"
        kb.append([InlineKeyboardButton(text=text, callback_data=f"eq_select_{i}")])
    kb.append([InlineKeyboardButton(text="❌ Очистить колоду", callback_data="eq_clear_all")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("equip"))
@dp.message(F.text == BTN_EQ)
async def cmd_equip(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    if message.from_user.id in user_trades: 
        return await message.answer("❌ Завершите обмен перед экипировкой!")
    
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user.get('gp_fifth_slot', 0) == 1 or user.get('gp_vip', 0) == 1:
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
            mut_str = "⭐" if r['mutation'] == 'Gold' else ("💎" if r['mutation'] == 'Diamond' else ("🌈" if r['mutation'] == 'Rainbow' else ""))
            ser_str = f" [#{r['serial_number']:04d}]" if r['serial_number'] > 0 else ""
            cards_info[r['id']] = f"{mut_str}{r['name']}{ser_str}".strip()
            
    await message.answer("🛡 <b>БОЕВАЯ КОЛОДА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите слот для настройки:", reply_markup=get_equip_main_keyboard(user, cards_info))

@dp.callback_query(F.data == "eq_clear_all")
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
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0
    """, (callback.from_user.id,))
    
    if not inv: return await callback.answer("У вас нет карт в инвентаре!", show_alert=True)
    
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {c['name']}"} for c in inv]
    
    await state.update_data(equip_slot=slot_num, equip_items_cards=items)
    kb = get_pagination_keyboard(items, 0, "eq_c", columns=1, items_per_page=8)
    
    await callback.message.edit_text(f"👇 Выберите карту для <b>Слота {slot_num}</b>:", reply_markup=kb)
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
        WHERE i.user_id = ? AND i.card_id = ? AND i.count > 0
    """, (callback.from_user.id, card_id))
    
    if not invs: return await callback.answer("Карта отсутствует!", show_alert=True)
    
    items = []
    for i in invs:
        c_dict = dict(i)
        if i['signed_by'] > 0:
            c_dict['signer_name'] = get_display_name({'username': i['username'], 'first_name': i['first_name']})
        
        name_str = format_card_name_plain(c_dict)
        mut = "⭐ " if i['mutation'] == 'Gold' else ("💎 " if i['mutation'] == 'Diamond' else ("🌈 " if i['mutation'] == 'Rainbow' else ""))
        items.append({"id": i['inv_id'], "btn_text": f"{mut}{name_str} (x{i['count']})"})
        
    await state.update_data(equip_items_vars=items)
    kb = get_pagination_keyboard(items, 0, "eq_v", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"eq_select_{slot_num}")])
    
    await callback.message.edit_text(f"👇 Выберите конкретную копию для <b>Слота {slot_num}</b>:", reply_markup=kb)
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
    if user['gp_fifth_slot'] == 1 or user['gp_vip'] == 1:
        slots.append('equip5')
        
    current_eq = [user[s] for s in slots]
    
    if inv_id in current_eq:
        return await callback.answer("❌ Эта копия уже экипирована!", show_alert=True)
        
    card_info = await fetch_one("SELECT card_id FROM inventory WHERE id = ?", (inv_id,))
    if not card_info: return await callback.answer("Ошибка")
    
    if user[slots[slot_num-1]] in current_eq:
        current_eq.remove(user[slots[slot_num-1]])
    
    if any(i != 0 for i in current_eq):
        inv_list = ",".join(map(str, [i for i in current_eq if i != 0]))
        other_cards = await fetch_all(f"SELECT card_id FROM inventory WHERE id IN ({inv_list})")
        if any(c['card_id'] == card_info['card_id'] for c in other_cards):
            return await callback.answer("❌ Нельзя экипировать две одинаковые карты!", show_alert=True)

    await execute_db(f"UPDATE users SET {slots[slot_num-1]} = ? WHERE id = ?", (inv_id, callback.from_user.id))
    await callback.message.edit_text(f"✅ Установлено в Слот {slot_num}!")
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
    if not bp: return await callback.answer("Не найдено!", show_alert=True)
    
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
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="bp_list_0")])
    
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
    try: 
        await callback.message.edit_text("🎟 <b>БАТЛ-ПАССЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await callback.message.answer("🎟 <b>БАТЛ-ПАССЫ</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.startswith("bp_set_act_"))
async def callback_bp_set_active(callback: types.CallbackQuery):
    bp_id = int(callback.data.split("_")[3])
    user_id = callback.from_user.id
    
    await execute_db("UPDATE user_bp SET is_active = 0 WHERE user_id = ?", (user_id,))
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
    if not lvl_data: return await callback.answer("Уровень не найден", show_alert=True)
        
    rewards = await fetch_all("SELECT * FROM bp_rewards WHERE level_id = ?", (lvl_data['id'],))
    
    text = (
        f"🏆 <b>{bp['title']} | Уровень {req_level}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Требуется XP: {lvl_data['xp_required']}</i>\n\n🎁 <b>Награды:</b>\n"
    )
    
    if not rewards:
        text += "└ <i>Наград нет.</i>\n"
    else:
        for r in rewards:
            if r['reward_type'] == 'shekels':
                text += f"└ 💰 <b>{r['amount']} Шекелей</b>\n"
            elif r['reward_type'] == 'card':
                c = await fetch_one("SELECT name FROM cards WHERE id = ?", (r['card_id'],))
                n = c['name'] if c else "Unknown"
                mut = "💎" if r['mutation'] == 'Diamond' else ("🌈" if r['mutation'] == 'Rainbow' else ("⭐" if r['mutation'] == 'Gold' else ""))
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
        kb.append([InlineKeyboardButton(text="🎁 ЗАБРАТЬ НАГРАДУ", callback_data=f"bp_claim_{bp_id}_{req_level}")])
        
    nav_row = []
    max_lvl = await fetch_one("SELECT MAX(level) as m FROM bp_levels WHERE bp_id = ?", (bp_id,))
    max_l = max_lvl['m'] if max_lvl and max_lvl['m'] else 1
    
    if req_level > 1: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"bp_lvl_{bp_id}_{req_level-1}"))
    if req_level < max_l: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"bp_lvl_{bp_id}_{req_level+1}"))
    if nav_row: kb.append(nav_row)
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"bp_view_{bp_id}")])
    
    try: 
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
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
    if not user_bp or user_bp['level'] < req_level: 
        return await callback.answer("Заблокировано", show_alert=True)
        
    claim_check = await fetch_one("SELECT * FROM user_bp_claims WHERE user_id = ? AND bp_id = ? AND level = ?", (user_id, bp_id, req_level))
    if claim_check: 
        return await callback.answer("Уже получено!", show_alert=True)
        
    lvl_data = await fetch_one("SELECT id FROM bp_levels WHERE bp_id = ? AND level = ?", (bp_id, req_level))
    rewards = await fetch_all("SELECT * FROM bp_rewards WHERE level_id = ?", (lvl_data['id'],))
    
    db = await get_db_connection()
    try:
        await db.execute("BEGIN TRANSACTION")
        for r in rewards:
            if r['reward_type'] == 'shekels':
                await db.execute("UPDATE users SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (r['amount'], r['amount'], user_id))
            elif r['reward_type'] == 'card':
                res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0", (user_id, r['card_id'], r['mutation']))
                inv_item = await res.fetchone()
                if inv_item:
                    await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                else:
                    await db.execute("INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by) VALUES (?, ?, 1, ?, 0, 0)", (user_id, r['card_id'], r['mutation']))
        
        await db.execute("INSERT INTO user_bp_claims (user_id, bp_id, level) VALUES (?, ?, ?)", (user_id, bp_id, req_level))
        await db.commit()
    finally:
        await db.close()
        
    await callback.answer("🎉 Награды получены!", show_alert=True)
    await callback_bp_level(callback)


async def get_team_data(user_id: int):
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    team = []
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user['gp_fifth_slot'] == 1 or user['gp_vip'] == 1:
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
            rainbow_prob = min(0.02, 0.01 * difficulty_mult) 
            diamond_prob = min(0.05, 0.02 * difficulty_mult)
            gold_prob = min(0.12, 0.05 * difficulty_mult)     
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
        team_copies.append(c_copy)
        
    return team_copies

def format_combat_team_vertical(team):
    if not team: return "<i>Все повержены</i>"
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
        f"⚔️ <b>АРЕНА: БИТВА</b> ⚔️\n━━━━━━━━━━━━━━━━━━━━━━━━\n🔵 <b>Команда {p1_name}:</b>\n{format_combat_team_vertical(t1)}\n\n🔴 <b>Команда {p2_name}:</b>\n{format_combat_team_vertical(t2)}\n━━━━━━━━━━━━━━━━━━━━━━━━\n📜 <b>Лог боя:</b>\n"
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
                ru_str += " ☠️ <i>Сгорел!</i>"
            add_dual_log(log1, log2, ru_str)
            c['burn'] = 0

async def execute_turn(atk_team, def_team, atk_name, def_name, log1, log2, force_attacker=None, force_target=None, mods=None):
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
    
    # MODIFIER: No Heals (Debuff)
    if mods and mods.get('mod_no_heals') == 1 and c_type == "Healer":
        # Healers cannot heal; they deal 20% of their heal power as damage
        c_type = "Single"
        base_dmg = max(5, int(base_dmg * 0.2))
        
    dead_ru = " ☠️ <i>Повержен!</i>"
    
    if c_type == "Booster":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
        
        dmg = max(10, int(target['max_hp'] * 0.1))
        target['hp'] -= dmg
        ru_str = f"🔋 {atk_name}: <b>{html.escape(atk['name'])}</b> разряжает батарею в <b>{html.escape(target['name'])}</b> на {dmg}!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
    elif c_type == "Healer":
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
            target['hp'] -= dmg
            ru_str = f"🎯 {atk_name}: Одинокий Хилер <b>{html.escape(atk['name'])}</b> наносит <b>{html.escape(target['name'])}</b> {dmg} урона!"
            if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
            add_dual_log(log1, log2, ru_str)
        
    elif c_type == "AOE":
        ru_str = f"🌪 {atk_name}: <b>{html.escape(atk['name'])}</b> вызывает ураган на {base_dmg} по всем!"
        for d in def_alive:
            d['hp'] -= base_dmg
            if d['hp'] <= 0:
                d['hp'] = 0
                ru_str += f" ☠️ <i>{html.escape(d['name'])} повержен!</i>"
        add_dual_log(log1, log2, ru_str)
        
    elif c_type == "Splash":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: main_t = force_target
        else: main_t = random.choice(def_alive)
            
        splash_dmg = int(base_dmg * 0.5)
        ru_str = f"🌊 {atk_name}: <b>{html.escape(atk['name'])}</b> наносит {base_dmg} по <b>{html.escape(main_t['name'])}</b> и {splash_dmg} брызгами по остальным!"
        for d in def_alive:
            dmg = base_dmg if d == main_t else splash_dmg
            d['hp'] -= dmg
            if d['hp'] <= 0:
                d['hp'] = 0
                ru_str += f" ☠️ <i>{html.escape(d['name'])} повержен!</i>"
        add_dual_log(log1, log2, ru_str)
        
    elif c_type == "Fire":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
            
        target['hp'] -= base_dmg
        target['burn'] = target.get('burn', 0) + base_dmg
        ru_str = f"🔥 {atk_name}: <b>{html.escape(atk['name'])}</b> поджигает <b>{html.escape(target['name'])}</b> на {base_dmg}!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
    else:
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
            
        target['hp'] -= base_dmg
        ru_str = f"🎯 {atk_name}: <b>{html.escape(atk['name'])}</b> наносит {base_dmg} урона по <b>{html.escape(target['name'])}</b>!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
    # MODIFIER: Player Vampirism (Buff)
    if mods and mods.get('mod_player_vamp') == 1 and atk in atk_team:
        heal_vamp = int(base_dmg * 0.25)
        atk['hp'] = min(atk['max_hp'], atk['hp'] + heal_vamp)
        add_dual_log(log1, log2, f"🩸 <b>Вампиризм:</b> {html.escape(atk['name'])} исцеляет себя на {heal_vamp} за счет нанесенного урона!")

    return True, heals

async def get_dynamic_trophies(rank_name: str, rank_idx: int, diff_scale: float = 1.0) -> int:
    """
    Рассчитывает получение кубков.
    Уран 6 и 7 стали слегка легче (больше базовых кубков).
    """
    if "Uranium VI" in rank_name or "Uranium VII" in rank_name:
        return random.randint(3, 7)
    base = max(5, 18 - int((rank_idx / 25) * 12)) 
    won = random.randint(base, base+3)
    return int(won * diff_scale)

async def add_bp_xp(user_id: int, xp_to_add: int) -> tuple:
    user_settings = await fetch_one("SELECT gp_double_xp, gp_vip FROM users WHERE id=?", (user_id,))
    xp_mult = 1.0
    if user_settings:
        if user_settings['gp_double_xp'] == 1: 
            xp_mult *= 2.0
        if user_settings['gp_vip'] == 1: 
            xp_mult *= 1.5
            
    final_xp = int(xp_to_add * xp_mult)
    
    db = await get_db_connection()
    try:
        user_bp = await db.execute("""
            SELECT ubp.bp_id, ubp.level, ubp.xp 
            FROM user_bp ubp JOIN battle_passes bp ON ubp.bp_id = bp.id
            WHERE ubp.user_id = ? AND ubp.is_active = 1
        """, (user_id,))
        ubp = await user_bp.fetchone()
        if not ubp: return False, None, 0
        
        bp_id = ubp['bp_id']
        curr_lvl = ubp['level']
        curr_xp = ubp['xp'] + final_xp
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
        try: 
            await msg.delete()
        except: 
            pass

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
    try: 
        await callback.message.edit_text(f"Выбран: <b>{atk['name']}</b>\nВыберите цель:", reply_markup=kb)
    except: 
        pass
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
        did_turn, heals = await execute_turn(t1, t2, p1_name, p2_name, log, None, force_attacker=atk, force_target=tgt, mods=mods)
    else:
        did_turn, heals = await execute_turn(t1, t2, p1_name, p2_name, log, None, mods=mods)
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
        
        # MODIFIER: Player Shield (Buff)
        if mods and mods.get('mod_player_shield') == 1:
            for c in t1:
                shield_val = int(c['max_hp'] * 0.3)
                c['hp'] += shield_val
                c['max_hp'] += shield_val
            log.append("🛡 <b>Щит:</b> Ваши юниты получили дополнительный щит на 30% HP!")

        # MODIFIER: Enemy Burn (Buff/Debuff Helper)
        if mods and mods.get('mod_enemy_burn') == 1:
            for c in t2:
                c['burn'] = int(c['max_hp'] * 0.05)
            log.append("🔥 <b>Горение ИИ:</b> Команда противника охвачена пламенем!")

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
                winner = p2_name
                winner_id = p2_id
                loser_id = p1_id
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
                    if "not found" in str(e).lower() or "deleted" in str(e).lower(): 
                        timeout_flag = True
                        break
                await battle_delay(battle_id, p1_id, p2_id)
                
                t2_alive = [c for c in t2 if c['hp'] > 0]
                if t2_alive and mods and mods.get('mod_player_atk_all') and not is_pvp:
                    did_turn_extra, heals_extra = await do_player_turn_wrapper(chat_id, p1_id, p1_name, p2_name, t1, t2, log, mods, is_pvp)
                    p1_total_heals += heals_extra
                    if did_turn_extra:
                        if len(log) > 6: log = log[-6:]
                        try: 
                            await safe_edit_text(msg, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log), reply_markup=get_battle_kb(battle_id))
                        except: 
                            pass
                        await battle_delay(battle_id, p1_id, p2_id)

            t2_alive = [c for c in t2 if c['hp'] > 0]
            if t2_alive:
                if time.time() - battle_start_time > 180:
                    timeout_flag = True
                    break

                did_turn_e, heals_e = await execute_turn(t2, t1, p2_name, p1_name, log, None, mods=mods)
                p2_total_heals += heals_e
                if did_turn_e:
                    if len(log) > 6: log = log[-6:]
                    try: 
                        await safe_edit_text(msg, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log), reply_markup=get_battle_kb(battle_id))
                    except Exception as e:
                        if "not found" in str(e).lower() or "deleted" in str(e).lower(): 
                            timeout_flag = True
                            break
                    await battle_delay(battle_id, p1_id, p2_id)
                    
                t1_alive_check = [c for c in t1 if c['hp'] > 0]
                if t1_alive_check and mods and mods.get('mod_enemy_atk_all') and not is_pvp:
                    did_turn_e_extra, heals_e_extra = await execute_turn(t2, t1, p2_name, p1_name, log, None, mods=mods)
                    p2_total_heals += heals_e_extra
                    if did_turn_e_extra:
                        if len(log) > 6: log = log[-6:]
                        try: 
                            await safe_edit_text(msg, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log), reply_markup=get_battle_kb(battle_id))
                        except: 
                            pass
                        await battle_delay(battle_id, p1_id, p2_id)
            turn += 1

        if timeout_flag:
            try: await msg.edit_text("⏳ <b>Бой прерван по техническим причинам.</b>")
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

            # DROP AN ADMIN-GENERATED REWARD CODE INSTEAD OF STRANGE ONES
            if winner_user_id is not None and "Ничья" not in winner:
                if random.random() <= 0.05:
                    db = await get_db_connection()
                    try:
                        # Find code created by admin that is active and doesn't have an owner
                        cursor = await db.execute("SELECT code FROM reward_codes WHERE is_active = 1 AND owner_id = 0 LIMIT 1")
                        row = await cursor.fetchone()
                        if row:
                            code = row['code']
                            await db.execute("UPDATE reward_codes SET owner_id = ? WHERE code = ?", (winner_user_id, code))
                            await db.commit()
                            code_text = f"🎁 <b>ВЫПАЛ УНИКАЛЬНЫЙ КОД-НАГРАДА! (Шанс 5%)</b>\nНажми, чтобы скопировать: <code>{code}</code>\nАктивируй через /codereward\n\n"
                    except Exception as e:
                        logging.error(f"Error dropping reward code: {e}")
                    finally:
                        await db.close()

            # ROBUX drop chance on battle wins (STRICT UNBUFFABLE)
            robux_drop_text = ""
            if winner_user_id == p1_id and not is_pvp:
                robux_chance = 0.0
                robux_amount = 0
                if diff_type == "easy":
                    robux_chance = 0.05
                    robux_amount = 1
                elif diff_type == "med":
                    robux_chance = 0.10
                    robux_amount = 1
                elif diff_type == "hard":
                    robux_chance = 0.20
                    robux_amount = 2
                elif diff_type == "nightmare":
                    robux_chance = 0.20
                    robux_amount = 3
                    
                if random.random() <= robux_chance:
                    await execute_db("UPDATE users SET robux = robux + ? WHERE id = ?", (robux_amount, p1_id))
                    robux_drop_text = f"\n💵 <b>БОНУС:</b> Вы получили <b>{robux_amount} R$</b> за победу!"

            final_text = code_text + f"🏁 <b>ИТОГИ БОЯ: {p1_name} VS {p2_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n👑 <b>Победитель: {winner}</b>\n{robux_drop_text}\n"
            bp_messages = []
            
            if pvp_no_rewards:
                final_text += "🤝 Дружеская дуэль завершена! Награды и кубки не начислялись."
            elif is_pvp:
                if "Ничья" not in winner and winner_id and loser_id:
                    await execute_db("UPDATE users SET trophies = trophies + 15 WHERE id = ?", (winner_id,))
                    await execute_db("UPDATE users SET trophies = MAX(0, trophies - 10) WHERE id = ?", (loser_id,))
                    final_text += f"🏆 Победитель забирает <b>+15 Кубков</b>\n💀 Проигравший теряет <b>-10 Кубков</b>"
            else:
                mod_reward_mult = 1.0
                mod_trophy_mult = 1.0
                
                # Modifiers balance
                if mods:
                    if mods.get('mod_enemy_hp'): 
                        mod_reward_mult += 0.3
                        mod_trophy_mult += 0.3
                    if mods.get('mod_enemy_atk_all'): 
                        mod_reward_mult += 0.35
                        mod_trophy_mult += 0.35
                    if mods.get('mod_enemy_stats'): 
                        mod_reward_mult += 0.2
                        mod_trophy_mult += 0.2
                    if mods.get('mod_no_heals'):
                        mod_reward_mult += 0.30
                        mod_trophy_mult += 0.30
                        
                    # Buffs reduce shekels/xp rewards
                    if mods.get('mod_player_atk_all'): 
                        mod_reward_mult -= 0.4
                    if mods.get('mod_manual_atk'): 
                        mod_reward_mult -= 0.5
                    if mods.get('mod_player_hp'): 
                        mod_reward_mult -= 0.3
                    if mods.get('mod_player_shield'):
                        mod_reward_mult -= 0.15
                    if mods.get('mod_player_vamp'):
                        mod_reward_mult -= 0.15
                    if mods.get('mod_enemy_burn'):
                        mod_reward_mult -= 0.20
                    
                mod_reward_mult = max(0.1, mod_reward_mult)
                coin_mult, xp_mult_event = await get_coin_xp_events()
                
                # Check Double Coins gamepass or VIP (+50% coins)
                gp_vip_multiplier = 1.0
                user_gp = await fetch_one("SELECT gp_double_coins, gp_vip FROM users WHERE id=?", (p1_id,))
                if user_gp:
                    if user_gp['gp_double_coins'] == 1: 
                        gp_vip_multiplier *= 2.0
                    if user_gp['gp_vip'] == 1: 
                        gp_vip_multiplier *= 1.5
                
                if winner == p1_name:
                    user_data = await fetch_one("SELECT trophies FROM users WHERE id = ?", (p1_id,))
                    user_trophies = user_data['trophies'] if user_data else 0
                    rank = await get_user_rank(user_trophies)
                    
                    coins_base = random.randint(25, 90) * rank['reward_mult'] * diff_trophies_scale * 0.85 * coin_mult * gp_vip_multiplier
                    coins_won = int(coins_base * mod_reward_mult)
                    won_t_base = await get_dynamic_trophies(rank['name'], rank['rank_idx'], diff_trophies_scale)
                    won_t = int(won_t_base * mod_trophy_mult)
                    
                    await execute_db("UPDATE users SET coins = coins + ?, total_coins = total_coins + ?, trophies = trophies + ? WHERE id = ?", (coins_won, coins_won, won_t, p1_id))
                    
                    final_text += f"🎉 <b>Награды:</b>\n💰 {coins_won} Шекелей"
                    if coin_mult > 1.0: final_text += f" (Ивент x{coin_mult})"
                    if gp_vip_multiplier > 1.0: final_text += f" (Геймпассы x{gp_vip_multiplier})"
                    if mod_reward_mult != 1.0: final_text += f" [Моды x{mod_reward_mult:.2f}]"
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
                        lost_t = random.randint(5, 12) 
                    else:
                        lost_t = 2
                    
                    await execute_db("UPDATE users SET trophies = MAX(0, trophies - ?) WHERE id = ?", (lost_t, p1_id))
                    final_text += f"💀 Вы проиграли и потеряли <b>{lost_t} 🏆</b>.\n"
                    bp_xp = int((5 * diff_bp_mult * xp_mult_event) * mod_reward_mult)
                    lvl_up, bp_title, new_lvl = await add_bp_xp(p1_id, bp_xp)
                    final_text += f"🎫 +{bp_xp} BP XP"
                    if lvl_up: bp_messages.append(f"🎉 <b>НОВЫЙ УРОВЕНЬ БП!</b> {new_lvl} уровень в сезоне «{bp_title}»!")
                    
            try: 
                await msg.edit_text(final_text, reply_markup=None)
            except Exception: 
                pass
            
            for b_msg in bp_messages:
                try: await bot.send_message(p1_id, b_msg)
                except: pass

        except Exception as e:
            logging.error(f"Reward error: {e}")
            try: await msg.edit_text("Ошибка при выдаче наград.", reply_markup=None)
            except: pass

    except Exception as e:
        logging.error(f"Critical battle loop error: {e}")
    finally:
        active_combats.discard(p1_id)
        if is_pvp and p2_id != 0: 
            active_combats.discard(p2_id)
        if chat_id in active_manual_battles: 
            active_manual_battles.pop(chat_id, None)

@dp.message(F.text == BTN_MODIFIERS)
async def cmd_modifiers_direct(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id=?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    def s(val): return "✅ Вкл" if val else "❌ Выкл"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 1.5x ХП Врагов ({s(user.get('mod_enemy_hp'))})", callback_data="set_mod_enemy_hp")],
        [InlineKeyboardButton(text=f"🔴 ИИ бьет 2 раза ({s(user.get('mod_enemy_atk_all'))})", callback_data="set_mod_enemy_atk_all")],
        [InlineKeyboardButton(text=f"🔴 1.2x Статы ИИ ({s(user.get('mod_enemy_stats'))})", callback_data="set_mod_enemy_stats")],
        [InlineKeyboardButton(text=f"🔴 Откл. Хила в бою ({s(user.get('mod_no_heals'))})", callback_data="set_mod_no_heals")],
        [InlineKeyboardButton(text=f"🟢 Игрок бьет 2 раза ({s(user.get('mod_player_atk_all'))})", callback_data="set_mod_player_atk_all")],
        [InlineKeyboardButton(text=f"🟢 Ручной выбор атаки ({s(user.get('mod_manual_atk'))})", callback_data="set_mod_manual_atk")],
        [InlineKeyboardButton(text=f"🟢 1.3x ХП Игрока ({s(user.get('mod_player_hp'))})", callback_data="set_mod_player_hp")],
        [InlineKeyboardButton(text=f"🟢 Старт со Щитом 30% ({s(user.get('mod_player_shield'))})", callback_data="set_mod_player_shield")],
        [InlineKeyboardButton(text=f"🟢 Вампиризм 25% ({s(user.get('mod_player_vamp'))})", callback_data="set_mod_player_vamp")],
        [InlineKeyboardButton(text=f"🟢 Горение ИИ 5%/ход ({s(user.get('mod_enemy_burn'))})", callback_data="set_mod_enemy_burn")]
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
    
    # Reload keyboard
    user = await fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    def s(val): return "✅ Вкл" if val else "❌ Выкл"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 1.5x ХП Врагов ({s(user.get('mod_enemy_hp'))})", callback_data="set_mod_enemy_hp")],
        [InlineKeyboardButton(text=f"🔴 ИИ бьет 2 раза ({s(user.get('mod_enemy_atk_all'))})", callback_data="set_mod_enemy_atk_all")],
        [InlineKeyboardButton(text=f"🔴 1.2x Статы ИИ ({s(user.get('mod_enemy_stats'))})", callback_data="set_mod_enemy_stats")],
        [InlineKeyboardButton(text=f"🔴 Откл. Хила в бою ({s(user.get('mod_no_heals'))})", callback_data="set_mod_no_heals")],
        [InlineKeyboardButton(text=f"🟢 Игрок бьет 2 раза ({s(user.get('mod_player_atk_all'))})", callback_data="set_mod_player_atk_all")],
        [InlineKeyboardButton(text=f"🟢 Ручной выбор атаки ({s(user.get('mod_manual_atk'))})", callback_data="set_mod_manual_atk")],
        [InlineKeyboardButton(text=f"🟢 1.3x ХП Игрока ({s(user.get('mod_player_hp'))})", callback_data="set_mod_player_hp")],
        [InlineKeyboardButton(text=f"🟢 Старт со Щитом 30% ({s(user.get('mod_player_shield'))})", callback_data="set_mod_player_shield")],
        [InlineKeyboardButton(text=f"🟢 Вампиризм 25% ({s(user.get('mod_player_vamp'))})", callback_data="set_mod_player_vamp")],
        [InlineKeyboardButton(text=f"🟢 Горение ИИ 5%/ход ({s(user.get('mod_enemy_burn'))})", callback_data="set_mod_enemy_burn")]
    ])
    try: 
        await callback.message.edit_reply_markup(reply_markup=kb)
    except: 
        pass
    await callback.answer()

@dp.message(F.text == BTN_PVE)
async def cmd_pve_select(message: types.Message):
    if await check_ban(message.from_user.id): return
    if message.from_user.id in active_combats: 
        return await message.answer("❌ Вы уже в бою!")
    if message.from_user.id in user_trades: 
        return await message.answer("❌ Завершите обмен!")
        
    team1 = await get_team_data(message.from_user.id)
    if not team1: 
        return await message.answer("❌ Боевая колода пуста!")
    
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
    elif diff_type == "med": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.0, 1.0, 1.0, "Средний 🟡"
    elif diff_type == "hard": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.5, 1.4, 1.2, "Сложный 🔴" 
    elif diff_type == "nightmare": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.9, 1.8, 1.5, "Кошмар ☠️"
        
    mods = {
        'mod_enemy_hp': user.get('mod_enemy_hp', 0),
        'mod_enemy_atk_all': user.get('mod_enemy_atk_all', 0),
        'mod_enemy_stats': user.get('mod_enemy_stats', 0),
        'mod_player_atk_all': user.get('mod_player_atk_all', 0),
        'mod_manual_atk': user.get('mod_manual_atk', 0),
        'mod_player_hp': user.get('mod_player_hp', 0),
        'mod_no_heals': user.get('mod_no_heals', 0),
        'mod_player_shield': user.get('mod_player_shield', 0),
        'mod_player_vamp': user.get('mod_player_vamp', 0),
        'mod_enemy_burn': user.get('mod_enemy_burn', 0)
    }

    try: await callback.message.edit_text(f"⚔️ <i>Ищем противника... Сложность: <b>{diff_name}</b></i>")
    except: pass
    
    team1 = await get_team_data(callback.from_user.id)
    rank = await get_user_rank(user['trophies'])
    
    team2 = await get_bot_team(callback.from_user.id, rank['difficulty_mult'] * power_mult, rank['name'], diff_type)
    if not team2: 
        try: await callback.message.edit_text("Ошибка: в базе нет подходящих карт.")
        except: pass
        return
    
    if mods['mod_enemy_hp']:
        for c in team2:
            c['hp'] = int(c['hp'] * 1.5)
            c['max_hp'] = c['hp']
    if mods['mod_enemy_stats']:
        for c in team2:
            c['damage'] = int(c['damage'] * 1.2)
            c['hp'] = int(c['hp'] * 1.2)
            c['max_hp'] = c['hp']
            c['booster_dmg_mult'] *= 1.2
            c['booster_hp_mult'] *= 1.2
    if mods['mod_player_hp']:
        for c in team1:
            c['hp'] = int(c['hp'] * 1.3)
            c['max_hp'] = c['hp']
            
    title_str = await get_user_titles_str(callback.from_user.id)
    p1_name = get_display_name(user) + title_str
    active_combats.add(callback.from_user.id)
    
    await log_user_action(callback.from_user.id, f"Начал PvE бой ({diff_type})")
    
    asyncio.create_task(run_battle_loop(bot, callback.message.chat.id, callback.from_user.id, p1_name, 0, f"AI ({diff_name})", team1, team2, trophies_scale, bp_xp_mult, is_pvp=False, mods=mods, diff_type=diff_type))
    await callback.answer()

@dp.message(F.text == BTN_PVP)
async def cmd_pvp_menu(message: types.Message):
    if await check_ban(message.from_user.id): return
    if message.from_user.id in active_combats or message.from_user.id in user_trades: 
        return await message.answer("❌ Заняты!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Найти случайного (Автоподбор)", callback_data="pvp_random")],
        [InlineKeyboardButton(text="🎯 Вызвать по ID / @username", callback_data="pvp_direct")]
    ])
    await message.answer("⚔️ <b>PvP ДУЭЛЬ</b>\nВыберите режим (награды за PvP дуэли отключены):", reply_markup=kb)

@dp.callback_query(F.data == "pvp_direct")
async def cb_pvp_direct(callback: types.CallbackQuery, state: FSMContext):
    try: await callback.message.edit_text("Введите @username или ID игрока:")
    except: pass
    await state.set_state(PvPState.waiting_target)
    asyncio.create_task(clear_fsm_timeout(state, callback.message.chat.id, 60))
    await callback.answer()

@dp.callback_query(F.data == "pvp_random")
async def cb_pvp_random(callback: types.CallbackQuery):
    u_id = callback.from_user.id
    user = await fetch_one("SELECT * FROM users WHERE id=?", (u_id,))
    
    if u_id in active_combats or u_id in user_trades: 
        return await callback.answer("Заняты!", show_alert=True)
    t1 = await get_team_data(u_id)
    if not t1: 
        return await callback.answer("Колода пуста!", show_alert=True)
    
    if u_id in pvp_queue:
        pvp_queue.remove(u_id)
        try: await callback.message.edit_text("Поиск отменен.")
        except: pass
        return
        
    valid_opponents = [x for x in pvp_queue if x != u_id and x not in active_combats and x not in user_trades]
    
    if valid_opponents:
        opp_id = valid_opponents[0]
        pvp_queue.remove(opp_id)
        
        opp = await fetch_one("SELECT * FROM users WHERE id=?", (opp_id,))
        t2 = await get_team_data(opp_id)
        
        active_combats.add(u_id)
        active_combats.add(opp_id)
        
        title_p1 = await get_user_titles_str(u_id)
        title_p2 = await get_user_titles_str(opp_id)
        p1_name = get_display_name(user) + title_p1
        p2_name = get_display_name(opp) + title_p2
        
        try: await callback.message.edit_text("Противник найден! Начинаем...")
        except: pass
        try: await bot.send_message(opp_id, "Противник найден! Начинаем...")
        except: pass
        
        await log_user_action(u_id, f"Начал PvP бой против {opp_id}")
        await log_user_action(opp_id, f"Начал PvP бой против {u_id}")
        
        asyncio.create_task(run_pvp_dual_broadcast(u_id, opp_id, p1_name, p2_name, t1, t2))
    else:
        pvp_queue.add(u_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить поиск", callback_data="pvp_random")]])
        try: await callback.message.edit_text("🔍 Поиск противника... Ожидайте.", reply_markup=kb)
        except: pass
    await callback.answer()

@dp.message(PvPState.waiting_target)
async def process_pvp_target(message: types.Message, state: FSMContext):
    val = message.text.strip()
    target_user = None
    user = await fetch_one("SELECT * FROM users WHERE id=?", (message.from_user.id,))
    
    if val.isdigit(): target_user = await fetch_one("SELECT * FROM users WHERE id = ?", (int(val),))
    else: target_user = await fetch_one("SELECT * FROM users WHERE username = ?", (val.lstrip('@'),))
        
    if not target_user: return await message.answer("❌ Игрок не найден.")
    if target_user['id'] == message.from_user.id: return await message.answer("❌ Самому себе нельзя!")
    if target_user['id'] in active_combats or target_user['id'] in user_trades: 
        return await message.answer("❌ Игрок занят!")

    challenger_name = get_display_name(user) + await get_user_titles_str(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Принять", callback_data=f"pvp_accept_{user['id']}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pvp_decline_{user['id']}")]
    ])
    
    try:
        await bot.send_message(target_user['id'], f"⚔️ <b>{challenger_name}</b> вызывает вас на дуэль!", reply_markup=kb)
        await message.answer("📨 Вызов отправлен.")
        await log_user_action(message.from_user.id, f"Вызвал игрока {target_user['id']} на дуэль")
    except: 
        await message.answer("Ошибка при отправке.")
    await state.clear()

@dp.callback_query(F.data.startswith("pvp_accept_"))
async def callback_pvp_accept(callback: types.CallbackQuery):
    challenger_id = int(callback.data.split("_")[2])
    target_id = callback.from_user.id
    
    if target_id in active_combats or challenger_id in active_combats or target_id in user_trades or challenger_id in user_trades:
        return await callback.answer("Заняты!", show_alert=True)
        
    t1 = await get_team_data(challenger_id)
    t2 = await get_team_data(target_id)
    
    if not t1 or not t2: 
        return await callback.answer("Колода пуста у одного из игроков!", show_alert=True)
        
    challenger = await fetch_one("SELECT * FROM users WHERE id = ?", (challenger_id,))
    target = await fetch_one("SELECT * FROM users WHERE id = ?", (target_id,))
    
    title_p1 = await get_user_titles_str(challenger_id)
    title_p2 = await get_user_titles_str(target_id)
    p1_name = get_display_name(challenger) + title_p1
    p2_name = get_display_name(target) + title_p2
    
    active_combats.add(challenger_id)
    active_combats.add(target_id)
    
    await log_user_action(target_id, f"Принял PvP вызов от {challenger_id}")
    
    asyncio.create_task(run_pvp_dual_broadcast(challenger_id, target_id, p1_name, p2_name, t1, t2))
    try: await callback.message.delete()
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("pvp_decline_"))
async def callback_pvp_decline(callback: types.CallbackQuery):
    challenger_id = int(callback.data.split("_")[2])
    try: await bot.send_message(challenger_id, f"❌ Вызов отклонен.")
    except: pass
    try: await callback.message.edit_text("❌ Вы отклонили вызов.")
    except: pass
    await callback.answer()

async def run_pvp_dual_broadcast(p1_id: int, p2_id: int, p1_name: str, p2_name: str, t1: list, t2: list):
    battle_id = f"pvp_{p1_id}_{p2_id}_{int(time.time())}"
    surrendered_players.discard((p1_id, battle_id))
    surrendered_players.discard((p2_id, battle_id))
    
    try:
        msg1 = await bot.send_message(p1_id, f"⚔️ Дуэль против <b>{p2_name}</b> начнется через 3 сек!")
        msg2 = await bot.send_message(p2_id, f"⚔️ Дуэль против <b>{p1_name}</b> начнется через 3 сек!")
        await asyncio.sleep(1)
        await safe_edit_text(msg1, "2...")
        await safe_edit_text(msg2, "2...")
        await asyncio.sleep(1)
        await safe_edit_text(msg1, "1...")
        await safe_edit_text(msg2, "1...")
        await asyncio.sleep(1)
        
        battle_start_time = time.time()
        log1 = []
        log2 = []
        apply_boosters(t1, p1_name, log1, log2)
        apply_boosters(t2, p2_name, log1, log2)
        
        if log1:
            header1 = build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log1)
            header2 = build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log2)
            await safe_edit_text(msg1, header1, reply_markup=get_battle_kb(battle_id))
            await safe_edit_text(msg2, header2, reply_markup=get_battle_kb(battle_id))
            await battle_delay(battle_id, p1_id, p2_id)

        turn = 1
        winner = None
        p1_heals = p2_heals = 0
        timeout_flag = False
        
        while True:
            if time.time() - battle_start_time > 180:
                timeout_flag = True
                break
                
            if (p1_id, battle_id) in surrendered_players and (p2_id, battle_id) in surrendered_players:
                winner = "Ничья"
                surrendered_players.discard((p1_id, battle_id))
                surrendered_players.discard((p2_id, battle_id))
                break
            elif (p1_id, battle_id) in surrendered_players:
                winner = p2_name
                surrendered_players.discard((p1_id, battle_id))
                log1.append(f"🏳️ <b>{p1_name} сдался!</b>")
                log2.append(f"🏳️ <b>{p1_name} сдался!</b>")
                break
            elif (p2_id, battle_id) in surrendered_players:
                winner = p1_name
                surrendered_players.discard((p2_id, battle_id))
                log1.append(f"🏳️ <b>{p2_name} сдался!</b>")
                log2.append(f"🏳️ <b>{p2_name} сдался!</b>")
                break

            t1_a = [c for c in t1 if c['hp'] > 0]
            t2_a = [c for c in t2 if c['hp'] > 0]
            if not t1_a and not t2_a: winner = "Ничья"; break
            elif not t1_a: winner = p2_name; break
            elif not t2_a: winner = p1_name; break
            if turn > 40: winner = "Ничья по раундам"; break

            did_turn, h = await execute_turn(t1, t2, p1_name, p2_name, log1, log2)
            p1_heals += h
            if did_turn:
                if len(log1) > 6: log1 = log1[-6:]; log2 = log2[-6:]
                try: 
                    await safe_edit_text(msg1, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log1), reply_markup=get_battle_kb(battle_id))
                except Exception as e:
                    if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag=True; break
                try: 
                    await safe_edit_text(msg2, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log2), reply_markup=get_battle_kb(battle_id))
                except Exception as e:
                    if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag=True; break
                await battle_delay(battle_id, p1_id, p2_id)

            t2_a = [c for c in t2 if c['hp'] > 0]
            if t2_a:
                if time.time() - battle_start_time > 180:
                    timeout_flag = True
                    break
                    
                did_turn, h = await execute_turn(t2, t1, p2_name, p1_name, log1, log2)
                p2_heals += h
                if did_turn:
                    if len(log1) > 6: log1 = log1[-6:]; log2 = log2[-6:]
                    try: 
                        await safe_edit_text(msg1, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log1), reply_markup=get_battle_kb(battle_id))
                    except Exception as e:
                        if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag=True; break
                    try: 
                        await safe_edit_text(msg2, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log2), reply_markup=get_battle_kb(battle_id))
                    except Exception as e:
                        if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag=True; break
                    await battle_delay(battle_id, p1_id, p2_id)
            turn += 1

        if timeout_flag:
            txt1 = "⏳ <b>Бой автоматически завершен по таймауту.</b>"
            try: await msg1.edit_text(txt1)
            except: pass
            try: await msg2.edit_text(txt1)
            except: pass
            return

        try:
            await add_quest_progress_new(p1_id, 'q_pvp', 1)
            await add_quest_progress_new(p2_id, 'q_pvp', 1)

            final1 = f"🏁 <b>ИТОГИ: {p1_name} VS {p2_name}</b>\nПобедитель: {winner}\nДружеская дуэль (без наград)."
            final2 = f"🏁 <b>ИТОГИ: {p1_name} VS {p2_name}</b>\nПобедитель: {winner}\nДружеская дуэль (без наград)."
            
            try: await msg1.edit_text(final1, reply_markup=None)
            except: pass
            try: await msg2.edit_text(final2, reply_markup=None)
            except: pass
        except Exception as e:
            logging.error(f"PVP Reward error: {e}")
        
    finally:
        active_combats.discard(p1_id)
        active_combats.discard(p2_id)


@dp.message(Command("trade"))
async def cmd_trade_request(message: types.Message, state: FSMContext):
    if await check_ban(message.from_user.id): return
    if message.from_user.id in active_combats or message.from_user.id in user_trades: 
        return await message.answer("Вы заняты!")
    parts = message.text.split()
    if len(parts) > 1:
        message.text = parts[1]
        await process_trade_target(message, state)
    else:
        await message.answer("🤝 <b>ОБМЕН</b>\nВведите @username или ID игрока:")
        await state.set_state(TradeState.waiting_target)
        asyncio.create_task(clear_fsm_timeout(state, message.chat.id, 60))

@dp.message(TradeState.waiting_target)
async def process_trade_target(message: types.Message, state: FSMContext):
    val = message.text.strip()
    user = await fetch_one("SELECT * FROM users WHERE id=?", (message.from_user.id,))
    target_user = None
    
    if val.isdigit(): target_user = await fetch_one("SELECT * FROM users WHERE id = ?", (int(val),))
    else: target_user = await fetch_one("SELECT * FROM users WHERE username = ?", (val.lstrip('@'),))
        
    if not target_user: return await message.answer("Игрок не найден в боте.")
    if target_user['id'] == message.from_user.id: return await message.answer("Нельзя обмениваться с самим собой!")
    if target_user['id'] in active_combats or target_user['id'] in user_trades: 
        return await message.answer("Игрок сейчас занят.")

    challenger_name = get_display_name(user) + await get_user_titles_str(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"tr_acc_{user['id']}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"tr_dec_{user['id']}")]
    ])
    
    try:
        await bot.send_message(target_user['id'], f"🤝 <b>{challenger_name}</b> предлагает вам обмен!", reply_markup=kb)
        await message.answer("📨 Запрос на обмен отправлен.")
        await log_user_action(message.from_user.id, f"Отправил запрос на трейд игроку {target_user['id']}")
    except: 
        await message.answer("Произошла ошибка отправки запроса.")
    await state.clear()

@dp.callback_query(F.data.startswith("tr_acc_"))
async def callback_trade_accept(callback: types.CallbackQuery):
    p1_id = int(callback.data.split("_")[2])
    p2_id = callback.from_user.id
    if p1_id in user_trades or p2_id in user_trades or p1_id in active_combats or p2_id in active_combats: 
        return await callback.answer("Заняты!", show_alert=True)
        
    p1 = await fetch_one("SELECT * FROM users WHERE id = ?", (p1_id,))
    p2 = await fetch_one("SELECT * FROM users WHERE id = ?", (p2_id,))
    
    trade_id = f"tr_{p1_id}_{p2_id}_{int(time.time())}"
    trade = {
        'id': trade_id, 'p1': p1_id, 'p2': p2_id,
        'p1_name': get_display_name(p1), 'p2_name': get_display_name(p2),
        'p1_offer': {}, 'p2_offer': {},  
        'p1_strings': {}, 'p2_strings': {}, 
        'p1_robux': 0, 'p2_robux': 0, # Robux exchange addition
        'p1_ready': False, 'p2_ready': False,
        'p1_confirmed': False, 'p2_confirmed': False,
        'p1_msg': None, 'p2_msg': None,
        'start_time': time.time(), 'status': 'ongoing'
    }
    
    active_trades[trade_id] = trade
    user_trades[p1_id] = trade_id
    user_trades[p2_id] = trade_id
    
    await log_user_action(p2_id, f"Принял запрос на трейд от {p1_id}")
    
    try:
        msg1 = await bot.send_message(p1_id, await render_trade_text(trade), reply_markup=get_trade_main_kb(trade, p1_id))
        trade['p1_msg'] = msg1.message_id
    except: pass
    try:
        msg2 = await bot.send_message(p2_id, await render_trade_text(trade), reply_markup=get_trade_main_kb(trade, p2_id))
        trade['p2_msg'] = msg2.message_id
    except: pass
    
    try: await callback.message.delete()
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_dec_"))
async def callback_trade_decline(callback: types.CallbackQuery):
    p1_id = int(callback.data.split("_")[2])
    try: await bot.send_message(p1_id, "❌ Запрос отклонен.")
    except: pass
    try: await callback.message.edit_text("❌ Запрос отклонен.")
    except: pass
    await callback.answer()

async def render_trade_text(trade):
    text = "🤝 <b>ТОРГОВАЯ КОМНАТА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    text += f"🔵 <b>Предлагает {trade['p1_name']}:</b>\n"
    has_p1_items = False
    if trade['p1_offer']:
        for inv_id, qty in trade['p1_offer'].items(): 
            text += f"  └ {qty}x {trade['p1_strings'].get(inv_id, '?')}\n"
            has_p1_items = True
    if trade.get('p1_robux', 0) > 0:
        text += f"  └ 💵 <b>{trade['p1_robux']} R$</b>\n"
        has_p1_items = True
    if not has_p1_items: 
        text += "  └ <i>Ничего</i>\n"
            
    text += f"\n🔴 <b>Предлагает {trade['p2_name']}:</b>\n"
    has_p2_items = False
    if trade['p2_offer']:
        for inv_id, qty in trade['p2_offer'].items(): 
            text += f"  └ {qty}x {trade['p2_strings'].get(inv_id, '?')}\n"
            has_p2_items = True
    if trade.get('p2_robux', 0) > 0:
        text += f"  └ 💵 <b>{trade['p2_robux']} R$</b>\n"
        has_p2_items = True
    if not has_p2_items: 
        text += "  └ <i>Ничего</i>\n"
            
    r_str = "✅ Готов"
    w_str = "⏳ Выбирает..."
    p1_st = r_str if trade['p1_ready'] else w_str
    p2_st = r_str if trade['p2_ready'] else w_str
    
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>Статус готовности:</b>\n"
    text += f"{trade['p1_name']}: {p1_st}\n{trade['p2_name']}: {p2_st}\n"
    return text

def get_trade_main_kb(trade, user_id):
    if trade['status'] != 'ongoing': return None
    kb = []
    if trade['p1_ready'] and trade['p2_ready']:
        is_conf = trade['p1_confirmed'] if user_id == trade['p1'] else trade['p2_confirmed']
        if is_conf: kb.append([InlineKeyboardButton(text="⏳ Ожидание...", callback_data="ignore")])
        else: kb.append([InlineKeyboardButton(text="🔒 ПОДТВЕРДИТЬ", callback_data="tr_action_confirm")])
    else:
        kb.append([
            InlineKeyboardButton(text="➕ Добавить Карту", callback_data="tr_menu_add"),
            InlineKeyboardButton(text="💵 Добавить R$", callback_data="tr_menu_add_robux")
        ])
        kb.append([InlineKeyboardButton(text="➖ Убрать Карты", callback_data="tr_menu_rem")])
        is_ready = trade['p1_ready'] if user_id == trade['p1'] else trade['p2_ready']
        if is_ready: kb.append([InlineKeyboardButton(text="⏳ Ожидание партнера...", callback_data="ignore")])
        else: kb.append([InlineKeyboardButton(text="✅ ГОТОВ К ОБМЕНУ", callback_data="tr_action_ready")])
            
    kb.append([InlineKeyboardButton(text="❌ Отменить обмен", callback_data="tr_action_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def update_trade_uis(trade):
    try: await bot.edit_message_text(await render_trade_text(trade), chat_id=trade['p1'], message_id=trade['p1_msg'], reply_markup=get_trade_main_kb(trade, trade['p1']))
    except: pass
    try: await bot.edit_message_text(await render_trade_text(trade), chat_id=trade['p2'], message_id=trade['p2_msg'], reply_markup=get_trade_main_kb(trade, trade['p2']))
    except: pass

@dp.callback_query(F.data.startswith("tr_action_"))
async def cb_trade_actions_fixed(callback: types.CallbackQuery):
    action = callback.data.split("_")[2]
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: 
        return await callback.answer("Ошибка: Обмен не найден", show_alert=True)
    trade = active_trades[trade_id]
    
    if action == "cancel":
        trade['status'] = 'cancelled'
        try: await bot.edit_message_text("❌ Обмен отменен.", chat_id=trade['p1'], message_id=trade['p1_msg'])
        except: pass
        try: await bot.edit_message_text("❌ Обмен отменен.", chat_id=trade['p2'], message_id=trade['p2_msg'])
        except: pass
        user_trades.pop(trade['p1'], None)
        user_trades.pop(trade['p2'], None)
        active_trades.pop(trade_id, None)
        return await callback.answer("Вы отменили обмен.")
        
    if action == "ready":
        if user_id == trade['p1']: trade['p1_ready'] = True
        else: trade['p2_ready'] = True
        await update_trade_uis(trade)
        return await callback.answer("Вы готовы!")
        
    if action == "confirm":
        if user_id == trade['p1']: trade['p1_confirmed'] = True
        else: trade['p2_confirmed'] = True
        await update_trade_uis(trade)
        if trade['p1_confirmed'] and trade['p2_confirmed']: 
            await execute_trade_fixed(trade_id)
    await callback.answer()


@dp.callback_query(F.data == "tr_menu_add_robux")
async def cb_trade_menu_add_robux(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    
    user = await fetch_one("SELECT robux FROM users WHERE id=?", (user_id,))
    await callback.message.answer(f"💵 Ваш баланс: <b>{user['robux']} R$</b>\nВведите количество робуксов, которое хотите предложить:")
    await state.set_state(TradeState.waiting_robux)
    await callback.answer()

@dp.message(TradeState.waiting_robux)
async def process_trade_robux_amount(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: 
        await state.clear()
        return await message.answer("Обмен завершен или отменен.")
        
    trade = active_trades[trade_id]
    user = await fetch_one("SELECT robux FROM users WHERE id=?", (user_id,))
    
    try:
        amt = int(message.text.strip())
        if amt < 0: raise ValueError
        if amt > user['robux']:
            return await message.answer(f"❌ Недостаточно средств! У вас только <b>{user['robux']} R$</b>")
            
        trade['p1_ready'] = False
        trade['p2_ready'] = False
        trade['p1_confirmed'] = False
        trade['p2_confirmed'] = False
        
        if user_id == trade['p1']:
            trade['p1_robux'] = amt
        else:
            trade['p2_robux'] = amt
            
        await message.answer(f"💵 Предложено <b>{amt} R$</b>")
        await update_trade_uis(trade)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите положительное целое число.")
        
    await state.clear()

@dp.callback_query(F.data == "tr_menu_add")
async def cb_trade_menu_add(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    
    trade['p1_ready'] = False; trade['p2_ready'] = False
    trade['p1_confirmed'] = False; trade['p2_confirmed'] = False
    
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by, u.username, u.first_name
        FROM inventory i JOIN cards c ON i.card_id = c.id LEFT JOIN users u ON i.signed_by = u.id
        WHERE i.user_id = ? AND i.count > 0
    """, (user_id,))
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    
    items = []
    for c in inv:
        avail = c['count'] - offer_dict.get(c['inv_id'], 0)
        if avail > 0:
            if c['signed_by'] != 0: c['signer_name'] = get_display_name({'username': c['username'], 'first_name': c['first_name']})
            n = format_card_name_plain(c)
            mut = "⭐ " if c['mutation'] == 'Gold' else ("💎 " if c['mutation'] == 'Diamond' else ("🌈 " if c['mutation'] == 'Rainbow' else ""))
            items.append({"id": c['inv_id'], "btn_text": f"{mut}{n} ({avail})" })
            
    kb = get_pagination_keyboard(items, 0, "tr_add", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="tr_menu_main")])
    try: 
        await callback.message.edit_text("Выбор карты для добавления:", reply_markup=kb)
    except: 
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_add_page_"))
async def cb_trade_add_paginate(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[3])
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by, u.username, u.first_name
        FROM inventory i JOIN cards c ON i.card_id = c.id LEFT JOIN users u ON i.signed_by = u.id
        WHERE i.user_id = ? AND i.count > 0
    """, (user_id,))
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = []
    for c in inv:
        avail = c['count'] - offer_dict.get(c['inv_id'], 0)
        if avail > 0:
            if c['signed_by'] != 0: c['signer_name'] = get_display_name({'username': c['username'], 'first_name': c['first_name']})
            n = format_card_name_plain(c)
            mut = "⭐ " if c['mutation'] == 'Gold' else ("💎 " if c['mutation'] == 'Diamond' else ("🌈 " if c['mutation'] == 'Rainbow' else ""))
            items.append({"id": c['inv_id'], "btn_text": f"{mut}{n} ({avail})"})
            
    kb = get_pagination_keyboard(items, page, "tr_add", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="tr_menu_main")])
    try: 
        await callback.message.edit_reply_markup(reply_markup=kb)
    except: 
        pass
    await callback.answer()


@dp.callback_query(F.data.startswith("tr_add_"))
async def cb_trade_do_add(callback: types.CallbackQuery):
    """
    FIXED: Больше не показывает средний палец. Карта мгновенно добавляется в трейд,
    обновляя статус торговой сессии.
    """
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    string_dict = trade['p1_strings'] if user_id == trade['p1'] else trade['p2_strings']
    
    trade['p1_ready'] = False; trade['p2_ready'] = False
    trade['p1_confirmed'] = False; trade['p2_confirmed'] = False
    
    details = await get_inv_item_details(inv_id)
    if not details: 
        return await callback.answer("Карта пропала или не найдена!", show_alert=True)
        
    current_qty = offer_dict.get(inv_id, 0)
    if current_qty >= details['count']:
        return await callback.answer("Вы уже предложили максимум доступных копий!", show_alert=True)
        
    offer_dict[inv_id] = current_qty + 1
    
    mut_emoji = "⭐" if details['mutation'] == 'Gold' else ("💎" if details['mutation'] == 'Diamond' else ("🌈" if details['mutation'] == 'Rainbow' else "⚪"))
    serial_str = f" [#{details['serial_number']:04d}]" if details['serial_number'] > 0 else ""
    signed_str = " ✍️" if details['signed_by'] > 0 else ""
    string_dict[inv_id] = f"{mut_emoji} {details['name']}{serial_str}{signed_str}"
    
    await callback.answer("Карта успешно добавлена!")
    await update_trade_uis(trade)

@dp.callback_query(F.data == "tr_menu_rem")
async def cb_trade_menu_rem(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    string_dict = trade['p1_strings'] if user_id == trade['p1'] else trade['p2_strings']
    
    trade['p1_ready'] = False; trade['p2_ready'] = False
    trade['p1_confirmed'] = False; trade['p2_confirmed'] = False
    
    items = []
    for i_id, qty in offer_dict.items():
        if qty > 0: 
            items.append({"id": i_id, "btn_text": f"❌ {string_dict[i_id]} (x{qty})"})
            
    kb = get_pagination_keyboard(items, 0, "tr_rem", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="tr_menu_main")])
    try: 
        await callback.message.edit_text("Выберите предмет для удаления из обмена:", reply_markup=kb)
    except: 
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_rem_page_"))
async def cb_trade_rem_paginate(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[3])
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    string_dict = trade['p1_strings'] if user_id == trade['p1'] else trade['p2_strings']
    
    items = []
    for i_id, qty in offer_dict.items():
        if qty > 0: 
            items.append({"id": i_id, "btn_text": f"❌ {string_dict[i_id]} (x{qty})"})
            
    kb = get_pagination_keyboard(items, page, "tr_rem", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="tr_menu_main")])
    try: 
        await callback.message.edit_reply_markup(reply_markup=kb)
    except: 
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_rem_"))
async def cb_trade_do_rem(callback: types.CallbackQuery):
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    
    if offer_dict.get(inv_id, 0) > 0:
        offer_dict[inv_id] -= 1
        if offer_dict[inv_id] == 0: 
            del offer_dict[inv_id]
            
    trade['p1_ready'] = False; trade['p2_ready'] = False
    trade['p1_confirmed'] = False; trade['p2_confirmed'] = False
    
    await callback.answer("Удалена 1 шт.")
    await update_trade_uis(trade)

@dp.callback_query(F.data == "tr_menu_main")
async def cb_trade_menu_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    await update_trade_uis(active_trades[trade_id])
    await callback.answer()


async def execute_trade_fixed(trade_id):
    trade = active_trades.pop(trade_id, None)
    if not trade: return
    user_trades.pop(trade['p1'], None)
    user_trades.pop(trade['p2'], None)
    
    db = await get_db_connection()
    try:
        await db.execute("BEGIN TRANSACTION")
        
        # Verify Robux balances before finalizing
        p1_stats = await db.execute("SELECT robux FROM users WHERE id=?", (trade['p1'],))
        p1_r = await p1_stats.fetchone()
        p2_stats = await db.execute("SELECT robux FROM users WHERE id=?", (trade['p2'],))
        p2_r = await p2_stats.fetchone()
        
        if p1_r['robux'] < trade.get('p1_robux', 0) or p2_r['robux'] < trade.get('p2_robux', 0):
            raise Exception("Недостаточно Робуксов для обмена у одного из игроков!")
            
        async def transfer_items(from_u, to_u, offer):
            for i_id, qty in offer.items():
                cur = await db.execute("SELECT card_id, mutation, serial_number, signed_by, count FROM inventory WHERE id = ?", (i_id,))
                row = await cur.fetchone()
                if not row or row['count'] < qty: 
                    raise Exception("Карта не найдена в инвентаре!")
                
                if row['count'] == qty:
                    await db.execute("DELETE FROM inventory WHERE id = ?", (i_id,))
                    for slot in ['equip1', 'equip2', 'equip3', 'equip4', 'equip5']:
                        await db.execute(f"UPDATE users SET {slot} = 0 WHERE {slot} = ?", (i_id,))
                else:
                    await db.execute("UPDATE inventory SET count = count - ? WHERE id = ?", (qty, i_id))
                    
                cur2 = await db.execute("""
                    SELECT id FROM inventory 
                    WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = ? AND signed_by = ?
                """, (to_u, row['card_id'], row['mutation'], row['serial_number'], row['signed_by']))
                dest = await cur2.fetchone()
                
                if dest: 
                    await db.execute("UPDATE inventory SET count = count + ? WHERE id = ?", (qty, dest['id']))
                else: 
                    await db.execute("""
                        INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (to_u, row['card_id'], qty, row['mutation'], row['serial_number'], row['signed_by']))

        await transfer_items(trade['p1'], trade['p2'], trade['p1_offer'])
        await transfer_items(trade['p2'], trade['p1'], trade['p2_offer'])
        
        # Transfer Robux
        if trade.get('p1_robux', 0) > 0:
            await db.execute("UPDATE users SET robux = robux - ? WHERE id = ?", (trade['p1_robux'], trade['p1']))
            await db.execute("UPDATE users SET robux = robux + ? WHERE id = ?", (trade['p1_robux'], trade['p2']))
        if trade.get('p2_robux', 0) > 0:
            await db.execute("UPDATE users SET robux = robux - ? WHERE id = ?", (trade['p2_robux'], trade['p2']))
            await db.execute("UPDATE users SET robux = robux + ? WHERE id = ?", (trade['p2_robux'], trade['p1']))

        await db.commit()
        success = True
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Trade Finalize Error: {e}")
        success = False
    finally:
        await db.close()
        
    if success:
        await log_user_action(trade['p1'], f"Успешно завершил обмен с {trade['p2']}")
        await log_user_action(trade['p2'], f"Успешно завершил обмен с {trade['p1']}")
        try: await bot.send_message(trade['p1'], "🎉 <b>ОБМЕН ЗАВЕРШЕН! Предметы переведены!</b>")
        except: pass
        try: await bot.send_message(trade['p2'], "🎉 <b>ОБМЕН ЗАВЕРШЕН! Предметы переведены!</b>")
        except: pass
    else:
        try: await bot.send_message(trade['p1'], "❌ Ошибка совершения обмена (возможно, у одного из участников недостаточно баланса R$ или карт).")
        except: pass
        try: await bot.send_message(trade['p2'], "❌ Ошибка совершения обмена.")
        except: pass

async def cancel_trade(trade_id, reason="Cancelled"):
    trade = active_trades.pop(trade_id, None)
    if not trade: return
    user_trades.pop(trade['p1'], None)
    user_trades.pop(trade['p2'], None)
    try: await bot.send_message(trade['p1'], f"❌ Обмен отменен. Причина: {reason}")
    except: pass
    try: await bot.send_message(trade['p2'], f"❌ Обмен отменен. Причина: {reason}")
    except: pass

async def get_inv_item_details(inv_id):
    row = await fetch_one("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.count, i.mutation, i.serial_number, i.signed_by, u.username, u.first_name
        FROM inventory i JOIN cards c ON i.card_id = c.id LEFT JOIN users u ON i.signed_by = u.id
        WHERE i.id = ?
    """, (inv_id,))
    if not row: return None
    if row['signed_by'] != 0: 
        row['signer_name'] = get_display_name({'username': row['username'], 'first_name': row['first_name']})
    return row

async def trade_timeout_task():
    while True:
        try:
            now = time.time()
            to_cancel = []
            for t_id, trade in active_trades.items():
                if now - trade['start_time'] > 600:
                    to_cancel.append(t_id)
            for t_id in to_cancel:
                await cancel_trade(t_id, reason="Таймаут истек (10 минут)")
        except: pass
        await asyncio.sleep(60)


@dp.message(F.text == BTN_SEED_PACKS)
async def cmd_seed_packs_menu(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT coins, gp_vip FROM users WHERE id = ?", (message.from_user.id,))
    packs = await fetch_all("SELECT * FROM seed_packs WHERE is_football = 0")
    
    discount = 0.9 if (user and user['gp_vip'] == 1) else 1.0
    bal = user['coins']
    
    text = (
        f"📦 <b>СИД-ПАКИ</b>\n💰 Твой баланс: <b>{bal} Шекелей</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nСид-Пак — это особый набор с повышенным шансом на крутые мутации (<b>15% на Золотую</b>, <b>5% на Алмазную</b>, <b>1.5% на Радужную</b>)!\n\nДоступные паки:\n"
    )
    
    kb = []
    if not packs:
        text += "\n<i>Паки отсутствуют. Ожидайте пополнения!</i>"
    else:
        for p in packs:
            desc_text = f" — {p['description']}" if p['description'] else ""
            price_val = int(p.get('price', 2000) * discount)
            text += f"🔹 <b>{p['title']}</b> (Цена: <b>{price_val} 💰</b>){desc_text}\n"
            kb.append([InlineKeyboardButton(text=f"🔍 Смотреть: {p['title']}", callback_data=f"sp_view_{p['id']}_shop")])
            
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("sp_view_"))
async def cb_sp_view(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    pack_id = int(parts[2])
    mode = parts[3] 
    user_id = callback.from_user.id
    user = await fetch_one("SELECT coins, gp_vip FROM users WHERE id=?", (user_id,))
    
    pack = await fetch_one("SELECT * FROM seed_packs WHERE id = ?", (pack_id,))
    if not pack: return await callback.answer("Ошибка!", show_alert=True)
    
    pack_cards = await fetch_all("SELECT c.name, spc.drop_chance FROM seed_pack_cards spc JOIN cards c ON spc.card_id = c.id WHERE spc.pack_id = ?", (pack_id,))
    
    discount = 0.9 if (user and user['gp_vip'] == 1) else 1.0
    pack_price = int(pack.get('price', 2000) * discount)
    
    text = f"📦 <b>СИД-ПАК: {pack['title']}</b>\n💬 <i>{pack['description']}</i>\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>Содержимое пака:</b>\n"
    if not pack_cards:
        text += "  └ <i>Пак пуст!</i>\n"
    else:
        luck_mult, _ = await get_active_events()
        
        # Stack luck boost
        total_luck = luck_mult
        if user:
            if user.get('gp_luck_boost') == 1: total_luck *= 1.5
            if user.get('gp_vip') == 1: total_luck *= 1.3
            
        total_w = sum(c['drop_chance'] * (total_luck if c['drop_chance'] < 15.0 else 1.0) for c in pack_cards)
        for idx, c in enumerate(pack_cards, 1):
            w = c['drop_chance'] * (total_luck if c['drop_chance'] < 15.0 else 1.0)
            chance_pct = (w / total_w) * 100 if total_w > 0 else 0
            text += f"  {idx}. {c['name']} (~{chance_pct:.2f}%)\n"
            
    kb = []
    if mode == "shop":
        bal = user['coins']
        text += f"\n💰 Ваш баланс: <b>{bal} Шекелей</b>\nЦена: <b>{pack_price} 💰</b>"
        kb.append([InlineKeyboardButton(text=f"🛒 Купить x1", callback_data=f"sp_buy_{pack_id}_1")])
        kb.append([InlineKeyboardButton(text=f"x3 ({pack_price * 3} 💰)", callback_data=f"sp_buy_{pack_id}_3"), InlineKeyboardButton(text=f"x10 ({pack_price * 10} 💰)", callback_data=f"sp_buy_{pack_id}_10")])
        kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="sp_shop_back_0")])
    elif mode == "inv":
        user_pack = await fetch_one("SELECT count FROM user_seed_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id))
        amount = user_pack['count'] if user_pack else 0
        text += f"\nУ вас есть: <b>{amount} шт.</b>\n"
        if amount > 0:
            kb.append([InlineKeyboardButton(text="📦 Открыть x1", callback_data=f"sp_open_{pack_id}_1")])
            if amount >= 5:
                kb.append([InlineKeyboardButton(text="📦 Открыть x5", callback_data=f"sp_open_{pack_id}_5")])
            kb.append([InlineKeyboardButton(text="📦 Открыть ВСЕ", callback_data=f"sp_open_{pack_id}_all")])
        kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="sp_inv_back_0")])

    try: 
        await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        try: 
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except: 
            pass
    await callback.answer()

@dp.callback_query(F.data.startswith("sp_shop_back_"))
async def cb_sp_shop_back(callback: types.CallbackQuery):
    fake_msg = callback.message
    fake_msg.text = BTN_SEED_PACKS
    await cmd_seed_packs_menu(fake_msg)
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.startswith("sp_inv_back_"))
async def cb_sp_inv_back(callback: types.CallbackQuery):
    await cb_inv_packs_menu(callback)

@dp.callback_query(F.data == "inv_packs_menu")
async def cb_inv_packs_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    user_packs = await fetch_all("""
        SELECT usp.count, sp.id as pack_id, sp.title
        FROM user_seed_packs usp JOIN seed_packs sp ON usp.pack_id = sp.id
        WHERE usp.user_id = ? AND usp.count > 0
    """, (user_id,))
    
    text = f"🎒 <b>ИНВЕНТАРЬ СИД-ПАКОВ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите пак для распаковки:\n\n"
    kb = [[InlineKeyboardButton(text="🎒 Карты", callback_data="inv_cards_menu"), InlineKeyboardButton(text="📦 Сид-Паки (Выбрано)", callback_data="ignore")]]
    
    if not user_packs: 
        text += "<i>У вас нет Сид-Паков.</i>"
    else:
        for p in user_packs:
            text += f"📦 <b>{p['title']}</b> — <b>{p['count']} шт.</b>\n"
            kb.append([InlineKeyboardButton(text=f"🔍 Смотреть: {p['title']}", callback_data=f"sp_view_{p['pack_id']}_inv")])
            
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data == "inv_cards_menu")
async def cb_inv_cards_menu(callback: types.CallbackQuery):
    text, kb = await get_inventory_text_and_kb(callback.from_user.id, 0)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("sp_buy_"))
async def cb_sp_buy_fixed(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    pack_id = int(parts[2])
    amount = int(parts[3])
    user_id = callback.from_user.id
    
    user = await fetch_one("SELECT coins, gp_vip FROM users WHERE id=?", (user_id,))
    pack = await fetch_one("SELECT title, price FROM seed_packs WHERE id = ?", (pack_id,))
    
    if not pack: return await callback.answer("Ошибка БД!", show_alert=True)
    
    discount = 0.9 if (user and user['gp_vip'] == 1) else 1.0
    pack_price = int(pack['price'] * discount)
    total_cost = pack_price * amount
    
    if user['coins'] < total_cost:
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)
        
    await execute_db("UPDATE users SET coins = coins - ? WHERE id = ?", (total_cost, user_id))
    await execute_db("""
        INSERT INTO user_seed_packs (user_id, pack_id, count)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, pack_id) DO UPDATE SET count = count + ?
    """, (user_id, pack_id, amount, amount))
    
    await add_quest_progress_new(user_id, 'q_shop_buy', 1)
    await log_user_action(user_id, f"Купил Сид-Пак '{pack['title']}' x{amount}")
    
    await callback.answer(f"✅ Успешно куплено {amount} шт.!", show_alert=True)
    
    new_callback = callback.model_copy(update={"data": f"sp_view_{pack_id}_shop"})
    await cb_sp_view(new_callback)


@dp.callback_query(F.data.startswith("sp_open_"))
async def cb_sp_open_fixed(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    pack_id = int(parts[2])
    amt_str = parts[3]
    user_id = callback.from_user.id
    
    user_pack = await fetch_one("SELECT count FROM user_seed_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id))
