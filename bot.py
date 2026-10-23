import os
import discord
import requests
from flask import Flask
from threading import Thread
import asyncio

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

ROLE_MAPPING = {
    "Schichtführer": "Schichtführer",
    "Vorarbeiter": "Vorarbeiter",
    "Stammbelegschaft": "Stammbelegschaft",
    "Aushilfe": "Aushilfe"
}

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

def determine_guild_role(member):
    role_names = [role.name for role in member.roles]
    for role_key in ["Schichtführer", "Vorarbeiter", "Stammbelegschaft", "Aushilfe"]:
        if role_key in role_names:
            return ROLE_MAPPING[role_key]
    return "Fremder"

async def perform_full_sync():
    print(">>> Starte Full Sync aller Server-Mitglieder...", flush=True)
    all_members_data = []

    for guild in client.guilds:
        if not guild.chunked:
            print(f">>> Lade Mitglieder-Cache für Gilde: {guild.name}", flush=True)
            await guild.chunk(cache=True)
            
        for member in guild.members:
            if not member.bot:
                role = determine_guild_role(member)
                all_members_data.append({
                    "discord_id": str(member.id),
                    "display_name": member.display_name,
                    "username": member.name,
                    "gild_rolle": role,
                    "status": "Aktiv"
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
    print(f">>> User beigetreten: {member.display_name} -> Trigger Full Sync", flush=True)
    await perform_full_sync()

@client.event
async def on_member_remove(member):
    print(f">>> User hat verlassen: {member.display_name} -> Trigger Full Sync", flush=True)
    await perform_full_sync()

@client.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        print(f">>> Rollenänderung bei {after.display_name} -> Trigger Full Sync", flush=True)
        await perform_full_sync()

if __name__ == "__main__":
    keep_alive()
    client.run(BOT_TOKEN)
