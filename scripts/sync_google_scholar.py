#!/usr/bin/env python3
"""Fetch the public Google Scholar profile and save its publication list for Jekyll."""

import json
from pathlib import Path

from scholarly import scholarly

PROFILE_ID = "jQBiItMAAAAJ"
OUTPUT = Path("_data/google_scholar_publications.json")
PDF_BY_TITLE = {
    "A novel method for functional brain networks based on static cerebral blood flow":
        "https://changwen-wu.github.io/files/Wu_Neuroimage_CBFnetworks.pdf",
}


def author_names(value):
    """Accept the list or string returned by different Scholar publication pages."""
    if isinstance(value, list):
        return [str(name).strip() for name in value if str(name).strip()]
    if not isinstance(value, str):
        return []
    if " and " in value:
        return [name.strip() for name in value.split(" and ") if name.strip()]
    return [name.strip() for name in value.split(",") if name.strip()]


def abbreviate_author(name):
    """Format a full author name as surname followed by given-name initials."""
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


def previous_publications():
    if not OUTPUT.exists():
        return {}
    return {
        paper["title"].casefold(): paper
        for paper in json.loads(OUTPUT.read_text(encoding="utf-8"))
        if paper.get("title")
    }


def main():
    previous = previous_publications()
    author = scholarly.search_author_id(PROFILE_ID)
    author = scholarly.fill(author, sections=["publications"])
    publications = []

    for item in author.get("publications", []):
        summary = item.get("bib", {})
        title = str(summary.get("title") or "").strip()
        if not title:
            continue
        prior = previous.get(title.casefold(), {})

        # Author profile rows contain only a short summary. Open each publication
        # to retrieve its authors, journal, and link.
        try:
            detailed = scholarly.fill(item)
        except Exception as error:
            print(f"Could not fetch details for {title}: {error}")
            detailed = item
        bib = detailed.get("bib", {})
        names = author_names(bib.get("author") or summary.get("author"))
        authors = ", ".join(names) or prior.get("authors", "")
        abbreviations = (
            "|".join(abbreviate_author(name) for name in names)
            if names else prior.get("author_abbreviations", "")
        )
        publications.append(
            {
                "title": title,
                "authors": authors,
                "author_abbreviations": abbreviations,
                "venue": str(
                    bib.get("venue") or bib.get("journal") or summary.get("venue")
                    or summary.get("journal") or prior.get("venue") or ""
                ).strip(),
                "year": str(
                    bib.get("pub_year") or summary.get("pub_year")
                    or prior.get("year") or ""
                ).strip(),
                "url": detailed.get("pub_url") or item.get("pub_url")
                       or prior.get("url", ""),
                "citations": int(
                    item.get("num_citations")
                    if item.get("num_citations") is not None
                    else prior.get("citations", 0)
                ),
                "pdf": PDF_BY_TITLE.get(title) or prior.get("pdf", ""),
            }
        )

    if not publications:
        raise RuntimeError("Google Scholar returned no publications; keeping the previous data.")

    publications.sort(key=lambda p: (p["year"], p["title"]), reverse=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(publications, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
