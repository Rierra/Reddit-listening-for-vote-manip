"""
upvote.biz API Client

Uses curl.exe subprocess to bypass Cloudflare protection.
This module handles all communication with the upvote.biz API.
"""

import subprocess
import json
from typing import Optional, Dict, Any, List
import config


class UpvoteBizAPI:
    """Client for interacting with the upvote.biz API via curl"""
    
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = api_url or config.API_URL
        self.api_key = api_key or config.API_KEY
        self.user_agent = 'API (compatible; MSIE 5.01; Windows NT 5.0)'
    
    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a request to the API using curl.exe
        
        Args:
            params: Dictionary of parameters to send
            
        Returns:
            JSON response as dictionary
        """
        params['key'] = self.api_key
        
        # Build query string
        query_parts = [f"{k}={v}" for k, v in params.items()]
        url = f"{self.api_url}?{'&'.join(query_parts)}"
        
        try:
            result = subprocess.run(
                ['curl.exe', '-s', '-A', self.user_agent, url],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {"error": f"curl failed: {result.stderr}"}
            
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            return {"error": "Request timed out"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}", "raw": result.stdout[:500]}
        except Exception as e:
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
