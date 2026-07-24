"""
extract.py — turn a screenshot of an attendance table into JSON.

This file is BOTH:
  1. A reusable function `extract_attendance(image_bytes, mime_type)` that
     main.py imports for the web app, and
  2. A standalone CLI so you can validate extraction quality BEFORE any UI
     exists:   python extract.py path/to/screenshot.png

It sends the image to a Groq vision model and asks for strict JSON. We use
temperature 0 (deterministic) and JSON mode so the model can't wander off into
prose. The model only READS numbers off the image — all the risky maths lives
in budget.py, never here.
"""

import base64
import json
import os
import sys

from dotenv import load_dotenv
from groq import Groq

load_dotenv()  # pull GROQ_API_KEY / GROQ_MODEL out of .env

# Groq's current vision + JSON-mode model. The old Llama 4 vision models
# (maverick/scout) were deprecated in 2026; qwen3.6-27b is Groq's migration
# target. Override with GROQ_MODEL if Groq rotates models again — see
# https://console.groq.com/docs/models for the live list.
DEFAULT_MODEL = "qwen/qwen3.6-27b"

# The extraction contract. Kept verbose on purpose: portal tables vary, and a
# vague prompt is where extraction quality goes to die.
SYSTEM_PROMPT = """\
You are a precise OCR/data-extraction tool for a college "Self Attendance \
Report" table. Read the table in the image and return its rows as JSON.

Return EXACTLY this shape and nothing else:
{
  "rows": [
    {"subject": "<subject name>", "type": "TH" | "PR",
     "present": <integer>, "total": <integer>,
     "percentage": <number or null>}
  ]
}

Rules:
- One object per TABLE ROW. A subject often has two rows: TH (Theory) and PR \
(Practical). Emit each as its own object, repeating the subject name.
- "present" = the "Present" column (periods attended).
- "total"   = the "Total Period" column (periods held).
- "type"    = "TH" for theory rows, "PR" for practical/lab rows. If a row has \
an explicit TH/PR label use it; otherwise infer from the subject; if truly \
unknown use "TH".
- "percentage" = the value shown in the Percentage column, as a number \
(e.g. 84.6). If no percentage is shown, use null. Do NOT calculate it \
yourself — only read what is printed.
- Read digits carefully; do not guess. If a cell is unreadable, use null.
- IGNORE summary/total/overall rows (e.g. "Grand Total", "Overall"). Only \
emit real subject rows.
- Output valid JSON only. No explanation, no markdown fences.\
"""


def extract_attendance(image_bytes: bytes, mime_type: str = "image/png") -> dict:
    """Send image bytes to the vision model and return the parsed rows dict.

    Raises RuntimeError with a helpful message if the key is missing.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    client = Groq(api_key=api_key)

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64}"

    completion = client.chat.completions.create(
        model=model,
        temperature=0,  # deterministic; we want the same read every time
        response_format={"type": "json_object"},  # force valid JSON
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text",
                     "text": "Extract the attendance table from this screenshot."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )

    raw = completion.choices[0].message.content
    data = json.loads(raw)

    # Normalise: always return {"rows": [...]}, tolerate a bare list.
    rows = data.get("rows", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        rows = []
    return {"rows": rows}


def _guess_mime(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    return "image/png"


if __name__ == "__main__":
    # Standalone validation: python extract.py screenshot.png
    if len(sys.argv) != 2:
        print("Usage: python extract.py <path-to-screenshot>")
        raise SystemExit(2)

    path = sys.argv[1]
    with open(path, "rb") as f:
        image_bytes = f.read()

    print(f"Model : {os.environ.get('GROQ_MODEL', DEFAULT_MODEL)}")
    print(f"Image : {path} ({len(image_bytes)} bytes)\n")

    result = extract_attendance(image_bytes, _guess_mime(path))

    print("Extracted JSON:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n{len(result['rows'])} row(s) extracted.")
