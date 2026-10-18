#!/usr/bin/env python3
"""Best-effort monthly retrieval of openly licensed publication PDFs and SI.

This complements the Scholar metadata sync. It never uses institutional access
or republishes a file without an explicit Creative Commons license signal.
"""

import io
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from pypdf import PdfReader


PUBLICATIONS = Path("_data/google_scholar_publications.json")
PDF_LINKS = Path("_data/publication_pdfs.json")
SI_LINKS = Path("_data/publication_supplements.json")
STATUS = Path("_data/publication_fulltext_status.json")
FILE_DIR = Path("files/publications")
SITE_URL = "https://changwen-wu.github.io"
CONTACT_EMAIL = "cw.wu1103@gmail.com"
MAX_BYTES = 25 * 1024 * 1024
HEADERS = {"User-Agent": "Changwen-Wu-homepage/1.0 (mailto:cw.wu1103@gmail.com)"}
SUPPLEMENT_PATTERN = re.compile(r"supplement|supporting|suppl_file|/doi/suppl/|_si_|mmc[0-9]", re.I)
ALLOWED_SI_SUFFIXES = {".pdf", ".zip", ".docx", ".xlsx", ".csv", ".txt"}


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def doi_of(paper):
    match = re.search(r"10\.\d{4,9}/[^\s?#]+", paper.get("url", ""), re.I)
    return match.group(0).rstrip(".,") if match else ""


def licensed(license_name):
    value = (license_name or "").lower()
    return value.startswith("cc-") or "creativecommons.org/licenses/" in value


def read_response(url, max_bytes=MAX_BYTES):
    if urlparse(url).scheme != "https":
        raise ValueError("non-HTTPS source")
    with requests.get(url, headers=HEADERS, timeout=18, stream=True) as response:
        response.raise_for_status()
        result = bytearray()
        for chunk in response.iter_content(65536):
            result.extend(chunk)
            if len(result) > max_bytes:
                raise ValueError("file exceeds size limit")
        return bytes(result), response.url, response.headers.get("Content-Type", "")


def pdf_matches_title(data, title):
    if not data.startswith(b"%PDF"):
        return False
    try:
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) < 1:
            return False
        first_pages = " ".join(page.extract_text() or "" for page in reader.pages[:2]).casefold()
    except Exception:
        return False
    words = {word for word in re.findall(r"[a-z]{5,}", title.casefold())}
    return bool(words) and sum(word in first_pages for word in words) >= max(2, len(words) // 2)


def unpaywall(doi):
    response = requests.get(
        f"https://api.unpaywall.org/v2/{doi}",
        params={"email": CONTACT_EMAIL},
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def pdf_candidates(record):
    seen = set()
    for location in [record.get("best_oa_location"), *(record.get("oa_locations") or [])]:
        if not isinstance(location, dict):
            continue
        url = location.get("url_for_pdf")
        if not url or url in seen:
            continue
        seen.add(url)
        yield url, location.get("license", "")


def filename_for(paper, doi, suffix=".pdf"):
    surname = (paper.get("author_abbreviations") or "Paper").split("|")[0].split(",")[0]
    stem = re.sub(r"[^A-Za-z0-9]+", "_", f"{surname}_{paper.get('year', '')}_{doi}")
    return stem.strip("_")[:110] + suffix


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = ""
        self.label = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href", "")
            self.label = []

    def handle_data(self, data):
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join(self.label)))
            self.href = ""
            self.label = []


def supplement_candidates(landing_url, title):
    try:
        html, final_url, content_type = read_response(landing_url, max_bytes=5 * 1024 * 1024)
        if "html" not in content_type.lower():
            return []
        document = html.decode("utf-8", errors="replace")
        title_words = [word for word in re.findall(r"[a-z]{5,}", title.casefold())][:5]
        if sum(word in document.casefold() for word in title_words) < min(2, len(title_words)):
            return []
        links = Links()
        links.feed(document)
        result = []
        for href, label in links.links:
            if not SUPPLEMENT_PATTERN.search(href + " " + label):
                continue
            url = urljoin(final_url, href)
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != urlparse(final_url).hostname:
                continue
            if Path(unquote(parsed.path)).suffix.lower() not in ALLOWED_SI_SUFFIXES:
                continue
            if url not in result:
                result.append(url)
        return result[:5]
    except (requests.RequestException, ValueError):
        return []


