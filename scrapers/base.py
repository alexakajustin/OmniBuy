"""Base scraper — abstract contract for all supplier scrapers."""

import re
import time
import logging
from abc import ABC, abstractmethod
from urllib.parse import urljoin

from curl_cffi import requests
from bs4 import BeautifulSoup

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, REQUEST_DELAY
from models.product import Product

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for all supplier scrapers.

    Subclasses only need to implement:
        - supplier_name (property)
        - base_url (property)
        - currency (property)
        - search(query) -> list[Product]
    
    Common logic (HTTP, price parsing, retries) lives here — DRY.
    """

    def __init__(self):
        self._session = requests.Session(impersonate="chrome110")
        self._session.headers.update(DEFAULT_HEADERS)
        self._last_request_time = 0.0

    # --- Abstract interface (what each scraper must implement) ---

    @property
    @abstractmethod
    def supplier_name(self) -> str:
        """Human-readable supplier name."""
        ...

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Supplier website base URL."""
        ...

    @property
    def currency(self) -> str:
        """Default currency for this supplier. Override for non-RON suppliers."""
        return "RON"

    @abstractmethod
    def search(self, query: str) -> list[Product]:
        """Search for products matching query. Returns list of Product."""
        ...

    def get_search_url(self, query: str) -> str:
        """Build the search URL for this supplier, sorted by price ascending where possible."""
        raise NotImplementedError("Each scraper must implement get_search_url")

    def _fallback_link(self, query: str) -> list[Product]:
        """Return a single Product representing a search link to the supplier website."""
        return [
            Product(
                name=f"[LINK] Caută '{query}' pe {self.supplier_name}",
                price=0.0,
                currency=self.currency,
                url=self.get_search_url(query),
                supplier=self.supplier_name,
                in_stock=True,
            )
        ]

    # --- Shared utilities (used by all scrapers) ---

    def _fetch(self, url: str) -> str | None:
        """GET request with retry logic and rate limiting.

        Returns HTML string or None on failure.
        """
        self._rate_limit()

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.warning(
                    "[%s] Request failed (attempt %d/%d): %s — %s",
                    self.supplier_name, attempt, MAX_RETRIES, url, e,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        logger.error("[%s] All retries exhausted for %s", self.supplier_name, url)
        return None

    def _parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML string into BeautifulSoup object."""
        return BeautifulSoup(html, "lxml")

    def _parse_price(self, raw: str) -> float | None:
        """Extract numeric price from messy strings.

        Handles formats like:
            '12,50 lei'  '€15.99'  '1.234,56 RON'  '15 990 Ft'
        Returns None if parsing fails.
        """
        if not raw:
            return None

        # Remove currency symbols and text
        cleaned = re.sub(r"[^\d.,\s]", "", raw).strip()
        if not cleaned:
            return None

        # If multiple numeric groups exist (e.g. "588.09 21 711.59"), pick the best matching price token
        tokens = cleaned.split()
        if len(tokens) > 1:
            for tok in tokens:
                if re.match(r"^\d{1,6}(?:[.,]\d{1,2})?$", tok):
                    cleaned = tok
                    break
            else:
                cleaned = tokens[0]
        else:
            # Remove spaces (thousands separator in some formats)
            cleaned = cleaned.replace(" ", "")

        # Determine decimal separator
        # If both . and , exist, the last one is the decimal separator
        has_dot = "." in cleaned
        has_comma = "," in cleaned

        if has_dot and has_comma:
            # e.g. "1.234,56" or "1,234.56"
            if cleaned.rfind(",") > cleaned.rfind("."):
                # Comma is decimal: "1.234,56" -> 1234.56
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # Dot is decimal: "1,234.56" -> 1234.56
                cleaned = cleaned.replace(",", "")
        elif has_comma:
            # Could be "1234,56" (decimal) or "1,234" (thousands)
            # If comma has exactly 2 digits after it, treat as decimal
            parts = cleaned.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                cleaned = cleaned.replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")

        try:
            return float(cleaned)
        except ValueError:
            logger.warning("[%s] Could not parse price: '%s'", self.supplier_name, raw)
            return None

    def _absolute_url(self, relative_url: str) -> str:
        """Convert relative URL to absolute using base_url."""
        if relative_url.startswith(("http://", "https://")):
            return relative_url
        return urljoin(self.base_url, relative_url)

    def _rate_limit(self):
        """Simple rate limiting — wait between requests to same supplier."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()


class LinkOnlyScraper(BaseScraper):
    """Base for suppliers where we only generate search URLs (no scraping).

    Used for sites with aggressive anti-bot (e.g. eMAG).
    """

    @abstractmethod
    def get_search_url(self, query: str) -> str:
        """Build the search URL for this supplier."""
        ...

    def search(self, query: str) -> list[Product]:
        """Return a single 'result' with the search link."""
        search_url = self.get_search_url(query)
        return [
            Product(
                name=f"[LINK] Caută '{query}' pe {self.supplier_name}",
                price=0.0,
                currency=self.currency,
                url=search_url,
                supplier=self.supplier_name,
                in_stock=True,
            )
        ]
