"""ATU Tech (a2t.ro) scraper — Vue Storefront catalog API.

The site renders search results client-side, so the HTML contains no products.
Instead we query the same Elasticsearch-backed catalog API the site's own JS uses.
"""

import logging
from urllib.parse import quote_plus

from scrapers.base import BaseScraper
from models.product import Product
from config import MAX_RESULTS_PER_SUPPLIER, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# Store index from the site's config (storeId 1 = Romanian store).
CATALOG_INDEX = "vue_storefront_catalog_1"
SEARCHABLE_VISIBILITY = (3, 4)  # Magento: 3 = search only, 4 = catalog + search


class Scraper(BaseScraper):
    """Scraper for a2t.ro."""

    @property
    def supplier_name(self) -> str:
        return "ATU Tech"

    @property
    def base_url(self) -> str:
        return "https://www.a2t.ro"

    def get_search_url(self, query: str) -> str:
        return f"{self.base_url}/cauta/{quote_plus(query)}?sort=price_asc"

    def search(self, query: str) -> list[Product]:
        # First require every word to match; if that finds nothing, accept any word
        # (the engine's relevancy filter then removes the noise).
        for operator in ("and", "or"):
            hits = self._query_api(query, operator)
            if hits is None:  # API error — don't hammer it with a second request
                return self._fallback_link(query)
            products = [p for p in (self._parse_hit(h) for h in hits) if p]
            if products:
                return products
        return []

    def _query_api(self, query: str, operator: str) -> list[dict] | None:
        url = f"{self.base_url}/api/catalog/{CATALOG_INDEX}/product/_search"
        body = {
            "query": {
                "bool": {
                    "must": [{
                        "multi_match": {
                            "query": query,
                            "fields": ["name^3", "sku^5"],
                            "operator": operator,
                        }
                    }],
                    "filter": [
                        {"term": {"status": 1}},
                        {"terms": {"visibility": list(SEARCHABLE_VISIBILITY)}},
                    ],
                }
            },
            "sort": [{"final_price": "asc"}],
            "size": MAX_RESULTS_PER_SUPPLIER,
        }

        self._rate_limit()
        try:
            response = self._session.post(url, json=body, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json().get("hits", {}).get("hits", [])
        except Exception as e:
            logger.warning("[%s] Catalog API failed: %s", self.supplier_name, e)
            return None

    def _parse_hit(self, hit: dict) -> Product | None:
        source = hit.get("_source", {})
        name = source.get("name")
        url_key = source.get("url_key")
        if not name or not url_key:
            return None

        price = _to_float(source.get("final_price")) or _to_float(source.get("price"))
        special = _to_float(source.get("special_price"))
        if special and (not price or special < price):
            price = special

        # Product pages live under /<category>/<url_key>.html (any category prefix resolves).
        categories = source.get("category") or []
        category = next(
            (c.get("url_path") for c in reversed(categories) if isinstance(c, dict) and c.get("url_path")),
            "produs",
        )

        stock = source.get("stock")
        in_stock = bool(stock.get("is_in_stock")) if isinstance(stock, dict) else True

        return Product(
            name=name,
            price=price or 0.0,
            currency="RON",
            url=f"{self.base_url}/{category}/{url_key}.html",
            supplier=self.supplier_name,
            in_stock=in_stock,
        )


def _to_float(value) -> float:
    try:
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0
