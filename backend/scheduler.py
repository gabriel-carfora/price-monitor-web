# backend/scheduler.py - Daily price refresh system

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from database import User, Watchlist, PriceHistory, ProductDetails, SessionLocal
from scraper import scrape_product_async
from pushover import send_pushover
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PriceRefreshScheduler:
    def __init__(self):
        self.running = False
        self.thread = None
        
    def start(self):
        """Start the background scheduler"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.thread.start()
            logger.info("Price refresh scheduler started")
    
    def stop(self):
        """Stop the background scheduler"""
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Price refresh scheduler stopped")
    
    def _run_scheduler(self):
        """Main scheduler loop"""
        while self.running:
            try:
                # Check if it's time for daily refresh (run at 6 AM)
                now = datetime.now(timezone.utc)
                
                # Calculate next 6 AM UTC
                next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
                if now.hour >= 6:
                    next_run += timedelta(days=1)
                
                # Wait until next run time
                sleep_seconds = (next_run - now).total_seconds()
                logger.info(f"Next price refresh scheduled for: {next_run}")
                
                # Sleep in chunks to allow for clean shutdown
                while sleep_seconds > 0 and self.running:
                    chunk_sleep = min(sleep_seconds, 60)  # Sleep in 1-minute chunks
                    time.sleep(chunk_sleep)
                    sleep_seconds -= chunk_sleep
                
                if self.running:
                    # Run the daily refresh
                    asyncio.run(self._daily_price_refresh())
                    
            except Exception as e:
                logger.error(f"Error in scheduler: {e}")
                time.sleep(300)  # Wait 5 minutes before retrying
    
    async def _daily_price_refresh(self):
        """Perform daily price refresh for all tracked products"""
        logger.info("Starting daily price refresh...")
        
        db = SessionLocal()
        try:
            # Get all unique URLs from watchlists
            watchlist_items = db.query(Watchlist).all()
            unique_urls = set(item.url for item in watchlist_items)
            
            logger.info(f"Refreshing prices for {len(unique_urls)} products")
            
            # Group users by URL for efficient processing
            url_to_users = {}
            for item in watchlist_items:
                if item.url not in url_to_users:
                    url_to_users[item.url] = []
                url_to_users[item.url].append(item.username)
            
            # Process each URL
            for url in unique_urls:
                try:
                    await self._refresh_product_price(db, url, url_to_users[url])
                    # Small delay to avoid overwhelming servers
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error refreshing price for {url}: {e}")
            
            logger.info("Daily price refresh completed")
            
        except Exception as e:
            logger.error(f"Error in daily price refresh: {e}")
        finally:
            db.close()
    
    async def _refresh_product_price(self, db: Session, url: str, usernames: list):
        """Refresh price for a single product and notify users if needed"""
        try:
            # Get current product data
            product = db.query(ProductDetails).filter(ProductDetails.url == url).first()
            
            # Store previous best price for comparison
            previous_best_price = product.best_price if product else None
            previous_average_price = product.average_price if product else None
            
            # Scrape fresh data (use empty exclusions for daily refresh)
            scraped_data = await scrape_product_async(url, excluded_retailers=[])
            
            if not scraped_data:
                logger.warning(f"No data scraped for {url}")
                return
            
            # Calculate new prices
            new_best_price = scraped_data["price"]
            new_average_price = scraped_data.get("average_price", new_best_price)
            all_retailers = scraped_data.get("all_retailers", [])
            
            # Calculate discount percentages
            previous_discount_percent = 0
            new_discount_percent = 0
            
            if previous_average_price and previous_best_price:
                previous_discount_percent = ((previous_average_price - previous_best_price) / previous_average_price) * 100
            
            if new_average_price and new_best_price:
                new_discount_percent = ((new_average_price - new_best_price) / new_average_price) * 100
            
            # Update product in database
            product_name = url.split("/")[-1].replace("-", " ").title()
            
            if product:
                product.best_price = new_best_price
                product.average_price = new_average_price
                product.best_retailer = scraped_data.get("retailer_name", "Unknown")
                product.retailers = all_retailers
                product.last_updated = datetime.now(timezone.utc)
            else:
                product = ProductDetails(
                    url=url,
                    product_name=product_name,
                    best_price=new_best_price,
                    average_price=new_average_price,
                    best_retailer=scraped_data.get("retailer_name", "Unknown"),
                    image_url=scraped_data.get("image_url"),
                    retailers=all_retailers,
                    price_history=[],
                    last_updated=datetime.now(timezone.utc)
                )
                db.add(product)
            
            db.commit()
            
            # Check each user for notification eligibility
            for username in usernames:
                await self._check_and_notify_user(
                    db, username, url, product_name,
                    new_best_price, new_average_price, new_discount_percent,
                    previous_discount_percent, scraped_data.get("retailer_name", "Unknown")
                )
            
            logger.info(f"Updated {product_name}: ${new_best_price:.2f} ({new_discount_percent:.1f}% off)")
            
        except Exception as e:
            logger.error(f"Error refreshing product {url}: {e}")
    
    async def _check_and_notify_user(self, db: Session, username: str, url: str, 
                                   product_name: str, best_price: float, average_price: float,
                                   current_discount_percent: float, previous_discount_percent: float,
                                   retailer_name: str):
        """Check if user should be notified and send notification"""
        try:
            # Get user settings
            user = db.query(User).filter(User.username == username).first()
            if not user or not user.pushover_code:
                return
            
            # Check user's price limit (percentage threshold)
            price_limit_percent = user.price_limit or 0
            
            # Conditions for notification:
            # 1. Current discount meets user's percentage threshold
            # 2. Current discount is better than previous discount
            # 3. There's actually a meaningful discount (>1%)
            
            should_notify = (
                current_discount_percent >= price_limit_percent and  # Meets user threshold
                current_discount_percent > previous_discount_percent and  # Better than before
                current_discount_percent > 1  # Meaningful discount
            )
            
            if should_notify:
                # Create notification message
                savings_amount = average_price - best_price
                message = (
                    f"🎉 Better Deal Alert!\n\n"
                    f"{product_name}\n"
                    f"💰 Now: ${best_price:.2f} (was ${average_price:.2f})\n"
                    f"📉 Discount: {current_discount_percent:.1f}% off\n"
                    f"💵 Save: ${savings_amount:.2f}\n"
                    f"🏪 Best at: {retailer_name}\n\n"
                    f"Previous best discount: {previous_discount_percent:.1f}%"
                )
                
                # Send notification
                success = await send_pushover(user.pushover_code, message)
                
                if success:
                    logger.info(f"Notification sent to {username} for {product_name}")
                else:
                    logger.error(f"Failed to send notification to {username}")
            else:
                logger.debug(f"No notification for {username}: discount {current_discount_percent:.1f}% (threshold: {price_limit_percent}%, previous: {previous_discount_percent:.1f}%)")
                
        except Exception as e:
            logger.error(f"Error checking notification for {username}: {e}")

# Global scheduler instance
price_scheduler = PriceRefreshScheduler()