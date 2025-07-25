# bot/__init__.py
"""Modular Telegram Bot Package"""

# bot/core/__init__.py
"""Core bot components"""

# bot/core/config.py
import os
from typing import Optional

class Config:
    """Bot configuration management"""
    
    def __init__(self):
        # Bot credentials
        self.BOT_TOKEN = os.getenv('BOT_TOKEN')
        self.API_ID = int(os.getenv('API_ID', '0'))
        self.API_HASH = os.getenv('API_HASH')
        
        # Owner and admin settings
        self.OWNER_ID = int(os.getenv('OWNER_ID', '0'))
        self.DEVS = self._parse_ids(os.getenv('DEV_USERS', ''))
        self.SUDOS = self._parse_ids(os.getenv('SUDO_USERS', ''))
        self.SUPPORTS = self._parse_ids(os.getenv('SUPPORT_USERS', ''))
        
        # Database settings
        self.DATABASE_URL = os.getenv('DATABASE_URL', 'data/bot.db')
        
        # Logging settings
        self.LOG_CHANNEL = os.getenv('LOG_CHANNEL')
        self.DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
        
        # Plugin settings
        self.LOAD_PLUGINS = os.getenv('LOAD_PLUGINS', 'True').lower() == 'true'
        self.DISABLED_PLUGINS = os.getenv('DISABLED_PLUGINS', '').split(',')
        
        # Additional settings
        self.WEBHOOK_URL = os.getenv('WEBHOOK_URL')
        self.PORT = int(os.getenv('PORT', '8443'))
    
    def _parse_ids(self, ids_str: str) -> list:
        """Parse comma-separated user IDs"""
        if not ids_str:
            return []
        return [int(id.strip()) for id in ids_str.split(',') if id.strip().isdigit()]
    
    def validate(self) -> bool:
        """Validate required configuration"""
        if not self.BOT_TOKEN:
            print("❌ BOT_TOKEN is required!")
            return False
        
        if not self.OWNER_ID:
            print("❌ OWNER_ID is required!")
            return False
        
        return True
    
    def get_rank(self, user_id: int) -> str:
        """Get user rank based on configuration"""
        if user_id == self.OWNER_ID:
            return 'owner'
        elif user_id in self.DEVS:
            return 'dev'
        elif user_id in self.SUDOS:
            return 'sudo'
        elif user_id in self.SUPPORTS:
            return 'support'
        else:
            return 'user'

# bot/core/database.py
import sqlite3
import asyncio
import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

