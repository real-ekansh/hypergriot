import os
import sys
import json
import time
import asyncio
import logging
import importlib
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import telebot
from telebot import types
from telebot.async_telebot import AsyncTeleBot
import pymongo
from pymongo import MongoClient

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
MONGODB_URL = os.getenv('MONGODB_URL')
USE_MONGODB = os.getenv('USE_MONGODB', 'false').lower() == 'true'

# Bot initialization
bot = AsyncTeleBot(BOT_TOKEN)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# User ranks
RANKS = {
    'owner': 5,
    'dev': 4,
    'admin': 3,
    'sudo': 2,
    'user': 1
}

class Database:
    def __init__(self):
        self.use_mongodb = USE_MONGODB and MONGODB_URL
        if self.use_mongodb:
            self.client = MongoClient(MONGODB_URL)
            self.db = self.client.hypergriot
            self.users = self.db.users
            self.groups = self.db.groups
        else:
            self.init_sqlite()
    
    def init_sqlite(self):
        self.conn = sqlite3.connect('hypergriot.db', check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                rank TEXT DEFAULT 'user',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                title TEXT,
                settings TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def get_user_rank(self, user_id: int) -> str:
        if user_id == OWNER_ID:
            return 'owner'
        
        if self.use_mongodb:
            user = self.users.find_one({'user_id': user_id})
            return user.get('rank', 'user') if user else 'user'
        else:
            cursor = self.conn.execute('SELECT rank FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 'user'
    
    def set_user_rank(self, user_id: int, rank: str, username: str = None, first_name: str = None):
        if self.use_mongodb:
            self.users.update_one(
                {'user_id': user_id},
                {'$set': {'rank': rank, 'username': username, 'first_name': first_name}},
                upsert=True
            )
        else:
            self.conn.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, rank)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, rank))
            self.conn.commit()
    
    def get_user_info(self, user_id: int) -> Optional[Dict]:
        if self.use_mongodb:
            return self.users.find_one({'user_id': user_id})
        else:
            cursor = self.conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            if result:
                return {
                    'user_id': result[0],
                    'username': result[1],
                    'first_name': result[2],
                    'rank': result[3],
                    'joined_at': result[4]
                }
            return None

db = Database()

def parse_time_duration(duration: str) -> int:
    """Parse time duration like 1d, 2h, 30m, 1w to seconds"""
    if not duration:
        return 0
    
    multipliers = {
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }
    
    try:
        if duration[-1] in multipliers:
            number = int(duration[:-1])
            return number * multipliers[duration[-1]]
    except (ValueError, IndexError):
        pass
    
    return 0

def check_rank(required_rank: str):
    """Decorator to check user rank"""
    def decorator(func):
        async def wrapper(message):
            user_rank = db.get_user_rank(message.from_user.id)
            if RANKS.get(user_rank, 0) >= RANKS.get(required_rank, 0):
                return await func(message)
            else:
                await bot.reply_to(message, "You don't have permission to use this command.")
        return wrapper
    return decorator

async def get_user_from_message(message, text: str):
    """Extract user from message (reply, username, or user_id)"""
    if message.reply_to_message:
        return message.reply_to_message.from_user
    
    parts = text.split()
    if len(parts) < 2:
        return None
    
    identifier = parts[1]
    
    # If it's a user ID
    if identifier.isdigit():
        try:
            user_id = int(identifier)
            chat_member = await bot.get_chat_member(message.chat.id, user_id)
            return chat_member.user
        except:
            return None
    
    # If it's a username
    if identifier.startswith('@'):
        try:
            username = identifier[1:]
            # Try to get user info from database first
            # In a real scenario, you'd need to maintain a username-to-id mapping
            return None  # Would need additional implementation
        except:
            return None
    
    return None

