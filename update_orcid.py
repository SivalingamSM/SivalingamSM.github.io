import html
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests


# ============================================================
# CONFIGURATION
# ============================================================

ORCID_ID = "0000-0003-0818-9007"
EMAIL = "siva915544@gmail.com"

ORCID_URL = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"

CROSSREF_API = "https://api.crossref.org/works"
OPENALEX_API = "https://api.openalex.org/works"

PUBLICATIONS_OUTPUT = Path("publications-auto.qmd")
HOME_UPDATES_OUTPUT = Path("home-updates.qmd")


ORCID_HEADERS = {
    "Accept": "application/vnd.orcid+json",
    "User-Agent": (
        f"SivalingamSM-Academic-Website/1.0 "
        f"(mailto:{EMAIL})"
    ),
}


API_HEADERS = {
    "User-Agent": (
        f"SivalingamSM-Academic-Website/1.0 "
        f"(mailto:{EMAIL})"
    ),
}


# ============================================================
# GENERAL UTILITIES
# ============================================================

def clean(value):
    if value is None:
        return ""

    value = str(value)

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def escape_html(value):
    return html.escape(
        clean(value),
        quote=True,
    )


def normalize_doi(doi):
    doi = clean(doi)

    doi = re.sub(
        r"^https?://(dx\.)?doi\.org/",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    doi = re.sub(
        r"^doi:\s*",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    return doi.strip()


# ============================================================
# ORCID
# ============================================================

def get_orcid_works():
    print(f"Reading ORCID record: {ORCID_ID}")

    response = requests.get(
        ORCID_URL,
        headers=ORCID_HEADERS,
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    works = []

    for group in data.get("group", []):
        summaries = group.get(
            "work-summary",
            [],
        )

        if not summaries:
            continue

        summary = summaries[0]

        title_data = summary.get("title") or {}

        title = (
            title_data
            .get("title", {})
            .get("value", "")
        )

        publication_date = (
            summary.get("publication-date")
            or {}
        )

        year = ""

        if publication_date.get("year"):
            year = clean(
                publication_date["year"]
                .get("value", "")
            )

        journal = ""

        journal_data = summary.get(
            "journal-title"
        )

        if journal_data:
            journal = clean(
                journal_data.get("value", "")
            )

        doi = ""

        external_ids = (
            summary
            .get("external-ids", {})
            .get("external-id", [])
        )

        for external_id in external_ids:
            identifier_type = clean(
                external_id.get(
                    "external-id-type",
                    "",
                )
            ).lower()

            if identifier_type == "doi":
                doi = normalize_doi(
                    external_id.get(
                        "external-id-value",
                        "",
                    )
                )

                break

        works.append(
            {
                "title": clean(title),
                "year": year,
                "journal": journal,
                "doi": doi,
            }
        )

    return works


# ============================================================
# CROSSREF
# ============================================================

def get_crossref_metadata(doi):
    if not doi:
        return None

    url = (
        CROSSREF_API
        + "/"
        + quote(doi, safe="")
    )

    try:
        response = requests.get(
            url,
            headers=API_HEADERS,
            params={
                "mailto": EMAIL,
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(
                f"  Crossref unavailable: {doi}"
            )

            return None

        return response.json().get(
            "message"
        )

    except requests.RequestException as error:
        print(
            f"  Crossref error for {doi}: "
            f"{error}"
        )

        return None


# ============================================================
# OPENALEX
# ============================================================

def get_openalex_metadata(doi):
    if not doi:
        return None

    openalex_id = (
        "https://doi.org/"
        + doi
    )

    url = (
        OPENALEX_API
        + "/"
        + quote(
            openalex_id,
            safe="",
        )
    )

    try:
        response = requests.get(
            url,
            headers=API_HEADERS,
            params={
                "mailto": EMAIL,
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(
                f"  Citation metadata unavailable: {doi}"
            )

            return None

        return response.json()

    except requests.RequestException as error:
        print(
            f"  Citation metadata error for {doi}: "
            f"{error}"
        )

        return None


# ============================================================
# AUTHORS
# ============================================================

def get_crossref_authors(metadata):
    authors = []

    if not metadata:
        return authors

    for author in metadata.get(
        "author",
        [],
    ):
        given = clean(
            author.get("given", "")
        )

        family = clean(
            author.get("family", "")
        )

        name = " ".join(
            part
            for part in [given, family]
            if part
        )

        if name:
            authors.append(name)

    return authors


def get_openalex_authors(metadata):
    authors = []

    if not metadata:
        return authors

    for authorship in metadata.get(
        "authorships",
        [],
    ):
        author = (
            authorship.get("author") or {}
        )

        name = clean(
            author.get("display_name", "")
        )

        if name:
            authors.append(name)

    return authors


# ============================================================
# METADATA EXTRACTION
# ============================================================

def get_year(crossref, openalex, fallback):
    date_fields = [
        "published-print",
        "published-online",
        "issued",
    ]

    if crossref:
        for field in date_fields:
            date = crossref.get(field)

            if not date:
                continue

            date_parts = date.get(
                "date-parts",
                [],
            )

            if (
                date_parts
                and date_parts[0]
                and date_parts[0][0]
            ):
                return str(
                    date_parts[0][0]
                )

    if openalex:
        year = openalex.get(
            "publication_year"
        )

        if year:
            return str(year)

    return fallback or "Undated"


def get_journal(crossref, openalex, fallback):
    if crossref:
        containers = crossref.get(
            "container-title",
            [],
        )

        if containers:
            return clean(containers[0])

    if openalex:
        primary_location = (
            openalex.get("primary_location")
            or {}
        )

        source = (
            primary_location.get("source")
            or {}
        )

        journal = clean(
            source.get("display_name", "")
        )

        if journal:
            return journal

    return fallback


def get_title(crossref, openalex, fallback):
    if crossref:
        titles = crossref.get(
            "title",
            [],
        )

        if titles:
            return clean(titles[0])

    if openalex:
        title = clean(
            openalex.get(
                "display_name",
                "",
            )
        )

        if title:
            return title

    return fallback


# ============================================================
# BUILD PUBLICATION DATABASE
# ============================================================

def build_publications(works):
    publications = []

    seen = set()

    total = len(works)

    for index, work in enumerate(
        works,
        start=1,
    ):
        print(
            f"[{index}/{total}] "
            f"{work['title']}"
        )

        doi = work["doi"]

        unique_key = (
            doi.lower()
            if doi
            else work["title"].lower()
        )

        if unique_key in seen:
            continue

        seen.add(unique_key)

        crossref = get_crossref_metadata(
            doi
        )

        openalex = get_openalex_metadata(
            doi
        )

        authors = get_crossref_authors(
            crossref
        )

        if not authors:
            authors = get_openalex_authors(
                openalex
            )

        if not authors:
            authors = ["Sivalingam S M"]

        title = get_title(
            crossref,
            openalex,
            work["title"],
        )

        journal = get_journal(
            crossref,
            openalex,
            work["journal"],
        )

        year = get_year(
            crossref,
            openalex,
            work["year"],
        )

        volume = ""
        issue = ""
        pages = ""

        if crossref:
            volume = clean(
                crossref.get(
                    "volume",
                    "",
                )
            )

            issue = clean(
                crossref.get(
                    "issue",
                    "",
                )
            )

            pages = clean(
                crossref.get(
                    "page",
                    "",
                )
            )

        citation_count = 0

        if openalex:
            citation_count = int(
                openalex.get(
                    "cited_by_count",
                    0,
                )
                or 0
            )

        publications.append(
            {
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "volume": volume,
                "issue": issue,
                "pages": pages,
                "doi": doi,
                "citations": citation_count,
            }
        )

        time.sleep(0.15)

    return publications


# ============================================================
# AUTHOR FORMATTING
# ============================================================

def format_authors(authors):
    output = []

    for author in authors:
        author_html = escape_html(author)

        normalized = re.sub(
            r"[^a-z]",
            "",
            author.lower(),
        )

        is_me = (
            "sivalingam" in normalized
            and (
                normalized.endswith("sm")
                or "sivalingamsm" in normalized
                or normalized.startswith(
                    "smsivalingam"
                )
            )
        )

        if is_me:
            output.append(
                '<strong class="my-name">'
                + author_html
                + "</strong>"
            )
        else:
            output.append(author_html)

    if len(output) == 1:
        return output[0]

    if len(output) == 2:
        return (
            output[0]
            + " and "
            + output[1]
        )

    return (
        ", ".join(output[:-1])
        + ", and "
        + output[-1]
    )


# ============================================================
# SORTING
# ============================================================

def sort_publications(publications):
    def key(item):
        try:
            year = int(item["year"])
        except ValueError:
            year = 0

        return (
            year,
            item["citations"],
            item["title"].lower(),
        )

    return sorted(
        publications,
        key=key,
        reverse=True,
    )


# ============================================================
# JOURNAL LINE
# ============================================================

def create_journal_line(publication):
    journal = escape_html(
        publication["journal"]
    )

    volume = escape_html(
        publication["volume"]
    )

    issue = escape_html(
        publication["issue"]
    )

    pages = escape_html(
        publication["pages"]
    )

    year = escape_html(
        publication["year"]
    )

    output = ""

    if journal:
        output += f"<em>{journal}</em>"

    if volume:
        output += (
            f", <strong>{volume}</strong>"
        )

    if issue:
        output += f"({issue})"

    if pages:
        output += f", {pages}"

    if output:
        output += f" ({year})"
    else:
        output = year

    return output


# ============================================================
# PUBLICATIONS PAGE
# ============================================================

def write_publications_qmd(publications):
    publications = sort_publications(
        publications
    )

    total = len(publications)

    total_citations = sum(
        publication["citations"]
        for publication in publications
    )

    valid_years = {
        publication["year"]
        for publication in publications
        if publication["year"] != "Undated"
    }

    lines = []

    lines.append(
        f"""```{{=html}}
<div class="research-metrics">
  <div class="metric-card">
    <div class="metric-number">{total}</div>
    <div class="metric-label">Publications</div>
  </div>

  <div class="metric-card">
    <div class="metric-number">{total_citations:,}</div>
    <div class="metric-label">Citations</div>
  </div>

  <div class="metric-card">
    <div class="metric-number">{len(valid_years)}</div>
    <div class="metric-label">Publication Years</div>
  </div>
</div>

<div class="publication-toolbar">
  <input
    type="text"
    id="publication-search"
    placeholder="Search by title, author, journal, or year..."
    onkeyup="filterPublications()"
  >
</div>
```"""
    )

    lines.append("")

    current_year = None

    for index, publication in enumerate(
        publications
    ):
        year = publication["year"]

        if year != current_year:
            lines.append(f"## {year}")
            lines.append("")

            current_year = year

        number = total - index

        authors = format_authors(
            publication["authors"]
        )

        title = escape_html(
            publication["title"]
        )

        journal_line = create_journal_line(
            publication
        )

        doi = publication["doi"]

        citations = publication["citations"]

        search_text = escape_html(
            " ".join(
                [
                    publication["title"],
                    " ".join(
                        publication["authors"]
                    ),
                    publication["journal"],
                    publication["year"],
                ]
            ).lower()
        )

        doi_button = ""

        if doi:
            doi_button = (
                '<a class="publication-button" '
                f'href="https://doi.org/'
                f'{escape_html(doi)}" '
                'target="_blank" '
                'rel="noopener noreferrer">'
                'DOI'
                '</a>'
            )

        citation_button = (
            '<span class="citation-button '
            'citation-disabled">'
            f'Cited by {citations}'
            '</span>'
        )

        card = f"""```{{=html}}
<div class="publication-card" data-search="{search_text}">
  <div class="publication-index">{number}</div>

  <div class="publication-content">
    <div class="publication-title">{title}</div>

    <div class="publication-authors">{authors}</div>

    <div class="publication-journal">{journal_line}</div>

    <div class="publication-actions">
      {doi_button}
      {citation_button}
    </div>
  </div>
</div>
```"""

        lines.append(card)
        lines.append("")

    lines.append(
        """```{=html}
<script>
function filterPublications() {
  const input =
    document.getElementById("publication-search");

  const filter =
    input.value.toLowerCase().trim();

  const cards =
    document.querySelectorAll(".publication-card");

  cards.forEach(function(card) {
    const text =
      (card.dataset.search || "").toLowerCase();

    card.style.display =
      text.includes(filter) ? "" : "none";
  });

  document.querySelectorAll("h2").forEach(
    function(heading) {

      const yearPattern =
        /^\\d{4}$|^Undated$/;

      if (
        !yearPattern.test(
          heading.textContent.trim()
        )
      ) {
        return;
      }

      let next =
        heading.nextElementSibling;

      let visiblePublication = false;

      while (
        next
        && next.tagName !== "H2"
      ) {
        if (
          next.classList
          && next.classList.contains(
            "publication-card"
          )
          && next.style.display !== "none"
        ) {
          visiblePublication = true;
        }

        next = next.nextElementSibling;
      }

      heading.style.display =
        visiblePublication ? "" : "none";
    }
  );
}
</script>
```"""
    )

    PUBLICATIONS_OUTPUT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        f"Created {PUBLICATIONS_OUTPUT}"
    )


# ============================================================
# AUTOMATIC HOME PAGE RESEARCH FEED
# ============================================================

def write_home_updates_qmd(publications):
    publications = sort_publications(
        publications
    )

    latest = publications[:3]

    lines = []

    lines.append(
        """```{=html}
<div class="research-feed">
"""
    )

    for publication in latest:
        title = escape_html(
            publication["title"]
        )

        journal = escape_html(
            publication["journal"]
        )

        year = escape_html(
            publication["year"]
        )

        doi = publication["doi"]

        citations = publication["citations"]

        if doi:
            title_html = (
                f'<a href="https://doi.org/'
                f'{escape_html(doi)}" '
                'target="_blank" '
                'rel="noopener noreferrer">'
                f'{title}'
                '</a>'
            )
        else:
            title_html = title

        lines.append(
            f"""
<div class="research-update">
  <div class="research-update-year">{year}</div>

  <div class="research-update-content">
    <div class="research-update-label">
      PUBLICATION
    </div>

    <div class="research-update-title">
      {title_html}
    </div>

    <div class="research-update-journal">
      {journal}
    </div>

    <div class="research-update-citations">
      {citations} citations
    </div>
  </div>
</div>
"""
        )

    lines.append(
        """
</div>
```"""
    )

    HOME_UPDATES_OUTPUT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        f"Created {HOME_UPDATES_OUTPUT}"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        works = get_orcid_works()

        print(
            f"Found {len(works)} ORCID works."
        )

        publications = build_publications(
            works
        )

        if not publications:
            print(
                "No publications found."
            )

            sys.exit(1)

        write_publications_qmd(
            publications
        )

        write_home_updates_qmd(
            publications
        )

        total_citations = sum(
            publication["citations"]
            for publication in publications
        )

        print("")
        print("Website research data updated.")
        print(
            f"Publications: {len(publications)}"
        )
        print(
            f"Citations: {total_citations}"
        )

    except Exception as error:
        print("")
        print(
            "Publication update failed:"
        )

        print(error)

        sys.exit(1)


if __name__ == "__main__":
    main()