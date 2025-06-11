from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright
import traceback
import json

def parse_price_data(data):
    """
    Robust parsing of price data from different possible formats
    
    Expected input formats:
    1. Dictionary of retailer entries
    2. List of entries
    3. Single entry dictionary
    """
    try:
        # If data is a dictionary with retailer URLs as keys
        if isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
            return data
        
        # If data is a list of entries
        if isinstance(data, list):
            # Group entries by retailer
            grouped_data = {}
            for entry in data:
                retailer = entry.get('retailer', 'Unknown')
                if retailer not in grouped_data:
                    grouped_data[retailer] = []
                grouped_data[retailer].append(entry)
            return grouped_data
        
        # If data is a single entry dictionary
        if isinstance(data, dict) and 'base_price' in data:
            return {'Unknown': [data]}
        
        # Unrecognized format
        print(f"Unrecognized data format: {type(data)}")
        print(f"Data contents: {json.dumps(data, indent=2)}")
        return {}
    
    except Exception as e:
        print(f"Error parsing price data: {e}")
        traceback.print_exc()
        return {}

def scrape_product(url):
    """Synchronous scraper function"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            api_response = {}

            def handle_response(response):
                if "/api/product/" in response.url and response.status == 200:
                    if "application/json" in response.headers.get("content-type", ""):
                        try:
                            api_response["data"] = response.json()
                        except Exception:
                            pass

            page.on("response", handle_response)
            page.goto(url)
            page.wait_for_timeout(5000)
            browser.close()

            # Extract and parse data
            raw_data = api_response.get("data", {})
            data = parse_price_data(raw_data)

            one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            best = None

            # Iterate through parsed data
            for retailer_url, entries in data.items():
                for entry in entries:
                    try:
                        # Parse timestamp (handle different timestamp formats)
                        timestamp_str = entry.get('created_at', entry.get('timestamp', ''))
                        if not timestamp_str:
                            continue

                        # Try parsing with microseconds
                        try:
                            ts = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                        except ValueError:
                            # Fallback to parsing without microseconds
                            ts = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        
                        if ts >= one_week_ago:
                            # Extract price, handling different possible keys
                            price = entry.get('base_price', entry.get('price', 0))
                            
                            if best is None or price < best["price"]:
                                best = {
                                    "price": price,
                                    "retailer": retailer_url,
                                    "timestamp": timestamp_str
                                }
                    except Exception as e:
                        print(f"Error processing entry: {e}")
                        continue
            
            return best
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        traceback.print_exc()
        return None

# Keep the async version for compatibility with existing async code
async def scrape_product_async(url):
    """Async wrapper for synchronous scraper"""
    return scrape_product(url)