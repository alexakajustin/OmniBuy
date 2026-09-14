"""Search engine — orchestrates parallel searches across suppliers."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import MAX_WORKERS
from models.product import Product
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SearchEngine:
    """Runs a search query across multiple scrapers in parallel."""

    def __init__(self, scrapers: list[BaseScraper]):
        self._scrapers = scrapers

    def search(self, query: str, ai_optimize: bool = False) -> list[Product]:
        """Search all scrapers concurrently for the given query.

        Failed scrapers are logged and skipped — never blocks the rest.
        """
        all_results: list[Product] = []

        # LLM Optimization
        optimized_query = query
        if ai_optimize:
            from engine.llm_optimizer import optimize_search_query
            optimized_query = optimize_search_query(query)
            if optimized_query != query:
                logger.info("Optimized search query: '%s' -> '%s'", query, optimized_query)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_scraper = {
                executor.submit(self._safe_search, scraper, optimized_query): scraper
                for scraper in self._scrapers
            }

            for future in as_completed(future_to_scraper):
                scraper = future_to_scraper[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    logger.info(
                        "[%s] Found %d results", scraper.supplier_name, len(results)
                    )
                except Exception as e:
                    logger.error(
                        "[%s] Unexpected error: %s", scraper.supplier_name, e
                    )

        # Normalize currencies to RON
        from engine.currency import get_rate
        for p in all_results:
            if p.currency != "RON" and p.price > 0:
                p.original_price = p.price
                p.original_currency = p.currency
                
                rate = get_rate(p.currency)
                p.price = round(p.price * rate, 2)
                p.currency = "RON"

        # Technical Spec & Relevancy Filter:
        # Strictly ensures mandatory technical features (PoE, Gigabit, Cat6, etc.) are respected
        from engine.spec_filter import filter_spec_compliance
        all_results = filter_spec_compliance(f"{query} {optimized_query}", all_results)

        return all_results

    @staticmethod
    def _safe_search(scraper: BaseScraper, query: str) -> list[Product]:
        """Wrapper that catches exceptions from individual scrapers."""
        try:
            if getattr(scraper, "is_link_only", False):
                # Return link without scraping
                if hasattr(scraper, "_fallback_link"):
                    return scraper._fallback_link(query)
                
                # If it's an actual LinkOnlyScraper
                if hasattr(scraper, "get_search_url"):
                    return scraper.search(query)
                
                # Generic fallback
                from urllib.parse import quote_plus
                url = getattr(scraper, "base_url", "")
                return [
                    Product(
                        name=f"[LINK] Caută '{query}' pe {scraper.supplier_name}",
                        price=0.0,
                        currency=scraper.currency,
                        url=f"{url}/search?q={quote_plus(query)}",
                        supplier=scraper.supplier_name,
                        in_stock=True,
                    )
                ]

            results = scraper.search(query)
            if not results:
                return scraper._fallback_link(query)
            return results
        except Exception as e:
            logger.error("[%s] Search failed: %s", scraper.supplier_name, e)
            return scraper._fallback_link(query)
