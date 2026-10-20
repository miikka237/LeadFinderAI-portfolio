"""Batch behaviour: target, duplicates, resume, error isolation, discovery, export."""

import csv
import os

import pytest
from conftest import ai_answer

from leadfinder.discovery import FakeSearchClient, build_queries, discover, is_bad_url
from leadfinder.exporter import export_results
from leadfinder.models import Candidate, Decision
from leadfinder.pipeline import evaluate_candidates
from leadfinder.retry import TransientError
from leadfinder.validator import MockLLMClient

# Five synthetic shops that all qualify. Each has its own checksum-valid ID.
SHOP_IDS = {
    "shop-a.invalid": "9900001-8",
    "shop-b.invalid": "9900002-6",
    "shop-c.invalid": "9900003-4",
    "shop-d.invalid": "9900004-2",
    "shop-e.invalid": "9900005-0",
}


def _llm(**kwargs):
    responses = {
        d: ai_answer(COMPANY_NAME=f"{d.split('.')[0].title()} Oy", BUSINESS_ID=bid, CANONICAL_DOMAIN=d)
        for d, bid in SHOP_IDS.items()
    }
    return MockLLMClient(responses, **kwargs)


def _fetch(domain):
    return f"Y-tunnus {SHOP_IDS[domain]}"


def _registry(business_id):
    return None


def _candidates(*domains):
    return [Candidate(url=f"https://www.{d}/", domain=d) for d in domains]


def _run(store, candidates, target=100, llm=None, **kwargs):
    return evaluate_candidates(candidates, store, llm or _llm(), _fetch, _registry,
                               target_accept=target, sleep=lambda s: None, **kwargs)


# --- Batch target ---------------------------------------------------------------

def test_stops_when_target_is_reached(store):
    llm = _llm()
    summary = _run(store, _candidates(*SHOP_IDS), target=2, llm=llm)
    assert summary.count(Decision.ACCEPT) == 2
    assert summary.target_reached
    assert llm.calls == 2  # no paid calls after the target is met


def test_target_counts_accepts_from_previous_runs(store):
    _run(store, _candidates("shop-a.invalid", "shop-b.invalid"), target=2)
    llm = _llm()
    summary = _run(store, _candidates("shop-c.invalid", "shop-d.invalid"), target=2, llm=llm)
    assert summary.results == []
    assert summary.target_reached
    assert llm.calls == 0


# --- Duplicates and resume -----------------------------------------------------

def test_duplicate_urls_are_evaluated_once(store):
    candidates = [
        Candidate(url="https://www.shop-a.invalid/", domain="shop-a.invalid"),
        Candidate(url="http://SHOP-A.invalid/sale", domain="SHOP-A.invalid"),
        Candidate(url="https://shop-a.invalid/?utm=x", domain=""),
    ]
    llm = _llm()
    summary = _run(store, candidates, llm=llm)
    assert summary.count(Decision.ACCEPT) == 1
    assert summary.skipped_duplicates == 2
    assert llm.calls == 1


def test_resume_skips_domains_evaluated_in_an_earlier_run(store):
    _run(store, _candidates("shop-a.invalid", "shop-b.invalid"))
    llm = _llm()
    summary = _run(store, _candidates("shop-a.invalid", "shop-b.invalid", "shop-c.invalid"), llm=llm)
    assert summary.skipped_already_evaluated == 2
    assert [r.domain for r in summary.results] == ["shop-c.invalid"]
    assert llm.calls == 1
    assert store.accepted_domains() == {"shop-a.invalid", "shop-b.invalid", "shop-c.invalid"}


def test_ai_error_is_not_stored_so_next_run_retries_it(store):
    down = MockLLMClient({}, fail_first={"shop-a.invalid": 99})
    first = _run(store, _candidates("shop-a.invalid"), llm=down)
    assert first.results[0].decision == Decision.REVIEW
    assert "shop-a.invalid" not in store.evaluated_domains()

    second = _run(store, _candidates("shop-a.invalid"))
    assert second.results[0].decision == Decision.ACCEPT


# --- Error isolation ------------------------------------------------------------

def test_llm_client_bug_for_one_domain_does_not_stop_the_batch(store):
    def crashing_llm(prompt):
        if "shop-b.invalid" in prompt:
            raise KeyError("bug in client code")
        return _llm()(prompt)

    summary = _run(store, _candidates("shop-a.invalid", "shop-b.invalid", "shop-c.invalid"), llm=crashing_llm)
    decisions = {r.domain: r.decision for r in summary.results}
    assert decisions["shop-a.invalid"] == Decision.ACCEPT
    assert decisions["shop-c.invalid"] == Decision.ACCEPT
    assert decisions["shop-b.invalid"] == Decision.REVIEW  # LLM failure -> safe ERROR -> REVIEW


