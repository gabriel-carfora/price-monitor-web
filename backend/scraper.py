from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
import traceback
import json
import asyncio
import statistics

def parse_price_data(data):
    """
    Parse price data from BuyWisely API response
    
    Expected format: Dictionary with retailer URLs as keys, arrays of price entries as values
    Alternative format: List of retailer objects
    """
    try:
        if isinstance(data, dict):
            # Standard format: {retailer_url: [price_entries]}
            parsed_data = {}
            for retailer_url, entries in data.items():
                if isinstance(entries, list):
                    parsed_data[retailer_url] = entries
                else:
                    print(f"Skipping non-list entry for {retailer_url}: {type(entries)}")
            return parsed_data
        
        elif isinstance(data, list):
            # Alternative format: [retailer_objects]
            parsed_data = {}
            for item in data:
                if isinstance(item, dict):
                    # Look for retailer info and prices
                    retailer_url = item.get('url', item.get('retailer', 'unknown'))
                    prices = item.get('prices', item.get('price_history', []))
                    
                    if isinstance(prices, list) and prices:
                        parsed_data[retailer_url] = prices
                    elif 'price' in item or 'base_price' in item:
                        # Single price entry
                        price_entry = {
                            'base_price': item.get('price', item.get('base_price', 0)),
                            'created_at': item.get('created_at', item.get('timestamp', datetime.now(timezone.utc).isoformat()))
                        }
                        parsed_data[retailer_url] = [price_entry]
            return parsed_data
        
        else:
            print(f"Unexpected data format: {type(data)}")
            return {}
    
    except Exception as e:
        print(f"Error parsing price data: {e}")
        traceback.print_exc()
        return {}

def extract_retailer_name(url):
    """Extract a clean retailer name from URL"""
    retailer_map = {
        "chemistwarehouse.com.au": "Chemist Warehouse",
        "priceline.com.au": "Priceline",
        "amazon.com.au": "Amazon AU",
        "ebay.com.au": "eBay",
        "woolworths.com.au": "Woolworths",
        "coles.com.au": "Coles",
        "bigw.com.au": "Big W",
        "kmart.com.au": "Kmart",
        "target.com.au": "Target",
        "pharmacy4less.com.au": "Pharmacy 4 Less",
        "mydeal.com.au": "MyDeal",
        "catch.com.au": "Catch"
    }
    
    for domain, name in retailer_map.items():
        if domain in url:
            return name
    
    # Extract domain name as fallback
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace("www.", "")
        return domain.split(".")[0].title()
    except:
        return url

