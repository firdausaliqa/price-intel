"""
End-to-end smoke test for Step 2: scrape -> parse -> DataFrame.

Run:
    python -m scraper.test_scrape

By default this only fetches 1 page (max 40 listings) to be polite while
we're still validating. Remove max_pages=1 once you've confirmed it works
and want the full dataset.
"""
import pandas as pd

from scraper.speedhome_scraper import SpeedhomeScraper, RobotsDisallowedError
from scraper.parser import normalize_listings

AREA_SLUG = "mont-kiara"

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

scraper = SpeedhomeScraper(respect_robots=True)

try:
    result = scraper.fetch_area(AREA_SLUG, max_pages=1)
except RobotsDisallowedError as e:
    print(f"BLOCKED BY ROBOTS.TXT POLICY: {e}")
    raise SystemExit(1)

print(f"success={result.success}")
print(f"total_elements={result.total_elements} total_pages={result.total_pages}")
print(f"pages_fetched={result.pages_fetched} listings_collected={len(result.listings)}")
if result.error:
    print(f"error (may be partial success): {result.error}")

if not result.listings:
    print("\nNo listings collected -- likely blocked. This is expected to")
    print("happen sometimes given Cloudflare's intermittent challenges. This")
    print("confirms the cached-data fallback (Step 4) is essential.")
    raise SystemExit(0)

records = normalize_listings(result.listings, area_query=AREA_SLUG)
df = pd.DataFrame(records)

print(f"\n=== DataFrame shape: {df.shape} ===")
print(df.head(10))

print("\n=== Unit Type value counts ===")
print(df["Unit Type"].value_counts())

print("\n=== Furnishing Status value counts ===")
print(df["Furnishing Status"].value_counts())

# Save for inspection / to seed a cached snapshot later
df.to_csv("test_scrape_output.csv", index=False)
print("\nSaved to test_scrape_output.csv")
