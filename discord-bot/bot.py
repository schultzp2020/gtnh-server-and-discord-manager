import re
import os
import asyncio
import socket
import struct
import datetime
import zipfile
import shutil
import discord
from discord import app_commands
from discord.ext import commands, tasks
import docker

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION (loaded from environment variables)
# ═══════════════════════════════════════════════════════════════
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
RCON_HOST = os.environ.get("RCON_HOST", "mc")
RCON_PORT = int(os.environ.get("RCON_PORT", "25575"))
RCON_PASSWORD = os.environ.get("RCON_PASSWORD", "")
MC_CONTAINER = os.environ.get("MC_CONTAINER", "mc-server")
ALLOWED_USERS = [int(x) for x in os.environ.get(
    "ALLOWED_USERS", "").split(",") if x]
ALLOWED_ROLES = [int(x) for x in os.environ.get(
    "ALLOWED_ROLES", "").split(",") if x]
DISABLE_WHITELIST = os.environ.get(
    "DISABLE_WHITELIST", "false").lower() == "true"
BRIDGE_CHANNEL_ID = int(os.environ.get("BRIDGE_CHANNEL_ID", "0"))
COMMAND_CHANNEL_ID = int(os.environ.get("COMMAND_CHANNEL_ID", "0"))

# Paths
MINECRAFT_DATA_DIR = os.environ.get("MINECRAFT_DATA_DIR", "/minecraft-data")
BACKUPS_DIR = os.environ.get(
    "BACKUPS_DIR", os.path.join(MINECRAFT_DATA_DIR, "backups"))

# ═══════════════════════════════════════════════════════════════
# BOT SETUP
# ═══════════════════════════════════════════════════════════════
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
docker_client = docker.from_env()

# Chat regex: [12:34:56] [Server thread/INFO] [minecraft/DedicatedServer]: <PlayerName> Message
# Adjusted to be more flexible for different server versions
# Generic regex to capture any "INFO: <Player> Message" pattern, ignoring timestamp/thread info
CHAT_REGEX = re.compile(r"INFO\]: <(.*?)> (.*)")

# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════


def get_backups():
    """List ZIP files in the backup directory, sorted by modification time (newest first)."""
    if not os.path.exists(BACKUPS_DIR):
        return []

    backups = []
    for f in os.listdir(BACKUPS_DIR):
        if f.endswith(".zip"):
            path = os.path.join(BACKUPS_DIR, f)
            backups.append((f, os.path.getmtime(path)))

    # Sort by time descending
    backups.sort(key=lambda x: x[1], reverse=True)
    return [b[0] for b in backups]


