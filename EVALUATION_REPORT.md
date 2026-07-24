# Evaluation Report

## 1. Synthetic ground-truth set (primary metric — exact numbers)

**Method:** `test_data/synthetic_ticket_log.txt` is a hand-written document
in the style of the assignment's own ticket-log example, covering all 8
required PII categories with repeats, plus deliberate non-PII lookalikes
(order numbers, tracking codes, generic non-birth dates, policy/committee
jargon). `test_data/ground_truth.py` hand-labels every instance. `eval.py`
locates each ground-truth span in the file, runs the detector pipeline, and
counts a detection as a match if it's the same category and its character
span overlaps the gold span.

**Result (run via `python3 eval.py`):**

| Category | TP | FN | FP | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| ADDRESS | 3 | 0 | 0 | 100% | 100% | 1.00 |
| COMPANY_NAME | 4 | 0 | 0 | 100% | 100% | 1.00 |
| CREDIT_CARD | 2 | 0 | 0 | 100% | 100% | 1.00 |
| DATE_OF_BIRTH | 3 | 0 | 0 | 100% | 100% | 1.00 |
| EMAIL | 5 | 0 | 0 | 100% | 100% | 1.00 |
| FULL_NAME | 6 | 0 | 0 | 100% | 100% | 1.00 |
| IP_ADDRESS | 3 | 0 | 0 | 100% | 100% | 1.00 |
| PHONE | 4 | 0 | 0 | 100% | 100% | 1.00 |
| SSN | 2 | 0 | 0 | 100% | 100% | 1.00 |
| **Overall** | **32** | **0** | **0** | **100%** | **100%** | **1.00** |

**True negatives:** 10/10 non-PII lookalikes (order numbers, tracking
codes, generic dates, policy/committee jargon) were correctly left
un-redacted.

**Accuracy** (TP+TN)/(TP+TN+FP+FN) over the combined gold+negative set:
**100%** (42/42).

This is a clean, small, fully-labeled set, so 100% reflects that the
detectors handle their target formats correctly and that the specific
precision guardrails (order-number exclusion, phone/SSN validity checks,
DOB context requirement) work as designed — not that the tool is perfect on
arbitrary real-world text (see Section 2).

Three real bugs were found and fixed via this eval loop during development:
1. A phone regex was matching the numeric tail of alphanumeric tracking
   codes (`TRK-99213456` → `99213456`).
2. The date-of-birth regex only matched "Month Day, Year"; it missed the
   "Day Month Year" format ("22 July 1985").
3. A jargon leak let "Ticket Priority" through as a company name.

## 2. Real-document stress test (KSH International Limited RHP)

**Why a separate section:** the attached file is a real ~350-page /
345,843-character SEBI IPO prospectus — a public regulatory filing, not a
short ticket log. Hand-labeling every PII instance across the whole
document isn't practical in the time available, so this section uses a
**sample-based manual audit** instead of exhaustive ground truth, and
reports what was found honestly, including the tool's real limitations.

**Detected counts (final run):**

| Category | Count | Unique values |
|---|---|---|
| EMAIL | 59 | 27 |
| PHONE | 32 | 20 |
| FULL_NAME | 196 | 75 |
| COMPANY_NAME | 497 | 218 |
| ADDRESS | 29 | 23 |
| SSN / CREDIT_CARD / IP_ADDRESS / DATE_OF_BIRTH | 0 | — (none present in a real public prospectus; confirmed by direct regex scan of the source text) |

### Regex-based categories — audited exhaustively (small unique-value counts)

| Category | Precision (unique) | Notes |
|---|---|---|
| EMAIL | 27/27 = 100% | All 27 unique matches are genuine corporate emails |
| PHONE | 20/20 = 100% (after fix) | Initial run had 20 false positives — Director Identification Numbers and fiscal-year ranges (e.g. "2023-2024") sitting in the same table columns as phone numbers were being caught by the format-only regex; fixed by adding a phone-context-keyword requirement for any candidate without an unambiguous `+countrycode` or `STD-code-number` shape |
| ADDRESS | 23/23 = 100% | All 23 unique matches are genuine mailing addresses (registered office, bank branches, RTA, auditor, escrow bank, etc.) |

Recall for these categories could not be measured against exhaustive gold
labels (no full 350-page hand-annotation was done), but spot checks of
known address/email/phone blocks in the document (registered office,
corporate office, statutory auditor, bankers to the offer) found no misses.

### NER-based categories — audited via manual sample review

**FULL_NAME — reviewed all 75 unique detections:**
- 34 true positives (real people: promoters, KMPs, directors, e.g. "Kushal
  Subbayya Hegde", "Rajesh Kushal Hegde", "Ashish Mathew Pulloor")
- 41 false positives — mostly (a) address/branch-name fragments picked up
  as PERSON ("Baner Pune", "Kubera Chambers Opp"), (b) financial/legal
  jargon that survived the shape filter ("PAT CAGR", "Mutual Funds",
  "Wilful Defaulter"), and (c) a company name mis-tagged as PERSON instead
  of COMPANY_NAME ("Kushal Electricals", "Waterloo Industrial Park")
- **Precision (unique-value basis): 34/75 ≈ 45%**

**COMPANY_NAME — reviewed a random sample of 50 of 218 unique detections
(seed=7 for reproducibility):**
- 17 true positives (real companies/entities: "KSH International Limited",
  "HDFC Bank Limited", "CARE Ratings Limited", "Bhandary Metal Extrusion
  Private Limited", family trusts, etc.)
- 33 false positives — mostly generic financial/legal jargon phrases
  ("Corporate Office", "Net Working Capital Days", "Group Companies"),
  truncated fragments from table-cell boundary errors ("Park IV Private
  Limited" — missing its preceding words), and a few person names
  mis-tagged as ORG ("Rakhi Girija Shetty")
- **Precision (sample basis): 17/50 = 34%**

### Honest interpretation

The regex-based categories generalize well to a completely different,
much messier real document — 100% precision on every unique value found,
once the DIN/fiscal-year fix was applied. The NER-based categories do not
generalize as well: a general-purpose small spaCy model, even with
blocklists and shape heuristics layered on top, has real trouble with
dense legal/financial prose full of Title-Case defined terms and
markdown-table formatting that breaks normal sentence structure. This is
a known, expected limitation of off-the-shelf NER on out-of-domain text,
not a hidden defect — it's why this report separates "exact numbers on a
controlled test set" from "sample-audited numbers on a hard real
document" rather than presenting one blended number.

**If this were going to production against real filings like this one, the
next investment would be:** a fine-tuned or larger spaCy/transformer NER
model trained on legal/financial text, or a reviewed custom dictionary of
this filing's own defined terms (SEBI prospectuses have a "Definitions"
section that could be parsed to build an exclude-list automatically).
