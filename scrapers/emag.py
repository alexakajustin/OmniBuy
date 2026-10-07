"""eMAG.ro scraper — real web scraper using curl_cffi and BeautifulSoup."""

import logging
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product
from config import MAX_RESULTS_PER_SUPPLIER

logger = logging.getLogger(__name__)


class Scraper(BaseScraper):
    """Scraper for eMAG.ro."""

    @property
    def supplier_name(self) -> str:
        return "eMAG"

    @property
    def base_url(self) -> str:
        return "https://www.emag.ro"

    def get_search_url(self, query: str) -> str:
        return f"{self.base_url}/search/{quote_plus(query)}/sort-priceasc/c"

    def search(self, query: str) -> list[Product]:
        search_url = self.get_search_url(query)
        self._rate_limit()

        try:
            response = self._session.get(search_url, timeout=15)
            response.raise_for_status()
            html = self._decode(response)
        except Exception as e:
            logger.warning("[%s] Search request failed: %s", self.supplier_name, e)
            return self._fallback_link(query)

        soup = self._parse_html(html)
        products = []

        # Select product cards
        items = (
            soup.select("div.card-item") or
            soup.select("div.card-v2") or
            soup.select("[data-name]")
        )

        for item in items[:MAX_RESULTS_PER_SUPPLIER]:
            try:
                product = self._parse_item(item)
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug("[%s] Failed to parse item: %s", self.supplier_name, e)
                continue

        if not products:
            logger.warning("[%s] No products parsed, returning fallback link", self.supplier_name)
            return self._fallback_link(query)

        return products

    def _parse_item(self, item) -> Product | None:
        """Parse a single product from eMAG card."""
        # Find product name and link
        link = (
            item.select_one("a.card-v2-title") or
            item.select_one("[data-zone='title'] a") or
            item.select_one("a[href]")
        )
        if not link:
            return None

        name = link.get("title") or link.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        url = self._absolute_url(link.get("href", ""))

        # Price
        price_el = (
            item.select_one(".product-new-price") or
            item.select_one(".price") or
            item.select_one("p.price")
        )
        price = 0.0
        if price_el:
            price_text = price_el.get_text(strip=True)
            # Remove sup elements or non-numeric details cleanly
            parsed_price = self._parse_price(price_text)
            if parsed_price is not None:
                price = parsed_price

        # Stock status
        in_stock = True
        text_lower = item.get_text().lower()
        if "stoc epuizat" in text_lower or "stoc 0" in text_lower:
            in_stock = False

        return Product(
            name=name,
            price=price,
            currency="RON",
            url=url,
            supplier=self.supplier_name,
            in_stock=in_stock,
        )
