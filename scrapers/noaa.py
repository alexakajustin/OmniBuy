"""NOAA Concept (noaa.ro) scraper — B2B supplier."""

import logging
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product
from config import MAX_RESULTS_PER_SUPPLIER

logger = logging.getLogger(__name__)


class Scraper(BaseScraper):
    """Scraper for noaa.ro — B2B IT infrastructure supplier."""

    @property
    def supplier_name(self) -> str:
        return "NOAA Concept"

    @property
    def base_url(self) -> str:
        return "https://www.noaa.ro"

    def get_search_url(self, query: str) -> str:
        return f"{self.base_url}/cautare/cauta?q={quote_plus(query)}&sort=p.price&order=ASC"

    def search(self, query: str) -> list[Product]:
        search_url = self.get_search_url(query)
        html = self._fetch(search_url)

        if not html:
            return self._fallback_link(query)

        soup = self._parse_html(html)
        products = []

        # Try multiple product container patterns including B2B table/list layout
        items = (
            soup.select("#rezultate-cautare .itemi > div") or
            soup.select("div.itemi > div") or
            soup.select("div.product-layout") or
            soup.select("div.product-thumb") or
            soup.select("div.product-item") or
            soup.select(".products .product") or
            soup.select("[itemtype*='Product']") or
            soup.select("div.categorii-produs")
        )

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
        """Parse a single product."""
        # Name and link
        link = (
            item.select_one("h2 a") or
            item.select_one("h4 a, h3 a, .product-name a, .name a") or
            item.select_one("a[href*='produs'], a[href*='product']") or
            item.select_one("a[title]")
        )
        if not link:
            return None

        name = link.get("title") or link.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        url = self._absolute_url(link.get("href", ""))

        # Try to find price
        price_el = item.select_one(
            ".price, .pret, .price-new, span[itemprop='price'], "
            ".product-price, .special-price"
        )
        price = 0.0
        if price_el:
            price_text = price_el.get("content") or price_el.get_text(strip=True)
            parsed_price = self._parse_price(price_text)
            if parsed_price is not None:
                price = parsed_price

        # Check stock (defaulting to True if not explicitly out of stock)
        in_stock = True
        text_lower = item.get_text().lower()
        if "stoc epuizat" in text_lower or "lipsa stoc" in text_lower:
            in_stock = False

        return Product(
            name=name,
            price=price,
            currency="RON",
            url=url,
            supplier=self.supplier_name,
            in_stock=in_stock,
        )
