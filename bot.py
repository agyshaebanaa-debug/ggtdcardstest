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
import json
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    FSInputFile, BotCommand, LabeledPrice, PreCheckoutQuery, SuccessfulPayment
)
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

try:
    from PIL import Image, ImageOps, ImageDraw
except ImportError:
    raise ImportError("Установите Pillow: pip install Pillow")

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
    "🛠 <b>Update 3: Fixes & Diamonds</b>\n\n"
    "• <b>Новая Мутация: Diamond 💎:</b> Дает +30% к статам, шанс 5%!\n"
    "• <b>Изменены шансы Мутаций:</b> Gold (15%, +15%), Diamond (5%, +30%), Rainbow (0.9%, +45%).\n"
    "• <b>Система Pity в Сид-Паках:</b> Админы теперь могут назначать гарант на определенную карту в паке.\n"
    "• <b>Коды Наград:</b> Исправлена система. Коды теперь генерируются только админами, добавлены инструменты очистки.\n"
    "• <b>Донат Юниты:</b> Добавлена возможность покупать уникальные карты напрямую за R$ и Stars!\n"
    "• <b>ИИ Бан:</b> Админы могут запрещать ботам использовать определенные карты.\n"
    "• <b>Исправления:</b> Починена пагинация инвентаря, отображение карт при выбивании, кнопка БП, крафты и баги с геймпассами."
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
BTN_MODS = "🧬 Модификаторы"
BTN_SIGN = "✍️ Подписать карту"
BTN_ADM = "⚙️ Админ-панель"
BTN_CRAFT = "🔨 Крафт"

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
                pity_mythic INTEGER DEFAULT 0,
                pity_super INTEGER DEFAULT 0,
                total_coins INTEGER DEFAULT 0,
                notif_shop INTEGER DEFAULT 1,
                notif_events INTEGER DEFAULT 1,
                notif_quests INTEGER DEFAULT 1,
                notif_announces INTEGER DEFAULT 1,
                mod_enemy_hp INTEGER DEFAULT 0,
                mod_enemy_atk_all INTEGER DEFAULT 0,
                mod_enemy_stats INTEGER DEFAULT 0,
                mod_player_atk_all INTEGER DEFAULT 0,
                mod_manual_atk INTEGER DEFAULT 0,
                mod_player_hp INTEGER DEFAULT 0,
                robux INTEGER DEFAULT 0,
                pass_x2_coins INTEGER DEFAULT 0,
                pass_x2_xp INTEGER DEFAULT 0,
                pass_5th_slot INTEGER DEFAULT 0,
                pass_luck INTEGER DEFAULT 0,
                pass_vip INTEGER DEFAULT 0,
                equip5 INTEGER DEFAULT 0,
                mod_enemy_regen INTEGER DEFAULT 0,
                mod_enemy_thorns INTEGER DEFAULT 0,
                mod_player_vampire INTEGER DEFAULT 0,
                mod_player_shield INTEGER DEFAULT 0
            )
        """)
        
        new_columns = [
            'robux', 'pass_x2_coins', 'pass_x2_xp', 'pass_5th_slot', 'pass_luck', 'pass_vip', 'equip5',
            'mod_enemy_regen', 'mod_enemy_thorns', 'mod_player_vampire', 'mod_player_shield'
        ]
        for col in new_columns:
            try: 
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
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
                booster_hp_mult REAL DEFAULT 1.0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                card_id INTEGER,
                count INTEGER DEFAULT 1,
                mutation TEXT DEFAULT 'Normal',
                serial_number INTEGER DEFAULT 0,
                signed_by INTEGER DEFAULT 0
            )
        """)
        
        await db.execute("UPDATE cards SET rarity = 'Super' WHERE rarity IN ('Godly')")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ranks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                min_trophies INTEGER,
                difficulty_mult REAL DEFAULT 1.0,
                reward_mult REAL DEFAULT 1.0
            )
        """)

        await db.execute("DELETE FROM ranks")
        default_ranks = [
            ("🟤 Bronze I", 0, 0.8, 1.0), ("🟤 Bronze II", 50, 0.85, 1.05), ("🟤 Bronze III", 100, 0.9, 1.1), ("🟤 Bronze IV", 150, 0.95, 1.15),
            ("⚪ Silver I", 200, 1.0, 1.2), ("⚪ Silver II", 300, 1.05, 1.25), ("⚪ Silver III", 400, 1.1, 1.3), ("⚪ Silver IV", 500, 1.15, 1.35),
            ("🟡 Gold I", 650, 1.2, 1.4), ("🟡 Gold II", 800, 1.3, 1.5), ("🟡 Gold III", 950, 1.4, 1.6), ("🟡 Gold IV", 1100, 1.5, 1.7),
            ("🟢 Platina I", 1300, 1.8, 1.8), ("🟢 Platina II", 1500, 2.5, 1.9), ("🟢 Platina III", 1700, 3.2, 2.0), ("🟢 Platina IV", 1900, 4.0, 2.1),
            ("💎 Diamond I", 2200, 5.0, 2.5), ("💎 Diamond II", 2500, 6.5, 2.8), ("💎 Diamond III", 2800, 8.0, 3.2), ("💎 Diamond IV", 3100, 10.0, 3.6),
            ("🔴 Ruby I", 3500, 13.0, 4.0), ("🔴 Ruby II", 4000, 15.0, 4.5), ("🔴 Ruby III", 4500, 17.0, 5.0), ("🔴 Ruby IV", 5000, 20.0, 5.5),
            ("☢️ Uranium I", 5700, 24.0, 6.0), ("☢️ Uranium II", 6500, 28.0, 6.5), ("☢️ Uranium III", 7400, 32.0, 7.0), ("☢️ Uranium IV", 8400, 36.0, 7.5), ("☢️ Uranium V", 9500, 40.0, 8.0),
            ("🌌 Uranium VI", 10000, 42.0, 9.0), ("🌌 Uranium VII", 15000, 50.0, 10.0)
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
                pity_card_id INTEGER DEFAULT 0,
                pity_limit INTEGER DEFAULT 0
            )
        """)
        
        try:
            await db.execute("ALTER TABLE seed_packs ADD COLUMN pity_card_id INTEGER DEFAULT 0")
            await db.execute("ALTER TABLE seed_packs ADD COLUMN pity_limit INTEGER DEFAULT 0")
        except: pass
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seed_pack_cards (
                pack_id INTEGER,
                card_id INTEGER,
                drop_chance REAL,
                PRIMARY KEY (pack_id, card_id)
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
            CREATE TABLE IF NOT EXISTS user_pack_pity (
                user_id INTEGER,
                pack_id INTEGER,
                opened_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, pack_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS donate_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER,
                price_robux INTEGER DEFAULT 0,
                price_stars INTEGER DEFAULT 0
            )
        """)

        await db.execute("""CREATE TABLE IF NOT EXISTS ai_banned_cards (card_id INTEGER PRIMARY KEY)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS shop_items (id INTEGER PRIMARY KEY AUTOINCREMENT, item_type TEXT, name TEXT, price INTEGER, stock INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admin_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS lb_rewards (id INTEGER PRIMARY KEY AUTOINCREMENT, bracket TEXT, reward_type TEXT, amount INTEGER DEFAULT 0, card_id INTEGER DEFAULT 0, mutation TEXT DEFAULT 'Normal', lb_type TEXT DEFAULT 'trophies')""")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS authorized_signers (
                user_id INTEGER PRIMARY KEY
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS battle_passes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                photo_id TEXT,
                created_at REAL
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
            CREATE TABLE IF NOT EXISTS reward_codes (
                code TEXT PRIMARY KEY,
                reward_type TEXT,
                amount INTEGER DEFAULT 0,
                item_id INTEGER DEFAULT 0,
                mutation TEXT DEFAULT 'Normal',
                owner_id INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
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
    
class AdminGPManage(StatesGroup):
    user_id = State()

class AdminDonUnit(StatesGroup):
    card_id = State()
    robux = State()
    stars = State()

class AdminSeedPackPity(StatesGroup):
    card_id = State()
    limit = State()

class AdminLBRewards(StatesGroup):
    bracket = State()
    reward_type = State() 
    amount = State()
    card_id = State()
    mutation = State()

class AdminBPCreation(StatesGroup):
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
    title = State()
    photo = State()
    description = State()
    price = State()
    card_select = State()
    card_chance = State()
    confirm_save = State()

class AdminRewardCode(StatesGroup):
    count = State()
    r_type = State()
    amount = State()
    card_id = State()
    mutation = State()
    pack_id = State()

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

class DonateState(StatesGroup):
    gift_target = State()
    exchange_amount = State()

def get_display_name(user_data: dict) -> str:
    if user_data.get('username'): 
        return html.escape(f"@{user_data['username']}")
    elif user_data.get('first_name'): 
        return html.escape(user_data['first_name'])
    return f"Player {user_data.get('id', '???')}"

async def get_user_titles_str(user_id: int) -> str:
    titles = []
    user = await fetch_one("SELECT pass_vip FROM users WHERE id = ?", (user_id,))
    if user and user['pass_vip'] == 1: titles.append("💎 VIP")
    if await is_admin(user_id): titles.append("👑 Администратор")
    if await is_signer(user_id): titles.append("✍️ Сигнер")
    if titles: return f" [<i>{', '.join(titles)}</i>]"
    return ""

def make_progress_bar(current, total, length=10):
    if total <= 0: return "🟩" * length
    pct = min(1.0, current / total)
    filled = int(pct * length)
    empty = length - filled
    return "🟩" * filled + "⬜" * empty

async def get_user_vip_discount(user_id: int) -> float:
    user = await fetch_one("SELECT pass_vip FROM users WHERE id = ?", (user_id,))
    if user and user['pass_vip'] == 1: return 0.9 
    return 1.0

def roll_mutation():
    r = random.random()
    if r <= 0.009: return "Rainbow"
    if r <= 0.059: return "Diamond"
    if r <= 0.209: return "Gold"
    return "Normal"

def roll_seed_pack_mutation():
    r = random.random()
    if r <= 0.02: return "Rainbow"
    if r <= 0.12: return "Diamond"
    if r <= 0.37: return "Gold"
    return "Normal"

def get_mutation_multiplier(mutation: str) -> float:
    if mutation == "Rainbow": return 1.45
    if mutation == "Diamond": return 1.30
    if mutation == "Gold": return 1.15
    return 1.0

def needs_serial_number(rarity: str, mutation: str) -> bool:
    if rarity in ['Leaderboard', 'Exclusive', 'Mythic', 'Super', 'Secret']: return True
    return False

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
                user = await fetch_one("SELECT notif_quests FROM users WHERE id = ?", (user_id,))
                
                await db.execute("UPDATE users SET coins = coins + 1500, total_coins = total_coins + 1500 WHERE id = ?", (user_id,))
                next_hour = (int(time.time()) // 3600 + 1) * 3600
                await db.execute("UPDATE user_dynamic_quests SET reset_time = ? WHERE user_id = ?", (next_hour, user_id))
                
                packs = await fetch_all("SELECT id, title FROM seed_packs")
                pack_reward_text = ""
                if packs:
                    gift_pack = random.choice(packs)
                    await db.execute("""
                        INSERT INTO user_seed_packs (user_id, pack_id, count)
                        VALUES (?, ?, 1)
                        ON CONFLICT(user_id, pack_id) DO UPDATE SET count = count + 1
                    """, (user_id, gift_pack['id']))
                    pack_reward_text = f"\n📦 А также вы получили Сид-Пак: <b>{gift_pack['title']}</b> (1 шт.)!"
                
                if user and user['notif_quests'] == 1:
                    try:
                        msg = f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\nВы выполнили все задания этого часа и получили <b>1500 💰 Шекелей</b>!{pack_reward_text}\nНовые квесты появятся в начале следующего часа!"
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
    if notif_type:
        query += f" AND {notif_type} = 1"
        
    users = await fetch_all(query)
    success = 0
    for u in users:
        if shop_types:
            wants = False
            for st in shop_types:
                col = f"notif_{st}"
                if u.get(col) == 1: 
                    wants = True
                    break
            if not wants: continue
        try:
            await bot.send_message(u['id'], text_ru)
            success += 1
            await asyncio.sleep(0.05)
        except: 
            pass
    await notify_super_admin(f"📢 <b>Broadcast complete.</b>\nDelivered: {success}")

def get_main_keyboard(is_adm: bool = False, is_sgn: bool = False):
    kb = [
        [KeyboardButton(text=BTN_DRAW), KeyboardButton(text=BTN_PVE), KeyboardButton(text=BTN_PVP)],
        [KeyboardButton(text=BTN_INV), KeyboardButton(text=BTN_PROF), KeyboardButton(text=BTN_EQ)],
        [KeyboardButton(text=BTN_QUESTS), KeyboardButton(text=BTN_SHOP), KeyboardButton(text=BTN_BP)],
        [KeyboardButton(text=BTN_TOP), KeyboardButton(text=BTN_IDX), KeyboardButton(text=BTN_SEED_PACKS)],
        [KeyboardButton(text=BTN_CRAFT), KeyboardButton(text=BTN_MODS)]
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

async def get_active_events(user_id: int = None):
    settings = await fetch_one("SELECT * FROM server_settings WHERE id = 1")
    now = time.time()
    luck = settings['luck_mult'] if settings['luck_end'] > now else 1.0
    cd = settings['cd_mult'] if settings['cd_end'] > now else 1.0
    
    if user_id:
        user = await fetch_one("SELECT pass_luck, pass_vip FROM users WHERE id = ?", (user_id,))
        if user:
            if user['pass_vip'] == 1: luck *= 1.3
            if user['pass_luck'] == 1: luck *= 1.5

    return luck, cd

async def get_coin_xp_events():
    settings = await fetch_one("SELECT * FROM server_settings WHERE id = 1")
    now = time.time()
    coin_mult = settings['coin_mult'] if settings['coin_end'] > now else 1.0
    xp_mult = settings['xp_mult'] if settings['xp_end'] > now else 1.0
    return coin_mult, xp_mult

async def give_card_to_user(user_id: int, card_id: int, mutation: str, rarity: str = None, custom_serial: int = None) -> tuple:
    if not rarity:
        card = await fetch_one("SELECT rarity FROM cards WHERE id = ?", (card_id,))
        rarity = card['rarity'] if card else 'Basic'
        
    db = await get_db_connection()
    try:
        if custom_serial is not None and custom_serial > 0:
            cursor = await db.execute(
                "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by) VALUES (?, ?, 1, ?, ?, 0)",
                (user_id, card_id, mutation, custom_serial)
            )
            return cursor.lastrowid, custom_serial, True
            
        if needs_serial_number(rarity, mutation):
            res = await db.execute("SELECT MAX(serial_number) as m FROM inventory WHERE card_id = ? AND mutation = ?", (card_id, mutation))
            row = await res.fetchone()
            curr_max = row['m'] if (row and row['m'] is not None) else 0
            new_serial = curr_max + 1
            
            cursor = await db.execute(
                "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by) VALUES (?, ?, 1, ?, ?, 0)", 
                (user_id, card_id, mutation, new_serial)
            )
            return cursor.lastrowid, new_serial, True
        else:
            res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0", (user_id, card_id, mutation))
            inv_item = await res.fetchone()
            if inv_item:
                await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                return inv_item['id'], 0, False
            else:
                cursor = await db.execute(
                    "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by) VALUES (?, ?, 1, ?, 0, 0)", 
                    (user_id, card_id, mutation)
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
            await bot.send_message(chat_id, "⏳ <i>Время ожидания истекло (1 минута). Команда сброшена.</i>")
        except: 
            pass

async def calculate_chance_weights(luck_mult: float = 1.0):
    query = """
        SELECT * FROM cards 
        WHERE drop_chance > 0 
        AND rarity NOT IN ('Leaderboard', 'Secret')
        AND id NOT IN (SELECT card_id FROM seed_pack_cards)
    """
        
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
                await db.execute("INSERT INTO shop_items (item_type, name, price, stock) VALUES (?, ?, ?, ?)", (p_id, p_name_ru, p_price, stock))
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

async def give_multiple_cards(user_id: int, count: int) -> list:
    luck_mult, _ = await get_active_events(user_id)
    user = await fetch_one("SELECT pity_mythic, pity_super FROM users WHERE id=?", (user_id,))
    pm = user['pity_mythic'] if user else 0
    ps = user['pity_super'] if user else 0

    query = """
        SELECT * FROM cards 
        WHERE drop_chance > 0 
        AND rarity NOT IN ('Leaderboard', 'Secret')
        AND id NOT IN (SELECT card_id FROM seed_pack_cards)
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
                        top_users = await fetch_all("SELECT id, trophies as score, username, first_name FROM users WHERE id != ? ORDER BY trophies DESC LIMIT 20", (SUPER_ADMIN_ID,))
                    elif lb_type == 'coins':
                        top_users = await fetch_all("SELECT id, total_coins as score, username, first_name FROM users WHERE id != ? ORDER BY total_coins DESC LIMIT 20", (SUPER_ADMIN_ID,))
                    else:
                        top_users = await fetch_all("""
                            SELECT u.id, SUM(i.count) as score, u.username, u.first_name 
                            FROM users u JOIN inventory i ON u.id = i.user_id 
                            WHERE u.id != ? GROUP BY u.id ORDER BY score DESC LIMIT 20
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
    while True:
        await asyncio.sleep(4 * 3600) 
        try:
            file = FSInputFile(DB_NAME)
            await bot.send_document(SUPER_ADMIN_ID, file, caption="📦 Автоматический бэкап БД (каждые 4 часа).")
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
        "🛒 <b>МАГАЗИН ДОНАТА:</b> /donate\n"
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
        "• Вы можете собрать боевую колоду из 4-х карт (или 5 с VIP-пассом). Для этого выбивайте карты в Гаче или покупайте в магазине.\n"
        "• Бой проходит в автоматическом или полуавтоматическом режиме (если включены модификаторы в Настройках).\n"
        "• В боях против ИИ (ботов) вы получаете <b>Шекели 💰</b>, кубки, опыт БП и шанс выбить <b>Робуксы (R$)</b>! Награды зависят от выбранной сложности.\n"
        "• <b>PvP Дуэли</b> позволяют сразиться с друзьями дружеской дуэлью или через автоподбор за кубки.\n\n"
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
        "• В меню Крафта вы можете создавать новые мощные карты по рецептам.\n"
        "• Слейте одинаковые карты (8 для всех, 4 для VIP), чтобы гарантированно повысить их мутацию!\n\n"
        "🤝 <b>СИСТЕМА ОБМЕНА (ТРЕЙДЫ)</b>\n"
        "• Используйте команду <code>/trade [ID/username]</code>, чтобы начать безопасный обмен картами и Робуксами с другим игроком!\n\n"
        "🛒 <b>ДОНАТ: /donate</b>\n"
    )
    await message.answer(guide)

@dp.message(F.text == BTN_MODS)
async def cmd_modifiers(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id=?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    def s(val): return "✅ Вкл" if val else "❌ Выкл"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 1.5x ХП Врагов ({s(user.get('mod_enemy_hp'))})", callback_data="set_mod_enemy_hp")],
        [InlineKeyboardButton(text=f"🔴 ИИ бьет 2 раза ({s(user.get('mod_enemy_atk_all'))})", callback_data="set_mod_enemy_atk_all")],
        [InlineKeyboardButton(text=f"🔴 1.2x Статы ИИ ({s(user.get('mod_enemy_stats'))})", callback_data="set_mod_enemy_stats")],
        [InlineKeyboardButton(text=f"🔴 Враги регенерируют ({s(user.get('mod_enemy_regen'))})", callback_data="set_mod_enemy_regen")],
        [InlineKeyboardButton(text=f"🔴 Вражеские шипы ({s(user.get('mod_enemy_thorns'))})", callback_data="set_mod_enemy_thorns")],
        [InlineKeyboardButton(text=f"🟢 Игрок бьет 2 раза ({s(user.get('mod_player_atk_all'))})", callback_data="set_mod_player_atk_all")],
        [InlineKeyboardButton(text=f"🟢 Ручной выбор атаки ({s(user.get('mod_manual_atk'))})", callback_data="set_mod_manual_atk")],
        [InlineKeyboardButton(text=f"🟢 1.3x ХП Игрока ({s(user.get('mod_player_hp'))})", callback_data="set_mod_player_hp")],
        [InlineKeyboardButton(text=f"🟢 Вампиризм ({s(user.get('mod_player_vampire'))})", callback_data="set_mod_player_vampire")],
        [InlineKeyboardButton(text=f"🟢 Старт со щитом ({s(user.get('mod_player_shield'))})", callback_data="set_mod_player_shield")]
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
    
    # Reload menu
    user = await fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    def s(val): return "✅ Вкл" if val else "❌ Выкл"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 1.5x ХП Врагов ({s(user.get('mod_enemy_hp'))})", callback_data="set_mod_enemy_hp")],
        [InlineKeyboardButton(text=f"🔴 ИИ бьет 2 раза ({s(user.get('mod_enemy_atk_all'))})", callback_data="set_mod_enemy_atk_all")],
        [InlineKeyboardButton(text=f"🔴 1.2x Статы ИИ ({s(user.get('mod_enemy_stats'))})", callback_data="set_mod_enemy_stats")],
        [InlineKeyboardButton(text=f"🔴 Враги регенерируют ({s(user.get('mod_enemy_regen'))})", callback_data="set_mod_enemy_regen")],
        [InlineKeyboardButton(text=f"🔴 Вражеские шипы ({s(user.get('mod_enemy_thorns'))})", callback_data="set_mod_enemy_thorns")],
        [InlineKeyboardButton(text=f"🟢 Игрок бьет 2 раза ({s(user.get('mod_player_atk_all'))})", callback_data="set_mod_player_atk_all")],
        [InlineKeyboardButton(text=f"🟢 Ручной выбор атаки ({s(user.get('mod_manual_atk'))})", callback_data="set_mod_manual_atk")],
        [InlineKeyboardButton(text=f"🟢 1.3x ХП Игрока ({s(user.get('mod_player_hp'))})", callback_data="set_mod_player_hp")],
        [InlineKeyboardButton(text=f"🟢 Вампиризм ({s(user.get('mod_player_vampire'))})", callback_data="set_mod_player_vampire")],
        [InlineKeyboardButton(text=f"🟢 Старт со щитом ({s(user.get('mod_player_shield'))})", callback_data="set_mod_player_shield")]
    ])
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await callback.answer()

@dp.message(Command("donate"))
async def cmd_donate(message: types.Message):
    if await check_ban(message.from_user.id): return
    
    text = (
        "💎 <b>ДОНАТ МАГАЗИН</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Здесь вы можете приобрести премиум-бонусы для вашего аккаунта! Поддержите разработку бота.\n\n"
        "Вы можете оплачивать покупки с помощью <b>R$ (Робуксов)</b> или через <b>Telegram Stars ⭐️</b>.\n"
        "Также вы можете порадовать друзей и купить им геймпасс в подарок!\n\n"
        "<i>Выберите категорию:</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 F2P Магазин (За Робуксы)", callback_data="don_f2p_menu")],
        [InlineKeyboardButton(text="⭐️ P2W Магазин (За Stars)", callback_data="don_p2w_menu")],
        [InlineKeyboardButton(text="💳 Купить Робуксы (R$)", callback_data="don_buy_robux")],
        [InlineKeyboardButton(text="🃏 Донат-Юниты", callback_data="don_units_menu")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "don_buy_robux")
async def cb_don_buy_robux(callback: types.CallbackQuery, state: FSMContext):
    text = (
        "💳 <b>ОБМЕННИК ВАЛЮТ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Курс: <b>1 R$ = 1000 Шекелей</b>\n"
        "<i>(Вы можете только покупать Робуксы, продать их за шекели нельзя)</i>\n\n"
        "Напишите в чат количество R$, которое хотите купить:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="don_main")]])
    await callback.message.edit_text(text, reply_markup=kb)
    await state.set_state(DonateState.exchange_amount)
    await callback.answer()

@dp.message(DonateState.exchange_amount)
async def process_buy_robux(message: types.Message, state: FSMContext):
    try:
        amt_r = int(message.text.strip())
        if amt_r <= 0: raise ValueError
        cost = amt_r * 1000
        
        user = await fetch_one("SELECT coins FROM users WHERE id = ?", (message.from_user.id,))
        if user['coins'] < cost:
            await message.answer(f"❌ Недостаточно шекелей! Нужно {cost} 💰, а у вас {user['coins']} 💰.")
        else:
            await execute_db("UPDATE users SET coins = coins - ?, robux = robux + ? WHERE id = ?", (cost, amt_r, message.from_user.id))
            await message.answer(f"✅ Вы успешно купили <b>{amt_r} R$</b> за {cost} Шекелей!")
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
    finally:
        await state.clear()
        
@dp.callback_query(F.data == "don_main")
async def cb_don_main(callback: types.CallbackQuery):
    text = (
        "💎 <b>ДОНАТ МАГАЗИН</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Здесь вы можете приобрести премиум-бонусы для вашего аккаунта! Поддержите разработку бота.\n\n"
        "Вы можете оплачивать покупки с помощью <b>R$ (Робуксов)</b> или через <b>Telegram Stars ⭐️</b>.\n"
        "Также вы можете порадовать друзей и купить им геймпасс в подарок!\n\n"
        "<i>Выберите категорию:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 F2P Магазин (За Робуксы)", callback_data="don_f2p_menu")],
        [InlineKeyboardButton(text="⭐️ P2W Магазин (За Stars)", callback_data="don_p2w_menu")],
        [InlineKeyboardButton(text="💳 Купить Робуксы (R$)", callback_data="don_buy_robux")],
        [InlineKeyboardButton(text="🃏 Донат-Юниты", callback_data="don_units_menu")]
    ])
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data == "don_f2p_menu")
async def cb_don_f2p_menu(callback: types.CallbackQuery):
    user = await fetch_one("SELECT robux FROM users WHERE id = ?", (callback.from_user.id,))
    text = (
        f"🟢 <b>F2P МАГАЗИН (Оплата Робуксами R$)</b>\n"
        f"Ваш баланс: <b>{user['robux']} R$</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите геймпасс для покупки:\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Навсегда Х2 Шекели (129 R$)", callback_data="don_buy_f2p_x2coins")],
        [InlineKeyboardButton(text="🎟 Навсегда Х2 Опыт БП (159 R$)", callback_data="don_buy_f2p_x2xp")],
        [InlineKeyboardButton(text="🃏 5-й Слот Юнита (159 R$)", callback_data="don_buy_f2p_slot5")],
        [InlineKeyboardButton(text="🍀 Навсегда Х1.5 Удача (129 R$)", callback_data="don_buy_f2p_luck")],
        [InlineKeyboardButton(text="👑 VIP Статус (339 R$)", callback_data="don_buy_f2p_vip")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="don_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "don_p2w_menu")
async def cb_don_p2w_menu(callback: types.CallbackQuery):
    text = (
        f"⭐️ <b>P2W МАГАЗИН (Оплата Telegram Stars)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите геймпасс для покупки:\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Навсегда Х2 Шекели (69 ⭐️)", callback_data="don_buy_p2w_x2coins")],
        [InlineKeyboardButton(text="🎟 Навсегда Х2 Опыт БП (69 ⭐️)", callback_data="don_buy_p2w_x2xp")],
        [InlineKeyboardButton(text="🃏 5-й Слот Юнита (79 ⭐️)", callback_data="don_buy_p2w_slot5")],
        [InlineKeyboardButton(text="🍀 Навсегда Х1.5 Удача (59 ⭐️)", callback_data="don_buy_p2w_luck")],
        [InlineKeyboardButton(text="👑 VIP Статус (179 ⭐️)", callback_data="don_buy_p2w_vip")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="don_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("don_buy_"))
async def cb_don_buy_init(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    currency = parts[2] # f2p or p2w
    item = parts[3]
    
    await state.update_data(donate_curr=currency, donate_item=item)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Купить себе", callback_data=f"don_target_self")],
        [InlineKeyboardButton(text="🎁 Купить в подарок", callback_data=f"don_target_gift")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="don_main")]
    ])
    
    await callback.message.edit_text("Кому вы хотите приобрести этот геймпасс?", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "don_target_self")
async def cb_don_target_self(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(donate_target_id=callback.from_user.id)
    await execute_donate_flow(callback.message, callback.from_user.id, state, is_callback=True)

@dp.callback_query(F.data == "don_target_gift")
async def cb_don_target_gift(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎁 <b>ПОДАРОК</b>\nВведите ID или @username игрока, которому хотите подарить геймпасс:")
    await state.set_state(DonateState.gift_target)
    await callback.answer()

@dp.message(DonateState.gift_target)
async def process_donate_gift_target(message: types.Message, state: FSMContext):
    val = message.text.strip()
    target_user = None
    if val.isdigit(): target_user = await fetch_one("SELECT * FROM users WHERE id = ?", (int(val),))
    else: target_user = await fetch_one("SELECT * FROM users WHERE username = ?", (val.lstrip('@'),))
        
    if not target_user: 
        return await message.answer("❌ Игрок не найден в базе данных.")
    
    await state.update_data(donate_target_id=target_user['id'])
    await execute_donate_flow(message, message.from_user.id, state, is_callback=False)

async def execute_donate_flow(trigger_msg, buyer_id, state: FSMContext, is_callback=False):
    data = await state.get_data()
    currency = data['donate_curr']
    item = data['donate_item']
    target_id = data['donate_target_id']
    
    f2p_prices = {"x2coins": 129, "x2xp": 159, "slot5": 159, "luck": 129, "vip": 339}
    p2w_prices = {"x2coins": 69, "x2xp": 69, "slot5": 79, "luck": 59, "vip": 179}
    item_names = {"x2coins": "Навсегда Х2 Шекели", "x2xp": "Навсегда Х2 Опыт БП", "slot5": "5-й Слот Юнита", "luck": "Навсегда Х1.5 Удача", "vip": "VIP Статус"}
    
    target_user = await fetch_one("SELECT * FROM users WHERE id = ?", (target_id,))
    if not target_user:
        msg = "❌ Ошибка: Целевой игрок не найден."
        if not is_callback: await trigger_msg.answer(msg)
        else: await trigger_msg.edit_text(msg)
        return await state.clear()
        
    target_name = get_display_name(target_user)
    
    pass_col = f"pass_{item}"
    if target_user.get(pass_col, 0) == 1:
        msg = f"❌ Ошибка: У игрока {target_name} уже есть этот геймпасс!"
        if not is_callback: await trigger_msg.answer(msg)
        else: await trigger_msg.edit_text(msg)
        return await state.clear()

    if currency == "f2p":
        price = f2p_prices[item]
        buyer = await fetch_one("SELECT robux FROM users WHERE id = ?", (buyer_id,))
        if buyer['robux'] < price:
            msg = f"❌ Недостаточно Робуксов! Нужно {price} R$, а у вас {buyer['robux']} R$."
            if not is_callback: await trigger_msg.answer(msg)
            else: await trigger_msg.edit_text(msg)
            return await state.clear()
            
        cb_data_str = f"donf2p_cfm_{item}_{target_id}" 
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить покупку", callback_data=cb_data_str)],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="don_main")]
        ])
        
        text = f"🛒 <b>ПОДТВЕРЖДЕНИЕ</b>\n\nТовар: <b>{item_names[item]}</b>\nПолучатель: <b>{target_name}</b>\nЦена: <b>{price} R$</b>"
        if not is_callback: await trigger_msg.answer(text, reply_markup=kb)
        else: await trigger_msg.edit_text(text, reply_markup=kb)
        
    elif currency == "p2w":
        price_stars = p2w_prices[item]
        payload = f"donp2w_{item}_{target_id}"
        pass_name = item_names[item]
        target_str = "для себя" if buyer_id == target_id else f"в подарок для {target_name}"
        label_text = f"{pass_name} ({target_str})"
        
        prices = [LabeledPrice(label=label_text, amount=price_stars)]
        desc = f"Покупка {pass_name} {target_str}."
        try:
            await bot.send_invoice(
                chat_id=buyer_id,
                title="Премиум Геймпасс",
                description=desc,
                payload=payload,
                provider_token="", 
                currency="XTR",
                prices=prices
            )
            if is_callback: await trigger_msg.delete()
        except Exception as e:
            msg = f"❌ Ошибка отправки счета: {e}"
            if not is_callback: await trigger_msg.answer(msg)
            else: await trigger_msg.edit_text(msg)
            
    await state.clear()

@dp.callback_query(F.data.startswith("donf2p_cfm_"))
async def cb_don_confirm_f2p(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    item = parts[2]
    target_id = int(parts[3])
    buyer_id = callback.from_user.id
    
    f2p_prices = {"x2coins": 129, "x2xp": 159, "slot5": 159, "luck": 129, "vip": 339}
    item_names = {"x2coins": "Навсегда Х2 Шекели", "x2xp": "Навсегда Х2 Опыт БП", "slot5": "5-й Слот Юнита", "luck": "Навсегда Х1.5 Удача", "vip": "VIP Статус"}
    price = f2p_prices[item]
    
    db = await get_db_connection()
    try:
        await db.execute("BEGIN EXCLUSIVE")
        buyer = await db.execute("SELECT robux FROM users WHERE id = ?", (buyer_id,))
        b_row = await buyer.fetchone()
        if not b_row or b_row['robux'] < price:
            raise ValueError("No money")
            
        target = await db.execute(f"SELECT pass_{item} FROM users WHERE id = ?", (target_id,))
        t_row = await target.fetchone()
        if not t_row or t_row[f"pass_{item}"] == 1:
            raise ValueError("Already has")
            
        await db.execute("UPDATE users SET robux = robux - ? WHERE id = ?", (price, buyer_id))
        await db.execute(f"UPDATE users SET pass_{item} = 1 WHERE id = ?", (target_id,))
        await db.commit()
        success = True
    except ValueError as e:
        await db.execute("ROLLBACK")
        success = False
        err = str(e)
    finally:
        await db.close()
        
    if success:
        await callback.message.edit_text("✅ <b>Оплата прошла успешно! Геймпасс выдан.</b>")
        if buyer_id != target_id:
            buyer_info = await fetch_one("SELECT * FROM users WHERE id = ?", (buyer_id,))
            try:
                await bot.send_message(target_id, f"🎁 <b>ВАМ ПОДАРОК!</b>\nИгрок <b>{get_display_name(buyer_info)}</b> подарил вам геймпасс: <b>{item_names[item]}</b>!\nПриятной игры!")
            except: pass
    else:
        if err == "No money": await callback.answer("❌ Недостаточно R$!", show_alert=True)
        else: await callback.answer("❌ Игрок уже имеет этот геймпасс!", show_alert=True)

@dp.pre_checkout_query(lambda query: query.invoice_payload.startswith("donp2w_") or query.invoice_payload.startswith("donunit_"))
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("donp2w_"):
        parts = payload.split("_")
        item = parts[1]
        target_id = int(parts[2])
        buyer_id = message.from_user.id
        
        item_names = {"x2coins": "Навсегда Х2 Шекели", "x2xp": "Навсегда Х2 Опыт БП", "slot5": "5-й Слот Юнита", "luck": "Навсегда Х1.5 Удача", "vip": "VIP Статус"}
        
        await execute_db(f"UPDATE users SET pass_{item} = 1 WHERE id = ?", (target_id,))
        await message.answer(f"⭐️ <b>Оплата через Telegram Stars прошла успешно!</b>\nГеймпасс выдан.")
        
        if buyer_id != target_id:
            buyer_info = await fetch_one("SELECT * FROM users WHERE id = ?", (buyer_id,))
            try:
                await bot.send_message(target_id, f"🎁 <b>ВАМ ПОДАРОК!</b>\nИгрок <b>{get_display_name(buyer_info)}</b> оплатил для вас геймпасс: <b>{item_names[item]}</b>!\nПриятной игры!")
            except: pass

    elif payload.startswith("donunit_"):
        parts = payload.split("_")
        unit_id = int(parts[1])
        buyer_id = message.from_user.id
        
        unit = await fetch_one("SELECT card_id FROM donate_units WHERE id = ?", (unit_id,))
        if unit:
            card = await fetch_one("SELECT * FROM cards WHERE id = ?", (unit['card_id'],))
            if card:
                _, serial, _ = await give_card_to_user(buyer_id, card['id'], "Normal", card['rarity'])
                await message.answer(f"⭐️ <b>Оплата через Telegram Stars прошла успешно!</b>\nДонат-юнит <b>{card['name']}</b> выдан в ваш инвентарь!")

@dp.callback_query(F.data == "don_units_menu")
async def cb_don_units_menu(callback: types.CallbackQuery):
    units = await fetch_all("SELECT d.id, d.price_robux, d.price_stars, c.name, c.rarity FROM donate_units d JOIN cards c ON d.card_id = c.id")
    if not units:
        return await callback.answer("Донат-юнитов пока нет в продаже.", show_alert=True)
        
    text = "🃏 <b>ЭКСКЛЮЗИВНЫЕ ДОНАТ-ЮНИТЫ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nЗдесь продаются особые карты напрямую!\n\n"
    kb = []
    for u in units:
        kb.append([InlineKeyboardButton(text=f"Купить: {u['name']}", callback_data=f"buy_don_unit_{u['id']}")])
        text += f"🔹 <b>{u['name']}</b> ({format_rarity_display(u['rarity'])})\n   └ 💵 {u['price_robux']} R$  |  ⭐️ {u['price_stars']} Stars\n\n"
        
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="don_main")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_don_unit_"))
async def cb_buy_don_unit(callback: types.CallbackQuery):
    unit_id = int(callback.data.split("_")[3])
    unit = await fetch_one("SELECT d.id, d.price_robux, d.price_stars, c.name FROM donate_units d JOIN cards c ON d.card_id = c.id WHERE d.id = ?", (unit_id,))
    if not unit: return await callback.answer("Юнит не найден.", show_alert=True)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Купить за {unit['price_robux']} R$", callback_data=f"cfmbuy_dunit_r_{unit['id']}")],
        [InlineKeyboardButton(text=f"Купить за {unit['price_stars']} ⭐️", callback_data=f"cfmbuy_dunit_s_{unit['id']}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="don_units_menu")]
    ])
    await callback.message.edit_text(f"🛒 <b>Покупка Донат-Юнита</b>\nВы выбрали: <b>{unit['name']}</b>\nВыберите способ оплаты:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("cfmbuy_dunit_r_"))
async def cb_buy_don_unit_robux(callback: types.CallbackQuery):
    unit_id = int(callback.data.split("_")[3])
    user_id = callback.from_user.id
    
    db = await get_db_connection()
    try:
        await db.execute("BEGIN EXCLUSIVE")
        user = await db.execute("SELECT robux FROM users WHERE id = ?", (user_id,))
        u_row = await user.fetchone()
        
        unit = await db.execute("SELECT d.price_robux, d.card_id, c.name, c.rarity FROM donate_units d JOIN cards c ON d.card_id = c.id WHERE d.id = ?", (unit_id,))
        un_row = await unit.fetchone()
        
        if not un_row: raise ValueError("Unit missing")
        if not u_row or u_row['robux'] < un_row['price_robux']: raise ValueError("No R$")
            
        await db.execute("UPDATE users SET robux = robux - ? WHERE id = ?", (un_row['price_robux'], user_id))
        await db.commit()
        success = True
    except ValueError as e:
        await db.execute("ROLLBACK")
        success = False
        err = str(e)
    finally:
        await db.close()
        
    if success:
        _, serial, _ = await give_card_to_user(user_id, un_row['card_id'], "Normal", un_row['rarity'])
        await callback.message.edit_text(f"✅ <b>Успешно куплено за Робуксы!</b>\nЮнит <b>{un_row['name']}</b> добавлен в инвентарь!")
    else:
        await callback.answer("❌ Недостаточно R$!", show_alert=True)

@dp.callback_query(F.data.startswith("cfmbuy_dunit_s_"))
async def cb_buy_don_unit_stars(callback: types.CallbackQuery):
    unit_id = int(callback.data.split("_")[3])
    buyer_id = callback.from_user.id
    
    unit = await fetch_one("SELECT d.price_stars, c.name FROM donate_units d JOIN cards c ON d.card_id = c.id WHERE d.id = ?", (unit_id,))
    if not unit: return await callback.answer("Ошибка БД", show_alert=True)
    
    payload = f"donunit_{unit_id}"
    label_text = f"Донат-Юнит: {unit['name']}"
    prices = [LabeledPrice(label=label_text, amount=unit['price_stars'])]
    
    try:
        await bot.send_invoice(
            chat_id=buyer_id,
            title="Эксклюзивный Юнит",
            description=f"Покупка {unit['name']} для вашей коллекции.",
            payload=payload,
            provider_token="", 
            currency="XTR",
            prices=prices
        )
        await callback.message.delete()
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка отправки счета: {e}")

@dp.message(Command("profile"), F.chat.type == "private")
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
    
    bp_text = "<i>Нет активного Батл-пасса</i>"
    if active_bp:
        bp_text = f"<b>{active_bp['title']}</b> (Ур. {active_bp['level']} | {active_bp['xp']} XP)"

    bal_str = f"💰 <b>Шекелей:</b> {user['coins']}\n💵 <b>Робуксов (R$):</b> {user['robux']}"
    tr_str = user['trophies']
    
    text = (
        f"👤 Профиль игрока <b>{name}</b>{title_str}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎖 <b>Ранг:</b> {rank['name']}\n🏆 <b>Кубки:</b> {tr_str}\n{bal_str}\n"
        f"🃏 <b>Всего карт:</b> {total_cards['s'] or 0}\n🎟 <b>Активный БП:</b> {bp_text}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    text += (
        f"🔮 <b>Гарант на Мифик:</b> {make_progress_bar(user['pity_mythic'], 1000, 8)} ({user['pity_mythic']}/1000)\n"
        f"🌠 <b>Гарант на Супер:</b> {make_progress_bar(user['pity_super'], 10000, 8)} ({user['pity_super']}/10000)\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
        
    text += "⚔️ <b>Экипировка:</b>\n"
    
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user.get('pass_5th_slot') == 1:
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
                mut_str = " 🌈" if row['mutation'] == "Rainbow" else (" 💎" if row['mutation'] == "Diamond" else (" ⭐" if row['mutation'] == 'Gold' else ""))
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

@dp.message(F.text == BTN_BP)
async def cmd_bp_menu(message: types.Message):
    if await check_ban(message.from_user.id): return
    uid = message.from_user.id
    active_bp = await fetch_one("SELECT ub.bp_id, ub.level, ub.xp, b.title, b.photo_id FROM user_bp ub JOIN battle_passes b ON ub.bp_id = b.id WHERE ub.user_id = ? AND ub.is_active = 1", (uid,))
    
    if active_bp:
        text = f"🎟 <b>БАТЛ-ПАСС: {active_bp['title']}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВаш уровень: <b>{active_bp['level']}</b>\nОпыт: <b>{active_bp['xp']} XP</b>\n\nОпыт дается за бои. Повышайте уровень, чтобы получать награды!"
        # В реальной системе здесь будет пагинация наград.
        await message.answer(text)
    else:
        passes = await fetch_all("SELECT * FROM battle_passes ORDER BY id DESC LIMIT 5")
        if not passes:
            return await message.answer("🎟 Сейчас нет активных сезонов Батл-Пасса.")
            
        text = "🎟 <b>ДОСТУПНЫЕ БАТЛ-ПАССЫ</b>\nВыберите сезон для активации:\n"
        kb = []
        for p in passes:
            kb.append([InlineKeyboardButton(text=f"Активировать: {p['title']}", callback_data=f"bp_act_{p['id']}")])
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("bp_act_"))
async def cb_bp_activate(callback: types.CallbackQuery):
    bp_id = int(callback.data.split("_")[2])
    uid = callback.from_user.id
    
    await execute_db("UPDATE user_bp SET is_active = 0 WHERE user_id = ?", (uid,))
    await execute_db("""
        INSERT INTO user_bp (user_id, bp_id, xp, level, is_active) VALUES (?, ?, 0, 1, 1)
        ON CONFLICT(user_id, bp_id) DO UPDATE SET is_active = 1
    """, (uid, bp_id))
    
    await callback.message.edit_text("✅ Вы успешно активировали этот Батл-Пасс! Играйте в бои, чтобы качать уровень.")
    await callback.answer()

@dp.message(Command("shop"))
@dp.message(F.text == BTN_SHOP)
async def cmd_shop(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT coins, pass_vip FROM users WHERE id = ?", (message.from_user.id,))
    items = await fetch_all("SELECT * FROM shop_items WHERE stock > 0")
    
    if not items:
        return await message.answer("🛒 <b>Магазин пока пуст.</b>\nЗавоз осуществляется каждые полтора часа. Жди уведомления!")
        
    bal = user['coins']
    val_sym = "💰"
    val_name = "Шекелей"
    discount = 0.9 if user['pass_vip'] == 1 else 1.0
    
    text = f"🛒 <b>ГЛОБАЛЬМАГАЗИН</b>\n{val_sym} Твой баланс: <b>{bal} {val_name}</b>\n<i>(Товары общие для всех. Кто успел, тот и купил!)</i>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    kb = []
    for i, item in enumerate(items, 1):
        final_price = int(item['price'] * discount)
        disc_str = f" <s>{item['price']}</s>" if discount < 1.0 else ""
        text += f"📦 <b>{item['name']}</b>\n      └ 💵 Цена: <b>{final_price}{disc_str} {val_sym}</b> | Остаток: <b>{item['stock']} шт.</b>\n\n"
        kb.append([InlineKeyboardButton(text=f"Купить: {item['name']} ({final_price} {val_sym})", callback_data=f"buy_shop_{item['id']}")])
        
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("buy_shop_"))
async def callback_buy_shop(callback: types.CallbackQuery):
    shop_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    user = await fetch_one("SELECT coins, pity_mythic, pity_super, pass_vip FROM users WHERE id = ?", (user_id,))
    item = await fetch_one("SELECT * FROM shop_items WHERE id = ?", (shop_id,))
    
    if not item or item['stock'] <= 0: return await callback.answer("❌ Этот товар закончился!", show_alert=True)
    
    discount = 0.9 if user['pass_vip'] == 1 else 1.0
    final_price = int(item['price'] * discount)
    
    if user['coins'] < final_price: return await callback.answer("❌ Недостаточно средств!", show_alert=True)
    
    await execute_db(f"UPDATE users SET coins = coins - ? WHERE id = ?", (final_price, user_id))
    await execute_db("UPDATE shop_items SET stock = stock - 1 WHERE id = ?", (shop_id,))
    
    await add_quest_progress_new(user_id, 'q_shop_buy', 1)
    
    i_type = item['item_type']
    if i_type.endswith("_rnd"):
        count = int(i_type.split("_")[0])
        won = await give_multiple_cards(user_id, count)
        
        await add_quest_progress_new(user_id, 'q_open', count)
            
        pity_pulls = [c for c in won if c.get('is_pity')]
        
        if count == 1: 
            mut_str = "🌈 " if won[0]['mutation'] == 'Rainbow' else ("💎 " if won[0]['mutation'] == 'Diamond' else ("⭐ " if won[0]['mutation'] == 'Gold' else ""))
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
        
        query = "SELECT * FROM cards WHERE rarity = ? AND id NOT IN (SELECT card_id FROM seed_pack_cards)"
        
        all_cards = await fetch_all(query, (target_rarity,))
        if not all_cards:
            await execute_db(f"UPDATE users SET coins = coins + ? WHERE id = ?", (final_price, user_id))
            return await callback.message.answer("❌ Ошибка БД.")
            
        won_card = random.choice(all_cards)
        mut = roll_mutation()
        _, serial, _ = await give_card_to_user(user_id, won_card['id'], mut, won_card['rarity'])
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

    await log_user_action(user_id, f"Купил в магазине: {i_type} ({final_price})")

    items = await fetch_all("SELECT * FROM shop_items WHERE stock > 0")
    if not items:
        await callback.message.edit_text("🛒 <b>Магазин полностью распродан!</b>\nЖдите следующего завоза.")
    else:
        new_val = user['coins'] - final_price
        val_sym = "💰"
        val_name = "Шекелей"
        text = f"🛒 <b>ГЛОБАЛЬНЫЙ МАГАЗИН</b>\n{val_sym} Твой баланс: <b>{new_val} {val_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        kb = []
        for i, itm in enumerate(items, 1):
            i_final_price = int(itm['price'] * discount)
            disc_str = f" <s>{itm['price']}</s>" if discount < 1.0 else ""
            text += f"📦 <b>{itm['name']}</b>\n      └ 💵 Цена: <b>{i_final_price}{disc_str} {val_sym}</b> | Остаток: <b>{itm['stock']} шт.</b>\n\n"
            kb.append([InlineKeyboardButton(text=f"Купить: {itm['name']} ({i_final_price} {val_sym})", callback_data=f"buy_shop_{itm['id']}")])
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
    actual_cooldown = int(base_cooldown / cd_mult)
    now = time.time()
    passed = now - user['last_getcard']
    
    if passed < actual_cooldown:
        left = int(actual_cooldown - passed)
        mins, secs = divmod(left, 60)
        return await message.answer(f"⏳ <b>Колода перемешивается!</b>\nОжидай: <b>{mins} мин. {secs} сек.</b>")
        
    won_list = await give_multiple_cards(user['id'], 1)
    if not won_list: return await message.answer("😔 В базе нет карт для этой гачи.")
    won_card = won_list[0]
        
    await execute_db(f"UPDATE users SET last_getcard = ? WHERE id = ?", (now, user['id']))
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
    if won_card.get('is_pity'):
        msg += f"🌟 <b>СИСТЕМА PITY! ГАРАНТИРОВАННЫЙ {won_card['pity_type']}!</b> 🌟\n\n"
        
    msg += f"🎉 <b>ВЫ ВЫБИЛИ КАРТУ!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n{mut_str}🃏 <b>Карта:</b> {n_fmt}\n💎 <b>Редкость:</b> {rarity_text}\n"
    
    if won_card['class_type'] == 'Booster': 
        msg += f"✨ <b>Класс:</b> БУСТЕР\n   └ Бафф DMG: <b>x{round(won_card['booster_dmg_mult']*mult, 2)}</b> | HP: <b>x{round(won_card['booster_hp_mult']*mult, 2)}</b>\n"
    elif won_card['class_type'] == 'Healer':
        msg += f"💗 <b>Класс:</b> ЦЕЛИТЕЛЬ\n   └ Лечение: <b>{int(won_card['damage']*mult)}</b> | ❤️ Здоровье: <b>{int(won_card['hp']*mult)}</b>\n"
    else: 
        msg += f"⚔️ <b>Класс:</b> БОЕЦ ({CLASS_EMOJI.get(won_card['class_type'], '')})\n   └ Урон: <b>{int(won_card['damage']*mult)}</b> | ❤️ Здоровье: <b>{int(won_card['hp']*mult)}</b>\n"
        
    if luck_mult > 1.0 and won_card['drop_chance'] < 15.0:
        msg += f"\n🍀 <i>Сработал множитель удачи!</i>"
        
    await message.answer_photo(photo=won_card['photo_id'], caption=msg)

async def get_index_text(user_id: int, page: int = 0, items_per_page: int = 8):
    query = "SELECT * FROM cards WHERE rarity != 'Secret'"
    all_cards = await fetch_all(query)
    user_inv = await fetch_all("SELECT DISTINCT card_id FROM inventory WHERE user_id = ?", (user_id,))
    user_card_ids = [item['card_id'] for item in user_inv]
    recipes = await fetch_all("SELECT target_card_id FROM craft_recipes")
    crafted_ids = [r['target_card_id'] for r in recipes]
    
    if not all_cards: return "Индекс пуст.", None
    
    luck_mult, _ = await get_active_events(user_id)
    weights_dict, total_w = await calculate_chance_weights(luck_mult)
    
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
    
    text = f"📖 <b>ИНДЕКС КАРТ (Стр. {page+1}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if luck_mult > 1.0: text += f"🍀 <b>Активен множитель удачи (x{luck_mult})! Шансы пересчитаны!</b>\n\n"
    
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
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"idx_page_{page-1}"))
    if total_pages > 1: nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"idx_page_{page+1}"))
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
        WHERE i.user_id = ? AND i.count > 0
    """, (user_id,))
    
    toggle_row = [
        InlineKeyboardButton(text=f"🎒 Карты (Выбрано)", callback_data="ignore"),
        InlineKeyboardButton(text=f"📦 Сид-Паки", callback_data=f"inv_packs_menu")
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
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

@dp.message(F.text == BTN_SIGN)
async def cmd_sign_card(message: types.Message):
    if await check_ban(message.from_user.id): return
    if not await is_signer(message.from_user.id): return
    if message.from_user.id in user_trades: return await message.answer("❌ Завершите обмен перед подписыванием карт!")
    
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
        return await callback.answer("Ошибка.", show_alert=True)
    finally:
        await db.close()
        
    await callback.message.delete()
    await callback.message.answer("✍️✅ <b>Успешно подписано!</b>")
    await callback.answer()

def get_equip_main_keyboard(user_info, cards_info):
    kb = []
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user_info.get('pass_5th_slot') == 1:
        slots.append('equip5')
        
    for i, slot in enumerate(slots, 1):
        inv_id = user_info[slot]
        sl_t = f"Слот {i}"
        text = f"{sl_t} [Пусто]" if inv_id == 0 else f"{sl_t}: {cards_info.get(inv_id, f'ID: {inv_id}')}"
        kb.append([InlineKeyboardButton(text=text, callback_data=f"eq_select_{i}")])
    kb.append([InlineKeyboardButton(text="❌ Очистить колоду", callback_data=f"eq_clear")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("equip"))
@dp.message(F.text == BTN_EQ)
async def cmd_equip(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (message.from_user.id,))
    if not user: return await message.answer("/start")
    
    if message.from_user.id in user_trades: return await message.answer("❌ Завершите обмен перед экипировкой!")
    
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user.get('pass_5th_slot') == 1: slots.append('equip5')
        
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
            
    header = "🛡 <b>БОЕВАЯ КОЛОДА</b>"
    await message.answer(f"{header}\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите слот:", reply_markup=get_equip_main_keyboard(user, cards_info))

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
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0
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
        WHERE i.user_id = ? AND i.card_id = ? AND i.count > 0
    """, (callback.from_user.id, card_id))
    
    if not invs: return await callback.answer("Карта пропала!", show_alert=True)
    
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
    if user.get('pass_5th_slot') == 1: slots.append('equip5')
        
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

async def get_team_data(user_id: int):
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    team = []
    slots = ['equip1', 'equip2', 'equip3', 'equip4']
    if user.get('pass_5th_slot') == 1: slots.append('equip5')
        
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
                
                if user.get('mod_player_shield') == 1:
                    card['shield'] = int(card['max_hp'] * 0.5)
                    
                team.append(card)
            else:
                await execute_db(f"UPDATE users SET {slot} = 0 WHERE id = ?", (user_id,))
    return team

async def get_bot_team(user_id: int, difficulty_mult: float, rank_name: str, diff_type: str = "med"):
    # Фильтруем забаненные для ИИ карты
    all_cards = await fetch_all("SELECT id, name, rarity, class_type, damage, hp, booster_dmg_mult, booster_hp_mult FROM cards WHERE rarity != 'Secret' AND id NOT IN (SELECT card_id FROM ai_banned_cards)")
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
            rainbow_prob = min(0.01, 0.005 * difficulty_mult)
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
        if c.get('shield', 0) > 0: status += "🛡"
        if c['class_type'] == 'Booster': status += "🔋"
        if c['class_type'] == 'Healer': status += "💗"
        
        s_str = f" [#{c['serial_number']:04d}]" if c.get('serial_number', 0) > 0 else ""
        sgn_str = ""
        if c.get('signed_by', 0) > 0:
            s_name = c.get('signer_name') or f"ID:{c['signed_by']}"
            sgn_str = f" ✍️ Sign: {s_name}"
            
        sh_text = f"+{c['shield']}🛡" if c.get('shield', 0) > 0 else ""
        
        if c['class_type'] == 'Healer':
            heal_val = int((c['damage'] + c.get('dmg_buff', 0)) * c.get('heal_power_mult', 1.0))
            res.append(f"• {html.escape(c['name'])}{s_str}{sgn_str}{status} (💗{heal_val} | ❤️{c['hp']}/{c['max_hp']}{sh_text})")
        else:
            dmg = c['damage'] + c.get('dmg_buff', 0)
            res.append(f"• {html.escape(c['name'])}{s_str}{sgn_str}{status} (⚔️{dmg} | ❤️{c['hp']}/{c['max_hp']}{sh_text})")
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

async def process_burns_and_regen(team, team_name, log1, log2, mods=None, is_bot_team=False):
    for c in team:
        if c['hp'] > 0:
            if c.get('burn', 0) > 0:
                c['hp'] -= c['burn']
                ru_str = f"🔥 {team_name}: <b>{html.escape(c['name'])}</b> получает {c['burn']} урона от горения!"
                if c['hp'] <= 0:
                    c['hp'] = 0
                    ru_str += " ☠️ <i>Сгорел дотла!</i>"
                add_dual_log(log1, log2, ru_str)
                c['burn'] = 0
                
            if mods and is_bot_team and mods.get('mod_enemy_regen') == 1 and c['hp'] > 0:
                regen_amt = int(c['max_hp'] * 0.05)
                if c['hp'] + regen_amt > c['max_hp']:
                    regen_amt = c['max_hp'] - c['hp']
                if regen_amt > 0:
                    c['hp'] += regen_amt
                    add_dual_log(log1, log2, f"🩸 {team_name}: <b>{html.escape(c['name'])}</b> регенерирует {regen_amt} ХП!")

def apply_damage_to_target(target, dmg):
    actual_dmg = 0
    if target.get('shield', 0) > 0:
        if target['shield'] >= dmg:
            target['shield'] -= dmg
        else:
            actual_dmg = dmg - target['shield']
            target['shield'] = 0
            target['hp'] -= actual_dmg
    else:
        target['hp'] -= dmg
        actual_dmg = dmg
    return actual_dmg

async def execute_turn(atk_team, def_team, atk_name, def_name, log1, log2, force_attacker=None, force_target=None, mods=None, is_player_atk=False):
    await process_burns_and_regen(atk_team, atk_name, log1, log2, mods, is_bot_team=not is_player_atk)
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
    total_dmg_dealt = 0
    
    if c_type == "Booster":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
        
        dmg = max(10, int(target['max_hp'] * 0.1))
        actual = apply_damage_to_target(target, dmg)
        total_dmg_dealt += actual
        
        ru_str = f"🔋 {atk_name}: <b>{html.escape(atk['name'])}</b> пускает заряд в <b>{html.escape(target['name'])}</b> на {dmg}!"
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
                
            ru_str = f"💗 {atk_name}: <b>{html.escape(atk['name'])}</b> исцеляет союзника <b>{html.escape(target['name'])}</b> на {heal_amount} HP! (Эффективность: {int(curr_mult * 100)}%)"
            add_dual_log(log1, log2, ru_str)
            heals += 1
            
            atk['heal_power_mult'] = max(0.0, curr_mult - 0.03)
        else:
            if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
            else: target = random.choice(def_alive)
            
            dmg = max(5, int(base_dmg * 0.2))
            actual = apply_damage_to_target(target, dmg)
            total_dmg_dealt += actual
            
            ru_str = f"🎯 {atk_name}: Одинокий Хилер <b>{html.escape(atk['name'])}</b> бьет <b>{html.escape(target['name'])}</b> на {dmg}!"
            if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
            add_dual_log(log1, log2, ru_str)
        
    elif c_type == "AOE":
        ru_str = f"🌪 {atk_name}: <b>{html.escape(atk['name'])}</b> бьет по всем на {base_dmg}!"
        for d in def_alive:
            actual = apply_damage_to_target(d, base_dmg)
            total_dmg_dealt += actual
            if d['hp'] <= 0:
                d['hp'] = 0
                ru_str += f" ☠️ <i>{html.escape(d['name'])} мертв!</i>"
        add_dual_log(log1, log2, ru_str)
        
    elif c_type == "Splash":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: main_t = force_target
        else: main_t = random.choice(def_alive)
            
        splash_dmg = int(base_dmg * 0.5)
        ru_str = f"🌊 {atk_name}: <b>{html.escape(atk['name'])}</b> наносит {base_dmg} по <b>{html.escape(main_t['name'])}</b> и {splash_dmg} остальным!"
        for d in def_alive:
            dmg = base_dmg if d == main_t else splash_dmg
            actual = apply_damage_to_target(d, dmg)
            total_dmg_dealt += actual
            if d['hp'] <= 0:
                d['hp'] = 0
                ru_str += f" ☠️ <i>{html.escape(d['name'])} мертв!</i>"
        add_dual_log(log1, log2, ru_str)
        
    elif c_type == "Fire":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
            
        actual = apply_damage_to_target(target, base_dmg)
        total_dmg_dealt += actual
        target['burn'] = target.get('burn', 0) + base_dmg
        ru_str = f"🔥 {atk_name}: <b>{html.escape(atk['name'])}</b> бьет <b>{html.escape(target['name'])}</b> на {base_dmg} и поджигает!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
    else:
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
            
        actual = apply_damage_to_target(target, base_dmg)
        total_dmg_dealt += actual
        ru_str = f"🎯 {atk_name}: <b>{html.escape(atk['name'])}</b> наносит {base_dmg} по <b>{html.escape(target['name'])}</b>!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
    if total_dmg_dealt > 0 and mods:
        if is_player_atk and mods.get('mod_player_vampire') == 1 and atk['hp'] > 0:
            vamp_heal = int(total_dmg_dealt * 0.2)
            if vamp_heal > 0:
                atk['hp'] = min(atk['max_hp'], atk['hp'] + vamp_heal)
                add_dual_log(log1, log2, f"🦇 {atk_name}: <b>{html.escape(atk['name'])}</b> высасывает {vamp_heal} ХП!")
                
        if not is_player_atk and mods.get('mod_enemy_thorns') == 1 and atk['hp'] > 0:
            thorn_dmg = int(total_dmg_dealt * 0.1)
            if thorn_dmg > 0:
                atk['hp'] -= thorn_dmg
                th_ru = f"🌵 {def_name}: Шипы наносят <b>{html.escape(atk['name'])}</b> {thorn_dmg} урона отдачи!"
                if atk['hp'] <= 0: atk['hp'] = 0; th_ru += " ☠️ <i>Убился об шипы!</i>"
                add_dual_log(log1, log2, th_ru)
        
    return True, heals

async def get_dynamic_trophies(rank_name: str, rank_idx: int, diff_scale: float = 1.0) -> int:
    if "Uranium VI" in rank_name or "Uranium VII" in rank_name:
        return random.randint(1, 2)
    base = max(5, 18 - int((rank_idx / 25) * 12)) 
    won = random.randint(base, base+3)
    return int(won * diff_scale)

async def add_bp_xp(user_id: int, xp_to_add: int) -> tuple:
    user = await fetch_one("SELECT pass_x2_xp, pass_vip FROM users WHERE id = ?", (user_id,))
    if user:
        if user['pass_x2_xp'] == 1: xp_to_add = int(xp_to_add * 2.0)
        if user['pass_vip'] == 1: xp_to_add = int(xp_to_add * 1.5)

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

async def run_battle_loop(bot: Bot, chat_id: int, p1_id: int, p1_name: str, p2_id: int, p2_name: str, t1: list, t2: list, diff_trophies_scale: float = 1.0, diff_bp_mult: float = 1.0, is_pvp: bool = False, pvp_no_rewards: bool = False, mods=None, diff_type="med"):
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
            user_info = await fetch_one("SELECT pass_x2_coins, pass_vip FROM users WHERE id = ?", (p1_id,))
            x2_coins = user_info.get('pass_x2_coins') == 1 if user_info else False
            vip_pass = user_info.get('pass_vip') == 1 if user_info else False
            
            if is_pvp:
                await add_quest_progress_new(p1_id, 'q_pvp', 1)
                if p2_id != 0: 
                    await add_quest_progress_new(p2_id, 'q_pvp', 1)
            else:
                await add_quest_progress_new(p1_id, 'q_pve', 1)

            code_text = ""
            robux_drop_text = ""
            winner_user_id = None
            if winner == p1_name: winner_user_id = p1_id
            elif is_pvp and winner == p2_name: winner_user_id = p2_id

            if winner_user_id is not None and "Ничья" not in winner:
                if random.random() <= 0.05: 
                    db = await get_db_connection()
                    try:
                        code_row = await db.execute("SELECT code FROM reward_codes WHERE is_active=1 AND owner_id=0 ORDER BY RANDOM() LIMIT 1")
                        res = await code_row.fetchone()
                        if res:
                            found_code = res['code']
                            await db.execute("UPDATE reward_codes SET owner_id = ? WHERE code = ?", (winner_user_id, found_code))
                            await db.commit()
                            code_text = (
                                f"🎁 <b>ВЫПАЛ УНИКАЛЬНЫЙ КОД-НАГРАДА! (Шанс 5%)</b>\nНажми, чтобы скопировать: <code>{found_code}</code>\nАктивируй через /codereward\n\n"
                            )
                    except Exception as e: 
                        logging.error(f"Reward Code Drop Error: {e}")
                    finally: 
                        await db.close()
                
                if winner_user_id == p1_id and not is_pvp:
                    r_drop = 0
                    if diff_type == "easy" and random.random() <= 0.05: r_drop = 1
                    elif diff_type == "med" and random.random() <= 0.10: r_drop = 1
                    elif diff_type == "hard" and random.random() <= 0.20: r_drop = 2
                    elif diff_type == "nightmare" and random.random() <= 0.20: r_drop = 3
                    
                    if r_drop > 0:
                        await execute_db("UPDATE users SET robux = robux + ? WHERE id = ?", (r_drop, p1_id))
                        robux_drop_text = f"💎 <b>ВЫПАЛ ДОНАТ ДРОП! Вы получили {r_drop} R$!</b>\n\n"

            final_text = robux_drop_text + code_text + f"🏁 <b>ИТОГИ БОЯ: {p1_name} VS {p2_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n👑 <b>Победитель: {winner}</b>\n\n"
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
                    if mods.get('mod_enemy_regen'): mod_reward_mult += 0.2; mod_trophy_mult += 0.15
                    if mods.get('mod_enemy_thorns'): mod_reward_mult += 0.25; mod_trophy_mult += 0.2
                    if mods.get('mod_player_atk_all'): mod_reward_mult -= 0.4
                    if mods.get('mod_manual_atk'): mod_reward_mult -= 0.5
                    if mods.get('mod_player_hp'): mod_reward_mult -= 0.3
                    if mods.get('mod_player_vampire'): mod_reward_mult -= 0.3
                    if mods.get('mod_player_shield'): mod_reward_mult -= 0.25
                    
                mod_reward_mult = max(0.1, mod_reward_mult)
                coin_mult, xp_mult_event = await get_coin_xp_events()
                
                if x2_coins: coin_mult *= 2.0
                if vip_pass: coin_mult *= 1.5
                
                if winner == p1_name:
                    user_data = await fetch_one("SELECT trophies FROM users WHERE id = ?", (p1_id,))
                    user_trophies = user_data['trophies'] if user_data else 0
                    rank = await get_user_rank(user_trophies)
                    
                    coins_base = random.randint(25, 90) * rank['reward_mult'] * diff_trophies_scale * 0.85 * coin_mult
                    coins_won = int(coins_base * mod_reward_mult)
                    won_t_base = await get_dynamic_trophies(rank['name'], rank['rank_idx'], diff_trophies_scale)
                    won_t = int(won_t_base * mod_trophy_mult)
                    
                    await execute_db("UPDATE users SET coins = coins + ?, total_coins = total_coins + ?, trophies = trophies + ? WHERE id = ?", (coins_won, coins_won, won_t, p1_id))
                    
                    final_text += f"🎉 <b>Награды:</b>\n💰 {coins_won} Шекелей"
                    if coin_mult > 1.0: final_text += f" (Геймпасс/Ивент x{coin_mult})"
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
    elif diff_type == "med": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.0, 1.0, 1.0, "Средний 🟡"
    elif diff_type == "hard": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.5, 1.4, 1.2, "Сложный 🔴" 
    elif diff_type == "nightmare": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.9, 1.8, 1.5, "Кошмар ☠️"
        
    mods = {
        'mod_enemy_hp': user.get('mod_enemy_hp', 0),
        'mod_enemy_atk_all': user.get('mod_enemy_atk_all', 0),
        'mod_enemy_stats': user.get('mod_enemy_stats', 0),
        'mod_enemy_regen': user.get('mod_enemy_regen', 0),
        'mod_enemy_thorns': user.get('mod_enemy_thorns', 0),
        'mod_player_atk_all': user.get('mod_player_atk_all', 0),
        'mod_manual_atk': user.get('mod_manual_atk', 0),
        'mod_player_hp': user.get('mod_player_hp', 0),
        'mod_player_vampire': user.get('mod_player_vampire', 0),
        'mod_player_shield': user.get('mod_player_shield', 0)
    }

    try: await callback.message.edit_text(f"⚔️ <i>Ищем противника... Сложность: <b>{diff_name}</b></i>")
    except: pass
    
    team1 = await get_team_data(callback.from_user.id)
    rank = await get_user_rank(user['trophies'])
    
    team2 = await get_bot_team(callback.from_user.id, rank['difficulty_mult'] * power_mult, rank['name'], diff_type)
    if not team2: 
        try: await callback.message.edit_text("Error: no cards in DB")
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
    
    await log_user_action(callback.from_user.id, f"Начал PvE бой (сложность: {diff_type})")
    
    asyncio.create_task(run_battle_loop(bot, callback.message.chat.id, callback.from_user.id, p1_name, 0, f"AI ({diff_name})", team1, team2, trophies_scale, bp_xp_mult, is_pvp=False, mods=mods, diff_type=diff_type))
    await callback.answer()

@dp.message(F.text == BTN_PVP)
async def cmd_pvp_menu(message: types.Message):
    if await check_ban(message.from_user.id): return
    if message.from_user.id in active_combats or message.from_user.id in user_trades: return await message.answer("❌ Заняты!")
    
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
    
    if u_id in active_combats or u_id in user_trades: return await callback.answer("Заняты!", show_alert=True)
    t1 = await get_team_data(u_id)
    if not t1: return await callback.answer("Колода пуста!", show_alert=True)
    
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
        
        await log_user_action(u_id, f"Начал PvP бой (Автоподбор) против {opp_id}")
        await log_user_action(opp_id, f"Начал PvP бой (Автоподбор) против {u_id}")
        
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
    if target_user['id'] in active_combats or target_user['id'] in user_trades: return await message.answer("❌ Игрок занят!")

    challenger_name = get_display_name(user) + await get_user_titles_str(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Принять", callback_data=f"pvp_accept_{user['id']}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pvp_decline_{user['id']}")]
    ])
    
    try:
        await bot.send_message(target_user['id'], f"⚔️ <b>{challenger_name}</b> вызывает вас на дуэль!", reply_markup=kb)
        await message.answer("📨 Вызов отправлен.")
        await log_user_action(message.from_user.id, f"Бросил вызов на PvP игроку {target_user['id']}")
    except: await message.answer("Ошибка при отправке.")
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
        try: await callback.message.edit_text("Deck empty error.")
        except: pass
        return
        
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
                winner = p2_name; surrendered_players.discard((p1_id, battle_id))
                log1.append(f"🏳️ <b>{p1_name} сдался!</b>")
                log2.append(f"🏳️ <b>{p1_name} сдался!</b>")
                break
            elif (p2_id, battle_id) in surrendered_players:
                winner = p1_name; surrendered_players.discard((p2_id, battle_id))
                log1.append(f"🏳️ <b>{p2_name} сдался!</b>")
                log2.append(f"🏳️ <b>{p2_name} сдался!</b>")
                break

            t1_a = [c for c in t1 if c['hp'] > 0]
            t2_a = [c for c in t2 if c['hp'] > 0]
            if not t1_a and not t2_a: winner = "Ничья"; break
            elif not t1_a: winner = p2_name; break
            elif not t2_a: winner = p1_name; break
            if turn > 40: winner = "Ничья по раундам"; break

            did_turn, h = await execute_turn(t1, t2, p1_name, p2_name, log1, log2, is_player_atk=True)
            p1_heals += h
            if did_turn:
                if len(log1) > 6: log1 = log1[-6:]; log2 = log2[-6:]
                try: await safe_edit_text(msg1, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log1), reply_markup=get_battle_kb(battle_id))
                except Exception as e:
                    if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag=True; break
                try: await safe_edit_text(msg2, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log2), reply_markup=get_battle_kb(battle_id))
                except Exception as e:
                    if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag=True; break
                await battle_delay(battle_id, p1_id, p2_id)

            t2_a = [c for c in t2 if c['hp'] > 0]
            if t2_a:
                if time.time() - battle_start_time > 180:
                    timeout_flag = True
                    break
                    
                did_turn, h = await execute_turn(t2, t1, p2_name, p1_name, log1, log2, is_player_atk=True)
                p2_heals += h
                if did_turn:
                    if len(log1) > 6: log1 = log1[-6:]; log2 = log2[-6:]
                    try: await safe_edit_text(msg1, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log1), reply_markup=get_battle_kb(battle_id))
                    except Exception as e:
                        if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag=True; break
                    try: await safe_edit_text(msg2, build_battle_header(p1_name, t1, p2_name, t2) + "\n".join(log2), reply_markup=get_battle_kb(battle_id))
                    except Exception as e:
                        if "not found" in str(e).lower() or "deleted" in str(e).lower(): timeout_flag=True; break
                    await battle_delay(battle_id, p1_id, p2_id)
            turn += 1

        if timeout_flag:
            txt1 = "⏳ <b>Бой прерван (ошибка или тайм-аут).</b>"
            try: await msg1.edit_text(txt1)
            except: pass
            try: await msg2.edit_text(txt1)
            except: pass
            return

        try:
            await add_quest_progress_new(p1_id, 'q_pvp', 1)
            await add_quest_progress_new(p2_id, 'q_pvp', 1)

            code_text_1 = ""
            code_text_2 = ""
            winner_user_id = None
            
            if "Ничья" not in winner:
                if winner == p1_name: winner_user_id = p1_id
                elif winner == p2_name: winner_user_id = p2_id
                
            if winner_user_id is not None:
                if random.random() <= 0.05:
                    db = await get_db_connection()
                    try:
                        code_row = await db.execute("SELECT code FROM reward_codes WHERE is_active=1 AND owner_id=0 ORDER BY RANDOM() LIMIT 1")
                        res = await code_row.fetchone()
                        if res:
                            found_code = res['code']
                            await db.execute("UPDATE reward_codes SET owner_id = ? WHERE code = ?", (winner_user_id, found_code))
                            await db.commit()
                            dropped_msg = f"🎁 <b>ВЫПАЛ УНИКАЛЬНЫЙ КОД-НАГРАДА! (5%)</b>\nНажми, чтобы скопировать: <code>{found_code}</code>\nАктивируй через /codereward\n\n"
                            if winner_user_id == p1_id: code_text_1 = dropped_msg
                            else: code_text_2 = dropped_msg
                    except Exception as e:
                        logging.error(f"Reward Code Drop PvP Error: {e}")
                    finally:
                        await db.close()

            final1 = code_text_1 + f"🏁 <b>ИТОГИ: {p1_name} VS {p2_name}</b>\nПобедитель: {winner}\nДружеская дуэль (без наград)."
            final2 = code_text_2 + f"🏁 <b>ИТОГИ: {p1_name} VS {p2_name}</b>\nПобедитель: {winner}\nДружеская дуэль (без наград)."
            
            try: await msg1.edit_text(final1, reply_markup=None)
            except: pass
            try: await msg2.edit_text(final2, reply_markup=None)
            except: pass
        except Exception as e:
            logging.error(f"PVP Reward error: {e}")
            try: await msg1.edit_text("Ошибка при выдаче наград.", reply_markup=None)
            except: pass
            try: await msg2.edit_text("Ошибка при выдаче наград.", reply_markup=None)
            except: pass
        
    finally:
        active_combats.discard(p1_id)
        active_combats.discard(p2_id)

@dp.message(Command("trade"))
async def cmd_trade_request(message: types.Message, state: FSMContext):
    if await check_ban(message.from_user.id): return
    if message.from_user.id in active_combats or message.from_user.id in user_trades: return await message.answer("Заняты!")
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
        
    if not target_user: return await message.answer("Игрок не найден.")
    if target_user['id'] == message.from_user.id: return await message.answer("Самому себе нельзя!")
    if target_user['id'] in active_combats or target_user['id'] in user_trades: return await message.answer("Игрок занят!")

    challenger_name = get_display_name(user) + await get_user_titles_str(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"tr_acc_{user['id']}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"tr_dec_{user['id']}")]
    ])
    
    try:
        await bot.send_message(target_user['id'], f"🤝 <b>{challenger_name}</b> предлагает обмен!", reply_markup=kb)
        await message.answer("📨 Запрос отправлен.")
        await log_user_action(message.from_user.id, f"Отправил запрос на трейд игроку {target_user['id']}")
    except: await message.answer("Ошибка.")
    await state.clear()

@dp.callback_query(F.data.startswith("tr_acc_"))
async def callback_trade_accept(callback: types.CallbackQuery):
    p1_id = int(callback.data.split("_")[2])
    p2_id = callback.from_user.id
    if p1_id in user_trades or p2_id in user_trades or p1_id in active_combats or p2_id in active_combats: return await callback.answer("Заняты!", show_alert=True)
        
    p1 = await fetch_one("SELECT * FROM users WHERE id = ?", (p1_id,))
    p2 = await fetch_one("SELECT * FROM users WHERE id = ?", (p2_id,))
    
    trade_id = f"tr_{p1_id}_{p2_id}_{int(time.time())}"
    trade = {
        'id': trade_id, 'p1': p1_id, 'p2': p2_id,
        'p1_name': get_display_name(p1), 'p2_name': get_display_name(p2),
        'p1_offer': {}, 'p2_offer': {},  
        'p1_robux': 0, 'p2_robux': 0, 
        'p1_strings': {}, 'p2_strings': {}, 
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
    try: await bot.send_message(p1_id, "❌ Отклонено.")
    except: pass
    try: await callback.message.edit_text("❌ Отклонено.")
    except: pass
    await callback.answer()

async def render_trade_text(trade):
    text = "🤝 <b>ТОРГОВАЯ КОМНАТА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    text += f"🔵 <b>Предлагает {trade['p1_name']}:</b>\n"
    if trade['p1_robux'] > 0: text += f"  └ 💎 {trade['p1_robux']} R$\n"
    if not trade['p1_offer'] and trade['p1_robux'] == 0: text += "  └ <i>Ничего</i>\n"
    else:
        for inv_id, qty in trade['p1_offer'].items(): text += f"  └ {qty}x {trade['p1_strings'].get(inv_id, '?')}\n"
            
    text += f"\n🔴 <b>Предлагает {trade['p2_name']}:</b>\n"
    if trade['p2_robux'] > 0: text += f"  └ 💎 {trade['p2_robux']} R$\n"
    if not trade['p2_offer'] and trade['p2_robux'] == 0: text += "  └ <i>Ничего</i>\n"
    else:
        for inv_id, qty in trade['p2_offer'].items(): text += f"  └ {qty}x {trade['p2_strings'].get(inv_id, '?')}\n"
            
    r_str = "✅ Готов"
    w_str = "⏳ Выбирает..."
    p1_st = r_str if trade['p1_ready'] else w_str
    p2_st = r_str if trade['p2_ready'] else w_str
    
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>Статус:</b>\n"
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
            InlineKeyboardButton(text="➕ Карта", callback_data="tr_menu_add"),
            InlineKeyboardButton(text="💎 Робуксы", callback_data="tr_menu_add_robux"),
            InlineKeyboardButton(text="➖ Убрать", callback_data="tr_menu_rem")
        ])
        is_ready = trade['p1_ready'] if user_id == trade['p1'] else trade['p2_ready']
        if is_ready: kb.append([InlineKeyboardButton(text="⏳ Ждем партнера...", callback_data="ignore")])
        else: kb.append([InlineKeyboardButton(text="✅ ГОТОВ К ОБМЕНУ", callback_data="tr_action_ready")])
            
    kb.append([InlineKeyboardButton(text="❌ Отменить трейд", callback_data="tr_action_cancel")])
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
    if not trade_id or trade_id not in active_trades: return await callback.answer("Ошибка: Трейд не найден", show_alert=True)
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
        return await callback.answer("Вы отменили трейд.")
        
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

async def execute_trade_fixed(trade_id):
    trade = active_trades.pop(trade_id, None)
    if not trade: return
    user_trades.pop(trade['p1'], None)
    user_trades.pop(trade['p2'], None)
    
    db = await get_db_connection()
    try:
        await db.execute("BEGIN")
        
        p1_r = trade['p1_robux']
        p2_r = trade['p2_robux']
        
        u1 = await db.execute("SELECT robux FROM users WHERE id = ?", (trade['p1'],))
        u1_bal = await u1.fetchone()
        u2 = await db.execute("SELECT robux FROM users WHERE id = ?", (trade['p2'],))
        u2_bal = await u2.fetchone()
        
        if u1_bal['robux'] < p1_r or u2_bal['robux'] < p2_r:
            raise Exception("Not enough robux")
            
        async def transfer_items(from_u, to_u, offer):
            for i_id, qty in offer.items():
                cur = await db.execute("SELECT card_id, mutation, serial_number, signed_by, count FROM inventory WHERE id = ?", (i_id,))
                row = await cur.fetchone()
                if not row or row['count'] < qty: raise Exception("Not enough")
                
                if row['count'] == qty:
                    await db.execute("DELETE FROM inventory WHERE id = ?", (i_id,))
                    await db.execute("UPDATE users SET equip1 = 0 WHERE equip1 = ?", (i_id,))
                    await db.execute("UPDATE users SET equip2 = 0 WHERE equip2 = ?", (i_id,))
                    await db.execute("UPDATE users SET equip3 = 0 WHERE equip3 = ?", (i_id,))
                    await db.execute("UPDATE users SET equip4 = 0 WHERE equip4 = ?", (i_id,))
                    await db.execute("UPDATE users SET equip5 = 0 WHERE equip5 = ?", (i_id,))
                else:
                    await db.execute("UPDATE inventory SET count = count - ? WHERE id = ?", (qty, i_id))
                    
                cur2 = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = ? AND signed_by = ?", (to_u, row['card_id'], row['mutation'], row['serial_number'], row['signed_by']))
                dest = await cur2.fetchone()
                
                if dest: await db.execute("UPDATE inventory SET count = count + ? WHERE id = ?", (qty, dest['id']))
                else: await db.execute("INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by) VALUES (?, ?, ?, ?, ?, ?)", (to_u, row['card_id'], qty, row['mutation'], row['serial_number'], row['signed_by']))

        await transfer_items(trade['p1'], trade['p2'], trade['p1_offer'])
        await transfer_items(trade['p2'], trade['p1'], trade['p2_offer'])
        
        if p1_r > 0:
            await db.execute("UPDATE users SET robux = robux - ? WHERE id = ?", (p1_r, trade['p1']))
            await db.execute("UPDATE users SET robux = robux + ? WHERE id = ?", (p1_r, trade['p2']))
        if p2_r > 0:
            await db.execute("UPDATE users SET robux = robux - ? WHERE id = ?", (p2_r, trade['p2']))
            await db.execute("UPDATE users SET robux = robux + ? WHERE id = ?", (p2_r, trade['p1']))
            
        await db.commit()
        success = True
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Trade Error: {e}")
        success = False
    finally:
        await db.close()
        
    if success:
        await log_user_action(trade['p1'], f"Успешно завершил трейд с {trade['p2']}")
        await log_user_action(trade['p2'], f"Успешно завершил трейд с {trade['p1']}")
        try: await bot.edit_message_text("🎉 <b>ОБМЕН ЗАВЕРШЕН! Вещи переведены.</b>", chat_id=trade['p1'], message_id=trade['p1_msg'])
        except: pass
        try: await bot.edit_message_text("🎉 <b>ОБМЕН ЗАВЕРШЕН! Вещи переведены.</b>", chat_id=trade['p2'], message_id=trade['p2_msg'])
        except: pass
    else:
        try: await bot.edit_message_text("❌ ОШИБКА ОБМЕНА (предметы пропали или не хватает валюты).", chat_id=trade['p1'], message_id=trade['p1_msg'])
        except: pass
        try: await bot.edit_message_text("❌ ОШИБКА ОБМЕНА (предметы пропали или не хватает валюты).", chat_id=trade['p2'], message_id=trade['p2_msg'])
        except: pass

async def cancel_trade(trade_id, reason="Cancelled"):
    trade = active_trades.pop(trade_id, None)
    if not trade: return
    user_trades.pop(trade['p1'], None)
    user_trades.pop(trade['p2'], None)
    try: await bot.edit_message_text(f"❌ {reason}", chat_id=trade['p1'], message_id=trade['p1_msg'])
    except: pass
    try: await bot.edit_message_text(f"❌ {reason}", chat_id=trade['p2'], message_id=trade['p2_msg'])
    except: pass

@dp.callback_query(F.data == "tr_menu_add_robux")
async def cb_trade_add_robux(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    
    user = await fetch_one("SELECT robux FROM users WHERE id = ?", (user_id,))
    if user['robux'] <= 0: return await callback.answer("❌ У вас нет Робуксов (R$)!", show_alert=True)
    
    await callback.message.edit_text(f"💎 Ваш баланс: {user['robux']} R$\nВведите количество Робуксов для добавления в трейд:")
    await state.set_state(TradeState.waiting_robux)
    await callback.answer()

@dp.message(TradeState.waiting_robux)
async def process_trade_add_robux(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades:
        await state.clear()
        return await message.answer("Трейд не найден.")
        
    trade = active_trades[trade_id]
    user = await fetch_one("SELECT robux FROM users WHERE id = ?", (user_id,))
    
    try:
        amt = int(message.text)
        if amt < 0: raise ValueError
        if amt > user['robux']:
            await message.answer("У вас нет столько Робуксов!")
            return await state.clear()
            
        if user_id == trade['p1']: trade['p1_robux'] = amt
        else: trade['p2_robux'] = amt
        
        trade['p1_ready'] = False; trade['p2_ready'] = False
        trade['p1_confirmed'] = False; trade['p2_confirmed'] = False
        
        await message.delete()
        await update_trade_uis(trade)
    except ValueError:
        await message.answer("❌ Введите корректное число.")
    finally:
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
            mut = "💎 " if c['mutation'] == 'Diamond' else ("⭐ " if c['mutation'] == 'Gold' else ("🌈 " if c['mutation'] == 'Rainbow' else ""))
            items.append({"id": c['inv_id'], "btn_text": f"{mut}{n} ({avail})"})
            
    kb = get_pagination_keyboard(items, 0, "tr_add", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙", callback_data="tr_menu_main")])
    try: await callback.message.edit_text("👇 Выберите карту для добавления:", reply_markup=kb)
    except: pass
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
            mut = "💎 " if c['mutation'] == 'Diamond' else ("⭐ " if c['mutation'] == 'Gold' else ("🌈 " if c['mutation'] == 'Rainbow' else ""))
            items.append({"id": c['inv_id'], "btn_text": f"{mut}{n} ({avail})"})
            
    kb = get_pagination_keyboard(items, page, "tr_add", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙", callback_data="tr_menu_main")])
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_add_"))
async def cb_trade_do_add(callback: types.CallbackQuery):
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
    
    c_info = await get_inv_item_details(inv_id)
    if c_info:
        mut = "💎 " if c_info['mutation'] == 'Diamond' else ("⭐ " if c_info['mutation'] == 'Gold' else ("🌈 " if c_info['mutation'] == 'Rainbow' else ""))
        string_dict[inv_id] = f"{mut}{format_card_name_plain(c_info)}"
        
    offer_dict[inv_id] = offer_dict.get(inv_id, 0) + 1
    await callback.answer("+1")
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
        if qty > 0: items.append({"id": i_id, "btn_text": f"❌ {string_dict[i_id]} (x{qty})"})
            
    kb = get_pagination_keyboard(items, 0, "tr_rem", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙", callback_data="tr_menu_main")])
    try: await callback.message.edit_text("👇 Выберите карту для удаления:", reply_markup=kb)
    except: pass
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
        if qty > 0: items.append({"id": i_id, "btn_text": f"❌ {string_dict[i_id]} (x{qty})"})
            
    kb = get_pagination_keyboard(items, page, "tr_rem", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙", callback_data="tr_menu_main")])
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
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
        if offer_dict[inv_id] == 0: del offer_dict[inv_id]
            
    trade['p1_ready'] = False; trade['p2_ready'] = False
    trade['p1_confirmed'] = False; trade['p2_confirmed'] = False
    
    await callback.answer("-1")
    await update_trade_uis(trade)

@dp.callback_query(F.data == "tr_menu_main")
async def cb_trade_menu_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    await update_trade_uis(active_trades[trade_id])
    await callback.answer()

async def trade_timeout_task():
    while True:
        try:
            now = time.time()
            to_cancel = []
            for t_id, trade in active_trades.items():
                if now - trade['start_time'] > 600:
                    to_cancel.append(t_id)
            for t_id in to_cancel:
                await cancel_trade(t_id, reason="Тайм-аут / Timeout")
        except: pass
        await asyncio.sleep(60)

async def get_inv_item_details(inv_id):
    row = await fetch_one("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.count, i.mutation, i.serial_number, i.signed_by, u.username, u.first_name
        FROM inventory i JOIN cards c ON i.card_id = c.id LEFT JOIN users u ON i.signed_by = u.id
        WHERE i.id = ?
    """, (inv_id,))
    if not row: return None
    if row['signed_by'] != 0: row['signer_name'] = get_display_name({'username': row['username'], 'first_name': row['first_name']})
    return row

@dp.message(F.text == BTN_SEED_PACKS)
async def cmd_seed_packs_menu(message: types.Message):
    if await check_ban(message.from_user.id): return
    user = await fetch_one("SELECT coins, pass_vip FROM users WHERE id = ?", (message.from_user.id,))
    packs = await fetch_all("SELECT * FROM seed_packs")
    
    bal = user['coins']
    val_sym = "💰"
    val_name = "Шекелей"
    discount = 0.9 if user['pass_vip'] == 1 else 1.0
    
    text = (
        f"📦 <b>МАГАЗИН СИД-ПАКОВ</b>\n{val_sym} Твой баланс: <b>{bal} {val_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nСид-Пак — это особый набор карт с гарантированным набором юнитов и повышенным шансом мутаций (<b>37% на Золотую</b>, <b>12% на Алмазную</b>, <b>2% на Радужную</b>)!\n\nДоступные паки:\n"
    )
    
    kb = []
    if not packs:
        text += "\n<i>Пусто. Ожидайте!</i>"
    else:
        for p in packs:
            desc_text = f" — {p['description']}" if p['description'] else ""
            price_val = int(p.get('price', 2000) * discount)
            text += f"🔹 <b>{p['title']}</b> (Цена: <b>{price_val} {val_sym}</b>){desc_text}\n"
            kb.append([InlineKeyboardButton(text=f"🔍 Смотреть: {p['title']}", callback_data=f"sp_view_{p['id']}_shop")])
            
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("sp_view_"))
async def cb_sp_view(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    pack_id = int(parts[2])
    mode = parts[3] 
    user_id = callback.from_user.id
    user = await fetch_one("SELECT coins, pass_vip FROM users WHERE id=?", (user_id,))
    
    pack = await fetch_one("SELECT * FROM seed_packs WHERE id = ?", (pack_id,))
    if not pack: return await callback.answer("Error!", show_alert=True)
    
    pack_cards = await fetch_all("SELECT c.name, spc.drop_chance FROM seed_pack_cards spc JOIN cards c ON spc.card_id = c.id WHERE spc.pack_id = ?", (pack_id,))
    discount = 0.9 if user['pass_vip'] == 1 else 1.0
    pack_price = int(pack.get('price', 2000) * discount)
    
    text = f"📦 <b>СИД-ПАК: {pack['title']}</b>\n💬 <i>{pack['description']}</i>\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>Содержимое пака:</b>\n"
    if not pack_cards:
        text += "  └ <i>Пак пуст!</i>\n"
    else:
        luck_mult, _ = await get_active_events(user_id)
        total_w = sum(c['drop_chance'] * (luck_mult if c['drop_chance'] < 15.0 else 1.0) for c in pack_cards)
        for idx, c in enumerate(pack_cards, 1):
            w = c['drop_chance'] * (luck_mult if c['drop_chance'] < 15.0 else 1.0)
            chance_pct = (w / total_w) * 100 if total_w > 0 else 0
            text += f"  {idx}. {c['name']} (~{chance_pct:.2f}%)\n"
            
    kb = []
    if mode == "shop":
        bal = user['coins']
        val_sym = "💰"
        val_name = "Шекелей"
        text += f"\n{val_sym} Ваш баланс: <b>{bal} {val_name}</b>\nЦена: <b>{pack_price} {val_sym}</b> за штуку."
        kb.append([InlineKeyboardButton(text=f"🛒 Купить x1", callback_data=f"sp_buy_{pack_id}_1")])
        kb.append([InlineKeyboardButton(text=f"x3 ({pack_price * 3} {val_sym})", callback_data=f"sp_buy_{pack_id}_3"), InlineKeyboardButton(text=f"x10 ({pack_price * 10} {val_sym})", callback_data=f"sp_buy_{pack_id}_10")])
        kb.append([InlineKeyboardButton(text="🔙 Назад в магазин", callback_data=f"sp_shop_back")])
    elif mode == "inv":
        user_pack = await fetch_one("SELECT count FROM user_seed_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id))
        amount = user_pack['count'] if user_pack else 0
        text += f"\nУ вас есть: <b>{amount} шт.</b>\n"
        
        pity = await fetch_one("SELECT opened_count FROM user_pack_pity WHERE user_id = ? AND pack_id = ?", (user_id, pack_id))
        opened = pity['opened_count'] if pity else 0
        if pack.get('pity_limit', 0) > 0:
            text += f"🌟 <b>Гарант PITY:</b> {opened}/{pack['pity_limit']}\n"
            
        if amount > 0:
            kb.append([InlineKeyboardButton(text="📦 Открыть x1", callback_data=f"sp_open_{pack_id}_1")])
            if amount >= 5:
                kb.append([InlineKeyboardButton(text="📦 Открыть x5", callback_data=f"sp_open_{pack_id}_5")])
            kb.append([InlineKeyboardButton(text="📦 Открыть ВСЕ", callback_data=f"sp_open_{pack_id}_all")])
        kb.append([InlineKeyboardButton(text="🔙 Назад в инвентарь", callback_data=f"sp_inv_back")])

    try: await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        try: await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except: pass
    await callback.answer()

@dp.callback_query(F.data == "sp_shop_back")
async def cb_sp_shop_back(callback: types.CallbackQuery):
    fake_msg = callback.message
    fake_msg.from_user = callback.from_user
    fake_msg.text = BTN_SEED_PACKS
    await cmd_seed_packs_menu(fake_msg)
    try: await callback.message.delete()
    except: pass
    await callback.answer()

@dp.callback_query(F.data == "sp_inv_back")
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
    kb = [[InlineKeyboardButton(text="🎒 Карты", callback_data=f"inv_cards_menu"), InlineKeyboardButton(text="📦 Сид-Паки (Выбрано)", callback_data="ignore")]]
    
    if not user_packs: text += "<i>У вас нет Сид-Паков.</i>"
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
    
    user = await fetch_one("SELECT coins, pass_vip FROM users WHERE id=?", (user_id,))
    pack = await fetch_one("SELECT title, price FROM seed_packs WHERE id = ?", (pack_id,))
    
    if not pack: return await callback.answer("Ошибка БД!", show_alert=True)
    
    discount = 0.9 if user['pass_vip'] == 1 else 1.0
    pack_price = int(pack.get('price', 2000) * discount)
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
    
    await callback.answer(f"✅ Куплено {amount} шт. Сид-Паков «{pack['title']}»!", show_alert=True)
    
    new_callback = callback.model_copy(update={"data": f"sp_view_{pack_id}_shop"})
    await cb_sp_view(new_callback)

@dp.callback_query(F.data.startswith("sp_open_"))
async def cb_sp_open_fixed(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    pack_id = int(parts[2])
    amt_str = parts[3]
    user_id = callback.from_user.id
    
    user_pack = await fetch_one("SELECT count FROM user_seed_packs WHERE user_id = ? AND pack_id = ?", (user_id, pack_id))
    pack = await fetch_one("SELECT title, photo_id, pity_card_id, pity_limit FROM seed_packs WHERE id = ?", (pack_id,))
    
    if not user_pack or user_pack['count'] <= 0: return await callback.answer("❌ У вас нет этого пака!", show_alert=True)
        
    amount = user_pack['count'] if amt_str == 'all' else int(amt_str)
    if amount > user_pack['count']: return await callback.answer("Ошибка количества", show_alert=True)
    
    await execute_db("UPDATE user_seed_packs SET count = count - ? WHERE user_id = ? AND pack_id = ?", (amount, user_id, pack_id))
    pack_cards = await fetch_all("SELECT card_id, drop_chance FROM seed_pack_cards WHERE pack_id = ?", (pack_id,))
    
    if not pack_cards:
        await execute_db("UPDATE user_seed_packs SET count = count + ? WHERE user_id = ? AND pack_id = ?", (amount, user_id, pack_id))
        return await callback.answer("Пак пуст в БД", show_alert=True)
        
    luck_mult, _ = await get_active_events(user_id)
    weights = []
    cards_list = []
    for pc in pack_cards:
        w = pc['drop_chance']
        if w < 15.0: w *= luck_mult
        weights.append(w)
        card_info = await fetch_one("SELECT * FROM cards WHERE id = ?", (pc['card_id'],))
        cards_list.append(card_info)
        
    user_pity = await fetch_one("SELECT opened_count FROM user_pack_pity WHERE user_id = ? AND pack_id = ?", (user_id, pack_id))
    curr_pity = user_pity['opened_count'] if user_pity else 0
    
    pity_card = None
    if pack.get('pity_card_id', 0) > 0 and pack.get('pity_limit', 0) > 0:
        pity_card = await fetch_one("SELECT * FROM cards WHERE id = ?", (pack['pity_card_id'],))
        
    won_cards = []
    for _ in range(amount):
        curr_pity += 1
        if pity_card and curr_pity >= pack['pity_limit']:
            mut = roll_seed_pack_mutation()
            _, serial, _ = await give_card_to_user(user_id, pity_card['id'], mut, pity_card['rarity'])
            c_copy = dict(pity_card)
            c_copy['mutation'] = mut
            c_copy['serial_number'] = serial
            c_copy['is_pity'] = True
            won_cards.append(c_copy)
            curr_pity = 0
        else:
            won_card = random.choices(cards_list, weights=weights, k=1)[0]
            mut = roll_seed_pack_mutation() 
            _, serial, _ = await give_card_to_user(user_id, won_card['id'], mut, won_card['rarity'])
            c_copy = dict(won_card)
            c_copy['mutation'] = mut
            c_copy['serial_number'] = serial
            c_copy['is_pity'] = False
            won_cards.append(c_copy)
            
    await execute_db("""
        INSERT INTO user_pack_pity (user_id, pack_id, opened_count) VALUES (?, ?, ?)
        ON CONFLICT(user_id, pack_id) DO UPDATE SET opened_count = ?
    """, (user_id, pack_id, curr_pity, curr_pity))
        
    await add_quest_progress_new(user_id, 'q_open', amount)
    await log_user_action(user_id, f"Открыл Сид-Пак '{pack['title']}' x{amount}")
    
    text_results = f"🎉 <b>РАСПАКОВКА {amount}x СИД-ПАКА «{pack['title']}» ЗАВЕРШЕНА!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    if amount == 1:
        single = won_cards[0]
        mut_str = "🌈 Радужная " if single['mutation'] == 'Rainbow' else ("💎 Алмазная " if single['mutation'] == 'Diamond' else ("⭐ Золотая " if single['mutation'] == 'Gold' else ""))
        mult = get_mutation_multiplier(single['mutation'])
        
        caption_text = text_results
        if single.get('is_pity'):
            caption_text += f"🌟 <b>СИСТЕМА PITY! ГАРАНТИРОВАННАЯ КАРТА ИЗ ПАКА!</b> 🌟\n\n"
            
        caption_text += f"🃏 {mut_str}{format_card_name(single)}\n💎 {format_rarity_display(single['rarity'])}\n"
        if single['class_type'] == 'Booster': 
            caption_text += f"✨ <b>БУСТЕР</b>\n⚔️ DMG Mult: <b>x{round(single['booster_dmg_mult']*mult, 2)}</b> | ❤️ HP Mult: <b>x{round(single['booster_hp_mult']*mult, 2)}</b>\n"
        elif single['class_type'] == 'Healer':
            caption_text += f"💗 <b>Лечение:</b> {int(single['damage']*mult)} | ❤️ <b>Здоровье:</b> {int(single['hp']*mult)}\n"
        else: 
            caption_text += f"⚔️ <b>Урон:</b> {int(single['damage']*mult)} | ❤️ <b>Здоровье:</b> {int(single['hp']*mult)}\n"
            
        await callback.message.answer_photo(photo=single['photo_id'], caption=caption_text)
        try: await callback.message.delete()
        except: pass
    else:
        for idx, c in enumerate(won_cards, 1):
            mut_str = "🌈 " if c['mutation'] == 'Rainbow' else ("💎 " if c['mutation'] == 'Diamond' else ("⭐ " if c['mutation'] == 'Gold' else "⚪ "))
            pity_str = " (🌟 PITY)" if c.get('is_pity') else ""
            text_results += f"{idx}. {mut_str}{format_card_name(c)}{pity_str}\n"
        text_results += "\n<i>Все карты добавлены в 🎒 Инвентарь.</i>"
        await callback.message.answer(text_results)
        try: await callback.message.delete()
        except: pass
        
    new_callback = callback.model_copy(update={"data": f"sp_view_{pack_id}_inv"})
    await cb_sp_view(new_callback)

def get_admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Карты", callback_data="adm_cards"), InlineKeyboardButton(text="👤 Игроки", callback_data="adm_users")],
        [InlineKeyboardButton(text="🎉 Ивенты", callback_data="adm_events"), InlineKeyboardButton(text="👑 Админы", callback_data="adm_admins")],
        [InlineKeyboardButton(text="🎟 Батл-пассы", callback_data="adm_bp_main"), InlineKeyboardButton(text="✍️ Сигнеры", callback_data="adm_signers")],
        [InlineKeyboardButton(text="🏆 Награды за Топ", callback_data="adm_lb_main"), InlineKeyboardButton(text="📦 Сид-Паки", callback_data="adm_sp_main")],
        [InlineKeyboardButton(text="🎁 Коды-Награды", callback_data="adm_codes_main"), InlineKeyboardButton(text="🔨 Настройка Крафтов", callback_data="adm_craft_main")],
        [InlineKeyboardButton(text="💎 Геймпассы", callback_data="adm_gp_main"), InlineKeyboardButton(text="🤖 ИИ Бан Карт", callback_data="adm_ai_ban_main")],
        [InlineKeyboardButton(text="💳 Донат Юниты", callback_data="adm_donunit_main"), InlineKeyboardButton(text="📦 Бэкап БД", callback_data="adm_db")]
    ])

@dp.message(F.text == BTN_ADM)
@dp.message(Command("admin"))
async def cmd_admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await message.answer("⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\nВыберите раздел для управления ботом:", reply_markup=get_admin_main_kb())

@dp.callback_query(F.data == "adm_main")
async def cq_adm_main(callback: types.CallbackQuery):
    await callback.message.edit_text("⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\nВыберите раздел для управления ботом:", reply_markup=get_admin_main_kb())

@dp.callback_query(F.data == "adm_gp_main")
async def adm_gp_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите ID или @username игрока для управления геймпассами:")
    await state.set_state(AdminGPManage.user_id)
    await callback.answer()

@dp.message(AdminGPManage.user_id)
async def adm_gp_user(message: types.Message, state: FSMContext):
    val = message.text.strip()
    if val.isdigit(): user = await fetch_one("SELECT * FROM users WHERE id = ?", (int(val),))
    else: user = await fetch_one("SELECT * FROM users WHERE username = ?", (val.lstrip('@'),))
    if not user: return await message.answer("❌ Игрок не найден.")
    await state.update_data(gp_manage_uid=user['id'])
    await show_user_gamepasses(message, user['id'])
    await state.clear()

async def show_user_gamepasses(message: types.Message, uid: int):
    user = await fetch_one("SELECT * FROM users WHERE id = ?", (uid,))
    name = get_display_name(user)
    def s(v): return "✅" if v else "❌"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"x2 Шекели {s(user.get('pass_x2_coins'))}", callback_data=f"adm_gp_tog_x2_coins_{uid}")],
        [InlineKeyboardButton(text=f"x2 Опыт БП {s(user.get('pass_x2_xp'))}", callback_data=f"adm_gp_tog_x2_xp_{uid}")],
        [InlineKeyboardButton(text=f"5-й Слот {s(user.get('pass_5th_slot'))}", callback_data=f"adm_gp_tog_5th_slot_{uid}")],
        [InlineKeyboardButton(text=f"x1.5 Удача {s(user.get('pass_luck'))}", callback_data=f"adm_gp_tog_luck_{uid}")],
        [InlineKeyboardButton(text=f"VIP Статус {s(user.get('pass_vip'))}", callback_data=f"adm_gp_tog_vip_{uid}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    if isinstance(message, types.Message):
        await message.answer(f"💎 <b>Геймпассы игрока {name} (ID: {uid})</b>\nНажимайте, чтобы выдать или забрать:", reply_markup=kb)
    else:
        await message.edit_text(f"💎 <b>Геймпассы игрока {name} (ID: {uid})</b>\nНажимайте, чтобы выдать или забрать:", reply_markup=kb)

@dp.callback_query(F.data.startswith("adm_gp_tog_"))
async def adm_gp_toggle(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    uid = int(parts[-1])
    field = "_".join(parts[3:-1])
    col = f"pass_{field}"
    
    user = await fetch_one(f"SELECT {col} FROM users WHERE id = ?", (uid,))
    new_val = 0 if user.get(col) == 1 else 1
    await execute_db(f"UPDATE users SET {col} = ? WHERE id = ?", (new_val, uid))
    
    await callback.answer(f"Обновлено!", show_alert=True)
    await show_user_gamepasses(callback.message, uid)

@dp.callback_query(F.data == "adm_ai_ban_main")
async def adm_ai_ban_main(callback: types.CallbackQuery, state: FSMContext):
    all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
    banned_cards = await fetch_all("SELECT card_id FROM ai_banned_cards")
    banned_ids = [c['card_id'] for c in banned_cards]
    
    items = []
    for c in all_cards:
        status = "🚫" if c['id'] in banned_ids else "✅"
        items.append({"id": c['id'], "btn_text": f"{status} {c['name']} (ID:{c['id']})"})
        
    kb = get_pagination_keyboard(items, 0, "admaiban", columns=1, items_per_page=10)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")])
    await state.update_data(ai_ban_items=items, ai_banned_ids=banned_ids)
    await callback.message.edit_text("🤖 <b>Бан карт для ИИ</b>\nНажмите на карту, чтобы запретить (🚫) или разрешить (✅) ИИ использовать ее в боях:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("admaiban_page_"))
async def adm_ai_ban_pag(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('ai_ban_items', []), page, "admaiban", columns=1, items_per_page=10)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("admaiban_"))
async def adm_ai_ban_toggle(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[1])
    
    data = await state.get_data()
    banned_ids = data.get('ai_banned_ids', [])
    
    if card_id in banned_ids:
        await execute_db("DELETE FROM ai_banned_cards WHERE card_id = ?", (card_id,))
        banned_ids.remove(card_id)
        await callback.answer("✅ Карта разрешена для ИИ!")
    else:
        await execute_db("INSERT INTO ai_banned_cards (card_id) VALUES (?)", (card_id,))
        banned_ids.append(card_id)
        await callback.answer("🚫 Карта запрещена для ИИ!")
        
    all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
    items = []
    for c in all_cards:
        status = "🚫" if c['id'] in banned_ids else "✅"
        items.append({"id": c['id'], "btn_text": f"{status} {c['name']} (ID:{c['id']})"})
        
    await state.update_data(ai_ban_items=items, ai_banned_ids=banned_ids)
    
    # Try to keep the same page
    kb_current = callback.message.reply_markup
    page = 0
    if kb_current and kb_current.inline_keyboard:
        for row in kb_current.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("admaiban_page_"):
                    # Quick hack to extract current page index roughly if needed, 
                    # but simple re-render of page 0 is safer fallback.
                    pass
                    
    kb = get_pagination_keyboard(items, page, "admaiban", columns=1, items_per_page=10)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")])
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass

@dp.callback_query(F.data == "adm_donunit_main")
async def adm_donunit_main(callback: types.CallbackQuery):
    units = await fetch_all("SELECT d.id, c.name, d.price_robux, d.price_stars FROM donate_units d JOIN cards c ON d.card_id = c.id")
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in units:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🗑 {u['name']} ({u['price_robux']}R$ / {u['price_stars']}⭐)", callback_data=f"adm_dunit_del_{u['id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Добавить Донат-Юнита", callback_data="adm_dunit_add")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")])
    await callback.message.edit_text("💳 <b>Управление Донат-Юнитами</b>\nНажмите 🗑 для удаления.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_dunit_del_"))
async def adm_dunit_del(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[3])
    await execute_db("DELETE FROM donate_units WHERE id = ?", (uid,))
    await callback.answer("Удалено!", show_alert=True)
    await adm_donunit_main(callback)

@dp.callback_query(F.data == "adm_dunit_add")
async def adm_dunit_add(callback: types.CallbackQuery, state: FSMContext):
    all_cards = await fetch_all("SELECT id, name FROM cards ORDER BY id DESC")
    items = [{"id": c['id'], "btn_text": c['name']} for c in all_cards]
    await state.update_data(dunit_items=items)
    kb = get_pagination_keyboard(items, 0, "admdc", columns=2, items_per_page=10)
    await callback.message.edit_text("Выберите карту, которая будет продаваться:", reply_markup=kb)
    await state.set_state(AdminDonUnit.card_id)
    await callback.answer()

@dp.callback_query(AdminDonUnit.card_id, F.data.startswith("admdc_page_"))
async def admdc_pag(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('dunit_items', []), page, "admdc", columns=2, items_per_page=10)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminDonUnit.card_id, F.data.startswith("admdc_"))
async def admdc_sel(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[1])
    await state.update_data(dunit_card_id=card_id)
    await callback.message.edit_text("Введите цену в Робуксах (R$):")
    await state.set_state(AdminDonUnit.robux)
    await callback.answer()

@dp.message(AdminDonUnit.robux)
async def admdunit_r(message: types.Message, state: FSMContext):
    try:
        r = int(message.text)
        await state.update_data(dunit_robux=r)
        await message.answer("Введите цену в Telegram Stars (⭐):")
        await state.set_state(AdminDonUnit.stars)
    except: await message.answer("Число!")

@dp.message(AdminDonUnit.stars)
async def admdunit_s(message: types.Message, state: FSMContext):
    try:
        s = int(message.text)
        data = await state.get_data()
        await execute_db("INSERT INTO donate_units (card_id, price_robux, price_stars) VALUES (?, ?, ?)", (data['dunit_card_id'], data['dunit_robux'], s))
        await message.answer("✅ Донат-Юнит добавлен!")
        await state.clear()
    except: await message.answer("Число!")

@dp.callback_query(F.data == "adm_sp_main")
async def adm_sp_main_menu(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать Сид-Пак", callback_data="adm_sp_cr_start")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="adm_sp_del_list")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("📦 <b>Управление Сид-Паками</b>\nЗдесь можно создавать паки карт с уникальными шансами.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "adm_sp_cr_start")
async def adm_sp_cr_start(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(sp_cards=[])
    await callback.message.answer(f"Создание Сид-Пака.\nВведите название (например: Новогодний Пак):")
    await state.set_state(CreateSeedPack.title)
    await callback.answer()

@dp.message(CreateSeedPack.title)
async def adm_sp_cr_title(message: types.Message, state: FSMContext):
    await state.update_data(sp_title=message.text)
    await message.answer("Отправьте фото для пака (или напишите 'Пропустить'):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Пропустить")]], resize_keyboard=True))
    await state.set_state(CreateSeedPack.photo)

@dp.message(CreateSeedPack.photo)
async def adm_sp_cr_photo(message: types.Message, state: FSMContext):
    if message.text == "Пропустить": await state.update_data(sp_photo=None)
    elif message.photo: await state.update_data(sp_photo=message.photo[-1].file_id)
    else: return await message.answer("Фото или 'Пропустить'!")
    await message.answer("Введите описание пака:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreateSeedPack.description)

@dp.message(CreateSeedPack.description)
async def adm_sp_cr_desc(message: types.Message, state: FSMContext):
    await state.update_data(sp_desc=message.text)
    await message.answer("Введите цену пака (в Шекелях):")
    await state.set_state(CreateSeedPack.price)

@dp.message(CreateSeedPack.price)
async def adm_sp_cr_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        await state.update_data(sp_price=price)
        
        all_cards = await fetch_all("SELECT id, name FROM cards")
        items = [{"id": c['id'], "btn_text": c['name']} for c in all_cards]
        await state.update_data(sp_pity_items=items)
        
        kb = get_pagination_keyboard(items, 0, "sppity", columns=2, items_per_page=10)
        kb.inline_keyboard.insert(0, [InlineKeyboardButton(text="🚫 Без Pity", callback_data="sppity_none")])
        await message.answer("🌟 Выберите карту для <b>PITY (Гаранта)</b> в этом паке:", reply_markup=kb)
        await state.set_state(AdminSeedPackPity.card_id)
    except: await message.answer("Число!")

@dp.callback_query(AdminSeedPackPity.card_id, F.data.startswith("sppity_page_"))
async def sppity_pag(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('sp_pity_items', []), page, "sppity", columns=2, items_per_page=10)
    kb.inline_keyboard.insert(0, [InlineKeyboardButton(text="🚫 Без Pity", callback_data="sppity_none")])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminSeedPackPity.card_id, F.data.startswith("sppity_"))
async def sppity_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    val = callback.data.split("_")[1]
    if val == "none":
        await state.update_data(sp_pity_card_id=0, sp_pity_limit=0)
        await adm_sp_cr_menu(callback.message, state)
        await callback.answer()
    else:
        await state.update_data(sp_pity_card_id=int(val))
        await callback.message.edit_text("Введите лимит Pity (например, 50 - гарант каждые 50 открытий):")
        await state.set_state(AdminSeedPackPity.limit)

@dp.message(AdminSeedPackPity.limit)
async def sppity_limit(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text)
        await state.update_data(sp_pity_limit=limit)
        await adm_sp_cr_menu(message, state)
    except: await message.answer("Число!")

async def adm_sp_cr_menu(msg, state: FSMContext):
    data = await state.get_data()
    
    pity_str = "Отключено"
    if data.get('sp_pity_card_id', 0) > 0:
        c_info = await fetch_one("SELECT name FROM cards WHERE id = ?", (data['sp_pity_card_id'],))
        if c_info: pity_str = f"Гарант {c_info['name']} каждые {data['sp_pity_limit']} открытий"
        
    text = f"📦 <b>Пак: {data['sp_title']}</b>\nЦена: {data['sp_price']}\nPITY: {pity_str}\n\nКарты в паке:\n"
    for i, c in enumerate(data.get('sp_cards', [])):
        text += f"{i+1}. ID:{c['card_id']} - Вес: {c['chance']}\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить карту", callback_data="sp_cr_add_c")],
        [InlineKeyboardButton(text="✅ Завершить создание", callback_data="sp_cr_finish")]
    ])
    if isinstance(msg, types.CallbackQuery): await msg.message.answer(text, reply_markup=kb)
    else: await msg.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "sp_cr_add_c")
