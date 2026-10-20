"""Final ACCEPT / REVIEW / REJECT decision.

A pure function with no I/O, so every rule is easy to test.

Principles:
  * Uncertainty is never turned into REJECT. If the facts are unclear,
    the answer is REVIEW and a human decides.
  * REJECT requires a clear negative fact (consumers cannot buy, quote-
    only site, B2B-only, conflicting company evidence, ...).
  * ACCEPT requires everything to be clearly positive: a real consumer
    webshop with online checkout AND a verified operator with a valid
    Business ID.
  * Company size or chain membership is not an input at all.
"""

from typing import Optional, Tuple

from .models import AIAssessment, Attribution, Decision

_REJECT_BUSINESS_TYPES = {"b2b_only", "vehicle_dealer_only"}
_REJECT_PURCHASE_MODELS = {"quote_only", "presentation_only"}
_REJECT_ATTRIBUTION = {"CONFLICT", "INVALID_BUSINESS_ID"}


def decide(ai: AIAssessment, attribution: Attribution) -> Tuple[Decision, Optional[str]]:
    if ai.ai_status != "OK":
        return Decision.REVIEW, f"AI status {ai.ai_status}: no reliable facts"

    if ai.b2c_purchase_available == "NO":
        return Decision.REJECT, "consumers cannot buy on the site"
    if ai.business_type in _REJECT_BUSINESS_TYPES:
        return Decision.REJECT, f"business type {ai.business_type}"
    if ai.purchase_model in _REJECT_PURCHASE_MODELS:
        return Decision.REJECT, f"purchase model {ai.purchase_model}"
    if ai.business_type == "marketplace" and not ai.company_name:
        return Decision.REJECT, "marketplace without a single operator"

    webshop_ok = (
        ai.is_real_webshop == "YES"
        and ai.b2c_purchase_available == "YES"
        and ai.purchase_model == "real_time_purchase"
    )
    if not webshop_ok:
        return Decision.REVIEW, "webshop facts not all clearly positive"

    if attribution.status in _REJECT_ATTRIBUTION:
        return Decision.REJECT, f"company check: {attribution.status}"

    if attribution.status == "VERIFIED" and attribution.business_id_valid:
        return Decision.ACCEPT, None

    return Decision.REVIEW, f"company not verified ({attribution.status})"
