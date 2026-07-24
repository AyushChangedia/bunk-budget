"""
main.py — the Bunk Budget web app.

Ties the two already-tested pieces together behind a small FastAPI surface:

  extract.py   reads a screenshot  -> rows of {subject, type, present, total}
  budget.py    turns each row      -> a verdict (safe / tight / below, colour, …)

The browser POSTs a screenshot to /api/analyze; we extract the rows, compute a
verdict per row, sort them worst-first, and hand back JSON. The frontend is
plain static HTML/CSS/JS and never re-implements the maths — budget.py stays
the single source of truth for "how many can I skip?".
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from budget import compute_budget, sort_worst_first
from extract import DEFAULT_MODEL, extract_attendance

load_dotenv()  # so GROQ_API_KEY / GROQ_MODEL work in local dev too

MAX_BYTES = 12 * 1024 * 1024  # 12 MB — attendance screenshots are tiny
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Bunk Budget",
    description="Upload your attendance screenshot; find out how many classes "
                "you can skip and still clear 80%.",
    version="1.0.0",
)


def analyze_rows(rows):
    """Turn extracted rows into computed verdicts, sorted worst-first.

    Each extracted row is {subject, type, present, total, percentage}. We run
    the numbers through budget.compute_budget (the only place the maths lives)
    and re-attach the subject/type so the frontend can label each verdict.
    """
    results = []
    for r in rows or []:
        verdict = compute_budget(r.get("present"), r.get("total"))
        subject = (str(r.get("subject") or "")).strip() or "Unknown subject"
        rtype = (str(r.get("type") or "")).strip().upper()
        verdict["subject"] = subject
        verdict["type"] = rtype if rtype in ("TH", "PR") else None
        results.append(verdict)
    return sort_worst_first(results)


def overall_summary(results):
    """Aggregate percentage across all readable rows (informational only).

    Skip advice stays per-row because 80% is enforced per subject-type; this
    is just the headline number a student recognises from the portal.
    """
    valid = [r for r in results if r["status"] != "unknown"]
    present = sum(r["present"] for r in valid)
    total = sum(r["total"] for r in valid)
    pct = round(present / total * 100, 1) if total else 0.0
    return {"present": present, "total": total, "percentage": pct,
            "subjects": len(results)}


@app.get("/api/health")
def health():
    """Cheap readiness probe; also tells the UI whether a key is configured."""
    return {
        "ok": True,
        "groq_key_set": bool(os.environ.get("GROQ_API_KEY")),
        "model": os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
    }


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    """Extract the attendance table from an uploaded image and score it."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(415, "Please upload an image file (PNG or JPG).")

    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded file was empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is too large (max 12 MB).")

    try:
        extracted = extract_attendance(data, file.content_type or "image/png")
    except RuntimeError as exc:
        # Missing/invalid key or other configuration problem — surface it.
        raise HTTPException(503, str(exc))
    except Exception as exc:  # network / model / JSON errors
        raise HTTPException(502, f"Could not read the screenshot: {exc}")

    results = analyze_rows(extracted.get("rows", []))
    if not results:
        raise HTTPException(
            422,
            "No subject rows were found. Make sure the screenshot shows the "
            "full attendance table.",
        )

    return {
        "rows": results,
        "overall": overall_summary(results),
        "count": len(results),
    }


# Static frontend is served last so it doesn't shadow the /api routes above.
# html=True makes "/" return static/index.html automatically.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
