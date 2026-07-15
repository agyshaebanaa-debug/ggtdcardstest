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
import smtplib
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
    raise ImportError("Установите Pillow: pip install Pillow")

import aiosqlite

# ========================================================================
# КОНФИГУРАЦИЯ БОТА И ПОЧТЫ
# ========================================================================
BOT_TOKEN = "8887633400:AAEvlERe0CN1twoc01jGxYzSi8f9Kbwck1A"
SUPER_ADMIN_ID = 5341904332
DB_NAME = "cards_database.db"

# Данные для отправки писем подтверждения Gmail
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "ggtdcards@gmail.com"
SMTP_PASSWORD = "jfil xprl oduh ciuc"

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

# ========================================================================
# КОНСТАНТЫ И СЛОВАРИ С ЭМОДЗИ
# ========================================================================
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
    {"id": "q_fb", "desc": "Сыграть {} Cardball-матчей", "target": (2, 5)},
    {"id": "q_open", "desc": "Открыть {} любых карт", "target": (5, 15)},
    {"id": "q_upgrade", "desc": "Улучшить мутацию {} раз", "target": (1, 3)},
    {"id": "q_craft", "desc": "Скрафтить {} карт", "target": (1, 2)}
]

UPDATE_LOGS = [
    "🛠 <b>Update 2: Accounts & Trade Fixes</b>\n\n"
    "• <b>Система игровых аккаунтов</b>: Теперь можно создать до 3 игровых аккаунтов на один Telegram ID с помощью команды /register!\n"
    "• <b>Безопасность</b>: Авторизация в аккаунты с паролем и верификацией через Gmail почту (код подтверждения).\n"
    "• <b>Трейд Фикс</b>: Названия карт теперь полностью видны при обмене, а лимит Callback Data больше никогда не вешает меню!\n"
    "• <b>Ивенты в Cardball</b>: Глобальные ивенты монет и опыта BP теперь честно работают и в футбольных матчах!\n"
    "• <b>Гача Фикс</b>: Эксклюзивные Cardball юниты больше не выпадают в стандартной гаче.\n"
    "• <b>Коды-Награды</b>: Логика промокодов полностью переписана и защищена от ложных ошибок."
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
BTN_SET = "⚙️ Настройки"
BTN_SIGN = "✍️ Подписать карту"
BTN_ADM = "⚙️ Админ-панель"
BTN_ENDLESS = "♾ Бесконечный режим"
BTN_CRAFT = "🔨 Крафт"
BTN_WC = "⚽ World Cup 2026 (Cardball)"
BTN_MAIN_MODE = "🔙 В обычный режим"

BTN_FB_DRAW = "⚽ Cardball Гача"
BTN_FB_DRAW_REGULAR = "🎲 Обычная Гача (В Карболе)"
BTN_FB_SHOP = "🛒 Cardball Магазин"
BTN_FB_PACKS = "📦 Cardball Паки"
BTN_FB_BP = "🎟 Cardball БП"
BTN_FB_MATCH = "⚽ Cardball Матч"
BTN_FB_LEAGUE = "🏆 Cardball Лига"
BTN_FB_PROF = "👤 Cardball Профиль"
BTN_FB_EQ = "🛡 Состав (Cardball)"
BTN_FB_INV = "🎒 Cardball Инвентарь"
BTN_FB_TRANSFER = "✈️ Трансфер в Основу"
BTN_FB_INDEX = "📖 Cardball Индекс"
BTN_FB_GUIDE = "📖 Гайд по Cardball"

# ========================================================================
# БАЗА ДАННЫХ И СМАРТ-МИГРАЦИИ (АККАУНТЫ)
# ========================================================================
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
        # Старая таблица users для хранения базовых связей с Telegram и миграции
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                coins INTEGER DEFAULT 0,
                trophies INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                last_getcard REAL DEFAULT 0,
                last_fb_getcard REAL DEFAULT 0,
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
                notif_1_rnd INTEGER DEFAULT 1,
                notif_3_rnd INTEGER DEFAULT 1,
                notif_5_rnd INTEGER DEFAULT 1,
                notif_10_rnd INTEGER DEFAULT 1,
                notif_25_rnd INTEGER DEFAULT 1,
                notif_50_rnd INTEGER DEFAULT 1,
                notif_100_rnd INTEGER DEFAULT 1,
                notif_rnd_leg INTEGER DEFAULT 1,
                notif_rnd_myth INTEGER DEFAULT 1,
                notif_rnd_sup INTEGER DEFAULT 1,
                mod_enemy_hp INTEGER DEFAULT 0,
                mod_enemy_atk_all INTEGER DEFAULT 0,
                mod_enemy_stats INTEGER DEFAULT 0,
                mod_player_atk_all INTEGER DEFAULT 0,
                mod_manual_atk INTEGER DEFAULT 0,
                mod_player_hp INTEGER DEFAULT 0,
                football_mode INTEGER DEFAULT 0,
                football_balls INTEGER DEFAULT 0,
                football_trophies INTEGER DEFAULT 0,
                football_team_id INTEGER DEFAULT 0,
                fb_equip1 INTEGER DEFAULT 0,
                fb_equip2 INTEGER DEFAULT 0,
                fb_equip3 INTEGER DEFAULT 0,
                fb_equip4 INTEGER DEFAULT 0,
                last_transfer REAL DEFAULT 0,
                migrated_to_account INTEGER DEFAULT 0
            )
        """)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN migrated_to_account INTEGER DEFAULT 0")
        except aiosqlite.OperationalError:
            pass

        # Новая таблица Accounts для поддержки до 3-х аккаунтов на Telegram ID
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                nickname TEXT,
                username TEXT UNIQUE,
                password_hash TEXT,
                email TEXT,
                is_verified INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                coins INTEGER DEFAULT 0,
                trophies INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                last_getcard REAL DEFAULT 0,
                last_fb_getcard REAL DEFAULT 0,
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
                notif_1_rnd INTEGER DEFAULT 1,
                notif_3_rnd INTEGER DEFAULT 1,
                notif_5_rnd INTEGER DEFAULT 1,
                notif_10_rnd INTEGER DEFAULT 1,
                notif_25_rnd INTEGER DEFAULT 1,
                notif_50_rnd INTEGER DEFAULT 1,
                notif_100_rnd INTEGER DEFAULT 1,
                notif_rnd_leg INTEGER DEFAULT 1,
                notif_rnd_myth INTEGER DEFAULT 1,
                notif_rnd_sup INTEGER DEFAULT 1,
                mod_enemy_hp INTEGER DEFAULT 0,
                mod_enemy_atk_all INTEGER DEFAULT 0,
                mod_enemy_stats INTEGER DEFAULT 0,
                mod_player_atk_all INTEGER DEFAULT 0,
                mod_manual_atk INTEGER DEFAULT 0,
                mod_player_hp INTEGER DEFAULT 0,
                football_mode INTEGER DEFAULT 0,
                football_balls INTEGER DEFAULT 0,
                football_trophies INTEGER DEFAULT 0,
                football_team_id INTEGER DEFAULT 0,
                fb_equip1 INTEGER DEFAULT 0,
                fb_equip2 INTEGER DEFAULT 0,
                fb_equip3 INTEGER DEFAULT 0,
                fb_equip4 INTEGER DEFAULT 0,
                last_transfer REAL DEFAULT 0
            )
        """)

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
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, -- Теперь это ID аккаунта (accounts.id)
                card_id INTEGER,
                count INTEGER DEFAULT 1,
                mutation TEXT DEFAULT 'Normal',
                serial_number INTEGER DEFAULT 0,
                signed_by INTEGER DEFAULT 0, -- ID аккаунта подписавшего
                is_football INTEGER DEFAULT 0
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
            ("🌌 Uranium VI", 10000, 50.0, 9.0), ("🌌 Uranium VII", 15000, 60.0, 10.0)
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
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_seed_packs (
                user_id INTEGER, -- ID аккаунта (accounts.id)
                pack_id INTEGER,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, pack_id)
            )
        """)

        await db.execute("""CREATE TABLE IF NOT EXISTS shop_items (id INTEGER PRIMARY KEY AUTOINCREMENT, item_type TEXT, name TEXT, price INTEGER, stock INTEGER, is_football INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admin_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS lb_rewards (id INTEGER PRIMARY KEY AUTOINCREMENT, bracket TEXT, reward_type TEXT, amount INTEGER DEFAULT 0, card_id INTEGER DEFAULT 0, mutation TEXT DEFAULT 'Normal', lb_type TEXT DEFAULT 'trophies')""")
        await db.execute("""CREATE TABLE IF NOT EXISTS authorized_signers (user_id INTEGER PRIMARY KEY)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS battle_passes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, photo_id TEXT, created_at REAL, is_football INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS bp_levels (id INTEGER PRIMARY KEY AUTOINCREMENT, bp_id INTEGER, level INTEGER, xp_required INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS bp_rewards (id INTEGER PRIMARY KEY AUTOINCREMENT, level_id INTEGER, reward_type TEXT, amount INTEGER DEFAULT 0, card_id INTEGER DEFAULT 0, mutation TEXT DEFAULT 'Normal')""")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_bp (
                user_id INTEGER, -- ID аккаунта (accounts.id)
                bp_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, bp_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_bp_claims (
                user_id INTEGER, -- ID аккаунта (accounts.id)
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

        await db.execute("""CREATE TABLE IF NOT EXISTS craft_recipes (id INTEGER PRIMARY KEY AUTOINCREMENT, target_card_id INTEGER, price INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS craft_ingredients (id INTEGER PRIMARY KEY AUTOINCREMENT, recipe_id INTEGER, card_id INTEGER, amount INTEGER DEFAULT 1)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS league_teams (id INTEGER PRIMARY KEY, name TEXT, score REAL DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS league_matches (id INTEGER PRIMARY KEY AUTOINCREMENT, stage INTEGER DEFAULT 0, t1_id INTEGER, t2_id INTEGER, t1_score REAL DEFAULT 0, t2_score REAL DEFAULT 0, winner_id INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS league_rewards_stages (stage_name TEXT, reward_type TEXT, amount INTEGER DEFAULT 0, card_id INTEGER DEFAULT 0, mutation TEXT DEFAULT 'Normal')""")

        async with db.execute("SELECT COUNT(*) as c FROM league_teams") as cursor:
            teams_count = await cursor.fetchone()
            
        if teams_count and dict(teams_count)['c'] == 0:
            for i in range(1, 9):
                await db.execute("INSERT INTO league_teams (id, name, score) VALUES (?, ?, 0)", (i, f"Сборная {i}"))
                
        async with db.execute("SELECT COUNT(*) as c FROM league_matches") as cursor:
            m_count = await cursor.fetchone()
        if m_count and dict(m_count)['c'] == 0:
            matches = [(1,1,2), (1,3,4), (1,5,6), (1,7,8)]
            for stage, t1, t2 in matches:
                await db.execute("INSERT INTO league_matches (stage, t1_id, t2_id) VALUES (?, ?, ?)", (stage, t1, t2))

        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (SUPER_ADMIN_ID,))
        await db.execute("INSERT OR IGNORE INTO server_settings (id) VALUES (1)")
        await db.commit()
    finally:
        await db.close()

# ========================================================================
# СИСТЕМА УПРАВЛЕНИЯ ТЕКУЩИМ АКТИВНЫМ АККАУНТОМ И МИГРАЦИЯ
# ========================================================================
async def get_active_account(telegram_id: int):
    """Возвращает данные текущего активного аккаунта пользователя Telegram"""
    acc = await fetch_one("SELECT * FROM accounts WHERE telegram_id = ? AND is_active = 1", (telegram_id,))
    if acc:
        return acc
    # Если активного нет, но есть хоть один верифицированный — делаем его активным
    all_accs = await fetch_all("SELECT * FROM accounts WHERE telegram_id = ? AND is_verified = 1", (telegram_id,))
    if all_accs:
        await execute_db("UPDATE accounts SET is_active = 0 WHERE telegram_id = ?", (telegram_id,))
        await execute_db("UPDATE accounts SET is_active = 1 WHERE id = ?", (all_accs[0]['id'],))
        return all_accs[0]
    return None

async def migrate_legacy_user(telegram_id: int, new_account_id: int):
    """Переносит статистику и инвентарь старого игрока на его первый кастомный аккаунт"""
    legacy = await fetch_one("SELECT * FROM users WHERE id = ? AND migrated_to_account = 0", (telegram_id,))
    if not legacy:
        return False
        
    await execute_db("""
        UPDATE accounts SET 
            coins = ?, trophies = ?, last_getcard = ?, last_fb_getcard = ?,
            equip1 = ?, equip2 = ?, equip3 = ?, equip4 = ?,
            pity_mythic = ?, pity_super = ?, total_coins = ?,
            notif_shop = ?, notif_events = ?, notif_quests = ?, notif_announces = ?,
            notif_1_rnd = ?, notif_3_rnd = ?, notif_5_rnd = ?, notif_10_rnd = ?,
            notif_25_rnd = ?, notif_50_rnd = ?, notif_100_rnd = ?,
            notif_rnd_leg = ?, notif_rnd_myth = ?, notif_rnd_sup = ?,
            mod_enemy_hp = ?, mod_enemy_atk_all = ?, mod_enemy_stats = ?,
            mod_player_atk_all = ?, mod_manual_atk = ?, mod_player_hp = ?,
            football_mode = ?, football_balls = ?, football_trophies = ?,
            football_team_id = ?, fb_equip1 = ?, fb_equip2 = ?, fb_equip3 = ?,
            fb_equip4 = ?, last_transfer = ?
        WHERE id = ?
    """, (
        legacy['coins'], legacy['trophies'], legacy['last_getcard'], legacy['last_fb_getcard'],
        legacy['equip1'], legacy['equip2'], legacy['equip3'], legacy['equip4'],
        legacy['pity_mythic'], legacy['pity_super'], legacy['total_coins'],
        legacy['notif_shop'], legacy['notif_events'], legacy['notif_quests'], legacy['notif_announces'],
        legacy['notif_1_rnd'], legacy['notif_3_rnd'], legacy['notif_5_rnd'], legacy['notif_10_rnd'],
        legacy['notif_25_rnd'], legacy['notif_50_rnd'], legacy['notif_100_rnd'],
        legacy['notif_rnd_leg'], legacy['notif_rnd_myth'], legacy['notif_rnd_sup'],
        legacy['mod_enemy_hp'], legacy['mod_enemy_atk_all'], legacy['mod_enemy_stats'],
        legacy['mod_player_atk_all'], legacy['mod_manual_atk'], legacy['mod_player_hp'],
        legacy['football_mode'], legacy['football_balls'], legacy['football_trophies'],
        legacy['football_team_id'], legacy['fb_equip1'], legacy['fb_equip2'], legacy['fb_equip3'],
        legacy['fb_equip4'], legacy['last_transfer'], new_account_id
    ))
    
    # Перепривязываем все вещи инвентаря на новый account_id
    await execute_db("UPDATE inventory SET user_id = ? WHERE user_id = ?", (new_account_id, telegram_id))
    # Перепривязываем сид-паки
    await execute_db("UPDATE user_seed_packs SET user_id = ? WHERE user_id = ?", (new_account_id, telegram_id))
    # Перепривязываем БП прогресс
    await execute_db("UPDATE user_bp SET user_id = ? WHERE user_id = ?", (new_account_id, telegram_id))
    await execute_db("UPDATE user_bp_claims SET user_id = ? WHERE user_id = ?", (new_account_id, telegram_id))
    
    # Помечаем миграцию завершенной
    await execute_db("UPDATE users SET migrated_to_account = ? WHERE id = ?", (new_account_id, telegram_id))
    return True

# ========================================================================
# ОТПРАВКА ВЕРИФИКАЦИОННЫХ ПИСЕМ (GMAIL SMTP)
# ========================================================================
def send_email_sync(to_email: str, code: str, nickname: str):
    """Синхронная отправка письма, запускается асинхронно в потоке"""
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = "Подтверждение аккаунта GG TD Cards"
    
    body = f"""
    <html>
    <head></head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #4a90e2; text-align: center;">Добро пожаловать в GG TD Cards!</h2>
            <p>Приветствуем вас, <b>{html.escape(nickname)}</b>!</p>
            <p>Вы начали регистрацию игрового аккаунта в нашем Telegram-боте. Пожалуйста, используйте код ниже для подтверждения почты:</p>
            <div style="text-align: center; margin: 30px 0; background-color: #f0f4f8; padding: 15px; border-radius: 5px; font-size: 28px; font-weight: bold; letter-spacing: 5px; color: #333;">
                {code}
            </div>
            <p style="color: #666; font-size: 12px; text-align: center; margin-top: 30px;">
                Если вы не регистрировались в боте, просто проигнорируйте это письмо.<br>
                Служба тех. поддержки: ggtdcards@gmail.com
            </p>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(body, 'html', 'utf-8'))
    
    server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.sendmail(SMTP_USER, to_email, msg.as_string())
    server.quit()

async def send_verification_email(to_email: str, code: str, nickname: str):
    """Асинхронная обертка для отправки почты без блокировки основного потока бота"""
    try:
        await asyncio.to_thread(send_email_sync, to_email, code, nickname)
        return True
    except Exception as e:
        logging.error(f"Gmail SMTP Send Error: {e}")
        return False

# ========================================================================
# FSM СОСТОЯНИЯ (С УЧЕТОМ РЕГИСТРАЦИИ И ВХОДА)
# ========================================================================
class RegisterAccount(StatesGroup):
    nickname = State()
    username = State()
    password = State()
    email = State()
    code = State()

class LoginAccount(StatesGroup):
    username = State()
    password = State()

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

class CreateSeedPack(StatesGroup):
    is_football = State()
    title = State()
    photo = State()
    description = State()
    price = State()
    card_select = State()
    card_chance = State()
    confirm_save = State()

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

class AdminLeagueRewards(StatesGroup):
    stage = State()
    amount = State()
    card_id = State()
    mutation = State()

class FakeCall:
    def __init__(self, message, data):
        self.message = message
        self.data = data
        self.from_user = message.from_user

# ========================================================================
# УТИЛИТЫ И ХЕЛПЕРЫ ДЛЯ UI
# ========================================================================
def get_display_name(acc_data: dict) -> str:
    """Возвращает красивое форматированное имя кастомного аккаунта"""
    if acc_data.get('username'): 
        return html.escape(f"@{acc_data['username']}")
    elif acc_data.get('nickname'): 
        return html.escape(acc_data['nickname'])
    return f"Player #{acc_data.get('id', '???')}"

async def get_user_titles_str(acc_id: int) -> str:
    # Титулы выдаем на основе Telegram ID привязанного аккаунта
    acc = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (acc_id,))
    if not acc: return ""
    tg_id = acc['telegram_id']
    titles = []
    if await is_admin(tg_id): titles.append("👑 Администратор")
    if await is_signer(tg_id): titles.append("✍️ Сигнер")
    if titles: return f" [<i>{', '.join(titles)}</i>]"
    return ""

def make_progress_bar(current, total, length=10):
    if total <= 0: return "🟩" * length
    pct = min(1.0, current / total)
    filled = int(pct * length)
    empty = length - filled
    return "🟩" * filled + "⬜" * empty

async def generate_dynamic_quests(acc_id: int):
    now = time.time()
    db = await get_db_connection()
    try:
        user_q = await db.execute("SELECT * FROM user_dynamic_quests WHERE user_id = ?", (acc_id,))
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
                """, (chosen[0]['id'], q1_t, chosen[1]['id'], q2_t, chosen[2]['id'], q3_t, next_hour, acc_id))
            else:
                await db.execute("""
                    INSERT INTO user_dynamic_quests (user_id, q1_id, q1_target, q2_id, q2_target, q3_id, q3_target, reset_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (acc_id, chosen[0]['id'], q1_t, chosen[1]['id'], q2_t, chosen[2]['id'], q3_t, next_hour))
            await db.commit()
    finally:
        await db.close()

async def add_quest_progress_new(acc_id: int, quest_type: str, amount: int = 1):
    await generate_dynamic_quests(acc_id)
    db = await get_db_connection()
    try:
        user_q = await db.execute("SELECT * FROM user_dynamic_quests WHERE user_id = ?", (acc_id,))
        uq = await user_q.fetchone()
        if not uq: return
        
        uq_dict = dict(uq)
        updated = False
        
        for i in range(1, 4):
            if uq_dict[f'q{i}_id'] == quest_type and uq_dict[f'q{i}_prog'] < uq_dict[f'q{i}_target']:
                new_prog = min(uq_dict[f'q{i}_target'], uq_dict[f'q{i}_prog'] + amount)
                await db.execute(f"UPDATE user_dynamic_quests SET q{i}_prog = ? WHERE user_id = ?", (new_prog, acc_id))
                uq_dict[f'q{i}_prog'] = new_prog
                updated = True
                
        if updated:
            if uq_dict['q1_prog'] >= uq_dict['q1_target'] and uq_dict['q2_prog'] >= uq_dict['q2_target'] and uq_dict['q3_prog'] >= uq_dict['q3_target']:
                acc = await fetch_one("SELECT telegram_id, notif_quests FROM accounts WHERE id = ?", (acc_id,))
                
                await db.execute("UPDATE accounts SET coins = coins + 1500, total_coins = total_coins + 1500 WHERE id = ?", (acc_id,))
                next_hour = (int(time.time()) // 3600 + 1) * 3600
                await db.execute("UPDATE user_dynamic_quests SET reset_time = ? WHERE user_id = ?", (next_hour, acc_id))
                
                packs = await fetch_all("SELECT id, title FROM seed_packs WHERE is_football = 0")
                pack_reward_text = ""
                if packs:
                    gift_pack = random.choice(packs)
                    await db.execute("""
                        INSERT INTO user_seed_packs (user_id, pack_id, count)
                        VALUES (?, ?, 1)
                        ON CONFLICT(user_id, pack_id) DO UPDATE SET count = count + 1
                    """, (acc_id, gift_pack['id']))
                    pack_reward_text = f"\n📦 А также вы получили Сид-Пак: <b>{gift_pack['title']}</b> (1 шт.)!"
                
                if acc and acc['notif_quests'] == 1:
                    try:
                        msg = f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\nВы выполнили все задания этого часа и получили <b>1500 💰 Шекелей</b>!{pack_reward_text}\nНовые квесты появятся в начале следующего часа!"
                        await bot.send_message(acc['telegram_id'], msg)
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

async def check_ban(acc_id: int) -> bool:
    res = await fetch_one("SELECT banned FROM accounts WHERE id = ?", (acc_id,))
    return bool(res and res['banned'] == 1)

async def notify_super_admin(text: str):
    try: 
        await bot.send_message(SUPER_ADMIN_ID, f"⚠️ <b>ADMIN LOG:</b>\n{text}")
    except Exception as e: 
        logging.error(f"Не удалось отправить лог: {e}")

async def log_admin(admin_id: int, action: str):
    await execute_db("INSERT INTO admin_logs (admin_id, action) VALUES (?, ?)", (admin_id, action))
    admin_info = await fetch_one("SELECT username, first_name FROM users WHERE id = ?", (admin_id,))
    name = f"ID {admin_id}"
    if admin_info:
        name = get_display_name(admin_info)
    else:
        # Пытаемся найти через активный аккаунт
        acc = await get_active_account(admin_id)
        if acc: name = get_display_name(acc)
    await notify_super_admin(f"Admin: <b>{name}</b> ({admin_id})\nAction: {action}")

async def broadcast_message(text_ru: str, notif_type: str = None, shop_types: set = None):
    query = "SELECT * FROM accounts WHERE banned = 0 AND is_active = 1"
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
            await bot.send_message(u['telegram_id'], text_ru)
            success += 1
            await asyncio.sleep(0.05)
        except: 
            pass
    await notify_super_admin(f"📢 <b>Broadcast complete.</b>\nDelivered: {success}")

def get_main_keyboard(is_adm: bool = False, is_sgn: bool = False, is_football: bool = False):
    if is_football:
        kb = [
            [KeyboardButton(text=BTN_FB_DRAW), KeyboardButton(text=BTN_FB_DRAW_REGULAR)],
            [KeyboardButton(text=BTN_FB_SHOP), KeyboardButton(text=BTN_FB_PACKS), KeyboardButton(text=BTN_FB_BP)],
            [KeyboardButton(text=BTN_FB_MATCH), KeyboardButton(text=BTN_FB_LEAGUE), KeyboardButton(text=BTN_FB_PROF)],
            [KeyboardButton(text=BTN_FB_EQ), KeyboardButton(text=BTN_FB_INV), KeyboardButton(text=BTN_FB_INDEX)],
            [KeyboardButton(text=BTN_MAIN_MODE), KeyboardButton(text=BTN_FB_TRANSFER), KeyboardButton(text=BTN_FB_GUIDE)]
        ]
    else:
        kb = [
            [KeyboardButton(text=BTN_DRAW), KeyboardButton(text=BTN_PVE), KeyboardButton(text=BTN_PVP)],
            [KeyboardButton(text=BTN_INV), KeyboardButton(text=BTN_PROF), KeyboardButton(text=BTN_EQ)],
            [KeyboardButton(text=BTN_QUESTS), KeyboardButton(text=BTN_SHOP), KeyboardButton(text=BTN_BP)],
            [KeyboardButton(text=BTN_TOP), KeyboardButton(text=BTN_IDX), KeyboardButton(text=BTN_SEED_PACKS)],
            [KeyboardButton(text=BTN_WC), KeyboardButton(text=BTN_CRAFT)], 
            [KeyboardButton(text=BTN_SET)]
        ]
    
    bottom_row = []
    if is_sgn and not is_football: bottom_row.append(KeyboardButton(text=BTN_SIGN))
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

async def get_active_events():
    settings = await fetch_one("SELECT * FROM server_settings WHERE id = 1")
    now = time.time()
    luck = settings['luck_mult'] if settings['luck_end'] > now else 1.0
    cd = settings['cd_mult'] if settings['cd_end'] > now else 1.0
    return luck, cd

async def get_coin_xp_events():
    settings = await fetch_one("SELECT * FROM server_settings WHERE id = 1")
    now = time.time()
    coin_mult = settings['coin_mult'] if settings['coin_end'] > now else 1.0
    xp_mult = settings['xp_mult'] if settings['xp_end'] > now else 1.0
    return coin_mult, xp_mult

def roll_mutation():
    r = random.random()
    if r <= 0.02: return "Rainbow"
    if r <= 0.12: return "Gold"
    return "Normal"

def roll_seed_pack_mutation():
    r = random.random()
    if r <= 0.02: return "Rainbow"
    if r <= 0.14: return "Gold"
    return "Normal"

def get_mutation_multiplier(mutation: str) -> float:
    if mutation == "Rainbow": return 1.2
    if mutation == "Gold": return 1.1
    return 1.0

def needs_serial_number(rarity: str, mutation: str) -> bool:
    if rarity in ['Leaderboard', 'Exclusive', 'Mythic', 'Super', 'Secret']: return True
    if rarity == 'Legendary' and mutation in ['Gold', 'Rainbow']: return True
    return False

async def give_card_to_user(acc_id: int, card_id: int, mutation: str, rarity: str = None, custom_serial: int = None, is_football: int = 0) -> tuple:
    if not rarity:
        card = await fetch_one("SELECT rarity FROM cards WHERE id = ?", (card_id,))
        rarity = card['rarity'] if card else 'Basic'
        
    db = await get_db_connection()
    try:
        if custom_serial is not None and custom_serial > 0:
            cursor = await db.execute(
                "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, ?, 0, ?)",
                (acc_id, card_id, mutation, custom_serial, is_football)
            )
            return cursor.lastrowid, custom_serial, True
            
        if needs_serial_number(rarity, mutation):
            res = await db.execute("SELECT MAX(serial_number) as m FROM inventory WHERE card_id = ? AND mutation = ?", (card_id, mutation))
            row = await res.fetchone()
            curr_max = row['m'] if (row and row['m'] is not None) else 0
            new_serial = curr_max + 1
            
            cursor = await db.execute(
                "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, ?, 0, ?)", 
                (acc_id, card_id, mutation, new_serial, is_football)
            )
            return cursor.lastrowid, new_serial, True
        else:
            res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0 AND is_football = ?", (acc_id, card_id, mutation, is_football))
            inv_item = await res.fetchone()
            if inv_item:
                await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                return inv_item['id'], 0, False
            else:
                cursor = await db.execute(
                    "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, 0, 0, ?)", 
                    (acc_id, card_id, mutation, is_football)
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
        signer_name = c.get('signer_name') or f"Account:{c['signed_by']}"
        name += f" <i>(✍️ Sign: {signer_name})</i>"
    return name

def format_card_name_plain(c):
    r_em = RARITY_EMOJI.get(c.get('rarity', 'Basic'), "⚪")
    c_em = CLASS_EMOJI.get(c.get('class_type', 'Single'), "🎯")
    name = f"{r_em} {c_em} {c['name']}"
    if c.get('serial_number', 0) > 0:
        name += f" [#{c['serial_number']:04d}]"
    if c.get('signed_by', 0) > 0:
        signer_name = c.get('signer_name') or f"Account:{c['signed_by']}"
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

async def get_card_sources(card_id: int) -> str:
    sources = []
    packs = await fetch_all("SELECT p.title FROM seed_pack_cards spc JOIN seed_packs p ON spc.pack_id = p.id WHERE spc.card_id = ?", (card_id,))
    if packs:
        sources.append("📦 Сид-Паки: " + ", ".join([p['title'] for p in packs]))
    
    c = await fetch_one("SELECT drop_chance, rarity, is_cardball_exclusive FROM cards WHERE id = ?", (card_id,))
    if c:
        if c['drop_chance'] > 0 and c['rarity'] not in ['Leaderboard', 'Secret'] and c.get('is_cardball_exclusive', 0) == 0:
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

# ========================================================================
# ЛОГИКА ШАНСОВ И МАГАЗИНА И PITY
# ========================================================================
async def calculate_chance_weights(luck_mult: float = 1.0, exclude_cardball=True):
    # При обычной гаче жестко убираем эксклюзивных юнитов
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
                
        for p_id, p_name_ru, p_price, p_max, p_chance in SHOP_PACKAGES:
            if random.random() <= p_chance:
                stock = random.randint(1, p_max)
                price_fb = max(10, p_price // 10) 
                await db.execute("INSERT INTO shop_items (item_type, name, price, stock, is_football) VALUES (?, ?, ?, ?, 1)", (p_id, f"⚽ {p_name_ru}", price_fb, stock))
                
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

async def give_multiple_cards(acc_id: int, count: int, is_football: int = 0) -> list:
    luck_mult, _ = await get_active_events()
    user = await fetch_one("SELECT pity_mythic, pity_super FROM accounts WHERE id=?", (acc_id,))
    pm = user['pity_mythic'] if user else 0
    ps = user['pity_super'] if user else 0

    query = """
        SELECT * FROM cards 
        WHERE drop_chance > 0 
        AND rarity NOT IN ('Leaderboard', 'Secret')
        AND id NOT IN (SELECT card_id FROM seed_pack_cards)
    """
    if is_football == 0:
        query += " AND is_cardball_exclusive = 0"
    else:
        query += " AND is_cardball_exclusive = 1"
        
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

        if is_football == 0:
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
        _, serial, _ = await give_card_to_user(acc_id, card['id'], mut, card['rarity'], is_football=is_football)

        c_copy = dict(card)
        c_copy['mutation'] = mut
        c_copy['serial_number'] = serial
        c_copy['is_pity'] = is_pity
        c_copy['pity_type'] = p_type
        c_copy['signed_by'] = 0
        results.append(c_copy)

    if is_football == 0:
        await execute_db("UPDATE accounts SET pity_mythic=?, pity_super=? WHERE id=?", (pm, ps, acc_id))
    return results

async def leaderboard_rewards_task():
    while True:
        try:
            settings = await fetch_one("SELECT last_lb_reward FROM server_settings WHERE id = 1")
            now = time.time()
            if settings and (now - settings['last_lb_reward'] >= 2 * 24 * 3600):
                
                for lb_type in ['trophies', 'coins', 'cards']:
                    if lb_type == 'trophies':
                        top_users = await fetch_all("SELECT id, telegram_id, trophies as score, username, nickname FROM accounts WHERE telegram_id != ? AND is_active = 1 ORDER BY trophies DESC LIMIT 20", (SUPER_ADMIN_ID,))
                    elif lb_type == 'coins':
                        top_users = await fetch_all("SELECT id, telegram_id, total_coins as score, username, nickname FROM accounts WHERE telegram_id != ? AND is_active = 1 ORDER BY total_coins DESC LIMIT 20", (SUPER_ADMIN_ID,))
                    else:
                        top_users = await fetch_all("""
                            SELECT u.id, u.telegram_id, SUM(i.count) as score, u.username, u.nickname 
                            FROM accounts u JOIN inventory i ON u.id = i.user_id 
                            WHERE u.telegram_id != ? AND i.is_football = 0 AND u.is_active = 1 GROUP BY u.id ORDER BY score DESC LIMIT 20
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
                                    await execute_db("UPDATE accounts SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (r['amount'], r['amount'], user['id']))
                                    reward_msgs_ru.append(f"💰 {r['amount']} Шекелей")
                                elif r['reward_type'] == 'card':
                                    c_info = await fetch_one("SELECT name, rarity FROM cards WHERE id = ?", (r['card_id'],))
                                    if c_info:
                                        _, serial, _ = await give_card_to_user(user['id'], r['card_id'], r['mutation'], c_info['rarity'])
                                        mut_str = "🌈" if r['mutation'] == 'Rainbow' else ("⭐" if r['mutation'] == 'Gold' else "")
                                        s_str = f" [#{serial:04d}]" if serial > 0 else ""
                                        reward_msgs_ru.append(f"🃏 {mut_str} {c_info['name']}{s_str}")
                                        
                            if rewards:
                                lb_name_ru = "Кубки (Сезон)" if lb_type == 'trophies' else ("Шекели (Все время)" if lb_type == 'coins' else "Карты (Все время)")
                                msg_text = f"🏆 <b>ГРАНДИОЗНАЯ НАГРАДА ЗА ТОП ИГРОКОВ ({lb_name_ru})!</b> 🏆\n\nПоздравляем! Вы заняли <b>{pos} место</b> в мире!\n\n🎁 <b>Награда:</b>\n" + "\n".join([f"🔸 {m}" for m in reward_msgs_ru])
                                try: 
                                    await bot.send_message(user['telegram_id'], msg_text)
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

# ========================================================================
# КОМАНДЫ РЕГИСТРАЦИИ И ВХОДА (FSM СЦЕНАРИИ)
# ========================================================================
@dp.message(Command("register"))
async def cmd_register(message: types.Message, state: FSMContext):
    # Разрешаем до 3-х аккаунтов на Telegram ID
    accs = await fetch_all("SELECT id FROM accounts WHERE telegram_id = ?", (message.from_user.id,))
    if len(accs) >= 3:
        return await message.answer("❌ <b>Достигнут лимит аккаунтов!</b>\nНа один аккаунт Telegram можно привязать не более 3-х игровых профилей.")
    
    await message.answer("📝 <b>РЕГИСТРАЦИЯ ИГРОВОГО АККАУНТА</b>\n\nВведите ваш игровой никнейм (отображаемое имя, до 30 символов):")
    await state.set_state(RegisterAccount.nickname)

@dp.message(RegisterAccount.nickname)
async def reg_nickname(message: types.Message, state: FSMContext):
    nick = message.text.strip()
    if len(nick) < 2 or len(nick) > 30:
        return await message.answer("❌ Длина никнейма должна быть от 2 до 30 символов. Введите снова:")
    await state.update_data(reg_nick=nick)
    await message.answer("🗣 Введите уникальный игровой юзернейм от 3 до 24 символов (например: @VerityGom325, будет использоваться для поиска в топах, трейдах и входа):")
    await state.set_state(RegisterAccount.username)

@dp.message(RegisterAccount.username)
async def reg_username(message: types.Message, state: FSMContext):
    user_raw = message.text.strip().lstrip('@')
    if len(user_raw) < 3 or len(user_raw) > 24:
        return await message.answer("❌ Юзернейм должен быть длиной от 3 до 24 символов. Введите снова:")
        
    # Проверяем уникальность
    exist = await fetch_one("SELECT 1 FROM accounts WHERE username = ?", (user_raw,))
    if exist:
        return await message.answer("❌ Этот юзернейм уже занят! Придумайте другой:")
        
    await state.update_data(reg_user=user_raw)
    await message.answer("🔑 Введите пароль для аккаунта (сохраните его, он потребуется для переключения командой /login):")
    await state.set_state(RegisterAccount.password)

@dp.message(RegisterAccount.password)
async def reg_password(message: types.Message, state: FSMContext):
    pwd = message.text.strip()
    if len(pwd) < 4:
        return await message.answer("❌ Пароль слишком простой (минимум 4 символа). Введите снова:")
        
    pwd_hash = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
    await state.update_data(reg_pwd=pwd_hash)
    
    await message.answer("📧 Отправьте ваш Gmail адрес почты для верификации и безопасности вашего аккаунта:")
    await state.set_state(RegisterAccount.email)

@dp.message(RegisterAccount.email)
async def reg_email(message: types.Message, state: FSMContext):
    email = message.text.strip().lower()
    if "@" not in email or not email.endswith("gmail.com"):
        return await message.answer("❌ Поддерживаются только адреса Gmail (например, @gmail.com). Введите снова:")
        
    # Генерация 6-значного кода верификации
    code = f"{random.randint(100000, 999999)}"
    data = await state.get_data()
    
    await message.answer("⏳ Отправляю письмо с кодом подтверждения на почту...")
    
    success = await send_verification_email(email, code, data['reg_nick'])
    if not success:
        return await message.answer("❌ Ошибка отправки почты. Убедитесь в правильности адреса или попробуйте позже.")
        
    await state.update_data(reg_email=email, reg_code=code)
    await message.answer("📬 Письмо отправлено! Введите шестизначный код верификации из письма:")
    await state.set_state(RegisterAccount.code)

@dp.message(RegisterAccount.code)
async def reg_code(message: types.Message, state: FSMContext):
    entered_code = message.text.strip()
    data = await state.get_data()
    
    if entered_code != data['reg_code']:
        return await message.answer("❌ Неверный код верификации! Попробуйте ввести снова:")
        
    db = await get_db_connection()
    try:
        # Сбрасываем флаги активности остальных аккаунтов этого Telegram ID
        await db.execute("UPDATE accounts SET is_active = 0 WHERE telegram_id = ?", (message.from_user.id,))
        
        # Создаем аккаунт
        cursor = await db.execute("""
            INSERT INTO accounts (telegram_id, nickname, username, password_hash, email, is_verified, is_active)
            VALUES (?, ?, ?, ?, ?, 1, 1)
        """, (message.from_user.id, data['reg_nick'], data['reg_user'], data['reg_pwd'], data['reg_email']))
        new_acc_id = cursor.lastrowid
        await db.commit()
        
        # Пытаемся мигрировать старые данные (если есть) на первый созданный аккаунт
        accs_count = await fetch_one("SELECT COUNT(*) as c FROM accounts WHERE telegram_id = ?", (message.from_user.id,))
        migrated = False
        if accs_count and accs_count['c'] == 1:
            migrated = await migrate_legacy_user(message.from_user.id, new_acc_id)
            
        await log_user_action(new_acc_id, "Зарегистрировал аккаунт")
        
        welcome = f"🎉 <b>АККАУНТ УСПЕШНО ЗАРЕГИСТРИРОВАН!</b>\n\n👤 Имя: <b>{data['reg_nick']}</b>\n🗣 Юзернейм: <b>@{data['reg_user']}</b>\n📬 Верифицированная почта: {data['reg_email']}\n"
        if migrated:
            welcome += "\n📦 <b>Обнаружен старый профиль!</b> Все ваши монеты, карты и кубки успешно перенесены на новый аккаунт!"
            
        adm = await is_admin(message.from_user.id)
        sgn = await is_signer(message.from_user.id)
        
        await message.answer(welcome, reply_markup=get_main_keyboard(adm, sgn, False))
    except Exception as e:
        logging.error(f"Reg save error: {e}")
        await message.answer("❌ Произошла ошибка сохранения аккаунта.")
    finally:
        await db.close()
        await state.clear()

@dp.message(Command("login"))
async def cmd_login(message: types.Message, state: FSMContext):
    if message.from_user.id in active_combats or message.from_user.id in user_trades:
        return await message.answer("❌ Нельзя переключать аккаунты во время боя или трейда!")
        
    await message.answer("🗣 <b>ВХОД В ДРУГОЙ АККАУНТ</b>\n\nВведите юзернейм аккаунта (без знака @):")
    await state.set_state(LoginAccount.username)

@dp.message(LoginAccount.username)
async def login_username(message: types.Message, state: FSMContext):
    user_raw = message.text.strip().lstrip('@')
    acc = await fetch_one("SELECT * FROM accounts WHERE username = ?", (user_raw,))
    if not acc:
        return await message.answer("❌ Аккаунт с таким юзернеймом не найден в системе. Введите заново:")
        
    await state.update_data(login_target_id=acc['id'], login_user=user_raw)
    await message.answer("🔑 Введите пароль от вашего аккаунта:")
    await state.set_state(LoginAccount.password)

@dp.message(LoginAccount.password)
async def login_password(message: types.Message, state: FSMContext):
    pwd = message.text.strip()
    data = await state.get_data()
    acc = await fetch_one("SELECT * FROM accounts WHERE id = ?", (data['login_target_id'],))
    
    pwd_hash = hashlib.sha256(pwd.encode('utf-8')).hexdigest()
    if acc['password_hash'] != pwd_hash:
        return await message.answer("❌ Неверный пароль! Попробуйте ввести заново:")
        
    # Сбрасываем флаг активности всех аккаунтов на этом Telegram ID
    await execute_db("UPDATE accounts SET is_active = 0 WHERE telegram_id = ?", (message.from_user.id,))
    # Активируем нужный
    await execute_db("UPDATE accounts SET is_active = 1, telegram_id = ? WHERE id = ?", (message.from_user.id, acc['id']))
    
    await log_user_action(acc['id'], "Переключился в аккаунт")
    
    adm = await is_admin(message.from_user.id)
    sgn = await is_signer(message.from_user.id)
    
    await message.answer(f"✅ Успешный вход в аккаунт <b>{acc['nickname']} (@{acc['username']})</b>!", reply_markup=get_main_keyboard(adm, sgn, bool(acc['football_mode'] == 1)))
    await state.clear()

# ========================================================================
# ОБЩИЙ ГВАРД ПРОВЕРКИ АКТИВНОГО АККАУНТА ДЛЯ ВСЕХ ОСТАЛЬНЫХ ДЕЙСТВИЙ
# ========================================================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await execute_db(
        "INSERT OR IGNORE INTO users (id, username, first_name) VALUES (?, ?, ?)", 
        (message.from_user.id, message.from_user.username, message.from_user.first_name)
    )
    
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc:
        return await message.answer(
            "👋 <b>Добро пожаловать в Card Battle Bot!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "У нас запущено <b>Обновление Аккаунтов (Update 2)</b>.\n"
            "Чтобы начать играть, сохраняя или начиная прогресс, вам требуется зарегистрировать игровой аккаунт.\n\n"
            "📌 <b>Для регистрации напишите:</b> /register\n"
            "📌 <b>Для входа в созданный аккаунт:</b> /login"
        )
        
    if await check_ban(active_acc['id']): return
    await log_user_action(active_acc['id'], "Открыл главное меню")
    
    adm = await is_admin(message.from_user.id)
    sgn = await is_signer(message.from_user.id)
    is_fb = active_acc['football_mode'] == 1
    
    text = (
        f"👋 <b>Добро пожаловать в Card Battle Bot!</b>\n"
        f"👤 Активный аккаунт: <b>{active_acc['nickname']} (@{active_acc['username']})</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Собери свою колоду уникальных юнитов, участвуй в ивентах и поднимай кубки на арене!\n\n"
        "📖 <b>ОГРОМНОЕ РУКОВОДСТВО ПО ИГРЕ:</b> /help\n"
        "📞 Тех.поддержка: @ggtdcards_support\n"
        "📰 Новости: @ggtdcardsnews\n"
        "📧 Почта: ggtdcards@gmail.com\n\n"
        "👇 <i>Используй красивое меню снизу для навигации:</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard(adm, sgn, is_football=is_fb))

@dp.message(Command("updatelog"))
async def cmd_updatelog(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
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
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    guide = (
        "📖 <b>ОГРОМНОЕ РУКОВОДСТВО ПО CARD BATTLE BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Добро пожаловать в карточную арену! Ниже описаны все основные механики нашего бота:\n\n"
        "⚔️ <b>ОСНОВНОЙ РЕЖИМ БОЯ (PvE и PvP)</b>\n"
        "• Вы можете собрать боевую колоду из 4-х карт. Для этого выбивайте карты в Гаче или покупайте в магазине.\n"
        "• Бой проходит в автоматическом или полуавтоматическом режиме (если включены модификаторы в Настройках).\n"
        "• В боях против ИИ (ботов) вы получаете <b>Шекели 💰</b>, кубки и опыт БП. Награды зависят от выбранной сложности.\n"
        "• <b>PvP Дуэли</b> позволяют сразиться с друзьями дружеской дуэлью (без изменения рейтинга и наград) или через автоподбор за кубки.\n\n"
        "💎 <b>РЕДКОСТИ И МУТАЦИИ КАРТ</b>\n"
        "Каждая карта имеет свою редкость и может выпасть с особой мутацией:\n"
        "⚪ Basic | 🟢 Uncommon | 🔵 Rare | 🟣 Epic | 🟡 Legendary | 🔴 Mythic | 🌈 Super | 🌸 Exclusive | 👑 Leaderboard\n"
        "• ⭐ <b>Золотая мутация</b> (+10% к характеристикам)\n"
        "• 🌈 <b>Радужная мутация</b> (+20% к характеристикам)\n\n"
        "⚡ <b>СИСТЕМА ГАРАНТИЙ (PITY)</b>\n"
        "• При открытии карт из обычной гачи вы застрахованы от неудач:\n"
        "└ Гарантированный <b>Мифик 🔴</b>: каждые 1000 открытий.\n"
        "└ Гарантированный <b>Супер 🌈</b>: каждые 10000 открытий.\n\n"
        "🔨 <b>МАСТЕРСКАЯ КРАФТА И СЛИЯНИЕ</b>\n"
        "• В меню Крафта вы можете создавать новые мощные карты по рецептам, вкладывая обычные копии.\n"
        "• Вы также можете слить 8 одинаковых обычных карт, чтобы гарантированно повысить их мутацию на уровень выше!\n\n"
        "🎟 <b>БАТЛ-ПАСС (СЕЗОНЫ)</b>\n"
        "• Получайте опыт БП за бои. Повышайте уровень и забирайте эксклюзивные награды, шекели и Сид-Паки!\n\n"
        "🤝 <b>СИСТЕМА ОБМЕНА (ТРЕЙДЫ)</b>\n"
        "• Используйте команду <code>/trade</code> или выберите Трейд, чтобы начать безопасный обмен картами с другим активным игроком!\n\n"
        "📞 <b>КОНТАКТЫ И СВЯЗЬ:</b>\n"
        "• 📰 Новости и обновления: @ggtdcardsnews\n"
        "• 💬 Наш чат поддержки: @ggtdcards_support\n"
        "• 📧 Email для предложений: ggtdcards@gmail.com\n"
    )
    await message.answer(guide)

@dp.message(F.text == BTN_WC)
async def cmd_switch_to_football(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    await execute_db("UPDATE accounts SET football_mode = 1 WHERE id = ?", (active_acc['id'],))
    adm = await is_admin(message.from_user.id)
    await message.answer("⚽ <b>РЕЖИМ CARDBALL АКТИВИРОВАН!</b>\nСобери команду из 4 карт и сразись за мячи!", reply_markup=get_main_keyboard(adm, False, True))

@dp.message(F.text == BTN_MAIN_MODE)
async def cmd_switch_to_main(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    await execute_db("UPDATE accounts SET football_mode = 0 WHERE id = ?", (active_acc['id'],))
    adm = await is_admin(message.from_user.id)
    sgn = await is_signer(message.from_user.id)
    await message.answer("🔙 <b>ВЫ ВЕРНУЛИСЬ В ОБЫЧНЫЙ РЕЖИМ!</b>", reply_markup=get_main_keyboard(adm, sgn, False))

@dp.message(F.text == BTN_SET)
async def cmd_settings(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    text = (
        "⚙️ <b>НАСТРОЙКИ АКТИВНОГО АККАУНТА</b>\n"
        f"Аккаунт: <b>{active_acc['nickname']} (@{active_acc['username']})</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Фильтр Магазина", callback_data="set_shop_filters")],
        [InlineKeyboardButton(text="🧬 Модификаторы боя (PvE)", callback_data="set_modifiers")],
        [InlineKeyboardButton(text=f"🎉 Ивенты: {'🔔 Вкл' if active_acc['notif_events'] else '🔕 Выкл'}", callback_data="set_toggle_events")],
        [InlineKeyboardButton(text=f"📜 Квесты: {'🔔 Вкл' if active_acc['notif_quests'] else '🔕 Выкл'}", callback_data="set_toggle_quests")],
        [InlineKeyboardButton(text=f"📢 Анонсы: {'🔔 Вкл' if active_acc['notif_announces'] else '🔕 Выкл'}", callback_data="set_toggle_announces")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "set_modifiers")
async def cb_modifiers_menu(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer("Зарегистрируйтесь: /register", show_alert=True)
    
    def s(val): return "✅ Вкл" if val else "❌ Выкл"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔴 1.5x ХП Врагов ({s(active_acc.get('mod_enemy_hp'))})", callback_data="set_mod_enemy_hp")],
        [InlineKeyboardButton(text=f"🔴 ИИ бьет 2 раза ({s(active_acc.get('mod_enemy_atk_all'))})", callback_data="set_mod_enemy_atk_all")],
        [InlineKeyboardButton(text=f"🔴 1.2x Статы ИИ ({s(active_acc.get('mod_enemy_stats'))})", callback_data="set_mod_enemy_stats")],
        [InlineKeyboardButton(text=f"🟢 Игрок бьет 2 раза ({s(active_acc.get('mod_player_atk_all'))})", callback_data="set_mod_player_atk_all")],
        [InlineKeyboardButton(text=f"🟢 Ручной выбор атаки ({s(active_acc.get('mod_manual_atk'))})", callback_data="set_mod_manual_atk")],
        [InlineKeyboardButton(text=f"🟢 1.3x ХП Игрока ({s(active_acc.get('mod_player_hp'))})", callback_data="set_mod_player_hp")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="set_main")]
    ])
    text = (
        "🧬 <b>МОДИФИКАТОРЫ БОЯ (PvE)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВключите модификаторы для усложнения или упрощения боев с ботами.\n\n"
        "🔴 <b>Дебаффы</b> повышают награды (монеты, опыт, кубки).\n🟢 <b>Баффы</b> снижают награды (монеты, опыт), кубки не режутся."
    )
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("set_mod_"))
async def cb_mod_toggle(callback: types.CallbackQuery):
    mod = callback.data.replace("set_mod_", "")
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    new_val = 1 if not active_acc.get(f"mod_{mod}") else 0
    await execute_db(f"UPDATE accounts SET mod_{mod} = ? WHERE id = ?", (new_val, active_acc['id']))
    
    # Имитируем обновление, чтобы перерендерить меню
    fake_acc = dict(active_acc)
    fake_acc[f"mod_{mod}"] = new_val
    await cb_modifiers_menu(callback)

@dp.callback_query(F.data == "set_shop_filters")
async def cb_shop_filters(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    text = "🛒 <b>ФИЛЬТР УВЕДОМЛЕНИЙ МАГАЗИНА</b>\nВыберите, о каких товарах вас уведомлять:"
    def b(name_ru, col):
        st = "🔔" if active_acc.get(col, 1) else "🔕"
        return InlineKeyboardButton(text=f"{name_ru} {st}", callback_data=f"set_shopfilt_{col}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [b("1 Случайная", "notif_1_rnd"), b("3 Случайные", "notif_3_rnd")],
        [b("5 Случайных", "notif_5_rnd"), b("10 Случайных", "notif_10_rnd")],
        [b("25 Случайных", "notif_25_rnd"), b("50 Случайных", "notif_50_rnd")],
        [b("100 Случайных", "notif_100_rnd"), b("Легендарная", "notif_rnd_leg")],
        [b("Мифическая", "notif_rnd_myth"), b("Супер Карта", "notif_rnd_sup")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="set_main")]
    ])
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("set_shopfilt_"))
async def cb_shopfilt_toggle(callback: types.CallbackQuery):
    col = callback.data.replace("set_shopfilt_", "")
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    new_val = 0 if active_acc.get(col, 1) == 1 else 1
    await execute_db(f"UPDATE accounts SET {col} = ? WHERE id = ?", (new_val, active_acc['id']))
    await cb_shop_filters(callback)

@dp.callback_query(F.data == "set_main")
async def cb_set_main(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    text = "⚙️ <b>НАСТРОЙКИ АККАУНТА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Фильтр Магазина", callback_data="set_shop_filters")],
        [InlineKeyboardButton(text="🧬 Модификаторы боя (PvE)", callback_data="set_modifiers")],
        [InlineKeyboardButton(text=f"🎉 Ивенты: {'🔔 Вкл' if active_acc['notif_events'] else '🔕 Выкл'}", callback_data="set_toggle_events")],
        [InlineKeyboardButton(text=f"📜 Квесты: {'🔔 Вкл' if active_acc['notif_quests'] else '🔕 Выкл'}", callback_data="set_toggle_quests")],
        [InlineKeyboardButton(text=f"📢 Анонсы: {'🔔 Вкл' if active_acc['notif_announces'] else '🔕 Выкл'}", callback_data="set_toggle_announces")]
    ])
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("set_toggle_"))
async def cb_settings_toggle(callback: types.CallbackQuery):
    field = callback.data.replace("set_toggle_", "notif_")
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    new_val = 0 if active_acc.get(field, 1) == 1 else 1
    await execute_db(f"UPDATE accounts SET {field} = ? WHERE id = ?", (new_val, active_acc['id']))
    await cb_set_main(callback)

@dp.message(Command("profile"), F.chat.type == "private")
@dp.message(F.text.in_([BTN_PROF, BTN_FB_PROF]))
async def cmd_profile(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    is_fb = active_acc['football_mode'] == 1
    rank = await get_user_rank(active_acc['football_trophies'] if is_fb else active_acc['trophies'])
    total_cards = await fetch_one("SELECT SUM(count) as s FROM inventory WHERE user_id = ? AND is_football = ?", (active_acc['id'], 1 if is_fb else 0))
    name = get_display_name(active_acc)
    title_str = await get_user_titles_str(active_acc['id'])
    
    active_bp = await fetch_one("""
        SELECT bp.title, ubp.level, ubp.xp 
        FROM user_bp ubp JOIN battle_passes bp ON ubp.bp_id = bp.id 
        WHERE ubp.user_id = ? AND ubp.is_active = 1 AND bp.is_football = ?
    """, (active_acc['id'], 1 if is_fb else 0))
    
    bp_text = "<i>Нет активного Батл-пасса</i>"
    if active_bp:
        bp_text = f"<b>{active_bp['title']}</b> (Ур. {active_bp['level']} | {active_bp['xp']} XP)"

    mode_title = "⚽ Профиль Cardball" if is_fb else "👤 Профиль игрока"
    bal_str = f"⚽ <b>Мячей:</b> {active_acc['football_balls']}" if is_fb else f"💰 <b>Шекелей:</b> {active_acc['coins']}"
    tr_str = active_acc['football_trophies'] if is_fb else active_acc['trophies']
    
    text = (
        f"{mode_title} <b>{name}</b>{title_str}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎖 <b>Ранг:</b> {rank['name']}\n🏆 <b>Кубки:</b> {tr_str}\n{bal_str}\n"
        f"🃏 <b>Всего карт:</b> {total_cards['s'] or 0}\n🎟 <b>Активный БП:</b> {bp_text}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    if not is_fb:
        text += (
            f"🔮 <b>Гарант на Мифик:</b> {make_progress_bar(active_acc['pity_mythic'], 1000, 8)} ({active_acc['pity_mythic']}/1000)\n"
            f"🌠 <b>Гарант на :</b> {make_progress_bar(active_acc['pity_super'], 10000, 8)} ({active_acc['pity_super']}/10000)\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        
    text += "⚔️ <b>Экипировка:</b>\n"
    slots = ['fb_equip1', 'fb_equip2', 'fb_equip3', 'fb_equip4'] if is_fb else ['equip1', 'equip2', 'equip3', 'equip4']
    role_names = ["Вратарь", "Защитник", "Полузащитник", "Нападающий"]
    
    for i, slot in enumerate(slots):
        inv_id = active_acc[slot]
        role_label = f"[{role_names[i]}] " if is_fb else f"{i+1}️⃣ "
        if inv_id != 0:
            row = await fetch_one("""
                SELECT c.id, c.name, c.rarity, c.class_type, c.damage, c.hp, c.booster_dmg_mult, c.booster_hp_mult,
                       i.mutation, i.serial_number, i.signed_by
                FROM inventory i JOIN cards c ON i.card_id = c.id
                WHERE i.id = ? AND i.user_id = ? AND i.count > 0
            """, (inv_id, active_acc['id']))
            
            if row:
                mult = get_mutation_multiplier(row['mutation'])
                mut_str = " 🌈" if row['mutation'] == "Rainbow" else (" ⭐" if row['mutation'] == 'Gold' else "")
                c_dict = dict(row)
                if row['signed_by'] > 0:
                    signer = await fetch_one("SELECT nickname, username FROM accounts WHERE id = ?", (row['signed_by'],))
                    if signer: c_dict['signer_name'] = get_display_name(signer)
                
                n = format_card_name(c_dict)
                if row['class_type'] == 'Booster': 
                    text += f" {role_label}{n}{mut_str}\n      └ <i>Бафф: DMG x{round(row['booster_dmg_mult']*mult, 2)} | HP x{round(row['booster_hp_mult']*mult, 2)}</i>\n"
                elif row['class_type'] == 'Healer':
                    text += f" {role_label}{n}{mut_str}\n      └ <i>Статы: 💗 Лечение: {int(row['damage']*mult)} | ❤️ Здоровье: {int(row['hp']*mult)}</i>\n"
                else: 
                    text += f" {role_label}{n}{mut_str}\n      └ <i>Статы: ⚔️ Урон: {int(row['damage']*mult)} | ❤️ Здоровье: {int(row['hp']*mult)}</i>\n"
            else:
                await execute_db(f"UPDATE accounts SET {slot} = 0 WHERE id = ?", (active_acc['id'],))
                text += f" {role_label}[Слот Пуст]\n"
        else:
            text += f" {role_label}[Слот Пуст]\n"
            
    await message.answer(text)

@dp.message(Command("quests"))
@dp.message(F.text == BTN_QUESTS)
async def cmd_quests(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    await generate_dynamic_quests(active_acc['id'])
    user = await fetch_one("SELECT * FROM user_dynamic_quests WHERE user_id = ?", (active_acc['id'],))
    if not user: return await message.answer("Ошибка системы квестов.")
    
    now = time.time()
    if user['reset_time'] < now:
        await generate_dynamic_quests(active_acc['id'])
        user = await fetch_one("SELECT * FROM user_dynamic_quests WHERE user_id = ?", (active_acc['id'],))
        
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
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
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
        top_users = await fetch_all("SELECT username, nickname, id, trophies as score FROM accounts WHERE telegram_id != ? AND is_active = 1 ORDER BY trophies DESC LIMIT 20", (SUPER_ADMIN_ID,))
        title_ru = "🏆 <b>МИРОВОЙ РЕЙТИНГ: КУБКИ (Топ-20)</b>"
        unit = "🏆"
    elif lb_type == 'coins':
        top_users = await fetch_all("SELECT username, nickname, id, total_coins as score FROM accounts WHERE telegram_id != ? AND is_active = 1 ORDER BY total_coins DESC LIMIT 20", (SUPER_ADMIN_ID,))
        title_ru = "💰 <b>МИРОВОЙ РЕЙТИНГ: ШЕКЕЛИ (Топ-20)</b>"
        unit = "💰"
    else:
        top_users = await fetch_all("SELECT u.id, u.username, u.nickname, SUM(i.count) as score FROM accounts u JOIN inventory i ON u.id = i.user_id WHERE u.telegram_id != ? AND i.is_football = 0 AND u.is_active = 1 GROUP BY u.id ORDER BY score DESC LIMIT 20", (SUPER_ADMIN_ID,))
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
                    mut = "🌈" if r['mutation'] == 'Rainbow' else ("⭐" if r['mutation'] == 'Gold' else "")
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
@dp.message(F.text.in_([BTN_SHOP, BTN_FB_SHOP]))
async def cmd_shop(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    is_fb = active_acc['football_mode'] == 1
    items = await fetch_all("SELECT * FROM shop_items WHERE stock > 0 AND is_football = ?", (1 if is_fb else 0,))
    
    if not items:
        return await message.answer("🛒 <b>Магазин пока пуст.</b>\nЗавоз осуществляется каждые полтора часа. Жди уведомления!")
        
    bal = active_acc['football_balls'] if is_fb else active_acc['coins']
    val_sym = "⚽" if is_fb else "💰"
    val_name = "Мячей" if is_fb else "Шекелей"
    
    text = f"🛒 <b>ГЛОБАЛЬНЫЙ МАГАЗИН {'(CARDBALL)' if is_fb else ''}</b>\n{val_sym} Твой баланс: <b>{bal} {val_name}</b>\n<i>(Товары общие для всех. Кто успел, тот и купил!)</i>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    kb = []
    for i, item in enumerate(items, 1):
        text += f"📦 <b>{item['name']}</b>\n      └ 💵 Цена: <b>{item['price']} {val_sym}</b> | Остаток: <b>{item['stock']} шт.</b>\n\n"
        kb.append([InlineKeyboardButton(text=f"Купить: {item['name']} ({item['price']} {val_sym})", callback_data=f"buy_shop_{item['id']}")])
        
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("buy_shop_"))
async def callback_buy_shop(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer("Ошибка аккаунта", show_alert=True)
    
    shop_id = int(callback.data.split("_")[2])
    item = await fetch_one("SELECT * FROM shop_items WHERE id = ?", (shop_id,))
    
    if not item or item['stock'] <= 0: return await callback.answer("❌ Этот товар закончился!", show_alert=True)
    
    is_fb = item['is_football'] == 1
    bal_col = 'football_balls' if is_fb else 'coins'
    
    if active_acc[bal_col] < item['price']: return await callback.answer("❌ Недостаточно средств!", show_alert=True)
    
    # Списание и начисление делаем в строгой транзакции!
    db = await get_db_connection()
    try:
        await db.execute("BEGIN EXCLUSIVE")
        # Проверяем баланс повторно
        cur_acc = await db.execute("SELECT coins, football_balls FROM accounts WHERE id = ?", (active_acc['id'],))
        row_acc = await cur_acc.fetchone()
        if not row_acc or row_acc[bal_col] < item['price']:
            raise ValueError("Insufficient balance")
            
        # Обновляем сток
        await db.execute("UPDATE shop_items SET stock = stock - 1 WHERE id = ?", (shop_id,))
        # Списываем баланс
        await db.execute(f"UPDATE accounts SET {bal_col} = {bal_col} - ? WHERE id = ?", (item['price'], active_acc['id']))
        await db.commit()
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Transaction rollbacked inside Shop: {e}")
        return await callback.answer("❌ Ошибка при оформлении покупки.", show_alert=True)
    finally:
        await db.close()

    if not is_fb: await add_quest_progress_new(active_acc['id'], 'q_shop_buy', 1)
    
    i_type = item['item_type']
    if i_type.endswith("_rnd"):
        count = int(i_type.split("_")[0])
        won = await give_multiple_cards(active_acc['id'], count, is_football=1 if is_fb else 0)
        
        if not is_fb: await add_quest_progress_new(active_acc['id'], 'q_open', count)
            
        pity_pulls = [c for c in won if c.get('is_pity')]
        
        if count == 1: 
            mut_str = "🌈 " if won[0]['mutation'] == 'Rainbow' else ("⭐ " if won[0]['mutation'] == 'Gold' else "")
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
        if is_fb == 0: query += " AND is_cardball_exclusive = 0"
        else: query += " AND is_cardball_exclusive = 1"
        
        all_cards = await fetch_all(query, (target_rarity,))
        if not all_cards:
            await execute_db(f"UPDATE accounts SET {bal_col} = {bal_col} + ? WHERE id = ?", (item['price'], active_acc['id']))
            return await callback.message.answer("❌ Ошибка БД.")
            
        won_card = random.choice(all_cards)
        mut = roll_mutation()
        _, serial, _ = await give_card_to_user(active_acc['id'], won_card['id'], mut, won_card['rarity'], is_football=1 if is_fb else 0)
        won_card['serial_number'] = serial
        won_card['signed_by'] = 0
        
        if not is_fb: await add_quest_progress_new(active_acc['id'], 'q_open', 1)
            
        pm = active_acc['pity_mythic']; ps = active_acc['pity_super']
        if target_rarity == 'Super': ps = 0; pm += 1
        elif target_rarity == 'Mythic': pm = 0; ps += 1
        else: ps += 1; pm += 1
        await execute_db("UPDATE accounts SET pity_mythic=?, pity_super=? WHERE id=?", (pm, ps, active_acc['id']))
        
        mut_str = "🌈 Радужная" if mut == 'Rainbow' else ("⭐ Золотая" if mut == 'Gold' else "Обычная")
        await callback.message.answer(f"✨ <b>Успешная покупка ГАРАНТА!</b>\nВы выбили: {format_card_name(won_card)}\nМутация: <b>{mut_str}</b>")

    await log_user_action(active_acc['id'], f"Купил в магазине: {i_type} ({item['price']})")

    items = await fetch_all("SELECT * FROM shop_items WHERE stock > 0 AND is_football = ?", (1 if is_fb else 0,))
    if not items:
        await callback.message.edit_text("🛒 <b>Магазин полностью распродан!</b>\nЖдите следующего завоза.")
    else:
        new_val = active_acc[bal_col] - item['price']
        val_sym = "⚽" if is_fb else "💰"
        val_name = "Мячей" if is_fb else "Шекелей"
        text = f"🛒 <b>ГЛОБАЛЬНЫЙ МАГАЗИН {'(CARDBALL)' if is_fb else ''}</b>\n{val_sym} Твой баланс: <b>{new_val} {val_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        kb = []
        for i, itm in enumerate(items, 1):
            text += f"📦 <b>{itm['name']}</b>\n      └ 💵 Цена: <b>{itm['price']} {val_sym}</b> | Остаток: <b>{itm['stock']} шт.</b>\n\n"
            kb.append([InlineKeyboardButton(text=f"Купить: {itm['name']} ({itm['price']} {val_sym})", callback_data=f"buy_shop_{itm['id']}")])
        try: await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except: pass
    
    await callback.answer()

# ========================================================================
# СИСТЕМА ГАЧИ (ВЫБИВАНИЕ КАРТ) И МУТАЦИИ
# ========================================================================
@dp.message(Command("getcard"))
@dp.message(F.text.in_([BTN_DRAW, BTN_FB_DRAW, BTN_FB_DRAW_REGULAR]))
async def cmd_getcard(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    if active_acc['id'] in user_trades: return await message.answer("❌ Завершите обмен перед выбиванием!")
    
    is_fb = message.text == BTN_FB_DRAW or message.text == BTN_FB_DRAW_REGULAR
    is_fb_exclusive = message.text == BTN_FB_DRAW
    
    luck_mult, cd_mult = await get_active_events()
    
    if is_fb_exclusive:
        base_cooldown = 10 * 60
        last_col = 'last_fb_getcard'
    else:
        base_cooldown = 3 * 60
        last_col = 'last_getcard'
        
    actual_cooldown = int(base_cooldown / cd_mult)
    now = time.time()
    passed = now - active_acc[last_col]
    
    if passed < actual_cooldown:
        left = int(actual_cooldown - passed)
        mins, secs = divmod(left, 60)
        return await message.answer(f"⏳ <b>Колода перемешивается!</b>\nОжидай: <b>{mins} мин. {secs} сек.</b>")
        
    # Исключаем Cardball эксклюзивных юнитов для обычной гачи, и включаем только для специальной футбольной гачи
    won_list = await give_multiple_cards(active_acc['id'], 1, is_football=1 if is_fb_exclusive else 0)
    if not won_list: return await message.answer("😔 В базе нет карт для этой гачи.")
    won_card = won_list[0]
        
    await execute_db(f"UPDATE accounts SET {last_col} = ? WHERE id = ?", (now, active_acc['id']))
    await add_quest_progress_new(active_acc['id'], 'q_open', 1)
    await log_user_action(active_acc['id'], f"Выбил карту{' (CARDBALL)' if is_fb_exclusive else ''}: {won_card['name']} (ID:{won_card['id']})")
    
    n_fmt = format_card_name(won_card)
    rarity_text = format_rarity_display(won_card['rarity'])
    
    mutation = won_card['mutation']
    mult = get_mutation_multiplier(mutation)
    mut_str = ""
    if mutation == "Gold": mut_str = "⭐ <b>ЗОЛОТАЯ МУТАЦИЯ! (+10% Статов)</b>\n"
    elif mutation == "Rainbow": mut_str = "🌈 <b>РАДУЖНАЯ МУТАЦИЯ! (+20% Статов)</b>\n"
    
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

# ========================================================================
# ИНДЕКС С РАЗДЕЛАМИ
# ========================================================================
async def get_index_text(acc_id: int, page: int = 0, items_per_page: int = 8, is_fb: bool = False, sub_section: str = "all"):
    query = "SELECT * FROM cards WHERE rarity != 'Secret'"
    if is_fb:
        if sub_section == "fb_exclusive":
            query += " AND is_cardball_exclusive = 1"
        elif sub_section == "ordinary":
            query += " AND is_cardball_exclusive = 0"
    else:
        query += " AND is_cardball_exclusive = 0"
        
    all_cards = await fetch_all(query)
    user_inv = await fetch_all("SELECT DISTINCT card_id FROM inventory WHERE user_id = ?", (acc_id,))
    user_card_ids = [item['card_id'] for item in user_inv]
    recipes = await fetch_all("SELECT target_card_id FROM craft_recipes")
    crafted_ids = [r['target_card_id'] for r in recipes]
    
    if not all_cards: return "Индекс пуст.", None
    
    luck_mult, _ = await get_active_events()
    weights_dict, total_w = await calculate_chance_weights(luck_mult, exclude_cardball=(sub_section == 'ordinary' or not is_fb))
    
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
    
    title_str = "⚽ CARDBALL" if is_fb else "🎒 ОСНОВНОЙ"
    if is_fb:
        title_str += f" ({'Все юниты' if sub_section == 'all' else ('Футбольные' if sub_section == 'fb_exclusive' else 'Обычные')})"
        
    text = f"📖 <b>{title_str} ИНДЕКС КАРТ (Стр. {page+1}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
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
    if is_fb:
        kb.append([
            InlineKeyboardButton(text="🎯 Все", callback_data=f"idxfb_all_page_{page}"),
            InlineKeyboardButton(text="⚽ Только Футбол", callback_data=f"idxfb_fb_exclusive_page_{page}"),
            InlineKeyboardButton(text="🎒 Обычные", callback_data=f"idxfb_ordinary_page_{page}")
        ])

    nav_row = []
    cb_prefix = f"idxfb_{sub_section}_" if is_fb else "idx_"
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{cb_prefix}page_{page-1}"))
    if total_pages > 1: nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{cb_prefix}page_{page+1}"))
    if nav_row: kb.append(nav_row)
    
    return text, InlineKeyboardMarkup(inline_keyboard=kb) if kb else None

@dp.message(Command("index"))
@dp.message(F.text.in_([BTN_IDX, BTN_FB_INDEX]))
async def cmd_index(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    is_fb = message.text == BTN_FB_INDEX
    text, kb = await get_index_text(active_acc['id'], 0, is_fb=is_fb, sub_section='all' if is_fb else 'ordinary')
    await message.answer(text, reply_markup=kb)
    
@dp.callback_query(F.data.startswith("idx_page_"))
async def callback_index_page(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    page = int(callback.data.split("_")[2])
    text, kb = await get_index_text(active_acc['id'], page, is_fb=False)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("idxfb_"))
async def callback_idxfb_router(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    parts = callback.data.split("_")
    if len(parts) >= 4 and parts[2] == "page":
        sub_sec = parts[1]
        page = int(parts[3])
    else:
        sub_sec = parts[1] if len(parts) > 1 else 'all'
        page = int(parts[3]) if len(parts) > 3 else 0
        
    if sub_sec not in ['all', 'fb_exclusive', 'ordinary']: sub_sec = 'all'
        
    text, kb = await get_index_text(active_acc['id'], page, is_fb=True, sub_section=sub_sec)
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

# ========================================================================
# ИНВЕНТАРЬ
# ========================================================================
async def get_inventory_text_and_kb(acc_id: int, page: int = 0, items_per_page: int = 30, is_football: int = 0):
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by, u.username, u.nickname
        FROM inventory i JOIN cards c ON i.card_id = c.id LEFT JOIN accounts u ON i.signed_by = u.id
        WHERE i.user_id = ? AND i.count > 0 AND i.is_football = ?
    """, (acc_id, is_football))
    
    fb_str = " (CARDBALL)" if is_football else ""
    toggle_row = [
        InlineKeyboardButton(text=f"🎒 Карты (Выбрано)", callback_data="ignore"),
        InlineKeyboardButton(text=f"📦 Сид-Паки{fb_str}", callback_data=f"inv_packs_menu_{is_football}")
    ]
    
    if not inv: 
        return f"🎒 Ваш инвентарь{fb_str} пуст. Используйте /getcard", InlineKeyboardMarkup(inline_keyboard=[toggle_row])
        
    mutation_weight = {"Rainbow": 3, "Gold": 2, "Normal": 1}
    for item in inv:
        if item['signed_by'] != 0:
            item['signer_name'] = get_display_name({'username': item['username'], 'nickname': item['nickname'], 'id': item['signed_by']})
    inv.sort(key=lambda x: (x['signed_by'] > 0, RARITY_WEIGHT.get(x['rarity'], 0), mutation_weight.get(x['mutation'], 0), x['card_id']), reverse=True)
    
    total_pages = max(1, math.ceil(len(inv) / items_per_page))
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = inv[start_idx:end_idx]
    
    text = f"🎒 <b>ИНВЕНТАРЬ КАРТ{fb_str} (Стр. {page+1}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for item in page_items:
        n_fmt = format_card_name(item).replace(" <b>[#-001]</b>", "")
        mut_emoji = ""
        if item['mutation'] == "Gold": mut_emoji = "⭐ "
        elif item['mutation'] == "Rainbow": mut_emoji = "🌈 "
        text += f"• {mut_emoji}{n_fmt} — <b>{item['count']} шт.</b>\n"
        
    kb = [toggle_row]
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"inv_page_{page-1}_{is_football}"))
    if total_pages > 1: nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"inv_page_{page+1}_{is_football}"))
    if nav_row: kb.append(nav_row)
    
    return text, InlineKeyboardMarkup(inline_keyboard=kb) if kb else None

@dp.message(Command("inventory"))
@dp.message(F.text.in_([BTN_INV, BTN_FB_INV]))
async def cmd_inventory(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    is_fb = message.text == BTN_FB_INV
    text, kb = await get_inventory_text_and_kb(active_acc['id'], 0, is_football=1 if is_fb else 0)
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("inv_page_"))
async def callback_inventory_page(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    parts = callback.data.split("_")
    page = int(parts[2])
    is_fb = int(parts[3]) if len(parts) > 3 else 0
    text, kb = await get_inventory_text_and_kb(active_acc['id'], page, is_football=is_fb)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.message(F.text == BTN_SIGN)
async def cmd_sign_card(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    if not await is_signer(message.from_user.id): return
    if active_acc['id'] in user_trades: return await message.answer("❌ Завершите обмен перед подписыванием карт!")
    
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0 AND i.signed_by = 0 AND i.is_football = 0
    """, (active_acc['id'],))
    
    if not inv: return await message.answer("❌ Нет карт для подписи.")
    
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = []
    for c in inv:
        mut_emoji = "⭐ " if c['mutation'] == 'Gold' else "🌈 " if c['mutation'] == 'Rainbow' else ""
        items.append({"id": c['inv_id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {mut_emoji}{c['name']} x{c['count']}"})
        
    kb = get_pagination_keyboard(items, 0, "sgn_c", columns=1, items_per_page=8)
    await message.answer("✍️ <b>ВЫБОР КАРТЫ ДЛЯ ПОДПИСИ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите карту:", reply_markup=kb)

@dp.callback_query(F.data.startswith("sgn_c_page_"))
async def cb_sign_card_paginate(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    page = int(callback.data.split("_")[3])
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0 AND i.signed_by = 0 AND i.is_football = 0
    """, (active_acc['id'],))
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = []
    for c in inv:
        mut_emoji = "⭐ " if c['mutation'] == 'Gold' else "🌈 " if c['mutation'] == 'Rainbow' else ""
        items.append({"id": c['inv_id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {mut_emoji}{c['name']} x{c['count']}"})
        
    kb = get_pagination_keyboard(items, page, "sgn_c", columns=1, items_per_page=8)
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("sgn_c_"))
async def cb_sign_card_select(callback: types.CallbackQuery):
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    if not await is_signer(callback.from_user.id): return await callback.answer("Нет прав!", show_alert=True)
    
    db = await get_db_connection()
    try:
        cur = await db.execute("SELECT card_id, count, mutation, serial_number, signed_by FROM inventory WHERE id = ? AND user_id = ?", (inv_id, active_acc['id']))
        row = await cur.fetchone()
        if not row or row['count'] < 1: return await callback.answer("Not found!", show_alert=True)
        if row['signed_by'] != 0: return await callback.answer("Already signed!", show_alert=True)
        
        await db.execute("BEGIN")
        if row['count'] == 1:
            await db.execute("DELETE FROM inventory WHERE id = ?", (inv_id,))
            await db.execute("UPDATE accounts SET equip1 = 0 WHERE equip1 = ?", (inv_id,))
            await db.execute("UPDATE accounts SET equip2 = 0 WHERE equip2 = ?", (inv_id,))
            await db.execute("UPDATE accounts SET equip3 = 0 WHERE equip3 = ?", (inv_id,))
            await db.execute("UPDATE accounts SET equip4 = 0 WHERE equip4 = ?", (inv_id,))
        else:
            await db.execute("UPDATE inventory SET count = count - 1 WHERE id = ?", (inv_id,))
            
        cur2 = await db.execute("""
            SELECT id FROM inventory 
            WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = ? AND signed_by = ? AND is_football = 0
        """, (active_acc['id'], row['card_id'], row['mutation'], row['serial_number'], active_acc['id']))
        dest = await cur2.fetchone()
        
        if dest:
            await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (dest['id'],))
        else:
            await db.execute("""
                INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football)
                VALUES (?, ?, 1, ?, ?, ?, 0)
            """, (active_acc['id'], row['card_id'], row['mutation'], row['serial_number'], active_acc['id']))
            
        await db.commit()
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Sign error: {e}")
        return await callback.answer("Ошибка.", show_alert=True)
    finally:
        await db.close()
        
    await callback.message.delete()
    await callback.message.answer("✍️✅ <b>Успешно подписано вашим игровым профилем!</b>")
    await callback.answer()

# ========================================================================
# ЭКИПИРОВКА (4 СЛОТА)
# ========================================================================
def get_equip_main_keyboard(user_info, cards_info, is_football=False):
    kb = []
    slots = ['fb_equip1', 'fb_equip2', 'fb_equip3', 'fb_equip4'] if is_football else ['equip1', 'equip2', 'equip3', 'equip4']
    role_names = ["Вратарь", "Защитник", "Полузащитник", "Нападающий"]
    
    for i, slot in enumerate(slots, 1):
        inv_id = user_info[slot]
        sl_t = f"[{role_names[i-1]}]" if is_football else f"Слот {i}"
        text = f"{sl_t} [Пусто]" if inv_id == 0 else f"{sl_t}: {cards_info.get(inv_id, f'ID: {inv_id}')}"
        kb.append([InlineKeyboardButton(text=text, callback_data=f"eq_select_{i}_{1 if is_football else 0}")])
    kb.append([InlineKeyboardButton(text="❌ Очистить колоду", callback_data=f"eq_clear_{1 if is_football else 0}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("equip"))
@dp.message(F.text.in_([BTN_EQ, BTN_FB_EQ]))
async def cmd_equip(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    is_fb = message.text == BTN_FB_EQ
    if active_acc['id'] in user_trades: return await message.answer("❌ Завершите обмен перед экипировкой!")
    
    slots = ['fb_equip1', 'fb_equip2', 'fb_equip3', 'fb_equip4'] if is_fb else ['equip1', 'equip2', 'equip3', 'equip4']
    inv_ids = [c for c in [active_acc[s] for s in slots] if c != 0]
    
    cards_info = {}
    if inv_ids:
        inv_list = ",".join(map(str, inv_ids))
        res = await fetch_all(f"""
            SELECT i.id, c.name, i.mutation, i.serial_number 
            FROM inventory i JOIN cards c ON i.card_id = c.id 
            WHERE i.id IN ({inv_list}) AND i.count > 0
        """)
        for r in res:
            mut_str = "⭐" if r['mutation'] == 'Gold' else "🌈" if r['mutation'] == 'Rainbow' else ""
            ser_str = f" [#{r['serial_number']:04d}]" if r['serial_number'] > 0 else ""
            cards_info[r['id']] = f"{mut_str}{r['name']}{ser_str}".strip()
            
    header = "🛡 <b>СОСТАВ CARDBALL</b>" if is_fb else "🛡 <b>БОЕВАЯ КОЛОДА</b>"
    await message.answer(f"{header}\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите слот/позицию:", reply_markup=get_equip_main_keyboard(active_acc, cards_info, is_fb))

@dp.callback_query(F.data.startswith("eq_clear_"))
async def cb_eq_clear(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    is_fb = int(callback.data.split("_")[2])
    
    if is_fb:
        await execute_db("UPDATE accounts SET fb_equip1 = 0, fb_equip2 = 0, fb_equip3 = 0, fb_equip4 = 0 WHERE id = ?", (active_acc['id'],))
    else:
        await execute_db("UPDATE accounts SET equip1 = 0, equip2 = 0, equip3 = 0, equip4 = 0 WHERE id = ?", (active_acc['id'],))
        
    await callback.message.edit_text("✅ Боевая колода успешно очищена!")
    await callback.answer()

@dp.callback_query(F.data.startswith("eq_select_"))
async def equip_slot_callback(callback: types.CallbackQuery, state: FSMContext):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    parts = callback.data.split("_")
    slot_num = int(parts[2])
    is_fb = int(parts[3])
    
    inv = await fetch_all("""
        SELECT DISTINCT c.id, c.name, c.rarity, c.class_type
        FROM inventory i JOIN cards c ON i.card_id = c.id WHERE i.user_id = ? AND i.count > 0 AND i.is_football = ?
    """, (active_acc['id'], is_fb))
    
    if not inv: return await callback.answer("Нет карт!", show_alert=True)
    
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '⚪')} {c['name']}"} for c in inv]
    
    await state.update_data(equip_slot=slot_num, equip_items_cards=items, equip_is_fb=is_fb)
    kb = get_pagination_keyboard(items, 0, "eq_c", columns=1, items_per_page=8)
    
    role_names = ["Вратаря", "Защитника", "Полузащитника", "Нападающего"]
    lbl = role_names[slot_num-1] if is_fb else f"Слота {slot_num}"
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
    is_fb = data.get('equip_is_fb', 0)
    
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    invs = await fetch_all("""
        SELECT i.id as inv_id, c.name, c.rarity, c.class_type, i.mutation, i.serial_number, i.signed_by, u.username, u.nickname, i.count
        FROM inventory i 
        JOIN cards c ON i.card_id = c.id 
        LEFT JOIN accounts u ON i.signed_by = u.id
        WHERE i.user_id = ? AND i.card_id = ? AND i.count > 0 AND i.is_football = ?
    """, (active_acc['id'], card_id, is_fb))
    
    if not invs: return await callback.answer("Карта пропала!", show_alert=True)
    
    items = []
    for i in invs:
        c_dict = dict(i)
        if i['signed_by'] > 0:
            c_dict['signer_name'] = get_display_name({'username': i['username'], 'nickname': i['nickname'], 'id': i['signed_by']})
        
        name_str = format_card_name_plain(c_dict)
        mut = "⭐ " if i['mutation'] == 'Gold' else "🌈 " if i['mutation'] == 'Rainbow' else ""
        items.append({"id": i['inv_id'], "btn_text": f"{mut}{name_str} (x{i['count']})"})
        
    await state.update_data(equip_items_vars=items)
    kb = get_pagination_keyboard(items, 0, "eq_v", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"eq_select_{slot_num}_{is_fb}")])
    
    role_names = ["Вратаря", "Защитника", "Полузащитника", "Нападающего"]
    lbl = role_names[slot_num-1] if is_fb else f"Слота {slot_num}"
    await callback.message.edit_text(f"👇 Выберите конкретную копию для <b>{lbl}</b>:", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("eq_v_page_"))
async def equip_var_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('equip_items_vars', []), page, "eq_v", columns=1, items_per_page=6)
    slot_num = data.get('equip_slot', 1)
    is_fb = data.get('equip_is_fb', 0)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"eq_select_{slot_num}_{is_fb}")])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("eq_v_"))
