"""Decision policy: ACCEPT only when everything is clearly positive."""

import pytest
from conftest import ai_answer

from leadfinder.decision import decide
from leadfinder.models import Attribution, Decision
from leadfinder.validator import parse_ai_response

VERIFIED = Attribution("VERIFIED", business_id_valid=True)


def _decide(attribution=VERIFIED, **answer_fields):
    return decide(parse_ai_response(ai_answer(**answer_fields)), attribution)[0]


def test_valid_candidate_is_accepted():
    assert _decide() == Decision.ACCEPT


def test_chain_or_manufacturer_is_not_rejected_for_being_big():
    assert _decide(BUSINESS_TYPE="chain") == Decision.ACCEPT
    assert _decide(BUSINESS_TYPE="manufacturer_direct") == Decision.ACCEPT


@pytest.mark.parametrize("fields", [
    {"B2C_PURCHASE_AVAILABLE": "NO"},
    {"BUSINESS_TYPE": "b2b_only"},
    {"BUSINESS_TYPE": "vehicle_dealer_only"},
    {"PURCHASE_MODEL": "quote_only"},
    {"PURCHASE_MODEL": "presentation_only"},
    {"BUSINESS_TYPE": "marketplace", "COMPANY_NAME": "UNKNOWN"},
])
def test_invalid_candidates_are_rejected(fields):
    assert _decide(**fields) == Decision.REJECT


@pytest.mark.parametrize("status", ["CONFLICT", "INVALID_BUSINESS_ID"])
def test_company_evidence_problems_are_rejected(status):
    assert _decide(attribution=Attribution(status)) == Decision.REJECT


def test_unverified_company_goes_to_review():
    assert _decide(attribution=Attribution("INSUFFICIENT_EVIDENCE", True)) == Decision.REVIEW


def test_verified_but_invalid_business_id_is_not_accepted():
    assert _decide(attribution=Attribution("VERIFIED", business_id_valid=False)) == Decision.REVIEW


def test_ai_error_is_review_even_if_other_fields_look_negative():
    # A broken answer must not be trusted in either direction.
    assert _decide(AI_STATUS="ERROR", B2C_PURCHASE_AVAILABLE="NO") == Decision.REVIEW