async def sp_cr_add_c(callback: types.CallbackQuery, state: FSMContext):
    query = "SELECT id, name, rarity FROM cards"
    cards = await fetch_all(query)
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'],'')} {c['name']}"} for c in cards]
    await state.update_data(sp_items=items)
    kb = get_pagination_keyboard(items, 0, "sp_cr_c", columns=1, items_per_page=8)
    await callback.message.edit_text("Выберите карту для добавления в пак:", reply_markup=kb)
    await state.set_state(CreateSeedPack.card_select)

@dp.callback_query(CreateSeedPack.card_select, F.data.startswith("sp_cr_c_page_"))
async def sp_cr_c_pag(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[4])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('sp_items', []), page, "sp_cr_c", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(CreateSeedPack.card_select, F.data.startswith("sp_cr_c_"))
async def sp_cr_c_sel(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    cid = int(callback.data.split("_")[3])
    await state.update_data(sp_curr_c=cid)
    await callback.message.edit_text("Введите вес выпадения этой карту (например 1.0, 50, 0.1):")
    await state.set_state(CreateSeedPack.card_chance)

@dp.message(CreateSeedPack.card_chance)
async def sp_cr_c_chance(message: types.Message, state: FSMContext):
    try:
        w = float(message.text.replace(',', '.'))
        data = await state.get_data()
        data['sp_cards'].append({'card_id': data['sp_curr_c'], 'chance': w})
        await state.update_data(sp_cards=data['sp_cards'])
        await adm_sp_cr_menu(message, state)
    except: await message.answer("Число!")

@dp.callback_query(F.data == "sp_cr_finish")
async def sp_cr_finish(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('sp_cards'): return await callback.answer("Пак пуст!", show_alert=True)
    db = await get_db_connection()
    try:
        cur = await db.execute("INSERT INTO seed_packs (title, photo_id, description, price, pity_card_id, pity_limit) VALUES (?, ?, ?, ?, ?, ?)",
                               (data['sp_title'], data.get('sp_photo'), data['sp_desc'], data['sp_price'], data.get('sp_pity_card_id', 0), data.get('sp_pity_limit', 0)))
        pid = cur.lastrowid
        for c in data['sp_cards']:
            await db.execute("INSERT INTO seed_pack_cards (pack_id, card_id, drop_chance) VALUES (?, ?, ?)",
                             (pid, c['card_id'], c['chance']))
        await db.commit()
        await callback.message.edit_text("✅ Сид-пак успешно создан!")
    finally: await db.close()
    await state.clear()
    
@dp.callback_query(F.data == "adm_sp_del_list")
async def adm_sp_del_list(callback: types.CallbackQuery):
    packs = await fetch_all("SELECT id, title FROM seed_packs")
    kb = []
    for p in packs: kb.append([InlineKeyboardButton(text=f"🗑 {p['title']}", callback_data=f"adm_sp_del_{p['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_sp_main")])
    await callback.message.edit_text("Выберите пак для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    
@dp.callback_query(F.data.startswith("adm_sp_del_"))
async def adm_sp_del_action(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[3])
    await execute_db("DELETE FROM seed_packs WHERE id = ?", (pid,))
    await execute_db("DELETE FROM seed_pack_cards WHERE pack_id = ?", (pid,))
    await execute_db("DELETE FROM user_pack_pity WHERE pack_id = ?", (pid,))
    await callback.answer("✅ Удалено!", show_alert=True)
    await adm_sp_main_menu(callback)

@dp.callback_query(F.data == "adm_codes_main")
async def adm_codes_main(callback: types.CallbackQuery):
    if callback.from_user.id != SUPER_ADMIN_ID: return await callback.answer("Только для Супер-Админа!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Сгенерировать коды", callback_data="adm_code_gen_start")],
        [InlineKeyboardButton(text="📜 Просмотр кодов", callback_data="adm_code_list_0")],
        [InlineKeyboardButton(text="🗑 Очистить ВСЕ коды", callback_data="adm_code_clear_all")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("🎁 <b>Управление Уникальными Кодами-наградами</b>\nКоды с шансом 5% могут выпадать победителям боёв.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "adm_code_clear_all")
async def adm_code_clear_all(callback: types.CallbackQuery):
    await execute_db("DELETE FROM reward_codes")
    await callback.answer("✅ Все коды удалены!", show_alert=True)
    await adm_codes_main(callback)

@dp.callback_query(F.data == "adm_code_gen_start")
async def adm_code_gen_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Сколько кодов вы хотите сгенерировать? (Введите число)")
    await state.set_state(AdminRewardCode.count)
    await callback.answer()

@dp.message(AdminRewardCode.count)
async def adm_code_gen_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if count <= 0: raise ValueError
        await state.update_data(gen_code_count=count)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Шекели", callback_data="cg_type_shekels")],
            [InlineKeyboardButton(text="🃏 Юниты", callback_data="cg_type_card")],
            [InlineKeyboardButton(text="📦 Сид-Паки", callback_data="cg_type_pack")]
        ])
        await message.answer(f"Генерируем {count} кодов. Что будет в награде?", reply_markup=kb)
        await state.set_state(AdminRewardCode.r_type)
    except:
        await message.answer("❌ Введите корректное положительное число.")

@dp.callback_query(AdminRewardCode.r_type, F.data.startswith("cg_type_"))
async def adm_code_gen_type(callback: types.CallbackQuery, state: FSMContext):
    r_type = callback.data.split("_")[2]
    await state.update_data(gen_code_type=r_type)
    
    if r_type == "shekels":
        await callback.message.edit_text("Введите количество шекелей, которое даст один код:")
        await state.set_state(AdminRewardCode.amount)
    elif r_type == "card":
        all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
        items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '')} {c['name']} (ID:{c['id']})"} for c in all_cards]
        await state.update_data(gen_items=items)
        kb = get_pagination_keyboard(items, 0, "cgc", columns=1, items_per_page=8)
        await callback.message.edit_text("Выберите карту, которую даст код:", reply_markup=kb)
        await state.set_state(AdminRewardCode.card_id)
    elif r_type == "pack":
        packs = await fetch_all("SELECT id, title FROM seed_packs ORDER BY id DESC")
        if not packs: return await callback.answer("Сид-паков нет!", show_alert=True)
        items = [{"id": p['id'], "btn_text": f"📦 {p['title']}"} for p in packs]
        await state.update_data(gen_items=items)
        kb = get_pagination_keyboard(items, 0, "cgp", columns=1, items_per_page=8)
        await callback.message.edit_text("Выберите Сид-Пак для награды:", reply_markup=kb)
        await state.set_state(AdminRewardCode.pack_id)
    await callback.answer()