async def equip_var_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    slot_num = data.get('equip_slot', 1)
    is_fb = data.get('equip_is_fb', 0)
    
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    slots = ['fb_equip1', 'fb_equip2', 'fb_equip3', 'fb_equip4'] if is_fb else ['equip1', 'equip2', 'equip3', 'equip4']
    current_eq = [active_acc[s] for s in slots]
    
    if inv_id in current_eq:
        return await callback.answer("❌ Эта копия уже экипирована!", show_alert=True)
        
    card_info = await fetch_one("SELECT card_id FROM inventory WHERE id = ?", (inv_id,))
    if not card_info: return await callback.answer("Error")
    
    if active_acc[slots[slot_num-1]] in current_eq:
        current_eq.remove(active_acc[slots[slot_num-1]])
    
    if any(i != 0 for i in current_eq):
        inv_list = ",".join(map(str, [i for i in current_eq if i != 0]))
        other_cards = await fetch_all(f"SELECT card_id FROM inventory WHERE id IN ({inv_list})")
        if any(c['card_id'] == card_info['card_id'] for c in other_cards):
            return await callback.answer("❌ Нельзя надеть две одинаковые карты!", show_alert=True)

    await execute_db(f"UPDATE accounts SET {slots[slot_num-1]} = ? WHERE id = ?", (inv_id, active_acc['id']))
    role_names = ["Вратарь", "Защитник", "Полузащитник", "Нападающий"]
    lbl = role_names[slot_num-1] if is_fb else f"Слот {slot_num}"
    await callback.message.edit_text(f"✅ Установлено в позицию: {lbl}!")
    await state.clear()
    await callback.answer()

