"""
Quick script to place a POST downvote order without Telegram alerts
"""
from api_client import UpvoteBizAPI

api = UpvoteBizAPI()

# Target post - clean URL without query params
# Target post - clean URL without query params
post_url = "https://www.reddit.com/r/india/comments/1qjt932/korean_tourist_allegedly_molested_at_bengaluru/"
quantity = 600

# First, let's see what services are available
print("=" * 60)
print("Available Reddit Services:")
print("=" * 60)
services = api.get_services()
for s in services:
    if 'reddit' in s.get('category', '').lower():
        service_id = s.get('service', 'N/A')
        name = s.get('name', 'N/A')
        rate = s.get('rate', 'N/A')
        min_qty = s.get('min', 'N/A')
        max_qty = s.get('max', 'N/A')
        print(f"ID {service_id:>3}: {name} (${rate}, min:{min_qty}, max:{max_qty})")

# Check balance
print("\n" + "=" * 60)
print("Account Balance:")
print("=" * 60)
balance = api.get_balance()
print(f"Balance: ${balance.get('balance', 'N/A')}")

# Find POST DOWNVOTES service
post_downvote_service_id = None
for s in services:
    name = s.get('name', '').upper()
    if 'POST' in name and 'DOWNVOTE' in name:
        post_downvote_service_id = int(s.get('service'))
        print(f"\nFound: {s.get('name')} - Service ID: {post_downvote_service_id}")
        break

if not post_downvote_service_id:
    print("\nNo POST DOWNVOTE service found. Using default ID 7...")
    post_downvote_service_id = 7

print("\n" + "=" * 60)
print("Placing Order:")
print("=" * 60)
print(f"Service ID: {post_downvote_service_id}")
print(f"URL: {post_url}")
print(f"Quantity: {quantity} downvotes")

result = api.add_order(post_downvote_service_id, post_url, quantity)
print(f"\nAPI Response: {result}")

if 'order' in result:
    print(f"\n{'='*60}")
    print(f"SUCCESS! Order ID: {result['order']}")
    print(f"{'='*60}")
elif 'error' in result:
    print(f"\n{'='*60}")
    print(f"ERROR: {result['error']}")
    print(f"{'='*60}")
