"""Global configuration for BestBuyTool."""

import os

# --- HTTP Settings ---
REQUEST_TIMEOUT = 15  # seconds
MAX_RETRIES = 2
RETRY_DELAY = 1.0  # seconds between retries
REQUEST_DELAY = 0.5  # seconds between requests to same supplier (rate limiting)

# --- User Agent ---
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# --- Search Settings ---
MAX_RESULTS_PER_SUPPLIER = 20  # cap results per supplier to keep output sane
MAX_WORKERS = 5  # parallel threads for concurrent supplier searches

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUPPLIERS_FILE = os.path.join(BASE_DIR, "suppliers.json")
