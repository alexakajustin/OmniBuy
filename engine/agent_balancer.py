"""Agent and Model Load Balancer.

Provides intelligent load balancing across:
1. LLM Model Fleets (Gemini, DeepSeek, etc.) with rate-limit circuit breaking,
   least-busy dispatching, and automated failover.
2. WebSocket Connected Device Agents for multi-tenant and multi-device routing.
"""

import time
import random
import asyncio
import logging
import threading
from enum import Enum
from typing import List, Dict, Optional
from dataclasses import dataclass
from contextlib import asynccontextmanager, contextmanager

logger = logging.getLogger("OmniBuy.AgentBalancer")


class BalancingStrategy(str, Enum):
    """Supported load balancing strategies."""
    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"
    PRIORITY_FALLBACK = "priority_fallback"
    RANDOM = "random"


# Standard fleet of Gemini models
DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-2-flash",
    "gemini-2-flash-lite",
    "gemini-3.1-pro",
    "gemini-2.5-pro",
]


@dataclass
class ModelHealth:
    """Tracks runtime metrics and circuit-breaker status for an agent model."""
    name: str
    active_requests: int = 0
    total_requests: int = 0
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    last_used: float = 0.0

    @property
    def is_available(self) -> bool:
        """Returns True if the model is not currently in cooldown."""
        return time.time() >= self.cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        """Returns remaining cooldown time in seconds, or 0.0 if healthy."""
        return max(0.0, self.cooldown_until - time.time())


class AgentModelLoadBalancer:
    """Thread-safe and async-safe load balancer for AI Agent Models."""

    def __init__(
        self,
        models: Optional[List[str]] = None,
        strategy: BalancingStrategy = BalancingStrategy.LEAST_BUSY,
        cooldown_seconds: float = 60.0,
    ):
        self.models = list(models) if models else list(DEFAULT_GEMINI_MODELS)
        self.strategy = strategy
        self.cooldown_seconds = cooldown_seconds
        self._stats: Dict[str, ModelHealth] = {m: ModelHealth(name=m) for m in self.models}
        self._sync_lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None
        self._rr_index = 0

    def _get_async_lock(self) -> asyncio.Lock:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def get_healthy_models(self) -> List[str]:
        """Return list of models that are currently not in cooldown."""
        now = time.time()
        return [m for m in self.models if self._stats[m].cooldown_until <= now]

    def pick_model_sync(self) -> str:
        """Select the best available model synchronously."""
        with self._sync_lock:
            healthy = self.get_healthy_models()
            if not healthy:
                # If all models are cooling down, select the one nearest to recovery
                logger.warning("All agent models are currently in cooldown! Picking nearest to expiry.")
                chosen = min(self.models, key=lambda m: self._stats[m].cooldown_until)
            else:
                if self.strategy == BalancingStrategy.ROUND_ROBIN:
                    chosen = healthy[self._rr_index % len(healthy)]
                    self._rr_index = (self._rr_index + 1) % len(healthy)

                elif self.strategy == BalancingStrategy.LEAST_BUSY:
                    # Pick model with lowest in-flight active requests, then least recently used
                    chosen = min(
                        healthy,
                        key=lambda m: (self._stats[m].active_requests, self._stats[m].last_used)
                    )

                elif self.strategy == BalancingStrategy.PRIORITY_FALLBACK:
                    chosen = healthy[0]

                elif self.strategy == BalancingStrategy.RANDOM:
                    chosen = random.choice(healthy)

                else:
                    chosen = healthy[0]

            stat = self._stats[chosen]
            stat.active_requests += 1
            stat.total_requests += 1
            stat.last_used = time.time()
            return chosen

    async def pick_model(self) -> str:
        """Select the best available model asynchronously."""
        async with self._get_async_lock():
            return self.pick_model_sync()

    def release_model_sync(
        self,
        model: str,
        success: bool = True,
        is_rate_limited: bool = False,
    ):
        """Update metrics and release active request counter synchronously."""
        with self._sync_lock:
            if model not in self._stats:
                return

            stat = self._stats[model]
            stat.active_requests = max(0, stat.active_requests - 1)

            if success:
                stat.consecutive_failures = 0
            else:
                stat.consecutive_failures += 1
                if is_rate_limited or stat.consecutive_failures >= 3:
                    # Exponential backoff on rate limits: 1x, 2x, up to 5x cooldown
                    multiplier = min(5, stat.consecutive_failures)
                    penalty = self.cooldown_seconds * multiplier
                    stat.cooldown_until = time.time() + penalty
                    logger.warning(
                        "Agent model '%s' rate-limited/failed (%d errors). Cooldown set to %.1fs",
                        model, stat.consecutive_failures, penalty,
                    )

    async def release_model(
        self,
        model: str,
        success: bool = True,
        is_rate_limited: bool = False,
    ):
        """Update metrics and release active request counter asynchronously."""
        async with self._get_async_lock():
            self.release_model_sync(model, success=success, is_rate_limited=is_rate_limited)

    @asynccontextmanager
    async def acquire(self):
        """Async context manager that automatically picks and releases a model."""
        model = await self.pick_model()
        success = False
        rate_limited = False
        try:
            yield model
            success = True
        except Exception as exc:
            err_msg = str(exc).lower()
            if any(term in err_msg for term in ["429", "quota", "resource_exhausted", "too many requests"]):
                rate_limited = True
            raise
        finally:
            await self.release_model(model, success=success, is_rate_limited=rate_limited)

    @contextmanager
    def acquire_sync(self):
        """Synchronous context manager that automatically picks and releases a model."""
        model = self.pick_model_sync()
        success = False
        rate_limited = False
        try:
            yield model
            success = True
        except Exception as exc:
            err_msg = str(exc).lower()
            if any(term in err_msg for term in ["429", "quota", "resource_exhausted", "too many requests"]):
                rate_limited = True
            raise
        finally:
            self.release_model_sync(model, success=success, is_rate_limited=rate_limited)

    def get_fallback_order_sync(self) -> List[str]:
        """Returns models ordered by availability and least load for failover loops."""
        with self._sync_lock:
            healthy = self.get_healthy_models()
            cooling = [m for m in self.models if m not in healthy]
            sorted_healthy = sorted(healthy, key=lambda m: self._stats[m].active_requests)
            return sorted_healthy + cooling

    async def get_fallback_order(self) -> List[str]:
        """Async version of get_fallback_order."""
        async with self._get_async_lock():
            return self.get_fallback_order_sync()

    def get_status(self) -> Dict[str, dict]:
        """Return real-time diagnostic stats for all models."""
        with self._sync_lock:
            return {
                name: {
                    "active_requests": stat.active_requests,
                    "total_requests": stat.total_requests,
                    "consecutive_failures": stat.consecutive_failures,
                    "available": stat.is_available,
                    "cooldown_remaining_sec": round(stat.cooldown_remaining, 1),
                }
                for name, stat in self._stats.items()
            }


