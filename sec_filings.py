from __future__ import annotations

import re
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import streamlit as st

from data_sources import SEC_HEADERS, WATCHLIST

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

IMPORTANT_FORMS = {
    "8-K", "10-K", "10-Q", "4",
    "SC 13D", "SC 13G", "13D", "13G",
    "SC 13D/A", "SC 13G/A", "13D/A", "13G/A"
}

# These are screening terms, not proof that a company has a problem.
RISK_TERMS = {
    "Liquidity / solvency": [
        "substantial doubt", "going concern", "liquidity risk",
        "default", "debt covenant", "unable to meet"
    ],
    "Dilution / capital raising": [
        "at-the-market", "at the market offering", "offering of shares",
        "registered direct offering", "dilutive", "dilution",
        "convertible notes", "warrant exercise"
    ],
    "Legal / regulatory": [
        "material litigation", "class action", "regulatory investigation",
        "subpoena", "consent decree", "government investigation"
    ],
    "Operations / business": [
        "material weakness", "cybersecurity incident",
        "business interruption", "impairment charge",
        "restructuring", "termination of agreement"
    ],
    "Financial performance": [
        "impairment", "significant decline in revenue",
        "net loss", "negative cash flow"
    ]
}


@st.cache_data(ttl=86400, show_spinner=False)
def get_company_ciks() -> dict:
    r = requests.get(SEC_TICKERS_URL, headers=SEC_HEADERS, timeout=25)
    r.raise_for_status()
    payload = r.json()
    return {
        v["ticker"].upper(): str(v["cik_str"]).zfill(10)
        for v in payload.values()
    }


@st.cache_data(ttl=1800, show_spinner=False)
def get_company_filings(ticker: str, limit: int = 60) -> pd.DataFrame:
    ticker = ticker.upper()
    cik = get_company_ciks().get(ticker)

    if not cik:
        return pd.DataFrame()

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=25)
    r.raise_for_status()
    data = r.json()

    recent = data.get("filings", {}).get("recent", {})
    rows = []

    forms = recent.get("form", [])
    for i, form in enumerate(forms):
        if form not in IMPORTANT_FORMS:
            continue

        accession = recent["accessionNumber"][i]
        primary = recent["primaryDocument"][i]
        accession_clean = accession.replace("-", "")

        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{accession_clean}/{primary}"
        )

        rows.append({
            "Ticker": ticker,
            "Company": data.get("name", ticker),
            "Form": form,
            "Filing Date": recent["filingDate"][i],
            "Report Date": recent.get("reportDate", [""] * len(forms))[i],
            "Description": recent.get(
                "primaryDocDescription", [""] * len(forms)
            )[i],
            "Accession": accession,
            "URL": doc_url,
            "CIK": cik
        })

        if len(rows) >= limit:
            break

    return pd.DataFrame(rows)


@st.cache_data(ttl=1800, show_spinner=False)
def get_watchlist_filings() -> pd.DataFrame:
    frames = []

    for ticker in WATCHLIST:
        try:
            df = get_company_filings(ticker)
            if not df.empty:
                frames.append(df)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out["Filing Date"] = pd.to_datetime(
        out["Filing Date"], errors="coerce"
    )
    return out.sort_values(
        ["Filing Date", "Ticker"],
        ascending=[False, True]
    ).reset_index(drop=True)


