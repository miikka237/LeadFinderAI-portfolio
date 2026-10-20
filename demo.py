"""Offline demo of the LeadFinderAI pipeline.

Runs the full flow on fictional data from examples/synthetic_candidates.json:

    search -> filter -> normalize/deduplicate -> AI validation (mocked)
    -> company identification -> ACCEPT / REVIEW / REJECT -> export

No API keys and no network connection are needed.

Usage:
    python demo.py                 # print results, export to output/demo_leads.xlsx
    python demo.py --no-export     # print only
    python demo.py --verbose       # also show pipeline log lines
"""

import argparse
import json
import logging
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from leadfinder.discovery import FakeSearchClient, build_queries, discover, is_bad_url  # noqa: E402
from leadfinder.exporter import export_results  # noqa: E402
from leadfinder.models import Decision  # noqa: E402
from leadfinder.pipeline import evaluate_candidates  # noqa: E402
from leadfinder.storage import Store  # noqa: E402
from leadfinder.validator import MockLLMClient, parse_ai_response  # noqa: E402

DATA_PATH = os.path.join(ROOT, "examples", "synthetic_candidates.json")


def load_data(path=DATA_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline LeadFinderAI demo (synthetic data).")
    parser.add_argument("--no-export", action="store_true", help="do not write an export file")
    parser.add_argument("--verbose", action="store_true", help="show pipeline log output")
    parser.add_argument("--target", type=int, default=10, help="target number of ACCEPT leads")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO if args.verbose else logging.WARNING,
        format="    [log] %(levelname)s %(name)s: %(message)s",
    )

    data = load_data()
    store = Store(":memory:")

    # Offline stand-ins for the real external services.
    search_client = FakeSearchClient(data["search_results"])
    llm = MockLLMClient(data["ai_responses"], fail_first=data.get("ai_transient_failures"))
    pages, registry = data["site_pages"], data["registry"]

    def fetch_page(domain):
        if domain not in pages:
            raise ConnectionError("page not available")
        return pages[domain]

    def lookup_registry(business_id):
        return registry.get(business_id)

    no_wait = lambda seconds: None  # skip real backoff delays in the demo  # noqa: E731

    # --- 1. Discovery -----------------------------------------------------
    print("=" * 72)
    print("1. DISCOVERY (fake search client, synthetic results)")
    print("=" * 72)
    queries = build_queries(data["categories"])
    for query in queries:
        raw = data["search_results"].get(query, [])
        filtered = [u for u in raw if is_bad_url(u)]
        print(f"  query: {query!r}: {len(raw)} results, {len(filtered)} filtered as non-shops")
        for url in filtered:
            print(f"      filtered: {url}")

    candidates = discover(store, search_client, queries, max_new_candidates=50, sleep=no_wait)
    total_kept = sum(len([u for u in data["search_results"].get(q, []) if not is_bad_url(u)]) for q in queries)
    print(f"\n  {len(candidates)} unique candidate domains "
          f"({total_kept - len(candidates)} duplicate URL(s) merged)")

    # --- 2. Evaluation ----------------------------------------------------
    print()
    print("=" * 72)
    print("2. VALIDATION AND DECISION (mocked LLM, offline company lookup)")
    print("=" * 72)

    def show(candidate, result):
        ai = parse_ai_response(data["ai_responses"].get(candidate.domain, ""))
        print(f"\n  discovered : {candidate.url}")
        print(f"  normalized : {candidate.domain}")
        if result.ai_status == "ERROR":
            print("  AI (mock)  : ERROR - answer did not follow the required format")
        else:
            print(f"  AI (mock)  : status={ai.ai_status} webshop={ai.is_real_webshop} "
                  f"consumer_purchase={ai.b2c_purchase_available} model={ai.purchase_model} "
                  f"type={ai.business_type}")
        company = f"{result.company_name} ({result.business_id})" if result.company_name else "-"
        print(f"  company    : {company} -> {result.attribution_status}")
        reason = f"  ({result.reason})" if result.reason else ""
        print(f"  RESULT     : {result.decision.value}{reason}")

    summary = evaluate_candidates(
        candidates, store, llm, fetch_page, lookup_registry,
        target_accept=args.target, sleep=no_wait, on_result=show,
    )

    # --- 3. Summary and export ---------------------------------------------
    print()
    print("=" * 72)
    print("3. SUMMARY")
    print("=" * 72)
    print(f"  ACCEPT: {summary.count(Decision.ACCEPT)}   "
          f"REVIEW: {summary.count(Decision.REVIEW)}   "
          f"REJECT: {summary.count(Decision.REJECT)}   "
          f"(LLM calls incl. retries: {llm.calls})")
    print("  Note: REJECT rows stay in the database only. AI errors are not saved as")
    print("        final results, so they are retried on the next run.")

    if not args.no_export:
        try:
            import openpyxl  # noqa: F401
            out_path = os.path.join(ROOT, "output", "demo_leads.xlsx")
        except ImportError:
            out_path = os.path.join(ROOT, "output", "demo_leads.csv")
        files = export_results(
            store.rows_by_decision(Decision.ACCEPT), store.rows_by_decision(Decision.REVIEW), out_path
        )
        for path in files:
            print(f"  exported: {os.path.relpath(path, ROOT)}")

    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
