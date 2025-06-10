from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, asyncio

from scraper import scrape_product
from pushover import send_pushover
from cache import cache  # Import cache

app = Flask(__name__)
CORS(app)

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, asyncio

from scraper import scrape_product
from pushover import send_pushover
from cache import cache  # Import cache

app = Flask(__name__)
CORS(app)

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

@app.route("/api/product-info", methods=["POST"])
def product_info():
    from scraper import scrape_product
    urls = request.json.get("urls", [])
    
    # Generate cache key
    cache_key = f"product-info:{','.join(sorted(urls))}"
    
    # Check cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return jsonify(cached_data)
    
    async def gather_data():
        results = []
        for url in urls:
            # Check individual URL cache
            url_cache_key = f"scrape:{url}"
            cached_scrape = cache.get(url_cache_key)
            
            if cached_scrape:
                best = cached_scrape
            else:
                best = await scrape_product(url)
                if best:
                    # Cache individual scrape result
                    cache.set(url_cache_key, best, ttl=300)  # 5 minutes
            
            if best:
                # Get aggregated average price
                agg_cache_key = f"aggregated-price:{url}"
                agg_data = cache.get(agg_cache_key)
                
                if agg_data and 'overall' in agg_data:
                    avg_price = agg_data['overall']['avg_price']
                else:
                    # Fallback to best price if no aggregated data
                    avg_price = best["price"]
                
                results.append({
                    "url": url,
                    "retailer": best["retailer"],
                    "best_price": best["price"],
                    "average_price": avg_price,
                    "product_name": url.split("/")[-1].replace("-", " ").capitalize()
                })
        return results

    enriched = asyncio.run(gather_data())
    
    # Cache the response
    cache.set(cache_key, enriched, ttl=300)  # 5 minutes
    
    return jsonify(enriched)

@app.route("/api/users/<username>", methods=["GET", "PUT"])
def user_settings(username):
    if request.method == "GET":
        # Check cache first
        cache_key = f"user:{username}"
        cached_user = cache.get(cache_key)
        if cached_user:
            return jsonify(cached_user)
        
        users = load_json(USERS_FILE)
        user_data = users.get(username, {})
        
        # Cache user data
        cache.set(cache_key, user_data, ttl=600)  # 10 minutes
        return jsonify(user_data)
    
    # PUT request - update user
    users = load_json(USERS_FILE)
    users[username] = request.json
    save_json(users, USERS_FILE)
    
    # Invalidate cache
    cache.delete(f"user:{username}")
    
    return jsonify({"status": "updated"})

@app.route("/api/watchlist/<username>", methods=["GET", "POST", "DELETE"])
def manage_watchlist(username):
    if request.method == "GET":
        # Check cache first
        cache_key = f"watchlist:{username}"
        cached_watchlist = cache.get(cache_key)
        if cached_watchlist is not None:
            return jsonify(cached_watchlist)
        
        watchlist = load_json(WATCHLIST_FILE)
        user_watchlist = watchlist.get(username, [])
        
        # Cache watchlist
        cache.set(cache_key, user_watchlist, ttl=600)  # 10 minutes
        return jsonify(user_watchlist)
    
    # POST or DELETE - modify watchlist
    watchlist = load_json(WATCHLIST_FILE)
    
    if request.method == "POST":
        url = request.json["url"]
        watchlist.setdefault(username, []).append(url)
    elif request.method == "DELETE":
        url = request.json["url"]
        watchlist.setdefault(username, []).remove(url)
    
    save_json(watchlist, WATCHLIST_FILE)
    
    # Invalidate cache
    cache.delete(f"watchlist:{username}")
    
    return jsonify({"status": "updated"})

