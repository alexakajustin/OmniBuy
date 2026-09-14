"""URY Shop (ury.ro) scraper — link-only.

URY loads products via AJAX (Algolia-based search), so static HTML
contains no product listings. We return a search link instead.
"""

import logging
from urllib.parse import quote

from scrapers.base import LinkOnlyScraper

logger = logging.getLogger(__name__)


class Scraper(LinkOnlyScraper):
    """Link-only scraper for ury.ro — products load via client-side AJAX."""

    @property
    def supplier_name(self) -> str:
        return "URY Shop"

    @property
    def base_url(self) -> str:
        return "https://ury.ro"

    def get_search_url(self, query: str) -> str:
        return f"{self.base_url}/cauta/?search={quote(query)}"
