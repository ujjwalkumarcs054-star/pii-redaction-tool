"""
detectors.py
------------
One detector function per PII category. Every detector has the same
signature so the engine (engine.py) can call them uniformly and so a new
PII type can be added by writing one function and registering it.

    def detect_XXX(text: str) -> list[Span]

Span = (start, end, matched_text, category, confidence)

Design notes
------------
- Structured PII (email, phone, SSN, credit card, IP, DOB) is detected with
  regex, because these have a fixed, learnable shape. Where a naive regex
  would over-match (credit cards, IPs), we add a validation step
  (Luhn checksum, octet range) to cut false positives.
- Unstructured PII (person names, company names, physical addresses) is
  detected with spaCy's statistical NER model, because there is no regex
  that reliably captures "a human name" or "a company name" across styles.
"""

from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass
class Span:
    start: int
    end: int
    text: str
    category: str
    confidence: float = 1.0

    def __repr__(self):
        return f"Span({self.category}, {self.text!r}, {self.start}:{self.end})"


# ---------------------------------------------------------------------------
# EMAIL
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

def detect_email(text: str) -> list[Span]:
    return [Span(m.start(), m.end(), m.group(), "EMAIL") for m in _EMAIL_RE.finditer(text)]


# ---------------------------------------------------------------------------
# PHONE NUMBER (Indian + generic international formats)
# ---------------------------------------------------------------------------
# Matches: +91 9876543210, +91-22-30752914, 022-68052182, (022) 6805 2182,
# +1 415-555-2671, plain 10-digit mobile numbers, etc.
_PHONE_RE = re.compile(
    r"""
    (?<!\d)
    (?:\+?\d{1,3}[-.\s]?)?          # optional country code
    (?:\(?\d{2,4}\)?[-.\s]?)?       # optional area/STD code
    \d{3,4}[-.\s]?\d{3,4}           # local number
    (?!\d)
    """,
    re.VERBOSE,
)

_YEAR_RANGE_RE = re.compile(r"^(19|20)\d{2}[-/](19|20)\d{2}$")

def _looks_like_phone(candidate: str) -> bool:
    digits = re.sub(r"\D", "", candidate)
    if not (7 <= len(digits) <= 13):
        return False
    # Fiscal year ranges like "2023-2024" are not phone numbers.
    if _YEAR_RANGE_RE.match(candidate.strip()):
        return False
    # Real phone numbers (even with an STD/area code) don't have more than
    # ~2 leading zeros; long zero-padded strings are usually table/ledger
    # reference codes picked up from financial statements.
    if re.match(r"^0{3,}", digits):
        return False
    return True

_ALNUM_CODE_PREFIX_RE = re.compile(r"[A-Za-z]{2,6}-$")
_PHONE_CONTEXT_RE = re.compile(
    r"\b(?:tel|telephone|phone|mobile|fax|contact|call|cell)\b", re.IGNORECASE
)

def detect_phone(text: str) -> list[Span]:
    spans = []
    for m in _PHONE_RE.finditer(text):
        candidate = m.group()
        if not _looks_like_phone(candidate):
            continue
        digits = re.sub(r"\D", "", candidate)
        if len(digits) in (6,):  # PIN code, not a phone number
            continue
        # Skip the numeric tail of an alphanumeric code like "TRK-99213456"
        # or "INV-12345678" -- these are business identifiers, not phones.
        prefix_window = text[max(0, m.start() - 8):m.start()]
        if _ALNUM_CODE_PREFIX_RE.search(prefix_window):
            continue
        # A number with an explicit "+" / international prefix is
        # unambiguous. A bare digit-group (no "+", no leading STD-style
        # "0") is only accepted if a phone-indicating word appears nearby
        # -- this is what separates real phone numbers from table
        # reference codes like DIN numbers, which sit in the same kind of
        # numeric column with no such keyword nearby.
        stripped = candidate.strip()
        has_std_code_shape = bool(re.match(r"^0\d{2,4}[-.\s]\d{6,8}$", stripped))
        if not stripped.startswith("+") and not has_std_code_shape:
            window = text[max(0, m.start() - 60):m.end() + 10]
            if not _PHONE_CONTEXT_RE.search(window):
                continue
        spans.append(Span(m.start(), m.end(), candidate, "PHONE"))
    return spans


