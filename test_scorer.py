"""Test suite for Enterprise Semantic Discovery and Multi-Factor Scorer."""

import sys
import os

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.product import Product
from engine.semantic_discovery import analyze_procurement_intent
from engine.scorer import evaluate_product_score, rank_products_by_score


def test_coaxial_and_plug_rejection():
    """Verify that coaxial cable and plugs are strictly disqualified when searching 100m cablu cat6e."""
    query = "100m cablu cat6e"
    intent = analyze_procurement_intent(query)

    assert intent.taxonomy_id == "IT-NET-CBL"
    assert "coaxial" in " ".join(intent.forbidden_keywords)
    assert intent.is_bulk_or_reel is True
    assert intent.min_expected_price >= 50.0

    # 1. The exact product from user screenshot (Coaxial RG6 at 0.57 RON)
    coaxial_prod = Product(
        name="Cablu coaxial RG6 , CCS, 100m, 75ohm Braun Group - RG6-100",
        price=0.57,
        currency="RON",
        url="https://www.mondoplast.ro/rg6",
        supplier="Mondoplast"
    )
    res_coax = evaluate_product_score(coaxial_prod, intent, query)
    assert res_coax["is_disqualified"] is True
    assert res_coax["composite_score"] == 0.0
    print(f"PASS: Coaxial cable disqualified (Reason: {res_coax['disqualification_reason']})")

    # 2. The RJ45 plug at 1.34 RON
    plug_prod = Product(
        name="Mufa RJ45 pentru cablu UTP 8p8c Cat 6e",
        price=1.34,
        currency="RON",
        url="https://www.emag.ro/mufa",
        supplier="eMAG"
    )
    res_plug = evaluate_product_score(plug_prod, intent, query)
    assert res_plug["is_disqualified"] is True
    assert res_plug["composite_score"] == 0.0
    print(f"PASS: RJ45 plug disqualified (Reason: {res_plug['disqualification_reason']})")

    # 2.5 The 5m patch cord at 28.09 RON from user screenshot (must be disqualified!)
    patch_cord_5m = Product(
        name="Patch Cord F/UTP cat.6 5m Braun Group - PCFTP6-5M-CU",
        price=28.09,
        currency="RON",
        url="https://www.mondoplast.ro/patch-cord-5m",
        supplier="Mondoplast"
    )
    res_cord = evaluate_product_score(patch_cord_5m, intent, query)
    assert res_cord["is_disqualified"] is True
    assert res_cord["composite_score"] == 0.0
    print(f"PASS: 5m Patch cord disqualified when asking for 100m (Reason: {res_cord['disqualification_reason']})")

    # 3. Real 100m Cat6 cable (must win top score)
    real_cable = Product(
        name="Cablu de retea UTP Cat6 cupru 100m rola gri",
        price=129.50,
        currency="RON",
        url="https://www.conectica.ro/cablu-cat6-100m",
        supplier="Conectica",
        in_stock=True
    )
    res_real = evaluate_product_score(real_cable, intent, query)
    assert res_real["is_disqualified"] is False
    assert res_real["composite_score"] >= 80.0
    print(f"PASS: Real Cat6 100m cable received high score: {res_real['composite_score']}/100")

    # 4. Test rank_products_by_score: real cable MUST be ranked #1
    ranked, disq_count = rank_products_by_score(query, [coaxial_prod, plug_prod, real_cable])
    assert disq_count == 2
    assert len(ranked) == 1
    assert ranked[0].name == real_cable.name
    print("PASS: rank_products_by_score successfully crowned real Cat6 cable as #1!")


def test_switch_poe_scoring():
    """Verify that non-PoE switch is disqualified from 'switch poe'."""
    query = "switch poe"
    intent = analyze_procurement_intent(query)

    fake_poe = Product(
        name="Switch D-Link DES-1005D",
        price=42.35,
        currency="RON",
        url="https://www.emag.ro/des-1005d",
        supplier="eMAG"
    )
    res_fake = evaluate_product_score(fake_poe, intent, query)
    assert res_fake["is_disqualified"] is True
    print(f"PASS: Non-PoE switch disqualified (Reason: {res_fake['disqualification_reason']})")

    real_poe = Product(
        name="Switch PoE TP-Link TL-SF1008P 8 Porturi 10/100 cu 4 Porturi PoE",
        price=189.00,
        currency="RON",
        url="https://www.conectica.ro/switch-poe",
        supplier="Conectica"
    )
    res_poe = evaluate_product_score(real_poe, intent, query)
    assert res_poe["is_disqualified"] is False
    assert res_poe["composite_score"] >= 80.0
    print(f"PASS: Real PoE switch received high score: {res_poe['composite_score']}/100")


def test_thermal_labels_rejection():
    """Verify that 'rola etichete termice' triggers the Labels taxonomy, not network cables."""
    query = "rola etichete termice"
    intent = analyze_procurement_intent(query)
    assert intent.taxonomy_id == "OFF-SPL-LBL"
    print("PASS: 'rola etichete termice' matched Office Supplies > Labels instead of generic/network!")

def test_thermal_labels_vs_utp_roll():
    """Verify that a UTP cable roll gets disqualified for a thermal labels query."""
    query = "rola etichete termice"
    intent = analyze_procurement_intent(query)
    
    # 1. Product that only matches "rola"
    utp_cable = Product(
        name="Rola cablu retea UTP cat. 5e CCA rola 305m",
        price=231.80,
        currency="RON",
        url="https://www.conectica.ro/utp",
        supplier="Conectica"
    )
    res_utp = evaluate_product_score(utp_cable, intent, query)
    
    # It should be disqualified because strict_match is True for OFF-SPL-LBL and it lacks required terms ("eticheta")
    assert res_utp["is_disqualified"] is True
    print(f"PASS: UTP Cable Roll correctly disqualified for thermal labels query. Reason: {res_utp['disqualification_reason']}")

    # 2. Real label roll
    label_roll = Product(
        name="Rola etichete termice albe 26 x 12 mm, 1500 buc",
        price=3.04,
        currency="RON",
        url="https://www.emag.ro/etichete",
        supplier="eMAG"
    )
    res_lbl = evaluate_product_score(label_roll, intent, query)
    assert res_lbl["is_disqualified"] is False
    assert res_lbl["composite_score"] > 50.0
    print(f"PASS: Real label roll correctly scored! ({res_lbl['composite_score']}/100)")


if __name__ == "__main__":
    test_coaxial_and_plug_rejection()
    test_switch_poe_scoring()
    test_thermal_labels_rejection()
    test_thermal_labels_vs_utp_roll()
    print("\nAll Semantic Discovery & Multi-Factor Scoring tests passed successfully!")
