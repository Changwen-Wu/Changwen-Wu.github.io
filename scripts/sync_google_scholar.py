#!/usr/bin/env python3
"""Sync Google Scholar titles and citations with complete publication metadata."""

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import requests

PROFILE_ID = "jQBiItMAAAAJ"
ORCID_ID = "0009-0007-2996-9965"
OUTPUT = Path("_data/google_scholar_publications.json")
PDF_LINKS = Path("_data/publication_pdfs.json")
# Upload PDFs to files/, then fill in their URLs in publication_pdfs.json.
PDF_BY_TITLE = json.loads(PDF_LINKS.read_text(encoding="utf-8")) if PDF_LINKS.exists() else {}


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


def publication_role(names, prior):
    """Keep manual labels; group new first- or last-author papers as lead."""
    saved_role = prior.get("role")
    if saved_role in {"lead", "contributor"}:
        return saved_role
    if names and (
        abbreviate_author(names[0]) == "Wu, C."
        or abbreviate_author(names[-1]) == "Wu, C."
    ):
        return "lead"
    return "contributor"


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
            "pdf": PDF_BY_TITLE.get(title, prior.get("pdf", "")),
            "role": publication_role(names, prior),
        }
    return list(publications.values())


def scholar_publications():
    """Run the unreliable Scholar client in a process with a hard deadline."""
    result = subprocess.run(
        [sys.executable, "scripts/scholar_snapshot.py"],
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def main():
    previous = previous_publications()
    try:
        scholar_items = scholar_publications()
    except (subprocess.SubprocessError, ValueError, IndexError) as error:
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

        bib = item.get("bib", {})
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
                "url": prior.get("url") or item.get("pub_url") or metadata.get("url", ""),
                "citations": int(
                    item.get("num_citations")
                    if item.get("num_citations") is not None
                    else prior.get("citations", 0)
                ),
                "pdf": PDF_BY_TITLE.get(title, prior.get("pdf", "")),
                "role": publication_role(names, prior),
            }
        )

    if not publications:
        raise RuntimeError("No publications were found; keeping the previous data.")

    publications.sort(key=lambda paper: (paper["year"], paper["title"]), reverse=True)
    for paper in publications:
        title = paper["title"]
        if title in PDF_BY_TITLE:
            paper["pdf"] = PDF_BY_TITLE[title]
        else:
            PDF_BY_TITLE[title] = paper.get("pdf", "")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(publications, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    PDF_LINKS.write_text(
        json.dumps(PDF_BY_TITLE, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
