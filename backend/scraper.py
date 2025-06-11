from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
import traceback
import json
import asyncio
import statistics

def parse_price_data(data):
    """
    Parse price data from BuyWisely API response
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

async def extract_product_image(page):
    """Extract product image from the BuyWisely page"""
    try:
        print("Attempting to extract product image...")
        
        # Common selectors for product images on BuyWisely
        image_selectors = [
            'img[alt*="product"]',  # Images with "product" in alt text
            'img[src*="product"]',  # Images with "product" in src
            'img[class*="product"]',  # Images with "product" in class
            '.product-image img',  # Product image containers
            '.product-img img',
            '[data-testid="product-image"] img',
            '.main-image img',
            '.hero-image img',
            # BuyWisely specific selectors (you may need to inspect their HTML)
            'img[src*="buywisely"]',
            'img[src*="cdn"]',
            # Generic fallbacks
            'main img:first-of-type',
            'article img:first-of-type',
            '.container img:first-of-type'
        ]
        
        for selector in image_selectors:
            try:
                # Wait for potential image to load
                await page.wait_for_selector(selector, timeout=2000)
                
                # Get the image element
                image_element = await page.query_selector(selector)
                if image_element:
                    # Get the src attribute
                    src = await image_element.get_attribute('src')
                    if src:
                        # Check if it's a valid image URL (not a placeholder or icon)
                        if (src.startswith('http') and 
                            any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']) and
                            'placeholder' not in src.lower() and
                            'icon' not in src.lower() and
                            'logo' not in src.lower()):
                            
                            print(f"Found product image: {src}")
                            return src
                            
            except Exception as e:
                # Continue to next selector if this one fails
                continue
        
        # If no specific selectors work, try to find any reasonable product image
        try:
            # Get all images on the page
            all_images = await page.query_selector_all('img')
            
            for img in all_images:
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt') or ''
                
                if (src and src.startswith('http') and
                    any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']) and
                    'product' in alt.lower() or 'item' in alt.lower()):
                    
                    print(f"Found product image via alt text: {src}")
                    return src
                    
        except Exception as e:
            print(f"Error in fallback image search: {e}")
        
        print("No product image found")
        return None
        
    except Exception as e:
        print(f"Error extracting product image: {e}")
        return None

async def scrape_product_async(url, excluded_retailers=None, days_back=30):
    """
    Scrape product from BuyWisely page and intercept API calls
    
    Args:
        url: BuyWisely product URL
        excluded_retailers: List of retailer domains to exclude
        days_back: Number of days of historical data to consider
    
    Returns:
        Dict with best price info, list of all retailers, and product image
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
                if ("/api/produhttps://buywisely.com.au/product/viva-paper-towel-white-pack-of-12-12-rolls-60-sheets-per-roll-ct/" in response.url and 
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
            
            # Wait longer for the main product API call and page content
            await page.wait_for_timeout(10000)
            
            # Extract product image while we're on the page
            product_image = await extract_product_image(page)
            
            # If no API responses yet, try scrolling or interacting with the page
            if not api_responses:
                print("No API responses yet, trying to trigger data loading...")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(5000)
            
            await browser.close()

            if not api_responses:
                print("No API responses intercepted")
                return None
            
            # Use the most recent/complete API response
            raw_data = api_responses[-1]
            print(f"Using response: type={type(raw_data)}")
            
            # Parse the price data
            data = parse_price_data(raw_data)
            
            if not data:
                print("No valid price data found")
                return None

            # Calculate date threshold
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            
            all_retailers = []  # List of all retailers with current prices
            historical_prices = []  # All prices for average calculation
            
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
                        # Parse timestamp
                        timestamp_str = entry.get('created_at', entry.get('timestamp', ''))
                        if not timestamp_str:
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
                        
                        # Only consider prices within our date range
                        if ts < cutoff_date:
                            continue
                        
                        # Extract price
                        price = entry.get('base_price', entry.get('price', 0))
                        if price <= 0:
                            continue
                        
                        retailer_prices.append(price)
                        historical_prices.append(price)
                        
                        # Consider prices from last 7 days as "current"
                        if ts >= datetime.now(timezone.utc) - timedelta(days=7):
                            recent_prices.append(price)
                    
                    except Exception as e:
                        print(f"Error processing entry {i}: {e}")
                        continue
                
                print(f"{retailer_name}: {len(retailer_prices)} total prices, {len(recent_prices)} recent prices")
                
                # Store retailer info if we have recent prices
                if recent_prices:
                    current_price = min(recent_prices)
                    avg_price = sum(retailer_prices) / len(retailer_prices) if retailer_prices else current_price
                    
                    all_retailers.append({
                        'name': retailer_name,
                        'price': current_price,
                        'url': retailer_url,
                        'avg_price': avg_price,
                        'price_count': len(retailer_prices)
                    })
                    print(f"{retailer_name}: Current price ${current_price:.2f}")
            
            if not historical_prices or not all_retailers:
                print("No valid retailers or historical prices found")
                return None
            
            # Sort retailers by price (best to worst)
            all_retailers.sort(key=lambda x: x['price'])
            
            # Calculate overall statistics
            avg_price = statistics.mean(historical_prices)
            best_retailer = all_retailers[0]
            
            print(f"\nSummary: {len(historical_prices)} total historical prices")
            print(f"Found {len(all_retailers)} retailers with current prices")
            if product_image:
                print(f"Extracted product image: {product_image}")
            
            result = {
                "price": best_retailer['price'],
                "retailer": best_retailer['url'],
                "retailer_name": best_retailer['name'],
                "average_price": round(avg_price, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_prices_analyzed": len(historical_prices),
                "retailers_analyzed": len(all_retailers),
                "savings": round(avg_price - best_retailer['price'], 2),
                "savings_percentage": round(((avg_price - best_retailer['price']) / avg_price) * 100, 1) if avg_price > 0 else 0,
                # New: Include all retailers data and product image
                "all_retailers": all_retailers,
                "image_url": product_image  # Add the extracted image URL
            }
            
            print(f"Analysis complete: Best price ${result['price']:.2f} at {result['retailer_name']}, "
                  f"Average ${result['average_price']:.2f}, "
                  f"Found {len(all_retailers)} retailers")
            
            return result
            
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        traceback.print_exc()
        return None