@app.route("/api/product/<path:product_url>", methods=["GET"])
def product_details(product_url):
    """Get detailed product information including price history"""
    from urllib.parse import unquote
    
    # Decode and create cache key
    url = unquote(product_url)
    cache_key = f"product-detail:{url}"
    
    # Check cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return jsonify(cached_data)
    
    async def get_details():
        # Scrape current data
        current_data = await scrape_product(url)
        if not current_data:
            return None
        
        # Get product name from URL
        product_name = url.split("/")[-1].replace("-", " ").title()
        
        # Extract product image from the page
        async def get_product_image():
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url)
                
                # Wait for image to load and get the main product image
                try:
                    await page.wait_for_selector('img.product-image, img[alt*="product"], img.main-image', timeout=5000)
                    image_url = await page.evaluate('''
                        () => {
                            // Try different selectors for product images
                            const img = document.querySelector('img.product-image') || 
                                       document.querySelector('img[alt*="product"]') ||
                                       document.querySelector('img.main-image') ||
                                       document.querySelector('div.product-images img') ||
                                       document.querySelector('img[src*="product"]');
                            return img ? img.src : null;
                        }
                    ''')
                except:
                    image_url = None
                
                await browser.close()
                return image_url
        
        image_url = await get_product_image()
        
        # Process price history to get unique prices per retailer
        from datetime import datetime, timezone
        
        # Simulate multiple retailers (in production, this would come from actual scraping)
        retailers = [
            {"name": "Chemist Warehouse", "price": current_data["price"], "url": "chemistwarehouse.com.au"},
            {"name": "Priceline", "price": current_data["price"] * 1.1, "url": "priceline.com.au"},
            {"name": "Amazon AU", "price": current_data["price"] * 0.95, "url": "amazon.com.au"},
            {"name": "eBay", "price": current_data["price"] * 1.05, "url": "ebay.com.au"}
        ]
        
        # Sort by price and filter unique retailers
        retailers.sort(key=lambda x: x["price"])
        seen_retailers = set()
        unique_retailers = []
        all_prices = []
        
        for retailer in retailers:
            if retailer["name"] not in seen_retailers:
                seen_retailers.add(retailer["name"])
                unique_retailers.append(retailer)
                all_prices.append(retailer["price"])
        
        # Calculate average
        average_price = sum(all_prices) / len(all_prices) if all_prices else 0
        
        return {
            "url": url,
            "product_name": product_name,
            "image_url": image_url,
            "current_best_price": unique_retailers[0]["price"] if unique_retailers else 0,
            "average_price": round(average_price, 2),
            "retailers": unique_retailers[:5],  # Top 5 unique retailers by price
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    try:
        result = asyncio.run(get_details())
        if not result:
            return jsonify({"error": "Product not found"}), 404
        
        # Cache the result
        cache.set(cache_key, result, ttl=600)  # 10 minutes
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notify/test/<username>", methods=["POST"])
def send_test(username):
    users = load_json(USERS_FILE)
    watchlist = load_json(WATCHLIST_FILE)

    user = users.get(username)
    urls = watchlist.get(username, [])
    if not user or not urls:
        return jsonify({"error": "User or watchlist not found"}), 404

    async def run():
        best = await scrape_product(urls[0])
        if not best:
            return {"error": "No price found"}

        msg = f"🧪 Test for {username}\n${best['price']} at {best['retailer']}\n{urls[0]}"
        sent = await send_pushover(user["pushover_code"], msg)
        return {"sent": sent}

    result = asyncio.run(run())
    return jsonify(result)

@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    """Admin endpoint to clear cache"""
    cache.clear_expired()
    return jsonify({"status": "cache cleared"})

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True)

@app.route("/api/users/<username>", methods=["GET", "PUT"])
def user_settings(username):
    if request.method == "GET":
        # Check cache first
        cache_key = f"user:{username}"
        cached_user = cache.get(cache_key)
        if cached_user:
            return jsonify(cached_user)
        
        users = load_json(USERS_FILE)
        user_data = users.get(username, {})
        
        # Cache user data
        cache.set(cache_key, user_data, ttl=600)  # 10 minutes
        return jsonify(user_data)
    
    # PUT request - update user
    users = load_json(USERS_FILE)
    users[username] = request.json
    save_json(users, USERS_FILE)
    
    # Invalidate cache
    cache.delete(f"user:{username}")
    
    return jsonify({"status": "updated"})

