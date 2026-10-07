"""Enterprise Semantic Intent & Discovery Engine.

Understands user procurement intent, identifies real target product categories,
determines realistic price baselines, flags negative accessory keywords,
and normalizes queries for supplier search engines.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("OmniBuy.SemanticDiscovery")

@dataclass
class IntentProfile:
    taxonomy_id: str
    domain: str
    category: str
    canonical_name: str
    supplier_queries: List[str]
    min_expected_price: float
    max_expected_price: float
    required_keywords: List[str] = field(default_factory=list)
    mandatory_sub_specs: List[List[str]] = field(default_factory=list)  # AND of ORs
    forbidden_keywords: List[str] = field(default_factory=list)
    is_bulk_or_reel: bool = False
    strict_match: bool = False


# Enterprise Procurement Taxonomy
TAXONOMY_PROFILES = [
    {
        "id": "IT-NET-CBL",
        "domain": "IT & Networking",
        "category": "Cables & Connectivity",
        "strict_match": True,
        "triggers": [r"\bcablu\b", r"\butp\b", r"\bftp\b", r"\bsftp\b", r"\bcat\.?\s*6[ea]?\b", r"\bcat\.?\s*5e?\b", r"\bcat\.?\s*7\b"],
        "required": [r"\bcat\.?\s*[567][ea]?\b", r"\butp\b", r"\bftp\b", r"\bsftp\b", r"\bretea\b", r"\bethernet\b", r"\btwisted\b"],
        "forbidden": [
            r"\bcoaxial\b", r"\brg6\b", r"\brg59\b", r"\brg11\b", r"\bmufa\b", r"\bconector\b",
            r"\bcleste\b", r"\btester\b", r"\bhdmi\b", r"\bvga\b", r"\baudio\b", r"\bsursa\b",
            r"\bcapison\b", r"\bprotectie\b", r"\bpriza\b", r"\bkeystone\b"
        ],
        "defaults": {
            "100m": {"min": 50.0, "max": 350.0},
            "305m": {"min": 150.0, "max": 900.0},
            "default": {"min": 5.0, "max": 500.0},
        }
    },
    {
        "id": "IT-NET-SWT",
        "domain": "IT & Networking",
        "category": "Switches",
        "strict_match": True,
        "triggers": [r"\bswitch\b", r"\bcomutator\b"],
        "required": [r"\bswitch\b", r"\bcomutator\b"],
        "forbidden": [
            r"\binjector\b", r"\bsplitter\b", r"\bextender\b", r"\bsursa\b",
            r"\badaptor\b", r"\bmodul\b", r"\bpatch panel\b"
        ],
        "defaults": {
            "poe": {"min": 95.0, "max": 3500.0},
            "default": {"min": 35.0, "max": 2000.0},
        }
    },
    {
        "id": "SEC-SUR-CAM",
        "domain": "Security",
        "category": "Surveillance Cameras",
        "strict_match": True,
        "triggers": [r"\bcamera\b", r"\bcameră\b"],
        "required": [r"\bcamera\b", r"\bcameră\b"],
        "forbidden": [
            r"\bsuport\b", r"\bdoza\b", r"\bcarcasa\b", r"\bcutie\b", r"\bsursa\b",
            r"\balimentator\b", r"\bconector\b", r"\bbalun\b"
        ],
        "defaults": {
            "default": {"min": 80.0, "max": 2500.0},
        }
    },
    {
        "id": "SEC-SUR-NVR",
        "domain": "Security",
        "category": "Recorders",
        "strict_match": True,
        "triggers": [r"\bnvr\b", r"\bdvr\b"],
        "required": [r"\bnvr\b", r"\bdvr\b"],
        "forbidden": [r"\bcamera\b", r"\bsuport\b", r"\bhdd\b", r"\bsursa\b"],
        "defaults": {
            "default": {"min": 180.0, "max": 4000.0},
        }
    },
    {
        "id": "OFF-SPL-LBL",
        "domain": "Office Supplies",
        "category": "Labels & Ribbons",
        "strict_match": True,
        "triggers": [r"\betichet[ea]\b", r"\beticheta\b", r"\btermic[ae]\b"],
        "required": [r"\betichet[ea]\b", r"\beticheta\b"],
        "forbidden": [r"\bcablu\b", r"\butp\b", r"\bswitch\b", r"\bcamera\b", r"\bpatch\b"],
        "defaults": {
            "default": {"min": 2.0, "max": 500.0},
        }
    }
]

def analyze_procurement_intent(query: str) -> IntentProfile:
    """
    Analyzes a user procurement query and returns a structured IntentProfile
    with taxonomy classification and expected parameters.
    """
    q_lower = query.lower()

    # Normalize typos
    normalized_q = re.sub(r"\bcat\s*6e\b", "cat6", q_lower)
    normalized_q = re.sub(r"\bcat6e\b", "cat6", normalized_q)

    # Match taxonomy
    matched_profile = None
    for profile in TAXONOMY_PROFILES:
        if any(re.search(trigger, q_lower) for trigger in profile["triggers"]):
            matched_profile = profile
            break

    if not matched_profile:
        # GEN-M-001 Generic Fallback
        # Strict match False -> we rely on Jaccard overlap in scorer
        return IntentProfile(
            taxonomy_id="GEN-M-001",
            domain="General",
            category="Uncategorized",
            canonical_name=query,
            supplier_queries=[normalized_q],
            min_expected_price=1.0,
            max_expected_price=100000.0,
            required_keywords=[w for w in re.findall(r"\b\w{3,}\b", normalized_q)],
            forbidden_keywords=[],
            is_bulk_or_reel=False,
            strict_match=False,
        )

    tax_id = matched_profile["id"]
    forbidden = list(matched_profile["forbidden"])
    required = list(matched_profile["required"])
    mandatory_sub_specs: List[List[str]] = []
    
    # Extract defaults
    if tax_id == "IT-NET-CBL":
        if re.search(r"\bcat\.?\s*6[ea]?\b", q_lower):
            mandatory_sub_specs.append([r"\bcat\.?\s*6[ea]?\b"])
        elif re.search(r"\bcat\.?\s*5e?\b", q_lower):
            mandatory_sub_specs.append([r"\bcat\.?\s*5e?\b"])

        is_100m = bool(re.search(r"\b100\s*m\b", q_lower))
        is_305m = bool(re.search(r"\b305\s*m\b", q_lower))

        if is_100m or is_305m:
            forbidden.extend([r"\bpatch\s*cord\b", r"\bpatchcord\b"])

        if is_100m:
            min_p, max_p = 65.0, matched_profile["defaults"]["100m"]["max"]
            supplier_queries = ["cablu utp cat6 100m", "cablu cat6 100m", "rola cat6 100m"]
        elif is_305m:
            min_p, max_p = 180.0, matched_profile["defaults"]["305m"]["max"]
            supplier_queries = ["cablu utp cat6 305m", "cablu cat6 305m", "rola cat6 305m"]
        else:
            min_p, max_p = matched_profile["defaults"]["default"]["min"], matched_profile["defaults"]["default"]["max"]
            supplier_queries = [normalized_q, f"cablu {normalized_q}"]

        canon_name = "Cablu de rețea"
        if re.search(r"\bcat\.?\s*6[ea]?\b", q_lower):
            canon_name += " Cat6"
        elif re.search(r"\bcat\.?\s*5e?\b", q_lower):
            canon_name += " Cat5"

        return IntentProfile(
            taxonomy_id=tax_id,
            domain=matched_profile["domain"],
            category=matched_profile["category"],
            canonical_name=canon_name,
            supplier_queries=supplier_queries,
            min_expected_price=min_p,
            max_expected_price=max_p,
            required_keywords=required,
            mandatory_sub_specs=mandatory_sub_specs,
            forbidden_keywords=forbidden,
            is_bulk_or_reel=is_100m or is_305m,
            strict_match=matched_profile["strict_match"]
        )

    elif tax_id == "IT-NET-SWT":
        is_poe = bool(re.search(r"\bpoe\b", q_lower))
        if is_poe:
            min_p, max_p = matched_profile["defaults"]["poe"]["min"], matched_profile["defaults"]["poe"]["max"]
            mandatory_sub_specs.append([r"\bpoe\b", r"\bpoe\+\b", r"\b802\.3af\b", r"\b802\.3at\b", r"power over ethernet"])
            supplier_queries = [normalized_q, "switch poe gigabit", "switch poe"]
        else:
            min_p, max_p = matched_profile["defaults"]["default"]["min"], matched_profile["defaults"]["default"]["max"]
            supplier_queries = [normalized_q]

        if bool(re.search(r"\bgigabit\b", q_lower)):
            mandatory_sub_specs.append([r"\bgigabit\b", r"\b1000m\b", r"\b1000mbps\b", r"\b10/100/1000\b"])

        return IntentProfile(
            taxonomy_id=tax_id,
            domain=matched_profile["domain"],
            category=matched_profile["category"],
            canonical_name="Switch de Rețea" + (" PoE" if is_poe else ""),
            supplier_queries=supplier_queries,
            min_expected_price=min_p,
            max_expected_price=max_p,
            required_keywords=required,
            mandatory_sub_specs=mandatory_sub_specs,
            forbidden_keywords=forbidden,
            is_bulk_or_reel=False,
            strict_match=matched_profile["strict_match"]
        )

    # General specific profile fallback (e.g. Labels, Cameras)
    return IntentProfile(
        taxonomy_id=tax_id,
        domain=matched_profile["domain"],
        category=matched_profile["category"],
        canonical_name=normalized_q.title(),
        supplier_queries=[normalized_q],
        min_expected_price=matched_profile["defaults"]["default"]["min"],
        max_expected_price=matched_profile["defaults"]["default"]["max"],
        required_keywords=required,
        mandatory_sub_specs=[],
        forbidden_keywords=forbidden,
        is_bulk_or_reel=False,
        strict_match=matched_profile["strict_match"]
    )

