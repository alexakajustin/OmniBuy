"""Tests for SearchEngine orchestration, relevancy filter and sorting."""

import pytest

from engine import llm_optimizer
from engine.comparator import best_buy, sort_by_price
from engine.search import SearchEngine, cap_per_supplier, filter_relevant
from models.product import Product
from scrapers.base import BaseScraper


class FakeScraper(BaseScraper):
    """Scraper returning canned results per query, without any HTTP."""

    def __init__(self, name="Fake", responses=None, error=None):
        super().__init__()
        self._name = name
        self._responses = responses or {}
        self._error = error
        self.queries = []

    @property
    def supplier_name(self):
        return self._name

    @property
    def base_url(self):
        return "https://example.com"

    def get_search_url(self, query):
        return f"{self.base_url}/search?q={query}"

    def search(self, query):
        self.queries.append(query)
        if self._error:
            raise self._error
        return [
            Product(name=n, price=p, currency="RON", url=f"{self.base_url}/{i}", supplier=self._name)
            for i, (n, p) in enumerate(self._responses.get(query, []))
        ]


def product(name, price=10.0, is_link=False):
    return Product(name=name, price=price, currency="RON", url="https://x", supplier="S", is_link=is_link)


@pytest.fixture
def ai_term(monkeypatch):
    """Make the AI optimizer return a fixed term without calling any API."""
    def set_term(term):
        monkeypatch.setattr(
            llm_optimizer, "optimize_search_query",
            lambda q: llm_optimizer.OptimizedQuery(q, term, "gemini"),
        )
    return set_term


def test_retries_with_original_query_when_ai_term_finds_nothing(ai_term):
    ai_term("DS-7108")
    scraper = FakeScraper(responses={"DVR Hikvision DS-7108": [("DVR Hikvision DS-7108", 500.0)]})

    outcome = SearchEngine([scraper]).search("DVR Hikvision DS-7108", ai_optimize=True)

    assert scraper.queries == ["DS-7108", "DVR Hikvision DS-7108"]
    assert [p.name for p in outcome.products] == ["DVR Hikvision DS-7108"]
    assert outcome.suppliers[0].status == "ok"
    assert outcome.suppliers[0].query_used == "DVR Hikvision DS-7108"


def test_no_retry_when_ai_term_finds_results(ai_term):
    ai_term("DS-7108")
    scraper = FakeScraper(responses={"DS-7108": [("DVR DS-7108", 500.0)]})

    outcome = SearchEngine([scraper]).search("DVR Hikvision DS-7108", ai_optimize=True)

    assert scraper.queries == ["DS-7108"]
    assert outcome.effective_query == "DS-7108"
    assert outcome.ai_source == "gemini"


def test_failing_scraper_returns_link_and_error_status():
    broken = FakeScraper(name="Broken", error=RuntimeError("boom"))
    working = FakeScraper(name="Working", responses={"cat6": [("Keystone cat6", 5.0)]})

    outcome = SearchEngine([broken, working]).search("cat6")

    statuses = {s.supplier: s.status for s in outcome.suppliers}
    assert statuses == {"Broken": "error", "Working": "ok"}
    links = [p for p in outcome.products if p.is_link]
    assert len(links) == 1 and links[0].supplier == "Broken"


def test_link_only_scraper_is_not_scraped():
    scraper = FakeScraper(responses={"cat6": [("Keystone cat6", 5.0)]})
    scraper.is_link_only = True

    outcome = SearchEngine([scraper]).search("cat6")

    assert scraper.queries == []
    assert outcome.products[0].is_link
    assert outcome.suppliers[0].status == "link"


def test_relevancy_filter_drops_unrelated_products():
    products = [product("Keystone cat6 UTP"), product("Keystone cat6 FTP"), product("Husa telefon"),
                product("[LINK]", 0.0, is_link=True)]
    kept = filter_relevant(products, ["keystone cat6"])
    assert [p.name for p in kept] == ["Keystone cat6 UTP", "Keystone cat6 FTP", "[LINK]"]


def test_relevancy_filter_keeps_few_good_matches_among_much_noise():
    # Mondoplast-style: loose search returns mostly unrelated products.
    products = [product(f"UPS interactiv {i}") for i in range(10)] + [product("Prelungitor 5 prize Schuko")]
    assert [p.name for p in filter_relevant(products, ["prelungitor 5 prize"])] == ["Prelungitor 5 prize Schuko"]


def test_relevancy_filter_requires_numbers_too():
    products = [product("Prelungitor cu 3 prize 1.5m"), product("Prelungitor cu protectie 5 prize Schuko")]
    kept = filter_relevant(products, ["prelungitor cu 5 prize"])
    assert [p.name for p in kept] == ["Prelungitor cu protectie 5 prize Schuko"]


def test_relevancy_filter_ignores_diacritics_and_plurals():
    products = [product("Priză dublă"), product("Prelungitoare 5 PRIZE")]
    assert len(filter_relevant(products, ["priza"])) == 1
    assert len(filter_relevant(products, ["prelungitor 5 prize"])) == 1


def test_relevancy_filter_ignores_separators_in_codes():
    products = [product("Cupla Keystone RJ45 Cat.6 neecranata"), product("Keystone fibra LC")]
    assert [p.name for p in filter_relevant(products, ["keystone cat6"])] == ["Cupla Keystone RJ45 Cat.6 neecranata"]


def test_relevancy_filter_uses_best_of_original_and_ai_term():
    products = [product("Omega OL5G5 negru")]
    assert filter_relevant(products, ["prelungitor negru 5m OL5G5", "OL5G5"]) == products


def test_relevancy_filter_skipped_when_nothing_matches():
    products = [product(f"Produs {i}") for i in range(5)]
    assert filter_relevant(products, ["keystone"]) == products


def test_cap_per_supplier_keeps_cheapest():
    products = [product(f"P{i}", price=float(10 - i)) for i in range(5)]
    assert [p.price for p in cap_per_supplier(products, 2)] == [6.0, 7.0]


def test_best_buy_prefers_in_stock():
    cheap_unavailable = product("Ieftin", 5.0)
    cheap_unavailable.in_stock = False
    available = product("Disponibil", 8.0)
    assert best_buy([cheap_unavailable, available]) is available
    assert best_buy([cheap_unavailable]) is cheap_unavailable


def test_supplier_with_only_irrelevant_results_gets_link():
    loose = FakeScraper(name="Loose", responses={"prelungitor 5 prize": [("UPS 2000VA", 600.0)]})
    good = FakeScraper(name="Good", responses={"prelungitor 5 prize": [("Prelungitor 5 prize", 40.0)]})
    outcome = SearchEngine([loose, good]).search("prelungitor 5 prize")
    statuses = {s.supplier: s.status for s in outcome.suppliers}
    assert statuses == {"Loose": "irrelevant", "Good": "ok"}
    assert [(p.supplier, p.is_link) for p in outcome.products] == [("Good", False), ("Loose", True)]


def test_unpriced_products_are_not_links_and_never_best_buy():
    products = [
        product("Link", 0.0, is_link=True),
        product("Fara pret", 0.0),
        product("Scump", 20.0),
        product("Ieftin", 5.0),
    ]
    assert [p.name for p in sort_by_price(products)] == ["Ieftin", "Scump", "Fara pret", "Link"]
    assert best_buy(products).name == "Ieftin"
