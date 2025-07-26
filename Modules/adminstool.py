const { PermissionsBitField, EmbedBuilder } = require('discord.js');

class AdminTools {
    constructor(client) {
        this.client = client;
        this.mutedUsers = new Map(); // Store muted users with expiry times
        this.bannedUsers = new Map(); // Store temporary bans with expiry times
    }

    // Helper function to resolve user from mention, ID, or username
    async resolveUser(guild, userInput) {
        if (!userInput) return null;

        // Remove mentions and get ID
        const userId = userInput.replace(/[<@!>]/g, '');
        
        // Try to get by ID first
        if (/^\d+$/.test(userId)) {
            try {
                return await guild.members.fetch(userId);
            } catch (error) {
                // Try to get user from client if not in guild
                try {
                    return await this.client.users.fetch(userId);
                } catch (e) {
                    return null;
                }
            }
        }

        // Try to find by username or display name
        const members = await guild.members.fetch();
        return members.find(member => 
            member.user.username.toLowerCase() === userInput.toLowerCase() ||
            member.displayName.toLowerCase() === userInput.toLowerCase()
        );
    }

    // Helper function to parse time (e.g., "1h", "30m", "7d")
    parseTime(timeStr) {
        if (!timeStr) return null;
        
        const match = timeStr.match(/^(\d+)([smhd])$/i);
        if (!match) return null;

        const [, amount, unit] = match;
        const multipliers = {
            's': 1000,
            'm': 60 * 1000,
            'h': 60 * 60 * 1000,
            'd': 24 * 60 * 60 * 1000
        };

        return parseInt(amount) * multipliers[unit.toLowerCase()];
    }

    // Check if user has required permissions
    hasPermission(member, permission) {
        return member.permissions.has(permission);
    }

    // Create error embed
    createErrorEmbed(message) {
        return new EmbedBuilder()
            .setColor('#FF0000')
            .setTitle('❌ Error')
            .setDescription(message);
    }

    // Create success embed
    createSuccessEmbed(message) {
        return new EmbedBuilder()
            .setColor('#00FF00')
            .setTitle('✅ Success')
            .setDescription(message);
    }

