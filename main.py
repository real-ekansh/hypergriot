# main.py
import os
import sys
import logging
import asyncio
import importlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configuration
class Config:
    # Bot credentials
    API_ID = int(os.getenv('API_ID', '12345'))
    API_HASH = os.getenv('API_HASH', 'your_api_hash')
    BOT_TOKEN = os.getenv('BOT_TOKEN', 'your_bot_token')
    
    # Admin configuration
    DEVS = list(map(int, os.getenv('DEVS', '').split(','))) if os.getenv('DEVS') else []
    SUDOS = list(map(int, os.getenv('SUDOS', '').split(','))) if os.getenv('SUDOS') else []
    SUPPORTS = list(map(int, os.getenv('SUPPORTS', '').split(','))) if os.getenv('SUPPORTS') else []
    
    # Logging
    LOG_CHAT = int(os.getenv('LOG_CHAT', '0'))  # Private logging chat ID
    
    # Database (you can extend this)
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///bot.db')

# Permission System
class PermissionLevel:
    DEV = 4
    SUDO = 3
    SUPPORT = 2
    USER = 1
    BANNED = 0

class PermissionManager:
    @staticmethod
    def get_permission_level(user_id: int) -> int:
        if user_id in Config.DEVS:
            return PermissionLevel.DEV
        elif user_id in Config.SUDOS:
            return PermissionLevel.SUDO
        elif user_id in Config.SUPPORTS:
            return PermissionLevel.SUPPORT
        else:
            return PermissionLevel.USER
    
    @staticmethod
    def has_permission(user_id: int, required_level: int) -> bool:
        return PermissionManager.get_permission_level(user_id) >= required_level
    
    @staticmethod
    def get_permission_name(level: int) -> str:
        names = {
            PermissionLevel.DEV: "Developer",
            PermissionLevel.SUDO: "Sudo",
            PermissionLevel.SUPPORT: "Support",
            PermissionLevel.USER: "User",
            PermissionLevel.BANNED: "Banned"
        }
        return names.get(level, "Unknown")