async def scrape_product_async(url, excluded_retailers=None, days_back=30):
    """
    Scrape product from BuyWisely page and intercept API calls
    
    Args:
        url: BuyWisely product URL
        excluded_retailers: List of retailer domains to exclude
        days_back: Number of days of historical data to consider
    """
    if excluded_retailers is None:
        excluded_retailers = []
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            api_responses = []

            async def handle_response(response):
                # Only intercept the main product API, not suggestions
                if ("/api/product/" in response.url and 
                    "/suggestions/" not in response.url and 
                    "/search/" not in response.url and
                    response.status == 200):
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        try:
                            data = await response.json()
                            api_responses.append(data)
                            print(f"Intercepted main product API: {response.url}")
                        except Exception as e:
                            print(f"Failed to parse API response: {e}")

            page.on("response", handle_response)
            
            print(f"Loading page: {url}")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait longer for the main product API call
            await page.wait_for_timeout(10000)
            
            # If no API responses yet, try scrolling or interacting with the page
            if not api_responses:
                print("No API responses yet, trying to trigger data loading...")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(5000)
            
            await browser.close()

            if not api_responses:
                print("No API responses intercepted")
                return None
            
            # Debug: log all intercepted responses
            print(f"Intercepted {len(api_responses)} API responses")
            for i, response in enumerate(api_responses):
                print(f"Response {i}: type={type(response)}, keys={list(response.keys()) if isinstance(response, dict) else 'N/A'}")
            
            # Use the most recent/complete API response
            raw_data = api_responses[-1]
            print(f"Using response: type={type(raw_data)}")
            
            if isinstance(raw_data, dict):
                print(f"Dict keys: {list(raw_data.keys())}")
                print(f"Processing API data with {len(raw_data)} entries")
            elif isinstance(raw_data, list):
                print(f"List length: {len(raw_data)}")
                print(f"Processing API data with {len(raw_data)} entries")
            
            # Parse the price data
            data = parse_price_data(raw_data)
            
            if not data:
                print("No valid price data found")
                return None

            # Calculate date threshold
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            
            current_prices = []  # Recent prices (last 7 days)
            historical_prices = []  # All prices within the period
            retailer_current_prices = {}  # Best current price per retailer
            
            print(f"Analyzing prices from {len(data)} retailers...")
            
            for retailer_url, entries in data.items():
                retailer_name = extract_retailer_name(retailer_url)
                
                # Skip excluded retailers
                if any(excluded in retailer_url.lower() for excluded in excluded_retailers):
                    print(f"Skipping excluded retailer: {retailer_name}")
                    continue
                
                print(f"\n--- Processing {retailer_name} ({len(entries)} entries) ---")
                
                retailer_prices = []
                recent_prices = []
                
                for i, entry in enumerate(entries):
                    try:
                        # Debug: Print first few entries to understand structure
                        if i < 2:
                            print(f"Entry {i}: {entry}")
                        
                        # Parse timestamp
                        timestamp_str = entry.get('created_at', entry.get('timestamp', ''))
                        if not timestamp_str:
                            print(f"Entry {i}: No timestamp found, skipping")
                            continue

                        # Handle different timestamp formats
                        try:
                            if '.' in timestamp_str:
                                ts = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                            else:
                                ts = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
                            ts = ts.replace(tzinfo=timezone.utc)
                        except ValueError as e:
                            print(f"Entry {i}: Failed to parse timestamp {timestamp_str}: {e}")
                            continue
                        
                        # Check age
                        age_days = (datetime.now(timezone.utc) - ts).days
                        if i < 2:  # Debug first few entries
                            print(f"Entry {i}: Date {ts}, Age: {age_days} days")
                        
                        # Only consider prices within our date range
                        if ts < cutoff_date:
                            if i < 2:
                                print(f"Entry {i}: Too old, skipping")
                            continue
                        
                        # Extract price
                        price = entry.get('base_price', entry.get('price', 0))
                        if price <= 0:
                            if i < 2:
                                print(f"Entry {i}: Invalid price {price}, skipping")
                            continue
                        
                        if i < 2:
                            print(f"Entry {i}: Valid price ${price}, age {age_days} days")
                        
                        retailer_prices.append(price)
                        historical_prices.append(price)
                        
                        # Consider prices from last 7 days as "current"
                        if ts >= datetime.now(timezone.utc) - timedelta(days=7):
                            recent_prices.append(price)
                            current_prices.append(price)
                            if i < 2:
                                print(f"Entry {i}: Added as current price")
                    
                    except Exception as e:
                        print(f"Error processing entry {i}: {e}")
                        continue
                
                print(f"{retailer_name}: {len(retailer_prices)} total prices, {len(recent_prices)} recent prices")
                
                # Store best current price for this retailer
                if recent_prices:
                    retailer_current_prices[retailer_name] = {
                        'price': min(recent_prices),
                        'url': retailer_url,
                        'avg_price': sum(retailer_prices) / len(retailer_prices) if retailer_prices else 0
                    }
                    print(f"{retailer_name}: Best current price ${min(recent_prices):.2f}")
                else:
                    print(f"{retailer_name}: No recent prices found")
            
            if not historical_prices:
                print("No valid historical prices found")
                return None
            
            print(f"\nSummary: {len(historical_prices)} total historical prices")
            print(f"Current prices (last 7 days): {len(current_prices)}")
            
            # If no current prices, use most recent prices from each retailer
            if not retailer_current_prices and historical_prices:
                print("No recent prices found, using most recent available prices...")
                
                for retailer_url, entries in data.items():
                    retailer_name = extract_retailer_name(retailer_url)
                    
                    # Skip excluded retailers
                    if any(excluded in retailer_url.lower() for excluded in excluded_retailers):
                        continue
                    
                    most_recent_price = None
                    most_recent_date = None
                    
                    for entry in entries:
                        try:
                            timestamp_str = entry.get('created_at', entry.get('timestamp', ''))
                            if not timestamp_str:
                                continue
                            
                            if '.' in timestamp_str:
                                ts = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                            else:
                                ts = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
                            ts = ts.replace(tzinfo=timezone.utc)
                            
                            if ts < cutoff_date:
                                continue
                                
                            price = entry.get('base_price', entry.get('price', 0))
                            if price <= 0:
                                continue
                            
                            if most_recent_date is None or ts > most_recent_date:
                                most_recent_date = ts
                                most_recent_price = price
                                
                        except Exception:
                            continue
                    
                    if most_recent_price is not None:
                        retailer_current_prices[retailer_name] = {
                            'price': most_recent_price,
                            'url': retailer_url,
                            'avg_price': most_recent_price
                        }
                        print(f"{retailer_name}: Most recent price ${most_recent_price:.2f} from {most_recent_date}")
            
            # Calculate statistics
            avg_price = statistics.mean(historical_prices)
            
            # Find best current price
            if not retailer_current_prices:
                print("No current prices found")
                return None
            
            best_retailer = min(retailer_current_prices.items(), 
                              key=lambda x: x[1]['price'])
            
            result = {
                "price": best_retailer[1]['price'],
                "retailer": best_retailer[1]['url'],
                "retailer_name": best_retailer[0],
                "average_price": round(avg_price, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_prices_analyzed": len(historical_prices),
                "retailers_analyzed": len(retailer_current_prices),
                "savings": round(avg_price - best_retailer[1]['price'], 2),
                "savings_percentage": round(((avg_price - best_retailer[1]['price']) / avg_price) * 100, 1) if avg_price > 0 else 0
            }
            
            print(f"Analysis complete: Best price ${result['price']:.2f} at {result['retailer_name']}, "
                  f"Average ${result['average_price']:.2f}, "
                  f"Savings: ${result['savings']:.2f} ({result['savings_percentage']}%)")
            
            return result
            
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        traceback.print_exc()
        return None