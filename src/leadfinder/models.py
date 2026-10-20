"""Data models shared across the pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Decision(str, Enum):
    ACCEPT = "ACCEPT"   # goes to the calling team
    REVIEW = "REVIEW"   # a human should look at it
    REJECT = "REJECT"   # clearly not a qualifying lead


@dataclass
class Candidate:
    """A website found by search, before any validation."""

    url: str
    domain: str                      # normalized, e.g. "northstarshop.invalid"
    source_query: Optional[str] = None


@dataclass
class AIAssessment:
    """Facts extracted from the LLM's structured answer.

    The LLM only reports facts. It never decides whether something is a
    good lead -- that is done by plain Python code in decision.py.
    Every field defaults to an "unknown" value, so a missing or broken
    answer can never look like a positive one.
    """

    ai_status: str = "ERROR"                 # OK | NO_DATA | AMBIGUOUS | ERROR
    is_real_webshop: str = "UNKNOWN"         # YES | NO | UNKNOWN
    b2c_purchase_available: str = "UNKNOWN"  # YES | NO | UNKNOWN
    purchase_model: str = "unknown"
    business_type: str = "unknown"
    canonical_domain: Optional[str] = None
    company_name: Optional[str] = None
    business_id: Optional[str] = None
    description: Optional[str] = None
    parse_errors: List[str] = field(default_factory=list)


@dataclass
class Attribution:
    """Result of checking who actually operates the domain."""

    status: str                         # VERIFIED | CONFLICT | INVALID_BUSINESS_ID | INSUFFICIENT_EVIDENCE
    business_id_valid: bool = False
    notes: List[str] = field(default_factory=list)


@dataclass
class LeadResult:
    """Final, export-ready result for one domain."""

    domain: str
    url: str
    decision: Decision
    reason: Optional[str]
    company_name: Optional[str] = None
    business_id: Optional[str] = None
    ai_status: str = "ERROR"
    business_type: str = "unknown"
    attribution_status: str = "INSUFFICIENT_EVIDENCE"
    source_query: Optional[str] = None

    def as_row(self) -> dict:
        return {
            "domain": self.domain,
            "url": self.url,
            "decision": self.decision.value,
            "reason": self.reason or "",
            "company_name": self.company_name or "",
            "business_id": self.business_id or "",
            "ai_status": self.ai_status,
            "business_type": self.business_type,
            "attribution_status": self.attribution_status,
            "source_query": self.source_query or "",
        }
