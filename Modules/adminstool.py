import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, Union
from telegram import Update, ChatMember, User
from telegram.ext import ContextTypes, CommandHandler, Application
from telegram.error import BadRequest, Forbidden

class AdminTools:
    def __init__(self):
        self.muted_users = {}  # Store temporary mutes: {chat_id: {user_id: unmute_time}}
        self.banned_users = {}  # Store temporary bans: {chat_id: {user_id: unban_time}}
    
    def parse_time(self, time_str: str) -> Optional[int]:
        """Parse time string like '1h', '30m', '1d' into seconds"""
        if not time_str:
            return None
        
        time_units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
        match = re.match(r'^(\d+)([smhdw])$', time_str.lower())
        
        if match:
            amount, unit = match.groups()
            return int(amount) * time_units[unit]
        return None
    
    async def get_user_from_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, args: list) -> Optional[User]:
        """Extract user from command arguments (mention, username, or ID)"""
        if update.message.reply_to_message:
            return update.message.reply_to_message.from_user
        
        if not args:
            return None
        
        user_identifier = args[0]
        
        # Check if it's a mention
        if user_identifier.startswith('@'):
            username = user_identifier[1:]
            try:
                chat_member = await context.bot.get_chat_member(update.effective_chat.id, username)
                return chat_member.user
            except:
                return None
        
        # Check if it's a user ID
        if user_identifier.isdigit():
            try:
                chat_member = await context.bot.get_chat_member(update.effective_chat.id, int(user_identifier))
                return chat_member.user
            except:
                return None
        
        return None
    
    async def is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
        """Check if user is admin"""
        try:
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
            return chat_member.status in ['creator', 'administrator']
        except:
            return False
    
    async def ban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ban a user permanently"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a user to ban (reply, mention, username, or ID).")
            return
        
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, user.id)
            reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
            await update.message.reply_text(f"Banned {user.full_name} (ID: {user.id})\nReason: {reason}")
        except Exception as e:
            await update.message.reply_text(f"Failed to ban user: {str(e)}")
    
    async def sban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Silent ban - ban without notification"""
        if not await self.is_admin(update, context, update.effective_user.id):
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            return
        
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, user.id)
            await context.bot.delete_message(update.effective_chat.id, update.message.message_id)
        except:
            pass
    
    async def tban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Temporarily ban a user"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /tban <user> <time> [reason]\nExample: /tban @username 1h spam")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a valid user.")
            return
        
        duration = self.parse_time(context.args[1])
        if not duration:
            await update.message.reply_text("Invalid time format. Use: 1s, 1m, 1h, 1d, 1w")
            return
        
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, user.id)
            
            # Schedule unban
            chat_id = update.effective_chat.id
            if chat_id not in self.banned_users:
                self.banned_users[chat_id] = {}
            
            unban_time = datetime.now() + timedelta(seconds=duration)
            self.banned_users[chat_id][user.id] = unban_time
            
            reason = " ".join(context.args[2:]) if len(context.args) > 2 else "No reason provided"
            await update.message.reply_text(f"Temporarily banned {user.full_name} for {context.args[1]}\nReason: {reason}")
            
            # Schedule unban task
            asyncio.create_task(self.schedule_unban(context, chat_id, user.id, duration))
        except Exception as e:
            await update.message.reply_text(f"Failed to ban user: {str(e)}")
    
    async def kick_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Kick a user (ban and immediately unban)"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a user to kick.")
            return
        
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, user.id)
            await context.bot.unban_chat_member(update.effective_chat.id, user.id)
            reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
            await update.message.reply_text(f"Kicked {user.full_name} (ID: {user.id})\nReason: {reason}")
        except Exception as e:
            await update.message.reply_text(f"Failed to kick user: {str(e)}")
    
    async def unban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unban a user"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a user to unban.")
            return
        
        try:
            await context.bot.unban_chat_member(update.effective_chat.id, user.id)
            await update.message.reply_text(f"Unbanned {user.full_name} (ID: {user.id})")
        except Exception as e:
            await update.message.reply_text(f"Failed to unban user: {str(e)}")
    
    async def mute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mute a user permanently"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a user to mute.")
            return
        
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, 
                user.id,
                permissions=ChatMember.RESTRICTED
            )
            reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
            await update.message.reply_text(f"Muted {user.full_name} (ID: {user.id})\nReason: {reason}")
        except Exception as e:
            await update.message.reply_text(f"Failed to mute user: {str(e)}")
    
    async def smute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Silent mute - mute without notification"""
        if not await self.is_admin(update, context, update.effective_user.id):
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            return
        
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, 
                user.id,
                permissions=ChatMember.RESTRICTED
            )
            await context.bot.delete_message(update.effective_chat.id, update.message.message_id)
        except:
            pass
    
    async def tmute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Temporarily mute a user"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /tmute <user> <time> [reason]\nExample: /tmute @username 1h spam")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a valid user.")
            return
        
        duration = self.parse_time(context.args[1])
        if not duration:
            await update.message.reply_text("Invalid time format. Use: 1s, 1m, 1h, 1d, 1w")
            return
        
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, 
                user.id,
                permissions=ChatMember.RESTRICTED,
                until_date=datetime.now() + timedelta(seconds=duration)
            )
            
            reason = " ".join(context.args[2:]) if len(context.args) > 2 else "No reason provided"
            await update.message.reply_text(f"Temporarily muted {user.full_name} for {context.args[1]}\nReason: {reason}")
        except Exception as e:
            await update.message.reply_text(f"Failed to mute user: {str(e)}")
    
    async def unmute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unmute a user"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a user to unmute.")
            return
        
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, 
                user.id,
                permissions=ChatMember.MEMBER
            )
            await update.message.reply_text(f"Unmuted {user.full_name} (ID: {user.id})")
        except Exception as e:
            await update.message.reply_text(f"Failed to unmute user: {str(e)}")
    
    async def promote_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Promote a user to admin"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a user to promote.")
            return
        
        try:
            await context.bot.promote_chat_member(
                update.effective_chat.id, 
                user.id,
                can_delete_messages=True,
                can_restrict_members=True,
                can_pin_messages=True,
                can_invite_users=True
            )
            title = " ".join(context.args[1:]) if len(context.args) > 1 else None
            if title:
                await context.bot.set_chat_administrator_custom_title(update.effective_chat.id, user.id, title)
            
            await update.message.reply_text(f"Promoted {user.full_name} (ID: {user.id})" + (f" with title: {title}" if title else ""))
        except Exception as e:
            await update.message.reply_text(f"Failed to promote user: {str(e)}")
    
    async def demote_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Demote an admin to regular user"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        user = await self.get_user_from_message(update, context, context.args)
        if not user:
            await update.message.reply_text("Please specify a user to demote.")
            return
        
        try:
            await context.bot.promote_chat_member(
                update.effective_chat.id, 
                user.id,
                can_delete_messages=False,
                can_restrict_members=False,
                can_pin_messages=False,
                can_invite_users=False,
                can_promote_members=False
            )
            await update.message.reply_text(f"Demoted {user.full_name} (ID: {user.id})")
        except Exception as e:
            await update.message.reply_text(f"Failed to demote user: {str(e)}")
    
    async def pin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pin a message"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text("Reply to a message to pin it.")
            return
        
        try:
            await context.bot.pin_chat_message(
                update.effective_chat.id, 
                update.message.reply_to_message.message_id,
                disable_notification=False
            )
            await update.message.reply_text("Message pinned successfully.")
        except Exception as e:
            await update.message.reply_text(f"Failed to pin message: {str(e)}")
    
    async def unpin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unpin a message"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        try:
            if update.message.reply_to_message:
                await context.bot.unpin_chat_message(
                    update.effective_chat.id, 
                    update.message.reply_to_message.message_id
                )
            else:
                await context.bot.unpin_all_chat_messages(update.effective_chat.id)
            
            await update.message.reply_text("Message(s) unpinned successfully.")
        except Exception as e:
            await update.message.reply_text(f"Failed to unpin message: {str(e)}")
    
    async def purge_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete messages (reply to start message or specify count)"""
        if not await self.is_admin(update, context, update.effective_user.id):
            await update.message.reply_text("You need admin permissions to use this command.")
            return
        
        if update.message.reply_to_message:
            # Delete from replied message to current
            start_id = update.message.reply_to_message.message_id
            end_id = update.message.message_id
            deleted = 0
            
            for msg_id in range(start_id, end_id + 1):
                try:
                    await context.bot.delete_message(update.effective_chat.id, msg_id)
                    deleted += 1
                except:
                    continue
            
            await update.message.reply_text(f"Deleted {deleted} messages.")
        elif context.args and context.args[0].isdigit():
            # Delete specified number of messages
            count = min(int(context.args[0]), 100)  # Limit to 100
            deleted = 0
            current_id = update.message.message_id
            
            for i in range(count + 1):  # +1 to include command message
                try:
                    await context.bot.delete_message(update.effective_chat.id, current_id - i)
                    deleted += 1
                except:
                    continue
            
            # Send confirmation and delete it after 3 seconds
            confirm_msg = await context.bot.send_message(
                update.effective_chat.id, 
                f"Deleted {deleted} messages."
            )
            asyncio.create_task(self.delete_after_delay(context, update.effective_chat.id, confirm_msg.message_id, 3))
        else:
            await update.message.reply_text("Reply to a message to start purging from there, or specify number of messages to delete.")
    
    async def spurge_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Silent purge - delete messages without confirmation"""
        if not await self.is_admin(update, context, update.effective_user.id):
            return
        
        if update.message.reply_to_message:
            start_id = update.message.reply_to_message.message_id
            end_id = update.message.message_id
            
            for msg_id in range(start_id, end_id + 1):
                try:
                    await context.bot.delete_message(update.effective_chat.id, msg_id)
                except:
                    continue
        elif context.args and context.args[0].isdigit():
            count = min(int(context.args[0]), 100)
            current_id = update.message.message_id
            
            for i in range(count + 1):
                try:
                    await context.bot.delete_message(update.effective_chat.id, current_id - i)
                except:
                    continue
    
    async def id_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get user/chat ID information"""
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
            await update.message.reply_text(
                f"User ID: {user.id}\n"
                f"Name: {user.full_name}\n"
                f"Username: @{user.username if user.username else 'None'}\n"
                f"Chat ID: {update.effective_chat.id}"
            )
        elif context.args:
            user = await self.get_user_from_message(update, context, context.args)
            if user:
                await update.message.reply_text(
                    f"User ID: {user.id}\n"
                    f"Name: {user.full_name}\n"
                    f"Username: @{user.username if user.username else 'None'}\n"
                    f"Chat ID: {update.effective_chat.id}"
                )
            else:
                await update.message.reply_text("User not found.")
        else:
            await update.message.reply_text(
                f"Your ID: {update.effective_user.id}\n"
                f"Chat ID: {update.effective_chat.id}"
            )
    
    async def info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get detailed user information"""
        user = None
        
        if update.message.reply_to_message:
            user = update.message.reply_to_message.from_user
        elif context.args:
            user = await self.get_user_from_message(update, context, context.args)
        else:
            user = update.effective_user
        
        if not user:
            await update.message.reply_text("User not found.")
            return
        
        try:
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
            
            info_text = f"User Information:\n"
            info_text += f"ID: {user.id}\n"
            info_text += f"Name: {user.full_name}\n"
            info_text += f"Username: @{user.username if user.username else 'None'}\n"
            info_text += f"Status: {chat_member.status}\n"
            info_text += f"Is Bot: {'Yes' if user.is_bot else 'No'}\n"
            
            if chat_member.status == 'restricted':
                info_text += f"Restricted: Yes\n"
            
            await update.message.reply_text(info_text)
        except Exception as e:
            await update.message.reply_text(f"Failed to get user info: {str(e)}")
    
    async def schedule_unban(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, duration: int):
        """Schedule automatic unban after duration"""
        await asyncio.sleep(duration)
        try:
            await context.bot.unban_chat_member(chat_id, user_id)
            if chat_id in self.banned_users and user_id in self.banned_users[chat_id]:
                del self.banned_users[chat_id][user_id]
        except:
            pass
    
    async def delete_after_delay(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int):
        """Delete a message after specified delay"""
        await asyncio.sleep(delay)
        try:
            await context.bot.delete_message(chat_id, message_id)
        except:
            pass
    
    def add_handlers(self, application: Application):
        """Add all command handlers to the application"""
        handlers = [
            CommandHandler("ban", self.ban_command),
            CommandHandler("sban", self.sban_command),
            CommandHandler("tban", self.tban_command),
            CommandHandler("kick", self.kick_command),
            CommandHandler("unban", self.unban_command),
            CommandHandler("mute", self.mute_command),
            CommandHandler("smute", self.smute_command),
            CommandHandler("tmute", self.tmute_command),
            CommandHandler("unmute", self.unmute_command),
            CommandHandler("promote", self.promote_command),
            CommandHandler("demote", self.demote_command),
            CommandHandler("pin", self.pin_command),
            CommandHandler("unpin", self.unpin_command),
            CommandHandler("purge", self.purge_command),
            CommandHandler("spurge", self.spurge_command),
            CommandHandler("id", self.id_command),
            CommandHandler("info", self.info_command),
        ]
        
        for handler in handlers:
            application.add_handler(handler)

# Setup function for module loading
def setup(application: Application):
    """Setup function to initialize the admin tools module"""
    admin_tools = AdminTools()
    admin_tools.add_handlers(application)
    return admin_tools

# Usage example:
# admin_tools = AdminTools()
# admin_tools.add_handlers(application)
