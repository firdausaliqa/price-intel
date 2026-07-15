"""
Follow-up recon: extract and pretty-print the __NEXT_DATA__ JSON structure
so we can see exact field names before writing the real parser.

Run:
    python -m scraper.recon_json
"""
import json
import time
import requests
from bs4 import BeautifulSoup
from scraper.config import REQUEST_HEADERS, BASE_URL

url = BASE_URL + "/rent/mont-kiara"

CHALLENGE_MARKERS = ["just a moment", "cf-chl", "challenge-platform", "__cf_chl"]


def is_challenge_page(html: str) -> bool:
    lower = html.lower()
    return any(marker in lower for marker in CHALLENGE_MARKERS)


def fetch_with_retry(url: str, max_attempts: int = 5, base_delay: float = 3.0):
    for attempt in range(1, max_attempts + 1):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        if resp.status_code == 200 and not is_challenge_page(resp.text):
            print(f"[attempt {attempt}] SUCCESS (200, real content)")
            return resp
        reason = "challenge page" if is_challenge_page(resp.text) else f"status {resp.status_code}"
        print(f"[attempt {attempt}] blocked ({reason}), retrying...")
        time.sleep(base_delay * attempt)  # increasing backoff
    return None


resp = fetch_with_retry(url)
if resp is None:
    print("\nAll attempts blocked by Cloudflare challenge. This confirms live")
    print("scraping cannot be guaranteed reliable -- the app MUST rely on the")
    print("cached/local data fallback. Try again in a few minutes, or run this")
    print("from a different network, to still capture a JSON sample for building")
    print("the parser against.")
    raise SystemExit(1)

soup = BeautifulSoup(resp.text, "lxml")
script = soup.find("script", id="__NEXT_DATA__")
data = json.loads(script.string)

property_list = data["props"]["pageProps"]["propertyList"]

# Top-level keys of propertyList (look for totalPages / totalElements / page size etc.)
print("=== propertyList top-level keys ===")
print(list(property_list.keys()))

print("\n=== pagination-ish fields (if present) ===")
for k in ["totalPages", "totalElements", "totalCount", "total", "page", "size", "number", "last", "first"]:
    if k in property_list:
        print(f"{k}: {property_list[k]}")

content = property_list.get("content", [])
print(f"\n=== number of listings on this page: {len(content)} ===")

print("\n=== FULL first listing record ===")
print(json.dumps(content[0], indent=2) if content else "No listings found")

# Also check pageProps itself for other top-level keys we might be missing
# (e.g. separate daily/monthly/yearly lists, filter metadata, area info)
print("\n=== pageProps top-level keys ===")
print(list(data["props"]["pageProps"].keys()))

with open("recon_next_data.json", "w", encoding="utf-8") as f:
    json.dump(data["props"]["pageProps"], f, indent=2)
print("\nFull pageProps JSON saved to recon_next_data.json for deeper inspection.")
