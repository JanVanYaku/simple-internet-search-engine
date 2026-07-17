# Simple Internet Search Engine

A beginner-friendly Python command-line search engine for simple open-source intelligence (OSINT) gathering. Type a name, title, company, topic, or question, then narrow the search with dork-style options such as exact phrases, site filters, file types, title words, URL words, excluded words, and date hints.

The app can search DuckDuckGo, Bing, or both. It prints results in a clean table and gives a short explanation of what the result set suggests.

Use it responsibly: search public information, respect privacy, and verify important claims from primary sources.

## Features

- Search from PowerShell.
- Prompt for a query if you do not type one.
- Use DuckDuckGo, Bing, or both engines with `--engine`.
- Narrow searches with `--exact`, `--any`, `--must`, `--exclude`, `--site`, `--filetype`, `--intitle`, `--inurl`, `--after`, and `--before`.
- Use OSINT presets for people, companies, news, documents, and public social/profile results.
- Display engine, title, domain, snippet, and URL.
- Explain the result set in plain language.
- Save JSON and CSV reports.
- Optionally open the first result in your browser.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Basic Search

If you do not specify `--limit`, the app shows 5 results by default.

```powershell
python .\simple_search_engine.py "OpenAI Codex"
```

Specify your own result limit:

```powershell
python .\simple_search_engine.py "Python web scraping tutorial" --limit 12
```

Use Bing:

```powershell
python .\simple_search_engine.py "OpenAI Codex" --engine bing
```

Use all supported engines:

```powershell
python .\simple_search_engine.py "OpenAI Codex" --engine all --limit 10
```

## Narrow Searches

Exact phrase:

```powershell
python .\simple_search_engine.py "cybersecurity training" --exact "beginner course"
```

Require and exclude words:

```powershell
python .\simple_search_engine.py "python requests" --must documentation --exclude jobs
```

Search one site:

```powershell
python .\simple_search_engine.py "Python beginners" --site python.org
```

Search public PDF documents:

```powershell
python .\simple_search_engine.py "annual report" --filetype pdf
```

Look for words in a page title or URL:

```powershell
python .\simple_search_engine.py "privacy policy" --intitle privacy --inurl policy
```

Use broad date hints where the search engine supports them:

```powershell
python .\simple_search_engine.py "AI regulation" --after 2025-01-01 --before 2026-01-01
```

## OSINT Presets

Person-oriented public profile search:

```powershell
python .\simple_search_engine.py "Jane Doe" --preset person --exact "Jane Doe" --engine all
```

Company-oriented search:

```powershell
python .\simple_search_engine.py "OpenAI" --preset company --engine all
```

News-oriented search:

```powershell
python .\simple_search_engine.py "OpenAI Codex" --preset news --engine all
```

Public document search:

```powershell
python .\simple_search_engine.py "security report" --preset documents --engine all
```

Public profile/social-domain search:

```powershell
python .\simple_search_engine.py "OpenAI" --preset social --engine all
```

Show the final built dork query:

```powershell
python .\simple_search_engine.py "OpenAI Codex" --preset news --site openai.com --show-query
```

## Reports

Save reports:

```powershell
python .\simple_search_engine.py "OpenAI Codex" --engine all --json-out .\reports\search.json --csv-out .\reports\search.csv
```

Open the first result:

```powershell
python .\simple_search_engine.py "OpenAI" --open-first
```

## Understanding Results

- The table shows returned results in rank order after duplicate URLs are removed.
- The engine column shows where the result was found.
- The domain column helps you quickly see the source.
- The snippet is a short preview from the search result page.
- The explanation summarizes top domains, engine coverage, and applied narrowing.
- For important facts, open the original pages and prefer official or primary sources.

## Safety Notes

This project is intended for lawful public-source research. It does not include credential-hunting presets, scraping behind logins, bypassing access controls, or collecting private information from non-public systems.