@dp.message(AdminRewardCode.amount)
async def adm_code_gen_shekels_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        data = await state.get_data()
        await generate_and_save_codes(message, state, data['gen_code_count'], 'shekels', amount=amount)
    except:
        await message.answer("❌ Число!")

@dp.callback_query(AdminRewardCode.card_id, F.data.startswith("cgc_page_"))
async def adm_code_card_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('gen_items', []), page, "cgc", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminRewardCode.card_id, F.data.startswith("cgc_"))
async def adm_code_card_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[1])
    await state.update_data(gen_card_id=card_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚪ Обычная", callback_data="cgmut_Normal")],
        [InlineKeyboardButton(text="⭐ Золотая", callback_data="cgmut_Gold")],
        [InlineKeyboardButton(text="💎 Алмазная", callback_data="cgmut_Diamond")],
        [InlineKeyboardButton(text="🌈 Радужная", callback_data="cgmut_Rainbow")]
    ])
    await callback.message.edit_text("Выберите мутацию:", reply_markup=kb)
    await state.set_state(AdminRewardCode.mutation)
    await callback.answer()

@dp.callback_query(AdminRewardCode.mutation, F.data.startswith("cgmut_"))
async def adm_code_mut_select(callback: types.CallbackQuery, state: FSMContext):
    mutation = callback.data.split("_")[1]
    data = await state.get_data()
    await generate_and_save_codes(callback.message, state, data['gen_code_count'], 'card', card_id=data['gen_card_id'], mutation=mutation)
    await callback.answer()

