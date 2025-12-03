# GTNH Discord Bot

A Discord bot for managing your GT New Horizons (GTNH) Minecraft server running in Docker/Podman. It uses the container API to control the container and RCON to send commands to the server.

## Features

- **Server Control**: Start, stop, and restart your Minecraft server from Discord
- **Chat Bridge**: Bidirectional chat between Discord and Minecraft
- **RCON Commands**: Execute any server command remotely
- **Backup Management**: Create and restore server backups
- **Access Control**: Whitelist users/roles who can control the server

## Prerequisites

### 1. Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a "New Application"
3. Go to the **Bot** tab and click "Add Bot"
4. **IMPORTANT**: Under "Privileged Gateway Intents", enable **MESSAGE CONTENT INTENT**
5. Copy your **Token** (you'll need this for configuration)

### 2. Invite Bot to Server

1. Go to **OAuth2** > **URL Generator** tab
2. Select `bot` scope
3. Select permissions: `Send Messages`, `Read Message History`
4. Copy the generated URL and invite the bot to your server

### 3. Get User/Role IDs

1. Enable "Developer Mode" in Discord settings (User Settings > Advanced > Developer Mode)
2. Right-click your user or a role and click "Copy ID"

## Configuration

All configuration is done via environment variables in `compose.yaml`:

| Variable | Description | Default |
|:---------|:------------|:--------|
| `DISCORD_TOKEN` | Your Bot Token from Discord Developer Portal | Required |
| `RCON_PASSWORD` | RCON password (must match server config) | Required |
| `ALLOWED_USERS` | Comma-separated Discord User IDs | `""` |
| `ALLOWED_ROLES` | Comma-separated Discord Role IDs | `""` |
| `DISABLE_WHITELIST` | Set `true` to allow anyone to use the bot | `false` |
| `BRIDGE_CHANNEL_ID` | Channel ID for Minecraft ↔ Discord chat | `0` (disabled) |
| `COMMAND_CHANNEL_ID` | Channel ID for bot commands | `0` (any channel) |
| `MC_CONTAINER` | Name of the Minecraft container | `mc-server` |
| `RCON_HOST` | Hostname of the RCON service | `mc` |
| `RCON_PORT` | RCON port number | `25575` |

## Commands

| Command | Description |
|:--------|:------------|
| `/status` | Check if server is running and see online players |
| `/start` | Start the Minecraft server container |
| `/stop` | Gracefully stop the server |
| `/restart` | Restart the server container |
| `/players` | List online players |
| `/say <message>` | Broadcast a message to server chat |
| `/cmd <command>` | Run any server command |
| `/logs [lines]` | View recent server logs (default 20) |
| `/save` | Trigger a server backup |
| `/load <backup_file>` | Restore a backup (stops server first) |
| `/help` | Show the help menu |

## Troubleshooting

- **"RCON Error: Connection refused"**: Server might still be starting. Wait and try `/status` again.
- **"Not authorized"**: Add your User ID to `ALLOWED_USERS` or get a role in `ALLOWED_ROLES`.
- **Bot doesn't respond**: Ensure `MESSAGE CONTENT INTENT` is enabled in Discord Developer Portal.
- **Container control issues**: Verify the Docker socket is mounted correctly in `compose.yaml`.

