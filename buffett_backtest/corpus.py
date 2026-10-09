"""Everything Buffett has said in public that can be downloaded, as plain text.

  letters   Berkshire shareholder letters, from berkshirehathaway.com
  meetings  Berkshire annual meeting transcripts (Warren Buffett Archive, 1994-)
  lectures  talks, articles and Q&As listed in lectures.csv
  rbcpa     partnership letters 1959-69, Berkshire letters 1973-76, and the
            interview / lecture / meeting-note transcripts collected on rbcpa.com

The CNBC Warren Buffett Archive (meeting videos and transcripts) refuses
requests from cloud IP ranges, so meeting Q&A comes from buffettfaq.com
(answers grouped by topic, each with its meeting and year) and from the
meeting notes on rbcpa.com.

Text goes to cache/corpus/<kind>/, and sources.csv records every item with
whether it was fetched, so gaps are visible.

Usage:
  python corpus.py fetch [letters|meetings|lectures ...]
  python corpus.py grep "owner earnings" [more words ...]
"""

import csv
import io
import json
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup

import data

ROOT = Path(__file__).resolve().parent
OUT = data.CACHE / "corpus"
SOURCES = ROOT / "sources.csv"

LETTERS_INDEX = "https://www.berkshirehathaway.com/letters/letters.html"
MEETING_ROOTS = ["https://buffett.cnbc.com/annual-meetings/", "https://warrenbuffett.com/"]
MEETING_LINK = re.compile(r"annual-meeting|/video/\d{4}/|transcript", re.I)
SPEAKER = re.compile(r"\b(WARREN BUFFETT|CHARLIE MUNGER)\s*:")


def unpack(body):
    """berkshirehathaway.com serves some files brotli-compressed without saying so."""
    if isinstance(body, bytes) and body[:4] != b"%PDF" and not body.lstrip()[:1] in (b"<", b"{"):
        try:
            import brotli
            return brotli.decompress(body)
        except Exception:                                # noqa: BLE001  (not brotli after all)
            pass
    return body


def ocr(pdf_bytes):
    """Text of a scanned PDF via pdftoppm + tesseract (empty if they are not installed)."""
    import shutil
    import subprocess
    import tempfile
    if not (shutil.which("pdftoppm") and shutil.which("tesseract")):
        return ""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.pdf"
        src.write_bytes(pdf_bytes)
        subprocess.run(["pdftoppm", "-r", "300", "-gray", str(src), str(Path(d) / "p")], check=True,
                       capture_output=True)
        out = []
        for img in sorted(Path(d).glob("p*.pgm")):
            r = subprocess.run(["tesseract", str(img), "-", "--psm", "4"], capture_output=True, text=True)
            out.append(r.stdout)
        return "\n".join(out)


def to_text(body, url):
    """PDF bytes or HTML -> plain text."""
    body = unpack(body)
    if isinstance(body, bytes) and body[:4] == b"%PDF":
        import pdfplumber
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            pages = len(pdf.pages)
        if len(text.strip()) < 200 * pages:            # a scan with no text layer
            text = ocr(body) or text
        return text
    if isinstance(body, bytes):
        try:
            html = body.decode("utf-8")
        except UnicodeDecodeError:
            html = body.decode("cp1252", "replace")
    else:
        html = body
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        t.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text("\n")
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _get(url, path):
    return data.cached(url, path, binary=True)


def _slug(url):
    p = urlparse(url)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (p.netloc + p.path).strip("/"))[:150]


