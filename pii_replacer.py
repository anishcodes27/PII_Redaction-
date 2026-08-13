"""
PII Replacement Engine.

Provides Faker-based synthetic data generation with a consistency cache so that
the same original PII value is always replaced by the same fake substitute
throughout an entire document.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, Optional

from faker import Faker

from config import ENTITY_TYPES, FAKER_LOCALE

logger = logging.getLogger(__name__)


class ConsistencyCache:
    """
    Maintains a mapping from original PII text (normalised) to its fake replacement.
    Ensures entity-level consistency across an entire document: the same real name,
    email, or phone number always maps to the same synthetic substitute.
    """

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    def _key(self, entity_type: str, original: str) -> str:
        """Build a normalised cache key from entity type and original text."""
        return f"{entity_type}::{original.strip().lower()}"

    def get(self, entity_type: str, original: str) -> Optional[str]:
        """Return the cached fake value for this entity, or None if not cached."""
        return self._store.get(self._key(entity_type, original))

    def set(self, entity_type: str, original: str, fake: str) -> None:
        """Store a fake value for a given entity type and original text."""
        self._store[self._key(entity_type, original)] = fake

    def clear(self) -> None:
        """Reset the cache (typically between documents)."""
        self._store.clear()

    @property
    def size(self) -> int:
        """Return the number of cached mappings."""
        return len(self._store)


class FakerReplacer:
    """
    Generates realistic synthetic replacements for each supported PII entity type
    using the Faker library. Uses ConsistencyCache to guarantee that the same
    original value always receives the same synthetic substitute within a document.
    """

    def __init__(self, locale: str = FAKER_LOCALE) -> None:
        self._fake = Faker(locale)
        Faker.seed(42)
        self._cache = ConsistencyCache()
        self._generators = {
            ENTITY_TYPES["PERSON"]: self._fake_person,
            ENTITY_TYPES["EMAIL"]: self._fake_email,
            ENTITY_TYPES["PHONE"]: self._fake_phone,
            ENTITY_TYPES["ORG"]: self._fake_org,
            ENTITY_TYPES["ADDRESS"]: self._fake_address,
            ENTITY_TYPES["SSN"]: self._fake_ssn,
            ENTITY_TYPES["CREDIT_CARD"]: self._fake_credit_card,
            ENTITY_TYPES["DATE_OF_BIRTH"]: self._fake_dob,
            ENTITY_TYPES["IP_ADDRESS"]: self._fake_ip,
        }

    def _fake_person(self, _original: str) -> str:
        return self._fake.name()

    def _fake_email(self, _original: str) -> str:
        return self._fake.email()

    def _fake_phone(self, _original: str) -> str:
        return self._fake.phone_number()

    def _fake_org(self, _original: str) -> str:
        return self._fake.company()

    def _fake_address(self, _original: str) -> str:
        return self._fake.city()

    def _fake_ssn(self, _original: str) -> str:
        return self._fake.ssn()

    def _fake_credit_card(self, _original: str) -> str:
        return self._fake.credit_card_number(card_type="visa")

    def _fake_dob(self, _original: str) -> str:
        dob = self._fake.date_of_birth(minimum_age=18, maximum_age=80)
        return dob.strftime("%m/%d/%Y")

    def _fake_ip(self, _original: str) -> str:
        return self._fake.ipv4_private()

    def replace(self, entity_type: str, original: str) -> str:
        """
        Return a consistent fake replacement for the given entity type and original value.
        Looks up the cache first; generates and caches a new value only on a cache miss.
        Falls back to a generic placeholder if the entity type is unsupported.
        """
        cached = self._cache.get(entity_type, original)
        if cached is not None:
            return cached

        generator = self._generators.get(entity_type)
        if generator is None:
            logger.warning("No generator for entity type '%s'; using placeholder.", entity_type)
            fake_value = f"[REDACTED_{entity_type}]"
        else:
            fake_value = generator(original)

        self._cache.set(entity_type, original, fake_value)
        logger.debug("Mapped '%s' (%s) → '%s'", original, entity_type, fake_value)
        return fake_value

    def reset_cache(self) -> None:
        """Clear the consistency cache, typically called between separate documents."""
        self._cache.clear()
        logger.info("Consistency cache cleared.")

    @property
    def cache_size(self) -> int:
        """Return the number of unique PII values mapped so far."""
        return self._cache.size
