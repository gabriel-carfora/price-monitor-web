from typing import Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _get_images_by_size_from_slug(slug: str, min_width=0, max_width=float('inf')) -> Optional[str]:
    url = f"https://buywisely.com.au/product/{slug}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, verify=False)
    soup = BeautifulSoup(response.text, 'html.parser')

    image_tags = soup.find_all('img')
    results = []

    for img in image_tags:
        src = img.get('src')
        if not src or '/_next/image' not in src or 'url=' not in src:
            continue

        parsed = urlparse(src)
        qs = parse_qs(parsed.query)
        encoded_url = qs.get('url', [None])[0]
        width_str = qs.get('w', [None])[0]

        if not encoded_url or not width_str:
            continue

        try:
            width = int(width_str)
            if min_width <= width <= max_width:
                decoded_url = unquote(encoded_url)
                results.append((decoded_url, width))
        except ValueError:
            continue

    # Sort by width descending and return the first match
    results.sort(key=lambda x: x[1], reverse=True)
    return results[0][0] if results else None


def get_high_quality_image(slug: str) -> Optional[str]:
    return _get_images_by_size_from_slug(slug, min_width=600)


def get_thumbnail_image(slug: str) -> Optional[str]:
    return _get_images_by_size_from_slug(slug, max_width=200)
