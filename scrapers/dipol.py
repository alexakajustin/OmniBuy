"""DIPOL (dipolnet.com) scraper — Polish/EU distributor."""

import logging
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product
from config import MAX_RESULTS_PER_SUPPLIER

logger = logging.getLogger(__name__)


class Scraper(BaseScraper):
    """Scraper for dipolnet.com — EU B2B distributor (Poland)."""

    @property
    def supplier_name(self) -> str:
        return "DIPOL"

    @property
    def base_url(self) -> str:
        return "https://www.dipolnet.com"

    @property
    def currency(self) -> str:
        return "EUR"

    def get_search_url(self, query: str) -> str:
        return f"{self.base_url}/search?q={quote_plus(query)}"

    def search(self, query: str) -> list[Product]:
        # DIPOL uses a search endpoint
        search_url = self.get_search_url(query)
        html = self._fetch(search_url)

        if not html:
            return self._fallback_link(query)

        soup = self._parse_html(html)
        products = []

        # Try common product patterns
        items = (
            soup.select("div.product-item") or
            soup.select("div.product") or
            soup.select("div.product-layout") or
            soup.select("[itemtype*='Product']") or
            soup.select("tr.product-row")
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
            return []

        return products

    def _parse_item(self, item) -> Product | None:
        link = (
            item.select_one("h2 a, h3 a, h4 a, .product-name a, .name a") or
            item.select_one("a.product-title, a[title]")
        )
        if not link:
            return None

        name = link.get("title") or link.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        url = self._absolute_url(link.get("href", ""))

        price_el = item.select_one(
            ".price, span.price, span[itemprop='price'], .product-price"
        )
        if not price_el:
            return None

        price_text = price_el.get("content") or price_el.get_text(strip=True)
        price = self._parse_price(price_text)
        if price is None:
            return None

        return Product(
            name=name,
            price=price,
            currency=self.currency,
            url=url,
            supplier=self.supplier_name,
            in_stock=True,
        )
