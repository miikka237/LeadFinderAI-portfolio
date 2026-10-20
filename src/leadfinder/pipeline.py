"""Batch evaluation: candidate -> AI validation -> identification -> decision.

Behaviour that mattered in real use:
  * Target-based: stop as soon as `target_accept` unique ACCEPT leads
    exist in storage (including ones from earlier runs).
  * Resumable: domains already evaluated in an earlier run are skipped;
    cached AI answers are reused.
  * Duplicate-safe: a domain is evaluated at most once per run and can
    count toward the target only once.
  * Fault-isolated: one domain raising an unexpected error is logged and
    skipped; it never aborts the batch.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional

from .decision import decide
from .identification import FetchFn, RegistryFn, identify_operator
from .models import Attribution, Candidate, Decision, LeadResult
from .normalization import normalize_domain
from .storage import Store
from .validator import QueryFn, validate_domain

log = logging.getLogger("leadfinder.pipeline")


@dataclass
class RunSummary:
    results: List[LeadResult] = field(default_factory=list)
    skipped_duplicates: int = 0
    skipped_already_evaluated: int = 0
    failed: int = 0
    target_reached: bool = False

    def count(self, decision: Decision) -> int:
        return sum(1 for r in self.results if r.decision == decision)


def evaluate_one(
    candidate: Candidate,
    query_fn: QueryFn,
    fetch_fn: FetchFn,
    registry_fn: RegistryFn,
    store: Optional[Store] = None,
    sleep: Callable[[float], None] = None,
) -> LeadResult:
    ai = validate_domain(candidate.domain, query_fn, store=store, sleep=sleep)

    if ai.ai_status == "OK":
        attribution = identify_operator(candidate.domain, ai, fetch_fn, registry_fn)
    else:
        # No reliable facts: don't spend extra lookups on it.
        attribution = Attribution("INSUFFICIENT_EVIDENCE")

    decision, reason = decide(ai, attribution)
    return LeadResult(
        domain=candidate.domain,
        url=candidate.url,
        decision=decision,
        reason=reason,
        company_name=ai.company_name,
        business_id=ai.business_id,
        ai_status=ai.ai_status,
        business_type=ai.business_type,
        attribution_status=attribution.status,
        source_query=candidate.source_query,
    )


def evaluate_candidates(
    candidates: Iterable[Candidate],
    store: Store,
    query_fn: QueryFn,
    fetch_fn: FetchFn,
    registry_fn: RegistryFn,
    target_accept: int,
    sleep: Callable[[float], None] = None,
    on_result: Callable[[Candidate, LeadResult], None] = None,
) -> RunSummary:
    summary = RunSummary()
    accepted = store.accepted_domains()          # progress from earlier runs counts
    already_evaluated = store.evaluated_domains()
    seen_this_run = set()

    log.info("starting batch: target=%d, already accepted=%d", target_accept, len(accepted))

    for candidate in candidates:
        if len(accepted) >= target_accept:
            summary.target_reached = True
            log.info("target of %d ACCEPT leads reached, stopping", target_accept)
            break

        domain = normalize_domain(candidate.domain or candidate.url)
        if domain is None or domain in seen_this_run:
            summary.skipped_duplicates += 1
            continue
        seen_this_run.add(domain)
        candidate.domain = domain

        if domain in already_evaluated:
            summary.skipped_already_evaluated += 1
            log.debug("already evaluated in an earlier run: %s", domain)
            continue

        try:
            result = evaluate_one(candidate, query_fn, fetch_fn, registry_fn, store=store, sleep=sleep)
        except Exception:
            summary.failed += 1
            log.exception("unexpected error for %s, skipping", domain)
            continue

        # AI errors are not stored as final results, so the domain is retried next run.
        if result.ai_status != "ERROR":
            store.save_result(result)
        if result.decision == Decision.ACCEPT:
            accepted.add(domain)

        summary.results.append(result)
        log.info("%s -> %s (%s)", domain, result.decision.value, result.reason or "all checks passed")
        if on_result:
            on_result(candidate, result)
    else:
        summary.target_reached = len(accepted) >= target_accept

    return summary
