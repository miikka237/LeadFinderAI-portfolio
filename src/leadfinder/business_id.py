"""Finnish Business ID (Y-tunnus) format and checksum validation.

Format: seven digits, a hyphen and a check digit, e.g. "9900001-8"
(a synthetic ID used throughout this repository).
The weights 7, 9, 10, 5, 8, 4, 2 are applied to the seven digits and the
sum is taken modulo 11:
  remainder 0 -> check digit 0
  remainder 1 -> no valid check digit exists for that prefix
  otherwise   -> check digit = 11 - remainder

This is an offline syntax check only. A valid checksum does NOT prove that
the company exists or that it operates a given website -- that is checked
separately in identification.py.
"""

import re
from typing import Optional

_WEIGHTS = (7, 9, 10, 5, 8, 4, 2)
_FORMAT_RE = re.compile(r"^(\d{7})-(\d)$")


def normalize_business_id(raw) -> Optional[str]:
    """Return "DDDDDDD-D", tolerating whitespace and a missing hyphen."""
    if raw is None:
        return None
    s = re.sub(r"\s+", "", str(raw))
    if not s:
        return None
    if re.fullmatch(r"\d{8}", s):
        s = s[:7] + "-" + s[7:]
    return s


def compute_check_digit(seven_digits: str) -> Optional[int]:
    total = sum(int(d) * w for d, w in zip(seven_digits, _WEIGHTS))
    remainder = total % 11
    if remainder == 1:
        return None
    return 0 if remainder == 0 else 11 - remainder


def is_valid_business_id(raw) -> bool:
    normalized = normalize_business_id(raw)
    if not normalized:
        return False
    match = _FORMAT_RE.match(normalized)
    if not match:
        return False
    digits, check = match.group(1), int(match.group(2))
    if digits == "0000000":
        # Passes the checksum but is never a real ID; it showed up as a
        # false positive when scanning web pages for ID-shaped strings.
        return False
    return compute_check_digit(digits) == check
