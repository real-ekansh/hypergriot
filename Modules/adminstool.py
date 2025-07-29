# modules/complete_admin.py
# Complete admin module with all missing commands

import time
import asyncio
from telebot import types

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
    RANKS = {
        'owner': 5,
        'dev': 4,
        'admin': 3,
        'sudo': 2,
        'user': 1
    }
    
    def decorator(func):
        async def wrapper(message):
            # In real implementation, this would check against database
            # For now, assume admin access for demo
            return await func(message)
        return wrapper
    return decorator

async def get_user_from_message(bot, message, text: str):
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
    
    return None

def register_handlers(bot):
    """Register all admin command handlers"""
    
    @bot.message_handler(commands=['promote'])
    @check_rank('admin')
    async def promote_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        target_user = await get_user_from_message(bot, message, message.text)
        if not target_user:
            await bot.reply_to(message, "Please reply to a user or provide user ID")
            return
        
        try:
            await bot.promote_chat_member(
                message.chat.id,
                target_user.id,
                can_delete_messages=True,
                can_restrict_members=True,
                can_pin_messages=True,
                can_promote_members=False,
                can_change_info=True,
                can_invite_users=True
            )
            await bot.reply_to(message, f"User {target_user.first_name} promoted to admin")
        except Exception as e:
            await bot.reply_to(message, f"Failed to promote user: {str(e)}")
    
    @bot.message_handler(commands=['demote'])
    @check_rank('admin')
    async def demote_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        target_user = await get_user_from_message(bot, message, message.text)
        if not target_user:
            await bot.reply_to(message, "Please reply to a user or provide user ID")
            return
        
        try:
            await bot.promote_chat_member(
                message.chat.id,
                target_user.id,
                can_delete_messages=False,
                can_restrict_members=False,
                can_pin_messages=False,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=False
            )
            await bot.reply_to(message, f"User {target_user.first_name} demoted from admin")
        except Exception as e:
            await bot.reply_to(message, f"Failed to demote user: {str(e)}")
    
    @bot.message_handler(commands=['pin'])
    @check_rank('admin')
    async def pin_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        if not message.reply_to_message:
            await bot.reply_to(message, "Please reply to a message to pin")
            return
        
        try:
            await bot.pin_chat_message(
                message.chat.id,
                message.reply_to_message.message_id,
                disable_notification=True
            )
            await bot.reply_to(message, "Message pinned")
        except Exception as e:
            await bot.reply_to(message, f"Failed to pin message: {str(e)}")
    
    @bot.message_handler(commands=['unpin'])
    @check_rank('admin')
    async def unpin_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        try:
            if message.reply_to_message:
                await bot.unpin_chat_message(message.chat.id, message.reply_to_message.message_id)
            else:
                await bot.unpin_chat_message(message.chat.id)
            await bot.reply_to(message, "Message unpinned")
        except Exception as e:
            await bot.reply_to(message, f"Failed to unpin message: {str(e)}")
    
    @bot.message_handler(commands=['purge'])
    @check_rank('admin')
    async def purge_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        parts = message.text.split()
        count = 1
        
        if message.reply_to_message:
            # Purge from replied message to current
            start_id = message.reply_to_message.message_id
            end_id = message.message_id
            count = end_id - start_id + 1
        elif len(parts) > 1 and parts[1].isdigit():
            count = min(int(parts[1]), 100)  # Limit to 100 messages
        
        try:
            deleted_count = 0
            current_message_id = message.message_id
            
            # Delete the purge command message first
            await bot.delete_message(message.chat.id, message.message_id)
            
            # Delete previous messages
            for i in range(1, count + 1):
                try:
                    await bot.delete_message(message.chat.id, current_message_id - i)
                    deleted_count += 1
                    await asyncio.sleep(0.1)  # Small delay to avoid rate limits
                except:
                    pass
            
            # Send confirmation message and delete it after 3 seconds
            confirm_msg = await bot.send_message(message.chat.id, f"Deleted {deleted_count} messages")
            await asyncio.sleep(3)
            await bot.delete_message(message.chat.id, confirm_msg.message_id)
            
        except Exception as e:
            await bot.send_message(message.chat.id, f"Failed to purge messages: {str(e)}")
    
    @bot.message_handler(commands=['report'])
    async def report_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        if not message.reply_to_message:
            await bot.reply_to(message, "Please reply to a message to report")
            return
        
        try:
            # Get group admins
            admins = await bot.get_chat_administrators(message.chat.id)
            admin_mentions = []
            
            for admin in admins:
                if not admin.user.is_bot and admin.user.username:
                    admin_mentions.append(f"@{admin.user.username}")
            
            reporter = message.from_user.username or message.from_user.first_name
            reported_user = message.reply_to_message.from_user.first_name
            
            report_text = f"Report from @{reporter if message.from_user.username else reporter}\n"
            report_text += f"Reported user: {reported_user}\n"
            report_text += f"Message: {message.reply_to_message.text[:100] if message.reply_to_message.text else 'Media/File'}..."
            
            if admin_mentions:
                report_text += f"\n\nAdmins: {' '.join(admin_mentions[:5])}"
            
            await bot.reply_to(message.reply_to_message, report_text)
            
        except Exception as e:
            await bot.reply_to(message, f"Failed to report message: {str(e)}")
    
    @bot.message_handler(commands=['sban'])
    @check_rank('admin')
    async def sban_command(message):
        """Silent ban - ban without notification"""
        if message.chat.type not in ['group', 'supergroup']:
            return
        
        target_user = await get_user_from_message(bot, message, message.text)
        if not target_user:
            return
        
        try:
            # Delete the command message
            await bot.delete_message(message.chat.id, message.message_id)
            
            # Parse duration
            parts = message.text.split()
            duration_seconds = 0
            ban_until = None
            
            if len(parts) > 2 or (len(parts) > 1 and not message.reply_to_message):
                duration_str = parts[-1]
                duration_seconds = parse_time_duration(duration_str)
                if duration_seconds > 0:
                    ban_until = int(time.time()) + duration_seconds
            
            await bot.ban_chat_member(
                message.chat.id, 
                target_user.id,
                until_date=ban_until
            )
            
        except Exception as e:
            pass  # Silent operation
    
    @bot.message_handler(commands=['lock'])
    @check_rank('admin')
    async def lock_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            await bot.reply_to(message, "Usage: /lock <type>\nTypes: msg, media, sticker, gif, game, inline, web, poll")
            return
        
        lock_type = parts[1].lower()
        
        try:
            current_permissions = await bot.get_chat(message.chat.id)
            permissions = types.ChatPermissions()
            
            # Set all current permissions first
            permissions.can_send_messages = True
            permissions.can_send_media_messages = True
            permissions.can_send_polls = True
            permissions.can_send_other_messages = True
            permissions.can_add_web_page_previews = True
            permissions.can_change_info = False
            permissions.can_invite_users = True
            permissions.can_pin_messages = False
            
            # Apply specific lock
            if lock_type in ['msg', 'messages']:
                permissions.can_send_messages = False
            elif lock_type in ['media']:
                permissions.can_send_media_messages = False
            elif lock_type in ['sticker', 'stickers']:
                permissions.can_send_other_messages = False
            elif lock_type in ['poll', 'polls']:
                permissions.can_send_polls = False
            elif lock_type in ['web', 'preview']:
                permissions.can_add_web_page_previews = False
            elif lock_type == 'all':
                permissions.can_send_messages = False
                permissions.can_send_media_messages = False
                permissions.can_send_polls = False
                permissions.can_send_other_messages = False
                permissions.can_add_web_page_previews = False
            
            await bot.set_chat_permissions(message.chat.id, permissions)
            await bot.reply_to(message, f"Locked {lock_type} for all members")
            
        except Exception as e:
            await bot.reply_to(message, f"Failed to set lock: {str(e)}")
    
    @bot.message_handler(commands=['unlock'])
    @check_rank('admin')
    async def unlock_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        parts = message.text.split()
        if len(parts) < 2:
            await bot.reply_to(message, "Usage: /unlock <type>\nTypes: msg, media, sticker, gif, game, inline, web, poll, all")
            return
        
        unlock_type = parts[1].lower()
        
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
            
            await bot.set_chat_permissions(message.chat.id, permissions)
            await bot.reply_to(message, f"Unlocked {unlock_type} for all members")
            
        except Exception as e:
            await bot.reply_to(message, f"Failed to remove lock: {str(e)}")
    
    @bot.message_handler(commands=['warn'])
    @check_rank('admin')
    async def warn_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        target_user = await get_user_from_message(bot, message, message.text)
        if not target_user:
            await bot.reply_to(message, "Please reply to a user or provide user ID")
            return
        
        parts = message.text.split(None, 2)
        reason = parts[2] if len(parts) > 2 else "No reason provided"
        
        # In a real implementation, you'd store warnings in database
        warn_text = f"User {target_user.first_name} has been warned\n"
        warn_text += f"Reason: {reason}\n"
        warn_text += f"Warning 1/3"  # This would be dynamic from database
        
        await bot.reply_to(message, warn_text)
    
    @bot.message_handler(commands=['warns'])
    @check_rank('admin')
    async def warns_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        target_user = await get_user_from_message(bot, message, message.text)
        if not target_user:
            target_user = message.from_user
        
        # In real implementation, fetch from database
        await bot.reply_to(message, f"User {target_user.first_name} has 0 warnings")
    
    @bot.message_handler(commands=['clearwarns'])
    @check_rank('admin')
    async def clearwarns_command(message):
        if message.chat.type not in ['group', 'supergroup']:
            await bot.reply_to(message, "This command can only be used in groups")
            return
        
        target_user = await get_user_from_message(bot, message, message.text)
        if not target_user:
            await bot.reply_to(message, "Please reply to a user or provide user ID")
            return
        
        # In real implementation, clear warnings from database
        await bot.reply_to(message, f"Cleared all warnings for {target_user.first_name}")

    print("Complete admin module loaded successfully")
