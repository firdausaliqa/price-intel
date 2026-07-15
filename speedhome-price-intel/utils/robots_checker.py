"""
Lightweight robots.txt checker built on urllib's RobotFileParser.

Usage:
    checker = RobotsChecker("https://speedhome.com")
    checker.can_fetch("/rent/mont-kiara")   -> True/False
    checker.crawl_delay()                    -> float seconds or None
"""
from __future__ import annotations
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin
import requests


DEFAULT_USER_AGENT = "SpeedhomePriceIntelBot/1.0 (+educational-technical-test; contact: your-email@example.com)"


class RobotsChecker:
    def __init__(self, base_url: str, user_agent: str = DEFAULT_USER_AGENT):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.robots_url = urljoin(self.base_url + "/", "robots.txt")
        self.parser = RobotFileParser()
        self._raw_text = ""
        self._loaded = False

    def load(self) -> bool:
        """Fetch and parse robots.txt. Returns True if successfully loaded."""
        try:
            resp = requests.get(
                self.robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=10,
            )
            if resp.status_code == 200:
                self._raw_text = resp.text
                self.parser.parse(resp.text.splitlines())
                self._loaded = True
                return True
            else:
                # No robots.txt or inaccessible -> default to conservative behavior
                # (RobotFileParser with no rules loaded allows everything by default,
                # so we track this explicitly instead of relying on that.)
                self._loaded = False
                return False
        except requests.RequestException as e:
            print(f"[RobotsChecker] Failed to fetch {self.robots_url}: {e}")
            self._loaded = False
            return False

    def can_fetch(self, path: str) -> bool:
        """
        Check whether `path` (relative or absolute) is allowed for our user agent.
        If robots.txt could not be loaded, we fail CLOSED (return False) so the
        caller must explicitly override -- we never silently assume 'allowed'.
        """
        if not self._loaded:
            return False
        url = path if path.startswith("http") else urljoin(self.base_url + "/", path.lstrip("/"))
        return self.parser.can_fetch(self.user_agent, url)

    def crawl_delay(self) -> float | None:
        if not self._loaded:
            return None
        delay = self.parser.crawl_delay(self.user_agent)
        return float(delay) if delay is not None else None

    def raw_text(self) -> str:
        return self._raw_text


if __name__ == "__main__":
    checker = RobotsChecker("https://speedhome.com")
    ok = checker.load()
    print(f"robots.txt loaded: {ok}")
    if ok:
        print("--- raw robots.txt ---")
        print(checker.raw_text())
        print("-----------------------")
        for test_path in ["/rent/mont-kiara", "/rent/bangsar", "/api/listings"]:
            print(f"can_fetch({test_path}) = {checker.can_fetch(test_path)}")
        print(f"crawl_delay = {checker.crawl_delay()}")
    else:
        print("Could not load robots.txt -- treat all paths as DISALLOWED until verified manually.")
