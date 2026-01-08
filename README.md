# Reddit Comment Downvoter Bot

Telegram bot that monitors Reddit posts and automatically downvotes comments from non-whitelisted users using the upvote.biz API.

## Features

- **Auto-monitoring**: Add a post URL and scanning starts automatically
- **Whitelist support**: Excel file + Telegram commands to manage whitelisted users
- **Interactive menus**: Inline keyboard buttons for easy management
- **Real-time notifications**: Get notified when comments are downvoted

## Setup

1. Install dependencies:
```bash
pip install python-telegram-bot python-dotenv pandas openpyxl requests
```

2. Create `.env` file:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
UPVOTE_API_KEY=your_api_key_here
```

3. Run the bot:
```bash
python telegram_bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/add <url>` | Add post to monitor (auto-starts scanner) |
| `/list` | Show monitored posts with remove buttons |
| `/status` | Show balance, stats, scanner status |
| `/stop_monitor` | Stop scanning |
| `/start_monitor` | Resume scanning |
| `/downvote <url>` | Instant one-off downvote |
| `/whitelist <user>` | Add user to whitelist |
| `/unwhitelist <user>` | Remove from whitelist |
| `/showwhitelist` | Show whitelist info |
| `/downvotes <num>` | Set downvotes per comment (min 3) |
| `/interval <sec>` | Set scan interval (min 30s) |

## Files

- `telegram_bot.py` - Main bot
- `api_client.py` - upvote.biz API wrapper
- `reddit_scanner.py` - Reddit comment fetcher
- `config.py` - Configuration
- `data/whitelist.xlsx` - Whitelisted usernames
- `data.json` - Posts, settings, stats (auto-created)

## Whitelist

Users can be whitelisted via:
1. **Excel file**: `data/whitelist.xlsx` (primary list)
2. **Telegram**: `/whitelist <username>` (stored in data.json)

Both sources are combined when checking comments.