# ========================================================================
# БАТЛ-ПАСС
# ========================================================================
@dp.message(F.text.in_([BTN_BP, BTN_FB_BP]))
async def cmd_battle_passes(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    is_fb = message.text == BTN_FB_BP
    passes = await fetch_all("SELECT * FROM battle_passes WHERE is_football = ? ORDER BY id DESC", (1 if is_fb else 0,))
    
    if not passes:
        return await message.answer("🎟 <b>Батл-пассы</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nНет доступных сезонов.")
        
    kb = []
    for bp in passes:
        kb.append([InlineKeyboardButton(text=f"🎫 {bp['title']}", callback_data=f"bp_view_{bp['id']}")])
        
    await message.answer("🎟 <b>БАТЛ-ПАССЫ</b>\nВыберите сезон:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("bp_view_"))
async def callback_bp_view(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    bp_id = int(callback.data.split("_")[2])
    bp = await fetch_one("SELECT * FROM battle_passes WHERE id = ?", (bp_id,))
    if not bp: return await callback.answer("Not found!", show_alert=True)
    is_fb = bp['is_football']
    
    user_bp = await fetch_one("SELECT * FROM user_bp WHERE user_id = ? AND bp_id = ?", (active_acc['id'], bp_id))
    if not user_bp:
        await execute_db("INSERT INTO user_bp (user_id, bp_id, xp, level, is_active) VALUES (?, ?, 0, 0, 0)", (active_acc['id'], bp_id))
        user_bp = await fetch_one("SELECT * FROM user_bp WHERE user_id = ? AND bp_id = ?", (active_acc['id'], bp_id))
        
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
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"bp_list_{is_fb}")])
    
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
    is_fb = int(callback.data.split("_")[2])
    passes = await fetch_all("SELECT * FROM battle_passes WHERE is_football = ? ORDER BY id DESC", (is_fb,))
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
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    bp_id = int(callback.data.split("_")[3])
    bp = await fetch_one("SELECT is_football FROM battle_passes WHERE id = ?", (bp_id,))
    is_fb = bp['is_football']
    
    await execute_db("""
        UPDATE user_bp SET is_active = 0 
        WHERE user_id = ? AND bp_id IN (SELECT id FROM battle_passes WHERE is_football = ?)
    """, (active_acc['id'], is_fb))
    
    await execute_db("UPDATE user_bp SET is_active = 1 WHERE user_id = ? AND bp_id = ?", (active_acc['id'], bp_id))
    await callback.answer()
    await callback_bp_view(callback)

