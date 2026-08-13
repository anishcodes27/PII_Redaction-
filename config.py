"""
Central configuration for the PII Redaction Tool.
Holds all regex patterns, entity type constants, and tunable parameters.
"""

import re

ENTITY_TYPES = {
    "PERSON": "PERSON",
    "EMAIL": "EMAIL",
    "PHONE": "PHONE",
    "ORG": "ORG",
    "ADDRESS": "ADDRESS",
    "SSN": "SSN",
    "CREDIT_CARD": "CREDIT_CARD",
    "DATE_OF_BIRTH": "DATE_OF_BIRTH",
    "IP_ADDRESS": "IP_ADDRESS",
}

import spacy

try:
    spacy.load("en_core_web_lg")
    SPACY_MODEL = "en_core_web_lg"
except Exception:
    SPACY_MODEL = "en_core_web_sm"


SPACY_ENTITY_MAP = {
    "PERSON": ENTITY_TYPES["PERSON"],
    "ORG": ENTITY_TYPES["ORG"],
    "GPE": ENTITY_TYPES["ADDRESS"],
    "LOC": ENTITY_TYPES["ADDRESS"],
    "FAC": ENTITY_TYPES["ADDRESS"],
}

REGEX_PATTERNS = {
    ENTITY_TYPES["EMAIL"]: re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        re.IGNORECASE,
    ),
    ENTITY_TYPES["SSN"]: re.compile(
        r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"
    ),
    ENTITY_TYPES["IP_ADDRESS"]: re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    ENTITY_TYPES["CREDIT_CARD"]: re.compile(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}"
        r"|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}"
        r"|(?:2131|1800|35\d{3})\d{11})\b"
    ),
    ENTITY_TYPES["DATE_OF_BIRTH"]: re.compile(
        r"\b(?:DOB|Date of Birth|Born|Birth Date)\s*[:\-]?\s*"
        r"(?:\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}"
        r"|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}"
        r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
        re.IGNORECASE,
    ),
    ENTITY_TYPES["PHONE"]: re.compile(
        r"(?:\+?\d{1,3}[\s\-\.]?)?"
        r"(?:\(?\d{3}\)?[\s\-\.]?)"
        r"\d{3}[\s\-\.]\d{4}"
        r"(?:\s*(?:x|ext|extension)\.?\s*\d{1,5})?"
    ),
}

PRESIDIO_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IP_ADDRESS",
    "DATE_TIME",
    "LOCATION",
    "NRP",
]

PRESIDIO_ENTITY_MAP = {
    "PERSON": ENTITY_TYPES["PERSON"],
    "EMAIL_ADDRESS": ENTITY_TYPES["EMAIL"],
    "PHONE_NUMBER": ENTITY_TYPES["PHONE"],
    "CREDIT_CARD": ENTITY_TYPES["CREDIT_CARD"],
    "US_SSN": ENTITY_TYPES["SSN"],
    "IP_ADDRESS": ENTITY_TYPES["IP_ADDRESS"],
    "DATE_TIME": ENTITY_TYPES["DATE_OF_BIRTH"],
    "LOCATION": ENTITY_TYPES["ADDRESS"],
}

CONFIDENCE_THRESHOLD = 0.4

FAKER_LOCALE = "en_US"

IGNORED_ENTITIES = {
    "company",
    "the company",
    "equity shares",
    "equity share",
    "shares",
    "share",
    "offer",
    "the offer",
    "floor price",
    "cap price",
    "offer price",
    "issue",
    "the issue",
    "board",
    "the board",
    "board of directors",
    "promoter",
    "promoters",
    "red herring prospectus",
    "prospectus",
    "sebi",
    "sebi icdr regulations",
    "icdr regulations",
    "book building process",
    "book running lead managers",
    "anchor investors",
    "upi",
    "asba",
    "asba bidders",
    "qibs",
    "nii",
    "niis",
    "rii",
    "riis",
    "bids",
    "bid",
    "bidders",
    "bidder",
    "table",
    "order",
    "ticket",
    "section",
    "act",
    "companies act",
    "registrar of companies",
}