def _plain_text(html: str) -> str:
    """Convert filing HTML to searchable plain text."""
    text = re.sub(
        r"(?is)<(script|style).*?>.*?</\1>", " ", html
    )
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sentences_around(text: str, phrase: str, width: int = 220) -> str:
    pos = text.lower().find(phrase.lower())
    if pos < 0:
        return ""
    start = max(0, pos - width // 2)
    end = min(len(text), pos + len(phrase) + width // 2)
    return text[start:end].strip()


@st.cache_data(ttl=3600, show_spinner=False)
def analyze_filing_document(url: str, form: str) -> dict:
    """
    Basic rule-based screening of the filing's primary document.
    This is not a legal, accounting or investment conclusion.
    """
    result = {
        "status": "Not analysed",
        "form": form,
        "word_count": 0,
        "risk_flags": [],
        "evidence": [],
        "summary": "",
        "limitation": ""
    }

    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=35)
        r.raise_for_status()

        # Avoid trying to process an unexpectedly huge document.
        raw = r.text[:5_000_000]
        text = _plain_text(raw)
        lower = text.lower()

        if len(text) < 300:
            result["status"] = "Document text unavailable"
            result["limitation"] = (
                "The primary filing document did not return enough "
                "readable text for screening."
            )
            return result

        result["word_count"] = len(text.split())
        flags = []
        evidence = []

        for category, terms in RISK_TERMS.items():
            found = []
            for term in terms:
                count = lower.count(term.lower())
                if count:
                    found.append((term, count))

            if found:
                flags.append({
                    "Category": category,
                    "Terms found": ", ".join(
                        f"{term} ({count})" for term, count in found
                    )
                })

                for term, _ in found[:2]:
                    evidence.append({
                        "Category": category,
                        "Matched term": term,
                        "Context": _sentences_around(text, term)
                    })

        result["risk_flags"] = flags
        result["evidence"] = evidence
        result["status"] = "Screened"

        if flags:
            result["summary"] = (
                f"Screening found terms in {len(flags)} risk category "
                f"(or categories). Open the filing and read the context "
                f"before drawing conclusions."
            )
        else:
            result["summary"] = (
                "No configured risk terms were detected. This does not "
                "mean the filing is risk-free."
            )

        result["limitation"] = (
            "Automated keyword screening only. Matches may be routine, "
            "historical or discussed as risks that have not occurred. "
            "The scan may miss risks expressed in different wording, "
            "tables, exhibits or documents not included in the primary file."
        )

    except Exception as exc:
        result["status"] = "Analysis unavailable"
        result["limitation"] = str(exc)[:300]

    return result




def parse_form4_xml(url: str, ticker: str = "") -> list[dict]:
    """Parse Form 4 transactions, keeping transaction code and ownership separate."""
    raw_url = url.replace("/xslF345X06/", "/")
    r = requests.get(raw_url, headers=SEC_HEADERS, timeout=25)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    def txt(node, path):
        if node is None:
            return ""
        el = node.find(path)
        return el.text.strip() if el is not None and el.text else ""

    owners = root.findall(".//reportingOwner")
    owner_details = []

    for owner in owners:
        name = txt(owner, ".//rptOwnerName") or "Not stated"
        relationship = owner.find(".//reportingOwnerRelationship")

        title = txt(relationship, "officerTitle")
        is_director = txt(relationship, "isDirector") == "1"
        is_officer = txt(relationship, "isOfficer") == "1"
        is_ten_percent = txt(relationship, "isTenPercentOwner") == "1"
        is_other = txt(relationship, "isOther") == "1"

        roles = []
        if is_director:
            roles.append("Director")
        if is_officer:
            roles.append("Officer")
        if is_ten_percent:
            roles.append("10% owner")
        if is_other:
            roles.append("Other")
        if title:
            roles.append(title)

        owner_details.append({
            "name": name,
            "role": ", ".join(roles) if roles else "Role not specified"
        })

    owner_names = "; ".join(x["name"] for x in owner_details) or "Not stated"
    owner_roles = "; ".join(
        f'{x["name"]}: {x["role"]}' for x in owner_details
    ) or "Not stated"

    rows = []

    for tx in root.findall(".//nonDerivativeTransaction"):
        code = txt(tx, ".//transactionCoding/transactionCode").upper()
        shares = txt(tx, ".//transactionAmounts/transactionShares/value")
        price = txt(tx, ".//transactionAmounts/transactionPricePerShare/value")
        date = txt(tx, ".//transactionDate/value")
        acquired = txt(
            tx, ".//transactionAmounts/transactionAcquiredDisposedCode/value"
        ).upper()

        security = txt(tx, ".//securityTitle/value")
        post_shares = txt(
            tx, ".//postTransactionAmounts/"
                "sharesOwnedFollowingTransaction/value"
        )
        ownership = txt(
            tx, ".//ownershipNature/directOrIndirectOwnership/value"
        ).upper()
        ownership_note = txt(
            tx, ".//ownershipNature/natureOfOwnership/value"
        )

        try:
            qty = float(shares) if shares else None
        except ValueError:
            qty = None

        try:
            px = float(price) if price else None
        except ValueError:
            px = None

        try:
            remaining = float(post_shares) if post_shares else None
        except ValueError:
            remaining = None

        code_labels = {
            "P": "Open-market purchase",
            "S": "Open-market sale",
            "A": "Grant / award",
            "M": "Option exercise",
            "F": "Tax withholding / payment",
            "G": "Gift",
            "C": "Conversion",
            "D": "Disposition to issuer",
            "J": "Other transaction",
            "X": "Option exercise / conversion"
        }
        transaction_type = code_labels.get(
            code, "Other / verify original filing"
        )

        side = (
            "Acquired" if acquired == "A"
            else "Disposed" if acquired == "D"
            else "Not stated"
        )

        if ownership == "D":
            ownership_type = "Direct"
        elif ownership == "I":
            ownership_type = "Indirect"
        else:
            ownership_type = "Not stated"

        rows.append({
            "Ticker": ticker.upper(),
            "Insider": owner_names,
            "Insider role": owner_roles,
            "Transaction Date": date,
            "Security": security,
            "Transaction Code": code,
            "Transaction Type": transaction_type,
            "Acquired / Disposed": side,
            "Ownership": ownership_type,
            "Ownership details": ownership_note,
            "Shares": qty,
            "Price": px,
            "Estimated Value": (
                qty * px if qty is not None and px is not None else None
            ),
            "Shares after transaction": remaining,
            "Source": url
        })

    return rows


EIGHT_K_ITEMS = {
    "1.01": "Entry into a material definitive agreement",
    "1.02": "Termination of a material definitive agreement",
    "1.03": "Bankruptcy or receivership",
    "2.01": "Completion of acquisition or disposition",
    "2.02": "Results of operations and financial condition",
    "2.03": "Creation of a direct financial obligation",
    "2.04": "Triggering events that accelerate obligations",
    "2.05": "Costs associated with exit or disposal activities",
    "2.06": "Material impairments",
    "3.01": "Notice of delisting or failure to satisfy listing rules",
    "3.02": "Unregistered sales of equity securities",
    "3.03": "Material modification to shareholder rights",
    "4.01": "Changes in certifying accountant",
    "4.02": "Non-reliance on previously issued financial statements",
    "5.01": "Changes in control of registrant",
    "5.02": "Departure or appointment of directors or officers",
    "5.03": "Amendments to articles or bylaws",
    "5.07": "Shareholder vote results",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other events",
    "9.01": "Financial statements and exhibits"
}


@st.cache_data(ttl=3600, show_spinner=False)
def extract_8k_events(url: str) -> dict:
    """Identify reported 8-K item numbers and provide nearby filing text."""
    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=35)
        r.raise_for_status()
        text = _plain_text(r.text[:5_000_000])

        if len(text) < 300:
            return {
                "status": "Document text unavailable",
                "events": [],
                "limitation": "The filing did not return enough readable text."
            }

        lower = text.lower()
        events = []

        for item, description in EIGHT_K_ITEMS.items():
            # SEC 8-K item headings usually appear as "Item 1.01".
            pattern = (
                r"\bitem\s+" + re.escape(item) +
                r"(?!\d)\s*[.\-:]?\s*"
            )
            matches = list(re.finditer(pattern, lower, flags=re.IGNORECASE))

            if matches:
                snippets = []
                for match in matches[:2]:
                    start = max(0, match.start() - 100)
                    end = min(len(text), match.end() + 650)
                    snippets.append(text[start:end].strip())

                events.append({
                    "Item": item,
                    "Event": description,
                    "Occurrences": len(matches),
                    "Context": "\n\n".join(snippets)
                })

        return {
            "status": "Screened",
            "events": events,
            "limitation": (
                "Item detection is automated. A detected item is not a "
                "judgement of whether the event is positive or negative. "
                "Read the complete filing and exhibits."
            )
        }

    except Exception as exc:
        return {
            "status": "Analysis unavailable",
            "events": [],
            "limitation": str(exc)[:300]
        }

