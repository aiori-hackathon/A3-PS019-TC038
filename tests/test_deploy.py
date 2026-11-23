"""Single-container deployment: static frontend served by the API on one origin."""
from fastapi.testclient import TestClient

from privacytwin.api import create_app


def _site(tmp_path, monkeypatch):
    web = tmp_path / "out"
    (web / "app" / "overview").mkdir(parents=True)
    (web / "index.html").write_text("<html>start</html>", encoding="utf-8")
    (web / "app" / "overview" / "index.html").write_text("<html>overview</html>", encoding="utf-8")
    monkeypatch.setenv("PRIVACYTWIN_STATIC_DIR", str(web))
    return TestClient(create_app(str(tmp_path / "pt.sqlite3")))


def test_static_frontend_and_api_share_one_origin(tmp_path, monkeypatch):
    c = _site(tmp_path, monkeypatch)
    page = c.get("/app/overview/")
    assert page.status_code == 200 and "overview" in page.text
    assert "connect-src 'self'" in page.headers["content-security-policy"]
    assert c.get("/").text == "<html>start</html>"
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.get("/api/health").headers["content-security-policy"].startswith("default-src 'none'")
    # same-origin writes: Origin equals the Host the page was served from
    h = {"X-Workspace-Key": "s" * 40, "Origin": "http://privacytwin.example", "Host": "privacytwin.example"}
    h["X-CSRF-Token"] = c.get("/api/session", headers=h).json()["csrf"]
    assert c.post("/api/demo", headers=h, json={}).status_code == 200
    assert c.get("/api/overview", headers={**h, "Origin": "https://evil.example"}).status_code == 403



def test_same_origin_browser_pattern(tmp_path, monkeypatch):
    """Browsers omit Origin on same-origin GETs but send it on POSTs; the token must still match."""
    c = _site(tmp_path, monkeypatch)
    base = {"X-Workspace-Key": "t" * 40, "Host": "privacytwin.example"}
    token = c.get("/api/session", headers=base).json()["csrf"]
    post = {**base, "Origin": "https://privacytwin.example", "X-CSRF-Token": token}
    assert c.post("/api/demo", headers=post, json={}).status_code == 200
    forged = {**base, "Origin": "https://evil.example", "X-CSRF-Token": token}
    assert c.post("/api/demo", headers=forged, json={}).status_code == 403
