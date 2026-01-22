
import sys
import time
import os

print(f"Python version: {sys.version}")

print("[1] Testing curl_cffi import...")
try:
    from curl_cffi import requests as cffi_requests
    print("SUCCESS: curl_cffi imported successfully")
    print(f"Version: {cffi_requests.__version__ if hasattr(cffi_requests, '__version__') else 'unknown'}")
except ImportError as e:
    print(f"FAILURE: Could not import curl_cffi: {e}")
    cffi_requests = None

print("[2] Testing connection to upvote.biz...")
url = "https://upvote.biz"

if cffi_requests:
    try:
        print(f"Attempting request with curl_cffi (impersonate='chrome110')...")
        session = cffi_requests.Session(impersonate="chrome110")
        response = session.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 403:
            print("Response headers:", response.headers)
            print("Response start:", response.text[:200])
            print("STILL BLOCKED BY CLOUDFLARE")
        elif response.status_code == 200:
            print("SUCCESS: Bypassed Cloudflare!")
        else:
            print(f"Unexpected status: {response.status_code}")
    except Exception as e:
        print(f"Error with curl_cffi: {e}")
else:
    print("Skipping curl_cffi test (not installed)")

print("[3] Testing connection with cloudscraper (fallback)...")
try:
    import cloudscraper
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    response = scraper.get(url)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("SUCCESS: Cloudscraper bypassed Cloudflare")
    elif response.status_code == 403:
        print("FAILURE: Cloudscraper blocked by Cloudflare")
    else:
        print(f"Unexpected status: {response.status_code}")
except ImportError:
    print("cloudscraper not installed")
except Exception as e:
    print(f"Error with cloudscraper: {e}")