# Logging Setup
class BotLogger:
    def __init__(self):
        self.setup_logging()
        self.logger = logging.getLogger('TelegramBot')
        
    def setup_logging(self):
        # Create logs directory
        Path('logs').mkdir(exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        # Separate error logging
        error_handler = logging.FileHandler(f'logs/errors_{datetime.now().strftime("%Y%m%d")}.log')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        
        error_logger = logging.getLogger('errors')
        error_logger.addHandler(error_handler)
    
    def info(self, message: str):
        self.logger.info(message)
    
    def error(self, message: str, exc_info=None):
        self.logger.error(message, exc_info=exc_info)
        # Also log to error file
        logging.getLogger('errors').error(message, exc_info=exc_info)
    
    def warning(self, message: str):
        self.logger.warning(message)

# Module System
class ModuleManager:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.modules: Dict[str, object] = {}
        self.module_commands: Dict[str, str] = {}
        
    def load_modules(self, modules_dir: str = "modules"):
        """Load all modules from the modules directory"""
        if not os.path.exists(modules_dir):
            os.makedirs(modules_dir)
            logger.info(f"Created modules directory: {modules_dir}")
            return
        
        module_files = [f[:-3] for f in os.listdir(modules_dir) 
                       if f.endswith('.py') and not f.startswith('_')]
        
        for module_name in module_files:
            try:
                self.load_module(module_name, modules_dir)
            except Exception as e:
                logger.error(f"Failed to load module {module_name}: {e}", exc_info=True)
    
    def load_module(self, module_name: str, modules_dir: str = "modules"):
        """Load a specific module"""
        try:
            # Import the module
            spec = importlib.util.spec_from_file_location(
                module_name, f"{modules_dir}/{module_name}.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Initialize module if it has setup function
            if hasattr(module, 'setup'):
                module.setup(self.bot)
            
            self.modules[module_name] = module
            logger.info(f"Successfully loaded module: {module_name}")
            
            # Register commands if module has them
            if hasattr(module, 'COMMANDS'):
                for cmd in module.COMMANDS:
                    self.module_commands[cmd] = module_name
            
        except Exception as e:
            logger.error(f"Error loading module {module_name}: {e}", exc_info=True)
            raise
    
    def unload_module(self, module_name: str):
        """Unload a specific module"""
        if module_name in self.modules:
            module = self.modules[module_name]
            
            # Call cleanup if available
            if hasattr(module, 'cleanup'):
                module.cleanup()
            
            # Remove commands
            commands_to_remove = [cmd for cmd, mod in self.module_commands.items() 
                                if mod == module_name]
            for cmd in commands_to_remove:
                del self.module_commands[cmd]
            
            del self.modules[module_name]
            logger.info(f"Unloaded module: {module_name}")
    
    def reload_module(self, module_name: str):
        """Reload a specific module"""
        if module_name in self.modules:
            self.unload_module(module_name)
        self.load_module(module_name)

# Main Bot Class
class TelegramGroupBot:
    def __init__(self):
        self.telethon_client = TelegramClient('bot_session', Config.API_ID, Config.API_HASH)
        self.ptb_app = Application.builder().token(Config.BOT_TOKEN).build()
        self.module_manager = ModuleManager(self)
        
        # Setup handlers
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup basic command handlers"""
        # PTB handlers
        self.ptb_app.add_handler(CommandHandler("start", self.start_command))
        self.ptb_app.add_handler(CommandHandler("help", self.help_command))
        self.ptb_app.add_handler(CommandHandler("ping", self.ping_command))
        
        # Telethon handlers
        self.telethon_client.add_event_handler(self.on_new_message, events.NewMessage)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        user_permission = PermissionManager.get_permission_level(user.id)
        permission_name = PermissionManager.get_permission_name(user_permission)
        
        await self.log_private(f"User {user.full_name} ({user.id}) started the bot. Permission: {permission_name}")
        
        start_text = f"""
🤖 **Welcome to Group Management Bot!**

Hello {user.first_name}! I'm a powerful group management bot.

**Your Permission Level:** {permission_name}

**Available Commands:**
• /help - Show help message
• /ping - Check bot response time

For more commands, use /help or contact administrators.
        """
        
        await update.message.reply_text(start_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_permission = PermissionManager.get_permission_level(update.effective_user.id)
        
        help_text = """
🆘 **Bot Help**

**Basic Commands:**
• /start - Start the bot
• /ping - Check bot status
• /help - Show this help message

**Permission Levels:**
• **Developer** - Full access to all features
• **Sudo** - Administrative privileges
• **Support** - Moderate privileges
• **User** - Basic commands only

**Modules:** {}
        """.format(", ".join(self.module_manager.modules.keys()) or "None loaded")
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ping command"""
        start_time = datetime.now()
        message = await update.message.reply_text("🏓 Pinging...")
        
        end_time = datetime.now()
        ping_time = (end_time - start_time).total_seconds() * 1000
        
        await message.edit_text(f"🏓 **Pong!**\n⏱️ Response time: `{ping_time:.2f}ms`", parse_mode='Markdown')
    
    async def on_new_message(self, event):
        """Handle new messages from Telethon"""
        # This can be used for advanced message handling
        # that requires Telethon's capabilities
        pass
    
    async def log_private(self, message: str):
        """Send log message to private logging chat"""
        if Config.LOG_CHAT:
            try:
                await self.telethon_client.send_message(Config.LOG_CHAT, f"📋 **Bot Log**\n{message}")
            except Exception as e:
                logger.error(f"Failed to send private log: {e}")
    
    async def start(self):
        """Start the bot"""
        logger.info("Starting Telegram Group Management Bot...")
        
        # Start Telethon client
        await self.telethon_client.start(bot_token=Config.BOT_TOKEN)
        logger.info("Telethon client started")
        
        # Load modules
        self.module_manager.load_modules()
        logger.info(f"Loaded {len(self.module_manager.modules)} modules")
        
        # Start PTB application
        await self.ptb_app.initialize()
        await self.ptb_app.start()
        logger.info("Python-telegram-bot application started")
        
        # Log startup
        await self.log_private("🚀 Bot started successfully!")
        
        logger.info("Bot is now running...")
        
        # Keep running
        await self.ptb_app.updater.start_polling()
        await self.telethon_client.run_until_disconnected()
    
    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping bot...")
        await self.log_private("🛑 Bot is shutting down...")
        
        await self.ptb_app.stop()
        await self.telethon_client.disconnect()
        logger.info("Bot stopped")

# Example Module (modules/example.py)
EXAMPLE_MODULE = '''
# modules/example.py
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

# Module metadata
MODULE_NAME = "Example Module"
MODULE_VERSION = "1.0.0"
COMMANDS = ["example", "test"]

async def example_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Example command handler"""
    await update.message.reply_text("This is an example command from a module!")

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test command handler"""
    await update.message.reply_text("Test command working!")

def setup(bot):
    """Setup function called when module is loaded"""
    # Add handlers to the bot
    bot.ptb_app.add_handler(CommandHandler("example", example_command))
    bot.ptb_app.add_handler(CommandHandler("test", test_command))
    print(f"Module {MODULE_NAME} v{MODULE_VERSION} loaded successfully!")

def cleanup():
    """Cleanup function called when module is unloaded"""
    print(f"Module {MODULE_NAME} unloaded")
'''

# Initialize logger
logger = BotLogger()

# Main execution
async def main():
    # Create example module if it doesn't exist
    os.makedirs('modules', exist_ok=True)
    if not os.path.exists('modules/example.py'):
        with open('modules/example.py', 'w') as f:
            f.write(EXAMPLE_MODULE)
        logger.info("Created example module")
    
    # Create bot instance and start
    bot = TelegramGroupBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
    finally:
        await bot.stop()

if __name__ == "__main__":
    # Check for required environment variables
    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables and try again.")
        sys.exit(1)
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
