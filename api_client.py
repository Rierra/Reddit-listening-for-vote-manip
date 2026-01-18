"""
upvote.biz API Client

Uses cloudscraper to bypass Cloudflare protection.
This module handles all communication with the upvote.biz API.
"""

import json
import sys
from urllib.parse import urlencode
from typing import Optional, Dict, Any, List
import cloudscraper
import config


class UpvoteBizAPI:
    """Client for interacting with the upvote.biz API via cloudscraper"""
    
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = api_url or config.API_URL
        self.api_key = api_key or config.API_KEY
        
        # Use cloudscraper to bypass Cloudflare protection
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        
        # Set realistic browser headers
        self.session.headers.update({
            'Accept': 'application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        # Configure proxy if available (OPTIONAL - cloudscraper should handle Cloudflare without proxy)
        # Only set PROXY_URL if you need additional proxy protection
        if config.PROXY_URL and config.PROXY_URL.strip():
            # PROXY_URL format: username:password@host:port or host:port
            if config.PROXY_URL.startswith(('http://', 'https://')):
                proxy_url = config.PROXY_URL
            else:
                proxy_url = f"http://{config.PROXY_URL}"
            
            self.session.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            print(f"[API] Using proxy for upvote.biz requests"); sys.stdout.flush()
        else:
            print(f"[API] No proxy configured - using cloudscraper directly (should bypass Cloudflare)"); sys.stdout.flush()
    
    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a request to the API using cloudscraper
        
        Args:
            params: Dictionary of parameters to send
            
        Returns:
            JSON response as dictionary
        """
        params['key'] = self.api_key
        
        # Build query string with proper URL encoding (like PHP's urlencode)
        url = f"{self.api_url}?{urlencode(params)}"
        
        print(f"[API] Requesting: {self.api_url}?action={params.get('action')}&..."); sys.stdout.flush()
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Check if response is HTML (Cloudflare block) or text error instead of JSON
            content_type = response.headers.get('Content-Type', '').lower()
            response_text = response.text.strip()
            
            # Check for proxy errors (happens before Cloudflare)
            if 'access denied' in response_text.lower() or 'ip is not in the whitelist' in response_text.lower():
                print(f"[API] Proxy access denied - proxy IP not whitelisted"); sys.stdout.flush()
                return {
                    "error": "Proxy access denied - IP not whitelisted. Remove PROXY_URL to use cloudscraper without proxy.",
                    "raw": response_text[:500]
                }
            
            # Check if response is HTML (Cloudflare block) instead of JSON
            if 'text/html' in content_type or response_text.startswith('<!DOCTYPE'):
                # Likely a Cloudflare block page
                print(f"[API] Cloudflare block detected - received HTML instead of JSON"); sys.stdout.flush()
                # Check for specific Cloudflare indicators
                if 'cloudflare' in response_text.lower() or 'cf-ray' in response.headers:
                    return {
                        "error": "Cloudflare protection block - cloudscraper should handle this, check if proxy is interfering",
                        "raw": response_text[:500]
                    }
                return {
                    "error": "Received HTML response instead of JSON",
                    "raw": response_text[:500]
                }
            
            # Try to parse as JSON
            try:
                data = response.json()
                print(f"[API] Response: {data}"); sys.stdout.flush()
                return data
            except json.JSONDecodeError as e:
                print(f"[API] Invalid JSON response: {e}"); sys.stdout.flush()
                return {
                    "error": f"Invalid JSON: {e}",
                    "raw": response.text[:500]
                }
                
        except Exception as e:
            error_msg = str(e)
            if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
                print(f"[API] Request timed out"); sys.stdout.flush()
                return {"error": "Request timed out"}
            elif 'cloudflare' in error_msg.lower():
                print(f"[API] Cloudflare block: {error_msg}"); sys.stdout.flush()
                return {"error": f"Cloudflare block: {error_msg}"}
            else:
                print(f"[API] Error: {error_msg}"); sys.stdout.flush()
                return {"error": error_msg}
    
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
