# GTNH Server with Discord Bot

A Docker Compose setup for running a GT New Horizons (GTNH) Minecraft server with an integrated Discord bot for remote management.

## Features

- **Containerized GTNH Server**: Using [itzg/minecraft-server](https://github.com/itzg/docker-minecraft-server) with Java 25 support
- **Discord Bot Integration**: Control your server from Discord with slash commands
- **Chat Bridge**: Bidirectional chat between Discord and Minecraft
- **Backup Management**: Create and restore backups via Discord commands
- **Access Control**: Whitelist specific users or roles for bot access

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Podman Network                           │
│                                                             │
│  ┌─────────────────┐         ┌─────────────────────┐       │
│  │  GTNH Server    │  RCON   │  Discord Bot        │       │
│  │  (mc)           │◄───────►│  (discord-bot)      │       │
│  │                 │         │                     │       │
│  │  Port: 25565    │         │  - Server Control   │       │
│  │  Java 25        │         │  - Chat Bridge      │       │
│  └─────────────────┘         │  - Backup Mgmt      │       │
│                              └─────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
              │                          │
              ▼                          ▼
        Minecraft               Discord API
        Clients
```

## Quick Start

### 1. Prerequisites

- Docker or Podman installed
- A Discord Bot Token ([setup guide](discord-bot/README.md#prerequisites))
- GTNH Server ZIP file

### 2. Download GTNH Server

1. Go to [gtnewhorizons.com/downloads](https://www.gtnewhorizons.com/downloads/)
2. Download the **Server** version for Java 17-25 (e.g., `GT_New_Horizons_2.8.1_Server_Java_17-25.zip`)
3. Place the ZIP file in the `modpacks/` folder

### 3. Configure

1. Copy the example environment file and edit with your values:

    ```bash
    cp .env.example .env
    ```

3. Edit `.env` with your configuration:
   - `CF_SERVER_MOD_FILENAME` - Your GTNH server ZIP filename
   - `DISCORD_TOKEN` - Your Discord bot token
   - `RCON_PASSWORD` - A secure password for RCON
   - `ALLOWED_USERS` - Your Discord user ID

### 4. Start Services

  ```bash
  # Using Podman
  podman compose up -d --build

  # Using Docker
  docker compose up -d --build
  ```

First startup will take several minutes as GTNH extracts and configures.

### 5. First-Run Configuration

After the first extraction, you need to rename the server start scripts in `./data/`:

```bash
cd data
mv startserver-java9.sh ServerStart.sh
```

Optionally, edit `ServerStart.sh` to customize Java settings:

```bash
# Example optimized settings:
java -XX:+UseCompactObjectHeaders -Xms10G -Xmx10G -Dfml.readTimeout=180 @java9args.txt -Dfml.queryResult=confirm -jar lwjgl3ify-forgePatches.jar nogui
```

Key options:
- `-XX:+UseCompactObjectHeaders` - Reduces memory usage (Java 25 only)
- `-Xms10G -Xmx10G` - Set min/max memory (adjust based on your system)
- `-Dfml.queryResult=confirm` - Auto-confirm missing blocks on version updates

After making changes, restart the server:

```bash
podman compose restart mc
```

### 6. Verify

- The server will be available at `localhost:25565`
- The Discord bot should appear online
- Use `/status` in Discord to check the connection

## Configuration Reference

All configuration is done via the `.env` file. Copy `env.example` to `.env` and edit.

| Variable | Description | Default |
|:---------|:------------|:--------|
| `CF_SERVER_MOD_FILENAME` | GTNH server ZIP filename in `./modpacks/` | Required |
| `DISCORD_TOKEN` | Bot token from Discord Developer Portal | Required |
| `RCON_PASSWORD` | Shared password for RCON communication | Required |
| `ALLOWED_USERS` | Comma-separated Discord User IDs | `""` |
| `ALLOWED_ROLES` | Comma-separated Discord Role IDs | `""` |
| `DISABLE_WHITELIST` | Allow anyone to use bot commands | `false` |
| `BRIDGE_CHANNEL_ID` | Channel for Minecraft ↔ Discord chat | `0` (disabled) |
| `COMMAND_CHANNEL_ID` | Restrict commands to specific channel | `0` (any) |

## Discord Commands

| Command | Description |
|:--------|:------------|
| `/status` | Check server status and online players |
| `/start` | Start the GTNH server |
| `/stop` | Gracefully stop the server |
| `/restart` | Restart the server |
| `/players` | List online players |
| `/say <message>` | Send message to server chat |
| `/cmd <command>` | Execute any server command |
| `/logs [lines]` | View recent server logs |
| `/save` | Trigger server backup |
| `/load <file>` | Restore from backup |
| `/help` | Show help menu |

## Directory Structure

```
demo/
├── compose.yaml          # Podman/Docker Compose configuration
├── .env                  # Your configuration (create from .env.example)
├── .env.example          # Environment variable template
├── LICENSE               # MIT License
├── README.md             # This file
├── modpacks/             # Place GTNH server ZIP here
│   └── GT_New_Horizons_X.X.X_Server_Java_17-25.zip
├── data/                 # Server data (created on first run)
│   ├── World/            # World save files
│   ├── backups/          # Server backups
│   ├── config/           # GTNH configuration
│   └── ...
└── discord-bot/
    ├── bot.py            # Discord bot source code
    ├── Dockerfile        # Bot container build file
    ├── requirements.txt  # Python dependencies
    └── README.md         # Bot-specific documentation
```

## Common Operations

### View Server Logs

```bash
podman compose logs -f mc
```

### Access Server Console

```bash
docker attach mc-server
# Detach with Ctrl+P, Ctrl+Q
```

### Update GTNH Version

It is recommended to update **one major version at a time** (e.g., 2.6 → 2.7 → 2.8).
See the [GTNH Migration Guide](https://gtnh.miraheze.org/wiki/Installing_and_Migrating) for details.

1. **Backup your current data:**

    ```bash
    podman compose stop mc
    tar -czvf backup-pre-update-$(date +%Y%m%d).tar.gz data/
    ```

2. **Download the new server ZIP** from [gtnewhorizons.com/downloads](https://www.gtnewhorizons.com/downloads/) and place in `modpacks/`

3. **Save these folders/files** from `./data/` (copy elsewhere temporarily):
   - `World/` - World save data
   - `backups/` - Server backups
   - `journeymap/` - Map data
   - `visualprospecting/` - Ore vein data
   - `serverutilities/` - Permissions, ranks, chunk loading

4. **Delete and let the new version regenerate:**
   - `config/`
   - `mods/`
   - `scripts/` (if exists)
   - `resources/` (if exists)

5. **Update `.env`** with the new ZIP filename:

    ```
    CF_SERVER_MOD_FILENAME=GT_New_Horizons_X.X.X_Server_Java_17-25.zip
    ```

6. **Start with fresh extraction:**

    ```bash
    podman compose up -d
    ```

7. **Restore your saved folders** back into `./data/` after the server initializes

8. **Re-apply any custom config changes** you made before the migration (e.g., `server.properties`, files in `config/`)

### Manual Backup

Server data is stored in `./data/`. To backup manually:

```bash
# Stop server first for consistency
podman compose stop mc

# Create backup
tar -czvf backup-$(date +%Y%m%d).tar.gz data/

# Restart server
podman compose start mc
```

## Troubleshooting

### Server takes forever to start

GTNH is a large modpack. First startup can take 5-10+ minutes. Check logs:

```bash
podman compose logs -f mc
```

### Out of memory errors

GTNH requires significant RAM. Edit `./data/ServerStart.sh` to adjust memory:

```bash
# Change -Xms and -Xmx values (e.g., 8G, 10G, 12G)
java -XX:+UseCompactObjectHeaders -Xms8G -Xmx8G -Dfml.readTimeout=180 @java9args.txt -jar lwjgl3ify-forgePatches.jar nogui
```

Then restart the server: `podman compose restart mc`

### Bot can't connect to RCON

- Ensure `RCON_PASSWORD` matches in both services
- Wait for server to fully start (GTNH takes time)
- Verify `ENABLE_RCON: "true"` is set