@dp.callback_query(F.data.startswith("bp_lvl_"))
async def callback_bp_level(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    parts = callback.data.split("_")
    bp_id = int(parts[2])
    req_level = int(parts[3])
    
    bp = await fetch_one("SELECT * FROM battle_passes WHERE id = ?", (bp_id,))
    user_bp = await fetch_one("SELECT level FROM user_bp WHERE user_id = ? AND bp_id = ?", (active_acc['id'], bp_id))
    user_curr_lvl = user_bp['level'] if user_bp else 0
    is_fb = bp['is_football']
    
    lvl_data = await fetch_one("SELECT id, xp_required FROM bp_levels WHERE bp_id = ? AND level = ?", (bp_id, req_level))
    if not lvl_data: return await callback.answer("Level not found", show_alert=True)
        
    rewards = await fetch_all("SELECT * FROM bp_rewards WHERE level_id = ?", (lvl_data['id'],))
    val_name = "Мячей" if is_fb else "Шекелей"
    val_sym = "⚽" if is_fb else "💰"
    
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
                mut = "🌈" if r['mutation'] == 'Rainbow' else ("⭐" if r['mutation'] == 'Gold' else "")
                text += f"└ 🃏 <b>{mut} {n}</b>\n"
                
    text += "\n📊 <b>Статус:</b> "
    is_reached = user_curr_lvl >= req_level
    claim_check = await fetch_one("SELECT * FROM user_bp_claims WHERE user_id = ? AND bp_id = ? AND level = ?", (active_acc['id'], bp_id, req_level))
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
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    parts = callback.data.split("_")
    bp_id = int(parts[2])
    req_level = int(parts[3])
    
    user_bp = await fetch_one("SELECT level FROM user_bp WHERE user_id = ? AND bp_id = ?", (active_acc['id'], bp_id))
    if not user_bp or user_bp['level'] < req_level: return await callback.answer("Locked", show_alert=True)
        
    claim_check = await fetch_one("SELECT * FROM user_bp_claims WHERE user_id = ? AND bp_id = ? AND level = ?", (active_acc['id'], bp_id, req_level))
    if claim_check: return await callback.answer("Already claimed", show_alert=True)
        
    lvl_data = await fetch_one("SELECT id FROM bp_levels WHERE bp_id = ? AND level = ?", (bp_id, req_level))
    rewards = await fetch_all("SELECT * FROM bp_rewards WHERE level_id = ?", (lvl_data['id'],))
    
    bp = await fetch_one("SELECT is_football FROM battle_passes WHERE id = ?", (bp_id,))
    is_fb = bp['is_football']
    bal_col = 'football_balls' if is_fb else 'coins'
    
    db = await get_db_connection()
    try:
        await db.execute("BEGIN")
        for r in rewards:
            if r['reward_type'] == 'shekels':
                if is_fb:
                    await db.execute(f"UPDATE accounts SET {bal_col} = {bal_col} + ? WHERE id = ?", (r['amount'], active_acc['id']))
                else:
                    await db.execute(f"UPDATE accounts SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (r['amount'], r['amount'], active_acc['id']))
            elif r['reward_type'] == 'card':
                res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0 AND is_football = ?", (active_acc['id'], r['card_id'], r['mutation'], is_fb))
                inv_item = await res.fetchone()
                if inv_item:
                    await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                else:
                    await db.execute("INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, 0, 0, ?)", (active_acc['id'], r['card_id'], r['mutation'], is_fb))
        
        await db.execute("INSERT INTO user_bp_claims (user_id, bp_id, level) VALUES (?, ?, ?)", (active_acc['id'], bp_id, req_level))
        await db.commit()
    finally:
        await db.close()
        
    await callback.answer("🎉 Reward claimed!", show_alert=True)
    await callback_bp_level(callback)

# ========================================================================
# БОЕВОЙ ДВИЖОК
# ========================================================================
async def get_team_data(acc_id: int, is_football: int = 0):
    user = await fetch_one("SELECT * FROM accounts WHERE id = ?", (acc_id,))
    team = []
    slots = ['fb_equip1', 'fb_equip2', 'fb_equip3', 'fb_equip4'] if is_football else ['equip1', 'equip2', 'equip3', 'equip4']
    for slot in slots:
        inv_id = user[slot]
        if inv_id != 0:
            row = await fetch_one("""
                SELECT c.id, c.name, c.rarity, c.class_type, c.damage, c.hp, c.booster_dmg_mult, c.booster_hp_mult,
                       i.mutation, i.serial_number, i.signed_by
                FROM inventory i JOIN cards c ON i.card_id = c.id
                WHERE i.id = ? AND i.user_id = ? AND i.count > 0
            """, (inv_id, acc_id))
            
            if row:
                card = dict(row)
                mult = get_mutation_multiplier(card['mutation'])
                card['damage'] = int(card['damage'] * mult)
                card['hp'] = int(card['hp'] * mult)
                if card['class_type'] == 'Booster':
                    card['booster_dmg_mult'] = round(card['booster_dmg_mult'] * mult, 2)
                    card['booster_hp_mult'] = round(card['booster_hp_mult'] * mult, 2)
                    
                if card['signed_by'] > 0:
                    signer_info = await fetch_one("SELECT username, nickname FROM accounts WHERE id = ?", (card['signed_by'],))
                    card['signer_name'] = get_display_name(signer_info) if signer_info else f"Account:{card['signed_by']}"

                card['max_hp'] = card['hp']
                card['burn'] = 0     
                card['dmg_buff'] = 0 
                card['heal_power_mult'] = 1.0
                card['trauma'] = 0
                team.append(card)
            else:
                await execute_db(f"UPDATE accounts SET {slot} = 0 WHERE id = ?", (acc_id,))
    return team

async def get_bot_team(acc_id: int, difficulty_mult: float, rank_name: str, diff_type: str = "med"):
    all_cards = await fetch_all("SELECT id, name, rarity, class_type, damage, hp, booster_dmg_mult, booster_hp_mult FROM cards WHERE rarity != 'Secret'")
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
            gold_prob = min(0.12, 0.05 * difficulty_mult)     
            if mut_chance < rainbow_prob: 
                c_copy['mutation'] = "Rainbow"
                c_copy['damage'] = int(c_copy['damage'] * 1.2)
                c_copy['hp'] = int(c_copy['hp'] * 1.2)
            elif mut_chance < rainbow_prob + gold_prob: 
                c_copy['mutation'] = "Gold"
                c_copy['damage'] = int(c_copy['damage'] * 1.1)
                c_copy['hp'] = int(c_copy['hp'] * 1.1)
            else: c_copy['mutation'] = "Normal"
        else: c_copy['mutation'] = "Normal"
            
        c_copy['max_hp'] = c_copy['hp']
        c_copy['burn'] = 0
        c_copy['dmg_buff'] = 0
        c_copy['serial_number'] = 0
        c_copy['signed_by'] = 0
        c_copy['heal_power_mult'] = 1.0  
        c_copy['trauma'] = 0
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
        elif c.get('mutation') == 'Gold': status += "⭐"
        if c.get('burn', 0) > 0: status += "🔥"
        if c.get('dmg_buff', 0) > 0: status += "✨"
        if c['class_type'] == 'Booster': status += "🔋"
        if c['class_type'] == 'Healer': status += "💗"
        
        s_str = f" [#{c['serial_number']:04d}]" if c.get('serial_number', 0) > 0 else ""
        sgn_str = ""
        if c.get('signed_by', 0) > 0:
            s_name = c.get('signer_name') or f"Account:{c['signed_by']}"
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
                ru_str += " ☠️ <i>Сгорел дотла!</i>"
            add_dual_log(log1, log2, ru_str)
            c['burn'] = 0

async def execute_turn(atk_team, def_team, atk_name, def_name, log1, log2, force_attacker=None, force_target=None):
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
        target['hp'] -= dmg
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
            target['hp'] -= dmg
            ru_str = f"🎯 {atk_name}: Одинокий Хилер <b>{html.escape(atk['name'])}</b> бьет <b>{html.escape(target['name'])}</b> на {dmg}!"
            if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
            add_dual_log(log1, log2, ru_str)
        
    elif c_type == "AOE":
        ru_str = f"🌪 {atk_name}: <b>{html.escape(atk['name'])}</b> бьет по всем на {base_dmg}!"
        for d in def_alive:
            d['hp'] -= base_dmg
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
            d['hp'] -= dmg
            if d['hp'] <= 0:
                d['hp'] = 0
                ru_str += f" ☠️ <i>{html.escape(d['name'])} мертв!</i>"
        add_dual_log(log1, log2, ru_str)
        
    elif c_type == "Fire":
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
            
        target['hp'] -= base_dmg
        target['burn'] = target.get('burn', 0) + base_dmg
        ru_str = f"🔥 {atk_name}: <b>{html.escape(atk['name'])}</b> бьет <b>{html.escape(target['name'])}</b> на {base_dmg} и поджигает!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
    else:
        if force_target and force_target['hp'] > 0 and force_target in def_alive: target = force_target
        else: target = random.choice(def_alive)
            
        target['hp'] -= base_dmg
        ru_str = f"🎯 {atk_name}: <b>{html.escape(atk['name'])}</b> наносит {base_dmg} по <b>{html.escape(target['name'])}</b>!"
        if target['hp'] <= 0: target['hp'] = 0; ru_str += dead_ru
        add_dual_log(log1, log2, ru_str)
        
    return True, heals

async def get_dynamic_trophies(rank_name: str, rank_idx: int, diff_scale: float = 1.0) -> int:
    if "Uranium VI" in rank_name or "Uranium VII" in rank_name:
        return random.randint(1, 2)
    base = max(5, 18 - int((rank_idx / 25) * 12)) 
    won = random.randint(base, base+3)
    return int(won * diff_scale)

async def add_bp_xp(acc_id: int, xp_to_add: int, is_football: int = 0) -> tuple:
    db = await get_db_connection()
    try:
        user_bp = await db.execute("""
            SELECT ubp.bp_id, ubp.level, ubp.xp 
            FROM user_bp ubp JOIN battle_passes bp ON ubp.bp_id = bp.id
            WHERE ubp.user_id = ? AND ubp.is_active = 1 AND bp.is_football = ?
        """, (acc_id, is_football))
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
                
        await db.execute("UPDATE user_bp SET level = ?, xp = ? WHERE user_id = ? AND bp_id = ?", (curr_lvl, curr_xp, acc_id, bp_id))
        bp_info = await db.execute("SELECT title FROM battle_passes WHERE id = ?", (bp_id,))
        bp = await bp_info.fetchone()
        
        await db.commit()
        return level_up, bp['title'] if bp else "BP", curr_lvl
    finally:
        await db.close()

# --- ЛОГИКА РУЧНОГО БОЯ ---
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
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    if chat_id not in active_manual_battles or active_manual_battles[chat_id]['p1_id'] != active_acc['id']:
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
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    if chat_id not in active_manual_battles or active_manual_battles[chat_id]['p1_id'] != active_acc['id']:
        return await callback.answer("Не ваш ход!", show_alert=True)

    idx = int(callback.data.split("_")[1])
    active_manual_battles[chat_id]['target_idx'] = idx
    active_manual_battles[chat_id]['event'].set()
    await callback.answer()

async def do_player_turn_wrapper(chat_id, p1_id, p1_name, p2_name, t1, t2, log, mods, is_pvp):
    if mods and mods.get('mod_manual_atk') and not is_pvp:
        atk, tgt = await player_manual_turn(chat_id, p1_id, t1, t2)
        did_turn, heals = await execute_turn(t1, t2, p1_name, p2_name, log, None, force_attacker=atk, force_target=tgt)
    else:
        did_turn, heals = await execute_turn(t1, t2, p1_name, p2_name, log, None)
    return did_turn, heals

# -----------------------------
# КНОПКА СДАТЬСЯ
@dp.callback_query(F.data.startswith("surrender_battle_"))
async def cb_surrender_battle_fixed(callback: types.CallbackQuery):
    battle_id = callback.data.split("_")[2]
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    surrendered_players.add((active_acc['id'], battle_id))
    chat_id = callback.message.chat.id
    if chat_id in active_manual_battles and active_manual_battles[chat_id]['p1_id'] == active_acc['id']:
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

async def run_battle_loop(bot: Bot, chat_id: int, p1_id: int, p1_name: str, p2_id: int, p2_name: str, t1: list, t2: list, diff_trophies_scale: float = 1.0, diff_bp_mult: float = 1.0, is_pvp: bool = False, pvp_no_rewards: bool = False, mods=None):
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

                did_turn_e, heals_e = await execute_turn(t2, t1, p2_name, p1_name, log, None)
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
                    did_turn_e_extra, heals_e_extra = await execute_turn(t2, t1, p2_name, p1_name, log, None)
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

            if winner_user_id is not None and "Ничья" not in winner:
                if random.random() <= 0.05: 
                    db = await get_db_connection()
                    try:
                        new_code = generate_reward_code()
                        amt = random.randint(1000, 5000)
                        await db.execute(
                            "INSERT INTO reward_codes (code, reward_type, amount, item_id, mutation, owner_id, is_active, is_football) VALUES (?, ?, ?, ?, ?, ?, 1, 0)",
                            (new_code, 'shekels', amt, 0, 'Normal', winner_user_id)
                        )
                        await db.commit()
                        code_text = (
                            f"🎁 <b>ВЫПАЛ УНИКАЛЬНЫЙ КОД-НАГРАДА! (Шанс 5%)</b>\nНажми, чтобы скопировать: <code>{new_code}</code>\nАктивируй через /codereward\n\n"
                        )
                    except Exception as e: 
                        logging.error(f"Reward Code Drop Error: {e}")
                    finally: 
                        await db.close()

            final_text = code_text + f"🏁 <b>ИТОГИ БОЯ: {p1_name} VS {p2_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n👑 <b>Победитель: {winner}</b>\n\n"
            bp_messages = []
            
            if pvp_no_rewards:
                final_text += "🤝 <b>Дружеская дуэль завершена!</b> Награды и кубки не начислялись."
            elif is_pvp:
                if "Ничья" not in winner and winner_id and loser_id:
                    await execute_db("UPDATE accounts SET trophies = trophies + 15 WHERE id = ?", (winner_id,))
                    await execute_db("UPDATE accounts SET trophies = MAX(0, trophies - 10) WHERE id = ?", (loser_id,))
                    final_text += f"🏆 Победитель забирает <b>+15 Кубков</b>\n💀 Проигравший теряет <b>-10 Кубков</b>"
            else:
                mod_reward_mult = 1.0; mod_trophy_mult = 1.0
                if mods:
                    if mods.get('mod_enemy_hp'): mod_reward_mult += 0.3; mod_trophy_mult += 0.3
                    if mods.get('mod_enemy_atk_all'): mod_reward_mult += 0.35; mod_trophy_mult += 0.35
                    if mods.get('mod_enemy_stats'): mod_reward_mult += 0.2; mod_trophy_mult += 0.2
                    if mods.get('mod_player_atk_all'): mod_reward_mult -= 0.4
                    if mods.get('mod_manual_atk'): mod_reward_mult -= 0.5
                    if mods.get('mod_player_hp'): mod_reward_mult -= 0.3
                    
                mod_reward_mult = max(0.1, mod_reward_mult)
                coin_mult, xp_mult_event = await get_coin_xp_events()
                
                if winner == p1_name:
                    user_data = await fetch_one("SELECT trophies, telegram_id FROM accounts WHERE id = ?", (p1_id,))
                    user_trophies = user_data['trophies'] if user_data else 0
                    rank = await get_user_rank(user_trophies)
                    
                    coins_base = random.randint(25, 90) * rank['reward_mult'] * diff_trophies_scale * 0.85 * coin_mult
                    coins_won = int(coins_base * mod_reward_mult)
                    won_t_base = await get_dynamic_trophies(rank['name'], rank['rank_idx'], diff_trophies_scale)
                    won_t = int(won_t_base * mod_trophy_mult)
                    
                    await execute_db("UPDATE accounts SET coins = coins + ?, total_coins = total_coins + ?, trophies = trophies + ? WHERE id = ?", (coins_won, coins_won, won_t, p1_id))
                    
                    final_text += f"🎉 <b>Награды:</b>\n💰 {coins_won} Шекелей"
                    if coin_mult > 1.0: final_text += f" (Ивент x{coin_mult})"
                    if mod_reward_mult != 1.0: final_text += f" [Моды x{mod_reward_mult:.2f}]"
                    final_text += f"\n🏆 {won_t} Кубков\n"
                    
                    bp_xp = int((20 * diff_bp_mult * xp_mult_event) * mod_reward_mult)
                    lvl_up, bp_title, new_lvl = await add_bp_xp(p1_id, bp_xp)
                    final_text += f"🎫 +{bp_xp} BP XP"
                    if lvl_up and user_data: bp_messages.append((user_data['telegram_id'], f"🎉 <b>НОВЫЙ УРОВЕНЬ БП!</b> {new_lvl} уровень в сезоне «{bp_title}»!"))
                    
                elif winner == p2_name:
                    user_data = await fetch_one("SELECT trophies, telegram_id FROM accounts WHERE id = ?", (p1_id,))
                    user_trophies = user_data['trophies'] if user_data else 0
                    rank = await get_user_rank(user_trophies)
                    
                    if "Uranium VI" in rank['name'] or "Uranium VII" in rank['name']:
                        lost_t = random.randint(30, 50)
                    else:
                        lost_t = 2
                    
                    await execute_db("UPDATE accounts SET trophies = MAX(0, trophies - ?) WHERE id = ?", (lost_t, p1_id))
                    final_text += f"💀 Вы проиграли и потеряли <b>{lost_t} 🏆</b>.\n"
                    bp_xp = int((5 * diff_bp_mult * xp_mult_event) * mod_reward_mult)
                    lvl_up, bp_title, new_lvl = await add_bp_xp(p1_id, bp_xp)
                    final_text += f"🎫 +{bp_xp} BP XP"
                    if lvl_up and user_data: bp_messages.append((user_data['telegram_id'], f"🎉 <b>НОВЫЙ УРОВЕНЬ БП!</b> {new_lvl} уровень в сезоне «{bp_title}»!"))
                    
            try: await msg.edit_text(final_text, reply_markup=None)
            except Exception: pass
            
            for tg_id, b_msg in bp_messages:
                try: await bot.send_message(tg_id, b_msg)
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
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    if active_acc['id'] in active_combats: return await message.answer("❌ Вы уже в бою!")
    if active_acc['id'] in user_trades: return await message.answer("❌ Завершите обмен!")
        
    team1 = await get_team_data(active_acc['id'])
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
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    if active_acc['id'] in active_combats or active_acc['id'] in user_trades:
        return await callback.answer("❌ Заняты!", show_alert=True)
        
    diff_type = callback.data.split("_")[2]
    power_mult, trophies_scale, bp_xp_mult = 1.0, 1.0, 1.0
    
    diff_name = "Средний"
    if diff_type == "easy": power_mult, trophies_scale, bp_xp_mult, diff_name = 0.7, 0.5, 0.8, "Лёгкий 🟢"
    elif diff_type == "med": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.0, 1.0, 1.0, "Средний 🟡"
    elif diff_type == "hard": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.5, 1.4, 1.2, "Сложный 🔴" 
    elif diff_type == "nightmare": power_mult, trophies_scale, bp_xp_mult, diff_name = 1.9, 1.8, 1.5, "Кошмар ☠️"
        
    mods = {
        'mod_enemy_hp': active_acc.get('mod_enemy_hp', 0),
        'mod_enemy_atk_all': active_acc.get('mod_enemy_atk_all', 0),
        'mod_enemy_stats': active_acc.get('mod_enemy_stats', 0),
        'mod_player_atk_all': active_acc.get('mod_player_atk_all', 0),
        'mod_manual_atk': active_acc.get('mod_manual_atk', 0),
        'mod_player_hp': active_acc.get('mod_player_hp', 0)
    }

    try: await callback.message.edit_text(f"⚔️ <i>Ищем противника... Сложность: <b>{diff_name}</b></i>")
    except: pass
    
    team1 = await get_team_data(active_acc['id'])
    rank = await get_user_rank(active_acc['trophies'])
    
    team2 = await get_bot_team(active_acc['id'], rank['difficulty_mult'] * power_mult, rank['name'], diff_type)
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
            
    title_str = await get_user_titles_str(active_acc['id'])
    p1_name = get_display_name(active_acc) + title_str
    active_combats.add(active_acc['id'])
    
    await log_user_action(active_acc['id'], f"Начал PvE бой (сложность: {diff_type})")
    
    asyncio.create_task(run_battle_loop(bot, callback.message.chat.id, active_acc['id'], p1_name, 0, f"AI ({diff_name})", team1, team2, trophies_scale, bp_xp_mult, is_pvp=False, mods=mods))
    await callback.answer()

@dp.message(F.text == BTN_PVP)
async def cmd_pvp_menu(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    if active_acc['id'] in active_combats or active_acc['id'] in user_trades: return await message.answer("❌ Заняты!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Найти случайного (Автоподбор)", callback_data="pvp_random")],
        [InlineKeyboardButton(text="🎯 Вызвать по @username игрового аккаунта", callback_data="pvp_direct")]
    ])
    await message.answer("⚔️ <b>PvP ДУЭЛЬ</b>\nВыберите режим (награды за PvP дуэли отключены):", reply_markup=kb)

