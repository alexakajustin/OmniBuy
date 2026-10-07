"""Mondoplast.ro scraper — POST-based search, tr.cout product rows."""

import logging
import re
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product

logger = logging.getLogger(__name__)


class Scraper(BaseScraper):
    """Scraper for mondoplast.ro — cables and telecoms equipment."""

    @property
    def supplier_name(self) -> str:
        return "Mondoplast"

    @property
    def base_url(self) -> str:
        return "https://www.mondoplast.ro"

    def get_search_url(self, query: str) -> str:
        # For fallback links — GET won't work, but the URL is still useful for the user
        return f"{self.base_url}/search.php?tosearch={quote_plus(query)}"

    def search(self, query: str) -> list[Product]:
        self._rate_limit()

        # Mondoplast search requires POST to /search.php with 'tosearch' param
        try:
            response = self._session.post(
                f"{self.base_url}/search.php",
                data={"tosearch": query},
                timeout=15,
            )
            response.raise_for_status()
            html = response.text
        except Exception as e:
            logger.warning("[%s] Search request failed: %s", self.supplier_name, e)
            return self._fallback_link(query)

        soup = self._parse_html(html)
        products = []

        # Product rows are <tr class="cout"> inside <table class="pdrdisp">.
        # The site's search is loose (OR-matching, unsorted), so parse every row and let the
        # engine's relevancy filter and price sort pick the right ones.
        items = soup.select("tr.cout")

        for item in items:
            try:
                product = self._parse_item(item)
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug("[%s] Failed to parse item: %s", self.supplier_name, e)
                continue

        return products

    def _parse_item(self, item) -> Product | None:
        """Parse a single product from a table row."""
        # Find product name and link — Mondoplast uses <a class="ftlink">
        link = item.select_one("a.ftlink") or item.select_one("a[href]")
        if not link:
            return None

        name = link.get("title") or link.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        url = self._absolute_url(link.get("href", ""))

        # Prices: the red one is WITHOUT VAT; every other supplier shows prices with VAT,
        # so use the "cuTVA 21%: 155.44 LEI" figure to keep the comparison fair.
        text = item.get_text(" ", strip=True)
        price = 0.0
        match = re.search(r"cuTVA[^:]*:\s*([\d.,]+)\s*LEI", text, re.I)
        if match:
            parsed = self._parse_price(match.group(1))
            if parsed is not None:
                price = parsed

        # Check stock
        in_stock = True
        text_lower = text.lower()
        if "la comanda" in text_lower or "sunati" in text_lower:
            in_stock = False

        return Product(
            name=name,
            price=price,
            currency="RON",
            url=url,
            supplier=self.supplier_name,
            in_stock=in_stock,
        )
