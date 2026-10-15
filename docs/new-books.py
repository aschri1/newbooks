#!/usr/bin/env python3

import os
import time
import urllib.parse
import json
import sys
from typing import List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xmltodict
import config

BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/analytics/reports"
API_KEY = config.ALMA_API_KEY
GB_API_KEY = config.GB_API_KEY

PATH = "/shared/Art Institute of Chicago/Reports/newbooks"
PARAMS = {"apikey": API_KEY, "path": PATH, "limit": "50", "col_names": "true"}
URL = BASE_URL + "?" + urllib.parse.urlencode(PARAMS)

OUTPUT_DIR = "gh-pages"  # this script is run from docs/ so gh-pages -> docs/gh-pages
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "new-books.json")
NO_DATA_MARKER = os.path.join(OUTPUT_DIR, "NO_DATA")

# Network retry configuration
DEFAULT_RETRIES = 5
BACKOFF_FACTOR = 1
STATUS_FORCELIST = (429, 500, 502, 503, 504)
TIMEOUT = 10  # seconds


def create_session(retries: int = DEFAULT_RETRIES, backoff_factor: float = BACKOFF_FACTOR) -> requests.Session:
    """Create a requests Session with urllib3 Retry configured."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=STATUS_FORCELIST,
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def isbn_lookup(session: requests.Session, isbns: str) -> str:
    """Return a cover thumbnail URL for the first ISBN that yields one, else empty string."""
    if not isbns:
        return ""

    for isbn in isbns.split("; "):
        try:
            gb_url = (
                "https://www.googleapis.com/books/v1/volumes?key="
                + GB_API_KEY
                + "&q=isbn:"
                + urllib.parse.quote(isbn)
                + "&fields=totalItems,items/id,items/volumeInfo(title,description,previewLink,imageLinks)&maxResults=1"
            )
            resp = session.get(gb_url, timeout=TIMEOUT)
            # even if requests does retries, check status
            if resp.status_code != 200:
                print(f"Google Books lookup returned {resp.status_code} for ISBN {isbn}")
                continue
            gb_json_data = resp.json()
            if "items" in gb_json_data:
                img = gb_json_data["items"][0]["volumeInfo"].get("imageLinks", {}).get("thumbnail")
                if img:
                    return img.replace("http:", "https:")
        except Exception as e:
            print(f"Error during Google Books lookup for ISBN {isbn}: {e}")
            # continue to next ISBN
            continue
    return ""


def isbn_lookup_with_retries(session: requests.Session, isbns: str, max_retries: int = 3) -> str:
    attempt = 0
    while attempt < max_retries:
        result = isbn_lookup(session, isbns)
        if result:
            return result
        attempt += 1
        wait = (2 ** attempt)
        print(f"ISBN lookup attempt {attempt} failed; sleeping {wait}s and retrying...")
        time.sleep(wait)
    return ""


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def write_no_data_marker():
    ensure_output_dir()
    with open(NO_DATA_MARKER, "w", encoding="utf-8") as f:
        f.write("no data produced\n")


def remove_no_data_marker():
    try:
        if os.path.exists(NO_DATA_MARKER):
            os.remove(NO_DATA_MARKER)
    except Exception:
        pass


def fetch_alma_report(session: requests.Session) -> List[dict]:
    """Fetch Alma analytics report and return parsed rows (may be empty list)."""
    try:
        resp = session.get(URL, timeout=TIMEOUT)
        if resp.status_code != 200:
            print(f"Alma report request returned status {resp.status_code}")
            return []
        xml = resp.content
        data = xmltodict.parse(xml)
        # Navigate safely to the rows
        rows = data.get("report", {}).get("QueryResult", {}).get("ResultXml", {}).get("rowset", {}).get("Row", [])
        # If a single row, xmltodict may return an OrderedDict instead of list
        if isinstance(rows, dict):
            rows = [rows]
        return rows
    except Exception as e:
        print(f"Error fetching or parsing Alma report: {e}")
        return []


def main():
    # Basic checks
    if not API_KEY:
        print("ALMA_API_KEY is not set in config.py")
        sys.exit(1)
    if not GB_API_KEY:
        print("GB_API_KEY is not set in config.py")
        sys.exit(1)

    ensure_output_dir()

    session = create_session()

    rows = fetch_alma_report(session)

    formatted_records = []
    for record in rows:
        fr = {
            "title": "",
            "author": "",
            "primo-url": "",
            "call-number": "",
            "cover-url": "",
            "created": "",
        }

        if "Column4" in record:
            fr["title"] = record["Column4"].replace("/", "").rstrip()
        if "Column1" in record:
            fr["author"] = record["Column1"]
        if "Column3" in record:
            fr["primo-url"] = (
                "https://artic.primo.exlibrisgroup.com/discovery/fulldisplay?docid=alma"
                + record.get("Column3", "")
                + "&context=L&vid=01ARTIC_INST:01ARTIC&search_scope=MyInst_and_CI&tab=Everything&lang=en"
            )
        if "Column6" in record:
            fr["call-number"] = record["Column6"]
        if record.get("Column2"):
            fr["cover-url"] = isbn_lookup_with_retries(session, record["Column2"])
        if "Column7" in record:
            fr["created"] = record["Column7"]

        # Only include records that have a cover (keeps previous behavior)
        if fr["cover-url"]:
            formatted_records.append(fr)

    # Always write a JSON file (may be empty)
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:
            json.dump(formatted_records, outfile, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to write output file {OUTPUT_FILE}: {e}")
        sys.exit(1)

    if not formatted_records:
        print("No book records produced (empty list). Creating NO_DATA marker so the workflow can skip deployment.")
        write_no_data_marker()
    else:
        remove_no_data_marker()
        print(f"Wrote {len(formatted_records)} records to {OUTPUT_FILE}")

    # Exit successfully; workflow will inspect NO_DATA marker to decide whether to deploy
    sys.exit(0)


if __name__ == "__main__":
    main()
