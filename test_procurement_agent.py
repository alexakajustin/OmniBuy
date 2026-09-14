"""Test suite for AI Procurement Agent, Technical Spec Filter, and Web Search."""

import sys
import os
import asyncio

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.product import Product
from engine.spec_filter import filter_spec_compliance, extract_mandatory_rules, is_product_compliant
from engine.procurement_agent import decompose_procurement_query


def test_spec_filter_poe():
    """Verify that false-positive non-PoE switches and PoE accessories are rejected."""
    query = "switch poe"
    rules = extract_mandatory_rules(query)
    assert len(rules) > 0
    assert rules[0][0] == "poe"

    # Test 1: The exact case from user's screenshot (D-Link DES-1005D non-PoE switch)
    fake_poe = Product(
        name="Switch D-Link DES-1005D",
        price=42.35,
        currency="RON",
        url="https://www.emag.ro/des-1005d",
        supplier="eMAG"
    )
    ok, reason = is_product_compliant(fake_poe, query, rules)
    assert not ok, f"Expected non-PoE switch to be rejected! Reason: {reason}"
    print(f"PASS: Non-PoE switch rejected correctly ({reason})")

    # Test 2: PoE injector when asking for switch
    injector = Product(
        name="Injector PoE TP-Link TL-POE150S",
        price=75.0,
        currency="RON",
        url="https://www.emag.ro/injector",
        supplier="eMAG"
    )
    ok_inj, reason_inj = is_product_compliant(injector, query, rules)
    assert not ok_inj, f"Expected injector to be rejected when asking for switch! Reason: {reason_inj}"
    print(f"PASS: PoE injector rejected when asking for switch ({reason_inj})")

    # Test 3: Real PoE switch (must pass)
    real_poe = Product(
        name="Switch TP-Link TL-SF1008P 8-Port 10/100 Desktop cu 4 Porturi PoE",
        price=189.0,
        currency="RON",
        url="https://www.conectica.ro/switch-poe",
        supplier="Conectica"
    )
    ok_real, reason_real = is_product_compliant(real_poe, query, rules)
    assert ok_real, f"Expected genuine PoE switch to pass! Reason: {reason_real}"
    print("PASS: Genuine PoE switch passed correctly")

    # Test 4: filter_spec_compliance on list
    filtered = filter_spec_compliance(query, [fake_poe, injector, real_poe])
    assert len(filtered) == 1
    assert filtered[0].name == real_poe.name
    print("PASS: filter_spec_compliance filtered out all false positives")


def test_spec_filter_surveillance():
    """Verify that mounts/brackets are rejected when searching for cameras."""
    query = "camera hikvision 4mp"
    rules = extract_mandatory_rules(query)

    mount = Product(
        name="Suport de perete Hikvision DS-1273ZJ pentru camera",
        price=45.0,
        currency="RON",
        url="https://a2t.ro/suport",
        supplier="ATU Tech"
    )
    ok_mount, reason_mount = is_product_compliant(mount, query, rules)
    assert not ok_mount, f"Mount should be rejected! Reason: {reason_mount}"
    print(f"PASS: Camera mount rejected correctly ({reason_mount})")

    camera = Product(
        name="Camera supraveghere IP Hikvision 4MP DS-2CD1043G0-I",
        price=249.0,
        currency="RON",
        url="https://a2t.ro/camera",
        supplier="ATU Tech"
    )
    ok_cam, reason_cam = is_product_compliant(camera, query, rules)
    assert ok_cam, f"Real camera should pass! Reason: {reason_cam}"
    print("PASS: Real camera passed correctly")


def test_multi_item_query_decomposition():
    """Verify that multi-item procurement queries are split correctly."""
    prompt1 = "Vreau un switch poe 8 porturi si 100m cablu cat6 utp"
    parts1 = decompose_procurement_query(prompt1)
    assert len(parts1) == 2, f"Expected 2 parts, got {parts1}"
    assert "switch poe 8 porturi" in parts1[0].lower()
    assert "100m cablu cat6 utp" in parts1[1].lower()
    print(f"PASS: Multi-item prompt split into: {parts1}")

    prompt2 = "camera hikvision 4mp, nvr 8 canale + patch panel cat6"
    parts2 = decompose_procurement_query(prompt2)
    assert len(parts2) == 3, f"Expected 3 parts, got {parts2}"
    print(f"PASS: Multi-item prompt split into: {parts2}")


def test_procurement_agent_generator():
    """Verify procurement agent produces streaming events."""
    from engine.procurement_agent import run_procurement_agent

    async def run_test():
        events = []
        # Run agent with mock search query and web search disabled for fast unit test
        async for evt in run_procurement_agent(
            user_prompt="keystone cat6",
            include_web_search=False,
            supplier_ids=["conectica"],
        ):
            events.append(evt)

        assert len(events) >= 2
        assert events[0]["type"] == "thought"
        last = events[-1]
        assert last["type"] in ["complete", "error"]
        print(f"PASS: Agent stream yielded {len(events)} events successfully")

    asyncio.run(run_test())


if __name__ == "__main__":
    test_spec_filter_poe()
    test_spec_filter_surveillance()
    test_multi_item_query_decomposition()
    test_procurement_agent_generator()
    print("\nAll Procurement Agent & Spec Filter test suites passed successfully!")