def fetch_letters():
    rows = []
    idx = _get(LETTERS_INDEX, "corpus/raw/letters.html")
    if idx is None:
        return [{"kind": "letter", "year": "", "title": "index", "url": LETTERS_INDEX, "status": "404"}]
    soup = BeautifulSoup(idx, "lxml")
    seen = set()
    for a in soup.find_all("a", href=True):
        url = urljoin(LETTERS_INDEX, a["href"])
        m = re.search(r"(19[5-9]\d|20[0-4]\d)", a.get_text() + " " + a["href"])
        if not m or url in seen or "letters" not in url:
            continue
        seen.add(url)
        year = m.group(1)
        path = OUT / "letters" / f"{year}.txt"
        rows.append(_save("letter", year, f"Shareholder letter {year}", url, path))
        # 1998-2003 pages are only a note linking to the PDF and HTML versions
        if path.exists() and path.stat().st_size < 5000:
            page = unpack(_get(url, f"corpus/raw/{_slug(url)}")).decode("cp1252", "replace")
            for href in re.findall(r'href="([^"]+)"', page, re.I):
                sub = urljoin(url, href)
                if year in sub and "adobe" not in sub:
                    rows.append(_save("letter", year, f"Shareholder letter {year}", sub, path))
    return rows


_written = set()


def _save(kind, year, title, url, path):
    """Download url as text into path; one sources.csv row."""
    row = {"kind": kind, "year": year, "title": title, "url": url}
    try:
        body = _get(url, f"corpus/raw/{_slug(url)}")
    except Exception as e:                               # noqa: BLE001  (record and move on)
        return {**row, "status": f"error: {type(e).__name__}"}
    if body is None:
        return {**row, "status": "404"}
    done = data.CACHE / "corpus" / "raw" / (_slug(url) + ".txt")   # extracted text (OCR is slow)
    text = done.read_text(encoding="utf-8") if done.exists() else to_text(body, url)
    done.write_text(text, encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path in _written and path.stat().st_size >= len(text):   # several links for one item: keep the longest
        return {**row, "status": "duplicate", "chars": len(text)}
    path.write_text(text, encoding="utf-8")
    _written.add(path)
    return {**row, "status": "ok", "chars": len(text), "path": str(path.relative_to(ROOT))}


def fetch_meetings(max_pages=6000, delay=0.3):
    """Crawl the archive and keep every page that is a speaker-labelled transcript."""
    rows, seen = [], set()
    queue = deque(MEETING_ROOTS)
    hosts = {urlparse(u).netloc for u in MEETING_ROOTS}
    while queue and len(seen) < max_pages:
        url = queue.popleft().split("#")[0]
        if url in seen:
            continue
        seen.add(url)
        try:
            body = _get(url, f"corpus/raw/meetings/{_slug(url)}")
        except Exception:                                # noqa: BLE001
            continue
        if body is None:
            continue
        html = body.decode("utf-8", "replace")
        text = to_text(html, url)
        if len(SPEAKER.findall(text)) >= 5:
            y = re.search(r"(199[4-9]|20[0-4]\d)", url) or re.search(r"(199[4-9]|20[0-4]\d)", text[:300])
            year = y.group(1) if y else ""
            path = OUT / "meetings" / f"{year or 'unknown'}_{_slug(url)[-80:]}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            rows.append({"kind": "meeting", "year": year, "title": text.split("\n", 1)[0][:120],
                         "url": url, "status": "ok", "chars": len(text),
                         "path": str(path.relative_to(ROOT))})
        for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
            nxt = urljoin(url, a["href"]).split("#")[0]
            if urlparse(nxt).netloc in hosts and MEETING_LINK.search(nxt) and nxt not in seen:
                queue.append(nxt)
        time.sleep(delay)
    return rows


def fetch_lectures():
    rows = []
    for r in pd.read_csv(ROOT / "lectures.csv", dtype=str).itertuples():
        best = None
        for url in [u.strip() for u in r.urls.split("|")]:
            path = OUT / "lectures" / f"{r.year}_{re.sub(r'[^A-Za-z0-9]+', '_', r.title)[:60]}.txt"
            row = _save(r.kind, r.year, r.title, url, path)
            if row["status"] in ("ok", "duplicate"):
                best = row
                break
            best = best or row
        rows.append(best)
    return rows


RBCPA_LETTERS = "https://www.rbcpa.com/warren-e-buffett/buffett-letters-1959-present/"