# Module loading system
def load_modules():
    """Load modules from modules directory"""
    modules_dir = 'modules'
    if not os.path.exists(modules_dir):
        os.makedirs(modules_dir)
        return
    
    for filename in os.listdir(modules_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3]
            try:
                spec = importlib.util.spec_from_file_location(
                    module_name, 
                    os.path.join(modules_dir, filename)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Register module handlers if they exist
                if hasattr(module, 'register_handlers'):
                    module.register_handlers(bot)
                
                logger.info(f"Loaded module: {module_name}")
            except Exception as e:
                logger.error(f"Failed to load module {module_name}: {e}")

# Basic commands
@bot.message_handler(commands=['start'])
async def start_command(message):
    welcome_text = f"""
Welcome to HyperGriot Bot!

I'm a powerful group management bot with advanced features.

Use /help to see available commands.
Bot developed for efficient group management.
    """
    await bot.reply_to(message, welcome_text.strip())

@bot.message_handler(commands=['help'])
async def help_command(message):
    text = message.text.split()
    
    if len(text) > 1:
        # Help for specific command
        cmd = text[1].lower()
        help_texts = {
            'start': '/start - Start the bot and see welcome message',
            'help': '/help [command] - Show help or help for specific command',
            'ping': '/ping - Check if bot is responsive',
            'status': '/status - Show bot status (sudo+)',
            'stats': '/stats - Show bot statistics (sudo+)',
            'shell': '/shell <command> - Execute shell command (owner only)',
            'setrank': '/setrank <user> <rank> - Set user rank (owner only)',
            'ban': '/ban [user] [duration] - Ban user from group',
            'unban': '/unban [user] - Unban user from group',
            'mute': '/mute [user] [duration] - Mute user in group',
            'unmute': '/unmute [user] - Unmute user in group',
            'kick': '/kick [user] - Kick user from group',
            'promote': '/promote [user] - Promote user to admin',
            'demote': '/demote [user] - Demote user from admin',
            'pin': '/pin [reply] - Pin message',
            'unpin': '/unpin - Unpin message',
            'purge': '/purge [number] - Delete messages',
            'id': '/id - Get user ID',
            'info': '/info [user] - Get user information'
        }
        
        if cmd in help_texts:
            await bot.reply_to(message, help_texts[cmd])
        else:
            await bot.reply_to(message, f"No help available for command: {cmd}")
    else:
        # General help
        user_rank = db.get_user_rank(message.from_user.id)
        rank_level = RANKS.get(user_rank, 0)
        
        help_text = """
Available Commands:

Basic Commands:
/start - Start the bot
/help [command] - Show help
/ping - Check bot status
/id - Get your user ID
/info [user] - Get user information
        """
        
        if rank_level >= RANKS['sudo']:
            help_text += """
Sudo Commands:
/status - Bot status
/stats - Bot statistics
            """
        
        if rank_level >= RANKS['admin']:
            help_text += """
Admin Commands:
/ban [user] [time] - Ban user
/unban [user] - Unban user
/mute [user] [time] - Mute user
/unmute [user] - Unmute user
/kick [user] - Kick user
/promote [user] - Promote user
/demote [user] - Demote user
/pin - Pin message (reply)
/unpin - Unpin message
/purge [number] - Delete messages
            """
        
        if rank_level >= RANKS['dev']:
            help_text += """
Dev Commands:
All admin commands available
            """
        
        if rank_level >= RANKS['owner']:
            help_text += """
Owner Commands:
/shell <command> - Execute shell
/setrank <user> <rank> - Set user rank
            """
        
        await bot.reply_to(message, help_text.strip())

@bot.message_handler(commands=['ping'])
async def ping_command(message):
    start_time = time.time()
    sent_message = await bot.reply_to(message, "Pinging...")
    end_time = time.time()
    
    ping_time = round((end_time - start_time) * 1000)
    await bot.edit_message_text(
        f"Pong! {ping_time}ms",
        message.chat.id,
        sent_message.message_id
    )

@bot.message_handler(commands=['status'])
@check_rank('sudo')
async def status_command(message):
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    
    status_text = f"""
Bot Status:

Uptime: {hours}h {minutes}m {seconds}s
Database: {'MongoDB' if db.use_mongodb else 'SQLite'}
Version: 1.0.0
Status: Online
    """
    await bot.reply_to(message, status_text.strip())

@bot.message_handler(commands=['stats'])
@check_rank('sudo')
async def stats_command(message):
    # Basic stats - can be expanded
    stats_text = """
Bot Statistics:

Groups: Active
Users: Tracked in database
Commands: All systems operational
Database: Connected
    """
    await bot.reply_to(message, stats_text.strip())

@bot.message_handler(commands=['shell', 'sh'])
@check_rank('owner')
async def shell_command(message):
    if len(message.text.split()) < 2:
        await bot.reply_to(message, "Usage: /shell <command>")
        return
    
    command = ' '.join(message.text.split()[1:])
    
    try:
        import subprocess
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout or result.stderr or "Command executed successfully"
        if len(output) > 4000:
            output = output[:4000] + "... (truncated)"
        
        await bot.reply_to(message, f"```\n{output}\n```", parse_mode='Markdown')
    except Exception as e:
        await bot.reply_to(message, f"Error executing command: {str(e)}")

@bot.message_handler(commands=['setrank'])
@check_rank('owner')
async def setrank_command(message):
    parts = message.text.split()
    if len(parts) < 3:
        await bot.reply_to(message, "Usage: /setrank <user_id/username> <rank>")
        return
    
    user_identifier = parts[1]
    new_rank = parts[2].lower()
    
    if new_rank not in RANKS:
        available_ranks = ', '.join(RANKS.keys())
        await bot.reply_to(message, f"Invalid rank. Available ranks: {available_ranks}")
        return
    
    try:
        if user_identifier.isdigit():
            user_id = int(user_identifier)
        else:
            await bot.reply_to(message, "Please provide user ID for now")
            return
        
        db.set_user_rank(user_id, new_rank)
        await bot.reply_to(message, f"User {user_id} rank set to {new_rank}")
    except Exception as e:
        await bot.reply_to(message, f"Error setting rank: {str(e)}")

@bot.message_handler(commands=['id'])
async def id_command(message):
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        await bot.reply_to(message, f"User ID: {user.id}")
    else:
        await bot.reply_to(message, f"Your ID: {message.from_user.id}")

@bot.message_handler(commands=['info'])
async def info_command(message):
    target_user = None
    
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    else:
        parts = message.text.split()
        if len(parts) > 1 and parts[1].isdigit():
            try:
                user_id = int(parts[1])
                chat_member = await bot.get_chat_member(message.chat.id, user_id)
                target_user = chat_member.user
            except:
                await bot.reply_to(message, "User not found")
                return
        else:
            target_user = message.from_user
    
    if target_user:
        user_info = db.get_user_info(target_user.id)
        rank = db.get_user_rank(target_user.id)
        
        info_text = f"""
User Information:

ID: {target_user.id}
Username: @{target_user.username or 'None'}
First Name: {target_user.first_name or 'None'}
Last Name: {target_user.last_name or 'None'}
Rank: {rank}
        """
        
        if user_info and 'joined_at' in user_info:
            info_text += f"Joined: {user_info['joined_at']}"
        
        await bot.reply_to(message, info_text.strip())

# Admin commands
@bot.message_handler(commands=['ban', 'tban'])
@check_rank('admin')
async def ban_command(message):
    if message.chat.type not in ['group', 'supergroup']:
        await bot.reply_to(message, "This command can only be used in groups")
        return
    
    target_user = await get_user_from_message(message, message.text)
    if not target_user:
        await bot.reply_to(message, "Please reply to a user or provide user ID")
        return
    
    # Check if duration is specified
    parts = message.text.split()
    duration_seconds = 0
    ban_until = None
    
    if len(parts) > 2 or (len(parts) > 1 and not message.reply_to_message):
        duration_str = parts[-1]
        duration_seconds = parse_time_duration(duration_str)
        if duration_seconds > 0:
            ban_until = int(time.time()) + duration_seconds
    
    try:
        await bot.ban_chat_member(
            message.chat.id, 
            target_user.id,
            until_date=ban_until
        )
        
        duration_text = f" for {parts[-1]}" if duration_seconds > 0 else " permanently"
        await bot.reply_to(message, f"User {target_user.first_name} banned{duration_text}")
    except Exception as e:
        await bot.reply_to(message, f"Failed to ban user: {str(e)}")

@bot.message_handler(commands=['unban'])
@check_rank('admin')
async def unban_command(message):
    if message.chat.type not in ['group', 'supergroup']:
        await bot.reply_to(message, "This command can only be used in groups")
        return
    
    target_user = await get_user_from_message(message, message.text)
    if not target_user:
        await bot.reply_to(message, "Please reply to a user or provide user ID")
        return
    
    try:
        await bot.unban_chat_member(message.chat.id, target_user.id)
        await bot.reply_to(message, f"User {target_user.first_name} unbanned")
    except Exception as e:
        await bot.reply_to(message, f"Failed to unban user: {str(e)}")

@bot.message_handler(commands=['kick', 'skick'])
@check_rank('admin')
async def kick_command(message):
    if message.chat.type not in ['group', 'supergroup']:
        await bot.reply_to(message, "This command can only be used in groups")
        return
    
    target_user = await get_user_from_message(message, message.text)
    if not target_user:
        await bot.reply_to(message, "Please reply to a user or provide user ID")
        return
    
    try:
        await bot.ban_chat_member(message.chat.id, target_user.id)
        await bot.unban_chat_member(message.chat.id, target_user.id)
        
        if not message.text.startswith('/s'):
            await bot.reply_to(message, f"User {target_user.first_name} kicked")
    except Exception as e:
        await bot.reply_to(message, f"Failed to kick user: {str(e)}")

# Add more admin commands...
@bot.message_handler(commands=['mute', 'tmute', 'smute'])
@check_rank('admin')
async def mute_command(message):
    if message.chat.type not in ['group', 'supergroup']:
        await bot.reply_to(message, "This command can only be used in groups")
        return
    
    target_user = await get_user_from_message(message, message.text)
    if not target_user:
        await bot.reply_to(message, "Please reply to a user or provide user ID")
        return
    
    # Parse duration
    parts = message.text.split()
    duration_seconds = 0
    mute_until = None
    
    if len(parts) > 2 or (len(parts) > 1 and not message.reply_to_message):
        duration_str = parts[-1]
        duration_seconds = parse_time_duration(duration_str)
        if duration_seconds > 0:
            mute_until = int(time.time()) + duration_seconds
    
    try:
        permissions = types.ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        
        await bot.restrict_chat_member(
            message.chat.id,
            target_user.id,
            permissions=permissions,
            until_date=mute_until
        )
        
        if not message.text.startswith('/s'):
            duration_text = f" for {parts[-1]}" if duration_seconds > 0 else " permanently"
            await bot.reply_to(message, f"User {target_user.first_name} muted{duration_text}")
    except Exception as e:
        await bot.reply_to(message, f"Failed to mute user: {str(e)}")

@bot.message_handler(commands=['unmute'])
@check_rank('admin')
async def unmute_command(message):
    if message.chat.type not in ['group', 'supergroup']:
        await bot.reply_to(message, "This command can only be used in groups")
        return
    
    target_user = await get_user_from_message(message, message.text)
    if not target_user:
        await bot.reply_to(message, "Please reply to a user or provide user ID")
        return
    
    try:
        permissions = types.ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )
        
        await bot.restrict_chat_member(
            message.chat.id,
            target_user.id,
            permissions=permissions
        )
        
        await bot.reply_to(message, f"User {target_user.first_name} unmuted")
    except Exception as e:
        await bot.reply_to(message, f"Failed to unmute user: {str(e)}")

# Global variables
start_time = time.time()

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("BOT_TOKEN environment variable is required!")
        sys.exit(1)
    
    if not OWNER_ID:
        print("OWNER_ID environment variable is required!")
        sys.exit(1)
    
    # Load modules
    load_modules()
    
    print("HyperGriot Bot starting...")
    print(f"Database: {'MongoDB' if db.use_mongodb else 'SQLite'}")
    
    # Start bot
    asyncio.run(bot.polling(non_stop=True))
