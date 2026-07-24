"""
app.py — Web demo for the PII redaction tool.

Lets a visitor paste text or upload a .txt file, runs the same
detectors.py / engine.py pipeline used by the CLI, and shows:
  - the redacted text
  - a per-category count of what was found and replaced

Note: nothing typed here is stored — each request is processed in
memory and discarded once the response is sent.
"""
from __future__ import annotations
from collections import Counter

from flask import Flask, render_template, request

from engine import detect_all, redact

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB upload cap

SAMPLE_TEXT = """Ticket #4471 - Rashi Patil (rashi.patil@gmail.com, +91 9876543210)
reported a login issue at Acme Corp. Escalated to Rohan Dey
(rohan.dey@gmail.com). Server log shows IP 192.168.1.42. DOB on file:
14 March 1990. Mailing address: 12 Oak Avenue, Rivertown 560034."""


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", sample_text=SAMPLE_TEXT)


MAX_DEMO_CHARS = 20_000  # keeps processing time reasonable on free-tier compute


@app.route("/redact", methods=["POST"])
def do_redact():
    text = request.form.get("text", "").strip()

    upload = request.files.get("file")
    if upload and upload.filename:
        text = upload.read().decode("utf-8", errors="replace")

    if not text:
        return render_template("index.html", sample_text=SAMPLE_TEXT,
                                error="Please paste some text or upload a .txt file.")

    if len(text) > MAX_DEMO_CHARS:
        return render_template(
            "index.html", sample_text=SAMPLE_TEXT,
            error=(f"This live demo is capped at {MAX_DEMO_CHARS:,} characters "
                   f"(yours was {len(text):,}) to keep processing fast on free-tier "
                   f"hosting. For full documents, run the CLI tool locally: "
                   f"python3 redact.py input.txt output.txt — see the GitHub repo."))

    spans = detect_all(text)
    counts = Counter(s.category for s in spans)
    redacted_text, spans_used, _ = redact(text, spans=spans)

    category_rows = sorted(counts.items(), key=lambda kv: -kv[1])
    total = sum(counts.values())

    return render_template(
        "result.html",
        redacted_text=redacted_text,
        category_rows=category_rows,
        total=total,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)