"""Comprehensive test suite for Agent and Model Load Balancer."""

import sys
import os
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.agent_balancer import (
    AgentModelLoadBalancer,
    WebSocketAgentBalancer,
    BalancingStrategy,
    DEFAULT_GEMINI_MODELS,
)


def test_least_busy_selection():
    models = ["model-a", "model-b", "model-c"]
    balancer = AgentModelLoadBalancer(models=models, strategy=BalancingStrategy.LEAST_BUSY)

    # Pick first model
    m1 = balancer.pick_model_sync()
    assert m1 == "model-a", f"Expected model-a, got {m1}"
    assert balancer._stats["model-a"].active_requests == 1

    # Next pick should pick model with 0 active requests (model-b or model-c)
    m2 = balancer.pick_model_sync()
    assert m2 in ["model-b", "model-c"], f"Expected model-b or model-c, got {m2}"
    assert balancer._stats[m2].active_requests == 1

    # Release m1
    balancer.release_model_sync(m1, success=True)
    assert balancer._stats[m1].active_requests == 0

    print("PASS: test_least_busy_selection")


def test_round_robin_selection():
    models = ["model-1", "model-2", "model-3"]
    balancer = AgentModelLoadBalancer(models=models, strategy=BalancingStrategy.ROUND_ROBIN)

    picks = [balancer.pick_model_sync() for _ in range(6)]
    expected = ["model-1", "model-2", "model-3", "model-1", "model-2", "model-3"]
    assert picks == expected, f"Expected {expected}, got {picks}"

    print("PASS: test_round_robin_selection")


def test_rate_limit_circuit_breaker():
    models = ["model-x", "model-y"]
    balancer = AgentModelLoadBalancer(models=models, cooldown_seconds=10.0)

    # Simulate 429 rate limit error on model-x
    m = balancer.pick_model_sync()
    assert m == "model-x"
    balancer.release_model_sync("model-x", success=False, is_rate_limited=True)

    assert not balancer._stats["model-x"].is_available
    assert balancer._stats["model-x"].cooldown_remaining > 0

    # Healthy models should only contain model-y now
    healthy = balancer.get_healthy_models()
    assert healthy == ["model-y"], f"Expected ['model-y'], got {healthy}"

    # Next pick must be model-y
    next_m = balancer.pick_model_sync()
    assert next_m == "model-y"

    # Fallback order should place healthy model-y first
    fallback_order = balancer.get_fallback_order_sync()
    assert fallback_order[0] == "model-y"
    assert fallback_order[1] == "model-x"

    print("PASS: test_rate_limit_circuit_breaker")


def test_websocket_agent_balancer():
    balancer = WebSocketAgentBalancer()

    class MockWS:
        client_state = type("State", (), {"name": "CONNECTED"})()

    balancer.register_agent(MockWS(), "tenant_1", "device_001")
    balancer.register_agent(MockWS(), "tenant_1", "device_002")

    online = balancer.get_online_agents("tenant_1")
    assert set(online) == {"device_001", "device_002"}

    # Test round robin picking
    p1 = balancer.pick_agent("tenant_1", strategy="round_robin")
    p2 = balancer.pick_agent("tenant_1", strategy="round_robin")
    p3 = balancer.pick_agent("tenant_1", strategy="round_robin")

    assert p1 == "device_001"
    assert p2 == "device_002"
    assert p3 == "device_001"

    print("PASS: test_websocket_agent_balancer")


def test_server_and_optimizer_import():
    from engine.llm_optimizer import gemini_balancer, optimize_search_query
    assert gemini_balancer is not None
    assert len(gemini_balancer.models) == len(DEFAULT_GEMINI_MODELS)
    assert gemini_balancer.strategy.value == "least_busy"

    from web.chat_router import router as chat_router
    assert chat_router is not None
    chat_routes = [r.path for r in chat_router.routes]
    assert any("agents/status" in r for r in chat_routes)
    assert any("pick-agent" in r for r in chat_routes)

    # Test server.py
    from web.server import app
    assert app is not None
    routes = [getattr(r, "path", None) or getattr(r, "path_format", "") for r in app.routes]
    assert any("/api/health" in str(r) for r in routes)
    print("PASS: web.server loaded successfully with /api/health route")

    print("PASS: test_server_and_optimizer_import")


if __name__ == "__main__":
    test_least_busy_selection()
    test_round_robin_selection()
    test_rate_limit_circuit_breaker()
    test_websocket_agent_balancer()
    test_server_and_optimizer_import()
    print("\nAll 5 load balancer test suites passed successfully!")
