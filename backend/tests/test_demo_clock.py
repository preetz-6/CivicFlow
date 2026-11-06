"""Demo clock pause / resume (reset early, keep the data fresh until the presentation)."""
from fastapi.testclient import TestClient

from app.core.clock import clock
from app.main import app


def test_pause_and_resume():
    saved = clock.dump()
    try:
        clock.load(saved | {"frozen": None})
        c = TestClient(app)
        p = c.post("/api/v1/demo/clock/pause").json()
        assert p["frozen"] is True
        assert c.get("/api/v1/clock").json()["now"] == p["now"]  # time stands still
        r = c.post("/api/v1/demo/clock/resume").json()
        assert r["frozen"] is False and r["now"] >= p["now"]
    finally:
        clock.load(saved)
