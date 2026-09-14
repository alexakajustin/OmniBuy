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
    original_price: float | None = None
    original_currency: str | None = None
    composite_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)

    @property
    def price_display(self) -> str:
        """Formatted price string, e.g. '12.50 RON'."""
        if self.original_price and self.original_currency:
            return f"{self.price:,.2f} RON ({self.original_price:,.2f} {self.original_currency})"
        return f"{self.price:,.2f} {self.currency}"

    def to_dict(self) -> dict:
        """Convert to dict for API & CSV export."""
        return {
            "name": self.name,
            "price": self.price,
            "currency": self.currency,
            "original_price": self.original_price,
            "original_currency": self.original_currency,
            "url": self.url,
            "supplier": self.supplier,
            "in_stock": self.in_stock,
            "composite_score": self.composite_score,
            "score_breakdown": self.score_breakdown,
            "timestamp": self.timestamp,
        }
