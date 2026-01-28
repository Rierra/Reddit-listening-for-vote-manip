"""
Reddit Scanner Module

Monitors Reddit posts for new comments using PRAW (Official Reddit API).
"""

import time
import praw
from typing import List, Set, Optional
from dataclasses import dataclass
import config

@dataclass
class RedditComment:
    """Represents a Reddit comment"""
    id: str
    author: str
    body: str
    permalink: str
    created_utc: float
    
    @property
    def full_url(self) -> str:
        """Get the full Reddit URL for this comment"""
        return f"https://www.reddit.com{self.permalink}"
    
    @property
    def age_hours(self) -> float:
        """Get the age of the comment in hours"""
        return (time.time() - self.created_utc) / 3600


class RedditScanner:
    """Scans Reddit posts for new comments using PRAW"""
    
    def __init__(self):
        # Initialize PRAW
        self.reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent=config.REDDIT_USER_AGENT,
            requestor_kwargs={'proxies': {'https': f"http://{config.PROXY_URL}", 'http': f"http://{config.PROXY_URL}"}} if config.PROXY_URL else None
        )
        
        self.processed_comments: Set[str] = set()
        self._load_processed()
    
    def _load_processed(self):
        """Load previously processed comment IDs"""
        try:
            with open(config.PROCESSED_COMMENTS_FILE, 'r') as f:
                self.processed_comments = set(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            self.processed_comments = set()
    
    def _save_processed(self):
        """Save processed comment IDs"""
        with open(config.PROCESSED_COMMENTS_FILE, 'w') as f:
            f.write('\n'.join(self.processed_comments))
    
    def mark_processed(self, comment_id: str):
        """Mark a comment as processed"""
        self.processed_comments.add(comment_id)
        self._save_processed()
    
    def get_comments(self, post_url: str) -> List[RedditComment]:
        """
        Fetch all comments from a Reddit post.
        
        Args:
            post_url: The Reddit post URL
            
        Returns:
            List of RedditComment objects
        """
        try:
            submission = self.reddit.submission(url=post_url)
            
            # We only need the newest comments, and we don't want to burn API limits
            # expanding the "more comments" forest too aggressively.
            # limit=0 removes all MoreComments objects, so we only get the initially loaded tree.
            # To catch "new" comments on a very active thread, this might miss some deep replies
            # if they are hidden behind 'more', but 'sort=new' isn't directly settable 
            # on the comment tree fetch in PRAW like it is in JSON AFAIK without extra calls.
            # However, for monitoring specific posts, usually we traverse what we can.
            
            # Use replace_more(limit=0) to remove MoreComments and avoid extra requests
            submission.comments.replace_more(limit=0)
            
            comments = []
            # Flatten the comment tree
            for comment in submission.comments.list():
                # Verify it's a valid comment (PRAW objects should be valid)
                if hasattr(comment, 'author') and comment.author:
                    comments.append(RedditComment(
                        id=comment.id,
                        author=comment.author.name,
                        body=comment.body,
                        permalink=comment.permalink,
                        created_utc=comment.created_utc
                    ))
            
            # Sort by creation time (newest first) to match expectation if needed
            comments.sort(key=lambda x: x.created_utc, reverse=True)
            return comments
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch comments from {post_url}: {e}")
            return []
    
    def get_new_comments(self, post_url: str, whitelist: Set[str]) -> List[RedditComment]:
        """
        Get new, non-whitelisted comments from a post.
        
        Args:
            post_url: The Reddit post URL
            whitelist: Set of usernames to ignore (case-insensitive)
            
        Returns:
            List of new comments that should be downvoted
        """
        # Note: processed_comments is set by BackgroundScanner from data.json
        # Do NOT reload from file here - it would override the correct data
        
        whitelist_lower = {u.lower() for u in whitelist}
        comments = self.get_comments(post_url)
        
        print(f"[DEBUG] Total comments fetched: {len(comments)}")
        
        new_comments = []
        for comment in comments:
            # Skip if already processed
            if comment.id in self.processed_comments:
                continue
            
            # Skip if author is whitelisted
            if comment.author.lower() in whitelist_lower:
                continue
            
            # Skip if comment is too old (>24 hours) -- optional but good practice
            if comment.age_hours > 24:
                continue
            
            new_comments.append(comment)
        
        return new_comments


def load_whitelist() -> Set[str]:
    """Load whitelisted usernames from file"""
    try:
        with open(config.WHITELIST_FILE, 'r') as f:
            return {line.strip() for line in f if line.strip() and not line.startswith('#')}
    except FileNotFoundError:
        return set()


def load_posts_to_monitor() -> List[str]:
    """Load post URLs to monitor from file"""
    try:
        with open(config.POSTS_FILE, 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return []

if __name__ == "__main__":
    print("=" * 60)
    print("REDDIT SCANNER TEST (PRAW)")
    print("=" * 60)
    
    scanner = RedditScanner()
    
    # Test with a sample post
    test_url = "https://www.reddit.com/r/test/comments/1hssrqd/test/"
    
    print(f"\n[1] Fetching comments from test post...")
    print(f"    URL: {test_url}")
    
    comments = scanner.get_comments(test_url)
    print(f"\n[2] Found {len(comments)} comments:")
    
    for i, comment in enumerate(comments[:5], 1):
        print(f"\n    [{i}] u/{comment.author}")
        print(f"        Age: {comment.age_hours:.1f} hours")
        print(f"        URL: {comment.full_url}")
        print(f"        Text: {comment.body[:50]}...")
    
    if len(comments) > 5:
        print(f"\n    ... and {len(comments) - 5} more comments")

