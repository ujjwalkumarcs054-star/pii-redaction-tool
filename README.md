# PII Redaction Tool — README

## What this is
A script that reads a text document, finds PII across 8 required categories,
and replaces each instance with a realistic **fake but consistent**
replacement (the same real value always maps to the same fake value
throughout the document).

Tested on two documents:
1. A **synthetic ticket log** I wrote myself (`test_data/synthetic_ticket_log.txt`),
   in the style of the assignment's own example, with full hand-labeled
   ground truth — used for exact precision/recall/F1 numbers.
2. The **actual attached file** — a real ~350-page SEBI Red Herring
   Prospectus (IPO filing) for KSH International Limited — used as a
   real-world stress test. Note this is a public regulatory filing, not a
   private "ticket log"; I redacted it anyway per the assignment, but its
   density of legal/financial jargon is a much harder NER environment than
   a typical support ticket, and the numbers below reflect that honestly.

## Approach: hybrid regex + spaCy NER, not one universal method

| Category | Method | Why |
|---|---|---|
| Email | Regex | Fixed, unambiguous format |
| Phone | Regex + context check | Format alone is ambiguous (looks like other numeric codes); a bare digit group is only accepted near a phone-indicating word ("Tel", "Mobile", ...) unless it has an unambiguous `+countrycode` or `STD-code-number` shape |
| SSN | Regex with SSA validity rules | Rejects structurally-invalid area numbers (000, 666, 900-999) to cut false positives |
| Credit card | Regex + **Luhn checksum** | Luhn check is what separates a real card number from any other 13-19 digit string (order IDs, IDs, etc.) |
| IP address | Regex + octet range (0-255) validation | Rejects things that only look like dotted-decimal numbers |
| Date of birth | Date regex + nearby birth-context keyword ("DOB", "date of birth", "born on") | A bare date is ambiguous (could be a filing date, incorporation date, etc.); requiring context is a deliberate precision/recall tradeoff |
| Full name | spaCy `en_core_web_sm` NER (`PERSON`) + shape/jargon filters | No regex reliably captures "a human name"; NER handles variation |
| Company name | spaCy NER (`ORG`) + legal-suffix / shape / jargon filters | Same reasoning as names |
| Address | Regex heuristic (door number + street/village keyword + PIN code) | More precise than tagging every `GPE`/`LOC` spaCy entity — see explicit scope decision below |

Code layout (`detectors.py` → `engine.py` → `redact.py`):
- **`detectors.py`** — one function per category, all with the same
  `(text) -> list[Span]` signature. **To add a new PII type**: write one
  function here and add one line to the `REGEX_DETECTORS` dict (or extend
  `detect_names_orgs_addresses` if it's an NER-based type).
- **`engine.py`** — merges all detector outputs, resolves overlapping spans
  by category priority, and generates consistent fake replacements via
  `FakeValueFactory` (same real value → same fake value, every time).
- **`redact.py`** — CLI: `python3 redact.py input.txt output.txt --audit audit.json`.

## Explicit scope decisions (precision requirement)

- **Order/ticket/tracking numbers are NOT treated as PII** — e.g. "Order
  #78542", "TRK-99213456" are business identifiers, not personal data. This
  is exercised directly in the synthetic test set's negative examples.
- **A bare city or country name (e.g. "Mumbai", "India") is NOT treated as
  an address** — it doesn't identify a specific individual or premises on
  its own. Only addresses with a structural marker (door number + street/
  village name + PIN code) are redacted. This was a deliberate call after
  the first pass over the real prospectus treated every `GPE`/`LOC` spaCy
  tag as an address, which was almost entirely false positives.
- **Fiscal-year ranges ("2023-2024") and long zero-padded reference/DIN
  codes are excluded from phone detection** — found during testing on the
  real document, where Director Identification Numbers sitting in the same
  table column as other codes were briefly getting misread as phone numbers.

## Known false positives / false negatives (see EVALUATION_REPORT.md for numbers)

- **On the synthetic ticket log:** none, after fixing three bugs the
  eval script surfaced (a tracking-number false positive, a missed
  day-first date format, and a jargon leak on "Ticket Priority").
- **On the real prospectus:** the NER-based categories (full name, company
  name) have real precision limits. Dense legal/financial text is full of
  Title-Case multi-word defined terms ("Bid Amount", "Floor Price", "Key
  Managerial Personnel") that a general-purpose NER model sometimes
  mis-tags as a person or company, and legal-drafting formatting (long
  table cells with no sentence punctuation) occasionally causes spans to
  merge across cell boundaries. I added blocklists and shape filters to
  cut the largest sources of noise, but did not try to make this
  document-perfect — a production system would need either a
  domain-fine-tuned NER model or a reviewed custom entity dictionary for
  this specific filing type. This is called out with real numbers in the
  evaluation report rather than glossed over.
- Regex-based categories (email, phone, IP, credit card, SSN) stayed
  effectively 100% precision on the real document once the phone-context
  fix above was applied — structured formats are inherently easier.

## Evaluation approach (summary — full numbers in EVALUATION_REPORT.md)

1. **Synthetic ground truth** (`test_data/ground_truth.py`): every PII
   instance in the synthetic ticket log is hand-labeled by category, plus a
   set of deliberate non-PII lookalikes. `eval.py` matches detector output
   against this ground truth span-by-span and reports precision/recall/F1
   per category plus an overall accuracy figure.
2. **Real-document sample audit**: since hand-labeling all ~350 pages of
   the real prospectus isn't practical in the time available, I manually
   reviewed *all* unique `FULL_NAME` detections (75) and a *random sample*
   of 50 of the 218 unique `COMPANY_NAME` detections, classifying each as a
   real name/company or not, to estimate precision on the harder document.
   Regex-based categories (email, phone, address, IP, SSN, credit card)
   were checked exhaustively since their unique-value counts are small
   enough to review in full.

## Deliverables in this submission
- `detectors.py`, `engine.py`, `redact.py` — source code
- `test_data/synthetic_ticket_log.txt`, `test_data/ground_truth.py`, `eval.py` — test set + evaluator
- `redacted_output.docx` — the redacted prospectus
- `EVALUATION_REPORT.md` — full precision/recall/accuracy numbers
