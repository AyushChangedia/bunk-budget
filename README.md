# 🎯 Bunk Budget

Upload a screenshot of your college **Self Attendance Report** and find out, per
subject, how many classes you can skip and still clear the mandatory **80%** —
or how many you need to attend in a row to claw your way back.

The problem it fixes: the portal shows raw `Present / Total` numbers and buries
the subjects that actually need attention. Bunk Budget reads the screenshot,
does the maths for every row, and floats the danger subjects to the top.

## How it works

```
screenshot ──▶ extract.py ──▶ rows {subject, type, present, total}
                                    │
                                    ▼
                               budget.py ──▶ verdict per row
                                    │          (safe / tight / below, colour, advice)
                                    ▼
                                main.py  ──▶ sorted worst-first ──▶ JSON ──▶ browser
```

- **`extract.py`** sends the image to a Groq vision model with a strict JSON
  schema (temperature 0, JSON mode). It only *reads* numbers off the image — it
  never calculates percentages.
- **`budget.py`** is the single source of truth for the maths. It uses exact
  integer arithmetic so a student sitting on exactly 80% is never told they are
  below the line. Run `python budget.py` to see the worked examples pass.
- **`main.py`** is a small FastAPI app that wires the two together and serves
  the frontend.
- **`static/index.html`** is a self-contained frontend (drag-drop, click, or
  paste a screenshot). It renders the results but never re-implements the maths.

## The 80% rule (why integer maths)

For a row with `present = p`, `total = t`:

| Question | Exact integer form |
|---|---|
| At/above 80%? | `5·p ≥ 4·t` |
| Skips still allowed | `(5·p) // 4 − t` |
| Attend-in-a-row to recover | `4·t − 5·p` |

Floats lie here: `floor(4 / 0.8) == 4` in Python (not 5), which would wrongly
flag an on-the-line student as failing. The integer forms are exact.

## For students

Just open the link you were given and upload (or paste) a screenshot of your
Self Attendance Report. That's it — no install, no terminal, no API key.

## Put it online (owner does this once)

Students shouldn't run anything. You deploy the app once to a host, set your
Groq key there, and share the URL. The key stays on the server and is never
exposed to the browser. One deploy serves both the API and the frontend.

**Render (free, recommended)**

1. Push this repo to GitHub.
2. [render.com](https://render.com) → **New → Blueprint** → pick this repo
   (it reads `render.yaml`).
3. When prompted, paste your `GROQ_API_KEY` (free from
   <https://console.groq.com>).
4. Deploy → share the `https://<name>.onrender.com` URL.

The free tier sleeps after ~15 min idle, so the first open can take ~30s.

**Anywhere else (Docker)**

A `Dockerfile` is included, so it runs on Railway, Fly.io, Hugging Face
Spaces, Cloud Run, or your own VPS:

```bash
docker build -t bunk-budget .
docker run -p 8000:8000 -e GROQ_API_KEY=your_key bunk-budget
```

Whatever host you pick, set **`GROQ_API_KEY`** in its environment/secrets — do
not commit it.

## Run it locally (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then paste your real GROQ_API_KEY
uvicorn main:app --reload     # open http://127.0.0.1:8000
```

The optional `GROQ_MODEL` env var overrides the default vision model.

## Validate without the UI

```bash
python extract.py path/to/screenshot.png   # print the extracted JSON
python budget.py                            # run the maths self-test
python test_app.py                          # offline end-to-end API test
```

`test_app.py` stubs the Groq call, so it exercises the whole upload → extract →
compute → sort pipeline with no network and no key.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/`             | The web UI |
| `GET`  | `/api/health`   | Readiness + whether a key is configured |
| `POST` | `/api/analyze`  | `multipart/form-data` with `file=<image>` → verdicts JSON |

`POST /api/analyze` response shape:

```json
{
  "rows": [
    {"subject": "Lab on Python", "type": "PR", "present": 4, "total": 8,
     "percentage": 50.0, "status": "below", "color": "red",
     "skips_allowed": null, "recover_needed": 12,
     "verdict": "Attend 12 classes in a row to recover"}
  ],
  "overall": {"present": 43, "total": 47, "percentage": 91.5, "subjects": 9},
  "count": 9
}
```

## Note

Attendance is checked per subject *and* per type (theory / practical). The
advice assumes future classes are actually held — it's guidance, not a
guarantee. Always confirm against the official portal.
