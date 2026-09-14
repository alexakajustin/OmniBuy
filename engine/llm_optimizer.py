"""LLM Query Optimizer using Gemini (primary) and DeepSeek (fallback)."""

import os
import json
import logging
import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

def optimize_search_query(user_query: str) -> str:
    """
    Uses LLMs to extract the optimal search term (e.g. MPN or short SKU) from a verbose user query.
    Falls back to DeepSeek if Gemini fails. Returns original query if all fail.
    """
    optimized = _call_gemini(user_query)
    if optimized:
        return optimized
        
    logger.warning("Gemini failed or not configured. Falling back to DeepSeek.")
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


def _call_gemini(user_query: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": _build_prompt(user_query)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        
    return None


def _call_deepseek(user_query: str) -> str | None:
    if not DEEPSEEK_API_KEY:
        return None
        
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a specialized search term optimizer."},
            {"role": "user", "content": _build_prompt(user_query)}
        ],
        "temperature": 0.1,
        "max_tokens": 20
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}")
        
    return None