# ---------------------------------------------------------------------------
# SOCIAL SECURITY NUMBER (US format: 123-45-6789)
# ---------------------------------------------------------------------------
_SSN_RE = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")

def detect_ssn(text: str) -> list[Span]:
    return [Span(m.start(), m.end(), m.group(), "SSN") for m in _SSN_RE.finditer(text)]


# ---------------------------------------------------------------------------
# CREDIT CARD NUMBER (13-19 digits, grouped or not) + Luhn checksum
# ---------------------------------------------------------------------------
_CC_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number]
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0

def detect_credit_card(text: str) -> list[Span]:
    spans = []
    for m in _CC_RE.finditer(text):
        digits = re.sub(r"[ -]", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            spans.append(Span(m.start(), m.end(), m.group(), "CREDIT_CARD"))
    return spans


# ---------------------------------------------------------------------------
# IP ADDRESS (IPv4, each octet validated 0-255)
# ---------------------------------------------------------------------------
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

def detect_ip(text: str) -> list[Span]:
    spans = []
    for m in _IP_RE.finditer(text):
        octets = m.group().split(".")
        if all(0 <= int(o) <= 255 for o in octets):
            spans.append(Span(m.start(), m.end(), m.group(), "IP_ADDRESS"))
    return spans


# ---------------------------------------------------------------------------
# DATE OF BIRTH
# ---------------------------------------------------------------------------
# A date on its own is ambiguous (filing date, incorporation date, board
# meeting date, etc). We only tag a date as DOB when a birth-related keyword
# appears within a short window before it, to keep precision high.
_MONTHS = (r"January|February|March|April|May|June|July|August|September|"
           r"October|November|December")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[-/](?:\d{1,2}|[A-Za-z]{3,9})[-/]\d{2,4}"
    rf"|(?:{_MONTHS})\s+\d{{1,2}},?\s+\d{{4}}"
    rf"|\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}})\b"
)
_DOB_CONTEXT_RE = re.compile(r"\b(?:date of birth|born on|d\.?o\.?b\.?)\b", re.IGNORECASE)

def detect_dob(text: str) -> list[Span]:
    spans = []
    for m in _DATE_RE.finditer(text):
        window_start = max(0, m.start() - 40)
        window = text[window_start:m.start()]
        if _DOB_CONTEXT_RE.search(window):
            spans.append(Span(m.start(), m.end(), m.group(), "DATE_OF_BIRTH"))
    return spans


# ---------------------------------------------------------------------------
# FULL NAMES / COMPANY NAMES / ADDRESSES  -- spaCy NER
# ---------------------------------------------------------------------------
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
    return _nlp

_GENERIC_BLOCKLIST = {
    "board", "offer", "shares", "equity", "prospectus", "committee", "act",
    "regulations", "annexure", "schedule", "size", "sale", "eligibility",
    "type", "total", "risks", "email", "company", "officer", "secretary",
    "compliance", "cap price", "promoters", "roc", "sebi", "qibs", "niis",
    "riis", "statement", "particulars", "details", "note", "annexure a",
}

_NAME_SHAPE_RE = re.compile(r"^[A-Z][a-zA-Z.&'-]*(?:\s+[A-Z][a-zA-Z.&'-]*){1,4}$")


