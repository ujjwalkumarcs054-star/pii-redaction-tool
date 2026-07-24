"""
engine.py
---------
Orchestrates detection (detectors.py) + consistent fake-value substitution.

Pipeline:
  1. Run every registered detector over the input text -> raw spans.
  2. Resolve overlaps (e.g. spaCy ADDRESS overlapping a regex ADDRESS_HEURISTIC
     span, or an ORG span inside a PERSON span) by preferring the more
     specific / higher-priority category and the longest match.
  3. For each surviving span, look up (or create) a fake replacement so the
     *same* real value always maps to the *same* fake value throughout the
     document (e.g. every occurrence of "Rashi Patil" -> "John Doe").
  4. Rebuild the text with replacements applied back-to-front so earlier
     offsets stay valid.
"""

from __future__ import annotations
import itertools
import random
from detectors import Span, REGEX_DETECTORS, detect_names_orgs_addresses

# Priority when two spans overlap: higher number wins.
CATEGORY_PRIORITY = {
    "EMAIL": 100,
    "SSN": 100,
    "CREDIT_CARD": 100,
    "IP_ADDRESS": 100,
    "DATE_OF_BIRTH": 90,
    "PHONE": 80,
    "ADDRESS_HEURISTIC": 70,
    "ADDRESS": 60,
    "FULL_NAME": 50,
    "COMPANY_NAME": 40,
}

# ADDRESS_HEURISTIC is a refinement of ADDRESS; normalize the label once
# overlap resolution has picked it.
_NORMALIZE_LABEL = {"ADDRESS_HEURISTIC": "ADDRESS"}


def _resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Greedy interval scheduling: sort by (priority desc, length desc),
    keep a span if it doesn't overlap anything already kept."""
    ordered = sorted(
        spans,
        key=lambda s: (-CATEGORY_PRIORITY.get(s.category, 0), -(s.end - s.start)),
    )
    kept: list[Span] = []
    occupied: list[tuple[int, int]] = []
    for s in ordered:
        if any(s.start < e and s.end > st for st, e in occupied):
            continue
        kept.append(s)
        occupied.append((s.start, s.end))
    kept.sort(key=lambda s: s.start)
    return kept


def detect_all(text: str) -> list[Span]:
    spans: list[Span] = []
    for detector in REGEX_DETECTORS.values():
        spans.extend(detector(text))
    spans.extend(detect_names_orgs_addresses(text))
    return _resolve_overlaps(spans)


# ---------------------------------------------------------------------------
# Fake value generation - deterministic per real value, varied across values
# ---------------------------------------------------------------------------
class FakeValueFactory:
    """Hands out a fake replacement for a given (category, real_value) pair.
    The same real value always gets the same fake value (a stable mapping),
    and different real values get different fake values where practical.
    """

    FIRST_NAMES = ["John", "Jane", "Peter", "Mary", "Alex", "Sam", "Chris",
                   "Taylor", "Jordan", "Morgan", "Casey", "Riley"]
    LAST_NAMES = ["Doe", "Parker", "Smith", "Johnson", "Lee", "Brown",
                  "Wilson", "Clark", "Walker", "Hall", "Young", "Allen"]
    COMPANY_NAMES = ["Acme Corp", "Globex Inc", "Initech LLC", "Umbrella Ltd",
                     "Stark Industries", "Wayne Enterprises", "Hooli Inc",
                     "Soylent Corp", "Vandelay Industries", "Wonka Ltd"]
    STREETS = ["Maple Street", "Oak Avenue", "Elm Road", "Cedar Lane",
               "Birch Boulevard", "Pine Drive"]
    CITIES = ["Springfield", "Rivertown", "Fairview", "Lakeside", "Millbrook"]

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)
        self._map: dict[tuple[str, str], str] = {}
        self._name_cycle = itertools.cycle(
            [f"{f} {l}" for f in self.FIRST_NAMES for l in self.LAST_NAMES]
        )
        self._company_cycle = itertools.cycle(self.COMPANY_NAMES)
        self._addr_cycle = itertools.cycle(
            [f"{n} {s}, {c}" for n in range(100, 999, 37)
             for s in self.STREETS for c in self.CITIES]
        )

    def _norm(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

    def get(self, category: str, real_value: str) -> str:
        key = (category, self._norm(real_value))
        if key in self._map:
            return self._map[key]

        fake = self._generate(category, real_value)
        self._map[key] = fake
        return fake

    def _generate(self, category: str, real_value: str) -> str:
        if category == "EMAIL":
            local, _, domain = real_value.partition("@")
            fake_person = self.get("FULL_NAME", local.replace(".", " "))
            return fake_person.lower().replace(" ", ".") + "@example.com"
        if category == "FULL_NAME":
            return next(self._name_cycle)
        if category == "COMPANY_NAME":
            return next(self._company_cycle)
        if category == "PHONE":
            # Keep the same country-code prefix "shape" but scramble digits.
            prefix = "+91 " if real_value.strip().startswith("+91") else ""
            digits = "".join(str(self._rng.randint(0, 9)) for _ in range(10))
            return f"{prefix}{digits[:5]} {digits[5:]}".strip()
        if category == "SSN":
            return f"{self._rng.randint(100,899):03d}-{self._rng.randint(10,99):02d}-{self._rng.randint(1000,9999):04d}"
        if category == "CREDIT_CARD":
            digits = [str(self._rng.randint(0, 9)) for _ in range(15)]
            partial = "4" + "".join(digits)  # Visa-like prefix
            # fix check digit via Luhn
            def luhn_checksum(num):
                total = 0
                parity = len(num) % 2
                for i, ch in enumerate(num):
                    d = int(ch)
                    if i % 2 == parity:
                        d *= 2
                        if d > 9:
                            d -= 9
                    total += d
                return total % 10
            check = (10 - luhn_checksum(partial + "0")) % 10
            full = partial + str(check)
            return f"{full[0:4]}-{full[4:8]}-{full[8:12]}-{full[12:16]}"
        if category == "IP_ADDRESS":
            return f"10.{self._rng.randint(0,255)}.{self._rng.randint(0,255)}.{self._rng.randint(1,254)}"
        if category == "DATE_OF_BIRTH":
            day = self._rng.randint(1, 28)
            month = self._rng.randint(1, 12)
            year = self._rng.randint(1950, 2005)
            return f"{day:02d}-{month:02d}-{year}"
        if category == "ADDRESS":
            return next(self._addr_cycle)
        return "[REDACTED]"


def redact(text: str, spans: list[Span] | None = None,
           factory: FakeValueFactory | None = None) -> tuple[str, list[Span], FakeValueFactory]:
    """Returns (redacted_text, spans_used, factory) so callers can also
    inspect what was found / how it was replaced."""
    if spans is None:
        spans = detect_all(text)
    if factory is None:
        factory = FakeValueFactory()

    out = text
    for s in sorted(spans, key=lambda s: s.start, reverse=True):
        category = _NORMALIZE_LABEL.get(s.category, s.category)
        fake = factory.get(category, s.text)
        out = out[:s.start] + fake + out[s.end:]
    return out, spans, factory
