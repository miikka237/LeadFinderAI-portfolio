# LeadFinderAI

> This is a sanitized portfolio version of a tool I used in real sales work.
> It contains no real production data, no API keys and no client-specific
> rules. All example companies and websites are fictional.

LeadFinderAI is a Python program that finds Finnish online stores and checks
whether they are good sales leads before anyone calls them.

```
search -> remove bad and duplicate results -> AI check -> company check
       -> ACCEPT / REVIEW / REJECT -> export to Excel
```

**Try it (no API keys or internet needed):**

```bash
pip install -r requirements.txt
python demo.py      # runs the whole flow on fictional example data
pytest              # runs the tests
```

## Why I built it

I worked on a phone sales campaign aimed at Finnish companies that sell
online. Many of the leads we got did not fit. Some companies had no online
store at all, some sold only to other businesses, and some only accepted
quote requests. Every bad lead wasted a call.

I wanted the program to answer one question before a lead reached a caller:

*Is this a Finnish company with a real online store where normal consumers
can buy, and which company is behind it?*

## What it does

1. **Search.** It searches the web by product category, for example
   "outdoor equipment online store", and collects the result links.
2. **Remove bad and duplicate results.** It drops links that are clearly not
   shops, such as social media, Wikipedia or blogs. It shortens each link to
   the website name and removes duplicates, including websites already
   checked in earlier runs.
3. **AI check.** For each website, an AI model answers a fixed list of
   questions with fixed answer options: Is it a real online store? Can
   consumers buy there? Does it only take quote requests? Which company runs
   it, and what is its Business ID (Y-tunnus)?
4. **Company check.** The program does not just trust the AI's answer about
   the company. It checks that the Business ID has a valid format, and that
   the ID or the company name can be found on the website and in the official
   Finnish company register (PRH/YTJ).
5. **Decision.** Simple rules written in Python give each website one result:
   - **ACCEPT** – everything is clearly positive and the company is confirmed.
   - **REVIEW** – something is unclear, so a person should look at it.
   - **REJECT** – there is a clear reason it is not a good lead, for example
     consumers cannot buy there or the company information does not match.
6. **Export.** Accepted leads and REVIEW cases are saved to an Excel file on
   separate sheets.

A few practical rules I set:

- The AI only reports facts. The Python rules make the final decision. This
  made it easier to see whether a wrong result came from the AI or from my
  rules.
- If the AI's answer is unclear or broken, the result is REVIEW, never
  ACCEPT or REJECT.
- Company size does not matter. A big chain with a real online store is
  still a valid lead.
- Results and progress are saved in a SQLite database. The program remembers
  where it stopped, so a long run can continue later.
- Successful AI checks are saved, so the same website does not usually need
  to be checked (and paid for) again.
- The run stops when it has found the number of accepted leads I asked for.
- If one website causes an error, it is written to the log and the program
  moves on to the next one.

## My role

- I noticed the problem myself in my sales work.
- I decided what makes a useful lead and which facts should lead to ACCEPT,
  REVIEW or REJECT.
- I used Claude Code as a development tool. I gave it tasks and described
  what I wanted the program to do.
- I reviewed the results, ran the tests and asked for changes when something
  did not work the way I wanted.
- I investigated wrong results and errors using the logs and the saved data.
- I changed the system step by step based on what happened in real runs.

## What was difficult

- **Getting usable answers from the AI.** Free-text answers were hard to use
  in code. Giving the AI a fixed answer format with fixed options made the
  answers much easier to read and test.
- **Finding out who runs a website.** The AI sometimes gave the wrong company
  or Business ID. That is why the company check against the website and the
  register was added.
- **Cost and stopped runs.** Searches and AI checks cost money, and long runs
  sometimes stopped halfway. Saving results and continuing from where the
  program stopped came from this.
- **Search quality.** Many search results were directories, news articles or
  social media pages. Filtering them out and trying different search phrases
  took several rounds.

## Tests

```bash
pytest
```

This public version has about 70 automated tests. The production version
has over 800.

The tests run without internet or API keys. Instead of real search, AI and
company register calls, they use fake versions that return prepared answers.

The tests check things like: good online stores get ACCEPT, business-only and
quote-only sites get REJECT, unclear AI answers get REVIEW, duplicates are
removed, the run stops at the target number of leads, and a stopped run can
continue.

## Demo

`python demo.py` runs the whole flow on fictional data from
[`examples/synthetic_candidates.json`](examples/synthetic_candidates.json).
The AI answers are prepared in advance. Simplified example of the results:

```
demo-outdoor.invalid
Company: Demo Outdoor Oy
Result: ACCEPT

sample-furniture.invalid
Reason: quote-only site
Result: REJECT

mossy-market.invalid
Reason: AI answer was unclear
Result: REVIEW

Summary: 2 ACCEPT / 3 REVIEW / 4 REJECT
```

Options: `--no-export` (print only), `--verbose` (show more log lines).

## Technologies

- **Python 3.10+**
- **SQLite** for saving results and progress
- **Python logging** for finding errors
- **openpyxl** for the Excel export
- **pytest** for the automated tests
- In production: **SerpAPI** for search results and AI-assisted website checks,
  `requests` for loading web pages, and the **PRH/YTJ** open data API for
  company information. In this repository these are replaced with fake
  offline versions.
- **Claude Code** as a development tool

## Privacy / sanitized portfolio note

This is a sanitized portfolio version written for publication. It is not a
copy of the production code.

- **No real production data.** No databases, Excel files, logs or lead lists
  from real runs.
- **No API keys or credentials.** The demo and tests need none.
- **Fictional examples.** All example companies, Business IDs and candidate
  websites are made up. The websites end in `.invalid`, which is never used
  by real websites.
- **Public websites only in filtering examples.** Well-known sites like
  Facebook may appear only to show that they are filtered out.
- **Simplified.** Campaign-specific rules and real search lists were removed.
  The production system has more parts, but the main idea and flow are the
  same.
