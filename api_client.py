"""
upvote.biz API Client

Uses cloudscraper to bypass Cloudflare protection.
This module handles all communication with the upvote.biz API.
"""

import json
import sys
import time
from urllib.parse import urlencode, urlparse
from typing import Optional, Dict, Any, List
import cloudscraper
import requests
import config

# Try to import curl_cffi - better Cloudflare bypass
try:
    from curl_cffi import requests as cffi_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    print("[API] curl_cffi not available - using cloudscraper only")


class UpvoteBizAPI:
    """Client for interacting with the upvote.biz API via cloudscraper"""
    
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = api_url or config.API_URL
        self.api_key = api_key or config.API_KEY
        self.session_established = False
        self.base_domain = urlparse(self.api_url).netloc
        
        # Try curl_cffi first (better Cloudflare bypass), fallback to cloudscraper
        if CURL_CFFI_AVAILABLE:
            try:
                # curl_cffi uses impersonate to mimic real browsers
                self.session = cffi_requests.Session(impersonate="chrome110")
                self.use_cffi = True
                print(f"[API] Using curl_cffi for Cloudflare bypass (better success rate)"); sys.stdout.flush()
            except Exception as e:
                print(f"[API] curl_cffi init failed, using cloudscraper: {e}"); sys.stdout.flush()
                self.session = cloudscraper.create_scraper(
                    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
                )
                self.use_cffi = False
        else:
            self.session = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
            )
            self.use_cffi = False
            print(f"[API] Using cloudscraper for Cloudflare bypass"); sys.stdout.flush()
        
        # Set realistic browser headers
        self.session.headers.update({
            'Accept': 'application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
        })
        
        # Configure proxy if available (OPTIONAL)
        if config.PROXY_URL and config.PROXY_URL.strip():
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
            print(f"[API] No proxy configured"); sys.stdout.flush()
    
    def _establish_session(self):
        """Visit the homepage first to establish a Cloudflare session"""
        if self.session_established:
            return True
        
        try:
            # Visit the main site first to establish Cloudflare session
            homepage_url = f"https://{self.base_domain}" if not self.base_domain.startswith('http') else f"http://{self.base_domain}"
            print(f"[API] Establishing Cloudflare session..."); sys.stdout.flush()
            response = self.session.get(homepage_url, timeout=15)
            # Don't check status - just establish session/cookies
            time.sleep(1)  # Small delay to seem more human
            self.session_established = True
            print(f"[API] Session established"); sys.stdout.flush()
            return True
        except Exception as e:
            print(f"[API] Failed to establish session (continuing anyway): {e}"); sys.stdout.flush()
            self.session_established = True  # Mark as attempted
            return False
    
    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a request to the API using cloudscraper
        
        Args:
            params: Dictionary of parameters to send
            
        Returns:
            JSON response as dictionary
        """
        params['key'] = self.api_key
        
        # Establish session first (helps with Cloudflare)
        self._establish_session()
        
        # Build query string with proper URL encoding (like PHP's urlencode)
        url = f"{self.api_url}?{urlencode(params)}"
        
        print(f"[API] Requesting: {self.api_url}?action={params.get('action')}&..."); sys.stdout.flush()
        
        # Retry logic for Cloudflare blocks
        max_retries = 2
        response = None
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30, allow_redirects=True)
                
                # If successful (not 403), break retry loop
                if response.status_code != 403:
                    break
                
                # If 403 and not last attempt, wait and retry
                if attempt < max_retries - 1:
                    print(f"[API] 403 received, retrying... (attempt {attempt + 1}/{max_retries})"); sys.stdout.flush()
                    time.sleep(2)
                    # Re-establish session for retry
                    self.session_established = False
                    self._establish_session()
                    
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    print(f"[API] Request failed, retrying... (attempt {attempt + 1}/{max_retries}): {e}"); sys.stdout.flush()
                    time.sleep(2)
                else:
                    raise
        
        # If we didn't get a response, raise the last exception
        if response is None and last_exception:
            raise last_exception
        if response is None:
            return {"error": "No response received"}
        
        try:
            # Check for 403/Forbidden errors specifically
            if response.status_code == 403:
                content_type = response.headers.get('Content-Type', '').lower()
                response_text = response.text.strip()
                
                # Check if it's a Cloudflare block (HTML response)
                if 'text/html' in content_type or response_text.startswith('<!DOCTYPE') or '<html' in response_text.lower():
                    print(f"[API] 403 Forbidden - Cloudflare block detected (HTML response)"); sys.stdout.flush()
                    # Check for specific Cloudflare indicators
                    if 'cloudflare' in response_text.lower() or 'cf-ray' in response.headers:
                        return {
                            "error": "403 Forbidden - Cloudflare protection block. Try using a proxy or contact upvote.biz support.",
                            "raw": response_text[:500]
                        }
                    return {
                        "error": "403 Forbidden - Received HTML instead of JSON (likely Cloudflare block)",
                        "raw": response_text[:500]
                    }
                else:
                    # 403 but not HTML - might be API rejecting the request
                    print(f"[API] 403 Forbidden - API rejected request (non-HTML response)"); sys.stdout.flush()
                    # Try to parse as JSON error message
                    try:
                        error_data = response.json()
                        return error_data
                    except:
                        pass
                    return {
                        "error": f"403 Forbidden - API rejected request. Check API key and request parameters. Response: {response_text[:200]}",
                        "raw": response_text[:500]
                    }
            
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
                
        except requests.HTTPError as e:
            # Handle other HTTP errors (4xx, 5xx)
            response = e.response if hasattr(e, 'response') else None
            if response:
                print(f"[API] HTTP {response.status_code} error: {e}"); sys.stdout.flush()
                return {
                    "error": f"HTTP {response.status_code}: {str(e)}",
                    "raw": response.text[:500] if hasattr(response, 'text') else str(e)
                }
            return {"error": f"HTTP Error: {str(e)}"}
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
