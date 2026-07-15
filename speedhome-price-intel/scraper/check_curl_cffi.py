"""
Standalone isolation test for curl_cffi -- run this directly (NOT through
Streamlit) to check whether curl_cffi behaves stably on your machine.

Run:
    python -m scraper.check_curl_cffi

If this crashes/segfaults, curl_cffi is not stable in your environment at
all, and browser impersonation should stay disabled everywhere (including
in test_scrape.py). If it succeeds here but crashes inside the Streamlit
app, that confirms the issue is specifically curl_cffi's Session
create/destroy churn across Streamlit's rerun/threading model -- in which
case it's safe to use in one-off scripts (like generating cached
snapshots) but should stay OFF inside the live app, which is the default
we ship with.
"""
try:
    from curl_cffi import requests as curl_requests
except ImportError:
    print("curl_cffi is not installed. Run: pip install curl_cffi")
    raise SystemExit(1)

print("Creating a single curl_cffi Session with impersonate='chrome'...")
session = curl_requests.Session(impersonate="chrome")
print("Session created OK.")

print("Making one test request to speedhome.com's API...")
try:
    resp = session.post(
        "https://speedhome.com/api/properties/search",
        json={
            "searchParams": {"loc": "mont-kiara"},
            "pathname": "/rent/[loc]",
            "page": 0,
            "itemsPerPage": 5,
            "userToken": None,
        },
        headers={
            "Content-Type": "application/json",
            "Origin": "https://speedhome.com",
            "Referer": "https://speedhome.com/rent/mont-kiara",
        },
        timeout=15,
    )
    print(f"Status: {resp.status_code}")
    print(f"Response length: {len(resp.text)} chars")
    if resp.status_code == 200:
        print("SUCCESS -- curl_cffi works on this machine for a single request.")
    else:
        print("Got a non-200 response -- likely blocked, but no crash. That's fine.")
except Exception as e:
    print(f"Request raised a normal Python exception (not a crash): {e}")

print("\nDone. If you saw this message, the process did NOT crash.")
