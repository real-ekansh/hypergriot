# main.py
import os
import sys
import logging
import importlib
import asyncio
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telethon import TelegramClient, events

# Load environment variables
load_dotenv()

# Bot configuration from .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 0))
MODULES_DIR = os.getenv("MODULES_DIR", "modules")

# Permission levels
DEV_USERS = set(map(int, os.getenv("DEV_USERS", "").split(","))) if os.getenv("DEV_USERS") else set()
SUDO_USERS = set(map(int, os.getenv("SUDO_USERS", "").split(","))) if os.getenv("SUDO_USERS") else set()
SUPPORT_USERS = set(map(int, os.getenv("SUPPORT_USERS", "").split(","))) if os.getenv("SUPPORT_USERS") else set()

# Logging setup
def setup_logging():
    # Main logger for general info
    info_logger = logging.getLogger("bot_info")
    info_logger.setLevel(logging.INFO)
    
    # Console handler for info
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # File handler for info
    info_file_handler = logging.FileHandler('bot_info.log')
    info_file_handler.setLevel(logging.INFO)
    info_file_handler.setFormatter(console_formatter)
    
    info_logger.addHandler(console_handler)
    info_logger.addHandler(info_file_handler)
    
    # Private logger for errors and tracebacks
    error_logger = logging.getLogger("bot_errors")
    error_logger.setLevel(logging.ERROR)
    
    # File handler for errors
    error_file_handler = logging.FileHandler('bot_errors.log')
    error_file_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    error_file_handler.setFormatter(error_formatter)
    
    error_logger.addHandler(error_file_handler)
    
    return info_logger, error_logger

info_logger, error_logger = setup_logging()

class PermissionSystem:
    """Custom permission system for the bot"""
    
    @staticmethod
    def is_dev(user_id: int) -> bool:
        return user_id in DEV_USERS
    
    @staticmethod
    def is_sudo(user_id: int) -> bool:
        return user_id in SUDO_USERS or PermissionSystem.is_dev(user_id)
    
    @staticmethod
    def is_support(user_id: int) -> bool:
        return user_id in SUPPORT_USERS or PermissionSystem.is_sudo(user_id)
    
    @staticmethod
    def get_user_rank(user_id: int) -> str:
        if PermissionSystem.is_dev(user_id):
            return "Dev"
        elif PermissionSystem.is_sudo(user_id):
            return "Sudo"
        elif PermissionSystem.is_support(user_id):
            return "Support"
        return "User"

