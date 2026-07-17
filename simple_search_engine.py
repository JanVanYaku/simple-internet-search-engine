#######################################################################
# Author: Lehlohonolo Adolf Matobakele
# Email: lehlohonolo.matobakele@gov.ls
# Contacxt: 00266 62320704
#######################################################################

"""Simple OSINT-focused command-line internet search engine."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import unicodedata
import webbrowser
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()


DUCKDUCKGO_SEARCH_URL = "https://html.duckduckgo.com/html/"
BING_SEARCH_URL = "https://www.bing.com/search"
USER_AGENT = "SimpleInternetSearchEngine/2.0 (+https://github.com/JanVanYaku)"
DEFAULT_RESULT_LIMIT = 5
SUPPORTED_ENGINES = {
    "duckduckgo": "DuckDuckGo",
    "bing": "Bing",
}


PRESET_DESCRIPTIONS = {
    "general": "No extra OSINT terms.",
    "person": "Public profile, biography, interview, and about-page signals.",
    "company": "Official, leadership, contact, profile, and report signals.",
    "news": "News, report, update, announcement, and interview signals.",
    "documents": "Public PDF documents and reports.",
    "social": "Public social/profile domains.",
}

PRESET_QUERY_PARTS = {
    "general": [],
    "person": ['(profile OR biography OR interview OR "about")'],
    "company": ['(official OR "about us" OR leadership OR contact OR profile OR report)'],
    "news": ["(news OR report OR update OR announcement OR interview)"],
    "documents": ["filetype:pdf"],
    "social": ["(site:linkedin.com OR site:github.com OR site:x.com OR site:facebook.com OR site:instagram.com)"],
}


@dataclass
class SearchResult:
    """One search result item."""

    rank: int
    engine: str
    title: str
    url: str
    domain: str
    snippet: str


@dataclass
class SearchReport:
    """Serializable search report."""

    generated_at: str
    query: str
    built_query: str
    engines: list[str]
    narrowing: dict[str, object]
    result_count: int
    results: list[SearchResult]
    explanation: str
    engine_errors: list[str]


def clean_text(value: str) -> str:
    """Normalize text for reliable Windows terminal output."""

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
    """Resolve search-engine redirect URLs to the original result URL when possible."""

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return clean_text(unquote(query["uddg"][0]))
    if parsed.netloc.lower().endswith("bing.com") and "u" in query:
        decoded = decode_bing_redirect(query["u"][0])
        if decoded:
            return clean_text(decoded)
    return clean_text(url)


def decode_bing_redirect(value: str) -> str:
    """Decode Bing's base64-style redirect target when present."""

    candidate = unquote(value)
    if candidate.startswith("a1"):
        candidate = candidate[2:]
    candidate = candidate.replace("-", "+").replace("_", "/")
    candidate += "=" * (-len(candidate) % 4)
    try:
        decoded = base64.b64decode(candidate).decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return ""
    if decoded.startswith(("http://", "https://")):
        return decoded
    return ""


def normalize_url(url: str) -> str:
    """Normalize a URL for duplicate detection."""

    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower().removeprefix("www."),
            path,
            "",
            parsed.query,
            "",
        )
    )


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


def flatten_values(values: list[str] | None) -> list[str]:
    """Split comma-separated CLI values while preserving normal phrases."""

    flattened: list[str] = []
    for value in values or []:
        for part in value.split(","):
            item = part.strip()
            if item:
                flattened.append(item)
    return flattened


def quote_operator_value(value: str) -> str:
    """Quote search operator values that contain spaces."""

    value = clean_text(value)
    if not value:
        return value
    if value.startswith('"') and value.endswith('"'):
        return value
    if any(char.isspace() for char in value):
        return f'"{value}"'
    return value


def build_or_group(operator: str, values: list[str]) -> str:
    """Build a single search operator or an OR group for repeated values."""

    parts = [f"{operator}:{quote_operator_value(value)}" for value in values]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def parse_engines(value: str | None) -> list[str]:
    """Parse --engine values such as 'duckduckgo', 'bing', or 'all'."""

    requested = flatten_values([value or "duckduckgo"])
    requested = [item.lower() for item in requested]
    if "all" in requested:
        return list(SUPPORTED_ENGINES)

    invalid = [item for item in requested if item not in SUPPORTED_ENGINES]
    if invalid:
        valid = ", ".join([*SUPPORTED_ENGINES, "all"])
        raise argparse.ArgumentTypeError(f"Unsupported engine: {', '.join(invalid)}. Choose: {valid}.")

    engines: list[str] = []
    for item in requested:
        if item not in engines:
            engines.append(item)
    return engines


