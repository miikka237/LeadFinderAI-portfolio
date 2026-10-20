"""Company identification: who actually operates this webshop?

The LLM may claim "this site is run by Example Oy, Business ID 9900001-8".
That claim is not trusted on its own. It is checked against:

  1. the shop's own pages (Finnish shops usually print their Business ID
     in the footer, terms of sale or contact page), and
  2. the company registry (does this Business ID belong to that name?).

Rules, in order:
  * claimed Business ID fails the checksum         -> INVALID_BUSINESS_ID
  * nothing was claimed                             -> INSUFFICIENT_EVIDENCE
  * the site shows a different valid Business ID    -> CONFLICT
  * registry has the ID under a different name      -> CONFLICT
  * the site shows the claimed Business ID          -> VERIFIED
  * the site shows the name AND the registry agrees -> VERIFIED
  * anything else                                   -> INSUFFICIENT_EVIDENCE

A registry match alone is never enough: it proves company <-> ID, not
company <-> domain.

The page fetch and the registry lookup are injected functions, so this
module runs fully offline in tests and in the demo.
"""

import logging
import re
from typing import Callable, List, Optional

from .business_id import is_valid_business_id, normalize_business_id
from .models import AIAssessment, Attribution

log = logging.getLogger("leadfinder.identification")

# (domain) -> page text, or raises
FetchFn = Callable[[str], str]
# (business_id) -> registered company name, or None if not found
RegistryFn = Callable[[str], Optional[str]]

_ID_PATTERN = re.compile(r"\b\d{7}-\d\b")
_LEGAL_FORMS = re.compile(r"\b(oyj|oy|ab|ky|tmi|ltd|gmbh|inc)\b\.?", re.IGNORECASE)


def find_business_ids(text: str) -> List[str]:
    """All checksum-valid Business IDs that appear in a page, de-duplicated."""
    found = [normalize_business_id(m) for m in _ID_PATTERN.findall(text or "")]
    return list(dict.fromkeys(i for i in found if is_valid_business_id(i)))


def normalize_company_name(name: Optional[str]) -> str:
    if not name:
        return ""
    s = _LEGAL_FORMS.sub(" ", name.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def names_match(a: Optional[str], b: Optional[str]) -> bool:
    """Strict comparison after removing legal forms ("Oy", "Ab", ...).

    No fuzzy matching: "Northstar Shop Oy" == "NORTHSTAR SHOP OY", but
    "Shop Oy" != "Northstar Shop Oy".
    """
    na, nb = normalize_company_name(a), normalize_company_name(b)
    return bool(na) and na == nb


def identify_operator(
    domain: str,
    ai: AIAssessment,
    fetch_fn: FetchFn,
    registry_fn: RegistryFn,
) -> Attribution:
    notes: List[str] = []
    claimed_id = normalize_business_id(ai.business_id) if ai.business_id else None
    id_valid = bool(claimed_id) and is_valid_business_id(claimed_id)

    if claimed_id and not id_valid:
        return Attribution("INVALID_BUSINESS_ID", False, [f"claimed ID {claimed_id} fails checksum"])

    if not claimed_id and not ai.company_name:
        return Attribution("INSUFFICIENT_EVIDENCE", False, ["no company claimed"])

    # Evidence from the site itself. A fetch failure is not evidence either way.
    try:
        page_text = fetch_fn(domain) or ""
    except Exception as exc:
        log.warning("could not fetch %s: %s", domain, exc)
        page_text = ""
        notes.append("site could not be fetched")

    ids_on_site = find_business_ids(page_text)
    name_on_site = bool(ai.company_name) and normalize_company_name(ai.company_name) in normalize_company_name(page_text)

    if claimed_id and ids_on_site and claimed_id not in ids_on_site:
        notes.append(f"site shows {ids_on_site}, AI claimed {claimed_id}")
        return Attribution("CONFLICT", id_valid, notes)

    # Registry check.
    registry_name = None
    if claimed_id:
        try:
            registry_name = registry_fn(claimed_id)
        except Exception as exc:
            log.warning("registry lookup failed for %s: %s", claimed_id, exc)
            notes.append("registry unavailable")

    if registry_name and ai.company_name and not names_match(registry_name, ai.company_name):
        notes.append(f"registry name '{registry_name}' != claimed '{ai.company_name}'")
        return Attribution("CONFLICT", id_valid, notes)

    if claimed_id and claimed_id in ids_on_site:
        notes.append("claimed Business ID found on the site")
        return Attribution("VERIFIED", id_valid, notes)

    if name_on_site and registry_name and names_match(registry_name, ai.company_name):
        notes.append("company name found on site and confirmed by registry")
        return Attribution("VERIFIED", id_valid, notes)

    notes.append("no independent evidence linking the domain to the claimed company")
    return Attribution("INSUFFICIENT_EVIDENCE", id_valid, notes)
