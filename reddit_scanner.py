"""
Reddit Scanner Module

Monitors Reddit posts for new comments using the public JSON API.
No login required - just appends .json to Reddit URLs.
"""

import requests
import time
from typing import List, Dict, Set, Optional
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
    """Scans Reddit posts for new comments"""
    
    def __init__(self):
        self.session = requests.Session()
        # Full browser User-Agent to bypass Reddit's datacenter IP blocking
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        # Configure proxy if set (for bypassing Reddit's VPS/datacenter IP blocking)
        if config.PROXY_URL:
            proxy_url = f"http://{config.PROXY_URL}"
            self.session.proxies = {
                'http': proxy_url,
                'https': proxy_url,
            }
            print(f"[INFO] Reddit scanner using proxy: {config.PROXY_URL.split('@')[1] if '@' in config.PROXY_URL else config.PROXY_URL}")
        
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
    
    def _extract_comments(self, data, comments: List[RedditComment]):
        """Recursively extract comments from Reddit API response"""
        if isinstance(data, dict):
            if data.get('kind') == 't1':  # Comment
                comment_data = data.get('data', {})
                comment = RedditComment(
                    id=comment_data.get('id', ''),
                    author=comment_data.get('author', '[deleted]'),
                    body=comment_data.get('body', ''),
                    permalink=comment_data.get('permalink', ''),
                    created_utc=comment_data.get('created_utc', 0)
                )
                if comment.id and comment.author != '[deleted]':
                    comments.append(comment)
                
                # Check for replies - can be empty string "", None, or a Listing dict
                replies = comment_data.get('replies')
                if replies and replies != "" and isinstance(replies, (dict, list)):
                    self._extract_comments(replies, comments)
            
            elif data.get('kind') == 'Listing':
                for child in data.get('data', {}).get('children', []):
                    self._extract_comments(child, comments)
        
        elif isinstance(data, list):
            for item in data:
                self._extract_comments(item, comments)
    
    def get_comments(self, post_url: str) -> List[RedditComment]:
        """
        Fetch all comments from a Reddit post.
        
        Args:
            post_url: The Reddit post URL
            
        Returns:
            List of RedditComment objects
        """
        # Convert URL to JSON endpoint
        # Remove trailing slash and query params
        clean_url = post_url.split('?')[0].rstrip('/')
        # Use sort=new to get newest comments first (critical for old posts)
        json_url = f"{clean_url}.json?sort=new"
        
        try:
            response = self.session.get(json_url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            comments = []
            # Reddit JSON API returns [post_data, comments_listing]
            # We need to extract from the comments listing (second element)
            if isinstance(data, list) and len(data) > 1:
                comments_data = data[1]  # Second element contains comments
                self._extract_comments(comments_data, comments)
            else:
                # Fallback: try extracting from the entire response
                self._extract_comments(data, comments)
            return comments
            
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"[WARN] Connection issue with {clean_url}: {e.__class__.__name__}")
            return []
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
                print(f"[DEBUG] Skipped {comment.author} - already processed")
                continue
            
            # Skip if author is whitelisted
            if comment.author.lower() in whitelist_lower:
                print(f"[DEBUG] Skipped {comment.author} - whitelisted")
                continue
            
            # Skip if comment is too old (>24 hours - API won't work)
            if comment.age_hours > 24:
                print(f"[DEBUG] Skipped {comment.author} - too old ({comment.age_hours:.1f}h)")
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


# Quick test if run directly
if __name__ == "__main__":
    print("=" * 60)
    print("REDDIT SCANNER TEST")
    print("=" * 60)
    
    scanner = RedditScanner()
    
    # Test with a sample post (r/test is a good test subreddit)
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
    
    print("\n[✓] Reddit scanner working!")
