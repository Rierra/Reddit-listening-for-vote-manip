"""
Reddit Comment Downvoter - Telegram Bot Interface

Control the downvoter from a Telegram group with interactive menus.
"""

import os
import json
import threading
import time
import re
from datetime import datetime, date
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from api_client import UpvoteBizAPI
from reddit_scanner import RedditScanner, RedditComment

# Load environment variables
load_dotenv()

# ============================================
# DATA MANAGEMENT
# ============================================

# For Render: Set DATA_DIR to your disk mount path (e.g., /var/data)
# Only data.json goes there - whitelist.xlsx stays in repo
DATA_DIR = os.getenv("DATA_DIR", ".")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
WHITELIST_EXCEL = "data/whitelist.xlsx"  # Always from repo

def load_whitelist_from_excel() -> set:
    """Load whitelisted usernames from Excel file"""
    try:
        df = pd.read_excel(WHITELIST_EXCEL)
        usernames = df.iloc[:, 0].dropna().astype(str).tolist()
        return {u.strip().lower() for u in usernames if u.strip()}
    except Exception as e:
        print(f"[WARNING] Could not load whitelist from Excel: {e}")
        return set()


def load_data() -> dict:
    """Load data from JSON file"""
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            # Ensure stats has comments_downvoted
            if "comments_downvoted" not in data.get("stats", {}):
                data.setdefault("stats", {})["comments_downvoted"] = 0
            return data
    except FileNotFoundError:
        return {
            "posts": [],
            "whitelist": [],
            "settings": {"downvotes_per_comment": 30, "scan_interval": 60},
            "processed_comments": [],
            "stats": {"total_orders": 0, "orders_today": 0, "comments_downvoted": 0, "last_reset": ""}
        }

def save_data(data: dict):
    """Save data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_full_whitelist() -> set:
    """Get combined whitelist from Excel + JSON"""
    excel_wl = load_whitelist_from_excel()
    data = load_data()
    json_wl = {u.lower() for u in data.get("whitelist", [])}
    return excel_wl | json_wl  # Union of both

def reset_daily_stats_if_needed(data: dict):
    """Reset daily stats if it's a new day"""
    today = date.today().isoformat()
    if data["stats"].get("last_reset") != today:
        data["stats"]["orders_today"] = 0
        data["stats"]["last_reset"] = today
        save_data(data)

def get_post_id(url: str) -> str:
    """Extract post ID from Reddit URL"""
    match = re.search(r'/comments/([a-zA-Z0-9]+)', url)
    return match.group(1) if match else url[-10:]

# ============================================
# BACKGROUND SCANNER
# ============================================

class BackgroundScanner:
    """Background thread that scans Reddit posts"""
    
    def __init__(self, bot_send_message):
        self.api = UpvoteBizAPI()
        self.scanner = RedditScanner()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.send_message = bot_send_message
        self.chat_id = None
    
    def start(self, chat_id: int):
        if self.running:
            return False
        self.running = True
        self.chat_id = chat_id
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return True
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        return True
    
    def _run_loop(self):
        while self.running:
            try:
                data = load_data()
                reset_daily_stats_if_needed(data)
                
                posts = data.get("posts", [])
                print(f"[SCAN] Scanning {len(posts)} posts, whitelist has {len(whitelist)} users")
                # Combined whitelist from Excel + bot-added users
                whitelist = get_full_whitelist()
                settings = data.get("settings", {})
                interval = settings.get("scan_interval", 60)
                downvotes = settings.get("downvotes_per_comment", 30)
                
                self.scanner.processed_comments = set(data.get("processed_comments", []))
                
                for post_url in posts:
                    if not self.running:
                        break
                    
                    new_comments = self.scanner.get_new_comments(post_url, whitelist)
                    print(f"[SCAN] Checked {len(self.scanner.processed_comments)} processed, found {len(new_comments)} new")
                    
                    for comment in new_comments:
                        if not self.running:
                            break
                        
                        response = self.api.downvote_comment(comment.full_url, downvotes)
                        
                        data = load_data()
                        if 'order' in response:
                            data["stats"]["total_orders"] += 1
                            data["stats"]["orders_today"] += 1
                            data["stats"]["comments_downvoted"] = data["stats"].get("comments_downvoted", 0) + 1
                            msg = f"[DOWNVOTED] u/{comment.author}\nOrder #{response['order']}\nDownvotes: {downvotes}"
                        else:
                            msg = f"[FAILED] u/{comment.author}\n{response.get('error', 'Unknown')}"
                        
                        data["processed_comments"].append(comment.id)
                        data["processed_comments"] = data["processed_comments"][-1000:]
                        save_data(data)
                        
                        if self.send_message and self.chat_id:
                            self.send_message(self.chat_id, msg)
                        
                        time.sleep(2)
                
                time.sleep(interval)
                
            except Exception as e:
                print(f"[Scanner Error] {e}")
                time.sleep(30)

