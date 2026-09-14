"""ATU Tech (a2t.ro) scraper — Vue Storefront API search with robust HTML scraper fallback."""

import logging
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product
from config import MAX_RESULTS_PER_SUPPLIER

logger = logging.getLogger(__name__)


class Scraper(BaseScraper):
    """Scraper for a2t.ro."""

    @property
    def supplier_name(self) -> str:
        return "ATU Tech"

    @property
    def base_url(self) -> str:
        return "https://www.a2t.ro"

    def get_search_url(self, query: str) -> str:
        # User specified clean search url format
        return f"{self.base_url}/cauta/{quote_plus(query)}?sort=price_asc"

    def search(self, query: str) -> list[Product]:
        # 1. Attempt Vue Storefront API search first
        api_url = f"{self.base_url}/api/catalog/vue_storefront_catalog/product/_search"
        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "sku", "description"],
                    "type": "best_fields",
                }
            },
            "size": MAX_RESULTS_PER_SUPPLIER,
        }

        self._rate_limit()
        
        import time
        for _ in range(15):  # retry up to 15 times (wait for valid response)
            try:
                response = self._session.post(
                    api_url,
                    json=body,
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    products = self._parse_api_response(data)
                    if products:
                        return products
            except Exception as e:
                logger.debug("[%s] Vue Storefront API failed, retrying...: %s", self.supplier_name, e)
            time.sleep(0.5)

        # 2. Fallback to HTML scraping
        return self._scrape_html(query)

    def _parse_api_response(self, data: dict) -> list[Product]:
        """Parse Vue Storefront API response."""
        products = []
        hits = data.get("hits", {}).get("hits", [])

        for hit in hits[:MAX_RESULTS_PER_SUPPLIER]:
            try:
                source = hit.get("_source", {})
                name = source.get("name", "")
                if not name:
                    continue

                price = source.get("special_price") or source.get("price") or 0.0
                if isinstance(price, str):
                    price = float(price) if price else 0.0
                price = float(price)

                slug = source.get("url_path") or source.get("url_key", "")
                url = f"{self.base_url}/{slug}" if slug else self.base_url

                stock = source.get("stock", {})
                in_stock = stock.get("is_in_stock", True) if isinstance(stock, dict) else True

                products.append(Product(
                    name=name,
                    price=price,
                    currency="RON",
                    url=url,
                    supplier=self.supplier_name,
                    in_stock=in_stock,
                ))
            except Exception as e:
                logger.debug("[%s] Failed to parse API hit: %s", self.supplier_name, e)
                continue

        return products

    def _scrape_html(self, query: str) -> list[Product]:
        """Scrape the search results page directly."""
        search_url = self.get_search_url(query)
        html = self._fetch(search_url)

        if not html:
            return self._fallback_link(query)

        soup = self._parse_html(html)
        products = []

        # Common selectors for product cards
        items = (
            soup.select(".product-item") or
            soup.select(".product-card") or
            soup.select(".product") or
            soup.select("div.product") or
            soup.select(".product-box") or
            soup.select("[itemtype*='Product']")
        )

        for item in items[:MAX_RESULTS_PER_SUPPLIER]:
            try:
                product = self._parse_html_item(item)
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug("[%s] HTML item parsing failed: %s", self.supplier_name, e)
                continue

        if not products:
            return self._fallback_link(query)

        return products

    def _parse_html_item(self, item) -> Product | None:
        """Parse product details from HTML card."""
        link = (
            item.select_one("h2 a, h3 a, h4 a, .product-name a, .title a") or
            item.select_one("a.product-title, a[href]")
        )
        if not link:
            return None

        name = link.get("title") or link.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        url = self._absolute_url(link.get("href", ""))

        price_el = item.select_one(
            ".price-new, .price, .pret, span.price, .special-price, .product-price"
        )
        price = 0.0
        if price_el:
            price_text = price_el.get("content") or price_el.get_text(strip=True)
            parsed_price = self._parse_price(price_text)
            if parsed_price is not None:
                price = parsed_price

        # Check stock status
        text_lower = item.get_text().lower()
        in_stock = "stoc epuizat" not in text_lower and "la comanda" not in text_lower

        return Product(
            name=name,
            price=price,
            currency="RON",
            url=url,
            supplier=self.supplier_name,
            in_stock=in_stock,
        )
