import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import threading
import statistics
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote, urlparse
import concurrent.futures

from sqlalchemy.orm import Session
from buywisely import BuyWiselyDirectAPI

from database import User, Watchlist, PriceHistory, SessionLocal, ProductDetails
from scraper import scrape_product_async
from pushover import send_pushover
from cache import cache
from scheduler import price_scheduler
from image_scraper import get_high_quality_image, get_thumbnail_image
from flask import make_response

# Initialize API client
buywisely_api = BuyWiselyDirectAPI()

app = Flask(__name__)
CORS(app)

class DatabaseService:
    """Centralized database operations"""
    @staticmethod
    def get_session() -> Session:
        return SessionLocal()

    @staticmethod
    def get_user(db: Session, username: str) -> Optional[Dict[str, Any]]:
        user = db.query(User).filter(User.username == username).first()
        if not user:
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
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(username=username)
            db.add(user)
        user.pushover_code = user_data.get('pushover_code', user.pushover_code)
        user.price_limit = user_data.get('price_limit', user.price_limit)
        user.retailer_exclusions = user_data.get('retailer_exclusions', user.retailer_exclusions)
        user.notification_frequency_days = user_data.get('notification_frequency_days', user.notification_frequency_days)
        print(f"💾 Saving retailer exclusions for {username}: {user_data.get('retailer_exclusions')}")
        db.commit()
        return {"status": "updated"}

    @staticmethod
    def get_watchlist(db: Session, username: str) -> List[str]:
        items = db.query(Watchlist).filter(Watchlist.username == username).all()
        return [item.url for item in items]

    @staticmethod
    def add_to_watchlist(db: Session, username: str, url: str) -> Dict[str, str]:
        exists = db.query(Watchlist).filter(
            Watchlist.username == username,
            Watchlist.url == url
        ).first()
        if not exists:
            db.add(Watchlist(username=username, url=url))
            db.commit()
        return {"status": "updated"}

    @staticmethod
    def remove_from_watchlist(db: Session, username: str, url: str) -> Dict[str, str]:
        db.query(Watchlist).filter(
            Watchlist.username == username,
            Watchlist.url == url
        ).delete()
        db.commit()
        return {"status": "updated"}

@app.route("/api/users/<username>", methods=["GET", "PUT"])
def user_settings(username):
    db = DatabaseService.get_session()
    try:
        if request.method == "GET":
            return jsonify(DatabaseService.get_user(db, username))

        data = request.json or {}
        if 'price_limit' in data and data['price_limit'] is not None:
            try:
                pl = float(data['price_limit'])
                if not 0 <= pl <= 100:
                    return jsonify({"error": "Price limit must be between 0 and 100 percent"}), 400
                data['price_limit'] = pl
            except Exception:
                return jsonify({"error": "Price limit must be a valid number"}), 400

        return jsonify(DatabaseService.update_user(db, username, data))
    finally:
        
        db.close()

@app.route("/api/refresh-prices", methods=["POST"])
def manual_refresh():
    def run_refresh():
        price_scheduler._daily_price_refresh()
    threading.Thread(target=run_refresh).start()
    return jsonify({
        "status": "Refresh started",
        "message": "Manual price refresh has been initiated."
    })

@app.route("/api/scheduler/status", methods=["GET"])
def scheduler_status():
    return jsonify({
        "running": price_scheduler.running,
        "next_refresh": "Daily at 6:00 AM UTC"
    })

@app.route("/api/watchlist/<username>", methods=["GET", "POST", "DELETE"])
def manage_watchlist(username):
    db = DatabaseService.get_session()
    try:
        if request.method == "GET":
            return jsonify(DatabaseService.get_watchlist(db, username))
        url = request.json.get("url")
        if request.method == "POST":
            return jsonify(DatabaseService.add_to_watchlist(db, username, url))
        return jsonify(DatabaseService.remove_from_watchlist(db, username, url))
    finally:
        db.close()