@dp.callback_query(AdminRewardCode.pack_id, F.data.startswith("cgp_page_"))
async def adm_code_pack_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('gen_items', []), page, "cgp", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminRewardCode.pack_id, F.data.startswith("cgp_"))
async def adm_code_pack_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    pack_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    await generate_and_save_codes(callback.message, state, data['gen_code_count'], 'pack', item_id=pack_id)
    await callback.answer()

async def generate_and_save_codes(message: types.Message, state: FSMContext, count: int, r_type: str, amount: int = 0, card_id: int = 0, mutation: str = 'Normal', item_id: int = 0):
    db = await get_db_connection()
    codes = []
    try:
        await db.execute("BEGIN EXCLUSIVE")
        for _ in range(count):
            code = generate_reward_code()
            codes.append(code)
            await db.execute(
                "INSERT INTO reward_codes (code, reward_type, amount, item_id, mutation, owner_id, is_active) VALUES (?, ?, ?, ?, ?, 0, 1)",
                (code, r_type, amount, card_id if r_type == 'card' else item_id, mutation)
            )
        await db.commit()
        
        codes_str = "\n".join(codes)
        bio = io.BytesIO(codes_str.encode('utf-8'))
        bio.seek(0)
        file = types.BufferedInputFile(bio.read(), filename="reward_codes.txt")
        
        info = f"Сгенерировано {count} кодов.\nТип: {r_type}\n"
        if r_type == 'shekels': info += f"Сумма: {amount}"
        elif r_type == 'card': info += f"Card ID: {card_id} | Mut: {mutation}"
        elif r_type == 'pack': info += f"Pack ID: {item_id}"
        
        await bot.send_document(message.chat.id, file, caption=f"✅ Готово!\n{info}")
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Gen code error: {e}")
    finally:
        await db.close()
    await state.clear()

