"""BestBuyTool — CLI entry point.

Usage:
    python main.py search "keystone cat6"
    python main.py search "rola velcro" --suppliers lan_shop emag
    python main.py search "DVR Hikvision" --country RO --csv results.csv
    python main.py suppliers
"""

import sys
import os
import argparse
import logging

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.registry import get_scrapers, list_suppliers
from engine.search import SearchEngine
from engine.comparator import sort_by_price
from output.console import print_results, print_suppliers
from output.csv_export import export


def setup_logging(verbose: bool = False):
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_search(args):
    """Execute a search across suppliers."""
    query = " ".join(args.query)
    if not query.strip():
        print("Eroare: query-ul de căutare nu poate fi gol.")
        sys.exit(1)

    # Parse supplier IDs
    supplier_ids = args.suppliers if args.suppliers else None
    country = args.country if args.country else None

    # Load scrapers
    scrapers = get_scrapers(
        supplier_ids=supplier_ids,
        country=country,
        force_scrape=getattr(args, "force", False),
    )
    if not scrapers:
        print("Eroare: niciun scraper disponibil cu filtrele specificate.")
        print("  Verifică suppliers.json sau folosește 'python main.py suppliers' pentru lista.")
        sys.exit(1)

    print(f"\n🔍 Caut '{query}' la {len(scrapers)} furnizor(i)...\n")

    # Search
    engine = SearchEngine(scrapers)
    results = engine.search(query, ai_optimize=getattr(args, "ai", False))

    # Sort by price
    results = sort_by_price(results)

    # Display
    print_results(results, query)

    # CSV export if requested
    if args.csv:
        export(results, args.csv)


def cmd_suppliers(args):
    """List all configured suppliers."""
    suppliers = list_suppliers()
    print_suppliers(suppliers)


def cmd_web(args):
    """Start FastAPI server for Web UI."""
    import uvicorn
    import webbrowser
    from threading import Timer

    host = args.host
    port = args.port

    url = f"http://{host}:{port}"
    print(f"\n🚀 Pornesc Web UI la: {url}")
    print("  Apasă Ctrl+C în terminal pentru a opri serverul.\n")

    # Automatically open browser after 1 second if not disabled
    if not args.no_browser:
        def open_browser():
            try:
                webbrowser.open(url)
            except Exception:
                pass

        Timer(1.0, open_browser).start()

    # Run Uvicorn server with auto-reload
    uvicorn.run("web.server:app", host=host, port=port, log_level="warning", reload=True)



def main():
    parser = argparse.ArgumentParser(
        prog="BestBuyTool",
        description="🛒 Compară prețuri de la furnizori multipli (RO + EU)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Logging detaliat")
    subparsers = parser.add_subparsers(dest="command", help="Comandă")

    # --- search command ---
    search_parser = subparsers.add_parser("search", help="Caută un produs la toți furnizorii")
    search_parser.add_argument("query", nargs="+", help="Ce cauți (ex: 'keystone cat6 UTP')")
    search_parser.add_argument(
        "--suppliers", "-s",
        nargs="+",
        help="Furnizori specifici (ID-uri din suppliers.json)",
    )
    search_parser.add_argument(
        "--country", "-c",
        help="Filtrează pe țară (ex: RO, PL)",
    )
    search_parser.add_argument(
        "--csv",
        help="Export rezultate în fișier CSV",
    )
    search_parser.add_argument(
        "--force",
        action="store_true",
        help="Forțează web scraping chiar și pentru furnizorii marcați cu link_only",
    )
    search_parser.add_argument(
        "--ai",
        action="store_true",
        help="Activează optimizarea automată a căutării cu Inteligența Artificială (Gemini)",
    )
    search_parser.set_defaults(func=cmd_search)

    # --- suppliers command ---
    suppliers_parser = subparsers.add_parser("suppliers", help="Listează furnizorii configurați")
    suppliers_parser.set_defaults(func=cmd_suppliers)

    # --- web command ---
    web_parser = subparsers.add_parser("web", help="Pornește interfața grafică (Web UI)")
    web_parser.add_argument("--host", default="127.0.0.1", help="Host pentru server (implicit: 127.0.0.1)")
    web_parser.add_argument("--port", type=int, default=8000, help="Port pentru server (implicit: 8000)")
    web_parser.add_argument("--no-browser", action="store_true", help="Nu deschide browserul automat")
    web_parser.set_defaults(func=cmd_web)

    # Parse and execute
    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    # Initialize exchange rates
    from engine.currency import init_exchange_rates
    init_exchange_rates()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Adjust behavior for --no-browser
    if args.command == "web" and args.no_browser:
        # Override the browser opening logic inside cmd_web
        pass

    args.func(args)


if __name__ == "__main__":
    main()


