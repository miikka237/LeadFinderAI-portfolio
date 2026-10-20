# LeadFinderAI

> **This repository is a sanitized portfolio version of a system used in real
> sales work. Production data, credentials and client-specific logic have been
> removed.** All company names, domains and Business IDs in this repository are
> fictional.

LeadFinderAI started from a practical problem in my sales work: many leads I
received did not even operate an online store, although the campaign targeted
ecommerce companies.

I built a Python/AI system to find and validate better leads before they
reached the calling team.

```
Search → candidate domains → clean-up and duplicate removal
       → AI-assisted check → company identification
       → final decision (ACCEPT / REVIEW / REJECT) → export
```

**Quick start (no API keys, no internet connection needed):**

```bash
pip install -r requirements.txt
python demo.py      # runs the whole flow on fictional example data
pytest              # runs the tests
```

---

## Why I built it

I worked on a phone sales campaign aimed at Finnish companies that sell online.
Many of the leads we received did not fit: some companies had no online store
at all, some sold only to other businesses, and some only accepted quote
requests. Every bad lead cost a call.

I wanted to answer one question automatically, before a lead reached a caller:

*Is this a Finnish company with a real online store where ordinary consumers
can buy, and which company exactly is behind it?*

The production version of this system was used in real sales work.

## What it does

1. **Finds candidates.** It runs web searches by product category, for example
   "outdoor equipment online store", and collects the result links.
2. **Cleans the list.** It removes links that are clearly not shops (social
   media, Wikipedia, blogs), reduces every link to a plain domain name such as
   `example-shop.invalid`, and removes duplicates, including domains already
   handled in earlier runs.
3. **Asks an AI model for facts.** For each domain, a large language model
   (LLM) answers a fixed set of questions in a fixed format: Is it a real
   online store? Can consumers buy there? Does it only take quote requests or
   sell only to businesses? Which company runs it, and what is its Finnish
   Business ID (Y-tunnus)?
4. **Checks the company.** The AI's answer about the company is not trusted
   as such. The Business ID must have a valid check digit and appear on the
   shop's own pages, or the company name must appear on the site and match
   the official company register.
5. **Decides.** Simple Python rules turn the facts into ACCEPT, REVIEW or
   REJECT.
6. **Exports.** Accepted leads and cases that need a human check are written
   to an Excel file, on separate sheets.

## How it works

### The AI reports facts, the code makes the decision

The AI is never asked "is this a good lead?". It is asked factual questions
and may only answer with specific allowed values:

```
AI_STATUS: OK | NO_DATA | AMBIGUOUS | ERROR
IS_REAL_WEBSHOP: YES | NO | UNKNOWN
B2C_PURCHASE_AVAILABLE: YES | NO | UNKNOWN      (can consumers buy?)
PURCHASE_MODEL: real_time_purchase | quote_only | presentation_only | ...
BUSINESS_TYPE: independent_b2c | chain | b2b_only | marketplace | ...
COMPANY_NAME: ...
BUSINESS_ID: ...
```

A separate Python function, covered by tests, makes the decision from these
facts ([`decision.py`](src/leadfinder/decision.py)). This made problems
easier to find: when a result was wrong, I could see whether the AI's facts
were wrong or the rule was wrong.

### Unclear cases go to a person

- If the AI's answer is missing, badly formatted or unsure, the program
  treats the facts as `UNKNOWN` or `ERROR`. It never guesses a positive value.
- Uncertainty never leads to REJECT. It leads to **REVIEW**, and a person
  decides.
- REJECT needs a clear negative fact, for example "consumers cannot buy" or
  "quote requests only", or company information that contradicts itself.
- ACCEPT needs every fact to be clearly positive *and* a confirmed company
  with a valid Business ID.
- Company size is not part of the rules. A large chain with a real consumer
  online store is a valid lead.

### Checking which company runs the site

The AI might say "this site is run by Example Oy, 9900001-8". That claim is
checked:

| What the check finds | Result |
|---|---|
| The Business ID has an invalid check digit | `INVALID_BUSINESS_ID` → REJECT |
| The site shows a *different* Business ID | `CONFLICT` → REJECT |
| The register lists the ID under a different company name | `CONFLICT` → REJECT |
| The site shows the claimed Business ID | `VERIFIED` |
| The company name is on the site *and* the register agrees | `VERIFIED` |
| Only the register agrees | `INSUFFICIENT_EVIDENCE` → REVIEW |

