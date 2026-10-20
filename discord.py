import os
import discord
import requests
from flask import Flask
from threading import Thread

# --- MINI WEB-SERVER (Hält den Bot in der Cloud 24/7 wach) ---
app = Flask('')

@app.route('/')
def home():
    return "Nachtschicht Bot ist online und aktiv!"

def run():
    port = int(os.environ.get("PORT", 8080))
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

def sync_member_to_sheets(member, status="Aktiv"):
    role = determine_guild_role(member)
    payload = {
        "discord_id": str(member.id),
        "display_name": member.display_name,
        "username": member.name,
        "gild_rolle": role,
        "status": status
    }
    try:
        response = requests.post(WEB_APP_URL, json=payload)
        print(f"Synced {member.display_name} ({role}) -> {response.status_code}")
    except Exception as e:
        print(f"Fehler beim Sync: {e}")

@client.event
async def on_ready():
    print(f"Bot angemeldet als {client.user}")
    for guild in client.guilds:
        async for member in guild.fetch_members(limit=None):
            if not member.bot:
                sync_member_to_sheets(member, status="Aktiv")
    print("Initialer Sync abgeschlossen!")

@client.event
async def on_member_join(member):
    sync_member_to_sheets(member, status="Aktiv")

@client.event
async def on_member_remove(member):
    sync_member_to_sheets(member, status="Inaktiv")

@client.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        sync_member_to_sheets(after, status="Aktiv")

if __name__ == "__main__":
    keep_alive()
    client.run(BOT_TOKEN)