@dp.callback_query(F.data == "pvp_direct")
async def cb_pvp_direct(callback: types.CallbackQuery, state: FSMContext):
    try: await callback.message.edit_text("Введите кастомный @username игрового аккаунта соперника:")
    except: pass
    await state.set_state(PvPState.waiting_target)
    asyncio.create_task(clear_fsm_timeout(state, callback.message.chat.id, 60))
    await callback.answer()

@dp.callback_query(F.data == "pvp_random")
async def cb_pvp_random(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    u_id = active_acc['id']
    
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
        
        opp = await fetch_one("SELECT * FROM accounts WHERE id=?", (opp_id,))
        t2 = await get_team_data(opp_id)
        
        active_combats.add(u_id)
        active_combats.add(opp_id)
        
        title_p1 = await get_user_titles_str(u_id)
        title_p2 = await get_user_titles_str(opp_id)
        p1_name = get_display_name(active_acc) + title_p1
        p2_name = get_display_name(opp) + title_p2
        
        try: await callback.message.edit_text("Противник найден! Начинаем...")
        except: pass
        try: await bot.send_message(opp['telegram_id'], "Противник найден! Начинаем...")
        except: pass
        
        await log_user_action(u_id, f"Начал PvP бой (Автоподбор) против аккаунта {opp_id}")
        await log_user_action(opp_id, f"Начал PvP бой (Автоподбор) против аккаунта {u_id}")
        
        asyncio.create_task(run_pvp_dual_broadcast(u_id, opp_id, p1_name, p2_name, t1, t2))
    else:
        pvp_queue.add(u_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить поиск", callback_data="pvp_random")]])
        try: await callback.message.edit_text("🔍 Поиск противника... Ожидайте.", reply_markup=kb)
        except: pass
    await callback.answer()

@dp.message(PvPState.waiting_target)
async def process_pvp_target(message: types.Message, state: FSMContext):
    val = message.text.strip().lstrip('@')
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Ошибка аккаунта")
    
    target_user = await fetch_one("SELECT * FROM accounts WHERE username = ?", (val,))
        
    if not target_user: return await message.answer("❌ Игровой аккаунт с таким юзернеймом не найден.")
    if target_user['id'] == active_acc['id']: return await message.answer("❌ Самому себе нельзя!")
    if target_user['id'] in active_combats or target_user['id'] in user_trades: return await message.answer("❌ Игрок сейчас занят!")

    challenger_name = get_display_name(active_acc) + await get_user_titles_str(active_acc['id'])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Принять", callback_data=f"pvp_accept_{active_acc['id']}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pvp_decline_{active_acc['id']}")]
    ])
    
    try:
        await bot.send_message(target_user['telegram_id'], f"⚔️ <b>{challenger_name}</b> вызывает ваш активный аккаунт на дуэль!", reply_markup=kb)
        await message.answer("📨 Вызов отправлен.")
        await log_user_action(active_acc['id'], f"Бросил вызов на PvP аккаунту {target_user['id']}")
    except: await message.answer("Ошибка при отправке вызова.")
    await state.clear()

