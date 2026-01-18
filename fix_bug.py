content = open('telegram_bot.py', 'r').read()

# Fix the bug: move whitelist definition BEFORE the print statement
old_buggy = '''posts = data.get("posts", [])
                print(f"[SCAN] Scanning {len(posts)} posts, whitelist has {len(whitelist)} users")
                # Combined whitelist from Excel + bot-added users
                whitelist = get_full_whitelist()'''

new_fixed = '''posts = data.get("posts", [])
                # Combined whitelist from Excel + bot-added users
                whitelist = get_full_whitelist()
                print(f"[SCAN] Scanning {len(posts)} posts, whitelist has {len(whitelist)} users")'''

content = content.replace(old_buggy, new_fixed)

# Also add sys.stdout.flush() to ensure logs appear
old_import = 'import time'
new_import = 'import time\nimport sys'
content = content.replace(old_import, new_import, 1)

# Add flush after print statements
content = content.replace(
    'print(f"[SCAN] Scanning {len(posts)} posts, whitelist has {len(whitelist)} users")',
    'print(f"[SCAN] Scanning {len(posts)} posts, whitelist has {len(whitelist)} users"); sys.stdout.flush()'
)

content = content.replace(
    'print(f"[SCAN] Checked {len(self.scanner.processed_comments)} processed, found {len(new_comments)} new")',
    'print(f"[SCAN] Found {len(new_comments)} new comments to downvote"); sys.stdout.flush()'
)

open('telegram_bot.py', 'w').write(content)
print('Fixed bug and added flush')
