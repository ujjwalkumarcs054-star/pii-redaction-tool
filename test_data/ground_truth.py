"""
ground_truth.py
---------------
Hand-labeled ground truth for test_data/synthetic_ticket_log.txt.

Each entry is (category, exact_text_as_it_appears_in_the_file). Where a
value repeats (e.g. "Bluewave Technologies Pvt Ltd" appears twice), it is
listed once per occurrence -- occurrences are matched left-to-right against
the source text so repeats are handled correctly.

Also included: NEGATIVE_EXAMPLES, substrings that must NOT be flagged as
PII by any category. These encode the assignment's explicit precision
requirement (e.g. "Order #78542" is a business identifier, not PII).
"""

GROUND_TRUTH = [
    # Ticket #45213
    ("FULL_NAME", "Rashi Patil"),          # "opened by Rashi Patil"
    ("FULL_NAME", "Rashi Patil"),          # "Customer: Rashi Patil"
    ("EMAIL", "rashi.patil@gmail.com"),
    ("PHONE", "+91 9876543210"),
    ("COMPANY_NAME", "Bluewave Technologies Pvt Ltd"),   # 1st occurrence
    ("ADDRESS", "42 Lakeview Road, Andheri, Mumbai – 400 069"),
    ("DATE_OF_BIRTH", "14-03-1990"),
    ("FULL_NAME", "Rohan Dey"),
    ("EMAIL", "rohan.dey@gmail.com"),
    ("PHONE", "+91 9123456780"),
    ("COMPANY_NAME", "Bluewave Technologies Pvt Ltd"),   # 2nd occurrence
    ("IP_ADDRESS", "192.168.1.55"),
    ("CREDIT_CARD", "4111 1111 1111 1111"),
    ("SSN", "123-45-6789"),

    # Ticket #45214
    ("FULL_NAME", "Meera Iyer"),
    ("EMAIL", "meera.iyer88@yahoo.com"),
    ("PHONE", "+91 9988776655"),
    ("COMPANY_NAME", "Contoso Global Services"),
    ("ADDRESS", "15/2 Palm Grove Society, Kothrud, Pune – 411 038"),
    ("DATE_OF_BIRTH", "22 July 1985"),
    ("IP_ADDRESS", "10.0.0.23"),
    ("CREDIT_CARD", "5500 0000 0000 0004"),
    ("SSN", "456-78-1234"),

    # Ticket #45215 -- deliberately contains NO PII (see NEGATIVE_EXAMPLES)

    # Ticket #45216
    ("FULL_NAME", "Devika Rao"),
    ("EMAIL", "devika.rao@outlook.com"),
    ("PHONE", "(022) 6805-2182"),
    ("COMPANY_NAME", "Meridian Analytics Inc"),
    ("ADDRESS", "7 Cedar Court, Bandra West, Mumbai – 400 050"),
    ("DATE_OF_BIRTH", "05/11/1992"),
    ("IP_ADDRESS", "203.0.113.44"),
    ("FULL_NAME", "Karan Bhatt"),
    ("EMAIL", "karan.bhatt@support.co.in"),
]

# Things that must NOT be redacted (business identifiers / generic dates /
# jargon that a naive detector might over-match). Used to score precision
# on deliberate near-miss lookalikes.
NEGATIVE_EXAMPLES = [
    "2026-01-04",       # ticket-open date, not a DOB (no birth context)
    "2026-01-05",
    "2026-01-07",
    "Order #78542",
    "TRK-99213456",
    "Ticket #45215",
    "$450.00",
    "Refund Policy",
    "Committee",
    "Annexure A",
]
