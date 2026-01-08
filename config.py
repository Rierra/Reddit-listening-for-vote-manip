"""
Configuration for Reddit Comment Downvoter
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================
# UPVOTE.BIZ API CONFIGURATION
# ============================================
API_URL = "https://upvote.biz/api/v1"
API_KEY = os.getenv("UPVOTE_API_KEY", "")

# Service ID for Reddit Comment Downvotes
# ID 8 = "COMMENT DOWNVOTES - up to 24 hours old comments" ($10.00 per order, min 3)
DOWNVOTE_SERVICE_ID = 8

# Default number of downvotes per comment
DEFAULT_DOWNVOTE_QUANTITY = 5

# ============================================
# REDDIT MONITORING SETTINGS
# ============================================
# How often to check for new comments (in seconds)
SCAN_INTERVAL = 60

# ============================================
# FILE PATHS
# ============================================
WHITELIST_FILE = "whitelist.txt"
POSTS_FILE = "posts_to_monitor.txt"
ORDER_HISTORY_FILE = "order_history.csv"
PROCESSED_COMMENTS_FILE = "processed_comments.txt"
