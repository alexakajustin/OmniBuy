"""Comparator — sort, group, and find best buy from product results."""

from models.product import Product


def sort_by_price(products: list[Product], ascending: bool = True) -> list[Product]:
    """Sort products by price. Link-only results (price=0) go to the end."""
    real_products = [p for p in products if p.price > 0]
    link_only = [p for p in products if p.price == 0]

    sorted_real = sorted(real_products, key=lambda p: p.price, reverse=not ascending)
    return sorted_real + link_only


def group_by_supplier(products: list[Product]) -> dict[str, list[Product]]:
    """Group products by supplier name."""
    groups: dict[str, list[Product]] = {}
    for product in products:
        groups.setdefault(product.supplier, []).append(product)
    return groups


def best_buy(products: list[Product]) -> Product | None:
    """Return the cheapest product (ignoring link-only results)."""
    priced = [p for p in products if p.price > 0]
    if not priced:
        return None
    return min(priced, key=lambda p: p.price)


def top_n(products: list[Product], n: int = 5) -> list[Product]:
    """Return top N cheapest products."""
    return sort_by_price(products)[:n]