def build_osint_query(
    base_query: str,
    args: argparse.Namespace,
    include_sites: bool = True,
) -> tuple[str, dict[str, object]]:
    """Build a narrowed OSINT query from CLI options."""

    exact_terms = flatten_values(args.exact)
    any_terms = flatten_values(args.any)
    must_terms = flatten_values(args.must)
    excluded_terms = flatten_values(args.exclude)
    sites = flatten_values(args.site)
    filetypes = [item.lstrip(".").lower() for item in flatten_values(args.filetype)]
    intitle_terms = flatten_values(args.intitle)
    inurl_terms = flatten_values(args.inurl)

    parts: list[str] = []
    if base_query:
        parts.append(clean_text(base_query))
    parts.extend(f'"{clean_text(term)}"' for term in exact_terms if clean_text(term))
    parts.extend(f"+{quote_operator_value(term)}" for term in must_terms if clean_text(term))

    if any_terms:
        parts.append("(" + " OR ".join(quote_operator_value(term) for term in any_terms) + ")")

    parts.extend(f"-{quote_operator_value(term)}" for term in excluded_terms if clean_text(term))

    if include_sites and sites:
        parts.append(build_or_group("site", sites))
    if filetypes:
        parts.append(build_or_group("filetype", filetypes))
    if intitle_terms:
        parts.append(build_or_group("intitle", intitle_terms))
    if inurl_terms:
        parts.append(build_or_group("inurl", inurl_terms))
    if args.after:
        parts.append(f"after:{clean_text(args.after)}")
    if args.before:
        parts.append(f"before:{clean_text(args.before)}")

    parts.extend(PRESET_QUERY_PARTS.get(args.preset, []))

    narrowing = {
        "preset": args.preset,
        "preset_description": PRESET_DESCRIPTIONS.get(args.preset, ""),
        "exact": exact_terms,
        "any": any_terms,
        "must": must_terms,
        "exclude": excluded_terms,
        "site": sites,
        "filetype": filetypes,
        "intitle": intitle_terms,
        "inurl": inurl_terms,
        "after": args.after,
        "before": args.before,
    }
    return " ".join(part for part in parts if part), narrowing