def fetch_rbcpa(max_pages=60):
    rows = []
    page = unpack(_get(RBCPA_LETTERS, "corpus/raw/rbcpa_letters.html")).decode("utf-8", "replace")
    for href in sorted(set(re.findall(r'href="(https://www\.rbcpa\.com/wp-content/uploads/[^"]+\.(?:pdf|html))"', page))):
        name = href.rsplit("/", 1)[1]
        y = re.search(r"(19[5-7]\d)", name)
        if not y:
            continue
        year = y.group(1)
        if int(year) <= 1970:
            rows.append(_save("partnership", year, f"Partnership letter {name.rsplit('.', 1)[0]}", href,
                              OUT / "partnership" / f"{name.rsplit('.', 1)[0]}.txt"))
        else:
            rows.append(_save("letter", year, f"Shareholder letter {year}", href, OUT / "letters" / f"{year}.txt"))
    # interviews, lectures and meeting notes are WordPress pages under /warren-e-buffett/
    items = []
    for kind in ("pages", "posts"):
        for n in range(1, max_pages + 1):
            try:                                         # past the last page WordPress answers 400
                body = data.cached(f"https://www.rbcpa.com/wp-json/wp/v2/{kind}?per_page=100&page={n}"
                                   "&_fields=link,title,date,content", f"corpus/raw/rbcpa_{kind}_{n}.json",
                                   ua=data.YAHOO_UA)
            except Exception:                            # noqa: BLE001
                break
            if not body or not body.lstrip().startswith("["):
                break
            batch = json.loads(body)
            if not batch:
                break
            items += batch
    for it in items:
        url, title = it["link"], BeautifulSoup(it["title"]["rendered"], "lxml").get_text()
        if "warren-e-buffett" not in url and "buffett" not in title.lower():
            continue
        slug = url.rstrip("/").rsplit("/", 1)[1]
        if slug == "buffett-letters-1959-present":
            continue
        text = to_text(it["content"]["rendered"], url)
        y = re.search(r"(19[5-9]\d|20[0-2]\d)", title + " " + slug)
        path = OUT / "rbcpa" / f"{slug[:100]}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(title + "\n\n" + text, encoding="utf-8")
        rows.append({"kind": "rbcpa", "year": y.group(1) if y else it["date"][:4], "title": title[:120],
                     "url": url, "status": "ok", "chars": len(text), "path": str(path.relative_to(ROOT))})
    return rows


def write_sources(rows):
    cols = ["kind", "year", "title", "url", "status", "chars", "path"]
    out = pd.DataFrame(rows, columns=cols)
    out = out[out["status"] != "duplicate"]
    # a failed mirror is noise once another copy of the same item was fetched
    got = set(out.loc[out["status"] == "ok", "title"])
    out = out[(out["status"] == "ok") | ~out["title"].isin(got)]
    out = out.sort_values(["kind", "year", "title"])
    out.to_csv(SOURCES, index=False, quoting=csv.QUOTE_MINIMAL)
    return out


def grep(words, width=400):
    """Passages containing all words (case-insensitive), with their source."""
    pats = [re.compile(re.escape(w), re.I) for w in words]
    for f in sorted(OUT.rglob("*.txt")):
        text = f.read_text(encoding="utf-8")
        for para in re.split(r"\n\s*\n", text):
            if all(p.search(para) for p in pats):
                flat = re.sub(r"\s+", " ", para).strip()
                print(f"--- {f.relative_to(OUT)}\n{flat[:width * 3]}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "grep":
        grep(sys.argv[2:])
        sys.exit()
    kinds = sys.argv[2:] or ["letters", "lectures", "rbcpa"]
    rows = []
    for k in kinds:
        print(f"fetching {k} ...")
        rows += {"letters": fetch_letters, "meetings": fetch_meetings, "lectures": fetch_lectures,
                 "rbcpa": fetch_rbcpa}[k]()
    out = write_sources(rows)
    print(out.groupby(["kind", "status"]).size().to_string())
