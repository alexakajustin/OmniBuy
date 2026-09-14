"""Currency conversion module."""

import logging
import requests

logger = logging.getLogger(__name__)

_rates = {"RON": 1.0}

def init_exchange_rates():
    """Fetch exchange rates relative to RON from a free API."""
    global _rates
    try:
        url = "https://open.er-api.com/v6/latest/EUR"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        rates = data.get("rates", {})
        ron_rate = rates.get("RON")
        if not ron_rate:
            raise ValueError("RON rate not found in API response")
            
        # Convert EUR base to RON base
        _rates["EUR"] = ron_rate
        if "PLN" in rates:
            _rates["PLN"] = ron_rate / rates["PLN"]
            
        logger.info(
            "Loaded exchange rates: 1 EUR = %.2f RON, 1 PLN = %.2f RON", 
            _rates.get("EUR", 0), _rates.get("PLN", 0)
        )
    except Exception as e:
        logger.warning("Failed to fetch exchange rates, using defaults: %s", e)
        # Fallback to rough defaults if API fails
        _rates["EUR"] = 4.97
        _rates["PLN"] = 1.15

def get_rate(currency: str) -> float:
    """Get the multiplier to convert the given currency to RON."""
    return _rates.get(currency.upper(), 1.0)
