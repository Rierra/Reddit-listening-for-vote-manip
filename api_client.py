"""
upvote.biz API Client

Uses Playwright (headless Chrome) to bypass Cloudflare TLS fingerprinting.
This is a drop-in replacement - all function signatures remain the same.
"""

import json
import sys
from urllib.parse import urlencode
from typing import Optional, Dict, Any, List
import config

try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext
except ImportError:
    print("[ERROR] playwright not installed. Run: pip install playwright")
    print("[ERROR] Then run: playwright install chromium")
    sys.exit(1)


class UpvoteBizAPI:
    """Client for interacting with the upvote.biz API via Playwright"""
    
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = api_url or config.API_URL
        self.api_key = api_key or config.API_KEY
        
        # Playwright browser instance (reused for performance)
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._browser_initialized = False
        
        # Configure proxy if available
        self.proxy_config = None
        if hasattr(config, 'API_PROXY') and config.API_PROXY:
            # Parse proxy URL: http://user:pass@host:port
            proxy_url = config.API_PROXY
            if '@' in proxy_url:
                # Has auth
                auth_part, server_part = proxy_url.split('@')
                protocol = auth_part.split('://')[0]
                username, password = auth_part.split('://')[1].split(':')
                server = server_part
                
                self.proxy_config = {
                    'server': f'{protocol}://{server}',
                    'username': username,
                    'password': password
                }
            else:
                # No auth
                self.proxy_config = {'server': proxy_url}
            
            print(f"[API] Using proxy: {server_part if '@' in proxy_url else proxy_url}")
            sys.stdout.flush()
        
        # Don't initialize browser in __init__ - do it lazily on first request
        # This avoids asyncio conflicts when created inside async context
    
    def _init_browser(self):
        """Initialize Playwright browser (called once, reused for all requests)"""
        try:
            self.playwright = sync_playwright().start()
            
            # Launch Chrome with realistic settings
            launch_options = {
                'headless': False,  # Make browser VISIBLE for debugging
                'args': [
                    '--disable-blink-features=AutomationControlled',  # Hide automation
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            }
            
            if self.proxy_config:
                launch_options['proxy'] = self.proxy_config
            
            self.browser = self.playwright.chromium.launch(**launch_options)
            
            # Create context with realistic browser settings
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
            )
            
            print("[API] Playwright browser initialized")
            sys.stdout.flush()
            self._browser_initialized = True
            
        except Exception as e:
            print(f"[API] Failed to initialize browser: {e}")
            sys.stdout.flush()
            raise
    
    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a request to the API using Playwright (bypasses Cloudflare)
        
        Args:
            params: Dictionary of parameters to send
            
        Returns:
            JSON response as dictionary
        """
        params['key'] = self.api_key
        url = f"{self.api_url}?{urlencode(params)}"
        
        print(f"[API] Requesting: {self.api_url}?action={params.get('action')}&...")
        sys.stdout.flush()
        
        # Lazy initialization - only start browser on first actual request
        if not self._browser_initialized:
            self._init_browser()
        
        try:
            # Create a new page for this request
            page = self.context.new_page()
            
            # Navigate to the API URL (Playwright handles Cloudflare automatically)
            response = page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Get the response body
            content = page.content()
            
            # Close the page (keep browser/context alive for reuse)
            page.close()
            
            # Extract JSON from HTML wrapper (API returns JSON inside <body> tags)
            import re
            
            if '<body>' in content:
                match = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL)
                if match:
                    content = match.group(1).strip()
            elif '<pre>' in content:
                match = re.search(r'<pre[^>]*>(.*?)</pre>', content, re.DOTALL)
                if match:
                    content = match.group(1).strip()
            
            # Check if it's actually a Cloudflare challenge page (has "Just a moment" or "challenge")
            if 'cloudflare' in content.lower() and ('challenge' in content.lower() or 'just a moment' in content.lower()):
                print(f"[API] Real Cloudflare challenge detected")
                print(f"[API] Status: {response.status}")
                print(f"[API] Response preview: {content[:200]}")
                sys.stdout.flush()
                return {"error": "Cloudflare challenge page", "status": response.status}
            
            # Try to parse as JSON
            try:
                result = json.loads(content)
                print(f"[API] Response: {result}")
                sys.stdout.flush()
                return result
            except json.JSONDecodeError:
                # Not valid JSON, probably still HTML
                print(f"[API] Could not parse as JSON")
                print(f"[API] Content: {content[:500]}")
                sys.stdout.flush()
                return {"error": "Invalid response format", "raw": content[:500]}
            
        except json.JSONDecodeError as e:
            print(f"[API] Invalid JSON: {e}")
            print(f"[API] Content preview: {content[:500] if 'content' in locals() else 'N/A'}")
            sys.stdout.flush()
            return {"error": f"Invalid JSON: {e}"}
        except Exception as e:
            print(f"[API] Error: {e}")
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
    
    def get_services(self) -> List[Dict[str, Any]]:
        """Get all available services from the API."""
        result = self._make_request({'action': 'services'})
        if isinstance(result, list):
            return result
        return []
    
    def get_balance(self) -> Dict[str, Any]:
        """Get current account balance."""
        return self._make_request({'action': 'balance'})
    
    def add_order(self, service_id: int, link: str, quantity: int) -> Dict[str, Any]:
        """
        Place a new order (upvote/downvote).
        
        Args:
            service_id: The service ID (8 for comment downvotes)
            link: The Reddit comment URL
            quantity: Number of downvotes (min 3)
            
        Returns:
            Dictionary with 'order' (order ID) on success
        """
        params = {
            'action': 'add',
            'service': service_id,
            'link': link,
            'quantity': quantity
        }
        return self._make_request(params)
    
    def downvote_comment(self, comment_url: str, quantity: int = None) -> Dict[str, Any]:
        """
        Convenience method to downvote a Reddit comment.
        
        Args:
            comment_url: The Reddit comment URL
            quantity: Number of downvotes (default from config, min 3)
            
        Returns:
            API response with order ID
        """
        qty = quantity or config.DEFAULT_DOWNVOTE_QUANTITY
        qty = max(3, qty)  # Minimum is 3 per API
        return self.add_order(config.DOWNVOTE_SERVICE_ID, comment_url, qty)
    
    def get_order_status(self, order_id: int) -> Dict[str, Any]:
        """Get the status of a specific order."""
        return self._make_request({'action': 'status', 'order': order_id})
    
    def get_multi_status(self, order_ids: List[int]) -> Dict[str, Any]:
        """Get status of multiple orders at once."""
        return self._make_request({
            'action': 'status',
            'orders': ','.join(map(str, order_ids))
        })
    
    def __del__(self):
        """Cleanup browser on exit"""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except:
            pass


# Quick test if run directly
if __name__ == "__main__":
    api = UpvoteBizAPI()
    
    print("=" * 60)
    print("UPVOTE.BIZ API TEST")
    print("=" * 60)
    
    # Check balance
    print("\n[1] Checking balance...")
    balance = api.get_balance()
    print(f"    Balance: ${balance.get('balance', 'N/A')} {balance.get('currency', '')}")
    
    # Get services
    print("\n[2] Available Reddit services:")
    services = api.get_services()
    for svc in services:
        if 'reddit' in svc.get('category', '').lower():
            print(f"    ID {svc['service']:>2}: {svc['name']} (${svc['rate']})")
    
    print("\n[✓] API connection successful!")
    print(f"    Using service ID {config.DOWNVOTE_SERVICE_ID} for comment downvotes")
    
    # Cleanup
    del api