# Global scanner instance
scanner_instance: Optional[BackgroundScanner] = None

# ============================================
# TELEGRAM COMMAND HANDLERS
# ============================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    keyboard = [
        [InlineKeyboardButton("Add Post", callback_data="help_add"),
         InlineKeyboardButton("List Posts", callback_data="list_posts")],
        [InlineKeyboardButton("Start Monitor", callback_data="start_mon"),
         InlineKeyboardButton("Stop Monitor", callback_data="stop_mon")],
        [InlineKeyboardButton("Status", callback_data="status"),
         InlineKeyboardButton("Whitelist", callback_data="show_whitelist")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Reddit Comment Downvoter\n\n"
        "Commands:\n"
        "/add <url> - Add post to monitor\n"
        "/list - Show monitored posts\n"
        "/status - Show stats\n"
        "/start_monitor - Start scanning\n"
        "/stop_monitor - Stop scanning\n"
        "/downvote <url> - Instant downvote\n/whitelist <user> - Add to whitelist\n/unwhitelist <user> - Remove\n\n"
        "Or use the buttons below:",
        reply_markup=reply_markup
    )

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add command"""
    if not context.args:
        await update.message.reply_text("Usage: /add <reddit_post_url>")
        return
    
    url = context.args[0]
    
    if not re.match(r'https?://(www\.|old\.)?reddit\.com/r/\w+/comments/\w+', url):
        await update.message.reply_text("Error: Invalid Reddit post URL")
        return
    
    data = load_data()
    if url in data["posts"]:
        await update.message.reply_text("Warning: Post already being monitored")
        return
    
    data["posts"].append(url)
    save_data(data)
    
    # Auto-start scanner if not running
    global scanner_instance
    if not scanner_instance or not scanner_instance.running:
        def sync_send(chat_id, text):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(context.bot.send_message(chat_id=chat_id, text=text))
            except:
                pass
        
        scanner_instance = BackgroundScanner(sync_send)
        scanner_instance.start(update.message.chat_id)
        await update.message.reply_text(f"Added post\n🟢 Scanner started - monitoring {len(data['posts'])} post(s)")
    else:
        await update.message.reply_text(f"Added post\nNow monitoring {len(data['posts'])} post(s)")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command - show posts with remove buttons"""
    data = load_data()
    posts = data.get("posts", [])
    
    if not posts:
        await update.message.reply_text("No posts being monitored\n\nUse /add <url> to add a post")
        return
    
    # Create inline keyboard with remove buttons
    keyboard = []
    for i, post in enumerate(posts):
        post_id = get_post_id(post)
        # Get subreddit name
        match = re.search(r'/r/([^/]+)/', post)
        subreddit = match.group(1) if match else "unknown"
        
        keyboard.append([
            InlineKeyboardButton(f"r/{subreddit} ({post_id})", callback_data=f"view_{i}"),
            InlineKeyboardButton("Remove", callback_data=f"remove_{i}")
        ])
    
    keyboard.append([InlineKeyboardButton("Remove All", callback_data="remove_all")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Monitoring {len(posts)} post(s):\n\nClick Remove to stop monitoring a post:",
        reply_markup=reply_markup
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    global scanner_instance
    
    data = load_data()
    reset_daily_stats_if_needed(data)
    
    running = "🟢 Running" if (scanner_instance and scanner_instance.running) else "🔴 Stopped"
    excel_whitelist = load_whitelist_from_excel()
    
    msg = (
        f"=== Downvoter Status ===\n\n"
        f"Scanner: {running}\n\n"
        f"--- Config ---\n"
        f"Posts monitored: {len(data.get('posts', []))}\n"
        f"Whitelisted: {len(excel_whitelist)}\n"
        f"Downvotes/comment: {data['settings'].get('downvotes_per_comment', 30)}\n"
        f"Scan interval: {data['settings'].get('scan_interval', 60)}s\n\n"
        f"--- Stats ---\n"
        f"Comments downvoted: {data['stats'].get('comments_downvoted', 0)}\n"
        f"Orders today: {data['stats'].get('orders_today', 0)}\n"
        f"Total orders: {data['stats'].get('total_orders', 0)}"
    )
    
    keyboard = [
        [InlineKeyboardButton("Refresh", callback_data="status"),
         InlineKeyboardButton("List Posts", callback_data="list_posts")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(msg, reply_markup=reply_markup)

async def cmd_start_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start_monitor command"""
    global scanner_instance
    
    if scanner_instance and scanner_instance.running:
        await update.message.reply_text("Warning: Scanner already running")
        return
    
    data = load_data()
    if not data.get("posts"):
        await update.message.reply_text("Error: No posts to monitor! Add some with /add first")
        return
    
    def sync_send(chat_id, text):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(context.bot.send_message(chat_id=chat_id, text=text))
            else:
                loop.run_until_complete(context.bot.send_message(chat_id=chat_id, text=text))
        except:
            pass
    
    scanner_instance = BackgroundScanner(sync_send)
    scanner_instance.start(update.message.chat_id)
    
    keyboard = [[InlineKeyboardButton("Stop Monitor", callback_data="stop_mon")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🟢 Scanner started\n\n"
        f"Monitoring {len(data['posts'])} post(s)\n"
        f"Scan interval: {data['settings'].get('scan_interval', 60)}s",
        reply_markup=reply_markup
    )

async def cmd_stop_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop_monitor command"""
    global scanner_instance
    
    if not scanner_instance or not scanner_instance.running:
        await update.message.reply_text("Warning: Scanner not running")
        return
    
    scanner_instance.stop()
    await update.message.reply_text("🔴 Scanner stopped")

async def cmd_downvotes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /downvotes command"""
    if not context.args:
        data = load_data()
        current = data['settings'].get('downvotes_per_comment', 30)
        await update.message.reply_text(f"Current: {current} downvotes per comment\n\nUsage: /downvotes <number>")
        return
    
    try:
        num = int(context.args[0])
        if num < 3:
            await update.message.reply_text("Error: Minimum is 3 (API limitation)")
            return
        
        data = load_data()
        data['settings']['downvotes_per_comment'] = num
        save_data(data)
        await update.message.reply_text(f"Set to {num} downvotes per comment")
    except ValueError:
        await update.message.reply_text("Error: Please enter a valid number")

async def cmd_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /interval command"""
    if not context.args:
        data = load_data()
        current = data['settings'].get('scan_interval', 60)
        await update.message.reply_text(f"Current: {current}s between scans\n\nUsage: /interval <seconds>")
        return
    
    try:
        num = int(context.args[0])
        if num < 30:
            await update.message.reply_text("Error: Minimum is 30 seconds")
            return
        
        data = load_data()
        data['settings']['scan_interval'] = num
        save_data(data)
        await update.message.reply_text(f"Set scan interval to {num}s")
    except ValueError:
        await update.message.reply_text("Error: Please enter a valid number")

async def cmd_downvote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /downvote command - instant downvote"""
    if not context.args:
        await update.message.reply_text(
            "Usage: /downvote <reddit_url> [quantity]\n\n"
            "Examples:\n"
            "/downvote https://reddit.com/r/.../comments/abc123/\n"
            "/downvote https://reddit.com/r/.../comments/abc123/ 10"
        )
        return
    
    url = context.args[0]
    
    data = load_data()
    default_qty = data['settings'].get('downvotes_per_comment', 30)
    
    if len(context.args) > 1:
        try:
            quantity = max(3, int(context.args[1]))
        except ValueError:
            quantity = default_qty
    else:
        quantity = default_qty
    
    if not re.match(r'https?://(www\.|old\.)?reddit\.com/r/\w+', url):
        await update.message.reply_text("Error: Invalid Reddit URL")
        return
    
    is_comment = '/comment/' in url or url.count('/') > 7
    service_id = 8 if is_comment else 1
    target_type = "comment" if is_comment else "post"
    
    await update.message.reply_text(f"Sending {quantity} downvotes to {target_type}...")
    
    api = UpvoteBizAPI()
    response = api.add_order(service_id, url, quantity)
    
    if 'order' in response:
        data = load_data()
        data["stats"]["total_orders"] += 1
        data["stats"]["orders_today"] += 1
        if is_comment:
            data["stats"]["comments_downvoted"] = data["stats"].get("comments_downvoted", 0) + 1
        save_data(data)
        
        await update.message.reply_text(
            f"Order placed\n"
            f"Order ID: {response['order']}\n"
            f"Type: {target_type}\n"
            f"Quantity: {quantity}"
        )
    else:
        await update.message.reply_text(f"Error: {response.get('error', 'Unknown error')}")

async def cmd_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /whitelist command - add user to whitelist"""
    if not context.args:
        await update.message.reply_text("Usage: /whitelist <username>\n\nExample: /whitelist spammer123")
        return
    
    username = context.args[0].lstrip('u/').lower()
    data = load_data()
    
    # Check if already in JSON whitelist
    if username in [u.lower() for u in data.get("whitelist", [])]:
        await update.message.reply_text(f"u/{username} is already whitelisted")
        return
    
    # Check if in Excel whitelist
    excel_wl = load_whitelist_from_excel()
    if username in excel_wl:
        await update.message.reply_text(f"u/{username} is already in Excel whitelist")
        return
    
    data.setdefault("whitelist", []).append(username)
    save_data(data)
    
    total = len(get_full_whitelist())
    await update.message.reply_text(f"Added u/{username} to whitelist\nTotal whitelisted: {total}")

async def cmd_unwhitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unwhitelist command - remove user from whitelist"""
    if not context.args:
        await update.message.reply_text("Usage: /unwhitelist <username>")
        return
    
    username = context.args[0].lstrip('u/').lower()
    data = load_data()
    
    # Find and remove (case-insensitive)
    found = False
    for u in data.get("whitelist", []):
        if u.lower() == username:
            data["whitelist"].remove(u)
            found = True
            break
    
    if found:
        save_data(data)
        await update.message.reply_text(f"Removed u/{username} from whitelist")
    else:
        # Check if in Excel
        if username in load_whitelist_from_excel():
            await update.message.reply_text(f"u/{username} is in Excel file - remove from Excel to unwhitelist")
        else:
            await update.message.reply_text(f"u/{username} not found in whitelist")

async def cmd_showwhitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /showwhitelist command"""
    excel_wl = load_whitelist_from_excel()
    data = load_data()
    json_wl = set(data.get("whitelist", []))
    
    msg = f"=== Whitelist ===\n\n"
    msg += f"From Excel: {len(excel_wl)} users\n"
    msg += f"Added via bot: {len(json_wl)} users\n"
    msg += f"Total: {len(excel_wl | json_wl)} users\n"
    
    if json_wl:
        msg += f"\nBot-added users:\n"
        msg += ", ".join([f"u/{u}" for u in list(json_wl)[:20]])
        if len(json_wl) > 20:
            msg += f"\n... and {len(json_wl) - 20} more"
    
    await update.message.reply_text(msg)

# ============================================
# CALLBACK QUERY HANDLER (for buttons)
# ============================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses"""
    global scanner_instance
    
    query = update.callback_query
    await query.answer()
    
    data_str = query.data
    
    if data_str == "status":
        # Refresh status
        data = load_data()
        reset_daily_stats_if_needed(data)
        api = UpvoteBizAPI()
        balance = api.get_balance()
        
        running = "🟢 Running" if (scanner_instance and scanner_instance.running) else "🔴 Stopped"
        excel_whitelist = load_whitelist_from_excel()
        
        msg = (
            f"=== Downvoter Status ===\n\n"
            f"Scanner: {running}\n"
            f"Balance: ${balance.get('balance', 'N/A')}\n\n"
            f"--- Config ---\n"
            f"Posts monitored: {len(data.get('posts', []))}\n"
            f"Whitelisted: {len(excel_whitelist)}\n"
            f"Downvotes/comment: {data['settings'].get('downvotes_per_comment', 30)}\n"
            f"Scan interval: {data['settings'].get('scan_interval', 60)}s\n\n"
            f"--- Stats ---\n"
            f"Comments downvoted: {data['stats'].get('comments_downvoted', 0)}\n"
            f"Orders today: {data['stats'].get('orders_today', 0)}\n"
            f"Total orders: {data['stats'].get('total_orders', 0)}"
        )
        
        keyboard = [
            [InlineKeyboardButton("Refresh", callback_data="status"),
             InlineKeyboardButton("List Posts", callback_data="list_posts")]
        ]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data_str == "list_posts":
        data = load_data()
        posts = data.get("posts", [])
        
        if not posts:
            await query.edit_message_text("No posts being monitored\n\nUse /add <url> to add a post")
            return
        
        keyboard = []
        for i, post in enumerate(posts):
            post_id = get_post_id(post)
            match = re.search(r'/r/([^/]+)/', post)
            subreddit = match.group(1) if match else "unknown"
            
            keyboard.append([
                InlineKeyboardButton(f"r/{subreddit} ({post_id})", callback_data=f"view_{i}"),
                InlineKeyboardButton("Remove", callback_data=f"remove_{i}")
            ])
        
        keyboard.append([InlineKeyboardButton("Remove All", callback_data="remove_all")])
        await query.edit_message_text(
            f"Monitoring {len(posts)} post(s):\n\nClick Remove to stop monitoring:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data_str.startswith("remove_"):
        if data_str == "remove_all":
            data = load_data()
            count = len(data["posts"])
            data["posts"] = []
            save_data(data)
            await query.edit_message_text(f"Removed all {count} posts from monitoring")
        else:
            index = int(data_str.split("_")[1])
            data = load_data()
            if 0 <= index < len(data["posts"]):
                removed = data["posts"].pop(index)
                save_data(data)
                await query.edit_message_text(
                    f"Removed post from monitoring\n\nRemaining: {len(data['posts'])} post(s)\n\nUse /list to see current posts"
                )
            else:
                await query.edit_message_text("Error: Post not found")
    
    elif data_str.startswith("view_"):
        index = int(data_str.split("_")[1])
        data = load_data()
        if 0 <= index < len(data["posts"]):
            post = data["posts"][index]
            keyboard = [
                [InlineKeyboardButton("Remove This Post", callback_data=f"remove_{index}")],
                [InlineKeyboardButton("Back to List", callback_data="list_posts")]
            ]
            await query.edit_message_text(f"Post URL:\n{post}", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data_str == "start_mon":
        
        if scanner_instance and scanner_instance.running:
            await query.edit_message_text("Warning: Scanner already running")
            return
        
        data = load_data()
        if not data.get("posts"):
            await query.edit_message_text("Error: No posts to monitor! Add some with /add first")
            return
        
        def sync_send(chat_id, text):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(context.bot.send_message(chat_id=chat_id, text=text))
            except:
                pass
        
        scanner_instance = BackgroundScanner(sync_send)
        scanner_instance.start(query.message.chat_id)
        
        keyboard = [[InlineKeyboardButton("Stop Monitor", callback_data="stop_mon")]]
        await query.edit_message_text(
            f"🟢 Scanner started\n\nMonitoring {len(data['posts'])} post(s)",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data_str == "stop_mon":
        
        if not scanner_instance or not scanner_instance.running:
            await query.edit_message_text("Scanner was not running")
            return
        
        scanner_instance.stop()
        
        keyboard = [[InlineKeyboardButton("Start Monitor", callback_data="start_mon")]]
        await query.edit_message_text("🔴 Scanner stopped", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data_str == "help_add":
        await query.edit_message_text(
            "To add a post to monitor:\n\n"
            "1. Copy the Reddit post URL\n"
            "2. Send: /add <url>\n\n"
            "Example:\n"
            "/add https://www.reddit.com/r/example/comments/abc123/post_title/"
        )

# ============================================
# MAIN
# ============================================

def main():
    """Start the bot"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token or token == "your_bot_token_here":
        print("=" * 50)
        print("ERROR: TELEGRAM_BOT_TOKEN not set!")
        print("")
        print("1. Create a bot via @BotFather on Telegram")
        print("2. Copy the token")
        print("3. Create .env file with:")
        print("   TELEGRAM_BOT_TOKEN=your_token_here")
        print("=" * 50)
        return
    
    print("=" * 50)
    print("Reddit Comment Downvoter - Telegram Bot")
    print("=" * 50)
    
    app = Application.builder().token(token).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("start_monitor", cmd_start_monitor))
    app.add_handler(CommandHandler("stop_monitor", cmd_stop_monitor))
    app.add_handler(CommandHandler("downvotes", cmd_downvotes))
    app.add_handler(CommandHandler("interval", cmd_interval))
    app.add_handler(CommandHandler("downvote", cmd_downvote))
    app.add_handler(CommandHandler("dv", cmd_downvote))
    app.add_handler(CommandHandler("whitelist", cmd_whitelist))
    app.add_handler(CommandHandler("unwhitelist", cmd_unwhitelist))
    app.add_handler(CommandHandler("showwhitelist", cmd_showwhitelist))
    
    # Add callback handler for buttons
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("[OK] Bot started! Press Ctrl+C to stop.")
    print("[i] Add the bot to a group and use /start")
    print(f"[i] Data directory: {DATA_DIR}")
    
    # drop_pending_updates=True prevents conflict errors when restarting
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
