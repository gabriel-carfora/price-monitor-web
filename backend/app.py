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
import concurrent.futures

from sqlalchemy.orm import Session
from database import User, Watchlist, PriceHistory, SessionLocal, ProductDetails
from scraper import scrape_product_async
from pushover import send_pushover
from cache import cache
from scheduler import price_scheduler

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

@app.route("/api/users/<username>", methods=["GET", "PUT"])
def user_settings(username):
    """Manage user settings with percentage-based price limits"""
    db = DatabaseService.get_session()
    
    try:
        if request.method == "GET":
            # Retrieve or create user
            user_data = DatabaseService.get_user(db, username)
            return jsonify(user_data)
        
        # PUT request - update user with validation
        user_data = request.json
        
        # Validate price_limit is a percentage (0-100)
        if 'price_limit' in user_data and user_data['price_limit'] is not None:
            try:
                price_limit = float(user_data['price_limit'])
                if price_limit < 0 or price_limit > 100:
                    return jsonify({"error": "Price limit must be between 0 and 100 percent"}), 400
                user_data['price_limit'] = price_limit
            except (ValueError, TypeError):
                return jsonify({"error": "Price limit must be a valid number"}), 400
        
        result = DatabaseService.update_user(db, username, user_data)
        return jsonify(result)
    
    finally:
        db.close()