@dp.callback_query(F.data.startswith("adm_code_list_"))
async def adm_code_list(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[3])
    codes = await fetch_all("SELECT * FROM reward_codes WHERE is_active = 1 ORDER BY code DESC")
    if not codes: return await callback.answer("Нет активных невыданных кодов.", show_alert=True)
    
    items = []
    for c in codes:
        own_status = f"Выбит ID:{c['owner_id']}" if c['owner_id'] != 0 else "Общий"
        items.append({"id": c['code'], "btn_text": f"🔑 {c['code'][:8]}... ({c['reward_type']} | {own_status})"})
        
    kb = get_pagination_keyboard(items, page, "admcode", columns=1, items_per_page=8)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_codes_main")])
    
    try: await callback.message.edit_text(f"📜 <b>Активные коды ({len(codes)} шт.)</b>\nНажмите для деактивации:", reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("admcode_page_"))
async def adm_code_list_pag(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    fake_call = callback.model_copy(update={"data": f"adm_code_list_{page}"})
    await adm_code_list(fake_call)

@dp.callback_query(F.data.startswith("admcode_"))
async def adm_code_deactivate(callback: types.CallbackQuery):
    if "page" in callback.data: return
    code = callback.data.split("_")[1]
    await execute_db("UPDATE reward_codes SET is_active = 0 WHERE code = ?", (code,))
    await callback.answer(f"Код деактивирован!", show_alert=True)
    fake_call = callback.model_copy(update={"data": "adm_code_list_0"})
    await adm_code_list(fake_call)

@dp.message(Command("codereward"))
async def cmd_codereward(message: types.Message, state: FSMContext):
    if await check_ban(message.from_user.id): return
    await message.answer("🎁 <b>АКТИВАЦИЯ КОДА</b>\nОтправьте ваш 28-значный код (или любой выданный):")
    await state.set_state(UserUseCode.waiting_code)

@dp.message(UserUseCode.waiting_code)
async def process_code_reward(message: types.Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    
    db = await get_db_connection()
    try:
        await db.execute("BEGIN EXCLUSIVE")
        cursor = await db.execute("SELECT * FROM reward_codes WHERE code = ? AND is_active = 1", (code,))
        code_data = await cursor.fetchone()
        
        if not code_data:
            await db.execute("ROLLBACK")
            await message.answer("❌ Код недействителен или уже использован.")
            return await state.clear()
            
        if code_data['owner_id'] != 0 and code_data['owner_id'] != user_id:
            await db.execute("ROLLBACK")
            await message.answer("❌ Этот код предназначен не для вас!")
            return await state.clear()
            
        await db.execute("UPDATE reward_codes SET is_active = 0 WHERE code = ?", (code,))
        
        r_type = code_data['reward_type']
        
        if r_type == 'shekels':
            await db.execute("UPDATE users SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (code_data['amount'], code_data['amount'], user_id))
            await message.answer(f"✅ Вы успешно активировали код!\nНаграда: <b>{code_data['amount']} 💰 Шекелей</b>!")
        elif r_type == 'card':
            _, serial, _ = await give_card_to_user(user_id, code_data['item_id'], code_data['mutation'])
            c_info = await fetch_one("SELECT name FROM cards WHERE id = ?", (code_data['item_id'],))
            mut_str = "🌈 " if code_data['mutation'] == 'Rainbow' else ("💎 " if code_data['mutation'] == 'Diamond' else ("⭐ " if code_data['mutation'] == 'Gold' else ""))
            s_str = f" [#{serial:04d}]" if serial > 0 else ""
            await message.answer(f"✅ Вы успешно активировали код!\nНаграда: 🃏 <b>{mut_str}{c_info['name']}{s_str}</b>!")
        elif r_type == 'pack':
            await db.execute("INSERT INTO user_seed_packs (user_id, pack_id, count) VALUES (?, ?, 1) ON CONFLICT(user_id, pack_id) DO UPDATE SET count = count + 1", (user_id, code_data['item_id']))
            p_info = await fetch_one("SELECT title FROM seed_packs WHERE id = ?", (code_data['item_id'],))
            await message.answer(f"✅ Вы успешно активировали код!\nНаграда: 📦 <b>Сид-Пак «{p_info['title']}»</b> (1 шт.)!")
        
        await db.commit()
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Code redeem error: {e}")
        await message.answer("❌ Произошла ошибка при получении награды. Возможно, этот код уже был активирован вами или другим игроком.")
    finally:
        await db.close()
    await state.clear()

@dp.callback_query(F.data == "adm_bp_main")
async def adm_bp_main(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать Батл-пасс", callback_data="adm_bp_create_start")],
        [InlineKeyboardButton(text="✏️ Редактировать Батл-пасс", callback_data="adm_bp_edit_list")],
        [InlineKeyboardButton(text="🗑 Удалить Батл-пасс", callback_data="adm_bp_delete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("🎟 <b>Управление Батл-пассами</b>\nСоздавайте новые сезоны и настраивайте награды.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "adm_bp_edit_list")
async def adm_bp_edit_list(callback: types.CallbackQuery):
    bps = await fetch_all("SELECT id, title FROM battle_passes")
    if not bps: return await callback.answer("Нет БП.", show_alert=True)
    kb = []
    for b in bps: kb.append([InlineKeyboardButton(text=f"✏️ {b['title']}", callback_data=f"abp_ed_{b['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_bp_main")])
    await callback.message.edit_text("Выберите БП для редактирования:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("abp_ed_"))
async def abp_ed_menu(callback: types.CallbackQuery, state: FSMContext):
    bpid = int(callback.data.split("_")[2])
    await state.update_data(ed_bp_id=bpid)
    bp = await fetch_one("SELECT * FROM battle_passes WHERE id = ?", (bpid,))
    text = f"✏️ Редактирование БП: <b>{bp['title']}</b>\nЧто меняем?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить название", callback_data="abp_ed_title")],
        [InlineKeyboardButton(text="Изменить фото", callback_data="abp_ed_photo")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_bp_edit_list")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await state.set_state(AdminBPEdit.edit_menu)
    await callback.answer()
    
@dp.callback_query(AdminBPEdit.edit_menu, F.data == "abp_ed_title")
async def abp_ed_title(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новое название для Батл-Пасса:")
    await state.set_state(AdminBPEdit.edit_title)
    await callback.answer()

@dp.message(AdminBPEdit.edit_title)
async def abp_ed_title_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await execute_db("UPDATE battle_passes SET title = ? WHERE id = ?", (message.text, data['ed_bp_id']))
    await message.answer("✅ Название обновлено!")
    await state.clear()

@dp.callback_query(AdminBPEdit.edit_menu, F.data == "abp_ed_photo")
async def abp_ed_photo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправьте новое фото для Батл-Пасса:")
    await state.set_state(AdminBPEdit.edit_photo)
    await callback.answer()

@dp.message(AdminBPEdit.edit_photo, F.photo)
async def abp_ed_photo_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await execute_db("UPDATE battle_passes SET photo_id = ? WHERE id = ?", (message.photo[-1].file_id, data['ed_bp_id']))
    await message.answer("✅ Фото обновлено!")
    await state.clear()

@dp.callback_query(F.data == "adm_bp_delete")
async def adm_bp_del_list(callback: types.CallbackQuery):
    passes = await fetch_all("SELECT * FROM battle_passes ORDER BY id DESC")
    if not passes:
        return await callback.answer("Батл-пассов пока нет.", show_alert=True)
        
    kb = []
    for bp in passes:
        kb.append([InlineKeyboardButton(text=f"🗑 Удалить: {bp['title']}", callback_data=f"adm_bp_del_id_{bp['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="adm_bp_main")])
    
    await callback.message.edit_text("Выберите Батл-пасс для полного удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_bp_del_id_"))
async def adm_bp_del_confirm(callback: types.CallbackQuery):
    bp_id = int(callback.data.split("_")[4])
    await execute_db("DELETE FROM battle_passes WHERE id = ?", (bp_id,))
    await execute_db("DELETE FROM bp_levels WHERE bp_id = ?", (bp_id,))
    await callback.answer("✅ Батл-пасс удален!", show_alert=True)
    await adm_bp_main(callback)

@dp.callback_query(F.data == "adm_bp_create_start")
async def adm_bp_create_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(f"🎟 <b>Создание Батл-пасса</b>\nШаг 1: Введите красивое НАЗВАНИЕ сезона (например: <i>Сезон 1: Зимняя Сказка</i>):")
    await state.set_state(AdminBPCreation.title)
    await callback.answer()

@dp.message(AdminBPCreation.title)
async def adm_bp_cr_title(message: types.Message, state: FSMContext):
    await state.update_data(bp_title=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Пропустить")]], resize_keyboard=True)
    await message.answer("Шаг 2: Отправьте ФОТО для батл-пасса (или нажмите Пропустить):", reply_markup=kb)
    await state.set_state(AdminBPCreation.photo)

@dp.message(AdminBPCreation.photo)
async def adm_bp_cr_photo(message: types.Message, state: FSMContext):
    if message.text == "Пропустить":
        await state.update_data(bp_photo=None)
    elif message.photo:
        await state.update_data(bp_photo=message.photo[-1].file_id)
    else:
        return await message.answer("Пожалуйста, отправьте фото или нажмите Пропустить.")
        
    await message.answer("Шаг 3: Сколько всего УРОВНЕЙ будет в этом батл-пассе? (Введите число, например 10):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AdminBPCreation.levels_count)

@dp.message(AdminBPCreation.levels_count)
async def adm_bp_cr_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        if count <= 0: raise ValueError
        await state.update_data(bp_levels_count=count, current_level=1, bp_data_levels={})
        await adm_bp_ask_level_xp(message, state, 1)
    except:
        await message.answer("❌ Введите корректное число больше 0.")

async def adm_bp_ask_level_xp(message_or_call, state: FSMContext, lvl: int):
    msg = f"⚙️ <b>Настройка Уровня {lvl}</b>\nСколько ОПЫТА (XP) требуется для достижения этого уровня?"
    if isinstance(message_or_call, types.CallbackQuery):
        await message_or_call.message.answer(msg)
    else:
        await message_or_call.answer(msg)
    await state.set_state(AdminBPCreation.level_xp)

@dp.message(AdminBPCreation.level_xp)
async def adm_bp_cr_lvl_xp(message: types.Message, state: FSMContext):
    try:
        xp = int(message.text)
        data = await state.get_data()
        lvl = data['current_level']
        
        bp_levels = data['bp_data_levels']
        if lvl not in bp_levels:
            bp_levels[lvl] = {'xp': xp, 'rewards': []}
        else:
            bp_levels[lvl]['xp'] = xp
            
        await state.update_data(bp_data_levels=bp_levels)
        await adm_bp_show_reward_menu(message, state, lvl)
    except ValueError:
        await message.answer("❌ Введите число.")

async def adm_bp_show_reward_menu(message_or_call, state: FSMContext, lvl: int):
    data = await state.get_data()
    rewards = data['bp_data_levels'][lvl]['rewards']
    
    val_name = "Шекелей"
    val_sym = "💰"
    
    text = f"⚙️ <b>Настройка Уровня {lvl}</b>\nНаграды на этом уровне:\n"
    if not rewards: text += "<i>Пока пусто</i>\n"
    else:
        for r in rewards:
            if r['type'] == 'shekels': text += f"{val_sym} {r['amount']} {val_name}\n"
            elif r['type'] == 'card': text += f"🃏 Карта ID:{r['card_id']} ({r['mutation']})\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Добавить {val_name}", callback_data="bpr_add_sh"), InlineKeyboardButton(text="➕ Добавить Карту", callback_data="bpr_add_cd")],
        [InlineKeyboardButton(text="✅ Завершить уровень", callback_data="bpr_next_lvl")]
    ])
    
    if isinstance(message_or_call, types.CallbackQuery):
        await message_or_call.message.answer(text, reply_markup=kb)
    else:
        await message_or_call.answer(text, reply_markup=kb)
    await state.set_state(AdminBPCreation.reward_action)

@dp.callback_query(AdminBPCreation.reward_action, F.data == "bpr_add_sh")
async def bpr_add_sh(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите количество:")
    await state.set_state(AdminBPCreation.reward_shekels)
    await callback.answer()

@dp.message(AdminBPCreation.reward_shekels)
async def bpr_save_sh(message: types.Message, state: FSMContext):
    try:
        amt = int(message.text)
        data = await state.get_data()
        lvl = data['current_level']
        data['bp_data_levels'][lvl]['rewards'].append({'type': 'shekels', 'amount': amt})
        await state.update_data(bp_data_levels=data['bp_data_levels'])
        await adm_bp_show_reward_menu(message, state, lvl)
    except:
        await message.answer("❌ Число!")

@dp.callback_query(AdminBPCreation.reward_action, F.data == "bpr_add_cd")
async def bpr_add_cd(callback: types.CallbackQuery, state: FSMContext):
    all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '')} {c['name']} (ID:{c['id']})"} for c in all_cards]
    await state.update_data(bpadm_items=items)
    kb = get_pagination_keyboard(items, 0, "bpadmc", columns=1, items_per_page=8)
    await callback.message.edit_text("Выберите карту для награды:", reply_markup=kb)
    await state.set_state(AdminBPCreation.reward_card)
    await callback.answer()

@dp.callback_query(AdminBPCreation.reward_card, F.data.startswith("bpadmc_page_"))
async def bpadm_c_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('bpadm_items', []), page, "bpadmc", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminBPCreation.reward_card, F.data.startswith("bpadmc_"))
async def bpadm_c_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[1])
    await state.update_data(bpadm_sel_card=card_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚪ Обычная", callback_data="bpadmmut_Normal")],
        [InlineKeyboardButton(text="⭐ Золотая", callback_data="bpadmmut_Gold")],
        [InlineKeyboardButton(text="💎 Алмазная", callback_data="bpadmmut_Diamond")],
        [InlineKeyboardButton(text="🌈 Радужная", callback_data="bpadmmut_Rainbow")]
    ])
    await callback.message.edit_text("Выберите мутацию для этой карты:", reply_markup=kb)
    await state.set_state(AdminBPCreation.reward_mutation)
    await callback.answer()

@dp.callback_query(AdminBPCreation.reward_mutation, F.data.startswith("bpadmmut_"))
async def bpadm_mut_select(callback: types.CallbackQuery, state: FSMContext):
    mutation = callback.data.split("_")[1]
    data = await state.get_data()
    lvl = data['current_level']
    card_id = data['bpadm_sel_card']
    
    data['bp_data_levels'][lvl]['rewards'].append({'type': 'card', 'card_id': card_id, 'mutation': mutation})
    await state.update_data(bp_data_levels=data['bp_data_levels'])
    
    try: await callback.message.delete()
    except: pass
    await adm_bp_show_reward_menu(callback, state, lvl)
    await callback.answer()

@dp.callback_query(AdminBPCreation.reward_action, F.data == "bpr_next_lvl")
async def bpr_next_lvl(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lvl = data['current_level']
    total_lvls = data['bp_levels_count']
    
    if lvl < total_lvls:
        await state.update_data(current_level=lvl + 1)
        try: await callback.message.delete()
        except: pass
        await adm_bp_ask_level_xp(callback, state, lvl + 1)
    else:
        try: await callback.message.delete()
        except: pass
        await adm_bp_finish_and_save(callback, state)
    await callback.answer()

async def adm_bp_finish_and_save(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    text = f"✅ <b>Все настроено! Создаю Батл-пасс:</b>\nНазвание: {data['bp_title']}\nУровней: {data['bp_levels_count']}\n\n"
    await callback.message.answer(text)
    
    db = await get_db_connection()
    try:
        cursor = await db.execute("INSERT INTO battle_passes (title, photo_id, created_at) VALUES (?, ?, ?)", (data['bp_title'], data.get('bp_photo'), time.time()))
        bp_id = cursor.lastrowid
        
        for lvl_num, lvl_data in data['bp_data_levels'].items():
            l_cursor = await db.execute("INSERT INTO bp_levels (bp_id, level, xp_required) VALUES (?, ?, ?)", (bp_id, lvl_num, lvl_data['xp']))
            level_id = l_cursor.lastrowid
            
            for r in lvl_data['rewards']:
                if r['type'] == 'shekels':
                    await db.execute("INSERT INTO bp_rewards (level_id, reward_type, amount) VALUES (?, ?, ?)", (level_id, 'shekels', r['amount']))
                elif r['type'] == 'card':
                    await db.execute("INSERT INTO bp_rewards (level_id, reward_type, card_id, mutation) VALUES (?, ?, ?, ?)", (level_id, 'card', r['card_id'], r['mutation']))
        
        await db.commit()
    finally:
        await db.close()
        
    await callback.message.answer("🎉 Батл-пасс успешно сохранен в базу и доступен игрокам!")
    await log_admin(callback.from_user.id, f"Создал новый Батл-пасс: {data['bp_title']}")
    await state.clear()

@dp.callback_query(F.data == "adm_lb_main")
async def adm_lb_main(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Кубки (Сезон)", callback_data="adm_lb_cat_trophies")],
        [InlineKeyboardButton(text="💰 Шекели (Все время)", callback_data="adm_lb_cat_coins")],
        [InlineKeyboardButton(text="🃏 Карты (Все время)", callback_data="adm_lb_cat_cards")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("🏆 <b>Настройка наград за Лидерборд</b>\nВыберите категорию:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_lb_cat_"))
async def adm_lb_cat_select(callback: types.CallbackQuery, state: FSMContext):
    cat = callback.data.split("_")[3]
    await state.update_data(lb_current_type=cat)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥇 1 Место", callback_data=f"lb_edit_1")],
        [InlineKeyboardButton(text="🥈 2 Место", callback_data=f"lb_edit_2")],
        [InlineKeyboardButton(text="🥉 3 Место", callback_data=f"lb_edit_3")],
        [InlineKeyboardButton(text="🏅 4-9 Места", callback_data=f"lb_edit_4_9")],
        [InlineKeyboardButton(text="🎖 10-20 Места", callback_data=f"lb_edit_10_20")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_lb_main")]
    ])
    cat_name = "Кубки" if cat == "trophies" else ("Шекели" if cat == "coins" else "Карты")
    await callback.message.edit_text(f"🏆 <b>Настройка наград: {cat_name}</b>\nВыберите позицию для редактирования наград:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("lb_edit_"))
async def adm_lb_edit(callback: types.CallbackQuery, state: FSMContext):
    bracket = callback.data.replace("lb_edit_", "")
    data = await state.get_data()
    lb_type = data.get('lb_current_type', 'trophies')
    
    rewards = await fetch_all("SELECT * FROM lb_rewards WHERE bracket = ? AND lb_type = ?", (bracket, lb_type))
    
    text = f"🏆 <b>Награды для места: {bracket.replace('_', '-')} ({lb_type})</b>\n\n"
    if not rewards:
        text += "<i>Награды не установлены.</i>\n"
    else:
        for r in rewards:
            if r['reward_type'] == 'shekels':
                text += f"💰 {r['amount']} Шекелей\n"
            elif r['reward_type'] == 'card':
                c = await fetch_one("SELECT name FROM cards WHERE id = ?", (r['card_id'],))
                n = c['name'] if c else "Удаленная карта"
                mut = "🌈" if r['mutation'] == 'Rainbow' else ("💎" if r['mutation'] == 'Diamond' else ("⭐" if r['mutation'] == 'Gold' else ""))
                text += f"🃏 {mut} {n} (ID: {r['card_id']})\n"
                
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить Шекели", callback_data=f"lb_add_sh_{bracket}")],
        [InlineKeyboardButton(text="➕ Добавить Карту", callback_data=f"lb_add_cd_{bracket}")],
        [InlineKeyboardButton(text="🗑 Очистить награды", callback_data=f"lb_clear_{bracket}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm_lb_cat_{lb_type}")]
    ])
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("lb_clear_"))
async def adm_lb_clear(callback: types.CallbackQuery, state: FSMContext):
    bracket = callback.data.replace("lb_clear_", "")
    data = await state.get_data()
    lb_type = data.get('lb_current_type', 'trophies')
    await execute_db("DELETE FROM lb_rewards WHERE bracket = ? AND lb_type = ?", (bracket, lb_type))
    await callback.answer("✅ Награды очищены!", show_alert=True)
    fake_call = callback.model_copy(update={"data": f"lb_edit_{bracket}"})
    await adm_lb_edit(fake_call, state)

@dp.callback_query(F.data.startswith("lb_add_sh_"))
async def adm_lb_add_shekels(callback: types.CallbackQuery, state: FSMContext):
    bracket = callback.data.replace("lb_add_sh_", "")
    await state.update_data(lb_bracket=bracket, lb_reward_type="shekels")
    await callback.message.answer("Введите количество Шекелей для выдачи:")
    await state.set_state(AdminLBRewards.amount)
    await callback.answer()

@dp.message(AdminLBRewards.amount)
async def adm_lb_save_shekels(message: types.Message, state: FSMContext):
    try:
        amt = int(message.text)
        data = await state.get_data()
        lb_type = data.get('lb_current_type', 'trophies')
        await execute_db("INSERT INTO lb_rewards (bracket, reward_type, amount, lb_type) VALUES (?, ?, ?, ?)", (data['lb_bracket'], 'shekels', amt, lb_type))
        await message.answer(f"✅ Награда {amt} шекелей добавлена для {data['lb_bracket']} места ({lb_type})!")
    except:
        await message.answer("❌ Число!")
    await state.clear()

@dp.callback_query(F.data.startswith("lb_add_cd_"))
async def adm_lb_add_card(callback: types.CallbackQuery, state: FSMContext):
    bracket = callback.data.replace("lb_add_cd_", "")
    await state.update_data(lb_bracket=bracket, lb_reward_type="card")
    
    all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '')} {c['name']} (ID:{c['id']})"} for c in all_cards]
    await state.update_data(lb_items=items)
    kb = get_pagination_keyboard(items, 0, "lbc", columns=1, items_per_page=8)
    
    await callback.message.edit_text("Выберите карту для награды:", reply_markup=kb)
    await state.set_state(AdminLBRewards.card_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("lbc_page_"), AdminLBRewards.card_id)