class ModuleLoader:
    """Dynamic module loader system"""
    
    def __init__(self, modules_dir: str):
        self.modules_dir = Path(modules_dir)
        self.loaded_modules: Dict[str, any] = {}
        self.module_handlers: List[any] = []
        
    def load_modules(self, application: Application) -> None:
        """Load all modules from the modules directory"""
        if not self.modules_dir.exists():
            self.modules_dir.mkdir(exist_ok=True)
            info_logger.info(f"Created modules directory: {self.modules_dir}")
            return
        
        # Add modules directory to Python path
        sys.path.insert(0, str(self.modules_dir.parent))
        
        for module_file in self.modules_dir.glob("*.py"):
            if module_file.name.startswith("_"):
                continue
                
            module_name = module_file.stem
            try:
                # Import the module
                spec = importlib.util.spec_from_file_location(
                    f"{self.modules_dir.name}.{module_name}", 
                    module_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Check if module has required setup function
                if hasattr(module, 'setup'):
                    handlers = module.setup()
                    if handlers:
                        for handler in handlers:
                            application.add_handler(handler)
                            self.module_handlers.append(handler)
                        
                    self.loaded_modules[module_name] = module
                    info_logger.info(f"Loaded module: {module_name}")
                else:
                    info_logger.warning(f"Module {module_name} missing setup() function")
                    
            except Exception as e:
                error_logger.error(f"Failed to load module {module_name}: {str(e)}", exc_info=True)
    
    def reload_module(self, module_name: str, application: Application) -> bool:
        """Reload a specific module"""
        try:
            if module_name in self.loaded_modules:
                # Remove old handlers
                old_module = self.loaded_modules[module_name]
                if hasattr(old_module, 'handlers'):
                    for handler in old_module.handlers:
                        if handler in self.module_handlers:
                            application.remove_handler(handler)
                            self.module_handlers.remove(handler)
                
                # Reload the module
                importlib.reload(self.loaded_modules[module_name])
                
                # Re-add handlers
                if hasattr(self.loaded_modules[module_name], 'setup'):
                    handlers = self.loaded_modules[module_name].setup()
                    if handlers:
                        for handler in handlers:
                            application.add_handler(handler)
                            self.module_handlers.append(handler)
                
                info_logger.info(f"Reloaded module: {module_name}")
                return True
            else:
                info_logger.warning(f"Module {module_name} not found in loaded modules")
                return False
                
        except Exception as e:
            error_logger.error(f"Failed to reload module {module_name}: {str(e)}", exc_info=True)
            return False

# Initialize module loader
module_loader = ModuleLoader(MODULES_DIR)

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user = update.effective_user
    info_logger.info(f"Start command received from user {user.id} ({user.username})")
    
    rank = PermissionSystem.get_user_rank(user.id)
    
    await update.message.reply_text(
        f"Welcome to the Group Management Bot!\n\n"
        f"Your ID: {user.id}\n"
        f"Your Rank: {rank}\n\n"
        f"Use /help to see available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    user = update.effective_user
    rank = PermissionSystem.get_user_rank(user.id)
    
    help_text = "Available Commands:\n\n"
    help_text += "General:\n"
    help_text += "/start - Start the bot\n"
    help_text += "/help - Show this help message\n"
    help_text += "/ping - Check bot response time\n"
    
    if PermissionSystem.is_support(user.id):
        help_text += "\nSupport Commands:\n"
        help_text += "/stats - Show bot statistics\n"
    
    if PermissionSystem.is_sudo(user.id):
        help_text += "\nSudo Commands:\n"
        help_text += "/broadcast - Broadcast message to all users\n"
    
    if PermissionSystem.is_dev(user.id):
        help_text += "\nDev Commands:\n"
        help_text += "/reload - Reload a module\n"
        help_text += "/modules - List loaded modules\n"
        help_text += "/eval - Execute Python code\n"
    
    await update.message.reply_text(help_text)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ping command"""
    start_time = datetime.now()
    msg = await update.message.reply_text("Pinging...")
    end_time = datetime.now()
    
    ping_time = (end_time - start_time).total_seconds() * 1000
    await msg.edit_text(f"Pong! Response time: {ping_time:.2f}ms")

async def modules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /modules command (Dev only)"""
    user = update.effective_user
    
    if not PermissionSystem.is_dev(user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if module_loader.loaded_modules:
        modules_list = "\n".join([f"- {name}" for name in module_loader.loaded_modules.keys()])
        await update.message.reply_text(f"Loaded modules:\n{modules_list}")
    else:
        await update.message.reply_text("No modules loaded.")

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reload command (Dev only)"""
    user = update.effective_user
    
    if not PermissionSystem.is_dev(user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /reload <module_name>")
        return
    
    module_name = context.args[0]
    if module_loader.reload_module(module_name, context.application):
        await update.message.reply_text(f"Successfully reloaded module: {module_name}")
    else:
        await update.message.reply_text(f"Failed to reload module: {module_name}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates"""
    error_logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "An error occurred while processing your request. The developers have been notified."
        )

async def post_init(application: Application) -> None:
    """Initialize bot after startup"""
    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help message"),
        BotCommand("ping", "Check bot response time"),
    ]
    await application.bot.set_my_commands(commands)
    
    # Load modules
    module_loader.load_modules(application)
    
    info_logger.info("Bot initialization completed")

def main():
    """Main function to run the bot"""
    if not BOT_TOKEN:
        error_logger.error("BOT_TOKEN not found in .env file")
        sys.exit(1)
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("modules", modules_command))
    application.add_handler(CommandHandler("reload", reload_command))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    info_logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
