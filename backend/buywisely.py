import subprocess
import json
import statistics
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

class BuyWiselyDirectAPI:
    """
    Direct API client for BuyWisely using curl under the hood.
    Only the Referer header is sent.
    """
    def __init__(self):
        pass

    def extract_product_slug(self, product_url):
        """Extract the product slug from the BuyWisely URL."""
        try:
            return product_url.split('/product/')[-1].rstrip('/')
        except Exception:
            return None

    def get_raw_data(self, product_url):
        """
        Shell out to curl to fetch the JSON from the BuyWisely API.
        Returns parsed JSON or None on failure.
        """
        print("🛰️ ENTERED get_raw_data")
        
        slug = self.extract_product_slug(product_url)
        if not slug:
            print("❌ Could not extract product slug")
            return None

        api_url = f"https://buywisely.com.au/api/product/{slug}"
        cmd = [
            "curl", "-s", "-L", "--tlsv1.2", "-k",
            "-H", f"Referer: {product_url}",
            api_url
        ]

        print(f"🔧 Running command: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ curl error: {result.stderr.strip()}")
            return None

        if not result.stdout.strip():
            print("❌ curl returned empty stdout")
            return None

        print("📄 curl response (first 500 chars):")
        print(result.stdout[:500])

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            print(f"↩️ Raw output:\n{result.stdout[:500]}")
            return None

    def parse_price_data(self, data):
        """
        Parse price data from the BuyWisely JSON response.
        Supports both dict-of-lists and list-of-objects formats.
        """
        parsed = {}
        if isinstance(data, dict):
            for url, entries in data.items():
                if isinstance(entries, list):
                    parsed[url] = entries
        elif isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                url = item.get('url') or item.get('retailer') or 'unknown'
                prices = item.get('prices') or item.get('price_history') or []
                if prices:
                    parsed[url] = prices
                elif 'price' in item or 'base_price' in item:
                    parsed[url] = [{
                        'base_price': item.get('price') or item.get('base_price', 0),
                        'created_at': item.get('created_at') or item.get('timestamp')
                    }]
        else:
            print(f"❌ Unexpected data format: {type(data)}")
        return parsed

    def extract_retailer_name(self, url):
        """Map known domains to retailer names, otherwise derive from URL."""
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
        try:
            hostname = urlparse(url).netloc.replace("www.", "")
            return hostname.split(".")[0].title()
        except Exception:
            return url

    def analyze_product(self, product_url, excluded_retailers=None, days_back=30):
        """
        Fetch, parse and analyze price history for a product.
        Returns a summary dict or None on failure.
        """
        print("🔍 ENTERED analyze_product")

        excluded_retailers = excluded_retailers or []
        print(f"🎯 Analyzing: {product_url}")
        raw = self.get_raw_data(product_url)
        if not raw:
            return None

        data = self.parse_price_data(raw)
        if not data:
            print("❌ No price data found")
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        all_prices = []
        retailers_summary = []

        for url, entries in data.items():
            print(f"🔍 Checking {url}")
            print(f"⛔ Exclusion list: {excluded_retailers}")
            print(f"🔍 URL domain: {urlparse(url).netloc.lower()}")

            if any(ex in url.lower() for ex in excluded_retailers):
                continue

            prices = []
            recent = []
            for e in entries:
                ts_str = e.get('created_at') or e.get('timestamp')
                if not ts_str:
                    continue
                try:
                    if '.' in ts_str:
                        ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                    else:
                        ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
                    ts = ts.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if ts < cutoff:
                    continue
                price = e.get('base_price') or e.get('price') or 0
                if price <= 0:
                    continue
                prices.append(price)
                all_prices.append(price)
                if ts >= datetime.now(timezone.utc) - timedelta(days=7):
                    recent.append(price)

            if recent:
                current = min(recent)
                avg = statistics.mean(prices) if prices else current
                retailers_summary.append({
                    "name": self.extract_retailer_name(url),
                    "url": url,
                    "price": current,
                    "avg_price": avg,
                    "price_count": len(prices)
                })

        if not all_prices or not retailers_summary:
            print("❌ No valid recent prices")
            return None

        retailers_summary.sort(key=lambda x: x["price"])
        best = retailers_summary[0]
        overall_avg = statistics.mean(all_prices)
        product_name = product_url.rstrip('/').split('/')[-1].replace('-', ' ').title()

        result = {
            "product_name": product_name,
            "best_price": best["price"],
            "best_retailer": best["name"],
            "best_url": best["url"],
            "average_price": round(overall_avg, 2),
            "savings": round(overall_avg - best["price"], 2),
            "savings_pct": round((overall_avg - best["price"]) / overall_avg * 100, 1),
            "retailers_analyzed": len(retailers_summary),
            "total_prices": len(all_prices),
            "all_retailers": retailers_summary,
            "method": "curl_direct"
        }

        print(f"🎉 Best price: ${result['best_price']:.2f} at {result['best_retailer']}")
        print(f"   Avg price: ${result['average_price']:.2f}")
        print(f"   Savings : ${result['savings']:.2f} ({result['savings_pct']}%)")
        return result

def get_product_data_direct(url, excluded_retailers=None, days_back=30):
    """Convenience wrapper."""
    client = BuyWiselyDirectAPI()
    return client.analyze_product(url, excluded_retailers, days_back)

def test_direct_api():
    """Test the direct API approach."""
    urls = [
        "https://buywisely.com.au/product/tom-ford-ombre-leather-eau-de-parfum-spray-100ml",
        "https://buywisely.com.au/product/viva-paper-towel-white-pack-of-12-12-rolls-60-sheets-per-roll-"
    ]
    for u in urls:
        print("\n" + "="*80)
        res = get_product_data_direct(u, excluded_retailers=["ebay"])
        if res:
            print(f"✅ SUCCESS: ${res['best_price']:.2f} from {res['best_retailer']}")
        else:
            print("❌ FAILED")
        print("="*80)

if __name__ == "__main__":
    test_direct_api()
