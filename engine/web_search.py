"""Broad Web Search Engine for IT & Electronics Suppliers.

Allows searching beyond the predefined supplier scrapers across the wider Romanian & EU web
(e.g. PC Garage, Altex, Senzorica, TME, Spy Shop, Cel.ro, etc.) using live web scraping.
"""

import re
import logging
from urllib.parse import quote_plus, urlparse
from typing import List

from curl_cffi import requests
from bs4 import BeautifulSoup

from models.product import Product
from engine.spec_filter import filter_spec_compliance

logger = logging.getLogger("OmniBuy.WebSearch")


def search_web_broad(query: str, max_results: int = 10) -> List[Product]:
    """
    Search the live web for products matching query on Romanian & EU tech sites.
    Extracts product titles, prices (when visible in snippets), domains, and links.
    """
    products: List[Product] = []

    # Build specialized search query for tech stores
    search_terms = f"{query} pret magazin ro OR preturi ro"
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_terms)}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8",
    }

    try:
        session = requests.Session(impersonate="chrome110")
        response = session.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "lxml")
            results = soup.select("div.result") or soup.select("div.web-result")

            for r in results:
                if len(products) >= max_results:
                    break

                title_el = r.select_one("a.result__a") or r.select_one("h2 a")
                snippet_el = r.select_one(".result__snippet") or r.select_one("a.result__snippet")
                url_el = r.select_one("a.result__url")

                if not title_el:
                    continue

                raw_title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                
                # Unwrap DuckDuckGo redirect url if needed
                if "uddg=" in href:
                    from urllib.parse import unquote, parse_qs
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    if "uddg" in qs:
                        href = qs["uddg"][0]

                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                
                # Detect domain
                domain = urlparse(href).netloc.replace("www.", "")
                if not domain or "duckduckgo" in domain:
                    continue

                # Filter out irrelevant aggregation/wikipedia sites
                if any(skip in domain for skip in ["wikipedia.org", "youtube.com", "facebook.com", "reddit.com", "tiktok.com"]):
                    continue

                # Attempt price extraction from snippet or title
                # Matches patterns like: '149,99 Lei', '250 RON', '45.50 lei'
                price = 0.0
                full_text = f"{raw_title} {snippet}"
                price_match = re.search(r"(\d{1,5}(?:[.,]\d{2})?)\s*(?:lei|ron)", full_text, re.IGNORECASE)
                if price_match:
                    raw_p = price_match.group(1).replace(".", "").replace(",", ".")
                    try:
                        price = float(raw_p)
                    except ValueError:
                        price = 0.0

                product = Product(
                    name=raw_title,
                    price=price,
                    currency="RON",
                    url=href,
                    supplier=f"[Web] {domain}",
                    in_stock=True,
                )
                products.append(product)

    except Exception as e:
        logger.warning("Broad web search error: %s", e)

    # Filter with technical spec constraints (e.g. ensuring PoE if requested)
    return filter_spec_compliance(query, products)