@dp.callback_query(F.data.startswith("pvp_accept_"))
async def callback_pvp_accept(callback: types.CallbackQuery):
    challenger_id = int(callback.data.split("_")[2])
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    target_id = active_acc['id']
    
    if target_id in active_combats or challenger_id in active_combats or target_id in user_trades or challenger_id in user_trades:
        return await callback.answer("Заняты!", show_alert=True)
        
    t1 = await get_team_data(challenger_id)
    t2 = await get_team_data(target_id)
    
    if not t1 or not t2: 
        try: await callback.message.edit_text("Deck empty error.")
        except: pass
        return
        
    challenger = await fetch_one("SELECT * FROM accounts WHERE id = ?", (challenger_id,))
    
    title_p1 = await get_user_titles_str(challenger_id)
    title_p2 = await get_user_titles_str(target_id)
    p1_name = get_display_name(challenger) + title_p1
    p2_name = get_display_name(active_acc) + title_p2
    
    active_combats.add(challenger_id)
    active_combats.add(target_id)
    
    await log_user_action(target_id, f"Принял PvP вызов от аккаунта {challenger_id}")
    
    asyncio.create_task(run_pvp_dual_broadcast(challenger_id, target_id, p1_name, p2_name, t1, t2))
    try: await callback.message.delete()
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("pvp_decline_"))
async def callback_pvp_decline(callback: types.CallbackQuery):
    challenger_id = int(callback.data.split("_")[2])
    challenger = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (challenger_id,))
    if challenger:
        try: await bot.send_message(challenger['telegram_id'], f"❌ Вызов отклонен.")
        except: pass
    try: await callback.message.edit_text("❌ Вы отклонили вызов.")
    except: pass
    await callback.answer()

async def run_pvp_dual_broadcast(p1_id: int, p2_id: int, p1_name: str, p2_name: str, t1: list, t2: list):
    battle_id = f"pvp_{p1_id}_{p2_id}_{int(time.time())}"
    surrendered_players.discard((p1_id, battle_id))
    surrendered_players.discard((p2_id, battle_id))
    
    p1_acc = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (p1_id,))
    p2_acc = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (p2_id,))
    
    if not p1_acc or not p2_acc:
        return
        
    try:
        msg1 = await bot.send_message(p1_acc['telegram_id'], f"⚔️ Дуэль против <b>{p2_name}</b> начнется через 3 сек!")
        msg2 = await bot.send_message(p2_acc['telegram_id'], f"⚔️ Дуэль против <b>{p1_name}</b> начнется через 3 сек!")
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

            did_turn, h = await execute_turn(t1, t2, p1_name, p2_name, log1, log2)
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
                    
                did_turn, h = await execute_turn(t2, t1, p2_name, p1_name, log1, log2)
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
                        new_code = generate_reward_code()
                        amt = random.randint(1000, 5000)
                        await db.execute(
                            "INSERT INTO reward_codes (code, reward_type, amount, item_id, mutation, owner_id, is_active, is_football) VALUES (?, ?, ?, ?, ?, ?, 1, 0)",
                            (new_code, 'shekels', amt, 0, 'Normal', winner_user_id)
                        )
                        await db.commit()
                        dropped_msg = f"🎁 <b>ВЫПАЛ УНИКАЛЬНЫЙ КОД-НАГРАДА! (5%)</b>\nНажми, чтобы скопировать: <code>{new_code}</code>\nАктивируй через /codereward\n\n"
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

# ========================================================================
# ТРЕЙДЫ (ИСПРАВЛЕННЫЕ И ОПТИМИЗИРОВАННЫЕ)
# ========================================================================
@dp.message(Command("trade"))
async def cmd_trade_request(message: types.Message, state: FSMContext):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    if active_acc['id'] in active_combats or active_acc['id'] in user_trades: 
        return await message.answer("Заняты!")
        
    parts = message.text.split()
    if len(parts) > 1:
        message.text = parts[1]
        await process_trade_target(message, state)
    else:
        await message.answer("🤝 <b>ОБМЕН</b>\nВведите @username игрового аккаунта партнера:")
        await state.set_state(TradeState.waiting_target)
        asyncio.create_task(clear_fsm_timeout(state, message.chat.id, 60))

@dp.message(TradeState.waiting_target)
async def process_trade_target(message: types.Message, state: FSMContext):
    val = message.text.strip().lstrip('@')
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await state.clear()
    
    target_user = await fetch_one("SELECT * FROM accounts WHERE username = ?", (val,))
        
    if not target_user: return await message.answer("Игровой аккаунт не найден.")
    if target_user['id'] == active_acc['id']: return await message.answer("Самому себе нельзя!")
    if target_user['id'] in active_combats or target_user['id'] in user_trades: return await message.answer("Игрок занят!")

    challenger_name = get_display_name(active_acc) + await get_user_titles_str(active_acc['id'])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"tr_acc_{active_acc['id']}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"tr_dec_{active_acc['id']}")]
    ])
    
    try:
        await bot.send_message(target_user['telegram_id'], f"🤝 <b>{challenger_name}</b> предлагает вам обмен картами!", reply_markup=kb)
        await message.answer("📨 Запрос обмена отправлен.")
        await log_user_action(active_acc['id'], f"Отправил запрос на трейд аккаунту {target_user['id']}")
    except: await message.answer("Ошибка при отправке запроса.")
    await state.clear()

@dp.callback_query(F.data.startswith("tr_acc_"))
async def callback_trade_accept(callback: types.CallbackQuery):
    p1_id = int(callback.data.split("_")[2])
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer("Ошибка аккаунта", show_alert=True)
    p2_id = active_acc['id']
    
    if p1_id in user_trades or p2_id in user_trades or p1_id in active_combats or p2_id in active_combats: 
        return await callback.answer("Заняты!", show_alert=True)
        
    p1 = await fetch_one("SELECT * FROM accounts WHERE id = ?", (p1_id,))
    p2 = await fetch_one("SELECT * FROM accounts WHERE id = ?", (p2_id,))
    
    trade_id = f"tr_{p1_id}_{p2_id}_{int(time.time())}"
    trade = {
        'id': trade_id, 'p1': p1_id, 'p2': p2_id,
        'p1_name': get_display_name(p1), 'p2_name': get_display_name(p2),
        'p1_offer': {}, 'p2_offer': {},  
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
        msg1 = await bot.send_message(p1['telegram_id'], await render_trade_text(trade), reply_markup=get_trade_main_kb(trade, p1_id))
        trade['p1_msg'] = msg1.message_id
    except: pass
    try:
        msg2 = await bot.send_message(p2['telegram_id'], await render_trade_text(trade), reply_markup=get_trade_main_kb(trade, p2_id))
        trade['p2_msg'] = msg2.message_id
    except: pass
    
    try: await callback.message.delete()
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_dec_"))
async def callback_trade_decline(callback: types.CallbackQuery):
    p1_id = int(callback.data.split("_")[2])
    p1 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (p1_id,))
    if p1:
        try: await bot.send_message(p1['telegram_id'], "❌ Запрос на обмен отклонен.")
        except: pass
    try: await callback.message.edit_text("❌ Отклонено.")
    except: pass
    await callback.answer()

async def render_trade_text(trade):
    text = "🤝 <b>ТОРГОВАЯ КОМНАТА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    text += f"🔵 <b>Предлагает {trade['p1_name']}:</b>\n"
    if not trade['p1_offer']: text += "  └ <i>Ничего</i>\n"
    else:
        for inv_id, qty in trade['p1_offer'].items(): text += f"  └ {qty}x {trade['p1_strings'].get(inv_id, '?')}\n"
            
    text += f"\n🔴 <b>Предлагает {trade['p2_name']}:</b>\n"
    if not trade['p2_offer']: text += "  └ <i>Ничего</i>\n"
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
            InlineKeyboardButton(text="➕ Добавить", callback_data="tr_menu_add"),
            InlineKeyboardButton(text="➖ Убрать", callback_data="tr_menu_rem")
        ])
        is_ready = trade['p1_ready'] if user_id == trade['p1'] else trade['p2_ready']
        if is_ready: kb.append([InlineKeyboardButton(text="⏳ Ждем партнера...", callback_data="ignore")])
        else: kb.append([InlineKeyboardButton(text="✅ ГОТОВ К ОБМЕНУ", callback_data="tr_action_ready")])
            
    kb.append([InlineKeyboardButton(text="❌ Отменить трейд", callback_data="tr_action_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def update_trade_uis(trade):
    p1 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (trade['p1'],))
    p2 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (trade['p2'],))
    try: await bot.edit_message_text(await render_trade_text(trade), chat_id=p1['telegram_id'], message_id=trade['p1_msg'], reply_markup=get_trade_main_kb(trade, trade['p1']))
    except: pass
    try: await bot.edit_message_text(await render_trade_text(trade), chat_id=p2['telegram_id'], message_id=trade['p2_msg'], reply_markup=get_trade_main_kb(trade, trade['p2']))
    except: pass

@dp.callback_query(F.data.startswith("tr_action_"))
async def cb_trade_actions_fixed(callback: types.CallbackQuery):
    action = callback.data.split("_")[2]
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    user_id = active_acc['id']
    
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer("Ошибка: Трейд не найден", show_alert=True)
    trade = active_trades[trade_id]
    
    if action == "cancel":
        trade['status'] = 'cancelled'
        p1 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (trade['p1'],))
        p2 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (trade['p2'],))
        try: await bot.edit_message_text("❌ Обмен отменен.", chat_id=p1['telegram_id'], message_id=trade['p1_msg'])
        except: pass
        try: await bot.edit_message_text("❌ Обмен отменен.", chat_id=p2['telegram_id'], message_id=trade['p2_msg'])
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
        async def transfer_items(from_u, to_u, offer):
            for i_id, qty in offer.items():
                cur = await db.execute("SELECT card_id, mutation, serial_number, signed_by, count, is_football FROM inventory WHERE id = ?", (i_id,))
                row = await cur.fetchone()
                if not row or row['count'] < qty: raise Exception("Not enough")
                
                if row['count'] == qty:
                    await db.execute("DELETE FROM inventory WHERE id = ?", (i_id,))
                    await db.execute("UPDATE accounts SET equip1 = 0 WHERE equip1 = ?", (i_id,))
                    await db.execute("UPDATE accounts SET equip2 = 0 WHERE equip2 = ?", (i_id,))
                    await db.execute("UPDATE accounts SET equip3 = 0 WHERE equip3 = ?", (i_id,))
                    await db.execute("UPDATE accounts SET equip4 = 0 WHERE equip4 = ?", (i_id,))
                else:
                    await db.execute("UPDATE inventory SET count = count - ? WHERE id = ?", (qty, i_id))
                    
                cur2 = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = ? AND signed_by = ? AND is_football = ?", (to_u, row['card_id'], row['mutation'], row['serial_number'], row['signed_by'], row['is_football']))
                dest = await cur2.fetchone()
                
                if dest: await db.execute("UPDATE inventory SET count = count + ? WHERE id = ?", (qty, dest['id']))
                else: await db.execute("INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, ?, ?, ?, ?, ?)", (to_u, row['card_id'], qty, row['mutation'], row['serial_number'], row['signed_by'], row['is_football']))

        await transfer_items(trade['p1'], trade['p2'], trade['p1_offer'])
        await transfer_items(trade['p2'], trade['p1'], trade['p2_offer'])
        await db.commit()
        success = True
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Trade Error: {e}")
        success = False
    finally:
        await db.close()
        
    p1 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (trade['p1'],))
    p2 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (trade['p2'],))
        
    if success:
        await log_user_action(trade['p1'], f"Успешно завершил трейд с {trade['p2']}")
        await log_user_action(trade['p2'], f"Успешно завершил трейд с {trade['p1']}")
        try: await bot.edit_message_text("🎉 <b>ОБМЕН ЗАВЕРШЕН! Карты переведены.</b>", chat_id=p1['telegram_id'], message_id=trade['p1_msg'])
        except: pass
        try: await bot.edit_message_text("🎉 <b>ОБМЕН ЗАВЕРШЕН! Карты переведены.</b>", chat_id=p2['telegram_id'], message_id=trade['p2_msg'])
        except: pass
    else:
        try: await bot.edit_message_text("❌ ОШИБКА ОБМЕНА (предметы пропали или не найдены).", chat_id=p1['telegram_id'], message_id=trade['p1_msg'])
        except: pass
        try: await bot.edit_message_text("❌ ОШИБКА ОБМЕНА (предметы пропали или не найдены).", chat_id=p2['telegram_id'], message_id=trade['p2_msg'])
        except: pass

async def cancel_trade(trade_id, reason="Cancelled"):
    trade = active_trades.pop(trade_id, None)
    if not trade: return
    user_trades.pop(trade['p1'], None)
    user_trades.pop(trade['p2'], None)
    p1 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (trade['p1'],))
    p2 = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (trade['p2'],))
    try: await bot.edit_message_text(f"❌ {reason}", chat_id=p1['telegram_id'], message_id=trade['p1_msg'])
    except: pass
    try: await bot.edit_message_text(f"❌ {reason}", chat_id=p2['telegram_id'], message_id=trade['p2_msg'])
    except: pass