def valid_attachment(data, suffix):
    if suffix == ".pdf":
        return data.startswith(b"%PDF")
    if suffix in {".zip", ".docx", ".xlsx"}:
        return data.startswith(b"PK\x03\x04")
    return bool(data) and not data.lstrip().lower().startswith(b"<html")


def supplement_landing_pages(record, paper):
    """Prefer the licensed OA landing page, then try the DOI landing page."""
    seen = set()
    for location in [record.get("best_oa_location"), *(record.get("oa_locations") or [])]:
        if not isinstance(location, dict):
            continue
        for key in ("url_for_landing_page", "url"):
            url = location.get(key)
            if url and url not in seen:
                seen.add(url)
                yield url, location.get("license", "")
    doi_url = paper.get("url", "")
    if doi_url and doi_url not in seen:
        yield doi_url, ""


def main():
    publications = read_json(PUBLICATIONS, [])
    pdf_links = read_json(PDF_LINKS, {})
    si_links = read_json(SI_LINKS, {})
    status = {}
    FILE_DIR.mkdir(parents=True, exist_ok=True)

    for paper in publications:
        title = paper["title"]
        doi = doi_of(paper)
        result = {"doi": doi, "checked_at": datetime.now(timezone.utc).date().isoformat(),
                  "pdf": "already_linked" if pdf_links.get(title) else "not_found",
                  "supplements": "not_found"}
        record = {}
        if doi:
            try:
                record = unpaywall(doi)
            except (requests.RequestException, ValueError) as error:
                result["lookup_error"] = str(error)[:160]

        if not pdf_links.get(title):
            for url, license_name in pdf_candidates(record):
                if not licensed(license_name):
                    result["pdf"] = "license_not_confirmed"
                    continue
                try:
                    data, source_url, _content_type = read_response(url)
                    if not pdf_matches_title(data, title):
                        result["pdf"] = "invalid_pdf_or_title"
                        continue
                    path = FILE_DIR / filename_for(paper, doi)
                    if not path.exists():
                        path.write_bytes(data)
                    pdf_links[title] = f"{SITE_URL}/{path.as_posix()}"
                    paper["pdf"] = pdf_links[title]
                    result.update(pdf="downloaded", pdf_source=source_url, license=license_name)
                    break
                except (requests.RequestException, ValueError) as error:
                    result["pdf"] = "fetch_failed"
                    result["pdf_error"] = str(error)[:160]

        if not si_links.get(title):
            found = []
            license_name = ""
            for landing, candidate_license in supplement_landing_pages(record, paper):
                found = supplement_candidates(landing, title)
                if found:
                    license_name = candidate_license
                    break
            if found:
                saved = []
                for index, url in enumerate(found, start=1):
                    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
                    if licensed(license_name):
                        try:
                            data, _final_url, _content_type = read_response(url)
                            if valid_attachment(data, suffix):
                                path = FILE_DIR / filename_for(paper, doi, f"_SI{index}{suffix}")
                                if not path.exists():
                                    path.write_bytes(data)
                                saved.append(f"{SITE_URL}/{path.as_posix()}")
                                continue
                        except (requests.RequestException, ValueError):
                            pass
                    saved.append(url)
                si_links[title] = saved
                result["supplements"] = "downloaded_or_linked"
                result["supplement_count"] = len(saved)
        status[title] = result

    write_json(PDF_LINKS, pdf_links)
    write_json(SI_LINKS, si_links)
    write_json(STATUS, status)
    write_json(PUBLICATIONS, publications)
    print(json.dumps({"papers": len(publications),
                      "pdfs_downloaded": sum(x["pdf"] == "downloaded" for x in status.values()),
                      "with_supplements": sum(x["supplements"] == "downloaded_or_linked" for x in status.values())}))


if __name__ == "__main__":
    main()

