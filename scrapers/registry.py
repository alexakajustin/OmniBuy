"""Scraper registry — dynamically loads scrapers from suppliers.json."""

import json
import importlib
import logging
from pathlib import Path

from config import SUPPLIERS_FILE
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


def _load_suppliers_config() -> list[dict]:
    """Load supplier definitions from suppliers.json."""
    config_path = Path(SUPPLIERS_FILE)
    if not config_path.exists():
        logger.error("suppliers.json not found at %s", config_path)
        return []

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("suppliers", [])


def _load_scraper(supplier: dict) -> BaseScraper | None:
    """Dynamically import and instantiate a scraper from its module path."""
    module_path = supplier["module"]
    try:
        module = importlib.import_module(module_path)
        # Convention: each scraper module has a `Scraper` class
        scraper_class = getattr(module, "Scraper")
        return scraper_class()
    except (ImportError, AttributeError) as e:
        logger.warning(
            "Could not load scraper '%s' (%s): %s",
            supplier["id"], module_path, e,
        )
        return None


def get_scrapers(
    supplier_ids: list[str] | None = None,
    country: str | None = None,
    force_scrape: bool = False,
) -> list[BaseScraper]:
    """Get scraper instances filtered by IDs and/or country.

    Args:
        supplier_ids: If provided, only load these supplier IDs.
        country: If provided, only load suppliers from this country.
        force_scrape: If True, bypass link_only constraints.

    Returns:
        List of instantiated scraper objects.
    """
    suppliers = _load_suppliers_config()
    scrapers = []

    for supplier in suppliers:
        # Skip disabled suppliers
        if not supplier.get("enabled", True):
            continue

        # Filter by ID if specified
        if supplier_ids and supplier["id"] not in supplier_ids:
            continue

        # Filter by country if specified
        if country and supplier.get("country", "").upper() != country.upper():
            continue

        scraper = _load_scraper(supplier)
        if scraper:
            # "link_only" in suppliers.json = the site blocks or can't be scraped, never scrape it.
            # force_scrape=False (UI checkbox off / CLI --links-only) turns scraping off for everyone.
            scraper.is_link_only = supplier.get("link_only", False) or not force_scrape
            scrapers.append(scraper)

    return scrapers


def list_suppliers() -> list[dict]:
    """Return all supplier configs for display."""
    return _load_suppliers_config()