    // BAN COMMAND
    async ban(message, args, silent = false) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.BanMembers)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to ban members.')] });
        }

        const userInput = args[0];
        const reason = args.slice(1).join(' ') || 'No reason provided';

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        try {
            await message.guild.members.ban(target.id, { reason: `${reason} | Banned by ${message.author.tag}` });
            
            if (!silent) {
                await message.reply({ 
                    embeds: [this.createSuccessEmbed(`Successfully banned ${target.user ? target.user.tag : target.tag}\nReason: ${reason}`)] 
                });
            }
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to ban user: ${error.message}`)] });
        }
    }

    // TEMPORARY BAN COMMAND
    async tban(message, args, silent = false) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.BanMembers)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to ban members.')] });
        }

        const userInput = args[0];
        const timeStr = args[1];
        const reason = args.slice(2).join(' ') || 'No reason provided';

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        const duration = this.parseTime(timeStr);
        if (!duration) {
            return message.reply({ embeds: [this.createErrorEmbed('Invalid time format. Use format like: 1h, 30m, 7d')] });
        }

        try {
            await message.guild.members.ban(target.id, { reason: `Temporary ban: ${reason} | Banned by ${message.author.tag}` });
            
            const unbanTime = Date.now() + duration;
            this.bannedUsers.set(target.id, { guildId: message.guild.id, unbanTime });

            setTimeout(async () => {
                try {
                    await message.guild.members.unban(target.id, 'Temporary ban expired');
                    this.bannedUsers.delete(target.id);
                } catch (error) {
                    console.error('Failed to auto-unban user:', error);
                }
            }, duration);

            if (!silent) {
                await message.reply({ 
                    embeds: [this.createSuccessEmbed(`Successfully temp-banned ${target.user ? target.user.tag : target.tag} for ${timeStr}\nReason: ${reason}`)] 
                });
            }
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to temp-ban user: ${error.message}`)] });
        }
    }

    // UNBAN COMMAND
    async unban(message, args) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.BanMembers)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to unban members.')] });
        }

        const userInput = args[0];
        const reason = args.slice(1).join(' ') || 'No reason provided';

        try {
            await message.guild.members.unban(userInput.replace(/[<@!>]/g, ''), `${reason} | Unbanned by ${message.author.tag}`);
            this.bannedUsers.delete(userInput.replace(/[<@!>]/g, ''));
            
            await message.reply({ 
                embeds: [this.createSuccessEmbed(`Successfully unbanned user\nReason: ${reason}`)] 
            });
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to unban user: ${error.message}`)] });
        }
    }

    // KICK COMMAND
    async kick(message, args, silent = false) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.KickMembers)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to kick members.')] });
        }

        const userInput = args[0];
        const reason = args.slice(1).join(' ') || 'No reason provided';

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        try {
            await target.kick(`${reason} | Kicked by ${message.author.tag}`);
            
            if (!silent) {
                await message.reply({ 
                    embeds: [this.createSuccessEmbed(`Successfully kicked ${target.user.tag}\nReason: ${reason}`)] 
                });
            }
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to kick user: ${error.message}`)] });
        }
    }

    // MUTE COMMAND
    async mute(message, args, silent = false) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.ModerateMembers)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to mute members.')] });
        }

        const userInput = args[0];
        const reason = args.slice(1).join(' ') || 'No reason provided';

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        try {
            await target.timeout(28 * 24 * 60 * 60 * 1000, `${reason} | Muted by ${message.author.tag}`); // Max timeout
            
            if (!silent) {
                await message.reply({ 
                    embeds: [this.createSuccessEmbed(`Successfully muted ${target.user.tag}\nReason: ${reason}`)] 
                });
            }
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to mute user: ${error.message}`)] });
        }
    }

    // TEMPORARY MUTE COMMAND
    async tmute(message, args, silent = false) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.ModerateMembers)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to mute members.')] });
        }

        const userInput = args[0];
        const timeStr = args[1];
        const reason = args.slice(2).join(' ') || 'No reason provided';

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        const duration = this.parseTime(timeStr);
        if (!duration) {
            return message.reply({ embeds: [this.createErrorEmbed('Invalid time format. Use format like: 1h, 30m, 7d')] });
        }

        try {
            await target.timeout(duration, `Temporary mute: ${reason} | Muted by ${message.author.tag}`);
            
            if (!silent) {
                await message.reply({ 
                    embeds: [this.createSuccessEmbed(`Successfully temp-muted ${target.user.tag} for ${timeStr}\nReason: ${reason}`)] 
                });
            }
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to temp-mute user: ${error.message}`)] });
        }
    }

    // UNMUTE COMMAND
    async unmute(message, args) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.ModerateMembers)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to unmute members.')] });
        }

        const userInput = args[0];
        const reason = args.slice(1).join(' ') || 'No reason provided';

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        try {
            await target.timeout(null, `${reason} | Unmuted by ${message.author.tag}`);
            
            await message.reply({ 
                embeds: [this.createSuccessEmbed(`Successfully unmuted ${target.user.tag}\nReason: ${reason}`)] 
            });
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to unmute user: ${error.message}`)] });
        }
    }

    // PROMOTE COMMAND (Add role)
    async promote(message, args) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.ManageRoles)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to manage roles.')] });
        }

        const userInput = args[0];
        const roleInput = args.slice(1).join(' ');

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        const role = message.guild.roles.cache.find(r => 
            r.name.toLowerCase() === roleInput.toLowerCase() || 
            r.id === roleInput.replace(/[<@&>]/g, '')
        );
        
        if (!role) {
            return message.reply({ embeds: [this.createErrorEmbed('Role not found.')] });
        }

        try {
            await target.roles.add(role, `Promoted by ${message.author.tag}`);
            
            await message.reply({ 
                embeds: [this.createSuccessEmbed(`Successfully promoted ${target.user.tag} to ${role.name}`)] 
            });
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to promote user: ${error.message}`)] });
        }
    }

    // DEMOTE COMMAND (Remove role)
    async demote(message, args) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.ManageRoles)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to manage roles.')] });
        }

        const userInput = args[0];
        const roleInput = args.slice(1).join(' ');

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        const role = message.guild.roles.cache.find(r => 
            r.name.toLowerCase() === roleInput.toLowerCase() || 
            r.id === roleInput.replace(/[<@&>]/g, '')
        );
        
        if (!role) {
            return message.reply({ embeds: [this.createErrorEmbed('Role not found.')] });
        }

        try {
            await target.roles.remove(role, `Demoted by ${message.author.tag}`);
            
            await message.reply({ 
                embeds: [this.createSuccessEmbed(`Successfully demoted ${target.user.tag} from ${role.name}`)] 
            });
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to demote user: ${error.message}`)] });
        }
    }

    // PIN COMMAND
    async pin(message, args) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.ManageMessages)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to manage messages.')] });
        }

        const messageId = args[0];
        if (!messageId) {
            return message.reply({ embeds: [this.createErrorEmbed('Please provide a message ID.')] });
        }

        try {
            const targetMessage = await message.channel.messages.fetch(messageId);
            await targetMessage.pin();
            
            await message.reply({ 
                embeds: [this.createSuccessEmbed('Successfully pinned the message.')] 
            });
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to pin message: ${error.message}`)] });
        }
    }

    // UNPIN COMMAND
    async unpin(message, args) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.ManageMessages)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to manage messages.')] });
        }

        const messageId = args[0];
        if (!messageId) {
            return message.reply({ embeds: [this.createErrorEmbed('Please provide a message ID.')] });
        }

        try {
            const targetMessage = await message.channel.messages.fetch(messageId);
            await targetMessage.unpin();
            
            await message.reply({ 
                embeds: [this.createSuccessEmbed('Successfully unpinned the message.')] 
            });
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to unpin message: ${error.message}`)] });
        }
    }

    // PURGE COMMAND
    async purge(message, args, silent = false) {
        if (!this.hasPermission(message.member, PermissionsBitField.Flags.ManageMessages)) {
            return message.reply({ embeds: [this.createErrorEmbed('You don\'t have permission to manage messages.')] });
        }

        const amount = parseInt(args[0]);
        if (!amount || amount < 1 || amount > 100) {
            return message.reply({ embeds: [this.createErrorEmbed('Please provide a valid number between 1 and 100.')] });
        }

        try {
            const messages = await message.channel.bulkDelete(amount + 1, true); // +1 to include command message
            
            if (!silent) {
                const reply = await message.channel.send({ 
                    embeds: [this.createSuccessEmbed(`Successfully deleted ${messages.size - 1} messages.`)] 
                });
                
                // Delete confirmation message after 5 seconds
                setTimeout(() => reply.delete().catch(() => {}), 5000);
            }
        } catch (error) {
            await message.reply({ embeds: [this.createErrorEmbed(`Failed to purge messages: ${error.message}`)] });
        }
    }

    // ID COMMAND
    async id(message, args) {
        const userInput = args[0];
        
        if (!userInput) {
            // Show command author's ID if no user specified
            const embed = new EmbedBuilder()
                .setColor('#0099FF')
                .setTitle('User ID')
                .addFields(
                    { name: 'User', value: message.author.tag, inline: true },
                    { name: 'ID', value: message.author.id, inline: true }
                )
                .setThumbnail(message.author.displayAvatarURL());
            
            return message.reply({ embeds: [embed] });
        }

        const target = await this.resolveUser(message.guild, userInput);
        if (!target) {
            return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
        }

        const user = target.user || target;
        const embed = new EmbedBuilder()
            .setColor('#0099FF')
            .setTitle('User ID')
            .addFields(
                { name: 'User', value: user.tag, inline: true },
                { name: 'ID', value: user.id, inline: true }
            )
            .setThumbnail(user.displayAvatarURL());

        await message.reply({ embeds: [embed] });
    }

    // INFO COMMAND
    async info(message, args) {
        const userInput = args[0];
        let target = message.member;

        if (userInput) {
            target = await this.resolveUser(message.guild, userInput);
            if (!target) {
                return message.reply({ embeds: [this.createErrorEmbed('User not found.')] });
            }
        }

        const user = target.user || target;
        const member = target.user ? target : await message.guild.members.fetch(target.id).catch(() => null);

        const embed = new EmbedBuilder()
            .setColor('#0099FF')
            .setTitle('User Information')
            .setThumbnail(user.displayAvatarURL())
            .addFields(
                { name: 'Username', value: user.tag, inline: true },
                { name: 'ID', value: user.id, inline: true },
                { name: 'Account Created', value: `<t:${Math.floor(user.createdTimestamp / 1000)}:F>`, inline: false }
            );

        if (member) {
            embed.addFields(
                { name: 'Joined Server', value: `<t:${Math.floor(member.joinedTimestamp / 1000)}:F>`, inline: false },
                { name: 'Roles', value: member.roles.cache.filter(r => r.id !== message.guild.id).map(r => r.toString()).join(', ') || 'None', inline: false }
            );
        }

        await message.reply({ embeds: [embed] });
    }

    // Command handler
    async handleCommand(message, command, args) {
        const commands = {
            // Regular commands
            'ban': () => this.ban(message, args),
            'tban': () => this.tban(message, args),
            'unban': () => this.unban(message, args),
            'kick': () => this.kick(message, args),
            'mute': () => this.mute(message, args),
            'tmute': () => this.tmute(message, args),
            'unmute': () => this.unmute(message, args),
            'promote': () => this.promote(message, args),
            'demote': () => this.demote(message, args),
            'pin': () => this.pin(message, args),
            'unpin': () => this.unpin(message, args),
            'purge': () => this.purge(message, args),
            'id': () => this.id(message, args),
            'info': () => this.info(message, args),

            // Silent commands
            'sban': () => this.ban(message, args, true),
            'stban': () => this.tban(message, args, true),
            'skick': () => this.kick(message, args, true),
            'smute': () => this.mute(message, args, true),
            'stmute': () => this.tmute(message, args, true),
            'spurge': () => this.purge(message, args, true)
        };

        const commandFunction = commands[command.toLowerCase()];
        if (commandFunction) {
            await commandFunction();
        }
    }
}

module.exports = AdminTools;
