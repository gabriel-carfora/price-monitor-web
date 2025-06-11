from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import asyncio
import json
import threading
import statistics
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session
from database import User, Watchlist, PriceHistory, SessionLocal, ProductDetails
from scraper import scrape_product
from pushover import send_pushover
from cache import cache

app = Flask(__name__)
CORS(app)

class DatabaseService:
    """Centralized database operations"""
    
    @staticmethod
    def get_session() -> Session:
        """Create and return a database session"""
        return SessionLocal()
    
    @staticmethod
    def get_user(db: Session, username: str) -> Optional[Dict[str, Any]]:
        """Retrieve or create a user"""
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            # Create default user if not exists
            user = User(
                username=username, 
                pushover_code='', 
                price_limit=None, 
                retailer_exclusions=[],
                notification_frequency_days=1
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        return {
            'username': user.username,
            'pushover_code': user.pushover_code,
            'price_limit': user.price_limit,
            'retailer_exclusions': user.retailer_exclusions,
            'notification_frequency_days': user.notification_frequency_days
        }
    
    @staticmethod
    def update_user(db: Session, username: str, user_data: Dict[str, Any]) -> Dict[str, str]:
        """Update user settings"""
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            user = User(username=username)
            db.add(user)
        
        # Update user fields
        user.pushover_code = user_data.get('pushover_code', user.pushover_code)
        user.price_limit = user_data.get('price_limit', user.price_limit)
        user.retailer_exclusions = user_data.get('retailer_exclusions', user.retailer_exclusions)
        user.notification_frequency_days = user_data.get('notification_frequency_days', user.notification_frequency_days)
        
        db.commit()
        return {"status": "updated"}
    
    @staticmethod
    def get_watchlist(db: Session, username: str) -> List[str]:
        """Retrieve watchlist for a user"""
        watchlist_items = db.query(Watchlist).filter(Watchlist.username == username).all()
        return [item.url for item in watchlist_items]
    
    @staticmethod
    def add_to_watchlist(db: Session, username: str, url: str) -> Dict[str, str]:
        """Add URL to user's watchlist"""
        existing = db.query(Watchlist).filter(
            Watchlist.username == username, 
            Watchlist.url == url
        ).first()
        
        if not existing:
            new_item = Watchlist(username=username, url=url)
            db.add(new_item)
            db.commit()
        
        return {"status": "updated"}
    
    @staticmethod
    def remove_from_watchlist(db: Session, username: str, url: str) -> Dict[str, str]:
        """Remove URL from user's watchlist"""
        db.query(Watchlist).filter(
            Watchlist.username == username, 
            Watchlist.url == url
        ).delete()
        db.commit()
        
        return {"status": "updated"}

class CacheService:
    """Centralized caching operations"""
    
    @staticmethod
    def get_user_cache_key(username: str) -> str:
        return f"user:{username}"
    
    @staticmethod
    def get_watchlist_cache_key(username: str) -> str:
        return f"watchlist:{username}"
    
    @staticmethod
    def get_product_info_cache_key(urls: List[str]) -> str:
        return f"product-info:{','.join(sorted(urls))}"
    
    @staticmethod
    def get_product_detail_cache_key(url: str) -> str:
        return f"product-detail:{url}"

class ScraperService:
    """Centralized scraping operations"""
    
    @staticmethod
    async def get_product_details(url: str) -> Dict[str, Any]:
        """Scrape product details with fallback and error handling"""
        try:
            # Scrape current data
            current_data = await scrape_product(url)
            if not current_data:
                return None
            
            # Get product name from URL
            product_name = url.split("/")[-1].replace("-", " ").title()
            
            # Extract product image (placeholder, can be expanded)
            image_url = await ScraperService._extract_product_image(url)
            
            # Simulate multiple retailers 
            retailers = [
                {"name": "Chemist Warehouse", "price": current_data["price"], "url": "chemistwarehouse.com.au"},
                {"name": "Priceline", "price": current_data["price"] * 1.1, "url": "priceline.com.au"},
                {"name": "Amazon AU", "price": current_data["price"] * 0.95, "url": "amazon.com.au"},
                {"name": "eBay", "price": current_data["price"] * 1.05, "url": "ebay.com.au"}
            ]
            
            # Sort and filter unique retailers
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
                "retailers": unique_retailers[:5],
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            print(f"Product scraping error for {url}: {e}")
            return None
    
    @staticmethod
    async def _extract_product_image(url: str) -> Optional[str]:
        """Extract product image with Playwright"""
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url)
            
            try:
                await page.wait_for_selector('img.product-image, img[alt*="product"], img.main-image', timeout=5000)
                image_url = await page.evaluate('''
                    () => {
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

@app.route("/api/users/<username>", methods=["GET", "PUT"])
def user_settings(username):
    """Manage user settings with caching"""
    db = DatabaseService.get_session()
    cache_key = CacheService.get_user_cache_key(username)
    
    try:
        if request.method == "GET":
            # Check cache first
            cached_user = cache.get(cache_key)
            if cached_user:
                return jsonify(cached_user)
            
            # Retrieve or create user
            user_data = DatabaseService.get_user(db, username)
            
            # Cache user data
            cache.set(cache_key, user_data, ttl=600)  # 10 minutes
            return jsonify(user_data)
        
        # PUT request - update user
        user_data = request.json
        result = DatabaseService.update_user(db, username, user_data)
        
        # Invalidate cache
        cache.delete(cache_key)
        
        return jsonify(result)
    
    finally:
        db.close()

@app.route("/api/watchlist/<username>", methods=["GET", "POST", "DELETE"])
def manage_watchlist(username):
    """Manage user's watchlist with caching"""
    db = DatabaseService.get_session()
    cache_key = CacheService.get_watchlist_cache_key(username)
    
    try:
        if request.method == "GET":
            # Check cache first
            cached_watchlist = cache.get(cache_key)
            if cached_watchlist is not None:
                return jsonify(cached_watchlist)
            
            # Get watchlist from database
            user_watchlist = DatabaseService.get_watchlist(db, username)
            
            # Cache watchlist
            cache.set(cache_key, user_watchlist, ttl=600)  # 10 minutes
            return jsonify(user_watchlist)
        
        # POST or DELETE - modify watchlist
        url = request.json["url"]
        if request.method == "POST":
            result = DatabaseService.add_to_watchlist(db, username, url)
        else:  # DELETE
            result = DatabaseService.remove_from_watchlist(db, username, url)
        
        # Invalidate cache
        cache.delete(cache_key)
        
        return jsonify(result)
    
    finally:
        db.close()

@app.route("/api/product-info", methods=["POST"])
def product_info():
    """Retrieve product information for multiple URLs"""
    urls = request.json.get("urls", [])
    cache_key = CacheService.get_product_info_cache_key(urls)
    
    # Check cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return jsonify(cached_data)
    
    def gather_data():
        results = []
        for url in urls:
            # Check individual URL cache
            url_cache_key = f"scrape:{url}"
            cached_scrape = cache.get(url_cache_key)
            
            if cached_scrape:
                best = cached_scrape
            else:
                # Use synchronous scraping
                best = scrape_product(url)
                if best:
                    # Cache individual scrape result
                    try:
                        cache.set(url_cache_key, best, ttl=300)  # 5 minutes
                    except Exception as e:
                        print(f"Error caching scrape result: {e}")
            
            if best:
                results.append({
                    "url": url,
                    "retailer": best["retailer"],
                    "best_price": best["price"],
                    "average_price": best.get("average_price", best["price"]),
                    "product_name": url.split("/")[-1].replace("-", " ").capitalize()
                })
        return results

    enriched = gather_data()
    
    # Cache the response
    try:
        cache.set(cache_key, enriched, ttl=300)  # 5 minutes
    except Exception as e:
        print(f"Error caching product info: {e}")
    
    return jsonify(enriched)

@app.route("/api/product/<path:product_url>", methods=["GET"])
async def product_details(product_url):
    """Get detailed product information"""
    # Decode the URL
    url = unquote(product_url)
    cache_key = CacheService.get_product_detail_cache_key(url)
    
    # Check cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return jsonify(cached_data)
    
    # Scrape product details
    result = await ScraperService.get_product_details(url)
    
    if not result:
        return jsonify({"error": "Product not found"}), 404
    
    # Cache the result
    cache.set(cache_key, result, ttl=600)  # 10 minutes
    
    return jsonify(result)

@app.route("/api/aggregate-prices", methods=["POST"])
def aggregate_prices():
    """Comprehensive price aggregation for all watched products"""
    def run_aggregation():
        db = SessionLocal()
        try:
            # Get all unique URLs from watchlists
            all_watchlist_items = db.query(Watchlist).all()
            all_urls = set(item.url for item in all_watchlist_items)
            
            print(f"Starting price aggregation for {len(all_urls)} products...")
            
            for url in all_urls:
                try:
                    # Scrape product details
                    product_data = asyncio.run(ScraperService.get_product_details(url))
                    
                    if not product_data:
                        print(f"No data found for {url}")
                        continue
                    
                    # Prepare detailed product information
                    product_details = {
                        "url": url,
                        "product_name": product_data.get("product_name", 
                            url.split("/")[-1].replace("-", " ").title()),
                        "best_price": product_data.get("current_best_price", 0),
                        "average_price": product_data.get("average_price", 0),
                        "best_retailer": product_data.get("retailers", [{}])[0].get("name", "Unknown"),
                        "image_url": product_data.get("image_url"),
                        "retailers": product_data.get("retailers", []),
                        "last_updated": datetime.now(timezone.utc)
                    }
                    
                    # Check if product already exists in database
                    existing_product = db.query(ProductDetails).filter(ProductDetails.url == url).first()
                    
                    if existing_product:
                        # Update existing product
                        for key, value in product_details.items():
                            setattr(existing_product, key, value)
                    else:
                        # Create new product entry
                        new_product = ProductDetails(**product_details)
                        db.add(new_product)
                    
                    # Commit changes for this product
                    db.commit()
                    
                    print(f"Processed {url}: ${product_details['best_price']} at {product_details['best_retailer']}")
                
                except Exception as e:
                    print(f"Error processing {url}: {e}")
                    db.rollback()
            
            print("Price aggregation complete.")
        
        except Exception as e:
            print(f"Critical aggregation error: {e}")
        
        finally:
            db.close()
    
    # Run in a separate thread
    thread = threading.Thread(target=run_aggregation)
    thread.start()
    
    return jsonify({
        "status": "Aggregation started",
        "message": "Price aggregation process has been initiated in the background."
    })

@app.route("/api/product-details", methods=["POST"])
def get_product_details():
    """Retrieve pre-processed product details for multiple URLs"""
    urls = request.json.get("urls", [])
    
    db = SessionLocal()
    try:
        # Fetch product details for given URLs
        product_details = []
        for url in urls:
            product = db.query(ProductDetails).filter(ProductDetails.url == url).first()
            
            if product:
                product_details.append({
                    "url": product.url,
                    "product_name": product.product_name,
                    "best_price": product.best_price,
                    "average_price": product.average_price,
                    "retailer": product.best_retailer,
                    "image_url": product.image_url
                })
        
        return jsonify(product_details)
    
    except Exception as e:
        print(f"Error retrieving product details: {e}")
        return jsonify({"error": "Failed to retrieve product details"}), 500
    
    finally:
        db.close()

if __name__ == "__main__":
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    app.run(debug=True)