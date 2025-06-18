# backend/search_scraper.py
import asyncio
from playwright.async_api import async_playwright
from urllib.parse import urljoin, quote, unquote
import traceback
from typing import List, Dict, Optional

class BuyWiselySearchScraper:
    """
    Scraper for BuyWisely search results to extract product links
    """
    
    def __init__(self):
        self.base_url = "https://buywisely.com.au"
        
    async def search_products(self, query: str, max_results: int = 50) -> List[Dict[str, str]]:
        """
        Search for products on BuyWisely and extract product links
        
        Args:
            query: Search term
            max_results: Maximum number of results to return
            
        Returns:
            List of dictionaries containing product info: {'url': str, 'title': str, 'offers_count': str}
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                context = await browser.new_context(user_agent=user_agent, viewport={"width": 800, "height": 600})
                page = await context.new_page()

                block_types = {"image", "font", "stylesheet", "media", "other"}

                async def block_requests(route, request):
                    if request.resource_type in block_types:
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/*", block_requests)
                # Construct search URL
                encoded_query = quote(query)
                search_url = f"{self.base_url}/product/search?q={encoded_query}"
                
                print(f"🔍 Searching for: {query}")
                print(f"📍 URL: {search_url}")
                
                # Navigate to search page
                await page.goto(search_url, wait_until="networkidle", timeout=20000)
                await page.wait_for_selector('a[href^="/product/"]', timeout=5000)
                
                # Look for the "Compare X offers" buttons that contain product links
                product_links = []
                
                # Target the specific button elements with the product links
                buttons = await page.query_selector_all('a[href^="/product/"]')
                
                print(f"🔎 Found {len(buttons)} potential product links")
                
                for button in buttons[:max_results]:
                    if len(product_links) >= max_results:
                        break
                    try:
                        # Get the href attribute
                        href = await button.get_attribute('href')
                        if not href or not href.startswith('/product/'):
                            continue
                            
                        # Get the full URL
                        full_url = urljoin(self.base_url, href)
                        
                        # Try to extract the "Compare X offers" text
                        offers_text = ""
                        text_element = await button.query_selector('p')
                        if text_element:
                            offers_text = await text_element.inner_text()
                        
                        # Extract product title from URL (as fallback)
                        product_slug = href.replace('/product/', '')
                        product_title = product_slug.replace('-', ' ').title()
                        
                        # Try to find a better product title from nearby elements
                        # Look for product title in the parent container
                        parent = await button.evaluate_handle('element => element.closest("[data-testid], .MuiCard-root, .MuiPaper-root")')
                        if parent:
                            # Look for heading elements
                            heading = await parent.query_selector('h1, h2, h3, h4, h5, h6, [class*="title"], [class*="name"]')
                            if heading:
                                title_text = await heading.inner_text()
                                if title_text.strip():
                                    product_title = title_text.strip()
                        
                        product_info = {
                            'url': full_url,
                            'title': product_title,
                            'offers_count': offers_text,
                            'slug': product_slug
                        }
                        
                        product_links.append(product_info)
                        print(f"✅ Found: {product_title} - {offers_text}")
                        
                    except Exception as e:
                        print(f"❌ Error processing button: {e}")
                        continue
                
                await browser.close()
                
                # Remove duplicates based on URL
                seen_urls = set()
                unique_products = []
                for product in product_links:
                    if product['url'] not in seen_urls:
                        seen_urls.add(product['url'])
                        unique_products.append(product)
                
                print(f"🎯 Extracted {len(unique_products)} unique products")
                return unique_products
                
        except Exception as e:
            print(f"💥 Search scraping error: {e}")
            traceback.print_exc()
            return []
    
    async def get_product_suggestions(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Get product suggestions for a search query
        
        Args:
            query: Search term
            limit: Maximum number of suggestions
            
        Returns:
            List of product suggestions
        """
        products = await self.search_products(query, max_results=limit)
        
        # Format for easy consumption
        suggestions = []
        for product in products:
            suggestions.append({
                'title': product['title'],
                'url': product['url'],
                'offers': product['offers_count']
            })
            
        return suggestions

def search_products_sync(query: str, max_results: int = 50) -> List[Dict[str, str]]:
    """
    Synchronous wrapper for search_products
    """
    scraper = BuyWiselySearchScraper()
    return asyncio.run(scraper.search_products(query, max_results))

def get_suggestions_sync(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Synchronous wrapper for get_product_suggestions
    """
    scraper = BuyWiselySearchScraper()
    return asyncio.run(scraper.get_product_suggestions(query, limit))
