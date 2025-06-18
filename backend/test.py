import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_images_by_size(product_url, min_width=0, max_width=float('inf')):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(product_url, headers=headers, verify=False)
    soup = BeautifulSoup(response.text, 'html.parser')

    image_tags = soup.find_all('img')
    filtered_images = []

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
        except ValueError:
            continue

        if min_width <= width <= max_width:
            decoded_url = unquote(encoded_url)
            filtered_images.append({
                'url': decoded_url,
                'width': width
            })

    return filtered_images


def get_high_quality_images(product_url):
    return get_images_by_size(product_url, min_width=600)


def get_thumbnail_images(product_url):
    return get_images_by_size(product_url, max_width=200)


# 🔍 Test
if __name__ == "__main__":
    test_url = "https://buywisely.com.au/product/google-pixel-buds-pro-2-hazel-"

    print("🔹 High quality images:")
    high_quality = get_high_quality_images(test_url)
    for img in high_quality:
        print(f"  - {img['url']} ({img['width']}px)")

    print("\n🔸 Thumbnail images:")
    thumbnails = get_thumbnail_images(test_url)
    for img in thumbnails:
        print(f"  - {img['url']} ({img['width']}px)")