def _is_name_shaped(clean: str) -> bool:
    """Unicode-aware replacement for _NAME_SHAPE_RE.

    The original regex only accepted [a-zA-Z], so accented names (Renée,
    Muñoz, Zoë) failed the shape filter even when spaCy correctly tagged
    them as PERSON/ORG. This checks the same shape -- 2 to 5 capitalized
    tokens, each starting with an uppercase letter -- using str.isupper()/
    isalpha(), which are unicode-aware in Python, instead of a fixed
    ASCII character class.
    """
    tokens = clean.split()
    if not (2 <= len(tokens) <= 5):
        return False
    for tok in tokens:
        core = tok.strip(".&'-")
        if not core:
            return False
        if not core[0].isupper():
            return False
        if not all(ch.isalpha() or ch in ".&'-" for ch in tok):
            return False
    return True

# Prospectus/finance-jargon tokens: if ANY token of a candidate name/company
# entity is one of these common nouns, it is almost certainly a defined
# legal/financial term ("Bid Amount", "Floor Price"), not a real person or
# company name. Real personal names very rarely collide with a business
# common-noun as a *second* token. This list is intentionally extensible --
# add a lowercase token here whenever a new jargon false positive is found.
_JARGON_TOKENS = {
    "account", "accounts", "advice", "amount", "application", "balances",
    "bidder", "bidders", "committee", "complex", "details", "fund",
    "investors", "investor", "measures", "measure", "personnel", "price",
    "slip", "society", "regulations", "regulation", "requirements",
    "statement", "structure", "system", "form", "forms", "period", "date",
    "dates", "percentage", "ratio", "ratios", "report", "reports", "policy",
    "policies", "procedure", "procedures", "framework", "guidelines",
    "code", "codes", "rules", "rule", "authority", "market", "markets",
    "segment", "division", "department", "circular", "notification",
    "scheme", "schemes", "manual", "register", "registrar", "certificate",
    "certification", "license", "licence", "permit", "approval",
    "clearance", "disclosure", "disclosures", "risk", "risks",
    "shareholder", "shareholders", "employee", "employees", "officers",
    "vehicle", "vehicles", "kilometers", "conditioning", "suraksha",
    "hour", "gigawatt-hour", "gwh", "slip", "website", "hufs", "huf",
    "ticket", "priority", "tracking", "reference", "order",
}


def _has_jargon_token(clean: str) -> bool:
    return any(tok.lower() in _JARGON_TOKENS for tok in clean.split())

_ORG_SUFFIX_RE = re.compile(
    r"\b(Limited|Ltd|LLP|Inc|Corp|Company|Bank|Trust|Industries|"
    r"Enterprises|Securities|Exchange|Board of India)\b", re.IGNORECASE
)


def _clean_ent_text(t: str) -> str:
    return t.strip().strip(",.;:")


def _spacy_safe_text(text: str) -> str:
    """Replace markdown escape backslashes (e.g. "Hegde\\*") with a space,
    1 character for 1 character, so downstream offsets stay valid.
    Left as-is, a literal backslash glued directly to a name/word confuses
    spaCy's tokenizer and can split a multi-token name in two (e.g.
    "Kushal Subbayya Hegde\\*" gets tokenized so that "Hegde\\*" is cut off
    from the PERSON entity, leaving a bare surname unredacted elsewhere).
    """
    return text.replace("\\", " ")


def detect_names_orgs_addresses(text: str, chunk_size: int = 100_000) -> list[Span]:
    """Run spaCy NER over the text in chunks (to respect model max length
    on very large documents) and map entity labels to our categories, then
    apply precision filters tuned for dense financial/legal table text.

    Design choice (documented in README): a bare city/country name (e.g.
    "Mumbai", "India") is NOT treated as PII on its own -- it doesn't
    identify a specific individual or premises. Only addresses with a
    structural marker (door number, street/village name, PIN code) are
    redacted as ADDRESS; see detect_address_heuristic for that logic.
    """
    nlp = _get_nlp()
    spans: list[Span] = []
    clean_text = _spacy_safe_text(text)

    for offset in range(0, len(text), chunk_size):
        chunk = clean_text[offset:offset + chunk_size]
        doc = nlp(chunk)
        for ent in doc.ents:
            raw = text[offset + ent.start_char: offset + ent.end_char]
            clean = _clean_ent_text(raw)
            low = clean.lower()

            if low in _GENERIC_BLOCKLIST or len(clean) < 3 or _has_jargon_token(clean):
                continue

            if ent.label_ == "PERSON":
                if not _is_name_shaped(clean):
                    continue
                label = "FULL_NAME"
            elif ent.label_ == "ORG":
                if not (_ORG_SUFFIX_RE.search(clean) or _is_name_shaped(clean)):
                    continue
                label = "COMPANY_NAME"
            else:
                continue

            start = offset + ent.start_char
            end = start + len(raw)
            spans.append(Span(start, end, raw, label))

    spans.extend(_propagate_confirmed_entities(text, spans))
    return spans


