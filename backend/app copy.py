from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import concurrent.futures
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import User, Watchlist, PriceHistory, SessionLocal, ProductDetails

# Import your new direct API class
from buywisely import BuyWiselyDirectAPI

app = Flask(__name__)
CORS(app)

# Initialize the direct API client
buywisely_api = BuyWiselyDirectAPI()

@app.route("/api/product-details", methods=["POST"])
def get_product_details():
    """
    Updated product details endpoint using direct API calls
    Much faster and more reliable than scraping!
    """
    urls = request.json.get("urls", [])
    username = request.headers.get('X-User', 'default')
    
    db = SessionLocal()
    try:
        # Get user settings for retailer exclusions
        user = db.query(User).filter(User.username == username).first()
        excluded_retailers = user.retailer_exclusions if user else []
        
        print(f"\n{'='*80}")
        print(f"🎯 DIRECT API REQUEST")
        print(f"👤 User: {username}")
        print(f"📦 Products: {len(urls)}")
        print(f"🚫 Excluded retailers: {excluded_retailers}")
        print(f"{'='*80}")
        
        product_details = []
        
        for url in urls:
            print(f"\n📍 Processing: {url}")
            
            # Check cache first (1-hour freshness)
            product = db.query(ProductDetails).filter(ProductDetails.url == url).first()
            
            is_recent = False
            if product and product.last_updated:
                now_utc = datetime.now(timezone.utc)
                last_updated = product.last_updated
                
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=timezone.utc)
                
                age = now_utc - last_updated
                is_recent = age.total_seconds() < 3600  # 1 hour
                print(f"💾 Cache: {'FRESH' if is_recent else 'STALE'} (age: {age})")
            
            if product and is_recent:
                print("✅ Using cached data")
                retailers_data = product.retailers if product.retailers else []
                
                product_details.append({
                    "url": product.url,
                    "product_name": product.product_name,
                    "best_price": product.best_price,
                    "average_price": product.average_price,
                    "retailer": product.best_retailer,
                    "image_url": product.image_url,
                    "savings": round(product.average_price - product.best_price, 2) if product.average_price and product.best_price else 0,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "all_retailers": retailers_data,
                    "debug_info": {
                        "source": "cache",
                        "cache_age_seconds": age.total_seconds(),
                        "method": "direct_api_cached"
                    }
                })
            else:
                print("🔄 Fetching fresh data via direct API...")
                
                try:
                    # Use direct API call instead of scraping
                    def run_direct_api():
                        return asyncio.run(
                            buywisely_api.analyze_product(url, excluded_retailers=excluded_retailers)
                        )
                    
                    # Run in thread pool to avoid blocking
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_direct_api)
                        api_result = future.result(timeout=60)  # 60 second timeout
                    
                    if api_result:
                        print(f"✅ Direct API success!")
                        print(f"💰 Price: ${api_result['price']:.2f}")
                        print(f"🏪 Retailers: {api_result['retailers_analyzed']}")
                        
                        # Prepare data for response
                        product_info = {
                            "url": url,
                            "product_name": api_result.get("product_name", url.split("/")[-1].replace("-", " ").title()),
                            "best_price": api_result["price"],
                            "average_price": api_result["average_price"],
                            "retailer": api_result["retailer_name"],
                            "image_url": api_result.get("image_url"),
                            "savings": api_result["savings"],
                            "last_updated": api_result["timestamp"],
                            "all_retailers": api_result["all_retailers"],
                            "debug_info": {
                                "source": "direct_api",
                                "retailers_analyzed": api_result["retailers_analyzed"],
                                "total_prices_analyzed": api_result["total_prices_analyzed"],
                                "savings_percentage": api_result["savings_percentage"],
                                "method": "direct_api_fresh"
                            }
                        }
                        
                        product_details.append(product_info)
                        
                        # Save/update in database
                        try:
                            if product:
                                # Update existing
                                product.product_name = product_info["product_name"]
                                product.best_price = api_result["price"]
                                product.average_price = api_result["average_price"]
                                product.best_retailer = api_result["retailer_name"]
                                product.image_url = api_result.get("image_url")
                                product.retailers = api_result["all_retailers"]
                                product.last_updated = datetime.now(timezone.utc)
                                print("💾 Updated existing database record")
                            else:
                                # Create new
                                new_product = ProductDetails(
                                    url=url,
                                    product_name=product_info["product_name"],
                                    best_price=api_result["price"],
                                    average_price=api_result["average_price"],
                                    best_retailer=api_result["retailer_name"],
                                    image_url=api_result.get("image_url"),
                                    retailers=api_result["all_retailers"],
                                    price_history=[],
                                    last_updated=datetime.now(timezone.utc)
                                )
                                db.add(new_product)
                                print("💾 Created new database record")
                            
                            db.commit()
                            
                        except Exception as e:
                            print(f"💥 Database error: {e}")
                            db.rollback()
                    else:
                        print("❌ Direct API returned no data")
                        # Add error entry
                        product_details.append({
                            "url": url,
                            "product_name": url.split("/")[-1].replace("-", " ").title(),
                            "best_price": 0,
                            "average_price": 0,
                            "retailer": "API Error",
                            "image_url": None,
                            "savings": 0,
                            "last_updated": None,
                            "all_retailers": [],
                            "debug_info": {
                                "source": "error",
                                "error_type": "api_no_data",
                                "method": "direct_api_failed",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        })
                        
                except Exception as e:
                    print(f"💥 Direct API error: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    # Add critical error entry
                    product_details.append({
                        "url": url,
                        "product_name": url.split("/")[-1].replace("-", " ").title(),
                        "best_price": 0,
                        "average_price": 0,
                        "retailer": "Critical Error",
                        "image_url": None,
                        "savings": 0,
                        "last_updated": None,
                        "all_retailers": [],
                        "debug_info": {
                            "source": "critical_error",
                            "error_type": "exception",
                            "error_message": str(e),
                            "method": "direct_api_exception",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    })
        
        print(f"\n{'='*80}")
        print(f"📊 PROCESSING COMPLETE")
        print(f"✅ Successful: {len([p for p in product_details if p['best_price'] > 0])}/{len(product_details)}")
        print(f"{'='*80}")
        
        return jsonify(product_details)
    
    except Exception as e:
        print(f"💥 Endpoint error: {e}")
        return jsonify({"error": "Failed to retrieve product details", "details": str(e)}), 500
    
    finally:
        db.close()

# Add a test endpoint for the direct API
@app.route("/api/test-direct", methods=["POST"])
def test_direct_api():
    """Test endpoint for the new direct API approach"""
    url = request.json.get("url")
    excluded_retailers = request.json.get("excluded_retailers", [])
    
    if not url:
        return jsonify({"error": "URL required"}), 400
    
    try:
        def run_test():
            return asyncio.run(
                buywisely_api.analyze_product(url, excluded_retailers=excluded_retailers)
            )
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)
        
        if result:
            return jsonify({
                "status": "success",
                "data": result,
                "message": f"Successfully fetched data for {result['retailers_analyzed']} retailers"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "No data returned from API"
            }), 404
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Update your scheduler to use direct API too
async def refresh_product_price_direct(db: Session, url: str, usernames: list):
    """Updated price refresh using direct API"""
    try:
        print(f"🔄 Refreshing price for: {url}")
        
        # Get current product data
        product = db.query(ProductDetails).filter(ProductDetails.url == url).first()
        
        # Store previous prices for comparison
        previous_best_price = product.best_price if product else None
        previous_average_price = product.average_price if product else None
        
        # Use direct API instead of scraping
        api_result = await buywisely_api.analyze_product(url, excluded_retailers=[])
        
        if not api_result:
            print(f"❌ No data from direct API for {url}")
            return
        
        # Update product in database
        product_name = api_result.get("product_name", url.split("/")[-1].replace("-", " ").title())
        
        if product:
            product.product_name = product_name
            product.best_price = api_result["price"]
            product.average_price = api_result["average_price"]
            product.best_retailer = api_result["retailer_name"]
            product.image_url = api_result.get("image_url")
            product.retailers = api_result["all_retailers"]
            product.last_updated = datetime.now(timezone.utc)
        else:
            product = ProductDetails(
                url=url,
                product_name=product_name,
                best_price=api_result["price"],
                average_price=api_result["average_price"],
                best_retailer=api_result["retailer_name"],
                image_url=api_result.get("image_url"),
                retailers=api_result["all_retailers"],
                price_history=[],
                last_updated=datetime.now(timezone.utc)
            )
            db.add(product)
        
        db.commit()
        
        # Calculate discount percentages for notifications
        previous_discount_percent = 0
        current_discount_percent = 0
        
        if previous_average_price and previous_best_price:
            previous_discount_percent = ((previous_average_price - previous_best_price) / previous_average_price) * 100
        
        if api_result["average_price"] and api_result["price"]:
            current_discount_percent = api_result["savings_percentage"]
        
        print(f"💰 Updated {product_name}: ${api_result['price']:.2f} ({current_discount_percent:.1f}% off)")
        
        # Check each user for notifications (your existing notification logic)
        # ... (keep your existing notification code)
        
    except Exception as e:
        print(f"💥 Error refreshing {url}: {e}")

if __name__ == "__main__":
    print("🚀 Starting Flask app with Direct API integration...")
    app.run(debug=True, host='0.0.0.0', port=5000)