A match in the register alone is not enough. It shows that the company and
the ID belong together, but not that this company runs this website.

### Long runs can be stopped and continued

Searches and AI calls cost money, and a run can stop halfway. So:

- The program **remembers which search it should run next** and continues
  from there.
- **AI answers are saved** per domain, so the same domain is never paid for
  twice. Failed answers are not saved, so they are tried again next time.
- A run **stops when it has found the target number of accepted leads**,
  counting leads found in earlier runs too.
- **One failing domain does not stop the run.** The error is logged and the
  program moves on.
- Calls to outside services are **retried only for temporary problems**
  such as timeouts. Problems that a retry cannot fix, such as an invalid API
  key, stop immediately instead of wasting paid calls.

## My role

- I noticed the business problem myself in my sales work.
- I designed what a useful lead should look like: which facts mean ACCEPT,
  REVIEW or REJECT.
- I used Claude Code actively as a development tool. I defined tasks and
  acceptance criteria, reviewed the changes it produced, ran tests, and asked
  for corrections when the implementation did not match what I wanted.
- I investigated errors from the logs and checked the quality of the search
  results.
- I improved the system step by step based on real results.

## What was difficult

- **Getting usable answers from the AI.** Free-form answers were hard to use
  in code. A fixed answer format with allowed values, and a parser that treats
  anything unexpected as unknown, made the answers predictable and testable.
- **Finding out who runs a website.** The AI's answer about the company and
  its Business ID was not always right, so it had to be checked against the
  site itself and the company register.
- **Cost and interrupted runs.** Search and AI calls cost money, and runs
  could stop halfway. Saving answers, remembering the search position and
  stopping at a target number of leads all came from this.
- **Search quality.** Many search results are directories, news articles or
  social media pages. Filtering them and comparing different kinds of search
  queries took several rounds.

## Testing

```bash
pytest
```

The tests run without internet access or API keys. The outside services
(search, AI, website fetch, company register) are replaced with fake
versions that return prepared answers.

This public repository contains about 70 tests. The production version has a
larger test suite (800+ tests). The tests here cover:

| Area | Examples |
|---|---|
| Accepting valid candidates | a clear consumer online store with a confirmed company is accepted; a large chain is not rejected for its size |
| Rejecting invalid candidates | business-only, quote-only, consumers cannot buy, conflicting Business ID, invalid check digit |
| Preventing duplicates | the same shop under different links is checked once; known domains are not saved again |
| Cleaning domain names | `https://WWW.Example-Shop.invalid/path?x=1` → `example-shop.invalid`, subdomains, broken input |
| Unclear AI answers | free text, missing fields, unknown values and `AMBIGUOUS` all lead to REVIEW, never ACCEPT or REJECT |
| Target number of leads | stops at the target; counts leads from earlier runs; no AI calls after the target is reached |
| Retries and errors | temporary errors are retried, permanent errors are not, one crashing domain does not stop the run |
| Continuing a run | search continues from the next query; already checked domains are skipped; saved AI answers are reused |

## Example run

`python demo.py` runs the whole flow on the fictional data in
[`examples/synthetic_candidates.json`](examples/synthetic_candidates.json).
The AI answers are prepared in advance, and one simulated timeout shows the
retry in action.