@app.route("/api/product-details", methods=["POST"])
def get_product_details():
    urls = request.json.get("urls", [])
    username = request.headers.get('X-User', 'default')
    print("THIS RIGHT HERE DAWG\n\n\n\n\n\n")
    print(username)
    db = SessionLocal()
    product_details = []
    try:
        user = db.query(User).filter(User.username == username).first()
        excluded = user.retailer_exclusions if user else []

        for url in urls:
            product = db.query(ProductDetails).filter(ProductDetails.url == url).first()
            fresh = False
            if product and product.last_updated:
                age = datetime.now(timezone.utc) - (product.last_updated.replace(tzinfo=timezone.utc) if product.last_updated.tzinfo is None else product.last_updated)
                fresh = age.total_seconds() < 3600
            if product and fresh:
                filtered_retailers = [r for r in (product.retailers or []) if not any(ex.lower() in r.get('url', '').lower() for ex in excluded)]

                best = min(filtered_retailers, key=lambda r: r['price']) if filtered_retailers else None
                average_price = round(sum(r['price'] for r in filtered_retailers) / len(filtered_retailers), 2) if filtered_retailers else 0

                product_details.append({
                    "url": product.url,
                    "product_name": product.product_name,
                    "best_price": best['price'] if best else 0,
                    "average_price": average_price,
                    "retailer": best['name'] if best else 'N/A',
                    "image_url": product.image_url,
                    "savings": round(average_price - best['price'], 2) if best else 0,
                    "last_updated": product.last_updated.isoformat() if product.last_updated else None,
                    "all_retailers": filtered_retailers,
                    "debug_info": {
                        "source": "cache_filtered",
                        "cache_age_seconds": age.total_seconds(),
                        "method": "direct_api_cached_filtered"
                    }
                })

            else:
                # Fetch fresh
                def call_api():
                    return buywisely_api.analyze_product(url, excluded_retailers=excluded)
                with concurrent.futures.ThreadPoolExecutor() as exec:
                    future = exec.submit(call_api)
                    api = future.result(timeout=60)
                if api:
                    info = {
                        "url": url,
                        "product_name": api.get("product_name", url.split('/')[-1].replace('-', ' ').title()),
                        "best_price": api["best_price"],
                        "average_price": api["average_price"],
                        "retailer": api["best_retailer"],
                        "image_url": api.get("image_url"),
                        "savings": api["savings"],
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                        "all_retailers": api["all_retailers"],
                        "debug_info": {
                            "source": "direct_api",
                            "retailers_analyzed": api["retailers_analyzed"],
                            "total_prices_analyzed": api["total_prices"],
                            "savings_percentage": api["savings_pct"],
                            "method": "direct_api_fresh"
                        }
                    }

                    product_details.append(info)
                    try:
                        if product:
                            product.product_name = info['product_name']
                            product.best_price = api['best_price']
                            product.average_price = api['average_price']
                            product.best_retailer = api["best_retailer"]
                            product.image_url = api.get('image_url')
                            product.retailers = api['all_retailers']
                            product.last_updated = datetime.now(timezone.utc)
                        else:
                            db.add(ProductDetails(
                                url=url,
                                product_name=info['product_name'],
                                best_price=api['best_price'],
                                average_price=api['average_price'],
                                best_retailer=api["best_retailer"],
                                image_url=api.get('image_url'),
                                retailers=api['all_retailers'],
                                last_updated=datetime.now(timezone.utc)
                            ))
                        db.commit()
                    except Exception as db_err:
                        print("💥 Database error:", db_err)
                        db.rollback()
                else:
                    product_details.append({
                        "url": url,
                        "product_name": url.split('/')[-1].replace('-', ' ').title(),
                        "best_price": 0,
                        "average_price": 0,
                        "retailer": "API Error",
                        "image_url": None,
                        "savings": 0,
                        "last_updated": None,
                        "all_retailers": [],
                        "debug_info": {"source": "error", "error_type": "api_no_data", "method": "direct_api_failed", "timestamp": datetime.now(timezone.utc).isoformat()}
                    })
        return jsonify(product_details)
    except Exception as e:
        print("💥 Endpoint error:", e)
        return jsonify({"error": "Failed to retrieve product details", "details": str(e)}), 500
    finally:
        db.close()

