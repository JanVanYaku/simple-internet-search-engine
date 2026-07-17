#######################################################################
# Author: Lehlohonolo Adolf Matobakele
# Email: lehlohonolo.matobakele@gov.ls
# Contacxt: 00266 62320704
#######################################################################

"""Simple command-line internet search engine."""

from __future__ import annotations

import argparse
import csv
import json
import unicodedata
import webbrowser
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()


SEARCH_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "SimpleInternetSearchEngine/1.0 (+https://github.com/JanVanYaku)"
DEFAULT_RESULT_LIMIT = 5


@dataclass
class SearchResult:
    """One search result item."""

    rank: int
    title: str
    url: str
    domain: str
    snippet: str


@dataclass
class SearchReport:
    """Serializable search report."""

    generated_at: str
    query: str
    result_count: int
    results: list[SearchResult]
    explanation: str


def clean_text(value: str) -> str:
    """Normalize whitespace for terminal output."""

    replacements = {
        "\u00a0": " ",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
    for original, replacement in replacements.items():
        value = value.replace(original, replacement)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(value.split()).strip()


def clean_result_url(url: str) -> str:
    """Resolve DuckDuckGo redirect URLs to the original result URL."""

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return unquote(query["uddg"][0])
    return url


def domain_from_url(url: str) -> str:
    """Return a readable domain name from a URL."""

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or "unknown"


def domain_matches(domain: str, site: str) -> bool:
    """Return True when a result domain belongs to the requested site."""

    normalized_domain = domain.lower().removeprefix("www.")
    normalized_site = site.lower().removeprefix("www.")
    return normalized_domain == normalized_site or normalized_domain.endswith(f".{normalized_site}")


def renumber_results(results: list[SearchResult]) -> list[SearchResult]:
    """Reset result ranks after filtering."""

    return [
        SearchResult(
            rank=index,
            title=result.title,
            url=result.url,
            domain=result.domain,
            snippet=result.snippet,
        )
        for index, result in enumerate(results, start=1)
    ]


def search_web(query: str, limit: int, timeout: float) -> list[SearchResult]:
    """Search the web using DuckDuckGo HTML results."""

    session = requests.Session()
    response = session.post(
        SEARCH_URL,
        data={"q": query},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    raw_results = soup.select(".result")
    results: list[SearchResult] = []

    for result in raw_results:
        title_node = result.select_one(".result__title a")
        snippet_node = result.select_one(".result__snippet")
        if not title_node:
            continue

        title = clean_text(title_node.get_text(" "))
        href = title_node.get("href") or ""
        url = clean_result_url(href)
        if not title or not url:
            continue

        snippet = clean_text(snippet_node.get_text(" ")) if snippet_node else ""
        results.append(
            SearchResult(
                rank=len(results) + 1,
                title=title,
                url=url,
                domain=domain_from_url(url),
                snippet=snippet,
            )
        )
        if len(results) >= limit:
            break

    return results


def explain_results(query: str, results: list[SearchResult]) -> str:
    """Create a short human-readable explanation of the search results."""

    if not results:
        return (
            f"No results were found for '{query}'. Check spelling, try fewer words, "
            "or search for a more specific phrase."
        )

    domain_counts = Counter(result.domain for result in results)
    top_domains = ", ".join(f"{domain} ({count})" for domain, count in domain_counts.most_common(3))
    first = results[0]
    official_hint = ""
    lowered_query = query.lower()
    if any(word in first.domain for word in lowered_query.split() if len(word) > 3):
        official_hint = " The first result domain appears related to the query, so it may be a good starting point."

    return (
        f"Found {len(results)} result(s) for '{query}'. The top result is from {first.domain}: "
        f"'{first.title}'. Common domains in this result set: {top_domains}."
        f"{official_hint} Review the top few results and prefer official or primary sources when accuracy matters."
    )


def render_results(query: str, results: list[SearchResult]) -> None:
    """Print search results in a table."""

    table = Table(title=f"Search Results for: {query}", show_lines=True)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Title", overflow="fold")
    table.add_column("Domain", style="magenta")
    table.add_column("Snippet", overflow="fold")
    table.add_column("URL", overflow="fold")

    if not results:
        table.add_row("-", "No results found", "-", "-", "-")
    for result in results:
        table.add_row(
            str(result.rank),
            result.title,
            result.domain,
            result.snippet or "-",
            result.url,
        )
    console.print(table)


def write_json_report(path: Path, report: SearchReport) -> None:
    """Write a JSON report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")


def write_csv_report(path: Path, results: list[SearchResult]) -> None:
    """Write search results as CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["rank", "title", "url", "domain", "snippet"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def prompt_for_query() -> str:
    """Ask for a query when the user did not provide one."""

    try:
        return input("Search for: ").strip()
    except EOFError:
        return ""


def build_parser() -> argparse.ArgumentParser:
    """Build command-line options."""

    parser = argparse.ArgumentParser(description="Simple command-line internet search engine.")
    parser.add_argument("query", nargs="*", help="Words to search for. If omitted, the app prompts you.")
    parser.add_argument(
        "--limit",
        type=int,
        help=f"Number of results to show. Default: {DEFAULT_RESULT_LIMIT}.",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds.")
    parser.add_argument("--site", help="Restrict search to a domain, for example wikipedia.org.")
    parser.add_argument("--open-first", action="store_true", help="Open the first result in your browser.")
    parser.add_argument("--json-out", type=Path, help="Save JSON report.")
    parser.add_argument("--csv-out", type=Path, help="Save CSV results.")
    return parser


def main() -> int:
    """CLI entry point."""

    args = build_parser().parse_args()
    base_query = " ".join(args.query).strip() or prompt_for_query()
    if not base_query:
        console.print("[red]Please enter something to search for.[/red]")
        return 1

    query = base_query
    if args.site:
        query = f"{query} site:{args.site}"

    limit = args.limit if args.limit is not None else DEFAULT_RESULT_LIMIT
    if limit < 1:
        console.print("[red]--limit must be 1 or greater.[/red]")
        return 1
    console.print(
        Panel(
            f"Query: [bold]{query}[/bold]\nLimit: [bold]{limit}[/bold]\nSource: DuckDuckGo HTML results",
            title="Simple Internet Search",
            border_style="cyan",
        )
    )

    try:
        results = search_web(query, limit=limit, timeout=max(args.timeout, 3.0))
        if args.site:
            results = [result for result in results if domain_matches(result.domain, args.site)]
            if not results:
                fallback = search_web(base_query, limit=limit * 3, timeout=max(args.timeout, 3.0))
                results = [result for result in fallback if domain_matches(result.domain, args.site)][:limit]
            results = renumber_results(results[:limit])
    except requests.RequestException as exc:
        console.print(f"[red]Search request failed:[/red] {exc}")
        return 1

    explanation = explain_results(query, results)
    render_results(query, results)
    console.print(Panel(explanation, title="Result Explanation", border_style="blue"))

    report = SearchReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        query=query,
        result_count=len(results),
        results=results,
        explanation=explanation,
    )
    if args.json_out:
        write_json_report(args.json_out.resolve(), report)
        console.print(f"[green]JSON report saved to {args.json_out.resolve()}[/green]")
    if args.csv_out:
        write_csv_report(args.csv_out.resolve(), results)
        console.print(f"[green]CSV report saved to {args.csv_out.resolve()}[/green]")
    if args.open_first and results:
        webbrowser.open(results[0].url)
        console.print(f"[green]Opened first result:[/green] {results[0].url}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Search interrupted by user.[/yellow]")
        raise SystemExit(130)
