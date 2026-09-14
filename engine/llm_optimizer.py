"""LLM Query Optimizer using a Load-Balanced Gemini Fleet (primary) and DeepSeek (fallback)."""

import os
import json
import logging
import requests
from dotenv import load_dotenv

from engine.agent_balancer import AgentModelLoadBalancer, BalancingStrategy

logger = logging.getLogger(__name__)

# Load .env variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Global Load Balancer for Gemini models
gemini_balancer = AgentModelLoadBalancer(
    strategy=BalancingStrategy.LEAST_BUSY,
    cooldown_seconds=60.0,
)


def optimize_search_query(user_query: str) -> str:
    """
    Uses LLMs to extract the optimal search term (e.g. MPN or short SKU) from a verbose user query.
    Rotates and load-balances across Gemini models, falling back to DeepSeek if all Gemini models fail.
    Returns original query if all fail.
    """
    optimized = _call_gemini_balanced(user_query)
    if optimized:
        return optimized
        
    logger.warning("All Gemini models failed or not configured. Falling back to DeepSeek.")
    optimized = _call_deepseek(user_query)
    if optimized:
        return optimized
        
    logger.warning("Both Gemini and DeepSeek failed. Using raw query.")
    return user_query


def _build_prompt(user_query: str) -> str:
    return (
        "You are an expert e-commerce search optimizer for IT and networking equipment. "
        f"A user searched for: '{user_query}'. "
        "Extract or infer the absolute best, most concise keyword (usually the manufacturer part number / MPN, SKU, or exact model) "
        "that should be typed into a supplier's search bar to find this exact product. "
        "Respond ONLY with the optimized search term and absolutely nothing else. "
        "Do not use quotes. Do not explain."
    )


def _call_gemini_balanced(user_query: str) -> str | None:
    """Attempt Gemini optimization by rotating through healthy models in the load balancer."""
    if not GEMINI_API_KEY:
        return None

    # Get models ordered by health & least busy
    models_to_try = gemini_balancer.get_fallback_order_sync()

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": _build_prompt(user_query)}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
            },
        }

        try:
            logger.debug("Trying Gemini model: %s", model_name)
            response = requests.post(url, json=payload, timeout=15)
            
            # Rate limit check (HTTP 429)
            if response.status_code == 429:
                logger.warning("Model %s returned 429 Too Many Requests, cooling down...", model_name)
                gemini_balancer.release_model_sync(model_name, success=False, is_rate_limited=True)
                continue

            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    result = parts[0].get("text", "").strip()
                    # Mark successful execution
                    gemini_balancer.release_model_sync(model_name, success=True)
                    return result

            # Non-empty response but no candidates
            gemini_balancer.release_model_sync(model_name, success=True)

        except Exception as e:
            err_msg = str(e).lower()
            is_429 = "429" in err_msg or "quota" in err_msg or "resource_exhausted" in err_msg
            logger.warning("Gemini model %s failed: %s", model_name, e)
            gemini_balancer.release_model_sync(model_name, success=False, is_rate_limited=is_429)
            continue

    return None


def _call_deepseek(user_query: str) -> str | None:
    if not DEEPSEEK_API_KEY:
        return None
        
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a specialized search term optimizer."},
            {"role": "user", "content": _build_prompt(user_query)},
        ],
        "temperature": 0.1,
        "max_tokens": 20,
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error("DeepSeek API error: %s", e)
        
    return None
