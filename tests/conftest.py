"""Shared test helpers. All external services are faked; no network, no API keys."""

import pytest

from leadfinder.storage import Store

# Synthetic, checksum-valid Business IDs (unallocated 99000xx range).
VALID_ID = "9900001-8"
OTHER_VALID_ID = "9900005-0"
INVALID_ID = "9900001-1"


def ai_answer(**overrides) -> str:
    """Build a well-formed LLM answer for a clearly qualifying webshop."""
    fields = {
        "AI_STATUS": "OK",
        "IS_REAL_WEBSHOP": "YES",
        "B2C_PURCHASE_AVAILABLE": "YES",
        "PURCHASE_MODEL": "real_time_purchase",
        "BUSINESS_TYPE": "independent_b2c",
        "CANONICAL_DOMAIN": "northstarshop.invalid",
        "COMPANY_NAME": "Northstar Shop Oy",
        "BUSINESS_ID": VALID_ID,
        "DESCRIPTION": "Synthetic test shop.",
    }
    fields.update(overrides)
    return "\n".join(f"{k}: {v}" for k, v in fields.items())


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def no_sleep():
    calls = []
    return lambda seconds: calls.append(seconds)
