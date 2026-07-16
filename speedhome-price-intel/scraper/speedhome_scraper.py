"""
SpeedhomeScraper: fetches property listings from SPEEDHOME's confirmed
internal JSON API (found via manual DevTools inspection, not guessed).

Endpoint:  POST https://speedhome.com/api/properties/search
Body:      {"searchParams": {"loc": "<area-slug>"}, "pathname": "/rent/[loc]",
            "page": <int>, "itemsPerPage": 40, "userToken": null}

This deliberately does NOT parse HTML -- the site's own frontend calls this
same endpoint, so we're reusing their public API contract rather than
scraping rendered markup. It's lighter on their servers and far more
reliable than DOM scraping.

Politeness / ethics:
  - robots.txt is checked once per session before any requests are made
  - a randomized delay is inserted between every page request
  - requests are capped with retries + exponential backoff; we give up
    cleanly (raising ScraperBlockedError) rather than hammering the server
  - a descriptive User-Agent identifies this as a bot with a contact point
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

import requests

from scraper.config import (
    API_SEARCH_URL,
    API_ITEMS_PER_PAGE,
    BASE_URL,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    MAX_RETRIES,
)
from utils.robots_checker import RobotsChecker

CHALLENGE_MARKERS = ["just a moment", "cf-chl", "challenge-platform", "__cf_chl"]


class ScraperBlockedError(Exception):
    """Raised when SPEEDHOME consistently blocks/challenges our requests."""


class RobotsDisallowedError(Exception):
    """Raised when robots.txt disallows the path we're trying to fetch."""


@dataclass
class ScrapeResult:
    area_slug: str
    listings: list[dict] = field(default_factory=list)
    total_elements: int = 0
    total_pages: int = 0
    pages_fetched: int = 0
    success: bool = False
    error: str | None = None