# Add a manual refresh endpoint for testing
@app.route("/api/refresh-prices", methods=["POST"])
def manual_refresh():
    """Manually trigger price refresh for testing"""
    try:
        # Run a manual refresh in the background
        def run_refresh():
            asyncio.run(price_scheduler._daily_price_refresh())
        
        thread = threading.Thread(target=run_refresh)
        thread.start()
        
        return jsonify({
            "status": "Refresh started",
            "message": "Manual price refresh has been initiated."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Add endpoint to check scheduler status
@app.route("/api/scheduler/status", methods=["GET"])
def scheduler_status():
    """Get scheduler status"""
    return jsonify({
        "running": price_scheduler.running,
        "next_refresh": "Daily at 6:00 AM UTC"
    })


@app.route("/api/watchlist/<username>", methods=["GET", "POST", "DELETE"])
def manage_watchlist(username):
    """Manage user's watchlist with caching"""
    db = DatabaseService.get_session()
    
    try:
        if request.method == "GET":
            # Get watchlist from database
            user_watchlist = DatabaseService.get_watchlist(db, username)
            return jsonify(user_watchlist)
        
        # POST or DELETE - modify watchlist
        url = request.json["url"]
        if request.method == "POST":
            result = DatabaseService.add_to_watchlist(db, username, url)
        else:  # DELETE
            result = DatabaseService.remove_from_watchlist(db, username, url)
        
        return jsonify(result)
    
    finally:
        db.close()


@app.route("/api/product-details", methods=["POST"])
def get_product_details():
    """Retrieve product details with proper price analysis and images"""
    urls = request.json.get("urls", [])
    username = request.headers.get('X-User', 'default')
    
    db = SessionLocal()
    try:
        # Get user settings for retailer exclusions
        user = db.query(User).filter(User.username == username).first()
        excluded_retailers = user.retailer_exclusions if user else []
        
        product_details = []
        
        for url in urls:
            # First try to get from ProductDetails table
            product = db.query(ProductDetails).filter(ProductDetails.url == url).first()
            
            # Check if data is recent (less than 1 hour old)
            is_recent = False
            if product and product.last_updated:
                # Ensure both datetimes are timezone-aware
                now_utc = datetime.now(timezone.utc)
                last_updated = product.last_updated
                
                # If last_updated is naive, assume it's UTC
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=timezone.utc)
                
                age = now_utc - last_updated
                is_recent = age.total_seconds() < 3600  # 1 hour
            
            if product and is_recent:
                # Use cached data
                retailers_data = product.retailers if product.retailers else []
                
                product_details.append({
                    "url": product.url,
                    "product_name": product.product_name,
                    "best_price": product.best_price,
                    "average_price": product.average_price,
                    "retailer": product.best_retailer,
                    "image_url": product.image_url,  # Include cached image
                    "savings": round(product.average_price - product.best_price, 2) if product.average_price and product.best_price else 0,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "all_retailers": retailers_data
                })
            else:
                # Scrape fresh data
                print(f"Scraping fresh data for: {url}")
                
                try:
                    # Use asyncio to run the async scraper with user exclusions
                    try:
                        scraped_data = asyncio.run(
                            scrape_product_async(url, excluded_retailers=excluded_retailers)
                        )
                    except RuntimeError:
                        # Already in an event loop, use thread pool
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(
                                asyncio.run, 
                                scrape_product_async(url, excluded_retailers=excluded_retailers)
                            )
                            scraped_data = future.result(timeout=60)
                    
                    if scraped_data:
                        # Extract product name from URL
                        product_name = url.split("/")[-1].replace("-", " ").title()
                        
                        # Get all retailers data and image URL
                        all_retailers = scraped_data.get("all_retailers", [])
                        image_url = scraped_data.get("image_url")  # Extract image URL
                        
                        product_info = {
                            "url": url,
                            "product_name": product_name,
                            "best_price": scraped_data["price"],
                            "average_price": scraped_data.get("average_price", scraped_data["price"]),
                            "retailer": scraped_data.get("retailer_name", "Unknown"),
                            "image_url": image_url,  # Include scraped image
                            "savings": scraped_data.get("savings", 0),
                            "last_updated": scraped_data.get("timestamp"),
                            "all_retailers": all_retailers
                        }
                        
                        product_details.append(product_info)
                        
                        # Save/update in database
                        try:
                            if product:
                                # Update existing
                                product.product_name = product_name
                                product.best_price = scraped_data["price"]
                                product.average_price = scraped_data.get("average_price", scraped_data["price"])
                                product.best_retailer = scraped_data.get("retailer_name", "Unknown")
                                product.image_url = image_url  # Store image URL
                                product.retailers = all_retailers
                                product.last_updated = datetime.now(timezone.utc)
                            else:
                                # Create new
                                new_product = ProductDetails(
                                    url=url,
                                    product_name=product_name,
                                    best_price=scraped_data["price"],
                                    average_price=scraped_data.get("average_price", scraped_data["price"]),
                                    best_retailer=scraped_data.get("retailer_name", "Unknown"),
                                    image_url=image_url,  # Store image URL
                                    retailers=all_retailers,
                                    price_history=[],
                                    last_updated=datetime.now(timezone.utc)
                                )
                                db.add(new_product)
                            
                            db.commit()
                            
                            # Log what we saved
                            image_status = "with image" if image_url else "without image"
                            print(f"Saved product data: {product_name} - ${scraped_data['price']:.2f} "
                                  f"with {len(all_retailers)} retailers {image_status}")
                            
                        except Exception as e:
                            print(f"Failed to save to database: {e}")
                            db.rollback()
                    else:
                        print(f"Failed to scrape product: {url}")
                        # Add placeholder entry
                        product_details.append({
                            "url": url,
                            "product_name": url.split("/")[-1].replace("-", " ").title(),
                            "best_price": 0,
                            "average_price": 0,
                            "retailer": "Unknown",
                            "image_url": None,
                            "savings": 0,
                            "last_updated": None,
                            "all_retailers": []
                        })
                        
                except Exception as e:
                    print(f"Error scraping {url}: {e}")
                    # Add error entry
                    product_details.append({
                        "url": url,
                        "product_name": url.split("/")[-1].replace("-", " ").title(),
                        "best_price": 0,
                        "average_price": 0,
                        "retailer": "Error",
                        "image_url": None,
                        "savings": 0,
                        "last_updated": None,
                        "all_retailers": []
                    })
        
        return jsonify(product_details)
    
    except Exception as e:
        print(f"Error retrieving product details: {e}")
        return jsonify({"error": "Failed to retrieve product details"}), 500
    
    finally:
        db.close()

@app.route("/api/aggregate-prices", methods=["POST"])
def aggregate_prices():
    """Trigger price aggregation"""
    def run_aggregation():
        print("Starting background price aggregation...")
        # This will now happen automatically when products are accessed
        # due to the 1-hour cache in get_product_details
    
    # Run in a separate thread
    thread = threading.Thread(target=run_aggregation)
    thread.start()
    
    return jsonify({
        "status": "Aggregation started",
        "message": "Price aggregation process has been initiated."
    })


if __name__ == "__main__":
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    # Start the price refresh scheduler
    print("Starting price refresh scheduler...")
    price_scheduler.start()
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        # Clean shutdown
        print("Stopping price refresh scheduler...")
        price_scheduler.stop()