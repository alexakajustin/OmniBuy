"""Tests for the AI query optimizer — mainly that hallucinated terms are rejected."""

import pytest

from engine import llm_optimizer as opt
from engine.agent_balancer import AgentModelLoadBalancer


@pytest.fixture(autouse=True)
def clear_cache():
    opt._cache.clear()
    yield
    opt._cache.clear()


def fake_providers(monkeypatch, gemini=None, deepseek=None):
    monkeypatch.setattr(opt, "_call_gemini", lambda q: gemini)
    monkeypatch.setattr(opt, "_call_deepseek", lambda q: deepseek)


# --- _validate_term ---------------------------------------------------------

@pytest.mark.parametrize("term, query", [
    ("DS-7108HGHI-K1", "DVR Hikvision DS-7108HGHI-K1 8 canale"),
    ("ds-7108hghi-k1", "DVR Hikvision DS-7108HGHI-K1 8 canale"),
    ("DS7108HGHI", "DVR Hikvision DS-7108HGHI-K1 8 canale"),  # separators dropped
    ("keystone cat6", "vreau un keystone cat6 utp pentru priza"),
    ("rola velcro", "rolă velcro neagră"),                      # diacritics ignored
])
def test_grounded_terms_are_accepted(term, query):
    assert opt._validate_term(term, query) is None


@pytest.mark.parametrize("term, query", [
    ("DS-7108HGHI-K1", "DVR Hikvision 8 canale"),        # invented part number
    ("Hikvision DS-7208", "DVR Hikvision 8 canale"),
    ("patch cord cat6", "cablu retea 2m"),               # translated / invented
    ("", "cablu retea"),
    ("x" * 200, "x" * 200),
])
def test_hallucinated_or_bad_terms_are_rejected(term, query):
    assert opt._validate_term(term, query) is not None


# --- _clean_term ------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ('{"search_term": "DS-7108HGHI-K1"}', "DS-7108HGHI-K1"),
    ('```json\n{"search_term": "keystone cat6"}\n```', "keystone cat6"),
    ('"keystone cat6"', "keystone cat6"),
    ("keystone cat6\nThis is the best term.", "keystone cat6"),
])
def test_clean_term(raw, expected):
    assert opt._clean_term(raw) == expected


# --- optimize_search_query --------------------------------------------------

def test_uses_grounded_gemini_answer(monkeypatch):
    fake_providers(monkeypatch, gemini='{"search_term": "DS-7108HGHI-K1"}')
    result = opt.optimize_search_query("DVR Hikvision DS-7108HGHI-K1 8 canale")
    assert result.term == "DS-7108HGHI-K1"
    assert result.source == "gemini"
    assert result.changed


def test_hallucination_falls_back_to_deepseek(monkeypatch):
    fake_providers(
        monkeypatch,
        gemini='{"search_term": "DS-7108HGHI-K1"}',   # not in query -> rejected
        deepseek='{"search_term": "DVR Hikvision"}',
    )
    result = opt.optimize_search_query("DVR Hikvision 8 canale")
    assert result.term == "DVR Hikvision"
    assert result.source == "deepseek"


def test_all_hallucinations_fall_back_to_original(monkeypatch):
    fake_providers(
        monkeypatch,
        gemini='{"search_term": "DS-7108HGHI-K1"}',
        deepseek='{"search_term": "DS-7104NI-Q1"}',
    )
    result = opt.optimize_search_query("DVR Hikvision 8 canale")
    assert result.term == "DVR Hikvision 8 canale"
    assert result.source == "original"
    assert not result.changed
    assert "respinsă" in result.note


def test_provider_outage_falls_back_and_is_not_cached(monkeypatch):
    fake_providers(monkeypatch)  # both return None
    result = opt.optimize_search_query("keystone cat6")
    assert result.source == "original"
    assert "keystone cat6" not in opt._cache


def test_successful_answer_is_cached(monkeypatch):
    calls = []

    def gemini(q):
        calls.append(q)
        return '{"search_term": "cat6"}'

    monkeypatch.setattr(opt, "_call_gemini", gemini)
    monkeypatch.setattr(opt, "_call_deepseek", lambda q: None)
    opt.optimize_search_query("keystone cat6")
    opt.optimize_search_query("keystone cat6")
    assert len(calls) == 1


def test_provider_errors_are_reported_in_note(monkeypatch):
    def broken(q):
        raise opt.ProviderError("HTTP 400 API key not valid")

    monkeypatch.setattr(opt, "_call_gemini", broken)
    monkeypatch.setattr(opt, "_call_deepseek", lambda q: None)
    result = opt.optimize_search_query("keystone cat6")
    assert result.source == "original"
    assert "gemini: HTTP 400 API key not valid" in result.note


def _gemini_reply(term):
    return {"candidates": [{"content": {"parts": [{"text": '{"search_term": "%s"}' % term}]}}]}


def test_gemini_falls_through_models_on_quota(monkeypatch):
    calls = []

    def post(url, payload, headers):
        calls.append(url)
        if "model-a" in url:
            raise opt.ProviderError("HTTP 429 quota", 429)
        return _gemini_reply("cat6")

    monkeypatch.setattr(opt, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(opt, "gemini_balancer", AgentModelLoadBalancer(models=["model-a", "model-b"]))
    monkeypatch.setattr(opt, "_post", post)
    assert opt._call_gemini("keystone cat6") == '{"search_term": "cat6"}'
    assert len(calls) == 2
    assert not opt.gemini_balancer._stats["model-a"].is_available  # cooled down after 429


def test_gemini_bad_key_does_not_try_other_models(monkeypatch):
    calls = []

    def post(url, payload, headers):
        calls.append(url)
        raise opt.ProviderError("HTTP 400 API key not valid", 400)

    monkeypatch.setattr(opt, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(opt, "gemini_balancer", AgentModelLoadBalancer(models=["model-a", "model-b"]))
    monkeypatch.setattr(opt, "_post", post)
    with pytest.raises(opt.ProviderError):
        opt._call_gemini("keystone cat6")
    assert len(calls) == 1