def test_unexpected_exception_in_evaluation_is_logged_and_skipped(store, monkeypatch, caplog):
    import leadfinder.pipeline as pipeline

    real = pipeline.evaluate_one

    def sometimes_crash(candidate, *args, **kwargs):
        if candidate.domain == "shop-b.invalid":
            raise RuntimeError("boom")
        return real(candidate, *args, **kwargs)

    monkeypatch.setattr(pipeline, "evaluate_one", sometimes_crash)
    summary = _run(store, _candidates("shop-a.invalid", "shop-b.invalid", "shop-c.invalid"))
    assert summary.failed == 1
    assert {r.domain for r in summary.results} == {"shop-a.invalid", "shop-c.invalid"}
    assert "shop-b.invalid" in caplog.text


# --- Discovery -----------------------------------------------------------------

@pytest.mark.parametrize("url, bad", [
    ("https://northstarshop.invalid/", False),
    ("https://www.facebook.com/some-page", True),
    ("https://en.wikipedia.org/wiki/Shop", True),
    ("https://blog.northstarshop.invalid/post", True),
    ("https://northstarshop.invalid/blog/new-arrivals", True),
    ("not a url", True),
])
def test_is_bad_url(url, bad):
    assert is_bad_url(url) is bad


def test_discovery_filters_and_deduplicates(store):
    client = FakeSearchClient({
        "decor verkkokauppa": [
            "https://www.shop-a.invalid/x", "http://shop-a.invalid/", "https://www.facebook.com/a",
            "https://shop-b.invalid/",
        ],
    })
    found = discover(store, client, build_queries(["decor"]), max_new_candidates=10)
    assert [c.domain for c in found] == ["shop-a.invalid", "shop-b.invalid"]


def test_discovery_cursor_resumes_from_next_query(store):
    queries = build_queries(["a", "b", "c"])
    client = FakeSearchClient({q: [f"https://shop-{q[0]}.invalid/"] for q in queries})

    discover(store, client, queries, max_new_candidates=1)  # handles query "a" only
    assert store.get_cursor() == 1

    # The next run continues from "b", not from the start of the list.
    discover(store, client, queries, max_new_candidates=10, max_queries=2)
    assert client.calls == ["a verkkokauppa", "b verkkokauppa", "c verkkokauppa"]
    assert store.get_cursor() % len(queries) == 0  # wrapped around, "a" is next


def test_discovery_does_not_store_known_domains_again(store):
    client = FakeSearchClient({"x verkkokauppa": ["https://shop-a.invalid/"]})
    queries = build_queries(["x"])
    assert len(discover(store, client, queries, 10)) == 1
    assert discover(store, client, queries, 10) == []


def test_discovery_retries_transient_search_errors_and_skips_failing_query(store):
    attempts = {"a verkkokauppa": 0, "b verkkokauppa": 0}

    class FlakyClient:
        def search(self, query):
            attempts[query] += 1
            if query == "a verkkokauppa" and attempts[query] < 2:
                raise TransientError("timeout")
            if query == "b verkkokauppa":
                raise TransientError("always down")
            return ["https://shop-a.invalid/"]

    found = discover(store, FlakyClient(), build_queries(["a", "b"]), 10, sleep=lambda s: None)
    assert [c.domain for c in found] == ["shop-a.invalid"]
    assert attempts == {"a verkkokauppa": 2, "b verkkokauppa": 3}  # b: 1 try + 2 retries, then skipped
    assert store.get_cursor() == 2


# --- Export -------------------------------------------------------------------

def test_csv_export_writes_leads_and_review(tmp_path):
    accept = [{"domain": "shop-a.invalid", "company_name": "Shop-A Oy"}]
    review = [{"domain": "shop-b.invalid", "reason": "company not verified"}]
    files = export_results(accept, review, str(tmp_path / "out.csv"))
    assert [os.path.basename(f) for f in files] == ["out_leads.csv", "out_review.csv"]
    with open(files[1], encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["reason"] == "company not verified"


def test_xlsx_export(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = export_results([{"domain": "shop-a.invalid"}], [], str(tmp_path / "leads.xlsx"))[0]
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Leads", "Review"]
    assert wb["Leads"]["A2"].value == "shop-a.invalid"
