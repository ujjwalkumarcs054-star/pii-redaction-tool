#!/usr/bin/env python3
"""
redact.py - CLI entry point.

Usage:
    python3 redact.py INPUT.txt OUTPUT.txt [--audit audit.json]

Reads a plain-text file, detects PII (see detectors.py), replaces every
instance with a consistent fake value (see engine.py), and writes the
redacted text out. Optionally writes an audit log (category + count only,
NOT the real values) so results can be reviewed without re-exposing PII.
"""
import argparse
import json
import sys
from collections import Counter
from engine import detect_all, redact


def main():
    ap = argparse.ArgumentParser(description="Redact PII from a text file.")
    ap.add_argument("input", help="Path to input .txt file")
    ap.add_argument("output", help="Path to write redacted .txt file")
    ap.add_argument("--audit", help="Optional path to write a JSON audit summary")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    print(f"Read {len(text):,} characters from {args.input}", file=sys.stderr)

    spans = detect_all(text)
    counts = Counter(s.category for s in spans)
    print("Detected PII by category:", file=sys.stderr)
    for cat, n in sorted(counts.items()):
        print(f"  {cat:15s} {n}", file=sys.stderr)

    redacted_text, spans_used, factory = redact(text, spans=spans)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(redacted_text)
    print(f"Wrote redacted text to {args.output}", file=sys.stderr)

    if args.audit:
        summary = {
            "total_spans_redacted": len(spans_used),
            "counts_by_category": dict(counts),
        }
        with open(args.audit, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Wrote audit summary to {args.audit}", file=sys.stderr)


if __name__ == "__main__":
    main()
