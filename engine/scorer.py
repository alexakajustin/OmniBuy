"""Multi-Factor Composite Scoring Engine.

Replaces naive 'min(price)' sorting with an evolutionary value & relevance scoring algorithm:
Evaluates:
- Semantic Category & Spec Match (disqualifies wrong categories / accessories)
- Price Sanity & Outlier Detection (rejects 0.57 lei plugs/meters when seeking 100m reels)
- In-Stock Availability
- Supplier Authority & Trust
"""

import re
import logging
from typing import List, Dict, Any, Tuple
from models.product import Product
from engine.semantic_discovery import analyze_procurement_intent, IntentProfile

logger = logging.getLogger("OmniBuy.Scorer")


def evaluate_product_score(product: Product, intent: IntentProfile, query: str) -> Dict[str, Any]:
    """
    Computes a multi-factor score (0 - 100) for a product against user intent.
    Returns score breakdown and disqualification status.
    """
    # Link-only entries (price 0) are kept for manual inspection
    if product.price == 0:
        return {
            "composite_score": 10.0,
            "relevance": 50.0,
            "price_sanity": 50.0,
            "stock": 50.0,
            "trust": 50.0,
            "is_disqualified": False,
            "reasons": ["Link direct magazin"],
        }

    name_lower = product.name.lower()
    q_lower = query.lower()

    # --- 1. Hard Disqualification Checks ---
    # A. Check forbidden keywords (e.g. coaxial when searching for network cable, or mufa when searching cable)
    for forbidden_regex in intent.forbidden_keywords:
        # Only check if user did NOT explicitly ask for the forbidden word
        if re.search(forbidden_regex, name_lower) and not re.search(forbidden_regex, q_lower):
            matched_term = re.search(forbidden_regex, name_lower).group(0)
            return {
                "composite_score": 0.0,
                "relevance": 0.0,
                "price_sanity": 0.0,
                "stock": 0.0,
                "trust": 0.0,
                "is_disqualified": True,
                "disqualification_reason": f"Accesoriu / categorie neconformă («{matched_term}»)",
                "reasons": [f"Eliminat: conține termen neconform «{matched_term}»"],
            }

    # B. Check required base keywords
    if intent.required_keywords:
        if getattr(intent, "strict_match", True):
            has_required = any(re.search(pat, name_lower) for pat in intent.required_keywords)
            if not has_required:
                return {
                    "composite_score": 0.0,
                    "relevance": 0.0,
                    "price_sanity": 0.0,
                    "stock": 0.0,
                    "trust": 0.0,
                    "is_disqualified": True,
                    "disqualification_reason": "Lipsesc specificațiile de bază cerute",
                    "reasons": ["Eliminat: nu conține specificațiile de bază"],
                }

    # C. Check mandatory sub-specifications (AND of sub-specs, e.g. PoE, Gigabit, Cat6)
    for sub_spec_list in intent.mandatory_sub_specs:
        has_sub_spec = any(re.search(pat, name_lower) for pat in sub_spec_list)
        if not has_sub_spec:
            spec_name = sub_spec_list[0].replace(r"\b", "").replace(r"\+", "+")
            return {
                "composite_score": 0.0,
                "relevance": 0.0,
                "price_sanity": 0.0,
                "stock": 0.0,
                "trust": 0.0,
                "is_disqualified": True,
                "disqualification_reason": f"Lipsesc specificațiile obligatorii («{spec_name}»)",
                "reasons": [f"Eliminat: nu conține specificația obligatorie «{spec_name}»"],
            }

    # D. Check quantitative numeric specifications (Length, Ports, Channels)
    # 1. Length in meters:
    req_lengths = re.findall(r"\b(\d+)\s*(?:m|metri|meter|meters)\b", q_lower)
    if req_lengths:
        target_len = req_lengths[0]
        # Find explicit lengths in product name (e.g. 5m, 100m, 305m)
        prod_lengths = re.findall(r"\b(\d+)\s*(?:m|metri)\b", name_lower)
        if prod_lengths:
            if target_len not in prod_lengths:
                return {
                    "composite_score": 0.0,
                    "relevance": 0.0,
                    "price_sanity": 0.0,
                    "stock": 0.0,
                    "trust": 0.0,
                    "is_disqualified": True,
                    "disqualification_reason": f"Lungime neconformă: s-a cerut {target_len}m, dar produsul are {prod_lengths[0]}m",
                    "reasons": [f"Eliminat: lungime neconformă ({prod_lengths[0]}m în loc de {target_len}m)"],
                }

    # 2. Port count for switches:
    req_ports = re.findall(r"\b(\d+)\s*(?:porturi|port|p)\b", q_lower)
    if req_ports and ("switch" in q_lower or intent.category == "network_switch"):
        target_ports = req_ports[0]
        prod_ports = re.findall(r"\b(\d+)\s*(?:porturi|port|p)\b", name_lower)
        if prod_ports:
            if target_ports not in prod_ports:
                return {
                    "composite_score": 0.0,
                    "relevance": 0.0,
                    "price_sanity": 0.0,
                    "stock": 0.0,
                    "trust": 0.0,
                    "is_disqualified": True,
                    "disqualification_reason": f"Număr de porturi neconform: s-a cerut {target_ports} porturi, dar produsul are {prod_ports[0]} porturi",
                    "reasons": [f"Eliminat: număr porturi neconform ({prod_ports[0]}p în loc de {target_ports}p)"],
                }

    # --- 2. Price Sanity Check (Detect 'Too Cheap to be True' Anomalies) ---
    price = product.price
    # If price is lower than 45% of minimum expected price when baseline is significant (> 40 lei)
    if (intent.is_bulk_or_reel or intent.min_expected_price >= 40.0) and price < (intent.min_expected_price * 0.45):
        return {
            "composite_score": 0.0,
            "relevance": 0.0,
            "price_sanity": 0.0,
            "stock": 0.0,
            "trust": 0.0,
            "is_disqualified": True,
            "disqualification_reason": f"Preț anomalic ({price:,.2f} RON) mult sub baremul minim realist ({intent.min_expected_price:.0f} RON)",
            "reasons": [f"Eliminat: preț anomalic ({price:,.2f} lei) sub baremul minim realist"],
        }

    # Calculate Price Sanity Score
    # Rewards products in the sweet spot of [min_expected_price, max_expected_price]
    if price < intent.min_expected_price:
        price_sanity_score = 60.0  # Suspiciously cheap but plausible discount
    elif price <= intent.max_expected_price:
        # Normalized score: cheaper within realistic bounds gets higher points
        norm = (price - intent.min_expected_price) / max(1.0, intent.max_expected_price - intent.min_expected_price)
        price_sanity_score = 100.0 - (norm * 30.0)  # Between 70 and 100
    else:
        # Overpriced compared to market average
        price_sanity_score = max(20.0, 70.0 - ((price - intent.max_expected_price) / intent.max_expected_price * 50.0))

    # --- 3. Relevance & Spec Match Score (Token Overlap) ---
    query_tokens = set(re.findall(r"\b\w{3,}\b", q_lower))
    name_tokens = set(re.findall(r"\b\w{3,}\b", name_lower))
    
    if query_tokens:
        overlap = len(query_tokens.intersection(name_tokens))
        overlap_ratio = overlap / len(query_tokens)
    else:
        overlap_ratio = 1.0

    # Strict penalty for generic fallback if overlap < 50%
    if not getattr(intent, "strict_match", True) and overlap_ratio < 0.5:
        return {
            "composite_score": 0.0,
            "relevance": 0.0,
            "price_sanity": 0.0,
            "stock": 0.0,
            "trust": 0.0,
            "is_disqualified": True,
            "disqualification_reason": f"Relevanță lexicală insuficientă ({int(overlap_ratio*100)}% din termeni)",
            "reasons": ["Eliminat: suprapunere de termeni sub 50%"],
        }

    # Base relevance based on overlap
    relevance_score = overlap_ratio * 100.0
    
    # If it's a strict match category and it passed all hard checks, minimum relevance is 80
    if getattr(intent, "strict_match", True):
        relevance_score = max(relevance_score, 80.0)

    # Bonus for exact length / port match
    if intent.is_bulk_or_reel and re.search(r"\b100\s*m\b", name_lower):
        relevance_score += 15.0
    if "poe" in q_lower and re.search(r"\bpoe\b", name_lower):
        relevance_score += 15.0
    if "gigabit" in q_lower and re.search(r"\bgigabit\b", name_lower):
        relevance_score += 10.0
    relevance_score = min(100.0, relevance_score)

    # --- 4. Stock Score ---
    stock_score = 100.0 if product.in_stock else 30.0

    # --- 5. Supplier Trust Score ---
    supplier_score = 90.0 if not product.supplier.startswith("[Web]") else 75.0

    # --- 6. Composite Weighted Calculation ---
    # 45% Relevance, 35% Price Value, 10% Stock, 10% Trust
    composite = (
        0.45 * relevance_score +
        0.35 * price_sanity_score +
        0.10 * stock_score +
        0.10 * supplier_score
    )

    return {
        "composite_score": round(composite, 1),
        "relevance": round(relevance_score, 1),
        "price_sanity": round(price_sanity_score, 1),
        "stock": round(stock_score, 1),
        "trust": round(supplier_score, 1),
        "is_disqualified": False,
        "reasons": [
            f"Scor Relevanță: {int(relevance_score)}%",
            f"Raport Preț/Valoare: {int(price_sanity_score)}%",
            "În stoc" if product.in_stock else "Stoc la cerere",
        ],
    }


