"""Conectica.ro scraper — server-side rendered, easy to parse."""

import logging
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product
from config import MAX_RESULTS_PER_SUPPLIER

logger = logging.getLogger(__name__)


class Scraper(BaseScraper):
    """Scraper for conectica.ro — well-structured HTML with schema.org markup."""

    @property
    def supplier_name(self) -> str:
        return "Conectica"

    @property
    def base_url(self) -> str:
        return "https://www.conectica.ro"

    def get_search_url(self, query: str) -> str:
        return f"{self.base_url}/cautare?q={quote_plus(query)}&sort=p.price&order=ASC"

    def search(self, query: str) -> list[Product]:
        search_url = self.get_search_url(query)
        html = self._fetch(search_url)
        if not html:
            return self._fallback_link(query)

        soup = self._parse_html(html)
        products = []

        # Each product is in a div.categorii-produs with schema.org Product markup
        items = soup.select("div.categorii-produs")

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
        """Parse a single product from the search results."""
        # Name: h3[itemprop="name"] > a
        name_tag = item.select_one('h3[itemprop="name"] a')
        if not name_tag:
            return None
        name = name_tag.get_text(strip=True)
        url = self._absolute_url(name_tag.get("href", ""))

        # Price: span[itemprop="price"] has content attribute with clean float
        price_tag = item.select_one('span[itemprop="price"]')
        if not price_tag:
            return None
        price_str = price_tag.get("content", "")
        price = self._parse_price(price_str)
        if price is None:
            return None

        # Stock: div.stoc-s text content
        stock_tag = item.select_one("div.stoc-s")
        stock_text = stock_tag.get_text(strip=True).lower() if stock_tag else ""
        in_stock = "stoc" in stock_text

        return Product(
            name=name,
            price=price,
            currency="RON",
            url=url,
            supplier=self.supplier_name,
            in_stock=in_stock,
        )
