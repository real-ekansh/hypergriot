#!/usr/bin/env python3
import os
import sys
import asyncio
import sqlite3
import subprocess
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import json

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', 'YOUR_API_HASH_HERE')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))  # Bot owner's user ID

# Ranking system
RANKS = {
    'dev': 4,
    'sudo': 3,
    'support': 2,
    'user': 1
}

RANK_NAMES = {4: 'Dev', 3: 'Sudo', 2: 'Support', 1: 'User'}

class Database:
    def __init__(self, db_path: str = 'bot.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table with ranking system
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                rank INTEGER DEFAULT 1,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Groups table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT,
                chat_type TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, 
                 last_name: str = None, rank: int = 1, added_by: int = None):
        """Add or update user in database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, rank, added_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, rank, added_by))
        
        conn.commit()
        conn.close()
    
    def get_user_rank(self, user_id: int) -> int:
        """Get user's rank"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT rank FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else 1
    
    def set_user_rank(self, user_id: int, rank: int, set_by: int) -> bool:
        """Set user's rank"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # First ensure user exists
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (user_id, rank, added_by) VALUES (?, ?, ?)
            ''', (user_id, rank, set_by))
        else:
            cursor.execute('''
                UPDATE users SET rank = ? WHERE user_id = ?
            ''', (rank, user_id))
        
        conn.commit()
        conn.close()
        return True
    
    def add_group(self, chat_id: int, chat_title: str, chat_type: str):
        """Add group to database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO groups (chat_id, chat_title, chat_type)
            VALUES (?, ?, ?)
        ''', (chat_id, chat_title, chat_type))
        
        conn.commit()
        conn.close()
    
    def log_action(self, chat_id: int, user_id: int, action: str, details: str = ""):
        """Log user actions"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO logs (chat_id, user_id, action, details)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, user_id, action, details))
        
        conn.commit()
        conn.close()
    
    def get_logs(self, limit: int = 10) -> list:
        """Get recent logs"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT l.*, u.username, u.first_name 
            FROM logs l
            LEFT JOIN users u ON l.user_id = u.user_id
            ORDER BY l.timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        result = cursor.fetchall()
        conn.close()
        return result

class TelegramBot:
    def __init__(self):
        self.db = Database()
        self.application = None
        self.telethon_client = None
        
        # Initialize owner
        if OWNER_ID:
            self.db.add_user(OWNER_ID, rank=4)  # Dev rank for owner
    
    def check_rank(self, user_id: int, required_rank: str) -> bool:
        """Check if user has required rank or higher"""
        user_rank = self.db.get_user_rank(user_id)
        return user_rank >= RANKS.get(required_rank, 1)
    
    def is_owner(self, user_id: int) -> bool:
        """Check if user is the owner"""
        return user_id == OWNER_ID
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Add user to database
        self.db.add_user(
            user.id, user.username, user.first_name, user.last_name
        )
        
        # Add group if it's a group chat
        if chat.type in ['group', 'supergroup']:
            self.db.add_group(chat.id, chat.title, chat.type)
        
        # Log action
        self.db.log_action(chat.id, user.id, "start", "User started the bot")
        
        welcome_text = f"""
🤖 **Group Management Bot**

Hello {user.first_name}! I'm a powerful group management bot.

**Your Info:**
• Rank: {RANK_NAMES.get(self.db.get_user_rank(user.id), 'User')}
• User ID: `{user.id}`

**Available Commands:**
• /help - Show all commands
• /ping - Check bot responsiveness
• /rank - Check your rank
• /logs - View recent logs (Dev/Sudo only)

**Admin Commands:**
• /setrank - Set user rank (Owner only)
• /shell - Execute shell commands (Dev only)
• /update - Update bot (Dev only)

Join our support chat for help and updates!
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Help", callback_data="help")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")]
        ])
        
        await update.message.reply_text(
            welcome_text, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_id = update.effective_user.id
        user_rank = self.db.get_user_rank(user_id)
        
        help_text = """
🔧 **Bot Commands**

**Basic Commands:**
• `/start` - Start the bot
• `/help` - Show this help message
• `/ping` - Check bot status
• `/rank` - Check your rank

**Support Commands (Support+):**
"""
        
        if user_rank >= RANKS['support']:
            help_text += """
• `/ban` - Ban a user
• `/kick` - Kick a user
• `/mute` - Mute a user
"""
        
        if user_rank >= RANKS['sudo']:
            help_text += """
**Sudo Commands:**
• `/logs` - View recent logs
• `/stats` - Bot statistics
"""
        
        if user_rank >= RANKS['dev']:
            help_text += """
**Dev Commands:**
• `/shell` - Execute shell commands
• `/update` - Update the bot
• `/restart` - Restart the bot
"""
        
        if self.is_owner(user_id):
            help_text += """
**Owner Commands:**
• `/setrank` - Set user ranks
• `/broadcast` - Broadcast message
"""
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ping command"""
        start_time = datetime.now()
        message = await update.message.reply_text("🏓 Pinging...")
        end_time = datetime.now()
        
        ping_time = (end_time - start_time).total_seconds() * 1000
        
        await message.edit_text(
            f"🏓 **Pong!**\n"
            f"📡 Latency: `{ping_time:.2f}ms`\n"
            f"⏰ Time: `{datetime.now().strftime('%H:%M:%S')}`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def rank_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /rank command"""
        user = update.effective_user
        target_user = None
        
        # Check if replying to someone or mentioning someone
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
        elif context.args:
            try:
                target_id = int(context.args[0])
                # This is simplified - in practice you'd want to get user info
                target_user = type('User', (), {'id': target_id, 'first_name': 'User'})()
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID!")
                return
        else:
            target_user = user
        
        rank_num = self.db.get_user_rank(target_user.id)
        rank_name = RANK_NAMES.get(rank_num, 'User')
        
        await update.message.reply_text(
            f"👤 **User Rank Info**\n\n"
            f"**User:** {target_user.first_name}\n"
            f"**ID:** `{target_user.id}`\n"
            f"**Rank:** {rank_name} ({rank_num}/4)",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def setrank_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setrank command (Owner only)"""
        if not self.is_owner(update.effective_user.id):
            await update.message.reply_text("❌ This command is owner-only!")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "📝 **Usage:** `/setrank <user_id> <rank>`\n\n"
                "**Available ranks:** dev, sudo, support",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        try:
            user_id = int(context.args[0])
            rank_name = context.args[1].lower()
            
            if rank_name not in RANKS:
                await update.message.reply_text("❌ Invalid rank! Use: dev, sudo, support")
                return
            
            rank_num = RANKS[rank_name]
            self.db.set_user_rank(user_id, rank_num, update.effective_user.id)
            
            # Log action
            self.db.log_action(
                update.effective_chat.id,
                update.effective_user.id,
                "setrank",
                f"Set user {user_id} to rank {rank_name}"
            )
            
            await update.message.reply_text(
                f"✅ Successfully set user `{user_id}` to rank **{rank_name.title()}**",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
    
    async def logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /logs command (Sudo+ only)"""
        if not self.check_rank(update.effective_user.id, 'sudo'):
            await update.message.reply_text("❌ You need Sudo rank or higher!")
            return
        
        logs = self.db.get_logs(10)
        
        if not logs:
            await update.message.reply_text("📝 No logs found!")
            return
        
        log_text = "📋 **Recent Logs:**\n\n"
        
        for log in logs:
            timestamp = log[5]
            username = log[6] or "Unknown"
            action = log[3]
            details = log[4]
            
            log_text += f"• **{action}** by {username}\n"
            if details:
                log_text += f"  ↳ {details}\n"
            log_text += f"  🕐 {timestamp}\n\n"
        
        await update.message.reply_text(log_text, parse_mode=ParseMode.MARKDOWN)
    
    async def shell_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /shell command (Dev only)"""
        if not self.check_rank(update.effective_user.id, 'dev'):
            await update.message.reply_text("❌ You need Dev rank!")
            return
        
        if not context.args:
            await update.message.reply_text("📝 **Usage:** `/shell <command>`")
            return
        
        command = ' '.join(context.args)
        
        # Security check - prevent dangerous commands
        dangerous_cmds = ['rm -rf', 'dd if=', 'mkfs', 'format', ':(){ :|:& };:']
        if any(cmd in command.lower() for cmd in dangerous_cmds):
            await update.message.reply_text("❌ Dangerous command blocked!")
            return
        
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            
            output = result.stdout or result.stderr or "No output"
            
            # Limit output length
            if len(output) > 3000:
                output = output[:3000] + "\n... (truncated)"
            
            await update.message.reply_text(
                f"💻 **Shell Command:**\n`{command}`\n\n"
                f"**Output:**\n```\n{output}\n```",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Log action
            self.db.log_action(
                update.effective_chat.id,
                update.effective_user.id,
                "shell",
                f"Executed: {command}"
            )
            
        except subprocess.TimeoutExpired:
            await update.message.reply_text("❌ Command timed out!")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def update_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /update command (Dev only)"""
        if not self.check_rank(update.effective_user.id, 'dev'):
            await update.message.reply_text("❌ You need Dev rank!")
            return
        
        await update.message.reply_text("🔄 Updating bot...")
        
        try:
            # Pull latest changes
            result = subprocess.run(['git', 'pull'], capture_output=True, text=True)
            
            if result.returncode == 0:
                await update.message.reply_text(
                    f"✅ **Update successful!**\n```\n{result.stdout}\n```",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Log action
                self.db.log_action(
                    update.effective_chat.id,
                    update.effective_user.id,
                    "update",
                    "Bot updated successfully"
                )
                
                # Restart bot
                await update.message.reply_text("🔄 Restarting bot...")
                os.execv(sys.executable, ['python'] + sys.argv)
                
            else:
                await update.message.reply_text(
                    f"❌ **Update failed:**\n```\n{result.stderr}\n```",
                    parse_mode=ParseMode.MARKDOWN
                )
                
        except Exception as e:
            await update.message.reply_text(f"❌ Update error: {str(e)}")
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all messages for logging"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Add user to database if not exists
        if not self.db.get_user_rank(user.id):
            self.db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        # Add group if it's a group chat
        if chat.type in ['group', 'supergroup']:
            self.db.add_group(chat.id, chat.title, chat.type)
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Exception while handling an update: {context.error}")
    
    def setup_telethon(self):
        """Setup Telethon client for advanced features"""
        if API_ID and API_HASH:
            self.telethon_client = TelegramClient('bot_session', API_ID, API_HASH)
            
            @self.telethon_client.on(events.NewMessage(pattern='/advanced'))
            async def advanced_handler(event):
                if self.check_rank(event.sender_id, 'dev'):
                    await event.reply("🔧 Advanced features available via Telethon!")
    
    def run(self):
        """Start the bot"""
        # Create application
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("ping", self.ping_command))
        self.application.add_handler(CommandHandler("rank", self.rank_command))
        self.application.add_handler(CommandHandler("setrank", self.setrank_command))
        self.application.add_handler(CommandHandler("logs", self.logs_command))
        self.application.add_handler(CommandHandler("shell", self.shell_command))
        self.application.add_handler(CommandHandler("update", self.update_command))
        
        # Message handler for logging
        self.application.add_handler(
            MessageHandler(filters.ALL & ~filters.COMMAND, self.message_handler)
        )
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
        
        # Setup Telethon
        self.setup_telethon()
        
        logger.info("🤖 Bot started successfully!")
        
        # Start the bot
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # Check if required environment variables are set
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ Please set BOT_TOKEN environment variable!")
        sys.exit(1)
    
    if not OWNER_ID:
        print("❌ Please set OWNER_ID environment variable!")
        sys.exit(1)
    
    # Start the bot
    bot = TelegramBot()
    bot.run()