async def adm_lb_c_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('lb_items', []), page, "lbc", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("lbc_"), AdminLBRewards.card_id)
async def adm_lb_c_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[1])
    await state.update_data(lb_card_id=card_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚪ Обычная", callback_data="lb_mut_Normal")],
        [InlineKeyboardButton(text="⭐ Золотая", callback_data="lb_mut_Gold")],
        [InlineKeyboardButton(text="💎 Алмазная", callback_data="lb_mut_Diamond")],
        [InlineKeyboardButton(text="🌈 Радужная", callback_data="lb_mut_Rainbow")]
    ])
    await callback.message.edit_text("Выберите мутацию для этой награды:", reply_markup=kb)
    await state.set_state(AdminLBRewards.mutation)
    await callback.answer()

@dp.callback_query(F.data.startswith("lb_mut_"), AdminLBRewards.mutation)
async def adm_lb_mut_select(callback: types.CallbackQuery, state: FSMContext):
    mutation = callback.data.split("_")[2]
    data = await state.get_data()
    bracket = data['lb_bracket']
    card_id = data['lb_card_id']
    lb_type = data.get('lb_current_type', 'trophies')
    
    await execute_db("INSERT INTO lb_rewards (bracket, reward_type, card_id, mutation, lb_type) VALUES (?, ?, ?, ?, ?)", (bracket, 'card', card_id, mutation, lb_type))
    
    await callback.message.edit_text(f"✅ Карта (ID {card_id}, Мутация: {mutation}) добавлена в награды для {bracket} места ({lb_type})!")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "adm_events")
async def cq_adm_events(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍀 Ивент Удачи", callback_data="ev_luck"), InlineKeyboardButton(text="⏳ Ивент КД", callback_data="ev_cd")],
        [InlineKeyboardButton(text="💰 Множитель монет", callback_data="ev_coin"), InlineKeyboardButton(text="🎫 Множитель опыта БП", callback_data="ev_xp")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("🎉 <b>Запуск Ивентов</b>\nПри запуске бот сделает массовую рассылку всем игрокам.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "ev_luck")
async def ev_luck_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи множитель УДАЧИ (например 2.0 для х2):")
    await state.set_state(EventLuck.mult)
    await callback.answer()

@dp.message(EventLuck.mult)
async def ev_luck_mult(message: types.Message, state: FSMContext):
    await state.update_data(mult=float(message.text.replace(',','.')))
    await message.answer("На сколько МИНУТ запускаем?")
    await state.set_state(EventLuck.mins)

@dp.message(EventLuck.mins)
async def ev_luck_finish(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        mins = int(message.text)
        end = time.time() + (mins * 60)
        await execute_db("UPDATE server_settings SET luck_mult = ?, luck_end = ? WHERE id = 1", (data['mult'], end))
        await log_admin(message.from_user.id, f"LUCK EVENT x{data['mult']} for {mins}m")
        await message.answer("✅ Ивент Удачи запущен. Начинаю рассылку...")
        await state.clear()
        
        ru_text = f"🍀 <b>ГЛОБАЛЬНЫЙ ИВЕНТ УДАЧИ!</b>\nШанс на редкие карты увеличен в {data['mult']} раз на {mins} минут! Загляните в Индекс, чтобы увидеть шансы!\n\n/getcard"
        asyncio.create_task(broadcast_message(ru_text, notif_type="notif_events"))
    except:
        await message.answer("Ошибка ввода.")

@dp.callback_query(F.data == "ev_cd")
async def ev_cd_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи множитель СКОРОСТИ (например 2.0 сделает откат в 2 раза быстрее):")
    await state.set_state(EventCD.mult)
    await callback.answer()

@dp.message(EventCD.mult)
async def ev_cd_mult(message: types.Message, state: FSMContext):
    await state.update_data(mult=float(message.text.replace(',','.')))
    await message.answer("На сколько МИНУТ запускаем?")
    await state.set_state(EventCD.mins)

@dp.message(EventCD.mins)
async def ev_cd_finish(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        mins = int(message.text)
        end = time.time() + (mins * 60)
        await execute_db("UPDATE server_settings SET cd_mult = ?, cd_end = ? WHERE id = 1", (data['mult'], end))
        await log_admin(message.from_user.id, f"CD EVENT x{data['mult']} for {mins}m")
        await message.answer("✅ Ивент Скорости запущен. Начинаю рассылку...")
        await state.clear()
        
        ru_text = f"⏳ <b>ГЛОБАЛЬНЫЙ ИВЕНТ СКОРОСТИ!</b>\nТаймер выбивания карт ускорен в {data['mult']} раз на {mins} минут!\n\n/getcard"
        asyncio.create_task(broadcast_message(ru_text, notif_type="notif_events"))
    except:
        await message.answer("Ошибка ввода.")

@dp.callback_query(F.data == "ev_coin")
async def ev_coin_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи множитель ШЕКЕЛЕЙ (например 1.5 или 2.0 для х2 за бои):")
    await state.set_state(EventCoin.mult)
    await callback.answer()

@dp.message(EventCoin.mult)
async def ev_coin_mult(message: types.Message, state: FSMContext):
    await state.update_data(mult=float(message.text.replace(',','.')))
    await message.answer("На сколько МИНУТ запускаем?")
    await state.set_state(EventCoin.mins)

@dp.message(EventCoin.mins)
async def ev_coin_finish(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        mins = int(message.text)
        end = time.time() + (mins * 60)
        await execute_db("UPDATE server_settings SET coin_mult = ?, coin_end = ? WHERE id = 1", (data['mult'], end))
        await log_admin(message.from_user.id, f"COIN EVENT x{data['mult']} for {mins}m")
        await message.answer("✅ Ивент Множителя монет запущен. Начинаю рассылку...")
        await state.clear()
        
        ru_text = f"💰 <b>ГЛОБАЛЬНЫЙ ИВЕНТ МОНЕТ!</b>\nПолучаемые шекели в боях против ИИ увеличены в {data['mult']} раз на {mins} минут!\n\n/pve"
        asyncio.create_task(broadcast_message(ru_text, notif_type="notif_events"))
    except:
        await message.answer("Ошибка ввода.")

@dp.callback_query(F.data == "ev_xp")
async def ev_xp_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи множитель ОПЫТА БП (например 2.0 для х2 опыта за бои):")
    await state.set_state(EventXP.mult)
    await callback.answer()

@dp.message(EventXP.mult)
async def ev_xp_mult(message: types.Message, state: FSMContext):
    try:
        await state.update_data(mult=float(message.text.replace(',', '.')))
        await message.answer("На сколько МИНУТ запускаем?")
        await state.set_state(EventXP.mins)
    except ValueError:
        await message.answer("❌ Введите корректный множитель (число).")

@dp.message(EventXP.mins)
async def ev_xp_finish(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        mins = int(message.text)
        end = time.time() + (mins * 60)
        await execute_db("UPDATE server_settings SET xp_mult = ?, xp_end = ? WHERE id = 1", (data['mult'], end))
        await log_admin(message.from_user.id, f"XP EVENT x{data['mult']} for {mins}m")
        await message.answer("✅ Ивент Множителя опыта БП запущен. Начинаю рассылку...")
        await state.clear()
        
        ru_text = f"🎫 <b>ГЛОБАЛЬНЫЙ ИВЕНТ НА ОПЫТ БП!</b>\nПолучаемый опыт Батл-пасса во всех боях увеличен в {data['mult']} раз на {mins} минут!\n\n/pve"
        asyncio.create_task(broadcast_message(ru_text, notif_type="notif_events"))
    except Exception as e:
        await message.answer(f"Ошибка ввода: {e}")
        await state.clear()

@dp.message(Command("announce"))
async def cmd_announce(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await message.answer("📢 <b>Глобальная Рассылка</b>\nОтправьте сообщение (текст, фото или видео с текстом), которое нужно разослать всем игрокам:")
    await state.set_state(AdminAnnounce.content)

@dp.message(AdminAnnounce.content)
async def process_announce(message: types.Message, state: FSMContext):
    users = await fetch_all("SELECT id FROM users WHERE banned = 0 AND notif_announces = 1")
    success = 0
    await message.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей (у кого включены анонсы)...")
    for u in users:
        try:
            await message.send_copy(chat_id=u['id'])
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Рассылка успешно завершена!\nДоставлено: {success} из {len(users)}")
    await log_admin(message.from_user.id, f"Использовал команду /announce (разослано {success} игрокам)")
    await state.clear()

@dp.message(Command("restock"))
async def cmd_admin_restock(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await restock_shop()
    await message.answer("✅ Ассортимент глобального магазина принудительно обновлен! Рассылка запущена.")

@dp.callback_query(F.data == "adm_db")
async def adm_db_func(callback: types.CallbackQuery):
    file = FSInputFile(DB_NAME)
    await callback.message.answer_document(file, caption="📦 Текущая БД. Чтобы восстановить/заменить, просто отправьте мне новый .db файл.")
    await callback.answer()

@dp.message(F.document)
async def process_bd_upload(message: types.Message):
    if not await is_admin(message.from_user.id): return
    if not message.document.file_name.endswith(".db"): return
    file = await bot.get_file(message.document.file_id)
    
    for ext in ["-wal", "-shm", "-journal"]:
        try:
            os.remove(f"{DB_NAME}{ext}")
        except OSError:
            pass
            
    await bot.download_file(file.file_path, DB_NAME)
    await check_and_update_schema()
    await log_admin(message.from_user.id, "DB Upload and Migration")
    await message.answer("✅ <b>БД успешно загружена и заменена!</b>")

@dp.callback_query(F.data == "adm_craft_main")
async def adm_craft_main(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать рецепт", callback_data="adm_craft_create")],
        [InlineKeyboardButton(text="✏️ Изменить рецепт", callback_data="adm_craft_edit_list")],
        [InlineKeyboardButton(text="🗑 Удалить рецепт", callback_data="adm_craft_delete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("🔨 <b>Управление Рецептами Крафта</b>\nЗдесь вы можете настраивать рецепты для создания карт.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "adm_craft_edit_list")
async def adm_craft_edit_list(callback: types.CallbackQuery):
    recipes = await fetch_all("SELECT r.id, c.name FROM craft_recipes r JOIN cards c ON r.target_card_id = c.id")
    if not recipes: return await callback.answer("Нет рецептов.", show_alert=True)
    
    kb = []
    for r in recipes:
        kb.append([InlineKeyboardButton(text=f"✏️ Изменить: {r['name']}", callback_data=f"adm_cr_ed_{r['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="adm_craft_main")])
    await callback.message.edit_text("Выберите рецепт для изменения:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_cr_ed_"))
async def adm_craft_edit_menu(callback: types.CallbackQuery, state: FSMContext):
    r_id = int(callback.data.split("_")[3])
    await state.update_data(editing_recipe_id=r_id)
    await show_craft_edit_menu(callback.message, state)
    await callback.answer()

async def show_craft_edit_menu(message_or_call, state: FSMContext):
    data = await state.get_data()
    r_id = data['editing_recipe_id']
    recipe = await fetch_one("SELECT r.id, r.price, c.name FROM craft_recipes r JOIN cards c ON r.target_card_id = c.id WHERE r.id = ?", (r_id,))
    ingredients = await fetch_all("SELECT i.id as ing_id, c.name, i.amount FROM craft_ingredients i JOIN cards c ON i.card_id = c.id WHERE i.recipe_id = ?", (r_id,))
    
    text = f"🔨 <b>Изменение рецепта: {recipe['name']}</b>\nЦена крафта: <b>{recipe['price']} 💰</b>\n\nИнгредиенты:\n"
    if not ingredients: text += "<i>Пусто</i>\n"
    else:
        for idx, ing in enumerate(ingredients, 1):
            text += f"{idx}. {ing['name']} x{ing['amount']}\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить цену", callback_data="cr_ed_price")],
        [InlineKeyboardButton(text="➕ Добавить ингредиент", callback_data="cr_ed_add_ing")],
        [InlineKeyboardButton(text="🗑 Удалить ингредиент", callback_data="cr_ed_del_ing")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_craft_edit_list")]
    ])
    
    if isinstance(message_or_call, types.Message): await message_or_call.answer(text, reply_markup=kb)
    else: await message_or_call.edit_text(text, reply_markup=kb)
    await state.set_state(AdminCraftEdit.menu)

@dp.callback_query(AdminCraftEdit.menu, F.data == "cr_ed_price")
async def cr_ed_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новую цену крафта в шекелях:")
    await state.set_state(AdminCraftEdit.edit_price)
    await callback.answer()

@dp.message(AdminCraftEdit.edit_price)
async def cr_ed_price_save(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        if price < 0: raise ValueError
        data = await state.get_data()
        r_id = data['editing_recipe_id']
        await execute_db("UPDATE craft_recipes SET price = ? WHERE id = ?", (price, r_id))
        await message.answer("✅ Цена обновлена!")
        await show_craft_edit_menu(message, state)
    except:
        await message.answer("❌ Введите положительное число.")

@dp.callback_query(AdminCraftEdit.menu, F.data == "cr_ed_add_ing")
async def cr_ed_add_ing(callback: types.CallbackQuery, state: FSMContext):
    all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {c['name']} (ID:{c['id']})"} for c in all_cards]
    await state.update_data(craft_items=items)
    kb = get_pagination_keyboard(items, 0, "cred_ing", columns=1, items_per_page=8)
    await callback.message.edit_text("Выберите карту-ингредиент для добавления:", reply_markup=kb)
    await state.set_state(AdminCraftEdit.add_ing_card)
    await callback.answer()

@dp.callback_query(AdminCraftEdit.add_ing_card, F.data.startswith("cred_ing_page_"))
async def cr_ed_add_ing_pag(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('craft_items', []), page, "cred_ing", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminCraftEdit.add_ing_card, F.data.startswith("cred_ing_"))
async def cr_ed_add_ing_sel(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[2])
    await state.update_data(cr_curr_ing=card_id)
    await callback.message.edit_text("Введите количество требуемых штук (например: 5):")
    await state.set_state(AdminCraftEdit.add_ing_amount)
    await callback.answer()

@dp.message(AdminCraftEdit.add_ing_amount)
async def cr_ed_add_ing_amt(message: types.Message, state: FSMContext):
    try:
        amt = int(message.text)
        if amt <= 0: raise ValueError
        data = await state.get_data()
        r_id = data['editing_recipe_id']
        c_id = data['cr_curr_ing']
        await execute_db("INSERT INTO craft_ingredients (recipe_id, card_id, amount) VALUES (?, ?, ?)", (r_id, c_id, amt))
        await message.answer("✅ Ингредиент добавлен!")
        await show_craft_edit_menu(message, state)
    except:
        await message.answer("❌ Число > 0.")

@dp.callback_query(AdminCraftEdit.menu, F.data == "cr_ed_del_ing")
async def cr_ed_del_ing(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    r_id = data['editing_recipe_id']
    ingredients = await fetch_all("SELECT i.id as ing_id, c.name, i.amount FROM craft_ingredients i JOIN cards c ON i.card_id = c.id WHERE i.recipe_id = ?", (r_id,))
    if not ingredients: return await callback.answer("Нет ингредиентов для удаления.", show_alert=True)
    
    kb = []
    for ing in ingredients:
        kb.append([InlineKeyboardButton(text=f"🗑 {ing['name']} x{ing['amount']}", callback_data=f"cr_del_ing_{ing['ing_id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="cr_ed_back")])
    await callback.message.edit_text("Выберите ингредиент для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("cr_del_ing_"))
async def cr_del_ing_action(callback: types.CallbackQuery, state: FSMContext):
    ing_id = int(callback.data.split("_")[3])
    await execute_db("DELETE FROM craft_ingredients WHERE id = ?", (ing_id,))
    await callback.answer("✅ Ингредиент удален!", show_alert=True)
    await show_craft_edit_menu(callback.message, state)

@dp.callback_query(F.data == "cr_ed_back")
async def cr_ed_back(callback: types.CallbackQuery, state: FSMContext):
    await show_craft_edit_menu(callback.message, state)
    await callback.answer()

@dp.callback_query(F.data == "adm_craft_delete")
async def adm_craft_del_list(callback: types.CallbackQuery):
    recipes = await fetch_all("SELECT r.id, c.name FROM craft_recipes r JOIN cards c ON r.target_card_id = c.id")
    if not recipes: return await callback.answer("Нет рецептов.", show_alert=True)
    
    kb = []
    for r in recipes:
        kb.append([InlineKeyboardButton(text=f"🗑 Удалить: {r['name']}", callback_data=f"adm_cr_del_{r['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="adm_craft_main")])
    await callback.message.edit_text("Выберите рецепт для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_cr_del_"))
async def adm_craft_del_action(callback: types.CallbackQuery):
    r_id = int(callback.data.split("_")[3])
    await execute_db("DELETE FROM craft_recipes WHERE id = ?", (r_id,))
    await execute_db("DELETE FROM craft_ingredients WHERE recipe_id = ?", (r_id,))
    await callback.answer("✅ Рецепт удален!", show_alert=True)
    await adm_craft_main(callback)

@dp.callback_query(F.data == "adm_craft_create")
async def adm_craft_cr_start(callback: types.CallbackQuery, state: FSMContext):
    all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {c['name']} (ID:{c['id']})"} for c in all_cards]
    await state.update_data(craft_items=items)
    kb = get_pagination_keyboard(items, 0, "crc_target", columns=1, items_per_page=8)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="adm_craft_main")])
    await callback.message.edit_text("🔨 <b>Шаг 1: Выберите карту, которая получится при крафте:</b>", reply_markup=kb)
    await state.set_state(AdminCraftCreate.target_card)
    await callback.answer()

@dp.callback_query(AdminCraftCreate.target_card, F.data.startswith("crc_target_page_"))
async def adm_craft_cr_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('craft_items', []), page, "crc_target", columns=1, items_per_page=8)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="adm_craft_main")])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminCraftCreate.target_card, F.data.startswith("crc_target_"))
async def adm_craft_cr_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[2])
    await state.update_data(cr_target=card_id, cr_ings=[])
    await callback.message.edit_text("🔨 <b>Шаг 2: Введите цену крафта в Шекелях (например: 50000):</b>")
    await state.set_state(AdminCraftCreate.price)
    await callback.answer()
    
@dp.message(AdminCraftCreate.price)
async def adm_craft_cr_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        if price < 0: raise ValueError
        await state.update_data(cr_price=price)
        await adm_craft_cr_show_menu(message, state)
    except:
        await message.answer("❌ Введите положительное число.")

async def adm_craft_cr_show_menu(msg, state: FSMContext):
    data = await state.get_data()
    t_card = await fetch_one("SELECT name FROM cards WHERE id = ?", (data['cr_target'],))
    
    text = f"🔨 <b>Настройка Рецепта</b>\nЦель: <b>{t_card['name']}</b>\nЦена: <b>{data['cr_price']} 💰</b>\n\nИнгредиенты:\n"
    if not data['cr_ings']: text += "<i>Пусто</i>\n"
    else:
        for idx, ing in enumerate(data['cr_ings'], 1):
            c = await fetch_one("SELECT name FROM cards WHERE id = ?", (ing['card_id'],))
            text += f"{idx}. {c['name']} x{ing['amount']}\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить ингредиент", callback_data="cr_add_ing")],
        [InlineKeyboardButton(text="✅ Завершить и сохранить", callback_data="cr_save")]
    ])
    
    if isinstance(msg, types.CallbackQuery): await msg.message.edit_text(text, reply_markup=kb)
    else: await msg.answer(text, reply_markup=kb)
    await state.set_state(AdminCraftCreate.add_ingredient_card)

@dp.callback_query(AdminCraftCreate.add_ingredient_card, F.data == "cr_add_ing")
async def adm_craft_add_ing(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('craft_items', []), 0, "crc_ing", columns=1, items_per_page=8)
    await callback.message.edit_text("Выберите карту-ингредиент:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminCraftCreate.add_ingredient_card, F.data.startswith("crc_ing_page_"))
async def adm_craft_ing_pag(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('craft_items', []), page, "crc_ing", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminCraftCreate.add_ingredient_card, F.data.startswith("crc_ing_"))
async def adm_craft_ing_sel(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[2])
    await state.update_data(cr_curr_ing=card_id)
    await callback.message.edit_text("Введите количество требуемых штук (например: 5):")
    await state.set_state(AdminCraftCreate.add_ingredient_amount)
    await callback.answer()

@dp.message(AdminCraftCreate.add_ingredient_amount)
async def adm_craft_ing_amt(message: types.Message, state: FSMContext):
    try:
        amt = int(message.text)
        if amt <= 0: raise ValueError
        data = await state.get_data()
        data['cr_ings'].append({'card_id': data['cr_curr_ing'], 'amount': amt})
        await state.update_data(cr_ings=data['cr_ings'])
        await adm_craft_cr_show_menu(message, state)
    except:
        await message.answer("❌ Число > 0.")

@dp.callback_query(AdminCraftCreate.add_ingredient_card, F.data == "cr_save")
async def adm_craft_save(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data['cr_ings']: return await callback.answer("❌ Добавьте хотя бы 1 ингредиент!", show_alert=True)
    
    db = await get_db_connection()
    try:
        cur = await db.execute("INSERT INTO craft_recipes (target_card_id, price) VALUES (?, ?)", (data['cr_target'], data['cr_price']))
        r_id = cur.lastrowid
        for ing in data['cr_ings']:
            await db.execute("INSERT INTO craft_ingredients (recipe_id, card_id, amount) VALUES (?, ?, ?)", (r_id, ing['card_id'], ing['amount']))
        await db.commit()
        await callback.message.edit_text("✅ Рецепт успешно создан!")
    finally:
        await db.close()
    await state.clear()
    await callback.answer()

@dp.message(F.text == BTN_CRAFT)
@dp.message(Command("craft"))
async def cmd_craft_menu(message: types.Message):
    if await check_ban(message.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Рецепты", callback_data="craft_recipes_list")],
        [InlineKeyboardButton(text="✨ Улучшение мутаций", callback_data="craft_upgrade_list")]
    ])
    await message.answer("🔨 <b>МАСТЕРСКАЯ КРАФТА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите раздел:", reply_markup=kb)

@dp.callback_query(F.data == "craft_menu_main")
async def cb_craft_menu_main(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Рецепты", callback_data="craft_recipes_list")],
        [InlineKeyboardButton(text="✨ Улучшение мутаций", callback_data="craft_upgrade_list")]
    ])
    try: await callback.message.edit_text("🔨 <b>МАСТЕРСКАЯ КРАФТА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите раздел:", reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data == "craft_recipes_list")
async def cb_craft_recipes_list(callback: types.CallbackQuery):
    recipes = await fetch_all("SELECT r.id, c.name FROM craft_recipes r JOIN cards c ON r.target_card_id = c.id")
    if not recipes: return await callback.answer("Рецептов пока нет.", show_alert=True)
    
    items = [{"id": r['id'], "btn_text": f"🔨 {r['name']}"} for r in recipes]
    kb = get_pagination_keyboard(items, 0, "craft_rec", columns=1, items_per_page=8)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="craft_menu_main")])
    await callback.message.edit_text("📜 <b>Доступные Рецепты</b>:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("craft_rec_page_"))
async def cb_craft_recipes_pag(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[3])
    recipes = await fetch_all("SELECT r.id, c.name FROM craft_recipes r JOIN cards c ON r.target_card_id = c.id")
    items = [{"id": r['id'], "btn_text": f"🔨 {r['name']}"} for r in recipes]
    kb = get_pagination_keyboard(items, page, "craft_rec", columns=1, items_per_page=8)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="craft_menu_main")])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

