from reddit_scanner import RedditScanner
import config
import sys
import praw

# Ensure credentials are loaded
if not config.REDDIT_CLIENT_ID or not config.REDDIT_CLIENT_SECRET:
    print("[ERROR] REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET not found in config.")
    sys.exit(1)

print(f"Using Client ID: '{config.REDDIT_CLIENT_ID}' (Len: {len(config.REDDIT_CLIENT_ID)})")
print(f"Using Client Secret: '{config.REDDIT_CLIENT_SECRET}' (Len: {len(config.REDDIT_CLIENT_SECRET)})")
print(f"Using User Agent: '{config.REDDIT_USER_AGENT}'")

try:
    scanner = RedditScanner()
    print("[SUCCESS] PRAW initialized.")
    
    # improved: fetch a real recent post from r/all or similar to ensure comments exist
    # but we need a URL string for scanner.get_comments
    
    # We can use PRAW to find one
    reddit = praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        user_agent=config.REDDIT_USER_AGENT
    )
    
    print("Finding a popular post to test...")
    # Get a hot post from r/AskReddit, almost guaranteed to have comments
    for submission in reddit.subreddit("AskReddit").hot(limit=3):
        if not submission.stickied and submission.num_comments > 5:
            test_url = submission.url
            print(f"Testing with: {test_url}")
            print(f"Post Title: {submission.title}")
            
            comments = scanner.get_comments(test_url)
            print(f"Found {len(comments)} comments.")
            
            if comments:
                print(f"First comment by u/{comments[0].author}: {comments[0].body[:100]}...")
                print("[PASS] Comments successfully fetched.")
                sys.exit(0)
            break
    
    print("[WARN] Could not find comments on tested posts, or something is wrong.")

except Exception as e:
    print(f"[FAIL] Error occurred: {e}")
    import traceback
    traceback.print_exc()
