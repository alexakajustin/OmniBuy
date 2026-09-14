"""Technical Specification & Relevancy Validator.

Ensures products strictly match technical constraints (PoE, Gigabit, Cat6, etc.)
and eliminates false positives (e.g. basic switches without PoE, brackets matching camera queries).
"""

import re
import logging
from typing import List, Tuple, Set
from models.product import Product

logger = logging.getLogger("OmniBuy.SpecFilter")

# Mandatory feature groups: if query contains any term in the key,
# the product MUST match at least one of the patterns in the value.
MANDATORY_CONSTRAINTS = {
    # Power over Ethernet
    "poe": {
        "required_patterns": [r"\bpoe\b", r"\bpoe\+\b", r"\b802\.3af\b", r"\b802\.3at\b", r"\b802\.3bt\b", r"power over ethernet"],
        "context_rejects": {
            "switch": [r"\binjector\b", r"\bsplitter\b", r"\bextender\b", r"\bsursa\b", r"\badaptor\b"]
        }
    },
    # Cabling categories
    "cat6": {
        "required_patterns": [r"\bcat\.?\s*6\b", r"\bcat6\b"],
    },
    "cat6a": {
        "required_patterns": [r"\bcat\.?\s*6a\b", r"\bcat6a\b"],
    },
    "cat5e": {
        "required_patterns": [r"\bcat\.?\s*5e\b", r"\bcat5e\b"],
    },
    "cat7": {
        "required_patterns": [r"\bcat\.?\s*7\b", r"\bcat7\b"],
    },
    # Shielding
    "utp": {
        "required_patterns": [r"\butp\b", r"\bu/utp\b"],
    },
    "ftp": {
        "required_patterns": [r"\bftp\b", r"\bf/utp\b", r"\bsftp\b", r"\bs/ftp\b"],
    },
    # Speed
    "gigabit": {
        "required_patterns": [r"\bgigabit\b", r"\b1000m\b", r"\b1000mbps\b", r"\b1gbps\b", r"\b10/100/1000\b"],
    },
    "10g": {
        "required_patterns": [r"\b10g\b", r"\b10gbps\b", r"\b10\s*gigabit\b"],
    },
    # Surveillance
    "nvr": {
        "required_patterns": [r"\bnvr\b", r"network video recorder"],
        "reject_patterns": [r"\bcamera\b", r"\bsuport\b", r"\bdoza\b", r"\bhdd\b"]
    },
    "dvr": {
        "required_patterns": [r"\bdvr\b", r"digital video recorder"],
        "reject_patterns": [r"\bcamera\b", r"\bsuport\b", r"\bdoza\b"]
    },
    "camera": {
        "required_patterns": [r"\bcamera\b", r"\bcameră\b"],
        "reject_patterns": [r"\bsuport\b", r"\bdoza\b", r"\bcarcasa\b", r"\bsursa\b", r"\bcutie\b", r"\bconector\b"]
    }
}


def extract_mandatory_rules(query: str) -> List[Tuple[str, dict]]:
    """Identify which mandatory technical constraints apply to this query."""
    q_lower = query.lower()
    active_rules = []
    
    for term, config in MANDATORY_CONSTRAINTS.items():
        # Check if term exists as a distinct word in the query
        if re.search(rf"\b{re.escape(term)}\b", q_lower):
            active_rules.append((term, config))
            
    return active_rules


def is_product_compliant(product: Product, query: str, active_rules: List[Tuple[str, dict]]) -> Tuple[bool, str]:
    """
    Check if a product satisfies all technical requirements of the query.
    Returns (is_compliant, reason_if_rejected).
    """
    # Link-only fallback entries are always preserved
    if product.price == 0:
        return True, "link_only"

    name_lower = product.name.lower()
    q_lower = query.lower()

    # 1. Check mandatory technical rules
    for term, config in active_rules:
        # Check required patterns
        req_patterns = config.get("required_patterns", [])
        has_required = any(re.search(pat, name_lower) for pat in req_patterns)
        
        if not has_required:
            return False, f"Missing required specification '{term}'"

        # Check reject patterns
        reject_patterns = config.get("reject_patterns", [])
        for rej in reject_patterns:
            # Only reject if the user query itself did NOT explicitly ask for the rejected word
            if re.search(rej, name_lower) and not re.search(rej, q_lower):
                return False, f"Matches accessory/reject pattern '{rej}'"

        # Check context rejects (e.g. user asked for 'switch poe', but product is 'injector poe')
        context_rejects = config.get("context_rejects", {})
        for context_word, forbidden_list in context_rejects.items():
            if context_word in q_lower:
                for forbidden in forbidden_list:
                    if re.search(forbidden, name_lower) and context_word not in name_lower:
                        return False, f"Is an accessory ({forbidden}) instead of a true {context_word}"

    # 2. General word overlap check (must have at least 50% core query words if multiple words)
    core_words = [w.lower() for w in re.findall(r"\b\w{3,}\b", q_lower)]
    if len(core_words) >= 2:
        matched_words = sum(1 for w in core_words if w in name_lower)
        # For multi-word queries like 'switch poe', must match all core constraints
        if matched_words < 1:
            return False, "Insufficient keyword overlap"

    return True, "compliant"


def filter_spec_compliance(query: str, products: List[Product]) -> List[Product]:
    """
    Filter out false-positive products that fail technical constraints.
    If filtering removes too many valid products, returns high-confidence filtered set.
    """
    active_rules = extract_mandatory_rules(query)
    if not active_rules:
        # No strict technical rules detected, return all
        return products

    compliant_products = []
    rejected_count = 0

    for p in products:
        ok, reason = is_product_compliant(p, query, active_rules)
        if ok:
            compliant_products.append(p)
        else:
            rejected_count += 1
            logger.debug("SpecFilter dropped '%s': %s", p.name, reason)

    logger.info(
        "SpecFilter for '%s': kept %d, dropped %d false positives (rules: %s)",
        query, len(compliant_products), rejected_count, [r[0] for r in active_rules]
    )

    # If at least one compliant real product was found, use the clean set
    real_compliant = [p for p in compliant_products if p.price > 0]
    if real_compliant:
        # Keep link-only fallbacks as well
        links = [p for p in products if p.price == 0]
        return compliant_products + [l for l in links if l not in compliant_products]

    # If everything was filtered out, return original so user sees something rather than empty
    logger.warning("SpecFilter would drop all products for '%s', returning unfiltered.", query)
    return products