def search_duckduckgo(query: str, limit: int, timeout: float) -> list[SearchResult]:
    """Search DuckDuckGo HTML results."""

    response = requests.post(
        DUCKDUCKGO_SEARCH_URL,
        data={"q": query},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[SearchResult] = []
    for result in soup.select(".result"):
        title_node = result.select_one(".result__title a")
        snippet_node = result.select_one(".result__snippet")
        if not title_node:
            continue

        title = clean_text(title_node.get_text(" "))
        url = clean_result_url(title_node.get("href") or "")
        if not title or not url:
            continue

        snippet = clean_text(snippet_node.get_text(" ")) if snippet_node else ""
        results.append(
            SearchResult(
                rank=0,
                engine="duckduckgo",
                title=title,
                url=url,
                domain=domain_from_url(url),
                snippet=snippet,
            )
        )
        if len(results) >= limit:
            break
    return results


def search_bing(query: str, limit: int, timeout: float) -> list[SearchResult]:
    """Search Bing HTML results."""

    response = requests.get(
        BING_SEARCH_URL,
        params={"q": query, "count": min(max(limit, 10), 50)},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[SearchResult] = []
    for result in soup.select("li.b_algo"):
        title_node = result.select_one("h2 a")
        snippet_node = result.select_one(".b_caption p") or result.select_one("p")
        if not title_node:
            continue

        title = clean_text(title_node.get_text(" "))
        url = clean_result_url(title_node.get("href") or "")
        if not title or not url:
            continue

        snippet = clean_text(snippet_node.get_text(" ")) if snippet_node else ""
        results.append(
            SearchResult(
                rank=0,
                engine="bing",
                title=title,
                url=url,
                domain=domain_from_url(url),
                snippet=snippet,
            )
        )
        if len(results) >= limit:
            break
    return results


def search_engine(engine: str, query: str, limit: int, timeout: float) -> list[SearchResult]:
    """Dispatch a search to one supported engine."""

    if engine == "duckduckgo":
        return search_duckduckgo(query, limit, timeout)
    if engine == "bing":
        return search_bing(query, limit, timeout)
    raise ValueError(f"Unsupported engine: {engine}")


def dedupe_and_rank(results: list[SearchResult], limit: int) -> list[SearchResult]:
    """Deduplicate URLs, merge engine labels, and rank the final result list."""

    by_url: dict[str, SearchResult] = {}
    ordered_keys: list[str] = []
    for result in results:
        key = normalize_url(result.url)
        if key in by_url:
            existing = by_url[key]
            engines = existing.engine.split("+")
            if result.engine not in engines:
                existing.engine = "+".join([*engines, result.engine])
            continue
        by_url[key] = result
        ordered_keys.append(key)

    ranked: list[SearchResult] = []
    for index, key in enumerate(ordered_keys[:limit], start=1):
        result = by_url[key]
        ranked.append(
            SearchResult(
                rank=index,
                engine=result.engine,
                title=result.title,
                url=result.url,
                domain=result.domain,
                snippet=result.snippet,
            )
        )
    return ranked


def search_web(
    query: str,
    limit: int,
    timeout: float,
    engines: list[str],
) -> tuple[list[SearchResult], list[str]]:
    """Search one or more engines and return deduplicated results plus engine errors."""

    result_sets: list[list[SearchResult]] = []
    errors: list[str] = []
    for engine in engines:
        try:
            result_sets.append(search_engine(engine, query, limit, timeout))
        except requests.RequestException as exc:
            errors.append(f"{SUPPORTED_ENGINES[engine]} failed: {exc}")
            result_sets.append([])

    combined: list[SearchResult] = []
    max_rows = max((len(result_set) for result_set in result_sets), default=0)
    for index in range(max_rows):
        for result_set in result_sets:
            if index < len(result_set):
                combined.append(result_set[index])
    return dedupe_and_rank(combined, limit), errors


def filter_by_sites(results: list[SearchResult], sites: list[str], limit: int) -> list[SearchResult]:
    """Filter results locally by one or more domains."""

    if not sites:
        return results
    filtered = [
        result
        for result in results
        if any(domain_matches(result.domain, site) for site in sites)
    ]
    return dedupe_and_rank(filtered, limit)


def describe_narrowing(narrowing: dict[str, object]) -> str:
    """Create a compact description of applied narrowing options."""

    active: list[str] = []
    if narrowing.get("preset") != "general":
        active.append(f"preset={narrowing.get('preset')}")
    for key in ["exact", "any", "must", "exclude", "site", "filetype", "intitle", "inurl"]:
        values = narrowing.get(key)
        if isinstance(values, list) and values:
            active.append(f"{key}={', '.join(str(value) for value in values)}")
    if narrowing.get("after"):
        active.append(f"after={narrowing['after']}")
    if narrowing.get("before"):
        active.append(f"before={narrowing['before']}")
    return "; ".join(active) if active else "none"


def explain_results(
    query: str,
    results: list[SearchResult],
    engines: list[str],
    narrowing: dict[str, object],
    engine_errors: list[str],
) -> str:
    """Create a short human-readable explanation of the search results."""

    engine_names = ", ".join(SUPPORTED_ENGINES[engine] for engine in engines)
    narrowing_text = describe_narrowing(narrowing)
    if not results:
        error_text = f" Engine notes: {'; '.join(engine_errors)}" if engine_errors else ""
        return (
            f"No results were found for '{query}' using {engine_names}. "
            f"Applied narrowing: {narrowing_text}. Try fewer filters, a simpler spelling, "
            f"or another engine.{error_text}"
        )

    domain_counts = Counter(result.domain for result in results)
    engine_counts = Counter(result.engine for result in results)
    top_domains = ", ".join(f"{domain} ({count})" for domain, count in domain_counts.most_common(3))
    engine_summary = ", ".join(f"{engine} ({count})" for engine, count in engine_counts.most_common())
    first = results[0]

    return (
        f"Found {len(results)} result(s) for '{query}' using {engine_names}. "
        f"The top result is from {first.domain}: '{first.title}'. "
        f"Common domains: {top_domains}. Engine coverage: {engine_summary}. "
        f"Applied narrowing: {narrowing_text}. For OSINT work, open the original pages, "
        "prefer primary sources, and keep notes on where each claim came from."
    )


def render_results(query: str, results: list[SearchResult]) -> None:
    """Print search results in a table."""

    table = Table(title=f"OSINT Search Results for: {query}", show_lines=True)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Engine", overflow="fold")
    table.add_column("Title", overflow="fold")
    table.add_column("Domain", style="magenta", overflow="fold")
    table.add_column("Snippet", overflow="fold")
    table.add_column("URL", overflow="fold")

    if not results:
        table.add_row("-", "-", "No results found", "-", "-", "-")
    for result in results:
        table.add_row(
            str(result.rank),
            result.engine,
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
            fieldnames=["rank", "engine", "title", "url", "domain", "snippet"],
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

    parser = argparse.ArgumentParser(description="Simple OSINT-focused command-line search engine.")
    parser.add_argument("query", nargs="*", help="Words to search for. If omitted, the app prompts you.")
    parser.add_argument(
        "--engine",
        default="duckduckgo",
        help="Search engine: duckduckgo, bing, all, or comma-separated values. Default: duckduckgo.",
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESET_DESCRIPTIONS),
        default="general",
        help="OSINT narrowing preset. Default: general.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help=f"Number of results to show. Default: {DEFAULT_RESULT_LIMIT}.",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds.")
    parser.add_argument("--exact", action="append", help="Require an exact phrase. Can be repeated.")
    parser.add_argument("--any", action="append", help="Add OR terms, comma-separated or repeated.")
    parser.add_argument("--must", action="append", help="Add a required word or phrase. Can be repeated.")
    parser.add_argument("--exclude", action="append", help="Exclude a word or phrase. Can be repeated.")
    parser.add_argument("--site", action="append", help="Restrict to a domain. Can be repeated.")
    parser.add_argument("--filetype", action="append", help="Restrict to a file type, for example pdf.")
    parser.add_argument("--intitle", action="append", help="Require a word or phrase in the page title.")
    parser.add_argument("--inurl", action="append", help="Require a word or phrase in the URL.")
    parser.add_argument("--after", help="Prefer results after a date, for example 2025-01-01.")
    parser.add_argument("--before", help="Prefer results before a date, for example 2026-01-01.")
    parser.add_argument("--show-query", action="store_true", help="Print the built dork query before searching.")
    parser.add_argument("--open-first", action="store_true", help="Open the first result in your browser.")
    parser.add_argument("--json-out", type=Path, help="Save JSON report.")
    parser.add_argument("--csv-out", type=Path, help="Save CSV results.")
    return parser


def main() -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args()
    base_query = " ".join(args.query).strip() or prompt_for_query()
    if not base_query:
        console.print("[red]Please enter something to search for.[/red]")
        return 1

    limit = args.limit if args.limit is not None else DEFAULT_RESULT_LIMIT
    if limit < 1:
        console.print("[red]--limit must be 1 or greater.[/red]")
        return 1

    try:
        engines = parse_engines(args.engine)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    built_query, narrowing = build_osint_query(base_query, args, include_sites=True)
    site_filters = flatten_values(args.site)
    console.print(
        Panel(
            f"Base query: [bold]{clean_text(base_query)}[/bold]\n"
            f"Built query: [bold]{built_query}[/bold]\n"
            f"Engines: [bold]{', '.join(SUPPORTED_ENGINES[engine] for engine in engines)}[/bold]\n"
            f"Limit: [bold]{limit}[/bold]\n"
            f"Narrowing: [bold]{describe_narrowing(narrowing)}[/bold]",
            title="OSINT Search",
            border_style="cyan",
        )
    )
    if args.show_query:
        console.print(f"[cyan]Search query:[/cyan] {built_query}")

    results, engine_errors = search_web(
        built_query,
        limit=limit,
        timeout=max(args.timeout, 3.0),
        engines=engines,
    )
    if site_filters:
        results = filter_by_sites(results, site_filters, limit)
        if not results:
            fallback_query, _ = build_osint_query(base_query, args, include_sites=False)
            fallback_results, fallback_errors = search_web(
                fallback_query,
                limit=limit * 3,
                timeout=max(args.timeout, 3.0),
                engines=engines,
            )
            engine_errors.extend(fallback_errors)
            results = filter_by_sites(fallback_results, site_filters, limit)

    if engine_errors:
        for error in engine_errors:
            console.print(f"[yellow]{error}[/yellow]")
    if not results and engine_errors and len(engine_errors) >= len(engines):
        console.print("[red]All selected search engines failed.[/red]")
        return 1

    explanation = explain_results(built_query, results, engines, narrowing, engine_errors)
    render_results(built_query, results)
    console.print(Panel(explanation, title="Result Explanation", border_style="blue"))

    report = SearchReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        query=base_query,
        built_query=built_query,
        engines=[SUPPORTED_ENGINES[engine] for engine in engines],
        narrowing=narrowing,
        result_count=len(results),
        results=results,
        explanation=explanation,
        engine_errors=engine_errors,
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
