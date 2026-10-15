#!/usr/bin/env python3

import os
import time
import urllib.parse
import urllib.request
import json
from urllib.error import HTTPError
import xmltodict
import config

BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/analytics/reports"
API_KEY = config.ALMA_API_KEY
GB_API_KEY = config.GB_API_KEY

PATH = "/shared/Art Institute of Chicago/Reports/newbooks"
PARAMS = {"apikey": API_KEY, "path": PATH, "limit": "50", "col_names": "true"}
URL = BASE_URL + "?" + urllib.parse.urlencode(PARAMS)

OUTPUT_DIR = "gh-pages"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "new-books.json")
MAX_RETRIES = 3

def isbn_lookup(ISBNs):
    """Return a cover thumbnail URL for the first ISBN that yields one, else ''."""
    for ISBN in ISBNs.split("; "):
        gb_url = (
            "https://www.googleapis.com/books/v1/volumes?key="
            + GB_API_KEY
            + "&q=isbn:"
            + urllib.parse.quote(ISBN)
            + "&fields=totalItems,items/id,items/volumeInfo(title,description,previewLink,imageLinks)&maxResults=1"
        )
        with urllib.request.urlopen(gb_url) as gb_response:
            gb_json_data = json.load(gb_response)
            if "items" in gb_json_data:
                img = gb_json_data["items"][0]["volumeInfo"].get("imageLinks", {}).get("thumbnail")
                if img:
                    return img.replace("http:", "https:")
    return ""

def isbn_lookup_with_retries(ISBNs, max_retries=MAX_RETRIES):
    attempt = 0
    while attempt < max_retries:
        try:
            return isbn_lookup(ISBNs)
        except HTTPError as e:
            if e.code == 429:
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt)
                time.sleep(wait)
                attempt += 1
            else:
                raise
    return ""

def main():
    # Ensure output dir exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Fetch Alma report
    with urllib.request.urlopen(URL) as response:
        xml = response.read()
    data = xmltodict.parse(xml)
    records = data["report"]["QueryResult"]["ResultXml"]["rowset"]["Row"]

    formatted_records = []
    for record in records:
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
            fr["cover-url"] = isbn_lookup_with_retries(record["Column2"])
        if "Column7" in record:
            fr["created"] = record["Column7"]

        # Only include records that have a cover (keeps previous behavior)
        if fr["cover-url"]:
            formatted_records.append(fr)

    # Write output (always write a JSON file, even if empty list)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:
        json.dump(formatted_records, outfile, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    main()
