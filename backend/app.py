from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, asyncio

from scraper import scrape_product
from pushover import send_pushover

app = Flask(__name__)
CORS(app)

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

@app.route("/api/product-info", methods=["POST"])
def product_info():
    from scraper import scrape_product  # adjust import if needed
    urls = request.json.get("urls", [])
    
    async def gather_data():
        results = []
        for url in urls:
            best = await scrape_product(url)
            if best:
                results.append({
                    "url": url,
                    "retailer": best["retailer"],
                    "best_price": best["price"],
                    "average_price": best.get("average_price", best["price"]),  # optional
                    "product_name": url.split("/")[-1].replace("-", " ").capitalize()
                })
        return results

    enriched = asyncio.run(gather_data())
    return jsonify(enriched)

@app.route("/api/users/<username>", methods=["GET", "PUT"])
def user_settings(username):
    users = load_json(USERS_FILE)
    if request.method == "GET":
        return jsonify(users.get(username, {}))
    users[username] = request.json
    save_json(users, USERS_FILE)
    return jsonify({"status": "updated"})

@app.route("/api/watchlist/<username>", methods=["GET", "POST", "DELETE"])
def manage_watchlist(username):
    watchlist = load_json(WATCHLIST_FILE)
    if request.method == "GET":
        return jsonify(watchlist.get(username, []))
    if request.method == "POST":
        url = request.json["url"]
        watchlist.setdefault(username, []).append(url)
    elif request.method == "DELETE":
        url = request.json["url"]
        watchlist.setdefault(username, []).remove(url)
    save_json(watchlist, WATCHLIST_FILE)
    return jsonify({"status": "updated"})

@app.route("/api/notify/test/<username>", methods=["POST"])
def send_test(username):
    users = load_json(USERS_FILE)
    watchlist = load_json(WATCHLIST_FILE)

    user = users.get(username)
    urls = watchlist.get(username, [])
    if not user or not urls:
        return jsonify({"error": "User or watchlist not found"}), 404

    async def run():
        best = await scrape_product(urls[0])
        if not best:
            return {"error": "No price found"}

        msg = f"🧪 Test for {username}\n${best['price']} at {best['retailer']}\n{urls[0]}"
        sent = await send_pushover(user["pushover_code"], msg)
        return {"sent": sent}

    result = asyncio.run(run())
    return jsonify(result)

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True)