@dp.callback_query(F.data == "tr_menu_add")
async def cb_trade_menu_add(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    user_id = active_acc['id']
    
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    
    trade['p1_ready'] = False; trade['p2_ready'] = False
    trade['p1_confirmed'] = False; trade['p2_confirmed'] = False
    
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by, u.username, u.nickname
        FROM inventory i JOIN cards c ON i.card_id = c.id LEFT JOIN accounts u ON i.signed_by = u.id
        WHERE i.user_id = ? AND i.count > 0 AND i.is_football = 0
    """, (user_id,))
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    
    items = []
    for c in inv:
        avail = c['count'] - offer_dict.get(c['inv_id'], 0)
        if avail > 0:
            if c['signed_by'] != 0: c['signer_name'] = get_display_name({'username': c['username'], 'nickname': c['nickname'], 'id': c['signed_by']})
            n = format_card_name_plain(c)
            mut = "⭐ " if c['mutation'] == 'Gold' else ("🌈 " if c['mutation'] == 'Rainbow' else "")
            items.append({"id": c['inv_id'], "btn_text": f"{mut}{n} ({avail})"})
            
    kb = get_pagination_keyboard(items, 0, "tr_add", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙", callback_data="tr_menu_main")])
    try: await callback.message.edit_text("👇 Выберите карту для добавления:", reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_add_page_"))
async def cb_trade_add_paginate(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[3])
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    user_id = active_acc['id']
    
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    
    inv = await fetch_all("""
        SELECT c.id as card_id, c.name, c.rarity, c.class_type, i.id as inv_id, i.count, i.mutation, i.serial_number, i.signed_by, u.username, u.nickname
        FROM inventory i JOIN cards c ON i.card_id = c.id LEFT JOIN accounts u ON i.signed_by = u.id
        WHERE i.user_id = ? AND i.count > 0 AND i.is_football = 0
    """, (user_id,))
    inv.sort(key=lambda x: RARITY_WEIGHT.get(x['rarity'], 0), reverse=True)
    items = []
    for c in inv:
        avail = c['count'] - offer_dict.get(c['inv_id'], 0)
        if avail > 0:
            if c['signed_by'] != 0: c['signer_name'] = get_display_name({'username': c['username'], 'nickname': c['nickname'], 'id': c['signed_by']})
            n = format_card_name_plain(c)
            mut = "⭐ " if c['mutation'] == 'Gold' else ("🌈 " if c['mutation'] == 'Rainbow' else "")
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
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    user_id = active_acc['id']
    
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    string_dict = trade['p1_strings'] if user_id == trade['p1'] else trade['p2_strings']
    
    row = await fetch_one("""
        SELECT c.name, i.mutation, i.count 
        FROM inventory i JOIN cards c ON i.card_id = c.id 
        WHERE i.id = ? AND i.user_id = ?
    """, (inv_id, user_id))
    
    if row and offer_dict.get(inv_id, 0) < row['count']:
        offer_dict[inv_id] = offer_dict.get(inv_id, 0) + 1
        mut = "⭐ " if row['mutation'] == 'Gold' else ("🌈 " if row['mutation'] == 'Rainbow' else "")
        string_dict[inv_id] = f"{mut}{row['name']}"
    else:
        return await callback.answer("Больше нет копий!", show_alert=True)
        
    trade['p1_ready'] = False; trade['p2_ready'] = False
    trade['p1_confirmed'] = False; trade['p2_confirmed'] = False
    
    await callback.answer("✅ Добавлено!")
    await update_trade_uis(trade)
    fake_call = callback.model_copy(update={"data": "tr_menu_add"})
    await cb_trade_menu_add(fake_call)

@dp.callback_query(F.data == "tr_menu_rem")
async def cb_trade_menu_rem(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    user_id = active_acc['id']
    
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    string_dict = trade['p1_strings'] if user_id == trade['p1'] else trade['p2_strings']
    
    items = []
    for i_id, qty in offer_dict.items():
        if qty > 0: items.append({"id": i_id, "btn_text": f"❌ Убрать: {string_dict[i_id]} (x{qty})"})
            
    if not items:
        return await callback.answer("Вы еще ничего не добавили!", show_alert=True)
        
    kb = get_pagination_keyboard(items, 0, "tr_rem", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙", callback_data="tr_menu_main")])
    try: await callback.message.edit_text("👇 Нажмите, чтобы убрать:", reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_rem_page_"))
async def cb_trade_rem_paginate(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[3])
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    user_id = active_acc['id']
    
    trade_id = user_trades.get(user_id)
    if not trade_id or trade_id not in active_trades: return await callback.answer()
    trade = active_trades[trade_id]
    offer_dict = trade['p1_offer'] if user_id == trade['p1'] else trade['p2_offer']
    string_dict = trade['p1_strings'] if user_id == trade['p1'] else trade['p2_strings']
    
    items = []
    for i_id, qty in offer_dict.items():
        if qty > 0: items.append({"id": i_id, "btn_text": f"❌ Убрать: {string_dict[i_id]} (x{qty})"})
            
    kb = get_pagination_keyboard(items, page, "tr_rem", columns=1, items_per_page=6)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙", callback_data="tr_menu_main")])
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("tr_rem_"))
async def cb_trade_do_rem(callback: types.CallbackQuery):
    if "page" in callback.data: return
    inv_id = int(callback.data.split("_")[2])
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    user_id = active_acc['id']
    
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
    
    await callback.answer("➖ Убрано!")
    await update_trade_uis(trade)
    fake_call = callback.model_copy(update={"data": "tr_menu_rem"})
    await cb_trade_menu_rem(fake_call)

@dp.callback_query(F.data == "tr_menu_main")
async def cb_trade_menu_main(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    user_id = active_acc['id']
    
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

# ========================================================================
# СИД-ПАКИ
# ========================================================================
@dp.message(F.text.in_([BTN_SEED_PACKS, BTN_FB_PACKS]))
async def cmd_seed_packs_menu(message: types.Message):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    is_fb = message.text == BTN_FB_PACKS
    packs = await fetch_all("SELECT * FROM seed_packs WHERE is_football = ?", (1 if is_fb else 0,))
    
    bal = active_acc['football_balls'] if is_fb else active_acc['coins']
    val_sym = "⚽" if is_fb else "💰"
    val_name = "Мячей" if is_fb else "Шекелей"
    
    text = (
        f"📦 <b>МАГАЗИН СИД-ПАКОВ {'(CARDBALL)' if is_fb else ''}</b>\n{val_sym} Твой баланс: <b>{bal} {val_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nСид-Пак — это особый набор карт с гарантированным набором юнитов и повышенным шансом мутаций (<b>12% на Золотую</b>, <b>2% на Радужную</b>)!\n\nДоступные паки:\n"
    )
    
    kb = []
    if not packs:
        text += "\n<i>Пусто. Ожидайте!</i>"
    else:
        for p in packs:
            desc_text = f" — {p['description']}" if p['description'] else ""
            price_val = p.get('price', 2000)
            text += f"🔹 <b>{p['title']}</b> (Цена: <b>{price_val} {val_sym}</b>){desc_text}\n"
            kb.append([InlineKeyboardButton(text=f"🔍 Смотреть: {p['title']}", callback_data=f"sp_view_{p['id']}_shop")])
            
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("sp_view_"))
async def cb_sp_view(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer("Ошибка аккаунта", show_alert=True)
    
    parts = callback.data.split("_")
    pack_id = int(parts[2])
    mode = parts[3] 
    
    pack = await fetch_one("SELECT * FROM seed_packs WHERE id = ?", (pack_id,))
    if not pack: return await callback.answer("Error!", show_alert=True)
    is_fb = pack['is_football'] == 1
    
    pack_cards = await fetch_all("SELECT c.name, spc.drop_chance FROM seed_pack_cards spc JOIN cards c ON spc.card_id = c.id WHERE spc.pack_id = ?", (pack_id,))
    pack_price = pack.get('price', 2000)
    
    text = f"📦 <b>СИД-ПАК: {pack['title']}</b>\n💬 <i>{pack['description']}</i>\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>Содержимое пака:</b>\n"
    if not pack_cards:
        text += "  └ <i>Пак пуст!</i>\n"
    else:
        luck_mult, _ = await get_active_events()
        total_w = sum(c['drop_chance'] * (luck_mult if c['drop_chance'] < 15.0 else 1.0) for c in pack_cards)
        for idx, c in enumerate(pack_cards, 1):
            w = c['drop_chance'] * (luck_mult if c['drop_chance'] < 15.0 else 1.0)
            chance_pct = (w / total_w) * 100 if total_w > 0 else 0
            text += f"  {idx}. {c['name']} (~{chance_pct:.2f}%)\n"
            
    kb = []
    if mode == "shop":
        bal = active_acc['football_balls'] if is_fb else active_acc['coins']
        val_sym = "⚽" if is_fb else "💰"
        val_name = "Мячей" if is_fb else "Шекелей"
        text += f"\n{val_sym} Ваш баланс: <b>{bal} {val_name}</b>\nЦена: <b>{pack_price} {val_sym}</b> за штуку."
        kb.append([InlineKeyboardButton(text=f"🛒 Купить x1", callback_data=f"sp_buy_{pack_id}_1")])
        kb.append([InlineKeyboardButton(text=f"x3 ({pack_price * 3} {val_sym})", callback_data=f"sp_buy_{pack_id}_3"), InlineKeyboardButton(text=f"x10 ({pack_price * 10} {val_sym})", callback_data=f"sp_buy_{pack_id}_10")])
        kb.append([InlineKeyboardButton(text="🔙 Назад в магазин", callback_data=f"sp_shop_back_{1 if is_fb else 0}")])
    elif mode == "inv":
        user_pack = await fetch_one("SELECT count FROM user_seed_packs WHERE user_id = ? AND pack_id = ?", (active_acc['id'], pack_id))
        amount = user_pack['count'] if user_pack else 0
        text += f"\nУ вас есть: <b>{amount} шт.</b>\n"
        if amount > 0:
            kb.append([InlineKeyboardButton(text="📦 Открыть x1", callback_data=f"sp_open_{pack_id}_1")])
            if amount >= 5:
                kb.append([InlineKeyboardButton(text="📦 Открыть x5", callback_data=f"sp_open_{pack_id}_5")])
            kb.append([InlineKeyboardButton(text="📦 Открыть ВСЕ", callback_data=f"sp_open_{pack_id}_all")])
        kb.append([InlineKeyboardButton(text="🔙 Назад в инвентарь", callback_data=f"sp_inv_back_{1 if is_fb else 0}")])

    try: await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        try: await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except: pass
    await callback.answer()

@dp.callback_query(F.data.startswith("sp_shop_back_"))
async def cb_sp_shop_back(callback: types.CallbackQuery):
    is_fb = int(callback.data.split("_")[3])
    fake_msg = callback.message
    fake_msg.text = BTN_FB_PACKS if is_fb else BTN_SEED_PACKS
    await cmd_seed_packs_menu(fake_msg)
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.startswith("sp_inv_back_"))
async def cb_sp_inv_back(callback: types.CallbackQuery):
    await cb_inv_packs_menu(callback)

@dp.callback_query(F.data.startswith("inv_packs_menu_"))
async def cb_inv_packs_menu(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    is_fb = int(callback.data.split("_")[3])
    
    user_packs = await fetch_all("""
        SELECT usp.count, sp.id as pack_id, sp.title
        FROM user_seed_packs usp JOIN seed_packs sp ON usp.pack_id = sp.id
        WHERE usp.user_id = ? AND usp.count > 0 AND sp.is_football = ?
    """, (active_acc['id'], is_fb))
    
    fb_str = " (CARDBALL)" if is_fb else ""
    text = f"🎒 <b>ИНВЕНТАРЬ СИД-ПАКОВ{fb_str}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nВыберите пак для распаковки:\n\n"
    
    kb = [[InlineKeyboardButton(text="🎒 Карты", callback_data=f"inv_cards_menu_{is_fb}"), InlineKeyboardButton(text="📦 Сид-Паки (Выбрано)", callback_data="ignore")]]
    
    if not user_packs: text += "<i>У вас нет Сид-Паков.</i>"
    else:
        for p in user_packs:
            text += f"📦 <b>{p['title']}</b> — <b>{p['count']} шт.</b>\n"
            kb.append([InlineKeyboardButton(text=f"🔍 Смотреть: {p['title']}", callback_data=f"sp_view_{p['pack_id']}_inv")])
            
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("inv_cards_menu_"))
async def cb_inv_cards_menu(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    is_fb = int(callback.data.split("_")[3])
    text, kb = await get_inventory_text_and_kb(active_acc['id'], 0, is_football=is_fb)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("sp_buy_"))
async def cb_sp_buy_fixed(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer("Ошибка аккаунта", show_alert=True)
    
    parts = callback.data.split("_")
    pack_id = int(parts[2])
    amount = int(parts[3])
    
    pack = await fetch_one("SELECT title, price, is_football FROM seed_packs WHERE id = ?", (pack_id,))
    if not pack: return await callback.answer("Ошибка БД!", show_alert=True)
    
    is_fb = pack['is_football'] == 1
    pack_price = pack['price'] if pack.get('price') is not None else 2000
    total_cost = pack_price * amount
    bal_col = 'football_balls' if is_fb else 'coins'
    
    if active_acc[bal_col] < total_cost:
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)
        
    await execute_db(f"UPDATE accounts SET {bal_col} = {bal_col} - ? WHERE id = ?", (total_cost, active_acc['id']))
    await execute_db("""
        INSERT INTO user_seed_packs (user_id, pack_id, count)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, pack_id) DO UPDATE SET count = count + ?
    """, (active_acc['id'], pack_id, amount, amount))
    
    if not is_fb: await add_quest_progress_new(active_acc['id'], 'q_shop_buy', 1)
    await log_user_action(active_acc['id'], f"Купил Сид-Пак '{pack['title']}' x{amount}")
    
    await callback.answer(f"✅ Куплено {amount} шт. Сид-Паков «{pack['title']}»!", show_alert=True)
    
    new_callback = callback.model_copy(update={"data": f"sp_view_{pack_id}_shop"})
    await cb_sp_view(new_callback)

@dp.callback_query(F.data.startswith("sp_open_"))
async def cb_sp_open_fixed(callback: types.CallbackQuery):
    active_acc = await get_active_account(callback.from_user.id)
    if not active_acc: return await callback.answer()
    
    parts = callback.data.split("_")
    pack_id = int(parts[2])
    amt_str = parts[3]
    
    user_pack = await fetch_one("SELECT count FROM user_seed_packs WHERE user_id = ? AND pack_id = ?", (active_acc['id'], pack_id))
    pack = await fetch_one("SELECT title, photo_id, is_football FROM seed_packs WHERE id = ?", (pack_id,))
    
    if not user_pack or user_pack['count'] <= 0: return await callback.answer("❌ У вас нет этого пака!", show_alert=True)
        
    amount = user_pack['count'] if amt_str == 'all' else int(amt_str)
    if amount > user_pack['count']: return await callback.answer("Ошибка количества", show_alert=True)
    
    is_fb = pack['is_football'] == 1
    await execute_db("UPDATE user_seed_packs SET count = count - ? WHERE user_id = ? AND pack_id = ?", (amount, active_acc['id'], pack_id))
    pack_cards = await fetch_all("SELECT card_id, drop_chance FROM seed_pack_cards WHERE pack_id = ?", (pack_id,))
    
    if not pack_cards:
        await execute_db("UPDATE user_seed_packs SET count = count + ? WHERE user_id = ? AND pack_id = ?", (amount, active_acc['id'], pack_id))
        return await callback.answer("Пак пуст в БД", show_alert=True)
        
    luck_mult, _ = await get_active_events()
    weights = []
    cards_list = []
    for pc in pack_cards:
        w = pc['drop_chance']
        if w < 15.0: w *= luck_mult
        weights.append(w)
        card_info = await fetch_one("SELECT * FROM cards WHERE id = ?", (pc['card_id'],))
        cards_list.append(card_info)
        
    won_cards = []
    for _ in range(amount):
        won_card = random.choices(cards_list, weights=weights, k=1)[0]
        mut = roll_seed_pack_mutation() 
        _, serial, _ = await give_card_to_user(active_acc['id'], won_card['id'], mut, won_card['rarity'], is_football=1 if is_fb else 0)
        
        c_copy = dict(won_card)
        c_copy['mutation'] = mut
        c_copy['serial_number'] = serial
        won_cards.append(c_copy)
        
    if not is_fb: await add_quest_progress_new(active_acc['id'], 'q_open', amount)
    await log_user_action(active_acc['id'], f"Открыл Сид-Пак '{pack['title']}' x{amount}")
    
    text_results = f"🎉 <b>РАСПАКОВКА {amount}x СИД-ПАКА «{pack['title']}» ЗАВЕРШЕНА!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    if amount == 1:
        single = won_cards[0]
        mut_str = "🌈 Радужная " if single['mutation'] == 'Rainbow' else ("⭐ Золотая " if single['mutation'] == 'Gold' else "")
        mult = get_mutation_multiplier(single['mutation'])
        
        caption_text = text_results + f"🃏 {mut_str}{format_card_name(single)}\n💎 {format_rarity_display(single['rarity'])}\n"
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
            mut_str = "🌈 " if c['mutation'] == 'Rainbow' else ("⭐ " if c['mutation'] == 'Gold' else "⚪ ")
            text_results += f"{idx}. {mut_str}{format_card_name(c)}\n"
        text_results += "\n<i>Все карты добавлены в 🎒 Инвентарь.</i>"
        await callback.message.answer(text_results)
        try: await callback.message.delete()
        except: pass
        
    new_callback = callback.model_copy(update={"data": f"sp_view_{pack_id}_inv"})
    await cb_sp_view(new_callback)

# ========================================================================
# КОДЫ-НАГРАДЫ (С ПОЛНЫМ ТРАНЗАКЦИОННЫМ ФИКСАМИ)
# ========================================================================
@dp.message(Command("codereward"))
async def cmd_codereward(message: types.Message, state: FSMContext):
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Зарегистрируйтесь: /register")
    if await check_ban(active_acc['id']): return
    
    await message.answer("🎁 <b>АКТИВАЦИЯ КОДА</b>\nОтправьте ваш 28-значный код (или любой выданный):")
    await state.set_state(UserUseCode.waiting_code)

@dp.message(UserUseCode.waiting_code)
async def process_code_reward(message: types.Message, state: FSMContext):
    code = message.text.strip()
    active_acc = await get_active_account(message.from_user.id)
    if not active_acc: return await message.answer("Ошибка аккаунта.")
    user_id = active_acc['id']
    
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
            
        # Обновляем статус кода, чтобы никто другой не мог использовать
        await db.execute("UPDATE reward_codes SET is_active = 0 WHERE code = ?", (code,))
        
        r_type = code_data['reward_type']
        is_fb = code_data.get('is_football', 0)
        
        if r_type == 'shekels':
            if is_fb:
                await db.execute("UPDATE accounts SET football_balls = football_balls + ? WHERE id = ?", (code_data['amount'], user_id))
                msg_reward = f"✅ Вы успешно активировали код!\nНаграда: <b>{code_data['amount']} ⚽ Мячей</b>!"
            else:
                await db.execute("UPDATE accounts SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (code_data['amount'], code_data['amount'], user_id))
                msg_reward = f"✅ Вы успешно активировали код!\nНаграда: <b>{code_data['amount']} 💰 Шекелей</b>!"
                
        elif r_type == 'card':
            res = await db.execute("SELECT MAX(serial_number) as m FROM inventory WHERE card_id = ? AND mutation = ?", (code_data['item_id'], code_data['mutation']))
            row = await res.fetchone()
            curr_max = row['m'] if (row and row['m'] is not None) else 0
            new_serial = curr_max + 1
            
            await db.execute(
                "INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, ?, 0, ?)", 
                (user_id, code_data['item_id'], code_data['mutation'], new_serial, is_fb)
            )
            
            c_info_c = await db.execute("SELECT name FROM cards WHERE id = ?", (code_data['item_id'],))
            c_info = await c_info_c.fetchone()
            mut_str = "🌈 " if code_data['mutation'] == 'Rainbow' else ("⭐ " if code_data['mutation'] == 'Gold' else "")
            s_str = f" [#{new_serial:04d}]" if new_serial > 0 else ""
            fb_str = " (Футбол)" if is_fb else ""
            msg_reward = f"✅ Вы успешно активировали код!\nНаграда: 🃏 <b>{mut_str}{c_info['name']}{s_str}</b>{fb_str}!"
            
        elif r_type == 'pack':
            await db.execute("""
                INSERT INTO user_seed_packs (user_id, pack_id, count) VALUES (?, ?, 1) 
                ON CONFLICT(user_id, pack_id) DO UPDATE SET count = count + 1
            """, (user_id, code_data['item_id']))
            p_info_c = await db.execute("SELECT title FROM seed_packs WHERE id = ?", (code_data['item_id'],))
            p_info = await p_info_c.fetchone()
            msg_reward = f"✅ Вы успешно активировали код!\nНаграда: 📦 <b>Сид-Пак «{p_info['title']}»</b> (1 шт.)!"
        
        await db.commit()
        await message.answer(msg_reward)
    except Exception as e:
        await db.execute("ROLLBACK")
        logging.error(f"Code redeem error: {e}")
        await message.answer("❌ Произошла ошибка БД при получении награды.")
    finally:
        await db.close()
    await state.clear()

# ========================================================================
# ПАНЕЛЬ АДМИНИСТРАТОРА
# ========================================================================
def get_admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Карты", callback_data="adm_cards"), InlineKeyboardButton(text="👤 Игроки", callback_data="adm_users")],
        [InlineKeyboardButton(text="🎉 Ивенты", callback_data="adm_events"), InlineKeyboardButton(text="👑 Админы", callback_data="adm_admins")],
        [InlineKeyboardButton(text="🎟 Батл-пассы", callback_data="adm_bp_main"), InlineKeyboardButton(text="✍️ Сигнеры", callback_data="adm_signers")],
        [InlineKeyboardButton(text="🏆 Награды за Топ", callback_data="adm_lb_main"), InlineKeyboardButton(text="📦 Сид-Паки", callback_data="adm_sp_main")],
        [InlineKeyboardButton(text="🎁 Коды-Награды", callback_data="adm_codes_main"), InlineKeyboardButton(text="⚽ Лига Награды", callback_data="adm_league_rewards")],
        [InlineKeyboardButton(text="🔨 Настройка Крафтов", callback_data="adm_craft_main"), InlineKeyboardButton(text="📦 Бэкап БД", callback_data="adm_db")]
    ])

@dp.message(F.text == BTN_ADM)
@dp.message(Command("admin"))
async def cmd_admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await message.answer("⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\nВыберите раздел для управления ботом:", reply_markup=get_admin_main_kb())

@dp.callback_query(F.data == "adm_main")
async def cq_adm_main(callback: types.CallbackQuery):
    await callback.message.edit_text("⚙️ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\nВыберите раздел для управления ботом:", reply_markup=get_admin_main_kb())

@dp.callback_query(F.data == "adm_league_rewards")
async def adm_league_rewards_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Четвертьфинал", callback_data="admlig_stage_1")],
        [InlineKeyboardButton(text="🟡 Полуфинал", callback_data="admlig_stage_2")],
        [InlineKeyboardButton(text="🔴 Финал", callback_data="admlig_stage_3")],
        [InlineKeyboardButton(text="🏆 Победитель Кубка", callback_data="admlig_stage_win")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("⚽ <b>Настройка Наград Лиги Cardball</b>\n\nВыбывшие команды получают награду той стадии, на которой вылетели. Победитель турнира получает награду за победу.\nВыберите стадию для настройки:", reply_markup=kb)

@dp.callback_query(F.data.startswith("admlig_stage_"))
async def adm_league_stage_edit(callback: types.CallbackQuery, state: FSMContext):
    stage = callback.data.split("_")[2]
    await state.update_data(league_stage=stage)
    
    rewards = await fetch_all("SELECT * FROM league_rewards_stages WHERE stage_name = ?", (stage,))
    
    s_names = {"1": "Четвертьфинал", "2": "Полуфинал", "3": "Финал", "win": "Победитель Кубка"}
    text = f"🏆 <b>Награды: {s_names[stage]}</b>\n\n"
    if not rewards:
        text += "<i>Пусто.</i>\n"
    else:
        for r in rewards:
            if r['reward_type'] == 'balls': text += f"⚽ {r['amount']} Мячей\n"
            elif r['reward_type'] == 'shekels': text += f"💰 {r['amount']} Шекелей\n"
            elif r['reward_type'] == 'card':
                c = await fetch_one("SELECT name FROM cards WHERE id = ?", (r['card_id'],))
                n = c['name'] if c else "Unknown"
                mut = "🌈" if r['mutation'] == 'Rainbow' else ("⭐" if r['mutation'] == 'Gold' else "")
                text += f"🃏 {mut} {n}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Мячи", callback_data="admlig_add_balls"), InlineKeyboardButton(text="➕ Шекели", callback_data="admlig_add_shekels")],
        [InlineKeyboardButton(text="➕ Карта", callback_data="admlig_add_card"), InlineKeyboardButton(text="🗑 Очистить", callback_data="admlig_clear")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_league_rewards")]
    ])
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: pass
    await callback.answer()

@dp.callback_query(F.data == "admlig_clear")
async def adm_league_clear(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    stage = data['league_stage']
    await execute_db("DELETE FROM league_rewards_stages WHERE stage_name = ?", (stage,))
    await callback.answer("✅ Награды очищены!", show_alert=True)
    fake_call = callback.model_copy(update={"data": f"admlig_stage_{stage}"})
    await adm_league_stage_edit(fake_call, state)

@dp.callback_query(F.data.in_(["admlig_add_balls", "admlig_add_shekels"]))
async def adm_league_add_curr(callback: types.CallbackQuery, state: FSMContext):
    r_type = "balls" if "balls" in callback.data else "shekels"
    await state.update_data(lig_reward_type=r_type)
    await callback.message.answer(f"Введите количество {'Мячей' if r_type=='balls' else 'Шекелей'} для награды:")
    await state.set_state(AdminLeagueRewards.amount)
    await callback.answer()

@dp.message(AdminLeagueRewards.amount)
async def adm_league_save_curr(message: types.Message, state: FSMContext):
    try:
        amt = int(message.text)
        data = await state.get_data()
        stage = data['league_stage']
        r_type = data['lig_reward_type']
        
        await execute_db("INSERT INTO league_rewards_stages (stage_name, reward_type, amount) VALUES (?, ?, ?)", (stage, r_type, amt))
        await message.answer("✅ Валюта добавлена в награды!")
        fake_call = FakeCall(message, f"admlig_stage_{stage}")
        await adm_league_stage_edit(fake_call, state)
    except ValueError:
        await message.answer("❌ Число!")

@dp.callback_query(F.data == "admlig_add_card")
async def adm_league_add_card(callback: types.CallbackQuery, state: FSMContext):
    all_cards = await fetch_all("SELECT id, name, rarity FROM cards ORDER BY id DESC")
    items = [{"id": c['id'], "btn_text": f"{RARITY_EMOJI.get(c['rarity'], '')} {c['name']} (ID:{c['id']})"} for c in all_cards]
    await state.update_data(lig_items=items)
    kb = get_pagination_keyboard(items, 0, "ligc", columns=1, items_per_page=8)
    await callback.message.edit_text("Выберите карту для награды:", reply_markup=kb)
    await state.set_state(AdminLeagueRewards.card_id)

@dp.callback_query(AdminLeagueRewards.card_id, F.data.startswith("ligc_page_"))
async def adm_league_c_paginate(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    data = await state.get_data()
    kb = get_pagination_keyboard(data.get('lig_items', []), page, "ligc", columns=1, items_per_page=8)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminLeagueRewards.card_id, F.data.startswith("ligc_"))
async def adm_league_c_select(callback: types.CallbackQuery, state: FSMContext):
    if "page" in callback.data: return
    card_id = int(callback.data.split("_")[1])
    await state.update_data(lig_card_id=card_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚪ Обычная", callback_data="ligmut_Normal")],
        [InlineKeyboardButton(text="⭐ Золотая", callback_data="ligmut_Gold")],
        [InlineKeyboardButton(text="🌈 Радужная", callback_data="ligmut_Rainbow")]
    ])
    await callback.message.edit_text("Выберите мутацию:", reply_markup=kb)
    await state.set_state(AdminLeagueRewards.mutation)
    await callback.answer()

@dp.callback_query(AdminLeagueRewards.mutation, F.data.startswith("ligmut_"))
async def adm_league_mut_select(callback: types.CallbackQuery, state: FSMContext):
    mutation = callback.data.split("_")[1]
    data = await state.get_data()
    stage = data['league_stage']
    card_id = data['lig_card_id']
    
    await execute_db("INSERT INTO league_rewards_stages (stage_name, reward_type, card_id, mutation) VALUES (?, 'card', ?, ?)", (stage, card_id, mutation))
    
    await callback.answer("✅ Карта добавлена в награды!", show_alert=True)
    fake_call = callback.model_copy(update={"data": f"admlig_stage_{stage}"})
    await adm_league_stage_edit(fake_call, state)

@dp.callback_query(F.data == "adm_sp_main")
async def adm_sp_main_menu(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать Сид-Пак (Обычный)", callback_data="adm_sp_cr_0")],
        [InlineKeyboardButton(text="⚽ Создать Сид-Пак (Футбол)", callback_data="adm_sp_cr_1")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="adm_sp_del_list")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("📦 <b>Управление Сид-Паками</b>\nЗдесь можно создавать паки карт с уникальными шансами.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_sp_cr_"))
async def adm_sp_cr_start(callback: types.CallbackQuery, state: FSMContext):
    is_fb = int(callback.data.split("_")[3])
    await state.update_data(sp_is_fb=is_fb, sp_cards=[])
    await callback.message.answer(f"Создание {'ФУТБОЛЬНОГО' if is_fb else 'ОБЫЧНОГО'} Сид-Пака.\nВведите название (например: Новогодний Пак):")
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
    await message.answer("Введите цену пака (в валюте режима):")
    await state.set_state(CreateSeedPack.price)

@dp.message(CreateSeedPack.price)
async def adm_sp_cr_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        await state.update_data(sp_price=price)
        await adm_sp_cr_menu(message, state)
    except: await message.answer("Число!")

async def adm_sp_cr_menu(msg, state: FSMContext):
    data = await state.get_data()
    text = f"📦 <b>Пак: {data['sp_title']}</b>\nЦена: {data['sp_price']}\nКарты в паке:\n"
    for i, c in enumerate(data['sp_cards']):
        text += f"{i+1}. ID:{c['card_id']} - Вес: {c['chance']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить карту", callback_data="sp_cr_add_c")],
        [InlineKeyboardButton(text="✅ Завершить создание", callback_data="sp_cr_finish")]
    ])
    if isinstance(msg, types.CallbackQuery): await msg.message.answer(text, reply_markup=kb)
    else: await msg.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "sp_cr_add_c")
async def sp_cr_add_c(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_fb = data.get('sp_is_fb', 0)
    query = "SELECT id, name, rarity FROM cards WHERE is_cardball_exclusive = ?"
    cards = await fetch_all(query, (is_fb,))
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
    await callback.message.edit_text("Введите вес выпадения этой карты (например 1.0, 50, 0.1):")
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
    if not data['sp_cards']: return await callback.answer("Пак пуст!", show_alert=True)
    db = await get_db_connection()
    try:
        cur = await db.execute("INSERT INTO seed_packs (title, photo_id, description, price, is_football) VALUES (?, ?, ?, ?, ?)",
                               (data['sp_title'], data.get('sp_photo'), data['sp_desc'], data['sp_price'], data.get('sp_is_fb', 0)))
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
    await callback.answer("✅ Удалено!", show_alert=True)
    await adm_sp_main_menu(callback)

@dp.callback_query(F.data == "adm_codes_main")
async def adm_codes_main(callback: types.CallbackQuery):
    if callback.from_user.id != SUPER_ADMIN_ID: return await callback.answer("Только для Супер-Админа!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Сгенерировать коды (Обычные)", callback_data="adm_code_gen_0")],
        [InlineKeyboardButton(text="⚽ Сгенерировать коды (Футбол)", callback_data="adm_code_gen_1")],
        [InlineKeyboardButton(text="📜 Просмотр кодов", callback_data="adm_code_list_0")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("🎁 <b>Управление Уникальными Кодами-наградами</b>\nКоды с шансом 5% могут выпадать победителям боёв.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_code_gen_"))
async def adm_code_gen_start(callback: types.CallbackQuery, state: FSMContext):
    is_fb = int(callback.data.split("_")[3])
    await state.update_data(gen_code_fb=is_fb)
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
    data = await state.get_data()
    is_fb = data.get('gen_code_fb', 0)
    db = await get_db_connection()
    codes = []
    try:
        await db.execute("BEGIN EXCLUSIVE")
        for _ in range(count):
            code = generate_reward_code()
            codes.append(code)
            await db.execute(
                "INSERT INTO reward_codes (code, reward_type, amount, item_id, mutation, owner_id, is_active, is_football) VALUES (?, ?, ?, ?, ?, 0, 1, ?)",
                (code, r_type, amount, card_id if r_type == 'card' else item_id, mutation, is_fb)
            )
        await db.commit()
        
        codes_str = "\n".join(codes)
        bio = io.BytesIO(codes_str.encode('utf-8'))
        bio.seek(0)
        file = types.BufferedInputFile(bio.read(), filename="reward_codes.txt")
        
        info = f"Сгенерировано {count} кодов.\nРежим: {'ФУТБОЛ' if is_fb else 'ОСНОВА'}\nТип: {r_type}\n"
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
        mod_str = "⚽" if c.get('is_football', 0) == 1 else "🎒"
        items.append({"id": c['code'], "btn_text": f"🔑 {mod_str} {c['code'][:8]}... ({c['reward_type']} | {own_status})"})
        
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
    await callback.message.answer("Введите ID пользователя (Telegram ID) для выдачи прав админа:")
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
    await callback.message.answer("Введите ID администратора (Telegram ID) для снятия прав:")
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
    await callback.message.answer("Введите ID (аккаунта) или @username пользователя для выдачи прав Сигнера:")
    await state.set_state(AdminSigner.add_id)
    await callback.answer()

@dp.message(AdminSigner.add_id)
async def cq_adm_sgn_add_msg(message: types.Message, state: FSMContext):
    val = message.text.strip().lstrip('@')
    target_user = None
    if val.isdigit(): target_user = await fetch_one("SELECT id, telegram_id FROM accounts WHERE id = ?", (int(val),))
    else: target_user = await fetch_one("SELECT id, telegram_id FROM accounts WHERE username = ?", (val,))
        
    if not target_user: await message.answer("❌ Пользователь не найден в базе данных бота.")
    else:
        uid = target_user['telegram_id'] # Signer rights are per Telegram User
        await execute_db("INSERT OR IGNORE INTO authorized_signers (user_id) VALUES (?)", (uid,))
        await message.answer(f"✅ Игрок назначен Сигнером!\n\n<i>Чтобы у него появилась кнопка в меню, ему нужно отправить любое сообщение боту или нажать /start.</i>")
    await state.clear()

@dp.callback_query(F.data == "adm_sgn_del")
async def cq_adm_sgn_del(callback: types.CallbackQuery):
    signers = await fetch_all("""
        SELECT a.user_id 
        FROM authorized_signers a
    """)
    if not signers: return await callback.answer("В списке никого нет.", show_alert=True)
    
    kb = []
    for s in signers:
        kb.append([InlineKeyboardButton(text=f"❌ Telegram ID: {s['user_id']}", callback_data=f"adm_sgn_rm_{s['user_id']}")])
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
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Да")], [KeyboardButton(text="Нет")]], resize_keyboard=True)
        await message.answer("Сделать эту карту ЭКСКЛЮЗИВНОЙ ДЛЯ CARDBALL? (Она не будет падать в обычной Гаче, только в Cardball паках и турнирах):", reply_markup=kb)
        await state.set_state(AddCard.is_cardball_exclusive)
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
        await state.update_data(hp=hp, booster_hp_mult=1.0)
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Да")], [KeyboardButton(text="Нет")]], resize_keyboard=True)
        await message.answer("Сделать эту карту ЭКСКЛЮЗИВНОЙ ДЛЯ CARDBALL? (Она не будет падать в обычной Гаче, только в Cardball паках):", reply_markup=kb)
        await state.set_state(AddCard.is_cardball_exclusive)
    except: await message.answer("❌ Число!")

@dp.message(AddCard.is_cardball_exclusive)
async def add_card_exclusive(message: types.Message, state: FSMContext):
    is_fb_ex = 1 if message.text.lower() == "да" else 0
    data = await state.get_data()
    
    try:
        await message.answer("⏳ Генерирую рамку редкости для карты...", reply_markup=ReplyKeyboardRemove())
        
        new_photo_id = await create_bordered_image(bot, data['photo'], data['rarity'])
        await execute_db(
            "INSERT INTO cards (name, rarity, class_type, damage, hp, drop_chance, photo_id, booster_dmg_mult, booster_hp_mult, is_cardball_exclusive) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data['name'], data['rarity'], data['class_type'], data.get('damage', 0), data.get('hp', 0), data['drop_chance'], new_photo_id, data.get('booster_dmg_mult', 1.0), data.get('booster_hp_mult', 1.0), is_fb_ex)
        )
        
        ex_str = " (Эксклюзив Cardball)" if is_fb_ex else ""
        await log_admin(message.from_user.id, f"Создана карта{ex_str}: {data['name']}")
        await message.answer_photo(new_photo_id, caption=f"✅ <b>Карта {data['name']} создана!{ex_str}</b>", reply_markup=get_main_keyboard(await is_admin(message.from_user.id), await is_signer(message.from_user.id)))
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
            for slot in ['equip1', 'equip2', 'equip3', 'equip4', 'fb_equip1', 'fb_equip2', 'fb_equip3', 'fb_equip4']:
                await execute_db(f"UPDATE accounts SET {slot} = 0 WHERE {slot} = ?", (i_id,))
                
        await log_admin(message.from_user.id, f"DELETED card ID {c_id}")
        await message.answer(f"✅ Карта {c_id} полностью удалена.")
    except: await message.answer("❌ Число.")
    await state.clear()

@dp.callback_query(F.data == "adm_users")
async def cq_adm_users(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Выдать карту", callback_data="adm_usr_givecard"),
         InlineKeyboardButton(text="➖ Забрать карту", callback_data="adm_usr_takecard")],
        [InlineKeyboardButton(text="💰 Выдать шекели/мячи", callback_data="adm_usr_give_coins"),
         InlineKeyboardButton(text="🏆 Выдать кубки", callback_data="adm_usr_give_trophies")],
        [InlineKeyboardButton(text="🔄 Сбросить состояние", callback_data="adm_usr_reset_battle")],
        [InlineKeyboardButton(text="🔨 Бан / Разбан", callback_data="adm_usr_ban")],
        [InlineKeyboardButton(text="📜 Логи игроков", callback_data="adm_usr_logs_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_main")]
    ])
    await callback.message.edit_text("👤 <b>Управление Игроками (Аккаунтами)</b>", reply_markup=kb)

@dp.callback_query(F.data == "adm_usr_logs_menu")
async def adm_usr_logs_menu_start(callback: types.CallbackQuery, state: FSMContext):
    recent_users = await fetch_all("""
        SELECT DISTINCT u.id, u.username, u.nickname 
        FROM user_action_logs l 
        JOIN accounts u ON l.user_id = u.id 
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
    await callback.message.edit_text("📜 <b>Глобальные логи игроков</b>\nВыберите аккаунт из недавних активных или найдите по ID:", reply_markup=kb)
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
    await callback.message.answer("Введите ID игрового аккаунта для просмотра логов:")
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
        
    text = f"📜 <b>Последние 50 действий (Acc ID: {uid}):</b>\n\n"
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
        
    text = f"📜 <b>Последние 50 действий (Acc ID: {uid}):</b>\n\n"
    for l in logs:
        text += f"🕒 {l['timestamp']}\n📝 {l['action']}\n\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="adm_usr_logs_menu")]])
    await message.answer(text[:4000], reply_markup=kb)

