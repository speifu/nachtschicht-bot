import os
import discord
import requests
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
intents.members = True
intents.audit_log = True  # Wichtig, um Kicks zu erkennen!
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
    
    # Prüfen, ob es ein Kick war über die Audit-Logs
    try:
        async for entry in member.guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
            if entry.target and entry.target.id == member.id:
                if (discord.utils.utcnow() - entry.created_at).total_seconds() < 15:
                    status = "Kick"
                    break
    except Exception as e:
        print(f"Audit-Log Prüfung fehlgeschlagen: {e}")

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
        "display_name": user.display_name if hasattr(user, 'display_name') else user.name,
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
