"""Search engine — orchestrates parallel searches across suppliers."""

import re
import logging
import unicodedata
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import MAX_WORKERS, MAX_RESULTS_PER_SUPPLIER
from models.product import Product
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


@dataclass
class SupplierStatus:
    """What happened at one supplier during a search."""

    supplier: str
    status: str            # "ok" | "link" (search link only) | "irrelevant" (only off-topic results) | "error"
    count: int = 0         # scraped (non-link) products returned
    query_used: str = ""

    def to_dict(self) -> dict:
        return {
            "supplier": self.supplier,
            "status": self.status,
            "count": self.count,
            "query_used": self.query_used,
        }


@dataclass
class SearchOutcome:
    """Full result of a search: products plus how they were obtained."""

    query: str
    effective_query: str
    products: list[Product] = field(default_factory=list)
    suppliers: list[SupplierStatus] = field(default_factory=list)
    ai_source: str | None = None   # None when AI was off; "gemini" | "deepseek" | "original"
    ai_note: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "effective_query": self.effective_query,
            "ai": None if self.ai_source is None else {"source": self.ai_source, "note": self.ai_note},
            "suppliers": [s.to_dict() for s in self.suppliers],
            "results": [p.to_dict() for p in self.products],
        }


class SearchEngine:
    """Runs a search query across multiple scrapers in parallel."""

    def __init__(self, scrapers: list[BaseScraper]):
        self._scrapers = scrapers

    def search(self, query: str, ai_optimize: bool = False) -> SearchOutcome:
        """Search all scrapers concurrently for the given query.

        Failed scrapers are logged and skipped — never blocks the rest.
        """
        outcome = SearchOutcome(query=query, effective_query=query)

        if ai_optimize:
            from engine.llm_optimizer import optimize_search_query
            optimized = optimize_search_query(query)
            outcome.effective_query = optimized.term
            outcome.ai_source = optimized.source
            outcome.ai_note = optimized.note
            if optimized.changed:
                logger.info("Optimized search query: '%s' -> '%s' (%s)", query, optimized.term, optimized.source)

        all_results: list[Product] = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_scraper = {
                executor.submit(self._run_scraper, scraper, outcome.effective_query, query): scraper
                for scraper in self._scrapers
            }

            for future in as_completed(future_to_scraper):
                scraper = future_to_scraper[future]
                try:
                    results, status = future.result()
                except Exception as e:
                    logger.error("[%s] Unexpected error: %s", scraper.supplier_name, e)
                    results, status = [], SupplierStatus(scraper.supplier_name, "error")
                all_results.extend(results)
                outcome.suppliers.append(status)
                logger.info("[%s] %s, %d results", scraper.supplier_name, status.status, status.count)

        _normalize_currencies(all_results)
        relevant = filter_relevant(all_results, [query, outcome.effective_query])
        outcome.products = cap_per_supplier(relevant, MAX_RESULTS_PER_SUPPLIER)

        # Report what survived filtering, not what the supplier's loose search returned.
        survivors: dict[str, int] = {}
        for p in outcome.products:
            if not p.is_link:
                survivors[p.supplier] = survivors.get(p.supplier, 0) + 1
        for status in outcome.suppliers:
            if status.status == "ok":
                status.count = survivors.get(status.supplier, 0)
                if not status.count:
                    # Everything it returned was noise — still give the user a link to check by hand.
                    status.status = "irrelevant"
                    scraper = next(sc for sc in self._scrapers if sc.supplier_name == status.supplier)
                    outcome.products.extend(scraper._fallback_link(status.query_used or query))
        outcome.suppliers.sort(key=lambda s: s.supplier)
        return outcome

    @classmethod
    def _run_scraper(
        cls, scraper: BaseScraper, effective_query: str, original_query: str
    ) -> tuple[list[Product], SupplierStatus]:
        """Search one supplier. If the AI-shortened term finds nothing, retry with the original."""
        query_used = effective_query
        results, failed = cls._safe_search(scraper, effective_query)

        if (
            effective_query != original_query
            and not scraper.is_link_only
            and not any(not p.is_link for p in results)
        ):
            logger.info("[%s] No results for AI term '%s', retrying with original query",
                        scraper.supplier_name, effective_query)
            query_used = original_query
            results, failed = cls._safe_search(scraper, original_query)

        scraped = sum(1 for p in results if not p.is_link)
        if scraped:
            status = "ok"
        elif failed:
            status = "error"
        else:
            status = "link"
        return results, SupplierStatus(scraper.supplier_name, status, scraped, query_used)

    @staticmethod
    def _safe_search(scraper: BaseScraper, query: str) -> tuple[list[Product], bool]:
        """Run a scraper, never raising. Returns (results, failed_with_exception)."""
        try:
            if scraper.is_link_only:
                return scraper._fallback_link(query), False

            results = scraper.search(query)
            if not results:
                return scraper._fallback_link(query), False
            return results, False
        except Exception as e:
            logger.error("[%s] Search failed: %s", scraper.supplier_name, e)
            try:
                return scraper._fallback_link(query), True
            except Exception:
                return [], True