def rank_products_by_score(query: str, products: List[Product]) -> Tuple[List[Product], int]:
    """
    Ranks products by composite value score instead of simple ascending price.
    Attaches score metadata to each product and filters out disqualified items.
    Returns (ranked_compliant_products, disqualified_count).
    """
    intent = analyze_procurement_intent(query)
    compliant_list = []
    disqualified_count = 0

    for p in products:
        eval_result = evaluate_product_score(p, intent, query)
        p.composite_score = eval_result["composite_score"]
        p.score_breakdown = eval_result

        if eval_result["is_disqualified"]:
            disqualified_count += 1
            logger.debug("Disqualified '%s': %s", p.name, eval_result.get("disqualification_reason"))
        else:
            compliant_list.append(p)

    # Sort compliant products by composite_score DESCENDING
    # Products with highest composite score (best match & value) are ranked first
    ranked = sorted(compliant_list, key=lambda p: p.composite_score, reverse=True)

    logger.info(
        "Ranked %d products for '%s': kept %d, disqualified %d false positives/anomalies",
        len(products), query, len(ranked), disqualified_count
    )

    # If ranking kept at least one valid real product, return it
    if ranked:
        return ranked, disqualified_count

    # Fallback: if everything was disqualified (rare edge case), return original products
    return products, 0
