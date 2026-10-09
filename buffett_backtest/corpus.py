"""Everything Buffett has said in public that can be downloaded, as plain text.

  letters   Berkshire shareholder letters, from berkshirehathaway.com
  meetings  Berkshire annual meeting transcripts (Warren Buffett Archive, 1994-)
  lectures  talks, articles and Q&As listed in lectures.csv

Text goes to cache/corpus/<kind>/, and sources.csv records every item with
whether it was fetched, so gaps are visible.

Usage:
  python corpus.py fetch [letters|meetings|lectures ...]
  python corpus.py grep "owner earnings" [more words ...]
"""

import csv
import io
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


def to_text(body, url):
    """PDF bytes or HTML -> plain text."""
    if isinstance(body, bytes) and body[:4] == b"%PDF":
        import pdfplumber
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    html = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
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
        rows.append(_save("letter", year, f"Shareholder letter {year}", url, OUT / "letters" / f"{year}.txt"))
    return rows


def _save(kind, year, title, url, path):
    """Download url as text into path; one sources.csv row."""
    row = {"kind": kind, "year": year, "title": title, "url": url}
    try:
        body = _get(url, f"corpus/raw/{_slug(url)}")
    except Exception as e:                               # noqa: BLE001  (record and move on)
        return {**row, "status": f"error: {type(e).__name__}"}
    if body is None:
        return {**row, "status": "404"}
    text = to_text(body, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > len(text):   # several links for one year: keep the longest
        return {**row, "status": "duplicate", "chars": len(text)}
    path.write_text(text, encoding="utf-8")
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


def write_sources(rows, kinds):
    old = pd.read_csv(SOURCES, dtype=str) if SOURCES.exists() else pd.DataFrame()
    kind_names = {"letters": "letter", "meetings": "meeting"}
    drop = {kind_names.get(k, k) for k in kinds}
    if not old.empty:
        old = old[~old["kind"].isin(drop | ({"article", "lecture", "partnership", "manual"}
                                            if "lectures" in kinds else set()))]
    new = pd.DataFrame(rows)
    out = pd.concat([old, new], ignore_index=True)
    cols = ["kind", "year", "title", "url", "status", "chars", "path"]
    out = out.reindex(columns=cols).sort_values(["kind", "year", "title"])
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
    kinds = sys.argv[2:] or ["letters", "lectures", "meetings"]
    rows = []
    for k in kinds:
        print(f"fetching {k} ...")
        rows += {"letters": fetch_letters, "meetings": fetch_meetings, "lectures": fetch_lectures}[k]()
    out = write_sources(rows, kinds)
    print(out.groupby(["kind", "status"]).size().to_string())