@dp.callback_query(F.data == "adm_usr_give_coins")
async def adm_usr_give_coins_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID игрового аккаунта для выдачи:")
    await state.set_state(AdminManage.give_coins_id)
    await callback.answer()

@dp.message(AdminManage.give_coins_id)
async def adm_usr_give_coins_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(target_id=uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Шекели", callback_data="givecurr_coins"), InlineKeyboardButton(text="⚽ Мячи (Футбол)", callback_data="givecurr_balls")]
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
        
        acc = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (uid,))
        if not acc:
            return await message.answer("Аккаунт не найден.")
            
        if c_type == 'coins':
            await execute_db("UPDATE accounts SET coins = coins + ?, total_coins = total_coins + ? WHERE id = ?", (amount, amount, uid))
            msg_alert = f"🎁 Администратор выдал вам <b>{amount} 💰 Шекелей</b>!"
        else:
            await execute_db("UPDATE accounts SET football_balls = football_balls + ? WHERE id = ?", (amount, uid))
            msg_alert = f"⚽ Администратор выдал вам <b>{amount} ⚽ Мячей</b>!"
            
        await log_admin(message.from_user.id, f"Выдал {amount} {c_type} аккаунту {uid}")
        await message.answer(f"✅ Успешно выдано {amount} единиц валюты аккаунту {uid}.")
        try: await bot.send_message(acc['telegram_id'], msg_alert)
        except: pass
    except ValueError:
        await message.answer("❌ Сумма должна быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_usr_give_trophies")
async def adm_usr_give_trophies_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID игрового аккаунта для выдачи кубков:")
    await state.set_state(AdminManage.give_trophies_id)
    await callback.answer()

@dp.message(AdminManage.give_trophies_id)
async def adm_usr_give_trophies_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(target_id=uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Кубки (Обычные)", callback_data="givetroph_main"), InlineKeyboardButton(text="⚽ Кубки (Футбол)", callback_data="givetroph_fb")]
        ])
        await message.answer("Какие кубки выдать?", reply_markup=kb)
    except ValueError:
        await message.answer("❌ ID должен быть числом.")

@dp.callback_query(F.data.startswith("givetroph_"))
async def adm_usr_give_trophies_type(callback: types.CallbackQuery, state: FSMContext):
    t_type = callback.data.split("_")[1]
    await state.update_data(give_trophies_type=t_type)
    await callback.message.answer("Сколько кубков выдать?")
    await state.set_state(AdminManage.give_trophies_amount)
    await callback.answer()

@dp.message(AdminManage.give_trophies_amount)
async def adm_usr_give_trophies_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        uid = data['target_id']
        t_type = data['give_trophies_type']
        
        acc = await fetch_one("SELECT telegram_id FROM accounts WHERE id = ?", (uid,))
        if not acc:
            return await message.answer("Аккаунт не найден.")
            
        col = 'trophies' if t_type == 'main' else 'football_trophies'
        await execute_db(f"UPDATE accounts SET {col} = {col} + ? WHERE id = ?", (amount, uid))
        await log_admin(message.from_user.id, f"Выдал {amount} {col} аккаунту {uid}")
        await message.answer(f"✅ Успешно выдано {amount} кубков аккаунту {uid}.")
        try:
            icon = "🏆" if t_type == 'main' else "⚽"
            msg_alert = f"{icon} Администратор выдал вам <b>{amount} {icon}</b>!"
            await bot.send_message(acc['telegram_id'], msg_alert)
        except: pass
    except ValueError:
        await message.answer("❌ Количество должно быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_usr_reset_battle")
async def adm_usr_reset_battle_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID аккаунта для сброса состояния боя и трейда:")
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
            await message.answer(f"✅ Состояние для аккаунта {uid} успешно сброшено.")
            await log_admin(message.from_user.id, f"Сбросил состояние для {uid}")
        else:
            await message.answer("ℹ️ Аккаунт не находился в активном поиске/трейде.")
            
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_usr_givecard")
async def adm_usr_give(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID аккаунта, которому хотим выдать карту:")
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
        [InlineKeyboardButton(text="🌈 Радужная", callback_data="give_mut_Rainbow")]
    ])
    await callback.message.edit_text("Выберите мутацию для карты:", reply_markup=kb)
    await state.set_state(GiveCard.mutation)
    await callback.answer()

@dp.callback_query(F.data.startswith("give_mut_"), GiveCard.mutation)
async def adm_give_mut_select(callback: types.CallbackQuery, state: FSMContext):
    mutation = callback.data.split("_")[2]
    await state.update_data(give_mutation=mutation)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="В обычный инвентарь", callback_data="givemode_0")],
        [InlineKeyboardButton(text="⚽ В ФУТБОЛЬНЫЙ инвентарь", callback_data="givemode_1")]
    ])
    await callback.message.edit_text("В какой инвентарь выдать карту?", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("givemode_"))
async def adm_give_mode(callback: types.CallbackQuery, state: FSMContext):
    is_fb = int(callback.data.split("_")[1])
    await state.update_data(give_is_fb=is_fb)
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
        is_fb = data.get('give_is_fb', 0)
        
        if serial == 0:
            db = await get_db_connection()
            try:
                res = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND card_id = ? AND mutation = ? AND serial_number = 0 AND signed_by = 0 AND is_football = ?", (user_id, card_id, mutation, is_fb))
                inv_item = await res.fetchone()
                if inv_item:
                    await db.execute("UPDATE inventory SET count = count + 1 WHERE id = ?", (inv_item['id'],))
                else:
                    await db.execute("INSERT INTO inventory (user_id, card_id, count, mutation, serial_number, signed_by, is_football) VALUES (?, ?, 1, ?, 0, 0, ?)", (user_id, card_id, mutation, is_fb))
                await db.commit()
            finally:
                await db.close()
            assigned_serial = 0
        else:
            _, assigned_serial, _ = await give_card_to_user(user_id, card_id, mutation, custom_serial=serial, is_football=is_fb)
            
        s_str = f" [#{assigned_serial:04d}]" if assigned_serial > 0 else ""
        fb_str = " (ФУТБОЛ)" if is_fb else ""
        await log_admin(message.from_user.id, f"GAVE card ID {card_id} (Mut:{mutation}, Serial:{assigned_serial}) to Account {user_id} {fb_str}")
        await message.answer(f"✅ Карта (ID {card_id}) успешно выдана аккаунту {user_id}!{fb_str}\nМутация: {mutation}{s_str}")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число от 0 до 9999.")

@dp.callback_query(F.data == "adm_usr_takecard")
async def adm_usr_take_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID аккаунта, у которого хотим забрать карту (удалить):")
    await state.set_state(TakeCard.user_id)
    await callback.answer()

@dp.message(TakeCard.user_id)
async def adm_usr_take_user(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(take_user_id=uid)
        
        inv = await fetch_all("""
            SELECT i.id as inv_id, c.name, c.rarity, i.count, i.mutation, i.serial_number, i.is_football 
            FROM inventory i JOIN cards c ON i.card_id = c.id 
            WHERE i.user_id = ? AND i.count > 0
        """, (uid,))
        
        if not inv:
            return await message.answer("У этого аккаунта пустой инвентарь или нет карт.")
            
        items = []
        for c in inv:
            mut_str = "⭐" if c['mutation'] == 'Gold' else "🌈" if c['mutation'] == 'Rainbow' else "⚪"
            ser_str = f" [#{c['serial_number']:04d}]" if c['serial_number'] > 0 else ""
            fb_str = "⚽ " if c['is_football'] else ""
            items.append({"id": c['inv_id'], "btn_text": f"{fb_str}{mut_str} {c['name']}{ser_str} (x{c['count']})"})
            
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
        for slot in ['equip1', 'equip2', 'equip3', 'equip4', 'fb_equip1', 'fb_equip2', 'fb_equip3', 'fb_equip4']:
            await execute_db(f"UPDATE accounts SET {slot} = 0 WHERE id = ? AND {slot} = ?", (uid, inv_id))
    else:
        await execute_db("UPDATE inventory SET count = count - ? WHERE id = ?", (amt, inv_id))
        
    await log_admin(message.from_user.id, f"Изъял карту inv_id {inv_id} в кол-ве {amt} у аккаунта {uid}")
    await message.answer(f"✅ Успешно удалено {amt} шт. карты из инвентаря аккаунта {uid}. Счётчик Exists автоматически обновлен.")
    await state.clear()

@dp.callback_query(F.data == "adm_usr_ban")
async def adm_usr_ban_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправь ID аккаунта для смены статуса бана (если забанен - разбанит):")
    await state.set_state(AdminBan.user_id)
    await callback.answer()

@dp.message(AdminBan.user_id)
async def adm_usr_ban_finish(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        usr = await fetch_one("SELECT banned FROM accounts WHERE id = ?", (uid,))
        if not usr: return await message.answer("Аккаунт не найден.")
        new_st = 0 if usr['banned'] == 1 else 1
        await execute_db("UPDATE accounts SET banned = ? WHERE id = ?", (new_st, uid))
        await log_admin(message.from_user.id, f"Set BAN status to {new_st} for Account {uid}")
        await message.answer(f"✅ Статус бана изменен на {new_st}.")
    except:
        pass
    await state.clear()

@dp.callback_query(F.data == "adm_bp_main")
async def adm_bp_main(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать ОБЫЧНЫЙ Батл-пасс", callback_data="adm_bp_create_0")],
        [InlineKeyboardButton(text="⚽ Создать ФУТБОЛЬНЫЙ Батл-пасс", callback_data="adm_bp_create_1")],
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
        fb_str = "⚽ " if bp['is_football'] else ""
        kb.append([InlineKeyboardButton(text=f"🗑 Удалить: {fb_str}{bp['title']}", callback_data=f"adm_bp_del_id_{bp['id']}")])
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

@dp.callback_query(F.data.startswith("adm_bp_create_"))
async def adm_bp_create_start(callback: types.CallbackQuery, state: FSMContext):
    is_fb = int(callback.data.split("_")[3])
    await state.update_data(bp_is_football=is_fb)
    mode_str = "ФУТБОЛЬНОГО" if is_fb else "ОБЫЧНОГО"
    await callback.message.answer(f"🎟 <b>Создание {mode_str} Батл-пасса</b>\nШаг 1: Введите красивое НАЗВАНИЕ сезона (например: <i>Сезон 1: Зимняя Сказка</i>):")
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
    is_fb = data.get('bp_is_football', 0)
    
    val_name = "Мячей" if is_fb else "Шекелей"
    val_sym = "⚽" if is_fb else "💰"
    
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
    is_fb = data.get('bp_is_football', 0)
    
    text = f"✅ <b>Все настроено! Создаю Батл-пасс:</b>\nНазвание: {data['bp_title']}\nУровней: {data['bp_levels_count']}\n\n"
    await callback.message.answer(text)
    
    db = await get_db_connection()
    try:
        cursor = await db.execute("INSERT INTO battle_passes (title, photo_id, created_at, is_football) VALUES (?, ?, ?, ?)", (data['bp_title'], data.get('bp_photo'), time.time(), is_fb))
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
