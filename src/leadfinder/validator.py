"""LLM-assisted validation of a candidate domain.

Design rule: the LLM describes facts, code applies policy.

The model is asked a fixed set of factual questions about the domain and
must answer in a strict "KEY: value" format with a closed set of allowed
values. The parser is deliberately pessimistic:

  * a missing or unrecognised value becomes UNKNOWN, never a guess
  * a missing or invalid AI_STATUS becomes ERROR
  * a failed / empty / timed-out call becomes ERROR, never an exception

The ACCEPT / REVIEW / REJECT decision is made later in decision.py.
"""

import logging
import re
from typing import Callable, Dict, Optional

from .models import AIAssessment
from .retry import TransientError, call_with_retry
from .storage import Store

log = logging.getLogger("leadfinder.validator")

PROMPT_VERSION = 1

AI_STATUS_VALUES = {"OK", "NO_DATA", "AMBIGUOUS", "ERROR"}
YES_NO_UNKNOWN = {"YES", "NO", "UNKNOWN"}
PURCHASE_MODELS = {
    "real_time_purchase", "quote_only", "presentation_only",
    "marketplace_multi_seller", "unknown",
}
BUSINESS_TYPES = {
    "independent_b2c", "chain", "manufacturer_direct", "marketplace",
    "b2b_only", "vehicle_dealer_only", "unknown",
}
_NULLISH = {"", "NONE", "UNKNOWN", "N/A", "NONE_FOUND"}
_LINE_RE = re.compile(r"^([A-Z0-9_]+):\s*(.*)$")

# Type of the injected LLM call: (prompt) -> raw answer text.
QueryFn = Callable[[str], str]


def build_prompt(domain: str) -> str:
    """The prompt sent to the LLM. Simplified from the production version."""
    return f"""You are checking one website for a Finnish consumer ecommerce lead list.
Research the domain "{domain}" and answer ONLY in the format below.
If you are not sure about a fact, answer UNKNOWN instead of guessing.

Definitions:
- A real webshop lets a buyer place an order and pay online.
  Quote-request-only or catalogue-only sites are NOT real webshops.
- B2C_PURCHASE_AVAILABLE is YES only if a private consumer can buy.
- Company size or chain membership must not affect your answers.
- Report facts only. Do not judge whether this is a good sales lead.

AI_STATUS: OK | NO_DATA | AMBIGUOUS | ERROR
IS_REAL_WEBSHOP: YES | NO | UNKNOWN
B2C_PURCHASE_AVAILABLE: YES | NO | UNKNOWN
PURCHASE_MODEL: {" | ".join(sorted(PURCHASE_MODELS))}
BUSINESS_TYPE: {" | ".join(sorted(BUSINESS_TYPES))}
CANONICAL_DOMAIN: <domain or NONE>
COMPANY_NAME: <legal company name or UNKNOWN>
BUSINESS_ID: <Finnish Business ID DDDDDDD-D or UNKNOWN>
DESCRIPTION: <one sentence>
"""


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None or value.strip().upper() in _NULLISH:
        return None
    return value.strip()


def parse_ai_response(raw_text: Optional[str]) -> AIAssessment:
    """Parse the LLM answer. Never raises; worst case is an ERROR assessment."""
    result = AIAssessment()
    if not raw_text or not str(raw_text).strip():
        result.parse_errors.append("empty_response")
        return result

    fields: Dict[str, str] = {}
    for line in str(raw_text).splitlines():
        match = _LINE_RE.match(line.strip())
        if match:
            fields[match.group(1)] = match.group(2).strip()

    def enum_field(key: str, allowed: set, default: str) -> str:
        value = fields.get(key, "")
        if value in allowed:
            return value
        result.parse_errors.append(f"missing_or_invalid:{key}")
        return default

    result.ai_status = enum_field("AI_STATUS", AI_STATUS_VALUES, "ERROR")
    result.is_real_webshop = enum_field("IS_REAL_WEBSHOP", YES_NO_UNKNOWN, "UNKNOWN")
    result.b2c_purchase_available = enum_field("B2C_PURCHASE_AVAILABLE", YES_NO_UNKNOWN, "UNKNOWN")
    result.purchase_model = enum_field("PURCHASE_MODEL", PURCHASE_MODELS, "unknown")
    result.business_type = enum_field("BUSINESS_TYPE", BUSINESS_TYPES, "unknown")
    result.canonical_domain = _clean(fields.get("CANONICAL_DOMAIN"))
    result.company_name = _clean(fields.get("COMPANY_NAME"))
    result.business_id = _clean(fields.get("BUSINESS_ID"))
    result.description = _clean(fields.get("DESCRIPTION"))
    return result


def validate_domain(
    domain: str,
    query_fn: QueryFn,
    store: Optional[Store] = None,
    sleep: Callable[[float], None] = None,
) -> AIAssessment:
    """Ask the LLM about `domain` and parse the answer.

    * Uses the cache in `store` if present, so a domain is never queried
      twice for the same PROMPT_VERSION (important with paid APIs).
    * Retries transient failures; any final failure becomes ai_status=ERROR.
    * Error results are NOT cached, so they are retried on the next run.
    """
    if store is not None:
        cached = store.get_ai_response(domain, PROMPT_VERSION)
        if cached is not None:
            log.debug("AI cache hit: %s", domain)
            return parse_ai_response(cached)

    retry_kwargs = {"sleep": sleep} if sleep else {}
    try:
        raw = call_with_retry(
            lambda: query_fn(build_prompt(domain)),
            on_retry=lambda n, exc: log.warning("AI retry %d for %s: %s", n, domain, exc),
            **retry_kwargs,
        )
    except Exception as exc:  # any client failure -> safe ERROR, never a crash
        log.error("AI call failed for %s: %s: %s", domain, type(exc).__name__, exc)
        failed = AIAssessment()
        failed.parse_errors.append(f"query_failed:{type(exc).__name__}")
        return failed

    assessment = parse_ai_response(raw)
    if store is not None and assessment.ai_status != "ERROR":
        store.save_ai_response(domain, PROMPT_VERSION, raw)
    return assessment


class MockLLMClient:
    """Offline stand-in for a real LLM API.

    `responses` maps domain -> canned answer text. `fail_first` maps
    domain -> number of times to raise TransientError before answering,
    which lets the demo and tests exercise the retry path.
    """

    def __init__(self, responses: Dict[str, str], fail_first: Dict[str, int] = None):
        self.responses = responses
        self.fail_first = dict(fail_first or {})
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        self.calls += 1
        match = re.search(r'domain "([^"]+)"', prompt)
        domain = match.group(1) if match else ""
        if self.fail_first.get(domain, 0) > 0:
            self.fail_first[domain] -= 1
            raise TransientError("simulated timeout")
        return self.responses.get(domain, "")
