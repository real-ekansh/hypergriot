# modules/admin.py
"""Admin module for group management"""

from telegram import Update, ChatPermissions
from telegram.ext import CommandHandler, ContextTypes, filters
from telegram.constants import ParseMode
import logging
from datetime import datetime, timedelta

# Import permission system from main
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import PermissionSystem, info_logger, error_logger

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user from the group"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Check if user has support permissions
    if not PermissionSystem.is_support(user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    # Check if command is used in a group
    if chat.type == 'private':
        await update.message.reply_text("This command can only be used in groups.")
        return
    
    # Check if replying to a message
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to ban them.")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    # Check if target is admin
    try:
        member = await chat.get_member(target_user.id)
        if member.status in ['administrator', 'creator']:
            await update.message.reply_text("Cannot ban an admin.")
            return
    except Exception as e:
        error_logger.error(f"Error checking member status: {str(e)}", exc_info=True)
        return
    
    # Ban the user
    try:
        await chat.ban_member(target_user.id)
        await update.message.reply_text(f"Banned {target_user.mention_html()}", parse_mode=ParseMode.HTML)
        info_logger.info(f"User {user.id} banned {target_user.id} from chat {chat.id}")
    except Exception as e:
        error_logger.error(f"Failed to ban user: {str(e)}", exc_info=True)
        await update.message.reply_text("Failed to ban user.")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unban a user from the group"""
    user = update.effective_user
    chat = update.effective_chat
    
    if not PermissionSystem.is_support(user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if chat.type == 'private':
        await update.message.reply_text("This command can only be used in groups.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    
    try:
        await chat.unban_member(target_user_id)
        await update.message.reply_text(f"Unbanned user {target_user_id}")
        info_logger.info(f"User {user.id} unbanned {target_user_id} from chat {chat.id}")
    except Exception as e:
        error_logger.error(f"Failed to unban user: {str(e)}", exc_info=True)
        await update.message.reply_text("Failed to unban user.")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mute a user in the group"""
    user = update.effective_user
    chat = update.effective_chat
    
    if not PermissionSystem.is_support(user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if chat.type == 'private':
        await update.message.reply_text("This command can only be used in groups.")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to mute them.")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    # Parse duration
    duration = 0
    if context.args:
        time_str = context.args[0]
        try:
            if time_str.endswith('m'):
                duration = int(time_str[:-1])
            elif time_str.endswith('h'):
                duration = int(time_str[:-1]) * 60
            elif time_str.endswith('d'):
                duration = int(time_str[:-1]) * 60 * 24
            else:
                duration = int(time_str)
        except ValueError:
            await update.message.reply_text("Invalid duration format. Use: 5m, 1h, 1d")
            return
    
    # Mute the user
    try:
        permissions = ChatPermissions(can_send_messages=False)
        
        if duration > 0:
            until_date = datetime.now() + timedelta(minutes=duration)
            await chat.restrict_member(target_user.id, permissions, until_date=until_date)
            await update.message.reply_text(f"Muted {target_user.mention_html()} for {duration} minutes", parse_mode=ParseMode.HTML)
        else:
            await chat.restrict_member(target_user.id, permissions)
            await update.message.reply_text(f"Muted {target_user.mention_html()} indefinitely", parse_mode=ParseMode.HTML)
            
        info_logger.info(f"User {user.id} muted {target_user.id} in chat {chat.id}")
    except Exception as e:
        error_logger.error(f"Failed to mute user: {str(e)}", exc_info=True)
        await update.message.reply_text("Failed to mute user.")

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute a user in the group"""
    user = update.effective_user
    chat = update.effective_chat
    
    if not PermissionSystem.is_support(user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if chat.type == 'private':
        await update.message.reply_text("This command can only be used in groups.")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to unmute them.")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )
        
        await chat.restrict_member(target_user.id, permissions)
        await update.message.reply_text(f"Unmuted {target_user.mention_html()}", parse_mode=ParseMode.HTML)
        info_logger.info(f"User {user.id} unmuted {target_user.id} in chat {chat.id}")
    except Exception as e:
        error_logger.error(f"Failed to unmute user: {str(e)}", exc_info=True)
        await update.message.reply_text("Failed to unmute user.")

async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Promote a user to admin (Sudo only)"""
    user = update.effective_user
    chat = update.effective_chat
    
    if not PermissionSystem.is_sudo(user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if chat.type == 'private':
        await update.message.reply_text("This command can only be used in groups.")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to promote them.")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    try:
        await chat.promote_member(
            target_user.id,
            can_change_info=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=False
        )
        await update.message.reply_text(f"Promoted {target_user.mention_html()} to admin", parse_mode=ParseMode.HTML)
        info_logger.info(f"User {user.id} promoted {target_user.id} in chat {chat.id}")
    except Exception as e:
        error_logger.error(f"Failed to promote user: {str(e)}", exc_info=True)
        await update.message.reply_text("Failed to promote user.")

async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Demote an admin (Sudo only)"""
    user = update.effective_user
    chat = update.effective_chat
    
    if not PermissionSystem.is_sudo(user.id):
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    if chat.type == 'private':
        await update.message.reply_text("This command can only be used in groups.")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to demote them.")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    try:
        await chat.promote_member(
            target_user.id,
            can_change_info=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False
        )
        await update.message.reply_text(f"Demoted {target_user.mention_html()}", parse_mode=ParseMode.HTML)
        info_logger.info(f"User {user.id} demoted {target_user.id} in chat {chat.id}")
    except Exception as e:
        error_logger.error(f"Failed to demote user: {str(e)}", exc_info=True)
        await update.message.reply_text("Failed to demote user.")

def setup():
    """Setup function called by module loader"""
    handlers = [
        CommandHandler("ban", ban_command),
        CommandHandler("unban", unban_command),
        CommandHandler("mute", mute_command),
        CommandHandler("unmute", unmute_command),
        CommandHandler("promote", promote_command),
        CommandHandler("demote", demote_command),
    ]
    
    # Store handlers for potential reload
    globals()['handlers'] = handlers
    
    return handlers
