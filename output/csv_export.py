"""CSV export — save search results to CSV file."""

import csv
import logging
from pathlib import Path

from models.product import Product

logger = logging.getLogger(__name__)


def export(products: list[Product], filepath: str):
    """Export products list to a CSV file."""
    if not products:
        logger.warning("No products to export.")
        return

    path = Path(filepath)
    fieldnames = [
        "name", "price", "currency", "original_price", "original_currency",
        "url", "supplier", "in_stock", "is_link", "timestamp",
    ]

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for product in products:
            writer.writerow(product.to_dict())

    logger.info("Exported %d products to %s", len(products), path)
    print(f"  ✓ Exportat {len(products)} produse → {path}")