class WebSocketAgentBalancer:
    """Load balancer for WebSocket connected client agents across tenants/devices."""

    def __init__(self):
        # Keys are f"{tenant_slug}_{device_uuid}" -> WebSocket
        self.agent_connections = {}
        self.admin_connections = {}
        self._tenant_rr: Dict[str, int] = {}
        self._lock = threading.Lock()

    def register_agent(self, websocket, tenant_slug: str, device_uuid: str):
        key = f"{tenant_slug}_{device_uuid}"
        with self._lock:
            self.agent_connections[key] = websocket

    def unregister_agent(self, tenant_slug: str, device_uuid: str):
        key = f"{tenant_slug}_{device_uuid}"
        with self._lock:
            if key in self.agent_connections:
                del self.agent_connections[key]

    def get_online_agents(self, tenant_slug: str) -> List[str]:
        """Get list of active device_uuids for a tenant."""
        prefix = f"{tenant_slug}_"
        with self._lock:
            active = []
            for key, ws in self.agent_connections.items():
                if key.startswith(prefix):
                    device_uuid = key[len(prefix):]
                    # If websocket is still connected
                    client_state = getattr(ws, "client_state", None)
                    state_name = getattr(client_state, "name", "")
                    if state_name != "DISCONNECTED":
                        active.append(device_uuid)
            return active

    def pick_agent(self, tenant_slug: str, strategy: str = "round_robin") -> Optional[str]:
        """Pick an online device agent for a tenant using round-robin."""
        available = self.get_online_agents(tenant_slug)
        if not available:
            return None

        with self._lock:
            if strategy == "round_robin":
                idx = self._tenant_rr.get(tenant_slug, 0)
                chosen = available[idx % len(available)]
                self._tenant_rr[tenant_slug] = (idx + 1) % len(available)
                return chosen

            return available[0]
