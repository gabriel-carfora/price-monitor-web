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
                product_details.append({
                    "url": product.url,
                    "product_name": product.product_name,
                    "best_price": product.best_price,
                    "average_price": product.average_price,
                    "retailer": product.best_retailer,
                    "image_url": product.image_url,
                    "savings": round(product.average_price - product.best_price, 2) if product.average_price and product.best_price else 0,
                    "last_updated": product.last_updated.isoformat() if product.last_updated else None,
                    "all_retailers": product.retailers or [],
                    "debug_info": {"source": "cache", "cache_age_seconds": age.total_seconds(), "method": "direct_api_cached"}
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
                            product.best_price = api['price']
                            product.average_price = api['average_price']
                            product.best_retailer = api['retailer_name']
                            product.image_url = api.get('image_url')
                            product.retailers = api['all_retailers']
                            product.last_updated = datetime.now(timezone.utc)
                        else:
                            db.add(ProductDetails(
                                url=url,
                                product_name=info['product_name'],
                                best_price=api['price'],
                                average_price=api['average_price'],
                                best_retailer=api['retailer_name'],
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

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    print("Starting price refresh scheduler...")
    price_scheduler.start()
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        print("Stopping scheduler...")
        price_scheduler.stop()