class SimpleRCON:
    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.socket = None
        self.request_id = 0

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(5)
        self.socket.connect((self.host, self.port))
        self._send(3, self.password)

    def disconnect(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def _send(self, type, payload):
        if not self.socket:
            raise ConnectionError("Not connected")

        self.request_id += 1
        # Packet format: Length (4), Request ID (4), Type (4), Payload (N), Padding (2)
        # Types: 3=Login, 2=Command, 0=Response
        data = struct.pack('<ii', self.request_id, type) + \
            payload.encode('utf-8') + b'\x00\x00'
        length = struct.pack('<i', len(data))
        self.socket.send(length + data)

        return self._read()

    def _read(self):
        # Read length
        length_data = self._recv_exact(4)
        length = struct.unpack('<i', length_data)[0]

        # Read packet data
        data = self._recv_exact(length)
        req_id, type = struct.unpack('<ii', data[:8])
        payload = data[8:-2].decode('utf-8')

        return payload

    def _recv_exact(self, n):
        data = b''
        while len(data) < n:
            chunk = self.socket.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        return data

    def command(self, cmd):
        return self._send(2, cmd)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()


async def is_authorized(interaction: discord.Interaction) -> bool:
    """Check if user is allowed to run commands."""
    # Check if commands are restricted to a specific channel
    if COMMAND_CHANNEL_ID != 0 and interaction.channel_id != COMMAND_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ Commands can only be used in <#{COMMAND_CHANNEL_ID}>", ephemeral=True)
        return False

    if DISABLE_WHITELIST:
        return True
    if interaction.user.id in ALLOWED_USERS:
        return True

    # Check roles
    if isinstance(interaction.user, discord.Member):
        user_role_ids = [role.id for role in interaction.user.roles]
        if any(role_id in ALLOWED_ROLES for role_id in user_role_ids):
            return True

    await interaction.response.send_message("❌ You are not authorized to run this command.", ephemeral=True)
    return False


def get_container():
    try:
        return docker_client.containers.get(MC_CONTAINER)
    except docker.errors.NotFound:
        return None


def is_server_running() -> bool:
    container = get_container()
    return container is not None and container.status == "running"


def send_rcon_command(command: str) -> str:
    try:
        print(f"DEBUG: Sending RCON command: {command}")
        with SimpleRCON(RCON_HOST, RCON_PORT, RCON_PASSWORD) as mcr:
            response = mcr.command(command)
            print(f"DEBUG: RCON Response: {response}")
            return response if response else "Command sent."
    except Exception as e:
        print(f"DEBUG: RCON Error: {e}")
        return f"RCON Error: {e}"


async def wait_for_server_ready(timeout: int = 180) -> bool:
    for _ in range(timeout):
        try:
            with SimpleRCON(RCON_HOST, RCON_PORT, RCON_PASSWORD) as mcr:
                mcr.command("list")
                return True
        except:
            await asyncio.sleep(1)
    return False

# ═══════════════════════════════════════════════════════════════
# BOT EVENTS
# ═══════════════════════════════════════════════════════════════


@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    if BRIDGE_CHANNEL_ID != 0:
        if not chat_bridge.is_running():
            chat_bridge.start()
        print(f"✅ Chat bridge enabled for channel {BRIDGE_CHANNEL_ID}")
    else:
        print("⚠️ BRIDGE_CHANNEL_ID not set. Chat bridge disabled.")

    if COMMAND_CHANNEL_ID != 0:
        print(f"✅ Commands restricted to channel {COMMAND_CHANNEL_ID}")

    # Start streaming logs
    bot.loop.create_task(stream_logs())


@bot.event
async def on_message(message):
    """Handle incoming messages for chat bridge."""
    if message.author == bot.user:
        return

    # Chat bridge logic (Discord -> Minecraft)
    if BRIDGE_CHANNEL_ID != 0 and message.channel.id == BRIDGE_CHANNEL_ID:
        if message.content:
            if not is_server_running():
                return
            safe_content = message.content.replace("\n", " ").replace('"', "'")
            send_rcon_command(
                f"say [Discord] <{message.author.display_name}> {safe_content}")


@tasks.loop(seconds=2)
async def chat_bridge():
    pass


async def stream_logs():
    await bot.wait_until_ready()
    channel = bot.get_channel(BRIDGE_CHANNEL_ID)
    if not channel:
        return
    while True:
        try:
            container = get_container()
            if not container or container.status != "running":
                await asyncio.sleep(10)
                continue
            await asyncio.to_thread(process_log_stream, container, channel, bot.loop)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Stream error: {e}")
            await asyncio.sleep(5)


def process_log_stream(container, channel, loop):
    try:
        # Use a specialized iterator to handle byte streams and newlines
        log_stream = container.logs(stream=True, follow=True, tail=0)
        buffer = ""

        for chunk in log_stream:
            # Decode chunk to string (handling potential partial multibyte characters is hard here,
            # but utf-8 errors='replace' is safe enough for logs)
            decoded_chunk = chunk.decode('utf-8', errors='replace')
            buffer += decoded_chunk

            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue

                print(f"DEBUG LOG: {line}")

                # Skip RCON/Discord echo messages to avoid loops
                if "[Rcon]" in line or "[Discord]" in line:
                    continue

                match = CHAT_REGEX.search(line)
                if match:
                    player, message = match.groups()
                    print(
                        f"DEBUG: Matched Chat - Player: {player}, Msg: {message}")
                    if player == "Discord":
                        continue
                    asyncio.run_coroutine_threadsafe(
                        channel.send(f"**<{player}>** {message}"), loop)
    except Exception as e:
        print(f"Log stream interrupted: {e}")

# ═══════════════════════════════════════════════════════════════
# SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════


@bot.tree.command(name="status", description="Check if the server is running")
async def status(interaction: discord.Interaction):
    if not await is_authorized(interaction):
        return

    if is_server_running():
        await interaction.response.defer()
        try:
            # Run RCON in executor to avoid blocking
            response = await asyncio.to_thread(send_rcon_command, "list")
            await interaction.followup.send(f"✅ **Server is ONLINE**\n```{response}```")
        except Exception as e:
            await interaction.followup.send("✅ **Server is ONLINE** (RCON unavailable)")
    else:
        await interaction.response.send_message("❌ **Server is OFFLINE**")


@bot.tree.command(name="start", description="Start the Minecraft server")
async def start(interaction: discord.Interaction):
    if not await is_authorized(interaction):
        return

    if is_server_running():
        await interaction.response.send_message("⚠️ Server is already running!")
        return

    container = get_container()
    if container is None:
        await interaction.response.send_message("❌ Container not found.")
        return

    await interaction.response.send_message("🚀 Starting server...")
    try:
        container.start()
        message = await interaction.original_response()
        await message.edit(content="⏳ Server is starting. This may take a few minutes...")

        if await wait_for_server_ready(timeout=300):
            await message.edit(content="✅ **Server is now ONLINE and ready!**")
        else:
            await message.edit(content="⚠️ Server started but taking longer than expected.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to start: {e}")


@bot.tree.command(name="stop", description="Stop the Minecraft server gracefully")
async def stop(interaction: discord.Interaction):
    if not await is_authorized(interaction):
        return

    if not is_server_running():
        await interaction.response.send_message("⚠️ Server is not running!")
        return

    await interaction.response.send_message("🛑 Stopping server...")
    try:
        container = get_container()
        # Use container stop which triggers graceful shutdown with autosave
        await asyncio.to_thread(container.stop, timeout=120)

        message = await interaction.original_response()
        await message.edit(content="✅ **Server stopped successfully!**")
    except Exception as e:
        await interaction.followup.send(f"❌ Error stopping server: {e}")


@bot.tree.command(name="restart", description="Restart the Minecraft server")
async def restart(interaction: discord.Interaction):
    if not await is_authorized(interaction):
        return

    await interaction.response.send_message("🔄 Restarting server...")
    container = get_container()
    if not container:
        await interaction.followup.send("❌ Container not found.")
        return

    try:
        if is_server_running():
            message = await interaction.original_response()
            await message.edit(content="🛑 Stopping server gracefully...")

            # Use container stop which triggers graceful shutdown with autosave
            await asyncio.to_thread(container.stop, timeout=120)

        message = await interaction.original_response()
        await message.edit(content="🚀 Starting server...")
        container.start()

        if await wait_for_server_ready(timeout=300):
            await message.edit(content="✅ **Server restarted and ready!**")
        else:
            await message.edit(content="⚠️ Restart in progress but taking longer than expected.")
    except Exception as e:
        await interaction.followup.send(f"❌ Restart failed: {e}")


@bot.tree.command(name="say", description="Send a message to the server")
async def say(interaction: discord.Interaction, message: str):
    if not await is_authorized(interaction):
        return

    if not is_server_running():
        await interaction.response.send_message("❌ Server is not running!")
        return

    await asyncio.to_thread(send_rcon_command, f"say [Discord] {interaction.user.display_name}: {message}")
    await interaction.response.send_message(f"💬 Message sent!")


@bot.tree.command(name="cmd", description="Execute a server command")
async def cmd(interaction: discord.Interaction, command: str):
    if not await is_authorized(interaction):
        return

    if not is_server_running():
        await interaction.response.send_message("❌ Server is not running!")
        return

    await interaction.response.defer()
    response = await asyncio.to_thread(send_rcon_command, command)
    if len(response) > 1900:
        response = response[:1900] + "..."
    await interaction.followup.send(f"```\n{response}\n```")


@bot.tree.command(name="players", description="List online players")
async def players(interaction: discord.Interaction):
    if not await is_authorized(interaction):
        return

    if not is_server_running():
        await interaction.response.send_message("❌ Server is not running!")
        return

    await interaction.response.defer()
    response = await asyncio.to_thread(send_rcon_command, "list")
    await interaction.followup.send(f"👥 **Online Players:**\n```{response}```")


@bot.tree.command(name="logs", description="Show recent server logs")
async def logs(interaction: discord.Interaction, lines: int = 20):
    if not await is_authorized(interaction):
        return

    container = get_container()
    if not container:
        await interaction.response.send_message("❌ Container not found.")
        return

    await interaction.response.defer()
    try:
        log_output = container.logs(tail=lines).decode("utf-8")
        if len(log_output) > 1900:
            log_output = log_output[-1900:]
        await interaction.followup.send(f"📜 **Last {lines} log lines:**\n```\n{log_output}\n```")
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching logs: {e}")


@bot.tree.command(name="save", description="Trigger a server save/backup")
async def save(interaction: discord.Interaction):
    if not await is_authorized(interaction):
        return

    if not is_server_running():
        await interaction.response.send_message("❌ Server is not running!")
        return

    await interaction.response.defer()
    await interaction.followup.send("💾 Starting backup...")
    response = await asyncio.to_thread(send_rcon_command, "backup start")
    await interaction.followup.send(f"✅ **Backup triggered!**\n```{response}```")


@bot.tree.command(name="load", description="Restore a server backup")
@app_commands.describe(backup_file="The backup ZIP file to restore")
async def load(interaction: discord.Interaction, backup_file: str):
    if not await is_authorized(interaction):
        return

    backup_path = os.path.join(BACKUPS_DIR, backup_file)
    if not os.path.exists(backup_path):
        await interaction.response.send_message(f"❌ Backup file not found: `{backup_file}`", ephemeral=True)
        return

    await interaction.response.send_message("⏳ **Restoring backup...** This will stop the server.")

    # 1. Stop Server
    try:
        if is_server_running():
            await interaction.edit_original_response(content="🛑 Stopping server gracefully...")

            # Use container stop which triggers graceful shutdown with autosave
            container = get_container()
            await asyncio.to_thread(container.stop, timeout=120)
    except Exception as e:
        await interaction.followup.send(f"❌ Error stopping server: {e}")
        return

    # 2. Create Safety Backup of Current State
    await interaction.edit_original_response(content="💾 Creating temporary backup of current state...")
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        temp_backup_name = f"pre-restore-backup-{timestamp}.zip"
        temp_backup_path = os.path.join(BACKUPS_DIR, temp_backup_name)

        def zip_current_state():
            with zipfile.ZipFile(temp_backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for folder in ["World", "visualprospecting"]:
                    folder_path = os.path.join(MINECRAFT_DATA_DIR, folder)
                    if os.path.exists(folder_path):
                        for root, dirs, files in os.walk(folder_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(
                                    file_path, MINECRAFT_DATA_DIR)
                                zipf.write(file_path, arcname)

        await asyncio.to_thread(zip_current_state)
        await interaction.followup.send(f"✅ Safety backup created: `{temp_backup_name}`")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to create safety backup: {e}. Aborting restore.")
        return

    # 3. Restore Files
    await interaction.edit_original_response(content="📂 Extracting backup...")
    try:
        def restore_files():
            # Delete existing folders
            for folder in ["World", "visualprospecting"]:
                folder_path = os.path.join(MINECRAFT_DATA_DIR, folder)
                if os.path.exists(folder_path):
                    shutil.rmtree(folder_path)

            # Extract zip
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(MINECRAFT_DATA_DIR)

        await asyncio.to_thread(restore_files)
    except Exception as e:
        await interaction.followup.send(f"❌ Restore failed: {e}. Check server data!")
        return

    # 4. Start Server
    await interaction.edit_original_response(content="🚀 Starting server...")
    try:
        container = get_container()
        container.start()
        await interaction.followup.send(f"✅ **Backup `{backup_file}` restored successfully!** Server is booting.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to start server: {e}")


@load.autocomplete("backup_file")
async def load_autocomplete(interaction: discord.Interaction, current: str):
    backups = get_backups()
    return [
        app_commands.Choice(name=b, value=b)
        for b in backups if current.lower() in b.lower()
    ][:25]  # Discord limit is 25 choices


@bot.tree.command(name="help", description="Show help menu")
async def help(interaction: discord.Interaction):
    help_text = """
**🎮 GTNH Discord Server Manager**

**Server Control:**
• `/status` - Check if server is running
• `/start` - Start the server
• `/stop` - Stop the server gracefully
• `/restart` - Restart the server

**Server Interaction:**
• `/players` - List online players
• `/say <message>` - Send a message to the server
• `/cmd <command>` - Execute any server command
• `/logs [lines]` - Show recent server logs (default 20)

**Maintenance:**
• `/save` - Trigger a server backup
• `/load <backup_file>` - Restore a backup (stops server)
• `/help` - Show this message
"""
    await interaction.response.send_message(help_text)


# ═══════════════════════════════════════════════════════════════
# RUN THE BOT
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR: DISCORD_TOKEN environment variable not set!")
        exit(1)

    print("🤖 Starting Discord bot...")
    bot.run(DISCORD_TOKEN)

