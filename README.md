# Claude Code Changelog Telegram Bot

A lightweight Telegram bot that monitors the [Claude Code changelog](https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md) and posts updates to a Telegram channel.

## 🔔 Live Alert Channel

The bot is currently running and posting updates to: **[@ClaudeCodeChangelog](https://t.me/ClaudeCodeChangelog)**

## ✨ Features

- Monitors Claude Code changelog for new versions
- Posts formatted updates to Telegram channel
- Persistent database prevents duplicate notifications
- Graceful shutdown handling
- Automatic retry logic for network issues
- Docker-ready with persistent storage

## 🚀 Quick Start

1. **Clone and setup**
   ```bash
   git clone <repo-url>
   cd claude-changelog-telegram-bot
   cp .env.example .env
   ```

2. **Configure your bot**
   - Create a Telegram bot via [@BotFather](https://t.me/BotFather)
   - Add your bot to your channel as admin
   - Edit `.env` with your credentials:
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=@yourchannel
   ```

3. **Run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

## 📊 Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Required | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Required | Channel username or chat ID |
| `POLL_INTERVAL` | 300 | Check interval in seconds |
| `DATABASE_PATH` | `data/bot.db` | SQLite database location |

## 🛠 Development

Run locally without Docker:
```bash
uv run python -m bot
```
