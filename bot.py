import os
import discord
import requests
import aiohttp

from flask import Flask
from threading import Thread
import asyncio
from datetime import datetime

# --- MINI WEB-SERVER (Keep-Alive für Render) ---
app = Flask('')

@app.route('/')
def home():
    return "Nachtschicht Bot ist online und aktiv!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD BOT KONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEB_APP_URL = os.environ.get("WEB_APP_URL")

# Rollen-Hierarchie (Höchste Rolle gewinnt in der Tabelle)
ROLE_HIERARCHY = [
    "Schichtführer",
    "Vorarbeiter",
    "Einsatzleiter",
    "Stammbelegschaft",
    "Aushilfe",
    "Neuling"
]

intents = discord.Intents.default()
intents.members = True  # Notwendig, um Mitglieder-Listen und Joins/Leaves zu erfassen
client = discord.Client(intents=intents)

def determine_guild_role(member):
    role_names = [role.name for role in member.roles]
    for role_key in ROLE_HIERARCHY:
        if role_key in role_names:
            return role_key
    return "Fremder"

def check_raid_status(member):
    role_names = [role.name for role in member.roles]
    if "Raid Ja" in role_names:
        return "Ja"
    return "Nein"

async def send_event_update(data):
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, lambda: requests.post(WEB_APP_URL, json=data, timeout=10)
        )
        print(f">>> Event-Update gesendet. Status: {response.status_code}", flush=True)
    except Exception as e:
        print(f">>> FEHLER beim Event-Update: {e}", flush=True)

async def perform_full_sync():
    print(">>> Starte Full Sync aller Server-Mitglieder...", flush=True)
    all_members_data = []

    for guild in client.guilds:
        async for member in guild.fetch_members(limit=None):
            if not member.bot:
                role = determine_guild_role(member)
                raid_status = check_raid_status(member)
                join_date = member.joined_at.strftime('%Y-%m-%d') if member.joined_at else ""

                all_members_data.append({
                    "discord_id": str(member.id),
                    "display_name": member.display_name,
                    "username": member.name,
                    "gild_rolle": role,
                    "status": "Aktiv",
                    "raid_check": raid_status,
                    "join_date": join_date,
                    "leave_date": ""
                })

    print(f">>> {len(all_members_data)} Mitglieder gesammelt. Sende an Google Sheets...", flush=True)

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, lambda: requests.post(WEB_APP_URL, json=all_members_data, timeout=15)
        )
        print(f">>> Full Sync erfolgreich! Server-Response: {response.status_code}", flush=True)
    except requests.exceptions.Timeout:
        print(">>> FEHLER: Google Apps Script Timeout nach 15 Sekunden.", flush=True)
    except Exception as e:
        print(f">>> FEHLER beim Full Sync zu Google Sheets: {e}", flush=True)

@client.event
async def on_ready():
    print(f">>> Bot erfolgreich angemeldet als {client.user}", flush=True)
    await perform_full_sync()

@client.event
async def on_member_join(member):
    print(f">>> User beigetreten: {member.display_name} -> Warte 5s auf Auto-Role...", flush=True)
    await asyncio.sleep(5)
    
    role = determine_guild_role(member)
    raid_status = check_raid_status(member)
    join_date = member.joined_at.strftime('%Y-%m-%d') if member.joined_at else datetime.now().strftime('%Y-%m-%d')
    
    data = {
        "discord_id": str(member.id),
        "display_name": member.display_name,
        "username": member.name,
        "gild_rolle": role,
        "status": "Aktiv",
        "raid_check": raid_status,
        "join_date": join_date,
        "leave_date": ""
    }
    await send_event_update(data)

