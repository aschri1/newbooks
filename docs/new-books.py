#!/usr/bin/env python

import urllib.parse
import urllib.request
import config
import xmltodict
import pprint
import json
import time
from urllib.error import HTTPError

base_url = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/analytics/reports"
api_key = config.ALMA_API_KEY
gb_api_key = config.GB_API_KEY

path = (
    "/shared/Art Institute of Chicago/Reports/newbooks"
)
params = {"apikey": api_key, "path": path, "limit": "50", "col_names": "true"}
url = base_url + "?" + urllib.parse.urlencode(params)

# function to lookup Google Books API by ISBN
def isbn_lookup(ISBNs):
    for ISBN in ISBNs.split("; "):
        gb_url = (
            "https://www.googleapis.com/books/v1/volumes?key="
            + gb_api_key
            + "&q=isbn:"
            + ISBN
            + "&fields=totalItems,items/id,items/volumeInfo(title,description,previewLink,imageLinks)&maxResults=1"
        )
        with urllib.request.urlopen(gb_url) as gb_response:
            gb_api = gb_response.read()
            gb_json_data = json.loads(gb_api)
            if "items" in gb_json_data:
                try:
                    thumbnail = gb_json_data["items"][0]["volumeInfo"]["imageLinks"][
                        "thumbnail"
                    ]
                    return thumbnail.replace("http:", "https:")
                except Exception as e:
                    thumbnail = ""
    return ""



with urllib.request.urlopen(url) as response:
    xml = response.read()
    dict = xmltodict.parse(xml)
    records = dict["report"]["QueryResult"]["ResultXml"]["rowset"]["Row"]
    formatted_records = []
    for record in records:
        formatted_record = {
            "title": "",
            "author": "",
            "primo-url": "",
            "call-number": "",
            "cover-url": "",
            "created": "",
        }
        if "Column4" in record:
            formatted_record["title"] = record["Column4"].replace(
                "/", "").rstrip()
        if "Column1" in record:
            formatted_record["author"] = record["Column1"]
        if "Column4" in record:
            formatted_record["primo-url"] = (
                "https://artic.primo.exlibrisgroup.com/discovery/fulldisplay?docid=alma"
                + record["Column3"]
                + "&context=L&vid=01ARTIC_INST:01ARTIC&search_scope=MyInst_and_CI&tab=Everything&lang=en"
            )
        if "Column6" in record:
            formatted_record["call-number"] = record["Column6"]
        if "Column2" in record and record["Column2"]:
            ISBNs = record["Column2"]
            formatted_record["cover-url"] = isbn_lookup(ISBNs)
        if "Column7" in record:
            formatted_record["created"] = record["Column7"]

        if formatted_record["cover-url"] != "":
            formatted_records.append(formatted_record)

    filename = "gh-pages/new-books.json"
    with open(filename, "w") as outfile:
        json.dump(formatted_records, outfile, indent=4)


# Example usage
retry_count = 0
max_retries = 3

for record in records:  # Assuming records is the iterable containing your data
    formatted_record = {
        "title": "",
        "author": "",
        "primo-url": "",
        "call-number": "",
        "cover-url": "",  # Initialize cover-url here
    }

    if "Column2" in record and record["Column2"]:
        ISBNs = record["Column2"]

        while retry_count < max_retries:
            try:
                formatted_record["cover-url"] = isbn_lookup(ISBNs)
                break  # Break out of the loop if the request is successful
            except HTTPError as e:
                if e.code == 429:
                        # Check for the Retry-After header
                        retry_after = e.headers.get('Retry-After')
                        if retry_after:
                            time.sleep(int(retry_after))  # Wait for the specified time
                            return isbn_lookup(ISBNs)  # Retry the request
                else:
                    raise  # Re-raise any other HTTPError
        else:
            print("Maximum number of retries reached. Unable to make the request.")

    # Rest of your code for processing the record and appending to formatted_records
