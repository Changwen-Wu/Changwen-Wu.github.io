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


def abbreviate_author(name):
    """Format a full author name as surname followed by given-name initials."""
    parts = name.strip().split()
    if len(parts) < 2:
        return name.strip()
    surname = parts[-1]
    initials = " ".join(f"{part[0]}." for part in parts[:-1] if part)
    return f"{surname}, {initials}"


def main():
    author = scholarly.search_author_id(PROFILE_ID)
    author = scholarly.fill(author, sections=["publications"])
    publications = []

    for item in author.get("publications", []):
        bib = item.get("bib", {})
        title = (bib.get("title") or "").strip()
        if not title:
            continue
        year = str(bib.get("pub_year") or "").strip()
        authors = (bib.get("author") or "").strip()
        author_names = [name.strip() for name in authors.split(",") if name.strip()]
        publications.append(
            {
                "title": title,
                "authors": authors,
                "author_abbreviations": "|".join(
                    abbreviate_author(name) for name in author_names
                ),
                "venue": (bib.get("venue") or bib.get("journal") or "").strip(),
                "year": year,
                "url": item.get("pub_url") or "",
                "citations": int(item.get("num_citations") or 0),
                "pdf": PDF_BY_TITLE.get(title, ""),
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