@client.event
async def on_member_remove(member):
    print(f">>> User hat den Server verlassen: {member.display_name}", flush=True)
    leave_date = datetime.now().strftime('%Y-%m-%d')
    status = "Leave"
    
    try:
        async for entry in member.guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
            if entry.target and entry.target.id == member.id:
                if (discord.utils.utcnow() - entry.created_at).total_seconds() < 15:
                    status = "Kick"
                    break
    except Exception as e:
        print(f"Audit-Log Prüfung fehlgeschlagen (Vermutlich fehlende Bot-Berechtigungen): {e}")

    data = {
        "discord_id": str(member.id),
        "display_name": member.display_name,
        "username": member.name,
        "gild_rolle": determine_guild_role(member),
        "status": status,
        "raid_check": check_raid_status(member),
        "join_date": member.joined_at.strftime('%Y-%m-%d') if member.joined_at else "",
        "leave_date": leave_date
    }
    await send_event_update(data)

@client.event
async def on_member_ban(guild, user):
    print(f">>> User wurde gebannt: {user.name}", flush=True)
    leave_date = datetime.now().strftime('%Y-%m-%d')
    data = {
        "discord_id": str(user.id),
        "display_name": getattr(user, 'display_name', user.name),
        "username": user.name,
        "gild_rolle": "Fremder",
        "status": "Ban",
        "raid_check": "Nein",
        "join_date": "",
        "leave_date": leave_date
    }
    await send_event_update(data)

@client.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        print(f">>> Rollenänderung bei {after.display_name} -> Update", flush=True)
        role = determine_guild_role(after)
        raid_status = check_raid_status(after)
        join_date = after.joined_at.strftime('%Y-%m-%d') if after.joined_at else ""
        
        data = {
            "discord_id": str(after.id),
            "display_name": after.display_name,
            "username": after.name,
            "gild_rolle": role,
            "status": "Aktiv",
            "raid_check": raid_status,
            "join_date": join_date,
            "leave_date": ""
        }
        await send_event_update(data)

if __name__ == "__main__":
    keep_alive()
    client.run(BOT_TOKEN)

from discord.ext import commands

# Deine Google Apps Script Web-App URL hier einfügen:
import aiohttp
import discord
from discord.ext import commands

APPS_SCRIPT_URL = "DEINE_APPS_SCRIPT_WEBAPP_URL_HIER"

@bot.tree.command(name="skz", description="Zeigt deinen aktuellen SKZ Punktestand und deinen gesamten Verlauf an.")
async def skz(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    user_id = str(interaction.user.id)
    url = f"{APPS_SCRIPT_URL}?discord_id={user_id}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("status") == "success":
                    punkte = data.get("punkte", 0)
                    history = data.get("history", [])
                    
                    embed = discord.Embed(
                        title=f"🏆 Deine SKZ Punkte: {punkte}",
                        description="Hier ist deine persönliche Übersicht und Historie:",
                        color=discord.Color.blue()
                    )
                    
                    if history:
                        history_text = ""
                        for item in history:
                            vorzeichen = "+" if item['punkte'] > 0 else ""
                            line = f"• **{item['datum']}**: `{vorzeichen}{item['punkte']} SKZ` – {item['grund']} *(von {item['von']})*\n"
                            
                            # Schutz vor Discord Nachrichtengrößen-Limit (max 1024 Zeichen pro Feld)
                            if len(history_text) + len(line) > 1000:
                                history_text += "• *... und weitere ältere Einträge.*"
                                break
                            history_text += line
                            
                        embed.add_field(name="📜 Gesamter Verlauf im Log", value=history_text, inline=False)
                    else:
                        embed.add_field(name="📜 Gesamter Verlauf im Log", value="Noch keine Log-Einträge vorhanden.", inline=False)
                        
                    embed.set_footer(text="Nachtschicht Raid-System • Nur für dich sichtbar")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("Fehler beim Abrufen deiner Daten aus dem Sheet.", ephemeral=True)
            else:
                await interaction.followup.send("Verbindung zum Tabellensystem fehlgeschlagen.", ephemeral=True)

@bot.event
async def on_ready():
    # Synchronisiert die Slash-Commands global mit Discord
    await bot.tree.sync()
    print(f"Bot ist eingeloggt als {bot.user} und Slash-Commands wurden synchronisiert!")
