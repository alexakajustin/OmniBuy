"""Lanberg (lanberg.pl) scraper — Polish manufacturer."""

import logging
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product
from config import MAX_RESULTS_PER_SUPPLIER

logger = logging.getLogger(__name__)


class Scraper(BaseScraper):
    """Scraper for lanberg.pl — Polish networking equipment manufacturer."""

    @property
    def supplier_name(self) -> str:
        return "Lanberg"

    @property
    def base_url(self) -> str:
        return "https://pl.lanberg.eu"

    @property
    def currency(self) -> str:
        return "PLN"

    def get_search_url(self, query: str) -> str:
        # e.g., https://pl.lanberg.eu/wyszukiwarka?query=rj45
        return f"{self.base_url}/wyszukiwarka?query={quote_plus(query)}"

    def search(self, query: str) -> list[Product]:
        search_url = self.get_search_url(query)
        html = self._fetch(search_url)

        if not html:
            return self._fallback_link(query)

        soup = self._parse_html(html)
        products = []

        # Try multiple product container patterns
        items = (
            soup.select(".card") or
            soup.select(".product-list__item") or
            soup.select("div.product-item") or
            soup.select("div.product") or
            soup.select("li.product-item") or
            soup.select("[itemtype*='Product']") or
            soup.select("div.product-layout")
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
        # Find product link
        link = (
            item.select_one("h2 a, h3 a, h4 a, .product-name a, .name a") or
            item.select_one("a.product-item-link, a.product-title, a[title], a.product-list__link") or
            item.select_one("a[href]")
        )
        if not link:
            return None

        name = link.get("title") or link.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        url = self._absolute_url(link.get("href", ""))

        # Try to find price
        price_el = item.select_one(
            ".price, span.price, span[itemprop='price'], .product-price"
        )
        price = 0.0
        if price_el:
            price_text = price_el.get("content") or price_el.get_text(strip=True)
            parsed_price = self._parse_price(price_text)
            if parsed_price is not None:
                price = parsed_price

        return Product(
            name=name,
            price=price,
            currency=self.currency,
            url=url,
            supplier=self.supplier_name,
            in_stock=True,
        )
