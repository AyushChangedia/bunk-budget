"""
test_app.py — end-to-end checks for the FastAPI layer, no network required.

We monkeypatch the Groq call (extract.extract_attendance) so we can exercise
the whole request pipeline — upload -> extract -> compute_budget -> sort ->
JSON — deterministically and offline. The maths itself is proven separately by
`python budget.py`; this file proves the wiring around it.

Run:  python test_app.py     (exit 0 = all passed)
"""

import io
import sys

from fastapi.testclient import TestClient

import main

# The rows the real screenshot should yield (subject/type/present/total).
FAKE_ROWS = {
    "rows": [
        {"subject": "Microcontrolller", "type": "TH", "present": 5, "total": 5},
        {"subject": "Microcontrolller", "type": "PR", "present": 6, "total": 6},
        {"subject": "OOP Using C++", "type": "TH", "present": 6, "total": 6},
        {"subject": "OOP Using C++", "type": "PR", "present": 4, "total": 4},
        {"subject": "Web Technologies", "type": "TH", "present": 4, "total": 4},
        {"subject": "Web Technologies", "type": "PR", "present": 6, "total": 6},
        {"subject": "Lab on Python", "type": "PR", "present": 4, "total": 8},
        {"subject": "Data Analytics", "type": "PR", "present": 2, "total": 2},
        {"subject": "Spiritual and Cultural Heritage : Indian Experience",
         "type": "TH", "present": 6, "total": 6},
    ]
}

client = TestClient(main.app)
_failures = []


def check(name, cond):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
    if not cond:
        _failures.append(name)


def _post_image(monkey_rows=FAKE_ROWS):
    # Patch the network-bound extractor with a canned reply.
    main.extract_attendance = lambda data, mime: monkey_rows
    files = {"file": ("shot.png", io.BytesIO(b"\x89PNG\r\n_fake_"), "image/png")}
    return client.post("/api/analyze", files=files)


def test_health():
    r = client.get("/api/health")
    check("health 200", r.status_code == 200)
    check("health reports ok", r.json().get("ok") is True)


def test_index_served():
    r = client.get("/")
    check("index served at /", r.status_code == 200)
    check("index looks like the app", "Bunk Budget" in r.text)


def test_analyze_happy_path():
    r = _post_image()
    check("analyze 200", r.status_code == 200)
    body = r.json()
    rows = body["rows"]
    check("all 9 rows returned", len(rows) == 9)

    # Worst-first: "Lab on Python" (50%) must be at the very top.
    check("worst subject sorted first",
          rows[0]["subject"] == "Lab on Python" and rows[0]["color"] == "red")
    check("worst verdict is a recovery message",
          "Attend" in rows[0]["verdict"])

    # Every row carries subject + type back out of the maths layer.
    check("subject/type re-attached",
          all(x.get("subject") and x.get("type") in ("TH", "PR") for x in rows))

    # Overall = 43 / 47 = 91.5% (rounded), across 9 subject-rows.
    ov = body["overall"]
    check("overall present/total", ov["present"] == 43 and ov["total"] == 47)
    check("overall percentage 91.5", ov["percentage"] == 91.5)
    check("overall subject count", ov["subjects"] == 9)


def test_null_cells_are_unknown():
    rows = {"rows": [{"subject": "Broken", "type": "TH",
                      "present": None, "total": None}]}
    r = _post_image(rows)
    check("null cells still 200", r.status_code == 200)
    body = r.json()
    check("null row is 'unknown'/grey",
          body["rows"][0]["status"] == "unknown"
          and body["rows"][0]["color"] == "grey")


def test_rejects_non_image():
    files = {"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    r = client.post("/api/analyze", files=files)
    check("non-image rejected (415)", r.status_code == 415)


def test_empty_extraction_422():
    r = _post_image({"rows": []})
    check("no rows -> 422", r.status_code == 422)


if __name__ == "__main__":
    for fn in [test_health, test_index_served, test_analyze_happy_path,
               test_null_cells_are_unknown, test_rejects_non_image,
               test_empty_extraction_422]:
        print(fn.__name__)
        fn()
    print("-" * 50)
    if _failures:
        print(f"SOME FAILED: {_failures}")
        sys.exit(1)
    print("ALL PASSED")
    sys.exit(0)
