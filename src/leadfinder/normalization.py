"""Domain normalization and deduplication.

Search results arrive as messy URLs ("https://WWW.Example-Shop.invalid/p?id=3",
"example-shop.invalid/", "http://example-shop.invalid:443"). Every URL is
reduced to one canonical hostname so the same shop is never evaluated
(or paid for) twice.
"""

import re
from typing import Iterable, List, Optional
from urllib.parse import urlsplit

# A naive "last two labels" root would treat "a.co.uk" and "b.co.uk" as the
# same site. This small list covers the common multi-label suffixes; it is
# a deliberate approximation, not a full Public Suffix List.
_MULTI_LABEL_SUFFIXES = frozenset({
    "co.uk", "org.uk", "ac.uk", "com.au", "co.nz", "co.jp", "com.br",
})

_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def normalize_domain(raw) -> Optional[str]:
    """Return a lowercase hostname without scheme, "www.", port or path.

    Returns None for anything that is not a well-formed hostname.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "://" not in s:
        s = "//" + s  # lets urlsplit treat "example-shop.invalid/path" as a host

    try:
        host = urlsplit(s).hostname
    except ValueError:
        return None
    if not host:
        return None

    host = host.strip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    if "." not in host:
        return None
    if not all(_LABEL_RE.match(label) for label in host.split(".")):
        return None
    return host


def registrable_root(raw) -> Optional[str]:
    """Best-effort registrable root: "kauppa.example-shop.invalid" -> "example-shop.invalid"."""
    host = normalize_domain(raw)
    if host is None:
        return None
    labels = host.split(".")
    last_two = ".".join(labels[-2:])
    if last_two in _MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def same_registrable_domain(a, b) -> bool:
    """True if both inputs belong to the same site. Never raises."""
    root_a, root_b = registrable_root(a), registrable_root(b)
    return root_a is not None and root_a == root_b


def dedupe_domains(urls: Iterable[str]) -> List[str]:
    """Normalize URLs and keep the first occurrence of each domain, in order.

    Unparseable inputs are dropped.
    """
    seen = set()
    result = []
    for url in urls:
        domain = normalize_domain(url)
        if domain and domain not in seen:
            seen.add(domain)
            result.append(domain)
    return result