```
========================================================================
1. DISCOVERY (fake search client, synthetic results)
========================================================================
  query: 'outdoor equipment verkkokauppa': 4 results, 2 filtered as non-shops
      filtered: https://www.facebook.com/demo-outdoor-page
      filtered: https://blog.trailguide.invalid/best-tents-2024
  ...
  9 unique candidate domains (1 duplicate URL(s) merged)

========================================================================
2. VALIDATION AND DECISION (mocked LLM, offline company lookup)
========================================================================

  discovered : https://www.demo-outdoor.invalid/tents?ref=search
  normalized : demo-outdoor.invalid
  AI (mock)  : status=OK webshop=YES consumer_purchase=YES model=real_time_purchase type=independent_b2c
  company    : Demo Outdoor Oy (9900002-6) -> VERIFIED
  RESULT     : ACCEPT
    [log] WARNING leadfinder.validator: AI retry 1 for northstarshop.invalid: simulated timeout
  ...

  discovered : https://sample-furniture.invalid/
  normalized : sample-furniture.invalid
  AI (mock)  : status=OK webshop=NO consumer_purchase=UNKNOWN model=quote_only type=independent_b2c
  company    : Sample Furniture Oy (9900006-9) -> VERIFIED
  RESULT     : REJECT  (purchase model quote_only)

  discovered : https://www.brightdesk.invalid/chairs
  normalized : brightdesk.invalid
  AI (mock)  : status=OK webshop=YES consumer_purchase=YES model=real_time_purchase type=independent_b2c
  company    : Brightdesk Oy (9900004-2) -> CONFLICT
  RESULT     : REJECT  (company check: CONFLICT)

  ...

  discovered : https://mossy-market.invalid/
  normalized : mossy-market.invalid
  AI (mock)  : ERROR - answer did not follow the required format
  company    : - -> INSUFFICIENT_EVIDENCE
  RESULT     : REVIEW  (AI status ERROR: no reliable facts)
  ...

========================================================================
3. SUMMARY
========================================================================
  ACCEPT: 2   REVIEW: 3   REJECT: 4   (LLM calls incl. retries: 10)
  Note: REJECT rows stay in the database only. AI errors are not saved as
        final results, so they are retried on the next run.
  exported: output/demo_leads.xlsx
```

Options: `--no-export` (print only), `--verbose` (show more log lines).

## Project structure

```
README.md
requirements.txt
pyproject.toml              pytest settings
demo.py                     offline demo of the whole flow
examples/
    synthetic_candidates.json   fictional search results, AI answers, web pages, register
src/leadfinder/
    models.py               data classes: Candidate, AIAssessment, LeadResult, Decision
    discovery.py            search queries, filtering out non-shops, remembering search position
    normalization.py        cleaning domain names and removing duplicates
    validator.py            AI question, strict answer reading, saving answers
    business_id.py          Finnish Business ID (Y-tunnus) check digit
    identification.py       checks the claimed company against the site and the register
    decision.py             ACCEPT / REVIEW / REJECT rules
    retry.py                retrying temporary errors
    storage.py              SQLite database: candidates, search position, AI answers, results
    pipeline.py             runs the checks for a batch of candidates
    exporter.py             Excel export (Leads and Review sheets) or CSV
tests/
    test_normalization.py   domain names, duplicates, Business ID check digit
    test_validator.py       reading AI answers, unclear answers, retries, company check
    test_decision.py        decision rules
    test_pipeline.py        target, duplicates, continuing runs, errors, search, export
    test_demo.py            the demo runs from start to finish
```

The outside services (search, AI, web page fetch, company register) are
passed into the code as ordinary functions. That is why the same code can
run with real services in production and with fake ones in the tests and the
demo.

## Technologies

- **Python 3.10+** and its standard library: `sqlite3`, `dataclasses`,
  `logging`, `re`, `urllib`
- **openpyxl** for the Excel export
- **pytest** for the tests
- In production: SerpAPI for Google search results, Google AI Mode (through
  SerpAPI) as the AI model that researches each site, `requests` for fetching
  web pages, and the open data API of the Finnish company register (PRH/YTJ).
  In this repository, all of these are replaced with offline fake versions.
- **Claude Code** as a development tool

## Privacy / sanitization note

This repository is a sanitized portfolio version. It was written for
publication and is not a copy of the production code.

- **No real data.** All companies, domains and Business IDs are fictional.
  Domains end in `.invalid`, which is reserved for examples and never used by
  real websites. Business IDs are fictional, checksum-valid examples used only
  to demonstrate the validation logic.
- **No credentials.** No API keys, `.env` files or passwords. The demo and
  tests need none.
- **No production results.** No databases, Excel files, logs or lead lists
  from real runs.
- **No client-specific logic.** Campaign-specific rules, exclusion lists,
  company blocklists and the real search query lists have been removed or
  replaced with simple examples.
- **Simplified.** The production system has more parts, such as several
  generations of search strategies, multiple result pages per search, more
  detailed checks of website pages, usage statistics and more detailed saving
  of results. This repository keeps the main structure and ideas in a form
  that can be read in a few minutes. It is not an exact copy of the
  production system.