def _normalize_currencies(products: list[Product]) -> None:
    """Convert every priced product to RON in place, keeping the original price."""
    from engine.currency import get_rate

    for p in products:
        if p.currency != "RON" and p.price > 0:
            p.original_price = p.price
            p.original_currency = p.currency
            p.price = round(p.price * get_rate(p.currency), 2)
            p.currency = "RON"


# Filler words that say nothing about the product.
STOPWORDS = {
    "cu", "de", "la", "si", "pt", "pentru", "din", "in", "pe", "un", "o", "a", "al", "ale",
    "sau", "fara", "vreau", "caut", "ceva", "the", "for", "and", "with",
}


def _words(text: str) -> list[str]:
    """Lowercase, diacritic-free alphanumeric tokens ('Priză 5m' -> ['priza', '5m'])."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", plain)


def _match_score(name: str, query_words: list[str]) -> float:
    """Fraction of query words found in the product name."""
    name_words = set(_words(name))
    # Separators removed, so "cat6" matches "Cat.6" / "CAT-6" and "ds7108" matches "DS-7108".
    name_compact = "".join(_words(name))
    hits = sum(
        1 for w in query_words
        # Exact word, or substring for longer words ("prelungitor" in "prelungitoare").
        if w in name_words or (len(w) >= 4 and w in name_compact)
    )
    return hits / len(query_words)


def filter_relevant(products: list[Product], queries: list[str]) -> list[Product]:
    """Keep scraped products whose name contains (nearly) all of the searched words.

    Supplier search engines are loose (Mondoplast returns UPSes for "prelungitor 5 prize",
    price-sorted results start with 3-socket strips), so a product must match at least
    75% of the best match's words, and never less than half of them. Every query variant
    (original and AI term) is tried and the best score counts. If nothing reaches half,
    the filter is skipped rather than returning nothing.
    """
    word_lists = []
    for q in queries:
        words = [w for w in _words(q) if w not in STOPWORDS]
        if words and words not in word_lists:
            word_lists.append(words)
    if not word_lists:
        return products

    scraped = [p for p in products if not p.is_link]
    links = [p for p in products if p.is_link]
    if not scraped:
        return products

    scores = {id(p): max(_match_score(p.name, words) for words in word_lists) for p in scraped}
    best = max(scores.values())
    if best < 0.5:
        return products

    threshold = max(0.5, 0.75 * best)
    matched = [p for p in scraped if scores[id(p)] >= threshold]
    dropped = len(scraped) - len(matched)
    if dropped:
        logger.debug("Relevancy filter dropped %d/%d scraped results", dropped, len(scraped))
    return matched + links


def cap_per_supplier(products: list[Product], limit: int) -> list[Product]:
    """Keep at most `limit` products per supplier, preferring the cheapest priced ones."""
    def order(p: Product):
        return (p.is_link, p.price <= 0, p.price)

    kept: dict[str, int] = {}
    result = []
    for p in sorted(products, key=order):
        if kept.get(p.supplier, 0) < limit:
            kept[p.supplier] = kept.get(p.supplier, 0) + 1
            result.append(p)
    return result