@app.route("/api/aggregate-prices", methods=["POST"])
def aggregate_prices():
    threading.Thread(target=lambda: print("Starting background price aggregation..."))
    return jsonify({"status": "Aggregation started", "message": "Price aggregation process initiated."})

@app.route("/api/search", methods=["POST"])
def search_products():
    """
    Search for products on BuyWisely
    """
    try:
        data = request.json or {}
        query = data.get('query', '').strip()
        limit = min(data.get('limit', 20), 20)  # Cap at 100 results
        
        if not query:
            return jsonify({"error": "Query parameter is required"}), 400
        
        if len(query) < 2:
            return jsonify({"error": "Query must be at least 2 characters"}), 400
        
        print(f"🔍 API Search request: '{query}' (limit: {limit})")
        
        # Import the scraper
        from search_scraper import search_products_sync
        
        # Perform the search
        results = search_products_sync(query, max_results=limit)
        
        response = {
            "query": query,
            "results": results,
            "total_found": len(results),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        print(f"✅ Search completed: {len(results)} results for '{query}'")
        return jsonify(response)
        
    except Exception as e:
        print(f"💥 Search API error: {e}")
        traceback.print_exc()
        return jsonify({
            "error": "Search failed", 
            "details": str(e)
        }), 500

@app.route("/api/search/suggestions", methods=["POST"])
def get_search_suggestions():
    """
    Get quick product suggestions for a search query
    
    Request body:
    {
        "query": "search term",
        "limit": 10  // optional, default 10
    }
    
    Returns:
    {
        "query": "search term",
        "suggestions": [
            {
                "title": "Product Name",
                "url": "https://buywisely.com.au/product/...",
                "offers": "Compare 10 offers"
            }
        ]
    }
    """
    try:
        data = request.json or {}
        query = data.get('query', '').strip()
        limit = min(data.get('limit', 10), 20)  # Cap at 20 suggestions
        
        if not query:
            return jsonify({"error": "Query parameter is required"}), 400
        
        if len(query) < 2:
            return jsonify({"error": "Query must be at least 2 characters"}), 400
        
        print(f"💡 API Suggestions request: '{query}' (limit: {limit})")
        
        # Import the scraper
        from search_scraper import get_suggestions_sync
        
        # Get suggestions
        suggestions = get_suggestions_sync(query, limit=limit)
        
        response = {
            "query": query,
            "suggestions": suggestions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        print(f"✅ Suggestions completed: {len(suggestions)} results for '{query}'")
        return jsonify(response)
        
    except Exception as e:
        print(f"💥 Suggestions API error: {e}")
        return jsonify({
            "error": "Suggestions failed", 
            "details": str(e)
        }), 500

@app.route("/api/product-image", methods=["POST", "OPTIONS"])
def get_product_image():
    if request.method == "OPTIONS":
        # Preflight request: respond with CORS-safe OK
        return '', 204

    try:
        data = request.get_json(force=True) or {}
        slug = data.get("slug", "").strip()
        size = data.get("size", "thumb").lower()

        if not slug or size not in ("thumb", "fullsize"):
            return jsonify({"error": "Missing or invalid parameters"}), 400

        image_url = (
            get_thumbnail_image(slug)
            if size == "thumb"
            else get_high_quality_image(slug)
        )

        response = jsonify({
            "slug": slug,
            "size": size,
            "image_url": image_url
        })
        response.headers['Cache-Control'] = 'public, max-age=604800'
        return response

    except Exception as e:
        print("💥 Image API error:", e)
        return jsonify({
            "error": "Image lookup failed",
            "details": str(e)
        }), 500
    
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    print("Starting price refresh scheduler...")
    price_scheduler.start()
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        print("Stopping scheduler...")
        price_scheduler.stop()
