import re
import sys
from pathlib import Path

import requests
import bibtexparser


ORCID_ID = "0000-0003-0818-9007"

ORCID_API = (
    f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
)

OUTPUT_FILE = Path("publications.bib")

HEADERS = {
    "Accept": "application/vnd.orcid+json",
    "User-Agent": (
        "SivalingamSM-Academic-Website/"
        "1.0 (ORCID publication synchronizer)"
    ),
}


def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    value = value.replace("\n", " ")
    value = value.replace("\r", " ")
    value = value.replace("\t", " ")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def escape_bibtex(value):
    value = clean_text(value)

    value = value.replace("\\", r"\textbackslash{}")
    value = value.replace("&", r"\&")
    value = value.replace("%", r"\%")
    value = value.replace("#", r"\#")

    return value


def get_value(item):
    if not item:
        return ""

    if isinstance(item, dict):
        return item.get("value", "") or ""

    return str(item)


def get_year(summary):
    publication_date = summary.get("publication-date")

    if not publication_date:
        return ""

    year = publication_date.get("year")

    return get_value(year)


def get_external_ids(summary):
    external_ids = summary.get("external-ids") or {}

    return external_ids.get("external-id") or []


def get_identifier(summary, identifier_type):
    identifier_type = identifier_type.lower()

    for external_id in get_external_ids(summary):

        current_type = clean_text(
            external_id.get("external-id-type")
        ).lower()

        if current_type == identifier_type:
            return clean_text(
                external_id.get("external-id-value")
            )

    return ""


def get_url(summary):
    url = summary.get("url")

    if isinstance(url, dict):
        return clean_text(url.get("value"))

    return ""


def make_key(title, year, number):
    words = re.findall(
        r"[A-Za-z0-9]+",
        title
    )

    if words:
        first_word = words[0].lower()
    else:
        first_word = "publication"

    year = year or "nd"

    return f"sivalingam{year}{first_word}{number}"


def get_work_summaries():
    print(f"Reading ORCID record: {ORCID_ID}")

    response = requests.get(
        ORCID_API,
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    summaries = []

    for group in data.get("group", []):

        work_summaries = group.get(
            "work-summary",
            []
        )

        if not work_summaries:
            continue

        # ORCID may contain several versions of the same work.
        # Use the first summary from each ORCID work group.
        summaries.append(work_summaries[0])

    return summaries


def convert_to_bibtex(summaries):
    entries = []

    seen = set()

    summaries = sorted(
        summaries,
        key=lambda item: get_year(item),
        reverse=True,
    )

    for number, summary in enumerate(
        summaries,
        start=1,
    ):

        title_data = summary.get("title") or {}
        title_item = title_data.get("title") or {}

        title = get_value(title_item)

        if not title:
            continue

        year = get_year(summary)

        journal = clean_text(
            summary.get("journal-title", {})
            .get("value", "")
            if summary.get("journal-title")
            else ""
        )

        work_type = clean_text(
            summary.get("type")
        ).lower()

        doi = get_identifier(summary, "doi")

        url = get_url(summary)

        unique_id = (
            doi.lower()
            if doi
            else title.lower()
        )

        if unique_id in seen:
            continue

        seen.add(unique_id)

        citation_key = make_key(
            title,
            year,
            number,
        )

        entry = {
            "ID": citation_key,
            "ENTRYTYPE": "article",
            "title": escape_bibtex(title),
            "author": "Sivalingam, S. M.",
        }

        if year:
            entry["year"] = year

        if journal:
            entry["journal"] = escape_bibtex(journal)

        if doi:
            entry["doi"] = doi
            entry["url"] = f"https://doi.org/{doi}"

        elif url:
            entry["url"] = url

        if work_type:
            entry["note"] = (
                "ORCID work type: "
                + escape_bibtex(work_type)
            )

        entries.append(entry)

    return entries


def write_bibliography(entries):
    library = bibtexparser.bibdatabase.BibDatabase()

    library.entries = entries

    writer = bibtexparser.bwriter.BibTexWriter()

    writer.indent = "  "

    bibtex = writer.write(library)

    OUTPUT_FILE.write_text(
        bibtex,
        encoding="utf-8",
    )

    print(
        f"Created {OUTPUT_FILE} "
        f"with {len(entries)} publications."
    )


def main():
    try:
        summaries = get_work_summaries()

        print(
            f"Found {len(summaries)} "
            "ORCID work groups."
        )

        entries = convert_to_bibtex(summaries)

        if not entries:
            print(
                "ERROR: No public publications "
                "were found in the ORCID record."
            )

            sys.exit(1)

        write_bibliography(entries)

    except requests.RequestException as error:
        print(
            "ORCID API request failed:"
        )

        print(error)

        sys.exit(1)

    except Exception as error:
        print(
            "Publication update failed:"
        )

        print(error)

        raise


if __name__ == "__main__":
    main()