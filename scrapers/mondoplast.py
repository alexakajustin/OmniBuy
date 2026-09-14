"""Mondoplast.ro scraper — POST-based search, tr.cout product rows."""

import logging
import re
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product
from config import MAX_RESULTS_PER_SUPPLIER

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

        # Product rows are <tr class="cout"> inside <table class="pdrdisp">
        items = soup.select("tr.cout")

        for item in items[:MAX_RESULTS_PER_SUPPLIER]:
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

        # Find price — typically in a <font color='red'> or last TD
        price = 0.0
        price_el = item.select_one("font[color='red'], .price, .pret, span.pret")
        if price_el:
            price_text = price_el.get_text(strip=True)
            parsed = self._parse_price(price_text)
            if parsed is not None:
                price = parsed
        else:
            # Regex fallback in the row text
            text = item.get_text()
            match = re.search(r"(\d+[.,]\d{2})\s*(lei|ron|RON|Lei|EUR|eur)", text)
            if match:
                parsed = self._parse_price(match.group(1))
                if parsed is not None:
                    price = parsed

        # Check stock
        in_stock = True
        text_lower = item.get_text().lower()
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
