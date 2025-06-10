from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

async def scrape_product(url):
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
        await page.goto(url)
        await page.wait_for_timeout(5000)
        await browser.close()

        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        best = None
        data = api_response.get("data", {})

        for retailer_url, entries in data.items():
            for entry in entries:
                try:
                    ts = datetime.strptime(entry["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                    if ts >= one_week_ago:
                        price = entry["base_price"]
                        if best is None or price < best["price"]:
                            best = {
                                "price": price,
                                "retailer": retailer_url,
                                "timestamp": entry["created_at"]
                            }
                except Exception:
                    continue
        return best
