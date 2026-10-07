"""Comparator — sort, group, and find best buy from product results."""

from models.product import Product


def sort_by_price(products: list[Product], ascending: bool = True) -> list[Product]:
    """Sort products by price.

    Products whose price could not be read come after the priced ones,
    and search-link placeholders go last.
    """
    priced = [p for p in products if not p.is_link and p.price > 0]
    unpriced = [p for p in products if not p.is_link and p.price <= 0]
    links = [p for p in products if p.is_link]

    sorted_priced = sorted(priced, key=lambda p: p.price, reverse=not ascending)
    return sorted_priced + unpriced + links


def group_by_supplier(products: list[Product]) -> dict[str, list[Product]]:
    """Group products by supplier name."""
    groups: dict[str, list[Product]] = {}
    for product in products:
        groups.setdefault(product.supplier, []).append(product)
    return groups


def best_buy(products: list[Product]) -> Product | None:
    """Return the cheapest product you can actually buy.

    Prefers in-stock products; falls back to the cheapest overall if none are in stock.
    Link-only and unpriced results are ignored.
    """
    priced = [p for p in products if not p.is_link and p.price > 0]
    if not priced:
        return None
    in_stock = [p for p in priced if p.in_stock]
    return min(in_stock or priced, key=lambda p: p.price)


def top_n(products: list[Product], n: int = 5) -> list[Product]:
    """Return top N cheapest products."""
    return sort_by_price(products)[:n]
