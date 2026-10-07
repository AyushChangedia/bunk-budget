"""
What a deploy breaks, which the rest of the suite cannot see.

test_app.py exercises the maths and the endpoints with the repository root as
the working directory and whatever is in the environment. A serverless host
gives neither, and both of those failures look the same from a browser: a 500
with nothing in it.
"""

import importlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent


@pytest.fixture
def keyless(monkeypatch):
    """The app as it is imported on a host where GROQ_API_KEY was never set."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    # load_dotenv() at import would otherwise put a developer's own key back.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)

    import main as main_module

    module = importlib.reload(main_module)
    yield module
    importlib.reload(main_module)


# ------------------------------------------------------- a missing API key --

def test_the_app_imports_without_a_key(keyless):
    """
    On a serverless host the import is the request, so anything that raises
    while a module loads takes down every route — including the page and the
    health probe, neither of which needs a key — and the browser is told only
    that a function failed.
    """
    assert keyless.app is not None


def test_the_page_loads_without_a_key(keyless):
    response = TestClient(keyless.app).get("/")
    assert response.status_code == 200
    assert "<!DOCTYPE html>" in response.text


def test_health_reports_the_missing_key_rather_than_failing(keyless):
    body = TestClient(keyless.app).get("/api/health").json()
    assert body["ok"] is True
    assert body["groq_key_set"] is False


def test_analyzing_without_a_key_is_503_and_names_it(keyless):
    # 503, not 500: the deploy is fine and the code is fine. It is one
    # environment variable short, which is an operator's problem.
    response = TestClient(keyless.app).post(
        "/api/analyze", files={"file": ("shot.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    )
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


# ---------------------------------------------------- the page, from anywhere --

def test_index_is_found_from_an_unrelated_working_directory(tmp_path):
    """
    A bare filename in FileResponse resolves against the working directory,
    which is the repository root locally and is not on a host. main.py already
    builds the path from __file__; this is what keeps it that way.
    """
    script = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from fastapi.testclient import TestClient\n"
        "import main\n"
        "r = TestClient(main.app).get('/')\n"
        "print(json.dumps({'status': r.status_code, 'html': '<!DOCTYPE html>' in r.text}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == 200
    assert payload["html"] is True


def test_the_index_path_is_absolute():
    import main

    assert main.INDEX_HTML.is_absolute()
    assert main.INDEX_HTML.is_file()


# --------------------------------------------------------- the entry point --

def test_main_exports_an_asgi_app_at_the_repository_root():
    # Vercel's FastAPI preset looks for the ASGI application here. A handler
    # under api/ is not needed, and a rewrite pointing at one is actively
    # wrong: it sends every request to the literal path "/api/index", which
    # is not a route, so the app answers its own 404 for the whole site.
    import main

    assert callable(main.app)
    assert (ROOT / "main.py").is_file()


def test_vercel_json_does_not_rewrite_the_path_away():
    config = json.loads((ROOT / "vercel.json").read_text())
    assert "rewrites" not in config, config.get("rewrites")


def test_the_function_has_room_to_read_a_screenshot():
    # The analyze route waits on a vision model. A function cut off at the
    # default limit turns a slow read into a platform error with nothing in it.
    config = json.loads((ROOT / "vercel.json").read_text())
    function = config["functions"]["main.py"]
    assert function["maxDuration"] >= 60
    assert function["memory"] >= 1024


def test_the_bundle_leaves_out_what_it_does_not_run():
    ignored = {
        line.strip()
        for line in (ROOT / ".vercelignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "test_app.py" in ignored
    assert "Dockerfile" in ignored


def test_the_api_routes_are_not_shadowed_by_the_page():
    # A catch-all StaticFiles mount at "/" answers every path with its own
    # bare 404, which showed up in production as uploads failing while the
    # page loaded fine. The explicit route must stay explicit.
    import main

    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    assert "/api/health" in paths
    assert "/api/analyze" in paths
    assert "/" in paths


def test_vercel_json_does_not_mix_builds_and_functions():
    # Vercel refuses the deployment outright: "The `functions` property cannot
    # be used in conjunction with the `builds` property." `builds` is also
    # redundant — the runtime detects api/*.py on its own — and setting it
    # switches off every other zero-config default along with it.
    config = json.loads((ROOT / "vercel.json").read_text())
    assert "builds" not in config
    assert "functions" in config