class SpeedhomeScraper:
    def __init__(self, respect_robots: bool = True, use_browser_impersonation: bool = False):
        """
        use_browser_impersonation=True attempts to use curl_cffi (Chrome TLS
        fingerprint impersonation), which sometimes gets past Cloudflare
        where plain `requests` is blocked.

        WARNING: curl_cffi bundles a compiled native extension and has known
        crash issues (hard process crashes, NOT catchable Python exceptions)
        on some platform/OpenSSL combinations, particularly on macOS. It is
        therefore OFF by default. Only enable it if you've verified it
        works stably on your machine in isolation first (see README /
        scraper/check_curl_cffi.py).
        """
        self._use_impersonation = False
        self.session = requests.Session()

        if use_browser_impersonation:
            try:
                from curl_cffi import requests as curl_requests
                self.session = curl_requests.Session(impersonate="chrome")
                self._use_impersonation = True
            except ImportError:
                pass  # fall back silently to plain requests.Session above

        self.session.headers.update(REQUEST_HEADERS)
        self._robots = RobotsChecker(BASE_URL)
        self._robots_loaded = False
        self.respect_robots = respect_robots

    def _ensure_robots_loaded(self):
        if not self.respect_robots or self._robots_loaded:
            return
        self._robots.load()
        self._robots_loaded = True

    def _check_allowed(self, area_slug: str):
        self._ensure_robots_loaded()
        if not self.respect_robots:
            return
        path = f"/rent/{area_slug}"
        if not self._robots._loaded:
            # We couldn't even fetch robots.txt (network error, DNS issue,
            # etc.) -- this is NOT the same as robots.txt actively
            # disallowing the path. We still refuse to scrape (conservative
            # default), but the error message must say so accurately rather
            # than implying a deliberate policy block.
            raise RobotsDisallowedError(
                f"Could not verify robots.txt for {BASE_URL} (network error "
                f"or site unreachable) -- refusing to scrape as a precaution. "
                f"This is not necessarily a real policy block."
            )
        if not self._robots.can_fetch(path):
            raise RobotsDisallowedError(
                f"robots.txt disallows fetching {path} -- refusing to scrape."
            )

    @staticmethod
    def _is_challenge_page(text: str) -> bool:
        lower = text.lower()
        return any(marker in lower for marker in CHALLENGE_MARKERS)

    def _politeness_delay(self):
        time.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))

    def _fetch_page(self, area_slug: str, page: int) -> dict:
        """Fetch a single page of results, with retry + backoff on failure."""
        payload = {
            "searchParams": {"loc": area_slug},
            "pathname": "/rent/[loc]",
            "page": page,
            "itemsPerPage": API_ITEMS_PER_PAGE,
            "userToken": None,
        }
        headers = {
            **REQUEST_HEADERS,
            "Content-Type": "application/json",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/rent/{area_slug}",
        }

        last_error = None
        for attempt in range(1, MAX_RETRIES + 2):  # e.g. MAX_RETRIES=2 -> 3 attempts
            try:
                resp = self.session.post(
                    API_SEARCH_URL,
                    json=payload,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
            except Exception as e:
                # Broad on purpose: curl_cffi and requests raise different
                # exception hierarchies, and we treat any transport failure
                # the same way -- log, back off, retry.
                last_error = f"{type(e).__name__}: {e}"
                time.sleep(2 * attempt)
                continue

            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    last_error = "200 OK but response was not valid JSON"
            elif self._is_challenge_page(resp.text):
                last_error = f"Cloudflare challenge page (status {resp.status_code})"
            else:
                last_error = f"Unexpected status {resp.status_code}"

            # backoff before retry
            time.sleep(2 * attempt)

        raise ScraperBlockedError(
            f"Failed to fetch page {page} for '{area_slug}' after "
            f"{MAX_RETRIES + 1} attempts. Last error: {last_error}"
        )

    def fetch_area(self, area_slug: str, max_pages: int | None = None) -> ScrapeResult:
        """
        Fetch all (or up to max_pages) pages of listings for an area slug.
        Returns a ScrapeResult -- never raises on partial success; only
        raises RobotsDisallowedError (policy) since that must hard-stop.
        ScraperBlockedError is caught and returned inside the result so the
        caller (Streamlit app) can gracefully fall back to cached data.
        """
        result = ScrapeResult(area_slug=area_slug)

        self._check_allowed(area_slug)  # raises RobotsDisallowedError if not allowed

        try:
            first_page = self._fetch_page(area_slug, page=0)
        except ScraperBlockedError as e:
            result.success = False
            result.error = str(e)
            return result

        result.total_elements = first_page.get("totalElements", 0)
        result.total_pages = first_page.get("totalPages", 1)
        result.listings.extend(first_page.get("content", []))
        result.pages_fetched = 1

        pages_to_fetch = result.total_pages
        if max_pages is not None:
            pages_to_fetch = min(pages_to_fetch, max_pages)

        for page in range(1, pages_to_fetch):
            self._politeness_delay()
            try:
                page_data = self._fetch_page(area_slug, page=page)
            except ScraperBlockedError as e:
                # Partial success: keep what we have, note the error, stop.
                result.error = f"Stopped early at page {page}: {e}"
                break
            result.listings.extend(page_data.get("content", []))
            result.pages_fetched += 1

        result.success = len(result.listings) > 0
        return result

    def close(self):
        """
        Explicitly release the session's underlying connection/native
        resources immediately, in the same thread that created them.
        Important when use_browser_impersonation=True: curl_cffi's native
        libcurl handle is not safe to garbage-collect on a different thread
        than the one that created it (which can happen naturally across
        Streamlit reruns) -- calling this deterministically avoids relying
        on Python's GC timing for that cleanup.
        """
        try:
            self.session.close()
        except Exception:
            pass  # best-effort; nothing more we can safely do here


if __name__ == "__main__":
    # Manual smoke test -- run with: python -m scraper.speedhome_scraper
    scraper = SpeedhomeScraper()
    res = scraper.fetch_area("mont-kiara", max_pages=1)  # just 1 page to be polite
    print(f"success={res.success} total_elements={res.total_elements} "
          f"total_pages={res.total_pages} fetched={len(res.listings)}")
    if res.error:
        print(f"error: {res.error}")
    if res.listings:
        print("\nFirst listing keys:", list(res.listings[0].keys())[:15], "...")
