"""LLM validation: parsing must be conservative and failures must be safe."""

from conftest import INVALID_ID, OTHER_VALID_ID, VALID_ID, ai_answer

from leadfinder.decision import decide
from leadfinder.identification import identify_operator
from leadfinder.models import AIAssessment, Attribution, Decision
from leadfinder.retry import PermanentError, TransientError
from leadfinder.validator import MockLLMClient, PROMPT_VERSION, parse_ai_response, validate_domain

DOMAIN = "northstarshop.invalid"


# --- Parsing -----------------------------------------------------------------

def test_parses_well_formed_answer():
    ai = parse_ai_response(ai_answer())
    assert ai.ai_status == "OK"
    assert ai.is_real_webshop == "YES"
    assert ai.company_name == "Northstar Shop Oy"
    assert ai.business_id == VALID_ID
    assert ai.parse_errors == []


def test_free_text_answer_becomes_error_not_a_guess():
    ai = parse_ai_response("Sure! This looks like a great online shop.")
    assert ai.ai_status == "ERROR"
    assert ai.is_real_webshop == "UNKNOWN"
    assert ai.b2c_purchase_available == "UNKNOWN"
    assert "missing_or_invalid:AI_STATUS" in ai.parse_errors


def test_invalid_enum_values_fall_back_to_unknown():
    ai = parse_ai_response(ai_answer(IS_REAL_WEBSHOP="PROBABLY", PURCHASE_MODEL="maybe_online"))
    assert ai.ai_status == "OK"
    assert ai.is_real_webshop == "UNKNOWN"
    assert ai.purchase_model == "unknown"


def test_unknown_placeholders_become_none():
    ai = parse_ai_response(ai_answer(COMPANY_NAME="UNKNOWN", BUSINESS_ID="N/A"))
    assert ai.company_name is None
    assert ai.business_id is None


def test_empty_answer_is_error():
    assert parse_ai_response("").ai_status == "ERROR"
    assert parse_ai_response(None).ai_status == "ERROR"


# --- Safe handling of uncertain or broken AI output in the final decision -----

def test_uncertain_ai_output_goes_to_review_never_reject_or_accept():
    for raw in [ai_answer(AI_STATUS="AMBIGUOUS"), ai_answer(AI_STATUS="NO_DATA"), "garbage", ""]:
        decision, _ = decide(parse_ai_response(raw), Attribution("VERIFIED", True))
        assert decision == Decision.REVIEW


def test_unknown_webshop_facts_go_to_review():
    ai = parse_ai_response(ai_answer(IS_REAL_WEBSHOP="UNKNOWN"))
    decision, _ = decide(ai, Attribution("VERIFIED", True))
    assert decision == Decision.REVIEW


# --- Calling the LLM: retry, errors and caching --------------------------------

def test_transient_failure_is_retried_then_succeeds(no_sleep):
    llm = MockLLMClient({DOMAIN: ai_answer()}, fail_first={DOMAIN: 2})
    ai = validate_domain(DOMAIN, llm, sleep=no_sleep)
    assert ai.ai_status == "OK"
    assert llm.calls == 3


def test_persistent_transient_failure_becomes_error_not_exception(no_sleep):
    llm = MockLLMClient({DOMAIN: ai_answer()}, fail_first={DOMAIN: 99})
    ai = validate_domain(DOMAIN, llm, sleep=no_sleep)
    assert ai.ai_status == "ERROR"
    assert llm.calls == 3  # 1 attempt + 2 retries, then give up


def test_permanent_failure_is_not_retried(no_sleep):
    calls = []

    def bad_key(prompt):
        calls.append(prompt)
        raise PermanentError("invalid API key")

    ai = validate_domain(DOMAIN, bad_key, sleep=no_sleep)
    assert ai.ai_status == "ERROR"
    assert len(calls) == 1


def test_successful_answer_is_cached_and_not_queried_again(store):
    llm = MockLLMClient({DOMAIN: ai_answer()})
    validate_domain(DOMAIN, llm, store=store)
    validate_domain(DOMAIN, llm, store=store)
    assert llm.calls == 1
    assert store.get_ai_response(DOMAIN, PROMPT_VERSION) is not None


def test_error_answer_is_not_cached_so_it_is_retried_next_run(store, no_sleep):
    def always_down(prompt):
        raise TransientError("timeout")

    validate_domain(DOMAIN, always_down, store=store, sleep=no_sleep)
    assert store.get_ai_response(DOMAIN, PROMPT_VERSION) is None


# --- Company identification ----------------------------------------------------

def _ai(**kw):
    return parse_ai_response(ai_answer(**kw))


def test_identification_verified_when_site_shows_claimed_id():
    att = identify_operator(DOMAIN, _ai(), lambda d: f"Northstar Shop Oy, Y-tunnus {VALID_ID}", lambda i: None)
    assert att.status == "VERIFIED"


def test_identification_conflict_when_site_shows_different_id():
    att = identify_operator(DOMAIN, _ai(), lambda d: f"Y-tunnus {OTHER_VALID_ID}", lambda i: None)
    assert att.status == "CONFLICT"


def test_identification_rejects_checksum_invalid_id():
    att = identify_operator(DOMAIN, _ai(BUSINESS_ID=INVALID_ID), lambda d: "", lambda i: None)
    assert att.status == "INVALID_BUSINESS_ID"


def test_registry_match_alone_is_not_enough():
    # Registry confirms company <-> ID, but nothing links the company to the domain.
    att = identify_operator(DOMAIN, _ai(), lambda d: "Welcome to our shop!", lambda i: "Northstar Shop Oy")
    assert att.status == "INSUFFICIENT_EVIDENCE"


def test_name_on_site_plus_registry_match_is_verified():
    att = identify_operator(DOMAIN, _ai(), lambda d: "(c) Northstar Shop Oy", lambda i: "NORTHSTAR SHOP OY")
    assert att.status == "VERIFIED"


def test_fetch_and_registry_failures_do_not_crash():
    def down(_):
        raise ConnectionError("offline")

    att = identify_operator(DOMAIN, _ai(), down, down)
    assert att.status == "INSUFFICIENT_EVIDENCE"


def test_no_claim_means_insufficient_evidence():
    att = identify_operator(DOMAIN, AIAssessment(ai_status="OK"), lambda d: "", lambda i: None)
    assert att.status == "INSUFFICIENT_EVIDENCE"
