#!/usr/bin/env python3
"""Sync Google Scholar titles and citations with complete publication metadata."""

import json
import re
import signal
import unicodedata
from contextlib import contextmanager
from pathlib import Path

import requests
from scholarly import scholarly

PROFILE_ID = "jQBiItMAAAAJ"
ORCID_ID = "0009-0007-2996-9965"
OUTPUT = Path("_data/google_scholar_publications.json")
PDF_BY_TITLE = {
    "A novel method for functional brain networks based on static cerebral blood flow":
        "https://changwen-wu.github.io/files/Wu_Neuroimage_CBFnetworks.pdf",
}


def author_names(value):
    if isinstance(value, list):
        return [str(name).strip() for name in value if str(name).strip()]
    if not isinstance(value, str):
        return []
    separator = " and " if " and " in value else ","
    return [name.strip() for name in value.split(separator) if name.strip()]


def abbreviate_author(name):
    if "," in name:
        surname, given = (part.strip() for part in name.split(",", 1))
        parts = given.split()
    else:
        parts = name.strip().split()
        if len(parts) < 2:
            return name.strip()
        surname, parts = parts[-1], parts[:-1]
    initials = " ".join(f"{part[0]}." for part in parts if part)
    return f"{surname}, {initials}" if initials else surname


def normalized_title(title):
    text = unicodedata.normalize("NFKC", title).casefold()
    return re.sub(r"[^\w]+", "", text)


def previous_publications():
    if not OUTPUT.exists():
        return {}
    return {
        normalized_title(paper["title"]): paper
        for paper in json.loads(OUTPUT.read_text(encoding="utf-8"))
        if paper.get("title")
    }


def crossref_metadata(title):
    """Use an exact title match so a similar paper cannot replace Scholar data."""
    try:
        response = requests.get(
            "https://api.crossref.org/works",
            params={"query.title": title, "rows": 5},
            headers={"User-Agent": "Changwen-Wu-homepage/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        matches = response.json()["message"]["items"]
    except (requests.RequestException, KeyError, ValueError) as error:
        print(f"Crossref lookup failed for {title}: {error}", flush=True)
        return {}

    for match in matches:
        candidate = (match.get("title") or [""])[0]
        if normalized_title(candidate) != normalized_title(title):
            continue
        authors = [
            " ".join(part for part in (entry.get("given"), entry.get("family")) if part)
            for entry in match.get("author", [])
        ]
        published = match.get("published", {}).get("date-parts", [[]])
        year = str(published[0][0]) if published and published[0] else ""
        doi = match.get("DOI") or ""
        return {
            "authors": [name for name in authors if name],
            "venue": (match.get("container-title") or [""])[0],
            "year": year,
            "url": f"https://doi.org/{doi}" if doi else "",
        }
    return {}


def crossref_author_publications(previous):
    """Add ORCID-matched works when Google Scholar blocks the Actions runner."""
    response = requests.get(
        "https://api.crossref.org/works",
        params={"filter": f"orcid:{ORCID_ID}", "rows": 100},
        headers={"User-Agent": "Changwen-Wu-homepage/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    works = response.json()["message"]["items"]
    publications = dict(previous)

    for work in works:
        contributors = work.get("author", [])
        if not any(
            entry.get("ORCID", "").rstrip("/").endswith(ORCID_ID)
            for entry in contributors
        ):
            continue
        title = str((work.get("title") or [""])[0]).strip()
        if not title:
            continue
        names = [
            " ".join(part for part in (entry.get("given"), entry.get("family")) if part)
            for entry in contributors
        ]
        names = [name for name in names if name]
        if not names:
            continue
        key = normalized_title(title)
        prior = publications.get(key, {})
        published = work.get("published", {}).get("date-parts", [[]])
        year = str(published[0][0]) if published and published[0] else ""
        doi = work.get("DOI") or ""
        publications[key] = {
            "title": prior.get("title") or title,
            "authors": prior.get("authors") or ", ".join(names),
            "author_abbreviations": prior.get("author_abbreviations") or "|".join(
                abbreviate_author(name) for name in names
            ),
            "venue": prior.get("venue") or (work.get("container-title") or [""])[0],
            "year": prior.get("year") or year,
            "url": prior.get("url") or (f"https://doi.org/{doi}" if doi else ""),
            "citations": prior.get("citations", 0),
            "pdf": PDF_BY_TITLE.get(title) or prior.get("pdf", ""),
        }
    return list(publications.values())


@contextmanager
def scholar_timeout(seconds):
    """Bound slow article-detail requests on the Linux Actions runner."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def timed_out(_signum, _frame):
        raise TimeoutError("Google Scholar publication request timed out")

    old_handler = signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def main():
    previous = previous_publications()
    try:
        with scholar_timeout(45):
            author = scholarly.search_author_id(PROFILE_ID)
            author = scholarly.fill(author, sections=["publications"])
        scholar_items = author.get("publications", [])
    except Exception as error:
        print(f"Google Scholar unavailable: {error}", flush=True)
        publications = crossref_author_publications(previous)
        if not publications:
            raise RuntimeError("Neither Scholar nor Crossref returned publications.") from error
        scholar_items = None

    if scholar_items is not None:
        publications = []

    for item in scholar_items or []:
        summary = item.get("bib", {})
        title = str(summary.get("title") or "").strip()
        if not title:
            continue
        prior = previous.get(normalized_title(title), {})
        names = author_names(summary.get("author"))
        metadata = {}

        needs_authors = not names and not prior.get("authors")
        needs_venue = not (summary.get("venue") or summary.get("journal") or prior.get("venue"))
        needs_link = not (item.get("pub_url") or prior.get("url"))
        if needs_authors or needs_venue or needs_link:
            metadata = crossref_metadata(title)

        # Profile rows usually contain a title and year only. Fetch a detailed
        # Scholar record when Crossref and saved data cannot supply authors.
        detailed = item
        if not names and not metadata.get("authors") and not prior.get("authors"):
            try:
                with scholar_timeout(12):
                    detailed = scholarly.fill(item)
            except Exception as error:
                print(f"Scholar details unavailable for {title}: {error}", flush=True)

        bib = detailed.get("bib", {})
        names = (
            author_names(bib.get("author"))
            or names
            or metadata.get("authors", [])
        )
        authors = prior.get("authors") or ", ".join(names)
        abbreviations = prior.get("author_abbreviations") or "|".join(
            abbreviate_author(name) for name in names
        )
        publications.append(
            {
                "title": title,
                "authors": authors,
                "author_abbreviations": abbreviations,
                "venue": str(
                    prior.get("venue") or bib.get("venue") or bib.get("journal")
                    or summary.get("venue") or summary.get("journal")
                    or metadata.get("venue") or ""
                ).strip(),
                "year": str(
                    bib.get("pub_year") or summary.get("pub_year")
                    or metadata.get("year") or prior.get("year") or ""
                ).strip(),
                "url": prior.get("url") or detailed.get("pub_url")
                       or item.get("pub_url") or metadata.get("url", ""),
                "citations": int(
                    item.get("num_citations")
                    if item.get("num_citations") is not None
                    else prior.get("citations", 0)
                ),
                "pdf": PDF_BY_TITLE.get(title) or prior.get("pdf", ""),
            }
        )

    if not publications:
        raise RuntimeError("No publications were found; keeping the previous data.")

    publications.sort(key=lambda paper: (paper["year"], paper["title"]), reverse=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(publications, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
