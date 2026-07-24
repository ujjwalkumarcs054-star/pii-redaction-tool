#!/usr/bin/env python3
"""
eval.py
-------
Measures precision / recall / F1 / accuracy of the redaction engine against
a hand-labeled ground truth file (test_data/ground_truth.py).

Methodology
-----------
1. Locate each ground-truth (category, text) occurrence in the source file
   to get its exact character span (repeats are matched left-to-right).
2. Run the detector pipeline (engine.detect_all) over the same source file.
3. A ground-truth span counts as a TRUE POSITIVE (recall hit) if some
   detected span of the SAME category overlaps it by at least one
   character. Otherwise it's a FALSE NEGATIVE (missed PII).
4. A detected span counts as a TRUE POSITIVE (precision hit) if it overlaps
   a ground-truth span of the same category. A detected span that overlaps
   NOTHING in ground truth -- or overlaps one of the explicit
   NEGATIVE_EXAMPLES -- is a FALSE POSITIVE (over-redaction).
5. NEGATIVE_EXAMPLES that are correctly left untouched count as TRUE
   NEGATIVES, giving us a bounded set over which to report "accuracy"
   (PII redaction has no natural universe of negatives otherwise).

Run: python3 eval.py
"""
import sys
sys.path.insert(0, "test_data")
from ground_truth import GROUND_TRUTH, NEGATIVE_EXAMPLES
from engine import detect_all

SOURCE_FILE = "test_data/synthetic_ticket_log.txt"


def locate_occurrences(text, items):
    """For a list of (category, substring), find each occurrence's
    (start, end) span, left-to-right, handling repeats correctly."""
    cursor_by_key = {}
    spans = []
    for category, substr in items:
        start_from = cursor_by_key.get((category, substr), 0)
        idx = text.find(substr, start_from)
        if idx == -1:
            spans.append((category, substr, None, None))
        else:
            spans.append((category, substr, idx, idx + len(substr)))
            cursor_by_key[(category, substr)] = idx + 1
    return spans


def overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and a_end > b_start


def main():
    with open(SOURCE_FILE, encoding="utf-8") as f:
        text = f.read()

    gold = locate_occurrences(text, GROUND_TRUTH)
    unresolved = [g for g in gold if g[2] is None]
    if unresolved:
        print("WARNING: could not locate these ground-truth strings in the "
              "source file (fix ground_truth.py):")
        for g in unresolved:
            print("  ", g)

    predicted = detect_all(text)

    # ---- Recall: did we catch each gold span? ----
    per_cat_recall = {}
    fn_examples = []
    for category, substr, start, end in gold:
        if start is None:
            continue
        hit = any(p.category == category and overlaps(start, end, p.start, p.end)
                  for p in predicted)
        d = per_cat_recall.setdefault(category, {"tp": 0, "fn": 0})
        if hit:
            d["tp"] += 1
        else:
            d["fn"] += 1
            fn_examples.append((category, substr))

    # ---- Precision: was each detected span actually gold (of same cat)? ----
    gold_spans_resolved = [(c, s, e) for c, _, s, e in gold if s is not None]
    per_cat_precision = {}
    fp_examples = []
    for p in predicted:
        is_true = any(c == p.category and overlaps(p.start, p.end, s, e)
                      for c, s, e in gold_spans_resolved)
        d = per_cat_precision.setdefault(p.category, {"tp": 0, "fp": 0})
        if is_true:
            d["tp"] += 1
        else:
            d["fp"] += 1
            fp_examples.append((p.category, p.text))

    # ---- Negative examples: did we correctly leave them alone? ----
    tn = 0
    fp_on_negatives = []
    for neg in NEGATIVE_EXAMPLES:
        idx = text.find(neg)
        if idx == -1:
            continue
        end = idx + len(neg)
        flagged = any(overlaps(idx, end, p.start, p.end) for p in predicted)
        if flagged:
            fp_on_negatives.append(neg)
        else:
            tn += 1

    # ---- Aggregate ----
    categories = sorted(set(per_cat_recall) | set(per_cat_precision))
    print(f"{'Category':15s} {'TP':>4s} {'FN':>4s} {'FP':>4s} {'Precision':>10s} {'Recall':>8s} {'F1':>6s}")
    total_tp = total_fn = total_fp = 0
    for cat in categories:
        r = per_cat_recall.get(cat, {"tp": 0, "fn": 0})
        p = per_cat_precision.get(cat, {"tp": 0, "fp": 0})
        tp = r["tp"]
        fn = r["fn"]
        fp = p["fp"]
        total_tp += tp
        total_fn += fn
        total_fp += fp
        prec = tp / (tp + fp) if (tp + fp) else float("nan")
        rec = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) and prec == prec and rec == rec and (prec + rec) > 0 else float("nan")
        print(f"{cat:15s} {tp:4d} {fn:4d} {fp:4d} {prec:10.2%} {rec:8.2%} {f1:6.2f}")

    overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else float("nan")
    overall_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else float("nan")
    overall_f1 = 2 * overall_prec * overall_rec / (overall_prec + overall_rec)
    accuracy = (total_tp + tn) / (total_tp + tn + total_fp + total_fn)

    print("-" * 70)
    print(f"{'OVERALL':15s} {total_tp:4d} {total_fn:4d} {total_fp:4d} {overall_prec:10.2%} {overall_rec:8.2%} {overall_f1:6.2f}")
    print(f"\nTrue negatives (correctly-ignored non-PII lookalikes): {tn}/{len(NEGATIVE_EXAMPLES)}")
    print(f"Accuracy (TP+TN)/(TP+TN+FP+FN) over gold+negative set: {accuracy:.2%}")

    if fn_examples:
        print("\nMissed (false negatives):")
        for c, s in fn_examples:
            print(f"  [{c}] {s!r}")
    if fp_examples:
        print("\nOver-redacted (false positives):")
        for c, s in fp_examples:
            print(f"  [{c}] {s!r}")
    if fp_on_negatives:
        print("\nNegative examples incorrectly flagged:")
        for s in fp_on_negatives:
            print(f"  {s!r}")


if __name__ == "__main__":
    main()
