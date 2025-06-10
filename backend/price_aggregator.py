# backend/price_aggregator.py
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from playwright.async_api import async_playwright
from cache import cache
import statistics

class PriceAggregator:
    def __init__(self):
        self.data_dir = "data"
        self.aggregated_data_file = os.path.join(self.data_dir, "aggregated_prices.json")
        
    def load_watchlist(self) -> Dict[str, List[str]]:
        """Load all watchlists"""
        watchlist_file = os.path.join(self.data_dir, "watchlist.json")
        if not os.path.exists(watchlist_file):
            return {}
        with open(watchlist_file, 'r') as f:
            return json.load(f)
    
    def load_aggregated_data(self) -> Dict[str, Dict]:
        """Load existing aggregated data"""
        if not os.path.exists(self.aggregated_data_file):
            return {}
        with open(self.aggregated_data_file, 'r') as f:
            return json.load(f)
    
    def save_aggregated_data(self, data: Dict[str, Dict]):
        """Save aggregated data"""
        with open(self.aggregated_data_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    async def scrape_all_prices(self, url: str) -> Optional[Dict]:
        """Scrape all retailer prices for a product"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            api_response = {}
            
            async def handle_response(response):
                if "/api/product/" in response.url and response.status == 200:
                    if "application/json" in response.headers.get("content-type", ""):
                        try:
                            api_response["data"] = await response.json()
                        except Exception:
                            pass
            
            page.on("response", handle_response)
            
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
                await page.wait_for_timeout(5000)  # Wait for dynamic content
            except Exception as e:
                print(f"Error loading page {url}: {e}")
                await browser.close()
                return None
            
            await browser.close()
            
            # Process the API response
            data = api_response.get("data", {})
            if not data:
                return None
            
            # Extract all prices from the past month
            one_month_ago = datetime.now(timezone.utc) - timedelta(days=30)
            all_prices = []
            retailer_prices = {}
            
            for retailer_url, entries in data.items():
                retailer_name = self._extract_retailer_name(retailer_url)
                prices_for_retailer = []
                
                for entry in entries:
                    try:
                        # Parse timestamp
                        ts = datetime.strptime(entry["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                        
                        # Only include prices from the past month
                        if ts >= one_month_ago:
                            price = float(entry["base_price"])
                            all_prices.append(price)
                            prices_for_retailer.append(price)
                    except Exception as e:
                        print(f"Error processing entry: {e}")
                        continue
                
                # Store average price per retailer
                if prices_for_retailer:
                    retailer_prices[retailer_name] = {
                        "min": min(prices_for_retailer),
                        "max": max(prices_for_retailer),
                        "avg": statistics.mean(prices_for_retailer),
                        "count": len(prices_for_retailer)
                    }
            
            if not all_prices:
                return None
            
            # Calculate overall statistics
            return {
                "url": url,
                "product_name": url.split("/")[-1].replace("-", " ").title(),
                "overall": {
                    "min_price": min(all_prices),
                    "max_price": max(all_prices),
                    "avg_price": round(statistics.mean(all_prices), 2),
                    "median_price": round(statistics.median(all_prices), 2),
                    "std_dev": round(statistics.stdev(all_prices), 2) if len(all_prices) > 1 else 0,
                    "total_data_points": len(all_prices)
                },
                "retailers": retailer_prices,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "period": {
                    "start": one_month_ago.isoformat(),
                    "end": datetime.now(timezone.utc).isoformat()
                }
            }
    
    def _extract_retailer_name(self, url: str) -> str:
        """Extract retailer name from URL"""
        # Map common URLs to retailer names
        retailer_map = {
            "chemistwarehouse.com.au": "Chemist Warehouse",
            "priceline.com.au": "Priceline",
            "amazon.com.au": "Amazon AU",
            "ebay.com.au": "eBay",
            "woolworths.com.au": "Woolworths",
            "coles.com.au": "Coles",
            "bigw.com.au": "Big W",
            "kmart.com.au": "Kmart",
            "target.com.au": "Target"
        }
        
        for domain, name in retailer_map.items():
            if domain in url:
                return name
        
        # Fallback: extract domain name
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            return domain.replace("www.", "").split(".")[0].title()
        except:
            return url
    
    async def aggregate_all_products(self):
        """Aggregate prices for all products in all watchlists"""
        print("Starting price aggregation...")
        
        # Get all unique URLs from all watchlists
        watchlists = self.load_watchlist()
        all_urls = set()
        
        for username, urls in watchlists.items():
            all_urls.update(urls)
        
        print(f"Found {len(all_urls)} unique products to process")
        
        # Load existing data
        aggregated_data = self.load_aggregated_data()
        
        # Process each URL
        for i, url in enumerate(all_urls, 1):
            print(f"\nProcessing {i}/{len(all_urls)}: {url}")
            
            try:
                result = await self.scrape_all_prices(url)
                
                if result:
                    # Store in aggregated data
                    aggregated_data[url] = result
                    
                    # Also update cache for immediate use
                    cache_key = f"aggregated-price:{url}"
                    cache.set(cache_key, result, ttl=30*24*60*60)  # 30 days
                    
                    print(f"✓ Successfully aggregated prices: avg=${result['overall']['avg_price']}")
                else:
                    print(f"✗ No data found")
                    
            except Exception as e:
                print(f"✗ Error: {e}")
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(2)
        
        # Save all aggregated data
        self.save_aggregated_data(aggregated_data)
        print(f"\nAggregation complete! Processed {len(all_urls)} products")
        
        # Print summary
        self.print_summary(aggregated_data)
    
    def print_summary(self, data: Dict[str, Dict]):
        """Print summary statistics"""
        print("\n" + "="*50)
        print("AGGREGATION SUMMARY")
        print("="*50)
        
        total_products = len(data)
        all_avg_prices = [item["overall"]["avg_price"] for item in data.values()]
        
        if all_avg_prices:
            print(f"Total products tracked: {total_products}")
            print(f"Overall average price: ${statistics.mean(all_avg_prices):.2f}")
            print(f"Lowest average: ${min(all_avg_prices):.2f}")
            print(f"Highest average: ${max(all_avg_prices):.2f}")
            
            # Find biggest price variations
            variations = [(url, data["overall"]["std_dev"]) 
                         for url, data in data.items() 
                         if data["overall"]["std_dev"] > 0]
            variations.sort(key=lambda x: x[1], reverse=True)
            
            if variations:
                print("\nTop 5 products with highest price variation:")
                for url, std_dev in variations[:5]:
                    product_name = data[url]["product_name"]
                    print(f"  - {product_name}: ±${std_dev:.2f}")

def main():
    """Run the aggregation"""
    aggregator = PriceAggregator()
    asyncio.run(aggregator.aggregate_all_products())

if __name__ == "__main__":
    main()