@app.route("/api/watchlist/<username>", methods=["GET", "POST", "DELETE"])
def manage_watchlist(username):
    if request.method == "GET":
        # Check cache first
        cache_key = f"watchlist:{username}"
        cached_watchlist = cache.get(cache_key)
        if cached_watchlist is not None:
            return jsonify(cached_watchlist)
        
        watchlist = load_json(WATCHLIST_FILE)
        user_watchlist = watchlist.get(username, [])
        
        # Cache watchlist
        cache.set(cache_key, user_watchlist, ttl=600)  # 10 minutes
        return jsonify(user_watchlist)
    
    # POST or DELETE - modify watchlist
    watchlist = load_json(WATCHLIST_FILE)
    
    if request.method == "POST":
        url = request.json["url"]
        watchlist.setdefault(username, []).append(url)
    elif request.method == "DELETE":
        url = request.json["url"]
        watchlist.setdefault(username, []).remove(url)
    
    save_json(watchlist, WATCHLIST_FILE)
    
    # Invalidate cache
    cache.delete(f"watchlist:{username}")
    
    return jsonify({"status": "updated"})

@app.route("/api/product/<path:product_url>", methods=["GET"])
def product_details(product_url):
    """Get detailed product information including price history"""
    from urllib.parse import unquote
    
    # Decode and create cache key
    url = unquote(product_url)
    cache_key = f"product-detail:{url}"
    
    # Check cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return jsonify(cached_data)
    
    async def get_details():
        # Scrape current data
        current_data = await scrape_product(url)
        if not current_data:
            return None
        
        # Get product name from URL
        product_name = url.split("/")[-1].replace("-", " ").title()
        
        # Extract product image from the page
        async def get_product_image():
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url)
                
                # Wait for image to load and get the main product image
                try:
                    await page.wait_for_selector('img.product-image, img[alt*="product"], img.main-image', timeout=5000)
                    image_url = await page.evaluate('''
                        () => {
                            // Try different selectors for product images
                            const img = document.querySelector('img.product-image') || 
                                       document.querySelector('img[alt*="product"]') ||
                                       document.querySelector('img.main-image') ||
                                       document.querySelector('div.product-images img') ||
                                       document.querySelector('img[src*="product"]');
                            return img ? img.src : null;
                        }
                    ''')
                except:
                    image_url = None
                
                await browser.close()
                return image_url
        
        image_url = await get_product_image()
        
        # Process price history to get unique prices per retailer
        from datetime import datetime, timezone
        
        # Simulate multiple retailers (in production, this would come from actual scraping)
        retailers = [
            {"name": "Chemist Warehouse", "price": current_data["price"], "url": "chemistwarehouse.com.au"},
            {"name": "Priceline", "price": current_data["price"] * 1.1, "url": "priceline.com.au"},
            {"name": "Amazon AU", "price": current_data["price"] * 0.95, "url": "amazon.com.au"},
            {"name": "eBay", "price": current_data["price"] * 1.05, "url": "ebay.com.au"}
        ]
        
        # Sort by price and filter unique retailers
        retailers.sort(key=lambda x: x["price"])
        seen_retailers = set()
        unique_retailers = []
        all_prices = []
        
        for retailer in retailers:
            if retailer["name"] not in seen_retailers:
                seen_retailers.add(retailer["name"])
                unique_retailers.append(retailer)
                all_prices.append(retailer["price"])
        
        # Calculate average
        average_price = sum(all_prices) / len(all_prices) if all_prices else 0
        
        return {
            "url": url,
            "product_name": product_name,
            "image_url": image_url,
            "current_best_price": unique_retailers[0]["price"] if unique_retailers else 0,
            "average_price": round(average_price, 2),
            "retailers": unique_retailers[:5],  # Top 5 unique retailers by price
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    try:
        result = asyncio.run(get_details())
        if not result:
            return jsonify({"error": "Product not found"}), 404
        
        # Cache the result
        cache.set(cache_key, result, ttl=600)  # 10 minutes
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notify/test/<username>", methods=["POST"])
def send_test(username):
    users = load_json(USERS_FILE)
    watchlist = load_json(WATCHLIST_FILE)

    user = users.get(username)
    urls = watchlist.get(username, [])
    if not user or not urls:
        return jsonify({"error": "User or watchlist not found"}), 404

    async def run():
        best = await scrape_product(urls[0])
        if not best:
            return {"error": "No price found"}

        msg = f"🧪 Test for {username}\n${best['price']} at {best['retailer']}\n{urls[0]}"
        sent = await send_pushover(user["pushover_code"], msg)
        return {"sent": sent}

    result = asyncio.run(run())
    return jsonify(result)

@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    """Admin endpoint to clear cache"""
    cache.clear_expired()
    return jsonify({"status": "cache cleared"})

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True)