async def render_user_craft_ui(msg_or_call, user_id, recipe_id):
    recipe = await fetch_one("SELECT target_card_id, price FROM craft_recipes WHERE id = ?", (recipe_id,))
    target_card = await fetch_one("SELECT name, photo_id, rarity FROM cards WHERE id = ?", (recipe['target_card_id'],))
    ingredients = await fetch_all("SELECT id, card_id, amount FROM craft_ingredients WHERE recipe_id = ?", (recipe_id,))
    user = await fetch_one("SELECT coins, pass_vip FROM users WHERE id = ?", (user_id,))
    
    discount = 0.9 if user['pass_vip'] == 1 else 1.0
    final_price = int(recipe['price'] * discount)
    
    session = active_craft_sessions.get(user_id)
    if not session or session['recipe_id'] != recipe_id:
        session = {'recipe_id': recipe_id, 'selected_slots': {}}
        for ing in ingredients:
            session['selected_slots'][ing['card_id']] = [] 
        active_craft_sessions[user_id] = session

    text = f"🔨 <b>КРАФТ: {target_card['name']}</b>\nСтоимость: {final_price} 💰 (У вас: {user['coins']})\n━━━━━━━━━━━━━━━━━━━━━━━━\nТребования для сборки:\n"
    
    all_filled = True
    gold_count = 0
    diamond_count = 0
    rainbow_count = 0
    total_needed = 0

    kb_btns = []
    
    for idx, ing in enumerate(ingredients, 1):
        c_name = (await fetch_one("SELECT name FROM cards WHERE id = ?", (ing['card_id'],)))['name']
        needed = ing['amount']
        total_needed += needed
        
        selected_for_this = session['selected_slots'].get(ing['card_id'], [])
        sel_count = sum(s['qty'] for s in selected_for_this)
        
        for s in selected_for_this:
            if s['mutation'] == 'Gold': gold_count += s['qty']
            if s['mutation'] == 'Diamond': diamond_count += s['qty']
            if s['mutation'] == 'Rainbow': rainbow_count += s['qty']

        text += f"{idx}. {c_name} (Собрано {sel_count}/{needed})\n"
        if sel_count < needed: 
            all_filled = False
            kb_btns.append([InlineKeyboardButton(text=f"➕ Добавить {c_name}", callback_data=f"ucraft_add_{recipe_id}_{ing['card_id']}")])

    text += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"⚠️ <i>Вы можете вкладывать любые версии карт. Чем больше мутированных вы вложите, тем выше шанс получить мутированный результат!</i>\n"
    
    if total_needed > 0:
        base_gold_chance = 20.0
        base_diamond_chance = 10.0
        base_rainbow_chance = 5.0
        
        bonus_gold = (gold_count / total_needed) * 80.0
        bonus_diamond = (diamond_count / total_needed) * 60.0
        bonus_rainbow = (rainbow_count / total_needed) * 50.0
        
        final_g = min(100.0, base_gold_chance + bonus_gold)
        final_d = min(100.0, base_diamond_chance + bonus_diamond)
        final_r = min(100.0, base_rainbow_chance + bonus_rainbow)
        text += f"Текущий шанс на ⭐ Золотую: ~{final_g:.1f}%\n"
        text += f"Текущий шанс на 💎 Алмазную: ~{final_d:.1f}%\n"
        text += f"Текущий шанс на 🌈 Радужную: ~{final_r:.1f}%\n"
    
    if all_filled:
        kb_btns.insert(0, [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ И СКРАФТИТЬ ✅", callback_data=f"ucraft_execute_{recipe_id}")])
        
    kb_btns.append([
        InlineKeyboardButton(text="⚡ Авто-заполнение", callback_data=f"ucraft_auto_{recipe_id}"),
        InlineKeyboardButton(text="🧹 Очистить слоты", callback_data=f"ucraft_clear_{recipe_id}")
    ])
    kb_btns.append([InlineKeyboardButton(text="🔙 К рецептам", callback_data="craft_recipes_list")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=kb_btns)
    if isinstance(msg_or_call, types.CallbackQuery):
        try: await msg_or_call.message.delete()
        except: pass
        await bot.send_photo(chat_id=user_id, photo=target_card['photo_id'], caption=text, reply_markup=markup)
    else:
        try: await msg_or_call.delete()
        except: pass
        await bot.send_photo(chat_id=user_id, photo=target_card['photo_id'], caption=text, reply_markup=markup)

@dp.callback_query(F.data.startswith("craft_rec_"))
async def cb_craft_rec_select(callback: types.CallbackQuery):
    if "page" in callback.data: return
    recipe_id = int(callback.data.split("_")[2])
    if callback.from_user.id in active_craft_sessions:
        active_craft_sessions.pop(callback.from_user.id)
    await render_user_craft_ui(callback, callback.from_user.id, recipe_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("ucraft_clear_"))
async def cb_ucraft_clear(callback: types.CallbackQuery):
    recipe_id = int(callback.data.split("_")[2])
    if callback.from_user.id in active_craft_sessions:
        active_craft_sessions.pop(callback.from_user.id)
    await render_user_craft_ui(callback, callback.from_user.id, recipe_id)
    await callback.answer("Слоты очищены!")

@dp.callback_query(F.data.startswith("ucraft_auto_"))
async def cb_ucraft_auto(callback: types.CallbackQuery):
    recipe_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    ingredients = await fetch_all("SELECT card_id, amount FROM craft_ingredients WHERE recipe_id = ?", (recipe_id,))
    session = active_craft_sessions.get(user_id)
    if not session: return await callback.answer("Ошибка сессии", show_alert=True)

    for ing in ingredients:
        c_id = ing['card_id']
        needed = ing['amount']
        
        selected_now = session['selected_slots'].get(c_id, [])
        sel_count = sum(s['qty'] for s in selected_now)
        if sel_count >= needed: continue
        
        rem_needed = needed - sel_count
        
        invs = await fetch_all("""
            SELECT id, count, mutation, serial_number, signed_by 
            FROM inventory 
            WHERE user_id = ? AND card_id = ?
            ORDER BY 
                CASE mutation WHEN 'Normal' THEN 1 WHEN 'Gold' THEN 2 WHEN 'Diamond' THEN 3 WHEN 'Rainbow' THEN 4 END ASC,
                signed_by ASC, serial_number ASC
        """, (user_id, c_id))
        
        for inv_item in invs:
            if rem_needed <= 0: break
            
            already_taken = 0
            for s in selected_now:
                if s['inv_id'] == inv_item['id']: already_taken += s['qty']
                
            available = inv_item['count'] - already_taken
            if available <= 0: continue
            
            take = min(available, rem_needed)
            
            found = False
            for s in session['selected_slots'][c_id]:
                if s['inv_id'] == inv_item['id']:
                    s['qty'] += take
                    found = True
                    break
            if not found:
                session['selected_slots'][c_id].append({
                    'inv_id': inv_item['id'],
                    'qty': take,
                    'mutation': inv_item['mutation']
                })
                
            rem_needed -= take

    active_craft_sessions[user_id] = session
    await render_user_craft_ui(callback, user_id, recipe_id)
    await callback.answer("Авто-заполнение выполнено!")

@dp.callback_query(F.data.startswith("ucraft_add_"))
async def cb_ucraft_add(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    recipe_id = int(parts[2])
    card_id = int(parts[3])
    user_id = callback.from_user.id
    
    session = active_craft_sessions.get(user_id)
    if not session: return await callback.answer("Ошибка сессии")
    
    invs = await fetch_all("""
        SELECT i.id, i.count, i.mutation, i.serial_number, i.signed_by, c.name 
        FROM inventory i JOIN cards c ON i.card_id = c.id
        WHERE i.user_id = ? AND i.card_id = ?
    """, (user_id, card_id))
    
    items = []
    selected_now = session['selected_slots'].get(card_id, [])
    
    for i in invs:
        already_taken = sum(s['qty'] for s in selected_now if s['inv_id'] == i['id'])
        available = i['count'] - already_taken
        if available > 0:
            mut_str = "⭐" if i['mutation'] == 'Gold' else "💎" if i['mutation'] == 'Diamond' else "🌈" if i['mutation'] == 'Rainbow' else "⚪"
            sign_str = "✍️" if i['signed_by'] > 0 else ""
            ser_str = f"[#{i['serial_number']:04d}]" if i['serial_number'] > 0 else ""
            
            label = f"{mut_str} {i['name']} {ser_str}{sign_str} (Дост: {available})"
            items.append({"id": f"{recipe_id}_{card_id}_{i['id']}", "btn_text": label})
            
    if not items:
        return await callback.answer("У вас нет свободных подходящих карт!", show_alert=True)
        
    kb = get_pagination_keyboard(items, 0, "ucraft_sel", columns=1, items_per_page=8)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"craft_rec_{recipe_id}")]) 
    
    try: await callback.message.delete()
    except: pass
    await bot.send_message(user_id, f"Выберите конкретную копию для крафта:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("ucraft_sel_page_"))
async def cb_ucraft_sel_page(callback: types.CallbackQuery):
    await callback.answer("Используйте первые 8 карт.")

@dp.callback_query(F.data.startswith("ucraft_sel_"))
async def cb_ucraft_sel(callback: types.CallbackQuery):
    if "page" in callback.data: return
    parts = callback.data.split("_")
    recipe_id = int(parts[2])
    card_id = int(parts[3])
    inv_id = int(parts[4])
    user_id = callback.from_user.id
    
    session = active_craft_sessions.get(user_id)
    if not session: return await callback.answer("Сессия истекла")
    
    row = await fetch_one("SELECT count, mutation FROM inventory WHERE id = ?", (inv_id,))
    if not row: return await callback.answer("Не найдено")
    
    ing_needed = await fetch_one("SELECT amount FROM craft_ingredients WHERE recipe_id = ? AND card_id = ?", (recipe_id, card_id))
    if not ing_needed: return await callback.answer("Ошибка рецепта")
    
    needed = ing_needed['amount']
    selected_now = session['selected_slots'].get(card_id, [])
    sel_count = sum(s['qty'] for s in selected_now)
    
    rem_needed = needed - sel_count
    if rem_needed <= 0:
        return await callback.answer("Слот уже заполнен полностью!", show_alert=True)
        
    already_taken = sum(s['qty'] for s in selected_now if s['inv_id'] == inv_id)
    available = row['count'] - already_taken
    
    take = min(available, rem_needed)
    if take > 0:
        found = False
        for s in session['selected_slots'][card_id]:
            if s['inv_id'] == inv_id:
                s['qty'] += take
                found = True
                break
        if not found:
            session['selected_slots'][card_id].append({
                'inv_id': inv_id,
                'qty': take,
                'mutation': row['mutation']
            })
            
    active_craft_sessions[user_id] = session
    await render_user_craft_ui(callback, user_id, recipe_id)
    await callback.answer("Добавлено!")

@dp.callback_query(F.data.startswith("ucraft_execute_"))
async def cb_ucraft_execute(callback: types.CallbackQuery):
    recipe_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    session = active_craft_sessions.get(user_id)
    if not session or session['recipe_id'] != recipe_id:
        return await callback.answer("Ошибка сессии!", show_alert=True)
        
    recipe = await fetch_one("SELECT target_card_id, price FROM craft_recipes WHERE id = ?", (recipe_id,))
    ingredients = await fetch_all("SELECT card_id, amount FROM craft_ingredients WHERE recipe_id = ?", (recipe_id,))
    user = await fetch_one("SELECT coins, pass_vip FROM users WHERE id = ?", (user_id,))
    
    discount = 0.9 if user['pass_vip'] == 1 else 1.0
    final_price = int(recipe['price'] * discount)
    
    if user['coins'] < final_price:
        return await callback.answer("❌ Недостаточно шекелей!", show_alert=True)
        
    gold_count = 0
    diamond_count = 0
    rainbow_count = 0
    total_needed = 0
    
    to_delete = {} 
    
    for ing in ingredients:
        c_id = ing['card_id']
        needed = ing['amount']
        total_needed += needed
        
        sel = session['selected_slots'].get(c_id, [])
        sel_count = sum(s['qty'] for s in sel)
        if sel_count < needed:
            return await callback.answer("❌ Вы не заполнили все слоты!", show_alert=True)
            
        for s in sel:
            if s['mutation'] == 'Gold': gold_count += s['qty']
            elif s['mutation'] == 'Diamond': diamond_count += s['qty']
            elif s['mutation'] == 'Rainbow': rainbow_count += s['qty']
            to_delete[s['inv_id']] = to_delete.get(s['inv_id'], 0) + s['qty']
            
    db = await get_db_connection()
    try:
        await db.execute("BEGIN EXCLUSIVE") 
        
        for inv_id, qty in to_delete.items():
            row = await db.execute("SELECT count FROM inventory WHERE id = ? AND user_id = ?", (inv_id, user_id))
            r = await row.fetchone()
            if not r or r['count'] < qty:
                raise ValueError(f"Not enough cards")
                
        for inv_id, qty in to_delete.items():
            row = await db.execute("SELECT count FROM inventory WHERE id = ?", (inv_id,))
            r = await row.fetchone()
            if r['count'] == qty:
                await db.execute("DELETE FROM inventory WHERE id = ?", (inv_id,))
                for s in ['equip1', 'equip2', 'equip3', 'equip4', 'equip5']:
                    await db.execute(f"UPDATE users SET {s} = 0 WHERE id = ? AND {s} = ?", (user_id, inv_id))
            else:
                await db.execute("UPDATE inventory SET count = count - ? WHERE id = ?", (qty, inv_id))
                
        await db.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (final_price, user_id))
        await db.commit()
    except ValueError:
        await db.execute("ROLLBACK")
        return await callback.answer("❌ Ошибка: Выбраны несуществующие или уже потраченные карты.", show_alert=True)
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Craft Error: {e}")
        return await callback.answer("❌ Системная ошибка БД.", show_alert=True)
    finally:
        await db.close()
        
    active_craft_sessions.pop(user_id, None)
    await add_quest_progress_new(user_id, 'q_craft', 1)
    
    target_card = await fetch_one("SELECT * FROM cards WHERE id = ?", (recipe['target_card_id'],))
    
    base_gold_chance = 20.0
    base_diamond_chance = 10.0
    base_rainbow_chance = 5.0
    bonus_gold = (gold_count / total_needed) * 80.0
    bonus_diamond = (diamond_count / total_needed) * 60.0
    bonus_rainbow = (rainbow_count / total_needed) * 50.0
    
    final_g = min(100.0, base_gold_chance + bonus_gold)
    final_d = min(100.0, base_diamond_chance + bonus_diamond)
    final_r = min(100.0, base_rainbow_chance + bonus_rainbow)
    
    rand_val = random.random() * 100.0
    if rand_val < final_r: result_mut = "Rainbow"
    elif rand_val < final_r + final_d: result_mut = "Diamond"
    elif rand_val < final_r + final_d + final_g: result_mut = "Gold"
    else: result_mut = "Normal"
    
    _, serial, _ = await give_card_to_user(user_id, target_card['id'], result_mut, target_card['rarity'])
    
    target_card['mutation'] = result_mut
    target_card['serial_number'] = serial
    target_card['signed_by'] = 0
    
    await log_user_action(user_id, f"Скрафтил {target_card['name']} (Mut: {result_mut})")
    
    mut_str = "🌈 Радужная" if result_mut == 'Rainbow' else ("💎 Алмазная" if result_mut == 'Diamond' else ("⭐ Золотая" if result_mut == 'Gold' else "Обычная"))
    text = f"🎉 <b>КРАФТ УСПЕШЕН!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВы создали: {format_card_name(target_card)}\nМутация: <b>{mut_str}</b>\n\nШансы были: Золото {final_g:.1f}%, Алмаз {final_d:.1f}%, Радуга {final_r:.1f}%\nКарта добавлена в инвентарь!"
    
    try: await callback.message.delete()
    except: pass
    await bot.send_photo(chat_id=user_id, photo=target_card['photo_id'], caption=text)
    await callback.answer()

@dp.callback_query(F.data == "craft_upgrade_list")
async def cb_craft_upgrade_list(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_info = await fetch_one("SELECT pass_vip FROM users WHERE id = ?", (user_id,))
    is_vip = user_info and user_info['pass_vip'] == 1
    req_count = 4 if is_vip else 8

    invs = await fetch_all(f"""
        SELECT card_id, mutation, SUM(count) as total
        FROM inventory
        WHERE user_id = ? AND signed_by = 0
        GROUP BY card_id, mutation
        HAVING total >= {req_count}
    """, (user_id,))
    
    if not invs:
        return await callback.answer(f"У вас нет {req_count} одинаковых копий одной мутации (без росписи) для улучшения.", show_alert=True)
        
    items = []
    for r in invs:
        if r['mutation'] == 'Rainbow': continue
        
        c_info = await fetch_one("SELECT name, rarity FROM cards WHERE id = ?", (r['card_id'],))
        if not c_info: continue
        
        from_mut = "⚪" if r['mutation'] == 'Normal' else ("⭐" if r['mutation'] == 'Gold' else "💎")
        to_mut = "⭐" if r['mutation'] == 'Normal' else ("💎" if r['mutation'] == 'Gold' else "🌈")
        
        items.append({
            "id": f"{r['card_id']}_{r['mutation']}",
            "btn_text": f"✨ {from_mut} {c_info['name']} ➡️ {to_mut}"
        })
        
    if not items:
        return await callback.answer("Нет доступных улучшений.", show_alert=True)
        
    kb = get_pagination_keyboard(items, 0, "crupgrade", columns=1, items_per_page=8)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="craft_menu_main")])
    await callback.message.edit_text(f"✨ <b>ДОСТУПНЫЕ УЛУЧШЕНИЯ</b>\nТребуется {req_count} карт для слияния.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("crupgrade_page_"))
async def cb_cr_upg_pag(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    user_info = await fetch_one("SELECT pass_vip FROM users WHERE id = ?", (user_id,))
    is_vip = user_info and user_info['pass_vip'] == 1
    req_count = 4 if is_vip else 8

    invs = await fetch_all(f"""
        SELECT card_id, mutation, SUM(count) as total
        FROM inventory
        WHERE user_id = ? AND signed_by = 0
        GROUP BY card_id, mutation
        HAVING total >= {req_count}
    """, (user_id,))
    
    items = []
    for r in invs:
        if r['mutation'] == 'Rainbow': continue
        c_info = await fetch_one("SELECT name, rarity FROM cards WHERE id = ?", (r['card_id'],))
        if not c_info: continue
        from_mut = "⚪" if r['mutation'] == 'Normal' else ("⭐" if r['mutation'] == 'Gold' else "💎")
        to_mut = "⭐" if r['mutation'] == 'Normal' else ("💎" if r['mutation'] == 'Gold' else "🌈")
        items.append({
            "id": f"{r['card_id']}_{r['mutation']}",
            "btn_text": f"✨ {from_mut} {c_info['name']} ➡️ {to_mut}"
        })
        
    kb = get_pagination_keyboard(items, page, "crupgrade", columns=1, items_per_page=8)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="craft_menu_main")])
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("crupgrade_"))
async def cb_cr_upg_select(callback: types.CallbackQuery):
    if "page" in callback.data: return
    parts = callback.data.split("_")
    card_id = int(parts[1])
    mutation = parts[2]
    user_id = callback.from_user.id
    
    c_info = await fetch_one("SELECT name FROM cards WHERE id = ?", (card_id,))
    from_mut = "⚪ Обычная" if mutation == 'Normal' else ("⭐ Золотая" if mutation == 'Gold' else "💎 Алмазная")
    to_mut = "⭐ Золотую" if mutation == 'Normal' else ("💎 Алмазную" if mutation == 'Gold' else "🌈 Радужную")
    
    total = (await fetch_one("SELECT SUM(count) as t FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND signed_by = 0", (user_id, card_id, mutation)))['t']
    user_info = await fetch_one("SELECT pass_vip FROM users WHERE id = ?", (user_id,))
    is_vip = user_info and user_info['pass_vip'] == 1
    req_count = 4 if is_vip else 8

    text = f"✨ <b>Улучшение: {c_info['name']}</b>\nИз {from_mut} в {to_mut}.\n\nУ вас есть: {total} шт. Требуется: {req_count} шт.\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ СЛИЯНИЕ", callback_data=f"crup_confirm_{card_id}_{mutation}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="craft_upgrade_list")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("crup_confirm_"))
async def cb_crup_confirm(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    card_id = int(parts[2])
    mutation = parts[3]
    user_id = callback.from_user.id
    
    to_mut = "Gold" if mutation == 'Normal' else ("Diamond" if mutation == 'Gold' else "Rainbow")
    user_info = await fetch_one("SELECT pass_vip FROM users WHERE id = ?", (user_id,))
    is_vip = user_info and user_info['pass_vip'] == 1
    needed = 4 if is_vip else 8

    db = await get_db_connection()
    try:
        await db.execute("BEGIN EXCLUSIVE")
        cur = await db.execute("SELECT SUM(count) as t FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND signed_by = 0", (user_id, card_id, mutation))
        row = await cur.fetchone()
        if not row or row['t'] is None or row['t'] < needed:
            raise ValueError("Not enough")
            
        cur = await db.execute("SELECT id, count FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND signed_by = 0 ORDER BY id ASC", (user_id, card_id, mutation))
        packs = await cur.fetchall()
        for pack in packs:
            if needed <= 0: break
            take = min(needed, pack['count'])
            if take == pack['count']:
                await db.execute("DELETE FROM inventory WHERE id = ?", (pack['id'],))
                for s in ['equip1', 'equip2', 'equip3', 'equip4', 'equip5']:
                    await db.execute(f"UPDATE users SET {s} = 0 WHERE id = ? AND {s} = ?", (user_id, pack['id']))
            else:
                await db.execute("UPDATE inventory SET count = count - ? WHERE id = ?", (take, pack['id']))
            needed -= take
        await db.commit()
    except ValueError:
        await db.execute("ROLLBACK")
        return await callback.answer("Ошибка слияния! Не хватает карт.", show_alert=True)
    except Exception as e:
        await db.execute("ROLLBACK")
        return await callback.answer("Системная ошибка.", show_alert=True)
    finally:
        await db.close()
        
    target_card = await fetch_one("SELECT * FROM cards WHERE id = ?", (card_id,))
    _, serial, _ = await give_card_to_user(user_id, target_card['id'], to_mut, target_card['rarity'])
    
    target_card['mutation'] = to_mut
    target_card['serial_number'] = serial
    target_card['signed_by'] = 0
    
    await log_user_action(user_id, f"Улучшил {target_card['name']} до {to_mut}")
    await add_quest_progress_new(user_id, 'q_upgrade', 1)
    
    mut_str = "🌈 Радужная" if to_mut == 'Rainbow' else ("💎 Алмазная" if to_mut == 'Diamond' else "⭐ Золотая")
    text = f"🎉 <b>УЛУЧШЕНИЕ УСПЕШНО!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВы получили: {format_card_name(target_card)}\nНовая Мутация: <b>{mut_str}</b>\n\nКарта добавлена в инвентарь!"
    await callback.message.edit_text(text, reply_markup=None)
    await callback.answer()

@dp.callback_query(F.data == "adm_admins")
async def cq_adm_admins(callback: types.CallbackQuery):
    if callback.from_user.id != SUPER_ADMIN_ID: return await callback.answer("Только для Супер-Админа!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="adm_add_admin"), InlineKeyboardButton(text="➖ Удалить", callback_data="adm_del_admin")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("👑 <b>Управление Администраторами</b>", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_admin")
async def cq_adm_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID пользователя для выдачи прав админа:")
    await state.set_state(AdminManage.add_id)
    await callback.answer()

@dp.message(AdminManage.add_id)
async def cq_adm_add_msg(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await execute_db("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
        await message.answer(f"✅ Пользователь {uid} назначен администратором.")
    except: await message.answer("❌ Должно быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_del_admin")
async def cq_adm_del(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID администратора для снятия прав:")
    await state.set_state(AdminManage.del_id)
    await callback.answer()

@dp.message(AdminManage.del_id)
async def cq_adm_del_msg(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        if uid == SUPER_ADMIN_ID:
            await message.answer("❌ Нельзя удалить Супер-Админа!")
        else:
            await execute_db("DELETE FROM admins WHERE user_id = ?", (uid,))
            await message.answer(f"✅ Администратор {uid} удален.")
    except: await message.answer("❌ Должно быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_signers")
async def cq_adm_signers(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Нанять (Добавить)", callback_data="adm_sgn_add"), InlineKeyboardButton(text="➖ Уволить (Убрать)", callback_data="adm_sgn_del")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("✍️ <b>Управление Сигнерами</b>\nПользователи в этом списке получают кнопку «Подписать карту» и могут оставлять свои росписи.", reply_markup=kb)

@dp.callback_query(F.data == "adm_sgn_add")
async def cq_adm_sgn_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID или @username пользователя для выдачи прав Сигнера:")
    await state.set_state(AdminSigner.add_id)
    await callback.answer()

@dp.message(AdminSigner.add_id)
async def cq_adm_sgn_add_msg(message: types.Message, state: FSMContext):
    val = message.text.strip()
    target_user = None
    if val.isdigit(): target_user = await fetch_one("SELECT id FROM users WHERE id = ?", (int(val),))
    else: target_user = await fetch_one("SELECT id FROM users WHERE username = ?", (val.lstrip('@'),))
        
    if not target_user: await message.answer("❌ Пользователь не найден в базе данных бота.")
    else:
        uid = target_user['id']
        await execute_db("INSERT OR IGNORE INTO authorized_signers (user_id) VALUES (?)", (uid,))
        await message.answer(f"✅ Пользователь {uid} назначен Сигнером!\n\n<i>Чтобы у него появилась кнопка в меню, ему нужно отправить любое сообщение боту или нажать /start.</i>")
    await state.clear()

@dp.callback_query(F.data == "adm_sgn_del")
async def cq_adm_sgn_del(callback: types.CallbackQuery):
    signers = await fetch_all("""
        SELECT a.user_id, u.username, u.first_name 
        FROM authorized_signers a LEFT JOIN users u ON a.user_id = u.id
    """)
    if not signers: return await callback.answer("В списке никого нет.", show_alert=True)
    
    kb = []
    for s in signers:
        name = get_display_name({'username': s['username'], 'first_name': s['first_name'], 'id': s['user_id']})
        kb.append([InlineKeyboardButton(text=f"❌ {name}", callback_data=f"adm_sgn_rm_{s['user_id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_signers")])
    await callback.message.edit_text("Выберите Сигнера для снятия прав:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("adm_sgn_rm_"))
async def cq_adm_sgn_rm(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[3])
    await execute_db("DELETE FROM authorized_signers WHERE user_id = ?", (uid,))
    await callback.answer("✅ Пользователь уволен с должности Сигнера!", show_alert=True)
    await cq_adm_sgn_del(callback)

@dp.callback_query(F.data == "adm_cards")
async def cq_adm_cards(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="adm_card_add"), InlineKeyboardButton(text="✏️ Редактировать", callback_data="adm_card_edit_list")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="adm_card_del")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("🃏 <b>Управление Картами</b>", reply_markup=kb)

@dp.callback_query(F.data == "adm_card_add")
async def adm_card_add_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправь фото карты:")
    await state.set_state(AddCard.photo)
    await callback.answer()

@dp.message(AddCard.photo, F.photo)
async def add_card_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("Введи название:")
    await state.set_state(AddCard.name)

@dp.message(AddCard.name)
async def add_card_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введи БАЗОВЫЙ ШАНС (вес, например 0.1, 5, 100). Для Лидерборда или Секретных карт введи 0:")
    await state.set_state(AddCard.drop_chance)

@dp.message(AddCard.drop_chance)
async def add_card_chance(message: types.Message, state: FSMContext):
    try:
        chance = float(message.text.replace(',', '.'))
        await state.update_data(drop_chance=chance)
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=r)] for r in RARITY_COLORS.keys()], resize_keyboard=True)
        await message.answer("Выбери редкость:", reply_markup=kb)
        await state.set_state(AddCard.rarity)
    except: await message.answer("❌ Должно быть число!")

@dp.message(AddCard.rarity)
async def add_card_rarity(message: types.Message, state: FSMContext):
    if message.text not in RARITY_COLORS: return await message.answer("Выбери с клавиатуры.")
    await state.update_data(rarity=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=c)] for c in CLASSES], resize_keyboard=True)
    await message.answer("Выбери тип (класс):", reply_markup=kb)
    await state.set_state(AddCard.class_type)

