"""Product data model."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Product:
    """A single product result from a supplier search."""

    name: str
    price: float
    currency: str  # "RON", "EUR", "PLN"
    url: str
    supplier: str
    in_stock: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    @property
    def price_display(self) -> str:
        """Formatted price string, e.g. '12.50 RON'."""
        return f"{self.price:,.2f} {self.currency}"

    def to_dict(self) -> dict:
        """Convert to dict for CSV export."""
        return {
            "name": self.name,
            "price": self.price,
            "currency": self.currency,
            "url": self.url,
            "supplier": self.supplier,
            "in_stock": self.in_stock,
            "timestamp": self.timestamp,
        }