class Database:
    """Database management class"""
    
    def __init__(self, db_path: str = 'data/bot.db'):
        self.db_path = db_path
        asyncio.create_task(self.init_db())
    
    async def init_db(self):
        """Initialize database with all required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Users table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    rank TEXT DEFAULT 'user',
                    is_banned INTEGER DEFAULT 0,
                    ban_reason TEXT,
                    added_by INTEGER,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Groups/Chats table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    chat_title TEXT,
                    chat_type TEXT,
                    is_active INTEGER DEFAULT 1,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    settings TEXT DEFAULT '{}'
                )
            ''')
            
            # Logs table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    action TEXT,
                    target_id INTEGER,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Global bans table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS global_bans (
                    user_id INTEGER PRIMARY KEY,
                    banned_by INTEGER,
                    reason TEXT,
                    ban_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Warnings table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    warned_by INTEGER,
                    reason TEXT,
                    warn_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Notes table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    note_name TEXT,
                    note_content TEXT,
                    note_type TEXT DEFAULT 'text',
                    created_by INTEGER,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Filters table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS filters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    keyword TEXT,
                    response TEXT,
                    filter_type TEXT DEFAULT 'text',
                    created_by INTEGER,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
    
    async def add_user(self, user_id: int, username: str = None, 
                      first_name: str = None, last_name: str = None,
                      rank: str = 'user', added_by: int = None):
        """Add or update user"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, rank, added_by, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, rank, added_by, datetime.now()))
            await db.commit()
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
        return None
    
    async def add_chat(self, chat_id: int, chat_title: str, chat_type: str):
        """Add or update chat"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO chats (chat_id, chat_title, chat_type)
                VALUES (?, ?, ?)
            ''', (chat_id, chat_title, chat_type))
            await db.commit()
    
    async def log_action(self, chat_id: int, user_id: int, action: str, 
                        target_id: int = None, details: str = ""):
        """Log user action"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO logs (chat_id, user_id, action, target_id, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, user_id, action, target_id, details))
            await db.commit()
    
    async def get_logs(self, limit: int = 10, chat_id: int = None) -> List[Dict]:
        """Get recent logs"""
        async with aiosqlite.connect(self.db_path) as db:
            query = '''
                SELECT l.*, u.username, u.first_name 
                FROM logs l
                LEFT JOIN users u ON l.user_id = u.user_id
            '''
            params = []
            
            if chat_id:
                query += ' WHERE l.chat_id = ?'
                params.append(chat_id)
            
            query += ' ORDER BY l.timestamp DESC LIMIT ?'
            params.append(limit)
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
    
    async def add_warning(self, chat_id: int, user_id: int, warned_by: int, reason: str):
        """Add warning to user"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO warnings (chat_id, user_id, warned_by, reason)
                VALUES (?, ?, ?, ?)
            ''', (chat_id, user_id, warned_by, reason))
            await db.commit()
    
    async def get_warnings(self, chat_id: int, user_id: int) -> int:
        """Get warning count for user in chat"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT COUNT(*) FROM warnings WHERE chat_id = ? AND user_id = ?
            ''', (chat_id, user_id)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

# bot/core/bot.py
import asyncio
import logging
import importlib
import pkgutil
from pathlib import Path
from telegram import Update
from telegram.ext import Application, ContextTypes
from telethon import TelegramClient

from .config import Config
from .database import Database
from .plugin_manager import PluginManager

logger = logging.getLogger(__name__)

class TelegramBot:
    """Main bot class with plugin support"""
    
    def __init__(self, config: Config, database: Database):
        self.config = config
        self.db = database
        self.application = None
        self.telethon_client = None
        self.plugin_manager = PluginManager(self)
        
        # Initialize owner in database
        if config.OWNER_ID:
            asyncio.create_task(self.db.add_user(
                config.OWNER_ID, rank='owner'
            ))
    
    def get_rank(self, user_id: int) -> str:
        """Get user rank"""
        return self.config.get_rank(user_id)
    
    def check_rank(self, user_id: int, required_rank: str) -> bool:
        """Check if user has required rank or higher"""
        rank_hierarchy = {
            'user': 1, 'support': 2, 'sudo': 3, 'dev': 4, 'owner': 5
        }
        
        user_rank = self.get_rank(user_id)
        return rank_hierarchy.get(user_rank, 1) >= rank_hierarchy.get(required_rank, 1)
    
    def is_owner(self, user_id: int) -> bool:
        """Check if user is owner"""
        return user_id == self.config.OWNER_ID
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Global error handler"""
        logger.error(f"Exception while handling update: {context.error}")
        
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ An error occurred while processing your request."
                )
            except Exception:
                pass
    
    def setup_telethon(self):
        """Setup Telethon client"""
        if self.config.API_ID and self.config.API_HASH:
            self.telethon_client = TelegramClient(
                'data/bot_session', self.config.API_ID, self.config.API_HASH
            )
            logger.info("✅ Telethon client initialized")
    
    def run(self):
        """Start the bot"""
        # Create application
        self.application = Application.builder().token(self.config.BOT_TOKEN).build()
        
        # Setup Telethon
        self.setup_telethon()
        
        # Load plugins
        if self.config.LOAD_PLUGINS:
            self.plugin_manager.load_all_plugins()
        
        # Add global error handler
        self.application.add_error_handler(self.error_handler)
        
        logger.info("🚀 Bot started successfully!")
        
        # Start polling
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

# bot/core/plugin_manager.py
import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

class PluginManager:
    """Plugin management system"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.loaded_plugins: Dict[str, object] = {}
        self.plugins_dir = Path("bot/plugins")
    
    def load_plugin(self, plugin_name: str) -> bool:
        """Load a single plugin"""
        try:
            # Skip disabled plugins
            if plugin_name in self.bot.config.DISABLED_PLUGINS:
                logger.info(f"⏭️ Plugin {plugin_name} is disabled, skipping...")
                return False
            
            plugin_path = self.plugins_dir / f"{plugin_name}.py"
            
            if not plugin_path.exists():
                logger.error(f"❌ Plugin file {plugin_path} not found!")
                return False
            
            # Import plugin module
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Initialize plugin
            if hasattr(module, 'setup'):
                module.setup(self.bot)
                self.loaded_plugins[plugin_name] = module
                logger.info(f"✅ Plugin {plugin_name} loaded successfully")
                return True
            else:
                logger.error(f"❌ Plugin {plugin_name} missing setup() function")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to load plugin {plugin_name}: {e}")
            return False
    
    def load_all_plugins(self):
        """Load all plugins from plugins directory"""
        if not self.plugins_dir.exists():
            logger.warning("⚠️ Plugins directory not found, creating...")
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            return
        
        plugin_files = list(self.plugins_dir.glob("*.py"))
        
        if not plugin_files:
            logger.info("ℹ️ No plugins found in plugins directory")
            return
        
        loaded_count = 0
        for plugin_file in plugin_files:
            if plugin_file.name.startswith('_'):
                continue  # Skip private files
            
            plugin_name = plugin_file.stem
            if self.load_plugin(plugin_name):
                loaded_count += 1
        
        logger.info(f"📦 Loaded {loaded_count}/{len(plugin_files)} plugins")
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin"""
        if plugin_name in self.loaded_plugins:
            # Unload first if it has cleanup function
            plugin = self.loaded_plugins[plugin_name]
            if hasattr(plugin, 'cleanup'):
                try:
                    plugin.cleanup(self.bot)
                except Exception as e:
                    logger.error(f"Error during plugin cleanup: {e}")
            
            del self.loaded_plugins[plugin_name]
        
        return self.load_plugin(plugin_name)
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin"""
        if plugin_name not in self.loaded_plugins:
            return False
        
        plugin = self.loaded_plugins[plugin_name]
        if hasattr(plugin, 'cleanup'):
            try:
                plugin.cleanup(self.bot)
            except Exception as e:
                logger.error(f"Error during plugin cleanup: {e}")
        
        del self.loaded_plugins[plugin_name]
        logger.info(f"🗑️ Plugin {plugin_name} unloaded")
        return True
    
    def get_loaded_plugins(self) -> List[str]:
        """Get list of loaded plugins"""
        return list(self.loaded_plugins.keys())