@dp.message(AddCard.class_type)
async def add_card_class(message: types.Message, state: FSMContext):
    if message.text not in CLASSES: return await message.answer("Выбери с клавиатуры.")
    await state.update_data(class_type=message.text)
    
    if message.text == "Booster":
        await message.answer("Введи множитель УРОНА (например, 1.5):", reply_markup=ReplyKeyboardRemove())
        await state.set_state(AddCard.booster_dmg)
    elif message.text == "Healer":
        await message.answer("Введи базовую силу лечения (целое число):", reply_markup=ReplyKeyboardRemove())
        await state.set_state(AddCard.damage)
    else:
        await message.answer("Введи базовый урон (целое число):", reply_markup=ReplyKeyboardRemove())
        await state.set_state(AddCard.damage)

@dp.message(AddCard.booster_dmg)
async def add_card_boost_dmg(message: types.Message, state: FSMContext):
    try:
        await state.update_data(booster_dmg_mult=float(message.text.replace(',','.')), damage=0)
        await message.answer("Введи множитель ХП (например, 1.2):")
        await state.set_state(AddCard.booster_hp)
    except: await message.answer("❌ Число!")

@dp.message(AddCard.booster_hp)
async def add_card_boost_hp(message: types.Message, state: FSMContext):
    try:
        hp_mult = float(message.text.replace(',','.'))
        await state.update_data(booster_hp_mult=hp_mult)
        await state.set_state(AddCard.hp) 
        msg = message
        msg.text = "0"
        await add_card_finish(msg, state)
    except: await message.answer("❌ Число!")

@dp.message(AddCard.damage)
async def add_card_dmg(message: types.Message, state: FSMContext):
    try:
        await state.update_data(damage=int(message.text), booster_dmg_mult=1.0)
        await message.answer("Введи здоровье (хп):")
        await state.set_state(AddCard.hp)
    except: await message.answer("❌ Число!")

@dp.message(AddCard.hp)
async def add_card_finish(message: types.Message, state: FSMContext):
    try:
        hp = int(message.text)
        data = await state.get_data()
        await state.update_data(hp=hp, booster_hp_mult=data.get('booster_hp_mult', 1.0))
        data = await state.get_data()
        
        await message.answer("⏳ Генерирую рамку редкости для карты...", reply_markup=ReplyKeyboardRemove())
        
        new_photo_id = await create_bordered_image(bot, data['photo'], data['rarity'])
        await execute_db(
            "INSERT INTO cards (name, rarity, class_type, damage, hp, drop_chance, photo_id, booster_dmg_mult, booster_hp_mult) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data['name'], data['rarity'], data['class_type'], data.get('damage', 0), data.get('hp', 0), data['drop_chance'], new_photo_id, data.get('booster_dmg_mult', 1.0), data.get('booster_hp_mult', 1.0))
        )
        
        await log_admin(message.from_user.id, f"Создана карта: {data['name']}")
        await message.answer_photo(new_photo_id, caption=f"✅ <b>Карта {data['name']} создана!</b>", reply_markup=get_main_keyboard(await is_admin(message.from_user.id), await is_signer(message.from_user.id)))
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}"); await state.clear()

@dp.callback_query(F.data == "adm_card_edit_list")
async def adm_card_edit_start(callback: types.CallbackQuery, state: FSMContext):
    cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
    if not cards: return await callback.answer("В базе нет карт!", show_alert=True)
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {c['name']} (ID:{c['id']})"} for c in cards]
    await state.update_data(adm_edit_items=items)
    kb = get_pagination_keyboard(items, 0, "adm_ed_c", columns=1, items_per_page=8)
    await callback.message.edit_text("👇 Выберите карту для редактирования:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_ed_c_page_"))
async def adm_card_edit_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[4])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('adm_edit_items', []), page, "adm_ed_c", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_ed_c_"))
async def adm_card_edit_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    c_id = int(callback.data.split("_")[3])
    card = await fetch_one("SELECT * FROM cards WHERE id = ?", (c_id,))
    if not card: return await callback.answer("❌ Карта не найдена.")
    
    await state.update_data(edit_id=c_id)
    
    label_dmg = "Лечение" if card['class_type'] == "Healer" else "Урон"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Имя", callback_data="edit_val_name"), InlineKeyboardButton(text="✏️ Шанс (Вес)", callback_data="edit_val_chance")],
        [InlineKeyboardButton(text=f"✏️ {label_dmg}", callback_data="edit_val_dmg"), InlineKeyboardButton(text="✏️ ХП", callback_data="edit_val_hp")],
        [InlineKeyboardButton(text="✏️ Буст Урон", callback_data="edit_val_bdmg"), InlineKeyboardButton(text="✏️ Буст ХП", callback_data="edit_val_bhp")],
        [InlineKeyboardButton(text="✏️ Класс", callback_data="edit_val_class")]
    ])
    await callback.message.edit_text(f"Редактирование <b>{card['name']}</b> (ID: {c_id})\nЧто меняем?", reply_markup=kb)
    await state.set_state(EditCard.waiting_new_value)
    await callback.answer()

@dp.callback_query(EditCard.waiting_new_value, F.data.startswith("edit_val_"))
async def adm_card_edit_field(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[2]
    await state.update_data(edit_field=field)
    if field == "class":
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=c)] for c in CLASSES], resize_keyboard=True)
        await callback.message.answer("Выберите новый класс с клавиатуры:", reply_markup=kb)
    else:
        label = "значение силы исцеления" if field == "dmg" else f"новое значение для параметра {field}"
        await callback.message.answer(f"Отправь {label}:")
    await callback.answer()

@dp.message(EditCard.waiting_new_value)
async def adm_card_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    c_id = data['edit_id']
    field = data['edit_field']
    val = message.text
    
    col_map = {
        "name": ("name", str), "chance": ("drop_chance", float),
        "dmg": ("damage", int), "hp": ("hp", int),
        "bdmg": ("booster_dmg_mult", float), "bhp": ("booster_hp_mult", float),
        "class": ("class_type", str)
    }
    col, cast_fn = col_map[field]
    try:
        if field == "class" and val not in CLASSES: return await message.answer("Неверный класс.")
        val = cast_fn(val.replace(',', '.')) if cast_fn == float else cast_fn(val)
        await execute_db(f"UPDATE cards SET {col} = ? WHERE id = ?", (val, c_id))
        await log_admin(message.from_user.id, f"Edited card ID {c_id}, {col} = {val}")
        
        await message.answer("✅ Изменено!", reply_markup=get_main_keyboard(await is_admin(message.from_user.id), await is_signer(message.from_user.id)))
        await state.clear()
    except: await message.answer("❌ Неверный формат значения.")

@dp.callback_query(F.data == "adm_card_del")
async def adm_card_del_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введи ID карты для удаления:")
    await state.set_state("waiting_del_id")
    await callback.answer()

@dp.message(StateFilter("waiting_del_id"))
async def adm_card_del_finish(message: types.Message, state: FSMContext):
    try:
        c_id = int(message.text)
        await execute_db("DELETE FROM cards WHERE id = ?", (c_id,))
        invs = await fetch_all("SELECT id FROM inventory WHERE card_id = ?", (c_id,))
        inv_ids = [i['id'] for i in invs]
        await execute_db("DELETE FROM inventory WHERE card_id = ?", (c_id,))
        for i_id in inv_ids:
            for slot in ['equip1', 'equip2', 'equip3', 'equip4', 'equip5']:
                await execute_db(f"UPDATE users SET {slot} = 0 WHERE {slot} = ?", (i_id,))
                
        await log_admin(message.from_user.id, f"DELETED card ID {c_id}")
        await message.answer(f"✅ Карта {c_id} полностью удалена.")
    except: await message.answer("❌ Число.")
    await state.clear()

@dp.callback_query(F.data == "adm_users")
async def cq_adm_users(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Выдать карту", callback_data="adm_usr_givecard"),
         InlineKeyboardButton(text="➖ Забрать карту", callback_data="adm_usr_takecard")],
        [InlineKeyboardButton(text="💰 Выдать шекели/робуксы", callback_data="adm_usr_give_coins"),
         InlineKeyboardButton(text="🏆 Выдать кубки", callback_data="adm_usr_give_trophies")],
        [InlineKeyboardButton(text="🔄 Сбросить состояние", callback_data="adm_usr_reset_battle")],
        [InlineKeyboardButton(text="🔨 Бан / Разбан", callback_data="adm_usr_ban")],
        [InlineKeyboardButton(text="📜 Логи игроков", callback_data="adm_usr_logs_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("👤 <b>Управление Игроками</b>", reply_markup=kb)

@dp.callback_query(F.data == "adm_usr_logs_menu")
async def adm_usr_logs_menu_start(callback: types.CallbackQuery, state: FSMContext):
    recent_users = await fetch_all("""
        SELECT DISTINCT u.id, u.username, u.first_name 
        FROM user_action_logs l 
        JOIN users u ON l.user_id = u.id 
        ORDER BY l.timestamp DESC LIMIT 30
    """)
    
    items = []
    for u in recent_users:
        name = get_display_name(u)
        items.append({"id": u['id'], "btn_text": f"👤 {name} (ID:{u['id']})"})
        
    kb = get_pagination_keyboard(items, 0, "admlog_u", columns=1, items_per_page=10)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔍 Поиск по ID", callback_data="admlog_search_id")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_users")])
    
    await state.update_data(admlog_users=items)
    await callback.message.edit_text("📜 <b>Глобальные логи игроков</b>\nВыберите игрока из недавних активных или найдите по ID:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("admlog_u_page_"))
async def admlog_u_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('admlog_users', []), page, "admlog_u", columns=1, items_per_page=10)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔍 Поиск по ID", callback_data="admlog_search_id")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_users")])
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("admlog_u_"))
async def admlog_u_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    uid = int(callback.data.split("_")[2])
    await show_user_logs(callback, uid)

@dp.callback_query(F.data == "admlog_search_id")
async def admlog_search_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID игрока для просмотра его логов:")
    await state.set_state(AdminManage.view_logs_id)
    await callback.answer()

@dp.message(AdminManage.view_logs_id)
async def admlog_search_id_msg(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await show_user_logs_msg(message, uid)
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
    await state.clear()

async def show_user_logs(callback: types.CallbackQuery, uid: int):
    logs = await fetch_all("SELECT action, timestamp FROM user_action_logs WHERE user_id = ? ORDER BY id DESC LIMIT 50", (uid,))
    if not logs:
        return await callback.answer("У этого игрока нет логов.", show_alert=True)
        
    text = f"📜 <b>Последние 50 действий (ID: {uid}):</b>\n\n"
    for l in logs:
        text += f"🕒 {l['timestamp']}\n📝 {l['action']}\n\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="adm_usr_logs_menu")]])
    try: await callback.message.edit_text(text[:4000], reply_markup=kb)
    except: pass
    await callback.answer()
    
async def show_user_logs_msg(message: types.Message, uid: int):
    logs = await fetch_all("SELECT action, timestamp FROM user_action_logs WHERE user_id = ? ORDER BY id DESC LIMIT 50", (uid,))
    if not logs:
        return await message.answer("У этого игрока нет логов.")
        
    text = f"📜 <b>Последние 50 действий (ID: {uid}):</b>\n\n"
    for l in logs:
        text += f"🕒 {l['timestamp']}\n📝 {l['action']}\n\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="adm_usr_logs_menu")]])
    await message.answer(text[:4000], reply_markup=kb)

@dp.callback_query(F.data == "adm_usr_give_coins")
async def adm_usr_give_coins_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID игрока для выдачи:")
    await state.set_state(AdminManage.give_coins_id)
    await callback.answer()

@dp.message(AdminManage.give_coins_id)
async def adm_usr_give_coins_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(target_id=uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Шекели", callback_data="givecurr_coins"), InlineKeyboardButton(text="💎 Робуксы (R$)", callback_data="givecurr_robux")]
        ])
        await message.answer("Что именно выдать?", reply_markup=kb)
    except ValueError:
        await message.answer("❌ ID должен быть числом.")

@dp.callback_query(F.data.startswith("givecurr_"))
async def adm_usr_give_curr_type(callback: types.CallbackQuery, state: FSMContext):
    c_type = callback.data.split("_")[1]
    await state.update_data(give_curr_type=c_type)
    await callback.message.answer("Сколько выдать?")
    await state.set_state(AdminManage.give_coins_amount)
    await callback.answer()

@dp.message(AdminManage.give_coins_amount)
async def adm_usr_give_coins_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        uid = data['target_id']
        c_type = data['give_curr_type']
        
        if c_type == 'coins':
            await execute_db("UPDATE users SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (amount, amount, uid))
            msg_alert = f"🎁 Администратор выдал вам <b>{amount} 💰 Шекелей</b>!"
        else:
            await execute_db("UPDATE users SET robux = robux + ? WHERE id = ?", (amount, uid))
            msg_alert = f"💎 Администратор выдал вам <b>{amount} R$</b>!"
            
        await log_admin(message.from_user.id, f"Выдал {amount} {c_type} игроку {uid}")
        await message.answer(f"✅ Успешно выдано {amount} единиц валюты игроку {uid}.")
        try: await bot.send_message(uid, msg_alert)
        except: pass
    except ValueError:
        await message.answer("❌ Сумма должна быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_usr_give_trophies")
async def adm_usr_give_trophies_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID игрока для выдачи кубков:")
    await state.set_state(AdminManage.give_trophies_id)
    await callback.answer()

@dp.message(AdminManage.give_trophies_id)
async def adm_usr_give_trophies_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(target_id=uid)
        await message.answer("Сколько кубков выдать?")
        await state.set_state(AdminManage.give_trophies_amount)
    except ValueError:
        await message.answer("❌ ID должен быть числом.")

@dp.message(AdminManage.give_trophies_amount)
async def adm_usr_give_trophies_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        uid = data['target_id']
        
        await execute_db("UPDATE users SET trophies = trophies + ? WHERE id = ?", (amount, uid))
        await log_admin(message.from_user.id, f"Выдал {amount} кубков игроку {uid}")
        await message.answer(f"✅ Успешно выдано {amount} кубков игроку {uid}.")
        try:
            msg_alert = f"🏆 Администратор выдал вам <b>{amount} 🏆</b>!"
            await bot.send_message(uid, msg_alert)
        except: pass
    except ValueError:
        await message.answer("❌ Количество должно быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_usr_reset_battle")
async def adm_usr_reset_battle_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID игрока для сброса состояния боя и трейда:")
    await state.set_state(AdminManage.reset_battle_id)
    await callback.answer()

@dp.message(AdminManage.reset_battle_id)
async def adm_usr_reset_battle_finish(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        flag = False
        if uid in active_combats:
            active_combats.discard(uid)
            flag = True
        if uid in pvp_queue:
            pvp_queue.discard(uid)
            flag = True
        if uid in user_trades:
            await cancel_trade(user_trades[uid], reason="Отмена администратором")
            flag = True
            
        if flag:
            await message.answer(f"✅ Состояние для игрока {uid} успешно сброшено.")
            await log_admin(message.from_user.id, f"Сбросил состояние для {uid}")
        else:
            await message.answer("ℹ️ Игрок не находился в активном поиске/трейде.")
            
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_usr_givecard")
async def adm_usr_give(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID игрока, которому хотим выдать карту:")
    await state.set_state(GiveCard.user_id)
    await callback.answer()

@dp.message(GiveCard.user_id)
async def adm_usr_give_user(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(give_user_id=uid)
        all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
        items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '')} {c['name']} (ID:{c['id']})"} for c in all_cards]
        await state.update_data(give_items=items)
        kb = get_pagination_keyboard(items, 0, "give_c", columns=1, items_per_page=8)
        await message.answer("Выберите карту для выдачи:", reply_markup=kb)
        await state.set_state(GiveCard.card_id)
    except:
        await message.answer("❌ ID должен быть числом.")

@dp.callback_query(F.data.startswith("give_c_page_"), GiveCard.card_id)
async def adm_give_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('give_items', []), page, "give_c", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("give_c_"), GiveCard.card_id)
async def adm_give_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[2])
    await state.update_data(give_card_id=card_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚪ Обычная", callback_data="give_mut_Normal")],
        [InlineKeyboardButton(text="⭐ Золотая", callback_data="give_mut_Gold")],
        [InlineKeyboardButton(text="💎 Алмазная", callback_data="give_mut_Diamond")],
        [InlineKeyboardButton(text="🌈 Радужная", callback_data="give_mut_Rainbow")]
    ])
    await callback.message.edit_text("Выберите мутацию для карты:", reply_markup=kb)
    await state.set_state(GiveCard.mutation)
    await callback.answer()

@dp.callback_query(F.data.startswith("give_mut_"), GiveCard.mutation)
async def adm_give_mut_select(callback: types.CallbackQuery, state: FSMContext):
    mutation = callback.data.split("_")[2]
    await state.update_data(give_mutation=mutation)
    
    await callback.message.edit_text("Введите СЕРИЙНЫЙ НОМЕР для карты (от 1 до 9999) или введите 0, чтобы выдать строго БЕЗ номера:")
    await state.set_state(GiveCard.custom_serial)
    await callback.answer()

@dp.message(GiveCard.custom_serial)
async def adm_give_serial_save(message: types.Message, state: FSMContext):
    try:
        serial = int(message.text)
        if serial < 0 or serial > 9999: raise ValueError
        
        data = await state.get_data()
        user_id = data.get('give_user_id')
        card_id = data.get('give_card_id')
        mutation = data.get('give_mutation')
        
        if serial == 0:
            db = await get_db_connection()
            try:
                res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0", (user_id, card_id, mutation))
                inv_item = await res.fetchone()
                if inv_item:
                    await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                else:
                    await db.execute("INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by) VALUES (?, ?, 1, ?, 0, 0)", (user_id, card_id, mutation))
                await db.commit()
            finally:
                await db.close()
            assigned_serial = 0
        else:
            _, assigned_serial, _ = await give_card_to_user(user_id, card_id, mutation, custom_serial=serial)
            
        s_str = f" [#{assigned_serial:04d}]" if assigned_serial > 0 else ""
        await log_admin(message.from_user.id, f"GAVE card ID {card_id} (Mut:{mutation}, Serial:{assigned_serial}) to User {user_id}")
        await message.answer(f"✅ Карта (ID {card_id}) успешно выдана игроку {user_id}!\nМутация: {mutation}{s_str}")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число от 0 до 9999.")

@dp.callback_query(F.data == "adm_usr_takecard")
async def adm_usr_take_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID игрока, у которого хотим забрать карту (удалить):")
    await state.set_state(TakeCard.user_id)
    await callback.answer()

@dp.message(TakeCard.user_id)
async def adm_usr_take_user(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(take_user_id=uid)
        
        inv = await fetch_all("""
            SELECT i.id as inv_id, c.name, c.rarity, i.count, i.mutation, i.serial_number 
            FROM inventory i JOIN cards c ON i.card_id = c.id 
            WHERE i.user_id = ? AND i.count > 0
        """, (uid,))
        
        if not inv:
            return await message.answer("У этого пользователя пустой инвентарь или нет карт.")
            
        items = []
        for c in inv:
            mut_str = "⭐" if c['mutation'] == 'Gold' else ("💎" if c['mutation'] == 'Diamond' else ("🌈" if c['mutation'] == 'Rainbow' else "⚪"))
            ser_str = f" [#{c['serial_number']:04d}]" if c['serial_number'] > 0 else ""
            items.append({"id": c['inv_id'], "btn_text": f"{mut_str} {c['name']}{ser_str} (x{c['count']})"})
            
        await state.update_data(take_items=items)
        kb = get_pagination_keyboard(items, 0, "take_c", columns=1, items_per_page=8)
        await message.answer("Выберите карту для изъятия:", reply_markup=kb)
        await state.set_state(TakeCard.inv_id)
    except:
        await message.answer("❌ ID должен быть числом.")

@dp.callback_query(F.data.startswith("take_c_page_"), TakeCard.inv_id)
async def adm_take_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('take_items', []), page, "take_c", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("take_c_"), TakeCard.inv_id)
async def adm_take_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    await state.update_data(take_inv_id=inv_id)
    
    await callback.message.edit_text("Сколько штук удалить? (Введите число или 'all' для удаления всех копий):")
    await state.set_state(TakeCard.amount)
    await callback.answer()

@dp.message(TakeCard.amount)
async def adm_take_amount(message: types.Message, state: FSMContext):
    amt_str = message.text.lower()
    data = await state.get_data()
    uid = data['take_user_id']
    inv_id = data['take_inv_id']
    
    inv_item = await fetch_one("SELECT count FROM inventory WHERE id = ? AND user_id = ?", (inv_id, uid))
    if not inv_item:
        await message.answer("Ошибка: карта не найдена в инвентаре.")
        return await state.clear()
        
    count_have = inv_item['count']
    if amt_str == 'all':
        amt = count_have
    else:
        try:
            amt = int(amt_str)
            if amt <= 0: raise ValueError
        except:
            return await message.answer("Введите корректное число больше 0 или 'all'.")
            
    if amt > count_have:
        amt = count_have
        
    if amt == count_have:
        await execute_db("DELETE FROM inventory WHERE id = ?", (inv_id,))
        for slot in ['equip1', 'equip2', 'equip3', 'equip4', 'equip5']:
            await execute_db(f"UPDATE users SET {slot} = 0 WHERE id = ? AND {slot} = ?", (uid, inv_id))
    else:
        await execute_db("UPDATE inventory SET count = count - ? WHERE id = ?", (amt, inv_id))
        
    await log_admin(message.from_user.id, f"Изъял карту inv_id {inv_id} в кол-ве {amt} у {uid}")
    await message.answer(f"✅ Успешно удалено {amt} шт. карты из инвентаря пользователя {uid}.")
    await state.clear()

@dp.callback_query(F.data == "adm_usr_ban")
async def adm_usr_ban_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправь ID игрока для смены статуса бана (если забанен - разбанит):")
    await state.set_state(AdminBan.user_id)
    await callback.answer()

@dp.message(AdminBan.user_id)
async def adm_usr_ban_finish(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        usr = await fetch_one("SELECT banned FROM users WHERE id = ?", (uid,))
        if not usr: return await message.answer("Игрок не найден.")
        new_st = 0 if usr['banned'] == 1 else 1
        await execute_db("UPDATE users SET banned = ? WHERE id = ?", (new_st, uid))
        await log_admin(message.from_user.id, f"Set BAN status to {new_st} for {uid}")
        await message.answer(f"✅ Статус бана изменен на {new_st}.")
    except:
        pass
    await state.clear()

async def main():
    await check_and_update_schema()
    
    shop_exists = await fetch_all("SELECT * FROM shop_items")
    if not shop_exists: await restock_shop()
    
    settings = await fetch_one("SELECT last_lb_reward FROM server_settings WHERE id = 1")
    if settings and settings['last_lb_reward'] == 0:
        await execute_db("UPDATE server_settings SET last_lb_reward = ? WHERE id = 1", (time.time(),))
    
    asyncio.create_task(shop_auto_restock_task())
    asyncio.create_task(leaderboard_rewards_task())
    asyncio.create_task(trade_timeout_task())
    asyncio.create_task(auto_backup_db())
    
    commands = [
        BotCommand(command="start", description="Главное меню / Main Menu"),
        BotCommand(command="updatelog", description="История обновлений / Updates"),
        BotCommand(command="donate", description="Магазин Доната / Donate Shop"),
        BotCommand(command="help", description="Огромное руководство / Guide"),
        BotCommand(command="getcard", description="Выбить карту / Draw Card"),
        BotCommand(command="shop", description="Магазин / Shop"),
        BotCommand(command="inventory", description="Инвентарь / Inventory"),
        BotCommand(command="equip", description="Экипировка колоды / Equip Deck"),
        BotCommand(command="craft", description="Мастерская Крафта / Crafting"),
        BotCommand(command="profile", description="Профиль и статы / Profile & Stats"),
        BotCommand(command="trade", description="Обменяться картами / Trade Cards"),
        BotCommand(command="quests", description="Квесты / Quests"),
        BotCommand(command="index", description="Индекс всех карт / Card Index"),
        BotCommand(command="top", description="Рейтинг игроков / Leaderboard"),
        BotCommand(command="codereward", description="Активировать код / Redeem Code")
    ]
    await bot.set_my_commands(commands)
    
    logging.info("🤖 Карточный бот успешно перезапущен (Полный апдейт: Diamond Мутация, Донат Юниты, ИИ Бан)!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
