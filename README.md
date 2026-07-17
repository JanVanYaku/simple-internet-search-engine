# Simple Internet Search Engine

A beginner-friendly Python command-line search engine. Type a name, title, question, or topic, and the app searches the internet, prints results in a clean table, and gives a short explanation of what the results suggest.

It uses DuckDuckGo's lightweight HTML results and does not require an API key.

## Features

- Search the internet from PowerShell.
- Prompt for a query if you do not type one.
- Display title, domain, snippet, and URL.
- Explain the result set in plain language.
- Restrict searches to a specific website with `--site`.
- Save JSON and CSV reports.
- Optionally open the first result in your browser.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

Search for anything:

```powershell
python .\simple_search_engine.py "Lehlohonolo Adolf Matobakele"
```

If you do not specify `--limit`, the app shows 5 results by default.

Search for a title or topic:

```powershell
python .\simple_search_engine.py "Python web scraping tutorial" --limit 12
```

Prompt mode:

```powershell
python .\simple_search_engine.py
```

Restrict to one site:

```powershell
python .\simple_search_engine.py "Python beginners" --site python.org
```

Save reports:

```powershell
python .\simple_search_engine.py "OpenAI Codex" --json-out .\reports\search.json --csv-out .\reports\search.csv
```

Open the first result:

```powershell
python .\simple_search_engine.py "OpenAI" --open-first
```

## Understanding Results

- The table shows the returned search results in rank order.
- The domain column helps you quickly see where the result came from.
- The snippet is a short preview from the search result page.
- The explanation summarizes the top result and common domains.
- For important facts, open the original pages and prefer official or primary sources.
