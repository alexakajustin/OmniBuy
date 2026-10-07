"""Tests for BaseScraper._parse_price."""

import pytest

from scrapers.conectica import Scraper


@pytest.fixture(scope="module")
def scraper():
    return Scraper()


@pytest.mark.parametrize("raw, expected", [
    ("12,50 lei", 12.50),
    ("€15.99", 15.99),
    ("1.234,56 RON", 1234.56),
    ("1,234.56", 1234.56),
    ("15 990 Ft", 15990.0),
    ("1234", 1234.0),
])
def test_parse_price(scraper, raw, expected):
    assert scraper._parse_price(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "lei", "pret la cerere"])
def test_parse_price_returns_none_for_garbage(scraper, raw):
    assert scraper._parse_price(raw) is None
