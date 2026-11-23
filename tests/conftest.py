import os
import sys
from pathlib import Path

os.environ["PRIVACYTWIN_LLM_DISABLE"] = "1"  # tests never call an external LLM
os.environ.setdefault("PRIVACYTWIN_WARM_EVAL", "0")

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from privacytwin.api import create_app  # noqa: E402

ORIGIN = "http://localhost:3000"


class Client:
    """Test client bound to one browser workspace, with CSRF handled like the frontend."""

    def __init__(self, app, key: str, origin: str = ORIGIN):
        self.c = TestClient(app)
        self.h = {"X-Workspace-Key": key, "Origin": origin, "X-Actor": "tester"}
        self.h["X-CSRF-Token"] = self.c.get("/api/session", headers=self.h).json()["csrf"]

    def get(self, url, **kw):
        return self.c.get(url, headers=self.h, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self.h, **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self.h, **kw)

    def scan_csv(self, name: str, data: bytes, **form):
        r = self.post("/api/scan", files={"file": (name, data, "text/csv")},
                      data={"sample_size": "1000", "strategy": "head", **form})
        assert r.status_code == 200, r.text
        import json
        events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
        return events


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "pt.sqlite3"))


@pytest.fixture
def client(app):
    return Client(app, "a" * 40)


@pytest.fixture(scope="session")
def demo_app(tmp_path_factory):
    app = create_app(str(tmp_path_factory.mktemp("demo") / "pt.sqlite3"))
    c = Client(app, "d" * 40)
    assert c.post("/api/demo", json={}).status_code == 200
    return app


@pytest.fixture
def demo(demo_app):
    return Client(demo_app, "d" * 40)
