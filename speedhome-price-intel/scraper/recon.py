"""
ONE-OFF RECON SCRIPT -- run this locally FIRST, before we write any real
scraping logic.

It answers three questions:
  1. Does robots.txt allow us to fetch /rent/<area> pages?
  2. Does a plain `requests` GET return real listing HTML, or a bot-check /
     empty shell (meaning the data is loaded via JS/XHR)?
  3. If it's JS-rendered, is there an underlying JSON API we can call
     directly instead of paying the cost of a full browser render?

Run:
    python -m scraper.recon
"""
from __future__ import annotations
import time
import json
import requests
from bs4 import BeautifulSoup

from utils.robots_checker import RobotsChecker, DEFAULT_USER_AGENT

BASE_URL = "https://speedhome.com"
TEST_AREA_PATH = "/rent/mont-kiara"

HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def check_robots():
    print("\n=== STEP A: robots.txt ===")
    checker = RobotsChecker(BASE_URL)
    loaded = checker.load()
    print(f"Loaded: {loaded}")
    if loaded:
        print(checker.raw_text()[:2000])
        print(f"\ncan_fetch('{TEST_AREA_PATH}') -> {checker.can_fetch(TEST_AREA_PATH)}")
        print(f"crawl_delay -> {checker.crawl_delay()}")
    return checker


def check_static_fetch():
    print("\n=== STEP B: plain requests GET ===")
    url = BASE_URL + TEST_AREA_PATH
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        print(f"Request failed entirely: {e}")
        return None

    print(f"Status code: {resp.status_code}")
    print(f"Server header: {resp.headers.get('Server')}")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    print(f"Set-Cookie present: {'set-cookie' in [h.lower() for h in resp.headers]}")

    # Cloudflare / bot-protection fingerprints
    body_lower = resp.text.lower()
    bot_markers = ["cf-browser-verification", "just a moment", "checking your browser",
                   "captcha", "cloudflare", "access denied", "please enable javascript"]
    hits = [m for m in bot_markers if m in body_lower]
    if hits:
        print(f"⚠️  Bot-protection markers found in body: {hits}")

    soup = BeautifulSoup(resp.text, "lxml")
    # Heuristic: count elements that look like listing cards
    candidate_selectors = ["[class*=listing]", "[class*=property]", "[class*=card]", "a[href*='/rent/']"]
    for sel in candidate_selectors:
        found = soup.select(sel)
        print(f"selector `{sel}` matched {len(found)} elements")

    # Look for embedded JSON (Next.js / Nuxt apps often dump state into a script tag)
    for script in soup.find_all("script"):
        if script.string and ("listing" in script.string.lower() or "__NEXT_DATA__" in (script.get("id") or "")):
            print(f"Found candidate embedded JSON script tag (id={script.get('id')}), length={len(script.string)}")
            print(script.string[:500])
            print("...")

    with open("recon_raw_page.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    print("\nFull HTML saved to recon_raw_page.html for manual inspection.")
    return resp


def check_likely_api():
    """
    Many listing sites load results via a JSON XHR endpoint. Since we can't
    run a real browser here, this just tries a few common guessed patterns.
    This is exploratory only -- the REAL way to find the API is to open
    Chrome DevTools > Network > XHR on the live site and copy the actual
    request. That's a manual step for you to do locally and report back.
    """
    print("\n=== STEP C: guessed API patterns (exploratory only) ===")
    guesses = [
        "/api/rent/mont-kiara",
        "/api/v1/listings?area=mont-kiara",
        "/api/property/search?area=mont-kiara",
    ]
    for path in guesses:
        url = BASE_URL + path
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            print(f"{path} -> {r.status_code} ({r.headers.get('Content-Type')})")
        except requests.RequestException as e:
            print(f"{path} -> error: {e}")
        time.sleep(1)  # be polite even during recon


if __name__ == "__main__":
    check_robots()
    time.sleep(1)
    check_static_fetch()
    time.sleep(1)
    check_likely_api()
    print("\n=== DONE ===")
    print("Next step: open recon_raw_page.html in a browser and/or open the")
    print("real site in Chrome DevTools (Network tab, filter XHR/Fetch) while")
    print("browsing an area page, and tell me what you see. That determines")
    print("whether Step 2 is a BeautifulSoup scraper, a JSON-API client, or")
    print("a Playwright-based scraper.")
