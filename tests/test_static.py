"""The built frontend is served from one folder with a client-side-routing fallback; nothing outside it is reachable."""
import os

from tests.conftest import make_client


def test_without_a_build_the_root_explains_how_to_build(client):
    r = client.get("/")
    assert r.status_code == 200 and "has not been built" in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_a_build_is_served_with_the_spa_fallback(settings, tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>Matter</title><div id=root></div>", encoding="utf-8")
    (static / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (static / "og.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "secret.txt").write_text("not served", encoding="utf-8")
    settings.static_dir = str(static)
    with make_client(settings) as c:
        assert "<title>Matter</title>" in c.get("/").text
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert "<title>Matter</title>" in c.get("/p/perov5-demo/goal").text        # client-side route
        js = c.get("/assets/app-abc123.js")
        assert js.status_code == 200 and "immutable" in js.headers["cache-control"]
        assert c.get("/og.png").content.startswith(b"\x89PNG")
        assert "<title>Matter</title>" in c.get("/../secret.txt").text              # falls back, never escapes
        assert "<title>Matter</title>" in c.get("/assets/../../secret.txt").text
        assert c.get("/api/missing").status_code == 404
