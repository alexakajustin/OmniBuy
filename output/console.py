"""Console output — formatted tables for terminal display."""

import sys
import io

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from colorama import init, Fore, Style
from tabulate import tabulate

from models.product import Product
from engine.comparator import best_buy, group_by_supplier

# Initialize colorama for Windows
init(autoreset=True)


def print_results(products: list[Product], query: str):
    """Print search results as a formatted table with best buy highlighted."""
    if not products:
        print(f"\n{Fore.YELLOW}Nu s-au găsit rezultate pentru: '{query}'{Style.RESET_ALL}")
        return

    cheapest = best_buy(products)

    print(f"\n{Fore.CYAN}{'═' * 80}")
    print(f"  Rezultate pentru: '{query}'  ({len(products)} produse găsite)")
    print(f"{'═' * 80}{Style.RESET_ALL}\n")

    # Build table rows
    rows = []
    for i, p in enumerate(products, 1):
        is_best = cheapest and p is cheapest
        if p.is_link:
            price_str = f"{Fore.BLUE}[LINK]{Style.RESET_ALL}"
        elif p.price <= 0:
            price_str = f"{Fore.YELLOW}preț indisponibil{Style.RESET_ALL}"
        elif is_best:
            price_str = f"{Fore.GREEN}★ {p.price_display}{Style.RESET_ALL}"
        else:
            price_str = p.price_display

        stock_str = f"{Fore.GREEN}✓{Style.RESET_ALL}" if p.in_stock else f"{Fore.RED}✗{Style.RESET_ALL}"

        # Truncate long names
        name = p.name[:60] + "…" if len(p.name) > 60 else p.name

        rows.append([i, name, price_str, p.supplier, stock_str, p.url[:70]])

    headers = ["#", "Produs", "Preț", "Furnizor", "Stoc", "Link"]
    print(tabulate(rows, headers=headers, tablefmt="simple"))

    # Best buy summary
    if cheapest:
        print(f"\n{Fore.GREEN}{'─' * 80}")
        print(f"  ★ BEST BUY: {cheapest.name}")
        print(f"    {cheapest.price_display} — {cheapest.supplier}")
        print(f"    {cheapest.url}")
        print(f"{'─' * 80}{Style.RESET_ALL}")

    # Link-only suppliers
    link_products = [p for p in products if p.is_link]
    if link_products:
        print(f"\n{Fore.BLUE}Linkuri directe (fără scraping):{Style.RESET_ALL}")
        for p in link_products:
            print(f"  → {p.supplier}: {p.url}")

    print()


def print_suppliers(suppliers: list[dict]):
    """Print configured suppliers as a table."""
    rows = []
    for s in suppliers:
        status = f"{Fore.GREEN}ON{Style.RESET_ALL}" if s.get("enabled") else f"{Fore.RED}OFF{Style.RESET_ALL}"
        mode = f"{Fore.BLUE}link-only{Style.RESET_ALL}" if s.get("link_only") else "scrape"
        rows.append([s["id"], s["name"], s.get("country", ""), s["url"], status, mode])

    headers = ["ID", "Nume", "Țară", "URL", "Status", "Mod"]
    print(f"\n{Fore.CYAN}Furnizori configurați:{Style.RESET_ALL}\n")
    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print()
