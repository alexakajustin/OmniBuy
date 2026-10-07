"""AI Procurement Chat Agent.

Orchestrates multi-item procurement, uses Enterprise Semantic Discovery,
queries boss-recommended suppliers + broader web, enforces technical spec compliance,
and applies Multi-Factor Value & Quality Scoring (replacing naive price sorting).
"""

import re
import json
import logging
import asyncio
from typing import List, Dict, Any, AsyncGenerator

from models.product import Product
from engine.search import SearchEngine
from scrapers.registry import get_scrapers
from engine.web_search import search_web_broad
from engine.semantic_discovery import analyze_procurement_intent
from engine.scorer import rank_products_by_score

logger = logging.getLogger("OmniBuy.ProcurementAgent")


def decompose_procurement_query(user_prompt: str) -> List[str]:
    """
    Split complex multi-item procurement prompts into individual search terms.
    E.g.: 'Vreau un switch poe 8 porturi si 100m cablu cat6' -> ['switch poe 8 porturi', 'cablu cat6 100m']
    """
    delimiters = [r"\s+și\s+", r"\s+si\s+", r"\s*\+\s*", r"\s*,\s*", r"\s+plus\s+", r"\s+and\s+"]
    pattern = "|".join(delimiters)
    
    parts = [p.strip() for p in re.split(pattern, user_prompt, flags=re.IGNORECASE) if len(p.strip()) > 2]
    
    clean_parts = []
    for part in parts:
        cleaned = re.sub(
            r"^(am nevoie de|caut|vreau|imi trebuie|găsește-mi|caută|preturi pentru|un|o|niște)\s+",
            "", part, flags=re.IGNORECASE
        ).strip()
        if len(cleaned) >= 3:
            clean_parts.append(cleaned)

    return clean_parts if clean_parts else [user_prompt.strip()]


async def run_procurement_agent(
    user_prompt: str,
    country: str | None = None,
    supplier_ids: List[str] | None = None,
    include_web_search: bool = True,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Executes the multi-stage procurement agent loop and yields streaming updates:
    1. Semantic Intent Analysis & Query Normalization.
    2. Concurrent Search across Recommended Suppliers and Live Web.
    3. Multi-Factor Value & Sanity Scoring (eliminates false positives like coaxial or plugs).
    4. Conversational recommendation synthesis.
    """
    yield {
        "type": "thought",
        "message": f"Analizez semantic cerința: «{user_prompt}»..."
    }

    # 1. Multi-item query decomposition
    sub_queries = decompose_procurement_query(user_prompt)
    yield {
        "type": "thought",
        "message": f"Identificate {len(sub_queries)} articol(e) de căutat: {', '.join([f'«{q}»' for q in sub_queries])}"
    }

    all_gathered_products: List[Product] = []
    item_results_map: Dict[str, Dict[str, Any]] = {}

    loop = asyncio.get_event_loop()

    for raw_query in sub_queries:
        # Semantic Discovery: analyze intent and build clean supplier query
        intent = analyze_procurement_intent(raw_query)
        primary_search_term = intent.supplier_queries[0]

        yield {
            "type": "thought",
            "message": f"🎯 Categorie detectată: {intent.canonical_name} (Caut la furnizori: «{primary_search_term}»)..."
        }

        # 2. Run recommended supplier scrapers
        scrapers = get_scrapers(supplier_ids=supplier_ids, country=country, force_scrape=True)
        scraped = []
        if scrapers:
            engine = SearchEngine(scrapers)
            outcome = await loop.run_in_executor(None, engine.search, primary_search_term, False)
            scraped = outcome.products

        # 3. Run broad web search if enabled
        web_products = []
        if include_web_search:
            yield {
                "type": "thought",
                "message": f"🌐 Extind căutarea pe internetul din RO/EU (PC Garage, Senzorica, TME etc.) pentru «{primary_search_term}»..."
            }
            web_products = await loop.run_in_executor(None, search_web_broad, primary_search_term, 8)

        # 4. Multi-Factor Value & Quality Scoring
        yield {
            "type": "thought",
            "message": f"⚖️ Evaluez scorul de conformitate, elimin anomalii de preț și accesorii neconforme..."
        }

        combined = scraped + web_products
        ranked_products, disqualified_count = rank_products_by_score(raw_query, combined)

        item_results_map[raw_query] = {
            "products": ranked_products,
            "disqualified_count": disqualified_count,
            "intent": intent,
        }
        all_gathered_products.extend(ranked_products)

    # 5. Build AI conversational advice
    yield {
        "type": "thought",
        "message": "Sintetizez cel mai bun produs conform scorului de calitate/preț..."
    }

    response_lines = []
    response_lines.append(f"### 🤖 Raport Asistent Achiziții OmniBuy\n")

    for raw_query, data in item_results_map.items():
        prods = data["products"]
        disq = data["disqualified_count"]
        intent = data["intent"]
        real_prods = [p for p in prods if p.price > 0 and getattr(p, "composite_score", 0) > 0]

        response_lines.append(f"#### 📦 Rezultate pentru: **«{raw_query}»**")

        if disq > 0:
            response_lines.append(f"> 🛡️ **Filtru Calitate & Sanity Preț**: Am eliminat automat **{disq} produse neconforme** (ex: cabluri coaxiale RG6, mufe sau accesorii derizorii sub prețul minim de {intent.min_expected_price:.0f} lei).")

        if not real_prods:
            response_lines.append(f"- ⚠️ Nu am găsit oferte verificate care să întrunească 100% specificațiile pentru categoria *{intent.canonical_name}*.")
            links = [p for p in prods if p.price == 0]
            if links:
                response_lines.append(f"- Poți verifica manual link-urile directe:")
                for l in links[:3]:
                    response_lines.append(f"  - [{l.supplier}]({l.url})")
            response_lines.append("")
            continue

        # Winner: highest composite score
        best = real_prods[0]
        score_val = int(getattr(best, "composite_score", 85))
        response_lines.append(f"- **⭐ Cel Mai Recomandat Produs (Scor: {score_val}/100)**: **[{best.name}]({best.url})**")
        response_lines.append(f"  - 💰 **{best.price:,.2f} RON** la **{best.supplier}** (În stoc: {'Da' if best.in_stock else 'Verifică site'})")

        # Cheapest compliant alternative (if different from best)
        cheapest_real = min(real_prods, key=lambda p: p.price)
        if cheapest_real.url != best.url and cheapest_real.price < best.price:
            response_lines.append(f"- **💡 Alternativă Buget Conformă**: [{cheapest_real.name}]({cheapest_real.url}) — **{cheapest_real.price:,.2f} RON** ({cheapest_real.supplier})")

        # Other quality alternatives
        alts = [p for p in real_prods[1:4] if p.url != cheapest_real.url]
        if alts:
            response_lines.append(f"- **Alte opțiuni conforme:**")
            for alt in alts:
                response_lines.append(f"  - [{alt.name}]({alt.url}) — **{alt.price:,.2f} RON** ({alt.supplier})")

        response_lines.append("")

    summary_text = "\n".join(response_lines)

    yield {
        "type": "complete",
        "markdown": summary_text,
        "products": [p.to_dict() for p in all_gathered_products],
        "items_count": len(all_gathered_products),
    }