# Add this endpoint to your backend/app.py file after the existing routes

@app.route("/api/product/<path:product_url>", methods=["GET"])
def product_details(product_url):
    """Get detailed product information including price history"""
    async def get_details():
        # Decode the URL (it will be URL-encoded in the route)
        from urllib.parse import unquote
        url = unquote(product_url)
        
        # Scrape current data
        current_data = await scrape_product(url)
        if not current_data:
            return None
        
        # Get product name from URL
        product_name = url.split("/")[-1].replace("-", " ").title()
        
        # Extract product image from the page
        async def get_product_image():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url)
                
                # Wait for image to load and get the main product image
                try:
                    await page.wait_for_selector('img.product-image, img[alt*="product"], img.main-image', timeout=5000)
                    image_url = await page.evaluate('''
                        () => {
                            // Try different selectors for product images
                            const img = document.querySelector('img.product-image') || 
                                       document.querySelector('img[alt*="product"]') ||
                                       document.querySelector('img.main-image') ||
                                       document.querySelector('div.product-images img') ||
                                       document.querySelector('img[src*="product"]');
                            return img ? img.src : null;
                        }
                    ''')
                except:
                    image_url = None
                
                await browser.close()
                return image_url
        
        image_url = await get_product_image()
        
        # Process price history to get unique prices per retailer
        from datetime import datetime, timezone, timedelta
        one_month_ago = datetime.now(timezone.utc) - timedelta(days=30)
        
        # Group prices by retailer and get the best (lowest) price for each
        retailer_prices = {}
        all_prices = []
        
        # Get the full data from scraping (this is a simplified version)
        # In reality, you'd need to modify scrape_product to return more data
        # For now, we'll simulate multiple retailers
        retailers = [
            {"name": "Chemist Warehouse", "price": current_data["price"], "url": "chemistwarehouse.com.au"},
            {"name": "Priceline", "price": current_data["price"] * 1.1, "url": "priceline.com.au"},
            {"name": "Amazon AU", "price": current_data["price"] * 0.95, "url": "amazon.com.au"},
            {"name": "eBay", "price": current_data["price"] * 1.05, "url": "ebay.com.au"}
        ]
        
        # Sort by price and filter unique retailers
        retailers.sort(key=lambda x: x["price"])
        seen_retailers = set()
        unique_retailers = []
        
        for retailer in retailers:
            if retailer["name"] not in seen_retailers:
                seen_retailers.add(retailer["name"])
                unique_retailers.append(retailer)
                all_prices.append(retailer["price"])
        
        # Get aggregated average price from cache or calculate
        aggregated_cache_key = f"aggregated-price:{url}"
        aggregated_data = cache.get(aggregated_cache_key)
        
        if aggregated_data and 'overall' in aggregated_data:
            # Use the monthly aggregated average
            average_price = aggregated_data['overall']['avg_price']
        else:
            # Fallback to simple average of current prices
            average_price = sum(all_prices) / len(all_prices) if all_prices else 0
        
        return {
            "url": url,
            "product_name": product_name,
            "image_url": image_url,
            "current_best_price": unique_retailers[0]["price"] if unique_retailers else 0,
            "average_price": round(average_price, 2),
            "retailers": unique_retailers[:5],  # Top 5 unique retailers by price
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    try:
        result = asyncio.run(get_details())
        if not result:
            return jsonify({"error": "Product not found"}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500