"""Search-based discovery of candidate webshop domains.

Flow per query:
    search engine -> raw result URLs -> drop obvious non-shops
    -> normalize + deduplicate -> store new candidates

Queries are built from a fixed list of product categories ("running shoes
online store", ...). A persistent cursor remembers which query to run
next, so a large category list can be worked through over several runs.

The production version used a paid search API. Here the search client is
an interface, and the demo/tests use a fake client with canned results.
"""

import logging
from typing import Callable, Dict, Iterable, List, Optional, Protocol
from urllib.parse import urlsplit

from .models import Candidate
from .normalization import normalize_domain, registrable_root
from .retry import call_with_retry
from .storage import Store

log = logging.getLogger("leadfinder.discovery")

# Sites that show up in search results but are never a company's own shop.
# (Generic public examples -- the production list was longer.)
BLOCKED_ROOT_DOMAINS = frozenset({
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com",
    "wikipedia.org", "reddit.com", "medium.com",
    "amazon.com", "ebay.com", "etsy.com",
})
BLOCKED_SUBDOMAIN_WORDS = ("blog", "wiki", "help", "support", "news", "forum")
BLOCKED_PATH_PARTS = ("/blog/", "/news/", "/article/", "/wiki/", "/tag/")


class SearchClient(Protocol):
    def search(self, query: str) -> List[str]:
        """Return result URLs for a query. May raise TransientError."""


class FakeSearchClient:
    """Returns canned results; used by the demo and tests (no network)."""

    def __init__(self, results_by_query: Dict[str, List[str]]):
        self.results_by_query = results_by_query
        self.calls: List[str] = []

    def search(self, query: str) -> List[str]:
        self.calls.append(query)
        return list(self.results_by_query.get(query, []))


def build_queries(categories: Iterable[str], suffix: str = "verkkokauppa") -> List[str]:
    """Deterministic query list ("verkkokauppa" = "online store" in Finnish).

    The order must stay stable, because the stored cursor is an index
    into this list.
    """
    return [f"{category} {suffix}" for category in categories]


def is_bad_url(url: str) -> bool:
    """True for URLs that are clearly not a company's own webshop."""
    domain = normalize_domain(url)
    if domain is None:
        return True
    if registrable_root(domain) in BLOCKED_ROOT_DOMAINS:
        return True
    subdomain = domain[: -len(registrable_root(domain))].rstrip(".")
    if any(word in subdomain for word in BLOCKED_SUBDOMAIN_WORDS):
        return True
    path = urlsplit(url if "://" in url else "//" + url).path.lower()
    return any(part in path for part in BLOCKED_PATH_PARTS)


def discover(
    store: Store,
    client: SearchClient,
    queries: List[str],
    max_new_candidates: int,
    max_queries: Optional[int] = None,
    sleep: Callable[[float], None] = None,
) -> List[Candidate]:
    """Run queries starting from the stored cursor until enough new
    candidates are found or every query has been tried once.

    The cursor is advanced only AFTER a query has been fully handled, so a
    crash mid-query means that query is simply re-run next time. A query
    that keeps failing is logged and skipped -- one bad query must not
    stop the whole run.
    """
    if not queries:
        return []

    retry_kwargs = {"sleep": sleep} if sleep else {}
    start = store.get_cursor() % len(queries)
    limit = min(len(queries), max_queries or len(queries))
    new_candidates: List[Candidate] = []

    for step in range(limit):
        if len(new_candidates) >= max_new_candidates:
            break
        index = (start + step) % len(queries)
        query = queries[index]

        try:
            urls = call_with_retry(
                lambda: client.search(query),
                on_retry=lambda n, exc: log.warning("retry %d for query %r: %s", n, query, exc),
                **retry_kwargs,
            )
        except Exception as exc:
            log.error("search failed for query %r, skipping: %s", query, exc)
            store.set_cursor(index + 1)
            continue

        kept = [u for u in urls if not is_bad_url(u)]
        log.info("query %r: %d results, %d after filtering", query, len(urls), len(kept))

        for url in kept:
            if len(new_candidates) >= max_new_candidates:
                break
            candidate = Candidate(url=url, domain=normalize_domain(url), source_query=query)
            if store.add_candidate(candidate):
                new_candidates.append(candidate)
            else:
                log.debug("duplicate domain skipped: %s", candidate.domain)

        store.set_cursor(index + 1)

    return new_candidates
