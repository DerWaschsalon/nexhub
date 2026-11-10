"""Kleine Prüfungen rund um Discord-Rechte, die mehrere Module brauchen."""

from __future__ import annotations

import discord


def can_assign(guild: discord.Guild, role: discord.Role) -> bool:
    """Darf und kann der Bot diese Rolle vergeben? (nicht verwaltet, nicht @everyone, unter seiner Rolle)"""
    me = guild.me
    return not role.managed and not role.is_default() and role < me.top_role and me.guild_permissions.manage_roles


def can_send(channel: discord.abc.GuildChannel) -> bool:
    """Darf der Bot in diesem Kanal schreiben?"""
    return channel.permissions_for(channel.guild.me).send_messages
