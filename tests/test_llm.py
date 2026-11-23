"""Groq/LLM layer: metadata-only payloads, graceful fallback, no verdict words."""
import io
import json

from privacytwin import llm


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_disabled_in_tests():
    assert llm.config() is None and llm.status()["enabled"] is False


def test_groq_payload_is_metadata_only(demo, monkeypatch):
    sent = []

    def fake_urlopen(req, timeout):
        sent.append((req.full_url, req.headers, json.loads(req.data)))
        return _Resp(json.dumps({"choices": [{"message": {"content": "Employees is the illegal hotspot (PT-00052)."}}]}).encode())

    monkeypatch.setenv("PRIVACYTWIN_LLM_DISABLE", "0")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    llm._cache.clear()
    a = demo.post("/api/assistant", json={"question": "What is the riskiest table?"}).json()
    assert a["mode"] == "llm" and "flagged" in a["answer"] and "illegal" not in a["answer"]
    s = demo.get("/api/ai/summary").json()
    assert s["mode"] == "llm" and s["narrative"]
    e = demo.post("/api/ai/explain", json={"pt_id": "PT-00004"}).json()
    assert e["mode"] == "llm"
    url, headers, body = sent[0]
    assert url == llm.GROQ_URL and headers["Authorization"] == "Bearer test-key"
    payload = json.dumps([b for _, _, b in sent])
    # masked examples and raw values never leave the server
    assert "XXXXXX" not in payload and "****@" not in payload and "masked_examples" not in payload


def test_fallback_when_llm_fails(demo, monkeypatch):
    def boom(req, timeout):
        raise llm.urllib.error.URLError("down")

    monkeypatch.setenv("PRIVACYTWIN_LLM_DISABLE", "0")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    llm._cache.clear()
    a = demo.post("/api/assistant", json={"question": "Which tables have Aadhaar with no retention?"}).json()
    assert a["mode"] == "offline" and "support_tickets" in a["answer"]


def test_rate_limit_retry(monkeypatch):
    import urllib.error
    calls = []

    def flaky(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "rate limited", {"retry-after": "0.01"}, None)
        return _Resp(json.dumps({"choices": [{"message": {"content": "ok after retry"}}]}).encode())

    monkeypatch.setenv("PRIVACYTWIN_LLM_DISABLE", "0")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm.chat("hello", cache=False) == "ok after retry" and len(calls) == 2

    calls.clear()

    def too_long(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 429, "rate limited", {"retry-after": "120"}, None)
    monkeypatch.setattr(llm.urllib.request, "urlopen", too_long)
    assert llm.chat("hello again", cache=False) is None and len(calls) == 1