@st.cache_data(ttl=3600, show_spinner=False)
def extract_8k_events(url: str) -> dict:
    """Identify reported 8-K item numbers and provide nearby filing text."""
    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=35)
        r.raise_for_status()
        text = _plain_text(r.text[:5_000_000])

        if len(text) < 300:
            return {
                "status": "Document text unavailable",
                "events": [],
                "limitation": "The filing did not return enough readable text."
            }

        lower = text.lower()
        events = []

        for item, description in EIGHT_K_ITEMS.items():
            # SEC 8-K item headings usually appear as "Item 1.01".
            pattern = (
                r"\bitem\s+" + re.escape(item) +
                r"(?!\d)\s*[.\-:]?\s*"
            )
            matches = list(re.finditer(pattern, lower, flags=re.IGNORECASE))

            if matches:
                snippets = []
                for match in matches[:2]:
                    start = max(0, match.start() - 100)
                    end = min(len(text), match.end() + 650)
                    snippets.append(text[start:end].strip())

                events.append({
                    "Item": item,
                    "Event": description,
                    "Occurrences": len(matches),
                    "Context": "\n\n".join(snippets)
                })

        return {
            "status": "Screened",
            "events": events,
            "limitation": (
                "Item detection is automated. A detected item is not a "
                "judgement of whether the event is positive or negative. "
                "Read the complete filing and exhibits."
            )
        }

    except Exception as exc:
        return {
            "status": "Analysis unavailable",
            "events": [],
            "limitation": str(exc)[:300]
        }

@st.cache_data(ttl=1800, show_spinner=False)
def get_watchlist_form4_transactions() -> pd.DataFrame:
    filings = get_watchlist_filings()

    if filings.empty:
        return pd.DataFrame()

    rows = []
    form4s = filings[filings["Form"] == "4"].head(100)

    for _, filing in form4s.iterrows():
        try:
            rows.extend(
                parse_form4_xml(filing["URL"], filing["Ticker"])
            )
        except Exception:
            continue

    df = pd.DataFrame(rows)

    if not df.empty:
        df["Transaction Date"] = pd.to_datetime(
            df["Transaction Date"], errors="coerce"
        )
        df = df.sort_values(
            ["Transaction Date", "Ticker"],
            ascending=[False, True]
        )

    return df