def _propagate_confirmed_entities(text: str, spans: list[Span]) -> list[Span]:
    """Second pass: catch repeated mentions spaCy's per-sentence NER missed.

    spaCy tags entities sentence-by-sentence, so the same name can be
    recognized in one sentence ("Filed by Ananya Sharma") and missed in
    another ("Customer Ananya Sharma called in") purely because of its
    position or surrounding grammar -- or missed only in an ALL-CAPS
    variant, since small spaCy models are known to be weaker on all-caps
    text (e.g. a normal-case "KSH International Limited" gets tagged, but
    the ALL-CAPS cover-page "KSH INTERNATIONAL LIMITED" does not). Once a
    name/company has been confirmed at least once elsewhere in the
    document, any other *exact, whole-word, case-insensitive* occurrence
    of that same string is almost certainly the same person or company,
    not a coincidence -- so we add it directly rather than relying on the
    NER model to catch it again. Matching is deliberately
    case-INsensitive (unlike a plain re-match) specifically to catch the
    ALL-CAPS case.
    """
    confirmed: dict[tuple[str, str], str] = {}
    for s in spans:
        if s.category in ("FULL_NAME", "COMPANY_NAME"):
            key = (s.category, s.text.lower())
            confirmed.setdefault(key, s.text)

    covered = [(s.start, s.end) for s in spans]
    extra: list[Span] = []
    for (category, _low), original in confirmed.items():
        pattern = re.compile(r"\b" + re.escape(original) + r"\b", re.IGNORECASE)
        for m in pattern.finditer(text):
            if any(m.start() < e and m.end() > st for st, e in covered):
                continue
            extra.append(Span(m.start(), m.end(), m.group(), category))
            covered.append((m.start(), m.end()))
    return extra


# Street-address heuristic fallback (catches multi-line mailing addresses
# that spaCy's GPE/LOC tags alone tend to only partially cover, e.g. addresses
# with door numbers, "Village", "Taluka", PIN codes).
_ADDRESS_LINE_RE = re.compile(
    r"\b\d{1,4}(?:/\d{1,4})*[,]?\s*[\w\- ]{0,60},?\s*(?:Village|Taluka|Road|Street|"
    r"Society|Nagar|Colony|Lane|Marg|Chowk|Complex|Tower|Floor|Court|Avenue|"
    r"Chambers|Enclave|Park|Layout|Residency|Building|Apartment)\b"
    r"[\w\s,.\-]{0,150}?(?:–|-)?\s*\d{3}\s?\d{3}\b",
    re.IGNORECASE,
)

def detect_address_heuristic(text: str) -> list[Span]:
    return [Span(m.start(), m.end(), m.group(), "ADDRESS")
            for m in _ADDRESS_LINE_RE.finditer(text)]


# ---------------------------------------------------------------------------
# Registry: category -> detector. Add a new PII type by writing a function
# above and adding one line here.
# ---------------------------------------------------------------------------
REGEX_DETECTORS = {
    "EMAIL": detect_email,
    "PHONE": detect_phone,
    "SSN": detect_ssn,
    "CREDIT_CARD": detect_credit_card,
    "IP_ADDRESS": detect_ip,
    "DATE_OF_BIRTH": detect_dob,
    "ADDRESS_HEURISTIC": detect_address_heuristic,
}